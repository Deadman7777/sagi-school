from rest_framework.permissions import BasePermission

# Mapping rôle → modules accessibles
ROLE_PERMISSIONS = {
    'SUPER_ADMIN': ['*'],
    'ADMIN_ECOLE': ['*'],
    'ADMIN_RH': ['rh', 'dashboard'],
    'ADMIN_COMPTABLE': ['comptabilite', 'fiscal', 'dashboard'],
    'ADMIN_SCOLARITE': ['eleves', 'paiements', 'dashboard'],
    'LECTEUR': ['dashboard'],
}

def has_module_access(user, module):
    if not user or not user.is_authenticated:
        return False
    role = getattr(user, 'role', None)
    if not role:
        return False
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
