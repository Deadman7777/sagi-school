from django.utils.functional import SimpleLazyObject
from .tenant import _resolve_tenant


class TenantMiddleware:
    """
    Attache request.tenant en lazy : la résolution sécurisée
    (cf. core/tenant.py) se fait au premier accès, dans la vue,
    après que DRF/JWT a authentifié request.user.

    Le header X-Tenant-ID est seulement parsé ici (pas de lookup DB) ;
    il n'est utilisé que si l'user authentifié est SUPER_ADMIN.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        header = request.headers.get('X-Tenant-ID')
        if header and header not in ('null', ''):
            request._tenant_id_from_header = header
        else:
            request._tenant_id_from_header = None

        # Résolution lazy : exécutée à la lecture de request.tenant
        request.tenant = SimpleLazyObject(lambda: _resolve_tenant(request))

        return self.get_response(request)
