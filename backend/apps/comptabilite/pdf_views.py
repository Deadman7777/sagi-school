from django.http import HttpResponse
from django.template.loader import render_to_string
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum
from django.utils import timezone
from apps.paiements.models import Exercice, Paiement
from apps.eleves.models import Eleve
from apps.comptabilite.models import JournalEntry
from apps.dashboard.views import get_tenant, sum_paiements


class ExportPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, type_doc):
        try:
            from weasyprint import HTML, CSS
        except ImportError:
            return HttpResponse('WeasyPrint non installé', status=500)

        tenant   = get_tenant(request)
        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()

        if not exercice:
            return HttpResponse('Aucun exercice actif', status=404)

        context = self._build_context(tenant, exercice, type_doc)
        html_str = render_to_string(f'pdf/{type_doc}.html', context)

        pdf = HTML(string=html_str, base_url=request.build_absolute_uri()).write_pdf()

        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{type_doc}_{exercice.annee_scolaire}.pdf"'
        return response

    def _build_context(self, tenant, exercice, type_doc):
            from apps.paiements.models import Paiement
            from apps.eleves.models import Eleve
            from django.db.models import Value, DecimalField
            from django.db.models.functions import Coalesce

            paiements = Paiement.objects.filter(tenant=tenant, exercice=exercice)
            total_recettes = sum_paiements(paiements)
            total_charges  = float(JournalEntry.objects.filter(
                tenant=tenant, exercice=exercice, source='CHARGE'
            ).aggregate(t=Sum('debit'))['t'] or 0)

            PLAN = {
                '706': 'Ventes prestations - Scolarité',
                '706.1': 'Ventes prestations - Cantine',
                '612': 'Loyer', '661': 'Salaires & charges',
                '606': 'Eau, électricité, fournitures',
                '521': 'Banque compte courant', '571': 'Caisse',
                '5521': 'WAVE', '5522': 'Orange Money', '5523': 'Free Money'
            }

            detail_produits = JournalEntry.objects.filter(
                tenant=tenant, exercice=exercice, no_compte__startswith='7'
            ).values('no_compte').annotate(total=Sum('credit')).order_by('no_compte')

            detail_charges = JournalEntry.objects.filter(
                tenant=tenant, exercice=exercice, no_compte__startswith='6'
            ).values('no_compte').annotate(total=Sum('debit')).order_by('no_compte')

            balance = JournalEntry.objects.filter(
                tenant=tenant, exercice=exercice
            ).values('no_compte').annotate(
                total_debit=Sum('debit'), total_credit=Sum('credit')
            ).order_by('no_compte')

            balance_data = []
            tot_d = tot_c = tot_sd = tot_sc = 0
            for b in balance:
                d  = float(b['total_debit']  or 0)
                cr = float(b['total_credit'] or 0)
                sd = max(d - cr, 0); sc = max(cr - d, 0)
                tot_d += d; tot_c += cr; tot_sd += sd; tot_sc += sc
                balance_data.append({
                    'compte': b['no_compte'],
                    'libelle': PLAN.get(b['no_compte'], b['no_compte']),
                    'debit': d, 'credit': cr, 'solde_d': sd, 'solde_c': sc
                })

            # Bilan
            solde_initial = float(exercice.solde_initial_caisse +
                                exercice.solde_initial_banque +
                                exercice.solde_initial_mobile)
            resultat_net  = total_recettes - total_charges

            tresorerie_comptes = JournalEntry.objects.filter(
                tenant=tenant, exercice=exercice, no_compte__startswith='5'
            ).values('no_compte').annotate(d=Sum('debit'), c=Sum('credit'))
            tresorerie_detail = []
            total_tresorerie  = 0
            for t in tresorerie_comptes:
                solde = float((t['d'] or 0)) - float((t['c'] or 0))
                if solde > 0:
                    tresorerie_detail.append({
                        'libelle': PLAN.get(t['no_compte'], t['no_compte']),
                        'montant': solde
                    })
                    total_tresorerie += solde

            eleves = Eleve.objects.filter(tenant=tenant, exercice=exercice).annotate(
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
                max(float(e.total_attendu) - float(e.paye or 0), 0) for e in eleves
            )
            total_actif  = total_tresorerie + total_creances
            total_dettes = max(total_charges * 0.1, 0)
            total_passif = solde_initial + resultat_net + total_dettes

            # Flux mensuels
            from django.db.models.functions import TruncMonth
            from django.db.models import Count
            par_mode = paiements.values('mode_paiement').annotate(
                nb=Count('id'),
                total=Sum('montant_inscription') + Sum('montant_mensualite') +
                    Sum('montant_uniforme')    + Sum('montant_fournitures') +
                    Sum('montant_cantine')     + Sum('montant_divers')
            ).order_by('-total')

            # Journal
            journal_entries = JournalEntry.objects.filter(
                tenant=tenant, exercice=exercice
            ).order_by('date_ecriture', 'no_piece')
            total_debit_journal  = float(journal_entries.aggregate(t=Sum('debit'))['t'] or 0)
            total_credit_journal = float(journal_entries.aggregate(t=Sum('credit'))['t'] or 0)
            
            return {
                'tenant':          tenant,
                'exercice':        exercice,
                'date_edition':    timezone.now(),
                'total_recettes':  total_recettes,
                'total_charges':   total_charges,
                'resultat_net':    total_recettes - total_charges,
                'tresorerie':      {
                    'solde_initial': solde_initial,
                    'variation':     resultat_net,
                    'solde_final':   solde_initial + resultat_net,
                },
                'detail_produits': [{'compte': d['no_compte'],
                                    'libelle': PLAN.get(d['no_compte'], d['no_compte']),
                                    'montant': float(d['total'] or 0)} for d in detail_produits],
                'detail_charges':  [{'compte': d['no_compte'],
                                    'libelle': PLAN.get(d['no_compte'], d['no_compte']),
                                    'montant': float(d['total'] or 0)} for d in detail_charges],
                'balance':         balance_data,
                'balance_totaux':  {'debit': tot_d, 'credit': tot_c,
                                    'solde_d': tot_sd, 'solde_c': tot_sc},
                # Bilan
                'actif': {
                    'tresorerie':       tresorerie_detail,
                    'total_tresorerie': round(total_tresorerie, 2),
                    'creances_clients': round(total_creances, 2),
                    'total_actif':      round(total_actif, 2),
                },
                'passif': {
                    'capital':        round(solde_initial, 2),
                    'resultat_net':   round(resultat_net, 2),
                    'total_capitaux': round(solde_initial + resultat_net, 2),
                    'dettes':         round(total_dettes, 2),
                    'total_passif':   round(total_passif, 2),
                },
                'equilibre': abs(total_actif - total_passif) < 1,
                # Flux
                'methode': 'Directe',
                'flux_exploitation': {
                    'encaissements_clients': round(total_recettes, 2),
                    'decaissements_charges': round(total_charges, 2),
                    'flux_net':              round(resultat_net, 2),
                },
                'flux_financement': {
                    'apports_capital': round(solde_initial, 2),
                    'flux_net':        round(solde_initial, 2),
                },
                'par_mode': [{'mode': m['mode_paiement'], 'nb': m['nb'],
                            'total': float(m['total'] or 0)} for m in par_mode],
                'eleves':    eleves,
                'paiements': paiements.select_related('eleve').order_by('date_paiement'),
                'journal':       journal_entries,
                'total_debit':   total_debit_journal,
                'total_credit':  total_credit_journal,
            }
