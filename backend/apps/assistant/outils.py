"""Le diagnostic conduit : ce que SAMA recueille, et ce que le serveur en fait.

**C'est ici que se matérialise le principe arrêté par la direction — l'assistant
recueille, nos serveurs rédigent.** SAMA ne dispose d'aucun modèle de fiche de
diagnostic : la fiche HG-COM-002 est confidentielle et ne lui est pas remise
(voir `connaissance.py`). Ce qu'il a à la place, c'est le **schéma** ci-dessous.
Il ne recopie pas un document, il remplit un formulaire dont le serveur possède
seul la mise en forme. Le jour où l'on produira un devis (étape 4), le même
principe s'appliquera aux montants : ils viendront du catalogue, pas d'une
mémoire.

**Le schéma est le document.** Chaque champ décrit ce qu'il attend, en français,
parce que c'est cette description que le modèle lit pour décider quoi demander
au visiteur. Un champ mal décrit ici produit une question mal posée là-bas : ce
fichier se relit comme on relit un questionnaire, pas comme on relit du code.

**Un seul champ obligatoire : le nom de l'établissement.** Exiger davantage
reviendrait à ne jamais rien enregistrer — un visiteur donne son numéro à la
fin d'un échange, ou pas du tout. Une fiche sans moyen de rappel vaut tout de
même mieux que rien : elle dit qu'un daara de Rufisque cherche à s'équiper.
"""
import logging
from datetime import date, timedelta

from apps.licences.models import Licence

logger = logging.getLogger(__name__)

NOM_OUTIL = 'enregistrer_le_prospect'

# Nombre d'exécutions autorisées pour un même message du visiteur. Deux suffit
# largement — enregistrer, puis éventuellement corriger. Sans borne, un modèle
# qui boucle appelle l'outil indéfiniment et chaque tour se paie.
MAX_APPELS_PAR_TOUR = 2


def definition_outil():
    """Le schéma remis au modèle. Constant : il fait partie du préfixe mis en
    cache, avant le prompt système, et ne doit pas varier d'un appel à l'autre."""
    licences = ', '.join(code for code, _ in Licence.TYPE_CHOICES)
    return {
        'name': NOM_OUTIL,
        'description': (
            "Transmet à l'équipe commerciale de HADY GESMAN la situation de "
            "l'établissement avec lequel tu échanges, pour qu'elle le rappelle "
            "et lui prépare une proposition.\n\n"
            "Appelle cet outil UNE SEULE FOIS par conversation, quand tu as "
            "compris qui est cet établissement et ce qu'il cherche — pas dès "
            "la première phrase. Ne l'appelle pas pour une question purement "
            "informative (« combien coûte la licence Pro ? ») à laquelle tu "
            "viens de répondre et qui n'appelle aucune suite.\n\n"
            "Ne renseigne QUE ce que le visiteur t'a dit. N'invente aucun "
            "numéro, aucun effectif, aucune ville. Un champ inconnu se laisse "
            "vide — c'est une information juste, contrairement à une supposition."
        ),
        'input_schema': {
            'type': 'object',
            'properties': {
                'etablissement': {
                    'type': 'string',
                    'description': "Nom de l'établissement, tel que le visiteur l'écrit.",
                },
                'type_organisation': {
                    'type': 'string',
                    'description': "Daara, École privée, Franco-arabe, "
                                   "Centre de formation, PME, ou autre.",
                },
                'ville': {'type': 'string', 'description': "Ville ou région."},
                'telephone': {
                    'type': 'string',
                    'description': "Numéro donné par le visiteur, tel quel.",
                },
                'email': {'type': 'string', 'description': "Adresse électronique."},
                'contact_nom': {
                    'type': 'string',
                    'description': "Nom de la personne avec qui tu échanges.",
                },
                'contact_fonction': {
                    'type': 'string',
                    'description': "Sa fonction : directeur, gestionnaire, "
                                   "comptable, fondateur…",
                },
                'nb_eleves': {
                    'type': 'integer',
                    'description': "Effectif d'élèves ou de bénéficiaires.",
                },
                'nb_employes': {
                    'type': 'integer',
                    'description': "Nombre d'enseignants et d'employés.",
                },
                'situation_actuelle': {
                    'type': 'string',
                    'description': "Comment l'établissement gère aujourd'hui : "
                                   "cahiers, Excel, un autre logiciel, rien.",
                },
                'besoins': {
                    'type': 'string',
                    'description': "Ce que le visiteur cherche à régler, dans "
                                   "SES mots. C'est le champ le plus utile au "
                                   "commercial qui rappellera : ne le résume "
                                   "pas en un mot.",
                },
                'licence_pressentie': {
                    'type': 'string',
                    'description': f"La licence qui semble adaptée ({licences}). "
                                   "C'est une orientation pour l'équipe, pas un "
                                   "engagement pris devant le visiteur.",
                },
                'accord_rappel': {
                    'type': 'boolean',
                    'description': "Le visiteur a-t-il accepté d'être rappelé ? "
                                   "Demande-le-lui avant d'enregistrer ses "
                                   "coordonnées ; ne réponds pas oui à sa place.",
                },
            },
            'required': ['etablissement'],
        },
    }


def _resume_diagnostic(donnees):
    """La fiche telle que le commercial la lira. Rédigée par le serveur.

    Les champs sont remis dans l'ordre d'un entretien — la situation, le besoin,
    la taille, l'orientation — et non dans celui, arbitraire, où le modèle les a
    fournis.
    """
    lignes = ["Diagnostic recueilli par l'assistant SAMA sur sagi-school.com.", ""]

    def ajouter(etiquette, valeur):
        if valeur not in (None, '', []):
            lignes.append(f"{etiquette} : {valeur}")

    ajouter("Situation actuelle", donnees.get('situation_actuelle'))
    ajouter("Besoin exprimé", donnees.get('besoins'))
    ajouter("Effectif", donnees.get('nb_eleves'))
    ajouter("Personnel", donnees.get('nb_employes'))

    licence = (donnees.get('licence_pressentie') or '').upper()
    if licence:
        ajouter("Licence pressentie",
                dict(Licence.TYPE_CHOICES).get(licence, licence))

    if donnees.get('accord_rappel'):
        lignes += ["", "Le visiteur a accepté d'être rappelé."]
    else:
        lignes += ["", "⚠ Le visiteur n'a pas explicitement accepté d'être "
                       "rappelé — à prendre en compte avant de l'appeler."]
    return "\n".join(lignes)


def executer(donnees, conversation=None):
    """Enregistre le diagnostic au fichier prospects. Rend (texte, prospect).

    `texte` est ce qui repart vers le modèle : une confirmation courte, sans
    identifiant interne — le visiteur n'en a que faire, et le modèle la lui
    répéterait. En cas d'échec, le message dit au modèle quoi faire, jamais
    l'erreur technique : elle finirait affichée dans la fenêtre de discussion.
    """
    from apps.prospects.enregistrement import enregistrer_demande

    try:
        prospect, _ = enregistrer_demande(
            # `besoins` alimente le champ `message` de la fiche ; les clés que
            # le modèle de données ignore atterrissent dans `donnees_brutes`,
            # où rien ne se perd.
            {**donnees, 'message': donnees.get('besoins') or ''},
            source='ASSISTANT', canal='ASSISTANT',
            resume=_resume_diagnostic(donnees), auteur='SAMA')
    except ValueError:
        return ("Le nom de l'établissement est nécessaire pour transmettre la "
                "situation. Demande-le au visiteur, puis réessaie.", None)
    except Exception:
        logger.exception('SAMA — enregistrement du diagnostic en échec')
        return ("La transmission n'a pas abouti. Invite le visiteur à appeler "
                "le +221 70 328 61 51, sans lui parler d'erreur technique.", None)

    # Une fiche dont le visiteur a dit oui doit apparaître dès demain dans
    # « à relancer » : c'est ce qui transforme une conversation en rendez-vous.
    if donnees.get('accord_rappel') and prospect.relance_le is None:
        prospect.relance_le = date.today() + timedelta(days=1)
        prospect.save(update_fields=['relance_le', 'updated_at'])

    if conversation is not None and conversation.prospect_id is None:
        conversation.prospect = prospect
        conversation.save(update_fields=['prospect', 'updated_at'])

    suite = ("L'équipe rappellera." if donnees.get('accord_rappel')
             else "Propose au visiteur d'être rappelé, s'il ne l'a pas déjà refusé.")
    return (f"Situation transmise à l'équipe commerciale de HADY GESMAN. {suite} "
            f"Confirme-le au visiteur en une phrase, sans détailler ce que tu as "
            f"transmis, et reste disponible pour ses questions.", prospect)


OUTILS = {NOM_OUTIL: executer}
