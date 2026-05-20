from django.contrib import admin
from .models import Employe, Paie, ParametresFiscaux, AvanceSalaire, BulletinPaie


@admin.register(Employe)
class EmployeAdmin(admin.ModelAdmin):
    list_display  = ('matricule', 'nom_complet', 'type_employe', 'poste', 'statut', 'salaire_base', 'est_cadre')
    list_filter   = ('statut', 'type_employe', 'niveau_enseignement', 'situation_matrimoniale', 'est_cadre')
    search_fields = ('matricule', 'nom_complet', 'poste')


@admin.register(ParametresFiscaux)
class ParametresFiscauxAdmin(admin.ModelAdmin):
    list_display = (
        'annee', 'taux_ipres_general_salarie', 'taux_ipres_general_patronal',
        'taux_css_prestations_familiales', 'taux_cfce', 'prime_transport',
    )


@admin.register(AvanceSalaire)
class AvanceSalaireAdmin(admin.ModelAdmin):
    list_display  = ('employe', 'montant', 'date_avance', 'mode_paiement', 'statut', 'no_piece')
    list_filter   = ('statut', 'mode_paiement')
    search_fields = ('employe__nom_complet', 'no_piece')


@admin.register(BulletinPaie)
class BulletinPaieAdmin(admin.ModelAdmin):
    list_display  = ('employe', 'mois', 'annee', 'salaire_brut', 'net_a_payer', 'statut')
    list_filter   = ('statut', 'annee', 'mois')
    search_fields = ('employe__nom_complet', 'employe__matricule')
    readonly_fields = (
        'salaire_brut', 'total_retenues_salariales', 'total_charges_patronales',
        'net_a_payer', 'cout_total_employeur', 'date_validation', 'date_paiement',
    )


@admin.register(Paie)
class PaieAdmin(admin.ModelAdmin):
    list_display  = ('employe', 'mois', 'salaire_brut', 'salaire_net', 'statut')
    list_filter   = ('statut',)
    search_fields = ('employe__nom_complet',)
