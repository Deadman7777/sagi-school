"""Retenue pour absences et retards, expliquée par une note sur le bulletin.

Le salaire convenu reste celui de la fiche employé ; un mois donné, des jours
d'absence ou des retards le diminuent. L'app propose le montant (1/30 par jour,
1/173,33 par heure), l'établissement peut le corriger, et une note — imprimée
sur le bulletin — dit à l'employé pourquoi son salaire a baissé.

La retenue diminue le BRUT : les cotisations se calculent sur ce qui est
réellement payé, et la charge 661 ne porte que le travail fait.
"""
import datetime
from decimal import Decimal

from django.template.loader import render_to_string
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.rh.models import BulletinPaie, Employe, ParametresFiscaux
from apps.rh.services import PaieCalculateur
from apps.tenants.models import Tenant
from apps.users.models import User


def _employe(tenant, salaire='150000'):
    return Employe.objects.create(
        tenant=tenant, nom_complet='Awa NDIAYE', type_employe='ENSEIGNANT',
        poste='Institutrice', salaire_base=Decimal(salaire),
        date_embauche=datetime.date(2025, 10, 1))


class RetenueAbsenceCalculTest(TestCase):
    def setUp(self):
        ParametresFiscaux.objects.create(annee=2026, tranches_ir=[])
        self.simplifie = _employe(Tenant.objects.create(nom='Daara', regime_paie='SIMPLIFIE'))
        self.complet = _employe(Tenant.objects.create(nom='École', regime_paie='COMPLET'))

    def _calc(self, employe, **kw):
        return PaieCalculateur.calculer_bulletin(employe, 3, 2026, **kw)

    def test_sans_absence_rien_ne_change(self):
        b = self._calc(self.simplifie)
        self.assertEqual(b['retenue_absence'], Decimal('0'))
        self.assertEqual(b['salaire_brut'], Decimal('150000'))

    def test_montant_propose_jours_et_heures(self):
        """2 jours = 150 000 × 2/30 = 10 000 ; 3 h = 150 000 × 3/173,33 ≈ 2 596."""
        b = self._calc(self.simplifie, nb_jours_absence=2, nb_heures_retard=3)
        self.assertEqual(b['retenue_absence'], Decimal('12596'))
        self.assertEqual(b['_retenue_absence_proposee'], Decimal('12596'))
        self.assertEqual(b['net_a_payer'], Decimal('137404'))

    def test_l_etablissement_corrige_le_montant(self):
        b = self._calc(self.simplifie, nb_jours_absence=2, retenue_absence=8000)
        self.assertEqual(b['retenue_absence'], Decimal('8000'))
        self.assertEqual(b['_retenue_absence_proposee'], Decimal('10000'))
        self.assertEqual(b['salaire_brut'], Decimal('142000'))

    def test_montant_saisi_sans_jours_ni_heures(self):
        b = self._calc(self.simplifie, retenue_absence=5000)
        self.assertEqual(b['salaire_brut'], Decimal('145000'))

    def test_retenue_bornee_au_salaire_de_base(self):
        b = self._calc(self.simplifie, nb_jours_absence=31)
        self.assertEqual(b['retenue_absence'], Decimal('150000'))
        self.assertEqual(b['net_a_payer'], Decimal('0'))

    def test_les_cotisations_portent_sur_le_brut_diminue(self):
        """IPRES calculé sur 140 000 et non sur 150 000."""
        entier = self._calc(self.complet)
        diminue = self._calc(self.complet, nb_jours_absence=2)
        self.assertEqual(diminue['salaire_brut'], Decimal('140000'))
        self.assertLess(diminue['ipres_general_salarie'], entier['ipres_general_salarie'])
        params = ParametresFiscaux.objects.get(annee=2026)
        attendu = (Decimal('140000') * params.taux_ipres_general_salarie / 100).quantize(Decimal('1'))
        self.assertEqual(diminue['ipres_general_salarie'], attendu)

    def test_note_obligatoire_a_la_creation(self):
        with self.assertRaisesMessage(ValueError, 'note est obligatoire'):
            PaieCalculateur.creer_bulletin(self.simplifie, 3, 2026, nb_jours_absence=1)
        self.assertFalse(BulletinPaie.objects.exists())

    def test_note_enregistree_avec_le_bulletin(self):
        b = PaieCalculateur.creer_bulletin(
            self.simplifie, 3, 2026, nb_jours_absence=2, nb_heures_retard=3,
            note_remuneration='  Absente les 12 et 13 mars ; 3 retards.  ')
        b.refresh_from_db()
        self.assertEqual(b.retenue_absence, Decimal('12596'))
        self.assertEqual(b.nb_jours_absence, Decimal('2'))
        self.assertEqual(b.note_remuneration, 'Absente les 12 et 13 mars ; 3 retards.')

    def test_une_note_seule_est_acceptee(self):
        """Expliquer une variation sans retenue (ex. prime exceptionnelle)."""
        b = PaieCalculateur.creer_bulletin(self.simplifie, 3, 2026,
                                           note_remuneration='Prime de fin de trimestre.')
        self.assertEqual(b.retenue_absence, Decimal('0'))
        self.assertEqual(b.note_remuneration, 'Prime de fin de trimestre.')

    def test_ecritures_equilibrees_et_charge_diminuee(self):
        from apps.comptabilite.models import JournalEntry
        from apps.paiements.models import Exercice
        from apps.rh.services import generer_ecritures_paie
        from django.db.models import Sum
        tenant = self.complet.tenant
        Exercice.objects.create(tenant=tenant, annee_scolaire='2025-2026',
                                date_debut=datetime.date(2025, 10, 1),
                                date_fin=datetime.date(2026, 9, 30))
        b = PaieCalculateur.creer_bulletin(self.complet, 3, 2026, nb_jours_absence=2,
                                           note_remuneration='Absent 2 jours.')
        generer_ecritures_paie(b, tenant)
        lignes = JournalEntry.objects.filter(tenant=tenant)
        tot = lignes.aggregate(d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(tot['d'], tot['c'])
        self.assertEqual(lignes.filter(no_compte='661').aggregate(s=Sum('debit'))['s'], Decimal('140000'))
        l422 = lignes.filter(no_compte='422').aggregate(d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(l422['d'], l422['c'], "la dette envers l'employé doit être soldée")


class RetenueAbsenceApiTest(APITestCase):
    def setUp(self):
        ParametresFiscaux.objects.create(annee=2026, tranches_ir=[])
        self.tenant = Tenant.objects.create(nom='Daara', regime_paie='SIMPLIFIE')
        self.user = User.objects.create_user('a@a.sn', 'x', nom='A',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.employe = _employe(self.tenant)

    def _payload(self, **extra):
        p = {'employe_id': str(self.employe.id), 'mois': 3, 'annee': 2026}
        p.update(extra)
        return p

    def test_previsualisation_renvoie_le_montant_propose(self):
        r = self.client.post('/api/rh/bulletins/calculer/',
                             self._payload(nb_jours_absence=2, retenue_absence=None), format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(Decimal(r.data['retenue_absence_proposee']), Decimal('10000'))
        self.assertEqual(Decimal(r.data['salaire_brut']), Decimal('140000'))

    def test_creation_sans_note_refusee_avec_message(self):
        r = self.client.post('/api/rh/bulletins/', self._payload(nb_jours_absence=2), format='json')
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn('note', r.data['error'])

    def test_creation_avec_note(self):
        r = self.client.post('/api/rh/bulletins/', self._payload(
            nb_jours_absence=1, retenue_absence=4000, note_remuneration='Absent le 5.'), format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Decimal(r.data['retenue_absence']), Decimal('4000'))
        self.assertEqual(r.data['note_remuneration'], 'Absent le 5.')

    def test_pdf_affiche_la_retenue_et_la_note(self):
        b = PaieCalculateur.creer_bulletin(
            self.employe, 3, 2026, nb_jours_absence=2, nb_heures_retard=3,
            note_remuneration='Absente les 12 et 13 mars.')
        html = render_to_string('pdf/bulletin_paie.html', {
            'bulletin': b, 'employe': b.employe, 'tenant': self.tenant,
            'regime': 'SIMPLIFIE', 'date_edition': timezone.now(), 'nom_mois': 'Mars'})
        self.assertIn('Retenue pour absence (2 j) et retards (3 h)', html)
        self.assertIn('-12596', html)
        self.assertIn('Absente les 12 et 13 mars.', html)
        self.assertNotIn('{%', html)
        self.assertNotIn('{#', html)
        r = self.client.get(f'/api/rh/bulletins/{b.id}/pdf/')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b'%PDF'))
