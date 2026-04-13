from django.contrib import admin
from .models import JournalEntry

@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display  = ['date_ecriture', 'no_piece', 'no_compte', 'libelle', 'debit', 'credit', 'source']
    list_filter   = ['source', 'no_compte', 'exercice']
    search_fields = ['no_piece', 'libelle', 'no_compte']
    ordering      = ['date_ecriture', 'no_piece']
    readonly_fields = ['source', 'source_id']
