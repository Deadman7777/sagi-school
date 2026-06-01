"""
Test manuel d'isolation tenant — à exécuter localement, AVANT déploiement cloud.

Scénario :
  1. Crée 2 tenants (A et B) + 1 user dans A
  2. Simule une requête où ce user envoie X-Tenant-ID=<B.id> dans le header
  3. Vérifie que _resolve_tenant retourne le tenant A (le SIEN), pas B
  4. Vérifie qu'un SUPER_ADMIN peut basculer via le header
  5. Vérifie qu'un non-authentifié obtient None

Usage :
  DJANGO_SETTINGS_MODULE=config.settings.local python test_tenant_isolation.py
"""
import os, sys, django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from django.test import RequestFactory
from django.contrib.auth.models import AnonymousUser
from core.tenant import _resolve_tenant
from core.middleware import TenantMiddleware


def make_request(user, tenant_id_header=None):
    """Crée une requête comme si le middleware avait tourné dessus."""
    rf = RequestFactory()
    headers = {}
    if tenant_id_header:
        headers['HTTP_X_TENANT_ID'] = tenant_id_header
    req = rf.get('/api/eleves/', **headers)
    req.user = user
    # Simule le middleware
    mw = TenantMiddleware(lambda r: None)
    mw(req)
    return req


def main():
    from apps.tenants.models import Tenant
    from apps.users.models import User

    # Setup : 2 tenants
    tenant_a, _ = Tenant.objects.get_or_create(
        nom='_TEST_École A', defaults={'code_etablissement': 'TEST_A'}
    )
    tenant_b, _ = Tenant.objects.get_or_create(
        nom='_TEST_École B', defaults={'code_etablissement': 'TEST_B'}
    )

    # User dans A
    user_a, _ = User.objects.get_or_create(
        email='_test_user_a@test.local',
        defaults={'nom': 'TestA', 'tenant': tenant_a, 'role': 'ADMIN_ECOLE'}
    )
    user_a.tenant = tenant_a; user_a.role = 'ADMIN_ECOLE'; user_a.save()

    # Super admin (sans tenant)
    super_admin, _ = User.objects.get_or_create(
        email='_test_super@test.local',
        defaults={'nom': 'TestSuper', 'tenant': None, 'role': 'SUPER_ADMIN'}
    )
    super_admin.tenant = None; super_admin.role = 'SUPER_ADMIN'; super_admin.save()

    failures = []

    # ─── Test 1 : User A SANS header → doit voir son tenant A ──────
    req = make_request(user_a)
    resolved = req.tenant._wrapped if hasattr(req.tenant, '_wrapped') else None
    # Force évaluation
    resolved = req.tenant
    actual_id = getattr(resolved, 'id', None)
    if actual_id == tenant_a.id:
        print('✅ TEST 1 OK : user A sans header → voit tenant A')
    else:
        failures.append(f'TEST 1 KO : attendu {tenant_a.id}, reçu {actual_id}')

    # ─── Test 2 : User A AVEC X-Tenant-ID=B → DOIT voir A (pas B) ──
    req = make_request(user_a, tenant_id_header=str(tenant_b.id))
    resolved = req.tenant
    actual_id = getattr(resolved, 'id', None)
    if actual_id == tenant_a.id:
        print('✅ TEST 2 OK : user A avec header B → voit A (header ignoré)')
    elif actual_id == tenant_b.id:
        failures.append('TEST 2 KO 🚨 : user A a réussi à voir tenant B via header — VULNÉRABLE !')
    else:
        failures.append(f'TEST 2 KO : attendu {tenant_a.id}, reçu {actual_id}')

    # ─── Test 3 : SUPER_ADMIN sans header → None ───────────────────
    req = make_request(super_admin)
    resolved = req.tenant
    actual = bool(resolved)
    if not actual:
        print('✅ TEST 3 OK : super_admin sans header → None')
    else:
        failures.append(f'TEST 3 KO : super_admin sans header devrait avoir None, reçu {resolved}')

    # ─── Test 4 : SUPER_ADMIN avec header B → voit B (basculement) ─
    req = make_request(super_admin, tenant_id_header=str(tenant_b.id))
    resolved = req.tenant
    actual_id = getattr(resolved, 'id', None)
    if actual_id == tenant_b.id:
        print('✅ TEST 4 OK : super_admin avec header B → voit B (basculement OK)')
    else:
        failures.append(f'TEST 4 KO : super_admin devrait voir B, reçu {actual_id}')

    # ─── Test 5 : SUPER_ADMIN avec header BIDON → None ─────────────
    req = make_request(super_admin, tenant_id_header='00000000-0000-0000-0000-000000000000')
    resolved = req.tenant
    actual = bool(resolved)
    if not actual:
        print('✅ TEST 5 OK : super_admin avec header invalide → None')
    else:
        failures.append('TEST 5 KO : super_admin avec UUID bidon ne devrait pas matcher')

    # ─── Test 6 : Anonymous → None ─────────────────────────────────
    req = make_request(AnonymousUser(), tenant_id_header=str(tenant_a.id))
    resolved = req.tenant
    actual = bool(resolved)
    if not actual:
        print('✅ TEST 6 OK : non authentifié → None (même avec header)')
    else:
        failures.append('TEST 6 KO : anon avec header ne devrait jamais matcher')

    # ─── Cleanup ───────────────────────────────────────────────────
    User.objects.filter(email__startswith='_test_').delete()
    Tenant.objects.filter(nom__startswith='_TEST_').delete()

    if failures:
        print('\n❌ ÉCHECS :')
        for f in failures:
            print('  -', f)
        sys.exit(1)
    print('\n🎉 Tous les tests passent — isolation tenant OK.')


if __name__ == '__main__':
    main()
