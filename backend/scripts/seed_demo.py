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
    prenom = random.choice(PRENOMS_G if genre == 'M' else PRENOMS_F)
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
        date_debut=DEBUT, date_fin=dt.date(2026, 9, 30))

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
            genre = random.choice('MF')
            nom_pere = f'{random.choice(PRENOMS_G)} {random.choice(NOMS)}'
            # Les enfants portent le nom de famille du père : une liste où les
            # noms ne se répondent pas se voit tout de suite.
            patronyme = nom_pere.split()[-1]
            prenom = random.choice(PRENOMS_G if genre == 'M' else PRENOMS_F)
            age = {'Maternelle': 5, 'Élémentaire': 8, 'Collège': 12}[section_nom]

            eleves.append(Eleve(
                tenant=tenant, exercice=exercice, section=sections[section_nom],
                classe=classe, numero=numero,
                matricule=f'GSLP-{DEBUT.year}-{numero:04d}',
                nom_complet=f'{prenom} {patronyme}', genre=genre,
                date_naissance=dt.date(DEBUT.year - age - random.randint(0, 2),
                                       random.randint(1, 12), random.randint(1, 28)),
                lieu_naissance=random.choice(['Dakar', 'Pikine', 'Guédiawaye',
                                              'Rufisque', 'Thiès', 'Mbour']),
                nom_pere=nom_pere, telephone_pere=_telephone(),
                nom_mere=f'{random.choice(PRENOMS_F)} {random.choice(NOMS)}',
                telephone_mere=_telephone(),
                date_entree=DEBUT, date_inscription=DEBUT,
                annee_entree=ANNEE, statut='INSCRIT'))

    Eleve.objects.bulk_create(eleves)
    for _, classe in classes:
        classe.effectif = EFFECTIFS[classe.nom]
        classe.save(update_fields=['effectif'])
    journal(f'{len(eleves)} élèves inscrits')
    return list(Eleve.objects.filter(exercice=exercice).order_by('numero'))


# ─── 5. Le personnel ────────────────────────────────────────────────────────
PERSONNEL = [
    ('Aminata Ndiaye',    'ADMINISTRATIF', 'Directrice',              450000, True),
    ('Ousmane Sarr',      'ADMINISTRATIF', 'Directeur des études',    350000, True),
    ('Fatou Mbaye',       'ADMINISTRATIF', 'Comptable',               280000, False),
    ('Khadija Diallo',    'ADMINISTRATIF', 'Secrétaire',              180000, False),
    ('Ibrahima Faye',     'ENSEIGNANT',    'Instituteur — CI',        220000, False),
    ('Adama Gueye',       'ENSEIGNANT',    'Institutrice — CP',       220000, False),
    ('Mamadou Thiam',     'ENSEIGNANT',    'Instituteur — CE1',       220000, False),
    ('Bineta Sow',        'ENSEIGNANT',    'Institutrice — CE2',      220000, False),
    ('Alioune Diagne',    'ENSEIGNANT',    'Instituteur — CM1',       235000, False),
    ('Rokhaya Seck',      'ENSEIGNANT',    'Institutrice — CM2',      235000, False),
    ('Serigne Kane',      'ENSEIGNANT',    'Professeur de français',  260000, False),
    ('Coumba Niang',      'ENSEIGNANT',    'Professeure de maths',    260000, False),
    ('Astou Camara',      'ENSEIGNANT',    'Éducatrice — Maternelle', 195000, False),
    ('Babacar Dieng',     'PERSONNEL',     'Surveillant général',     165000, False),
    ('Maimouna Touré',    'PERSONNEL',     'Agente d\'entretien',     120000, False),
]


def creer_personnel(tenant):
    for rang, (nom, type_emp, poste, salaire, cadre) in enumerate(PERSONNEL, 1):
        Employe.objects.create(
            tenant=tenant, matricule=f'EMP-{rang:03d}', nom_complet=nom,
            type_employe=type_emp, poste=poste, type_contrat='CDI',
            date_embauche=dt.date(2025 - random.randint(0, 5),
                                  random.randint(1, 12), 1),
            salaire_base=salaire, telephone=_telephone(),
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


def creer_paiements(client, exercice, eleves):
    total, refuses = 0, 0
    for eleve in eleves:
        section = eleve.section
        profil = _profil()

        # L'inscription se règle à l'entrée, sauf pour les familles en retard.
        if profil != 'en_retard' or random.random() < 0.6:
            reponse = client.post('/api/paiements/paiements/', {
                'eleve': str(eleve.id), 'exercice': str(exercice.id),
                'montant_inscription': int(section.frais_inscription),
                'montant_uniforme': int(section.frais_uniforme),
                'montant_fournitures': int(section.frais_fournitures),
                'date_paiement': _date_du_mois(10).isoformat(),
                'mode_paiement': random.choice(MODES),
                'observations': 'Inscription et fournitures',
            }, format='json')
            total += 1
            refuses += reponse.status_code != 201

        if profil == 'en_retard':
            continue

        mois_regles = (MOIS_SCOLAIRES if profil == 'a_jour'
                       else MOIS_SCOLAIRES[:random.randint(2, 6)])
        # Les familles règlent rarement mois par mois : on regroupe par deux ou
        # trois, comme au guichet.
        paquet = []
        for mois in mois_regles:
            paquet.append(mois)
            if len(paquet) >= random.randint(1, 3) or mois == mois_regles[-1]:
                reponse = client.post('/api/paiements/paiements/', {
                    'eleve': str(eleve.id), 'exercice': str(exercice.id),
                    'montant_mensualite': int(section.frais_mensualite) * len(paquet),
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
            'compte_credit': tresorerie, 'date_ecriture': date_charge.isoformat(),
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


# ─── Assemblage ─────────────────────────────────────────────────────────────
def main():
    print(f'\nConstruction de la démonstration — {ECOLE}\n')

    tenant, exercice, directrice = creer_ecole()
    sections = creer_sections(tenant)
    classes = creer_classes(tenant)
    eleves = creer_eleves(tenant, exercice, sections, classes)
    creer_personnel(tenant)
    creer_notes(tenant, classes)

    # Le plan comptable doit exister avant la première écriture.
    from django.core.management import call_command
    call_command('init_plan_comptable', verbosity=0)

    call_command('init_parametres_fiscaux', verbosity=0)

    client = APIClient()
    client.force_authenticate(user=directrice)
    creer_paiements(client, exercice, eleves)
    creer_charges(client)
    creer_paie(client, list(Employe.objects.values_list('id', flat=True)))

    from apps.comptabilite.models import JournalEntry
    ecritures = JournalEntry.objects.filter(tenant=tenant).count()

    print(f'\n  Base : {tenant.nom} — {len(eleves)} élèves, {ecritures} écritures')
    print('  Connexion : directrice@lespalmiers.sn / Demo2026!')
    print('\n  python manage.py runserver 8765 --settings=config.settings.demo\n')


if __name__ == '__main__':
    main()
