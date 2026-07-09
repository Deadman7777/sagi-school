from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, Value, DecimalField
from django.db.models.functions import Coalesce, TruncMonth
from apps.comptabilite.models import JournalEntry
from core.permissions import IsTenantMember
from core.tenant import get_tenant
from .models import Eleve, Section, Service
from apps.paiements.models import Exercice
from .serializers import EleveSerializer, SectionSerializer, ServiceSerializer
from django.db.models import Max
from django.utils import timezone


class SectionViewSet(viewsets.ModelViewSet):
    serializer_class   = SectionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Section.objects.filter(tenant=get_tenant(self.request))

    def perform_create(self, serializer):
        serializer.save(tenant=get_tenant(self.request))


class ServiceViewSet(viewsets.ModelViewSet):
    serializer_class   = ServiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Service.objects.filter(tenant=get_tenant(self.request))

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
            'section', 'exercice'
        ).prefetch_related('paiements', 'abonnements__service').annotate(
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

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        """Template Excel d'import, avec les sections de l'école en consigne."""
        from django.http import HttpResponse
        from .import_eleves import generer_template
        tenant = get_tenant(request)
        try:
            buf = generer_template(tenant)
        except ImportError as e:
            return Response({'error': str(e)}, status=400)
        resp = HttpResponse(
            buf.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        resp['Content-Disposition'] = 'attachment; filename="import_eleves_sagi.xlsx"'
        return resp

    @action(detail=False, methods=['post'], url_path='import-excel')
    def import_excel(self, request):
        """Import d'élèves depuis un .xlsx.

        Sans confirmer=1 : analyse seule, rend le rapport ligne par ligne.
        Avec confirmer=1 : re-analyse puis crée les lignes OK en transaction
        (les DOUBLON sont ignorés — l'import est rejouable sans doublonner).
        """
        from django.db import transaction
        from core.models import log_audit
        from .import_eleves import analyser

        tenant = get_tenant(request)
        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()
        if not exercice:
            return Response({'error': 'Aucun exercice actif trouvé.'}, status=400)

        fichier = request.FILES.get('fichier')
        if not fichier:
            return Response({'error': 'Aucun fichier reçu.'}, status=400)

        try:
            rapport = analyser(fichier, tenant, exercice)
        except (ImportError, ValueError) as e:
            return Response({'error': str(e)}, status=400)

        if request.data.get('confirmer') != '1':
            return Response(rapport)

        from apps.paiements.reprise import creer_paiement_reprise
        a_creer  = [l for l in rapport['lignes'] if l['statut'] == 'OK']
        annee    = str(timezone.now().year)
        code_etb = (tenant.code_etablissement or 'ETB').upper()
        reprises, montant_reprise = 0, 0.0
        with transaction.atomic():
            numero = Eleve.objects.filter(tenant=tenant).aggregate(m=Max('numero'))['m'] or 0
            for ligne in a_creer:
                data = ligne['data']
                numero += 1
                eleve = Eleve.objects.create(
                    tenant=tenant, exercice=exercice, numero=numero,
                    matricule=data.pop('matricule') or f"{annee}-{code_etb}-{str(numero).zfill(6)}",
                    **data,
                )
                if ligne['montant_reprise'] > 0:
                    paiement = creer_paiement_reprise(
                        tenant, exercice, eleve, user=request.user, **ligne['reprise'],
                    )
                    if paiement:
                        reprises += 1
                        montant_reprise += float(paiement.total)
        log_audit(request, 'IMPORT', 'Eleve',
                  description=f"Import Excel : {len(a_creer)} élèves créés, "
                              f"{reprises} reprises de soldes ({montant_reprise:,.0f} FCFA), "
                              f"{rapport['resume']['doublons']} doublons ignorés, "
                              f"{rapport['resume']['erreurs']} lignes en erreur")
        return Response({'resume': rapport['resume'], 'crees': len(a_creer),
                         'reprises': reprises, 'montant_reprise': montant_reprise})

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

        qs = Eleve.objects.filter(tenant=tenant).select_related('section', 'exercice').order_by('nom_complet')
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

        # Vrai total annuel dû = mensualité × mensualités dues − prise en charge
        # (source de vérité partagée avec liste élèves / dashboard / reçus)
        total_annuel = round(float(eleve.total_attendu), 2)
        total_paye = round(sum(deja_paye.values()), 2)

        # ── Services optionnels auxquels l'élève est abonné ─────────────────
        services_abonnes = [
            {
                'id':          str(ab.service_id),
                'nom':         ab.service.nom,
                'montant':     float(ab.service.montant),
                'periodicite': ab.service.periodicite,
            }
            for ab in eleve.abonnements.all() if ab.service.actif
        ]

        # ── Mois de l'année scolaire : dus (prorata entrée) + déjà réglés ────
        nb_dus     = eleve.nb_mensualites_dues
        mois_payes = set()
        if exercice:
            for p in pmt_qs.filter(statut='ACTIF'):
                for mr in (p.mois_regles or []):
                    mois_payes.add(int(mr))
        mois_ecole = []
        if exercice:
            nb_total = exercice.nb_mensualites
            y, mo = exercice.date_debut.year, exercice.date_debut.month
            for i in range(nb_total):
                mois_ecole.append({
                    'num':   mo,
                    'annee': y,
                    'label': MOIS_FR.get(mo, str(mo)),
                    'du':    i >= (nb_total - nb_dus),   # les mois avant l'entrée ne sont pas dus
                    'paye':  mo in mois_payes,
                })
                mo += 1
                if mo > 12:
                    mo = 1
                    y += 1

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
            'total_annuel_net':  total_annuel,
            'total_paye':        total_paye,
            'total_restant':     round(max(total_annuel - total_paye, 0), 2),
            'nb_paiements':      nb_paiements,
            'nb_mensualites_dues': nb_dus,
            'mois_ecole':        mois_ecole,
            'services':          services_abonnes,
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

        # ── Raccourci rapide : détail individuel seulement ───────────────────
        if eleve_id:
            try:
                eleve = Eleve.objects.select_related('section', 'exercice').get(
                    id=eleve_id, tenant=tenant
                )
            except (Eleve.DoesNotExist, Exception):
                return Response({'eleve': None})

            paiements_eleve = Paiement.objects.filter(
                tenant=tenant, exercice=exercice, eleve=eleve
            ).order_by('date_paiement').only(
                'no_piece', 'date_paiement', 'mode_paiement',
                'montant_inscription', 'montant_mensualite', 'montant_uniforme',
                'montant_fournitures', 'montant_cantine', 'montant_divers',
            )

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
            return Response({
                'eleve': {
                    'id':         str(eleve.id),
                    'nom':        eleve.nom_complet,
                    'section':    eleve.section.nom if eleve.section else '',
                    'attendu':    attendu,
                    'total_paye': round(cumul, 2),
                    'reste':      round(attendu - cumul, 2),
                    'taux':       round(cumul / attendu * 100, 1) if attendu else 0,
                    'paiements':  items,
                }
            })

        # ── 1. Paiements ventilés par mois (un seul passage) ─────────────────
        #  - inscription / uniforme / fournitures / cantine / divers manuel → par date de paiement
        #  - mensualité + services → par mois concerné (mois_regles), sinon par date de paiement
        from collections import defaultdict
        debut_year, debut_month = exercice.date_debut.year, exercice.date_debut.month
        def _annee_du_mois(num):
            return debut_year if num >= debut_month else debut_year + 1

        def _cell():
            return {'nb': 0, 'inscription': 0.0, 'uniforme': 0.0, 'fournitures': 0.0,
                    'cantine': 0.0, 'mensualite': 0.0, 'services': 0.0, 'divers': 0.0}
        par_mois = defaultdict(_cell)

        for p in Paiement.objects.filter(tenant=tenant, exercice=exercice, statut='ACTIF').only(
                'date_paiement', 'montant_inscription', 'montant_mensualite',
                'montant_uniforme', 'montant_fournitures', 'montant_cantine',
                'montant_divers', 'mois_regles', 'services_regles'):
            d  = p.date_paiement
            dk = (d.year, d.month)
            cell = par_mois[dk]
            cell['inscription'] += float(p.montant_inscription or 0)
            cell['uniforme']    += float(p.montant_uniforme    or 0)
            cell['fournitures'] += float(p.montant_fournitures or 0)
            cell['cantine']     += float(p.montant_cantine     or 0)
            # services itemisés (inclus dans montant_divers) + divers manuel résiduel
            svc           = sum(float(s.get('montant') or 0) for s in (p.services_regles or []))
            divers_manuel = max(0.0, float(p.montant_divers or 0) - svc)
            cell['divers'] += divers_manuel
            # mensualité + services ventilés par mois concerné (anticipation)
            mm   = float(p.montant_mensualite or 0)
            mois = [int(x) for x in (p.mois_regles or [])]
            if mois:
                n = len(mois)
                for num in mois:
                    c = par_mois[(_annee_du_mois(num), num)]
                    c['mensualite'] += mm  / n
                    c['services']   += svc / n
            else:
                cell['mensualite'] += mm
                cell['services']   += svc

            # Compteur de paiements : sur chaque mois où le paiement laisse une trace
            # (mois de saisie + mois réglés par anticipation), pas seulement le mois de
            # la date de paiement — sinon les mensualités ventilées affichent nb = 0.
            mois_touches = {dk}
            for num in mois:
                mois_touches.add((_annee_du_mois(num), num))
            for key in mois_touches:
                par_mois[key]['nb'] += 1

        # ── Charges mensuelles (débits 6xx depuis journal) ───────────────────
        charges_qs = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice,
            no_compte__startswith='6', debit__gt=0
        ).annotate(mois_tronc=TruncMonth('date_ecriture')).values('mois_tronc').annotate(
            total=Sum('debit')
        ).order_by('mois_tronc')
        charges_par_mois = {
            (c['mois_tronc'].year, c['mois_tronc'].month): float(c['total'] or 0)
            for c in charges_qs if c['mois_tronc']
        }

        # ── Investissements mensuels (débits 2xx, source INVEST) ─────────────
        invest_qs = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice,
            source='INVEST', no_compte__startswith='2', debit__gt=0
        ).annotate(mois_tronc=TruncMonth('date_ecriture')).values('mois_tronc').annotate(
            total=Sum('debit')
        ).order_by('mois_tronc')
        invest_par_mois = {
            (i['mois_tronc'].year, i['mois_tronc'].month): float(i['total'] or 0)
            for i in invest_qs if i['mois_tronc']
        }

        # Générer TOUS les mois de l'exercice (même à 0)
        debut = exercice.date_debut.replace(day=1)
        fin   = exercice.date_fin.replace(day=1)
        global_data = []
        cur = debut
        while cur <= fin:
            key = (cur.year, cur.month)
            m   = par_mois.get(key, {})
            inscription = round(float(m.get('inscription') or 0), 2)
            mens        = round(float(m.get('mensualite')  or 0), 2)
            services    = round(float(m.get('services')    or 0), 2)
            uniforme    = round(float(m.get('uniforme')    or 0), 2)
            fournitures = round(float(m.get('fournitures') or 0), 2)
            cantine     = round(float(m.get('cantine')     or 0), 2)
            divers      = round(float(m.get('divers')      or 0), 2)
            enc = round(inscription + mens + services + uniforme + fournitures + cantine + divers, 2)
            charges       = round(charges_par_mois.get(key, 0.0), 2)
            investissements = round(invest_par_mois.get(key, 0.0), 2)
            decaissements = round(charges + investissements, 2)
            global_data.append({
                'mois':            f"{MOIS_FR[cur.month]} {cur.year}",
                'mois_court':      MOIS_COURT_FR[cur.month],
                'mois_num':        cur.month,
                'annee':           cur.year,
                'total':           enc,
                'nb':              m.get('nb', 0),
                'inscription':     inscription,
                'mensualite':      mens,
                'services':        services,
                'uniforme':        uniforme,
                'fournitures':     fournitures,
                'cantine':         cantine,
                'divers':          divers,
                'charges':         charges,
                'investissements': investissements,
                'decaissements':   decaissements,
                'marge':           round(enc - decaissements, 2),
            })
            cur += relativedelta(months=1)

        # ── 2. Synthèse + sections + créances (itération unique sur les élèves) ─
        # Charger toutes les sections en une seule requête pour éviter les N+1
        eleves_qs = Eleve.objects.filter(
            tenant=tenant, exercice=exercice, statut='INSCRIT'
        ).select_related('section', 'exercice').prefetch_related('abonnements__service')

        # Paiements par élève et par section en 2 requêtes DB au lieu de boucles Python
        _pmt_sum = (
            Sum('montant_inscription') + Sum('montant_mensualite') +
            Sum('montant_uniforme')    + Sum('montant_fournitures') +
            Sum('montant_cantine')     + Sum('montant_divers')
        )
        pmt_eleve = {
            r['eleve_id']: float(r['paye'] or 0)
            for r in Paiement.objects.filter(
                tenant=tenant, exercice=exercice, statut='ACTIF'
            ).values('eleve_id').annotate(paye=_pmt_sum)
        }
        pmt_section_raw = {
            r['eleve__section__nom']: float(r['paye'] or 0)
            for r in Paiement.objects.filter(
                tenant=tenant, exercice=exercice, statut='ACTIF'
            ).values('eleve__section__nom').annotate(paye=_pmt_sum)
        }

        # Itération unique sur les élèves pour synthèse + sections + créances
        total_attendu = 0.0
        nb_eleves     = 0
        sections_dict: dict = {}
        creances      = []

        for e in eleves_qs:
            att  = float(e.total_attendu)
            paye = pmt_eleve.get(e.id, 0.0)
            snom = e.section.nom if e.section else '—'

            total_attendu += att
            nb_eleves     += 1

            if snom not in sections_dict:
                sections_dict[snom] = {'nb': 0, 'attendu': 0.0}
            sections_dict[snom]['nb']      += 1
            sections_dict[snom]['attendu'] += att

            reste = att - paye
            if reste > 0:
                creances.append({
                    'id':      str(e.id),
                    'nom':     e.nom_complet,
                    'section': snom,
                    'attendu': round(att, 2),
                    'paye':    round(paye, 2),
                    'reste':   round(reste, 2),
                    'taux':    round(paye / att * 100, 1) if att else 0,
                })

        creances.sort(key=lambda x: x['reste'], reverse=True)

        # Total réellement encaissé = somme de tous les paiements de l'exercice
        total_paiements = sum(pmt_eleve.values())
        reste_global    = total_attendu - total_paiements
        taux_global     = round(total_paiements / total_attendu * 100, 1) if total_attendu else 0
        total_charges   = sum(charges_par_mois.values())
        total_invest    = sum(invest_par_mois.values())

        synthese = {
            'nb_eleves':              nb_eleves,
            'total_attendu':          round(total_attendu, 2),
            'total_paye':             round(total_paiements, 2),
            'reste':                  round(reste_global, 2),
            'taux_recouvrement':      taux_global,
            'exercice':               exercice.annee_scolaire,
            'total_charges':          round(total_charges, 2),
            'total_investissements':  round(total_invest, 2),
            'marge_globale':          round(total_paiements - total_charges - total_invest, 2),
        }

        sections_data = []
        for snom, info in sorted(sections_dict.items()):
            paye = pmt_section_raw.get(snom, 0.0)
            att  = info['attendu']
            sections_data.append({
                'nom':           snom,
                'nb_eleves':     info['nb'],
                'total_attendu': round(att, 2),
                'total_paye':    round(paye, 2),
                'reste':         round(att - paye, 2),
                'taux':          round(paye / att * 100, 1) if att else 0,
            })

        return Response({
            'global':   global_data,
            'synthese': synthese,
            'sections': sections_data,
            'creances': creances[:20],
            'eleve':    None,
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
        ).select_related('section', 'exercice').prefetch_related('abonnements__service')

        # ── Totaux globaux ────────────────────────────────────────────────
        total_theorique_global       = 0.0
        total_attendu_global         = 0.0   # avec services (recettes réelles attendues)
        total_attendu_frais_global   = 0.0   # frais scolaires seuls, après PEC (sans services)
        cout_mensuel_pec_global      = 0.0
        cout_annuel_pec_global       = 0.0

        for e in eleves_tous:
            th  = e.total_theorique
            pec = e.montant_pec_annuel
            total_theorique_global      += th
            total_attendu_global        += float(e.total_attendu)
            total_attendu_frais_global  += max(th - pec, 0.0)
            cout_mensuel_pec_global     += e.montant_pec_mensualite_mensuel
            cout_annuel_pec_global      += pec

        # La perte annuelle = écart entre le théorique et l'attendu sur le même
        # périmètre (frais scolaires). Les services optionnels (cantine, etc.) sont
        # des recettes en plus, hors PEC : ils ne doivent pas réduire la perte.
        perte_annuelle = round(total_theorique_global - total_attendu_frais_global, 2)

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


class ElevesListePDFView(APIView):
    """Génère la liste PDF des élèves avec montants payés, restes et alertes."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from io import BytesIO
        from django.http import HttpResponse
        from django.template.loader import render_to_string
        from django.utils import timezone
        try:
            from xhtml2pdf import pisa
        except ImportError:
            return HttpResponse('xhtml2pdf non installé', status=500)

        tenant   = get_tenant(request)
        # Honore ?exercice=<id> pour la liste d'une année clôturée ; sinon actif.
        ex_id = request.query_params.get('exercice')
        if ex_id:
            exercice = Exercice.objects.filter(tenant=tenant, id=ex_id).first()
        else:
            exercice = Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()
        if not exercice:
            return HttpResponse('Aucun exercice', status=404)

        qs = Eleve.objects.filter(
            tenant=tenant, exercice=exercice
        ).select_related('section', 'exercice').prefetch_related('paiements', 'abonnements__service').annotate(
            total_paye_sql=Coalesce(
                Sum('paiements__montant_inscription') +
                Sum('paiements__montant_mensualite')  +
                Sum('paiements__montant_uniforme')    +
                Sum('paiements__montant_fournitures') +
                Sum('paiements__montant_cantine')     +
                Sum('paiements__montant_divers'),
                Value(0), output_field=DecimalField()
            )
        ).order_by('section__nom', 'numero')

        filtre_statut = request.query_params.get('statut', '')
        filtre_alerte = request.query_params.get('alerte', '')
        if filtre_statut:
            qs = qs.filter(statut=filtre_statut)

        eleves_data = []
        total_attendu_global = 0.0
        total_paye_global    = 0.0
        nb_critique = nb_urgent = nb_attention = 0

        for e in qs:
            attendu = float(e.total_attendu)
            paye    = float(e.total_paye_sql or 0)
            reste   = round(max(0.0, attendu - paye), 0)
            alerte  = e.niveau_alerte

            if alerte == 'CRITIQUE':   nb_critique  += 1
            elif alerte == 'URGENT':   nb_urgent    += 1
            elif alerte == 'ATTENTION': nb_attention += 1

            total_attendu_global += attendu
            total_paye_global    += paye

            eleves_data.append({
                'numero':       e.numero,
                'matricule':    e.matricule or '—',
                'nom_complet':  e.nom_complet,
                'genre':        e.genre,
                'section_nom':  e.section.nom if e.section else '—',
                'statut':       e.statut,
                'prise_en_charge': bool(e.prise_en_charge or e.type_pec),
                'total_attendu': round(attendu, 0),
                'total_paye':    round(paye, 0),
                'reste':         reste,
                'niveau_alerte': alerte,
            })

        if filtre_alerte:
            eleves_data = [e for e in eleves_data if e['niveau_alerte'] == filtre_alerte]

        total_reste_global = round(max(0.0, total_attendu_global - total_paye_global), 0)

        context = {
            'tenant':            tenant,
            'exercice':          exercice,
            'date_edition':      timezone.now(),
            'eleves':            eleves_data,
            'nb_eleves':         len(eleves_data),
            'total_attendu':     round(total_attendu_global, 0),
            'total_paye':        round(total_paye_global, 0),
            'total_reste':       total_reste_global,
            'nb_critique':       nb_critique,
            'nb_urgent':         nb_urgent,
            'nb_attention':      nb_attention,
            'filtre_statut':     filtre_statut,
            'filtre_alerte':     filtre_alerte,
        }

        html_str = render_to_string('pdf/eleves.html', context)
        buffer   = BytesIO()
        result   = pisa.CreatePDF(html_str, dest=buffer, encoding='utf-8')
        if result.err:
            return HttpResponse('Erreur génération PDF', status=500)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        fname    = f"eleves_{exercice.annee_scolaire}.pdf"
        response['Content-Disposition'] = f'inline; filename="{fname}"'
        return response


class SituationElevePDFView(APIView):
    """PDF de situation financière individuelle d'un élève (paiements + solde)."""
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

        from apps.paiements.models import Paiement, Exercice as _Exercice

        tenant = get_tenant(request)
        try:
            eleve = Eleve.objects.select_related('section', 'exercice').get(id=eleve_id, tenant=tenant)
        except Eleve.DoesNotExist:
            return HttpResponse('Élève introuvable', status=404)

        exercice = _Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()

        paiements_qs = Paiement.objects.filter(
            tenant=tenant, eleve=eleve, exercice=exercice
        ).order_by('date_paiement') if exercice else Paiement.objects.none()

        paiements_list = []
        for p in paiements_qs:
            total_p = float(
                (p.montant_inscription or 0) + (p.montant_mensualite or 0) +
                (p.montant_uniforme or 0) + (p.montant_fournitures or 0) +
                (p.montant_cantine or 0) + (p.montant_divers or 0)
            )
            paiements_list.append({
                'date':          p.date_paiement,
                'no_recu':       p.no_piece or '—',
                'mode':          p.get_mode_paiement_display() if hasattr(p, 'get_mode_paiement_display') else p.mode_paiement,
                'inscription':   float(p.montant_inscription  or 0),
                'mensualite':    float(p.montant_mensualite    or 0),
                'uniforme':      float(p.montant_uniforme      or 0),
                'fournitures':   float(p.montant_fournitures   or 0),
                'cantine':       float(p.montant_cantine       or 0),
                'divers':        float(p.montant_divers        or 0),
                'total':         total_p,
                'observations':  p.observations or '',
            })

        total_paye   = sum(p['total'] for p in paiements_list)
        total_attendu = float(eleve.total_attendu)
        reste        = round(max(0.0, total_attendu - total_paye), 0)

        context = {
            'tenant':         tenant,
            'eleve':          eleve,
            'section_nom':    eleve.section.nom if eleve.section else '—',
            'exercice':       exercice,
            'date_edition':   timezone.now(),
            'paiements':      paiements_list,
            'total_paye':     round(total_paye, 0),
            'total_attendu':  round(total_attendu, 0),
            'reste':          reste,
            'nb_paiements':   len(paiements_list),
        }

        html_str = render_to_string('pdf/situation_eleve.html', context)
        buf      = BytesIO()
        result   = pisa.CreatePDF(html_str, dest=buf, encoding='utf-8')
        if result.err:
            return HttpResponse('Erreur génération PDF', status=500)

        response = HttpResponse(buf.getvalue(), content_type='application/pdf')
        safe_name = eleve.nom_complet.replace(' ', '_').replace('/', '-')
        response['Content-Disposition'] = f'inline; filename="situation_{safe_name}.pdf"'
        return response


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


class FicheElevePDFView(APIView):
    """Export PDF de la fiche complète d'un élève (identité, parents, situation)."""
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

        from apps.paiements.models import Exercice

        tenant = get_tenant(request)
        try:
            eleve = Eleve.objects.select_related('section', 'exercice').get(id=eleve_id, tenant=tenant)
        except Eleve.DoesNotExist:
            return HttpResponse('Élève introuvable', status=404)

        exercice = Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()

        total_attendu = float(eleve.total_attendu)
        total_paye    = float(eleve.total_paye)
        reste         = round(max(0.0, total_attendu - total_paye), 0)

        motif_pec = dict(Eleve.PRISE_EN_CHARGE_CHOICES).get(eleve.prise_en_charge, eleve.prise_en_charge or '')
        type_pec  = dict(Eleve.TYPE_PEC_CHOICES).get(eleve.type_pec, eleve.type_pec or '')

        context = {
            'tenant':            tenant,
            'eleve':             eleve,
            'section_nom':       eleve.section.nom if eleve.section else '—',
            'exercice':          exercice,
            'date_edition':      timezone.now(),
            'total_theorique':   round(float(eleve.total_theorique), 0),
            'montant_pec_annuel': round(float(eleve.montant_pec_annuel), 0),
            'total_attendu':     round(total_attendu, 0),
            'total_paye':        round(total_paye, 0),
            'reste':             reste,
            'motif_pec':         motif_pec,
            'type_pec':          type_pec,
        }

        html_str = render_to_string('pdf/fiche_eleve.html', context)
        buf      = BytesIO()
        result   = pisa.CreatePDF(html_str, dest=buf, encoding='utf-8')
        if result.err:
            return HttpResponse('Erreur génération fiche PDF.', status=500)

        response = HttpResponse(buf.getvalue(), content_type='application/pdf')
        safe_name = eleve.nom_complet.replace(' ', '_').replace('/', '-')
        response['Content-Disposition'] = f'inline; filename="fiche_{safe_name}.pdf"'
        return response
