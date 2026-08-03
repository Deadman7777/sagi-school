from django.db import models

from core.models import TenantModel


class Conversation(TenantModel):
    """Un fil d'échange avec SAMA, rattaché à une école et à un utilisateur.

    Les conversations sont cloisonnées par établissement comme le reste du
    logiciel : une école ne voit jamais les échanges d'une autre. Elles le sont
    aussi par utilisateur — le comptable n'a pas à lire ce que le directeur a
    demandé à l'assistant.
    """
    utilisateur = models.ForeignKey('users.User', on_delete=models.CASCADE,
                                    related_name='conversations_sama')
    titre = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [models.Index(fields=['tenant', 'utilisateur', '-updated_at'])]

    def __str__(self):
        return self.titre or f'Conversation {self.id}'


class Message(TenantModel):
    """Un tour de parole.

    Le contenu est conservé tel quel : c'est la trace de ce que l'assistant a
    répondu à un client, et elle doit rester consultable si une réponse est
    contestée. Les compteurs de jetons servent au suivi de consommation.
    """
    ROLES = [('user', 'Utilisateur'), ('assistant', 'SAMA')]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE,
                                     related_name='messages')
    role    = models.CharField(max_length=10, choices=ROLES)
    contenu = models.TextField()
    jetons_entree = models.IntegerField(default=0)
    jetons_sortie = models.IntegerField(default=0)
    jetons_cache  = models.IntegerField(default=0)

    class Meta:
        ordering = ['created_at']
        indexes = [models.Index(fields=['conversation', 'created_at'])]

    def __str__(self):
        return f'{self.get_role_display()} — {self.contenu[:60]}'
