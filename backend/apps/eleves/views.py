from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, Prefetch, Value, DecimalField, F, Q
from django.db.models.functions import Coalesce, TruncMonth
from apps.comptabilite.models import JournalEntry
from core.permissions import IsTenantMember
from core.tenant import get_tenant
from .models import (Eleve, Organisme, PriseEnChargeOrganisme, Section,
                     Service)
from .parcours import STATUTS_SORTIE
from apps.paiements.models import Exercice, Paiement
from .serializers import (EleveSerializer, OrganismeSerializer,
                          PriseEnChargeOrganismeSerializer, SectionSerializer,
                          ServiceSerializer)
from django.db.models import Max
from django.utils import timezone


def _date(valeur):
    """Date ISO venue du client, ou None. Tolère une chaîne vide."""
    import datetime
    if not valeur:
        return None
    if isinstance(valeur, datetime.date):
        return valeur
    try:
        return datetime.date.fromisoformat(str(valeur)[:10])
    except ValueError:
        return None


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


def contexte_liste_nominative(tenant, exercice, classe_id=None, section=None,
                              groupe='classe'):
    """Contexte d'une liste d'élèves SANS aucune donnée financière.

    Une liste de classe circule : elle est affichée, photocopiée, passée entre
    des mains d'enseignants et d'élèves. Y faire figurer ce que chaque famille
    doit exposerait leur situation à tous ceux qui la lisent. Ce contexte ne
    porte donc que l'identité et les dates.

    Partagé par l'export global et l'export par classe : deux constructions
    séparées finiraient par diverger, et l'une des deux laisserait passer un
    montant.
    """
    qs = (Eleve.objects.filter(tenant=tenant, exercice=exercice,
                               fiche_creance=False)
          .exclude(statut__in=STATUTS_SORTIE)
          .select_related('classe', 'section'))

    if classe_id == 'sans':
        qs, titre = qs.filter(classe__isnull=True), 'Sans classe'
    elif classe_id:
        qs = qs.filter(classe_id=classe_id)
        premiere = qs.first()
        titre = premiere.classe.nom if premiere and premiere.classe else ''
    else:
        titre = 'Toutes classes'

    if section:
        qs = qs.filter(section__nom=section)
        titre = f"{titre} — {section}" if titre != 'Toutes classes' else section

    from .tri import trier

    eleves = [{
        'matricule':      e.matricule or '—',
        'nom_complet':    e.nom_complet,
        'genre':          e.genre or '',
        'date_naissance': e.date_naissance,
        'date_entree':    e.date_entree or e.date_inscription,
        'classe':         e.classe.nom if e.classe else '—',
        'section':        e.section.nom if e.section else '—',
    } for e in trier(qs, groupe)]

    # Sur une liste d'UNE classe, la colonne serait la même valeur répétée ;
    # sur la liste globale, c'est l'information qui manque. Même raisonnement
    # pour la section : regroupé par section, sans la colonne, le lecteur ne
    # voit pas sur quoi repose l'ordre des lignes qu'il a sous les yeux.
    montrer_classe  = not classe_id
    montrer_section = groupe == 'section' and not section

    return {'tenant': tenant, 'exercice': exercice, 'classe': titre,
            'eleves': eleves, 'nb': len(eleves), 'date_edition': timezone.now(),
            'montrer_classe':  montrer_classe,
            'montrer_section': montrer_section,
            # Largeur calculée ici : un gabarit Django ne sait pas compter, et
            # des pourcentages qui ne tombent pas juste déforment la table
            # (xhtml2pdf AJOUTE le padding à la largeur demandée). Le nom
            # absorbe ce que les colonnes optionnelles laissent : 53 % à lui
            # seul, moins 16 pour la section et 12 pour la classe.
            'largeur_nom': 53 - 16 * montrer_section - 12 * montrer_classe}


class OrganismeViewSet(viewsets.ModelViewSet):
    """Organismes qui prennent en charge la scolarité : État, ONG, fondation…"""
    serializer_class   = OrganismeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (Organisme.objects.filter(tenant=get_tenant(self.request))
                .annotate(nb_boursiers_sql=Count('prises_en_charge')))

    def perform_create(self, serializer):
        serializer.save(tenant=get_tenant(self.request))

    def destroy(self, request, *args, **kwargs):
        """Un organisme qui suit des boursiers ne se supprime pas.

        Le PROTECT du modèle lèverait une 500 illisible : on répond ici avec
        le motif et le nombre d'élèves concernés, pour que l'école sache quoi
        faire — retirer les bourses d'abord, ou simplement désactiver.
        """
        organisme = self.get_object()
        nb = organisme.prises_en_charge.count()
        if nb:
            return Response(
                {'error': f"« {organisme.nom} » suit {nb} boursier(s). Retirez "
                          f"leurs prises en charge d'abord, ou désactivez "
                          f"l'organisme pour le sortir des listes."},
                status=400)
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'], url_path='suivi')
    def suivi(self, request):
        """Position financière de chaque organisme : couvert, reçu, dû.

        C'est le tableau qui justifie la fonctionnalité — sans lui, une école
        sait qu'un ministère finance des étudiants, mais pas s'il a payé.
        """
        from apps.comptabilite.views import get_exercice

        tenant   = get_tenant(request)
        exercice = get_exercice(tenant, request)
        if not exercice:
            return Response({'lignes': [], 'totaux': {}})

        lignes = []
        for organisme in Organisme.objects.filter(tenant=tenant):
            pecs = (PriseEnChargeOrganisme.objects
                    .filter(tenant=tenant, organisme=organisme, exercice=exercice)
                    .select_related('eleve__section')
                    .prefetch_related('eleve__abonnements__service'))
            couvert = recu = 0.0
            eleves = []
            for pec in pecs:
                eleve = pec.eleve
                part  = eleve.part_organisme
                paye  = eleve.paye_organisme
                couvert += part
                recu    += paye
                eleves.append({
                    'eleve_id':   str(eleve.id),
                    'matricule':  eleve.matricule or '',
                    'nom_complet': eleve.nom_complet,
                    'reference':  pec.reference,
                    'couvert':    part,
                    'recu':       paye,
                    'reste':      round(max(part - paye, 0.0), 2),
                })
            if not eleves and not organisme.actif:
                continue
            lignes.append({
                'organisme_id': str(organisme.id),
                'nom':          organisme.nom,
                'type':         organisme.get_type_display(),
                'reference':    organisme.reference,
                'contact':      organisme.telephone or organisme.email,
                'actif':        organisme.actif,
                'nb_boursiers': len(eleves),
                'couvert':      round(couvert, 2),
                'recu':         round(recu, 2),
                'reste':        round(max(couvert - recu, 0.0), 2),
                'eleves':       sorted(eleves, key=lambda e: e['nom_complet']),
            })

        lignes.sort(key=lambda l: l['reste'], reverse=True)
        return Response({
            'exercice': exercice.annee_scolaire,
            'lignes':   lignes,
            'totaux': {
                'nb_organismes': len(lignes),
                'nb_boursiers':  sum(l['nb_boursiers'] for l in lignes),
                'couvert':       round(sum(l['couvert'] for l in lignes), 2),
                'recu':          round(sum(l['recu'] for l in lignes), 2),
                'reste':         round(sum(l['reste'] for l in lignes), 2),
            },
        })


class PriseEnChargeOrganismeViewSet(viewsets.ModelViewSet):
    """Attribution d'une bourse à un élève, pour un exercice."""
    serializer_class   = PriseEnChargeOrganismeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = (PriseEnChargeOrganisme.objects
              .filter(tenant=get_tenant(self.request))
              .select_related('organisme', 'eleve'))
        if eleve := self.request.query_params.get('eleve'):
            qs = qs.filter(eleve_id=eleve)
        if organisme := self.request.query_params.get('organisme'):
            qs = qs.filter(organisme_id=organisme)
        return qs

    def perform_create(self, serializer):
        from .creances_organisme import appliquer

        tenant = get_tenant(self.request)
        # L'exercice n'est pas demandé au client : une bourse s'attribue
        # toujours sur l'année en cours, et le laisser choisir ouvrirait la
        # porte à des attributions sur une année clôturée.
        exercice = serializer.validated_data.get('exercice') or Exercice.objects.filter(
            tenant=tenant, cloture=False).order_by('-date_debut').first()
        pec = serializer.save(tenant=tenant, exercice=exercice)
        appliquer(pec)

    def perform_update(self, serializer):
        from .creances_organisme import appliquer
        appliquer(serializer.save())

    def perform_destroy(self, instance):
        from .creances_organisme import supprimer_creance
        supprimer_creance(instance)
        instance.delete()


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

        from .echeancier import PREFETCH_PAIEMENTS

        qs = Eleve.objects.filter(tenant=tenant).select_related(
            # `tenant` : l'échéancier y lit le réglage d'exigibilité, et
            # l'alerte de chaque fiche vient désormais de l'échéancier.
            'tenant', 'section', 'exercice', 'reliquat_exercice_origine'
        ).prefetch_related(
            'paiements', 'abonnements__service',
            # Sans ce prefetch, part_organisme déclenche une requête par élève.
            'prises_en_charge_organisme__organisme',
            # Les paiements actifs, sous le nom que l'échéancier va chercher.
            Prefetch('paiements',
                     queryset=Paiement.objects.filter(statut='ACTIF'),
                     to_attr=PREFETCH_PAIEMENTS),
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
            # Reliquat déjà encaissé — annoté pour que le reliquat restant de
            # chaque élève se lise sans une requête par ligne (cf. reliquat_paye).
            reliquat_paye_sql=Coalesce(
                Sum('paiements__montant_reliquat',
                    filter=Q(paiements__statut='ACTIF')),
                Value(0), output_field=DecimalField()
            ),
            # Ce qu'un organisme a versé pour cet élève — distingué du reste
            # pour que l'alerte ne juge que la famille.
            paye_organisme_sql=Coalesce(
                Sum('paiements__montant_inscription',
                    filter=Q(paiements__statut='ACTIF', paiements__organisme__isnull=False)) +
                Sum('paiements__montant_mensualite',
                    filter=Q(paiements__statut='ACTIF', paiements__organisme__isnull=False)) +
                Sum('paiements__montant_uniforme',
                    filter=Q(paiements__statut='ACTIF', paiements__organisme__isnull=False)) +
                Sum('paiements__montant_fournitures',
                    filter=Q(paiements__statut='ACTIF', paiements__organisme__isnull=False)) +
                Sum('paiements__montant_cantine',
                    filter=Q(paiements__statut='ACTIF', paiements__organisme__isnull=False)) +
                Sum('paiements__montant_divers',
                    filter=Q(paiements__statut='ACTIF', paiements__organisme__isnull=False)),
                Value(0), output_field=DecimalField()
            ),
        )

        # Les fiches de créance ne sont pas des élèves : elles n'existent que
        # pour porter au bilan l'ardoise d'un enfant déjà parti. Elles se
        # consultent depuis « Anciens élèves » (?creances=1 pour les voir ici).
        veut_creances = self.request.query_params.get('creances') in ('1', 'true', 'True')
        if not veut_creances:
            qs = qs.filter(fiche_creance=False)

        # Les sortis (diplômés, transférés, abandons) ne sont plus des élèves
        # actifs : les garder ici fausse l'effectif et les listes de classe.
        # Ils vivent dans « Anciens élèves ». ?sortants=1 pour les revoir —
        # l'école a parfois besoin d'y revenir, typiquement pour encaisser un
        # dernier règlement après le départ.
        # UNIQUEMENT sur la liste : get_object() passe par ce queryset, et
        # exclure les sortants ici rendrait leur fiche impossible à ouvrir ou à
        # corriger — on ne pourrait plus réinscrire un enfant revenu après un
        # abandon, ni rectifier un statut posé par erreur.
        #
        # Trois demandes explicites restent par ailleurs prioritaires — les
        # honorer et ne rien renvoyer serait absurde : ?sortants=1, un ?statut=
        # de sortie, et ?creances=1 (une fiche de créance appartient par
        # définition à un sortant).
        if (self.action == 'list'
                and self.request.query_params.get('sortants') not in ('1', 'true', 'True')
                and not self.request.query_params.get('statut')
                and not veut_creances):
            qs = qs.exclude(statut__in=STATUTS_SORTIE)

        if section := self.request.query_params.get('section'):
            qs = qs.filter(section__nom=section)
        if exercice := self.request.query_params.get('exercice'):
            qs = qs.filter(exercice_id=exercice)
        if statut := self.request.query_params.get('statut'):
            qs = qs.filter(statut=statut)
        if pec := self.request.query_params.get('prise_en_charge'):
            qs = qs.filter(prise_en_charge=pec)
        # Suivi des dettes antérieures : ne garder que les élèves qui traînent
        # un reliquat encore ouvert (reporté > déjà réglé).
        if self.request.query_params.get('avec_reliquat') in ('1', 'true', 'True'):
            qs = qs.filter(reliquat_anterieur__gt=0).filter(
                reliquat_anterieur__gt=F('reliquat_paye_sql'))

        return qs.order_by('numero')

    def perform_create(self, serializer):

        tenant = get_tenant(self.request)
        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()

        if not exercice:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Aucun exercice actif trouvé.")

        # Numéro interne + matricule de promo (AAAA-CODE-NNNN) + entrée figée.
        # La date d'entrée est celle saisie sur la fiche : un élève inscrit en
        # cours d'année appartient bien à la promo de l'exercice, mais garde
        # sa vraie date d'arrivée.
        from .matricules import identite_nouvel_eleve
        identite = identite_nouvel_eleve(
            tenant, exercice,
            date_entree=serializer.validated_data.get('date_inscription'))

        eleve = serializer.save(tenant=tenant, exercice=exercice, **identite)
        self._sync_reliquat(serializer, eleve)

    def perform_update(self, serializer):
        self._sync_reliquat(serializer, serializer.save())

    @staticmethod
    def _sync_reliquat(serializer, eleve):
        """Recale l'à-nouveaux 411/890 quand l'impayé antérieur a été touché.

        L'écriture est recalculée en entier par le service — corriger le montant
        d'une fiche trois fois ne laisse qu'une seule pièce au journal."""
        from apps.paiements.reliquat_migration import synchroniser_ecritures
        touche = {'reliquat_anterieur', 'reliquat_note'} & set(serializer.initial_data or {})
        if touche and eleve.exercice_id and not eleve.exercice.cloture:
            synchroniser_ecritures(eleve)

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
        from apps.paiements.reliquat_migration import definir_impaye_anterieur
        from .matricules import Attributeur
        a_creer  = [l for l in rapport['lignes'] if l['statut'] == 'OK']
        reprises, montant_reprise = 0, 0.0
        impayes, montant_impaye = 0, 0.0
        with transaction.atomic():
            attributeur = Attributeur(tenant, exercice)
            for ligne in a_creer:
                data = ligne['data']
                identite = attributeur.suivant(
                    matricule=data.pop('matricule'),
                    date_entree=data.get('date_inscription'))
                eleve = Eleve.objects.create(
                    tenant=tenant, exercice=exercice, **identite, **data,
                )
                if ligne['montant_reprise'] > 0:
                    paiement = creer_paiement_reprise(
                        tenant, exercice, eleve, user=request.user, **ligne['reprise'],
                    )
                    if paiement:
                        reprises += 1
                        montant_reprise += float(paiement.total)
                # Ardoise des années d'avant : à-nouveaux 411/890, sans 706 ni
                # trésorerie — indépendante de la reprise ci-dessus.
                if ligne.get('impaye_anterieur', 0) > 0:
                    definir_impaye_anterieur(eleve, ligne['impaye_anterieur'],
                                             note=ligne.get('origine_impaye') or '')
                    impayes += 1
                    montant_impaye += ligne['impaye_anterieur']
        log_audit(request, 'IMPORT', 'Eleve',
                  description=f"Import Excel : {len(a_creer)} élèves créés, "
                              f"{reprises} reprises de soldes ({montant_reprise:,.0f} FCFA), "
                              f"{impayes} impayés antérieurs ({montant_impaye:,.0f} FCFA), "
                              f"{rapport['resume']['doublons']} doublons ignorés, "
                              f"{rapport['resume']['erreurs']} lignes en erreur")
        return Response({'resume': rapport['resume'], 'crees': len(a_creer),
                         'reprises': reprises, 'montant_reprise': montant_reprise,
                         'impayes_anterieurs': impayes,
                         'montant_impaye_anterieur': round(montant_impaye, 2)})

    @action(detail=True, methods=['get', 'post'], url_path='corriger-reprise')
    def corriger_reprise(self, request, pk=None):
        """Lit (GET) ou corrige (POST) le « déjà payé » de reprise d'un élève.

        POST : recrée la reprise avec les montants corrigés. Si l'exercice a des
        agrégats migrés (source MIGRATION sur les produits 70), la reprise est
        automatiquement neutralisée en 890 (le produit est déjà dans l'agrégat)."""
        from django.db import transaction
        from apps.paiements.models import Paiement
        from apps.paiements.reprise import creer_paiement_reprise
        from apps.comptabilite.neutralisation import neutraliser_reprises

        tenant   = get_tenant(request)
        eleve    = self.get_object()
        exercice = Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()
        if not exercice:
            return Response({'error': 'Aucun exercice actif'}, status=400)
        reprise = Paiement.objects.filter(tenant=tenant, exercice=exercice, eleve=eleve,
                                          mode_paiement='REPRISE').first()

        if request.method == 'GET':
            return Response({
                'montant_inscription': float(reprise.montant_inscription) if reprise else 0,
                'montant_mensualite':  float(reprise.montant_mensualite)  if reprise else 0,
                'montant_divers':      float(reprise.montant_divers)      if reprise else 0,
                'total_attendu':       float(eleve.total_attendu),
                'reste_a_payer':       float(eleve.reste_a_payer),
            })

        d = request.data
        montants = {
            'montant_inscription': float(d.get('montant_inscription', 0) or 0),
            'montant_mensualite':  float(d.get('montant_mensualite', 0) or 0),
            'montant_uniforme': 0, 'montant_fournitures': 0,
            'montant_divers':      float(d.get('montant_divers', 0) or 0),
        }
        with transaction.atomic():
            if reprise:
                JournalEntry.objects.filter(tenant=tenant, exercice=exercice,
                                            source='PAIEMENT', source_id=reprise.id).delete()
                reprise.delete()
            if sum(montants.values()) > 0:
                creer_paiement_reprise(tenant, exercice, eleve, user=request.user,
                                       montants=montants)
            # Neutralisation recalculée sur TOUTES les reprises en vigueur —
            # jamais empilée sur l'existante. Sans cela, chaque correction
            # laissait un débit 706 orphelin qui rongeait les produits migrés
            # jusqu'à mettre le total des recettes à 0.
            neutraliser_reprises(tenant, exercice)
        eleve.refresh_from_db()
        from core.models import log_audit
        log_audit(request, 'UPDATE', 'Eleve', str(eleve.id),
                  f"Correction du déjà payé (reprise) — {eleve.nom_complet}")
        return Response({'success': True, 'reste_a_payer': float(eleve.reste_a_payer)})

    @action(detail=False, methods=['get', 'post'], url_path='impayes-anterieurs')
    def impayes_anterieurs(self, request):
        """Saisie en lot des impayés antérieurs — écran de migration.

        GET  : la liste des élèves de l'exercice actif avec leur impayé
               antérieur actuel, allégée (pas d'annotation de paiements).
        POST : {"lignes": [{"eleve_id": ..., "montant": ..., "note": "..."}]}
               Applique ligne par ligne et rend le détail des refus. Une ligne
               en erreur n'empêche pas les autres de passer : sur 300 élèves
               saisis à la main, tout annuler pour une faute de frappe serait
               le meilleur moyen de décourager l'école.
        """
        from django.db.models import Sum as _Sum
        from apps.paiements.reliquat_migration import (definir_impaye_anterieur,
                                                       resume_impayes_anterieurs)

        tenant   = get_tenant(request)
        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False).order_by('-date_debut').first()
        if not exercice:
            return Response({'error': 'Aucun exercice actif trouvé.'}, status=400)

        if request.method == 'GET':
            qs = Eleve.objects.filter(
                tenant=tenant, exercice=exercice
            ).select_related('section').annotate(
                reliquat_paye_sql=Coalesce(
                    _Sum('paiements__montant_reliquat',
                         filter=Q(paiements__statut='ACTIF')),
                    Value(0), output_field=DecimalField()),
            ).order_by('section__ordre', 'nom_complet')
            return Response({
                'exercice': exercice.annee_scolaire,
                'resume':   resume_impayes_anterieurs(tenant, exercice),
                'lignes': [{
                    'eleve_id':    str(e.id),
                    'matricule':   e.matricule or '',
                    'nom_complet': e.nom_complet,
                    'section':     e.section.nom if e.section else '',
                    'montant':     round(float(e.reliquat_anterieur or 0), 2),
                    'deja_paye':   e.reliquat_paye,
                    'restant':     e.reliquat_restant,
                    'note':        e.reliquat_note,
                } for e in qs],
            })

        lignes = request.data.get('lignes') or []
        if not isinstance(lignes, list):
            return Response({'error': "« lignes » doit être une liste."}, status=400)

        eleves = {str(e.id): e for e in Eleve.objects.filter(
            tenant=tenant, exercice=exercice,
            id__in=[l.get('eleve_id') for l in lignes if l.get('eleve_id')])}

        appliques, refuses, total = [], [], 0.0
        for ligne in lignes:
            eleve = eleves.get(str(ligne.get('eleve_id')))
            if not eleve:
                refuses.append({'eleve_id': ligne.get('eleve_id'),
                                'motif': 'Élève introuvable sur cet exercice'})
                continue
            try:
                res = definir_impaye_anterieur(eleve, ligne.get('montant'),
                                               note=ligne.get('note'))
            except (ValueError, TypeError) as e:
                refuses.append({'eleve_id': str(eleve.id),
                                'nom_complet': eleve.nom_complet, 'motif': str(e)})
                continue
            total += res['montant']
            appliques.append({'eleve_id': str(eleve.id),
                              'nom_complet': eleve.nom_complet, **res})

        from core.models import log_audit
        log_audit(request, 'UPDATE', 'Eleve',
                  description=f"Impayés antérieurs : {len(appliques)} élève(s) "
                              f"mis à jour ({total:,.0f} FCFA), {len(refuses)} refusé(s)")
        return Response({'appliques': appliques, 'refuses': refuses,
                         'nb_appliques': len(appliques), 'nb_refuses': len(refuses),
                         'resume': resume_impayes_anterieurs(tenant, exercice)})

    @action(detail=False, methods=['get'], url_path='effectifs-classes')
    def effectifs_classes(self, request):
        """Nombre d'élèves ACTIFS par classe, à l'instant présent.

        Compté sur le même périmètre que la liste — sortis et fiches de créance
        exclus — sinon l'effectif d'une classe annoncerait des enfants partis.
        """
        # Import local : évite un cycle eleves <-> comptabilite au chargement.
        from apps.comptabilite.views import get_exercice

        tenant = get_tenant(request)
        exercice = get_exercice(tenant, request)
        if not exercice:
            return Response({'classes': [], 'total': 0})

        qs = (Eleve.objects.filter(tenant=tenant, exercice=exercice,
                                   fiche_creance=False)
              .exclude(statut__in=STATUTS_SORTIE))
        lignes = list(qs.values('classe_id', 'classe__nom', 'section__nom')
                        .annotate(nb=Count('id'))
                        .order_by('section__nom', 'classe__nom'))
        return Response({
            'exercice': exercice.annee_scolaire,
            'total':    qs.count(),
            'classes': [{
                'classe_id': str(l['classe_id']) if l['classe_id'] else None,
                'classe':    l['classe__nom'] or 'Sans classe',
                'section':   l['section__nom'] or '—',
                'nb':        l['nb'],
            } for l in lignes],
        })

    @action(detail=False, methods=['get'], url_path='liste-classe-pdf')
    def liste_classe_pdf(self, request):
        """Liste nominative d'une classe — SANS aucune donnée financière.

        C'est le document qu'un enseignant affiche ou fait circuler : y faire
        figurer ce que chaque famille doit exposerait la situation financière
        des élèves à qui la liste passe entre les mains. Uniquement l'identité
        et les dates, comme demandé.
        """
        from io import BytesIO

        from django.http import HttpResponse
        from django.template.loader import render_to_string

        from apps.comptabilite.views import get_exercice
        try:
            from xhtml2pdf import pisa
        except ImportError:
            return HttpResponse('xhtml2pdf non installé', status=500)

        tenant = get_tenant(request)
        exercice = get_exercice(tenant, request)
        if not exercice:
            return HttpResponse('Aucun exercice actif', status=404)

        # Une liste d'UNE classe n'a pas de groupe à ordonner : reste
        # l'ancienneté, que `trier` applique de toute façon.
        contexte = contexte_liste_nominative(
            tenant, exercice, request.query_params.get('classe'),
            groupe=request.query_params.get('tri', 'matricule'))
        titre = contexte['classe']
        html = render_to_string('pdf/liste_classe.html', contexte)
        buf = BytesIO()
        if pisa.CreatePDF(html, dest=buf, encoding='utf-8').err:
            return HttpResponse('Erreur génération PDF.', status=500)
        resp = HttpResponse(buf.getvalue(), content_type='application/pdf')
        resp['Content-Disposition'] = (
            f'attachment; filename="liste_{titre or "classe"}_{exercice.annee_scolaire}.pdf"')
        return resp

    @action(detail=False, methods=['post'], url_path='ancien')
    def creer_ancien(self, request):
        """Enregistre un ancien élève qui n'a jamais existé dans le système.

        Une école qui migre garde la mémoire de ses diplômés bien avant SAGI
        SCHOOL. Sans ce point d'entrée, cette base est perdue : l'import et le
        formulaire ordinaire réclament une section et un tarif, or on ne veut
        ici que l'identité et les dates.

        La fiche est créée sur l'exercice actif — c'est le seul point d'ancrage
        disponible — mais son statut de sortie la tient hors de la liste et des
        effectifs. Son matricule porte la promo de sa VRAIE date d'entrée, pas
        celle de la saisie (voir matricules.annee_promo).
        """
        from core.models import log_audit

        from .matricules import identite_nouvel_eleve

        tenant = get_tenant(request)
        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False).order_by('-date_debut').first()
        if not exercice:
            return Response({'error': 'Aucun exercice actif.'}, status=400)

        data = request.data
        nom = (data.get('nom_complet') or '').strip()
        if not nom:
            return Response({'nom_complet': 'Le nom est obligatoire.'}, status=400)

        statut = data.get('statut') or 'DIPLOME'
        if statut not in STATUTS_SORTIE:
            return Response(
                {'statut': f"Statut attendu parmi {', '.join(STATUTS_SORTIE)}."},
                status=400)

        entree = _date(data.get('date_entree'))
        sortie = _date(data.get('date_sortie'))
        if not entree:
            return Response({'date_entree': "La date d'entrée est obligatoire."},
                            status=400)
        if sortie and sortie < entree:
            return Response(
                {'date_sortie': "La sortie ne peut pas précéder l'entrée."},
                status=400)

        identite = identite_nouvel_eleve(tenant, exercice, date_entree=entree)
        eleve = Eleve.objects.create(
            tenant=tenant, exercice=exercice, nom_complet=nom,
            genre=data.get('genre') or '',
            date_naissance=_date(data.get('date_naissance')),
            lieu_naissance=data.get('lieu_naissance') or '',
            nom_tuteur=data.get('nom_tuteur') or '',
            telephone_tuteur=data.get('telephone_tuteur') or '',
            statut=statut, date_sortie=sortie,
            # date_inscription porte la vraie entrée : c'est elle que lit le
            # regroupement par enfant et le rebasage des matricules.
            date_inscription=entree,
            **identite)
        log_audit(request, 'CREER', 'Eleve', str(eleve.id),
                  description=f"Ancien élève enregistré : {nom} ({identite['matricule']})")
        return Response(EleveSerializer(eleve).data, status=201)

    @action(detail=True, methods=['get'], url_path='echeancier')
    def echeancier(self, request, pk=None):
        """Ce que l'élève doit mois par mois, et ce qui reste sur chacun.

        Un total (« reste à payer 91 000 ») ne dit rien à une famille qui règle
        au mois : elle ne sait ni quels mois sont soldés, ni combien il manque
        sur celui en cours. Lecture directe comme pour le parcours — une fiche
        de créance doit rester consultable.
        """
        from .echeancier import construire_echeancier
        eleve = (Eleve.objects.filter(tenant=get_tenant(request), pk=pk)
                 .select_related('section', 'exercice')
                 .prefetch_related('abonnements__service').first())
        if not eleve:
            return Response({'error': 'Élève introuvable.'}, status=404)
        return Response(construire_echeancier(eleve))

    @action(detail=True, methods=['get'], url_path='parcours')
    def parcours(self, request, pk=None):
        """Scolarité complète de l'enfant, année par année, depuis son entrée.

        Rassemble les fiches éparpillées sur les exercices — c'est la lecture
        continue qui manquait pour suivre un élève qui reste plusieurs années
        et pour rouvrir le dossier d'un diplômé longtemps après son départ.
        """
        from .parcours import construire_parcours
        # Lecture directe et non self.get_object() : le queryset de la liste
        # écarte les fiches de créance, or c'est justement depuis « Anciens
        # élèves » qu'on ouvre le parcours d'un enfant parti en devant.
        eleve = Eleve.objects.filter(tenant=get_tenant(request), pk=pk).first()
        if not eleve:
            return Response({'error': 'Élève introuvable.'}, status=404)
        return Response(construire_parcours(eleve))

    @action(detail=False, methods=['get'], url_path='sante-migration')
    def sante_migration(self, request):
        """État de complétude des données reprises — ce qui reste à compléter.

        Une migration se termine progressivement : sans ce tableau, les trous
        se découvrent au moment d'éditer un bilan, six mois plus tard."""
        from .sante_migration import diagnostiquer

        tenant   = get_tenant(request)
        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False).order_by('-date_debut').first()
        if not exercice:
            return Response({'error': 'Aucun exercice actif trouvé.'}, status=400)
        return Response(diagnostiquer(tenant, exercice))

    @action(detail=True, methods=['post'], url_path='montants-mois')
    def montants_mois(self, request, pk=None):
        """Fixe le montant DÛ de certains mois, quand il diffère du tarif.

        Attend {"montants": {"7": 30000}} — dict vide pour tout remettre au
        tarif ordinaire.

        Deux usages du terrain, indissociables du mois d'entrée : une réduction
        sur un mois entamé à mi-parcours (entré le 16, il ne le vivra qu'à
        moitié), et un mois déjà réglé dans les frais d'inscription, donc à 0.

        Zéro est une valeur LÉGITIME, distincte de « pas de montant saisi » :
        c'est toute la raison d'un dict plutôt que d'une liste de couples.

        Contrairement à l'imputation du payé, aucun total n'est verrouillé ici :
        ce que l'école facture lui appartient. C'est l'argent REÇU qui doit
        s'accorder au grand livre, pas le tarif décidé.
        """
        from .echeancier import construire_echeancier, mois_factures

        eleve = (Eleve.objects.filter(tenant=get_tenant(request), pk=pk)
                 .select_related('section', 'exercice')
                 .prefetch_related('abonnements__service').first())
        if not eleve:
            return Response({'error': 'Élève introuvable.'}, status=404)
        if eleve.exercice and eleve.exercice.cloture:
            return Response(
                {'error': f"L'exercice {eleve.exercice.annee_scolaire} est clôturé."},
                status=400)

        brut = request.data.get('montants')
        if brut is None or not isinstance(brut, dict):
            return Response({'montants': 'Attendu : un objet {mois: montant}.'},
                            status=400)

        factures = set(mois_factures(eleve))
        propre = {}
        for cle, valeur in brut.items():
            try:
                mois, montant = int(cle), round(float(valeur or 0), 2)
            except (TypeError, ValueError):
                return Response({'montants': 'Mois et montants numériques attendus.'},
                                status=400)
            if mois not in factures:
                return Response(
                    {'montants': f"Le mois {mois} n'est pas facturé à cet élève."},
                    status=400)
            if montant < 0:
                return Response({'montants': 'Un montant dû ne peut pas être négatif.'},
                                status=400)
            propre[str(mois)] = montant

        # Descendre un mois SOUS ce qui y a déjà été encaissé creuserait un
        # trop-perçu : on refuse en le disant, comme pour les mois dus.
        ech = construire_echeancier(eleve)
        deja = {l['mois']: l['paye'] for l in ech['lignes']}
        trop = [m for m in propre if deja.get(int(m), 0) > float(propre[m]) + 0.01]
        if trop:
            from .echeancier import NOMS_MOIS
            noms = ', '.join(NOMS_MOIS.get(int(m), m) for m in sorted(trop, key=int))
            return Response({'montants':
                             f"Déjà encaissé plus que ce montant pour : {noms}. "
                             f"Corrigez d'abord la répartition ou le paiement."},
                            status=400)

        eleve.montants_mois = propre
        eleve.save(update_fields=['montants_mois'])
        return Response(construire_echeancier(eleve))

    @action(detail=True, methods=['post'], url_path='imputation')
    def imputation(self, request, pk=None):
        """Saisit le montant réellement réglé pour chaque mois.

        Attend {"imputation": {"7": 60000, "8": 30000}} — dict vide pour revenir
        à la répartition automatique.

        Sert d'abord à préciser des données MIGRÉES : la reprise enregistre un
        « déjà payé » global, sans détail mensuel, et l'école connaît souvent la
        vraie ventilation. Le total saisi peut donc s'écarter de ce que porte la
        reprise — l'écart y est reporté.

        La trésorerie n'est JAMAIS touchée : une reprise s'écrit
        411 D / 706 C / 890 D / 411 C, pas un franc de caisse. En revanche, un
        écart qui dépasse la reprise viendrait forcément d'un encaissement réel
        et là on refuse : corriger de l'argent reçu passe par la modification du
        paiement, qui écrit au grand livre.
        """
        from django.db import transaction

        from apps.comptabilite.neutralisation import neutraliser_reprises
        from apps.paiements.models import Paiement
        from apps.paiements.reprise import creer_paiement_reprise
        from core.models import log_audit

        from .echeancier import construire_echeancier, mois_factures

        def recharger():
            e = (Eleve.objects.filter(tenant=tenant, pk=pk)
                 .select_related('section', 'exercice')
                 .prefetch_related('abonnements__service').first())
            return e

        tenant = get_tenant(request)
        eleve = recharger()
        if not eleve:
            return Response({'error': 'Élève introuvable.'}, status=404)
        exercice = eleve.exercice
        if not exercice:
            return Response({'error': "L'élève n'est rattaché à aucun exercice."}, status=400)
        if exercice.cloture:
            return Response(
                {'error': f"L'exercice {exercice.annee_scolaire} est clôturé."}, status=400)

        brut = request.data.get('imputation')
        if brut is None or not isinstance(brut, dict):
            return Response(
                {'imputation': 'Attendu : un objet {mois: montant}.'}, status=400)

        # Retour à l'automatique.
        if not brut:
            eleve.imputation_mois = {}
            eleve.save(update_fields=['imputation_mois'])
            return Response(construire_echeancier(eleve))

        factures = set(mois_factures(eleve))
        propre = {}
        for cle, valeur in brut.items():
            try:
                mois, montant = int(cle), round(float(valeur or 0), 2)
            except (TypeError, ValueError):
                return Response({'imputation': 'Mois et montants numériques attendus.'},
                                status=400)
            if mois not in factures:
                return Response(
                    {'imputation': f"Le mois {mois} n'est pas facturé à cet élève."},
                    status=400)
            if montant < 0:
                return Response({'imputation': 'Un montant payé ne peut pas être négatif.'},
                                status=400)
            propre[str(mois)] = montant

        # Ce que les paiements portent aujourd'hui, imputation manuelle mise de côté.
        eleve.imputation_mois = {}
        reel = round(sum(l['paye'] for l in construire_echeancier(eleve)['lignes']), 2)
        saisi = round(sum(propre.values()), 2)
        ecart = round(saisi - reel, 2)

        reprise = Paiement.objects.filter(tenant=tenant, exercice=exercice,
                                          eleve=eleve, mode_paiement='REPRISE',
                                          statut='ACTIF').first()
        repris = float(reprise.montant_mensualite) if reprise else 0.0

        if abs(ecart) > 0.01:
            nouveau_repris = round(repris + ecart, 2)
            if nouveau_repris < 0:
                return Response({'imputation':
                                 f"Le total saisi ({saisi:,.0f} FCFA) descend sous les "
                                 f"encaissements réels. Seule la part reprise à la "
                                 f"migration ({repris:,.0f} FCFA) est corrigeable ici ; "
                                 f"pour un paiement encaissé, modifiez le paiement."},
                                status=400)
            with transaction.atomic():
                montants = {
                    'montant_inscription': float(reprise.montant_inscription) if reprise else 0.0,
                    'montant_mensualite':  nouveau_repris,
                    'montant_uniforme':    float(reprise.montant_uniforme) if reprise else 0.0,
                    'montant_fournitures': float(reprise.montant_fournitures) if reprise else 0.0,
                    'montant_divers':      float(reprise.montant_divers) if reprise else 0.0,
                }
                if reprise:
                    JournalEntry.objects.filter(
                        tenant=tenant, exercice=exercice,
                        source='PAIEMENT', source_id=reprise.id).delete()
                    reprise.delete()
                if sum(montants.values()) > 0:
                    creer_paiement_reprise(tenant, exercice, eleve,
                                           user=request.user, montants=montants)
                # Recalculée en entier, jamais empilée (leçon des débits 706
                # orphelins qui avaient mis les recettes à 0).
                neutraliser_reprises(tenant, exercice)

        eleve = recharger()
        eleve.imputation_mois = propre
        eleve.save(update_fields=['imputation_mois'])
        log_audit(request, 'UPDATE', 'Eleve', str(eleve.id),
                  description=(f"Répartition mensuelle du payé — {eleve.nom_complet}"
                               + (f" (reprise ajustée de {ecart:+,.0f} FCFA)"
                                  if abs(ecart) > 0.01 else "")))
        reponse = construire_echeancier(eleve)
        reponse['reprise_ajustee'] = round(ecart, 2) if abs(ecart) > 0.01 else 0
        return Response(reponse)

    @action(detail=False, methods=['get'], url_path='rappels')
    def rappels(self, request):
        """Qui relancer aujourd'hui, et combien la famille doit-elle.

        Ne retient que ce qui est exigible au sens du réglage de l'école :
        réclamer un mois pas encore dû décrédibiliserait les vrais rappels.
        """
        from apps.comptabilite.views import get_exercice

        from .rappels import eleves_a_rappeler, fenetre_rappel

        tenant = get_tenant(request)
        exercice = get_exercice(tenant, request)
        if not exercice:
            return Response({'fenetre': fenetre_rappel(tenant), 'lignes': [],
                             'nb': 0, 'total_exigible': 0})
        return Response(eleves_a_rappeler(tenant, exercice))

    @action(detail=False, methods=['post'], url_path='rappels/envoyer')
    def envoyer_rappels_action(self, request):
        """Déclenche l'envoi des rappels du mois (bouton de l'écran Paramètres).

        Sans envoi SMS activé ET sans passerelle configurée, tout est SIMULÉ :
        journalisé, rien n'est émis. C'est le défaut, et c'est voulu — un
        message parti par erreur à des centaines de familles ne se rattrape pas.

        `forcer` permet de sortir de la fenêtre de rappel ; un élève déjà
        prévenu ce mois-ci reste sauté quoi qu'il arrive.
        """
        from apps.comptabilite.views import get_exercice
        from core.models import log_audit

        from .rappels import envoyer_rappels

        tenant = get_tenant(request)
        exercice = get_exercice(tenant, request)
        if not exercice:
            return Response({'error': 'Aucun exercice actif.'}, status=400)

        rapport = envoyer_rappels(
            tenant, exercice,
            forcer=str(request.data.get('forcer', '')).lower() in ('1', 'true'))
        log_audit(request, 'ENVOYER', 'Rappel', str(tenant.id),
                  description=(f"Rappels {rapport.get('periode', '')} : "
                               f"{rapport['envoyes']} envoyé(s), "
                               f"{rapport['simules']} simulé(s), "
                               f"{rapport['echecs']} échec(s)"))
        return Response(rapport)

    @action(detail=False, methods=['get'], url_path='rappels/historique')
    def historique_rappels(self, request):
        """Les 100 derniers rappels — un parent qui dit n'avoir rien reçu se
        vérifie ici."""
        from .models import RappelEnvoye

        lignes = (RappelEnvoye.objects.filter(tenant=get_tenant(request))
                  .select_related('eleve')[:100])
        return Response({'lignes': [{
            'id':          str(r.id),
            'eleve':       r.eleve.nom_complet,
            'periode':     r.periode,
            'destinataire': r.destinataire,
            'montant':     float(r.montant),
            'statut':      r.statut,
            'detail':      r.detail,
            'envoye_le':   r.created_at,
        } for r in lignes]})

    @action(detail=False, methods=['get'], url_path='anciens')
    def anciens(self, request):
        """Base historique des élèves sortis (diplômés, transférés, abandons).

        Indépendante de l'exercice actif : un diplômé de 2019 s'y retrouve
        comme un transféré de l'an dernier. Le statut retenu est celui de la
        dernière fiche — un enfant réinscrit après un abandon n'y est plus.
        """
        from .parcours import anciens_eleves
        return Response(anciens_eleves(
            get_tenant(request),
            recherche=request.query_params.get('q', ''),
            statut=request.query_params.get('statut', '')))

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
            # Après un rebasage, l'école cherche encore par l'ancien numéro
            # (carnets papier, anciens reçus).
            _Q(matricule_ancien__icontains=q) |
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

        from .echeancier import construire_echeancier

        eleve    = self.get_object()
        tenant   = eleve.tenant
        exercice = Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()

        section = eleve.section

        # ── Frais bruts de la section ──────────────────────────────────
        fees_bruts = {
            'inscription': float(section.frais_inscription) if section else 0,
            'mensualite':  float(section.frais_mensualite)  if section else 0,
            'uniforme':    float(section.frais_uniforme)    if section else 0,
            'fournitures': float(section.frais_fournitures) if section else 0,
        }

        # ── Frais nets de prise en charge ──────────────────────────────
        # Les montants viennent de la FICHE, via les mêmes propriétés que le
        # suivi financier. Cet endroit recalculait la prise en charge à partir
        # des anciens taux (type_pec, taux_pec_*), que la migration 0024 a
        # remis à zéro en rendant les montants seuls maîtres : le calcul
        # rendait donc le tarif BRUT depuis. L'écran de paiement réclamait la
        # mensualité entière à un élève pris en charge, et le solde du reçu
        # contredisait celui de sa fiche.
        #
        # Deux calculs séparés d'une même chose finissent toujours par
        # diverger : il n'y en a plus qu'un.
        fees_nets = {
            'inscription': round(max(fees_bruts['inscription']
                                     - eleve.montant_pec_inscription, 0.0), 2),
            'mensualite':  eleve.frais_mensualite_effectif,
            'uniforme':    fees_bruts['uniforme'],
            'fournitures': fees_bruts['fournitures'],
        }

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
                # UNIQUE : None = dû à l'inscription, 1..12 = mois calendaire
                'mois_unique': ab.service.mois_unique,
            }
            for ab in eleve.abonnements.all() if ab.service.actif
        ]

        # ── Mois de l'année scolaire : le dû, le versé et le reste, mois par mois
        # Ces trois montants viennent de l'ÉCHÉANCIER, qui fait déjà foi sur la
        # fiche, les alertes et les relances. La saisie n'avait ici qu'un
        # booléen « payé », vrai dès qu'un paiement DÉSIGNAIT le mois — même
        # s'il n'en couvrait qu'un tiers. Un mois réglé à moitié se croyait
        # soldé : l'écran proposait le suivant et laissait le trou derrière lui.
        # Encaisser un acompte était donc impossible sans perdre sa trace.
        nb_dus     = eleve.nb_mensualites_dues
        ech        = construire_echeancier(eleve)
        par_mois   = {ligne['mois']: ligne for ligne in ech['lignes']}
        pec_mois   = eleve.montant_pec_mensualite_mensuel
        mois_ecole = []
        if exercice:
            nb_total = exercice.nb_mensualites
            debut    = exercice.date_debut
            y, mo = debut.year, debut.month
            # Fenêtre affichée : les mois de l'exercice, plus tout mois facturé
            # qui tomberait au-delà (régime passager à cheval, mois saisis à la
            # main). Un mois dû mais non affiché serait impayable depuis ici.
            for i in range(12):
                ligne = par_mois.get(mo)
                if i < nb_total or ligne:
                    du    = float(ligne['du'])    if ligne else 0.0
                    paye  = float(ligne['paye'])  if ligne else 0.0
                    # La réduction ne s'applique qu'aux mois au tarif ordinaire :
                    # un montant saisi à la main POUR ce mois est le dû final,
                    # il ne se laisse pas réduire une seconde fois.
                    pec   = 0.0 if (ligne is None or ligne['montant_saisi']) else pec_mois
                    mois_ecole.append({
                        'num':     mo,
                        'annee':   ligne['annee'] if ligne else y,
                        'label':   MOIS_FR.get(mo, str(mo)),
                        # Facturé à CET élève : c'est l'échéancier qui le dit, et
                        # non plus un prorata recalculé ici qui ignorait les mois
                        # saisis par l'école.
                        'du':      bool(ligne),
                        'du_brut': round(du + pec, 2),
                        'pec':     round(pec, 2),
                        'montant': round(du, 2),
                        'verse':   round(paye, 2),
                        'reste':   round(float(ligne['reste']) if ligne else 0.0, 2),
                        # SOLDE / PARTIEL / IMPAYE — « payé » ne suffisait pas à
                        # distinguer un mois soldé d'un mois entamé.
                        'statut':  ligne['statut'] if ligne else '',
                        'paye':    bool(ligne) and ligne['statut'] == 'SOLDE',
                        'echu':    bool(ligne['echu']) if ligne else False,
                        'montant_saisi': bool(ligne and ligne['montant_saisi']),
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
            # La prise en charge, décomposée : ce que l'école FACTURE, ce qu'un
            # tiers (ou l'école elle-même) prend en charge, ce qui reste à la
            # famille. Le guichet ne voyait que le montant net : impossible de
            # répondre à un parent qui demande pourquoi on lui réclame 65 000
            # quand le tarif affiché est de 73 000.
            'pec': {
                'libelle':   eleve.prise_en_charge or '',
                'organisme': (eleve.pec_organisme.organisme.nom
                              if eleve.pec_organisme else ''),
                'inscription': {
                    'brut': fees_bruts['inscription'],
                    'pec':  eleve.montant_pec_inscription,
                    'net':  fees_nets['inscription'],
                },
                # Le mois ORDINAIRE, services mensuels compris : c'est le
                # montant que la famille reconnaît, pas la seule mensualité.
                'mensuel': {
                    'brut': round(eleve.du_mensuel_standard
                                  + eleve.montant_pec_mensualite_mensuel, 2),
                    'pec':  eleve.montant_pec_mensualite_mensuel,
                    'net':  eleve.du_mensuel_standard,
                },
                'annuel': {
                    'brut': round(total_annuel + eleve.montant_pec_annuel, 2),
                    'pec':  eleve.montant_pec_annuel,
                    'net':  total_annuel,
                },
            },
            # Montants
            'fees_bruts':    fees_bruts,
            'fees_nets':     fees_nets,
            'deja_paye':     deja_paye,
            'reste':         reste,
            # Résumé
            'total_annuel_net':  total_annuel,
            'total_paye':        total_paye,
            'total_restant':     round(max(total_annuel - total_paye, 0), 2),
            # Dette d'un exercice antérieur, encaissable sur ce même règlement.
            # Elle vit à part du dû de l'année : elle ne constate aucun produit
            # (voir apps.paiements.ecritures.lignes_paiement).
            'reliquat': {
                'annee':   eleve.reliquat_origine_libelle,
                'du':      round(float(eleve.reliquat_anterieur or 0), 2),
                'paye':    eleve.reliquat_paye,
                'restant': eleve.reliquat_restant,
            },
            'total_restant_global': round(max(total_annuel - total_paye, 0)
                                          + eleve.reliquat_restant, 2),
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

        # Variante NOMINATIVE : identité et dates seulement. C'est le document
        # qui circule — affiché, photocopié, passé entre des mains
        # d'enseignants et d'élèves. Y faire figurer ce que chaque famille doit
        # exposerait leur situation à tous ceux qui le lisent.
        # Ordre de sortie choisi par l'école : ses sections dans SON ordre,
        # ses classes, ou toute l'école en un seul fil d'ancienneté.
        groupe = request.query_params.get('tri') or 'section'

        if request.query_params.get('financier') in ('0', 'false', 'False', 'non'):
            contexte = contexte_liste_nominative(
                tenant, exercice,
                request.query_params.get('classe'),
                request.query_params.get('section'),
                groupe=groupe)
            html = render_to_string('pdf/liste_classe.html', contexte)
            buf = BytesIO()
            if pisa.CreatePDF(html, dest=buf, encoding='utf-8').err:
                return HttpResponse('Erreur génération PDF.', status=500)
            resp = HttpResponse(buf.getvalue(), content_type='application/pdf')
            resp['Content-Disposition'] = (
                f'attachment; filename="liste_eleves_{exercice.annee_scolaire}.pdf"')
            return resp

        # `precharger` : l'alerte de chaque élève vient désormais de son
        # échéancier, qui a besoin des paiements. Sans le préchargement, une
        # liste de 300 fiches ferait 300 requêtes de plus.
        from .echeancier import precharger
        qs = precharger(Eleve.objects.filter(
            tenant=tenant, exercice=exercice
        )).annotate(
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

        filtre_statut = request.query_params.get('statut', '')
        filtre_alerte = request.query_params.get('alerte', '')
        if filtre_statut:
            qs = qs.filter(statut=filtre_statut)
        else:
            # Même périmètre que la liste à l'écran : ni les sortis (diplômés,
            # transférés, abandons), ni les fiches de créance — qui ne sont pas
            # des élèves mais des porteuses d'ardoise. Les laisser gonflait
            # l'effectif du document et y faisait figurer des enfants partis
            # depuis des années. Un ?statut= explicite reste honoré.
            qs = qs.filter(fiche_creance=False).exclude(statut__in=STATUTS_SORTIE)

        eleves_data = []
        total_attendu_global = 0.0
        total_paye_global    = 0.0
        nb_critique = nb_urgent = nb_attention = nb_a_jour = 0

        # Même tri que la liste nominative : les deux documents doivent se
        # lire ligne à ligne l'un en face de l'autre.
        from .tri import trier

        for e in trier(qs, groupe):
            attendu = float(e.total_attendu)
            paye    = float(e.total_paye_sql or 0)
            reste   = round(max(0.0, attendu - paye), 0)
            alerte  = e.niveau_alerte

            if alerte == 'CRITIQUE':   nb_critique  += 1
            elif alerte == 'URGENT':   nb_urgent    += 1
            elif alerte == 'ATTENTION': nb_attention += 1
            else:                       nb_a_jour    += 1

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
            'nb_a_jour':         nb_a_jour,
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

        # total_p ne somme que les 6 catégories : le suivi ci-dessous porte
        # sur l'année en cours. La dette antérieure est présentée à part.
        total_paye   = sum(p['total'] for p in paiements_list)
        total_attendu = float(eleve.total_attendu)
        reste        = round(max(0.0, total_attendu - total_paye), 0)
        reliquat     = eleve.reliquat_restant

        # Détail mois par mois + synthèse : c'est ce que la famille lit en
        # premier. Sans lui, le document ne donnait qu'un total, inutilisable
        # pour un parent qui règle au mois.
        from .echeancier import NOMS_MOIS, construire_echeancier
        ech = construire_echeancier(eleve)
        for ligne in ech['lignes']:
            ligne['libelle'] = f"{NOMS_MOIS.get(ligne['mois'], ligne['mois'])} {ligne['annee']}"

        context = {
            'tenant':         tenant,
            'eleve':          eleve,
            'section_nom':    eleve.section.nom if eleve.section else '—',
            'exercice':       exercice,
            'date_edition':   timezone.now(),
            'paiements':      paiements_list,
            'echeancier':     ech['lignes'],
            'hors_mensualite': ech['hors_mensualite'],
            'ech_totaux':     ech['totaux'],
            'synthese':       ech['synthese'],
            'total_paye':     round(total_paye, 0),
            'total_attendu':  round(total_attendu, 0),
            'reste':          reste,
            # Reliquat d'un exercice antérieur — ce que la famille doit encore
            # au titre des années passées, en plus du reste de l'année.
            'reliquat_du':      round(float(eleve.reliquat_anterieur or 0), 0),
            'reliquat_restant': round(reliquat, 0),
            'reliquat_annee':   eleve.reliquat_origine_libelle,
            'reste_global':     round(reste + reliquat, 0),
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

        # Personnalisation du certificat : défauts = version standard complète,
        # surchargés par la config de l'école (Paramètres → Certificat).
        cfg = {
            'entete_ministere': True,   # bloc République / Ministère
            'reference':        True,   # ligne « Réf. N° »
            'matricule':        True,   # matricule + statut
            'naissance':        True,   # date et lieu de naissance
            'parents':          True,   # lignes père / mère
            'signature_parent': True,   # colonne signature parent/tuteur
            'cachet':           True,   # zone cachet de l'établissement
            'mention_validite': True,   # mention de validité en pied
            'texte_intro':      '',     # remplace le texte d'introduction standard
            'texte_conclusion': '',     # remplace la conclusion standard
        }
        cfg.update(getattr(tenant, 'config_certificat', None) or {})

        context = {
            'tenant':          tenant,
            'cfg':             cfg,
            'eleve':           eleve,
            'section_nom':     eleve.section.nom if eleve.section else '—',
            'annee_scolaire':  exercice.annee_scolaire if exercice else '—',
            'date_edition':    timezone.now(),
            'directeur_nom':   getattr(tenant, 'directeur_nom', '') or '',
            'tenant_ville':    getattr(tenant, 'ville', '') or '',
            'tenant_rccm':     getattr(tenant, 'rccm', '') or '',
            'tenant_autorisation': getattr(tenant, 'numero_autorisation', '') or '',
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


class ParcoursElevePDFView(APIView):
    """Dossier de scolarité : toutes les années de l'enfant sur une page.

    C'est le document qu'on remet à une famille qui part, ou qu'on ressort
    des archives pour un ancien élève — d'où la lecture continue plutôt
    qu'une photo de l'année en cours."""
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

        from .parcours import construire_parcours

        tenant = get_tenant(request)
        eleve = Eleve.objects.filter(tenant=tenant, id=eleve_id).first()
        if not eleve:
            return HttpResponse('Élève introuvable', status=404)

        html_str = render_to_string('pdf/parcours_eleve.html', {
            'tenant':       tenant,
            'p':            construire_parcours(eleve),
            'date_edition': timezone.now(),
        })
        buf    = BytesIO()
        result = pisa.CreatePDF(html_str, dest=buf, encoding='utf-8')
        if result.err:
            return HttpResponse('Erreur génération du parcours PDF.', status=500)

        response = HttpResponse(buf.getvalue(), content_type='application/pdf')
        safe_name = eleve.nom_complet.replace(' ', '_').replace('/', '-')
        response['Content-Disposition'] = f'inline; filename="parcours_{safe_name}.pdf"'
        return response
