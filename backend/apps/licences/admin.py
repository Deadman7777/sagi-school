from django.contrib import admin
from .models import Licence

@admin.register(Licence)
class LicenceAdmin(admin.ModelAdmin):
    list_display  = ['tenant', 'type', 'statut', 'date_debut', 'date_fin', 'est_active', 'jours_restants']
    list_filter   = ['type', 'statut']
    search_fields = ['tenant__nom', 'cle_licence']
    readonly_fields = ['cle_licence', 'est_active', 'jours_restants']
    ordering      = ['date_fin']

    def save_model(self, request, obj, form, change):
        if not obj.cle_licence:
            obj.cle_licence = Licence.generer_cle(obj.tenant.rccm or 'SNDKR')
        super().save_model(request, obj, form, change)
