"""Création d'une école cliente par HADY GESMAN : validation, puis tout ou rien.

**Chaque champ est vérifié avant d'écrire.** Une valeur trop longue ne doit
plus remonter de la base en erreur 500, que l'écran traduisait par un
« Impossible de créer l'école » sans cause : on ne savait pas quel champ
corriger, sur place, devant le client.

**L'école, sa licence et son exercice naissent ensemble.** Si l'un échoue,
rien n'est enregistré : pas d'école orpheline sans licence, qui réapparaîtrait
en double au second essai.
"""
from datetime import date

from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction

from apps.paiements.models import Exercice
from apps.tenants.models import Tenant

from .models import Licence

# Champ du formulaire → libellé montré à l'utilisateur.
CHAMPS_TENANT = {
    'nom': 'Nom', 'ville': 'Ville', 'adresse': 'Adresse', 'telephone': 'Téléphone',
    'email': 'Email', 'rccm': 'RCCM', 'ninea': 'NINEA',
    'code_etablissement': 'Code établissement',
}


class CreationEcoleErreur(ValueError):
    """Refus lisible : le message dit quel champ corriger."""


def _texte(data, champ):
    return str(data.get(champ) or '').strip()


def _date(valeur, libelle):
    try:
        return date.fromisoformat(str(valeur)[:10])
    except (TypeError, ValueError):
        raise CreationEcoleErreur(f'{libelle} : date invalide.')


def valider(data):
    """Les valeurs nettoyées, ou CreationEcoleErreur sur le premier champ fautif."""
    valeurs = {champ: _texte(data, champ) for champ in CHAMPS_TENANT}
    if not valeurs['nom']:
        raise CreationEcoleErreur("Le nom de l'école est obligatoire.")
    valeurs['code_etablissement'] = valeurs['code_etablissement'] or 'ETB'
    for champ, libelle in CHAMPS_TENANT.items():
        limite = Tenant._meta.get_field(champ).max_length
        if limite and len(valeurs[champ]) > limite:
            raise CreationEcoleErreur(
                f'{libelle} : {limite} caractères au plus ({len(valeurs[champ])} saisis).')
    if valeurs['email']:
        try:
            validate_email(valeurs['email'])
        except ValidationError:
            raise CreationEcoleErreur('Email : adresse invalide.')

    type_licence = _texte(data, 'type_licence') or 'ESSAI'
    if type_licence not in dict(Licence.TYPE_CHOICES):
        raise CreationEcoleErreur('Type de licence inconnu.')
    try:
        mois = int(data.get('mois_licence') or 12)
    except (TypeError, ValueError):
        raise CreationEcoleErreur('Durée de licence invalide.')
    if not 1 <= mois <= 60:
        raise CreationEcoleErreur('La durée de licence doit tenir entre 1 et 60 mois.')

    annee = _texte(data, 'annee_scolaire') or '2025-2026'
    if len(annee) > Exercice._meta.get_field('annee_scolaire').max_length:
        raise CreationEcoleErreur('Année scolaire : valeur trop longue (ex. 2026-2027).')
    debut = _date(data.get('date_debut') or '2025-10-01', "Début de l'année scolaire")
    fin = _date(data.get('date_fin') or '2026-09-30', "Fin de l'année scolaire")
    if fin <= debut:
        raise CreationEcoleErreur("La fin de l'année scolaire doit suivre son début.")

    return {'tenant': valeurs, 'type_licence': type_licence, 'mois': mois,
            'exercice': {'annee_scolaire': annee, 'date_debut': debut, 'date_fin': fin}}


def creer_ecole(data):
    """(tenant, licence) — créés ensemble ou pas du tout."""
    v = valider(data)
    with transaction.atomic():
        tenant = Tenant.objects.create(**v['tenant'])
        aujourdhui = date.today()
        licence = Licence.objects.create(
            tenant=tenant,
            cle_licence=Licence.generer_cle(tenant.rccm or tenant.nom[:6].upper()),
            type=v['type_licence'],
            statut='ACTIVE' if v['type_licence'] != 'ESSAI' else 'ESSAI',
            date_debut=aujourdhui,
            date_fin=aujourdhui + relativedelta(months=v['mois']),
        )
        Exercice.objects.create(tenant=tenant, devise='FCFA', **v['exercice'])
    return tenant, licence
