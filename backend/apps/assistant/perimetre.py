"""Le périmètre réel de chaque licence, lu DANS LE CODE.

L'assistant a interdiction d'inventer une fonctionnalité. Cette interdiction ne
vaut rien si sa documentation, elle, en invente : le catalogue commercial
annonçait une « gestion des emplois du temps » qui n'existe nulle part dans le
logiciel, et une gestion fiscale en licence Pro alors que le module est réservé
à l'Avancé.

Un document se périme ; le code, non. Ce fichier ne DÉCRIT pas les licences, il
les INTERROGE : la liste vient de `Licence.MODULES_PAR_TYPE`, la source de
vérité qu'applique réellement le contrôle d'accès. Ajoutez un module à une
licence et le texte remis à l'assistant suit, sans que personne ait à y penser.
"""
from apps.licences.models import Licence

# Ce qu'un module ouvre concrètement, dit dans les mots du client — pas en
# noms de routes. C'est la seule partie rédigée à la main, et elle ne parle que
# de modules qui existent : une clé sans route correspondante ne s'affiche pas.
MODULES = {
    '/dashboard':     ("Tableau de bord",
                       "vue d'ensemble : effectifs, encaissements du mois, "
                       "impayés, résultat, alertes"),
    '/eleves':        ("Élèves",
                       "inscriptions, fiches, tuteurs, échéanciers, "
                       "import Excel, certificats de scolarité"),
    '/paiements':     ("Paiements",
                       "encaissements, reçus PDF, suivi des créances, "
                       "relances, clôture d'exercice"),
    '/comptabilite':  ("Comptabilité",
                       "SYSCOHADA Révisé : journal, grand livre, balance, "
                       "bilan, compte de résultat, charges, immobilisations"),
    '/suivi-mensuel': ("Suivi mensuel",
                       "recettes et dépenses mois par mois, marge, "
                       "comparaison au budget"),
    '/academique':    ("Gestion académique",
                       "classes, matières, coefficients, notes, moyennes, "
                       "rangs, bulletins PDF, analyse des résultats"),
    '/rh':            ("Ressources humaines",
                       "personnel, contrats, paie, bulletins, avances, "
                       "déclarations sociales"),
    '/fiscal':        ("Fiscal",
                       "obligations IS, IMF, CFCE, TVA, CEL, échéancier "
                       "fiscal et conseils"),
    '/gmrf':          ("Mobilisation des ressources financières",
                       "subventions, dons, prêts, échéanciers de "
                       "remboursement, tableaux de bord bailleurs"),
    '/gouvernance':   ("Gouvernance",
                       "projets, gestion électronique des documents, "
                       "budget analytique, traçabilité des ressources"),
}


def modules_de(type_licence):
    """Les modules ouverts par une licence, en clair. Ordre du code conservé."""
    routes = Licence.MODULES_PAR_TYPE.get(type_licence, [])
    return [MODULES[r] for r in routes if r in MODULES]


def texte_perimetre():
    """Le périmètre des cinq licences, prêt à être remis à l'assistant."""
    lignes = [
        "# Périmètre réel des licences SAGI SCHOOL",
        "",
        "Généré automatiquement depuis le code du logiciel "
        "(`apps/licences/models.py`). C'est ce que le contrôle d'accès applique "
        "réellement, et cela prime sur tout document commercial.",
        "",
    ]
    for code, libelle in Licence.TYPE_CHOICES:
        lignes.append(f"## Licence {libelle}")
        lignes.append("")
        for nom, detail in modules_de(code):
            lignes.append(f"- **{nom}** — {detail}")
        lignes.append("")

    # Ce que le logiciel ne fait pas. Sans cette liste, un prospect qui demande
    # « gérez-vous les emplois du temps ? » n'obtient qu'un silence, que
    # l'assistant est tenté de combler.
    lignes += [
        "## Ce que SAGI SCHOOL ne fait pas aujourd'hui",
        "",
        "À dire clairement si la question est posée, sans le présenter comme "
        "une évolution prévue :",
        "",
        "- **Emplois du temps** — aucune génération ni gestion d'emploi du temps.",
        "- **Cantine et transport** — pas de module dédié ; ces prestations se "
        "gèrent comme des services optionnels facturés à l'élève.",
        "- **Portail parents / élèves** — pas d'accès en ligne pour les familles.",
        "- **Bibliothèque, infirmerie, internat** — non couverts.",
        "- **Pointage biométrique, présences** — non couverts.",
        "",
    ]
    return "\n".join(lignes)
