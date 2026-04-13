from django.core.cache import cache


class TenantMiddleware:
    """
    Identifie le tenant depuis le header X-Tenant-ID.
    Met en cache le tenant pour éviter les requêtes répétées.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = None
        tenant_id = request.headers.get('X-Tenant-ID')

        if tenant_id and tenant_id != 'null' and tenant_id != '':
            # Cache 5 min pour éviter les requêtes répétées
            cache_key = f'tenant_{tenant_id}'
            tenant    = cache.get(cache_key)
            if not tenant:
                try:
                    from apps.tenants.models import Tenant
                    tenant = Tenant.objects.get(id=tenant_id, actif=True)
                    cache.set(cache_key, tenant, 300)
                except Exception:
                    tenant = None
            request.tenant = tenant

        return self.get_response(request)
