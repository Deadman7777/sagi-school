"""Un réglage enregistré est visible tout de suite, partout.

Le bug réel (18/09/2026) : on modifiait une échéance dans Paramètres, on
passait dans un autre module, on revenait — et la valeur d'avant était de
retour ; elle réapparaissait « au bout d'un moment ». Rien n'était perdu en
base. L'objet Tenant est mis en cache 5 minutes (core/tenant.py) et porte
TOUS les réglages de l'école : l'enregistrement ne jetait pas cette copie,
donc les vues relisaient l'ancienne pendant 5 minutes. Cloud et local.

Une école neuve n'avait rien en cache — d'où « ça marche pour la nouvelle
école, pas pour les autres ».

Ce que ces tests rendent impossible :
- un réglage enregistré que la lecture suivante ne voit pas ;
- une école dont la copie en cache survit à son propre enregistrement ;
- une réponse d'API sans consigne de cache (ceinture et bretelles : le
  navigateur et Electron sont libres, sinon, de resservir l'ancienne).
"""
from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.tenants.models import Tenant
from apps.users.models import User


class CacheApiTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='École du Cap', code_etablissement='CAP')
        self.user = User.objects.create_user('dir@cap.sn', 'x', nom='Directeur',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)

    def test_toute_reponse_api_interdit_le_cache(self):
        for url in ('/api/tenants/mon_ecole/', '/api/eleves/garde-soir/', '/api/eleves/'):
            with self.subTest(url=url):
                reponse = self.client.get(url)
                self.assertIn('no-store', reponse['Cache-Control'], url)

    def test_la_valeur_relue_est_celle_qu_on_vient_d_enregistrer(self):
        # Le scénario signalé : on enregistre, on repart, on revient.
        # La lecture préalable met l'école en cache, comme une session réelle.
        self.client.get('/api/tenants/mon_ecole/')
        reponse = self.client.patch('/api/tenants/mon_ecole/',
                                    {'garde_soir_actif': True, 'jour_echeance': 5}, format='json')
        self.assertEqual(reponse.status_code, 200, reponse.data)

        relu = self.client.get('/api/tenants/mon_ecole/').data
        self.assertTrue(relu['garde_soir_actif'])
        self.assertEqual(relu['jour_echeance'], 5)

    def test_le_reglage_traverse_les_autres_modules(self):
        # Le bouton Garderie de l'écran Élèves lit le même réglage par une
        # autre vue : elle doit voir la même chose, tout de suite.
        self.client.get('/api/eleves/garde-soir/')
        self.client.patch('/api/tenants/mon_ecole/', {'garde_soir_actif': True}, format='json')
        self.assertTrue(self.client.get('/api/eleves/garde-soir/').data['actif'])

        self.client.patch('/api/tenants/mon_ecole/', {'garde_soir_actif': False}, format='json')
        self.assertFalse(self.client.get('/api/eleves/garde-soir/').data['actif'])

    def test_enregistrer_jette_la_copie_en_cache(self):
        from core.tenant import cle_cache_tenant
        self.client.get('/api/tenants/mon_ecole/')
        self.assertIsNotNone(cache.get(cle_cache_tenant(self.tenant.id)))
        self.tenant.jour_echeance = 7
        self.tenant.save()
        self.assertIsNone(cache.get(cle_cache_tenant(self.tenant.id)))
