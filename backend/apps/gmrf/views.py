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
                     NattCotisation, NattReception, Pret, PretEcheance)
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
        data['documents'] = cycle.documents or []
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


# ── Prêts ────────────────────────────────────────────────────────────────────
_PRET_PERIODE_DELTA = {
    'MENSUELLE':     relativedelta(months=1),
    'TRIMESTRIELLE': relativedelta(months=3),
    'SEMESTRIELLE':  relativedelta(months=6),
    'ANNUELLE':      relativedelta(years=1),
}


def _echeance_to_dict(e):
    return {
        'id': str(e.id), 'numero': e.numero, 'date_echeance': str(e.date_echeance),
        'capital_debut': float(e.capital_debut), 'montant_echeance': float(e.montant_echeance),
        'part_capital': float(e.part_capital), 'part_interet': float(e.part_interet),
        'capital_fin': float(e.capital_fin), 'penalite': float(e.penalite),
        'statut': e.statut, 'date_paiement': str(e.date_paiement) if e.date_paiement else None,
    }


def _pret_to_dict(pret, detail=False):
    echs = list(pret.echeances.all())
    payees = [e for e in echs if e.statut == 'PAYE']
    capital_rembourse = sum(float(e.part_capital) for e in payees)
    interets_payes = sum(float(e.part_interet) for e in payees)
    capital_restant = round(float(pret.montant) - capital_rembourse, 2)
    total_interets = sum(float(e.part_interet) for e in echs)
    data = {
        'id': str(pret.id), 'reference': pret.reference, 'type_pret': pret.type_pret,
        'type_label': pret.get_type_pret_display(), 'organisme_preteur': pret.organisme_preteur,
        'objet': pret.objet, 'montant': float(pret.montant), 'devise': pret.devise,
        'taux_interet': float(pret.taux_interet), 'duree_mois': pret.duree_mois,
        'periodicite': pret.periodicite, 'mode_amortissement': pret.mode_amortissement,
        'date_deblocage': str(pret.date_deblocage),
        'frais_dossier': float(pret.frais_dossier),
        'compte_tresorerie': pret.compte_tresorerie, 'compte_emprunt': pret.compte_emprunt,
        'compte_interets': pret.compte_interets, 'compte_frais': pret.compte_frais,
        'compte_penalites': pret.compte_penalites,
        'garanties': pret.garanties, 'observations': pret.observations, 'statut': pret.statut,
        'nb_echeances': pret.nb_echeances,
        # Synthèse
        'nb_echeances_payees': len(payees),
        'capital_rembourse': round(capital_rembourse, 2),
        'capital_restant_du': capital_restant,
        'interets_payes': round(interets_payes, 2),
        'total_interets': round(total_interets, 2),
        'cout_total_credit': round(float(pret.montant) + total_interets + float(pret.frais_dossier), 2),
        'pourcentage_rembourse': round(100 * capital_rembourse / float(pret.montant), 1) if pret.montant else 0,
    }
    if detail:
        data['echeances'] = [_echeance_to_dict(e) for e in echs]
        data['documents'] = pret.documents or []
    return data


class PretView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        tenant = get_tenant(request)
        if pk:
            try:
                pret = Pret.objects.prefetch_related('echeances').get(tenant=tenant, id=pk)
                return Response(_pret_to_dict(pret, detail=True))
            except Pret.DoesNotExist:
                return Response({'error': 'Non trouvé'}, status=404)
        qs = Pret.objects.filter(tenant=tenant).prefetch_related('echeances')
        lignes = [_pret_to_dict(p) for p in qs]
        return Response({
            'prets': lignes,
            'synthese': {
                'nombre': len(lignes),
                'capital_emprunte': round(sum(l['montant'] for l in lignes), 2),
                'capital_restant_du': round(sum(l['capital_restant_du'] for l in lignes
                                                 if l['statut'] == 'EN_COURS'), 2),
            },
        })

    def post(self, request):
        """Simulation du tableau d'amortissement sans enregistrement (aperçu)."""
        d = request.data
        if d.get('action') != 'simuler':
            return self._creer(request)
        rows = services.calcul_amortissement(
            d.get('montant', 0), d.get('taux_interet', 0),
            self._nb(d), d.get('periodicite', 'MENSUELLE'),
            d.get('mode_amortissement', 'CONSTANT'))
        return Response({'echeances': [{k: float(v) if k != 'numero' else v
                                        for k, v in r.items()} for r in rows]})

    @staticmethod
    def _nb(d):
        mois_par_periode = {'MENSUELLE': 1, 'TRIMESTRIELLE': 3, 'SEMESTRIELLE': 6, 'ANNUELLE': 12}
        pas = mois_par_periode.get(d.get('periodicite', 'MENSUELLE'), 1)
        try:
            return max(1, round(int(d.get('duree_mois', 0)) / pas))
        except (TypeError, ValueError):
            return 0

    @transaction.atomic
    def _creer(self, request):
        tenant = get_tenant(request)
        d = request.data
        montant = _d(d.get('montant'))
        try:
            duree = int(d.get('duree_mois'))
        except (TypeError, ValueError):
            return Response({'error': 'Durée invalide'}, status=400)
        if montant is None or montant <= 0 or duree <= 0:
            return Response({'error': 'Montant et durée doivent être > 0'}, status=400)
        if not d.get('organisme_preteur'):
            return Response({'error': 'Organisme prêteur requis'}, status=400)
        date_deblocage = d.get('date_deblocage')
        if not date_deblocage:
            return Response({'error': 'Date de déblocage requise'}, status=400)

        periodicite = d.get('periodicite', 'MENSUELLE')
        pret = Pret.objects.create(
            tenant=tenant, reference=_next_ref(tenant, Pret, 'PRET'),
            type_pret=d.get('type_pret', 'BANCAIRE'),
            organisme_preteur=d.get('organisme_preteur', '').strip(),
            objet=d.get('objet', ''), montant=montant, devise=d.get('devise', 'XOF'),
            taux_interet=_d(d.get('taux_interet', 0)), duree_mois=duree,
            periodicite=periodicite, mode_amortissement=d.get('mode_amortissement', 'CONSTANT'),
            date_deblocage=date_deblocage,
            date_premiere_echeance=d.get('date_premiere_echeance') or None,
            frais_dossier=_d(d.get('frais_dossier', 0)),
            compte_tresorerie=d.get('compte_tresorerie', '521'),
            compte_emprunt=d.get('compte_emprunt', '162'),
            compte_interets=d.get('compte_interets', '671'),
            compte_frais=d.get('compte_frais', '6312'),
            compte_penalites=d.get('compte_penalites', '6718'),
            garanties=d.get('garanties', ''), observations=d.get('observations', ''),
            documents=d.get('documents', []),
        )

        # Tableau d'amortissement + dates
        delta = _PRET_PERIODE_DELTA.get(periodicite, _PRET_PERIODE_DELTA['MENSUELLE'])
        d0 = datetime.date.fromisoformat(str(pret.date_premiere_echeance or date_deblocage))
        rows = services.calcul_amortissement(montant, pret.taux_interet, pret.nb_echeances,
                                             periodicite, pret.mode_amortissement)
        PretEcheance.objects.bulk_create([
            PretEcheance(tenant=tenant, pret=pret, numero=r['numero'],
                         date_echeance=d0 + delta * (r['numero'] - 1),
                         capital_debut=r['capital_debut'], montant_echeance=r['montant_echeance'],
                         part_capital=r['part_capital'], part_interet=r['part_interet'],
                         capital_fin=r['capital_fin'])
            for r in rows
        ])
        # Déblocage des fonds
        services.generer_ecriture_deblocage_pret(pret, tenant)
        log_audit(request, 'CREATION', 'Pret', pret.id, pret.organisme_preteur)
        pret = Pret.objects.prefetch_related('echeances').get(id=pret.id)
        return Response(_pret_to_dict(pret, detail=True), status=201)


class PretEcheanceView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def patch(self, request, pk):
        """Payer / annuler une échéance de prêt."""
        tenant = get_tenant(request)
        try:
            e = PretEcheance.objects.select_related('pret').get(tenant=tenant, id=pk)
        except PretEcheance.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)

        action = request.data.get('action')
        if action == 'payer' and e.statut != 'PAYE':
            penalite = _d(request.data.get('penalite', 0)) or Decimal('0')
            e.penalite = penalite
            e.statut = 'PAYE'
            e.date_paiement = request.data.get('date_paiement') or datetime.date.today()
            e.save()
            services.generer_ecriture_echeance(e, tenant)
            # Prêt soldé ?
            if not e.pret.echeances.exclude(statut='PAYE').exists():
                e.pret.statut = 'SOLDE'
                e.pret.save(update_fields=['statut', 'updated_at'])
        elif action == 'annuler' and e.statut == 'PAYE':
            services.annuler_ecriture_echeance(e, tenant)
            e.statut = 'A_PAYER'
            e.date_paiement = None
            e.penalite = 0
            e.save()
            if e.pret.statut == 'SOLDE':
                e.pret.statut = 'EN_COURS'
                e.pret.save(update_fields=['statut', 'updated_at'])
        else:
            return Response({'error': 'Action invalide pour ce statut'}, status=400)
        log_audit(request, 'MODIFICATION', 'PretEcheance', e.id, action)
        return Response(_echeance_to_dict(e))


# ── Documents joints (base64) sur les entités GMRF ───────────────────────────
class DocumentsView(APIView):
    permission_classes = [IsAuthenticated]

    MODELS = {'financement': Financement, 'natt': NattCycle, 'pret': Pret}
    MAX_DOCS = 15
    MAX_TAILLE = 6_000_000  # ~6 Mo par document (base64)

    def _get(self, request, type, pk):
        model = self.MODELS.get(type)
        if not model:
            return None, Response({'error': 'Type inconnu'}, status=400)
        try:
            return model.objects.get(tenant=get_tenant(request), id=pk), None
        except model.DoesNotExist:
            return None, Response({'error': 'Non trouvé'}, status=404)

    def post(self, request, type, pk):
        """Ajoute un document {nom, data} (data = data URI base64)."""
        obj, err = self._get(request, type, pk)
        if err:
            return err
        nom = (request.data.get('nom') or 'document').strip()[:120]
        data = request.data.get('data') or ''
        if not data.startswith('data:'):
            return Response({'error': 'Format de fichier invalide'}, status=400)
        if len(data) > self.MAX_TAILLE:
            return Response({'error': 'Fichier trop volumineux (max ~4 Mo)'}, status=400)
        docs = list(obj.documents or [])
        if len(docs) >= self.MAX_DOCS:
            return Response({'error': f'Maximum {self.MAX_DOCS} documents'}, status=400)
        docs.append({'nom': nom, 'data': data})
        obj.documents = docs
        obj.save(update_fields=['documents', 'updated_at'])
        log_audit(request, 'MODIFICATION', model_name(obj), obj.id, f'+ document {nom}')
        return Response({'documents': [{'nom': d.get('nom')} for d in docs]}, status=201)

    def delete(self, request, type, pk):
        """Supprime le document à l'index ?index=."""
        obj, err = self._get(request, type, pk)
        if err:
            return err
        try:
            idx = int(request.query_params.get('index'))
        except (TypeError, ValueError):
            return Response({'error': 'Index invalide'}, status=400)
        docs = list(obj.documents or [])
        if not 0 <= idx < len(docs):
            return Response({'error': 'Index hors limites'}, status=400)
        docs.pop(idx)
        obj.documents = docs
        obj.save(update_fields=['documents', 'updated_at'])
        return Response({'documents': [{'nom': d.get('nom')} for d in docs]})


def model_name(obj):
    return obj.__class__.__name__


# ── Retards : bascule A_PAYER -> EN_RETARD pour les échéances dépassées ───────
def _maj_retards(tenant):
    today = datetime.date.today()
    NattCotisation.objects.filter(
        tenant=tenant, statut='A_PAYER', date_echeance__lt=today).update(statut='EN_RETARD')
    PretEcheance.objects.filter(
        tenant=tenant, statut='A_PAYER', date_echeance__lt=today).update(statut='EN_RETARD')


_MOIS_FR = ['jan', 'fév', 'mar', 'avr', 'mai', 'juin', 'juil', 'aoû', 'sep', 'oct', 'nov', 'déc']


def _mois_key(d):
    return f"{d.year}-{d.month:02d}"


def _mois_label(annee, mois):
    return f"{_MOIS_FR[mois - 1]} {str(annee)[2:]}"


def _serie_mois(depart, n):
    """Liste ordonnée de n mois consécutifs à partir de `depart` (1er du mois)."""
    base = depart.replace(day=1)
    return [base + relativedelta(months=i) for i in range(n)]


# ── Tableau de bord GMRF ─────────────────────────────────────────────────────
class DashboardGMRFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_tenant(request)
        _maj_retards(tenant)
        fins = Financement.objects.filter(tenant=tenant)
        total_dons = sum(float(f.montant) for f in fins
                         if f.statut == 'RECU' and f.type_financement.categorie == 'DON')
        total_subv = sum(float(f.montant) for f in fins
                         if f.statut == 'RECU' and f.type_financement.categorie in ('SUBV_INVEST', 'SUBV_EXPLOIT'))
        total_autres = sum(float(f.montant) for f in fins if f.statut == 'RECU') - total_dons - total_subv

        cycles = NattCycle.objects.filter(tenant=tenant).prefetch_related('cotisations', 'reception')
        natt_en_cours = [c for c in cycles if c.statut == 'EN_COURS']

        # Prêts
        prets = Pret.objects.filter(tenant=tenant).prefetch_related('echeances')
        prets_en_cours = [p for p in prets if p.statut == 'EN_COURS']
        capital_restant = round(sum(_pret_to_dict(p)['capital_restant_du'] for p in prets_en_cours), 2)
        montant_emprunte = round(sum(float(p.montant) for p in prets), 2)

        # Échéances à venir (30 jours) : cotisations NATT + échéances de prêt
        today = datetime.date.today()
        horizon = today + datetime.timedelta(days=30)
        cotis = NattCotisation.objects.filter(
            tenant=tenant, statut__in=['A_PAYER', 'EN_RETARD'], date_echeance__lte=horizon,
        ).select_related('cycle').order_by('date_echeance')[:20]
        pret_echs = PretEcheance.objects.filter(
            tenant=tenant, statut__in=['A_PAYER', 'EN_RETARD'], date_echeance__lte=horizon,
        ).select_related('pret').order_by('date_echeance')[:20]

        echeances_a_venir = [{
            'type': 'NATT', 'reference': e.cycle.reference, 'nom': e.cycle.nom,
            'numero': e.numero, 'date_echeance': str(e.date_echeance),
            'montant': float(e.montant), 'en_retard': e.date_echeance < today,
        } for e in cotis] + [{
            'type': 'PRET', 'reference': e.pret.reference, 'nom': e.pret.organisme_preteur,
            'numero': e.numero, 'date_echeance': str(e.date_echeance),
            'montant': float(e.montant_echeance), 'en_retard': e.date_echeance < today,
        } for e in pret_echs]
        echeances_a_venir.sort(key=lambda x: x['date_echeance'])

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
            'prets': {
                'nombre_en_cours': len(prets_en_cours),
                'montant_emprunte': montant_emprunte,
                'capital_restant_du': capital_restant,
            },
            'echeances_a_venir': echeances_a_venir[:25],
        })


# ── Analyse décisionnelle : ratios, graphiques, alertes ──────────────────────
class AnalyseGMRFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_tenant(request)
        _maj_retards(tenant)
        today = datetime.date.today()

        fins = list(Financement.objects.filter(tenant=tenant, statut='RECU').select_related('type_financement'))
        prets = list(Pret.objects.filter(tenant=tenant).prefetch_related('echeances'))
        cycles = list(NattCycle.objects.filter(tenant=tenant).prefetch_related('cotisations', 'reception'))

        # ── Répartition des ressources par catégorie ──
        CATS = {
            'DON': 'Dons', 'SUBV_INVEST': "Subv. investissement", 'SUBV_EXPLOIT': "Subv. exploitation",
            'PARTENARIAT': 'Partenariats', 'CROWDFUNDING': 'Crowdfunding',
            'REVENU_EXCEPT': 'Revenus exceptionnels', 'AUTRE': 'Autres',
        }
        repartition = {k: 0.0 for k in CATS}
        for f in fins:
            cat = f.type_financement.categorie
            repartition[cat if cat in repartition else 'AUTRE'] += float(f.montant)
        # Prêts et NATT comme sources de financement mobilisées
        total_prets = round(sum(float(p.montant) for p in prets), 2)
        total_natt_recu = round(sum(float(c.reception.montant_recu)
                                    for c in cycles if getattr(c, 'reception', None)), 2)
        repartition_list = [{'categorie': lbl, 'montant': round(repartition[k], 2)}
                            for k, lbl in CATS.items() if repartition[k] > 0]
        if total_prets > 0:
            repartition_list.append({'categorie': 'Prêts', 'montant': total_prets})
        if total_natt_recu > 0:
            repartition_list.append({'categorie': 'NATT / Tontine', 'montant': total_natt_recu})
        repartition_list.sort(key=lambda x: -x['montant'])

        total_finance_recu = round(sum(float(f.montant) for f in fins), 2)
        ressources_mobilisees = round(total_finance_recu + total_prets + total_natt_recu, 2)

        # ── Ratios financiers ──
        capital_restant_prets = round(sum(_pret_to_dict(p)['capital_restant_du']
                                          for p in prets if p.statut == 'EN_COURS'), 2)
        dette_natt = round(sum(_cycle_to_dict(c)['reste_a_verser']
                               for c in cycles if getattr(c, 'reception', None) and c.statut == 'EN_COURS'), 2)
        dette_totale = round(capital_restant_prets + dette_natt, 2)
        interets_previsionnels = round(sum(float(e.part_interet) for p in prets
                                           if p.statut == 'EN_COURS' for e in p.echeances.all()), 2)
        base = ressources_mobilisees or 1
        ratios = {
            'ressources_mobilisees': ressources_mobilisees,
            'dette_totale': dette_totale,
            'capital_restant_prets': capital_restant_prets,
            'dette_natt': dette_natt,
            'taux_endettement': round(100 * dette_totale / base, 1),
            'part_financement_externe': round(100 * (total_prets + total_natt_recu) / base, 1),
            'interets_previsionnels': interets_previsionnels,
            'cout_dette': round(100 * interets_previsionnels / (capital_restant_prets or 1), 1),
        }

        # ── Évolution mensuelle des ressources mobilisées (12 derniers mois) ──
        mois_passes = _serie_mois(today - relativedelta(months=11), 12)
        evo = {_mois_key(m): 0.0 for m in mois_passes}
        for f in fins:
            if f.date_reception and _mois_key(f.date_reception) in evo:
                evo[_mois_key(f.date_reception)] += float(f.montant)
        for p in prets:
            if _mois_key(p.date_deblocage) in evo:
                evo[_mois_key(p.date_deblocage)] += float(p.montant)
        for c in cycles:
            r = getattr(c, 'reception', None)
            if r and _mois_key(r.date_reception) in evo:
                evo[_mois_key(r.date_reception)] += float(r.montant_recu)
        evolution = [{'mois': _mois_label(m.year, m.month), 'montant': round(evo[_mois_key(m)], 2)}
                     for m in mois_passes]

        # ── Échéancier de remboursement à venir (12 prochains mois) ──
        mois_futurs = _serie_mois(today, 12)
        ech = {_mois_key(m): 0.0 for m in mois_futurs}
        for p in prets:
            for e in p.echeances.all():
                if e.statut != 'PAYE' and _mois_key(e.date_echeance) in ech:
                    ech[_mois_key(e.date_echeance)] += float(e.montant_echeance)
        for c in cycles:
            for co in c.cotisations.all():
                if co.statut != 'PAYE' and _mois_key(co.date_echeance) in ech:
                    ech[_mois_key(co.date_echeance)] += float(co.montant)
        echeancier = [{'mois': _mois_label(m.year, m.month), 'montant': round(ech[_mois_key(m)], 2)}
                      for m in mois_futurs]

        # ── Alertes ──
        alertes = []
        seuil = today + datetime.timedelta(days=7)
        for co in NattCotisation.objects.filter(
                tenant=tenant, statut__in=['A_PAYER', 'EN_RETARD'],
                date_echeance__lte=seuil).select_related('cycle').order_by('date_echeance'):
            retard = co.date_echeance < today
            alertes.append({
                'niveau': 'danger' if retard else 'warn', 'type': 'NATT',
                'titre': f"Cotisation {co.cycle.nom}",
                'message': f"Échéance #{co.numero} {'en retard depuis' if retard else 'à payer'} le {co.date_echeance:%d/%m/%Y}",
                'montant': float(co.montant), 'date': str(co.date_echeance),
            })
        for e in PretEcheance.objects.filter(
                tenant=tenant, statut__in=['A_PAYER', 'EN_RETARD'],
                date_echeance__lte=seuil).select_related('pret').order_by('date_echeance'):
            retard = e.date_echeance < today
            alertes.append({
                'niveau': 'danger' if retard else 'warn', 'type': 'PRET',
                'titre': f"Prêt {e.pret.organisme_preteur}",
                'message': f"Échéance #{e.numero} {'en retard depuis' if retard else 'à régler'} le {e.date_echeance:%d/%m/%Y}",
                'montant': float(e.montant_echeance), 'date': str(e.date_echeance),
            })
        # Financements promis anciens (> 60 jours) non encaissés
        limite = today - datetime.timedelta(days=60)
        for f in Financement.objects.filter(tenant=tenant, statut='ATTENDU').select_related('type_financement'):
            if f.date_reception and f.date_reception < limite:
                alertes.append({
                    'niveau': 'info', 'type': 'FINANCEMENT',
                    'titre': f"{f.type_financement.libelle} attendu",
                    'message': f"{f.libelle} promis mais non encaissé depuis le {f.date_reception:%d/%m/%Y}",
                    'montant': float(f.montant), 'date': str(f.date_reception),
                })
        alertes.sort(key=lambda a: (a['niveau'] != 'danger', a['date']))

        return Response({
            'ratios': ratios,
            'repartition': repartition_list,
            'evolution': evolution,
            'echeancier': echeancier,
            'alertes': alertes,
        })
