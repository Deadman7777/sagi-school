"""L'API du fichier prospects — réservée à HADY GESMAN.

Convention de l'application : APIView / ViewSet et sérialisation manuelle. Ici
elle rend un service supplémentaire — un formulaire public alimente ces
enregistrements, et un sérialiseur DRF exposerait mécaniquement des champs qui
n'ont pas à être modifiables depuis l'extérieur (`donnees_brutes`, `source`,
`courriel_envoye`). La liste blanche ci-dessous est explicite.
"""
from datetime import date, timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.permissions import IsSuperAdmin

from .enregistrement import _nombre, enregistrer_demande, normaliser_telephone
from .models import ORIGINES, TYPES_ORGANISATION, InteractionProspect, Prospect

# Ce qu'un commercial peut modifier après coup. `donnees_brutes` n'y est pas :
# c'est la trace de ce qui a été reçu, elle ne se réécrit pas.
CHAMPS_MODIFIABLES = {
    'etablissement', 'type_organisation', 'date_creation', 'adresse', 'ville',
    'telephone', 'email', 'site_web', 'contact_nom', 'contact_fonction',
    'contact_telephone', 'contact_email', 'pouvoir_decisionnel',
    'origine_details', 'disponibilites', 'message',
    'statut', 'relance_le', 'notes', 'perdu_motif',
}
CHAMPS_NOMBRE = {'nb_eleves', 'nb_employes', 'nb_classes', 'nb_sites'}


def _interaction_dict(i):
    return {
        'id':     str(i.id),
        'date':   i.date,
        'canal':  i.canal,
        'canal_libelle': i.get_canal_display(),
        'resume': i.resume,
        'auteur': i.auteur,
    }


def _prospect_dict(p, complet=False):
    base = {
        'id':            str(p.id),
        'etablissement': p.etablissement,
        'type_organisation': p.type_organisation,
        'ville':         p.ville,
        'telephone':     p.telephone,
        'email':         p.email,
        'contact_nom':   p.contact_nom,
        'contact_fonction': p.contact_fonction,
        'contact_telephone': p.contact_telephone,
        'nb_eleves':     p.nb_eleves,
        'statut':        p.statut,
        'statut_libelle': p.get_statut_display(),
        'source':        p.source,
        'relance_le':    p.relance_le,
        'relance_en_retard': p.relance_en_retard,
        'anciennete_jours': p.anciennete_jours,
        'nb_interactions': getattr(p, 'nb_interactions', None),
        'cree_le':       p.created_at,
    }
    if not complet:
        return base
    base.update({
        'date_creation':  p.date_creation,
        'adresse':        p.adresse,
        'site_web':       p.site_web,
        'contact_email':  p.contact_email,
        'pouvoir_decisionnel': p.pouvoir_decisionnel,
        'origines':       p.origines,
        'origine_details': p.origine_details,
        'nb_employes':    p.nb_employes,
        'nb_classes':     p.nb_classes,
        'nb_sites':       p.nb_sites,
        'disponibilites': p.disponibilites,
        'message':        p.message,
        'notes':          p.notes,
        'perdu_motif':    p.perdu_motif,
        'courriel_envoye': p.courriel_envoye,
        'donnees_brutes': p.donnees_brutes,
        'tenant_converti': str(p.tenant_converti_id) if p.tenant_converti_id else None,
        'tenant_converti_nom': p.tenant_converti.nom if p.tenant_converti_id else '',
        'date_conversion': p.date_conversion,
        'interactions':   [_interaction_dict(i) for i in p.interactions.all()],
    })
    return base


class ProspectViewSet(viewsets.ViewSet):
    permission_classes = [IsSuperAdmin]

    def list(self, request):
        """Filtres : `statut`, `source`, `q` (recherche libre), `a_relancer`."""
        qs = Prospect.objects.annotate(nb_interactions=Count('interactions'))

        if statut := request.query_params.get('statut'):
            if statut == 'EN_COURS':
                qs = qs.exclude(statut__in=('GAGNE', 'PERDU'))
            else:
                qs = qs.filter(statut=statut)
        if source := request.query_params.get('source'):
            qs = qs.filter(source=source)
        if request.query_params.get('a_relancer') in ('1', 'true', 'True'):
            qs = qs.filter(relance_le__lte=date.today()).exclude(
                statut__in=('GAGNE', 'PERDU'))
        if q := (request.query_params.get('q') or '').strip():
            recherche = (Q(etablissement__icontains=q) | Q(ville__icontains=q)
                         | Q(contact_nom__icontains=q) | Q(email__icontains=q)
                         | Q(contact_email__icontains=q))
            # Le téléphone se cherche sous sa forme normalisée : personne ne
            # retape les espaces et l'indicatif à l'identique. La condition
            # n'est ajoutée que si la recherche contient des chiffres — un
            # `contains=''` ramènerait toute la table.
            if cle_tel := normaliser_telephone(q):
                recherche |= Q(telephone_cle__contains=cle_tel)
            qs = qs.filter(recherche)

        return Response([_prospect_dict(p) for p in qs[:500]])

    def retrieve(self, request, pk=None):
        prospect = Prospect.objects.filter(pk=pk).prefetch_related(
            'interactions').select_related('tenant_converti').first()
        if not prospect:
            return Response({'error': 'Prospect introuvable.'}, status=404)
        return Response(_prospect_dict(prospect, complet=True))

    def create(self, request):
        """Saisie manuelle — un prospect rencontré en clientèle, au téléphone.

        Passe par le même chemin que le formulaire public : le rapprochement
        des doublons s'applique donc aussi à la saisie manuelle, ce qui est
        précisément le cas où l'on crée sans le savoir une seconde fiche.
        """
        try:
            prospect, cree = enregistrer_demande(
                request.data, source='MANUEL', canal='AUTRE',
                resume=str(request.data.get('resume') or '').strip()
                       or 'Fiche créée manuellement.',
                auteur=str(request.user))
        except ValueError as e:
            return Response({'error': str(e)}, status=400)
        return Response({**_prospect_dict(prospect, complet=True), 'cree': cree},
                        status=status.HTTP_201_CREATED if cree else status.HTTP_200_OK)

    def partial_update(self, request, pk=None):
        prospect = Prospect.objects.filter(pk=pk).first()
        if not prospect:
            return Response({'error': 'Prospect introuvable.'}, status=404)

        modifies = []
        for cle, valeur in request.data.items():
            if cle in CHAMPS_NOMBRE:
                setattr(prospect, cle, _nombre(valeur))
                modifies.append(cle)
            elif cle in CHAMPS_MODIFIABLES:
                if cle == 'relance_le':
                    setattr(prospect, cle, valeur or None)
                else:
                    setattr(prospect, cle, str(valeur or '').strip())
                modifies.append(cle)

        if 'telephone' in modifies:
            prospect.telephone_cle = normaliser_telephone(prospect.telephone)
            modifies.append('telephone_cle')

        # Une affaire gagnée ou perdue n'a plus de relance en attente : la
        # laisser afficherait indéfiniment un rappel sur un dossier clos.
        if prospect.statut in ('GAGNE', 'PERDU') and prospect.relance_le:
            prospect.relance_le = None
            modifies.append('relance_le')
        if prospect.statut == 'GAGNE' and not prospect.date_conversion:
            prospect.date_conversion = date.today()
            modifies.append('date_conversion')

        if modifies:
            prospect.save(update_fields=list(set(modifies)) + ['updated_at'])
        prospect.refresh_from_db()
        return Response(_prospect_dict(prospect, complet=True))

    def destroy(self, request, pk=None):
        prospect = Prospect.objects.filter(pk=pk).first()
        if not prospect:
            return Response({'error': 'Prospect introuvable.'}, status=404)
        prospect.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def interaction(self, request, pk=None):
        """Consigne un échange, et décale la relance si on en fixe une."""
        prospect = Prospect.objects.filter(pk=pk).first()
        if not prospect:
            return Response({'error': 'Prospect introuvable.'}, status=404)

        resume = str(request.data.get('resume') or '').strip()
        if not resume:
            return Response({'error': "Le résumé de l'échange est obligatoire."},
                            status=400)

        InteractionProspect.objects.create(
            prospect=prospect,
            canal=str(request.data.get('canal') or 'APPEL')[:20],
            date=request.data.get('date') or date.today(),
            resume=resume[:5000], auteur=str(request.user))

        modifies = []
        if 'relance_le' in request.data:
            prospect.relance_le = request.data['relance_le'] or None
            modifies.append('relance_le')
        # Un échange consigné sur un prospect jamais rappelé le fait sortir de
        # « Nouveau » : la pile des demandes non traitées reste juste.
        if prospect.statut == 'NOUVEAU':
            prospect.statut = 'CONTACTE'
            modifies.append('statut')
        if modifies:
            prospect.save(update_fields=modifies + ['updated_at'])

        prospect.refresh_from_db()
        return Response(_prospect_dict(prospect, complet=True))

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Ce qu'un responsable commercial regarde en ouvrant l'écran."""
        aujourdhui, maintenant = date.today(), timezone.now()
        par_statut = dict(Prospect.objects.values_list('statut').annotate(
            n=Count('id')).values_list('statut', 'n'))

        ouverts = Prospect.objects.exclude(statut__in=('GAGNE', 'PERDU'))
        gagnes = par_statut.get('GAGNE', 0)
        clos = gagnes + par_statut.get('PERDU', 0)

        return Response({
            'total':        sum(par_statut.values()),
            'par_statut':   [{'statut': s, 'libelle': libelle,
                              'nombre': par_statut.get(s, 0)}
                             for s, libelle in Prospect.STATUT_CHOICES],
            'nouveaux':     par_statut.get('NOUVEAU', 0),
            'en_cours':     ouverts.count(),
            'gagnes':       gagnes,
            # Le chiffre qui dira si le site vitrine rapporte : sur les
            # affaires tranchées, combien sont devenues des écoles clientes.
            'taux_conversion': round(gagnes / clos * 100, 1) if clos else 0.0,
            'a_relancer':   ouverts.filter(relance_le__lte=aujourdhui).count(),
            'en_retard':    ouverts.filter(relance_le__lt=aujourdhui).count(),
            # `created_at` est un DateTimeField : le comparer à une date nue
            # laisserait Django l'interpréter comme naïve, et le décompte
            # dériverait du décalage horaire sur toute installation hors UTC.
            'recus_30j':    Prospect.objects.filter(
                                created_at__gte=maintenant - timedelta(days=30)).count(),
            # Une demande reçue et jamais rappelée est le seul vrai échec de ce
            # fichier : c'est la situation qu'il existe pour rendre impossible.
            'jamais_contactes': ouverts.filter(
                                statut='NOUVEAU',
                                created_at__lt=maintenant - timedelta(days=2)).count(),
        })

    @action(detail=False, methods=['get'], url_path='referentiels')
    def referentiels(self, request):
        """Les listes proposées à la saisie, servies par le serveur pour que
        le site vitrine et l'écran de suivi ne divergent jamais."""
        return Response({
            'types_organisation': list(TYPES_ORGANISATION),
            'origines':           list(ORIGINES),
            'statuts':  [{'code': c, 'libelle': l} for c, l in Prospect.STATUT_CHOICES],
            'sources':  [{'code': c, 'libelle': l} for c, l in Prospect.SOURCE_CHOICES],
            'canaux':   [{'code': c, 'libelle': l}
                         for c, l in InteractionProspect.CANAL_CHOICES],
        })
