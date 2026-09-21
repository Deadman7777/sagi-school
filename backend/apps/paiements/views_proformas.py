"""API des factures proforma de scolarité (calcul dans `proformas.py`).

    GET  /api/paiements/proformas/options/      sections, formules, services, réglages
    POST /api/paiements/proformas/apercu/       chiffrage sans enregistrer
    POST /api/paiements/proformas/              émission (numérotée, figée)
    GET  /api/paiements/proformas/?q=           liste
    GET  /api/paiements/proformas/{id}/pdf/     document à remettre au parent
    POST /api/paiements/proformas/{id}/annuler/ {motif}
"""
import datetime

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.models import log_audit
from core.permissions import IsTenantMember
from core.tenant import get_tenant

from . import proformas as P
from .models import Exercice, Proforma


def _date(valeur):
    """« 2026-10-01 » ou « 2026-10 » (sélecteur de mois) → date ; sinon None."""
    if not valeur:
        return None
    texte = str(valeur)[:10]
    try:
        if len(texte) == 7:
            return datetime.date.fromisoformat(texte + '-01')
        return datetime.date.fromisoformat(texte)
    except ValueError:
        raise P.ProformaErreur("Date d'entrée illisible.")


def _auteur(user):
    return ' '.join(x for x in (getattr(user, 'prenom', ''), getattr(user, 'nom', '')) if x) \
        or str(getattr(user, 'email', '') or '')


def _serialiser(p, complet=False):
    donnees = {
        'id': str(p.id), 'numero': p.numero, 'statut': p.statut,
        'date_emission': p.date_emission, 'date_validite': p.date_validite,
        'expiree': p.statut == 'EMISE' and p.date_validite < datetime.date.today(),
        'annee_scolaire': p.annee_scolaire,
        'eleve_id': str(p.eleve_id) if p.eleve_id else None,
        'nouvel_eleve': (p.parametres or {}).get('mode') != 'ELEVE',
        'beneficiaire': p.beneficiaire, 'matricule': p.matricule,
        'section_nom': p.section_nom, 'formule_nom': p.formule_nom,
        'parent_nom': p.parent_nom, 'parent_telephone': p.parent_telephone,
        'total_du': float(p.total_du), 'deja_regle': float(p.deja_regle),
        'part_organisme': float(p.part_organisme), 'organisme_nom': p.organisme_nom,
        'remise_libelle': p.remise_libelle, 'remise_montant': float(p.remise_montant),
        'net_a_payer': float(p.net_a_payer),
        'motif_annulation': p.motif_annulation, 'emise_par': p.emise_par,
    }
    if complet:
        donnees.update({'lignes': p.lignes, 'echeancier': p.echeancier,
                        'observations': p.observations, 'conditions': p.conditions,
                        'parametres': p.parametres})
    return donnees


class ProformaViewSet(viewsets.ViewSet):
    permission_classes = [IsTenantMember]

    # ── Lecture ───────────────────────────────────────────────────────────
    def list(self, request):
        from django.db.models import Q
        tenant = get_tenant(request)
        qs = Proforma.objects.filter(tenant=tenant)
        if q := (request.query_params.get('q') or '').strip():
            qs = qs.filter(Q(numero__icontains=q) | Q(beneficiaire__icontains=q)
                           | Q(parent_nom__icontains=q) | Q(parent_telephone__icontains=q)
                           | Q(matricule__icontains=q))
        if statut := request.query_params.get('statut'):
            qs = qs.filter(statut=statut)
        return Response([_serialiser(p) for p in qs[:300]])

    def retrieve(self, request, pk=None):
        p = self._proforma(request, pk)
        return Response(_serialiser(p, complet=True)) if p else Response(status=404)

    @action(detail=False, methods=['get'])
    def options(self, request):
        """Tout ce que le formulaire propose : grilles de frais, formules,
        services, et les réglages qui changent le chiffrage."""
        from apps.eleves.models import FormuleSection, Section, Service
        from apps.comptabilite.views import get_exercice

        tenant = get_tenant(request)
        exercice = get_exercice(tenant)
        formules = {}
        for f in FormuleSection.objects.filter(tenant=tenant, actif=True):
            formules.setdefault(str(f.section_id), []).append(
                {'id': str(f.id), 'nom': f.nom, 'mensualite': float(f.frais_mensualite)})
        suivant = P.exercice_chiffre(exercice, True) if exercice else None
        return Response({
            'exercice': ({'id': str(exercice.id), 'annee_scolaire': exercice.annee_scolaire,
                          'date_debut': exercice.date_debut, 'date_fin': exercice.date_fin}
                         if exercice else None),
            'annee_suivante': ({'annee_scolaire': suivant.annee_scolaire,
                                'date_debut': suivant.date_debut, 'date_fin': suivant.date_fin}
                               if suivant else None),
            'sections': [{
                'id': str(s.id), 'nom': s.nom,
                'inscription': float(s.frais_inscription),
                'renouvellement': float(s.frais_renouvellement),
                'mensualite': float(s.frais_mensualite),
                'a_la_journee': s.a_la_journee,
                'formules': formules.get(str(s.id), []),
            } for s in Section.objects.filter(tenant=tenant)],
            'services': [{
                'id': str(s.id), 'nom': s.nom, 'montant': float(s.montant),
                'periodicite': s.periodicite,
            } for s in Service.objects.filter(tenant=tenant, actif=True)],
            'renouvellement_actif': bool(getattr(tenant, 'renouvellement_actif', False)),
            'libelle_renouvellement': getattr(tenant, 'libelle_renouvellement', '') or 'Renouvellement',
            'validite_jours': P.VALIDITE_JOURS,
            'conditions': P.derniere_conditions(tenant),
        })

    # ── Chiffrage ─────────────────────────────────────────────────────────
    def _chiffrer(self, request):
        """(résultat, contexte d'émission) — lève ProformaErreur."""
        from apps.comptabilite.views import get_exercice
        from apps.eleves.familles import contact_effectif
        from apps.eleves.models import Eleve, FormuleSection, Section, Service

        tenant = get_tenant(request)
        d = request.data
        mode = d.get('mode') or 'NOUVEAU'
        parametres = {k: d.get(k) for k in (
            'mode', 'eleve_id', 'mois', 'inclure_entree', 'inclure_anterieur',
            'section_id', 'formule_id', 'date_entree', 'service_ids',
            'renouvellement', 'annee_suivante', 'remise_type', 'remise_valeur')
            if d.get(k) not in (None, '', [])}

        if mode == 'ELEVE':
            eleve = Eleve.objects.filter(tenant=tenant, id=d.get('eleve_id')).select_related(
                'section', 'exercice').first() if d.get('eleve_id') else None
            if eleve is None:
                raise P.ProformaErreur('Choisissez un élève.')
            mois = [int(m) for m in (d.get('mois') or [])]
            calcul = P.chiffrer_eleve(eleve, mois=mois or None,
                                      inclure_entree=d.get('inclure_entree', True) is not False,
                                      inclure_anterieur=d.get('inclure_anterieur', True) is not False)
            contact = contact_effectif(eleve)
            contexte = {
                'eleve': eleve, 'exercice': eleve.exercice,
                'beneficiaire': eleve.nom_complet,
                'section_nom': eleve.section.nom if eleve.section else '',
                'formule_nom': (eleve.formule_actuelle.nom if eleve.formule_actuelle else ''),
                'parent_nom': d.get('parent_nom') or contact.get('nom') or '',
                'parent_telephone': d.get('parent_telephone') or contact.get('telephone') or '',
            }
        else:
            exercice = get_exercice(tenant)
            if exercice is None:
                raise P.ProformaErreur("Aucun exercice ouvert : créez l'année scolaire d'abord.")
            section = Section.objects.filter(tenant=tenant, id=d.get('section_id')).first() \
                if d.get('section_id') else None
            if section is None:
                raise P.ProformaErreur('Choisissez la classe (section) demandée.')
            formule = None
            if d.get('formule_id'):
                formule = FormuleSection.objects.filter(
                    tenant=tenant, section=section, id=d['formule_id']).first()
            services = list(Service.objects.filter(tenant=tenant, actif=True,
                                                   id__in=d.get('service_ids') or []))
            calcul = P.chiffrer_nouvel_eleve(
                tenant, exercice, section, formule=formule,
                date_entree=_date(d.get('date_entree')), services=services,
                renouvellement=bool(d.get('renouvellement')),
                annee_suivante=bool(d.get('annee_suivante')))
            contexte = {
                'eleve': None, 'exercice': exercice,
                'beneficiaire': (d.get('beneficiaire') or '').strip(),
                'section_nom': section.nom, 'formule_nom': formule.nom if formule else '',
                'parent_nom': d.get('parent_nom') or '',
                'parent_telephone': d.get('parent_telephone') or '',
            }

        resultat = P.finaliser(calcul, lignes_libres=d.get('lignes_libres') or [],
                               remise_type=d.get('remise_type') or '',
                               remise_valeur=d.get('remise_valeur') or 0,
                               remise_libelle=d.get('remise_libelle') or '')
        if d.get('lignes_libres'):
            parametres['lignes_libres'] = d['lignes_libres']
        contexte['parametres'] = parametres
        return resultat, contexte

    @action(detail=False, methods=['post'])
    def apercu(self, request):
        try:
            resultat, ctx = self._chiffrer(request)
        except P.ProformaErreur as e:
            return Response({'error': str(e)}, status=400)
        return Response({**resultat,
                         'beneficiaire': ctx['beneficiaire'], 'section_nom': ctx['section_nom'],
                         'formule_nom': ctx['formule_nom'], 'parent_nom': ctx['parent_nom'],
                         'parent_telephone': ctx['parent_telephone']})

    def create(self, request):
        tenant = get_tenant(request)
        d = request.data
        try:
            resultat, ctx = self._chiffrer(request)
            p = P.emettre(
                tenant, ctx['exercice'], resultat, eleve=ctx['eleve'],
                beneficiaire=ctx['beneficiaire'], section_nom=ctx['section_nom'],
                formule_nom=ctx['formule_nom'], parent_nom=ctx['parent_nom'],
                parent_telephone=ctx['parent_telephone'],
                validite_jours=d.get('validite_jours'),
                observations=d.get('observations') or '', conditions=d.get('conditions') or '',
                parametres=ctx['parametres'], auteur=_auteur(request.user))
        except P.ProformaErreur as e:
            return Response({'error': str(e)}, status=400)
        log_audit(request, 'CREATE', 'Proforma', str(p.id),
                  f"Proforma {p.numero} — {p.beneficiaire} — {float(p.net_a_payer):,.0f} FCFA")
        return Response(_serialiser(p, complet=True), status=status.HTTP_201_CREATED)

    # ── Document et annulation ────────────────────────────────────────────
    def _proforma(self, request, pk):
        return Proforma.objects.filter(tenant=get_tenant(request), id=pk).select_related(
            'tenant').first()

    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        from io import BytesIO
        import re
        import unicodedata

        from django.http import HttpResponse
        from django.template.loader import render_to_string
        from xhtml2pdf import pisa

        p = self._proforma(request, pk)
        if p is None:
            return Response(status=404)
        html = render_to_string('pdf/proforma_scolarite.html', P.contexte_pdf(p))
        buf = BytesIO()
        if pisa.CreatePDF(html, dest=buf, encoding='utf-8').err:
            return HttpResponse('Erreur génération PDF.', status=500)
        nom = unicodedata.normalize('NFD', p.beneficiaire or '')
        nom = re.sub(r'[^A-Za-z0-9-]', '', nom.encode('ascii', 'ignore').decode())
        resp = HttpResponse(buf.getvalue(), content_type='application/pdf')
        resp['Content-Disposition'] = (
            f'inline; filename="proforma_{p.numero}{"_" + nom if nom else ""}.pdf"')
        return resp

    @action(detail=True, methods=['post'])
    def annuler(self, request, pk=None):
        p = self._proforma(request, pk)
        if p is None:
            return Response(status=404)
        if p.statut == 'ANNULEE':
            return Response({'error': 'Cette proforma est déjà annulée.'}, status=400)
        motif = (request.data.get('motif') or '').strip()
        if not motif:
            return Response({'error': "Indiquez le motif de l'annulation."}, status=400)
        p.statut, p.motif_annulation = 'ANNULEE', motif[:255]
        p.save(update_fields=['statut', 'motif_annulation', 'updated_at'])
        log_audit(request, 'ANNULER', 'Proforma', str(p.id), f"Proforma {p.numero} — {motif}")
        return Response(_serialiser(p, complet=True))
