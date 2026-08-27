"""Ce qui empêche une nuit d'activité anormale de brûler le budget du mois.

À l'intérieur de l'application, la dépense de SAMA était bornée d'elle-même :
elle ne concernait que des écoles clientes, en nombre connu, chacune adossée à
un abonnement encaissé. Sur un site public, plus rien de tout cela n'est vrai.
Les visiteurs sont inconnus et sans limite de nombre, une partie du trafic est
constituée de robots, et aucune recette ne vient en face d'une conversation.

Quatre bornes, indépendantes, du plus grossier au plus fin :

1. **Le plafond mensuel** — le budget arrêté par la direction. Atteint, le
   service se tait jusqu'au mois suivant.
2. **Le coupe-circuit journalier** — pour qu'une seule journée ne puisse pas
   consommer le mois. C'est lui qui arrête un robot dans la nuit.
3. **La limite par visiteur** — nombre de conversations ouvertes dans la
   journée depuis la même adresse.
4. **La borne de conversation** — nombre de tours dans un même fil. Sans elle,
   un fil qui n'en finit pas renvoie tout son historique au modèle à chaque
   tour : la note croît en carré, pas en ligne droite.

**Pourquoi la base et non le cache.** Le cache de Django est ici un
`LocMemCache` : chaque processus serveur a le sien. Quatre `gunicorn`
donneraient quatre compteurs indépendants, donc quatre fois le plafond. Les
compteurs vivent en base, incrémentés par `F()`, et restent justes quel que
soit le nombre de processus.

**Le décompte a lieu APRÈS la réponse**, quand la consommation réelle est
connue : le coût d'un échange ne se devine pas avant de l'avoir fait. Le
plafond est donc constaté, jamais prédit — un dépassement possible est celui du
dernier échange, de l'ordre de quelques francs. Vouloir mieux exigerait de
refuser par anticipation des conversations qui ne coûteront rien.
"""
import hashlib
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from .models import ConsommationJournaliere, Conversation


class LimiteAtteinte(Exception):
    """Un garde-fou a refusé la demande — avec ce qu'il faut dire au visiteur.

    `raison` est destinée aux journaux et au suivi ; `str(exception)` est le
    message affiché, et il ne doit jamais laisser entendre que le visiteur a
    mal agi quand c'est simplement notre budget qui est atteint.
    """

    def __init__(self, message, raison):
        super().__init__(message)
        self.raison = raison


def _reglage(nom, defaut):
    return getattr(settings, nom, defaut)


def cle_visiteur(request):
    """Une empreinte stable de l'adresse du visiteur — jamais l'adresse.

    Salée avec `SECRET_KEY` : sans le secret du serveur, l'empreinte ne se
    remonte pas par simple essai des quelque quatre milliards d'adresses
    possibles. On compte les visiteurs, on ne les identifie pas.

    Derrière un proxy (le cas du cloud, nginx puis Cloudflare), l'adresse réelle
    est le PREMIER élément de `X-Forwarded-For` : les suivants sont les relais
    traversés. Prendre `REMOTE_ADDR` donnerait l'adresse de nginx, et tous les
    visiteurs partageraient alors la même limite.
    """
    transmis = request.META.get('HTTP_X_FORWARDED_FOR', '')
    adresse = (transmis.split(',')[0].strip() if transmis
               else request.META.get('REMOTE_ADDR', '')) or 'inconnue'
    graine = f'{settings.SECRET_KEY}|sama|{adresse}'
    return hashlib.sha256(graine.encode()).hexdigest()[:64]


def origine(request):
    """Le site d'où vient la conversation, sans le chemin ni les paramètres."""
    referent = request.META.get('HTTP_REFERER', '') or ''
    sans_schema = referent.split('://', 1)[-1]
    return sans_schema.split('/', 1)[0][:120]


def depense_du_jour(jour=None):
    ligne = ConsommationJournaliere.objects.filter(jour=jour or date.today()).first()
    return ligne.cout_fcfa if ligne else Decimal('0')


def depense_du_mois(jour=None):
    jour = jour or date.today()
    debut = jour.replace(day=1)
    total = ConsommationJournaliere.objects.filter(
        jour__gte=debut, jour__lte=jour).aggregate(t=Sum('cout_fcfa'))['t']
    return total or Decimal('0')


def conversation_est_au_bout(conversation):
    """Ce fil a-t-il consommé le nombre de tours qui lui était accordé ?

    Compte les messages, les deux rôles confondus : un « tour » est un
    aller-retour, et la borne par défaut de vingt en autorise donc dix.
    """
    max_messages = int(_reglage('SAMA_MAX_MESSAGES_CONVERSATION', 20))
    return max_messages > 0 and conversation.messages.count() >= max_messages


def verifier_avant_message(request, conversation):
    """Lève `LimiteAtteinte` si cet échange ne doit pas avoir lieu.

    Appelé avant tout appel au modèle. `conversation` vaut None quand le
    visiteur en ouvre une nouvelle.
    """
    plafond_mois = Decimal(str(_reglage('SAMA_PLAFOND_MOIS_FCFA', 10000)))
    if plafond_mois > 0 and depense_du_mois() >= plafond_mois:
        raise LimiteAtteinte(
            "L'assistant a atteint son budget pour ce mois. Écrivez-nous, "
            "l'équipe HADY GESMAN vous répondra directement.",
            'plafond_mensuel')

    plafond_jour = Decimal(str(_reglage('SAMA_PLAFOND_JOUR_FCFA', 1000)))
    if plafond_jour > 0 and depense_du_jour() >= plafond_jour:
        raise LimiteAtteinte(
            "L'assistant a beaucoup échangé aujourd'hui et se repose. "
            "Revenez demain, ou écrivez-nous : nous vous répondrons.",
            'coupe_circuit_journalier')

    if conversation is not None:
        if conversation.close or conversation_est_au_bout(conversation):
            raise LimiteAtteinte(
                "Cette conversation est arrivée à son terme. Ouvrez-en une "
                "nouvelle, ou demandez à être rappelé par notre équipe.",
                'conversation_bornee')
        return

    max_conversations = int(_reglage('SAMA_MAX_CONVERSATIONS_VISITEUR_JOUR', 5))
    if max_conversations > 0:
        deja = Conversation.objects.filter(
            cle_visiteur=cle_visiteur(request),
            created_at__date=date.today()).count()
        if deja >= max_conversations:
            raise LimiteAtteinte(
                "Vous avez déjà eu plusieurs conversations aujourd'hui. "
                "Pour aller plus loin, demandez à être rappelé par notre "
                "équipe — c'est plus efficace qu'un échange de plus.",
                'limite_visiteur')


@transaction.atomic
def enregistrer_consommation(usage, cout, nouvelle_conversation=False):
    """Ajoute cet échange au compteur du jour.

    `get_or_create` puis `update(F(...))` : l'incrément se fait en base, donc
    deux processus qui répondent en même temps n'en perdent aucun. Passer par
    des attributs Python ferait gagner le dernier écrivain, et le compteur
    dériverait à la baisse — précisément dans le sens qui désarme le plafond.
    """
    ConsommationJournaliere.objects.get_or_create(jour=date.today())
    ConsommationJournaliere.objects.filter(jour=date.today()).update(
        nb_messages           = F('nb_messages') + 1,
        nb_conversations      = F('nb_conversations') + (1 if nouvelle_conversation else 0),
        jetons_entree         = F('jetons_entree') + (usage.get('jetons_entree') or 0),
        jetons_sortie         = F('jetons_sortie') + (usage.get('jetons_sortie') or 0),
        jetons_cache_lecture  = F('jetons_cache_lecture') + (usage.get('jetons_cache_lecture') or 0),
        jetons_cache_ecriture = F('jetons_cache_ecriture') + (usage.get('jetons_cache_ecriture') or 0),
        cout_fcfa             = F('cout_fcfa') + cout,
        # `auto_now` ne joue pas sur un `update()` en masse : sans cette
        # ligne, la date de dernière écriture resterait celle de la création.
        updated_at            = timezone.now(),
    )


def etat_budget():
    """Où en est la dépense — pour l'écran de suivi et la commande de contrôle."""
    plafond_jour = Decimal(str(_reglage('SAMA_PLAFOND_JOUR_FCFA', 1000)))
    plafond_mois = Decimal(str(_reglage('SAMA_PLAFOND_MOIS_FCFA', 10000)))
    jour, mois = depense_du_jour(), depense_du_mois()
    return {
        'depense_jour':  jour,
        'plafond_jour':  plafond_jour,
        'depense_mois':  mois,
        'plafond_mois':  plafond_mois,
        'suspendu':      (plafond_jour > 0 and jour >= plafond_jour)
                         or (plafond_mois > 0 and mois >= plafond_mois),
        'part_mois':     float(round(mois / plafond_mois * 100, 1)) if plafond_mois else 0.0,
    }


def historique(jours=30):
    """La consommation des N derniers jours, du plus récent au plus ancien."""
    depuis = date.today() - timedelta(days=jours)
    return list(ConsommationJournaliere.objects.filter(jour__gte=depuis))
