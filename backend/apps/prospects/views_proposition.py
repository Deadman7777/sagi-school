"""API des propositions commerciales et de la bibliothèque de documents.

Réservée à HADY GESMAN (SUPER_ADMIN). Mêmes transitions que les devis :
BROUILLON (modifiable) → VALIDEE (relue, figée) → ENVOYEE → ACCEPTEE / REFUSEE.
Une proposition validée ne se réécrit plus : on la duplique.
"""
from decimal import Decimal, InvalidOperation

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.licences.models import Licence
from core.permissions import IsSuperAdmin

from . import proposition as PR
from .messagerie import EnvoiErreur, decoder_data_uri, smtp_configure
from .models import DocumentBibliotheque, Prospect, PropositionCommerciale

CHAMPS_TEXTE = {'etablissement': 200, 'sous_titre': 250, 'adresse': 300, 'telephones': 200,
                'email': 254, 'autres_contacts': 200, 'a_l_attention': 200, 'contact_nom': 200,
                'programme': 150, 'edition': 20, 'contexte': 6000}
CHAMPS_MONTANT = ('frais_installation', 'frais_migration')
CHAMPS_TAUX = ('taux_semestriel', 'taux_annuel')

TAILLE_MAX_DOCUMENT = 10 * 1024 * 1024
TAILLE_MAX_CACHET = 1024 * 1024


def _erreur(message, code=400):
    return Response({'error': str(message)}, status=code)


def _document_dict(d):
    return {'id': str(d.id), 'titre': d.titre, 'categorie': d.categorie,
            'categorie_libelle': d.get_categorie_display(), 'description': d.description,
            'nom_fichier': d.nom_fichier, 'taille': d.taille,
            'joindre_par_defaut': d.joindre_par_defaut, 'actif': d.actif, 'ordre': d.ordre,
            'created_at': d.created_at}


def _proposition_dict(p, complet=False):
    ch = PR.chiffrage(p)
    base = {
        'id': str(p.id), 'reference': p.reference,
        'prospect': str(p.prospect_id) if p.prospect_id else None,
        'etablissement': p.etablissement, 'type_licence': p.type_licence,
        'licence_libelle': PR.libelle_licence(p.type_licence),
        'statut': p.statut, 'statut_libelle': p.get_statut_display(),
        'date_emission': p.date_emission, 'date_validite': p.date_validite,
        'expiree': p.expiree, 'modifiable': p.modifiable,
        'total_annuel': ch['annuelle']['total'],
        'envoyee_le': p.envoyee_le, 'envoyee_a': p.envoyee_a, 'erreur_envoi': p.erreur_envoi,
        'formule_choisie': p.formule_choisie,
        'formule_libelle': p.get_formule_choisie_display() if p.formule_choisie else '',
        'migration_choisie': p.migration_choisie,
    }
    if not complet:
        return base
    base.update({c: getattr(p, c) for c in CHAMPS_TEXTE})
    base.update({
        'besoins': p.besoins or [], 'resultats': p.resultats or [],
        'prix_mensuel': int(p.prix_mensuel),
        'taux_semestriel': float(p.taux_semestriel), 'taux_annuel': float(p.taux_annuel),
        'frais_installation': int(p.frais_installation), 'frais_migration': int(p.frais_migration),
        'migration_proposee': p.migration_proposee, 'validite_jours': p.validite_jours,
        'documents_joints': [str(i) for i in p.documents_joints.values_list('id', flat=True)],
        'chiffrage': ch, 'etablie_par': p.etablie_par, 'validee_par': p.validee_par,
        'validee_le': p.validee_le,
    })
    return base


class PropositionViewSet(viewsets.ViewSet):
    permission_classes = [IsSuperAdmin]

    def _get(self, pk):
        return PropositionCommerciale.objects.filter(pk=pk).first()

    def list(self, request):
        qs = PropositionCommerciale.objects.all()
        if prospect := request.query_params.get('prospect'):
            qs = qs.filter(prospect_id=prospect)
        if statut := request.query_params.get('statut'):
            qs = qs.filter(statut=statut)
        return Response([_proposition_dict(p) for p in qs[:300]])

    def retrieve(self, request, pk=None):
        p = self._get(pk)
        return Response(_proposition_dict(p, complet=True)) if p else _erreur('Introuvable.', 404)

    def create(self, request):
        """Depuis une fiche (`prospect`), ou pour un client qui n'en a pas encore :
        `etablissement` (+ ville, téléphone, e-mail, interlocuteur). La fiche est
        alors créée — ou retrouvée, par le même rapprochement des doublons que
        la saisie manuelle — pour que l'affaire soit suivie comme les autres."""
        d = request.data
        if d.get('prospect'):
            prospect = Prospect.objects.filter(pk=d.get('prospect')).first()
            if not prospect:
                return _erreur('Fiche prospect introuvable.', 404)
        else:
            if not str(d.get('etablissement') or '').strip():
                return _erreur("Indiquez le nom de l'établissement.")
            from .enregistrement import enregistrer_demande
            champs = ('etablissement', 'ville', 'telephone', 'email', 'contact_nom',
                      'type_organisation')
            try:
                prospect, _ = enregistrer_demande(
                    {c: str(d.get(c) or '').strip() for c in champs if d.get(c)},
                    source='MANUEL', canal='AUTRE',
                    resume='Fiche créée depuis une proposition commerciale.',
                    auteur=str(request.user))
            except ValueError as exc:
                return _erreur(exc)
        try:
            p = PR.etablir(prospect, str(request.data.get('type_licence') or ''),
                           auteur=str(request.user))
        except PR.PropositionErreur as exc:
            return _erreur(exc)
        return Response(_proposition_dict(p, complet=True), status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        p = self._get(pk)
        if not p:
            return _erreur('Introuvable.', 404)
        if not p.modifiable:
            return _erreur("Une proposition validée ne se modifie plus : dupliquez-la.")
        d = request.data
        for champ, longueur in CHAMPS_TEXTE.items():
            if champ in d:
                setattr(p, champ, str(d[champ] or '').strip()[:longueur])
        for champ in ('besoins', 'resultats'):
            if champ in d:
                lignes = d[champ] if isinstance(d[champ], list) else str(d[champ] or '').split('\n')
                setattr(p, champ, [str(l).strip()[:400] for l in lignes if str(l).strip()][:15])
        try:
            for champ in CHAMPS_MONTANT:
                if champ in d:
                    valeur = Decimal(str(d[champ] or 0)).quantize(Decimal('1'))
                    if valeur < 0:
                        raise InvalidOperation
                    setattr(p, champ, valeur)
            for champ in CHAMPS_TAUX:
                if champ in d:
                    taux = Decimal(str(d[champ] or 0))
                    if not 0 <= taux < 1:
                        raise InvalidOperation
                    setattr(p, champ, taux)
            if 'validite_jours' in d:
                jours = int(d['validite_jours'])
                if not 1 <= jours <= 180:
                    raise ValueError
                p.validite_jours = jours
        except (InvalidOperation, ValueError, TypeError):
            return _erreur('Montant, taux (0 à 99 %) ou validité (1 à 180 jours) invalide.')
        if 'migration_proposee' in d:
            p.migration_proposee = bool(d['migration_proposee'])
        if 'type_licence' in d and d['type_licence'] != p.type_licence:
            nouveau = str(d['type_licence'])
            if nouveau not in dict(Licence.TYPE_CHOICES) or nouveau == 'ESSAI':
                return _erreur('Choisissez une licence payante.')
            from apps.licences.catalogue import tarif_mensuel
            p.type_licence, p.prix_mensuel = nouveau, tarif_mensuel(nouveau)
        if not p.etablissement:
            return _erreur("Le nom de l'établissement est obligatoire.")
        p.save()
        if 'documents_joints' in d:
            p.documents_joints.set(DocumentBibliotheque.objects.filter(
                id__in=[str(i) for i in (d['documents_joints'] or [])], actif=True))
        return Response(_proposition_dict(p, complet=True))

    def destroy(self, request, pk=None):
        p = self._get(pk)
        if not p:
            return _erreur('Introuvable.', 404)
        if p.statut != 'BROUILLON':
            return _erreur("Seul un brouillon se supprime ; une proposition validée reste tracée.")
        p.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        from .proposition_pdf import rendre_pdf
        p = self._get(pk)
        if not p:
            return _erreur('Introuvable.', 404)
        reponse = HttpResponse(rendre_pdf(p), content_type='application/pdf')
        reponse['Content-Disposition'] = f'inline; filename="{PR.nom_fichier(p)}"'
        return reponse

    @action(detail=True, methods=['post'])
    def valider(self, request, pk=None):
        p = self._get(pk)
        if not p:
            return _erreur('Introuvable.', 404)
        if p.statut != 'BROUILLON':
            return _erreur('Seul un brouillon se valide.')
        if p.expiree:
            return _erreur("Sa validité est dépassée : mettez à jour la date ou dupliquez-la.")
        p.statut, p.validee_par, p.validee_le = 'VALIDEE', str(request.user), timezone.now()
        p.save(update_fields=['statut', 'validee_par', 'validee_le', 'updated_at'])
        return Response(_proposition_dict(p, complet=True))

    @action(detail=True, methods=['post'])
    def rouvrir(self, request, pk=None):
        """Validée mais pas encore envoyée : on peut encore la corriger."""
        p = self._get(pk)
        if not p:
            return _erreur('Introuvable.', 404)
        if p.statut != 'VALIDEE':
            return _erreur("Une proposition déjà envoyée ne se rouvre pas : dupliquez-la.")
        p.statut, p.validee_par, p.validee_le = 'BROUILLON', '', None
        p.save(update_fields=['statut', 'validee_par', 'validee_le', 'updated_at'])
        return Response(_proposition_dict(p, complet=True))

    @action(detail=True, methods=['post'])
    def dupliquer(self, request, pk=None):
        source = self._get(pk)
        if not source:
            return _erreur('Introuvable.', 404)
        documents = list(source.documents_joints.all())
        copie = PropositionCommerciale.objects.get(pk=source.pk)
        copie.pk = None
        copie.id = None
        copie.reference = PR.prochaine_reference(source.etablissement)
        copie.statut = 'BROUILLON'
        copie.date_emission = timezone.localdate()
        for champ in ('validee_par', 'envoyee_a', 'erreur_envoi', 'formule_choisie'):
            setattr(copie, champ, '')
        copie.validee_le = copie.envoyee_le = copie.repondue_le = None
        copie.migration_choisie = None
        copie.etablie_par = str(request.user)
        copie.save()
        copie.documents_joints.set(documents)
        return Response(_proposition_dict(copie, complet=True), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def courriel(self, request, pk=None):
        """Le courriel proposé (modifiable à l'écran) et le lien WhatsApp."""
        p = self._get(pk)
        if not p:
            return _erreur('Introuvable.', 404)
        return Response({**PR.courriel_par_defaut(p), 'whatsapp': PR.whatsapp(p),
                         'smtp': smtp_configure()})

    @action(detail=True, methods=['post'])
    def envoyer(self, request, pk=None):
        p = self._get(pk)
        if not p:
            return _erreur('Introuvable.', 404)
        d = request.data
        defaut = PR.courriel_par_defaut(p)
        ids = d.get('documents')
        documents = (list(DocumentBibliotheque.objects.filter(id__in=[str(i) for i in ids], actif=True))
                     if isinstance(ids, list) else list(p.documents_joints.filter(actif=True)))
        try:
            servis = PR.envoyer(p, d.get('destinataires') or defaut['destinataires'],
                                str(d.get('sujet') or defaut['sujet'])[:250],
                                str(d.get('corps') or defaut['corps']),
                                documents, auteur=str(request.user))
        except (PR.PropositionErreur, EnvoiErreur) as exc:
            return _erreur(exc)
        return Response({**_proposition_dict(p, complet=True), 'servis': servis,
                         'whatsapp': PR.whatsapp(p)})

    @action(detail=True, methods=['post'])
    def repondre(self, request, pk=None):
        """La réponse du client : ACCEPTEE (avec sa formule) ou REFUSEE."""
        p = self._get(pk)
        if not p:
            return _erreur('Introuvable.', 404)
        if p.statut not in ('VALIDEE', 'ENVOYEE', 'ACCEPTEE', 'REFUSEE'):
            return _erreur("Validez d'abord la proposition.")
        decision = str(request.data.get('decision') or '')
        if decision not in ('ACCEPTEE', 'REFUSEE'):
            return _erreur('Décision attendue : ACCEPTEE ou REFUSEE.')
        formule = str(request.data.get('formule') or '')
        if decision == 'ACCEPTEE' and formule not in PR.FORMULES_LIBELLES:
            return _erreur('Indiquez la formule choisie par le client.')
        p.statut = decision
        p.formule_choisie = formule if decision == 'ACCEPTEE' else ''
        migration = request.data.get('migration')
        p.migration_choisie = None if migration is None or decision == 'REFUSEE' else bool(migration)
        p.repondue_le = timezone.now()
        p.save(update_fields=['statut', 'formule_choisie', 'migration_choisie', 'repondue_le',
                              'updated_at'])
        if p.prospect_id:
            from .models import InteractionProspect
            resume = (f"Proposition {p.reference} acceptée — {PR.FORMULES_LIBELLES[formule]}"
                      + (', avec migration' if p.migration_choisie else '') + '.'
                      if decision == 'ACCEPTEE' else f"Proposition {p.reference} refusée.")
            InteractionProspect.objects.create(prospect_id=p.prospect_id, canal='AUTRE',
                                               auteur=str(request.user), resume=resume)
        return Response(_proposition_dict(p, complet=True))


class BibliothequeViewSet(viewsets.ViewSet):
    """Brochures, catalogue… : {titre, categorie, nom_fichier, contenu (data URI PDF)}."""
    permission_classes = [IsSuperAdmin]

    def list(self, request):
        qs = DocumentBibliotheque.objects.defer('contenu')
        if request.query_params.get('actifs'):
            qs = qs.filter(actif=True)
        return Response([_document_dict(d) for d in qs])

    def create(self, request):
        d = request.data
        decode = decoder_data_uri(d.get('contenu'))
        if not decode:
            return _erreur('Fichier illisible.')
        mime, octets = decode
        if mime != 'application/pdf':
            return _erreur('Seuls les fichiers PDF sont acceptés.')
        if len(octets) > TAILLE_MAX_DOCUMENT:
            return _erreur('Fichier trop lourd (10 Mo au plus).')
        nom = str(d.get('nom_fichier') or 'document.pdf').strip()[:200]
        categorie = d.get('categorie') if d.get('categorie') in dict(
            DocumentBibliotheque.CATEGORIE_CHOICES) else 'BROCHURE'
        doc = DocumentBibliotheque.objects.create(
            titre=str(d.get('titre') or nom.rsplit('.', 1)[0]).strip()[:200],
            categorie=categorie, description=str(d.get('description') or '').strip()[:300],
            nom_fichier=nom, mime_type=mime, taille=len(octets), contenu=d['contenu'],
            joindre_par_defaut=bool(d.get('joindre_par_defaut', True)),
            ordre=DocumentBibliotheque.objects.count(), ajoute_par=str(request.user))
        return Response(_document_dict(doc), status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        doc = DocumentBibliotheque.objects.filter(pk=pk).first()
        if not doc:
            return _erreur('Introuvable.', 404)
        d = request.data
        if 'titre' in d and str(d['titre']).strip():
            doc.titre = str(d['titre']).strip()[:200]
        if 'description' in d:
            doc.description = str(d['description'] or '').strip()[:300]
        if d.get('categorie') in dict(DocumentBibliotheque.CATEGORIE_CHOICES):
            doc.categorie = d['categorie']
        for champ in ('joindre_par_defaut', 'actif'):
            if champ in d:
                setattr(doc, champ, bool(d[champ]))
        if 'ordre' in d:
            try:
                doc.ordre = max(int(d['ordre']), 0)
            except (TypeError, ValueError):
                return _erreur('Ordre invalide.')
        doc.save()
        return Response(_document_dict(doc))

    def destroy(self, request, pk=None):
        doc = DocumentBibliotheque.objects.filter(pk=pk).first()
        if not doc:
            return _erreur('Introuvable.', 404)
        if doc.propositions.exclude(statut='BROUILLON').exists():
            # Déjà joint à une proposition envoyée : on le retire des listes
            # sans effacer la trace de ce qui a été remis au client.
            doc.actif = False
            doc.save(update_fields=['actif', 'updated_at'])
            return Response(_document_dict(doc))
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'])
    def fichier(self, request, pk=None):
        doc = DocumentBibliotheque.objects.filter(pk=pk).first()
        decode = decoder_data_uri(doc.contenu) if doc else None
        if not decode:
            return _erreur('Introuvable.', 404)
        reponse = HttpResponse(decode[1], content_type=decode[0])
        reponse['Content-Disposition'] = f'inline; filename="{doc.nom_fichier}"'
        return reponse
