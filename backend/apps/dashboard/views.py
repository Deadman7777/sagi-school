from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, Value, DecimalField
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone
from django.core.cache import cache
from apps.eleves.models import Eleve
from apps.paiements.models import Paiement, Exercice
from apps.comptabilite.models import JournalEntry


def get_tenant(request):
    if request.tenant:
        return request.tenant
    if hasattr(request.user, 'tenant') and request.user.tenant:
        return request.user.tenant
    return None


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

        paiements      = Paiement.objects.filter(tenant=tenant, exercice=exercice)
        total_recettes = sum_paiements(paiements)
        total_charges  = float(JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice, source='CHARGE'
        ).aggregate(t=Sum('debit'))['t'] or 0)
        solde_initial  = float(exercice.solde_initial_caisse +
                               exercice.solde_initial_banque +
                               exercice.solde_initial_mobile)

        today  = timezone.now().date()
        debut          = exercice.date_debut
        months_elapsed = max(0, min(
            (today.year - debut.year) * 12 + (today.month - debut.month), 10
        ))

        eleves = Eleve.objects.filter(
            tenant=tenant, exercice=exercice
        ).annotate(
            total_paye_sql=Coalesce(
                Sum('paiements__montant_inscription') +
                Sum('paiements__montant_mensualite')  +
                Sum('paiements__montant_uniforme')    +
                Sum('paiements__montant_fournitures') +
                Sum('paiements__montant_cantine')     +
                Sum('paiements__montant_divers'),
                Value(0), output_field=DecimalField()
            ),
            mensualites_payees_sql=Coalesce(
                Sum('paiements__montant_mensualite'),
                Value(0), output_field=DecimalField()
            ),
        ).select_related('section')

        critique = urgent = attention = ok = a_jour = 0
        for e in eleves:
            total = float(e.total_attendu)
            paye  = float(e.total_paye_sql or 0)
            if total <= 0 or paye >= total:
                a_jour += 1; continue
            mensualite = float(e.section.frais_mensualite) if e.section else 0
            if mensualite > 0:
                mens_payees = float(e.mensualites_payees_sql or 0)
                arrieres    = max(0.0, months_elapsed * mensualite - mens_payees)
                if arrieres <= 0:
                    ok += 1
                else:
                    nb_arr = arrieres / mensualite
                    if nb_arr * 30 >= 60 and nb_arr >= 2: critique   += 1
                    elif nb_arr * 30 >= 30 and nb_arr >= 1: urgent    += 1
                    else:                                    attention += 1
            else:
                ok += 1

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

        # Prises en charge
        pec_qs = eleves.filter(prise_en_charge__isnull=False).exclude(prise_en_charge='')
        pec_nb = pec_qs.count()
        pec_categories = list(pec_qs.values('prise_en_charge').annotate(nb=Count('id')))

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
                'tresorerie':          solde_initial + total_recettes - total_charges,
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

        today  = timezone.now().date()
        debut  = exercice.date_debut
        months_elapsed = max(0, min(
            (today.year - debut.year) * 12 + (today.month - debut.month), 10
        ))

        eleves = Eleve.objects.filter(
            tenant=tenant, exercice=exercice
        ).annotate(
            total_paye_sql=Coalesce(
                Sum('paiements__montant_inscription') +
                Sum('paiements__montant_mensualite')  +
                Sum('paiements__montant_uniforme')    +
                Sum('paiements__montant_fournitures') +
                Sum('paiements__montant_cantine')     +
                Sum('paiements__montant_divers'),
                Value(0), output_field=DecimalField()
            ),
            mensualites_payees_sql=Coalesce(
                Sum('paiements__montant_mensualite'),
                Value(0), output_field=DecimalField()
            ),
        ).select_related('section')

        data = []
        for e in eleves:
            total = float(e.total_attendu)
            paye  = float(e.total_paye_sql or 0)
            reste = total - paye
            if reste <= 0: continue

            mensualite  = float(e.section.frais_mensualite) if e.section else 0
            nb_arrieres = 0.0

            if mensualite > 0:
                mens_payees = float(e.mensualites_payees_sql or 0)
                arrieres    = max(0.0, months_elapsed * mensualite - mens_payees)
                if arrieres <= 0:
                    continue  # aucun arriéré — pas d'alerte
                nb_arrieres  = arrieres / mensualite
                jours_retard = nb_arrieres * 30
                if jours_retard >= 60 and nb_arrieres >= 2: alerte = 'CRITIQUE'
                elif jours_retard >= 30 and nb_arrieres >= 1: alerte = 'URGENT'
                else:                                          alerte = 'ATTENTION'
            else:
                ratio  = paye / total if total > 0 else 0
                alerte = 'URGENT' if ratio < 0.5 else 'ATTENTION'

            data.append({
                'id':                    str(e.id),
                'nom_complet':           e.nom_complet,
                'section':               e.section.nom if e.section else '',
                'telephone':             e.telephone_pere,
                'reste_a_payer':         reste,
                'niveau_alerte':         alerte,
                'nb_mensualites_arrieres': round(nb_arrieres, 1),
            })

        POIDS = {'CRITIQUE': 0, 'URGENT': 1, 'ATTENTION': 2}
        data.sort(key=lambda x: (POIDS.get(x['niveau_alerte'], 9), -x['reste_a_payer']))
        return Response(data[:30])


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

        # Encaissements par canal (source: table Paiement — mode_paiement fiable)
        enc_qs = Paiement.objects.filter(
            tenant=tenant, exercice=exercice
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

        # Décaissements par compte tréso (crédits sur comptes de trésorerie = sorties)
        # Les débits sur comptes tréso = encaissements paiements (source PAIEMENT) → exclus ici
        dec_qs = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice,
            no_compte__in=('571', '5521', '5522', '5523', '521'),
            credit__gt=0
        ).exclude(source='PAIEMENT').values('no_compte').annotate(montant=Sum('credit'))
        dec_by_compte = {d['no_compte']: float(d['montant'] or 0) for d in dec_qs}

        canaux_result = []
        dec_521_attribue = False  # évite double-comptage VIREMENT + CHEQUE sur même compte 521

        for mode, libelle, compte, initial_key in self.CANAUX:
            enc          = enc_by_canal.get(mode, {'nb': 0, 'montant': 0.0})
            solde_initial = soldes_initiaux.get(initial_key, 0.0) if initial_key else 0.0

            if compte == '521':
                if not dec_521_attribue:
                    decaissements = dec_by_compte.get('521', 0.0)
                    dec_521_attribue = True
                else:
                    decaissements = 0.0
            else:
                decaissements = dec_by_compte.get(compte, 0.0)

            solde = round(solde_initial + enc['montant'] - decaissements, 2)

            if enc['nb'] > 0 or solde_initial > 0 or decaissements > 0:
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

        return Response({
            'exercice': exercice.annee_scolaire,
            'canaux':   canaux_result,
            'totaux': {
                'solde_initial': round(total_initial, 2),
                'encaissements': round(total_enc, 2),
                'decaissements': round(total_dec, 2),
                'solde':         round(total_initial + total_enc - total_dec, 2),
            },
        })
