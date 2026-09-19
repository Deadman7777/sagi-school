"""Suppression DÉFINITIVE d'une école — décision du 13/09/2026.

« Supprimer » dans l'écran Licences ne retirait que la LICENCE : l'école
restait en base, active, avec ses fiches, ses utilisateurs et ses écritures.
Elle disparaissait de l'écran (qui liste des licences) mais comptait toujours
dans « écoles équipées » du site vitrine — 13 écoles affichées pour 3 réelles.

Désormais la suppression efface l'école et TOUT ce qui lui appartient
(élèves, paiements, écritures, RH, utilisateurs…), dans une transaction.
Irréversible : réservée au super admin, et l'écran exige de retaper le nom.

Des liens PROTECT existent à l'intérieur d'une même école (un paiement vers
son organisme payeur ou sa caisse, une prise en charge vers son organisme,
une formule d'élève, un financement GMRF vers son type…). La cascade s'y
arrête sur ProtectedError. On efface donc d'abord ces enfants.

⚠️ Cette liste ne s'écrit PAS à la main : elle a été énumérée en dur le
13/09/2026, et le 19/09 la suppression d'une école a échoué sur un lien
apparu depuis (`PriseEnChargeOrganisme.organisme`, les boursiers) — pendant
une bascule en cloud, au pire moment. Les modèles bloquants sont donc
découverts dans le schéma, et toute fonctionnalité qui ajoutera un PROTECT
sera couverte sans qu'on y pense.

Les sauvegardes déjà reçues sur disque ne sont pas touchées.
"""
from django.apps import apps as django_apps
from django.db import models, transaction
from django.db.models.deletion import ProtectedError


def _modeles_bloquants():
    """Modèles portant une FK PROTECT, avec de quoi les filtrer sur l'école.

    Rend (modèle, chemin) où `chemin` est le lookup menant au tenant :
    'tenant' quand le modèle le porte, sinon la traversée d'une de ses FK
    protégées (un justificatif de facturation n'a pas de tenant, sa facture
    si).
    """
    for modele in django_apps.get_models():
        proteges = [f.name for f in modele._meta.fields
                    if getattr(f, 'remote_field', None)
                    and f.remote_field.on_delete is models.PROTECT]
        if not proteges:
            continue
        champs = {f.name for f in modele._meta.fields}
        if 'tenant' in champs:
            yield modele, 'tenant'
            continue
        for nom in proteges:
            cible = modele._meta.get_field(nom).related_model
            if any(f.name == 'tenant' for f in cible._meta.fields):
                yield modele, f'{nom}__tenant'
                break


def _effacer_les_bloquants(tenant):
    """Efface les enfants qui protègent, jusqu'à ce que plus rien ne bloque.

    Un enfant peut lui-même être protégé par un autre (encaissement →
    facture → justificatif) : on repasse tant que chaque tour débloque
    quelque chose. Un tour sans progrès signifie un lien qu'on ne sait pas
    dénouer — on laisse alors remonter l'erreur d'origine, explicite.
    """
    restants = list(_modeles_bloquants())
    while restants:
        bloques = []
        for modele, chemin in restants:
            try:
                with transaction.atomic():
                    modele.objects.filter(**{chemin: tenant}).delete()
            except ProtectedError:
                bloques.append((modele, chemin))
        if len(bloques) == len(restants):
            return          # plus de progrès : tenant.delete() dira pourquoi
        restants = bloques


def compter(tenant):
    from apps.eleves.models import Eleve
    from apps.paiements.models import Paiement
    from apps.users.models import User
    return {
        'ecole':        tenant.nom,
        'eleves':       Eleve.objects.filter(tenant=tenant).count(),
        'paiements':    Paiement.objects.filter(tenant=tenant).count(),
        'utilisateurs': User.objects.filter(tenant=tenant).count(),
    }


def supprimer_ecole(tenant):
    """Efface l'école et ses données. Rend le décompte de ce qui a été effacé."""
    bilan = compter(tenant)
    with transaction.atomic():
        _effacer_les_bloquants(tenant)
        tenant.delete()
    from django.core.cache import cache
    cache.delete('site_public_stats')
    return bilan


def ecoles_sans_licence():
    from apps.tenants.models import Tenant
    return Tenant.objects.filter(licence__isnull=True).order_by('created_at')
