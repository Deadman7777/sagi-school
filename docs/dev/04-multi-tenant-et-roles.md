# 4 — Multi-tenant, authentification et rôles

Une installation cloud héberge toutes les écoles clientes dans **une seule base
de données**. La séparation est logique, pas physique. Tout ce document existe
pour qu'elle ne fuie jamais.

## Le principe

Chaque modèle métier porte une clé étrangère `tenant` (via `TenantModel`).
Chaque requête est rattachée à un tenant. Chaque `queryset` filtre dessus.

Il n'y a **pas** de mécanisme automatique qui filtre à votre place. Pas de
manager par défaut, pas de middleware qui réécrit les requêtes. Un `queryset`
non filtré retourne les données de toutes les écoles. C'est un choix explicite —
un filtrage magique donne une fausse sécurité et casse les commandes de
maintenance — mais il vous rend responsable.

## Résoudre le tenant : une seule façon

```python
from core.tenant import get_tenant

def ma_vue(request):
    tenant = get_tenant(request)
    qs = MonModele.objects.filter(tenant=tenant)
```

**Jamais** de *réimplémentation* locale de la résolution. **Jamais** de lecture
directe de l'en-tête `X-Tenant-ID`. Les deux ont existé et les deux étaient des
failles.

Vous croiserez des méthodes `get_tenant(self)` sur certains ViewSets — par
exemple `apps/paiements/views.py`. Ce sont de simples délégations
(`return get_tenant(self.request)`) pour raccourcir l'écriture dans la classe,
pas des variantes du calcul. Si vous en ajoutez une, qu'elle reste une
délégation d'une ligne.

### Les règles de résolution

`backend/core/tenant.py`, fonction `_resolve_tenant` :

| Utilisateur | En-tête `X-Tenant-ID` | Tenant retenu |
|---|---|---|
| Non authentifié | quelconque | `None` |
| Rôle normal | **ignoré** | celui de l'utilisateur |
| `SUPER_ADMIN` | fourni | celui de l'en-tête |
| `SUPER_ADMIN` | absent | `None` — jamais de repli sur « la première école » |

L'en-tête n'est digne de confiance **que** pour un super-administrateur. Sans
cette règle, un utilisateur authentifié de l'école A lirait l'école B en
falsifiant un en-tête.

Le résultat est mis en cache 5 minutes par identifiant (`_fetch_tenant`), et
seuls les tenants `actif=True` sont résolus.

### Pourquoi la résolution est paresseuse

`TenantMiddleware` s'exécute **avant** l'authentification DRF : au moment où il
tourne, `request.user` est encore anonyme. Il pose donc un `SimpleLazyObject`
qui appellera `_resolve_tenant` à la première lecture — dans la vue, une fois
l'utilisateur authentifié.

Conséquence : **ne lisez pas `request.tenant` dans un middleware** placé avant
DRF, vous obtiendriez `None`.

## Authentification

JWT, via `djangorestframework-simplejwt`. Configuration dans
`backend/config/settings/base.py` :

```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ('...JWTAuthentication',),
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 500,
}
```

Tout est authentifié par défaut. Les rares vues publiques déclarent
explicitement `permission_classes = [AllowAny]` — la demande de démonstration du
site vitrine et les compteurs agrégés (`apps/licences/site_public.py`), et la
réception de sauvegarde, qui s'authentifie par signature de clé de licence.

Côté frontend, `core/interceptors/auth.interceptor.ts` ajoute à chaque requête
le `Authorization: Bearer <token>` et, le cas échéant, le `X-Tenant-ID`.

> `PAGE_SIZE = 500` est volontairement élevé : les écrans affichent des listes
> complètes (tous les élèves, tout le journal). Si vous ajoutez un écran sur une
> table qui peut dépasser ce volume, paginez côté client explicitement.

## Rôles

`backend/apps/users/models.py` et `backend/core/permissions.py`.

| Rôle | Portée | Qui, dans la vraie vie |
|---|---|---|
| `SUPER_ADMIN` | Toutes les écoles | **HADY GESMAN, l'éditeur** |
| `ADMIN_ECOLE` | Son école, tout | Le directeur ou fondateur d'une école cliente |
| `ADMIN_RH` | `rh`, `dashboard` | Responsable du personnel |
| `ADMIN_COMPTABLE` | `comptabilite`, `fiscal`, `dashboard` | Comptable |
| `ADMIN_SCOLARITE` | `eleves`, `paiements`, `dashboard` | Secrétariat |
| `LECTEUR` | `dashboard` | Membre du conseil, expert-comptable externe |

> **Ne confondez pas `SUPER_ADMIN` et `ADMIN_ECOLE`.** Le premier est l'éditeur
> du logiciel et administre le parc de clients ; le second est le client. Un
> `SUPER_ADMIN` **n'a pas de tenant** : les vues métier lui renvoient une erreur
> et le redirigent vers son propre tableau de bord
> (`/api/dashboard/superadmin/`). Une vue qui suppose « tout utilisateur a un
> tenant » plantera pour lui.

Le mapping rôle → modules vit dans `ROLE_PERMISSIONS`
(`backend/core/permissions.py`), avec les classes de permission DRF associées
(`CanAccessRH`, `CanAccessComptabilite`, `CanAccessScolarite`, `IsSuperAdmin`,
`IsAdminEcole`).

## Journal d'audit

`core.models.log_audit(request, action, modele, objet_id, description)` écrit une
entrée `dashboard.AuditLog`. Appelez-le sur toute opération sensible :
création et annulation de règlement, validation de bulletin de paie, changement
de licence, clôture d'exercice.

C'est ce qui rend un compte partagé inutilisable en pratique : sans un compte par
personne, le journal ne dit plus qui a fait quoi.

## La checklist avant d'ouvrir une pull request

- [ ] Tout nouveau modèle hérite de `TenantModel`.
- [ ] Tout `queryset` d'une vue filtre sur `tenant`.
- [ ] Le tenant vient de `get_tenant(request)`, d'aucune autre source.
- [ ] Tout champ séquentiel a une `UniqueConstraint(tenant, champ)`.
- [ ] Les opérations sensibles appellent `log_audit`.
- [ ] Le cas `SUPER_ADMIN` sans tenant ne provoque pas d'exception.

Il existe un test dédié à l'isolation : `backend/core/test_tenant_isolation.py`,
et un test à deux écoles `backend/apps/tenants/tests_deux_ecoles.py`. Étendez-les
plutôt que d'en créer d'autres.
