from django.contrib import admin
from .models import Eleve, Section

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display  = ['nom', 'tenant', 'frais_inscription', 'frais_mensualite', 'frais_uniforme', 'frais_fournitures', 'total_annuel']
    list_filter   = ['tenant']
    search_fields = ['nom']
    readonly_fields = ['total_annuel']

@admin.register(Eleve)
class EleveAdmin(admin.ModelAdmin):
    list_display  = ['nom_complet', 'section', 'genre', 'statut', 'niveau_alerte', 'total_attendu', 'total_paye', 'reste_a_payer', 'telephone_parent']
    list_filter   = ['statut', 'genre', 'section', 'tenant']
    search_fields = ['nom_complet', 'telephone_parent']
    readonly_fields = ['total_attendu', 'total_paye', 'reste_a_payer', 'niveau_alerte']
    ordering      = ['nom_complet']
