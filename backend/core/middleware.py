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


class ApiSansCacheMiddleware:
    """Une réponse d'API n'est jamais resservie depuis un cache.

    Ni Django ni nginx ne posaient d'en-tête sur /api/ : sans consigne, le
    navigateur — et Electron, qui a le même cache HTTP — est libre de rendre
    l'ancienne réponse. On modifiait une échéance dans Paramètres, on passait
    dans un autre module, on revenait : la valeur d'avant était de retour.
    Elle n'était pas perdue, elle était relue dans le cache.

    Le rechargement forcé (Ctrl+Shift+R) masquait le problème sur le cloud,
    et n'existe même pas sur un poste local.

    Une vue qui pose délibérément son propre Cache-Control garde le sien.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith('/api/') and not response.has_header('Cache-Control'):
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        return response
