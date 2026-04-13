from django.contrib import admin
from .models import Tenant

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display  = ['nom', 'ville', 'rccm', 'ninea', 'actif', 'created_at']
    list_filter   = ['actif', 'ville']
    search_fields = ['nom', 'rccm', 'ninea']
    list_editable = ['actif']
