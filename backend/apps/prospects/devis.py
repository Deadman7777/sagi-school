"""L'établissement d'un devis : ce que le serveur produit, et rien d'autre.

Deux règles gouvernent ce module, et elles expliquent tout le reste.

**Le serveur ne chiffre que ce dont il connaît le tarif.** La licence vient de
`apps.licences.catalogue` ; l'installation et les prestations sur mesure sont
saisies par un humain, parce que le catalogue les annonce « à partir de », ce
qui est un plancher et non un prix. Déduire un montant d'un plancher serait
exactement la faute que ce module existe pour empêcher.

**Ce qui est inclus vient du CODE.** La liste des modules portée par le devis
est produite par `apps.assistant.perimetre`, pas recopiée du catalogue
commercial — celui-ci annonce en licence Avancée une « gestion des emplois du
temps » qui n'existe nulle part dans le logiciel. Un devis signé qui la promet
nous engage à la livrer.
"""
import re
from datetime import date, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction

from apps.licences.catalogue import VALIDITE_DEVIS_JOURS, chiffrer

from .models import Devis, InteractionProspect

PREFIXE = 'HG-DEV'

# Trois tentatives suffisent : la collision suppose deux établissements de devis
# dans la même milliseconde, ce qui n'arrive qu'à deux commerciaux qui cliquent
# ensemble. Au-delà, mieux vaut une erreur qu'une boucle.
MAX_TENTATIVES = 3


def prochain_numero(annee=None):
    """Le numéro suivant pour l'année : HG-DEV-2026-0004.

    La séquence est GLOBALE — un devis appartient à HADY GESMAN, pas à une
    école — contrairement aux séquences du logiciel, qui sont par établissement.

    Elle démarre au-dessus des devis établis à la main avant l'existence de ce
    module : `HG-DEV-2026-0001` est le devis de référence du corpus commercial,
    et réattribuer son numéro créerait deux pièces différentes portant la même
    référence. D'où `DEVIS_NUMERO_MIN`.
    """
    annee = annee or date.today().year
    plancher = int(getattr(settings, 'DEVIS_NUMERO_MIN', 2))

    rangs = [plancher - 1]
    for numero in Devis.objects.filter(
            numero__startswith=f'{PREFIXE}-{annee}-').values_list('numero', flat=True):
        if trouve := re.search(r'(\d+)$', numero):
            rangs.append(int(trouve.group(1)))
    return f'{PREFIXE}-{annee}-{max(rangs) + 1:04d}'


def etablir(prospect, type_licence, cycle='ANNUEL', mois=12, auteur='',
            frais_installation=0, prestations='', montant_prestations=0,
            observations=''):
    """Établit un devis en BROUILLON à partir d'une fiche prospect.

    Les coordonnées sont RECOPIÉES depuis la fiche, pas référencées : le client
    corrige parfois son nom après coup, et une pièce déjà remise ne doit pas se
    réécrire toute seule.
    """
    chiffrage = chiffrer(type_licence, cycle, mois)
    aujourdhui = date.today()

    for tentative in range(MAX_TENTATIVES):
        try:
            with transaction.atomic():
                devis = Devis.objects.create(
                    prospect=prospect,
                    numero=prochain_numero(aujourdhui.year),
                    etablissement=prospect.etablissement,
                    ville=prospect.ville,
                    contact_nom=prospect.contact_nom,
                    contact_fonction=prospect.contact_fonction,
                    telephone=prospect.telephone or prospect.contact_telephone,
                    email=prospect.contact_email or prospect.email,
                    type_licence=type_licence,
                    cycle=chiffrage['cycle'],
                    mois=chiffrage['mois'],
                    prix_mensuel=chiffrage['prix_mensuel'],
                    montant_brut=chiffrage['montant_brut'],
                    taux_remise=chiffrage['taux_remise'],
                    montant_remise=chiffrage['montant_remise'],
                    montant_net=chiffrage['montant_net'],
                    frais_installation=frais_installation or 0,
                    prestations=prestations or '',
                    montant_prestations=montant_prestations or 0,
                    observations=observations or '',
                    date_emission=aujourdhui,
                    date_validite=aujourdhui + timedelta(days=VALIDITE_DEVIS_JOURS),
                    etabli_par=auteur)
            break
        except IntegrityError:                 # numéro pris entre-temps
            if tentative == MAX_TENTATIVES - 1:
                raise
    else:                                       # pragma: no cover — défensif
        raise IntegrityError('Numéro de devis introuvable après plusieurs essais.')

    # L'historique de la relation doit porter la trace de la proposition :
    # c'est là que le commercial qui rappelle ira voir ce qui a été promis.
    InteractionProspect.objects.create(
        prospect=prospect, canal='AUTRE', auteur=auteur or 'Serveur',
        resume=(f"Devis {devis.numero} établi — licence {type_licence}, "
                f"{devis.mois} mois, {int(devis.montant_total):,} F CFA. "
                f"Valable jusqu'au {devis.date_validite:%d/%m/%Y}."
                ).replace(',', ' '))

    # La proposition fait avancer l'affaire, sauf si elle était déjà tranchée.
    if prospect.statut in ('NOUVEAU', 'CONTACTE', 'QUALIFIE'):
        prospect.statut = 'DEVIS'
        prospect.save(update_fields=['statut', 'updated_at'])

    return devis


def modules_inclus(type_licence):
    """Ce que la licence ouvre réellement, pour l'imprimer sur le devis."""
    from apps.assistant.perimetre import modules_de
    return modules_de(type_licence)


def francs(montant):
    """243000 devient « 243 000 F ».

    L'espace est insécable : un montant coupé en fin de ligne — « 243 » puis
    « 000 F » à la ligne suivante — se lit comme deux nombres sur une pièce que
    le client vérifie. Django n'a pas de filtre qui groupe par espaces :
    `intcomma` pose des virgules, ce qui en franc CFA se lit comme des décimales.
    """
    return f'{int(montant):,}'.replace(',', '\u00a0') + '\u00a0F'


def contexte_pdf(devis):
    """Tout ce que le gabarit a besoin de savoir, calculé ici.

    Rien n'est calculé ni mis en forme dans le gabarit : une division posée
    dans un `{{ }}` finit par produire un montant que personne ne sait refaire.
    """
    from django.conf import settings

    from apps.licences.catalogue import MOYENS_PAIEMENT, REFERENCE_CATALOGUE
    from apps.licences.models import Licence

    modules = modules_inclus(devis.type_licence)
    # Deux colonnes équilibrées : xhtml2pdf ne sait pas répartir un flux en
    # colonnes, la répartition se fait donc en Python.
    milieu = (len(modules) + 1) // 2

    return {
        'devis': devis,
        'libelle_licence': dict(Licence.TYPE_CHOICES).get(devis.type_licence,
                                                          devis.type_licence),
        'libelle_cycle': 'Annuel' if devis.cycle == 'ANNUEL' else 'Mensuel',
        'pourcentage_remise': int(devis.taux_remise * 100),
        'montants': {
            'prix_mensuel':  francs(devis.prix_mensuel),
            'brut':          francs(devis.montant_brut),
            'installation':  francs(devis.frais_installation),
            'prestations':   francs(devis.montant_prestations),
            'avant_remise':  francs(devis.montant_brut + devis.frais_installation
                                    + devis.montant_prestations),
            'remise':        francs(devis.montant_remise),
            'total':         francs(devis.montant_total),
        },
        'modules_gauche': modules[:milieu],
        'modules_droite': modules[milieu:],
        'moyens_paiement': ', '.join(MOYENS_PAIEMENT),
        'reference_catalogue': REFERENCE_CATALOGUE,
        'editeur': {
            'telephone': getattr(settings, 'EDITEUR_TELEPHONE',
                                 '+221 70 328 61 51 · +221 78 429 78 30'),
            'email':     getattr(settings, 'LICENCE_SUPPORT_EMAIL',
                                 'contact@sagi-school.com'),
            'site':      getattr(settings, 'EDITEUR_SITE', 'sagi-school.com'),
            'ninea':     getattr(settings, 'EDITEUR_NINEA', '012673986'),
        },
    }


def rendre_pdf(devis):
    """Le devis en PDF. Rend (octets, erreur)."""
    from io import BytesIO

    from django.template.loader import render_to_string

    try:
        from xhtml2pdf import pisa
    except ImportError:                          # pragma: no cover
        return None, 'xhtml2pdf non installé'

    html = render_to_string('pdf/devis.html', contexte_pdf(devis))
    tampon = BytesIO()
    if pisa.CreatePDF(html, dest=tampon, encoding='utf-8').err:
        return None, 'Erreur de génération du PDF.'
    return tampon.getvalue(), None
