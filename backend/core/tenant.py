"""
Résolution sécurisée du tenant pour une requête.

Le header X-Tenant-ID seul n'est PAS digne de confiance — un user
authentifié de l'école A pourrait sinon le falsifier pour accéder
aux données de l'école B.

Règles :
  - User normal             → request.tenant = user.tenant (header ignoré)
  - SUPER_ADMIN + header    → request.tenant = tenant(header) (basculement)
  - SUPER_ADMIN sans header → request.tenant = None
  - Non authentifié         → request.tenant = None

Le middleware (core/middleware.py) attache request.tenant en
SimpleLazyObject qui appelle _resolve_tenant(request) — l'évaluation
se fait donc à la lecture (dans la vue, après authentification DRF).
"""
from django.core.cache import cache


def _resolve_tenant(request):
    """Résolution sécurisée, appelée par le SimpleLazyObject."""
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return None

    role = getattr(user, 'role', None)
    header_tid = getattr(request, '_tenant_id_from_header', None)

    if role == 'SUPER_ADMIN':
        # Super admin peut spécifier explicitement un tenant via header.
        # Pas de fallback "premier tenant trouvé" : il DOIT être explicite.
        if header_tid:
            return _fetch_tenant(header_tid)
        return None

    # User normal : forcé sur SON tenant. Le header est IGNORÉ.
    user_tenant_id = getattr(user, 'tenant_id', None)
    if user_tenant_id:
        return _fetch_tenant(str(user_tenant_id))
    return None


def _fetch_tenant(tenant_id):
    """Lookup tenant (cache 5 min) sans crasher si l'ID est invalide."""
    cache_key = f'tenant_{tenant_id}'
    tenant = cache.get(cache_key)
    if tenant is not None:
        return tenant
    try:
        from apps.tenants.models import Tenant
        tenant = Tenant.objects.get(id=tenant_id, actif=True)
        cache.set(cache_key, tenant, 300)
        return tenant
    except Exception:
        return None


def get_tenant(request):
    """
    Helper public pour les vues. Équivalent à request.tenant
    (qui est lui-même un SimpleLazyObject câblé sur _resolve_tenant).
    À utiliser partout au lieu des get_tenant() locaux à chaque app.
    """
    return request.tenant
