from django.contrib import admin
from .models import Paiement, Exercice

@admin.register(Exercice)
class ExerciceAdmin(admin.ModelAdmin):
    list_display  = ['annee_scolaire', 'tenant', 'date_debut', 'date_fin', 'cloture']
    list_filter   = ['cloture', 'tenant']
    search_fields = ['annee_scolaire']

@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    list_display  = ['no_piece', 'eleve', 'date_paiement', 'mode_paiement', 'total', 'saisi_par']
    list_filter   = ['mode_paiement', 'exercice', 'tenant']
    search_fields = ['no_piece', 'eleve__nom_complet']
    readonly_fields = ['no_piece', 'total']
    ordering      = ['-date_paiement']
