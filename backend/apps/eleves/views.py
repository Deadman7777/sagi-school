from rest_framework import viewsets, filters
from rest_framework.decorators import action
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

    @action(detail=False, methods=['get'], url_path='search')
    def search(self, request):
        """Recherche ultra-légère pour l'autocomplétion — pas d'annotation paiements.
        Renvoie max 15 résultats enrichis pour différencier les homonymes.
        """
        from django.db.models import Q as _Q
        q = request.query_params.get('q', '').strip()
        if len(q) < 2:
            return Response([])

        tenant   = get_tenant(request)
        exercice = Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()

        qs = Eleve.objects.filter(tenant=tenant).select_related('section').order_by('nom_complet')
        if exercice:
            qs = qs.filter(exercice=exercice)

        # Recherche multi-champs : nom, matricule, père, mère, téléphone
        qs = qs.filter(
            _Q(nom_complet__icontains=q) |
            _Q(matricule__icontains=q)   |
            _Q(nom_pere__icontains=q)    |
            _Q(telephone_pere__icontains=q)
        )[:15]

        return Response([{
            'id':                   str(e.id),
            'numero':               e.numero,
            'nom_complet':          e.nom_complet,
            'matricule':            e.matricule or '',
            'section_id':           str(e.section_id) if e.section_id else '',
            'section_nom':          e.section.nom if e.section else '',
            'date_naissance':       str(e.date_naissance) if e.date_naissance else '',
            'lieu_naissance':       e.lieu_naissance or '',
            'nom_pere':             e.nom_pere or '',
            'telephone_pere':       e.telephone_pere or '',
            'nom_mere':             e.nom_mere or '',
            'statut':               e.statut,
            'prise_en_charge':      e.prise_en_charge or '',
            'taux_prise_en_charge': float(e.taux_prise_en_charge or 0),
        } for e in qs])

    @action(detail=True, methods=['get'], url_path='saisie-paiement')
    def saisie_paiement(self, request, pk=None):
        """Données pré-calculées pour le formulaire de saisie de paiement.
        Inclut : frais de la section, prise en charge, déjà payé par catégorie, reste à payer.
        """
        from apps.paiements.models import Paiement
        from django.db.models import Sum as _Sum

        eleve    = self.get_object()
        tenant   = eleve.tenant
        exercice = Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()

        section  = eleve.section
        type_pec         = eleve.type_pec or ''
        taux_inscription = float(eleve.taux_pec_inscription or 0) / 100.0
        taux_mensualite  = float(eleve.taux_pec_mensualite  or 0) / 100.0

        # ── Frais bruts de la section ──────────────────────────────────
        fees_bruts = {
            'inscription': float(section.frais_inscription) if section else 0,
            'mensualite':  float(section.frais_mensualite)  if section else 0,
            'uniforme':    float(section.frais_uniforme)    if section else 0,
            'fournitures': float(section.frais_fournitures) if section else 0,
            'yendu':       float(section.frais_yendu)       if section else 0,
        }

        # ── Frais nets selon le type de prise en charge ────────────────
        def _appliquer_pec(nature, montant):
            if type_pec == 'TOTALE':
                if nature == 'inscription': return round(montant * (1 - taux_inscription), 2)
                if nature == 'mensualite':  return round(montant * (1 - taux_mensualite),  2)
            elif type_pec == 'INSCRIPTION' and nature == 'inscription':
                return round(montant * (1 - taux_inscription), 2)
            elif type_pec == 'MENSUALITES' and nature == 'mensualite':
                return round(montant * (1 - taux_mensualite), 2)
            return montant

        fees_nets = {k: _appliquer_pec(k, v) for k, v in fees_bruts.items()}

        # ── Déjà payé par catégorie pour cet exercice ──────────────────
        if exercice:
            pmt_qs = Paiement.objects.filter(eleve=eleve, exercice=exercice)
            agg    = pmt_qs.aggregate(
                inscription  = _Sum('montant_inscription'),
                mensualite   = _Sum('montant_mensualite'),
                uniforme     = _Sum('montant_uniforme'),
                fournitures  = _Sum('montant_fournitures'),
                cantine      = _Sum('montant_cantine'),
                divers       = _Sum('montant_divers'),
            )
            deja_paye = {k: float(v or 0) for k, v in agg.items()}
            nb_paiements = pmt_qs.count()
        else:
            deja_paye    = {k: 0.0 for k in ['inscription','mensualite','uniforme','fournitures','cantine','divers']}
            nb_paiements = 0

        # ── Reste à payer par catégorie ────────────────────────────────
        reste = {
            'inscription':  round(max(fees_nets['inscription']  - deja_paye['inscription'],  0), 2),
            'mensualite':   round(max(fees_nets['mensualite']   - deja_paye['mensualite'],   0), 2),
            'uniforme':     round(max(fees_nets['uniforme']     - deja_paye['uniforme'],     0), 2),
            'fournitures':  round(max(fees_nets['fournitures']  - deja_paye['fournitures'],  0), 2),
        }

        total_net = round(sum(fees_nets.values()), 2)
        total_paye = round(sum(deja_paye.values()), 2)

        return Response({
            'eleve_id':       str(eleve.id),
            'nom_complet':    eleve.nom_complet,
            'matricule':      eleve.matricule or '',
            'statut':         eleve.statut,
            'section_nom':    section.nom if section else '',
            # Prise en charge
            'prise_en_charge':        eleve.prise_en_charge or '',
            'type_pec':               eleve.type_pec or '',
            'taux_pec_inscription':   float(eleve.taux_pec_inscription or 0),
            'taux_pec_mensualite':    float(eleve.taux_pec_mensualite  or 0),
            'montant_pec_inscription':eleve.montant_pec_inscription,
            'montant_pec_mensuel':    eleve.montant_pec_mensualite_mensuel,
            'montant_pec_annuel':     eleve.montant_pec_annuel,
            'obs_prise_en_charge':    eleve.obs_prise_en_charge or '',
            # Montants
            'fees_bruts':    fees_bruts,
            'fees_nets':     fees_nets,
            'deja_paye':     deja_paye,
            'reste':         reste,
            # Résumé
            'total_annuel_net':  total_net,
            'total_paye':        total_paye,
            'total_restant':     round(max(total_net - total_paye, 0), 2),
            'nb_paiements':      nb_paiements,
            'exercice_id':       str(exercice.id) if exercice else '',
            'annee_scolaire':    exercice.annee_scolaire if exercice else '',
        })


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


class PriseEnChargeStatsView(APIView):
    """Statistiques et impact financier des prises en charge."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant   = get_tenant(request)
        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()

        if not exercice:
            return Response({'error': 'Aucun exercice actif'}, status=400)

        eleves_tous = Eleve.objects.filter(
            tenant=tenant, exercice=exercice, statut='INSCRIT'
        ).select_related('section')

        # ── Totaux globaux ────────────────────────────────────────────────
        total_theorique_global   = 0.0
        total_attendu_global     = 0.0
        cout_mensuel_pec_global  = 0.0
        cout_annuel_pec_global   = 0.0

        for e in eleves_tous:
            total_theorique_global  += e.total_theorique
            total_attendu_global    += float(e.total_attendu)
            cout_mensuel_pec_global += e.montant_pec_mensualite_mensuel
            cout_annuel_pec_global  += e.montant_pec_annuel

        perte_annuelle = round(total_theorique_global - total_attendu_global, 2)

        # ── Élèves sous prise en charge ───────────────────────────────────
        eleves_pec = [e for e in eleves_tous if e.type_pec]
        nb_pec     = len(eleves_pec)

        # Par type
        from collections import Counter
        compteur_type  = Counter(e.type_pec                  for e in eleves_pec if e.type_pec)
        compteur_motif = Counter(e.prise_en_charge            for e in eleves_pec if e.prise_en_charge)

        nb_par_type  = [{'type':  t, 'libelle': dict(Eleve.TYPE_PEC_CHOICES).get(t, t), 'nb': n}
                        for t, n in sorted(compteur_type.items())]
        nb_par_motif = [{'motif': m, 'libelle': dict(Eleve.PRISE_EN_CHARGE_CHOICES).get(m, m), 'nb': n}
                        for m, n in sorted(compteur_motif.items())]

        # Paiements réels des élèves en prise en charge
        from apps.paiements.models import Paiement
        from django.db.models import Sum as DSum
        ids_pec = [e.id for e in eleves_pec]
        pmt_pec = {}
        if ids_pec:
            rows = Paiement.objects.filter(
                tenant=tenant, exercice=exercice, eleve_id__in=ids_pec
            ).values('eleve_id').annotate(
                paye=DSum('montant_inscription') + DSum('montant_mensualite') +
                     DSum('montant_uniforme')    + DSum('montant_fournitures') +
                     DSum('montant_cantine')     + DSum('montant_divers')
            )
            pmt_pec = {r['eleve_id']: float(r['paye'] or 0) for r in rows}

        # ── Détail par élève ──────────────────────────────────────────────
        detail = []
        for e in sorted(eleves_pec, key=lambda x: x.nom_complet):
            paye  = pmt_pec.get(e.id, 0.0)
            reste = round(float(e.total_attendu) - paye, 2)
            detail.append({
                'eleve_id':               str(e.id),
                'nom_complet':            e.nom_complet,
                'section':                e.section.nom if e.section else '—',
                'motif':                  e.prise_en_charge or '',
                'type_pec':               e.type_pec or '',
                'taux_pec_inscription':   float(e.taux_pec_inscription or 0),
                'taux_pec_mensualite':    float(e.taux_pec_mensualite  or 0),
                'montant_pec_inscription':e.montant_pec_inscription,
                'montant_pec_mensuel':    e.montant_pec_mensualite_mensuel,
                'montant_pec_annuel':     e.montant_pec_annuel,
                'total_theorique':        e.total_theorique,
                'total_attendu':          float(e.total_attendu),
                'total_paye':             paye,
                'reste_a_payer':          reste,
                'niveau_alerte':          e.niveau_alerte,
            })

        # ── Recettes mensuelles théoriques vs réelles ─────────────────────
        nb_eleves_total = eleves_tous.count()
        mensualite_theorique_mensuelle = sum(
            float(e.section.frais_mensualite) for e in eleves_tous if e.section
        )
        mensualite_reelle_mensuelle = sum(
            e.frais_mensualite_effectif for e in eleves_tous
        )

        return Response({
            'nb_total_eleves':    nb_eleves_total,
            'nb_eleves_pec':      nb_pec,
            'nb_par_type':        nb_par_type,
            'nb_par_motif':       nb_par_motif,
            'financier': {
                'recettes_theoriques_annuelles':    round(total_theorique_global, 2),
                'recettes_reelles_attendues':        round(total_attendu_global, 2),
                'perte_annuelle_pec':                perte_annuelle,
                'cout_mensuel_pec':                  round(cout_mensuel_pec_global, 2),
                'cout_annuel_pec':                   round(cout_annuel_pec_global, 2),
                'mensualite_theorique_mensuelle':     round(mensualite_theorique_mensuelle, 2),
                'mensualite_reelle_mensuelle':        round(mensualite_reelle_mensuelle, 2),
                'ecart_mensuel':                      round(mensualite_theorique_mensuelle - mensualite_reelle_mensuelle, 2),
            },
            'detail': detail,
        })


class CertificatScolariteView(APIView):
    """Génère le certificat de scolarité PDF d'un élève."""
    permission_classes = [IsAuthenticated]

    def get(self, request, eleve_id):
        from io import BytesIO
        from django.http import HttpResponse
        from django.template.loader import render_to_string
        from django.utils import timezone
        try:
            from xhtml2pdf import pisa
        except ImportError:
            return HttpResponse('xhtml2pdf non installé', status=500)

        tenant = get_tenant(request)
        try:
            eleve = Eleve.objects.get(id=eleve_id, tenant=tenant)
        except Eleve.DoesNotExist:
            return HttpResponse('Élève introuvable', status=404)

        from apps.paiements.models import Exercice
        exercice = Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()

        context = {
            'tenant':          tenant,
            'eleve':           eleve,
            'section_nom':     eleve.section.nom if eleve.section else '—',
            'annee_scolaire':  exercice.annee_scolaire if exercice else '—',
            'date_edition':    timezone.now(),
            'directeur_nom':   getattr(tenant, 'directeur_nom', '') or '',
            'tenant_ville':    getattr(tenant, 'ville', '') or '',
            'tenant_rccm':     getattr(tenant, 'rccm', '') or '',
            'tenant_telephone':getattr(tenant, 'telephone', '') or '',
        }

        html_str = render_to_string('pdf/certificat_scolarite.html', context)
        buf      = BytesIO()
        result   = pisa.CreatePDF(html_str, dest=buf, encoding='utf-8')
        if result.err:
            return HttpResponse('Erreur génération certificat.', status=500)

        response = HttpResponse(buf.getvalue(), content_type='application/pdf')
        safe_name = eleve.nom_complet.replace(' ', '_').replace('/', '-')
        response['Content-Disposition'] = f'inline; filename="certificat_{safe_name}.pdf"'
        return response
