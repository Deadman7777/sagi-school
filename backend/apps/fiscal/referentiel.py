"""Référentiel fiscal national (Sénégal) installé par défaut.

Données pures : la migration 0002 et la commande `installer_referentiel_fiscal`
les installent sans jamais écraser une valeur déjà présente — une valeur
corrigée par HADY GESMAN ou par l'école reste la sienne. Une loi de finances
qui change un taux s'enregistre comme un NOUVEAU paramètre daté (date
d'effet) : les exercices passés gardent le taux de leur époque.

`a_verifier=True` signale une valeur reprise sans certitude du texte en
vigueur : l'écran l'affiche comme telle, et elle doit être confirmée (CGI,
loi de finances de l'année, DGID) avant de servir à une déclaration.
"""
import datetime

D0 = datetime.date(2013, 1, 1)          # entrée en vigueur du CGI (loi 2012-31)

# (code, libellé, valeur, unité, date d'effet, référence, à vérifier)
PARAMETRES = [
    ('IS_TAUX', "Taux de l'impôt sur les sociétés", 30, '%', D0,
     "CGI — impôt sur les sociétés, taux normal", False),
    ('IMF_TAUX', "Impôt minimum forfaitaire — taux sur le chiffre d'affaires HT", 0.5, '%', D0,
     "CGI — minimum d'imposition (IMF)", True),
    ('IMF_MIN', 'Impôt minimum forfaitaire — plancher', 500000, 'FCFA', D0,
     "CGI — minimum d'imposition (IMF)", True),
    ('IMF_MAX', 'Impôt minimum forfaitaire — plafond', 5000000, 'FCFA', D0,
     "CGI — minimum d'imposition (IMF)", True),
    ('TVA_TAUX_NORMAL', 'TVA — taux normal', 18, '%', D0, 'CGI — TVA, taux normal', False),
    ('TVA_TAUX_REDUIT', 'TVA — taux réduit (hébergement et restauration touristiques)', 10, '%', D0,
     'CGI — TVA, taux réduit', True),
    ('CFCE_TAUX', "Contribution forfaitaire à la charge de l'employeur (CFCE)", 3, '%', D0,
     'CGI — CFCE', False),
    ('RAS_PRESTATAIRES_TAUX', 'Retenue à la source sur prestations de non-résidents / non immatriculés',
     5, '%', D0, 'CGI — retenues à la source', True),
    ('CGU_SEUIL_SERVICES', 'Contribution globale unique — seuil de chiffre d’affaires (services)',
     50000000, 'FCFA', D0, 'CGI — contribution globale unique', True),
    ('ECHEANCE_DECLARATION_MOIS', 'Mois de dépôt de la déclaration annuelle (après la clôture)', 4,
     'MOIS', D0, 'CGI — obligations déclaratives (dépôt avant le 30 avril N+1)', True),
]

# Obligations : (code, libellé, base, formule, paramètres, périodicité,
# échéance, débit, crédit, conditions, message si non applicable,
# référence, à vérifier, ordre, description)
OBLIGATIONS = [
    ('IS', "Impôt sur les sociétés (IS) / minimum forfaitaire (IMF)", 'RESULTAT', 'IS_IMF',
     {'taux': 'IS_TAUX', 'minimum_taux': 'IMF_TAUX', 'minimum_plancher': 'IMF_MIN',
      'minimum_plafond': 'IMF_MAX'},
     'Annuelle', 'Acomptes 15 février et 30 avril · solde avec la déclaration (30 avril N+1)',
     '891', '441',
     {'but_lucratif': True, 'regimes': ['REEL_NORMAL', 'REEL_SIMPLIFIE']},
     "Non applicable au profil déclaré : un établissement sans but lucratif, ou relevant d'un autre "
     "régime, n'est pas soumis à l'IS sur ses activités non lucratives. Une activité lucrative "
     "accessoire peut l'être : vérifiez avec votre conseil.",
     'CGI — impôt sur les sociétés et IMF', False, 10,
     "Le montant dû est le plus élevé de l'IS (taux × résultat estimé) et du minimum forfaitaire "
     "(taux × chiffre d'affaires, entre plancher et plafond)."),
    ('CGU', 'Contribution globale unique (CGU)', 'SAISIE', 'SAISIE', {'seuil': 'CGU_SEUIL_SERVICES'},
     'Annuelle (paiements fractionnés)', "Selon l'avis d'imposition", '6418', '4428',
     {'regimes': ['CGU']}, '', 'CGI — contribution globale unique', True, 15,
     "Impôt synthétique des petites entreprises individuelles : il remplace l'impôt sur le revenu, "
     "la TVA et la CEL. Saisissez le montant de votre avis."),
    ('TVA', 'TVA', 'TVA_NETTE', 'TVA', {'taux': 'TVA_TAUX_NORMAL'},
     'Mensuelle', 'Le 15 du mois suivant', '', '',
     {'assujetti_tva': True},
     "Les prestations d'enseignement sont exonérées de TVA : ne facturez pas de TVA sur la "
     "scolarité. Une activité annexe taxable (transport de tiers, location…) rend assujetti pour "
     "cette activité : déclarez-le dans le profil fiscal et dans le paramétrage de l'activité.",
     'CGI — TVA (opérations exonérées : enseignement)', True, 20,
     'TVA facturée par les activités taxables (compte 443x) diminuée de la TVA déductible (445x).'),
    ('CFCE', "CFCE — Contribution forfaitaire à la charge de l'employeur", 'MASSE_SALARIALE',
     'MASSE_SALARIALE', {'taux': 'CFCE_TAUX'}, 'Mensuelle (avec la BRS)',
     'Le 15 du mois suivant, avec la BRS', '6413', '4421', {'employeur': True},
     "Aucun salaire versé sur l'exercice.", 'CGI — CFCE', False, 30,
     'Comptabilisée automatiquement à la validation des bulletins (module RH) ; estimée depuis '
     'le journal sinon.'),
    ('RETENUES', 'Retenues sur salaires (IR, TRIMF) et cotisations (IPRES, CSS)', 'MASSE_SALARIALE',
     'RH', {}, 'Mensuelle', 'Le 15 du mois suivant (BRS)', '', '', {'employeur': True}, '',
     'CGI — impôt sur le revenu (retenue à la source) ; Code de la sécurité sociale', False, 40,
     'Calculées et comptabilisées par le module RH à la validation des bulletins.'),
    ('CEL', 'Contribution économique locale (CEL)', 'SAISIE', 'SAISIE', {}, 'Annuelle',
     "Selon l'avis de la collectivité", '6414', '442', {'exclure_regimes': ['CGU', 'NON_ASSUJETTI']},
     '', 'CGI — contribution économique locale (CEL-VL / CEL-VA)', True, 50,
     "Due à la collectivité : valeur locative des locaux (CEL-VL) et valeur ajoutée (CEL-VA). "
     "Saisissez le montant de l'avis d'imposition."),
    ('CFPB', 'Contribution foncière des propriétés bâties', 'SAISIE', 'SAISIE', {}, 'Annuelle',
     "Selon l'avis d'imposition", '6412', '442', {'proprietaire_locaux': True},
     "L'établissement n'est pas déclaré propriétaire de ses locaux.",
     'CGI — contributions foncières', True, 60,
     "Due par le propriétaire des locaux. Certaines exonérations existent pour les immeubles "
     "affectés à l'enseignement : vérifiez votre situation."),
    ('RAS', 'Retenues à la source sur prestataires', 'AUCUNE', 'INFO',
     {'taux': 'RAS_PRESTATAIRES_TAUX'}, 'Mensuelle', 'Le 15 du mois suivant', '', '', {}, '',
     'CGI — retenues à la source', True, 70,
     "Les sommes versées à certains prestataires (non-résidents, prestataires non immatriculés) "
     "supportent une retenue à reverser : vérifiez chaque contrat."),
]


def installer(ParametreFiscal, ObligationFiscale):
    """Crée ce qui manque ; ne modifie jamais l'existant. Rend (params, obligations) créés."""
    n_p = n_o = 0
    for code, lib, val, unite, effet, ref, verif in PARAMETRES:
        _, cree = ParametreFiscal.objects.get_or_create(
            tenant=None, code=code, date_effet=effet,
            defaults={'libelle': lib, 'valeur': val, 'unite': unite, 'reference': ref,
                      'a_verifier': verif})
        n_p += cree
    for (code, lib, base, formule, params, perio, ech, deb, cred, cond, msg, ref, verif, ordre,
         desc) in OBLIGATIONS:
        _, cree = ObligationFiscale.objects.get_or_create(
            code=code, defaults={'libelle': lib, 'base': base, 'formule': formule, 'parametres': params,
                                 'periodicite': perio, 'echeance': ech, 'compte_debit': deb,
                                 'compte_credit': cred, 'conditions': cond,
                                 'message_non_applicable': msg, 'reference': ref, 'a_verifier': verif,
                                 'ordre': ordre, 'description': desc})
        n_o += cree
    return n_p, n_o
