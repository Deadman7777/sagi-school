"""Ce que SAMA garde d'une conversation publique.

**Rien ici n'est cloisonné par école.** SAMA a quitté l'application : il vit sur
sagi-school.com et parle à des visiteurs anonymes, qui n'appartiennent à aucun
établissement client. `TimeStampedModel` donc, et non `TenantModel`.

**Aucune adresse IP n'est stockée.** Limiter un visiteur suppose de le
reconnaître, pas de l'identifier : `cle_visiteur` est une empreinte de son
adresse, calculée avec le secret du serveur. Elle suffit à compter, et ne permet
pas de remonter à quelqu'un — c'est le minimum qu'on doive à des gens qui n'ont
rien signé.
"""
from django.db import models

from core.models import TimeStampedModel


class Conversation(TimeStampedModel):
    """Un fil d'échange avec un visiteur du site."""

    # Empreinte de l'adresse du visiteur (voir `garde_fous.cle_visiteur`).
    # Indexée : c'est la clé du décompte par visiteur, interrogé à chaque
    # message.
    cle_visiteur = models.CharField(max_length=64, blank=True, db_index=True)
    # Le site d'où vient la conversation, pour distinguer sagi-school.com d'un
    # essai local. Jamais l'URL complète : elle n'apprendrait rien de plus.
    origine = models.CharField(max_length=120, blank=True)
    titre   = models.CharField(max_length=200, blank=True)
    # La fiche que cette conversation a produite, s'il y en a une. C'est le
    # seul lien entre ce que dit l'assistant et ce que fait le commercial :
    # sans lui, on saurait combien SAMA coûte, jamais ce qu'il rapporte.
    prospect = models.ForeignKey(
        'prospects.Prospect', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='conversations')
    # Une conversation atteint sa borne et ne repart pas : sans cela, un
    # visiteur peut faire durer un seul fil indéfiniment, et chaque tour
    # renvoie tout l'historique au modèle — la note croît en carré.
    close   = models.BooleanField(default=False)

    class Meta:
        ordering = ['-updated_at']
        indexes = [models.Index(fields=['cle_visiteur', '-created_at'])]

    def __str__(self):
        return self.titre or f'Conversation {self.id}'


class Message(TimeStampedModel):
    """Un tour de parole, et ce qu'il a coûté.

    Le contenu est conservé tel quel : c'est la trace de ce que l'assistant a
    répondu à un visiteur, et elle doit rester consultable si une réponse est
    contestée — sur un site public, ce qu'il dit engage l'entreprise.
    """
    ROLES = [('user', 'Visiteur'), ('assistant', 'SAMA')]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE,
                                     related_name='messages')
    role    = models.CharField(max_length=10, choices=ROLES)
    contenu = models.TextField()

    jetons_entree         = models.IntegerField(default=0)
    jetons_sortie         = models.IntegerField(default=0)
    jetons_cache_lecture  = models.IntegerField(default=0)
    jetons_cache_ecriture = models.IntegerField(default=0)
    # Calculé par `client.cout_fcfa` au moment de l'échange, avec les tarifs
    # d'alors. Recalculer après coup donnerait un autre chiffre le jour où le
    # modèle ou le taux de change change : ce qui est dépensé est figé.
    cout_fcfa = models.DecimalField(max_digits=10, decimal_places=4, default=0)

    class Meta:
        ordering = ['created_at']
        indexes = [models.Index(fields=['conversation', 'created_at'])]

    def __str__(self):
        return f'{self.get_role_display()} — {self.contenu[:60]}'


class ConsommationJournaliere(TimeStampedModel):
    """Le total dépensé dans la journée — la base du coupe-circuit.

    Redondant avec la somme des `Message` ? Oui, et volontairement. Le
    coupe-circuit est interrogé AVANT chaque appel au modèle : il ne peut pas
    reposer sur une agrégation qui balaierait toute la table à chaque message.
    Une ligne par jour, incrémentée en base par `F()`, reste juste même avec
    plusieurs processus serveur en parallèle — ce que le cache mémoire de Django
    ne garantirait pas, chaque `gunicorn` ayant le sien.
    """
    jour = models.DateField(unique=True)

    nb_conversations = models.IntegerField(default=0)
    nb_messages      = models.IntegerField(default=0)

    jetons_entree         = models.BigIntegerField(default=0)
    jetons_sortie         = models.BigIntegerField(default=0)
    jetons_cache_lecture  = models.BigIntegerField(default=0)
    jetons_cache_ecriture = models.BigIntegerField(default=0)

    cout_fcfa = models.DecimalField(max_digits=12, decimal_places=4, default=0)

    class Meta:
        ordering = ['-jour']
        verbose_name = 'Consommation journalière'
        verbose_name_plural = 'Consommations journalières'

    def __str__(self):
        return f'{self.jour:%d/%m/%Y} — {self.cout_fcfa} F ({self.nb_messages} messages)'
