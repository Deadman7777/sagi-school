from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
import uuid


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra):
        email = self.normalize_email(email)
        user  = self.model(email=email, **extra)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault('role', 'SUPER_ADMIN')
        extra.setdefault('is_staff', True)
        extra.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('SUPER_ADMIN',      'Super Administrateur'),
        ('ADMIN_ECOLE',      'Administrateur École'),
        ('ADMIN_RH',         'Responsable RH'),
        ('ADMIN_COMPTABLE',  'Responsable Comptable'),
        ('ADMIN_SCOLARITE',  'Responsable Scolarité'),
        ('LECTEUR',          'Lecteur'),
    ]

    id        = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant    = models.ForeignKey('tenants.Tenant', null=True, blank=True,
                                   on_delete=models.CASCADE, related_name='users')
    nom       = models.CharField(max_length=150)
    prenom    = models.CharField(max_length=150, blank=True)
    email     = models.EmailField(unique=True)
    role      = models.CharField(max_length=20, choices=ROLE_CHOICES, default='LECTURE')
    actif     = models.BooleanField(default=True)
    is_staff  = models.BooleanField(default=False)
    derniere_connexion = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['nom']
    objects = UserManager()

    class Meta:
        db_table = 'users'

    def __str__(self):
        return f"{self.nom} ({self.role})"
