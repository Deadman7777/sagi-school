from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, Value, DecimalField, Q
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone
from django.core.cache import cache
from apps.eleves.models import Eleve
from apps.paiements.models import Paiement, Exercice
from apps.comptabilite.models import JournalEntry
from core.tenant import get_tenant
from .models import AuditLog


def sum_paiements(qs):
    agg = qs.aggregate(
        t=Sum('montant_inscription') + Sum('montant_mensualite') +
          Sum('montant_uniforme')    + Sum('montant_fournitures') +
          Sum('montant_cantine')     + Sum('montant_divers')
    )
    return float(agg['t'] or 0)


class DashboardSuperAdminView(APIView):
    """Dashboard exclusif HADY GESMAN — stats globales sans détails écoles."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'SUPER_ADMIN':
            return Response({'error': 'Accès refusé'}, status=403)

        from apps.tenants.models import Tenant
        from apps.licences.models import Licence

        cache_key = 'dashboard_superadmin'
        cached    = cache.get(cache_key)
        if cached:
            return Response(cached)

        total_ecoles  = Tenant.objects.filter(actif=True).count()
        licences      = Licence.objects.select_related('tenant').all()
        actives       = licences.filter(statut='ACTIVE').count()
        expirees      = licences.filter(statut='EXPIREE').count()
        essai         = licences.filter(statut='ESSAI').count()

        TARIFS = {'PRO': 150000, 'BASIC': 75000, 'ESSAI': 0, 'ENTERPRISE': 300000}
        revenus_annuels = sum(
            TARIFS.get(l.type, 0) for l in licences.filter(statut='ACTIVE')
        )

        # Licences expirant dans 30 jours
        alertes = [{
            'ecole':          l.tenant.nom,
            'jours_restants': l.jours_restants,
            'date_fin':       str(l.date_fin),
            'type':           l.type,
        } for l in licences.filter(statut='ACTIVE') if 0 <= l.jours_restants <= 30]

        # Activité récente (nouvelles écoles ce mois)
        from django.utils import timezone
        debut_mois = timezone.now().replace(day=1, hour=0, minute=0, second=0)
        nouvelles  = Tenant.objects.filter(created_at__gte=debut_mois).count()

        result = {
            'ecoles': {
                'total':     total_ecoles,
                'actives':   actives,
                'expirees':  expirees,
                'essai':     essai,
                'nouvelles_ce_mois': nouvelles,
            },
            'finances': {
                'revenus_annuels':  revenus_annuels,
                'revenus_mensuels': revenus_annuels // 12,
            },
            'alertes_expiration': sorted(alertes, key=lambda x: x['jours_restants']),
        }
        cache.set(cache_key, result, 300)
        return Response(result)


class DashboardKPIView(APIView):
    """Dashboard école — données financières du tenant connecté."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Super admin redirigé vers son propre dashboard
        if request.user.role == 'SUPER_ADMIN':
            return Response({'error': 'Utilisez /api/dashboard/superadmin/'}, status=400)

        tenant = get_tenant(request)
        if not tenant:
            return Response({
                'exercice': None,
                'kpis': {'total_recettes': 0, 'total_charges': 0,
                         'resultat_net': 0, 'tresorerie': 0},
                'eleves': {'total': 0, 'urgent': 0, 'attention': 0, 'ok': 0},
                'modes_paiement': [], 'recettes_mensuelles': [],
            })

        cache_key = f'dashboard_kpis_{tenant.id}'
        cached    = cache.get(cache_key)
        if cached:
            return Response(cached)

        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()

        if not exercice:
            return Response({
                'exercice': None,
                'kpis': {'total_recettes': 0, 'total_charges': 0,
                         'resultat_net': 0, 'tresorerie': 0},
                'eleves': {'total': 0, 'urgent': 0, 'attention': 0, 'ok': 0},
                'modes_paiement': [], 'recettes_mensuelles': [],
                'message': 'Aucun exercice actif'
            })

        paiements      = Paiement.objects.filter(tenant=tenant, exercice=exercice, statut='ACTIF')
        total_recettes = sum_paiements(paiements)
        # Charges directes (CHARGE) + comptabilisations de budget (BUDGET) :
        # même suivi au tableau de bord quelle que soit l'origine de la charge.
        charges_agg    = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice, source__in=('CHARGE', 'BUDGET'),
        ).filter(
            Q(no_compte__startswith='6') | Q(no_compte__startswith='2')
        ).aggregate(t_debit=Sum('debit'), t_credit=Sum('credit'))
        total_charges  = max(0.0, float(charges_agg['t_debit'] or 0) - float(charges_agg['t_credit'] or 0))
        solde_initial  = float(exercice.solde_initial_caisse +
                               exercice.solde_initial_banque +
                               exercice.solde_initial_mobile)

        today = timezone.now().date()

        _pf = Q(paiements__statut='ACTIF')
        eleves = Eleve.objects.filter(
            tenant=tenant, exercice=exercice
        ).annotate(
            total_paye_sql=Coalesce(
                Sum('paiements__montant_inscription', filter=_pf) +
                Sum('paiements__montant_mensualite',  filter=_pf) +
                Sum('paiements__montant_uniforme',    filter=_pf) +
                Sum('paiements__montant_fournitures', filter=_pf) +
                Sum('paiements__montant_cantine',     filter=_pf) +
                Sum('paiements__montant_divers',      filter=_pf),
                Value(0), output_field=DecimalField()
            ),
            mensualites_payees_sql=Coalesce(
                Sum('paiements__montant_mensualite', filter=_pf),
                Value(0), output_field=DecimalField()
            ),
        ).select_related('section', 'exercice').prefetch_related('abonnements__service')

        # Mêmes niveaux que le module Élèves (source de vérité : Eleve.niveau_alerte_detail)
        critique = urgent = attention = ok = a_jour = 0
        compteur = {'CRITIQUE': 0, 'URGENT': 0, 'ATTENTION': 0, 'OK': 0, 'A_JOUR': 0}
        for e in eleves:
            niveau, _ = e.niveau_alerte_detail(
                e.total_paye_sql or 0, e.mensualites_payees_sql or 0, today)
            compteur[niveau] += 1
        critique, urgent, attention, ok, a_jour = (
            compteur['CRITIQUE'], compteur['URGENT'], compteur['ATTENTION'],
            compteur['OK'], compteur['A_JOUR'])

        modes_raw = paiements.values('mode_paiement').annotate(
            nb=Count('id'),
            total=Sum('montant_inscription') + Sum('montant_mensualite') +
                  Sum('montant_uniforme')    + Sum('montant_fournitures') +
                  Sum('montant_cantine')     + Sum('montant_divers')
        ).order_by('-total')

        mensuel_raw = paiements.annotate(
            mois=TruncMonth('date_paiement')
        ).values('mois').annotate(
            total=Sum('montant_inscription') + Sum('montant_mensualite') +
                  Sum('montant_uniforme')    + Sum('montant_fournitures') +
                  Sum('montant_cantine')     + Sum('montant_divers')
        ).order_by('mois')
        
        # Calcul taux recouvrement et impayés
        total_attendu = sum(float(e.total_attendu) for e in eleves)
        total_paye    = sum(float(e.total_paye_sql or 0) for e in eleves)
        total_impayes = max(total_attendu - total_paye, 0)
        taux_recouvrement = round((total_paye / total_attendu * 100), 1) if total_attendu > 0 else 0

        # Statuts élèves
        statuts_qs = eleves.values('statut').annotate(nb=Count('id'))
        statuts    = {s['statut']: s['nb'] for s in statuts_qs}

        # Prises en charge — queryset PROPRE (sans la jointure paiements de `eleves`,
        # sinon Count('id') compte chaque élève autant de fois qu'il a de paiements)
        pec_qs = Eleve.objects.filter(
            tenant=tenant, exercice=exercice, prise_en_charge__isnull=False
        ).exclude(prise_en_charge='')
        pec_nb = pec_qs.count()
        pec_categories = list(pec_qs.values('prise_en_charge').annotate(nb=Count('id')))

        tresorerie_mvt = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice,
            no_compte__in=('571', '5521', '5522', '5523', '521')
        ).aggregate(t_debit=Sum('debit'), t_credit=Sum('credit'))
        tresorerie = round(
            solde_initial +
            float(tresorerie_mvt['t_debit']  or 0) -
            float(tresorerie_mvt['t_credit'] or 0),
            2
        )

        result = {
            'exercice': {
                'annee_scolaire': exercice.annee_scolaire,
                'date_debut':     str(exercice.date_debut),
                'date_fin':       str(exercice.date_fin),
            },
            'kpis': {
                'total_recettes':      total_recettes,
                'total_charges':       total_charges,
                'resultat_net':        total_recettes - total_charges,
                'tresorerie':          tresorerie,
                'total_attendu':       round(total_attendu, 2),
                'total_impayes':       round(total_impayes, 2),
                'taux_recouvrement':   taux_recouvrement,
            },
            'eleves': {
                'total':      eleves.count(),
                'inscrits':   statuts.get('INSCRIT',   0),
                'abandonnes': statuts.get('ABANDONNE', 0),
                'transferes': statuts.get('TRANSFERE', 0),
                'diplomes':   statuts.get('DIPLOME',   0),
                'critique':   critique,
                'urgent':     urgent,
                'attention':  attention,
                'ok':         ok,
                'a_jour':     a_jour,
                'garcons':    eleves.filter(genre='G').count(),
                'filles':     eleves.filter(genre='F').count(),
            },
            'prises_en_charge': {
                'total':       pec_nb,
                'categories':  [{'categorie': p['prise_en_charge'], 'nb': p['nb']} for p in pec_categories],
            },
            'modes_paiement': [{'mode_paiement': m['mode_paiement'],
                                 'nb': m['nb'], 'total': float(m['total'] or 0)}
                                for m in modes_raw],
            'recettes_mensuelles': [{'mois': m['mois'].strftime('%b %Y'),
                                      'total': float(m['total'] or 0)}
                                     for m in mensuel_raw if m['mois']],
        }
        cache.set(cache_key, result, 300)
        return Response(result)


class DashboardAlerteView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_tenant(request)
        if not tenant or request.user.role == 'SUPER_ADMIN':
            return Response([])

        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()
        if not exercice:
            return Response([])

        from dateutil.relativedelta import relativedelta
        from django.db.models import Prefetch
        from apps.eleves.views import MOIS_FR

        today    = timezone.now().date()
        debut    = exercice.date_debut
        nb_total = exercice.nb_mensualites

        # Mois de l'exercice échus à ce jour (du début jusqu'au mois courant inclus)
        mois_exercice = []
        for i in range(nb_total):
            md = debut + relativedelta(months=i)
            if (md.year, md.month) > (today.year, today.month):
                break
            mois_exercice.append((i, md.year, md.month))

        eleves = Eleve.objects.filter(
            tenant=tenant, exercice=exercice, statut='INSCRIT'
        ).select_related('section', 'exercice').prefetch_related(
            'abonnements__service',
            Prefetch('paiements',
                     queryset=Paiement.objects.filter(statut='ACTIF').only(
                         'eleve_id', 'montant_mensualite', 'mois_regles',
                         'montant_inscription', 'montant_uniforme',
                         'montant_fournitures', 'montant_cantine', 'montant_divers'),
                     to_attr='paiements_actifs'),
        )

        data = []
        for e in eleves:
            mensualite = e.frais_mensualite_effectif  # après prise en charge
            if mensualite <= 0:
                continue  # pas d'échéancier mensuel → pas d'arriéré calculable ici

            # Mois effectivement réglés (via mois_regles) + montants payés
            mois_payes  = set()
            mens_payees = 0.0
            total_paye  = 0.0
            for p in e.paiements_actifs:
                mm = float(p.montant_mensualite or 0)
                mens_payees += mm
                total_paye  += (mm + float(p.montant_inscription or 0) +
                                float(p.montant_uniforme or 0) + float(p.montant_fournitures or 0) +
                                float(p.montant_cantine or 0) + float(p.montant_divers or 0))
                for num in (p.mois_regles or []):
                    mois_payes.add(int(num))

            # Niveau + nb de mois d'arriéré : MÊME source de vérité que le module Élèves
            alerte, nb_arr = e.niveau_alerte_detail(total_paye, mens_payees, today)
            if alerte in ('A_JOUR', 'OK') or nb_arr <= 0:
                continue  # à jour sur les mensualités échues → pas d'arriéré (exclu)

            # Mois concernés : ceux dus (au prorata de l'entrée) non couverts par mois_regles
            insc = e.date_inscription or debut
            mois_avant_entree = max(0, (insc.year - debut.year) * 12 + (insc.month - debut.month)) if insc > debut else 0
            mois_dus  = [(y, m) for (i, y, m) in mois_exercice if i >= mois_avant_entree]
            non_payes = [(y, m) for (y, m) in mois_dus if m not in mois_payes]
            source    = non_payes if len(non_payes) >= nb_arr else mois_dus
            libelles  = [MOIS_FR.get(m, str(m)) for (y, m) in source[-nb_arr:]]
            montant_arriere = round(nb_arr * mensualite)

            data.append({
                'id':              str(e.id),
                'nom_complet':     e.nom_complet,
                'section':         e.section.nom if e.section else '',
                'telephone':       e.telephone_pere,
                'montant_arriere': montant_arriere,
                'mois_arrieres':   libelles,
                'nb_mois_arrieres': nb_arr,
                'reste_a_payer':   round(float(e.total_attendu) - total_paye, 0),
                'niveau_alerte':   alerte,
            })

        POIDS = {'CRITIQUE': 0, 'URGENT': 1, 'ATTENTION': 2}
        data.sort(key=lambda x: (POIDS.get(x['niveau_alerte'], 9), -x['montant_arriere']))
        return Response(data)


class DashboardTresorerieCanauView(APIView):
    """Solde de trésorerie par canal de paiement — encaissements vs décaissements."""
    permission_classes = [IsAuthenticated]

    # (mode_paiement, libellé, compte_trésorerie, clé_solde_initial)
    CANAUX = [
        ('ESPECE',       'Espèce',       '571',  'caisse'),
        ('WAVE',         'Wave',          '5521', 'mobile'),
        ('ORANGE_MONEY', 'Orange Money',  '5522', None),
        ('FREE_MONEY',   'Free Money',    '5523', None),
        ('VIREMENT',     'Virement',      '521',  'banque'),
        ('CHEQUE',       'Chèque',        '521',  None),
    ]

    def get(self, request):
        if request.user.role == 'SUPER_ADMIN':
            return Response({'error': 'Non disponible pour super admin'}, status=400)

        tenant = get_tenant(request)
        if not tenant:
            return Response({'exercice': None, 'canaux': [], 'totaux': {}})

        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()
        if not exercice:
            return Response({'exercice': None, 'canaux': [], 'totaux': {}})

        soldes_initiaux = {
            'caisse': float(exercice.solde_initial_caisse),
            'banque': float(exercice.solde_initial_banque),
            'mobile': float(exercice.solde_initial_mobile),
        }

        # Mouvements nets sur comptes de trésorerie — arithmétique pure journal (toutes sources)
        # Toute annulation (ANNUL_PAIEMENT, ANNUL_PAIE, ANNUL_AVANCE, contre-écriture charge) est
        # automatiquement prise en compte : debit/crédit se compensent.
        balance_qs = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice,
            no_compte__in=('571', '5521', '5522', '5523', '521')
        ).values('no_compte').annotate(
            total_debit=Sum('debit'),
            total_credit=Sum('credit')
        )
        balance_by_compte = {
            b['no_compte']: float(b['total_debit'] or 0) - float(b['total_credit'] or 0)
            for b in balance_qs
        }

        # Encaissements actifs par canal (pour affichage nb + montant perçu)
        enc_qs = Paiement.objects.filter(
            tenant=tenant, exercice=exercice, statut='ACTIF'
        ).values('mode_paiement').annotate(
            nb=Count('id'),
            montant=Sum('montant_inscription') + Sum('montant_mensualite') +
                    Sum('montant_uniforme')    + Sum('montant_fournitures') +
                    Sum('montant_cantine')     + Sum('montant_divers')
        )
        enc_by_canal = {
            e['mode_paiement']: {'nb': e['nb'], 'montant': float(e['montant'] or 0)}
            for e in enc_qs
        }

        # Décaissements (charges/paie/invest) — crédits trésorerie hors scolarité
        dec_qs = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice,
            no_compte__in=('571', '5521', '5522', '5523', '521'),
            credit__gt=0
        ).exclude(source__in=('PAIEMENT', 'ANNUL_PAIEMENT')).values('no_compte').annotate(
            montant=Sum('credit')
        )
        dec_by_compte = {d['no_compte']: float(d['montant'] or 0) for d in dec_qs}

        canaux_result = []
        compte521_attribue = False

        for mode, libelle, compte, initial_key in self.CANAUX:
            enc           = enc_by_canal.get(mode, {'nb': 0, 'montant': 0.0})
            solde_initial = soldes_initiaux.get(initial_key, 0.0) if initial_key else 0.0

            if compte == '521':
                if not compte521_attribue:
                    net_journal   = balance_by_compte.get('521', 0.0)
                    decaissements = dec_by_compte.get('521', 0.0)
                    compte521_attribue = True
                else:
                    net_journal   = 0.0
                    decaissements = 0.0
            else:
                net_journal   = balance_by_compte.get(compte, 0.0)
                decaissements = dec_by_compte.get(compte, 0.0)

            solde = round(solde_initial + net_journal, 2)

            if enc['nb'] > 0 or solde_initial > 0 or decaissements > 0 or net_journal != 0:
                canaux_result.append({
                    'canal':         mode,
                    'libelle':       libelle,
                    'compte':        compte,
                    'nb':            enc['nb'],
                    'solde_initial': round(solde_initial, 2),
                    'encaissements': round(enc['montant'], 2),
                    'decaissements': round(decaissements, 2),
                    'solde':         solde,
                })

        total_initial = sum(soldes_initiaux.values())
        total_enc     = sum(c['encaissements'] for c in canaux_result)
        total_dec     = sum(c['decaissements'] for c in canaux_result)
        total_solde   = round(sum(c['solde'] for c in canaux_result), 2)

        return Response({
            'exercice': exercice.annee_scolaire,
            'canaux':   canaux_result,
            'totaux': {
                'solde_initial': round(total_initial, 2),
                'encaissements': round(total_enc, 2),
                'decaissements': round(total_dec, 2),
                'solde':         total_solde,
            },
        })


class AuditLogView(APIView):
    """Journal d'audit admin-only — 100 dernières entrées du tenant."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_tenant(request)
        qs = AuditLog.objects.filter(tenant=tenant).order_by('-created_at')[:100]
        data = [{
            'id':          str(e.id),
            'action':      e.action,
            'modele':      e.modele,
            'objet_id':    e.objet_id,
            'utilisateur': e.utilisateur,
            'description': e.description,
            'created_at':  e.created_at.isoformat(),
        } for e in qs]
        return Response(data)
