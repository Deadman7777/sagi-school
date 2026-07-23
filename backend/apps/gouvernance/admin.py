from django.contrib import admin
from .models import (Projet, PieceJustificative, TransfertTresorerie,
                     Ressource, AffectationRessource, Provision,
                     CompteBancaire, Rapprochement, LigneReleve)

admin.site.register(CompteBancaire)
admin.site.register(Rapprochement)
admin.site.register(LigneReleve)


@admin.register(Provision)
class ProvisionAdmin(admin.ModelAdmin):
    list_display = ('reference', 'libelle', 'type_provision', 'montant', 'montant_repris', 'statut')
    list_filter = ('type_provision', 'statut')
    search_fields = ('reference', 'libelle')


@admin.register(Ressource)
class RessourceAdmin(admin.ModelAdmin):
    list_display = ('reference', 'libelle', 'type_ressource', 'montant', 'statut')
    list_filter = ('type_ressource', 'statut')
    search_fields = ('reference', 'libelle', 'organisme')


@admin.register(AffectationRessource)
class AffectationRessourceAdmin(admin.ModelAdmin):
    list_display = ('ressource', 'type_emploi', 'libelle', 'montant_affecte')
    list_filter = ('type_emploi',)


@admin.register(TransfertTresorerie)
class TransfertTresorerieAdmin(admin.ModelAdmin):
    list_display = ('reference', 'date_transfert', 'compte_source', 'compte_destination',
                    'montant', 'frais', 'statut')
    list_filter = ('statut',)
    search_fields = ('reference', 'motif')


@admin.register(Projet)
class ProjetAdmin(admin.ModelAdmin):
    list_display = ('code', 'libelle', 'statut', 'budget_prevu', 'est_actif')
    list_filter = ('statut', 'est_actif')
    search_fields = ('code', 'libelle')


@admin.register(PieceJustificative)
class PieceJustificativeAdmin(admin.ModelAdmin):
    list_display = ('nom', 'type_piece', 'objet_type', 'objet_id', 'taille', 'created_at')
    list_filter = ('objet_type', 'type_piece')
    search_fields = ('nom', 'reference')
    # Le contenu base64 est volumineux : on l'exclut de l'admin.
    exclude = ('contenu',)
