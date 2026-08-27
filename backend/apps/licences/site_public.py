"""
Demande de démonstration depuis le site vitrine sagi-school.com.

Endpoint PUBLIC (AllowAny) : le prospect remplit la fiche (sections 1-4 de la
Fiche Prospect Commercial HG-COM-001).

**La demande est d'abord enregistrée au fichier prospects, ensuite seulement
notifiée par courriel.** L'ordre n'est pas un détail : dans la version
précédente le courriel était le seul dépôt, et tout ce qu'il n'atteignait pas —
SMTP non configuré, boîte pleine, message classé en indésirable — était perdu
sans que personne ne le sache. La base est désormais la source de vérité et le
courriel une commodité ; `reply_to` reste posé sur l'adresse du prospect pour
qu'un simple « Répondre » propose un rendez-vous.

Le champ `envoye` de la réponse dit donc maintenant « votre demande est bien
arrivée chez nous » — ce qui est vrai dès l'enregistrement. `notifie` dit si le
courriel est parti, et n'intéresse que le diagnostic.

Origine autorisée côté CORS : ajouter https://sagi-school.com (+ www) à
CORS_ALLOWED_ORIGINS dans le .env du cloud.
"""
import logging
from django.conf import settings
from django.core.mail import EmailMessage
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle

from apps.prospects.enregistrement import enregistrer_demande

# Les libellés proposés au visiteur (types d'organisation, origines du contact)
# vivaient ici ; ils vivent maintenant avec le modèle qui les stocke —
# `apps.prospects.models` — et sont servis au site vitrine par
# GET /api/prospects/referentiels/. Deux listes séparées finissent toujours par
# diverger.

logger = logging.getLogger(__name__)


class DemandeDemoThrottle(AnonRateThrottle):
    rate = '5/hour'


class DemandeDemoView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []          # public : pas de session ni JWT
    throttle_classes = [DemandeDemoThrottle]

    def post(self, request):
        d = request.data

        # Honeypot anti-spam : champ invisible pour un humain, rempli par les bots.
        if d.get('site_web_confirmation'):
            return Response({'envoye': True})

        champ = lambda k: str(d.get(k, '') or '').strip()[:300]

        etablissement = champ('etablissement')
        contact_nom   = champ('contact_nom')
        telephone     = champ('telephone') or champ('contact_telephone')
        if not etablissement or not contact_nom or not telephone:
            return Response(
                {'error': "Nom de l'établissement, nom du contact et téléphone sont obligatoires."},
                status=400)

        # ── L'enregistrement d'abord. Tout ce qui suit peut échouer sans que
        # la demande soit perdue.
        try:
            prospect, cree = enregistrer_demande(request.data, source='SITE',
                                                 canal='SITE')
        except Exception:
            logger.exception('Demande de démo : enregistrement du prospect en échec')
            prospect, cree = None, True

        origines = d.get('origines') or []
        if not isinstance(origines, list):
            origines = [origines]
        origines = [o for o in (str(x).strip()[:60] for x in origines) if o][:8]

        lignes = [
            "Nouvelle demande de démonstration reçue depuis sagi-school.com",
            "",
            "── 1. IDENTIFICATION DU PROSPECT ─────────────────────",
            f"Établissement      : {etablissement}",
            f"Type d'organisation: {champ('type_organisation') or '—'}",
            f"Date de création   : {champ('date_creation') or '—'}",
            f"Adresse            : {champ('adresse') or '—'}",
            f"Ville / Région     : {champ('ville') or '—'}",
            f"Téléphone principal: {champ('telephone') or '—'}",
            f"Email              : {champ('email') or '—'}",
            f"Site web / réseaux : {champ('site_web') or '—'}",
            "",
            "── 2. CONTACT PRINCIPAL ──────────────────────────────",
            f"Nom et prénom      : {contact_nom}",
            f"Fonction           : {champ('contact_fonction') or '—'}",
            f"Téléphone          : {champ('contact_telephone') or '—'}",
            f"Email              : {champ('contact_email') or '—'}",
            f"Pouvoir décisionnel: {champ('pouvoir_decisionnel') or '—'}",
            "",
            "── 3. ORIGINE DU PROSPECT ────────────────────────────",
            f"Canal              : {', '.join(origines) or '—'}",
            f"Détails            : {champ('origine_details') or '—'}",
            "",
            "── 4. INFORMATIONS SUR L'ORGANISATION ────────────────",
            f"Élèves/bénéficiaires : {champ('nb_eleves') or '—'}",
            f"Enseignants/employés : {champ('nb_employes') or '—'}",
            f"Classes/départements : {champ('nb_classes') or '—'}",
            f"Sites d'exploitation : {champ('nb_sites') or '—'}",
            "",
            "── RENDEZ-VOUS ───────────────────────────────────────",
            f"Disponibilités du prospect : {champ('disponibilites') or '—'}",
        ]
        message = str(d.get('message', '') or '').strip()[:2000]
        if message:
            lignes += ["", "Message :", message]
        corps = "\n".join(lignes)

        if prospect is not None:
            corps += (f"\n\nFiche prospect : {prospect.id}"
                      + ("" if cree else "\n(Cet établissement avait déjà une fiche"
                                         " — la demande y a été rattachée.)"))

        marque = "🎯" if cree else "🔁"
        sujet = f"{marque} Demande de démo — {etablissement}" + \
                (f" ({champ('ville')})" if champ('ville') else "")

        destinataire = getattr(settings, 'LICENCE_SUPPORT_EMAIL', 'hadygesman@gmail.com')
        reply_to = [e for e in (champ('contact_email'), champ('email')) if e][:1]

        smtp_configure = ('smtp' in settings.EMAIL_BACKEND
                          and getattr(settings, 'EMAIL_HOST', '') not in ('', 'localhost'))
        notifie = False
        if smtp_configure:
            try:
                EmailMessage(
                    subject=sujet, body=corps,
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@sagi-school.com'),
                    to=[destinataire], reply_to=reply_to or None,
                ).send()
                notifie = True
            except Exception:
                logger.exception('Demande de démo : notification par courriel en échec')

        if prospect is not None and notifie:
            prospect.courriel_envoye = True
            prospect.save(update_fields=['courriel_envoye', 'updated_at'])

        # `envoye` reflète l'enregistrement, pas le courriel : le visiteur doit
        # être remercié dès lors que sa demande est chez nous. Il ne redevient
        # False que si même la base n'a pas voulu d'elle.
        return Response({'envoye': prospect is not None, 'notifie': notifie})


class PublicStatsView(APIView):
    """GET /api/public/stats/ — compteurs agrégés pour la section
    « Ils nous font confiance » du site vitrine. Aucune donnée nominative :
    uniquement des totaux. Résultat mis en cache 1 h.

    Les installations locales (Electron) ne sont pas dans la base cloud :
    les compléter via STATS_OFFSET_ECOLES / STATS_OFFSET_ELEVES /
    STATS_OFFSET_PAIEMENTS dans le .env du cloud.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        from django.core.cache import cache
        stats = cache.get('site_public_stats')
        if stats is None:
            from django.db.models import Sum
            from apps.tenants.models import Tenant
            from apps.eleves.models import Eleve
            from apps.paiements.models import Paiement

            ecoles = Tenant.objects.filter(actif=True).count()
            # Élèves des exercices en cours (un élève par exercice actif)
            eleves = Eleve.objects.filter(exercice__cloture=False).count()
            agg = Paiement.objects.filter(statut='ACTIF').aggregate(
                t=Sum('montant_inscription') + Sum('montant_mensualite') +
                  Sum('montant_uniforme')    + Sum('montant_fournitures') +
                  Sum('montant_cantine')     + Sum('montant_divers'))
            paiements = float(agg['t'] or 0)

            stats = {
                'ecoles':    ecoles    + int(getattr(settings, 'STATS_OFFSET_ECOLES', 0)),
                'eleves':    eleves    + int(getattr(settings, 'STATS_OFFSET_ELEVES', 0)),
                'paiements': paiements + float(getattr(settings, 'STATS_OFFSET_PAIEMENTS', 0)),
            }
            cache.set('site_public_stats', stats, 3600)
        return Response(stats)
