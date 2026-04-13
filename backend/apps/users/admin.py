from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display   = ['email', 'nom', 'role', 'tenant', 'actif', 'created_at']
    list_filter    = ['role', 'actif', 'tenant']
    search_fields  = ['email', 'nom']
    ordering       = ['email']
    fieldsets      = (
        (None,           {'fields': ('email', 'password')}),
        ('Informations', {'fields': ('nom', 'prenom', 'role', 'tenant')}),
        ('Permissions',  {'fields': ('actif', 'is_staff', 'is_superuser')}),
    )
    add_fieldsets  = (
        (None, {'fields': ('email', 'nom', 'role', 'tenant', 'password1', 'password2')}),
    )
