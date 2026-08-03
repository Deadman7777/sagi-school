"""Vues API du socle Gouvernance (convention APIView, sérialisation manuelle)."""
import base64
import datetime
import re
from decimal import Decimal, InvalidOperation

from django.db.models import Max, Sum, Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from django.db import transaction

from core.tenant import get_tenant
from core.models import log_audit
from apps.comptabilite.models import JournalEntry
from apps.comptabilite.views import get_plan_dict
from apps.paiements.models import Exercice
from .models import (Projet, PieceJustificative, TransfertTresorerie,
                     Ressource, AffectationRessource, Provision,
                     CompteBancaire, Rapprochement, LigneReleve)
from . import services


def _d(v):
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _next_code(tenant, model, prefix, field='code'):
    """Séquence PAR tenant (jamais globale) — évite la collision 500 sur une
    nouvelle école."""
    last = model.objects.filter(tenant=tenant).aggregate(m=Max(field))['m']
    nums = re.findall(r'\d+', last or f'{prefix}-0000')
    n = int(nums[-1]) + 1 if nums else 1
    return f"{prefix}-{n:04d}"


# ── Projets ──────────────────────────────────────────────────────────────────
def _consommation_projet(tenant, projet_id):
    """Montant réellement engagé sur un projet, lu depuis le grand livre.

    On somme les débits des écritures taggées `projet` sur les comptes de
    charges (classe 6) et d'immobilisations (classe 2). C'est l'unique source de
    vérité : aucune duplication de montant dans le modèle Projet."""
    agg = JournalEntry.objects.filter(
        tenant=tenant, projet_id=projet_id,
    ).filter(Q(no_compte__startswith='6') | Q(no_compte__startswith='2')).aggregate(
        d=Sum('debit'), c=Sum('credit'))
    return (agg['d'] or Decimal('0')) - (agg['c'] or Decimal('0'))


def _projet_to_dict(p, consomme=None):
    budget = p.budget_prevu or Decimal('0')
    consomme = Decimal('0') if consomme is None else consomme
    reste = budget - consomme
    taux = float(round(consomme / budget * 100, 1)) if budget else 0.0
    return {
        'id': str(p.id), 'code': p.code, 'libelle': p.libelle,
        'description': p.description, 'responsable': p.responsable,
        'date_debut': str(p.date_debut) if p.date_debut else None,
        'date_fin': str(p.date_fin) if p.date_fin else None,
        'budget_prevu': float(budget), 'statut': p.statut,
        'statut_label': p.get_statut_display(),
        'observations': p.observations, 'est_actif': p.est_actif,
        'montant_consomme': float(consomme),
        'montant_restant': float(reste),
        'taux_consommation': taux,
    }


class ProjetView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        tenant = get_tenant(request)
        if pk:
            try:
                p = Projet.objects.get(tenant=tenant, id=pk)
            except Projet.DoesNotExist:
                return Response({'error': 'Non trouvé'}, status=404)
            return Response(_projet_to_dict(p, _consommation_projet(tenant, p.id)))

        qs = Projet.objects.filter(tenant=tenant)
        if request.query_params.get('actifs') == '1':
            qs = qs.filter(est_actif=True)
        # Consommation en une requête agrégée (évite le N+1).
        conso = {
            row['projet_id']: (row['d'] or Decimal('0')) - (row['c'] or Decimal('0'))
            for row in JournalEntry.objects.filter(
                tenant=tenant, projet__isnull=False,
            ).filter(Q(no_compte__startswith='6') | Q(no_compte__startswith='2'))
            .values('projet_id').annotate(d=Sum('debit'), c=Sum('credit'))
        }
        return Response([_projet_to_dict(p, conso.get(p.id, Decimal('0'))) for p in qs])

    def post(self, request):
        tenant = get_tenant(request)
        d = request.data
        libelle = (d.get('libelle') or '').strip()
        if not libelle:
            return Response({'error': 'Libellé requis'}, status=400)
        code = (d.get('code') or '').strip() or _next_code(tenant, Projet, 'PROJ')
        if Projet.objects.filter(tenant=tenant, code=code).exists():
            return Response({'error': f'Le code {code} existe déjà'}, status=400)
        budget = _d(d.get('budget_prevu', 0)) or Decimal('0')
        p = Projet.objects.create(
            tenant=tenant, code=code, libelle=libelle,
            description=d.get('description', ''),
            responsable=d.get('responsable', ''),
            date_debut=d.get('date_debut') or None,
            date_fin=d.get('date_fin') or None,
            budget_prevu=budget,
            statut=d.get('statut', 'PLANIFIE'),
            observations=d.get('observations', ''),
        )
        log_audit(request, 'CREATION', 'Projet', p.id, f'{code} — {libelle}')
        return Response(_projet_to_dict(p), status=201)

    def patch(self, request, pk):
        tenant = get_tenant(request)
        try:
            p = Projet.objects.get(tenant=tenant, id=pk)
        except Projet.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)
        d = request.data
        for f in ('libelle', 'description', 'responsable', 'statut',
                  'observations', 'est_actif'):
            if f in d:
                setattr(p, f, d[f])
        for f in ('date_debut', 'date_fin'):
            if f in d:
                setattr(p, f, d[f] or None)
        if 'budget_prevu' in d:
            budget = _d(d['budget_prevu'])
            if budget is None:
                return Response({'error': 'Budget invalide'}, status=400)
            p.budget_prevu = budget
        p.save()
        log_audit(request, 'MODIFICATION', 'Projet', p.id, p.code)
        return Response(_projet_to_dict(p, _consommation_projet(tenant, p.id)))

    def delete(self, request, pk):
        tenant = get_tenant(request)
        try:
            p = Projet.objects.get(tenant=tenant, id=pk)
        except Projet.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)
        # Un projet déjà mouvementé en compta n'est pas supprimé : on le rend
        # inactif pour préserver la traçabilité des écritures qui le référencent.
        if JournalEntry.objects.filter(tenant=tenant, projet_id=p.id).exists():
            p.est_actif = False
            p.save(update_fields=['est_actif', 'updated_at'])
            log_audit(request, 'MODIFICATION', 'Projet', p.id, f'{p.code} désactivé (écritures liées)')
            return Response({'desactive': True,
                             'message': 'Projet mouvementé : désactivé plutôt que supprimé.'})
        log_audit(request, 'SUPPRESSION', 'Projet', p.id, p.code)
        p.delete()
        return Response(status=204)


# ── Pièces justificatives (GED générique) ────────────────────────────────────
MAX_TAILLE = 6_000_000   # ~6 Mo (data URI base64)
MAX_PAR_OBJET = 20
OBJET_TYPES = {c[0] for c in PieceJustificative.OBJET_CHOICES}


def _piece_meta(p):
    """Métadonnées SANS le contenu (liste légère)."""
    return {
        'id': str(p.id), 'objet_type': p.objet_type, 'objet_id': str(p.objet_id),
        'type_piece': p.type_piece, 'type_piece_label': p.get_type_piece_display(),
        'nom': p.nom, 'mime_type': p.mime_type, 'taille': p.taille,
        'reference': p.reference,
        'date_document': str(p.date_document) if p.date_document else None,
        'observations': p.observations,
        'created_at': p.created_at.isoformat(),
    }


class PieceJustificativeView(APIView):
    """GED générique.

    GET  /pieces/?objet_type=..&objet_id=..  → liste des métadonnées (léger)
    GET  /pieces/<pk>/                       → pièce complète avec contenu base64
    POST /pieces/                            → dépôt d'une pièce
    DELETE /pieces/<pk>/                     → suppression
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        tenant = get_tenant(request)
        if pk:
            try:
                p = PieceJustificative.objects.get(tenant=tenant, id=pk)
            except PieceJustificative.DoesNotExist:
                return Response({'error': 'Non trouvé'}, status=404)
            data = _piece_meta(p)
            data['contenu'] = p.contenu
            return Response(data)

        objet_type = request.query_params.get('objet_type')
        objet_id = request.query_params.get('objet_id')
        if not objet_type or not objet_id:
            return Response({'error': 'objet_type et objet_id requis'}, status=400)
        qs = PieceJustificative.objects.filter(
            tenant=tenant, objet_type=objet_type, objet_id=objet_id)
        return Response([_piece_meta(p) for p in qs])

    def post(self, request):
        tenant = get_tenant(request)
        d = request.data
        objet_type = (d.get('objet_type') or '').upper()
        objet_id = d.get('objet_id')
        if objet_type not in OBJET_TYPES:
            return Response({'error': 'objet_type inconnu'}, status=400)
        if not objet_id:
            return Response({'error': 'objet_id requis'}, status=400)
        contenu = d.get('contenu') or d.get('data') or ''
        if not contenu.startswith('data:'):
            return Response({'error': 'Fichier invalide (data URI base64 attendu)'}, status=400)
        if len(contenu) > MAX_TAILLE:
            return Response({'error': 'Fichier trop volumineux (max ~4,5 Mo)'}, status=400)
        if PieceJustificative.objects.filter(
                tenant=tenant, objet_type=objet_type, objet_id=objet_id).count() >= MAX_PAR_OBJET:
            return Response({'error': f'Maximum {MAX_PAR_OBJET} pièces par élément'}, status=400)

        # mime + taille décodée depuis le data URI
        mime = ''
        taille = 0
        m = re.match(r'data:([^;]*);base64,(.*)', contenu, re.DOTALL)
        if m:
            mime = m.group(1)
            try:
                taille = len(base64.b64decode(m.group(2)))
            except Exception:
                taille = 0

        p = PieceJustificative.objects.create(
            tenant=tenant, objet_type=objet_type, objet_id=objet_id,
            type_piece=d.get('type_piece', 'AUTRE'),
            nom=(d.get('nom') or 'document').strip()[:200],
            mime_type=mime, taille=taille, contenu=contenu,
            reference=(d.get('reference') or '')[:80],
            date_document=d.get('date_document') or None,
            observations=d.get('observations', ''),
            uploaded_par=request.user if request.user.is_authenticated else None,
        )
        log_audit(request, 'CREATION', 'PieceJustificative', p.id,
                  f'{objet_type} — {p.nom}')
        return Response(_piece_meta(p), status=201)

    def delete(self, request, pk):
        tenant = get_tenant(request)
        try:
            p = PieceJustificative.objects.get(tenant=tenant, id=pk)
        except PieceJustificative.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)
        log_audit(request, 'SUPPRESSION', 'PieceJustificative', p.id, p.nom)
        p.delete()
        return Response(status=204)


# ── Transferts internes de trésorerie (Lot 1) ────────────────────────────────
# Canaux de trésorerie par défaut (compte, libellé, clé de solde initial exercice).
# Comptes paramétrables : l'UI accepte aussi un compte libre.
CANAUX_TRESORERIE = [
    ('571',  'Caisse principale', 'caisse'),
    ('5715', 'Petite caisse',     None),
    ('521',  'Banque',            'banque'),
    ('522',  'Banque — épargne',  None),
    ('5521', 'Wave',              'mobile'),
    ('5522', 'Orange Money',      None),
    ('5523', 'Free Money',        None),
    ('5524', 'Wizall',            None),
]


def _exercice_actif(tenant):
    return Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()


def _soldes_canaux(tenant, exercice):
    """Solde courant de chaque canal = solde initial + (débits − crédits) au journal.

    Cohérent avec `DashboardTresorerieCanauView` : le solde initial mobile est
    porté par le compte Wave (5521)."""
    net = {}
    for row in JournalEntry.objects.filter(tenant=tenant, exercice=exercice).values(
            'no_compte').annotate(d=Sum('debit'), c=Sum('credit')):
        net[row['no_compte']] = float(row['d'] or 0) - float(row['c'] or 0)
    initiaux = {
        'caisse': float(exercice.solde_initial_caisse),
        'banque': float(exercice.solde_initial_banque),
        'mobile': float(exercice.solde_initial_mobile),
    }
    plan = get_plan_dict(tenant)
    canaux = []
    for compte, libelle, cle in CANAUX_TRESORERIE:
        init = initiaux.get(cle, 0.0) if cle else 0.0
        canaux.append({
            'compte': compte,
            'libelle': plan.get(compte, libelle),
            'solde': round(init + net.get(compte, 0.0), 2),
        })
    return canaux


class CanauxTresorerieView(APIView):
    """Liste des canaux de trésorerie avec leur solde courant (pour l'UI transfert)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_tenant(request)
        exercice = _exercice_actif(tenant)
        if not exercice:
            return Response({'exercice': None, 'canaux': []})
        return Response({'exercice': exercice.annee_scolaire,
                         'canaux': _soldes_canaux(tenant, exercice)})


def _transfert_to_dict(t, plan=None):
    plan = plan or {}
    return {
        'id': str(t.id), 'reference': t.reference,
        'date_transfert': str(t.date_transfert),
        'compte_source': t.compte_source,
        'compte_source_libelle': plan.get(t.compte_source, t.compte_source),
        'compte_destination': t.compte_destination,
        'compte_destination_libelle': plan.get(t.compte_destination, t.compte_destination),
        'montant': float(t.montant), 'frais': float(t.frais),
        'compte_virement': t.compte_virement, 'compte_frais': t.compte_frais,
        'motif': t.motif, 'statut': t.statut,
        'statut_label': t.get_statut_display(),
        'projet_id': str(t.projet_id) if t.projet_id else None,
        'observations': t.observations,
        'created_at': t.created_at.isoformat(),
    }


class TransfertView(APIView):
    """Transferts internes de trésorerie.

    GET    /transferts/         → liste (exercice actif)
    POST   /transferts/         → crée + comptabilise (585)
    DELETE /transferts/<pk>/    → annule (extourne les écritures, statut ANNULE)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_tenant(request)
        exercice = _exercice_actif(tenant)
        if not exercice:
            return Response([])
        plan = get_plan_dict(tenant)
        qs = TransfertTresorerie.objects.filter(tenant=tenant, exercice=exercice)
        return Response([_transfert_to_dict(t, plan) for t in qs])

    def post(self, request):
        tenant = get_tenant(request)
        exercice = _exercice_actif(tenant)
        if not exercice:
            return Response({'error': 'Aucun exercice actif'}, status=400)

        d = request.data
        source = (d.get('compte_source') or '').strip()
        dest   = (d.get('compte_destination') or '').strip()
        montant = _d(d.get('montant'))
        frais   = _d(d.get('frais', 0)) or Decimal('0')
        if not source or not dest:
            return Response({'error': 'Comptes source et destination requis'}, status=400)
        if source == dest:
            return Response({'error': 'Les comptes source et destination doivent différer'}, status=400)
        if montant is None or montant <= 0:
            return Response({'error': 'Montant invalide'}, status=400)
        if frais < 0:
            return Response({'error': 'Frais invalides'}, status=400)

        projet = None
        if d.get('projet_id'):
            projet = Projet.objects.filter(tenant=tenant, id=d['projet_id']).first()

        reference = (d.get('reference') or '').strip() or _next_code(tenant, TransfertTresorerie, 'TRF', field='reference')
        if TransfertTresorerie.objects.filter(tenant=tenant, reference=reference).exists():
            return Response({'error': f'La référence {reference} existe déjà'}, status=400)

        with transaction.atomic():
            t = TransfertTresorerie.objects.create(
                tenant=tenant, exercice=exercice, reference=reference,
                date_transfert=d.get('date_transfert') or datetime.date.today(),
                compte_source=source, compte_destination=dest,
                montant=montant, frais=frais,
                compte_virement=(d.get('compte_virement') or '585').strip(),
                compte_frais=(d.get('compte_frais') or '6312').strip(),
                motif=(d.get('motif') or '')[:200],
                projet=projet, observations=d.get('observations', ''),
            )
            services.generer_ecriture_transfert(t, tenant)
        log_audit(request, 'CREATION', 'TransfertTresorerie', t.id,
                  f'{reference} {source}→{dest} {montant}')
        plan = get_plan_dict(tenant)
        return Response(_transfert_to_dict(t, plan), status=201)

    def delete(self, request, pk):
        tenant = get_tenant(request)
        try:
            t = TransfertTresorerie.objects.get(tenant=tenant, id=pk)
        except TransfertTresorerie.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)
        if t.statut == 'ANNULE':
            return Response({'error': 'Transfert déjà annulé'}, status=400)
        if t.exercice.cloture:
            return Response({'error': 'Exercice clôturé : annulation impossible'}, status=400)
        with transaction.atomic():
            services.annuler_ecriture_transfert(t, tenant)
            t.statut = 'ANNULE'
            t.save(update_fields=['statut', 'updated_at'])
        log_audit(request, 'ANNULATION', 'TransfertTresorerie', t.id, t.reference)
        return Response({'annule': True})


# ── Ressources financières unifiées + affectations (Lot 2) ───────────────────
def _ressource_to_dict(r, consomme=None, affecte=None):
    montant   = r.montant or Decimal('0')
    consomme  = Decimal('0') if consomme is None else consomme
    affecte   = Decimal('0') if affecte is None else affecte
    restant   = montant - consomme
    taux      = float(round(consomme / montant * 100, 1)) if montant else 0.0
    return {
        'id': str(r.id), 'reference': r.reference,
        'type_ressource': r.type_ressource, 'type_label': r.get_type_ressource_display(),
        'libelle': r.libelle, 'organisme': r.organisme,
        'montant': float(montant),
        'date_ressource': str(r.date_ressource) if r.date_ressource else None,
        'compte_tresorerie': r.compte_tresorerie, 'convention': r.convention,
        'taux': float(r.taux), 'statut': r.statut, 'statut_label': r.get_statut_display(),
        'observations': r.observations,
        'projet_id': str(r.projet_id) if r.projet_id else None,
        'financement_id': str(r.financement_id) if r.financement_id else None,
        'pret_id': str(r.pret_id) if r.pret_id else None,
        'montant_consomme': float(consomme),
        'montant_affecte': float(affecte),
        'montant_restant': float(restant),
        'disponible_a_affecter': float(montant - affecte),
        'taux_consommation': taux,
    }


class RessourceView(APIView):
    permission_classes = [IsAuthenticated]

    def _stats_bulk(self, tenant, ressource_ids):
        """Consommation (ledger, net débit−crédit) + affectation (planning) par
        ressource, sans N+1."""
        conso = {
            row['ressource_id']: (row['d'] or Decimal('0')) - (row['c'] or Decimal('0'))
            for row in JournalEntry.objects.filter(
                tenant=tenant, ressource_id__in=ressource_ids,
            ).filter(Q(no_compte__startswith='6') | Q(no_compte__startswith='2'))
            .values('ressource_id').annotate(d=Sum('debit'), c=Sum('credit'))
        }
        affect = {
            row['ressource_id']: row['total']
            for row in AffectationRessource.objects.filter(
                tenant=tenant, ressource_id__in=ressource_ids
            ).values('ressource_id').annotate(total=Sum('montant_affecte'))
        }
        return conso, affect

    def get(self, request, pk=None):
        tenant = get_tenant(request)
        if pk:
            try:
                r = Ressource.objects.get(tenant=tenant, id=pk)
            except Ressource.DoesNotExist:
                return Response({'error': 'Non trouvé'}, status=404)
            conso, affect = self._stats_bulk(tenant, [r.id])
            return Response(_ressource_to_dict(r, conso.get(r.id, Decimal('0')),
                                               affect.get(r.id, Decimal('0'))))
        qs = list(Ressource.objects.filter(tenant=tenant))
        conso, affect = self._stats_bulk(tenant, [r.id for r in qs])
        return Response([_ressource_to_dict(r, conso.get(r.id, Decimal('0')),
                                            affect.get(r.id, Decimal('0'))) for r in qs])

    def post(self, request):
        tenant = get_tenant(request)
        d = request.data
        libelle = (d.get('libelle') or '').strip()
        montant = _d(d.get('montant'))
        if not libelle:
            return Response({'error': 'Libellé requis'}, status=400)
        if montant is None or montant <= 0:
            return Response({'error': 'Montant invalide'}, status=400)
        reference = (d.get('reference') or '').strip() or _next_code(tenant, Ressource, 'RES', field='reference')
        if Ressource.objects.filter(tenant=tenant, reference=reference).exists():
            return Response({'error': f'La référence {reference} existe déjà'}, status=400)

        projet = Projet.objects.filter(tenant=tenant, id=d['projet_id']).first() if d.get('projet_id') else None
        r = Ressource.objects.create(
            tenant=tenant, reference=reference,
            type_ressource=d.get('type_ressource', 'AUTRE'),
            libelle=libelle, organisme=d.get('organisme', ''),
            montant=montant, date_ressource=d.get('date_ressource') or None,
            compte_tresorerie=d.get('compte_tresorerie', ''),
            convention=d.get('convention', ''), taux=_d(d.get('taux', 0)) or Decimal('0'),
            observations=d.get('observations', ''), projet=projet,
        )
        log_audit(request, 'CREATION', 'Ressource', r.id, f'{reference} — {libelle}')
        return Response(_ressource_to_dict(r), status=201)

    def patch(self, request, pk):
        tenant = get_tenant(request)
        try:
            r = Ressource.objects.get(tenant=tenant, id=pk)
        except Ressource.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)
        d = request.data
        for f in ('type_ressource', 'libelle', 'organisme', 'compte_tresorerie',
                  'convention', 'statut', 'observations'):
            if f in d:
                setattr(r, f, d[f])
        if 'date_ressource' in d:
            r.date_ressource = d['date_ressource'] or None
        if 'taux' in d:
            r.taux = _d(d['taux']) or Decimal('0')
        if 'montant' in d:
            m = _d(d['montant'])
            if m is None or m <= 0:
                return Response({'error': 'Montant invalide'}, status=400)
            # On ne peut pas réduire l'enveloppe sous ce qui est déjà consommé.
            conso = services.consommation_ressource(tenant, r.id)
            if m < conso:
                return Response({'error': f'Montant < déjà consommé ({conso:.0f})'}, status=400)
            r.montant = m
        if 'projet_id' in d:
            r.projet = Projet.objects.filter(tenant=tenant, id=d['projet_id']).first() if d['projet_id'] else None
        r.save()
        conso, affect = self._stats_bulk(tenant, [r.id])
        log_audit(request, 'MODIFICATION', 'Ressource', r.id, r.reference)
        return Response(_ressource_to_dict(r, conso.get(r.id, Decimal('0')), affect.get(r.id, Decimal('0'))))

    def delete(self, request, pk):
        tenant = get_tenant(request)
        try:
            r = Ressource.objects.get(tenant=tenant, id=pk)
        except Ressource.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)
        # Ressource déjà consommée en compta : clôturée plutôt que supprimée
        # (les écritures qui la référencent conservent leur traçabilité).
        if JournalEntry.objects.filter(tenant=tenant, ressource_id=r.id).exists():
            r.statut = 'CLOTUREE'
            r.save(update_fields=['statut', 'updated_at'])
            return Response({'cloturee': True,
                             'message': 'Ressource mouvementée : clôturée plutôt que supprimée.'})
        log_audit(request, 'SUPPRESSION', 'Ressource', r.id, r.reference)
        r.delete()
        return Response(status=204)


class RessourceTracabiliteView(APIView):
    """Traçabilité d'une ressource : d'où vient / à quoi elle sert / son impact."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        tenant = get_tenant(request)
        try:
            r = Ressource.objects.get(tenant=tenant, id=pk)
        except Ressource.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)

        affectations = [{
            'id': str(a.id), 'type_emploi': a.type_emploi,
            'type_label': a.get_type_emploi_display(), 'libelle': a.libelle,
            'montant_affecte': float(a.montant_affecte),
            'projet_id': str(a.projet_id) if a.projet_id else None,
            'date_affectation': str(a.date_affectation) if a.date_affectation else None,
        } for a in r.affectations.all()]

        # Consommations réelles : débits 6xx/2xx taggés sur la ressource.
        conso_qs = JournalEntry.objects.filter(
            tenant=tenant, ressource_id=r.id, debit__gt=0,
        ).filter(Q(no_compte__startswith='6') | Q(no_compte__startswith='2')).order_by('date_ecriture')
        consommations = [{
            'id': str(e.id), 'date': str(e.date_ecriture), 'no_piece': e.no_piece,
            'no_compte': e.no_compte, 'libelle': e.libelle, 'montant': float(e.debit),
            'source': e.source, 'nature': 'IMMOBILISATION' if e.no_compte.startswith('2') else 'CHARGE',
            'projet_id': str(e.projet_id) if e.projet_id else None,
        } for e in conso_qs]

        conso, affect = RessourceView()._stats_bulk(tenant, [r.id])
        return Response({
            'ressource': _ressource_to_dict(r, conso.get(r.id, Decimal('0')), affect.get(r.id, Decimal('0'))),
            'affectations': affectations,
            'consommations': consommations,
        })


class AffectationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_tenant(request)
        ressource_id = request.query_params.get('ressource_id')
        if not ressource_id:
            return Response({'error': 'ressource_id requis'}, status=400)
        qs = AffectationRessource.objects.filter(tenant=tenant, ressource_id=ressource_id)
        return Response([{
            'id': str(a.id), 'ressource_id': str(a.ressource_id),
            'type_emploi': a.type_emploi, 'type_label': a.get_type_emploi_display(),
            'libelle': a.libelle, 'montant_affecte': float(a.montant_affecte),
            'projet_id': str(a.projet_id) if a.projet_id else None,
            'date_affectation': str(a.date_affectation) if a.date_affectation else None,
            'observations': a.observations,
        } for a in qs])

    def post(self, request):
        tenant = get_tenant(request)
        d = request.data
        try:
            ressource = Ressource.objects.get(tenant=tenant, id=d.get('ressource_id'))
        except Ressource.DoesNotExist:
            return Response({'error': 'Ressource introuvable'}, status=404)
        libelle = (d.get('libelle') or '').strip()
        montant = _d(d.get('montant_affecte'))
        if not libelle:
            return Response({'error': 'Libellé requis'}, status=400)
        if montant is None or montant <= 0:
            return Response({'error': 'Montant invalide'}, status=400)
        # L'affectation ne peut pas dépasser le disponible à affecter.
        deja = AffectationRessource.objects.filter(
            tenant=tenant, ressource=ressource).aggregate(t=Sum('montant_affecte'))['t'] or Decimal('0')
        if montant > (ressource.montant - deja):
            return Response({'error': f'Dépassement : disponible à affecter {ressource.montant - deja:.0f}'},
                            status=400)
        projet = Projet.objects.filter(tenant=tenant, id=d['projet_id']).first() if d.get('projet_id') else None
        a = AffectationRessource.objects.create(
            tenant=tenant, ressource=ressource,
            type_emploi=d.get('type_emploi', 'AUTRE'), libelle=libelle,
            montant_affecte=montant, projet=projet,
            date_affectation=d.get('date_affectation') or None,
            observations=d.get('observations', ''),
        )
        log_audit(request, 'CREATION', 'AffectationRessource', a.id, f'{ressource.reference} → {libelle}')
        return Response({'id': str(a.id)}, status=201)

    def delete(self, request, pk):
        tenant = get_tenant(request)
        try:
            a = AffectationRessource.objects.get(tenant=tenant, id=pk)
        except AffectationRessource.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)
        a.delete()
        return Response(status=204)


# ── Traçabilité (Lot 3) : d'où vient / à quoi sert / quel impact ─────────────
# Catégories d'emploi (« à quoi a servi le franc ») par préfixe de compte.
CATEGORIES_EMPLOI = [
    ('Immobilisations', ('2',)),
    ('Salaires',        ('66',)),
    ('Frais financiers', ('67',)),
    ('Impôts et taxes', ('64',)),
    ('Fonctionnement',  ('60', '61', '62', '63', '65')),
]


def _categorie_emploi(no_compte):
    for libelle, prefixes in CATEGORIES_EMPLOI:
        if any(no_compte.startswith(p) for p in prefixes):
            return libelle
    return 'Autres'


class ProjetTracabiliteView(APIView):
    """Traçabilité d'un projet : origine des fonds, emplois, immobilisations créées."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        tenant = get_tenant(request)
        try:
            p = Projet.objects.get(tenant=tenant, id=pk)
        except Projet.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)

        entries = JournalEntry.objects.filter(
            tenant=tenant, projet_id=p.id,
        ).filter(Q(no_compte__startswith='6') | Q(no_compte__startswith='2'))

        # Emplois par nature (net débit − crédit).
        emplois = {}
        for e in entries:
            cat = _categorie_emploi(e.no_compte)
            emplois[cat] = emplois.get(cat, Decimal('0')) + e.debit - e.credit
        emplois_list = [{'nature': k, 'montant': float(v)} for k, v in emplois.items() if v]

        # Origines : ressources ayant financé les dépenses du projet.
        origines = {}
        for e in entries.filter(ressource__isnull=False).select_related('ressource'):
            r = e.ressource
            origines.setdefault(str(r.id), {'libelle': r.libelle, 'type': r.get_type_ressource_display(),
                                            'montant': Decimal('0')})
            origines[str(r.id)]['montant'] += e.debit - e.credit
        origines_list = [{'ressource_id': k, **v, 'montant': float(v['montant'])}
                         for k, v in origines.items() if v['montant']]

        # Immobilisations créées sous ce projet.
        from apps.comptabilite.models import Immobilisation
        immos = [{
            'id': str(i.id), 'no_bien': i.no_bien, 'libelle': i.libelle,
            'valeur_entree': float(i.valeur_entree),
            'valeur_nette_comptable': i.valeur_nette_comptable,
        } for i in Immobilisation.objects.filter(tenant=tenant, projet_id=p.id)]

        consomme = _consommation_projet(tenant, p.id)
        return Response({
            'projet': _projet_to_dict(p, consomme),
            'origines': origines_list,
            'emplois': emplois_list,
            'immobilisations': immos,
        })


# ── Provisions SYSCOHADA (Lot 4) ─────────────────────────────────────────────
# Comptes par défaut (dotation, provision, reprise) — tous paramétrables ensuite.
DEFAULTS_PROVISION = {
    'RISQUE':           ('6911', '191', '7911'),
    'LITIGE':           ('6911', '191', '7911'),
    'CHARGE':           ('6911', '198', '7911'),
    'CREANCE_DOUTEUSE': ('6911', '491', '7911'),
    'REGLEMENTEE':      ('851',  '151', '861'),
}


def _provision_to_dict(p):
    return {
        'id': str(p.id), 'reference': p.reference,
        'type_provision': p.type_provision, 'type_label': p.get_type_provision_display(),
        'libelle': p.libelle, 'montant': float(p.montant),
        'montant_repris': float(p.montant_repris), 'montant_actuel': float(p.montant_actuel),
        'date_dotation': str(p.date_dotation),
        'compte_dotation': p.compte_dotation, 'compte_provision': p.compte_provision,
        'compte_reprise': p.compte_reprise, 'tiers': p.tiers,
        'observations': p.observations, 'statut': p.statut,
        'statut_label': p.get_statut_display(),
    }


class ProvisionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_tenant(request)
        exercice = _exercice_actif(tenant)
        if not exercice:
            return Response([])
        qs = Provision.objects.filter(tenant=tenant, exercice=exercice)
        return Response([_provision_to_dict(p) for p in qs])

    def post(self, request):
        tenant = get_tenant(request)
        exercice = _exercice_actif(tenant)
        if not exercice:
            return Response({'error': 'Aucun exercice actif'}, status=400)
        d = request.data
        libelle = (d.get('libelle') or '').strip()
        montant = _d(d.get('montant'))
        type_prov = d.get('type_provision', 'RISQUE')
        if type_prov not in DEFAULTS_PROVISION:
            return Response({'error': 'Type de provision inconnu'}, status=400)
        if not libelle:
            return Response({'error': 'Libellé requis'}, status=400)
        if montant is None or montant <= 0:
            return Response({'error': 'Montant invalide'}, status=400)

        dot_def, prov_def, rep_def = DEFAULTS_PROVISION[type_prov]
        reference = (d.get('reference') or '').strip() or _next_code(tenant, Provision, 'PROV', field='reference')
        if Provision.objects.filter(tenant=tenant, reference=reference).exists():
            return Response({'error': f'La référence {reference} existe déjà'}, status=400)

        with transaction.atomic():
            p = Provision.objects.create(
                tenant=tenant, exercice=exercice, reference=reference,
                type_provision=type_prov, libelle=libelle, montant=montant,
                date_dotation=d.get('date_dotation') or datetime.date.today(),
                compte_dotation=(d.get('compte_dotation') or dot_def).strip(),
                compte_provision=(d.get('compte_provision') or prov_def).strip(),
                compte_reprise=(d.get('compte_reprise') or rep_def).strip(),
                tiers=d.get('tiers', ''), observations=d.get('observations', ''),
            )
            services.generer_ecriture_dotation(p, tenant)
        log_audit(request, 'CREATION', 'Provision', p.id, f'{reference} — {libelle}')
        return Response(_provision_to_dict(p), status=201)

    def delete(self, request, pk):
        tenant = get_tenant(request)
        try:
            p = Provision.objects.get(tenant=tenant, id=pk)
        except Provision.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)
        if p.statut == 'ANNULEE':
            return Response({'error': 'Provision déjà annulée'}, status=400)
        if p.exercice.cloture:
            return Response({'error': 'Exercice clôturé : annulation impossible'}, status=400)
        with transaction.atomic():
            services.annuler_ecriture_provision(p, tenant)
            p.statut = 'ANNULEE'
            p.save(update_fields=['statut', 'updated_at'])
        log_audit(request, 'ANNULATION', 'Provision', p.id, p.reference)
        return Response({'annule': True})


class ProvisionRepriseView(APIView):
    """Reprise (partielle ou totale) d'une provision : POST montant."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        tenant = get_tenant(request)
        try:
            p = Provision.objects.get(tenant=tenant, id=pk)
        except Provision.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)
        if p.statut != 'ACTIVE':
            return Response({'error': 'Provision non active'}, status=400)
        if p.exercice.cloture:
            return Response({'error': 'Exercice clôturé'}, status=400)
        montant = _d(request.data.get('montant'))
        if montant is None or montant <= 0:
            return Response({'error': 'Montant invalide'}, status=400)
        if montant > p.montant_actuel:
            return Response({'error': f'Reprise > provision restante ({p.montant_actuel:.0f})'}, status=400)
        with transaction.atomic():
            services.generer_ecriture_reprise(p, montant, tenant,
                                              date=request.data.get('date') or None)
            p.montant_repris = p.montant_repris + montant
            if p.montant_repris >= p.montant:
                p.statut = 'SOLDEE'
            p.save(update_fields=['montant_repris', 'statut', 'updated_at'])
        log_audit(request, 'MODIFICATION', 'Provision', p.id, f'Reprise {montant:.0f} sur {p.reference}')
        return Response(_provision_to_dict(p))


# ── Rapprochement bancaire (Lot 5) ───────────────────────────────────────────
def _compte_bancaire_to_dict(cb, solde_comptable=None):
    return {
        'id': str(cb.id), 'libelle': cb.libelle, 'banque': cb.banque,
        'numero_compte': cb.numero_compte, 'no_compte_comptable': cb.no_compte_comptable,
        'devise': cb.devise, 'solde_initial': float(cb.solde_initial), 'actif': cb.actif,
        'solde_comptable': float(solde_comptable) if solde_comptable is not None else None,
    }


class CompteBancaireView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        tenant = get_tenant(request)
        today = datetime.date.today()
        if pk:
            try:
                cb = CompteBancaire.objects.get(tenant=tenant, id=pk)
            except CompteBancaire.DoesNotExist:
                return Response({'error': 'Non trouvé'}, status=404)
            return Response(_compte_bancaire_to_dict(cb, services.solde_comptable_banque(cb, today, tenant)))
        out = []
        for cb in CompteBancaire.objects.filter(tenant=tenant):
            out.append(_compte_bancaire_to_dict(cb, services.solde_comptable_banque(cb, today, tenant)))
        return Response(out)

    def post(self, request):
        tenant = get_tenant(request)
        d = request.data
        libelle = (d.get('libelle') or '').strip()
        if not libelle:
            return Response({'error': 'Libellé requis'}, status=400)
        cb = CompteBancaire.objects.create(
            tenant=tenant, libelle=libelle, banque=d.get('banque', ''),
            numero_compte=d.get('numero_compte', ''),
            no_compte_comptable=(d.get('no_compte_comptable') or '521').strip(),
            devise=d.get('devise', 'XOF'), solde_initial=_d(d.get('solde_initial', 0)) or Decimal('0'),
        )
        log_audit(request, 'CREATION', 'CompteBancaire', cb.id, libelle)
        return Response(_compte_bancaire_to_dict(cb), status=201)

    def patch(self, request, pk):
        tenant = get_tenant(request)
        try:
            cb = CompteBancaire.objects.get(tenant=tenant, id=pk)
        except CompteBancaire.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)
        for f in ('libelle', 'banque', 'numero_compte', 'no_compte_comptable', 'devise', 'actif'):
            if f in request.data:
                setattr(cb, f, request.data[f])
        if 'solde_initial' in request.data:
            cb.solde_initial = _d(request.data['solde_initial']) or Decimal('0')
        cb.save()
        return Response(_compte_bancaire_to_dict(cb))

    def delete(self, request, pk):
        tenant = get_tenant(request)
        try:
            cb = CompteBancaire.objects.get(tenant=tenant, id=pk)
        except CompteBancaire.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)
        if cb.rapprochements.exists():
            cb.actif = False
            cb.save(update_fields=['actif', 'updated_at'])
            return Response({'desactive': True})
        cb.delete()
        return Response(status=204)


def _ligne_to_dict(l):
    return {
        'id': str(l.id), 'date_operation': str(l.date_operation), 'libelle': l.libelle,
        'montant': float(l.montant), 'sens': l.sens, 'reference': l.reference,
        'statut': l.statut, 'journal_entry_id': str(l.journal_entry_id) if l.journal_entry_id else None,
    }


def _rapprochement_stats(rap, tenant):
    cb = rap.compte_bancaire
    solde_comptable = services.solde_comptable_banque(cb, rap.date_rapprochement, tenant)
    ecart = _d(rap.solde_releve) - solde_comptable
    lignes = list(rap.lignes.all())
    nb_non = sum(1 for l in lignes if l.statut == 'NON_RAPPROCHEE')
    return solde_comptable, ecart, lignes, nb_non


class RapprochementView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        tenant = get_tenant(request)
        exercice = _exercice_actif(tenant)
        if pk:
            try:
                rap = Rapprochement.objects.select_related('compte_bancaire').get(tenant=tenant, id=pk)
            except Rapprochement.DoesNotExist:
                return Response({'error': 'Non trouvé'}, status=404)
            solde_comptable, ecart, lignes, nb_non = _rapprochement_stats(rap, tenant)
            # Écritures du ledger non pointées (expliquent une part de l'écart).
            non_pointees = [{
                'id': str(e.id), 'date': str(e.date_ecriture), 'no_piece': e.no_piece,
                'libelle': e.libelle, 'debit': float(e.debit), 'credit': float(e.credit),
                'sens': 'ENTREE' if e.debit > 0 else 'SORTIE',
                'montant': float(e.debit if e.debit > 0 else e.credit),
            } for e in services.ecritures_non_rapprochees(
                rap.compte_bancaire, rap.exercice, tenant)
              if e.date_ecriture <= rap.date_rapprochement]
            return Response({
                'id': str(rap.id), 'reference': rap.reference,
                'compte_bancaire_id': str(rap.compte_bancaire_id),
                'compte_bancaire_libelle': rap.compte_bancaire.libelle,
                'no_compte_comptable': rap.compte_bancaire.no_compte_comptable,
                'date_rapprochement': str(rap.date_rapprochement),
                'solde_releve': float(rap.solde_releve),
                'solde_comptable': float(solde_comptable),
                'ecart': float(ecart),
                'statut': rap.statut, 'observations': rap.observations,
                'lignes': [_ligne_to_dict(l) for l in lignes],
                'ecritures_non_pointees': non_pointees,
                'nb_non_rapprochees': nb_non,
            })
        # Liste
        qs = Rapprochement.objects.filter(tenant=tenant).select_related('compte_bancaire')
        if exercice:
            qs = qs.filter(exercice=exercice)
        out = []
        for rap in qs:
            solde_comptable, ecart, lignes, nb_non = _rapprochement_stats(rap, tenant)
            out.append({
                'id': str(rap.id), 'reference': rap.reference,
                'compte_bancaire_libelle': rap.compte_bancaire.libelle,
                'date_rapprochement': str(rap.date_rapprochement),
                'solde_releve': float(rap.solde_releve),
                'solde_comptable': float(solde_comptable), 'ecart': float(ecart),
                'statut': rap.statut, 'nb_lignes': len(lignes), 'nb_non_rapprochees': nb_non,
            })
        return Response(out)

    def post(self, request):
        tenant = get_tenant(request)
        exercice = _exercice_actif(tenant)
        if not exercice:
            return Response({'error': 'Aucun exercice actif'}, status=400)
        d = request.data
        try:
            cb = CompteBancaire.objects.get(tenant=tenant, id=d.get('compte_bancaire_id'))
        except CompteBancaire.DoesNotExist:
            return Response({'error': 'Compte bancaire introuvable'}, status=404)
        if not d.get('date_rapprochement'):
            return Response({'error': 'Date de rapprochement requise'}, status=400)
        reference = (d.get('reference') or '').strip() or _next_code(tenant, Rapprochement, 'RAP', field='reference')
        if Rapprochement.objects.filter(tenant=tenant, reference=reference).exists():
            return Response({'error': f'La référence {reference} existe déjà'}, status=400)
        with transaction.atomic():
            rap = Rapprochement.objects.create(
                tenant=tenant, compte_bancaire=cb, exercice=exercice, reference=reference,
                date_rapprochement=d['date_rapprochement'],
                solde_releve=_d(d.get('solde_releve', 0)) or Decimal('0'),
                observations=d.get('observations', ''),
            )
            # Import optionnel des lignes du relevé.
            for lg in (d.get('lignes') or []):
                montant = _d(lg.get('montant'))
                if montant is None or montant <= 0 or not lg.get('date_operation'):
                    continue
                LigneReleve.objects.create(
                    tenant=tenant, rapprochement=rap, date_operation=lg['date_operation'],
                    libelle=(lg.get('libelle') or '')[:200], montant=montant,
                    sens=lg.get('sens', 'SORTIE'), reference=(lg.get('reference') or '')[:80],
                )
        log_audit(request, 'CREATION', 'Rapprochement', rap.id, reference)
        return self.get(request, pk=rap.id)

    def delete(self, request, pk):
        tenant = get_tenant(request)
        try:
            rap = Rapprochement.objects.get(tenant=tenant, id=pk)
        except Rapprochement.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)
        if rap.statut == 'VALIDE':
            return Response({'error': 'Rapprochement validé : suppression impossible'}, status=400)
        # Les écritures de régularisation générées restent (SYSCOHADA) ; on ne
        # supprime que la session et ses lignes.
        rap.delete()
        return Response(status=204)


class LigneReleveView(APIView):
    """Ajout/suppression d'une ligne de relevé, et rapprochement MANUEL (lien)."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        tenant = get_tenant(request)
        try:
            rap = Rapprochement.objects.get(tenant=tenant, id=pk)
        except Rapprochement.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)
        if rap.statut == 'VALIDE':
            return Response({'error': 'Rapprochement validé'}, status=400)
        d = request.data
        montant = _d(d.get('montant'))
        if montant is None or montant <= 0 or not d.get('date_operation'):
            return Response({'error': 'Date et montant requis'}, status=400)
        l = LigneReleve.objects.create(
            tenant=tenant, rapprochement=rap, date_operation=d['date_operation'],
            libelle=(d.get('libelle') or '')[:200], montant=montant,
            sens=d.get('sens', 'SORTIE'), reference=(d.get('reference') or '')[:80],
        )
        return Response(_ligne_to_dict(l), status=201)

    def patch(self, request, pk, lid):
        """Rapprochement manuel : lie la ligne à une écriture (journal_entry_id),
        ou délie (journal_entry_id null)."""
        tenant = get_tenant(request)
        try:
            l = LigneReleve.objects.get(tenant=tenant, id=lid, rapprochement_id=pk)
        except LigneReleve.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)
        je_id = request.data.get('journal_entry_id')
        if not je_id:
            l.journal_entry = None
            l.statut = 'NON_RAPPROCHEE'
            l.save(update_fields=['journal_entry', 'statut', 'updated_at'])
            return Response(_ligne_to_dict(l))
        cb = l.rapprochement.compte_bancaire
        try:
            e = JournalEntry.objects.get(tenant=tenant, id=je_id, no_compte=cb.no_compte_comptable)
        except JournalEntry.DoesNotExist:
            return Response({'error': 'Écriture invalide (pas sur ce compte bancaire)'}, status=400)
        if LigneReleve.objects.filter(
                tenant=tenant, rapprochement__compte_bancaire=cb, journal_entry=e
        ).exclude(id=l.id).exists():
            return Response({'error': 'Écriture déjà rapprochée'}, status=400)
        l.journal_entry = e
        l.statut = 'RAPPROCHEE'
        l.save(update_fields=['journal_entry', 'statut', 'updated_at'])
        return Response(_ligne_to_dict(l))

    def delete(self, request, pk, lid):
        tenant = get_tenant(request)
        try:
            l = LigneReleve.objects.get(tenant=tenant, id=lid, rapprochement_id=pk)
        except LigneReleve.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)
        if l.statut == 'REGULARISEE':
            return Response({'error': 'Ligne régularisée : écriture générée, non supprimable ici'}, status=400)
        l.delete()
        return Response(status=204)


class RapprochementAutoView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        tenant = get_tenant(request)
        try:
            rap = Rapprochement.objects.get(tenant=tenant, id=pk)
        except Rapprochement.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)
        if rap.statut == 'VALIDE':
            return Response({'error': 'Rapprochement validé'}, status=400)
        n = services.rapprochement_auto(rap, tenant)
        log_audit(request, 'MODIFICATION', 'Rapprochement', rap.id, f'Auto : {n} rapprochement(s)')
        return Response({'rapproches': n})


class RegularisationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, lid):
        tenant = get_tenant(request)
        try:
            l = LigneReleve.objects.get(tenant=tenant, id=lid, rapprochement_id=pk)
        except LigneReleve.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)
        if l.statut != 'NON_RAPPROCHEE':
            return Response({'error': 'Ligne déjà rapprochée/régularisée'}, status=400)
        if l.rapprochement.statut == 'VALIDE':
            return Response({'error': 'Rapprochement validé'}, status=400)
        compte = (request.data.get('compte_contrepartie') or '').strip()
        if not compte:
            # Défaut : agios/frais (631) pour une sortie, revenus financiers (771) pour une entrée.
            compte = '631' if l.sens == 'SORTIE' else '771'
        with transaction.atomic():
            services.generer_ecriture_regularisation(l, compte, tenant,
                                                     libelle_extra=request.data.get('libelle', ''))
        log_audit(request, 'CREATION', 'RegularisationRapprochement', l.id, l.libelle)
        return Response(_ligne_to_dict(l), status=201)


class RapprochementValiderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        tenant = get_tenant(request)
        try:
            rap = Rapprochement.objects.get(tenant=tenant, id=pk)
        except Rapprochement.DoesNotExist:
            return Response({'error': 'Non trouvé'}, status=404)
        from django.utils import timezone
        rap.statut = 'VALIDE'
        rap.date_validation = timezone.now()
        rap.save(update_fields=['statut', 'date_validation', 'updated_at'])
        log_audit(request, 'MODIFICATION', 'Rapprochement', rap.id, f'Validé {rap.reference}')
        return Response({'valide': True})


# ── Tableau de bord consolidé (Lot 6) ────────────────────────────────────────
TRESO_ACCOUNTS = ('571', '5715', '521', '522', '5521', '5522', '5523', '5524')
GROUPES_TRESO = {
    'banques': ('521', '522'),
    'caisses': ('571', '5715'),
    'mobile':  ('5521', '5522', '5523', '5524'),
}


class DashboardGouvernanceView(APIView):
    """Tableaux de bord de gouvernance : ressources, trésorerie, investissements,
    pilotage — consolidation des lots 0-5 sur l'exercice actif."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.comptabilite.models import Immobilisation

        tenant = get_tenant(request)
        exercice = _exercice_actif(tenant)
        if not exercice:
            return Response({'exercice': None})
        entries = JournalEntry.objects.filter(tenant=tenant, exercice=exercice)

        # ── RESSOURCES ────────────────────────────────────────────────────
        ressources = list(Ressource.objects.filter(tenant=tenant).exclude(statut='ANNULEE'))
        conso_res = {
            row['ressource_id']: (row['d'] or Decimal('0')) - (row['c'] or Decimal('0'))
            for row in entries.filter(ressource__isnull=False)
            .filter(Q(no_compte__startswith='6') | Q(no_compte__startswith='2'))
            .values('ressource_id').annotate(d=Sum('debit'), c=Sum('credit'))
        }
        total_obtenu = sum((r.montant for r in ressources), Decimal('0'))
        total_conso  = sum((conso_res.get(r.id, Decimal('0')) for r in ressources), Decimal('0'))
        rep_origine = {}
        for r in ressources:
            lbl = r.get_type_ressource_display()
            g = rep_origine.setdefault(lbl, {'montant': Decimal('0'), 'consomme': Decimal('0')})
            g['montant'] += r.montant
            g['consomme'] += conso_res.get(r.id, Decimal('0'))
        rep_financement = [{
            'libelle': r.libelle, 'type': r.get_type_ressource_display(),
            'montant': float(r.montant),
            'consomme': float(conso_res.get(r.id, Decimal('0'))),
            'disponible': float(r.montant - conso_res.get(r.id, Decimal('0'))),
        } for r in ressources]
        # Répartition par projet (consommation nette 6xx/2xx taggée projet).
        rep_projet = []
        conso_proj = {
            row['projet_id']: (row['d'] or Decimal('0')) - (row['c'] or Decimal('0'))
            for row in entries.filter(projet__isnull=False)
            .filter(Q(no_compte__startswith='6') | Q(no_compte__startswith='2'))
            .values('projet_id').annotate(d=Sum('debit'), c=Sum('credit'))
        }
        if conso_proj:
            projets = {p.id: p for p in Projet.objects.filter(tenant=tenant, id__in=conso_proj.keys())}
            rep_projet = [{'libelle': projets[pid].libelle if pid in projets else '—',
                           'consomme': float(v)} for pid, v in conso_proj.items() if v]

        ressources_bloc = {
            'total_obtenu': float(total_obtenu),
            'total_consomme': float(total_conso),
            'total_disponible': float(total_obtenu - total_conso),
            'repartition_origine': [{'origine': k, 'montant': float(v['montant']),
                                     'consomme': float(v['consomme'])}
                                    for k, v in rep_origine.items()],
            'repartition_projet': sorted(rep_projet, key=lambda x: -x['consomme']),
            'repartition_financement': rep_financement,
        }

        # ── TRÉSORERIE ────────────────────────────────────────────────────
        canaux = _soldes_canaux(tenant, exercice)
        solde_par_compte = {c['compte']: c['solde'] for c in canaux}
        groupes = {g: round(sum(solde_par_compte.get(cpt, 0.0) for cpt in comptes), 2)
                   for g, comptes in GROUPES_TRESO.items()}
        # Flux entrants/sortants réels (hors virements internes).
        flux = entries.filter(no_compte__in=TRESO_ACCOUNTS).exclude(
            source__in=('TRANSFERT', 'ANNUL_TRANSFERT')).aggregate(
            d=Sum('debit'), c=Sum('credit'))
        tresorerie_bloc = {
            'canaux': canaux,
            'banques': groupes['banques'], 'caisses': groupes['caisses'], 'mobile': groupes['mobile'],
            'total': round(sum(groupes.values()), 2),
            'flux_entrants': float(flux['d'] or 0),
            'flux_sortants': float(flux['c'] or 0),
        }

        # ── INVESTISSEMENTS ───────────────────────────────────────────────
        immos = list(Immobilisation.objects.filter(tenant=tenant, est_cede=False)
                     .select_related('ressource'))
        valeur_brute = sum((i.valeur_entree for i in immos), Decimal('0'))
        cumul_amort  = sum((i.cumul_amortissements for i in immos), Decimal('0'))
        valeur_nette = float(valeur_brute) - float(cumul_amort)
        rep_mode = {}
        for i in immos:
            mode = i.ressource.get_type_ressource_display() if i.ressource_id else 'Fonds propres / trésorerie'
            rep_mode[mode] = rep_mode.get(mode, 0.0) + float(i.valeur_entree)
        investissements_bloc = {
            'nombre': len(immos),
            'valeur_brute': float(valeur_brute),
            'cumul_amortissements': float(cumul_amort),
            'valeur_nette': round(valeur_nette, 2),
            'repartition_financement': [{'mode': k, 'montant': v} for k, v in rep_mode.items()],
        }

        # ── PILOTAGE ──────────────────────────────────────────────────────
        usages_map = {}
        for row in entries.filter(
                Q(no_compte__startswith='6') | Q(no_compte__startswith='2')
        ).values('no_compte').annotate(d=Sum('debit'), c=Sum('credit')):
            cat = _categorie_emploi(row['no_compte'])
            usages_map[cat] = usages_map.get(cat, Decimal('0')) + (row['d'] or 0) - (row['c'] or 0)
        usages = sorted([{'nature': k, 'montant': float(v)} for k, v in usages_map.items() if v],
                        key=lambda x: -x['montant'])
        # Produits, charges et résultat : le MÊME calcul que le compte de
        # résultat et le tableau de bord (apps/comptabilite/resultat.py).
        #
        # Ces deux lignes sommaient le débit BRUT des comptes 6 et le crédit
        # BRUT des comptes 7. Une annulation de règlement ou une neutralisation
        # de migration écrit sa contre-écriture dans l'autre sens : elle était
        # donc ignorée, et l'écran de pilotage — celui qu'on ouvre devant un
        # conseil d'administration ou un bailleur — gonflait produits comme
        # charges. Trois lignes plus haut, le graphique des emplois nettait
        # déjà correctement : le même écran se contredisait lui-même.
        from apps.comptabilite.resultat import totaux_resultat
        _tot = totaux_resultat(entries)
        charges = _tot['total_charges']
        produits = _tot['total_produits']
        taux_global = float(round(total_conso / total_obtenu * 100, 1)) if total_obtenu else 0.0

        # Alertes
        alertes = []
        for r in ressources:
            if r.statut == 'ACTIVE' and r.montant:
                taux = conso_res.get(r.id, Decimal('0')) / r.montant
                if taux >= Decimal('0.9'):
                    alertes.append({'niveau': 'warn',
                                    'message': f"Ressource « {r.libelle} » consommée à {float(taux*100):.0f}%"})
        for p in Projet.objects.filter(tenant=tenant, est_actif=True):
            if p.budget_prevu and conso_proj.get(p.id, Decimal('0')) > p.budget_prevu:
                alertes.append({'niveau': 'danger',
                                'message': f"Projet « {p.libelle} » dépasse son budget"})
        rap_ecart = 0
        for rap in Rapprochement.objects.filter(tenant=tenant, exercice=exercice, statut='EN_COURS'):
            sc = services.solde_comptable_banque(rap.compte_bancaire, rap.date_rapprochement, tenant)
            if abs(_d(rap.solde_releve) - sc) > Decimal('0.01'):
                rap_ecart += 1
        if rap_ecart:
            alertes.append({'niveau': 'info',
                            'message': f"{rap_ecart} rapprochement(s) bancaire(s) avec écart non soldé"})

        pilotage_bloc = {
            'origine': ressources_bloc['repartition_origine'],
            'utilisation': usages,
            'taux_consommation': taux_global,
            'alertes': alertes,
            'indicateurs': {
                'charges': charges, 'produits': produits,
                'resultat': round(produits - charges, 2),
                'nb_ressources': len(ressources),
                'nb_projets': Projet.objects.filter(tenant=tenant, est_actif=True).count(),
                'provisions_actives': float(sum(
                    (p.montant_actuel for p in Provision.objects.filter(
                        tenant=tenant, exercice=exercice, statut='ACTIVE')), Decimal('0'))),
            },
        }

        return Response({
            'exercice': exercice.annee_scolaire,
            'ressources': ressources_bloc,
            'tresorerie': tresorerie_bloc,
            'investissements': investissements_bloc,
            'pilotage': pilotage_bloc,
        })


class TracabiliteGlobaleView(APIView):
    """Traçabilité consolidée de l'exercice : origine / usage / impact du franc."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.comptabilite.models import Immobilisation
        from apps.paiements.models import Paiement

        tenant = get_tenant(request)
        exercice = _exercice_actif(tenant)
        if not exercice:
            return Response({'exercice': None, 'origines': [], 'usages': [], 'impact': {}})

        entries = JournalEntry.objects.filter(tenant=tenant, exercice=exercice)

        # ── D'où vient l'argent ── ressources (mobilisé/consommé) + recettes scolaires
        conso_par_ressource = {
            row['ressource_id']: (row['d'] or Decimal('0')) - (row['c'] or Decimal('0'))
            for row in entries.filter(ressource__isnull=False)
            .filter(Q(no_compte__startswith='6') | Q(no_compte__startswith='2'))
            .values('ressource_id').annotate(d=Sum('debit'), c=Sum('credit'))
        }
        origines = []
        for r in Ressource.objects.filter(tenant=tenant).exclude(statut='ANNULEE'):
            origines.append({
                'origine': r.libelle, 'type': r.get_type_ressource_display(),
                'mobilise': float(r.montant),
                'consomme': float(conso_par_ressource.get(r.id, Decimal('0'))),
            })
        # Recettes scolaires (encaissements élèves) — origine majeure hors ressources GMRF.
        recettes = Paiement.objects.filter(
            tenant=tenant, exercice=exercice, statut='ACTIF').aggregate(
            t=Sum('montant_inscription') + Sum('montant_mensualite') + Sum('montant_uniforme') +
              Sum('montant_fournitures') + Sum('montant_cantine') + Sum('montant_divers'))['t'] or Decimal('0')
        if recettes:
            origines.append({'origine': 'Recettes scolaires', 'type': 'Scolarité',
                             'mobilise': float(recettes), 'consomme': None})

        # ── À quoi il sert ── emplois par nature (net débit sur 6xx/2xx)
        usages_map = {}
        for row in entries.filter(
                Q(no_compte__startswith='6') | Q(no_compte__startswith='2')
        ).values('no_compte').annotate(d=Sum('debit'), c=Sum('credit')):
            cat = _categorie_emploi(row['no_compte'])
            usages_map[cat] = usages_map.get(cat, Decimal('0')) + (row['d'] or 0) - (row['c'] or 0)
        usages = [{'nature': k, 'montant': float(v)} for k, v in usages_map.items() if v]
        usages.sort(key=lambda x: -x['montant'])

        # ── Quel impact ──
        immos = Immobilisation.objects.filter(tenant=tenant, est_cede=False)
        vnc_totale = sum(i.valeur_nette_comptable for i in immos)
        # Net, pour la même raison que le pilotage ci-dessus.
        from apps.comptabilite.resultat import totaux_resultat
        charges_totales = Decimal(str(totaux_resultat(entries)['total_charges']))
        impact = {
            'nb_immobilisations': immos.count(),
            'valeur_nette_immobilisations': float(vnc_totale),
            'nb_projets': Projet.objects.filter(tenant=tenant, est_actif=True).count(),
            'nb_ressources': Ressource.objects.filter(tenant=tenant, statut='ACTIVE').count(),
            'charges_exercice': float(charges_totales),
        }
        return Response({
            'exercice': exercice.annee_scolaire,
            'origines': origines, 'usages': usages, 'impact': impact,
        })
