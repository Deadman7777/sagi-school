from rest_framework.views import APIView
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count
from apps.eleves.models import Eleve
from core.permissions import IsTenantMember
from .models import Paiement, Exercice
from .serializers import PaiementSerializer, ExerciceSerializer


class ExerciceViewSet(viewsets.ModelViewSet):
    serializer_class   = ExerciceSerializer
    permission_classes = [IsTenantMember]

    def get_queryset(self):
        tenant = self.request.tenant
        if not tenant and self.request.user.role == 'SUPER_ADMIN':
            from apps.tenants.models import Tenant
            tenant = Tenant.objects.first()
        return Exercice.objects.filter(tenant=tenant)

    def perform_create(self, serializer):
        tenant = self.request.tenant
        if not tenant and self.request.user.role == 'SUPER_ADMIN':
            from apps.tenants.models import Tenant
            tenant = Tenant.objects.first()
        serializer.save(tenant=tenant)


class PaiementViewSet(viewsets.ModelViewSet):
    serializer_class   = PaiementSerializer
    permission_classes = [IsAuthenticated]

    def get_tenant(self):
        if self.request.tenant:
            return self.request.tenant
        if self.request.user.role == 'SUPER_ADMIN':
            from apps.tenants.models import Tenant
            return Tenant.objects.first()
        return None

    def get_queryset(self):
        tenant = self.get_tenant()
        if not tenant:
            return Paiement.objects.none()
        qs = Paiement.objects.filter(tenant=tenant).select_related('eleve', 'exercice')
        if eleve_id := self.request.query_params.get('eleve'):
            qs = qs.filter(eleve_id=eleve_id)
        if mode := self.request.query_params.get('mode'):
            qs = qs.filter(mode_paiement=mode)
        return qs

    def perform_create(self, serializer):
        tenant = self.get_tenant()
        
        # Exercice actif
        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()
        if not exercice:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Aucun exercice actif trouvé.")
        
        # Générer no_piece automatique
        from django.db.models import Max
        import re
        last = Paiement.objects.filter(tenant=tenant).aggregate(Max('no_piece'))['no_piece__max']
        if last:
            nums = re.findall(r'\d+', last)
            next_num = int(nums[-1]) + 1 if nums else 1
        else:
            next_num = 1
        no_piece = f"REC-{next_num:04d}"

        paiement = serializer.save(
            tenant=tenant,
            exercice=exercice,
            no_piece=no_piece,
            saisi_par=self.request.user
        )

        # Double écriture SYSCOHADA
        from apps.comptabilite.models import JournalEntry
        montant = float(paiement.total)
        eleve_nom = paiement.eleve.nom_complet

        compte_reglement, libelle_compte = {
            'ESPECE':       ('571', 'Caisse'),
            'WAVE':         ('5521', 'WAVE'),
            'ORANGE_MONEY': ('5522', 'Orange Money'),
            'FREE_MONEY':   ('5523', 'Free Money'),
            'VIREMENT':     ('521', 'Banque'),
            'CHEQUE':       ('521', 'Banque'),
        }.get(paiement.mode_paiement, ('571', 'Caisse'))

        libelle = f"{eleve_nom} - {no_piece}"
        date = paiement.date_paiement

        # Écriture 1 — Constatation créance : Débit 411 / Crédit 706
        # Écriture 2 — Règlement           : Débit 5xx / Crédit 411
        ecritures = [
            dict(ordre=1, no_compte='411',           debit=montant, credit=0,
                 libelle=f"Créance scolarité — {libelle}"),
            dict(ordre=2, no_compte='706',           debit=0,       credit=montant,
                 libelle=f"Créance scolarité — {libelle}"),
            dict(ordre=3, no_compte=compte_reglement, debit=montant, credit=0,
                 libelle=f"Règlement {libelle_compte} — {libelle}"),
            dict(ordre=4, no_compte='411',           debit=0,       credit=montant,
                 libelle=f"Règlement {libelle_compte} — {libelle}"),
        ]

        for e in ecritures:
            JournalEntry.objects.create(
                tenant=tenant,
                exercice=exercice,
                no_piece=no_piece,
                date_ecriture=date,
                source='PAIEMENT',
                source_id=paiement.id,
                **e
            )

        from core.models import log_audit
        log_audit(self.request, 'CREATE', 'Paiement', str(paiement.id),
                  f"{eleve_nom} — {no_piece} — {montant:,.0f} FCFA ({paiement.mode_paiement})")

    @action(detail=False, methods=['get'])
    def stats(self, request):
        tenant   = self.get_tenant()
        exercice = Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()
        if not exercice:
            return Response({'total': 0, 'nb_transactions': 0, 'par_mode': []})

        paiements = Paiement.objects.filter(tenant=tenant, exercice=exercice)

        def total(qs):
            a = qs.aggregate(
                t=Sum('montant_inscription') + Sum('montant_mensualite') +
                  Sum('montant_uniforme')    + Sum('montant_fournitures') +
                  Sum('montant_cantine')     + Sum('montant_divers')
            )
            return float(a['t'] or 0)

        par_mode = []
        for m in paiements.values('mode_paiement').annotate(nb=Count('id')):
            par_mode.append({
                'mode':  m['mode_paiement'],
                'nb':    m['nb'],
                'total': total(paiements.filter(mode_paiement=m['mode_paiement']))
            })

        return Response({
            'total':           total(paiements),
            'nb_transactions': paiements.count(),
            'par_mode':        sorted(par_mode, key=lambda x: x['total'], reverse=True),
        })

    def _build_recu_context(self, p):
        """Construit le contexte complet du reçu (JSON + PDF)."""
        from django.db.models import Sum as _Sum
        from django.utils import timezone as _tz

        MODE_LABELS = {
            'ESPECE': 'Espèces (caisse)', 'WAVE': 'Wave',
            'ORANGE_MONEY': 'Orange Money', 'FREE_MONEY': 'Free Money',
            'VIREMENT': 'Virement bancaire', 'CHEQUE': 'Chèque',
        }

        # Cumul des paiements AVANT ce reçu
        paiements_avant = Paiement.objects.filter(
            tenant=p.tenant, eleve=p.eleve, exercice=p.exercice,
            date_paiement__lt=p.date_paiement,
        ).exclude(id=p.id)
        # Inclure les paiements du même jour avec un no_piece inférieur
        meme_jour = Paiement.objects.filter(
            tenant=p.tenant, eleve=p.eleve, exercice=p.exercice,
            date_paiement=p.date_paiement,
        ).exclude(id=p.id).filter(no_piece__lt=p.no_piece)

        def _sum_qs(qs):
            a = qs.aggregate(
                t=_Sum('montant_inscription') + _Sum('montant_mensualite') +
                  _Sum('montant_uniforme')    + _Sum('montant_fournitures') +
                  _Sum('montant_cantine')     + _Sum('montant_divers')
            )
            return float(a['t'] or 0)

        deja_paye_avant = _sum_qs(paiements_avant) + _sum_qs(meme_jour)
        total_attendu   = float(p.eleve.total_attendu)
        total_paiement  = float(p.total)
        reste_apres     = max(total_attendu - deja_paye_avant - total_paiement, 0)

        # Lignes détail (uniquement les montants > 0)
        lignes = []
        if p.montant_inscription: lignes.append(('Frais d\'inscription',  float(p.montant_inscription)))
        if p.montant_mensualite:  lignes.append(('Mensualité scolaire',   float(p.montant_mensualite)))
        if p.montant_uniforme:    lignes.append(('Uniforme scolaire',     float(p.montant_uniforme)))
        if p.montant_fournitures: lignes.append(('Fournitures scolaires', float(p.montant_fournitures)))
        if p.montant_cantine:     lignes.append(('Cantine / Restauration',float(p.montant_cantine)))
        if p.montant_divers:      lignes.append(('Frais divers',          float(p.montant_divers)))

        # Numéro séquentiel du reçu pour cet élève
        nb_recu_eleve = Paiement.objects.filter(
            tenant=p.tenant, eleve=p.eleve, exercice=p.exercice
        ).filter(date_paiement__lte=p.date_paiement).count()

        return {
            'paiement_id':       str(p.id),
            'no_piece':          p.no_piece,
            'date':              str(p.date_paiement),
            'heure_edition':     _tz.now().strftime('%H:%M'),
            'date_edition':      _tz.now().strftime('%d/%m/%Y à %H:%M'),
            # Élève
            'eleve':             p.eleve.nom_complet,
            'matricule':         p.eleve.matricule or '—',
            'section':           p.eleve.section.nom if p.eleve.section else '—',
            'genre':             p.eleve.genre,
            'date_naissance':    str(p.eleve.date_naissance) if p.eleve.date_naissance else '—',
            'lieu_naissance':    p.eleve.lieu_naissance or '—',
            # Parents
            'nom_pere':          p.eleve.nom_pere or '—',
            'telephone_pere':    p.eleve.telephone_pere or '—',
            'nom_mere':          p.eleve.nom_mere or '—',
            'telephone_mere':    p.eleve.telephone_mere or '—',
            # Exercice
            'annee_scolaire':    p.exercice.annee_scolaire,
            # Montants
            'lignes':            lignes,
            'inscription':       float(p.montant_inscription),
            'mensualite':        float(p.montant_mensualite),
            'uniforme':          float(p.montant_uniforme),
            'fournitures':       float(p.montant_fournitures),
            'cantine':           float(p.montant_cantine),
            'divers':            float(p.montant_divers),
            'total':             total_paiement,
            # Suivi financier
            'total_attendu':     round(total_attendu, 2),
            'deja_paye_avant':   round(deja_paye_avant, 2),
            'total_paye_apres':  round(deja_paye_avant + total_paiement, 2),
            'reste_apres':       round(reste_apres, 2),
            'nb_recu_eleve':     nb_recu_eleve,
            # Paiement
            'mode_paiement':     p.mode_paiement,
            'mode_label':        MODE_LABELS.get(p.mode_paiement, p.mode_paiement),
            'observations':      p.observations or '',
            'saisi_par':         p.saisi_par.nom if p.saisi_par else '—',
            # Établissement
            'tenant_nom':        p.tenant.nom   if p.tenant else 'SAGI SCHOOL',
            'tenant_ville':      p.tenant.ville if p.tenant else '',
            'tenant_rccm':       getattr(p.tenant, 'rccm', '') or '',
            'tenant_telephone':  getattr(p.tenant, 'telephone', '') or '',
        }

    @action(detail=True, methods=['get'])
    def recu(self, request, pk=None):
        """Données JSON du reçu."""
        p = self.get_object()
        return Response(self._build_recu_context(p))

    @action(detail=True, methods=['get'], url_path='recu-pdf')
    def recu_pdf(self, request, pk=None):
        """Génère le PDF professionnel du reçu de paiement."""
        from io import BytesIO
        from django.http import HttpResponse
        from django.template.loader import render_to_string
        try:
            from xhtml2pdf import pisa
        except ImportError:
            return HttpResponse('xhtml2pdf non installé', status=500)

        p       = self.get_object()
        context = self._build_recu_context(p)
        context['p'] = p  # accès direct à l'objet pour le template

        html_str = render_to_string('pdf/recu_paiement.html', context)
        buf      = BytesIO()
        result   = pisa.CreatePDF(html_str, dest=buf, encoding='utf-8')
        if result.err:
            return HttpResponse('Erreur génération PDF reçu.', status=500)

        response = HttpResponse(buf.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="recu_{p.no_piece}.pdf"'
        return response


class CloturerExerciceView(APIView):
    permission_classes = [IsAuthenticated]

    def get_tenant(self):
        if self.request.tenant:
            return self.request.tenant
        if hasattr(self.request.user, 'tenant') and self.request.user.tenant:
            return self.request.user.tenant
        return None

    def get(self, request):
        """Vérifie si l'exercice peut être clôturé."""
        from .cloturer import verifier_avant_cloture
        tenant   = self.get_tenant()
        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()

        if not exercice:
            return Response({'error': 'Aucun exercice actif'}, status=404)

        verification = verifier_avant_cloture(exercice)
        verification['exercice'] = {
            'id':             str(exercice.id),
            'annee_scolaire': exercice.annee_scolaire,
            'date_debut':     str(exercice.date_debut),
            'date_fin':       str(exercice.date_fin),
        }
        return Response(verification)

    def post(self, request):
        """Clôture l'exercice."""
        from .cloturer import verifier_avant_cloture, cloturer_exercice
        from core.permissions import IsAdminEcole

        tenant   = self.get_tenant()
        exercice = Exercice.objects.filter(
            tenant=tenant, cloture=False
        ).order_by('-date_debut').first()

        if not exercice:
            return Response({'error': 'Aucun exercice actif'}, status=404)

        # Vérification finale
        verif = verifier_avant_cloture(exercice)
        if not verif['peut_cloturer']:
            return Response({
                'error':     'Clôture impossible',
                'problemes': verif['problemes']
            }, status=400)

        # Confirmation requise
        if not request.data.get('confirme'):
            return Response({
                'error': 'Confirmation requise',
                'message': 'Envoyez {"confirme": true} pour confirmer la clôture'
            }, status=400)

        creer_suivant = request.data.get('creer_suivant', True)
        result        = cloturer_exercice(exercice, creer_suivant)

        return Response({
            'success': True,
            'message': f"Exercice {result['exercice_cloture']} clôturé ✅",
            **result
        })
