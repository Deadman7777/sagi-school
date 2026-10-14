"""La proposition commerciale : établie depuis une fiche prospect, relue, envoyée.

Le modèle est celui de la proposition HG-IDM-2026 remise à l'Internat Daroul
Mouminati (octobre 2026) : synthèse, compréhension du besoin, lots, les trois
formules chiffrées côte à côte, modalités de paiement, calendrier et bloc
d'acceptation à remplir dans le PDF.

Ce qui est CALCULÉ ici et jamais saisi : la référence, les montants (catalogue
+ `catalogue.formules`), les dates. Ce qui est PERSONNALISABLE : l'en-tête
client, le contexte, les besoins, les résultats attendus, le programme, les
forfaits d'installation et de migration (le catalogue les annonce comme des
planchers).
"""
import re
import unicodedata
from datetime import date

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.licences import catalogue

from .messagerie import (envoyer_courriel, lien_whatsapp, pieces_bibliotheque,
                         signature_editeur)
from .models import (DocumentBibliotheque, InteractionProspect, ParametresFacturation,
                     PropositionCommerciale)

MOTS_VIDES = {'de', 'du', 'des', 'la', 'le', 'les', 'l', 'd', 'et', 'pour', 'au', 'aux',
              'en', 'a', 'un', 'une', 'sur', 'par'}

FORMULES_LIBELLES = dict(PropositionCommerciale.FORMULE_CHOICES)


class PropositionErreur(ValueError):
    """Refus lisible, montré tel quel à l'écran."""


def _sans_accents(texte):
    return ''.join(c for c in unicodedata.normalize('NFD', texte)
                   if unicodedata.category(c) != 'Mn')


def sigle(etablissement):
    """« Internat Daroul Mouminati » → « IDM » ; « École Sainte-Anne » → « ESA »."""
    mots = re.findall(r"[A-Za-z0-9]+", _sans_accents(etablissement or ''))
    lettres = ''.join(m[0].upper() for m in mots if m.lower() not in MOTS_VIDES)
    return lettres[:5] or 'CLI'


def prochaine_reference(etablissement, annee=None):
    """HG-IDM-2026, puis HG-IDM-2026-2 si l'établissement en a déjà une cette année."""
    base = f'HG-{sigle(etablissement)}-{annee or date.today().year}'
    if not PropositionCommerciale.objects.filter(reference=base).exists():
        return base
    rang = 2
    while PropositionCommerciale.objects.filter(reference=f'{base}-{rang}').exists():
        rang += 1
    return f'{base}-{rang}'


def edition_scolaire(jour=None):
    """L'année scolaire de la proposition : à partir d'août, la suivante commence."""
    jour = jour or date.today()
    debut = jour.year if jour.month >= 8 else jour.year - 1
    return f'{debut}–{debut + 1}'


def libelle_licence(type_licence):
    from apps.licences.models import Licence
    return dict(Licence.TYPE_CHOICES).get(type_licence, type_licence).upper()


def est_daara(type_licence, prospect=None):
    return (type_licence == 'TAXAWU_DAARA'
            or (prospect is not None and (prospect.type_organisation or '').lower() == 'daara'))


def textes_par_defaut(etablissement, type_licence, ville='', programme='', prospect=None):
    """Contexte, besoins et résultats proposés d'office — à personnaliser."""
    publics = 'apprenants' if est_daara(type_licence, prospect) else 'élèves'
    phrase_programme = (f" Il est admis au {programme}, au titre duquel la licence "
                        f"{libelle_licence(type_licence)} lui est proposée." if programme else '')
    contexte = (
        f"{etablissement} est un établissement d'enseignement"
        f"{' situé à ' + ville if ville else ''}.{phrase_programme}\n\n"
        f"Un établissement gère au quotidien des {publics}, des familles, des contributions "
        f"et des équipes. Disposer d'un outil numérique unique, fiable et accessible selon "
        f"des rôles définis permet de consacrer davantage de temps à la mission éducative.")
    besoins = [
        f"Centraliser les informations des {publics} et de leurs familles dans une base unique et sécurisée.",
        "Suivre mois par mois les paiements et les contributions, et identifier rapidement les retards.",
        "Disposer d'une vision claire et fiable pour le pilotage de l'établissement.",
        "Limiter les erreurs et les pertes de temps liées aux registres papier ou aux fichiers dispersés.",
        "Former les équipes afin qu'elles prennent rapidement l'outil en main.",
    ]
    resultats = [
        "Des données sécurisées, accessibles uniquement aux personnes habilitées.",
        "Un suivi mensuel lisible des paiements.",
        "Un gain de temps pour la Direction et les équipes administratives.",
        "Une équipe formée et autonome dès la mise en production.",
    ]
    return contexte, besoins, resultats


def etablir(prospect, type_licence, auteur=''):
    """Établit une proposition en BROUILLON, préremplie depuis la fiche prospect."""
    from apps.licences.models import Licence
    if type_licence not in dict(Licence.TYPE_CHOICES) or type_licence == 'ESSAI':
        raise PropositionErreur('Choisissez une licence payante.')

    programme = 'Programme TAXAWU DAARA' if type_licence == 'TAXAWU_DAARA' else ''
    contexte, besoins, resultats = textes_par_defaut(
        prospect.etablissement, type_licence, prospect.ville, programme, prospect)
    adresse = ', '.join(x for x in (prospect.adresse, prospect.ville) if x)
    telephones = ' · '.join(dict.fromkeys(
        x for x in (prospect.telephone, prospect.contact_telephone) if x))
    emails = ' · '.join(dict.fromkeys(x for x in (prospect.email, prospect.contact_email) if x))

    for tentative in range(3):
        try:
            with transaction.atomic():
                p = PropositionCommerciale.objects.create(
                    prospect=prospect,
                    reference=prochaine_reference(prospect.etablissement),
                    etablissement=prospect.etablissement,
                    adresse=adresse, telephones=telephones, email=emails,
                    autres_contacts=prospect.site_web or '',
                    a_l_attention=('La Direction' if not prospect.contact_fonction
                                   else f"{prospect.contact_nom}, {prospect.contact_fonction}".strip(', ')),
                    contact_nom=prospect.contact_nom or '',
                    type_licence=type_licence, programme=programme,
                    edition=edition_scolaire(),
                    prix_mensuel=catalogue.tarif_mensuel(type_licence),
                    taux_semestriel=catalogue.remise_semestrielle(),
                    taux_annuel=catalogue.remise_annuelle(),
                    frais_installation=catalogue.FRAIS_INSTALLATION,
                    frais_migration=catalogue.FRAIS_MIGRATION_MIN,
                    contexte=contexte, besoins=besoins, resultats=resultats,
                    validite_jours=catalogue.VALIDITE_DEVIS_JOURS,
                    etablie_par=auteur)
            break
        except IntegrityError:
            if tentative == 2:
                raise
    p.documents_joints.set(DocumentBibliotheque.objects.filter(actif=True, joindre_par_defaut=True))

    InteractionProspect.objects.create(
        prospect=prospect, canal='AUTRE', auteur=auteur or 'Serveur',
        resume=f"Proposition commerciale {p.reference} établie — licence "
               f"{libelle_licence(type_licence)}.")
    if prospect.statut in ('NOUVEAU', 'CONTACTE', 'QUALIFIE'):
        prospect.statut = 'DEVIS'
        prospect.save(update_fields=['statut', 'updated_at'])
    return p


def chiffrage(p):
    return catalogue.formules(p.prix_mensuel, p.taux_semestriel, p.taux_annuel,
                              p.frais_installation, p.frais_migration)


def francs(montant):
    """316000 → « 316 000 » (espace insécable : un montant ne se coupe pas)."""
    return f'{int(montant):,}'.replace(',', ' ')


def date_longue(jour):
    mois = ('janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août',
            'septembre', 'octobre', 'novembre', 'décembre')
    return f'{jour.day} {mois[jour.month - 1]} {jour.year}'


def nom_fichier(p):
    propre = re.sub(r'[^A-Za-z0-9]+', '_', _sans_accents(p.etablissement)).strip('_')[:40]
    suffixe = '-BROUILLON' if p.statut == 'BROUILLON' else ''
    return f'Proposition_{p.reference}_{propre}{suffixe}.pdf'


# ── Le courriel ─────────────────────────────────────────────────────────────

def courriel_par_defaut(p):
    """Sujet, corps et destinataires proposés à l'écran, modifiables avant l'envoi."""
    params = ParametresFacturation.actuels()
    licence = libelle_licence(p.type_licence)
    appel = f"Bonjour {p.contact_nom}," if p.contact_nom else "Madame, Monsieur,"
    pieces = [f"- la proposition commerciale {p.reference} (à compléter et nous retourner) ;"]
    pieces += [f"- {d.titre} ;" for d in p.documents_joints.filter(actif=True)]
    corps = (
        f"{appel}\n\n"
        f"À la suite de nos échanges, nous avons le plaisir de vous adresser notre proposition "
        f"commerciale {p.reference} pour la licence {licence} de SAGI SCHOOL"
        f"{' (' + p.programme + ')' if p.programme else ''}, destinée à {p.etablissement}.\n\n"
        f"Vous trouverez en pièces jointes :\n" + '\n'.join(pieces) + "\n\n"
        f"La proposition présente les trois formules (mensuelle, semestrielle et annuelle), "
        f"les montants correspondants et les conditions de paiement. Pour l'accepter, il "
        f"suffit d'ouvrir le PDF, de cocher la formule souhaitée, de renseigner le nom, la "
        f"fonction et la date, puis de nous renvoyer le fichier.\n\n"
        f"Elle est valable jusqu'au {date_longue(p.date_validite)}.\n\n"
        f"Nous restons à votre disposition pour toute question ou pour organiser une "
        f"démonstration.\n\n"
        f"Cordialement,\n\n{signature_editeur(params)}")
    return {
        'sujet': f"Proposition commerciale {p.reference} — Licence {licence} — {p.etablissement}",
        'corps': corps,
        'destinataires': ', '.join(re.split(r'\s*·\s*', p.email)) if p.email else '',
    }


def texte_whatsapp(p):
    params = ParametresFacturation.actuels()
    appel = f"Bonjour {p.contact_nom}" if p.contact_nom else "Bonjour"
    return (f"{appel}, ici {params.signataire_nom or 'HADY GESMAN'} de HADY GESMAN. "
            f"Nous venons de vous adresser par e-mail notre proposition commerciale "
            f"{p.reference} pour la licence {libelle_licence(p.type_licence)} de SAGI SCHOOL"
            f"{', avec nos brochures et notre catalogue' if p.documents_joints.exists() else ''}. "
            f"Elle est valable jusqu'au "
            f"{date_longue(p.date_validite)}. N'hésitez pas à nous écrire ici pour toute question.")


def whatsapp(p):
    return lien_whatsapp(p.telephones, texte_whatsapp(p))


def envoyer(p, destinataires, sujet, corps, documents, auteur=''):
    """Envoie la proposition validée (ou la renvoie). Rend les adresses servies."""
    from .proposition_pdf import rendre_pdf
    if p.statut not in ('VALIDEE', 'ENVOYEE'):
        raise PropositionErreur("Validez la proposition avant de l'envoyer.")
    pieces = [(nom_fichier(p), rendre_pdf(p), 'application/pdf')]
    pieces += pieces_bibliotheque(documents)
    params = ParametresFacturation.actuels()
    try:
        servis = envoyer_courriel(sujet, corps, destinataires, pieces,
                                  reply_to=params.email or None)
    except Exception as exc:
        p.erreur_envoi = str(exc)[:1000]
        p.save(update_fields=['erreur_envoi', 'updated_at'])
        raise
    p.statut = 'ENVOYEE'
    p.envoyee_le = timezone.now()
    p.envoyee_a = ', '.join(servis)[:500]
    p.erreur_envoi = ''
    p.save(update_fields=['statut', 'envoyee_le', 'envoyee_a', 'erreur_envoi', 'updated_at'])
    p.documents_joints.set(documents)
    if p.prospect_id:
        InteractionProspect.objects.create(
            prospect_id=p.prospect_id, canal='EMAIL', auteur=auteur or 'Serveur',
            resume=f"Proposition {p.reference} envoyée par e-mail à {p.envoyee_a} "
                   f"({len(pieces)} pièce(s) jointe(s)).")
    return servis
