"""Facturation commerciale de HADY GESMAN : proformas, factures, avoirs, reçus.

Trois règles, qui expliquent tout le module.

**Une pièce émise ne bouge plus.** Brouillon modifiable, puis émission : le
numéro est attribué, les montants et le client sont figés. Une facture fausse
se corrige par un avoir, jamais par une retouche — le client a déjà l'original.

**La numérotation est continue.** Un numéro n'est attribué qu'à l'émission, dans
une séquence annuelle par type (HG-FAC-2026-0001, 0002…). Un brouillon supprimé
ne laisse donc aucun trou.

**Le serveur calcule, l'écran affiche.** Montant de ligne, total HT, TVA, TTC,
solde d'une facture : tout est calculé ici, une seule fois. Le franc CFA n'a
pas de centimes : chaque montant est arrondi au franc, la TVA sur le total HT.
"""
import re
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (MODES_ENCAISSEMENT, DocumentCommercial, Encaissement, InteractionProspect,
                     LigneDocument, ParametresFacturation)

MAX_TENTATIVES = 3
PREFIXE_RECU = 'HG-REC'


class FacturationErreur(ValueError):
    """Une opération refusée, avec un message destiné à l'utilisateur."""


def franc(valeur):
    return Decimal(str(valeur or 0)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)


# ── Numérotation ─────────────────────────────────────────────────────────

def _prochain(prefixe, annee, valeurs):
    rangs = [0]
    for numero in valeurs:
        if trouve := re.search(r'(\d+)$', numero or ''):
            rangs.append(int(trouve.group(1)))
    return f'{prefixe}-{annee}-{max(rangs) + 1:04d}'


def prochain_numero_document(type_doc, annee):
    prefixe = DocumentCommercial.PREFIXES[type_doc]
    valeurs = DocumentCommercial.objects.filter(
        numero__startswith=f'{prefixe}-{annee}-').values_list('numero', flat=True)
    return _prochain(prefixe, annee, valeurs)


def prochain_numero_recu(annee):
    valeurs = Encaissement.objects.filter(
        numero__startswith=f'{PREFIXE_RECU}-{annee}-').values_list('numero', flat=True)
    return _prochain(PREFIXE_RECU, annee, valeurs)


# ── Calcul ───────────────────────────────────────────────────────────────

def recalculer(document):
    """Recalcule chaque ligne et les totaux d'un brouillon, puis enregistre."""
    total_ht = Decimal('0')
    for ligne in document.lignes.all():
        montant = franc(Decimal(ligne.quantite) * Decimal(ligne.prix_unitaire))
        if ligne.montant != montant:
            ligne.montant = montant
            ligne.save(update_fields=['montant', 'updated_at'])
        total_ht += montant
    document.total_ht = total_ht
    document.montant_tva = (franc(total_ht * Decimal(document.taux_tva) / 100)
                            if document.tva_applicable else Decimal('0'))
    document.total_ttc = document.total_ht + document.montant_tva
    document.save(update_fields=['total_ht', 'montant_tva', 'total_ttc', 'updated_at'])
    return document


def remplacer_lignes(document, lignes):
    """Remplace les lignes d'un brouillon par `lignes` (liste de dicts)."""
    if not document.modifiable:
        raise FacturationErreur('Une pièce émise ne se modifie plus.')
    document.lignes.all().delete()
    for i, l in enumerate(lignes):
        designation = str(l.get('designation') or '').strip()[:250]
        if not designation:
            continue
        try:
            quantite = Decimal(str(l.get('quantite') if l.get('quantite') not in (None, '') else 1))
            prix = franc(l.get('prix_unitaire'))
        except Exception:
            raise FacturationErreur(f'Ligne « {designation} » : quantité ou prix invalide.')
        if quantite <= 0:
            raise FacturationErreur(f'Ligne « {designation} » : la quantité doit être positive.')
        LigneDocument.objects.create(
            document=document, ordre=i, designation=designation,
            detail=str(l.get('detail') or '').strip()[:2000],
            quantite=quantite, unite=str(l.get('unite') or '').strip()[:30],
            prix_unitaire=prix)
    return recalculer(document)


# ── Création des brouillons ──────────────────────────────────────────────

def _client_depuis_prospect(p):
    return {
        'client_nom':       p.etablissement,
        'client_contact':   ' — '.join(x for x in (p.contact_nom, p.contact_fonction) if x),
        'client_adresse':   p.adresse,
        'client_ville':     p.ville,
        'client_telephone': p.contact_telephone or p.telephone,
        'client_email':     p.contact_email or p.email,
    }


def _client_depuis_tenant(t):
    return {
        'client_nom':       t.nom,
        'client_adresse':   t.adresse,
        'client_ville':     t.ville,
        'client_telephone': t.telephone,
        'client_email':     t.email,
        'client_ninea':     t.ninea,
    }


def _tracer(document, resume, auteur):
    if document.prospect_id:
        InteractionProspect.objects.create(prospect=document.prospect, canal='AUTRE',
                                           auteur=auteur or 'Serveur', resume=resume)


def creer_brouillon(type_doc, auteur='', prospect=None, tenant=None, devis=None,
                    origine=None, client=None, lignes=None, objet='', observations=''):
    """Un brouillon, client recopié depuis la source la plus précise disponible."""
    if type_doc not in DocumentCommercial.PREFIXES:
        raise FacturationErreur('Type de document inconnu.')
    params = ParametresFacturation.actuels()

    champs = {}
    if origine is not None:
        champs = {f: getattr(origine, f) for f in (
            'client_nom', 'client_contact', 'client_adresse', 'client_ville',
            'client_telephone', 'client_email', 'client_ninea')}
        prospect = prospect or origine.prospect
        tenant = tenant or origine.tenant
        devis = devis or origine.devis
    elif prospect is not None:
        champs = _client_depuis_prospect(prospect)
    elif tenant is not None:
        champs = _client_depuis_tenant(tenant)
    champs.update({k: v for k, v in (client or {}).items() if v not in (None, '')})
    if not str(champs.get('client_nom') or '').strip():
        raise FacturationErreur('Le nom du client est obligatoire.')

    # Un avoir reprend la TVA de la facture qu'il corrige, pas le réglage du jour.
    if type_doc == 'AVOIR' and origine is not None:
        tva = {'tva_applicable': origine.tva_applicable, 'taux_tva': origine.taux_tva,
               'mention_tva': origine.mention_tva}
    else:
        tva = {'tva_applicable': params.tva_applicable, 'taux_tva': params.taux_tva,
               'mention_tva': '' if params.tva_applicable else params.mention_sans_tva}

    document = DocumentCommercial.objects.create(
        type=type_doc, prospect=prospect, tenant=tenant, devis=devis, origine=origine,
        objet=objet[:250], observations=observations, conditions=params.conditions,
        etabli_par=auteur, **tva, **{k: str(v)[:300] for k, v in champs.items()})
    remplacer_lignes(document, lignes or [])
    return document


def lignes_depuis_devis(devis):
    """Les lignes d'un devis : la remise reste sur sa propre ligne."""
    from apps.licences.models import Licence
    libelle = dict(Licence.TYPE_CHOICES).get(devis.type_licence, devis.type_licence)
    lignes = [{
        'designation': f'Licence SAGI SCHOOL {libelle}',
        'detail': f'Abonnement {devis.mois} mois — devis {devis.numero}',
        'quantite': devis.mois, 'unite': 'mois', 'prix_unitaire': devis.prix_mensuel,
    }]
    if devis.montant_remise:
        pct = int(Decimal(devis.taux_remise) * 100)
        lignes.append({'designation': f'Remise paiement annuel ({pct} %)',
                       'quantite': 1, 'prix_unitaire': -devis.montant_remise})
    if devis.frais_installation:
        lignes.append({'designation': 'Déploiement et intégration',
                       'detail': 'Installation, reprise des données, formation des utilisateurs.',
                       'quantite': 1, 'prix_unitaire': devis.frais_installation})
    if devis.montant_prestations or devis.prestations:
        lignes.append({'designation': 'Prestations complémentaires',
                       'detail': devis.prestations, 'quantite': 1,
                       'prix_unitaire': devis.montant_prestations})
    return lignes


def depuis_devis(devis, type_doc, auteur=''):
    if devis.statut not in ('VALIDE', 'ENVOYE', 'ACCEPTE'):
        raise FacturationErreur("Seul un devis validé peut être repris dans une facture.")
    if type_doc == 'FACTURE' and devis.statut != 'ACCEPTE':
        raise FacturationErreur("Une facture se fonde sur un devis accepté. "
                                "Pour un devis encore en attente, établissez une proforma.")
    document = creer_brouillon(type_doc, auteur=auteur, prospect=devis.prospect, devis=devis,
                               lignes=lignes_depuis_devis(devis),
                               objet=f'Licence SAGI SCHOOL — devis {devis.numero}')
    # Les coordonnées figées sur le devis priment sur la fiche, peut-être retouchée depuis.
    for champ, source in (('client_nom', 'etablissement'), ('client_ville', 'ville'),
                          ('client_telephone', 'telephone'), ('client_email', 'email')):
        if getattr(devis, source):
            setattr(document, champ, getattr(devis, source))
    document.save()
    return document


def lignes_renouvellement(tenant, mois=12):
    """Renouvellement d'une école cliente, chiffré depuis le catalogue."""
    from apps.licences.catalogue import chiffrer
    from apps.licences.models import Licence
    licence = Licence.objects.filter(tenant=tenant).first()
    if licence is None or licence.type == 'ESSAI':
        raise FacturationErreur("Cette école n'a pas de licence payante à renouveler.")
    cycle = 'ANNUEL' if mois >= 12 else 'MENSUEL'
    c = chiffrer(licence.type, cycle, mois)
    debut = max(licence.date_fin + timedelta(days=1), date.today())
    fin = _ajouter_mois(debut, mois) - timedelta(days=1)
    libelle = dict(Licence.TYPE_CHOICES).get(licence.type, licence.type)
    lignes = [{
        'designation': f'Licence SAGI SCHOOL {libelle}',
        'detail': f'Renouvellement du {debut:%d/%m/%Y} au {fin:%d/%m/%Y}',
        'quantite': c['mois'], 'unite': 'mois', 'prix_unitaire': c['prix_mensuel'],
    }]
    if c['montant_remise']:
        lignes.append({'designation': f"Remise paiement annuel ({int(c['taux_remise'] * 100)} %)",
                       'quantite': 1, 'prix_unitaire': -c['montant_remise']})
    return lignes


def _ajouter_mois(jour, mois):
    import calendar
    annee = jour.year + (jour.month - 1 + mois) // 12
    m = (jour.month - 1 + mois) % 12 + 1
    return date(annee, m, min(jour.day, calendar.monthrange(annee, m)[1]))


def convertir_proforma(proforma, auteur=''):
    """La facture définitive d'une proforma émise : brouillon, lignes reprises."""
    if proforma.type != 'PROFORMA' or proforma.statut != 'EMIS':
        raise FacturationErreur('Seule une proforma émise se convertit en facture.')
    if proforma.derives.filter(type='FACTURE').exists():
        raise FacturationErreur('Cette proforma a déjà sa facture.')
    return creer_brouillon('FACTURE', auteur=auteur, origine=proforma, objet=proforma.objet,
                           lignes=_copier_lignes(proforma))


def preparer_avoir(facture, auteur='', motif=''):
    """Un avoir en brouillon : par défaut il annule toute la facture ; on
    réduit les lignes pour un avoir partiel."""
    if facture.type != 'FACTURE' or facture.statut != 'EMIS':
        raise FacturationErreur('Un avoir corrige une facture émise.')
    document = creer_brouillon('AVOIR', auteur=auteur, origine=facture,
                               objet=f'Avoir sur facture {facture.numero}',
                               lignes=_copier_lignes(facture))
    document.motif = motif
    document.save(update_fields=['motif', 'updated_at'])
    return document


def _copier_lignes(document):
    return [{'designation': l.designation, 'detail': l.detail, 'quantite': l.quantite,
             'unite': l.unite, 'prix_unitaire': l.prix_unitaire}
            for l in document.lignes.all()]


# ── Émission ─────────────────────────────────────────────────────────────

def emettre(document, auteur=''):
    """Attribue le numéro et fige la pièce."""
    if not document.modifiable:
        raise FacturationErreur('Cette pièce est déjà émise.')
    recalculer(document)
    if not document.lignes.exists():
        raise FacturationErreur('Ajoutez au moins une ligne avant d’émettre.')
    if document.total_ttc <= 0:
        raise FacturationErreur('Le montant total doit être positif.')

    if document.type == 'AVOIR':
        facture = document.origine
        if facture is None or facture.type != 'FACTURE' or facture.statut != 'EMIS':
            raise FacturationErreur('Un avoir doit se rattacher à une facture émise.')
        disponible = facture.total_ttc - facture.montant_avoirs
        if document.total_ttc > disponible:
            raise FacturationErreur(
                f"L'avoir dépasse ce qui reste à corriger sur la facture {facture.numero} "
                f"({int(disponible)} F).")
        if not document.motif.strip():
            raise FacturationErreur("Indiquez le motif de l'avoir.")

    params = ParametresFacturation.actuels()
    aujourdhui = date.today()
    for tentative in range(MAX_TENTATIVES):
        try:
            with transaction.atomic():
                document.numero = prochain_numero_document(document.type, aujourdhui.year)
                document.statut = 'EMIS'
                document.date_emission = aujourdhui
                if document.type == 'FACTURE' and document.date_echeance is None:
                    document.date_echeance = aujourdhui + timedelta(days=params.delai_paiement_jours)
                if document.type == 'PROFORMA' and document.date_validite is None:
                    document.date_validite = aujourdhui + timedelta(days=params.validite_proforma_jours)
                document.emis_par = auteur
                document.emis_le = timezone.now()
                document.save()
            break
        except IntegrityError:
            document.numero = ''
            if tentative == MAX_TENTATIVES - 1:
                raise

    if document.type == 'FACTURE' and document.origine and document.origine.type == 'PROFORMA':
        document.origine.statut = 'CONVERTI'
        document.origine.save(update_fields=['statut', 'updated_at'])

    libelle = dict(DocumentCommercial.TYPE_CHOICES)[document.type]
    _tracer(document, f"{libelle} {document.numero} émise — {int(document.total_ttc):,} F."
            .replace(',', ' '), auteur)
    return document


# ── Encaissements ────────────────────────────────────────────────────────

def encaisser(facture, montant, mode='VIREMENT', jour=None, reference='', observations='',
              auteur=''):
    if facture.type != 'FACTURE' or facture.statut != 'EMIS':
        raise FacturationErreur('Un paiement se rattache à une facture émise.')
    montant = franc(montant)
    if montant <= 0:
        raise FacturationErreur('Le montant encaissé doit être positif.')
    if montant > facture.solde:
        raise FacturationErreur(
            f'Le montant dépasse le reste à payer ({int(max(facture.solde, 0))} F).')
    jour = jour or date.today()
    if jour > date.today():
        raise FacturationErreur("La date d'un encaissement ne peut pas être dans le futur.")

    for tentative in range(MAX_TENTATIVES):
        try:
            with transaction.atomic():
                recu = Encaissement.objects.create(
                    facture=facture, numero=prochain_numero_recu(jour.year), date=jour,
                    montant=montant, mode=mode, reference=reference[:120],
                    observations=observations, recu_par=auteur)
            break
        except IntegrityError:
            if tentative == MAX_TENTATIVES - 1:
                raise
    _tracer(facture, f"Paiement de {int(montant):,} F reçu sur {facture.numero} "
                     f"(reçu {recu.numero}).".replace(',', ' '), auteur)
    return recu


def annuler_encaissement(recu, motif, auteur=''):
    if recu.annule:
        raise FacturationErreur('Ce reçu est déjà annulé.')
    if not (motif or '').strip():
        raise FacturationErreur("Indiquez le motif de l'annulation.")
    recu.annule = True
    recu.annule_motif = motif.strip()[:250]
    recu.annule_le = timezone.now()
    recu.save(update_fields=['annule', 'annule_motif', 'annule_le', 'updated_at'])
    _tracer(recu.facture, f"Reçu {recu.numero} annulé : {recu.annule_motif}", auteur)
    return recu


# ── Tableau de bord ──────────────────────────────────────────────────────

def synthese():
    """Facturé, encaissé, restant dû et en retard — sur les factures émises."""
    factures = list(DocumentCommercial.objects.filter(type='FACTURE', statut='EMIS')
                    .prefetch_related('encaissements', 'derives'))
    facture = sum((f.total_ttc - f.montant_avoirs for f in factures), Decimal('0'))
    encaisse = sum((f.montant_encaisse for f in factures), Decimal('0'))
    impayees = [f for f in factures if f.statut_paiement in ('A_PAYER', 'PARTIELLE')]
    retard = [f for f in impayees if f.en_retard]
    return {
        'facture':          int(facture),
        'encaisse':         int(encaisse),
        'restant':          int(sum((f.solde for f in impayees), Decimal('0'))),
        'nb_impayees':      len(impayees),
        'en_retard':        int(sum((f.solde for f in retard), Decimal('0'))),
        'nb_en_retard':     len(retard),
    }


# ── PDF ──────────────────────────────────────────────────────────────────

def montant_en_lettres(valeur):
    """243000 → « deux cent quarante-trois mille francs CFA »."""
    n = int(valeur)
    if n in (0, 1):
        return f"{'zéro' if n == 0 else 'un'} franc CFA"
    # « un million DE francs », mais « un million cent mille francs »
    liaison = ' de' if n % 1_000_000 == 0 else ''
    return f'{_lettres(n)}{liaison} francs CFA'


_UNITES = ['zéro', 'un', 'deux', 'trois', 'quatre', 'cinq', 'six', 'sept', 'huit', 'neuf', 'dix',
           'onze', 'douze', 'treize', 'quatorze', 'quinze', 'seize']
_DIZAINES = {2: 'vingt', 3: 'trente', 4: 'quarante', 5: 'cinquante', 6: 'soixante'}


def _moins_de_cent(n):
    if n <= 16:
        return _UNITES[n]
    if n < 20:
        return 'dix-' + _UNITES[n - 10]
    d, u = divmod(n, 10)
    if d in (7, 9):
        base = 'soixante' if d == 7 else 'quatre-vingt'
        reste = 10 + u
        liaison = ' et ' if (d == 7 and u == 1) else '-'
        return base + liaison + _moins_de_cent(reste)
    if d == 8:
        return 'quatre-vingts' if u == 0 else 'quatre-vingt-' + _UNITES[u]
    if u == 0:
        return _DIZAINES[d]
    return _DIZAINES[d] + (' et un' if u == 1 else '-' + _UNITES[u])


def _moins_de_mille(n):
    c, r = divmod(n, 100)
    if c == 0:
        return _moins_de_cent(r)
    tete = 'cent' if c == 1 else f'{_UNITES[c]} cent'
    if r == 0:
        return tete + ('s' if c > 1 else '')
    return f'{tete} {_moins_de_cent(r)}'


def _lettres(n):
    parties = []
    for valeur, nom in ((1_000_000_000, 'milliard'), (1_000_000, 'million')):
        q, n = divmod(n, valeur)
        if q:
            parties.append(f"{_lettres(q)} {nom}{'s' if q > 1 else ''}")
    q, n = divmod(n, 1000)
    if q:
        # « deux cents » et « quatre-vingts » perdent leur s devant « mille »
        tete = _moins_de_mille(q)
        if tete.endswith('cents') or tete.endswith('vingts'):
            tete = tete[:-1]
        parties.append('mille' if q == 1 else f'{tete} mille')
    if n:
        parties.append(_moins_de_mille(n))
    return ' '.join(parties)


def francs(montant):
    """Espace insécable : un montant coupé en fin de ligne se lit comme deux nombres."""
    signe = '− ' if int(montant) < 0 else ''
    return signe + f'{abs(int(montant)):,}'.replace(',', ' ') + ' F'


def _quantite(q):
    q = Decimal(q)
    return f'{q:.2f}'.rstrip('0').rstrip('.').replace('.', ',')


def contexte_document(document):
    params = ParametresFacturation.actuels()
    titres = {'PROFORMA': 'FACTURE PROFORMA', 'FACTURE': 'FACTURE', 'AVOIR': 'AVOIR'}
    return {
        'doc': document,
        'titre': titres[document.type],
        'emetteur': params,
        'lignes': [{
            'designation': l.designation, 'detail': l.detail,
            'quantite': _quantite(l.quantite) + (f' {l.unite}' if l.unite else ''),
            'prix_unitaire': francs(l.prix_unitaire), 'montant': francs(l.montant),
        } for l in document.lignes.all()],
        'montants': {
            'ht': francs(document.total_ht), 'tva': francs(document.montant_tva),
            'ttc': francs(document.total_ttc),
            'encaisse': francs(document.montant_encaisse),
            'avoirs': francs(document.montant_avoirs),
            'solde': francs(max(document.solde, 0)),
        },
        'taux_tva': _quantite(document.taux_tva),
        'en_lettres': montant_en_lettres(document.total_ttc),
        'modes': ', '.join(label for code, label in MODES_ENCAISSEMENT if code != 'AUTRE'),
    }


def contexte_recu(recu):
    params = ParametresFacturation.actuels()
    facture = recu.facture
    # La situation AU MOMENT du paiement : un reçu réimprimé plus tard doit dire
    # la même chose que l'original remis au client.
    anterieurs = sum((e.montant for e in facture.encaissements.filter(annule=False)
                      if (e.date, e.created_at) < (recu.date, recu.created_at)), Decimal('0'))
    avoirs = sum((a.total_ttc for a in facture.derives.filter(type='AVOIR', statut='EMIS')
                  if a.emis_le and a.emis_le <= recu.created_at), Decimal('0'))
    reste = facture.total_ttc - avoirs - anterieurs - (0 if recu.annule else recu.montant)
    return {
        'recu': recu, 'facture': facture, 'emetteur': params,
        'mode': recu.get_mode_display(),
        'montants': {'montant': francs(recu.montant), 'facture': francs(facture.total_ttc),
                     'avoirs': francs(avoirs), 'anterieurs': francs(anterieurs),
                     'reste': francs(max(reste, 0))},
        'reste_nul': reste <= 0,
        'avoirs_au_paiement': avoirs,
        'en_lettres': montant_en_lettres(recu.montant),
    }


def rendre_pdf(gabarit, contexte):
    from io import BytesIO
    from django.template.loader import render_to_string
    from xhtml2pdf import pisa
    html = render_to_string(gabarit, contexte)
    tampon = BytesIO()
    if pisa.CreatePDF(html, dest=tampon, encoding='utf-8').err:
        raise FacturationErreur('Erreur de génération du PDF.')
    return tampon.getvalue()
