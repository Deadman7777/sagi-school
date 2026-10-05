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

# Les taux, seuils et obligations ne sont plus écrits ici : ils sont datés et
# paramétrables (apps/fiscal/models.py, referentiel.py, moteur.py).

DISCLAIMER = ("Montants estimés automatiquement depuis les données du système "
              "(CGI du Sénégal). À confirmer avec votre expert-comptable ou la "
              "DGID avant toute déclaration ou paiement.")

MOIS_FR = {
    1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril', 5: 'mai', 6: 'juin',
    7: 'juillet', 8: 'août', 9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre',
}

# Comptes SYSCOHADA de comptabilisation par obligation :
# constatation = débit compte de charge (ou 891) / crédit compte État (44x)
def _exercice_courant(tenant, request=None):
    """L'exercice consulté : `?exercice=` (un exercice antérieur à régulariser,
    ou clôturé en lecture), sinon l'exercice courant."""
    from apps.comptabilite.views import get_exercice
    return get_exercice(tenant, request)


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
        from .parametres import valeur_parametre
        masse = float(j.filter(no_compte='661', source='PAIE')
                       .aggregate(t=Sum('debit'))['t'] or 0)
        cfce  = round(masse * float(valeur_parametre('CFCE_TAUX', tenant, exercice.date_fin, 3)) / 100, 2)
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
    """Liste des obligations fiscales de l'établissement, montants estimés —
    selon son profil fiscal et les paramètres en vigueur (moteur.py)."""
    from .moteur import calculer
    d = donnees_financieres(tenant, exercice)
    return calculer(tenant, exercice, d,
                    lambda code: _deja_comptabilise(tenant, exercice, code)), d


class ObligationsEtablissementView(APIView):
    """GET /fiscal/obligations/ — obligations fiscales calculées dès RCCM+NINEA saisis."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_tenant(request)
        exercice = _exercice_courant(tenant, request) if tenant else None
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
        from .moteur import profil_de
        profil = profil_de(tenant)
        return Response({
            'identification': identification,
            'exercice':       exercice.annee_scolaire,
            'exercice_id':    str(exercice.id),
            'profil': {'forme_juridique': profil.get_forme_juridique_display(),
                       'statut': profil.get_statut_display(),
                       'regime': profil.get_regime_display(),
                       'but_lucratif': profil.but_lucratif,
                       'assujetti_tva': profil.assujetti_tva},
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

        from apps.comptabilite.views import get_exercice_ecriture
        from .moteur import comptes_obligation
        tenant   = get_tenant(request)
        try:
            # Exercice courant, ou exercice antérieur encore ouvert (exercice_id).
            exercice = get_exercice_ecriture(tenant, request) if tenant else None
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        if not exercice:
            return Response({'error': 'Aucun exercice actif.'}, status=400)

        code    = str(request.data.get('code', '')).upper()
        comptes = comptes_obligation(code)
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
        exercice = _exercice_courant(tenant, request) if tenant else None
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

        is_ligne = None
        if d['resultat'] > 0 and rccm and ninea:
            from .moteur import calculer
            is_ligne = next((o for o in calculer(tenant, exercice, d, lambda c: 0)
                             if o['code'] == 'IS' and o['statut'] == 'ESTIMATION'), None)
        if is_ligne:
            is_estime = is_ligne['montant']
            deja = _deja_comptabilise(tenant, exercice, 'IS')
            if deja < is_estime:
                add('FISCAL', 'ATTENTION', 'Provision IS recommandée',
                    f"Résultat estimé positif ({d['resultat']:,.0f} FCFA) : provisionnez "
                    f"~{is_estime:,.0f} FCFA d'impôt sur les sociétés (acomptes 15 février et 30 avril). "
                    f"Déjà comptabilisé : {deja:,.0f} FCFA.")

        from .moteur import profil_de
        if not profil_de(tenant).assujetti_tva:
            from apps.comptabilite.models import Activite
            taxables = list(Activite.objects.filter(tenant=tenant, actif=True, regime_tva='TAXABLE')
                            .values_list('libelle', flat=True))
            if taxables:
                add('FISCAL', 'ATTENTION', 'Activité taxable, établissement non assujetti',
                    f"L'activité « {', '.join(taxables)} » est paramétrée soumise à TVA alors que le "
                    "profil fiscal déclare l'établissement non assujetti : mettez le profil à jour "
                    "(Fiscal → Profil) ou corrigez le régime de l'activité.")
            else:
                add('FISCAL', 'INFO', 'TVA : enseignement exonéré',
                    "Ne facturez pas de TVA sur les frais de scolarité (exonération CGI). Les activités "
                    "annexes (transport de tiers, location…) peuvent être taxables : paramétrez-les "
                    "dans Comptabilité → Activités.")

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
