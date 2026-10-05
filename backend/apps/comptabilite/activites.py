"""Comptabilité multi-activité : enseignement, transport, restauration…

Un établissement ne vit pas que de la scolarité. Exemple rencontré en
démonstration (octobre 2026) : une école loue ses bus à des clients
extérieurs, sans rapport avec le ramassage de ses élèves. Ces recettes, et les
dépenses qui vont avec (carburant, chauffeurs, entretien), doivent se lire à
part, sans quitter la comptabilité générale.

Le principe tient en une règle : **l'activité est une dimension du grand
livre**, comme le projet. Chaque ligne d'écriture porte (ou non) son activité
(`JournalEntry.activite`) ; une ligne sans activité appartient à l'activité
principale. Les recettes, dépenses et résultat d'une activité s'obtiennent par
agrégation — il n'y a pas de second jeu de montants qui pourrait diverger.

Les opérations propres aux activités sont générées automatiquement à partir
du paramétrage de l'activité (compte de produit, compte client, régime TVA) :

  facture validée  : client (D, TTC) / produit (C, HT) / TVA facturée 4432 (C)
  règlement        : trésorerie selon le mode (D) / client (C)
  annulation       : extourne exacte de la facture (pièce ANNUL_FACT_ACT)
"""
import re
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.utils import timezone

from .models import Activite, FactureActivite, JournalEntry, ReglementFacture

COMPTE_TVA_FACTUREE = '4432'      # TVA facturée sur prestations de services
SOURCE_FACTURE = 'FACT_ACT'
SOURCE_REGLEMENT = 'REGL_ACT'
SOURCE_ANNULATION = 'ANNUL_FACT_ACT'

# Les activités proposées à la création d'un établissement : l'enseignement
# seul est créé d'office ; les autres sont des modèles que l'école active.
MODELES_ACTIVITES = {
    'ENSEIGNEMENT': {'libelle': 'Enseignement', 'compte_produit': '706', 'regime_tva': 'EXONERE'},
    'TRANSPORT':    {'libelle': 'Transport', 'compte_produit': '7062', 'compte_charge': '618',
                     'regime_tva': 'TAXABLE'},
    'RESTAURATION': {'libelle': 'Restauration', 'compte_produit': '7061', 'compte_charge': '604',
                     'regime_tva': 'EXONERE'},
    'HEBERGEMENT':  {'libelle': 'Hébergement / internat', 'compte_produit': '7064',
                     'regime_tva': 'EXONERE'},
    'PRESTATION':   {'libelle': 'Prestations externes', 'compte_produit': '7068',
                     'regime_tva': 'TAXABLE'},
    'LOCATION':     {'libelle': 'Location de locaux / matériel', 'compte_produit': '7083',
                     'regime_tva': 'TAXABLE'},
}


def _arrondi(valeur):
    return Decimal(str(valeur)).quantize(Decimal('1'), rounding=ROUND_HALF_UP) \
        if valeur is not None else Decimal('0')


def activite_principale(tenant):
    """L'activité principale de l'école (créée à la première demande).

    Une école qui n'a jamais ouvert ce module en a une quand même : toutes ses
    écritures non marquées lui appartiennent.
    """
    act = Activite.objects.filter(tenant=tenant, est_principale=True).first()
    if act is None:
        act, _ = Activite.objects.get_or_create(
            tenant=tenant, code='ENSEIGNEMENT',
            defaults={'libelle': 'Enseignement', 'type_activite': 'ENSEIGNEMENT',
                      'compte_produit': '706', 'regime_tva': 'EXONERE',
                      'est_principale': True})
        if not act.est_principale:
            act.est_principale = True
            act.save(update_fields=['est_principale'])
    return act


def resoudre_activite(tenant, activite_id):
    """L'activité désignée par l'identifiant, ou None. Lève ValueError si
    l'identifiant ne désigne aucune activité de l'école (jamais celle d'une
    autre école)."""
    if not activite_id:
        return None
    act = Activite.objects.filter(tenant=tenant, id=activite_id).first()
    if act is None:
        raise ValueError('Activité introuvable.')
    return act


def taux_tva(activite, date=None):
    """Taux de TVA (en %) applicable aux factures de l'activité."""
    if activite.regime_tva != 'TAXABLE':
        return Decimal('0')
    if activite.taux_tva is not None:
        return Decimal(activite.taux_tva)
    from apps.fiscal.parametres import valeur_parametre
    return Decimal(str(valeur_parametre('TVA_TAUX_NORMAL', activite.tenant, date, defaut=18)))


def calculer_montants(facture):
    """HT, TVA et TTC depuis les lignes de la facture (arrondis au franc)."""
    ht = Decimal('0')
    for l in facture.lignes or []:
        qte = Decimal(str(l.get('quantite') or 0))
        pu = Decimal(str(l.get('prix_unitaire') or 0))
        ht += qte * pu
    facture.montant_ht = _arrondi(ht)
    facture.taux_tva = taux_tva(facture.activite, facture.date_facture)
    facture.montant_tva = _arrondi(facture.montant_ht * facture.taux_tva / 100)
    facture.montant_ttc = facture.montant_ht + facture.montant_tva
    return facture


def _prochain_numero(tenant, prefixe, modele=FactureActivite, champ='numero'):
    """Numéro séquentiel PAR école (jamais global : deux écoles ont chacune leur
    FA-0001)."""
    dernier = (modele.objects.filter(tenant=tenant, **{f'{champ}__startswith': prefixe})
               .aggregate(m=Max(champ))['m'])
    nums = re.findall(r'\d+', dernier or '')
    return f"{prefixe}{int(nums[-1]) + 1 if nums else 1:04d}"


def _ecrire(tenant, exercice, no_piece, date, source, source_id, activite, lignes):
    for i, l in enumerate(lignes, start=1):
        JournalEntry.objects.create(
            tenant=tenant, exercice=exercice, no_piece=no_piece, date_ecriture=date,
            source=source, source_id=source_id, ordre=i, activite=activite, **l)


@transaction.atomic
def valider_facture(facture):
    """Numérote et comptabilise une facture brouillon."""
    if facture.statut != 'BROUILLON':
        raise ValueError('Seule une facture brouillon peut être validée.')
    if facture.exercice.cloture:
        raise ValueError("L'exercice de la facture est clôturé.")
    calculer_montants(facture)
    if facture.montant_ttc <= 0:
        raise ValueError('Une facture sans montant ne se valide pas.')
    act = facture.activite
    facture.numero = _prochain_numero(facture.tenant, 'FA-')
    lib = f"Facture {facture.numero} — {facture.client_nom}"
    lignes = [dict(no_compte=act.compte_client, debit=facture.montant_ttc, credit=0, libelle=lib),
              dict(no_compte=act.compte_produit, debit=0, credit=facture.montant_ht,
                   libelle=f"{act.libelle} — {lib}")]
    if facture.montant_tva > 0:
        lignes.append(dict(no_compte=COMPTE_TVA_FACTUREE, debit=0, credit=facture.montant_tva,
                           libelle=f"TVA facturée {facture.taux_tva:g} % — {lib}"))
    _ecrire(facture.tenant, facture.exercice, facture.numero, facture.date_facture,
            SOURCE_FACTURE, facture.id, act, lignes)
    facture.statut = 'VALIDEE'
    facture.date_validation = timezone.now()
    facture.save()
    return facture


@transaction.atomic
def regler_facture(facture, montant, date, mode='ESPECE', reference='', exercice=None):
    """Encaisse tout ou partie d'une facture validée."""
    from .tresorerie import lignes_tresorerie

    if facture.statut not in ('VALIDEE', 'PARTIEL'):
        raise ValueError("Seule une facture validée et non soldée peut être réglée.")
    montant = _arrondi(montant)
    if montant <= 0:
        raise ValueError('Montant invalide.')
    if float(montant) > facture.reste_a_regler + 0.01:
        raise ValueError(f"Règlement ({montant:,.0f}) supérieur au reste à régler "
                         f"({facture.reste_a_regler:,.0f}).")
    exercice = exercice or facture.exercice
    if exercice.cloture:
        raise ValueError("L'exercice du règlement est clôturé.")
    act = facture.activite
    no_piece = _prochain_numero(facture.tenant, 'RFA-', ReglementFacture, 'no_piece')
    reg = ReglementFacture.objects.create(
        tenant=facture.tenant, facture=facture, exercice=exercice, date_reglement=date,
        montant=montant, mode=mode, reference=reference, no_piece=no_piece)
    lib = f"Règlement {facture.numero} — {facture.client_nom}" + (f" ({reference})" if reference else '')
    tresor = lignes_tresorerie([{'mode': mode, 'montant': float(montant)}], 'debit', lib, ordre_debut=1)
    for l in tresor:
        l.pop('ordre', None)
    lignes = tresor + [dict(no_compte=act.compte_client, debit=0, credit=montant, libelle=lib)]
    _ecrire(facture.tenant, exercice, no_piece, date, SOURCE_REGLEMENT, reg.id, act, lignes)
    facture.montant_regle = Decimal(facture.montant_regle) + montant
    facture.statut = 'PAYEE' if facture.reste_a_regler <= 0.01 else 'PARTIEL'
    facture.save(update_fields=['montant_regle', 'statut', 'updated_at'])
    return reg


@transaction.atomic
def annuler_facture(facture, motif=''):
    """Extourne une facture validée sans règlement. Brouillon : supprimé."""
    if facture.statut == 'BROUILLON':
        facture.delete()
        return None
    if facture.statut == 'ANNULEE':
        raise ValueError('Facture déjà annulée.')
    if facture.reglements.filter(annule=False).exists():
        raise ValueError("Cette facture a reçu des règlements : annulez d'abord les règlements, "
                         "ou émettez un avoir.")
    exercice = facture.exercice
    if exercice.cloture:
        raise ValueError("L'exercice de la facture est clôturé : passez l'annulation "
                         "par une écriture sur l'exercice courant.")
    origine = list(JournalEntry.objects.filter(tenant=facture.tenant, source=SOURCE_FACTURE,
                                               source_id=facture.id))
    no_piece = f"AN-{facture.numero}"
    for e in origine:
        JournalEntry.objects.create(
            tenant=facture.tenant, exercice=exercice, no_piece=no_piece,
            date_ecriture=timezone.localdate(), source=SOURCE_ANNULATION, source_id=facture.id,
            ordre=e.ordre, no_compte=e.no_compte, debit=e.credit, credit=e.debit,
            libelle=f"ANNULATION — {e.libelle}" + (f" ({motif})" if motif else ''),
            activite=e.activite, projet=e.projet)
    facture.statut = 'ANNULEE'
    facture.observations = (facture.observations + f"\nAnnulée : {motif}").strip()
    facture.save(update_fields=['statut', 'observations', 'updated_at'])
    return facture


@transaction.atomic
def annuler_reglement(reglement):
    """Extourne un règlement (chèque impayé, erreur de saisie)."""
    if reglement.annule:
        raise ValueError('Règlement déjà annulé.')
    if reglement.exercice.cloture:
        raise ValueError("L'exercice du règlement est clôturé.")
    for e in JournalEntry.objects.filter(tenant=reglement.tenant, source=SOURCE_REGLEMENT,
                                         source_id=reglement.id):
        JournalEntry.objects.create(
            tenant=reglement.tenant, exercice=reglement.exercice,
            no_piece=f"AN-{reglement.no_piece}", date_ecriture=timezone.localdate(),
            source='ANNUL_' + SOURCE_REGLEMENT, source_id=reglement.id, ordre=e.ordre,
            no_compte=e.no_compte, debit=e.credit, credit=e.debit,
            libelle=f"ANNULATION — {e.libelle}", activite=e.activite)
    reglement.annule = True
    reglement.save(update_fields=['annule', 'updated_at'])
    f = reglement.facture
    f.montant_regle = Decimal(f.montant_regle) - Decimal(reglement.montant)
    f.statut = 'VALIDEE' if f.montant_regle <= 0 else 'PARTIEL'
    f.save(update_fields=['montant_regle', 'statut', 'updated_at'])
    return reglement


def resultats_par_activite(tenant, exercice):
    """Produits, charges et résultat de chaque activité sur l'exercice.

    Mêmes conventions que le compte de résultat (apps/comptabilite/resultat.py) :
    montants NETS (une annulation se déduit), classes 6/7 et HAO 8 hors 890
    (le compte d'à-nouveaux n'est pas un résultat). Les lignes sans activité
    vont à l'activité principale. La somme des résultats par activité est
    donc, au franc près, le résultat net de l'exercice.
    """
    from .resultat import totaux_resultat

    principale = activite_principale(tenant)
    activites = {a.id: a for a in Activite.objects.filter(tenant=tenant)}
    q_prod = Q(no_compte__startswith='7') | Q(no_compte__startswith='82') | \
        Q(no_compte__startswith='84') | Q(no_compte__startswith='86') | Q(no_compte__startswith='88')
    q_chg = Q(no_compte__startswith='6') | Q(no_compte__startswith='81') | \
        Q(no_compte__startswith='83') | Q(no_compte__startswith='85') | \
        Q(no_compte__startswith='87') | Q(no_compte__startswith='89')
    base = JournalEntry.objects.filter(tenant=tenant, exercice=exercice).exclude(no_compte='890')

    par = {a_id: {'produits': 0.0, 'charges': 0.0} for a_id in activites}

    def cumuler(qs, cle, sens):
        for r in qs.values('activite_id').annotate(d=Sum('debit'), c=Sum('credit')):
            a_id = r['activite_id'] or principale.id
            d, c = float(r['d'] or 0), float(r['c'] or 0)
            par.setdefault(a_id, {'produits': 0.0, 'charges': 0.0})
            par[a_id][cle] += (c - d) if sens == 'credit' else (d - c)

    cumuler(base.filter(q_prod), 'produits', 'credit')
    cumuler(base.filter(q_chg), 'charges', 'debit')

    factures = (FactureActivite.objects.filter(tenant=tenant, exercice=exercice)
                .exclude(statut__in=('BROUILLON', 'ANNULEE'))
                .values('activite_id').annotate(nb=Count('id'), ttc=Sum('montant_ttc'),
                                                regle=Sum('montant_regle')))
    fact = {f['activite_id']: f for f in factures}

    lignes = []
    for a_id, v in par.items():
        a = activites.get(a_id)
        if a is None:
            continue
        if not a.actif and not (v['produits'] or v['charges']):
            continue
        f = fact.get(a_id, {})
        lignes.append({
            'activite_id': str(a.id), 'code': a.code, 'libelle': a.libelle,
            'type_activite': a.type_activite, 'est_principale': a.est_principale,
            'produits': round(v['produits'], 2), 'charges': round(v['charges'], 2),
            'resultat': round(v['produits'] - v['charges'], 2),
            'marge': round((v['produits'] - v['charges']) / v['produits'] * 100, 1)
                     if v['produits'] > 0 else None,
            'factures_ttc': round(float(f.get('ttc') or 0), 2),
            'creances': round(float(f.get('ttc') or 0) - float(f.get('regle') or 0), 2),
        })
    lignes.sort(key=lambda l: (not l['est_principale'], l['libelle']))
    totaux = totaux_resultat(JournalEntry.objects.filter(tenant=tenant, exercice=exercice))
    return {
        'activites': lignes,
        'total_produits': round(sum(l['produits'] for l in lignes), 2),
        'total_charges': round(sum(l['charges'] for l in lignes), 2),
        'total_resultat': round(sum(l['resultat'] for l in lignes), 2),
        # Contrôle : le résultat de l'exercice tel que le calcule le compte de
        # résultat. Un écart signale une écriture hors des conventions.
        'resultat_exercice': totaux['resultat_net'],
    }
