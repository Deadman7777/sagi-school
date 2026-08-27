from django.contrib import admin

from .models import Devis, InteractionProspect, Prospect


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


@admin.register(Devis)
class DevisAdmin(admin.ModelAdmin):
    list_display  = ('numero', 'etablissement', 'type_licence', 'montant_net',
                     'statut', 'date_emission', 'date_validite')
    list_filter   = ('statut', 'type_licence', 'cycle')
    search_fields = ('numero', 'etablissement', 'contact_nom')
    date_hierarchy = 'date_emission'
    # Les montants sont chiffrés depuis le catalogue : les retoucher ici
    # contournerait la seule garantie qu'un devis ne porte pas un prix inventé.
    readonly_fields = ('numero', 'prix_mensuel', 'montant_brut', 'taux_remise',
                       'montant_remise', 'montant_net', 'valide_par',
                       'valide_le', 'envoye_le', 'created_at', 'updated_at')
