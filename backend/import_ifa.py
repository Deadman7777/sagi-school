"""
Script d'import Excel → Django
École : IFA AL HILMU WAL HAMAL
Fichier : empty-sheet__17_.xlsx

Usage :
  cd ~/Documents/hady-gesman/backend
  source venv/bin/activate
  python import_ifa.py --excel /chemin/vers/empty-sheet__17_.xlsx
"""

import os, sys, django, argparse
from datetime import datetime

# ── Setup Django ─────────────────────────────────────────────
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

import pandas as pd
from apps.tenants.models import Tenant
from apps.eleves.models import Eleve, Section
from apps.paiements.models import Exercice, Paiement
from apps.comptabilite.models import JournalEntry

# ── Config ───────────────────────────────────────────────────
TENANT_NOM    = 'IFA AL HILMU WAL HAMAL'
ANNEE         = '2025-2026'
MODE_MAP = {
    'WAVE':         'WAVE',
    'ESPECE':       'ESPECE',
    'ORANGE MONEY': 'ORANGE_MONEY',
    'FREE MONEY':   'FREE_MONEY',
    'VIREMENT':     'VIREMENT',
    'CHEQUE':       'CHEQUE',
}

def log(msg):
    print(f"  {'✅' if '✅' not in msg else ''} {msg}")

def run(excel_path):
    print("\n" + "="*60)
    print("  IMPORT EXCEL → HADY GESMAN")
    print(f"  Fichier : {excel_path}")
    print("="*60 + "\n")

    # ── Charger Excel ────────────────────────────────────────
    print("📂 Chargement Excel...")
    sheets = pd.read_excel(excel_path, sheet_name=None, header=None)

    # ── Récupérer Tenant ─────────────────────────────────────
    print(f"\n🏫 Tenant...")
    try:
        tenant = Tenant.objects.get(nom=TENANT_NOM)
        log(f"✅ Trouvé : {tenant.nom}")
    except Tenant.DoesNotExist:
        print(f"  ❌ Tenant '{TENANT_NOM}' introuvable !")
        print("  → Créez-le d'abord dans l'admin Django")
        sys.exit(1)

    # ── Récupérer Exercice ───────────────────────────────────
    print(f"\n📅 Exercice {ANNEE}...")
    try:
        exercice = Exercice.objects.get(tenant=tenant, annee_scolaire=ANNEE)
        log(f"✅ Trouvé : {exercice.annee_scolaire}")
    except Exercice.DoesNotExist:
        print(f"  ❌ Exercice '{ANNEE}' introuvable !")
        print("  → Créez-le d'abord dans l'admin Django")
        sys.exit(1)

    # ── Créer/Récupérer Sections ─────────────────────────────
    print("\n📚 Sections...")
    SECTIONS_CONFIG = {
        'Grande Section': {'inscription': 20000, 'mensualite': 15000, 'uniforme': 35000, 'fournitures': 20000, 'yendu': 10000},
        'Moyenne Section': {'inscription': 20000, 'mensualite': 15000, 'uniforme': 35000, 'fournitures': 15000, 'yendu': 8000},
        'Petite Section':  {'inscription': 20000, 'mensualite': 15000, 'uniforme': 30000, 'fournitures': 15000, 'yendu': 8000},
        'Garderie':        {'inscription': 20000, 'mensualite': 25000, 'uniforme': 32000, 'fournitures': 15000, 'yendu': 10000},
    }

    sections = {}
    for nom, frais in SECTIONS_CONFIG.items():
        section, created = Section.objects.get_or_create(
            tenant=tenant, nom=nom,
            defaults={
                'frais_inscription':  frais['inscription'],
                'frais_mensualite':   frais['mensualite'],
                'frais_uniforme':     frais['uniforme'],
                'frais_fournitures':  frais['fournitures'],
                'frais_yendu':        frais['yendu'],
            }
        )
        sections[nom] = section
        log(f"✅ {'Créée' if created else 'Existante'} : {nom}")

    # ── Importer Élèves ──────────────────────────────────────
    print("\n👥 Import des élèves...")
    df_eleves = sheets['BASE_ELEVES']
    eleves_map = {}  # nom → objet Eleve
    nb_crees = nb_existants = 0

    for i in range(5, df_eleves.shape[0]):
        row = df_eleves.iloc[i]
        if pd.isna(row[1]) or not isinstance(row[1], (int, float)):
            continue
        try:
            num = int(row[1])
            nom = str(row[2]) if not pd.isna(row[2]) else ''
            if not nom or nom == 'nan' or num > 100:
                continue

            section_nom = str(row[3]) if not pd.isna(row[3]) else 'Grande Section'
            section     = sections.get(section_nom, sections.get('Grande Section'))
            genre_raw   = str(row[19]).strip() if not pd.isna(row[19]) else 'G'
            genre       = 'F' if genre_raw == 'F' else 'G'
            telephone   = str(row[13]).replace("'", '').strip() if not pd.isna(row[13]) else ''
            date_insc   = row[14].date() if not pd.isna(row[14]) and hasattr(row[14], 'date') else None

            eleve, created = Eleve.objects.get_or_create(
                tenant=tenant,
                exercice=exercice,
                nom_complet=nom,
                defaults={
                    'numero':           num,
                    'section':          section,
                    'genre':            genre,
                    'telephone_parent': telephone,
                    'date_inscription': date_insc or exercice.date_debut,
                    'statut':           'INSCRIT',
                }
            )
            eleves_map[nom] = eleve
            if created:
                nb_crees += 1
            else:
                nb_existants += 1

        except Exception as e:
            print(f"  ⚠️  Ligne {i} ignorée: {e}")
            continue

    log(f"✅ {nb_crees} élèves créés, {nb_existants} déjà existants")
    print(f"  📊 Total élèves en base : {len(eleves_map)}")

    # ── Importer Paiements ───────────────────────────────────
    print("\n💰 Import des paiements...")
    df_recettes = sheets['SAISIE_RECETTES']
    nb_paie_crees = nb_paie_existants = 0
    total_importe = 0

    for i in range(5, df_recettes.shape[0]):
        row = df_recettes.iloc[i]
        if pd.isna(row[1]) or not isinstance(row[1], (int, float)):
            continue
        try:
            nom_eleve = str(row[3]) if not pd.isna(row[3]) else ''
            if not nom_eleve or nom_eleve == 'nan':
                continue

            no_piece  = str(row[12]) if not pd.isna(row[12]) else f'REC-{int(row[1]):04d}'
            date_paie = row[2].date() if not pd.isna(row[2]) and hasattr(row[2], 'date') else exercice.date_debut
            uniforme  = int(row[5])  if not pd.isna(row[5])  else 0
            fourni    = int(row[6])  if not pd.isna(row[6])  else 0
            inscript  = int(row[7])  if not pd.isna(row[7])  else 0
            mensual   = int(row[8])  if not pd.isna(row[8])  else 0
            cantine   = int(row[9])  if not pd.isna(row[9])  else 0
            mode_raw  = str(row[11]).strip().upper() if not pd.isna(row[11]) else 'ESPECE'
            mode      = MODE_MAP.get(mode_raw, 'ESPECE')

            # Trouver l'élève
            eleve = eleves_map.get(nom_eleve)
            if not eleve:
                # Recherche partielle
                matches = [e for n, e in eleves_map.items() if nom_eleve.lower() in n.lower()]
                eleve   = matches[0] if matches else None

            if not eleve:
                print(f"  ⚠️  Élève introuvable : {nom_eleve}")
                continue

            # Vérifier si paiement existe déjà
            if Paiement.objects.filter(no_piece=no_piece).exists():
                nb_paie_existants += 1
                continue

            # Créer le paiement (le save() génère l'écriture comptable auto)
            paiement = Paiement(
                tenant              = tenant,
                eleve               = eleve,
                exercice            = exercice,
                no_piece            = no_piece,
                date_paiement       = date_paie,
                montant_inscription = inscript,
                montant_mensualite  = mensual,
                montant_uniforme    = uniforme,
                montant_fournitures = fourni,
                montant_cantine     = cantine,
                montant_divers      = 0,
                mode_paiement       = mode,
            )
            paiement.save()
            total_importe += paiement.total
            nb_paie_crees += 1

        except Exception as e:
            print(f"  ⚠️  Recette ligne {i} ignorée: {e}")
            continue

    log(f"✅ {nb_paie_crees} paiements créés, {nb_paie_existants} déjà existants")
    print(f"  💵 Total importé : {total_importe:,.0f} FCFA")

    # ── Récapitulatif final ──────────────────────────────────
    print("\n" + "="*60)
    print("  RÉCAPITULATIF")
    print("="*60)
    print(f"  🏫 École      : {tenant.nom}")
    print(f"  📅 Exercice   : {exercice.annee_scolaire}")
    print(f"  👥 Élèves     : {Eleve.objects.filter(tenant=tenant, exercice=exercice).count()}")
    print(f"  💰 Paiements  : {Paiement.objects.filter(tenant=tenant, exercice=exercice).count()}")

    # Total recettes en base
    from django.db.models import Sum
    total_base = Paiement.objects.filter(tenant=tenant, exercice=exercice).aggregate(
        t=Sum('montant_inscription') + Sum('montant_mensualite') +
          Sum('montant_uniforme')    + Sum('montant_fournitures') +
          Sum('montant_cantine')     + Sum('montant_divers')
    )['t'] or 0
    print(f"  💵 Total recettes : {total_base:,.0f} FCFA")
    print(f"  📊 Écritures journal : {JournalEntry.objects.filter(tenant=tenant, exercice=exercice).count()}")
    print("\n  ✅ Import terminé avec succès !")
    print("="*60 + "\n")

    # Vérification vs Excel
    EXCEL_TOTAL = 5_803_000
    if abs(float(total_base) - EXCEL_TOTAL) < 1000:
        print(f"  🎯 VALIDATION : Total correspond à l'Excel ({EXCEL_TOTAL:,} FCFA) ✅")
    else:
        print(f"  ⚠️  Écart avec Excel : base={total_base:,.0f} vs excel={EXCEL_TOTAL:,}")
    print()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Import Excel IFA → Django')
    parser.add_argument('--excel', required=True, help='Chemin vers le fichier Excel')
    args = parser.parse_args()

    if not os.path.exists(args.excel):
        print(f"❌ Fichier introuvable : {args.excel}")
        sys.exit(1)

    run(args.excel)
