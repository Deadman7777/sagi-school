"""
Export PDF des documents comptables SYSCOHADA Révisé.
Chaque type_doc réutilise exactement la logique de l'API view correspondante.
"""
from io import BytesIO
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.db.models import Sum, Q, Value, DecimalField, Count
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from apps.paiements.models import Exercice, Paiement
from apps.eleves.models import Eleve
from apps.comptabilite.models import JournalEntry, CompteComptable, BudgetLigne, Immobilisation

from apps.comptabilite.views import (
    get_plan_dict, get_tenant, get_exercice,
    _mobile_aggregate, _sum_paiements, _detecter_systeme,
    _compte_sort_key, _immo_to_dict,
    _compute_account_sfs, _sum_sf_side,
    PLAN_COMPTABLE, MOBILE_ACCOUNTS, SEUIL_SMT_SERVICES, MOIS_CHAMPS, MOIS_NOMS,
)


class ExportPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, type_doc):
        try:
            from xhtml2pdf import pisa
        except ImportError:
            return HttpResponse('xhtml2pdf non installé', status=500)

        tenant   = get_tenant(request)
        # Honore ?exercice=<id> pour exporter une année clôturée ; sinon actif.
        exercice = get_exercice(tenant, request)

        if not exercice:
            return HttpResponse('Aucun exercice actif', status=404)

        try:
            context = self._build_context(tenant, exercice, type_doc)
        except Exception as e:
            import traceback
            return HttpResponse(f'Erreur contexte : {e}\n{traceback.format_exc()}', status=500)

        try:
            html_str = render_to_string(f'pdf/{type_doc}.html', context)
        except Exception as e:
            return HttpResponse(f'Template introuvable : pdf/{type_doc}.html — {e}', status=500)

        buffer = BytesIO()
        result = pisa.CreatePDF(html_str, dest=buffer, encoding='utf-8')
        if result.err:
            return HttpResponse('Erreur génération PDF.', status=500)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = (
            f'attachment; filename="{type_doc}_{exercice.annee_scolaire}.pdf"'
        )
        return response

    # ──────────────────────────────────────────────────────────────────────────
    def _build_context(self, tenant, exercice, type_doc):
        ctx = {
            'tenant':       tenant,
            'exercice':     exercice,
            'date_edition': timezone.now(),
        }

        entries   = JournalEntry.objects.filter(tenant=tenant, exercice=exercice)
        paiements = Paiement.objects.filter(tenant=tenant, exercice=exercice)
        plan      = get_plan_dict(tenant)

        # ── JOURNAL ────────────────────────────────────────────────────────────
        if type_doc == 'journal':
            qs = entries.order_by('date_ecriture', 'no_piece', 'ordre')
            journal_data = [{
                'date_ecriture':  e.date_ecriture,
                'no_piece':       e.no_piece,
                'no_compte':      e.no_compte,
                'libelle_compte': plan.get(e.no_compte, e.no_compte),
                'libelle':        e.libelle,
                'debit':          float(e.debit),
                'credit':         float(e.credit),
                'source':         e.source,
            } for e in qs]
            ctx.update({
                'journal':      journal_data,
                'total_debit':  round(sum(r['debit']  for r in journal_data), 2),
                'total_credit': round(sum(r['credit'] for r in journal_data), 2),
            })

        # ── GRAND LIVRE ────────────────────────────────────────────────────────
        elif type_doc == 'grand_livre':
            mob_d, mob_c = _mobile_aggregate(tenant, exercice)
            comptes = entries.exclude(
                no_compte__in=('5521', '5522', '5523')
            ).values('no_compte').annotate(
                total_debit=Sum('debit'), total_credit=Sum('credit')
            ).order_by('no_compte')

            data = {}
            for c in comptes:
                no = c['no_compte']
                d  = float(c['total_debit']  or 0)
                cr = float(c['total_credit'] or 0)
                if no == '552':
                    d, cr = mob_d, mob_c
                data[no] = {
                    'no_compte':       no,
                    'libelle':         plan.get(no, no),
                    'total_debit':     round(d, 2),
                    'total_credit':    round(cr, 2),
                    'solde_debiteur':  round(max(d - cr, 0), 2),
                    'solde_crediteur': round(max(cr - d, 0), 2),
                    'is_synthetic':    False,
                }
            if mob_d > 0 or mob_c > 0:
                if '552' not in data:
                    data['552'] = {
                        'no_compte': '552', 'libelle': plan.get('552', 'Mobile Money'),
                        'total_debit': round(mob_d, 2), 'total_credit': round(mob_c, 2),
                        'solde_debiteur':  round(max(mob_d - mob_c, 0), 2),
                        'solde_crediteur': round(max(mob_c - mob_d, 0), 2),
                        'is_synthetic': True,
                    }
            for sub in ('5521', '5522', '5523'):
                agg = entries.filter(no_compte=sub).aggregate(d=Sum('debit'), c=Sum('credit'))
                sd, sc = float(agg['d'] or 0), float(agg['c'] or 0)
                if sd > 0 or sc > 0:
                    data[sub] = {
                        'no_compte': sub, 'libelle': f'  └ {plan.get(sub, sub)}',
                        'total_debit': round(sd, 2), 'total_credit': round(sc, 2),
                        'solde_debiteur':  round(max(sd - sc, 0), 2),
                        'solde_crediteur': round(max(sc - sd, 0), 2),
                        'is_synthetic': False,
                    }

            gl = sorted(data.values(), key=lambda x: _compte_sort_key(x['no_compte']))
            ctx.update({
                'grand_livre':    gl,
                'gl_total_debit':  round(sum(r['total_debit']    for r in gl), 2),
                'gl_total_credit': round(sum(r['total_credit']   for r in gl), 2),
                'gl_total_sd':     round(sum(r['solde_debiteur'] for r in gl), 2),
                'gl_total_sc':     round(sum(r['solde_crediteur']for r in gl), 2),
            })

        # ── BALANCE ────────────────────────────────────────────────────────────
        elif type_doc == 'balance':
            mob_d, mob_c = _mobile_aggregate(tenant, exercice)
            soldes_initiaux = {
                '521': float(exercice.solde_initial_banque),
                '571': float(exercice.solde_initial_caisse),
                '552': float(exercice.solde_initial_mobile),
            }
            comptes = entries.exclude(
                no_compte__in=('5521', '5522', '5523')
            ).values('no_compte').annotate(
                mvt_debit=Sum('debit'), mvt_credit=Sum('credit')
            ).order_by('no_compte')

            lignes = {}
            tot_so_d = tot_so_c = tot_mvt_d = tot_mvt_c = tot_sf_d = tot_sf_c = 0.0

            for c in comptes:
                no    = c['no_compte']
                mvt_d = float(c['mvt_debit']  or 0)
                mvt_c = float(c['mvt_credit'] or 0)
                if no == '552':
                    mvt_d, mvt_c = mob_d, mob_c
                so_d    = soldes_initiaux.get(no, 0.0)
                total_d = so_d + mvt_d
                sf_d = round(max(total_d - mvt_c, 0), 2)
                sf_c = round(max(mvt_c - total_d, 0), 2)
                if no not in lignes:
                    lignes[no] = {
                        'no_compte':    no,
                        'libelle':      plan.get(no, no),
                        'so_debiteur':  round(so_d, 2),
                        'so_crediteur': 0,
                        'mvt_debit':    round(mvt_d, 2),
                        'mvt_credit':   round(mvt_c, 2),
                        'sf_debiteur':  sf_d,
                        'sf_crediteur': sf_c,
                        'is_synthetic': False,
                    }
                    tot_so_d  += so_d;  tot_mvt_d += mvt_d;  tot_mvt_c += mvt_c
                    tot_sf_d  += sf_d;  tot_sf_c  += sf_c

            if '552' not in lignes and (mob_d > 0 or mob_c > 0):
                so_d = float(exercice.solde_initial_mobile)
                total_d = so_d + mob_d
                sf_d = round(max(total_d - mob_c, 0), 2)
                sf_c = round(max(mob_c - total_d, 0), 2)
                lignes['552'] = {
                    'no_compte': '552', 'libelle': plan.get('552', 'Mobile Money'),
                    'so_debiteur': round(so_d, 2), 'so_crediteur': 0,
                    'mvt_debit': round(mob_d, 2), 'mvt_credit': round(mob_c, 2),
                    'sf_debiteur': sf_d, 'sf_crediteur': sf_c, 'is_synthetic': True,
                }
                tot_so_d += so_d; tot_mvt_d += mob_d; tot_mvt_c += mob_c
                tot_sf_d += sf_d; tot_sf_c  += sf_c

            bal_sorted = sorted(lignes.values(), key=lambda x: _compte_sort_key(x['no_compte']))
            ctx.update({
                'balance': bal_sorted,
                'balance_totaux': {
                    'so_debiteur':  round(tot_so_d, 2),
                    'so_crediteur': round(tot_so_c, 2),
                    'mvt_debit':    round(tot_mvt_d, 2),
                    'mvt_credit':   round(tot_mvt_c, 2),
                    'sf_debiteur':  round(tot_sf_d, 2),
                    'sf_crediteur': round(tot_sf_c, 2),
                },
            })

        # ── COMPTE DE RÉSULTAT ─────────────────────────────────────────────────
        elif type_doc == 'compte_resultat':
            caht    = _sum_paiements(paiements)
            systeme = _detecter_systeme(caht)

            def _sum(prefixes, field='debit'):
                q = Q()
                for p in prefixes: q |= Q(no_compte__startswith=p)
                return float(entries.filter(q).aggregate(t=Sum(field))['t'] or 0)

            def _detail(prefixes, field='debit'):
                q = Q()
                for p in prefixes: q |= Q(no_compte__startswith=p)
                rows = entries.filter(q).values('no_compte').annotate(t=Sum(field)).order_by('no_compte')
                return [{'compte': r['no_compte'],
                         'libelle': plan.get(r['no_compte'], r['no_compte']),
                         'montant': round(float(r['t'] or 0), 2)}
                        for r in rows if float(r['t'] or 0) > 0]

            ventes_marchandises      = _sum(['701'], 'credit')
            prestations_services     = _sum(['706', '707', '708'], 'credit')
            subventions_exploitation = _sum(['74'], 'credit')
            autres_produits          = _sum(['75'], 'credit')
            reprises_amort           = _sum(['781', '791'], 'credit')
            production_exercice = prestations_services + subventions_exploitation + autres_produits + reprises_amort

            achats_marchandises  = _sum(['601'], 'debit')
            autres_achats        = _sum(['602', '604', '605', '607', '608'], 'debit')
            transports           = _sum(['61'], 'debit')
            services_ext_a       = _sum(['621', '622', '623', '624', '625'], 'debit')
            services_ext_b       = _sum(['626', '627', '628'], 'debit')
            impots_taxes         = _sum(['641', '642', '645'], 'debit')
            autres_charges       = _sum(['651', '652', '653', '655', '658'], 'debit')
            charges_personnel    = _sum(['661', '662', '663', '664', '665', '666', '6641'], 'debit')
            dotations_amort      = _sum(['681', '691'], 'debit')
            consommations_interm = autres_achats + transports + services_ext_a + services_ext_b

            mc  = ventes_marchandises - achats_marchandises
            vab = mc + production_exercice - consommations_interm
            ebe = vab - charges_personnel - impots_taxes
            re  = ebe - dotations_amort - autres_charges
            produits_financiers = _sum(['77'], 'credit')
            charges_financieres = _sum(['67', '631'], 'debit')
            rf  = produits_financiers - charges_financieres
            rao = re + rf
            resultat_hao = _sum(['82', '84', '85', '86', '88'], 'credit') - _sum(['81', '83', '85', '87'], 'debit')
            impot        = _sum(['89'], 'debit')
            resultat_net = rao + resultat_hao - impot

            _7agg = entries.filter(no_compte__startswith='7').aggregate(t_d=Sum('debit'), t_c=Sum('credit'))
            _6agg = entries.filter(no_compte__startswith='6').aggregate(t_d=Sum('debit'), t_c=Sum('credit'))
            _haop_agg = entries.filter(
                Q(no_compte__startswith='82') | Q(no_compte__startswith='84') |
                Q(no_compte__startswith='86') | Q(no_compte__startswith='88')
            ).aggregate(t_d=Sum('debit'), t_c=Sum('credit'))
            _haoc_agg = entries.filter(
                Q(no_compte__startswith='81') | Q(no_compte__startswith='83') |
                Q(no_compte__startswith='87') | Q(no_compte__startswith='89')
            ).aggregate(t_d=Sum('debit'), t_c=Sum('credit'))
            total_produits = round(
                float(_7agg['t_c'] or 0) - float(_7agg['t_d'] or 0) +
                max(float(_haop_agg['t_c'] or 0) - float(_haop_agg['t_d'] or 0), 0), 2)
            total_charges = round(
                float(_6agg['t_d'] or 0) - float(_6agg['t_c'] or 0) +
                max(float(_haoc_agg['t_d'] or 0) - float(_haoc_agg['t_c'] or 0), 0), 2)
            resultat_net  = round(total_produits - total_charges, 2)

            ctx.update({
                'systeme':  systeme,
                'caht':     round(caht, 2),
                'sig': {
                    'ventes_marchandises':  round(ventes_marchandises, 2),
                    'achats_marchandises':  round(achats_marchandises, 2),
                    'mc':                   round(mc, 2),
                    'production_exercice':  round(production_exercice, 2),
                    'consommations_interm': round(consommations_interm, 2),
                    'vab':                  round(vab, 2),
                    'charges_personnel':    round(charges_personnel, 2),
                    'impots_taxes':         round(impots_taxes, 2),
                    'ebe':                  round(ebe, 2),
                    'dotations_amort':      round(dotations_amort, 2),
                    'autres_charges':       round(autres_charges, 2),
                    're':                   round(re, 2),
                    'produits_financiers':  round(produits_financiers, 2),
                    'charges_financieres':  round(charges_financieres, 2),
                    'rf':                   round(rf, 2),
                    'rao':                  round(rao, 2),
                    'resultat_hao':         round(resultat_hao, 2),
                    'impot':                round(impot, 2),
                    'resultat_net':         round(resultat_net, 2),
                },
                'detail_produits': _detail(['7', '82', '84', '86', '88'], 'credit'),
                'detail_charges':  _detail(['6', '81', '83', '85', '87', '89'], 'debit'),
                'total_produits':  total_produits,
                'total_charges':   total_charges,
                'resultat_net':    resultat_net,
            })

        # ── BILAN ──────────────────────────────────────────────────────────────
        elif type_doc == 'bilan':
            caht    = _sum_paiements(paiements)
            systeme = _detecter_systeme(caht)

            sfs = _compute_account_sfs(entries, exercice, tenant)

            incorporel_t, incorporel_d = _sum_sf_side(sfs, 'sf_d', ['20', '21'], plan)
            corporel_t,   corporel_d   = _sum_sf_side(sfs, 'sf_d', ['22', '23', '24', '25'], plan)
            financier_t,  financier_d  = _sum_sf_side(sfs, 'sf_d', ['26', '27'], plan)
            amort_t, _                 = _sum_sf_side(sfs, 'sf_c', ['28'], plan)
            total_corporel_net = round(max(corporel_t - amort_t, 0), 2)
            total_immobilise   = round(incorporel_t + total_corporel_net + financier_t, 2)

            stocks_t,   stocks_d   = _sum_sf_side(sfs, 'sf_d', ['31','32','33','34','35','36','37','38'], plan)
            creances_t, creances_d = _sum_sf_side(sfs, 'sf_d', ['40','41','42','43','44','45','46','47'], plan)
            prov_b_t,   _          = _sum_sf_side(sfs, 'sf_c', ['49'], plan)
            total_circulant_ao = round(stocks_t + creances_t - prov_b_t, 2)

            hao_actif_t, hao_actif_d = _sum_sf_side(sfs, 'sf_d', ['48'], plan)

            treso_actif_t, treso_actif_d = _sum_sf_side(sfs, 'sf_d', ['51','52','53','54','55','57','58'], plan)

            total_actif = round(total_immobilise + total_circulant_ao + hao_actif_t + treso_actif_t, 2)

            capital = float(exercice.solde_initial_banque + exercice.solde_initial_caisse +
                            exercice.solde_initial_mobile)
            _7agg = entries.filter(no_compte__startswith='7').aggregate(d=Sum('debit'), c=Sum('credit'))
            _6agg = entries.filter(no_compte__startswith='6').aggregate(d=Sum('debit'), c=Sum('credit'))
            resultat_net = round(
                float(_7agg['c'] or 0) - float(_7agg['d'] or 0) -
                (float(_6agg['d'] or 0) - float(_6agg['c'] or 0)), 2)
            total_capitaux = round(capital + resultat_net, 2)

            dettes_fin_t, dettes_fin_d = _sum_sf_side(sfs, 'sf_c', ['16', '17', '18', '19'], plan)
            dettes_ao_t,  dettes_ao_d  = _sum_sf_side(sfs, 'sf_c', ['40','41','42','43','44','45','46','47'], plan)
            hao_passif_t, hao_passif_d = _sum_sf_side(sfs, 'sf_c', ['48'], plan)
            treso_passif_t, treso_passif_d = _sum_sf_side(sfs, 'sf_c', ['51','52','53','54','55','57','58'], plan)

            total_passif = round(total_capitaux + dettes_fin_t + dettes_ao_t + hao_passif_t + treso_passif_t, 2)

            def _sub(detail, prefixes):
                return round(sum(x['montant'] for x in detail if any(x['compte'].startswith(p) for p in prefixes)), 2)

            ctx.update({
                'systeme': systeme,
                'caht':    round(caht, 2),
                'actif': {
                    'immobilise': {
                        'incorporel': incorporel_d,
                        'corporel':   corporel_d,
                        'financier':  financier_d,
                        'amort':      round(amort_t, 2),
                        'total':      total_immobilise,
                    },
                    'circulant_ao': {
                        'stocks':   stocks_d,
                        'creances': creances_d,
                        'total':    total_circulant_ao,
                    },
                    'circulant_hao': {
                        'detail': hao_actif_d,
                        'total':  hao_actif_t,
                    },
                    'tresorerie_actif': {
                        'detail': treso_actif_d,
                        'total':  treso_actif_t,
                    },
                    'total_actif': total_actif,
                },
                'passif': {
                    'capitaux_propres': {
                        'capital':      round(capital, 2),
                        'resultat_net': resultat_net,
                        'total':        total_capitaux,
                    },
                    'dettes_financieres': {
                        'detail': dettes_fin_d,
                        'total':  dettes_fin_t,
                    },
                    'passif_circulant_ao': {
                        'detail':           dettes_ao_d,
                        'fournisseurs':     _sub(dettes_ao_d, ['40', '401', '404']),
                        'dettes_fiscales':  _sub(dettes_ao_d, ['44']),
                        'dettes_personnel': _sub(dettes_ao_d, ['42']),
                        'dettes_sociales':  _sub(dettes_ao_d, ['43']),
                        'total':            dettes_ao_t,
                    },
                    'passif_circulant_hao': {
                        'detail': hao_passif_d,
                        'total':  hao_passif_t,
                    },
                    'tresorerie_passif': {
                        'detail': treso_passif_d,
                        'total':  treso_passif_t,
                    },
                    'total_passif': total_passif,
                },
                'equilibre': abs(total_actif - total_passif) < 1,
            })

        # ── TABLEAU DES FLUX — Méthode Indirecte (AUDCIF Art. 32) ────────────────
        elif type_doc == 'tableau_flux':
            systeme = _detecter_systeme(_sum_paiements(paiements))

            sfs = _compute_account_sfs(entries, exercice, tenant)

            _7agg = entries.filter(no_compte__startswith='7').aggregate(d=Sum('debit'), c=Sum('credit'))
            _6agg = entries.filter(no_compte__startswith='6').aggregate(d=Sum('debit'), c=Sum('credit'))
            resultat_net = round(
                float(_7agg['c'] or 0) - float(_7agg['d'] or 0) -
                (float(_6agg['d'] or 0) - float(_6agg['c'] or 0)), 2)

            amort = round(float(entries.filter(
                Q(no_compte__startswith='681') | Q(no_compte__startswith='691')
            ).aggregate(t=Sum('debit'))['t'] or 0), 2)

            actif_b_t, _ = _sum_sf_side(sfs, 'sf_d',
                ['31','32','33','34','35','36','37','38','40','41','42','43','44','45','46','47'], plan)
            passif_h_t, _ = _sum_sf_side(sfs, 'sf_c',
                ['40','41','42','43','44','45','46','47'], plan)
            var_actif_b  = round(-actif_b_t, 2)
            var_passif_h = round(passif_h_t, 2)
            flux_a = round(resultat_net + amort + var_actif_b + var_passif_h, 2)

            TRESO_COMPTES = list(MOBILE_ACCOUNTS) + ['521', '522', '571']
            agg_inv_out = entries.filter(
                source='INVEST', no_compte__in=TRESO_COMPTES, credit__gt=0,
            ).aggregate(t=Sum('credit'))
            acquisitions = round(float(agg_inv_out['t'] or 0), 2)
            agg_inv_in = entries.filter(
                source__in=('INVEST', 'CESSION'), no_compte__in=TRESO_COMPTES, debit__gt=0,
            ).aggregate(t=Sum('debit'))
            cessions = round(float(agg_inv_in['t'] or 0), 2)
            flux_b = round(cessions - acquisitions, 2)

            agg_empr = entries.filter(
                Q(no_compte__startswith='16') | Q(no_compte__startswith='17') |
                Q(no_compte__startswith='18') | Q(no_compte__startswith='19')
            ).aggregate(d=Sum('debit'), c=Sum('credit'))
            nouveaux_emprunts = round(float(agg_empr['c'] or 0), 2)
            remboursements    = round(float(agg_empr['d'] or 0), 2)
            flux_c = round(nouveaux_emprunts - remboursements, 2)

            treso_actif_t,  _ = _sum_sf_side(sfs, 'sf_d', ['51','52','53','54','55','57','58'], plan)
            treso_passif_t, _ = _sum_sf_side(sfs, 'sf_c', ['51','52','53','54','55','57','58'], plan)
            tn_fin   = round(treso_actif_t - treso_passif_t, 2)
            tn_debut = round(float(exercice.solde_initial_banque + exercice.solde_initial_caisse +
                                   exercice.solde_initial_mobile), 2)
            variation = round(flux_a + flux_b + flux_c, 2)

            par_mode_qs = paiements.values('mode_paiement').annotate(
                nb=Count('id'),
                total=Coalesce(
                    Sum('montant_inscription') + Sum('montant_mensualite') +
                    Sum('montant_uniforme') + Sum('montant_fournitures') +
                    Sum('montant_cantine') + Sum('montant_divers'),
                    Value(0), output_field=DecimalField()
                )
            ).order_by('-total')

            ctx.update({
                'methode': 'Indirecte',
                'systeme': systeme,
                'flux_a': {
                    'resultat_net':  resultat_net,
                    'amort':         amort,
                    'var_actif_b':   var_actif_b,
                    'var_passif_h':  var_passif_h,
                    'flux_net':      flux_a,
                },
                'flux_b': {
                    'acquisitions': acquisitions,
                    'cessions':     cessions,
                    'flux_net':     flux_b,
                },
                'flux_c': {
                    'emprunts':       nouveaux_emprunts,
                    'remboursements': remboursements,
                    'flux_net':       flux_c,
                },
                'tresorerie': {
                    'tn_debut':  tn_debut,
                    'variation': variation,
                    'tn_fin':    tn_fin,
                },
                'par_mode': [
                    {'mode': p['mode_paiement'], 'nb': p['nb'], 'total': float(p['total'] or 0)}
                    for p in par_mode_qs
                ],
            })

        # ── NOTES ANNEXES ──────────────────────────────────────────────────────
        elif type_doc == 'notes_annexes':
            caht    = _sum_paiements(paiements)
            systeme = _detecter_systeme(caht)
            nb_eleves    = Eleve.objects.filter(tenant=tenant, exercice=exercice).count()
            nb_paiements = paiements.count()
            total_charges_n = float(entries.filter(no_compte__startswith='6').aggregate(t=Sum('debit'))['t'] or 0)
            charges_perso   = float(entries.filter(no_compte__in=['661', '662']).aggregate(t=Sum('debit'))['t'] or 0)

            sections = Eleve.objects.filter(tenant=tenant, exercice=exercice).values(
                'section__nom'
            ).annotate(nb=Count('id')).order_by('-nb')

            treso_cloture = []
            for no, lib in [('521', 'Banque'), ('571', 'Caisse'), ('552', 'Mobile Money')]:
                if no == '552':
                    mob_d, mob_c = _mobile_aggregate(tenant, exercice)
                    solde = float(exercice.solde_initial_mobile) + mob_d - mob_c
                else:
                    so_key = 'solde_initial_banque' if no == '521' else 'solde_initial_caisse'
                    so = float(getattr(exercice, so_key, 0))
                    agg = entries.filter(no_compte=no).aggregate(d=Sum('debit'), c=Sum('credit'))
                    solde = so + float(agg['d'] or 0) - float(agg['c'] or 0)
                if abs(solde) > 0:
                    treso_cloture.append({'compte': no, 'libelle': lib, 'solde': round(solde, 2)})

            _7agg = entries.filter(no_compte__startswith='7').aggregate(d=Sum('debit'), c=Sum('credit'))
            _6agg = entries.filter(no_compte__startswith='6').aggregate(d=Sum('debit'), c=Sum('credit'))
            resultat_net_n = round(
                (float(_7agg['c'] or 0) - float(_7agg['d'] or 0)) -
                (float(_6agg['d'] or 0) - float(_6agg['c'] or 0)), 2
            )
            ctx.update({
                'systeme':    systeme,
                'caht':       round(caht, 2),
                'seuil_smt':  SEUIL_SMT_SERVICES,
                'resultat_net': resultat_net_n,
                'note1': {
                    'secteur':      'Éducation (Services)',
                    'referentiel':  f'SYSCOHADA Révisé (AUDCIF 2017) — {systeme}',
                    'nb_eleves':    nb_eleves,
                    'nb_paiements': nb_paiements,
                    'sections':     [{'nom': s['section__nom'] or '—', 'nb': s['nb']} for s in sections],
                },
                'note2': {
                    'base_evaluation': 'Coût historique',
                    'amortissement':   'Linéaire sur la durée d\'utilisation estimée',
                    'creances':        'Évaluées à leur valeur nominale',
                    'tresorerie':      'Espèces, banque et monnaie électronique (57x / 552x)',
                    'comptabilite':    'Engagement — créances et dettes constatées à la date de l\'opération',
                },
                'note3': {
                    'masse_salariale': round(charges_perso, 2),
                    'total_charges':   round(total_charges_n, 2),
                },
                'note4': {'comptes': treso_cloture},
            })

        # ── CHARGES ────────────────────────────────────────────────────────────
        elif type_doc == 'charges':
            caht    = _sum_paiements(paiements)
            charges_qs = entries.filter(
                source__in=('CHARGE', 'PAIE'), debit__gt=0
            ).filter(
                Q(no_compte__startswith='6') | Q(no_compte__startswith='2')
            ).order_by('-date_ecriture')

            charges_list = [{
                'date_ecriture':  c.date_ecriture,
                'no_piece':       c.no_piece,
                'no_compte':      c.no_compte,
                'libelle':        c.libelle,
                'montant':        float(c.debit),
                'libelle_compte': plan.get(c.no_compte, c.no_compte),
            } for c in charges_qs]

            total_charges = round(sum(r['montant'] for r in charges_list), 2)
            total_recettes = round(caht, 2)

            _6agg = entries.filter(no_compte__startswith='6').aggregate(d=Sum('debit'), c=Sum('credit'))
            _7agg = entries.filter(no_compte__startswith='7').aggregate(d=Sum('debit'), c=Sum('credit'))
            resultat_net = round(
                (float(_7agg['c'] or 0) - float(_7agg['d'] or 0)) -
                (float(_6agg['d'] or 0) - float(_6agg['c'] or 0)), 2
            )
            ctx.update({
                'charges_list':  charges_list,
                'total_charges': total_charges,
                'total_recettes': total_recettes,
                'resultat_net':  resultat_net,
            })

        # ── BUDGET ─────────────────────────────────────────────────────────────
        elif type_doc == 'budget':
            lignes_qs = BudgetLigne.objects.filter(tenant=tenant, exercice=exercice)
            result = []
            total_prevu = total_realise = 0.0
            total_fixe_prevu = total_fixe_realise = 0.0
            total_var_prevu  = total_var_realise  = 0.0

            for l in lignes_qs:
                t_prevu = t_realise = 0.0
                for champ in MOIS_CHAMPS:
                    t_prevu += float(getattr(l, champ, 0) or 0)
                realise = float(entries.filter(
                    source__in=('CHARGE', 'PAIE', 'BUDGET'), debit__gt=0
                ).filter(
                    Q(no_compte=l.no_compte) | Q(no_compte__startswith=l.no_compte)
                ).aggregate(t=Sum('debit'))['t'] or 0)
                t_realise = realise
                pct = round(t_realise / t_prevu * 100, 1) if t_prevu else 0
                total_prevu += t_prevu; total_realise += t_realise
                if l.type_charge == 'FIXE':
                    total_fixe_prevu += t_prevu; total_fixe_realise += t_realise
                else:
                    total_var_prevu  += t_prevu; total_var_realise  += t_realise
                result.append({
                    'no_compte':        l.no_compte,
                    'libelle':          l.libelle or plan.get(l.no_compte, l.no_compte),
                    'type_charge':      l.type_charge,
                    'total_prevu':      round(t_prevu, 2),
                    'total_realise':    round(t_realise, 2),
                    'taux_realisation': pct,
                })
            ctx.update({
                'lignes': result,
                'totaux': {
                    'fixe':     {'prevu': round(total_fixe_prevu, 2), 'realise': round(total_fixe_realise, 2)},
                    'variable': {'prevu': round(total_var_prevu, 2),  'realise': round(total_var_realise, 2)},
                    'total':    {'prevu': round(total_prevu, 2),       'realise': round(total_realise, 2)},
                },
            })

        # ── INVESTISSEMENTS ────────────────────────────────────────────────────
        elif type_doc == 'investissement':
            immobils = list(Immobilisation.objects.filter(tenant=tenant, est_cede=False).order_by('no_bien'))
            lignes   = [_immo_to_dict(i) for i in immobils]
            ctx.update({
                'immobilisations': lignes,
                'synthese': {
                    'total_brut':  round(sum(i['valeur_entree']          for i in lignes), 2),
                    'total_amort': round(sum(i['cumul_amortissements']   for i in lignes), 2),
                    'total_vnc':   round(sum(i['valeur_nette_comptable'] for i in lignes), 2),
                    'nb_biens':    len(lignes),
                },
            })

        return ctx
