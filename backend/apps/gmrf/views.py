"""Vues API du module GMRF (convention APIView, sérialisation manuelle)."""
import datetime
import re
from decimal import Decimal, InvalidOperation

from dateutil.relativedelta import relativedelta
from django.db.models import Max, Sum
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from core.tenant import get_tenant
from core.models import log_audit
from .models import (TypeFinancement, Financement, NattCycle,
                     NattCotisation, NattReception)
from . import services


# ── Types de financement par défaut (paramétrables ensuite par l'école) ──────
TYPES_DEFAUT = [
    ('DON',           'Don',                          'DON',           'PRODUIT',  '7588'),
    ('SUBV_EXPLOIT',  "Subvention d'exploitation",    'SUBV_EXPLOIT',  'PRODUIT',  '71'),
    ('SUBV_INVEST',   "Subvention d'investissement",  'SUBV_INVEST',   'CAPITAUX', '14'),
    ('PARTENARIAT',   'Partenariat financier',        'PARTENARIAT',   'PRODUIT',  '7588'),
    ('CROWDFUNDING',  'Financement participatif',     'CROWDFUNDING',  'PRODUIT',  '7588'),
    ('REVENU_EXCEPT', 'Revenu exceptionnel',          'REVENU_EXCEPT', 'PRODUIT',  '848'),
    ('NATT',          'NATT / Tontine',               'NATT',          'DETTE',    '4718'),
    ('AUTRE',         'Autre source de financement',  'AUTRE',         'PRODUIT',  '7588'),
]


def _seed_types(tenant):
    """Crée les types par défaut à la première utilisation (idempotent)."""
    if TypeFinancement.objects.filter(tenant=tenant).exists():
        return
    TypeFinancement.objects.bulk_create([
        TypeFinancement(tenant=tenant, code=code, libelle=lib, categorie=cat,
                        nature_comptable=nat, compte_ressource=cpt, est_systeme=True)
        for code, lib, cat, nat, cpt in TYPES_DEFAUT
    ])


def _d(v):
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _next_ref(tenant, model, prefix):
    last = model.objects.filter(tenant=tenant).aggregate(m=Max('reference'))['m']
    nums = re.findall(r'\d+', last or f'{prefix}-0000')
    n = int(nums[-1]) + 1 if nums else 1
    return f"{prefix}-{n:04d}"


# ── Types de financement ─────────────────────────────────────────────────────
def _type_to_dict(t):
    return {
        'id': str(t.id), 'code': t.code, 'libelle': t.libelle,
        'categorie': t.categorie, 'categorie_label': t.get_categorie_display(),
        'nature_comptable': t.nature_comptable,
        'compte_ressource': t.compte_ressource,
        'compte_tresorerie_defaut': t.compte_tresorerie_defaut,
        'description': t.description, 'est_actif': t.est_actif,
        'est_systeme': t.est_systeme,
    }


class TypeFinancementView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_tenant(request)
        _seed_types(tenant)
        qs = TypeFinancement.objects.filter(tenant=tenant)
        return Response([_type_to_dict(t) for t in qs])

    def post(self, request):
        tenant = get_tenant(request)
        d = request.data
        libelle = (d.get('libelle') or '').strip()
        if not libelle:
            return Response({'error': 'Libellé requis'}, status=400)
        code = (d.get('code') or libelle).strip().upper().replace(' ', '_')[:30]
        t = TypeFinancement.objects.create(
            tenant=tenant, code=code, libelle=libelle,
            categorie=d.get('categorie', 'AUTRE'),
            nature_comptable=d.get('nature_comptable', 'PRODUIT'),
            compte_ressource=d.get('compte_ressource', '7588'),
            compte_tresorerie_defaut=d.get('compte_tresorerie_defaut', '571'),
            description=d.get('description', ''),
        )
        log_audit(request, 'CREATION', 'TypeFinancement', t.id, libelle)
        return Response(_type_to_dict(t), status=201)

    def patch(self, request, pk):
        tenant = get_tenant(request)
        try:
            t = TypeFinancement.objects.get(tenant=tenant, id=pk)
        except TypeFinancement.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)
        for f in ('libelle', 'categorie', 'nature_comptable', 'compte_ressource',
                  'compte_tresorerie_defaut', 'description', 'est_actif'):
            if f in request.data:
                setattr(t, f, request.data[f])
        t.save()
        return Response(_type_to_dict(t))

    def delete(self, request, pk):
        tenant = get_tenant(request)
        try:
            t = TypeFinancement.objects.get(tenant=tenant, id=pk)
        except TypeFinancement.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)
        if t.est_systeme:
            return Response({'error': 'Type système non supprimable'}, status=400)
        if t.financements.exists():
            return Response({'error': 'Type utilisé par des financements'}, status=400)
        t.delete()
        return Response(status=204)


# ── Financements simples ─────────────────────────────────────────────────────
def _fin_to_dict(f):
    return {
        'id': str(f.id), 'reference': f.reference,
        'type_financement': str(f.type_financement_id),
        'type_libelle': f.type_financement.libelle,
        'categorie': f.type_financement.categorie,
        'libelle': f.libelle, 'source': f.source, 'type_source': f.type_source,
        'coordonnees': f.coordonnees, 'montant': float(f.montant), 'devise': f.devise,
        'date_reception': str(f.date_reception) if f.date_reception else None,
        'compte_tresorerie': f.compte_tresorerie, 'compte_ressource': f.compte_ressource,
        'statut': f.statut, 'observations': f.observations, 'documents': f.documents,
    }


class FinancementView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        tenant = get_tenant(request)
        if pk:
            try:
                return Response(_fin_to_dict(Financement.objects.get(tenant=tenant, id=pk)))
            except Financement.DoesNotExist:
                return Response({'error': 'Non trouvé'}, status=404)
        qs = Financement.objects.filter(tenant=tenant).select_related('type_financement')
        cat = request.query_params.get('categorie')
        if cat:
            qs = qs.filter(type_financement__categorie=cat)
        lignes = [_fin_to_dict(f) for f in qs]
        total_recu = sum(l['montant'] for l in lignes if l['statut'] == 'RECU')
        total_attendu = sum(l['montant'] for l in lignes if l['statut'] == 'ATTENDU')
        return Response({
            'financements': lignes,
            'synthese': {'total_recu': round(total_recu, 2),
                         'total_attendu': round(total_attendu, 2),
                         'nombre': len(lignes)},
        })

    @transaction.atomic
    def post(self, request):
        tenant = get_tenant(request)
        d = request.data
        montant = _d(d.get('montant'))
        if montant is None or montant <= 0:
            return Response({'error': 'Montant invalide'}, status=400)
        try:
            tf = TypeFinancement.objects.get(tenant=tenant, id=d.get('type_financement'))
        except (TypeFinancement.DoesNotExist, ValueError):
            return Response({'error': 'Type de financement invalide'}, status=400)

        statut = d.get('statut', 'ATTENDU')
        f = Financement.objects.create(
            tenant=tenant, reference=_next_ref(tenant, Financement, 'GRF'),
            type_financement=tf, libelle=(d.get('libelle') or tf.libelle).strip(),
            source=d.get('source', ''), type_source=d.get('type_source', 'AUTRE'),
            coordonnees=d.get('coordonnees', ''), montant=montant,
            devise=d.get('devise', 'XOF'),
            date_reception=d.get('date_reception') or (datetime.date.today() if statut == 'RECU' else None),
            compte_tresorerie=d.get('compte_tresorerie', tf.compte_tresorerie_defaut),
            compte_ressource=d.get('compte_ressource', tf.compte_ressource),
            statut=statut, observations=d.get('observations', ''),
            documents=d.get('documents', []),
        )
        if f.statut == 'RECU':
            services.generer_ecriture_financement(f, tenant)
        log_audit(request, 'CREATION', 'Financement', f.id, f.libelle)
        return Response(_fin_to_dict(f), status=201)

    @transaction.atomic
    def patch(self, request, pk):
        """Encaisser / annuler un financement."""
        tenant = get_tenant(request)
        try:
            f = Financement.objects.get(tenant=tenant, id=pk)
        except Financement.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)

        action = request.data.get('action')
        if action == 'encaisser' and f.statut == 'ATTENDU':
            f.statut = 'RECU'
            f.date_reception = request.data.get('date_reception') or datetime.date.today()
            if request.data.get('compte_tresorerie'):
                f.compte_tresorerie = request.data['compte_tresorerie']
            f.save()
            services.generer_ecriture_financement(f, tenant)
        elif action == 'annuler' and f.statut == 'RECU':
            services.annuler_ecriture_financement(f, tenant)
            f.statut = 'ANNULE'
            f.save()
        else:
            return Response({'error': 'Action invalide pour ce statut'}, status=400)
        log_audit(request, 'MODIFICATION', 'Financement', f.id, action)
        return Response(_fin_to_dict(f))


# ── NATT / Tontine ───────────────────────────────────────────────────────────
_PERIODE_DELTA = {
    'HEBDOMADAIRE': relativedelta(weeks=1),
    'MENSUELLE':    relativedelta(months=1),
    'TRIMESTRIELLE': relativedelta(months=3),
}


def _cotis_to_dict(c):
    return {
        'id': str(c.id), 'numero': c.numero, 'date_echeance': str(c.date_echeance),
        'montant': float(c.montant), 'statut': c.statut,
        'date_paiement': str(c.date_paiement) if c.date_paiement else None,
    }


def _cycle_to_dict(cycle, detail=False):
    cotis = list(cycle.cotisations.all())
    payees = [c for c in cotis if c.statut == 'PAYE']
    total_verse = sum(float(c.montant) for c in payees)
    reception = getattr(cycle, 'reception', None)
    montant_recu = float(reception.montant_recu) if reception else 0.0
    nb = len(cotis) or cycle.duree or 1
    data = {
        'id': str(cycle.id), 'reference': cycle.reference, 'nom': cycle.nom,
        'organisateur': cycle.organisateur, 'type_organisateur': cycle.type_organisateur,
        'nb_participants': cycle.nb_participants, 'duree': cycle.duree,
        'periodicite': cycle.periodicite,
        'montant_cotisation': float(cycle.montant_cotisation),
        'montant_cagnotte': cycle.montant_cagnotte,
        'total_a_cotiser': cycle.total_a_cotiser,
        'mode_attribution': cycle.mode_attribution,
        'date_debut': str(cycle.date_debut),
        'date_fin': str(cycle.date_fin) if cycle.date_fin else None,
        'compte_tresorerie': cycle.compte_tresorerie,
        'compte_creance': cycle.compte_creance, 'compte_dette': cycle.compte_dette,
        'devise': cycle.devise, 'statut': cycle.statut,
        'observations': cycle.observations,
        # Tableau de suivi
        'nb_cotisations_payees': len(payees),
        'nb_cotisations_restantes': len(cotis) - len(payees),
        'total_verse': round(total_verse, 2),
        'reste_a_verser': round(cycle.total_a_cotiser - total_verse, 2),
        'montant_recu': montant_recu,
        'cagnotte_recue': reception is not None,
        'numero_echeance_reception': reception.numero_echeance if reception else None,
        'pourcentage_avancement': round(100 * len(payees) / nb, 1),
    }
    if detail:
        data['cotisations'] = [_cotis_to_dict(c) for c in cotis]
        data['reception'] = ({
            'id': str(reception.id), 'numero_echeance': reception.numero_echeance,
            'date_reception': str(reception.date_reception),
            'montant_recu': float(reception.montant_recu),
            'compte_tresorerie': reception.compte_tresorerie,
            'montant_creance_soldee': float(reception.montant_creance_soldee),
            'montant_dette': float(reception.montant_dette),
        } if reception else None)
    return data


class NattCycleView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        tenant = get_tenant(request)
        if pk:
            try:
                cycle = NattCycle.objects.prefetch_related('cotisations').get(tenant=tenant, id=pk)
                return Response(_cycle_to_dict(cycle, detail=True))
            except NattCycle.DoesNotExist:
                return Response({'error': 'Non trouvé'}, status=404)
        qs = NattCycle.objects.filter(tenant=tenant).prefetch_related('cotisations')
        return Response([_cycle_to_dict(c) for c in qs])

    @transaction.atomic
    def post(self, request):
        """Crée un cycle NATT et génère automatiquement l'échéancier de cotisations."""
        tenant = get_tenant(request)
        d = request.data
        montant = _d(d.get('montant_cotisation'))
        try:
            duree = int(d.get('duree'))
        except (TypeError, ValueError):
            return Response({'error': 'Durée invalide'}, status=400)
        if montant is None or montant <= 0 or duree <= 0:
            return Response({'error': 'Cotisation et durée doivent être > 0'}, status=400)
        date_debut = d.get('date_debut')
        if not date_debut:
            return Response({'error': 'Date de début requise'}, status=400)

        periodicite = d.get('periodicite', 'MENSUELLE')
        delta = _PERIODE_DELTA.get(periodicite, _PERIODE_DELTA['MENSUELLE'])
        d0 = datetime.date.fromisoformat(str(date_debut))
        date_fin = d0 + delta * (duree - 1)

        cycle = NattCycle.objects.create(
            tenant=tenant, reference=_next_ref(tenant, NattCycle, 'NATT'),
            nom=(d.get('nom') or 'NATT').strip(), organisateur=d.get('organisateur', ''),
            type_organisateur=d.get('type_organisateur', 'AUTRE'),
            coordonnees=d.get('coordonnees', ''),
            nb_participants=int(d.get('nb_participants') or 0), duree=duree,
            periodicite=periodicite, montant_cotisation=montant,
            mode_attribution=d.get('mode_attribution', 'TIRAGE'),
            date_debut=d0, date_fin=date_fin,
            compte_tresorerie=d.get('compte_tresorerie', '571'),
            compte_creance=d.get('compte_creance', '4718'),
            compte_dette=d.get('compte_dette', '4798'),
            devise=d.get('devise', 'XOF'), observations=d.get('observations', ''),
            documents=d.get('documents', []),
        )
        # Échéancier automatique
        NattCotisation.objects.bulk_create([
            NattCotisation(tenant=tenant, cycle=cycle, numero=i,
                           date_echeance=d0 + delta * (i - 1), montant=montant)
            for i in range(1, duree + 1)
        ])
        log_audit(request, 'CREATION', 'NattCycle', cycle.id, cycle.nom)
        cycle = NattCycle.objects.prefetch_related('cotisations').get(id=cycle.id)
        return Response(_cycle_to_dict(cycle, detail=True), status=201)


class NattCotisationView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def patch(self, request, pk):
        """Payer ou annuler une cotisation."""
        tenant = get_tenant(request)
        try:
            c = NattCotisation.objects.select_related('cycle').get(tenant=tenant, id=pk)
        except NattCotisation.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)

        action = request.data.get('action')
        if action == 'payer' and c.statut != 'PAYE':
            c.statut = 'PAYE'
            c.date_paiement = request.data.get('date_paiement') or datetime.date.today()
            c.compte_tresorerie = request.data.get('compte_tresorerie', '') or c.cycle.compte_tresorerie
            c.save()
            services.generer_ecriture_cotisation(c, tenant)
        elif action == 'annuler' and c.statut == 'PAYE':
            services.annuler_ecriture_cotisation(c, tenant)
            c.statut = 'A_PAYER'
            c.date_paiement = None
            c.save()
        else:
            return Response({'error': 'Action invalide pour ce statut'}, status=400)
        log_audit(request, 'MODIFICATION', 'NattCotisation', c.id, action)
        return Response(_cotis_to_dict(c))


class NattReceptionView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        """Enregistre la réception de la cagnotte pour un cycle (pk = cycle)."""
        tenant = get_tenant(request)
        try:
            cycle = NattCycle.objects.get(tenant=tenant, id=pk)
        except NattCycle.DoesNotExist:
            return Response({'error': 'Cycle non trouvé'}, status=404)
        if NattReception.objects.filter(tenant=tenant, cycle=cycle).exists():
            return Response({'error': 'Cagnotte déjà reçue pour ce cycle'}, status=400)

        d = request.data
        try:
            numero = int(d.get('numero_echeance'))
        except (TypeError, ValueError):
            return Response({'error': "Numéro d'échéance invalide"}, status=400)
        montant = _d(d.get('montant_recu')) or _d(cycle.montant_cagnotte)
        if montant is None or montant <= 0:
            return Response({'error': 'Montant reçu invalide'}, status=400)

        reception = NattReception.objects.create(
            tenant=tenant, cycle=cycle, numero_echeance=numero,
            date_reception=d.get('date_reception') or datetime.date.today(),
            montant_recu=montant,
            compte_tresorerie=d.get('compte_tresorerie', cycle.compte_tresorerie),
            observations=d.get('observations', ''),
        )
        services.generer_ecriture_reception(reception, tenant)
        log_audit(request, 'CREATION', 'NattReception', reception.id, cycle.reference)
        cycle = NattCycle.objects.prefetch_related('cotisations').get(id=cycle.id)
        return Response(_cycle_to_dict(cycle, detail=True), status=201)


# ── Tableau de bord GMRF ─────────────────────────────────────────────────────
class DashboardGMRFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_tenant(request)
        fins = Financement.objects.filter(tenant=tenant)
        total_dons = sum(float(f.montant) for f in fins
                         if f.statut == 'RECU' and f.type_financement.categorie == 'DON')
        total_subv = sum(float(f.montant) for f in fins
                         if f.statut == 'RECU' and f.type_financement.categorie in ('SUBV_INVEST', 'SUBV_EXPLOIT'))
        total_autres = sum(float(f.montant) for f in fins if f.statut == 'RECU') - total_dons - total_subv

        cycles = NattCycle.objects.filter(tenant=tenant).prefetch_related('cotisations', 'reception')
        natt_en_cours = [c for c in cycles if c.statut == 'EN_COURS']

        # Échéances de cotisation à venir (30 jours)
        horizon = datetime.date.today() + datetime.timedelta(days=30)
        echeances = NattCotisation.objects.filter(
            tenant=tenant, statut__in=['A_PAYER', 'EN_RETARD'],
            date_echeance__lte=horizon,
        ).select_related('cycle').order_by('date_echeance')[:20]

        return Response({
            'ressources': {
                'total_dons': round(total_dons, 2),
                'total_subventions': round(total_subv, 2),
                'total_autres': round(total_autres, 2),
                'total_mobilise': round(total_dons + total_subv + total_autres, 2),
            },
            'natt': {
                'nombre_en_cours': len(natt_en_cours),
                'total_verse': round(sum(_cycle_to_dict(c)['total_verse'] for c in natt_en_cours), 2),
                'total_recu': round(sum(_cycle_to_dict(c)['montant_recu'] for c in natt_en_cours), 2),
            },
            'echeances_a_venir': [{
                'cycle': e.cycle.reference, 'nom': e.cycle.nom,
                'numero': e.numero, 'date_echeance': str(e.date_echeance),
                'montant': float(e.montant),
                'en_retard': e.date_echeance < datetime.date.today(),
            } for e in echeances],
        })
