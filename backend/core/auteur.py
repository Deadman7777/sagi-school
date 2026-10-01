"""L'utilisateur à l'origine de la requête en cours.

Chaque écriture comptable doit dire QUI l'a passée : une école qui confie la
caisse à deux chargés de scolarité fait chaque soir le point de chacun. Les
écritures naissent à des dizaines d'endroits (encaissement, annulation,
charge, paie, avance, transfert…) ; leur passer l'utilisateur un par un en
aurait oublié. Le journal le lit donc ici, au moment de l'enregistrement
(voir JournalEntry.save et son bulk_create).

On retient la REQUÊTE, pas l'utilisateur : avec un jeton JWT, DRF
n'authentifie qu'à l'intérieur de la vue, bien après les middlewares. Il
recopie alors l'utilisateur sur la requête Django — c'est là qu'on le lit.

Hors requête (commande, migration, tâche planifiée) : None, l'écriture reste
sans auteur.
"""
from contextvars import ContextVar

_requete = ContextVar('requete_courante', default=None)


def utilisateur_courant():
    """L'utilisateur authentifié de la requête en cours, ou None."""
    requete = _requete.get()
    user = getattr(requete, 'user', None) if requete is not None else None
    return user if user is not None and user.is_authenticated else None


class AuteurMiddleware:
    """Rend la requête en cours lisible par utilisateur_courant()."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        jeton = _requete.set(request)
        try:
            return self.get_response(request)
        finally:
            _requete.reset(jeton)
