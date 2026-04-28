from django.db.models import Sum
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Q
from apps.paiements.models import Exercice, Paiement
from apps.eleves.models import Eleve
from .models import JournalEntry
from django.utils import timezone


def get_tenant(request):
    if request.tenant:
        return request.tenant
    if request.user.role == 'SUPER_ADMIN':
        from apps.tenants.models import Tenant
        return Tenant.objects.first()
    return None


def get_exercice(tenant):
    return Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()


class JournalView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant)
        if not exercice:
            return Response([])

        entries = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice
        ).order_by('date_ecriture', 'no_piece')

        return Response([{
            'date':     str(e.date_ecriture),
            'no_piece': e.no_piece,
            'no_compte': e.no_compte,
            'libelle':  e.libelle,
            'debit':    float(e.debit),
            'credit':   float(e.credit),
            'source':   e.source,
        } for e in entries])


class GrandLivreView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant)
        if not exercice:
            return Response([])

        comptes = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice
        ).values('no_compte').annotate(
            total_debit=Sum('debit'),
            total_credit=Sum('credit')
        ).order_by('no_compte')

        # Plan comptable pour les libellés
        PLAN = {
            '521': 'Banque compte courant',
            '571': 'Caisse',
            '5521': 'WAVE',
            '5522': 'Orange Money',
            '5523': 'Free Money',
            '706': 'Produits scolarité',
            '706.1': 'Produits cantine',
            '612': 'Loyer',
            '661': 'Salaires',
            '606': 'Eau & fournitures',
        }

        data = []
        for c in comptes:
            debit  = float(c['total_debit']  or 0)
            credit = float(c['total_credit'] or 0)
            data.append({
                'no_compte':      c['no_compte'],
                'libelle':        PLAN.get(c['no_compte'], c['no_compte']),
                'total_debit':    debit,
                'total_credit':   credit,
                'solde_debiteur':  max(debit - credit, 0),
                'solde_crediteur': max(credit - debit, 0),
            })
        return Response(data)


class BalanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant)
        if not exercice:
            return Response({'lignes': [], 'totaux': {}})

        comptes = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice
        ).values('no_compte').annotate(
            total_debit=Sum('debit'),
            total_credit=Sum('credit')
        ).order_by('no_compte')

        PLAN = {
            '521': 'Banque', '571': 'Caisse',
            '5521': 'WAVE', '5522': 'Orange Money', '5523': 'Free Money',
            '706': 'Produits scolarité', '706.1': 'Produits cantine',
            '612': 'Loyer', '661': 'Salaires', '606': 'Eau & fournitures',
        }

        lignes = []
        tot_debit = tot_credit = tot_sd = tot_sc = 0

        for c in comptes:
            d  = float(c['total_debit']  or 0)
            cr = float(c['total_credit'] or 0)
            sd = max(d - cr, 0)
            sc = max(cr - d, 0)
            tot_debit  += d
            tot_credit += cr
            tot_sd     += sd
            tot_sc     += sc
            lignes.append({
                'no_compte':       c['no_compte'],
                'libelle':         PLAN.get(c['no_compte'], c['no_compte']),
                'total_debit':     d,
                'total_credit':    cr,
                'solde_debiteur':  sd,
                'solde_crediteur': sc,
            })

        return Response({
            'lignes': lignes,
            'totaux': {
                'total_debit':     tot_debit,
                'total_credit':    tot_credit,
                'solde_debiteur':  tot_sd,
                'solde_crediteur': tot_sc,
            }
        })


class CompteResultatView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant)
        if not exercice:
            return Response({})

        # Produits — comptes 7xx
        produits = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice, no_compte__startswith='7'
        ).aggregate(total=Sum('credit'))
        total_produits = float(produits['total'] or 0)

        # Charges — comptes 6xx
        charges = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice, no_compte__startswith='6'
        ).aggregate(total=Sum('debit'))
        total_charges = float(charges['total'] or 0)

        # Détail produits par compte
        detail_produits = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice, no_compte__startswith='7'
        ).values('no_compte').annotate(total=Sum('credit')).order_by('no_compte')

        # Détail charges par compte
        detail_charges = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice, no_compte__startswith='6'
        ).values('no_compte').annotate(total=Sum('debit')).order_by('no_compte')

        PLAN = {
            '706': 'Ventes prestations - Scolarité',
            '706.1': 'Ventes prestations - Cantine',
            '612': 'Loyer',
            '661': 'Salaires & charges',
            '606': 'Eau, électricité, fournitures',
        }

        return Response({
            'exercice':       exercice.annee_scolaire,
            'total_produits': total_produits,
            'total_charges':  total_charges,
            'resultat_net':   total_produits - total_charges,
            'detail_produits': [{
                'compte':  d['no_compte'],
                'libelle': PLAN.get(d['no_compte'], d['no_compte']),
                'montant': float(d['total'] or 0)
            } for d in detail_produits],
            'detail_charges': [{
                'compte':  d['no_compte'],
                'libelle': PLAN.get(d['no_compte'], d['no_compte']),
                'montant': float(d['total'] or 0)
            } for d in detail_charges],
        })


class BilanView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.paiements.models import Exercice, Paiement
        from apps.dashboard.views import get_tenant

        tenant   = get_tenant(request)
        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()

        if not exercice:
            return Response({})

        paiements = Paiement.objects.filter(tenant=tenant, exercice=exercice)

        def sum_p(qs):
            a = qs.aggregate(
                t=Sum('montant_inscription') + Sum('montant_mensualite') +
                  Sum('montant_uniforme')    + Sum('montant_fournitures') +
                  Sum('montant_cantine')     + Sum('montant_divers')
            )
            return float(a['t'] or 0)

        total_recettes = sum_p(paiements)
        total_charges  = float(JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice, source='CHARGE'
        ).aggregate(t=Sum('debit'))['t'] or 0)
        resultat_net   = total_recettes - total_charges

        solde_initial  = float(exercice.solde_initial_caisse +
                               exercice.solde_initial_banque +
                               exercice.solde_initial_mobile)
        tresorerie     = solde_initial + total_recettes - total_charges

        # ── ACTIF ────────────────────────────────────────────
        # Trésorerie (comptes 5xxx)
        tresorerie_comptes = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice, no_compte__startswith='5'
        ).values('no_compte').annotate(
            d=Sum('debit'), c=Sum('credit')
        )
        tresorerie_detail = []
        total_tresorerie  = 0
        PLAN = {
            '521': 'Banque compte courant', '571': 'Caisse',
            '5521': 'WAVE', '5522': 'Orange Money', '5523': 'Free Money'
        }
        for t in tresorerie_comptes:
            solde = float((t['d'] or 0)) - float((t['c'] or 0))
            if solde > 0:
                tresorerie_detail.append({
                    'compte':  t['no_compte'],
                    'libelle': PLAN.get(t['no_compte'], t['no_compte']),
                    'montant': solde
                })
                total_tresorerie += solde

        # Créances clients (élèves non payés)
        from apps.eleves.models import Eleve
        from django.db.models import Value, DecimalField
        from django.db.models.functions import Coalesce
        eleves = Eleve.objects.filter(
            tenant=tenant, exercice=exercice
        ).annotate(
            paye=Coalesce(
                Sum('paiements__montant_inscription') +
                Sum('paiements__montant_mensualite')  +
                Sum('paiements__montant_uniforme')    +
                Sum('paiements__montant_fournitures') +
                Sum('paiements__montant_cantine')     +
                Sum('paiements__montant_divers'),
                Value(0), output_field=DecimalField()
            )
        ).select_related('section')

        total_creances = sum(
            max(float(e.total_attendu) - float(e.paye or 0), 0)
            for e in eleves
        )

        total_actif = total_tresorerie + total_creances

        # ── PASSIF ───────────────────────────────────────────
        # Capital
        capital = float(exercice.solde_initial_caisse +
                        exercice.solde_initial_banque +
                        exercice.solde_initial_mobile)

        # Dettes fournisseurs (charges non payées — simplifié)
        total_dettes = max(total_charges * 0.1, 0)  # estimation 10% en attente

        total_passif = capital + resultat_net + total_dettes

        return Response({
            'exercice':     exercice.annee_scolaire,
            'date_bilan':   str(exercice.date_fin),
            'actif': {
                'tresorerie':        tresorerie_detail,
                'total_tresorerie':  round(total_tresorerie, 2),
                'creances_clients':  round(total_creances, 2),
                'total_actif':       round(total_actif, 2),
            },
            'passif': {
                'capital':           round(capital, 2),
                'resultat_net':      round(resultat_net, 2),
                'total_capitaux':    round(capital + resultat_net, 2),
                'dettes':            round(total_dettes, 2),
                'total_passif':      round(total_passif, 2),
            },
            'equilibre': abs(total_actif - total_passif) < 1,
        })


class TableauFluxView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.paiements.models import Exercice, Paiement
        from apps.dashboard.views import get_tenant
        from django.db.models.functions import TruncMonth

        tenant   = get_tenant(request)
        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()

        if not exercice:
            return Response({})

        paiements = Paiement.objects.filter(tenant=tenant, exercice=exercice)

        def sum_p(qs):
            a = qs.aggregate(
                t=Sum('montant_inscription') + Sum('montant_mensualite') +
                  Sum('montant_uniforme')    + Sum('montant_fournitures') +
                  Sum('montant_cantine')     + Sum('montant_divers')
            )
            return float(a['t'] or 0)

        # Flux d'exploitation
        encaissements_clients = sum_p(paiements)
        decaissements_charges = float(JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice, source='CHARGE'
        ).aggregate(t=Sum('debit'))['t'] or 0)

        flux_exploitation = encaissements_clients - decaissements_charges

        # Trésorerie
        solde_initial = float(exercice.solde_initial_caisse +
                              exercice.solde_initial_banque +
                              exercice.solde_initial_mobile)
        solde_final   = solde_initial + flux_exploitation

        # Détail par mode de paiement
        from django.db.models import Count
        par_mode = paiements.values('mode_paiement').annotate(
            nb=Count('id'),
            total=Sum('montant_inscription') + Sum('montant_mensualite') +
                  Sum('montant_uniforme')    + Sum('montant_fournitures') +
                  Sum('montant_cantine')     + Sum('montant_divers')
        ).order_by('-total')

        # Flux mensuels
        mensuel = paiements.annotate(
            mois=TruncMonth('date_paiement')
        ).values('mois').annotate(
            encaisse=Sum('montant_inscription') + Sum('montant_mensualite') +
                     Sum('montant_uniforme')    + Sum('montant_fournitures') +
                     Sum('montant_cantine')     + Sum('montant_divers')
        ).order_by('mois')

        # Charges par catégorie
        charges_detail = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice, source='CHARGE'
        ).values('no_compte').annotate(
            total=Sum('debit')
        ).order_by('-total')

        PLAN = {
            '612': 'Loyer', '661': 'Salaires & charges',
            '606': 'Eau, électricité, fournitures',
        }

        return Response({
            'exercice':    exercice.annee_scolaire,
            'methode':     'Directe',
            'flux_exploitation': {
                'encaissements_clients': round(encaissements_clients, 2),
                'decaissements_charges': round(decaissements_charges, 2),
                'flux_net':              round(flux_exploitation, 2),
            },
            'flux_investissement': {
                'acquisitions':  0,
                'cessions':      0,
                'flux_net':      0,
            },
            'flux_financement': {
                'apports_capital': round(solde_initial, 2),
                'flux_net':        round(solde_initial, 2),
            },
            'tresorerie': {
                'solde_initial': round(solde_initial, 2),
                'variation':     round(flux_exploitation, 2),
                'solde_final':   round(solde_final, 2),
            },
            'par_mode': [{
                'mode':  m['mode_paiement'],
                'nb':    m['nb'],
                'total': float(m['total'] or 0)
            } for m in par_mode],
            'flux_mensuels': [{
                'mois':     m['mois'].strftime('%b %Y') if m['mois'] else '',
                'encaisse': float(m['encaisse'] or 0)
            } for m in mensuel if m['mois']],
            'charges_detail': [{
                'compte':  c['no_compte'],
                'libelle': PLAN.get(c['no_compte'], c['no_compte']),
                'montant': float(c['total'] or 0)
            } for c in charges_detail],
        })


class HistoriqueExercicesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.paiements.models import Exercice, Paiement
        from apps.dashboard.views import get_tenant

        tenant = get_tenant(request)

        # Tous les exercices clôturés
        exercices_clotures = Exercice.objects.filter(
            tenant=tenant, cloture=True
        ).order_by('-date_debut')

        # Exercice actif
        exercice_actif = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()

        historique = []
        for ex in exercices_clotures:
            paiements = Paiement.objects.filter(tenant=tenant, exercice=ex)
            total_rec = float(paiements.aggregate(
                t=Sum('montant_inscription') + Sum('montant_mensualite') +
                  Sum('montant_uniforme')    + Sum('montant_fournitures') +
                  Sum('montant_cantine')     + Sum('montant_divers')
            )['t'] or 0)
            total_cha = float(JournalEntry.objects.filter(
                tenant=tenant, exercice=ex, source='CHARGE'
            ).aggregate(t=Sum('debit'))['t'] or 0)
            from apps.eleves.models import Eleve
            nb_eleves = Eleve.objects.filter(tenant=tenant, exercice=ex).count()

            historique.append({
                'id':              str(ex.id),
                'annee_scolaire':  ex.annee_scolaire,
                'date_debut':      str(ex.date_debut),
                'date_fin':        str(ex.date_fin),
                'date_cloture':    str(ex.date_cloture) if ex.date_cloture else None,
                'total_recettes':  round(total_rec, 2),
                'total_charges':   round(total_cha, 2),
                'resultat_net':    round(total_rec - total_cha, 2),
                'nb_eleves':       nb_eleves,
                'nb_paiements':    paiements.count(),
            })

        return Response({
            'exercice_actif': {
                'annee_scolaire': exercice_actif.annee_scolaire if exercice_actif else None,
                'date_debut':     str(exercice_actif.date_debut) if exercice_actif else None,
                'date_fin':       str(exercice_actif.date_fin)   if exercice_actif else None,
            } if exercice_actif else None,
            'historique': historique,
            'nb_exercices_clotures': len(historique),
        })

class ChargeView(APIView):
    permission_classes = [IsAuthenticated]

    PLAN_CHARGES = {
        '601': 'Achats marchandises',
        '602': 'Achats matières premières',
        '604': 'Achats fournitures',
        '606': 'Eau, électricité, fournitures',
        '611': 'Transport',
        '612': 'Loyer',
        '613': 'Locations diverses',
        '621': 'Personnel extérieur',
        '622': 'Rémunérations intermédiaires',
        '623': 'Publicité',
        '624': 'Transport du personnel',
        '625': 'Déplacements et missions',
        '631': 'Frais bancaires',
        '641': 'Impôts et taxes',
        '651': 'Pertes sur créances',
        '661': 'Salaires & charges',
        '662': 'Charges sociales',
        '681': 'Dotations amortissements',
    }

    def get(self, request):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant)
        if not exercice:
            return Response([])

        charges = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice, source='CHARGE',
            debit__gt=0, no_compte__startswith='6'
        ).order_by('-date_ecriture')

        return Response([{
            'id':           str(c.id),
            'date':         str(c.date_ecriture),
            'no_piece':     c.no_piece,
            'no_compte':    c.no_compte,
            'libelle':      c.libelle,
            'montant':      float(c.debit),
            'libelle_compte': self.PLAN_CHARGES.get(c.no_compte, c.no_compte),
        } for c in charges])

    def post(self, request):
        tenant   = get_tenant(request)
        exercice = get_exercice(tenant)
        if not exercice:
            return Response({'error': 'Aucun exercice actif'}, status=400)

        data = request.data
        no_compte = data.get('no_compte', '606')
        montant   = float(data.get('montant', 0))
        libelle   = data.get('libelle', '')
        date      = data.get('date', str(timezone.now().date()))

        if montant <= 0:
            return Response({'error': 'Montant invalide'}, status=400)

        # Générer no_piece
        from django.db.models import Max
        import re
        last = JournalEntry.objects.filter(
            tenant=tenant, source='CHARGE'
        ).aggregate(Max('no_piece'))['no_piece__max']
        nums = re.findall(r'\d+', last or 'CHG-0000')
        no_piece = f"CHG-{int(nums[-1]) + 1:04d}" if nums else 'CHG-0001'

        libelle_compte = self.PLAN_CHARGES.get(no_compte, no_compte)

        # Double écriture SYSCOHADA charges
        # Débit compte de charge (6xx) / Crédit compte de trésorerie (5xx/571)
        compte_credit = data.get('compte_credit', '571')  # Caisse par défaut

        JournalEntry.objects.create(
            tenant=tenant, exercice=exercice,
            no_piece=no_piece, date_ecriture=date,
            no_compte=no_compte,
            libelle=f"{libelle_compte} - {libelle}",
            debit=montant, credit=0,
            source='CHARGE', source_id=None,
        )
        JournalEntry.objects.create(
            tenant=tenant, exercice=exercice,
            no_piece=no_piece, date_ecriture=date,
            no_compte=compte_credit,
            libelle=f"Règlement {libelle_compte} - {libelle}",
            debit=0, credit=montant,
            source='CHARGE', source_id=None,
        )

        return Response({
            'success': True,
            'no_piece': no_piece,
            'montant': montant,
            'libelle': libelle,
        }, status=201)

    def delete(self, request, pk):
        tenant = get_tenant(request)
        JournalEntry.objects.filter(
            tenant=tenant, source='CHARGE',
            no_piece=JournalEntry.objects.get(id=pk).no_piece
        ).delete()
        return Response({'success': True})