"""Le suivi de SAMA en administration.

Deux écrans en lecture seule : ce que l'assistant a répondu, et ce qu'il a
coûté. Rien n'est modifiable — une conversation est une trace, et le compteur
du jour commande le coupe-circuit : les corriger à la main désarmerait ce que
`garde_fous` protège.
"""
from django.contrib import admin

from .models import ConsommationJournaliere, Conversation, Message


class MessageInline(admin.TabularInline):
    model = MessageModel = Message
    extra = 0
    fields = ('role', 'contenu', 'cout_fcfa', 'created_at')
    readonly_fields = fields
    can_delete = False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display  = ('titre', 'origine', 'close', 'created_at')
    list_filter   = ('close', 'origine')
    search_fields = ('titre', 'messages__contenu')
    readonly_fields = ('cle_visiteur', 'origine', 'titre', 'close',
                       'created_at', 'updated_at')
    date_hierarchy = 'created_at'
    inlines = [MessageInline]

    def has_add_permission(self, request):
        return False


@admin.register(ConsommationJournaliere)
class ConsommationJournaliereAdmin(admin.ModelAdmin):
    list_display  = ('jour', 'cout_fcfa', 'nb_conversations', 'nb_messages',
                     'jetons_sortie')
    date_hierarchy = 'jour'
    readonly_fields = [c.name for c in ConsommationJournaliere._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
