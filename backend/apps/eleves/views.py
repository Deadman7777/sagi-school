from rest_framework import viewsets, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, Value, DecimalField
from django.db.models.functions import Coalesce, TruncMonth
from core.permissions import IsTenantMember
from .models import Eleve, Section
from apps.paiements.models import Exercice
from .serializers import EleveSerializer, SectionSerializer
from django.db.models import Max
from django.utils import timezone


def get_tenant(request):
    if request.tenant:
        return request.tenant
    if hasattr(request.user, 'tenant') and request.user.tenant:
        return request.user.tenant
    if request.user.role == 'SUPER_ADMIN':
        from apps.tenants.models import Tenant
        return Tenant.objects.first()
    return None


class SectionViewSet(viewsets.ModelViewSet):
    serializer_class   = SectionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Section.objects.filter(tenant=get_tenant(self.request))

    def perform_create(self, serializer):
        serializer.save(tenant=get_tenant(self.request))


class EleveViewSet(viewsets.ModelViewSet):
    serializer_class   = EleveSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ['nom_complet', 'telephone_pere', 'telephone_mere']
    ordering_fields    = ['nom_complet', 'date_inscription', 'numero']

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return Eleve.objects.none()

        qs = Eleve.objects.filter(tenant=tenant).select_related(
            'section'
        ).prefetch_related('paiements').annotate(
            total_paye_sql=Coalesce(
                Sum('paiements__montant_inscription') +
                Sum('paiements__montant_mensualite')  +
                Sum('paiements__montant_uniforme')    +
                Sum('paiements__montant_fournitures') +
                Sum('paiements__montant_cantine')     +
                Sum('paiements__montant_divers'),
                Value(0), output_field=DecimalField()
            )
        )

        if section := self.request.query_params.get('section'):
            qs = qs.filter(section__nom=section)
        if exercice := self.request.query_params.get('exercice'):
            qs = qs.filter(exercice_id=exercice)
        if statut := self.request.query_params.get('statut'):
            qs = qs.filter(statut=statut)
        if pec := self.request.query_params.get('prise_en_charge'):
            qs = qs.filter(prise_en_charge=pec)

        return qs.order_by('numero')

    def perform_create(self, serializer):

        tenant = get_tenant(self.request)
        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()

        if not exercice:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Aucun exercice actif trouvé.")

        # ID interne séquentiel
        max_num = Eleve.objects.filter(tenant=tenant).aggregate(
            m=Max('numero')
        )['m'] or 0
        numero = max_num + 1

        # Matricule visible : AAAA-ETB-NNNNNN
        annee    = str(timezone.now().year)
        code_etb = (tenant.code_etablissement or 'ETB').upper()
        matricule = f"{annee}-{code_etb}-{str(numero).zfill(6)}"

        serializer.save(tenant=tenant, exercice=exercice, numero=numero, matricule=matricule)


MOIS_FR = {
    1:'Janvier', 2:'Février', 3:'Mars',    4:'Avril',
    5:'Mai',     6:'Juin',    7:'Juillet', 8:'Août',
    9:'Septembre',10:'Octobre',11:'Novembre',12:'Décembre',
}
MOIS_COURT_FR = {
    1:'Jan', 2:'Fév', 3:'Mar', 4:'Avr', 5:'Mai', 6:'Jun',
    7:'Jul', 8:'Aoû', 9:'Sep',10:'Oct',11:'Nov',12:'Déc',
}


class SuiviMensuelView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        import datetime
        from dateutil.relativedelta import relativedelta
        from django.db.models import Sum as DSum
        from apps.paiements.models import Exercice, Paiement

        tenant   = get_tenant(request)
        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()

        if not exercice:
            return Response({
                'global': [], 'sections': [], 'synthese': {},
                'creances': [], 'eleve': None,
            })

        eleve_id = request.query_params.get('eleve_id')

        # ── 1. Paiements mensuels agrégés ───────────────────────────────────
        mensuel_qs = Paiement.objects.filter(
            tenant=tenant, exercice=exercice
        ).annotate(mois_tronc=TruncMonth('date_paiement')).values('mois_tronc').annotate(
            total       = Sum('montant_inscription') + Sum('montant_mensualite') +
                          Sum('montant_uniforme')    + Sum('montant_fournitures') +
                          Sum('montant_cantine')     + Sum('montant_divers'),
            nb          = Count('id'),
            inscription = Sum('montant_inscription'),
            mensualite  = Sum('montant_mensualite'),
            uniforme    = Sum('montant_uniforme'),
            fournitures = Sum('montant_fournitures'),
            cantine     = Sum('montant_cantine'),
        ).order_by('mois_tronc')

        # Index par (annee, mois)
        pmt_par_mois = {}
        for m in mensuel_qs:
            if m['mois_tronc']:
                key = (m['mois_tronc'].year, m['mois_tronc'].month)
                pmt_par_mois[key] = m

        # Générer TOUS les mois de l'exercice (même à 0)
        debut = exercice.date_debut.replace(day=1)
        fin   = exercice.date_fin.replace(day=1)
        global_data = []
        cur = debut
        while cur <= fin:
            key = (cur.year, cur.month)
            m   = pmt_par_mois.get(key, {})
            global_data.append({
                'mois':        f"{MOIS_FR[cur.month]} {cur.year}",
                'mois_court':  MOIS_COURT_FR[cur.month],
                'mois_num':    cur.month,
                'annee':       cur.year,
                'total':       float(m.get('total')       or 0),
                'nb':          m.get('nb', 0),
                'inscription': float(m.get('inscription') or 0),
                'mensualite':  float(m.get('mensualite')  or 0),
                'uniforme':    float(m.get('uniforme')    or 0),
                'fournitures': float(m.get('fournitures') or 0),
                'cantine':     float(m.get('cantine')     or 0),
            })
            cur += relativedelta(months=1)

        # ── 2. Synthèse globale ──────────────────────────────────────────────
        eleves_qs = Eleve.objects.filter(
            tenant=tenant, exercice=exercice, statut='INSCRIT'
        ).select_related('section')

        total_attendu  = sum(float(e.total_attendu) for e in eleves_qs)
        total_paiements = sum(float(m.get('total') or 0) for m in pmt_par_mois.values())
        reste_global   = total_attendu - total_paiements
        taux_global    = round(total_paiements / total_attendu * 100, 1) if total_attendu else 0

        synthese = {
            'nb_eleves':         eleves_qs.count(),
            'total_attendu':     round(total_attendu, 2),
            'total_paye':        round(total_paiements, 2),
            'reste':             round(reste_global, 2),
            'taux_recouvrement': taux_global,
            'exercice':          exercice.annee_scolaire,
        }

        # ── 3. Par section ──────────────────────────────────────────────────
        sections_dict = {}
        for e in eleves_qs:
            snom = e.section.nom if e.section else '—'
            if snom not in sections_dict:
                sections_dict[snom] = {'nb': 0, 'attendu': 0.0}
            sections_dict[snom]['nb']      += 1
            sections_dict[snom]['attendu'] += float(e.total_attendu)

        # Paiements par section
        pmt_section = Paiement.objects.filter(
            tenant=tenant, exercice=exercice
        ).values('eleve__section__nom').annotate(
            paye=Sum('montant_inscription') + Sum('montant_mensualite') +
                 Sum('montant_uniforme')    + Sum('montant_fournitures') +
                 Sum('montant_cantine')     + Sum('montant_divers')
        )
        paye_par_section = {r['eleve__section__nom']: float(r['paye'] or 0) for r in pmt_section}

        sections_data = []
        for snom, info in sorted(sections_dict.items()):
            paye = paye_par_section.get(snom, 0.0)
            att  = info['attendu']
            sections_data.append({
                'nom':           snom,
                'nb_eleves':     info['nb'],
                'total_attendu': round(att, 2),
                'total_paye':    round(paye, 2),
                'reste':         round(att - paye, 2),
                'taux':          round(paye / att * 100, 1) if att else 0,
            })

        # ── 4. Top débiteurs ────────────────────────────────────────────────
        # Paiements par élève
        pmt_eleve = {
            r['eleve_id']: float(r['paye'] or 0)
            for r in Paiement.objects.filter(
                tenant=tenant, exercice=exercice
            ).values('eleve_id').annotate(
                paye=Sum('montant_inscription') + Sum('montant_mensualite') +
                     Sum('montant_uniforme')    + Sum('montant_fournitures') +
                     Sum('montant_cantine')     + Sum('montant_divers')
            )
        }

        creances = []
        for e in eleves_qs:
            att  = float(e.total_attendu)
            paye = pmt_eleve.get(e.id, 0.0)
            reste = att - paye
            if reste > 0:
                creances.append({
                    'id':      str(e.id),
                    'nom':     e.nom_complet,
                    'section': e.section.nom if e.section else '—',
                    'attendu': round(att, 2),
                    'paye':    round(paye, 2),
                    'reste':   round(reste, 2),
                    'taux':    round(paye / att * 100, 1) if att else 0,
                })
        creances.sort(key=lambda x: x['reste'], reverse=True)

        # ── 5. Détail élève ────────────────────────────────────────────────
        eleve_data = None
        if eleve_id:
            try:
                eleve = Eleve.objects.get(id=eleve_id, tenant=tenant)
                paiements_eleve = Paiement.objects.filter(
                    tenant=tenant, exercice=exercice, eleve=eleve
                ).order_by('date_paiement')

                items = []
                cumul = 0.0
                for p in paiements_eleve:
                    t = float(p.total)
                    cumul += t
                    items.append({
                        'no_piece':    p.no_piece,
                        'date':        str(p.date_paiement),
                        'inscription': float(p.montant_inscription),
                        'mensualite':  float(p.montant_mensualite),
                        'uniforme':    float(p.montant_uniforme),
                        'fournitures': float(p.montant_fournitures),
                        'cantine':     float(p.montant_cantine),
                        'divers':      float(p.montant_divers),
                        'total':       t,
                        'cumul':       round(cumul, 2),
                        'mode':        p.mode_paiement,
                    })

                attendu = float(eleve.total_attendu)
                eleve_data = {
                    'id':         str(eleve.id),
                    'nom':        eleve.nom_complet,
                    'section':    eleve.section.nom if eleve.section else '',
                    'attendu':    attendu,
                    'total_paye': round(cumul, 2),
                    'reste':      round(attendu - cumul, 2),
                    'taux':       round(cumul / attendu * 100, 1) if attendu else 0,
                    'paiements':  items,
                }
            except Eleve.DoesNotExist:
                pass

        return Response({
            'global':   global_data,
            'synthese': synthese,
            'sections': sections_data,
            'creances': creances[:20],
            'eleve':    eleve_data,
        })
