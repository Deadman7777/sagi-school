"""Peuple l'instance de démonstration — l'école qu'on filme et qu'on photographie.

**Pourquoi un script et non une base sauvegardée.** Les captures doivent être
refaites à chaque version du logiciel, sinon elles montrent une interface qui
n'existe plus. Une base figée vieillit en silence ; un script se rejoue.

**Pourquoi l'API et non l'ORM pour les mouvements d'argent.** Dans SAGI SCHOOL,
il n'y a pas de saisie comptable : c'est l'enregistrement d'un règlement ou
d'une charge qui écrit lui-même ses écritures. Créer un paiement directement en
base donnerait une école dont le tableau de bord affiche des recettes, mais dont
le grand livre est vide — et la vidéo montrerait un bilan faux. Les données de
référence (sections, classes, élèves, personnel) passent en revanche par l'ORM :
elles ne produisent aucune écriture, et l'API n'y ajouterait que de la lenteur.

**Une école entièrement inventée.** Aucun nom, aucun numéro, aucun montant ne
vient d'une école cliente. C'est la seule garantie qui tienne quand les images
finissent sur un site public.

Usage :

    rm -f demo.sqlite3
    python manage.py migrate --settings=config.settings.demo
    python scripts/seed_demo.py
    python manage.py runserver 8765 --settings=config.settings.demo
"""
import datetime as dt
import os
import random
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.demo')

import django  # noqa: E402

django.setup()

from django.utils import timezone  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

from apps.academique.models import (Classe, Evaluation, Matiere,  # noqa: E402
                                    NiveauScolaire, Note, TypeEvaluation)
from apps.eleves.models import Eleve, Section  # noqa: E402
from apps.licences.models import Licence  # noqa: E402
from apps.paiements.models import Exercice  # noqa: E402
from apps.rh.models import Employe  # noqa: E402
from apps.tenants.models import Tenant  # noqa: E402
from apps.users.models import User  # noqa: E402

# Graine fixe : deux exécutions donnent la même école. Une capture refaite six
# mois plus tard doit pouvoir être comparée à la précédente.
random.seed(1789)

ECOLE = 'Groupe Scolaire Les Palmiers'
ANNEE = '2025-2026'
DEBUT = dt.date(2025, 10, 1)
FIN = dt.date(2026, 6, 30)
NB_MENSUALITES = 9

PRENOMS_G = ['Moussa', 'Abdoulaye', 'Cheikh', 'Ibrahima', 'Mamadou', 'Ousmane',
             'Alioune', 'Modou', 'Babacar', 'Serigne', 'Pape', 'Assane',
             'Lamine', 'Souleymane', 'Amadou', 'Malick', 'Idrissa', 'Saliou']
PRENOMS_F = ['Aminata', 'Fatou', 'Mariama', 'Awa', 'Khadija', 'Ndèye',
             'Sokhna', 'Adama', 'Bineta', 'Rokhaya', 'Astou', 'Coumba',
             'Dieynaba', 'Maimouna', 'Aïssatou', 'Seynabou', 'Yacine', 'Penda']
NOMS = ['Diop', 'Ndiaye', 'Fall', 'Sarr', 'Gueye', 'Ba', 'Sow', 'Diallo',
        'Faye', 'Sy', 'Mbaye', 'Cissé', 'Thiam', 'Diagne', 'Seck', 'Kane',
        'Camara', 'Dieng', 'Niang', 'Touré', 'Sagna', 'Badji', 'Wade', 'Sène']


def journal(message):
    print(f'  · {message}')


def _nom(genre):
    prenom = random.choice(PRENOMS_G if genre == 'G' else PRENOMS_F)
    return f'{prenom} {random.choice(NOMS)}'


def _telephone():
    return f'7{random.choice("068")} {random.randint(100, 999)} '\
           f'{random.randint(10, 99)} {random.randint(10, 99)}'


# ─── 1. L'école, sa licence, son exercice, son directeur ────────────────────
def creer_ecole():
    if Tenant.objects.exists():
        raise SystemExit("Une école existe déjà — supprimez demo.sqlite3 d'abord.")

    tenant = Tenant.objects.create(
        nom=ECOLE, ville='Dakar', adresse='Sicap Liberté 6, Villa 8452',
        telephone='33 824 15 07', email='contact@lespalmiers.sn',
        rccm='SN-DKR-2019-B-4471', ninea='0074512983',
        numero_autorisation='MEN/DAJLD/2019-0412',
        code_etablissement='GSLP', periode_scolaire='TRIMESTRE', nb_periodes=3,
        echeance_mensualite='DEBUT_MOIS')

    Licence.objects.create(
        tenant=tenant, cle_licence='DEMO-AVAN-2025-PALM',
        type='AVANCE', statut='ACTIVE',
        date_debut=DEBUT, date_fin=dt.date(2027, 7, 31))

    exercice = Exercice.objects.create(
        tenant=tenant, annee_scolaire=ANNEE, date_debut=DEBUT, date_fin=FIN,
        nb_mensualites=NB_MENSUALITES, solde_initial_caisse=Decimal('350000'),
        solde_initial_banque=Decimal('1200000'))

    directrice = User.objects.create_user(
        email='directrice@lespalmiers.sn', password='Demo2026!',
        nom='Ndiaye', prenom='Aminata', role='ADMIN_ECOLE', tenant=tenant)

    journal(f'{ECOLE} — licence Avancée, exercice {ANNEE} ({NB_MENSUALITES} mensualités)')
    return tenant, exercice, directrice


# ─── 2. Les sections et leurs tarifs ────────────────────────────────────────
SECTIONS = [
    # (nom, inscription, mensualité, uniforme, fournitures)
    ('Maternelle',  60000, 25000, 15000, 10000),
    ('Élémentaire', 75000, 30000, 18000, 12000),
    ('Collège',     90000, 40000, 20000, 15000),
]


def creer_sections(tenant):
    sections = {}
    for ordre, (nom, insc, mens, unif, four) in enumerate(SECTIONS):
        sections[nom] = Section.objects.create(
            tenant=tenant, nom=nom, ordre=ordre,
            frais_inscription=insc, frais_mensualite=mens,
            frais_uniforme=unif, frais_fournitures=four)
    journal(f'{len(sections)} sections tarifées')
    return sections


# ─── 3. Niveaux, classes, matières ──────────────────────────────────────────
CLASSES = [
    # (section, niveau_code, niveau_nom, classe)
    ('Maternelle',  'MATERNELLE',  'Maternelle',  'Grande Section'),
    ('Élémentaire', 'ELEMENTAIRE', 'Élémentaire', 'CI'),
    ('Élémentaire', 'ELEMENTAIRE', 'Élémentaire', 'CP'),
    ('Élémentaire', 'ELEMENTAIRE', 'Élémentaire', 'CE1'),
    ('Élémentaire', 'ELEMENTAIRE', 'Élémentaire', 'CE2'),
    ('Élémentaire', 'ELEMENTAIRE', 'Élémentaire', 'CM1'),
    ('Élémentaire', 'ELEMENTAIRE', 'Élémentaire', 'CM2'),
    ('Collège',     'MOYEN',       'Moyen',       '6e'),
]

MATIERES = {
    'Maternelle':  [('Éveil', 2), ('Langage', 3), ('Graphisme', 2)],
    'Élémentaire': [('Français', 4), ('Mathématiques', 4), ('Éveil scientifique', 2),
                    ('Histoire-Géographie', 2), ('Anglais', 2), ('Éducation religieuse', 2)],
    'Collège':     [('Français', 5), ('Mathématiques', 5), ('Anglais', 3),
                    ('Sciences de la vie et de la Terre', 3), ('Histoire-Géographie', 3),
                    ('Physique-Chimie', 3), ('Éducation religieuse', 2)],
}


def creer_classes(tenant):
    niveaux, classes = {}, []
    for section, code, nom_niveau, nom_classe in CLASSES:
        if code not in niveaux:
            niveaux[code] = NiveauScolaire.objects.create(
                tenant=tenant, nom=nom_niveau, code=code, ordre=len(niveaux))
        classe = Classe.objects.create(
            tenant=tenant, niveau=niveaux[code], nom=nom_classe,
            code=nom_classe.upper().replace(' ', ''), ordre=len(classes))
        for ordre, (nom, coef) in enumerate(MATIERES[section]):
            Matiere.objects.create(tenant=tenant, classe=classe, nom=nom,
                                   coefficient=coef, ordre=ordre)
        classes.append((section, classe))
    journal(f'{len(classes)} classes, {Matiere.objects.count()} matières')
    return classes


# ─── 4. Les élèves ──────────────────────────────────────────────────────────
# Répartition par classe. Le total fait 187 : un effectif d'école de quartier,
# assez grand pour que les listes aient l'air vraies, assez petit pour que le
# peuplement tienne en une minute.
EFFECTIFS = {'Grande Section': 22, 'CI': 26, 'CP': 25, 'CE1': 24,
             'CE2': 23, 'CM1': 22, 'CM2': 21, '6e': 24}


def creer_eleves(tenant, exercice, sections, classes):
    eleves, numero = [], 0
    for section_nom, classe in classes:
        for _ in range(EFFECTIFS[classe.nom]):
            numero += 1
            genre = random.choice('GF')
            nom_pere = f'{random.choice(PRENOMS_G)} {random.choice(NOMS)}'
            # Les enfants portent le nom de famille du père : une liste où les
            # noms ne se répondent pas se voit tout de suite.
            patronyme = nom_pere.split()[-1]
            prenom = random.choice(PRENOMS_G if genre == 'G' else PRENOMS_F)
            age = {'Maternelle': 5, 'Élémentaire': 8, 'Collège': 12}[section_nom]

            eleves.append(Eleve(
                tenant=tenant, exercice=exercice, section=sections[section_nom],
                classe=classe, numero=numero,
                matricule=f'{DEBUT.year}-GSLP-{numero:04d}',
                nom_complet=f'{prenom} {patronyme.upper()}', genre=genre,
                date_naissance=dt.date(DEBUT.year - age - random.randint(0, 2),
                                       random.randint(1, 12), random.randint(1, 28)),
                lieu_naissance=random.choice(['Dakar', 'Pikine', 'Guédiawaye',
                                              'Rufisque', 'Thiès', 'Mbour']),
                nom_pere=nom_pere, telephone_pere=_telephone(),
                nom_mere=f'{random.choice(PRENOMS_F)} {random.choice(NOMS)}',
                telephone_mere=_telephone(),
                date_entree=DEBUT, date_inscription=DEBUT,
                annee_entree=ANNEE, statut='INSCRIT'))

    _creer_des_fratries(eleves)
    Eleve.objects.bulk_create(eleves)
    for _, classe in classes:
        classe.effectif = EFFECTIFS[classe.nom]
        classe.save(update_fields=['effectif'])
    journal(f'{len(eleves)} élèves inscrits')
    return list(Eleve.objects.filter(exercice=exercice).order_by('numero'))


def _creer_des_fratries(eleves):
    """Donne des frères et sœurs à quelques élèves, comme dans une vraie école.

    Les parents étaient tirés au sort pour chaque enfant : la démo n'avait donc
    pas une seule fratrie, alors qu'aucune école n'en manque — et le
    regroupement des familles n'y montrait rien du tout.

    Une fratrie, c'est le même père, le même numéro et le même patronyme, mais
    des classes différentes : c'est précisément ce que l'école voit sur le
    terrain, et ce qui justifie de ne plus saisir cinq fois les mêmes
    coordonnées.
    """
    familles = [(5, 'Ousmane Ndiaye'), (4, 'Modou Fall'), (3, 'Cheikh Diop'),
                (2, 'Abdoulaye Sow'), (2, 'Ibrahima Ba')]
    disponibles = list(eleves)
    random.shuffle(disponibles)
    for combien, pere in familles:
        if len(disponibles) < combien:
            break
        patronyme = pere.split()[-1]
        numero = _telephone()
        mere = f'{random.choice(PRENOMS_F)} {patronyme}'
        numero_mere = _telephone()
        for _ in range(combien):
            enfant = disponibles.pop()
            prenom = enfant.nom_complet.split()[0]
            enfant.nom_complet = f'{prenom} {patronyme.upper()}'
            enfant.nom_pere = pere
            enfant.telephone_pere = numero
            enfant.nom_mere = mere
            enfant.telephone_mere = numero_mere


# ─── 5. Le personnel ────────────────────────────────────────────────────────
PERSONNEL = [
    ('Aminata Ndiaye',    'ADMINISTRATION', 'Directrice',              450000, True),
    ('Ousmane Sarr',      'ADMINISTRATION', 'Directeur des études',    350000, True),
    ('Fatou Mbaye',       'ADMINISTRATION', 'Comptable',               280000, False),
    ('Khadija Diallo',    'ADMINISTRATION', 'Secrétaire',              180000, False),
    ('Ibrahima Faye',     'ENSEIGNANT',    'Instituteur — CI',        220000, False),
    ('Adama Gueye',       'ENSEIGNANT',    'Institutrice — CP',       220000, False),
    ('Mamadou Thiam',     'ENSEIGNANT',    'Instituteur — CE1',       220000, False),
    ('Bineta Sow',        'ENSEIGNANT',    'Institutrice — CE2',      220000, False),
    ('Alioune Diagne',    'ENSEIGNANT',    'Instituteur — CM1',       235000, False),
    ('Rokhaya Seck',      'ENSEIGNANT',    'Institutrice — CM2',      235000, False),
    ('Serigne Kane',      'ENSEIGNANT',    'Professeur de français',  260000, False),
    ('Coumba Niang',      'ENSEIGNANT',    'Professeure de maths',    260000, False),
    ('Astou Camara',      'ENSEIGNANT',    'Éducatrice — Maternelle', 195000, False),
    ('Babacar Dieng',     'APPUI',         'Surveillant général',     165000, False),
    ('Maimouna Touré',    'APPUI',         'Agente d\'entretien',     120000, False),
]


def creer_personnel(tenant):
    for rang, (nom, type_emp, poste, salaire, cadre) in enumerate(PERSONNEL, 1):
        Employe.objects.create(
            tenant=tenant, matricule=f'EMP-{rang:03d}', nom_complet=nom,
            type_employe=type_emp, poste=poste, type_contrat='CDI',
            date_embauche=dt.date(2025 - random.randint(0, 5),
                                  random.randint(1, 12), 1),
            salaire_base=salaire, telephone=_telephone(),
            # Le canal de paie décide du compte de trésorerie débité : tout
            # payer en espèces viderait la caisse bien au-delà de ce qu'elle
            # reçoit, et la démonstration afficherait une caisse négative.
            mode_paiement={'ADMINISTRATION': 'BANQUE', 'APPUI': 'CAISSE'}.get(
                type_emp, 'WAVE' if rang % 2 else 'ORANGE_MONEY'),
            statut='ACTIF', est_cadre=cadre,
            nb_enfants=random.randint(0, 4),
            situation_matrimoniale=random.choice(['MARIE', 'CELIBATAIRE']))
    journal(f'{len(PERSONNEL)} salariés')


# ─── 6. Les règlements ──────────────────────────────────────────────────────
# Trois profils de familles, dans des proportions qui ressemblent à la réalité
# d'une école de quartier. Une démonstration où tout le monde a payé ne montre
# ni le suivi des créances ni les relances — c'est-à-dire ce que le logiciel
# apporte de plus visible.
PROFILS = [
    ('a_jour',   0.55),   # inscription + toutes les mensualités échues
    ('partiel',  0.30),   # inscription + une partie des mensualités
    ('en_retard', 0.15),  # inscription seule, ou rien
]

MODES = ['ESPECE', 'ESPECE', 'ESPECE', 'WAVE', 'ORANGE_MONEY', 'VIREMENT']

# Les mensualités d'une année scolaire sénégalaise : octobre à juin.
MOIS_SCOLAIRES = [10, 11, 12, 1, 2, 3, 4, 5, 6]


def _profil():
    tirage, cumul = random.random(), 0.0
    for nom, part in PROFILS:
        cumul += part
        if tirage <= cumul:
            return nom
    return 'a_jour'


def _date_du_mois(mois):
    """Une date de règlement plausible dans le mois : plutôt en début de mois."""
    annee = DEBUT.year if mois >= 10 else DEBUT.year + 1
    return dt.date(annee, mois, min(random.randint(1, 12), 28))


# ─── 5 bis. Les services optionnels ─────────────────────────────────────────
# Assurance pour tous, cantine et transport pour une partie des familles : sans
# eux, le reçu ne montre jamais une ligne de service ni la part « produits
# accessoires » (758) que la comptabilité distingue du service éducatif (706).
SERVICES = [
    # (nom, montant, périodicité, part des élèves abonnés)
    ('Assurance scolaire', 5000,  'UNIQUE',  1.0),
    ('Cantine',            12000, 'MENSUEL', 0.35),
    ('Transport scolaire', 15000, 'MENSUEL', 0.15),
]


def creer_services(tenant, eleves):
    from apps.eleves.models import EleveService, Service
    abonnements = []
    for nom, montant, periodicite, part in SERVICES:
        service = Service.objects.create(tenant=tenant, nom=nom, montant=montant,
                                         periodicite=periodicite)
        for eleve in eleves:
            if random.random() < part:
                abonnements.append(EleveService(tenant=tenant, eleve=eleve,
                                                service=service))
    EleveService.objects.bulk_create(abonnements)
    journal(f'{len(SERVICES)} services, {len(abonnements)} abonnements')


def _services_de(eleve):
    """(services uniques, services mensuels) souscrits par l'élève."""
    uniques, mensuels = [], []
    for ab in eleve.abonnements.select_related('service'):
        (uniques if ab.service.periodicite == 'UNIQUE' else mensuels).append(ab.service)
    return uniques, mensuels


def _dus_famille(eleve):
    """(inscription, mensualité) que la FAMILLE règle, remises déduites.

    Payer le tarif plein d'une section à un élève pris en charge, boursier ou
    remisé au titre de la fratrie donnerait des familles en trop-perçu — une
    démonstration qui se contredit dès qu'on ouvre une fiche.
    """
    bourse = eleve.pec_organisme
    inscription = (float(eleve.section.frais_inscription)
                   - float(eleve.montant_pec_inscription)
                   - float(bourse.montant_inscription if bourse else 0))
    mensualite = (float(eleve.section.frais_mensualite) - float(eleve.pec_mensualite or 0)
                  - float(bourse.montant_mensualite if bourse else 0))
    return max(int(inscription), 0), max(int(mensualite), 0)


def creer_paiements(client, exercice, eleves):
    total, refuses = 0, 0
    for eleve in eleves:
        eleve.refresh_from_db()
        section = eleve.section
        profil = _profil()
        uniques, mensuels = _services_de(eleve)
        inscription, mensualite = _dus_famille(eleve)

        # L'inscription se règle à l'entrée, sauf pour les familles en retard.
        if profil != 'en_retard' or random.random() < 0.6:
            lignes = [{'nom': sv.nom, 'montant': int(sv.montant), 'nature': 'UNIQUE'}
                      for sv in uniques]
            reponse = client.post('/api/paiements/paiements/', {
                'eleve': str(eleve.id), 'exercice': str(exercice.id),
                'montant_inscription': inscription,
                'montant_uniforme': int(section.frais_uniforme),
                'montant_fournitures': int(section.frais_fournitures),
                'montant_divers': sum(l['montant'] for l in lignes),
                'services_regles': lignes,
                'date_paiement': _date_du_mois(10).isoformat(),
                'mode_paiement': random.choice(MODES),
                'observations': 'Inscription et fournitures',
            }, format='json')
            total += 1
            refuses += reponse.status_code != 201

        if profil == 'en_retard':
            continue

        mois_regles = (MOIS_SCOLAIRES if profil == 'a_jour'
                       else MOIS_SCOLAIRES[:random.randint(5, 8)])
        if eleve.date_sortie:
            # Un élève parti ne règle que les mois où il était là.
            mois_regles = [m for m in mois_regles if m in (10, 11, 12, 1, 2)]
        if not mois_regles or not mensualite:
            continue
        # Les familles règlent rarement mois par mois : on regroupe par deux ou
        # trois, comme au guichet.
        paquet = []
        for mois in mois_regles:
            paquet.append(mois)
            if len(paquet) >= random.randint(1, 3) or mois == mois_regles[-1]:
                lignes = [{'nom': sv.nom, 'montant': int(sv.montant) * len(paquet),
                           'nature': 'MENSUEL'} for sv in mensuels]
                reponse = client.post('/api/paiements/paiements/', {
                    'eleve': str(eleve.id), 'exercice': str(exercice.id),
                    'montant_mensualite': mensualite * len(paquet),
                    'montant_divers': sum(l['montant'] for l in lignes),
                    'services_regles': lignes,
                    'mois_regles': paquet,
                    'date_paiement': _date_du_mois(paquet[0]).isoformat(),
                    'mode_paiement': random.choice(MODES),
                }, format='json')
                total += 1
                refuses += reponse.status_code != 201
                paquet = []

    journal(f'{total} règlements enregistrés'
            + (f' — {refuses} REFUSÉS' if refuses else ''))
    if refuses:
        raise SystemExit("Des règlements ont été refusés : la comptabilité "
                         "serait incomplète, on n'enregistre pas une démo fausse.")


# ─── 7. Les charges ─────────────────────────────────────────────────────────
# Une école qui n'a que des recettes affiche un résultat absurde. Ces charges
# donnent un compte de résultat et un bilan qui tiennent debout.
CHARGES_MENSUELLES = [
    ('622',  'Loyer des locaux',                     650000, '521'),
    ('6052', 'Électricité — Senelec',                 95000, '571'),
    ('6051', 'Eau — SEN\'EAU',                        28000, '571'),
    ('628',  'Internet et téléphone',                 45000, '5521'),
    ('6054', 'Fournitures scolaires et pédagogiques', 120000, '571'),
    ('624',  'Entretien des locaux',                  60000, '571'),
]
CHARGES_PONCTUELLES = [
    (11, '627', 'Impression des supports de communication', 180000, '571'),
    (1,  '633', 'Formation des enseignants au numérique',   350000, '521'),
    (3,  '624', 'Réfection de la cour de récréation',       420000, '521'),
    (5,  '635', 'Sortie pédagogique — Île de Gorée',        275000, '571'),
]


def creer_charges(client):
    total, refuses = 0, 0

    def enregistrer(compte, libelle, montant, tresorerie, date_charge):
        nonlocal total, refuses
        reponse = client.post('/api/comptabilite/charges/', {
            'no_compte': compte, 'libelle': libelle, 'montant': montant,
            'compte_credit': tresorerie, 'date': date_charge.isoformat(),
        }, format='json')
        total += 1
        refuses += reponse.status_code != 201
        return reponse

    for mois in MOIS_SCOLAIRES:
        for compte, libelle, montant, tresorerie in CHARGES_MENSUELLES:
            enregistrer(compte, f'{libelle} — {_date_du_mois(mois):%m/%Y}',
                        montant, tresorerie, _date_du_mois(mois))

    for mois, compte, libelle, montant, tresorerie in CHARGES_PONCTUELLES:
        enregistrer(compte, libelle, montant, tresorerie, _date_du_mois(mois))

    journal(f'{total} charges enregistrées'
            + (f' — {refuses} REFUSÉES' if refuses else ''))
    return refuses


# ─── 7 bis. La paie ─────────────────────────────────────────────────────────
# Le poste le plus lourd d'une école, et de loin. Sans lui, la démonstration
# afficherait un résultat de plusieurs dizaines de millions sur 187 élèves —
# un directeur le verrait au premier coup d'œil.
#
# On passe par `/api/rh/bulletins/`, le chemin qu'emprunte réellement
# l'application : il calcule IPRES, CSS et IR au barème, et la validation
# écrit une comptabilité ÉQUILIBRÉE (661 / 422, puis les retenues en 4313 et
# 4472). L'autre chemin, `/api/rh/paies/`, débite le brut et ne crédite que le
# net — voir la note remise au user.
def creer_paie(client, employes_ids):
    bulletins, refuses = 0, 0
    for annee, mois in [(DEBUT.year, m) for m in (10, 11, 12)] + \
                       [(DEBUT.year + 1, m) for m in (1, 2, 3, 4, 5, 6)]:
        for employe_id in employes_ids:
            reponse = client.post('/api/rh/bulletins/', {
                'employe_id': str(employe_id), 'mois': mois, 'annee': annee,
            }, format='json')
            if reponse.status_code != 201:
                refuses += 1
                continue
            # La validation est ce qui écrit la comptabilité : un bulletin
            # resté en brouillon ne coûte rien à l'école.
            client.post(f"/api/rh/bulletins/{reponse.data['id']}/valider/",
                        {}, format='json')
            bulletins += 1

    journal(f'{bulletins} bulletins de paie validés'
            + (f' — {refuses} REFUSÉS' if refuses else ''))
    return refuses


def creer_avances(client, employes):
    """Avant la paie : c'est le bulletin du mois qui les impute."""
    for rang, montant, date in ((4, 50000, '2026-02-10'), (13, 120000, '2026-03-12'),
                                (9, 75000, '2026-05-06')):
        _poster(client, '/api/rh/avances/', {
            'employe': str(employes[rang]), 'montant': montant, 'date_avance': date,
            'mode_paiement': 'CAISSE', 'observations': 'Avance sur salaire'})
    journal('3 avances sur salaire')


# ─── 8. Les notes ───────────────────────────────────────────────────────────
# Deux classes suffisent pour montrer un bulletin et l'analyse des résultats :
# noter les 187 élèves sur trois trimestres ferait des milliers d'écritures
# sans rien ajouter à l'image.
CLASSES_NOTEES = ['CM2', '6e']
TRIMESTRES = ['T1', 'T2', 'T3']


def creer_notes(tenant, classes):
    types = {}
    for nom, poids in (('Devoir', 1), ('Composition', 2)):
        types[nom] = TypeEvaluation.objects.create(
            tenant=tenant, nom=nom, poids=poids)

    notes, evaluations = [], 0
    for _, classe in classes:
        if classe.nom not in CLASSES_NOTEES:
            continue
        eleves = list(Eleve.objects.filter(classe=classe))
        # Un niveau propre à chaque élève : sans cela, tous les bulletins se
        # ressemblent et les rangs n'ont aucun sens.
        niveau_eleve = {e.id: random.uniform(7.5, 17.0) for e in eleves}

        for matiere in classe.matieres.all():
            for trimestre in TRIMESTRES:
                for nom_type, mois in (('Devoir', 11), ('Composition', 12)):
                    evaluation = Evaluation.objects.create(
                        tenant=tenant, matiere=matiere, type_eval=types[nom_type],
                        trimestre=trimestre, date_eval=_date_du_mois(mois),
                        titre=f'{nom_type} {trimestre}')
                    evaluations += 1
                    for eleve in eleves:
                        valeur = niveau_eleve[eleve.id] + random.uniform(-2.5, 2.5)
                        notes.append(Note(
                            tenant=tenant, eleve=eleve, evaluation=evaluation,
                            valeur=round(min(max(valeur, 0), 20), 2)))

    Note.objects.bulk_create(notes)
    journal(f'{evaluations} évaluations, {len(notes)} notes '
            f'({", ".join(CLASSES_NOTEES)})')


# ─── 9. Ce que l'école fait d'autre que la scolarité ────────────────────────
# Le guide de formation photographie TOUS les modules. Une démonstration qui
# s'arrête aux élèves et à la paie laisse vides la garderie, les familles, les
# immobilisations, les ressources financières et la gouvernance — et le guide
# retomberait sur des captures d'une version périmée.
def _poster(client, url, donnees, attendu=(200, 201)):
    reponse = client.post(url, donnees, format='json')
    if reponse.status_code not in attendu:
        raise SystemExit(f'{url} refusé ({reponse.status_code}) : '
                         f'{getattr(reponse, "data", reponse.content)}')
    return reponse.data


def _patcher(client, url, donnees):
    reponse = client.patch(url, donnees, format='json')
    if reponse.status_code not in (200, 201):
        raise SystemExit(f'{url} refusé ({reponse.status_code}) : '
                         f'{getattr(reponse, "data", reponse.content)}')
    return reponse.data


def _logo_png():
    """Un palmier stylisé, dessiné ici : aucun logo réel ne doit apparaître."""
    import base64
    import io

    from PIL import Image, ImageDraw
    img = Image.new('RGBA', (240, 240), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((6, 6, 234, 234), fill=(11, 94, 74, 255))
    d.polygon([(112, 200), (128, 200), (124, 104), (116, 104)], fill=(233, 196, 106, 255))
    for dx, dy in ((-70, -18), (-40, -58), (0, -74), (40, -58), (70, -18)):
        d.line((120, 104, 120 + dx, 104 + dy), fill=(245, 252, 248, 255), width=13)
    tampon = io.BytesIO()
    img.save(tampon, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(tampon.getvalue()).decode()


def completer_ecole(tenant):
    """Identité complète, équipe et réglages : ce que montre Paramètres."""
    tenant.logo = _logo_png()
    tenant.inspection_academie = 'IA de Dakar'
    tenant.inspection_ief = 'IEF de Grand Dakar'
    tenant.directeur_civilite, tenant.directeur_nom = 'MME', 'Aminata Ndiaye'
    tenant.rappel_actif = True
    tenant.garde_soir_actif = True
    tenant.garde_soir_heure_limite = dt.time(17, 30)
    tenant.garde_soir_facturation_a = dt.time(17, 45)
    tenant.garde_soir_tarif = 1000
    tenant.save()
    for email, prenom, nom, role in (
            ('secretariat@lespalmiers.sn', 'Khadija', 'Diallo', 'ADMIN_SCOLARITE'),
            ('comptabilite@lespalmiers.sn', 'Fatou', 'Mbaye', 'ADMIN_COMPTABLE'),
            ('etudes@lespalmiers.sn', 'Ousmane', 'Sarr', 'LECTEUR')):
        User.objects.create_user(email=email, password='Demo2026!', nom=nom,
                                 prenom=prenom, role=role, tenant=tenant)
    from apps.comptabilite.models import CaisseEncaissement
    CaisseEncaissement.objects.create(tenant=tenant, nom='Caisse garderie',
                                      no_compte='5716')
    journal('logo, inspections, trois comptes utilisateurs, caisse garderie')


def creer_garderie(client, tenant, exercice):
    """Une section facturée à la journée et une semaine d'appels."""
    garderie = Section.objects.create(
        tenant=tenant, nom='Garderie', ordre=9, mode_tarif='JOURNEE',
        frais_inscription=10000, tarif_demi_journee=3000, tarif_journee=5000)
    enfants = []
    for numero in range(1, 9):
        genre = random.choice('GF')
        pere = f'{random.choice(PRENOMS_G)} {random.choice(NOMS)}'
        enfants.append(Eleve.objects.create(
            tenant=tenant, exercice=exercice, section=garderie, classe=None,
            numero=500 + numero, matricule=f'{DEBUT.year}-GSLP-{500 + numero:04d}',
            nom_complet=f'{random.choice(PRENOMS_G if genre == "G" else PRENOMS_F)} '
                        f'{pere.split()[-1].upper()}',
            genre=genre, date_naissance=dt.date(2022, random.randint(1, 12), 10),
            nom_pere=pere, telephone_pere=_telephone(),
            date_entree=dt.date(2026, 5, 4), date_inscription=dt.date(2026, 5, 4),
            annee_entree=ANNEE, statut='INSCRIT'))
    jours = [dt.date(2026, 6, j) for j in (1, 2, 3, 4, 5, 8, 9, 10, 11, 12)]
    for jour in jours:
        _poster(client, '/api/eleves/garderie/appel/', {
            'date': jour.isoformat(),
            'presences': [{'eleve': str(e.id),
                           'formule': random.choice(['JOURNEE', 'JOURNEE', 'DEMI_JOURNEE'])}
                          for e in enfants if random.random() < 0.8]})
    # Garde du soir : quelques retards de parents sur les élèves du primaire.
    retards = 0
    for eleve in Eleve.objects.filter(exercice=exercice, section__nom='Élémentaire')[:6]:
        for jour in random.sample(jours, 2):
            _poster(client, '/api/eleves/garde-soir/', {
                'eleve': str(eleve.id), 'date': jour.isoformat(),
                'heure_depart': random.choice(['17:50', '18:20', '18:40'])})
            retards += 1
    # La moitié des familles règle le mois de juin à la caisse de la garderie,
    # par le même chemin que le bouton « Encaisser » de l'écran Garderie.
    from apps.comptabilite.models import CaisseEncaissement
    caisse = CaisseEncaissement.objects.get(tenant=tenant, no_compte='5716')
    for enfant in enfants:
        _poster(client, '/api/paiements/paiements/', {
            'eleve': str(enfant.id), 'exercice': str(exercice.id),
            'montant_inscription': int(garderie.frais_inscription),
            'date_paiement': '2026-05-04', 'mode_paiement': 'ESPECE',
            'caisse': str(caisse.id)})
    for enfant in enfants[::2]:
        du = int(enfant.du_du_mois(6))
        if du:
            _poster(client, '/api/paiements/paiements/', {
                'eleve': str(enfant.id), 'exercice': str(exercice.id),
                'montant_mensualite': du, 'mois_regles': [6], 'part_accessoire': du,
                'date_paiement': '2026-06-15', 'mode_paiement': 'ESPECE',
                'caisse': str(caisse.id)})
    journal(f'garderie : {len(enfants)} enfants, {len(jours)} appels ; '
            f'{retards} soirs de garde')
    return enfants


def creer_familles_et_bourses(client, tenant):
    """Les fratries regroupées, un barème fratrie, un organisme boursier."""
    groupes = client.get('/api/eleves/familles/fratries-probables/').data['groupes']
    _poster(client, '/api/eleves/familles/regrouper/', {'groupes': [
        {'eleve_ids': [e['id'] for e in g['eleves']], 'nom': g['nom_propose'],
         'contact': g.get('contact') or {}} for g in groupes]})
    from django.db.models import Count

    from apps.eleves.models import BaremeFratrie, Famille, Organisme
    BaremeFratrie.objects.create(tenant=tenant, rang=2, forme_mensualite='POURCENTAGE',
                                 valeur_mensualite=10)
    BaremeFratrie.objects.create(tenant=tenant, rang=3, forme_mensualite='POURCENTAGE',
                                 valeur_mensualite=20, forme_inscription='POURCENTAGE',
                                 valeur_inscription=50)
    grande = Famille.objects.filter(tenant=tenant).annotate(
        n=Count('eleves')).order_by('-n').first()
    _poster(client, f'/api/eleves/familles/{grande.id}/appliquer-bareme/', {})

    Organisme.objects.create(tenant=tenant, nom='Fondation Horizon Éducation',
                             type='FONDATION', contact_nom='Mme Sy',
                             telephone='33 860 12 34')
    journal(f'{len(groupes)} familles regroupées, barème fratrie appliqué à '
            f'« {grande.nom} », un organisme boursier')


def creer_cas_particuliers(client, tenant, exercice):
    """Une prise en charge, une bourse, un départ : les cas du guichet."""
    from apps.eleves.models import Organisme
    eleves = list(Eleve.objects.filter(exercice=exercice, famille__isnull=True,
                                       section__nom='Élémentaire').order_by('numero'))
    orphelin, boursier, boursiere, parti = eleves[3], eleves[11], eleves[27], eleves[40]
    _patcher(client, f'/api/eleves/liste/{orphelin.id}/', {
        'prise_en_charge': 'ORPHELIN', 'obs_prise_en_charge': 'Père décédé en 2024',
        'pec_mensualite': int(orphelin.section.frais_mensualite)})
    fondation = Organisme.objects.get(tenant=tenant)
    for eleve in (boursier, boursiere):
        _poster(client, '/api/eleves/bourses/', {
            'eleve': str(eleve.id), 'organisme': str(fondation.id),
            'exercice': str(exercice.id),
            'montant_mensualite': int(eleve.section.frais_mensualite) // 2,
            'reference': 'CONV-2025-014'})
    _patcher(client, f'/api/eleves/liste/{parti.id}/', {
        'statut': 'TRANSFERE', 'date_sortie': '2026-02-13'})
    journal('une prise en charge, deux boursiers, un transfert')


def creer_proformas(client, exercice):
    """Deux proformas : une famille qui veut régler l'année d'un coup, un futur élève."""
    eleve = next(e for e in Eleve.objects.filter(exercice=exercice, famille__isnull=True,
                                                 section__nom='Collège').order_by('numero')
                 if e.reste_a_payer > 0)
    _poster(client, '/api/paiements/proformas/', {
        'mode': 'ELEVE', 'eleve_id': str(eleve.id),
        'parent_nom': eleve.nom_pere, 'parent_telephone': eleve.telephone_pere})
    section = Section.objects.get(tenant=eleve.tenant, nom='Élémentaire')
    _poster(client, '/api/paiements/proformas/', {
        'mode': 'NOUVEAU', 'section_id': str(section.id), 'date_entree': '2026-01-05',
        'beneficiaire': 'Mame Diarra GUEYE', 'parent_nom': 'Alioune Gueye',
        'parent_telephone': '77 412 55 90'})
    journal('2 proformas de scolarité')


IMMOBILISATIONS = [
    # (libellé, compte, valeur, durée, date, mode)
    ('Minibus de ramassage scolaire', '245',  12500000, 5, '2025-10-06', 'VIREMENT'),
    ('Parc informatique — 12 postes', '244',  3600000,  3, '2025-10-20', 'VIREMENT'),
    ('Tables-bancs — 60 places',      '244',  1800000,  10, '2025-11-03', 'ESPECE'),
    ('Photocopieur multifonction',    '244',  1350000,  4, '2026-01-12', 'WAVE'),
]
BUDGET = [
    # (compte, libellé, type, montant mensuel)
    ('622',  'Loyer des locaux',            'FIXE',     650000),
    ('6052', 'Électricité',                 'VARIABLE', 80000),
    ('6054', 'Fournitures pédagogiques',    'VARIABLE', 100000),
    ('624',  'Entretien et réparations',    'VARIABLE', 50000),
    ('628',  'Internet et téléphone',       'FIXE',     45000),
]


def creer_patrimoine_et_budget(client):
    for libelle, compte, valeur, duree, date, mode in IMMOBILISATIONS:
        _poster(client, '/api/comptabilite/immobilisations/', {
            'libelle': libelle, 'no_compte_immobilisation': compte,
            'no_compte_amortissement': '28' + compte[2:], 'valeur_entree': valeur,
            'duree_utilisation': duree, 'date_entree': date,
            'mode_reglement': mode,
            'compte_tresorerie': {'VIREMENT': '521', 'ESPECE': '571', 'WAVE': '5521'}[mode]})
    for compte, libelle, type_charge, montant in BUDGET:
        mois = {f'm{m:02d}': montant for m in MOIS_SCOLAIRES}
        _poster(client, '/api/comptabilite/budget/', {
            'no_compte': compte, 'libelle': libelle, 'type_charge': type_charge, **mois})
    journal(f'{len(IMMOBILISATIONS)} immobilisations, {len(BUDGET)} lignes de budget')


def creer_ressources_financieres(client):
    """Dons, subvention, tontine, prêt — puis les projets qu'ils financent."""
    types = {t['code']: t for t in client.get('/api/gmrf/types/').data}

    def type_de(*mots):
        for t in types.values():
            if all(m in t['libelle'].lower() for m in mots):
                return t['id']
        return next(iter(types.values()))['id']

    _poster(client, '/api/gmrf/financements/', {
        'type_financement': type_de('don'), 'libelle': 'Don de l\'association des parents',
        'source': 'APE des Palmiers', 'type_source': 'ASSOCIATION', 'montant': 1500000,
        'statut': 'RECU', 'date_reception': '2025-12-15', 'compte_tresorerie': '521'})
    _poster(client, '/api/gmrf/financements/', {
        'type_financement': type_de('subvention'), 'libelle': 'Subvention cantine scolaire',
        'source': 'Commune de Grand Dakar', 'type_source': 'ETAT', 'montant': 1200000,
        'statut': 'RECU', 'date_reception': '2026-01-20', 'compte_tresorerie': '521'})
    _poster(client, '/api/gmrf/financements/', {
        'type_financement': type_de('subvention'), 'libelle': 'Appui à l\'équipement numérique',
        'source': 'Ministère de l\'Éducation nationale', 'type_source': 'ETAT',
        'montant': 2500000, 'statut': 'ATTENDU'})

    cycle = _poster(client, '/api/gmrf/natt/', {
        'nom': 'Natt des enseignants', 'organisateur': 'Amicale du personnel',
        'nb_participants': 10, 'duree': 10, 'periodicite': 'MENSUELLE',
        'montant_cotisation': 200000, 'date_debut': '2025-10-05',
        'compte_tresorerie': '571'})
    for cotisation in cycle['cotisations'][:8]:
        _patcher(client, f"/api/gmrf/cotisations/{cotisation['id']}/", {
            'action': 'payer', 'date_paiement': cotisation['date_echeance'],
            'compte_tresorerie': '571'})
    _poster(client, f"/api/gmrf/natt/{cycle['id']}/reception/", {
        'numero_echeance': 6, 'date_reception': '2026-03-05'})

    pret = _poster(client, '/api/gmrf/prets/', {
        'type_pret': 'BANCAIRE', 'organisme_preteur': 'Banque de l\'Habitat du Sénégal',
        'objet': 'Construction de deux salles de classe', 'montant': 8000000,
        'taux_interet': 9.5, 'duree_mois': 36, 'periodicite': 'MENSUELLE',
        'mode_amortissement': 'CONSTANT', 'date_deblocage': '2025-11-10',
        'date_premiere_echeance': '2025-12-10', 'compte_tresorerie': '521'})
    for echeance in pret['echeances'][:7]:
        _patcher(client, f"/api/gmrf/echeances/{echeance['id']}/", {
            'action': 'payer', 'date_paiement': echeance['date_echeance'],
            'compte_tresorerie': '521'})
    journal('3 financements, une tontine, un prêt bancaire')


def creer_gouvernance(client):
    cantine = _poster(client, '/api/gouvernance/projets/', {
        'code': 'CANT-26', 'libelle': 'Programme cantine', 'responsable': 'Fatou Mbaye',
        'budget_prevu': 1200000, 'statut': 'EN_COURS', 'date_debut': '2026-01-01'})
    numerique = _poster(client, '/api/gouvernance/projets/', {
        'code': 'NUM-26', 'libelle': 'Équipement numérique', 'responsable': 'Ousmane Sarr',
        'budget_prevu': 3600000, 'statut': 'EN_COURS', 'date_debut': '2025-10-01'})
    _poster(client, '/api/gouvernance/projets/', {
        'code': 'BIB-26', 'libelle': 'Réfection de la bibliothèque',
        'responsable': 'Aminata Ndiaye', 'budget_prevu': 900000, 'statut': 'PLANIFIE'})
    ressource = _poster(client, '/api/gouvernance/ressources/', {
        'type_ressource': 'SUBVENTION', 'libelle': 'Subvention communale — cantine',
        'organisme': 'Commune de Grand Dakar', 'montant': 1200000,
        'date_ressource': '2026-01-20', 'projet_id': cantine['id']})
    _poster(client, '/api/gouvernance/ressources/', {
        'type_ressource': 'FONDS_PROPRES', 'libelle': 'Recettes scolaires affectées',
        'montant': 3600000, 'date_ressource': '2025-10-01', 'projet_id': numerique['id']})
    for mois, montant in ((2, 320000), (3, 320000)):
        _poster(client, '/api/comptabilite/charges/', {
            'no_compte': '601', 'libelle': f'Denrées de cantine — {mois:02d}/2026',
            'montant': montant, 'compte_credit': '571',
            'date': f'2026-{mois:02d}-08',
            'projet_id': cantine['id'], 'ressource_id': ressource['id']})
    for mois in (11, 12, 1, 2, 3, 4, 5, 6):
        annee = DEBUT.year if mois >= 10 else DEBUT.year + 1
        _poster(client, '/api/gouvernance/transferts/', {
            'compte_source': '571', 'compte_destination': '521',
            'montant': random.choice([1500000, 2000000, 2500000]),
            'date_transfert': f'{annee}-{mois:02d}-28',
            'observations': 'Versement des espèces en banque'})
    journal('3 projets, 2 ressources, 8 versements en banque')


def calculer_moyennes(client):
    """Ce que fait le directeur des études en fin de trimestre, par l'API."""
    for classe in Classe.objects.filter(nom__in=CLASSES_NOTEES):
        for trimestre in TRIMESTRES:
            _poster(client, '/api/academique/calculer/', {
                'classe_id': str(classe.id), 'trimestre': trimestre})
    journal(f'moyennes calculées : {", ".join(CLASSES_NOTEES)}, trois trimestres')


# ─── Assemblage ─────────────────────────────────────────────────────────────
def main():
    print(f'\nConstruction de la démonstration — {ECOLE}\n')

    tenant, exercice, directrice = creer_ecole()
    sections = creer_sections(tenant)
    classes = creer_classes(tenant)
    eleves = creer_eleves(tenant, exercice, sections, classes)
    creer_personnel(tenant)
    creer_services(tenant, eleves)
    creer_notes(tenant, classes)

    # Le plan comptable doit exister avant la première écriture.
    from django.core.management import call_command
    call_command('init_plan_comptable', verbosity=0)

    call_command('init_parametres_fiscaux', verbosity=0)

    client = APIClient()
    client.force_authenticate(user=directrice)
    completer_ecole(tenant)
    # Familles, remises et bourses AVANT les règlements : les familles paient
    # alors ce qu'elles doivent vraiment.
    creer_familles_et_bourses(client, tenant)
    creer_cas_particuliers(client, tenant, exercice)
    creer_paiements(client, exercice, eleves)
    creer_charges(client)
    creer_avances(client, list(Employe.objects.order_by('matricule')
                               .values_list('id', flat=True)))
    creer_paie(client, list(Employe.objects.values_list('id', flat=True)))

    creer_garderie(client, tenant, exercice)
    creer_proformas(client, exercice)
    creer_patrimoine_et_budget(client)
    creer_ressources_financieres(client)
    creer_gouvernance(client)
    calculer_moyennes(client)

    from apps.comptabilite.models import JournalEntry
    ecritures = JournalEntry.objects.filter(tenant=tenant).count()

    print(f'\n  Base : {tenant.nom} — {len(eleves)} élèves, {ecritures} écritures')
    print('  Connexion : directrice@lespalmiers.sn / Demo2026!')
    print('\n  python manage.py runserver 8765 --settings=config.settings.demo\n')


if __name__ == '__main__':
    main()
