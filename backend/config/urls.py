from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings

from core.health import health

urlpatterns = [
    path('admin/',            admin.site.urls),
    path('api/health/',       health),
    path('api/auth/',         include('apps.users.urls')),
    path('api/tenants/',      include('apps.tenants.urls')),
    path('api/licences/',     include('apps.licences.urls')),
    path('api/eleves/',       include('apps.eleves.urls')),
    path('api/paiements/',    include('apps.paiements.urls')),
    path('api/comptabilite/', include('apps.comptabilite.urls')),
    path('api/fiscal/',       include('apps.fiscal.urls')),
    path('api/dashboard/',    include('apps.dashboard.urls')),
    path('api/rh/', include('apps.rh.urls')),
    path('api/academique/', include('apps.academique.urls')),
    path('api/daara/',      include('apps.daara.urls')),
]

if getattr(settings, 'FRONTEND_DIR', None):
    import os
    from django.http import HttpResponse
    from django.views.static import serve

    FRONTEND = settings.FRONTEND_DIR

    def angular_index(request):
        index = os.path.join(FRONTEND, 'index.html')
        if os.path.exists(index):
            with open(index, 'rb') as f:
                return HttpResponse(f.read(), content_type='text/html')
        return HttpResponse(
            f'index.html non trouvé — chemin testé: {index}', status=404
        )

    urlpatterns += [
        re_path(r'^(?P<path>.*\.(js|css|ico|png|jpg|svg|woff2?|ttf|map|json|txt))$',
                serve, {'document_root': FRONTEND}),
        re_path(r'^(?!api/)(?!admin/).*$', angular_index),
    ]
elif settings.DEBUG:
    import debug_toolbar
    urlpatterns += [path('__debug__/', include(debug_toolbar.urls))]
