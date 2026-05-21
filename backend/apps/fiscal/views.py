from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum
import datetime


MOIS_FR = {
    1:'Janvier', 2:'Février', 3:'Mars',    4:'Avril',
    5:'Mai',     6:'Juin',    7:'Juillet', 8:'Août',
    9:'Septembre',10:'Octobre',11:'Novembre',12:'Décembre',
}


def get_tenant(request):
    if request.tenant:
        return request.tenant
    if request.user.role == 'SUPER_ADMIN':
        from apps.tenants.models import Tenant
        return Tenant.objects.first()
    return None


# ── Taux fiscaux Sénégal (Convention Collective Enseignement Privé 2018) ──────
# Références : Code Général des Impôts (CGI) + IPRES + CSS + CFCE
TAUX = {
    # IPRES (Institut de Prévoyance Retraite du Sénégal)
    'ipres_gen_salarie':   0.056,   # 5.6% salarial   (régime général, plafonné)
    'ipres_gen_patronal':  0.084,   # 8.4% patronal
    'ipres_cadre_salarie': 0.024,   # 2.4% salarial   (régime cadre)
    'ipres_cadre_patronal':0.036,   # 3.6% patronal

    # CSS - Caisse de Sécurité Sociale
    'css_prestations_fam': 0.07,    # 7% patronal uniquement
    'atmp':                0.01,    # 1% patronal - Accidents du Travail (éducation)

    # CFCE (Contribution Forfaitaire à la Charge de l'Employeur)
    'cfce':                0.03,    # 3% du brut imposable (Art. 188 CGI)

    # BRS (Bordereau de Règlement des Salaires)
    'brs':                 0.05,    # 5% masse salariale brute
}

# Plafond IPRES Général mensuel (2024)
PLAFOND_IPRES_GEN  = 1_578_000  # FCFA/mois
PLAFOND_IPRES_CADRE = 3_948_000  # FCFA/mois (tranche entre plafond gén. et ce plafond)


def _calculer_ir_senegal(salaire_net_mensuel):
    """Barème progressif IR mensuel — Art. 173 CGI Sénégal (tranches annuelles / 12)."""
    # Tranches annuelles → mensualiser
    annuel = salaire_net_mensuel * 12
    if annuel <= 630_000:
        ir = 0
    elif annuel <= 1_500_000:
        ir = (annuel - 630_000) * 0.20
    elif annuel <= 4_000_000:
        ir = 174_000 + (annuel - 1_500_000) * 0.30
    elif annuel <= 8_000_000:
        ir = 924_000 + (annuel - 4_000_000) * 0.35
    elif annuel <= 13_500_000:
        ir = 2_324_000 + (annuel - 8_000_000) * 0.37
    else:
        ir = 4_359_000 + (annuel - 13_500_000) * 0.40
    return round(ir / 12, 2)


class DeclarationsFiscalesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.paiements.models import Exercice
        from apps.comptabilite.models import JournalEntry

        tenant   = get_tenant(request)
        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()

        if not exercice:
            return Response({'declarations': [], 'synthese': {}, 'taux': TAUX})

        # ── Données réelles depuis les bulletins de paie (module RH) ──────────
        try:
            from apps.rh.models import BulletinPaie
            bulletins_qs = BulletinPaie.objects.filter(
                tenant=tenant, statut__in=('VALIDE', 'PAYE')
            ).order_by('annee', 'mois')
            use_bulletins = bulletins_qs.exists()
        except Exception:
            use_bulletins = False

        # Fallback : journal entries source='PAIE' sur compte 661
        if not use_bulletins:
            sal_entries = JournalEntry.objects.filter(
                tenant=tenant, exercice=exercice,
                no_compte='661', source='PAIE', debit__gt=0
            )

        declarations = []
        debut = exercice.date_debut
        fin   = exercice.date_fin
        today = datetime.date.today()
        mois_actuel = datetime.date(debut.year, debut.month, 1)

        total_masse = total_brs = total_ipres_s = total_ipres_p = 0.0
        total_css = total_cfce = total_ir = total_impots = 0.0

        while mois_actuel <= fin and mois_actuel <= today:
            mois_num = mois_actuel.month
            annee    = mois_actuel.year

            if use_bulletins:
                # Données réelles depuis BulletinPaie
                buls = bulletins_qs.filter(mois=mois_num, annee=annee)
                masse          = float(buls.aggregate(t=Sum('salaire_brut'))['t'] or 0)
                ipres_s        = float(buls.aggregate(t=Sum('ipres_general_salarie') +
                                                         Sum('ipres_cadre_salarie'))['t'] or 0)
                ipres_p        = float(buls.aggregate(t=Sum('ipres_general_patronal') +
                                                         Sum('ipres_cadre_patronal'))['t'] or 0)
                css_atmp       = float(buls.aggregate(t=Sum('css_prestations_familiales') +
                                                         Sum('atmp'))['t'] or 0)
                cfce_val       = float(buls.aggregate(t=Sum('cfce'))['t'] or 0)
                ir_val         = float(buls.aggregate(t=Sum('ir_retenu'))['t'] or 0)
            else:
                # Estimation depuis journal
                masse  = float(sal_entries.filter(
                    date_ecriture__year=annee, date_ecriture__month=mois_num
                ).aggregate(t=Sum('debit'))['t'] or 0)
                if masse == 0:
                    # Fallback: répartition uniforme du total annuel
                    total_an = float(sal_entries.aggregate(t=Sum('debit'))['t'] or 0)
                    masse    = round(total_an / 10, 2)  # 10 mois scolaires

                # Estimation si pas de bulletins
                masse_plaf = min(masse, PLAFOND_IPRES_GEN)
                ipres_s    = round(masse_plaf * TAUX['ipres_gen_salarie'],  2)
                ipres_p    = round(masse_plaf * TAUX['ipres_gen_patronal'], 2)
                css_atmp   = round(masse * (TAUX['css_prestations_fam'] + TAUX['atmp']), 2)
                cfce_val   = round(masse * TAUX['cfce'], 2)
                net_est    = masse - ipres_s
                ir_val     = _calculer_ir_senegal(net_est) if masse > 0 else 0

            brs_val     = round(masse * TAUX['brs'], 2)
            total_impots_mois = round(brs_val + ipres_s + ipres_p + css_atmp + ir_val + cfce_val, 2)

            # Accumulation
            total_masse   += masse
            total_brs     += brs_val
            total_ipres_s += ipres_s
            total_ipres_p += ipres_p
            total_css     += css_atmp
            total_cfce    += cfce_val
            total_ir      += ir_val
            total_impots  += total_impots_mois

            # Date limite dépôt : 15 du mois M+1
            if mois_actuel.month == 12:
                limite = datetime.date(annee + 1, 1, 15)
            else:
                limite = datetime.date(annee, mois_actuel.month + 1, 15)

            if limite > today:
                statut = 'A_VENIR'
            elif masse == 0:
                statut = 'EN_RETARD'
            else:
                statut = 'EN_REGLE'

            declarations.append({
                'mois':            f"{MOIS_FR[mois_num]} {annee}",
                'mois_num':        mois_num,
                'annee':           annee,
                'masse_salariale': round(masse,      2),
                'brs':             brs_val,
                'ipres_salarie':   round(ipres_s,    2),
                'ipres_patronal':  round(ipres_p,    2),
                'css_atmp':        round(css_atmp,   2),
                'ir':              round(ir_val,     2),
                'cfce':            round(cfce_val,   2),
                'montant_brs':     brs_val,
                'total_impots':    total_impots_mois,
                'date_limite':     str(limite),
                'statut':          statut,
                'source':          'BULLETINS' if use_bulletins else 'ESTIMATION',
            })

            if mois_actuel.month == 12:
                mois_actuel = datetime.date(mois_actuel.year + 1, 1, 1)
            else:
                mois_actuel = datetime.date(mois_actuel.year, mois_actuel.month + 1, 1)

        synthese = {
            'masse_salariale':   round(total_masse,   2),
            'brs_total':         round(total_brs,     2),
            'ipres_salarie':     round(total_ipres_s, 2),
            'ipres_patronal':    round(total_ipres_p, 2),
            'css_atmp_total':    round(total_css,     2),
            'ir_total':          round(total_ir,      2),
            'cfce_total':        round(total_cfce,    2),
            'total_impots':      round(total_impots,  2),
            'brs_retard':        round(sum(d['total_impots'] for d in declarations if d['statut'] == 'EN_RETARD'), 2),
            'brs_regle':         round(sum(d['total_impots'] for d in declarations if d['statut'] == 'EN_REGLE'),  2),
            'source':            'BULLETINS' if use_bulletins else 'ESTIMATION',
        }

        return Response({
            'declarations': declarations,
            'synthese':     synthese,
            'taux':         TAUX,
            'exercice':     exercice.annee_scolaire,
        })
