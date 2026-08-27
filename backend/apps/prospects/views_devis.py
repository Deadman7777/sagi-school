"""L'API des devis — réservée à HADY GESMAN.

**Rien ne part sans un humain.** C'est l'arbitrage de la direction, et il est
appliqué ici par des transitions, pas par une consigne : un devis naît en
BROUILLON, ne devient VALIDE que si quelqu'un le valide, et ne peut être marqué
ENVOYÉ qu'à partir de VALIDE. Aucun chemin ne mène de BROUILLON à ENVOYÉ.

**Un devis validé ne se réécrit plus.** Il a été relu pour être envoyé :
autoriser sa modification ferait exister deux versions d'une même référence,
dont l'une est chez le client. Pour changer une proposition, on en établit une
autre — c'est ce que fait un commercial sur papier.
"""
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.permissions import IsSuperAdmin

from .devis import etablir, modules_inclus, rendre_pdf
from .models import Devis, InteractionProspect, Prospect

# Ce qu'un commercial peut retoucher tant que le devis est un brouillon. Les
# montants de la licence n'y sont pas : ils viennent du catalogue, et les
# rendre modifiables reviendrait à rouvrir la porte au tarif inventé. Pour
# changer l'offre, on change la licence ou la durée, et le serveur rechiffre.
CHAMPS_MODIFIABLES = {'frais_installation', 'montant_prestations',
                      'prestations', 'observations', 'etablissement', 'ville',
                      'contact_nom', 'contact_fonction', 'telephone', 'email'}
CHAMPS_MONTANT = {'frais_installation', 'montant_prestations'}


def _devis_dict(d, complet=False):
    base = {
        'id':            str(d.id),
        'numero':        d.numero,
        'prospect':      str(d.prospect_id) if d.prospect_id else None,
        'etablissement': d.etablissement,
        'type_licence':  d.type_licence,
        'cycle':         d.cycle,
        'mois':          d.mois,
        'montant_net':   int(d.montant_net),
        'montant_total': int(d.montant_total),
        'statut':        d.statut,
        'statut_libelle': d.get_statut_display(),
        'date_emission': d.date_emission,
        'date_validite': d.date_validite,
        'expire':        d.expire,
        'modifiable':    d.modifiable,
    }
    if not complet:
        return base
    base.update({
        'ville':            d.ville,
        'contact_nom':      d.contact_nom,
        'contact_fonction': d.contact_fonction,
        'telephone':        d.telephone,
        'email':            d.email,
        'prix_mensuel':     int(d.prix_mensuel),
        'montant_brut':     int(d.montant_brut),
        'taux_remise':      float(d.taux_remise),
        'montant_remise':   int(d.montant_remise),
        'frais_installation':  int(d.frais_installation),
        'prestations':         d.prestations,
        'montant_prestations': int(d.montant_prestations),
        'observations':     d.observations,
        'etabli_par':       d.etabli_par,
        'valide_par':       d.valide_par,
        'valide_le':        d.valide_le,
        'envoye_le':        d.envoye_le,
        # Ce que la licence ouvre RÉELLEMENT — lu dans le code, comme sur le
        # PDF. L'écran ne doit pas afficher autre chose que la pièce.
        'modules': [{'nom': nom, 'detail': detail}
                    for nom, detail in modules_inclus(d.type_licence)],
    })
    return base


def _entier(valeur):
    try:
        return max(int(float(valeur or 0)), 0)
    except (TypeError, ValueError):
        return 0


class DevisViewSet(viewsets.ViewSet):
    permission_classes = [IsSuperAdmin]

    def _tracer(self, devis, resume, auteur):
        """Chaque étape laisse une trace dans l'historique du prospect.

        C'est là que le commercial qui rappelle ira voir ce qui a été promis,
        quand, et par qui — pas dans une table de devis qu'il n'ouvre jamais.
        """
        if devis.prospect_id:
            InteractionProspect.objects.create(
                prospect=devis.prospect, canal='AUTRE', auteur=auteur,
                resume=resume)

    def list(self, request):
        qs = Devis.objects.select_related('prospect')
        if prospect := request.query_params.get('prospect'):
            qs = qs.filter(prospect_id=prospect)
        if statut := request.query_params.get('statut'):
            qs = qs.filter(statut=statut)
        return Response([_devis_dict(d) for d in qs[:300]])

    def retrieve(self, request, pk=None):
        devis = Devis.objects.filter(pk=pk).first()
        if not devis:
            return Response({'error': 'Devis introuvable.'}, status=404)
        return Response(_devis_dict(devis, complet=True))

    def create(self, request):
        """Établit un devis à partir d'une fiche prospect."""
        from apps.licences.catalogue import TARIFS_MENSUEL

        prospect = Prospect.objects.filter(
            pk=request.data.get('prospect')).first()
        if not prospect:
            return Response({'error': 'Prospect introuvable.'}, status=400)

        type_licence = str(request.data.get('type_licence') or '').upper()
        if type_licence not in TARIFS_MENSUEL:
            return Response({'error': "Cette licence n'est pas au catalogue."},
                            status=400)

        cycle = 'ANNUEL' if request.data.get('cycle') != 'MENSUEL' else 'MENSUEL'
        mois = _entier(request.data.get('mois')) or (12 if cycle == 'ANNUEL' else 1)
        if not 1 <= mois <= 60:
            return Response({'error': 'La durée doit tenir entre 1 et 60 mois.'},
                            status=400)

        devis = etablir(
            prospect, type_licence, cycle=cycle, mois=mois,
            auteur=str(request.user),
            frais_installation=_entier(request.data.get('frais_installation')),
            prestations=str(request.data.get('prestations') or '').strip()[:2000],
            montant_prestations=_entier(request.data.get('montant_prestations')),
            observations=str(request.data.get('observations') or '').strip()[:2000])
        return Response(_devis_dict(devis, complet=True),
                        status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        devis = Devis.objects.filter(pk=pk).first()
        if not devis:
            return Response({'error': 'Devis introuvable.'}, status=404)
        if not devis.modifiable:
            return Response(
                {'error': "Ce devis a été validé : il ne se modifie plus. "
                          "Établissez-en un nouveau."}, status=409)

        modifies = []
        for cle, valeur in request.data.items():
            if cle not in CHAMPS_MODIFIABLES:
                continue
            if cle in CHAMPS_MONTANT:
                setattr(devis, cle, _entier(valeur))
            else:
                setattr(devis, cle, str(valeur or '').strip()[:2000])
            modifies.append(cle)
        if modifies:
            devis.save(update_fields=modifies + ['updated_at'])
        return Response(_devis_dict(devis, complet=True))

    def destroy(self, request, pk=None):
        devis = Devis.objects.filter(pk=pk).first()
        if not devis:
            return Response({'error': 'Devis introuvable.'}, status=404)
        if devis.statut != 'BROUILLON':
            return Response(
                {'error': "Un devis validé ou envoyé ne se supprime pas : "
                          "c'est une pièce commerciale."}, status=409)
        devis.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def valider(self, request, pk=None):
        """Le passage obligé : quelqu'un relit et engage l'entreprise."""
        devis = Devis.objects.filter(pk=pk).first()
        if not devis:
            return Response({'error': 'Devis introuvable.'}, status=404)
        if devis.statut != 'BROUILLON':
            return Response({'error': 'Seul un brouillon se valide.'}, status=409)

        devis.statut = 'VALIDE'
        devis.valide_par = str(request.user)
        devis.valide_le = timezone.now()
        devis.save(update_fields=['statut', 'valide_par', 'valide_le', 'updated_at'])
        self._tracer(devis, f"Devis {devis.numero} validé, prêt à être envoyé.",
                     str(request.user))
        return Response(_devis_dict(devis, complet=True))

    @action(detail=True, methods=['post'])
    def envoyer(self, request, pk=None):
        """Marque le devis comme remis au prospect.

        Aucun courriel n'est expédié d'ici : le commercial l'envoie lui-même,
        avec son mot d'accompagnement. Automatiser cet envoi supprimerait le
        seul moment où quelqu'un regarde la pièce avant qu'elle ne parte.
        """
        devis = Devis.objects.filter(pk=pk).first()
        if not devis:
            return Response({'error': 'Devis introuvable.'}, status=404)
        if devis.statut != 'VALIDE':
            return Response(
                {'error': "Un devis doit être validé avant d'être envoyé."},
                status=409)
        if devis.expire:
            return Response(
                {'error': "Ce devis a dépassé sa validité de trente jours. "
                          "Établissez-en un nouveau."}, status=409)

        devis.statut = 'ENVOYE'
        devis.envoye_le = timezone.now()
        devis.save(update_fields=['statut', 'envoye_le', 'updated_at'])
        self._tracer(devis, f"Devis {devis.numero} envoyé au prospect.",
                     str(request.user))
        return Response(_devis_dict(devis, complet=True))

    @action(detail=True, methods=['post'])
    def trancher(self, request, pk=None):
        """Le prospect a répondu : {"reponse": "ACCEPTE"|"REFUSE", "motif": ""}.

        Le statut du prospect n'est pas touché : un devis accepté n'est pas
        encore un client — l'école existe le jour où sa licence est créée, et
        c'est ce geste-là qui fait passer la fiche à « Gagné ».
        """
        devis = Devis.objects.filter(pk=pk).first()
        if not devis:
            return Response({'error': 'Devis introuvable.'}, status=404)
        if devis.statut != 'ENVOYE':
            return Response(
                {'error': "Seul un devis envoyé peut être accepté ou refusé."},
                status=409)

        reponse = str(request.data.get('reponse') or '').upper()
        if reponse not in ('ACCEPTE', 'REFUSE'):
            return Response({'error': 'Réponse attendue : ACCEPTE ou REFUSE.'},
                            status=400)

        devis.statut = reponse
        devis.save(update_fields=['statut', 'updated_at'])

        motif = str(request.data.get('motif') or '').strip()[:500]
        verbe = 'accepté' if reponse == 'ACCEPTE' else 'refusé'
        self._tracer(devis, f"Devis {devis.numero} {verbe} par le prospect."
                            + (f"\n{motif}" if motif else ''), str(request.user))
        return Response(_devis_dict(devis, complet=True))

    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        devis = Devis.objects.filter(pk=pk).first()
        if not devis:
            return HttpResponse('Devis introuvable', status=404)
        octets, erreur = rendre_pdf(devis)
        if erreur:
            return HttpResponse(erreur, status=500)
        reponse = HttpResponse(octets, content_type='application/pdf')
        # Le nom du fichier porte l'état : un brouillon enregistré sur un poste
        # ne doit pas se retrouver en pièce jointe par simple glisser-déposer.
        marque = '-BROUILLON' if devis.statut == 'BROUILLON' else ''
        reponse['Content-Disposition'] = (
            f'inline; filename="{devis.numero}{marque}.pdf"')
        return reponse
