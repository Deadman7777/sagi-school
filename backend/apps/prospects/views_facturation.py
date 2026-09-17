"""L'API de facturation commerciale — réservée à HADY GESMAN (SUPER_ADMIN).

Les règles (numérotation à l'émission, pièce émise figée, avoir pour corriger)
sont appliquées dans `facturation.py` ; cette couche traduit les requêtes et
renvoie un message lisible quand une opération est refusée.
"""
from datetime import date

from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsSuperAdmin

from . import facturation as F
from .models import (MODES_ENCAISSEMENT, Devis, DocumentCommercial, Encaissement,
                     JustificatifFacturation, ParametresFacturation, Prospect)

CHAMPS_CLIENT = ('client_nom', 'client_contact', 'client_adresse', 'client_ville',
                 'client_telephone', 'client_email', 'client_ninea')
CHAMPS_TEXTE = ('objet', 'motif', 'conditions', 'observations')


def _auteur(request):
    return str(request.user)


def _erreur(exc, code=400):
    return Response({'error': str(exc)}, status=code)


def _date(valeur):
    if not valeur:
        return None
    try:
        return date.fromisoformat(str(valeur)[:10])
    except ValueError:
        raise F.FacturationErreur('Date invalide.')


def _justificatif_dict(j):
    """Sans le contenu : la liste reste légère, le fichier se télécharge à part."""
    return {
        'id': str(j.id), 'nom': j.nom, 'type_piece': j.type_piece,
        'type_libelle': j.get_type_piece_display(), 'mime_type': j.mime_type, 'taille': j.taille,
        'observations': j.observations, 'ajoute_par': j.ajoute_par, 'created_at': j.created_at,
    }


def _recu_dict(r):
    return {
        'justificatifs': [_justificatif_dict(j) for j in r.justificatifs.defer('contenu')],
        'id': str(r.id), 'numero': r.numero, 'date': r.date, 'montant': int(r.montant),
        'mode': r.mode, 'mode_libelle': r.get_mode_display(), 'reference': r.reference,
        'observations': r.observations, 'recu_par': r.recu_par,
        'annule': r.annule, 'annule_motif': r.annule_motif,
        'facture': str(r.facture_id), 'facture_numero': r.facture.numero,
        'client_nom': r.facture.client_nom,
    }


def _document_dict(d, complet=False):
    base = {
        'id': str(d.id), 'type': d.type, 'type_libelle': d.get_type_display(),
        'numero': d.numero, 'statut': d.statut, 'statut_libelle': d.get_statut_display(),
        'client_nom': d.client_nom, 'objet': d.objet,
        'date_emission': d.date_emission, 'date_echeance': d.date_echeance,
        'date_validite': d.date_validite,
        'total_ht': int(d.total_ht), 'montant_tva': int(d.montant_tva), 'total_ttc': int(d.total_ttc),
        'statut_paiement': d.statut_paiement,
        'solde': int(d.solde), 'en_retard': d.en_retard,
        'prospect': str(d.prospect_id) if d.prospect_id else None,
        'tenant': str(d.tenant_id) if d.tenant_id else None,
        'modifiable': d.modifiable, 'created_at': d.created_at,
        'taux_acompte': float(d.taux_acompte), 'montant_acompte': int(d.montant_acompte),
        'acompte_recu': d.acompte_recu, 'etape': d.etape,
        'prestation_demarree_le': d.prestation_demarree_le,
        'prestation_livree_le': d.prestation_livree_le,
    }
    if not complet:
        return base
    base.update({f: getattr(d, f) for f in CHAMPS_CLIENT + CHAMPS_TEXTE})
    base.update({
        'tva_applicable': d.tva_applicable, 'taux_tva': float(d.taux_tva),
        'mention_tva': d.mention_tva,
        'montant_encaisse': int(d.montant_encaisse), 'montant_avoirs': int(d.montant_avoirs),
        'devis': str(d.devis_id) if d.devis_id else None,
        'devis_numero': d.devis.numero if d.devis_id else None,
        'origine': str(d.origine_id) if d.origine_id else None,
        'origine_numero': d.origine.numero if d.origine_id else None,
        'derives': [{'id': str(x.id), 'type': x.type, 'numero': x.numero, 'statut': x.statut,
                     'total_ttc': int(x.total_ttc)} for x in d.derives.all()],
        'etabli_par': d.etabli_par, 'emis_par': d.emis_par, 'emis_le': d.emis_le,
        'lignes': [{
            'id': str(l.id), 'designation': l.designation, 'detail': l.detail,
            'quantite': float(l.quantite), 'unite': l.unite,
            'prix_unitaire': int(l.prix_unitaire), 'montant': int(l.montant),
        } for l in d.lignes.all()],
        'encaissements': [_recu_dict(r) for r in d.encaissements.all()],
        'echeancier': [{**e, 'montant': int(e['montant']), 'paye': int(e['paye'])}
                       for e in F.echeancier(d)],
        'justificatifs': [_justificatif_dict(j) for j in d.justificatifs.defer('contenu')],
    })
    return base


class ParametresFacturationView(APIView):
    permission_classes = [IsSuperAdmin]
    CHAMPS = ('raison_sociale', 'forme_juridique', 'adresse', 'ville', 'telephone', 'email',
              'site_web', 'ninea', 'rccm', 'mention_sans_tva', 'coordonnees_paiement', 'conditions')

    def _dict(self, p):
        d = {c: getattr(p, c) for c in self.CHAMPS}
        d.update({'tva_applicable': p.tva_applicable, 'taux_tva': float(p.taux_tva),
                  'delai_paiement_jours': p.delai_paiement_jours,
                  'validite_proforma_jours': p.validite_proforma_jours,
                  'taux_acompte_defaut': float(p.taux_acompte_defaut),
                  'types_justificatif': [{'value': c, 'label': l}
                                         for c, l in JustificatifFacturation.TYPE_CHOICES],
                  'modes': [{'value': c, 'label': l} for c, l in MODES_ENCAISSEMENT]})
        return d

    def get(self, request):
        return Response(self._dict(ParametresFacturation.actuels()))

    def patch(self, request):
        p = ParametresFacturation.actuels()
        for champ in self.CHAMPS:
            if champ in request.data:
                setattr(p, champ, str(request.data[champ] or '').strip()[:2000])
        if 'tva_applicable' in request.data:
            p.tva_applicable = bool(request.data['tva_applicable'])
        try:
            if 'taux_tva' in request.data:
                taux = float(request.data['taux_tva'])
                if not 0 <= taux <= 100:
                    raise ValueError
                p.taux_tva = taux
            for champ in ('delai_paiement_jours', 'validite_proforma_jours'):
                if champ in request.data:
                    jours = int(request.data[champ])
                    if not 0 <= jours <= 365:
                        raise ValueError
                    setattr(p, champ, jours)
            if 'taux_acompte_defaut' in request.data:
                p.taux_acompte_defaut = F.taux_acompte_valide(request.data['taux_acompte_defaut'])
        except F.FacturationErreur as exc:
            return _erreur(exc)
        except (TypeError, ValueError):
            return _erreur('Taux de TVA (0 à 100) ou délai (0 à 365 jours) invalide.')
        p.save()
        return Response(self._dict(p))


class DocumentCommercialViewSet(viewsets.ViewSet):
    permission_classes = [IsSuperAdmin]

    def _get(self, pk):
        return DocumentCommercial.objects.filter(pk=pk).first()

    def _filtrer(self, request):
        qs = DocumentCommercial.objects.select_related('origine')
        q = request.query_params
        if q.get('type'):
            qs = qs.filter(type=q['type'])
        if q.get('statut'):
            qs = qs.filter(statut=q['statut'])
        if q.get('prospect'):
            qs = qs.filter(prospect_id=q['prospect'])
        if q.get('tenant'):
            qs = qs.filter(tenant_id=q['tenant'])
        if q.get('recherche'):
            from django.db.models import Q
            r = q['recherche']
            qs = qs.filter(Q(client_nom__icontains=r) | Q(numero__icontains=r) | Q(objet__icontains=r))
        documents = list(qs[:500])
        if q.get('suivi'):              # prestations avec acompte pas encore terminées
            documents = [d for d in documents if d.etape not in (None, 'TERMINEE')]
        if q.get('impayees'):
            documents = [d for d in documents if d.statut_paiement in ('A_PAYER', 'PARTIELLE')]
        return documents

    def list(self, request):
        return Response([_document_dict(d) for d in self._filtrer(request)])

    @action(detail=False, methods=['get'], url_path='etat-pdf')
    def etat_pdf(self, request):
        """La liste telle que filtrée à l'écran, en PDF, avec ses totaux."""
        q = request.query_params
        filtre = ('Factures impayées' if q.get('impayees') else
                  'Prestations en cours de suivi' if q.get('suivi') else
                  {'PROFORMA': 'Factures proforma', 'FACTURE': 'Factures', 'AVOIR': 'Avoirs'}
                  .get(q.get('type'), 'Toutes les pièces'))
        if q.get('recherche'):
            filtre += f" — « {q['recherche']} »"
        try:
            octets = F.rendre_pdf('pdf/etat_facturation.html',
                                  F.contexte_etat(self._filtrer(request), filtre))
        except F.FacturationErreur as exc:
            return HttpResponse(str(exc), status=500)
        reponse = HttpResponse(octets, content_type='application/pdf')
        reponse['Content-Disposition'] = f'attachment; filename="etat-facturation-{date.today():%Y-%m-%d}.pdf"'
        return reponse

    @action(detail=True, methods=['get'], url_path='releve-pdf')
    def releve_pdf(self, request, pk=None):
        """Relevé de compte du client de cette pièce (même prospect, même école, ou même nom)."""
        d = self._get(pk)
        if not d:
            return HttpResponse('Document introuvable', status=404)
        documents = list(F.documents_du_client(prospect=d.prospect, tenant=d.tenant,
                                               client_nom=d.client_nom)
                         .prefetch_related('encaissements', 'derives'))
        # Coordonnées de la pièce la plus récente : c'est la plus à jour.
        recente = max(documents, key=lambda x: x.created_at, default=d)
        client = {f.replace('client_', ''): getattr(recente, f) for f in CHAMPS_CLIENT}
        try:
            octets = F.rendre_pdf('pdf/releve_compte_client.html', F.contexte_releve(documents, client))
        except F.FacturationErreur as exc:
            return HttpResponse(str(exc), status=500)
        import re
        nom = re.sub(r'[^A-Za-z0-9]+', '-', recente.client_nom).strip('-')[:40] or 'client'
        reponse = HttpResponse(octets, content_type='application/pdf')
        reponse['Content-Disposition'] = f'attachment; filename="releve-{nom}-{date.today():%Y-%m-%d}.pdf"'
        return reponse

    def retrieve(self, request, pk=None):
        d = self._get(pk)
        if not d:
            return _erreur('Document introuvable.', 404)
        return Response(_document_dict(d, complet=True))

    def create(self, request):
        """Brouillon depuis une source : {"type", "devis"|"prospect"|"tenant"|client…, "lignes"}.

        Pour une école cliente, "renouvellement_mois" préremplit la licence depuis le catalogue.
        """
        data = request.data
        type_doc = str(data.get('type') or '').upper()
        if type_doc == 'AVOIR':
            return _erreur("Un avoir s'établit depuis la facture qu'il corrige.")
        try:
            if data.get('devis'):
                devis = Devis.objects.filter(pk=data['devis']).first()
                if not devis:
                    return _erreur('Devis introuvable.')
                document = F.depuis_devis(devis, type_doc, auteur=_auteur(request))
            else:
                prospect = tenant = None
                if data.get('prospect'):
                    prospect = Prospect.objects.filter(pk=data['prospect']).first()
                    if not prospect:
                        return _erreur('Prospect introuvable.')
                if data.get('tenant'):
                    from apps.tenants.models import Tenant
                    tenant = Tenant.objects.filter(pk=data['tenant']).first()
                    if not tenant:
                        return _erreur('École introuvable.')
                lignes = data.get('lignes') or []
                objet = str(data.get('objet') or '')
                if tenant is not None and data.get('renouvellement_mois'):
                    mois = int(data['renouvellement_mois'])
                    if not 1 <= mois <= 60:
                        return _erreur('La durée doit tenir entre 1 et 60 mois.')
                    lignes = F.lignes_renouvellement(tenant, mois)
                    objet = objet or 'Renouvellement de licence SAGI SCHOOL'
                client = {c: data.get(c) for c in CHAMPS_CLIENT if data.get(c)}
                document = F.creer_brouillon(type_doc, auteur=_auteur(request), prospect=prospect,
                                             tenant=tenant, client=client, lignes=lignes,
                                             objet=objet, observations=str(data.get('observations') or ''),
                                             taux_acompte=data.get('taux_acompte'))
        except F.FacturationErreur as exc:
            return _erreur(exc)
        return Response(_document_dict(document, complet=True), status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        d = self._get(pk)
        if not d:
            return _erreur('Document introuvable.', 404)
        if not d.modifiable:
            return _erreur("Cette pièce est émise : elle ne se modifie plus. "
                           "Pour corriger une facture, établissez un avoir.", 409)
        data = request.data
        try:
            for champ in CHAMPS_CLIENT + CHAMPS_TEXTE:
                if champ in data:
                    setattr(d, champ, str(data[champ] or '').strip()[:2000 if champ in CHAMPS_TEXTE else 300])
            if not d.client_nom.strip():
                return _erreur('Le nom du client est obligatoire.')
            for champ in ('date_echeance', 'date_validite'):
                if champ in data:
                    setattr(d, champ, _date(data[champ]))
            if d.type != 'AVOIR':           # l'avoir garde la TVA de sa facture
                if 'tva_applicable' in data:
                    d.tva_applicable = bool(data['tva_applicable'])
                if 'taux_tva' in data:
                    taux = float(data['taux_tva'])
                    if not 0 <= taux <= 100:
                        return _erreur('Taux de TVA invalide.')
                    d.taux_tva = taux
                if 'mention_tva' in data:
                    d.mention_tva = str(data['mention_tva'] or '').strip()[:250]
                if 'taux_acompte' in data:
                    d.taux_acompte = F.taux_acompte_valide(data['taux_acompte'])
            d.save()
            if 'lignes' in data:
                F.remplacer_lignes(d, data['lignes'] or [])
            else:
                F.recalculer(d)
        except F.FacturationErreur as exc:
            return _erreur(exc)
        except (TypeError, ValueError):
            return _erreur('Valeur invalide.')
        return Response(_document_dict(d, complet=True))

    def destroy(self, request, pk=None):
        d = self._get(pk)
        if not d:
            return _erreur('Document introuvable.', 404)
        if not d.modifiable:
            return _erreur("Une pièce émise ne se supprime pas.", 409)
        d.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def emettre(self, request, pk=None):
        d = self._get(pk)
        if not d:
            return _erreur('Document introuvable.', 404)
        try:
            F.emettre(d, auteur=_auteur(request))
        except F.FacturationErreur as exc:
            return _erreur(exc, 409)
        return Response(_document_dict(d, complet=True))

    @action(detail=True, methods=['post'])
    def convertir(self, request, pk=None):
        """Proforma émise → facture en brouillon."""
        d = self._get(pk)
        if not d:
            return _erreur('Document introuvable.', 404)
        try:
            facture = F.convertir_proforma(d, auteur=_auteur(request))
        except F.FacturationErreur as exc:
            return _erreur(exc, 409)
        return Response(_document_dict(facture, complet=True), status=status.HTTP_201_CREATED)

    def _etape(self, request, pk, fonction):
        d = self._get(pk)
        if not d:
            return _erreur('Document introuvable.', 404)
        try:
            fonction(d, jour=_date(request.data.get('date')), auteur=_auteur(request))
        except F.FacturationErreur as exc:
            return _erreur(exc, 409)
        return Response(_document_dict(d, complet=True))

    @action(detail=True, methods=['post'])
    def demarrer(self, request, pk=None):
        """Acompte reçu → la prestation démarre."""
        return self._etape(request, pk, F.demarrer_prestation)

    @action(detail=True, methods=['post'])
    def livrer(self, request, pk=None):
        """Prestation livrée → le solde devient exigible."""
        return self._etape(request, pk, F.livrer_prestation)

    @action(detail=True, methods=['post'])
    def avoir(self, request, pk=None):
        """Facture émise → avoir en brouillon (total par défaut)."""
        d = self._get(pk)
        if not d:
            return _erreur('Document introuvable.', 404)
        try:
            avoir = F.preparer_avoir(d, auteur=_auteur(request),
                                     motif=str(request.data.get('motif') or '').strip())
        except F.FacturationErreur as exc:
            return _erreur(exc, 409)
        return Response(_document_dict(avoir, complet=True), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def encaisser(self, request, pk=None):
        d = self._get(pk)
        if not d:
            return _erreur('Document introuvable.', 404)
        mode = str(request.data.get('mode') or 'VIREMENT')
        if mode not in dict(MODES_ENCAISSEMENT):
            return _erreur('Mode de paiement inconnu.')
        try:
            recu = F.encaisser(d, request.data.get('montant'), mode=mode,
                               jour=_date(request.data.get('date')),
                               reference=str(request.data.get('reference') or '').strip(),
                               observations=str(request.data.get('observations') or '').strip(),
                               auteur=_auteur(request))
        except F.FacturationErreur as exc:
            return _erreur(exc, 409)
        return Response({'recu': _recu_dict(recu), 'facture': _document_dict(d, complet=True)},
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        d = self._get(pk)
        if not d:
            return HttpResponse('Document introuvable', status=404)
        try:
            octets = F.rendre_pdf('pdf/document_commercial.html', F.contexte_document(d))
        except F.FacturationErreur as exc:
            return HttpResponse(str(exc), status=500)
        nom = d.numero or f'{d.get_type_display()}-BROUILLON'.replace(' ', '-')
        reponse = HttpResponse(octets, content_type='application/pdf')
        reponse['Content-Disposition'] = f'inline; filename="{nom}.pdf"'
        return reponse

    @action(detail=False, methods=['get'])
    def synthese(self, request):
        return Response(F.synthese())

    @action(detail=False, methods=['get'])
    def clients(self, request):
        """Les écoles clientes, avec leur licence, pour préremplir une facture."""
        from apps.tenants.models import Tenant
        ecoles = []
        for t in Tenant.objects.select_related('licence').order_by('nom'):
            licence = getattr(t, 'licence', None)
            ecoles.append({'id': str(t.id), 'nom': t.nom, 'ville': t.ville,
                           'licence_type': licence.type if licence else None,
                           'licence_fin': licence.date_fin if licence else None})
        return Response(ecoles)


class JustificatifViewSet(viewsets.ViewSet):
    """Pièces justificatives : {"document"|"encaissement", "nom", "contenu" (data URI), "type_piece"}."""
    permission_classes = [IsSuperAdmin]

    def list(self, request):
        qs = JustificatifFacturation.objects.all()
        if d := request.query_params.get('document'):
            qs = qs.filter(document_id=d)
        if e := request.query_params.get('encaissement'):
            qs = qs.filter(encaissement_id=e)
        return Response([_justificatif_dict(j) for j in qs.defer('contenu')[:500]])

    def create(self, request):
        data = request.data
        document = encaissement = None
        if data.get('document'):
            document = DocumentCommercial.objects.filter(pk=data['document']).first()
            if not document:
                return _erreur('Document introuvable.', 404)
        if data.get('encaissement'):
            encaissement = Encaissement.objects.filter(pk=data['encaissement']).first()
            if not encaissement:
                return _erreur('Reçu introuvable.', 404)
        try:
            piece = F.ajouter_justificatif(data.get('contenu'), data.get('nom'), document=document,
                                           encaissement=encaissement,
                                           type_piece=str(data.get('type_piece') or ''),
                                           observations=data.get('observations'),
                                           auteur=_auteur(request))
        except F.FacturationErreur as exc:
            return _erreur(exc)
        return Response(_justificatif_dict(piece), status=status.HTTP_201_CREATED)

    def destroy(self, request, pk=None):
        piece = JustificatifFacturation.objects.filter(pk=pk).first()
        if not piece:
            return _erreur('Pièce introuvable.', 404)
        F.supprimer_justificatif(piece, auteur=_auteur(request))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'])
    def fichier(self, request, pk=None):
        piece = JustificatifFacturation.objects.filter(pk=pk).first()
        if not piece:
            return HttpResponse('Pièce introuvable', status=404)
        octets, mime = F.fichier_justificatif(piece)
        reponse = HttpResponse(octets, content_type=mime)
        from urllib.parse import quote
        ascii_nom = piece.nom.encode('ascii', 'ignore').decode().replace('"', '') or 'justificatif'
        reponse['Content-Disposition'] = (f'inline; filename="{ascii_nom}"; '
                                          f"filename*=UTF-8''{quote(piece.nom)}")
        return reponse


class EncaissementViewSet(viewsets.ViewSet):
    permission_classes = [IsSuperAdmin]

    def list(self, request):
        qs = Encaissement.objects.select_related('facture')
        if f := request.query_params.get('facture'):
            qs = qs.filter(facture_id=f)
        return Response([_recu_dict(r) for r in qs[:500]])

    @action(detail=True, methods=['post'])
    def annuler(self, request, pk=None):
        recu = Encaissement.objects.filter(pk=pk).first()
        if not recu:
            return _erreur('Reçu introuvable.', 404)
        try:
            F.annuler_encaissement(recu, str(request.data.get('motif') or ''), auteur=_auteur(request))
        except F.FacturationErreur as exc:
            return _erreur(exc, 409)
        return Response(_recu_dict(recu))

    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        recu = Encaissement.objects.filter(pk=pk).first()
        if not recu:
            return HttpResponse('Reçu introuvable', status=404)
        try:
            octets = F.rendre_pdf('pdf/recu_encaissement.html', F.contexte_recu(recu))
        except F.FacturationErreur as exc:
            return HttpResponse(str(exc), status=500)
        reponse = HttpResponse(octets, content_type='application/pdf')
        reponse['Content-Disposition'] = f'inline; filename="{recu.numero}.pdf"'
        return reponse
