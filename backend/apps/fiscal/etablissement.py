"""
Obligations fiscales de l'ÉTABLISSEMENT (au-delà des salaires) + conseils
temps réel pour la prise de décision.

Dès que le RCCM et le NINEA sont renseignés (Paramètres), les obligations
sont calculées depuis les données du système (journal SYSCOHADA, bulletins
de paie) selon le CGI sénégalais. Les montants restent ESTIMATIFS : ils
doivent être confirmés avec un expert-comptable ou la DGID avant déclaration.
"""
import datetime
import re

from django.db.models import Sum, Max
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from core.tenant import get_tenant

# ── Paramètres fiscaux Sénégal (CGI) — niveau établissement ──────────────────
TAUX_IS  = 0.30       # Impôt sur les sociétés — art. 36 CGI
TAUX_IMF = 0.005      # Impôt minimum forfaitaire : 0,5 % des produits
IMF_MIN  = 500_000    # plancher IMF (FCFA)
IMF_MAX  = 5_000_000  # plafond IMF (FCFA)

DISCLAIMER = ("Montants estimés automatiquement depuis les données du système "
              "(CGI du Sénégal). À confirmer avec votre expert-comptable ou la "
              "DGID avant toute déclaration ou paiement.")

MOIS_FR = {
    1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril', 5: 'mai', 6: 'juin',
    7: 'juillet', 8: 'août', 9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre',
}

# Comptes SYSCOHADA de comptabilisation par obligation :
# constatation = débit compte de charge (ou 891) / crédit compte État (44x)
COMPTES_OBLIGATIONS = {
    'IS':   {'debit': '891',  'credit': '441',  'libelle': 'Impôt sur les bénéfices'},
    'IMF':  {'debit': '891',  'credit': '441',  'libelle': 'Impôt minimum forfaitaire'},
    'CFCE': {'debit': '6413', 'credit': '4421', 'libelle': 'CFCE'},
    'CEL':  {'debit': '6414', 'credit': '442',  'libelle': 'Contribution Économique Locale (ex-patente)'},
}


def _exercice_courant(tenant):
    from apps.paiements.models import Exercice
    return Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()


def _bulletins_exercice(tenant, exercice):
    """Bulletins validés/payés dont le mois tombe dans l'exercice."""
    from apps.rh.models import BulletinPaie
    buls = BulletinPaie.objects.filter(tenant=tenant, statut__in=('VALIDE', 'PAYE'))
    debut, fin = exercice.date_debut, exercice.date_fin
    return [b for b in buls
            if debut.replace(day=1) <= datetime.date(b.annee, b.mois, 1) <= fin]


def donnees_financieres(tenant, exercice):
    """Agrégats compta + paie de l'exercice, base des obligations et conseils."""
    from apps.comptabilite.models import JournalEntry

    j = JournalEntry.objects.filter(tenant=tenant, exercice=exercice)
    prod = j.filter(no_compte__startswith='7').aggregate(d=Sum('debit'), c=Sum('credit'))
    produits = float(prod['c'] or 0) - float(prod['d'] or 0)
    chg = j.filter(no_compte__startswith='6').aggregate(d=Sum('debit'), c=Sum('credit'))
    charges = float(chg['d'] or 0) - float(chg['c'] or 0)

    buls = _bulletins_exercice(tenant, exercice)
    if buls:
        masse = float(sum(b.salaire_brut for b in buls))
        cfce  = float(sum(b.cfce for b in buls))
        source_paie = 'BULLETINS'
    else:
        masse = float(j.filter(no_compte='661', source='PAIE')
                       .aggregate(t=Sum('debit'))['t'] or 0)
        cfce  = round(masse * 0.03, 2)
        source_paie = 'ESTIMATION'

    treso_mvt = j.filter(no_compte__in=('571', '5521', '5522', '5523', '521')) \
                 .aggregate(d=Sum('debit'), c=Sum('credit'))
    tresorerie = round(
        float(exercice.solde_initial_caisse + exercice.solde_initial_banque +
              exercice.solde_initial_mobile) +
        float(treso_mvt['d'] or 0) - float(treso_mvt['c'] or 0), 2)

    # Équilibre du journal (débits = crédits) — contrôle d'intégrité
    eq = j.aggregate(d=Sum('debit'), c=Sum('credit'))
    desequilibre = round(float(eq['d'] or 0) - float(eq['c'] or 0), 2)

    return {
        'produits':     round(produits, 2),
        'charges':      round(charges, 2),
        'resultat':     round(produits - charges, 2),
        'masse_salariale': round(masse, 2),
        'cfce':         round(cfce, 2),
        'tresorerie':   tresorerie,
        'source_paie':  source_paie,
        'desequilibre': desequilibre,
    }


def _deja_comptabilise(tenant, exercice, code):
    """Total déjà provisionné/payé pour une obligation (écritures FISCAL_<code>)."""
    from apps.comptabilite.models import JournalEntry
    return float(JournalEntry.objects.filter(
        tenant=tenant, exercice=exercice, source=f'FISCAL_{code}', ordre=1,
    ).aggregate(t=Sum('debit'))['t'] or 0)


def calculer_obligations(tenant, exercice):
    """Liste des obligations fiscales de l'établissement, montants estimés."""
    d = donnees_financieres(tenant, exercice)
    produits, resultat = d['produits'], d['resultat']

    is_calc = round(max(0.0, resultat) * TAUX_IS, 0)
    imf     = round(min(max(produits * TAUX_IMF, IMF_MIN), IMF_MAX), 0) if produits > 0 else IMF_MIN
    # L'IS dû ne peut être inférieur à l'IMF (art. 38 CGI)
    is_du   = max(is_calc, imf)

    obligations = [
        {
            'code': 'IS',
            'libelle': 'Impôt sur les sociétés (IS) / IMF',
            'description': (f"IS 30 % du résultat estimé ({resultat:,.0f} FCFA) = {is_calc:,.0f} FCFA ; "
                            f"minimum forfaitaire (0,5 % des produits, plancher 500 000, plafond 5 000 000) "
                            f"= {imf:,.0f} FCFA. Le montant dû est le plus élevé des deux."),
            'base': resultat if is_calc >= imf else produits,
            'taux': '30 % (ou IMF 0,5 %)',
            'montant': is_du,
            'periodicite': 'Annuelle',
            'echeance': 'Acomptes 15 février et 30 avril · solde avec la déclaration (30 avril N+1)',
            'statut': 'ESTIMATION',
            'comptabilisable': True,
            'deja_comptabilise': _deja_comptabilise(tenant, exercice, 'IS'),
            'comptes': COMPTES_OBLIGATIONS['IS'],
        },
        {
            'code': 'CFCE',
            'libelle': "CFCE — Contribution forfaitaire à la charge de l'employeur",
            'description': ("3 % de la masse salariale brute (art. 188 CGI). "
                            + ("Comptabilisée automatiquement à la validation des bulletins (module RH)."
                               if d['source_paie'] == 'BULLETINS'
                               else "Estimation depuis le journal — validez les bulletins de paie (module RH) pour des montants réels.")),
            'base': d['masse_salariale'],
            'taux': '3 %',
            'montant': d['cfce'],
            'periodicite': 'Mensuelle (avec la BRS)',
            'echeance': 'Le 15 du mois suivant, avec la BRS',
            'statut': 'BULLETINS' if d['source_paie'] == 'BULLETINS' else 'ESTIMATION',
            'comptabilisable': d['source_paie'] != 'BULLETINS',
            'deja_comptabilise': _deja_comptabilise(tenant, exercice, 'CFCE'),
            'comptes': COMPTES_OBLIGATIONS['CFCE'],
        },
        {
            'code': 'TVA',
            'libelle': 'TVA',
            'description': ("Les prestations d'enseignement scolaire et universitaire sont EXONÉRÉES de TVA "
                            "(annexe du CGI). Ne facturez pas de TVA sur les frais de scolarité. "
                            "Les activités annexes (cantine, transport…) peuvent être taxables : vérifiez avec votre conseil."),
            'base': None,
            'taux': 'Exonéré (18 % sur activités taxables)',
            'montant': 0,
            'periodicite': '—',
            'echeance': '—',
            'statut': 'EXONERE',
            'comptabilisable': False,
            'deja_comptabilise': 0,
            'comptes': None,
        },
        {
            'code': 'CEL',
            'libelle': 'CEL — Contribution Économique Locale (ex-patente)',
            'description': ("Due à la collectivité locale : CEL-VL assise sur la valeur locative des locaux "
                            "et CEL-VA sur la valeur ajoutée. Les bases ne sont pas gérées par le système : "
                            "saisissez le montant de votre avis d'imposition pour le comptabiliser."),
            'base': None,
            'taux': 'Selon avis d’imposition',
            'montant': None,
            'periodicite': 'Annuelle',
            'echeance': 'Selon avis de la collectivité (généralement avant le 30 avril)',
            'statut': 'A_SAISIR',
            'comptabilisable': True,
            'deja_comptabilise': _deja_comptabilise(tenant, exercice, 'CEL'),
            'comptes': COMPTES_OBLIGATIONS['CEL'],
        },
        {
            'code': 'RETENUES',
            'libelle': 'Retenues sur salaires (IR, TRIMF) et cotisations (IPRES, CSS)',
            'description': ("Calculées et comptabilisées automatiquement par le module RH à la validation "
                            "des bulletins ; à reverser chaque mois avec la BRS (voir l'onglet Déclarations)."),
            'base': d['masse_salariale'],
            'taux': 'Barème IR / taux IPRES-CSS',
            'montant': None,
            'periodicite': 'Mensuelle',
            'echeance': 'Le 15 du mois suivant (BRS)',
            'statut': 'GERE_PAR_RH',
            'comptabilisable': False,
            'deja_comptabilise': 0,
            'comptes': None,
        },
    ]
    return obligations, d


class ObligationsEtablissementView(APIView):
    """GET /fiscal/obligations/ — obligations fiscales calculées dès RCCM+NINEA saisis."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_tenant(request)
        exercice = _exercice_courant(tenant) if tenant else None
        identification = {
            'rccm':  getattr(tenant, 'rccm', '') or '',
            'ninea': getattr(tenant, 'ninea', '') or '',
            'complet': bool(getattr(tenant, 'rccm', '') and getattr(tenant, 'ninea', '')),
        }
        if not exercice:
            return Response({'identification': identification, 'obligations': [],
                             'donnees': {}, 'disclaimer': DISCLAIMER,
                             'message': 'Aucun exercice actif.'})
        if not identification['complet']:
            return Response({'identification': identification, 'obligations': [],
                             'donnees': {}, 'disclaimer': DISCLAIMER,
                             'message': ("Renseignez le RCCM et le NINEA de l'établissement "
                                         "(Paramètres → Infos école) pour activer le calcul "
                                         "automatique des obligations fiscales.")})

        obligations, donnees = calculer_obligations(tenant, exercice)
        return Response({
            'identification': identification,
            'exercice':       exercice.annee_scolaire,
            'obligations':    obligations,
            'donnees':        donnees,
            'disclaimer':     DISCLAIMER,
        })


class ComptabiliserObligationView(APIView):
    """POST /fiscal/comptabiliser/ — écritures SYSCOHADA d'une obligation.

    body : {code, montant, date?, mode: PROVISION|PAIEMENT, canal?}
    PROVISION : débit charge (641x / 891) · crédit État (44x)
    PAIEMENT  : provision + règlement (débit 44x · crédit trésorerie <canal>)
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.comptabilite.models import JournalEntry

        tenant   = get_tenant(request)
        exercice = _exercice_courant(tenant) if tenant else None
        if not exercice:
            return Response({'error': 'Aucun exercice actif.'}, status=400)

        code    = str(request.data.get('code', '')).upper()
        comptes = COMPTES_OBLIGATIONS.get(code)
        if not comptes:
            return Response({'error': f"Obligation inconnue ou non comptabilisable : {code}"}, status=400)

        try:
            montant = float(request.data.get('montant', 0))
        except (TypeError, ValueError):
            montant = 0
        if montant <= 0:
            return Response({'error': 'Montant invalide.'}, status=400)

        mode  = request.data.get('mode', 'PROVISION')
        canal = request.data.get('canal', '571')
        if canal not in ('571', '5521', '5522', '5523', '521'):
            return Response({'error': 'Canal de trésorerie invalide.'}, status=400)
        date  = request.data.get('date', str(timezone.now().date()))

        # Séquence de pièce FISC-xxxx propre au tenant (toutes obligations confondues)
        last = JournalEntry.objects.filter(
            tenant=tenant, source__startswith='FISCAL_',
        ).aggregate(Max('no_piece'))['no_piece__max']
        nums = re.findall(r'\d+', last or 'FISC-0000')
        no_piece = f"FISC-{int(nums[-1]) + 1:04d}" if nums else 'FISC-0001'

        lib = f"{comptes['libelle']} — exercice {exercice.annee_scolaire}"
        ecritures = [
            dict(ordre=1, no_compte=comptes['debit'],  debit=montant, credit=0, libelle=lib),
            dict(ordre=2, no_compte=comptes['credit'], debit=0, credit=montant, libelle=lib),
        ]
        if mode == 'PAIEMENT':
            ecritures += [
                dict(ordre=3, no_compte=comptes['credit'], debit=montant, credit=0,
                     libelle=f"Règlement {lib}"),
                dict(ordre=4, no_compte=canal, debit=0, credit=montant,
                     libelle=f"Règlement {lib}"),
            ]

        for e in ecritures:
            JournalEntry.objects.create(
                tenant=tenant, exercice=exercice,
                no_piece=no_piece, date_ecriture=date,
                source=f'FISCAL_{code}', source_id=None, **e,
            )

        return Response({'success': True, 'no_piece': no_piece,
                         'montant': montant, 'mode': mode}, status=201)


class ConseilsView(APIView):
    """GET /fiscal/conseils/ — conseils fiscaux, comptables et financiers
    générés en temps réel depuis les données du système."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant   = get_tenant(request)
        exercice = _exercice_courant(tenant) if tenant else None
        if not exercice:
            return Response({'conseils': [], 'disclaimer': DISCLAIMER})

        d = donnees_financieres(tenant, exercice)
        today = timezone.now().date()
        conseils = []

        def add(categorie, niveau, titre, detail):
            conseils.append({'categorie': categorie, 'niveau': niveau,
                             'titre': titre, 'detail': detail})

        # ── Fiscal ────────────────────────────────────────────────────────
        rccm, ninea = getattr(tenant, 'rccm', ''), getattr(tenant, 'ninea', '')
        if not (rccm and ninea):
            manquants = ' et '.join(x for x, v in (('RCCM', rccm), ('NINEA', ninea)) if not v)
            add('FISCAL', 'URGENT', 'Identification fiscale incomplète',
                f"Renseignez le {manquants} dans Paramètres → Infos école : indispensable pour "
                "vos déclarations (BRS, IS) et pour activer le calcul automatique des obligations.")

        if d['masse_salariale'] > 0:
            prochain = (today.replace(day=1) + datetime.timedelta(days=32)).replace(day=15)
            add('FISCAL', 'ATTENTION', 'BRS à déposer',
                f"Déposez la BRS du mois de {MOIS_FR[today.month]} avant le "
                f"15 {MOIS_FR[prochain.month]} (retenues IR + IPRES/CSS + CFCE) pour éviter pénalités et intérêts de retard.")

        if d['resultat'] > 0 and rccm and ninea:
            is_estime = round(max(d['resultat'] * TAUX_IS,
                                  min(max(d['produits'] * TAUX_IMF, IMF_MIN), IMF_MAX)), 0)
            deja = _deja_comptabilise(tenant, exercice, 'IS')
            if deja < is_estime:
                add('FISCAL', 'ATTENTION', 'Provision IS recommandée',
                    f"Résultat estimé positif ({d['resultat']:,.0f} FCFA) : provisionnez "
                    f"~{is_estime:,.0f} FCFA d'impôt sur les sociétés (acomptes 15 février et 30 avril). "
                    f"Déjà comptabilisé : {deja:,.0f} FCFA.")

        add('FISCAL', 'INFO', 'TVA : enseignement exonéré',
            "Ne facturez pas de TVA sur les frais de scolarité (exonération CGI). Les activités "
            "annexes (cantine, transport) peuvent être taxables : vérifiez avec votre conseil.")

        if d['source_paie'] == 'ESTIMATION' and d['masse_salariale'] > 0:
            add('FISCAL', 'INFO', 'Fiabilisez vos déclarations sociales',
                "Vos montants IPRES/CSS/IR/CFCE sont estimés : validez les bulletins de paie dans "
                "le module RH pour déclarer des montants réels.")

        # ── Comptable ─────────────────────────────────────────────────────
        if abs(d['desequilibre']) > 0.01:
            add('COMPTABLE', 'URGENT', 'Journal déséquilibré',
                f"Écart débits/crédits de {d['desequilibre']:,.0f} FCFA sur l'exercice : "
                "contrôlez la balance (Comptabilité) avant toute édition d'états financiers.")

        if d['charges'] > d['produits'] and d['produits'] > 0:
            add('COMPTABLE', 'ATTENTION', 'Résultat déficitaire',
                f"Charges ({d['charges']:,.0f} FCFA) supérieures aux produits ({d['produits']:,.0f} FCFA). "
                "Analysez les postes de charges (Charges & marge) et le recouvrement des scolarités.")

        if exercice.date_fin < today:
            add('COMPTABLE', 'ATTENTION', 'Exercice échu à clôturer',
                f"L'exercice {exercice.annee_scolaire} est terminé depuis le "
                f"{exercice.date_fin.strftime('%d/%m/%Y')} : préparez la clôture "
                "(Paramètres → Clôture) après validation des écritures.")

        # ── Financier ─────────────────────────────────────────────────────
        mois_ecoules = max(1, (today.year - exercice.date_debut.year) * 12 +
                           today.month - exercice.date_debut.month)
        charges_moy = d['charges'] / mois_ecoules if d['charges'] > 0 else 0
        if charges_moy > 0:
            if d['tresorerie'] < 0:
                add('FINANCIER', 'URGENT', 'Trésorerie négative',
                    f"Trésorerie de {d['tresorerie']:,.0f} FCFA : suspendez les dépenses non essentielles "
                    "et intensifiez le recouvrement (module Élèves → alertes de paiement).")
            elif d['tresorerie'] < charges_moy:
                add('FINANCIER', 'URGENT', 'Trésorerie critique',
                    f"Trésorerie ({d['tresorerie']:,.0f} FCFA) inférieure à un mois de charges "
                    f"(~{charges_moy:,.0f} FCFA/mois) : priorité au recouvrement des impayés.")
            elif d['tresorerie'] < 3 * charges_moy:
                add('FINANCIER', 'ATTENTION', 'Trésorerie sous surveillance',
                    f"Trésorerie ({d['tresorerie']:,.0f} FCFA) couvre moins de 3 mois de charges "
                    f"(~{charges_moy:,.0f} FCFA/mois) : anticipez les échéances (salaires, BRS).")

        if d['produits'] > 0 and d['masse_salariale'] / d['produits'] > 0.6:
            add('FINANCIER', 'ATTENTION', 'Masse salariale élevée',
                f"La masse salariale représente {100 * d['masse_salariale'] / d['produits']:.0f} % des produits "
                "(seuil de vigilance : 60 %) : surveillez ce ratio avant tout recrutement.")

        # Recouvrement des scolarités
        from apps.dashboard.views import sum_paiements  # somme des paiements actifs
        from apps.paiements.models import Paiement
        paye = sum_paiements(Paiement.objects.filter(tenant=tenant, exercice=exercice, statut='ACTIF'))
        from apps.eleves.models import Eleve
        eleves = Eleve.objects.filter(tenant=tenant, exercice=exercice) \
                              .select_related('section', 'exercice') \
                              .prefetch_related('abonnements__service')
        attendu = sum(float(e.total_attendu) for e in eleves)
        if attendu > 0:
            taux = 100 * paye / attendu
            if taux < 70:
                add('FINANCIER', 'ATTENTION', 'Recouvrement faible',
                    f"Taux de recouvrement de {taux:.0f} % ({paye:,.0f} / {attendu:,.0f} FCFA) : "
                    "relancez les familles depuis les alertes de paiement (module Élèves).")
            elif attendu - paye > 0:
                add('FINANCIER', 'INFO', 'Impayés à suivre',
                    f"{attendu - paye:,.0f} FCFA restent à recouvrer sur l'exercice "
                    f"(taux de recouvrement : {taux:.0f} %).")

        POIDS = {'URGENT': 0, 'ATTENTION': 1, 'INFO': 2}
        conseils.sort(key=lambda c: POIDS.get(c['niveau'], 9))
        return Response({'conseils': conseils, 'disclaimer': DISCLAIMER,
                         'exercice': exercice.annee_scolaire})
