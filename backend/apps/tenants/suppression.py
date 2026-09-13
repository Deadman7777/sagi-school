"""Suppression DÉFINITIVE d'une école — décision du 13/09/2026.

« Supprimer » dans l'écran Licences ne retirait que la LICENCE : l'école
restait en base, active, avec ses fiches, ses utilisateurs et ses écritures.
Elle disparaissait de l'écran (qui liste des licences) mais comptait toujours
dans « écoles équipées » du site vitrine — 13 écoles affichées pour 3 réelles.

Désormais la suppression efface l'école et TOUT ce qui lui appartient
(élèves, paiements, écritures, RH, utilisateurs…), dans une transaction.
Irréversible : réservée au super admin, et l'écran exige de retaper le nom.

Deux liens sont protégés (PROTECT) à l'intérieur d'une même école : un
paiement vers son organisme payeur, un financement GMRF vers son type. On
efface d'abord ces enfants, sinon la cascade s'arrête sur ProtectedError.
Les sauvegardes déjà reçues sur disque ne sont pas touchées.
"""
from django.db import transaction


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
    from apps.gmrf.models import Financement
    from apps.paiements.models import Paiement

    bilan = compter(tenant)
    with transaction.atomic():
        Paiement.objects.filter(tenant=tenant).delete()
        Financement.objects.filter(tenant=tenant).delete()
        tenant.delete()
    from django.core.cache import cache
    cache.delete('site_public_stats')
    return bilan


def ecoles_sans_licence():
    from apps.tenants.models import Tenant
    return Tenant.objects.filter(licence__isnull=True).order_by('created_at')
