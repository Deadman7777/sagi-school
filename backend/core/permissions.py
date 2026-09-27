from rest_framework.permissions import BasePermission

# Mapping rôle → modules accessibles. MIROIR EXACT du menu de l'application
# (frontend/src/app/layout/shell/shell.component.ts, itemVisible) : le serveur
# refuse ce que le menu ne montre pas. Les deux listes divergeaient — le rôle
# « Responsable scolarité » voyait Académique à l'écran, pas au serveur.
ROLE_PERMISSIONS = {
    'SUPER_ADMIN': ['*'],
    'ADMIN_ECOLE': ['*'],
    'ADMIN_RH': ['rh', 'dashboard'],
    'ADMIN_COMPTABLE': ['comptabilite', 'fiscal', 'paiements', 'suivi-mensuel', 'gmrf',
                        'gouvernance', 'dashboard'],
    'ADMIN_SCOLARITE': ['eleves', 'garderie', 'paiements', 'suivi-mensuel', 'academique',
                        'dashboard'],
    'LECTEUR': ['dashboard'],
}

# Préfixe d'API → modules dont l'accès autorise à y ÉCRIRE. Un écran écrit
# parfois dans l'API d'un autre module : la saisie d'une charge (écran
# Paiements) écrit en comptabilité, l'encaissement d'une famille écrit sous
# /api/eleves/. Les préfixes absents (auth, tenants, licences, sauvegarde…)
# ont leurs propres contrôles.
MODULES_ECRITURE = {
    'eleves':       {'eleves', 'paiements', 'garderie', 'academique', 'suivi-mensuel'},
    'paiements':    {'paiements', 'eleves', 'garderie', 'suivi-mensuel'},
    'comptabilite': {'comptabilite', 'paiements', 'fiscal', 'gouvernance', 'suivi-mensuel'},
    'fiscal':       {'fiscal', 'comptabilite'},
    'academique':   {'academique'},
    'daara':        {'academique', 'eleves'},
    'gmrf':         {'gmrf'},
    'gouvernance':  {'gouvernance', 'comptabilite', 'paiements'},
    'rh':           {'rh'},
}


def peut_ecrire(user, prefixe):
    """L'utilisateur peut-il modifier les données sous /api/<prefixe>/ ?"""
    modules = MODULES_ECRITURE.get(prefixe)
    if modules is None:
        return True
    return any(has_module_access(user, m) for m in modules)


def has_module_access(user, module):
    if not user or not user.is_authenticated:
        return False
    role = getattr(user, 'role', None)
    if not role:
        return False
    # Modules choisis par l'école pour cet utilisateur : ils font foi et
    # remplacent ceux du rôle. Le plafond reste la licence, vérifiée ailleurs.
    perso = getattr(user, 'modules_autorises', None) or []
    if perso:
        return module in perso or module == 'dashboard'
    allowed = ROLE_PERMISSIONS.get(role, [])
    return '*' in allowed or module in allowed

class IsTenantMember(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.actif

class CanAccessRH(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and has_module_access(request.user, 'rh')

class CanAccessComptabilite(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and has_module_access(request.user, 'comptabilite')

class CanAccessScolarite(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and has_module_access(request.user, 'eleves')

class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'SUPER_ADMIN'

class IsAdminEcole(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in (
            'SUPER_ADMIN', 'ADMIN_ECOLE'
        )
