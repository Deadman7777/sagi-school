"""De la soumission brute à la fiche prospect.

Ce module est le point de passage unique : le formulaire du site vitrine y
entre aujourd'hui, l'assistant SAMA y entrera demain quand il conduira le
diagnostic. Un seul endroit qui décide de créer ou de compléter une fiche,
donc un seul comportement à corriger le jour où il déraille.

**Le rapprochement, et pourquoi il compte.** Un prospect qui remplit le
formulaire deux fois — parce qu'il n'a pas eu de réponse, ou qu'il hésite entre
deux offres — ne doit pas produire deux fiches. Deux fiches, c'est deux
commerciaux qui rappellent le même directeur, et un historique coupé en deux.
On rapproche donc sur le téléphone d'abord (le plus fiable au Sénégal, où
beaucoup d'établissements n'ont pas d'adresse électronique), puis sur le
courriel, puis sur le couple établissement + ville.

**Compléter n'est pas écraser.** Une seconde soumission remplit les champs
restés vides ; elle ne remplace jamais une valeur déjà connue, et ne touche
jamais au statut commercial. Sans cette règle, un prospect qui renvoie le
formulaire ferait retomber à « Nouveau » une affaire déjà qualifiée.
"""
import re

from django.db import transaction

from .models import InteractionProspect, Prospect

# Les champs recopiés tels quels depuis la soumission, avec leur longueur
# maximale. Un formulaire public envoie ce qu'il veut, y compris 40 000
# caractères dans « ville » : on tronque au lieu de lever une erreur.
CHAMPS_TEXTE = {
    'etablissement': 200, 'type_organisation': 30, 'date_creation': 40,
    'adresse': 300, 'ville': 120, 'telephone': 60, 'email': 254,
    'site_web': 200, 'contact_nom': 200, 'contact_fonction': 150,
    'contact_telephone': 60, 'contact_email': 254,
    'pouvoir_decisionnel': 80, 'disponibilites': 300,
}
CHAMPS_NOMBRE = ('nb_eleves', 'nb_employes', 'nb_classes', 'nb_sites')

# Au-delà, ce n'est plus un message mais un dépôt : on garde de quoi
# comprendre la demande, pas de quoi remplir la base.
MAX_MESSAGE = 2000
MAX_BRUT = 20000


def normaliser_telephone(valeur):
    """La forme sur laquelle deux numéros se comparent.

    On ne garde que les chiffres, puis les neuf derniers : c'est la longueur
    d'un numéro sénégalais sans indicatif. « +221 77 123 45 67 »,
    « 00221771234567 » et « 77 123 45 67 » se rejoignent donc sur `771234567`.
    Un numéro plus court est gardé tel quel — mieux vaut ne pas rapprocher que
    rapprocher à tort deux établissements différents.
    """
    chiffres = re.sub(r'\D', '', str(valeur or ''))
    return chiffres[-9:] if len(chiffres) >= 9 else chiffres


def _nombre(valeur):
    """« environ 300 élèves » vaut 300. Ce qui n'a aucun chiffre vaut None.

    Le formulaire annonce un nombre mais rien n'empêche d'y écrire une phrase,
    et la phrase entière reste de toute façon dans `donnees_brutes`.
    """
    chiffres = re.sub(r'\D', '', str(valeur or ''))
    if not chiffres:
        return None
    try:
        return min(int(chiffres), 2_000_000_000)   # borne du PositiveIntegerField
    except ValueError:
        return None


def _texte(donnees, cle, longueur):
    return str(donnees.get(cle, '') or '').strip()[:longueur]


def _origines(donnees):
    brut = donnees.get('origines') or donnees.get('origine') or []
    if not isinstance(brut, list):
        brut = [brut]
    return [o for o in (str(x).strip()[:60] for x in brut) if o][:8]


def extraire(donnees):
    """La soumission brute rendue sous la forme des champs du modèle.

    Séparé de l'enregistrement pour être testable seul, et parce que l'API de
    saisie manuelle a besoin du même nettoyage sans la logique de doublon.
    """
    champs = {cle: _texte(donnees, cle, n) for cle, n in CHAMPS_TEXTE.items()}
    # Le formulaire du site nomme le téléphone de l'établissement `telephone`
    # et celui du contact `contact_telephone`, mais les premières versions
    # n'envoyaient que l'un des deux : on accepte l'un pour l'autre.
    if not champs['telephone']:
        champs['telephone'] = champs['contact_telephone']
    if not champs['contact_telephone']:
        champs['contact_telephone'] = champs['telephone']

    champs['telephone_cle'] = normaliser_telephone(champs['telephone'])
    champs.update({cle: _nombre(donnees.get(cle)) for cle in CHAMPS_NOMBRE})
    champs['origines'] = _origines(donnees)
    champs['origine_details'] = str(donnees.get('origine_details', '') or '').strip()[:MAX_MESSAGE]
    champs['message'] = str(donnees.get('message', '') or '').strip()[:MAX_MESSAGE]
    return champs


def trouver_existant(champs):
    """La fiche que cette soumission vient probablement compléter, ou None."""
    if cle := champs.get('telephone_cle'):
        if p := Prospect.objects.filter(telephone_cle=cle).first():
            return p
    for adresse in (champs.get('contact_email'), champs.get('email')):
        if adresse:
            trouve = Prospect.objects.filter(email__iexact=adresse).first() \
                or Prospect.objects.filter(contact_email__iexact=adresse).first()
            if trouve:
                return trouve
    if champs.get('etablissement'):
        return Prospect.objects.filter(
            etablissement__iexact=champs['etablissement'],
            ville__iexact=champs.get('ville', '')).first()
    return None


@transaction.atomic
def enregistrer_demande(donnees, source='SITE', canal='SITE', resume=None,
                        auteur=''):
    """Enregistre une demande et rend `(prospect, cree)`.

    `cree` vaut False quand la demande a rejoint une fiche existante — l'appelant
    s'en sert pour signaler « demande déjà connue » plutôt que « nouveau
    prospect » dans la notification.
    """
    champs = extraire(donnees)
    if not champs['etablissement']:
        raise ValueError("Le nom de l'établissement est obligatoire.")

    brut = {cle: valeur for cle, valeur in dict(donnees).items()
            if cle != 'site_web_confirmation'}   # le miel du piège à robots

    prospect = trouver_existant(champs)
    cree = prospect is None

    if cree:
        prospect = Prospect(source=source, donnees_brutes=_borner(brut), **champs)
        prospect.save()
    else:
        # Compléter, jamais écraser : ce qu'on sait déjà a été vérifié par un
        # commercial, la nouvelle soumission ne l'a pas été.
        modifies = []
        for cle, valeur in champs.items():
            if valeur in (None, '', []):
                continue
            if not getattr(prospect, cle):
                setattr(prospect, cle, valeur)
                modifies.append(cle)
        if modifies:
            prospect.save(update_fields=modifies + ['updated_at'])

    InteractionProspect.objects.create(
        prospect=prospect, canal=canal, auteur=auteur,
        resume=resume or _resume_par_defaut(champs, cree))
    return prospect, cree


def _borner(brut):
    """`donnees_brutes` garde la soumission, pas un fichier déposé dedans."""
    total, garde = 0, {}
    for cle, valeur in brut.items():
        texte = str(valeur)[:MAX_BRUT]
        total += len(texte)
        if total > MAX_BRUT:
            break
        garde[str(cle)[:60]] = texte
    return garde


def _resume_par_defaut(champs, cree):
    lignes = ["Demande de démonstration reçue depuis le site."
              if cree else
              "Nouvelle demande reçue depuis le site (fiche déjà existante)."]
    if champs.get('disponibilites'):
        lignes.append(f"Disponibilités : {champs['disponibilites']}")
    if champs.get('message'):
        lignes.append(f"Message : {champs['message']}")
    return "\n".join(lignes)
