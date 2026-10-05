"""Dossier ETAFI (états financiers de synthèse, SYSCOHADA Révisé) d'un exercice.

Les chiffres viennent de apps/comptabilite/etats.py (un seul calcul pour
l'écran, les exports et la liasse). Ici : l'assemblage du dossier.

- Système normal (SN) : page de garde, fiches R1 (identification) et R2
  (activités), bilan actif, bilan passif, compte de résultat, tableau des
  flux de trésorerie, notes annexes, balance générale, contrôles.
- Système minimal de trésorerie (SMT, petites entités : recettes sous le
  seuil de l'AUDCIF pour les services) : page de garde, R1, R2, bilan et
  compte de résultat simplifiés, état de trésorerie, notes, balance, contrôles.

Chaque document est téléchargeable seul ; le dossier complet est un ZIP
(un PDF par document + la liasse en un seul PDF + la balance en CSV + le
résumé des contrôles), archivé en base avec son empreinte (EtafiArchive).
"""
import csv
import hashlib
import io
import json
import zipfile
from io import BytesIO

from django.template.loader import render_to_string
from django.utils import timezone

from . import etats

DOCUMENTS_SN = [
    ('garde', '00_page_de_garde', 'Page de garde'),
    ('r1', '01_fiche_R1_identification', "Fiche R1 — Identification de l'entité"),
    ('r2', '02_fiche_R2_activites', "Fiche R2 — Activités de l'entité"),
    ('bilan_actif', '03_bilan_actif', 'Bilan — Actif'),
    ('bilan_passif', '04_bilan_passif', 'Bilan — Passif'),
    ('compte_resultat', '05_compte_de_resultat', 'Compte de résultat'),
    ('tft', '06_tableau_des_flux', 'Tableau des flux de trésorerie'),
    ('notes', '07_notes_annexes', 'Notes annexes'),
    ('balance', '08_balance_generale', 'Balance générale'),
    ('controles', '09_controles', 'Contrôles de cohérence'),
]
DOCUMENTS_SMT = [
    ('garde', '00_page_de_garde', 'Page de garde'),
    ('r1', '01_fiche_R1_identification', "Fiche R1 — Identification de l'entité"),
    ('r2', '02_fiche_R2_activites', "Fiche R2 — Activités de l'entité"),
    ('bilan_smt', '03_bilan_smt', 'Bilan (système minimal de trésorerie)'),
    ('resultat_smt', '04_compte_de_resultat_smt', 'Compte de résultat (système minimal de trésorerie)'),
    ('tresorerie_smt', '05_etat_de_tresorerie', 'État de la trésorerie'),
    ('notes', '06_notes_annexes', 'Notes annexes'),
    ('balance', '07_balance_generale', 'Balance générale'),
    ('controles', '08_controles', 'Contrôles de cohérence'),
]


def systeme_par_defaut(tenant, exercice):
    """SN ou SMT selon le chiffre d'affaires (XB) et le seuil de l'AUDCIF."""
    from .views import SEUIL_SMT_SERVICES
    ca = etats.compte_resultat_etafi(exercice)['chiffre_affaires']
    return 'SN' if ca >= SEUIL_SMT_SERVICES else 'SMT'


def documents(systeme):
    return DOCUMENTS_SMT if systeme == 'SMT' else DOCUMENTS_SN


def _profil(tenant):
    from apps.fiscal.moteur import profil_de
    return profil_de(tenant)


def construire(tenant, exercice, systeme=None):
    """Toutes les données du dossier (sans rendu)."""
    systeme = systeme or systeme_par_defaut(tenant, exercice)
    bilan = etats.bilan_etafi(exercice)
    cr = etats.compte_resultat_etafi(exercice)
    tft = etats.tft_etafi(exercice)
    notes = etats.notes_etafi(tenant, exercice)
    balance = etats.balance_generale(tenant, exercice)
    from .activites import resultats_par_activite
    from .exercices import controle_continuite, exercice_precedent
    activites = resultats_par_activite(tenant, exercice)
    precedent = exercice_precedent(exercice)

    from django.db.models import Sum
    from .models import JournalEntry
    agg = JournalEntry.objects.filter(tenant=tenant, exercice=exercice).aggregate(
        d=Sum('debit'), c=Sum('credit'))
    ecart_journal = float((agg['d'] or 0) - (agg['c'] or 0))
    controles = [
        {'libelle': 'Journal équilibré (total débit = total crédit)', 'ok': abs(ecart_journal) < 1,
         'detail': f'Écart : {ecart_journal:,.0f}'.replace(',', ' ')},
        {'libelle': 'Bilan équilibré (BZ = DZ)', 'ok': bilan['equilibre'],
         'detail': f"Actif {bilan['total_actif']:,.0f} — Passif {bilan['total_passif']:,.0f}".replace(',', ' ')},
        {'libelle': 'Résultat du compte de résultat = résultat du bilan (XI = CJ)',
         'ok': abs(cr['resultat'] - bilan['resultat']) < 1,
         'detail': f"XI {cr['resultat']:,.0f} — CJ {bilan['resultat']:,.0f}".replace(',', ' ')},
        {'libelle': 'Trésorerie du TFT = trésorerie du bilan (ZH = BT − DT)',
         'ok': abs(tft['ecart']) < 1,
         'detail': f"Écart : {tft['ecart']:,.0f}".replace(',', ' ')},
        {'libelle': 'Somme des résultats par activité = résultat net',
         'ok': abs(activites['total_resultat'] - cr['resultat']) < 1,
         'detail': f"{activites['total_resultat']:,.0f}".replace(',', ' ')},
    ]
    if precedent is not None and exercice.an_genere_le:
        ecarts = controle_continuite(precedent, exercice)
        controles.append({'libelle': f'Continuité : à-nouveaux conformes à la clôture {precedent.annee_scolaire}',
                          'ok': not ecarts,
                          'detail': f'{len(ecarts)} écart(s)' if ecarts else 'Conforme'})
    elif precedent is not None:
        controles.append({'libelle': f'Continuité avec {precedent.annee_scolaire}', 'ok': None,
                          'detail': "À-nouveaux non générés : ouverture par les soldes initiaux "
                                    "de trésorerie seulement."})
    return {'systeme': systeme, 'bilan': bilan, 'cr': cr, 'tft': tft, 'notes': notes,
            'balance': balance, 'activites': activites, 'controles': controles,
            'precedent': precedent.annee_scolaire if precedent else None,
            'profil': _profil(tenant)}


def resume(donnees):
    return {'systeme': donnees['systeme'], 'total_bilan': donnees['bilan']['total_actif'],
            'resultat': donnees['cr']['resultat'], 'chiffre_affaires': donnees['cr']['chiffre_affaires'],
            'tresorerie': donnees['tft']['tresorerie_bilan'],
            'controles_ok': all(c['ok'] is not False for c in donnees['controles'])}


# ── Contexte de rendu par document ───────────────────────────────────────────
def _tableau_simple(lignes, colonnes, cles):
    return {'colonnes': colonnes,
            'lignes': [{'cellules': [l.get(k) for k in cles], 'total': l.get('total', False)} for l in lignes]}


def _contexte(code, tenant, exercice, d, titre, statut):
    base = {'tenant': tenant, 'exercice': exercice, 'titre': titre, 'systeme': d['systeme'],
            'statut': statut, 'date_edition': timezone.localdate(), 'profil': d['profil'],
            'precedent': d['precedent'], 'tables': [], 'paragraphes': []}
    n1 = f"Net {d['precedent']}" if d['precedent'] else 'Net N-1'
    if code == 'garde':
        base['gabarit'] = 'garde'
        base['documents'] = [t for _c, _f, t in documents(d['systeme'])[1:]]
    elif code == 'r1':
        p = d['profil']
        base['gabarit'] = 'fiche'
        base['champs'] = [
            ('Dénomination sociale', tenant.nom),
            ('Forme juridique', p.get_forme_juridique_display() if p else '—'),
            ('Statut', p.get_statut_display() if p else '—'),
            ('Régime fiscal', p.get_regime_display() if p else '—'),
            ('NINEA', tenant.ninea or '—'), ('RCCM', tenant.rccm or '—'),
            ("Numéro d'autorisation d'ouverture", tenant.numero_autorisation or '—'),
            ('Adresse', f"{tenant.adresse or ''} {tenant.ville or ''}".strip() or '—'),
            ('Téléphone / courriel', ' · '.join(x for x in (tenant.telephone, tenant.email) if x) or '—'),
            ('Dirigeant', f"{tenant.get_directeur_civilite_display() if tenant.directeur_civilite else ''} "
                          f"{tenant.directeur_nom or ''}".strip() or '—'),
            ('Activité principale', 'Enseignement privé'),
            ('Exercice', f"{exercice.annee_scolaire} — du {exercice.date_debut:%d/%m/%Y} au "
                         f"{exercice.date_fin:%d/%m/%Y}"),
            ('Durée (mois)', str(round((exercice.date_fin - exercice.date_debut).days / 30.44))),
            ('Système comptable', 'Système normal' if d['systeme'] == 'SN'
             else 'Système minimal de trésorerie'),
            ('Exercice précédent', d['precedent'] or 'Premier exercice dans SAGI SCHOOL'),
        ]
    elif code == 'r2':
        base['tables'] = [{'titre': 'Activités exercées', **_tableau_simple(
            [{'a': a['libelle'], 'b': a['produits'], 'c': a['charges'], 'd': a['resultat'],
              'e': (f"{a['produits'] / d['activites']['total_produits'] * 100:.1f} %"
                    if d['activites']['total_produits'] else '—')}
             for a in d['activites']['activites']]
            + [{'a': 'TOTAL', 'b': d['activites']['total_produits'], 'c': d['activites']['total_charges'],
                'd': d['activites']['total_resultat'], 'e': '100 %', 'total': True}],
            ['Activité', 'Produits', 'Charges', 'Résultat', 'Part du produit'], ['a', 'b', 'c', 'd', 'e'])}]
    elif code == 'bilan_actif':
        base['tables'] = [{'titre': '', **_tableau_simple(
            d['bilan']['actif'], ['Réf.', 'Actif', 'Brut', 'Amort. / Dépréc.', 'Net', n1],
            ['ref', 'libelle', 'brut', 'amort', 'net', 'net_n1'])}]
    elif code == 'bilan_passif':
        base['tables'] = [{'titre': '', **_tableau_simple(
            d['bilan']['passif'], ['Réf.', 'Passif', 'Net', n1], ['ref', 'libelle', 'net', 'net_n1'])}]
        base['paragraphes'] = ["CH comprend les capitaux d'ouverture non ventilés (soldes initiaux de "
                               "trésorerie et à-nouveaux nets du compte 890) lorsque l'établissement n'a "
                               "pas saisi de bilan d'entrée détaillé."]
    elif code == 'compte_resultat':
        base['tables'] = [{'titre': '', **_tableau_simple(
            d['cr']['lignes'], ['Réf.', 'Libellé', '', 'Net', n1], ['ref', 'libelle', 'signe', 'net', 'net_n1'])}]
    elif code == 'tft':
        base['tables'] = [{'titre': '', **_tableau_simple(
            d['tft']['lignes'], ['Réf.', 'Libellé', 'Net', n1], ['ref', 'libelle', 'net', 'net_n1'])}]
        if abs(d['tft']['ecart']) >= 1:
            base['paragraphes'] = [f"Écart de rapprochement avec la trésorerie du bilan : "
                                   f"{d['tft']['ecart']:,.0f} FCFA (écritures hors schéma : voir le journal)."
                                   .replace(',', ' ')]
    elif code == 'notes':
        base['tables'] = [{'titre': f"Note {n['numero']} — {n['titre']}", 'colonnes': n['colonnes'],
                           'lignes': [{'cellules': l, 'total': (l[1] == 'TOTAL' if len(l) > 1 else False)
                                       or l[0] == 'TOTAL'} for l in n['lignes']]}
                          for n in d['notes']]
    elif code == 'balance':
        b = d['balance']
        base['paysage'] = True
        base['tables'] = [{'titre': '', 'colonnes': ['Compte', 'Libellé', 'Ouv. débit', 'Ouv. crédit',
                                                     'Mvt débit', 'Mvt crédit', 'Clôt. débit', 'Clôt. crédit'],
                           'lignes': [{'cellules': [l['compte'], l['libelle'], l['ouv_d'], l['ouv_c'], l['mvt_d'],
                                                    l['mvt_c'], l['clo_d'], l['clo_c']], 'total': False}
                                      for l in b['lignes']]
                           + [{'cellules': ['', 'TOTAUX'] + [b['totaux'].get(k, 0) for k in
                                                             ('ouv_d', 'ouv_c', 'mvt_d', 'mvt_c', 'clo_d', 'clo_c')],
                               'total': True}]}]
    elif code == 'controles':
        base['gabarit'] = 'controles'
        base['controles'] = d['controles']
    elif code == 'bilan_smt':
        a = {l['ref']: l for l in d['bilan']['actif']}
        p = {l['ref']: l for l in d['bilan']['passif']}
        lignes = [
            {'a': 'Immobilisations (nettes)', 'b': a['AZ']['net'], 'c': a['AZ']['net_n1']},
            {'a': 'Stocks', 'b': a['BB']['net'], 'c': a['BB']['net_n1']},
            {'a': 'Créances (familles, clients, autres)', 'b': a['BG']['net'], 'c': a['BG']['net_n1']},
            {'a': 'Trésorerie', 'b': a['BT']['net'], 'c': a['BT']['net_n1']},
            {'a': 'TOTAL ACTIF', 'b': a['BZ']['net'], 'c': a['BZ']['net_n1'], 'total': True},
            {'a': 'Capitaux propres (dont résultat)', 'b': p['CP']['net'], 'c': p['CP']['net_n1']},
            {'a': 'Dettes financières', 'b': p['DD']['net'], 'c': p['DD']['net_n1']},
            {'a': 'Dettes circulantes', 'b': p['DP']['net'], 'c': p['DP']['net_n1']},
            {'a': 'Trésorerie-passif', 'b': p['DT']['net'], 'c': p['DT']['net_n1']},
            {'a': 'TOTAL PASSIF', 'b': p['DZ']['net'], 'c': p['DZ']['net_n1'], 'total': True},
        ]
        base['tables'] = [{'titre': '', **_tableau_simple(lignes, ['Rubrique', 'Exercice N', n1], ['a', 'b', 'c'])}]
    elif code == 'resultat_smt':
        v = {l['ref']: l for l in d['cr']['lignes']}
        groupes = [('Recettes', [('Prestations de services (scolarité, activités)', ('TB', 'TC', 'TD', 'TA')),
                                 ("Subventions d'exploitation", ('TG',)), ('Autres recettes', ('TE', 'TF', 'TH', 'TI', 'TK', 'TL', 'TM', 'TJ', 'TN', 'TO'))]),
                   ('Dépenses', [('Achats', ('RA', 'RB', 'RC', 'RD', 'RE', 'RF')), ('Transports et services extérieurs', ('RG', 'RH')),
                                 ('Impôts et taxes', ('RI',)), ('Charges de personnel', ('RK',)),
                                 ('Autres charges', ('RJ', 'RL', 'RM', 'RN', 'RO', 'RP', 'RQ', 'RS'))])]
        lignes = []
        for titre_g, sous in groupes:
            tot = tot1 = 0
            for lib, refs in sous:
                n = sum(v[r]['net'] for r in refs)
                n_1 = sum((v[r]['net_n1'] or 0) for r in refs) if d['precedent'] else None
                tot += n
                tot1 += n_1 or 0
                lignes.append({'a': lib, 'b': round(n, 2), 'c': n_1})
            lignes.append({'a': f'TOTAL {titre_g.upper()}', 'b': round(tot, 2),
                           'c': round(tot1, 2) if d['precedent'] else None, 'total': True})
        lignes.append({'a': 'RÉSULTAT NET', 'b': v['XI']['net'], 'c': v['XI']['net_n1'], 'total': True})
        base['tables'] = [{'titre': '', **_tableau_simple(lignes, ['Rubrique', 'Exercice N', n1], ['a', 'b', 'c'])}]
    elif code == 'tresorerie_smt':
        notes11 = next(n for n in d['notes'] if n['numero'] == '11')
        t = {l['ref']: l['net'] for l in d['tft']['lignes']}
        base['tables'] = [
            {'titre': 'Variation de la trésorerie', **_tableau_simple([
                {'a': 'Trésorerie au début de l’exercice', 'b': t['ZA']},
                {'a': 'Flux des activités opérationnelles', 'b': t['ZB']},
                {'a': "Flux d'investissement", 'b': t['ZC']},
                {'a': 'Flux de financement', 'b': t['ZF']},
                {'a': 'Trésorerie à la fin de l’exercice', 'b': t['ZH'], 'total': True}],
                ['Rubrique', 'Montant'], ['a', 'b'])},
            {'titre': 'Soldes par compte de trésorerie', 'colonnes': notes11['colonnes'],
             'lignes': [{'cellules': l, 'total': l[1] == 'TOTAL'} for l in notes11['lignes']]},
        ]
    return base


def _cellule(v, colonne_montant):
    """{'v': texte, 'n': aligné à droite}. Montants en FCFA, espace insécable
    comme séparateur de milliers, sans décimale."""
    from decimal import Decimal
    # Jamais de cellule vide : xhtml2pdf ramène sa colonne à zéro.
    if v is None or v == '':
        return {'v': '—' if colonne_montant else '\xa0', 'n': colonne_montant}
    if isinstance(v, bool):
        return {'v': 'oui' if v else 'non', 'n': False}
    if isinstance(v, (int, float, Decimal)):
        n = round(float(v))
        return {'v': f'{n:,}'.replace(',', ' ') if n else '0', 'n': True}
    return {'v': str(v), 'n': False}


def _largeurs(table):
    """Largeurs de colonnes en pourcentages ENTIERS (xhtml2pdf écrase une
    colonne sans largeur, et lit mal les décimales). Une colonne de texte
    prend la place ; les montants se partagent le reste."""
    n = len(table['colonnes'])
    if n <= 1:
        return [100]
    texte_en_premier = any(l['cellules'][1]['n'] for l in table['lignes'] if len(l['cellules']) > 1)
    if texte_en_premier or n == 2:
        k = min(18, 60 // (n - 1))
        return [100 - k * (n - 1)] + [k] * (n - 1)
    k = min(15, 60 // (n - 2))
    return [9, 100 - 9 - k * (n - 2)] + [k] * (n - 2)


def rendre_pdf(code, tenant, exercice, donnees, statut='PROVISOIRE'):
    from xhtml2pdf import pisa
    titre = next((t for c, _f, t in documents(donnees['systeme']) if c == code), code)
    contexte = _contexte(code, tenant, exercice, donnees, titre, statut)
    for t in contexte['tables']:
        for l in t['lignes']:
            l['cellules'] = [_cellule(v, i >= 2) for i, v in enumerate(l['cellules'])]
        t['entetes'] = list(zip(t['colonnes'], _largeurs(t)))
    html = render_to_string('pdf/etafi_document.html', contexte)
    tampon = BytesIO()
    if pisa.CreatePDF(html, dest=tampon, encoding='utf-8').err:
        raise RuntimeError(f'Rendu PDF impossible : {code}')
    return tampon.getvalue()


def balance_csv(donnees):
    tampon = io.StringIO()
    w = csv.writer(tampon, delimiter=';')
    w.writerow(['Compte', 'Libellé', 'Ouverture débit', 'Ouverture crédit', 'Mouvements débit',
                'Mouvements crédit', 'Clôture débit', 'Clôture crédit'])
    for l in donnees['balance']['lignes']:
        w.writerow([l['compte'], l['libelle']] + [str(l[k]).replace('.', ',') for k in
                                                  ('ouv_d', 'ouv_c', 'mvt_d', 'mvt_c', 'clo_d', 'clo_c')])
    return tampon.getvalue().encode('utf-8-sig')


def dossier_zip(tenant, exercice, systeme=None, statut='PROVISOIRE'):
    """(octets du ZIP, données) : tous les documents + liasse complète."""
    from pypdf import PdfWriter
    donnees = construire(tenant, exercice, systeme)
    tampon = BytesIO()
    liasse = PdfWriter()
    prefixe = f"ETAFI_{exercice.annee_scolaire}"
    with zipfile.ZipFile(tampon, 'w', zipfile.ZIP_DEFLATED) as z:
        for code, fichier, _titre in documents(donnees['systeme']):
            pdf = rendre_pdf(code, tenant, exercice, donnees, statut)
            z.writestr(f"{prefixe}/{fichier}.pdf", pdf)
            liasse.append(BytesIO(pdf))
        complet = BytesIO()
        liasse.write(complet)
        z.writestr(f"{prefixe}/{prefixe}_liasse_complete.pdf", complet.getvalue())
        z.writestr(f"{prefixe}/balance_generale.csv", balance_csv(donnees))
        z.writestr(f"{prefixe}/controles.json", json.dumps(
            {'exercice': exercice.annee_scolaire, 'etablissement': tenant.nom,
             'genere_le': timezone.now().isoformat(), 'statut': statut,
             **resume(donnees), 'controles': donnees['controles']}, ensure_ascii=False, indent=2))
    return tampon.getvalue(), donnees


def archiver(tenant, exercice, utilisateur=None, systeme=None, observations=''):
    """Génère le dossier complet et l'archive (nouvelle version)."""
    from django.db.models import Max
    from .models import EtafiArchive
    statut = 'DEFINITIF' if exercice.cloture else 'PROVISOIRE'
    contenu, donnees = dossier_zip(tenant, exercice, systeme, statut)
    version = (EtafiArchive.objects.filter(tenant=tenant, exercice=exercice)
               .aggregate(m=Max('version'))['m'] or 0) + 1
    return EtafiArchive.objects.create(
        tenant=tenant, exercice=exercice, version=version, statut=statut,
        systeme=donnees['systeme'], genere_par=utilisateur, contenu_zip=contenu,
        taille=len(contenu), empreinte=hashlib.sha256(contenu).hexdigest(),
        resume=resume(donnees), observations=observations)
