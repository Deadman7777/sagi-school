from django.contrib import admin

from .models import Sourate, Subdivision, NiveauDaara, ParcoursNongo, SuiviQuotidien


@admin.register(Sourate)
class SourateAdmin(admin.ModelAdmin):
    list_display = ('numero', 'nom_fr', 'nom_ar', 'type_revelation',
                    'nb_versets_hafs', 'nb_versets_warsh')
    list_filter = ('type_revelation',)
    search_fields = ('nom_fr', 'nom_ar', 'numero')


@admin.register(Subdivision)
class SubdivisionAdmin(admin.ModelAdmin):
    list_display = ('riwaya', 'type', 'numero', 'sourate_debut', 'verset_debut')
    list_filter = ('riwaya', 'type')


@admin.register(NiveauDaara)
class NiveauDaaraAdmin(admin.ModelAdmin):
    list_display = ('nom_fr', 'nom_ar', 'categorie', 'ordre', 'tenant')
    list_filter = ('categorie', 'tenant')


@admin.register(ParcoursNongo)
class ParcoursNongoAdmin(admin.ModelAdmin):
    list_display = ('eleve', 'riwaya', 'niveau', 'statut', 'date_debut', 'date_sortie', 'tenant')
    list_filter = ('riwaya', 'statut', 'tenant')


@admin.register(SuiviQuotidien)
class SuiviQuotidienAdmin(admin.ModelAdmin):
    list_display = ('date', 'parcours', 'qualite', 'present')
    list_filter = ('qualite', 'present')
    date_hierarchy = 'date'
