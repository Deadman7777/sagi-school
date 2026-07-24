"""Reconstruit le « déjà payé » / reste dû par élève (Complexe Shoumoul, 2026).

Modèle Shoumoul : le renouvellement (55 000/an, en janvier) remplace l'inscription
pour les élèves déjà présents. Tous les élèves sont à jour de leurs mensualités
jan→juil (7 mois) ; il leur reste août→déc (5 mois) + le renouvellement pour ceux
qui ne l'ont pas versé.

Par élève :
  - déjà payé = 7 × mensualité + renouvellement versé
  - reste dû  = (nb_mensualites − 7) × mensualité + (55 000 − renouvellement versé)

Le produit 706 (13 410 500, agrégats Excel + récents) n'est PAS modifié : les
reprises par élève sont neutralisées en 890 (706 D / 890 C) pour ne pas doubler.

  python manage.py recaler_reste_du_shoumoul [--tenant_id UUID] [--exercice 2026]
      [--renouvellement 55000] [--mois-payes 7] [--appliquer]

Sans --appliquer : rapport par élève. Idempotent (remet à plat les reprises
existantes avant de reconstruire).
"""
import unicodedata
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum

from apps.tenants.models import Tenant
from apps.paiements.models import Exercice, Paiement
from apps.comptabilite.models import JournalEntry
from apps.paiements.reprise import creer_paiement_reprise


def _norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode()
    return ' '.join(s.lower().split())


# Renouvellement versé (55 000 = complet). Clés = noms normalisés.
RENOUV_VERSE = {
    _norm('Aïssata Kébé'): 55000,
    _norm('Maryam Mamadou BA'): 55000,
    _norm('Sokhna Mariama Bousso BADIANE'): 55000,
    _norm('Mouhamed Salih BADIANE'): 55000,
    _norm('El Hadji Mamadou Moustapha NGOM'): 55000,
    _norm('Papa Sélé Mbaye'): 55000,
    _norm('Fanta Mbaye'): 55000,
    _norm('Keba FALL'): 55000,
    _norm('Adjia Fatou TRAORE'): 55000,
    _norm('Fatou Kiné TRAORE'): 55000,
    _norm('Khady Mountapha DIOP'): 55000,
    _norm('Abdoulaye NDIAYE'): 27500,
    _norm('Mouhamed Abdallah NDIAYE'): 27500,
    _norm('Diariatoulah TALL'): 32500,
}


class Command(BaseCommand):
    help = "Reconstruit le déjà payé / reste dû par élève (modèle Shoumoul)."

    def add_arguments(self, parser):
        parser.add_argument('--tenant_id')
        parser.add_argument('--exercice')
        parser.add_argument('--renouvellement', type=Decimal, default=Decimal('55000'))
        parser.add_argument('--mois-payes', type=int, default=7)
        parser.add_argument('--appliquer', action='store_true')

    def handle(self, *args, **o):
        from apps.eleves.models import Eleve
        tenant = self._tenant(o.get('tenant_id'))
        ex = self._exercice(tenant, o.get('exercice'))
        renouv = o['renouvellement']
        mois_payes = o['mois_payes']
        mois_restants = max(ex.nb_mensualites - mois_payes, 0)

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n═══ Reconstruction reste dû par élève — {tenant.nom} — {ex.annee_scolaire} ═══"))
        self.stdout.write(f"  Renouvellement {renouv:,.0f} · {mois_payes} mois payés / "
                          f"{mois_restants} restants · {ex.nb_mensualites} mensualités\n")

        eleves = list(Eleve.objects.filter(tenant=tenant, exercice=ex).select_related('section'))
        matched = set()
        plan, total_paye, total_reste, alertes = [], Decimal('0'), Decimal('0'), []

        for e in eleves:
            if not e.section:
                alertes.append(f"{e.nom_complet} : sans section, ignoré")
                continue
            M = Decimal(str(e.frais_mensualite_effectif))
            verse = Decimal('0')
            key = _norm(e.nom_complet)
            if key in RENOUV_VERSE:
                verse = Decimal(str(RENOUV_VERSE[key]))
                matched.add(key)
            attendu = Decimal(str(e.total_attendu))
            # Reste voulu = 5 mois + renouvellement dû, borné au total attendu
            # (un élève ne peut pas devoir plus que son dû prorata).
            reste = min(mois_restants * M + (renouv - verse), attendu)
            paye = attendu - reste                      # ce que la reprise doit refléter
            plan.append((e, M, verse, paye, reste, attendu))
            total_paye += paye
            total_reste += reste
            # Contrôle : le modèle attend total_attendu = renouv + nb×M (+ 0 autre)
            attendu_modele = renouv + ex.nb_mensualites * M
            if abs(attendu - attendu_modele) > 1:
                alertes.append(f"{e.nom_complet} : total attendu {attendu:,.0f} ≠ modèle "
                               f"{attendu_modele:,.0f} (55k + {ex.nb_mensualites}×{M:,.0f})")

        # Noms de la liste non trouvés
        for key in RENOUV_VERSE:
            if key not in matched:
                alertes.append(f"Renouvellement : « {key} » non apparié à un élève")

        self.stdout.write("  Élève                                 mensualité   renouv   déjà payé     reste dû")
        for e, M, verse, paye, reste, attendu in plan[:80]:
            self.stdout.write(f"    {e.nom_complet[:34]:<34} {M:>10,.0f} {verse:>8,.0f} "
                              f"{paye:>11,.0f} {reste:>12,.0f}")
        if len(plan) > 80:
            self.stdout.write(f"    … (+{len(plan) - 80} élèves)")

        self.stdout.write(self.style.MIGRATE_LABEL(
            f"\n  {len(plan)} élèves · déjà payé total {total_paye:,.0f} · reste dû total {total_reste:,.0f}"))
        if alertes:
            self.stdout.write(self.style.WARNING("\n  ⚠ Points à vérifier :"))
            for a in alertes[:40]:
                self.stdout.write(self.style.WARNING(f"    - {a}"))

        if not o['appliquer']:
            self.stdout.write(self.style.MIGRATE_LABEL(
                "\n  DRY-RUN — aucune modification. Relancer avec --appliquer pour reconstruire."))
            return

        # ── Application ──
        with transaction.atomic():
            # 1. Remise à plat des reprises existantes (fiches + écritures) + neutralisation RECAL-REP
            anciennes = Paiement.objects.filter(tenant=tenant, exercice=ex, mode_paiement='REPRISE')
            ids = list(anciennes.values_list('id', flat=True))
            JournalEntry.objects.filter(tenant=tenant, exercice=ex, source='PAIEMENT',
                                        source_id__in=ids).delete()
            JournalEntry.objects.filter(tenant=tenant, exercice=ex, no_piece='RECAL-REP').delete()
            anciennes.delete()

            # 2. Recréation par élève (écritures standard 411/706/890)
            for e, M, verse, paye, reste, attendu in plan:
                if paye <= 0:
                    continue
                # Renouvellement d'abord (remplace l'inscription), le reste en mensualités.
                inscription = min(verse, paye)
                montants = {
                    'montant_inscription': float(inscription),
                    'montant_mensualite':  float(paye - inscription),
                    'montant_uniforme':    0,
                    'montant_fournitures': 0,
                }
                creer_paiement_reprise(tenant, ex, e, montants=montants)

            # 3. Neutraliser le 706 des nouvelles reprises (706 = agrégats Excel, pas de double)
            neuf_ids = list(Paiement.objects.filter(
                tenant=tenant, exercice=ex, mode_paiement='REPRISE').values_list('id', flat=True))
            r706 = Decimal(str(JournalEntry.objects.filter(
                tenant=tenant, exercice=ex, source='PAIEMENT', source_id__in=neuf_ids,
                no_compte='706', credit__gt=0).aggregate(c=Sum('credit'))['c'] or 0))
            if r706 > 0:
                JournalEntry.objects.bulk_create([
                    JournalEntry(tenant=tenant, exercice=ex, no_piece='RECAL-REP',
                                 date_ecriture=ex.date_debut, source='RECAL_MIGRATION',
                                 no_compte='706', debit=r706, credit=0, ordre=1,
                                 libelle="Neutralisation reprise reconstruite (706 = agrégats Excel)"),
                    JournalEntry(tenant=tenant, exercice=ex, no_piece='RECAL-REP',
                                 date_ecriture=ex.date_debut, source='RECAL_MIGRATION',
                                 no_compte='890', debit=0, credit=r706, ordre=2,
                                 libelle="Contrepartie neutralisation reprise reconstruite"),
                ])

        self.stdout.write(self.style.SUCCESS(
            f"\n  ✓ Reconstruit : {len(plan)} élèves. Reste dû total {total_reste:,.0f}. "
            f"706 inchangé (reprises neutralisées en 890)."))

    def _tenant(self, tid):
        if tid:
            try:
                return Tenant.objects.get(id=tid)
            except Tenant.DoesNotExist:
                raise CommandError(f'Tenant {tid} introuvable')
        ts = list(Tenant.objects.all()[:2])
        if len(ts) == 1:
            return ts[0]
        raise CommandError('Plusieurs tenants : préciser --tenant_id')

    def _exercice(self, tenant, annee):
        qs = Exercice.objects.filter(tenant=tenant)
        ex = qs.filter(annee_scolaire=annee).first() if annee else \
            qs.filter(cloture=False).order_by('-date_debut').first()
        if not ex:
            raise CommandError("Exercice introuvable : préciser --exercice")
        return ex
