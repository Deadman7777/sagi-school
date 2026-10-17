"""Demande de renouvellement de licence — enregistrer, notifier, relayer.

Trois défauts faisaient disparaître les demandes (suivi Shoumoul, sept. 2026) :
  1. le courriel était le SEUL dépôt : une erreur SMTP (mot de passe
     d'application révoqué, quota Gmail, réseau) était avalée par un
     `except: pass` et la demande n'existait nulle part ;
  2. l'écran répondait alors par un lien `mailto:` — sans client de messagerie
     sur le poste, il ne se passait rien, et l'utilisateur croyait avoir envoyé ;
  3. une installation locale n'a pas de SMTP : la demande ne quittait jamais
     l'école.

Désormais :
  - la demande est ENREGISTRÉE d'abord (DemandeRenouvellement) ;
  - sur le cloud, elle part par courriel, et l'erreur éventuelle est journalisée
    et conservée sur la demande ;
  - en local sans SMTP, elle est RELAYÉE au cloud (authentifiée par la
    signature de la clé de licence, comme les sauvegardes), qui l'enregistre et
    envoie le courriel ;
  - l'écran dit la vérité : « reçue par HADY GESMAN » seulement si le courriel
    est parti ou si le cloud a accusé réception ; sinon il propose WhatsApp et
    le téléphone.
"""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail import EmailMessage

from .models import DemandeRenouvellement

logger = logging.getLogger(__name__)

TIMEOUT_RELAIS = 15


def destinataire():
    return getattr(settings, 'LICENCE_SUPPORT_EMAIL', 'hadygesman@gmail.com')


def smtp_configure():
    return ('smtp' in getattr(settings, 'EMAIL_BACKEND', '')
            and getattr(settings, 'EMAIL_HOST', '') not in ('', 'localhost'))


def composer(demande):
    sujet = f"[SAGI SCHOOL] Demande de renouvellement — {demande.ecole_nom}"
    lignes = [
        "Nouvelle demande de renouvellement de licence.",
        "",
        f"École       : {demande.ecole_nom}",
        f"Téléphone   : {demande.telephone or '—'}",
        "",
        f"Licence     : {demande.type_licence or '—'}",
        f"Clé         : {demande.cle_licence or '—'}",
        f"Expire le   : {demande.date_fin or '—'}",
        "",
        *([f"Formule     : {demande.type_demande or demande.type_licence} — {demande.mois} mois"
           + (f" — {demande.montant:,} FCFA".replace(',', ' ') if demande.montant else ''),
           f"Paiement    : {demande.moyen_paiement or 'non précisé'}"
           + (f" — réf. {demande.reference_paiement}" if demande.reference_paiement else ''),
           ""] if demande.mois else []),
        f"Demandeur   : {demande.demandeur or '—'} — {demande.email_demandeur or '—'}",
        f"Origine     : {demande.get_origine_display()}",
        f"Référence   : {demande.id}",
    ]
    if demande.message:
        lignes += ["", "Message :", demande.message]
    return sujet, "\n".join(lignes)


def notifier_par_courriel(demande):
    """Envoie le courriel. Rend (ok, erreur) et met la demande à jour."""
    if not smtp_configure():
        return False, "SMTP non configuré sur ce serveur."
    sujet, corps = composer(demande)
    try:
        EmailMessage(
            subject=sujet, body=corps,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None)
                       or getattr(settings, 'EMAIL_HOST_USER', None),
            to=[destinataire()],
            reply_to=[demande.email_demandeur] if demande.email_demandeur else None,
        ).send(fail_silently=False)
    except Exception as exc:
        logger.exception('Demande de renouvellement %s : courriel en échec', demande.id)
        erreur = f"{type(exc).__name__}: {exc}"[:1000]
        demande.erreur = erreur
        demande.save(update_fields=['erreur', 'updated_at'])
        return False, erreur
    demande.courriel_envoye = True
    demande.erreur = ''
    demande.save(update_fields=['courriel_envoye', 'erreur', 'updated_at'])
    return True, ''


def relayer_vers_cloud(demande):
    """Installation locale : transmet la demande au cloud. Rend (ok, erreur)."""
    url = settings.SAGI_CLOUD_URL.rstrip('/') + '/api/licences/relais-renouvellement/'
    corps = json.dumps({
        'ecole_nom': demande.ecole_nom, 'type_licence': demande.type_licence,
        'date_fin': str(demande.date_fin or ''), 'demandeur': demande.demandeur,
        'email_demandeur': demande.email_demandeur, 'telephone': demande.telephone,
        'message': demande.message, 'reference_locale': str(demande.id),
        'type_demande': demande.type_demande, 'mois': demande.mois,
        'moyen_paiement': demande.moyen_paiement,
        'reference_paiement': demande.reference_paiement,
    }).encode('utf-8')
    requete = urllib.request.Request(url, data=corps, method='POST', headers={
        'Content-Type': 'application/json',
        # Sans User-Agent explicite, Cloudflare bloque « Python-urllib ».
        'User-Agent': 'SAGI-SCHOOL-Licence/1.0 (+https://sagi-school.com)',
        'X-Cle-Licence': demande.cle_licence,
    })
    try:
        with urllib.request.urlopen(requete, timeout=TIMEOUT_RELAIS) as reponse:
            data = json.loads(reponse.read().decode('utf-8') or '{}')
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.warning('Relais renouvellement %s vers le cloud impossible : %s', demande.id, exc)
        erreur = f"Relais cloud impossible (connexion internet ?) : {exc}"[:1000]
        demande.erreur = erreur
        demande.save(update_fields=['erreur', 'updated_at'])
        return False, erreur
    ok = bool(data.get('recue'))
    demande.relayee = ok
    demande.courriel_envoye = bool(data.get('courriel_envoye'))
    demande.erreur = '' if ok else str(data.get('detail') or 'Réponse inattendue du cloud')[:1000]
    demande.save(update_fields=['relayee', 'courriel_envoye', 'erreur', 'updated_at'])
    return ok, demande.erreur


def formule_demandee(licence, data):
    """La formule choisie par « Renouveler maintenant », validée et chiffrée par le serveur.

    Rend {} quand rien n'est choisi (ancienne demande libre).
    """
    from .alertes import montant
    from .models import Licence
    try:
        mois = int(data.get('mois') or 0)
    except (TypeError, ValueError):
        mois = 0
    if mois not in (1, 6, 12):
        return {}
    type_ = str(data.get('type') or '').strip() or licence.type
    if type_ not in dict(Licence.TYPE_CHOICES) or type_ == 'ESSAI':
        type_ = licence.type if licence.type != 'ESSAI' else 'BASIC'
    return {
        'type_demande': type_, 'mois': mois, 'montant': montant(type_, mois),
        'moyen_paiement': str(data.get('moyen_paiement') or '').strip()[:60],
        'reference_paiement': str(data.get('reference_paiement') or '').strip()[:120],
    }


def prolonger(licence, mois, type_licence=None):
    """Renouvelle : max(date de fin, aujourd'hui) + `mois`. Le temps restant n'est pas perdu."""
    from dateutil.relativedelta import relativedelta
    from django.utils import timezone
    base = max(licence.date_fin, timezone.now().date())
    licence.date_fin = base + relativedelta(months=mois)
    if type_licence and type_licence != licence.type:
        licence.type = type_licence
        licence.date_debut = timezone.now().date()
    licence.statut = 'ACTIVE'
    licence.save()
    return licence


def demander(licence, user, message='', formule=None):
    """Enregistre puis achemine une demande. Rend (demande, recue_par_hady_gesman)."""
    t = licence.tenant
    est_cloud = getattr(settings, 'SAGI_EST_CLOUD', False)
    local_sans_smtp = not est_cloud and not smtp_configure()
    demande = DemandeRenouvellement.objects.create(
        tenant=t, licence=licence, ecole_nom=t.nom + (f" ({t.ville})" if t.ville else ''),
        cle_licence=licence.cle_licence, type_licence=licence.type, date_fin=licence.date_fin,
        demandeur=f"{getattr(user, 'prenom', '') or ''} {getattr(user, 'nom', '') or ''}".strip(),
        email_demandeur=getattr(user, 'email', '') or t.email or '',
        telephone=t.telephone or '',
        message=(message or '').strip()[:2000],
        origine='LOCAL' if local_sans_smtp else 'CLOUD',
        **(formule or {}),
    )
    if local_sans_smtp:
        ok, _ = relayer_vers_cloud(demande)
        if ok:
            demande.origine = 'RELAIS'
            demande.save(update_fields=['origine', 'updated_at'])
        return demande, ok
    ok, _ = notifier_par_courriel(demande)
    return demande, ok
