"""Envoyer à un client : courriel avec pièces jointes, et lien WhatsApp.

Partagé par les propositions commerciales et les relances de fin de licence.

**Le courriel part du serveur cloud** (SMTP du `.env`, le même que pour les
demandes de renouvellement). Sans SMTP — une installation locale, un poste de
développement —, rien ne part et l'appelant reçoit l'erreur : il ne doit
jamais annoncer « envoyé » sur la foi d'un backend console.

**WhatsApp ne s'automatise pas** sans l'API payante de Meta : on produit un
lien `wa.me` qui ouvre la conversation avec le message déjà rédigé ; l'envoi
reste un clic humain.
"""
import base64
import logging
import re
from urllib.parse import quote

from django.conf import settings
from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)

# Gmail refuse au-delà de 25 Mo : on garde de la marge pour l'encodage base64
# (un tiers de plus) et l'enveloppe du message.
TAILLE_MAX_PIECES = 17 * 1024 * 1024


class EnvoiErreur(ValueError):
    """Refus lisible : adresse manquante, SMTP absent, pièces trop lourdes."""


def smtp_configure():
    from apps.licences.renouvellement import smtp_configure as configure
    return configure()


def adresses(texte):
    """« a@x.sn; b@y.sn , c@z.sn » → ['a@x.sn', 'b@y.sn', 'c@z.sn'] (sans doublon)."""
    vues, liste = set(), []
    for a in re.split(r'[\s,;]+', str(texte or '')):
        a = a.strip()
        if a and '@' in a and a.lower() not in vues:
            vues.add(a.lower())
            liste.append(a)
    return liste


def decoder_data_uri(contenu):
    """'data:application/pdf;base64,....' → (mime, octets). None si invalide."""
    trouve = re.match(r'data:([^;,]+);base64,(.+)$', str(contenu or ''), re.DOTALL)
    if not trouve:
        return None
    try:
        return trouve.group(1), base64.b64decode(trouve.group(2), validate=False)
    except (ValueError, TypeError):
        return None


def envoyer_courriel(sujet, corps, destinataires, pieces=(), reply_to=None, cc=None):
    """Envoie le courriel. `pieces` : [(nom_fichier, octets, mime)].

    Lève EnvoiErreur avec un message à montrer tel quel ; laisse remonter
    l'exception SMTP d'origine dans le journal.
    """
    destinataires = adresses(destinataires) if isinstance(destinataires, str) else list(destinataires)
    if not destinataires:
        raise EnvoiErreur("Aucune adresse e-mail pour ce client.")
    if not smtp_configure():
        raise EnvoiErreur("L'envoi d'e-mails n'est pas configuré sur ce serveur (SMTP).")
    if sum(len(octets) for _, octets, _ in pieces) > TAILLE_MAX_PIECES:
        raise EnvoiErreur("Les pièces jointes dépassent 17 Mo : retirez une brochure.")

    message = EmailMessage(
        subject=sujet, body=corps,
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None)
                   or getattr(settings, 'EMAIL_HOST_USER', None),
        to=destinataires, cc=adresses(cc) if cc else None,
        reply_to=adresses(reply_to) if reply_to else None)
    for nom, octets, mime in pieces:
        message.attach(nom, octets, mime)
    try:
        message.send(fail_silently=False)
    except Exception as exc:
        logger.exception('Courriel « %s » à %s : échec', sujet, destinataires)
        raise EnvoiErreur(f"Le serveur de messagerie a refusé l'envoi : {type(exc).__name__}: {exc}"[:900])
    return destinataires


def numero_whatsapp(telephone):
    """Le premier numéro exploitable, au format international sans « + ».

    « 77 656 76 14 · 70 561 53 99 » → « 221776567614 ». Un numéro sénégalais à
    9 chiffres reçoit l'indicatif 221 ; un numéro déjà international est gardé.
    """
    for morceau in re.split(r'[·/,;|]|\s{2,}', str(telephone or '')):
        chiffres = re.sub(r'\D', '', morceau)
        if chiffres.startswith('00'):
            chiffres = chiffres[2:]
        if len(chiffres) == 9 and chiffres[0] in '37':
            return '221' + chiffres
        if len(chiffres) >= 11:
            return chiffres
    return ''


def lien_whatsapp(telephone, texte):
    """Lien wa.me qui ouvre la conversation, message prérempli ; '' sans numéro."""
    numero = numero_whatsapp(telephone)
    return f'https://wa.me/{numero}?text={quote(texte)}' if numero else ''


def pieces_bibliotheque(documents):
    """[(nom, octets, mime)] des documents de la bibliothèque, dans l'ordre."""
    pieces = []
    for doc in documents:
        decode = decoder_data_uri(doc.contenu)
        if decode:
            pieces.append((doc.nom_fichier, decode[1], decode[0]))
    return pieces


def signature_editeur(params):
    """Le bas de courriel : signataire, entreprise, coordonnées."""
    lignes = [l for l in (
        params.signataire_nom,
        params.signataire_fonction,
        params.raison_sociale or 'HADY GESMAN',
        ' · '.join(x for x in (params.telephone, params.email) if x),
        params.site_web,
    ) if l]
    return '\n'.join(lignes)
