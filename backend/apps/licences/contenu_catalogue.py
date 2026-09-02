"""Le texte commercial du catalogue — tout ce qui ne se déduit PAS du code.

**Ce fichier ne décrit aucune fonctionnalité.** Le périmètre de chaque licence
est produit par `apps.assistant.perimetre.modules_de()`, qui interroge
`Licence.MODULES_PAR_TYPE` — la table que le contrôle d'accès applique
réellement. C'est la leçon de la version précédente du catalogue : elle
annonçait une « gestion des emplois du temps » qui n'existe nulle part et une
gestion fiscale en licence Pro alors que le module est réservé à l'Avancé.
Un document se périme, le code non.

Ce qui reste ici est du positionnement, des prestations de service et des
conditions commerciales : rien de tout cela n'existe dans le logiciel, donc
rien ne peut en être déduit. C'est écrit à la main, et c'est assumé.
"""

# À qui s'adresse chaque licence, et à quoi elle donne droit en dehors des
# modules. Le texte de `positionnement` est commercial ; `remarque` sert aux
# précisions qui engagent (éligibilité, durée).
POSITIONNEMENT = {
    'ESSAI': {
        'accroche': 'Découvrir la plateforme avant toute souscription.',
        'positionnement': "Trente jours d'accès complet aux modules ci-dessous, "
                          "avec le paramétrage initial, une formation de prise en "
                          "main et l'assistance standard.",
        'remarque': "L'essai ne couvre pas l'ensemble des modules du logiciel : "
                    "il ouvre ceux qui permettent d'évaluer la gestion courante.",
    },
    'BASIC': {
        'accroche': 'Pour une structure qui veut d’abord remettre de l’ordre.',
        'positionnement': 'Destinée aux petites écoles, centres de formation et '
                          'établissements en phase de structuration.',
        'remarque': "La comptabilité SYSCOHADA n'est pas comprise : elle s'ouvre "
                    'à partir de la licence Pro.',
    },
    'PRO': {
        'accroche': 'Pour professionnaliser la gestion administrative et financière.',
        'positionnement': 'Reprend la licence Basic et y ajoute la comptabilité '
                          'conforme au SYSCOHADA Révisé : journal, grand livre, '
                          'balance, bilan et compte de résultat.',
        'remarque': 'Le module fiscal et la gestion académique ne sont pas compris ; '
                    'ils relèvent de la licence Avancée.',
    },
    'AVANCE': {
        'accroche': 'Pour un établissement structuré ou un groupe scolaire.',
        'positionnement': 'La totalité des modules du logiciel : à la gestion '
                          'administrative et comptable s’ajoutent l’académique, les '
                          'ressources humaines, le fiscal, la mobilisation des '
                          'ressources et la gouvernance.',
        'remarque': '',
    },
    'TAXAWU_DAARA': {
        'accroche': 'Le tarif social du programme TAXAWU DAARA 2030.',
        'positionnement': 'Conçue pour les daaras modernes et les établissements '
                          'franco-arabes. Elle ouvre les mêmes modules que la '
                          'licence Avancée : ce qui la distingue n’est pas le '
                          'périmètre, c’est le tarif et les établissements qui y '
                          'ont droit.',
        'remarque': 'Éligibilité réservée aux daaras et établissements franco-arabes, '
                    'dans le cadre du programme TAXAWU DAARA 2030.',
    },
}

# Les prestations de déploiement. Elles n'existent pas dans le logiciel : ce
# sont des interventions humaines, écrites à la main et à jour du catalogue
# 2026-2027.
DEPLOIEMENT = [
    ('Audit et diagnostic initial', 'Gratuit',
     ['Analyse des besoins',
      'Diagnostic organisationnel',
      'Identification des processus à digitaliser']),
    ('Installation et paramétrage', '100 000 FCFA',
     ["Paramétrage complet de l'établissement",
      'Création des comptes utilisateurs',
      'Configuration des classes et niveaux',
      'Configuration comptable et fiscale']),
    ('Formation des équipes', 'Comprise dans le déploiement',
     ['Formation des administrateurs',
      'Formation des utilisateurs',
      "Documentation d'utilisation"]),
    ('Migration des données', 'À partir de 50 000 FCFA',
     ['Import des élèves',
      'Import des historiques de paiements',
      'Reprise des données existantes']),
]

# L'accompagnement externalisé : le métier d'agence de HADY GESMAN, distinct
# de la licence logicielle.
ACCOMPAGNEMENT = [
    ('Pack Gestion Essentielle', 'À partir de 75 000 FCFA / mois',
     ['Organisation administrative', 'Classement documentaire',
      'Suivi administratif', 'Tableaux de bord simplifiés',
      'Assistance administrative']),
    ('Pack Comptabilité et Fiscalité', 'À partir de 150 000 FCFA / mois',
     ['Saisie comptable SYSCOHADA', 'Rapprochements bancaires',
      'Suivi des comptes clients et fournisseurs',
      'Préparation des déclarations fiscales', 'Veille réglementaire',
      'Reporting mensuel']),
    ('Pack Pilotage Financier', 'À partir de 250 000 FCFA / mois',
     ['Analyse financière', 'Prévisions de trésorerie', 'Suivi budgétaire',
      'Tableaux de bord stratégiques', 'Accompagnement du dirigeant']),
    ('Direction Administrative et Financière externalisée',
     'À partir de 400 000 FCFA / mois',
     ['Supervision administrative', 'Supervision comptable',
      'Pilotage financier', 'Relations avec les partenaires financiers',
      "Préparation des dossiers d'investissement", 'Reporting de direction']),
]

OFFRES_COMBINEES = [
    ('Pack Daara Numérique',
     'Licence Taxawu Daara + accompagnement administratif simplifié',
     'À partir de 75 000 FCFA / mois'),
    ('Pack École Performante',
     'Licence Pro + accompagnement comptable et fiscal',
     'À partir de 200 000 FCFA / mois'),
    ('Pack Groupe Scolaire Premium',
     'Licence Avancée + direction administrative et financière externalisée',
     'À partir de 350 000 FCFA / mois'),
]

DOMAINES_INTERVENTION = [
    ('Transformation numérique des établissements éducatifs',
     ['Digitalisation des processus administratifs',
      'Automatisation des opérations récurrentes',
      'Centralisation des données',
      'Production de rapports décisionnels']),
    ('Gestion administrative externalisée',
     ['Organisation documentaire', 'Gestion des procédures internes',
      'Suivi administratif', 'Archivage physique et numérique']),
    ('Gestion comptable et financière',
     ['Comptabilité conforme au SYSCOHADA Révisé', 'Suivi de trésorerie',
      'Tableaux de bord financiers', 'Pilotage budgétaire']),
    ('Gestion fiscale',
     ['Préparation des déclarations fiscales', 'Conformité fiscale',
      'Veille réglementaire', 'Assistance lors des contrôles fiscaux']),
    ('Accompagnement stratégique',
     ['Analyse financière', 'Aide à la décision',
      'Préparation des dossiers investisseurs', 'Recherche de financement']),
]

CIBLES_PLATEFORME = [
    'Écoles privées', 'Établissements franco-arabes', 'Daaras modernes',
    'Centres de formation', 'Instituts professionnels',
    'Groupes scolaires multisites',
]

MODALITES_PAIEMENT = ['Paiement mensuel', 'Paiement trimestriel',
                      'Paiement semestriel', 'Paiement annuel']

ENGAGEMENTS = [
    'Respecter les normes du SYSCOHADA Révisé',
    'Assurer la conformité avec la réglementation fiscale sénégalaise',
    'Garantir la confidentialité des données',
    'Fournir un accompagnement adapté aux réalités locales',
    'Développer des solutions durables et évolutives',
]
