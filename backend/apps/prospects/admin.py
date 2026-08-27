from django.contrib import admin

from .models import InteractionProspect, Prospect


class InteractionInline(admin.TabularInline):
    model = InteractionProspect
    extra = 0
    fields = ('date', 'canal', 'resume', 'auteur')


@admin.register(Prospect)
class ProspectAdmin(admin.ModelAdmin):
    list_display  = ('etablissement', 'ville', 'contact_nom', 'telephone',
                     'statut', 'source', 'relance_le', 'created_at')
    list_filter   = ('statut', 'source', 'type_organisation')
    search_fields = ('etablissement', 'ville', 'contact_nom', 'telephone_cle',
                     'email', 'contact_email')
    readonly_fields = ('telephone_cle', 'donnees_brutes', 'created_at', 'updated_at')
    date_hierarchy  = 'created_at'
    inlines = [InteractionInline]


@admin.register(InteractionProspect)
class InteractionProspectAdmin(admin.ModelAdmin):
    list_display  = ('prospect', 'date', 'canal', 'auteur')
    list_filter   = ('canal',)
    search_fields = ('prospect__etablissement', 'resume')
