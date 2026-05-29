"""
Initialise une nouvelle installation SAGI SCHOOL chez une école cliente :
- Tenant (école)
- Licence ESSAI 30 jours
- Exercice scolaire courant
- User ADMIN_ECOLE (le directeur / admin principal de cette école)

Le SUPER_ADMIN (propriétaire du produit HADY GESMAN) n'est PAS créé ici :
il est géré séparément via `manage.py createsuperuser`.

Données passées via un fichier JSON (--payload chemin.json) pour éviter les
problèmes d'échappement shell avec les caractères spéciaux du mot de passe.

Idempotent : si une école existe déjà, la commande quitte sans rien
faire (réinstallation / lancement répété ne casse rien).
"""
import json
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from dateutil.relativedelta import relativedelta

from apps.tenants.models import Tenant
from apps.licences.models import Licence
from apps.paiements.models import Exercice
from apps.users.models import User


REQUIRED_FIELDS = [
    'ecole_nom', 'admin_email', 'admin_password',
    'admin_nom', 'annee_scolaire', 'date_debut', 'date_fin',
]


class Command(BaseCommand):
    help = "Crée Tenant + Licence ESSAI + Exercice + admin_ecole (1ère installation école cliente)"

    def add_arguments(self, parser):
        parser.add_argument('--payload', required=True,
                            help="Chemin vers le fichier JSON contenant les données d'install")

    def handle(self, *args, **opts):
        payload_path = Path(opts['payload'])
        if not payload_path.exists():
            raise CommandError(f"Fichier payload introuvable : {payload_path}")

        data = json.loads(payload_path.read_text(encoding='utf-8'))

        missing = [f for f in REQUIRED_FIELDS if not data.get(f)]
        if missing:
            raise CommandError(f"Champs manquants : {', '.join(missing)}")

        if Tenant.objects.exists():
            self.stdout.write(self.style.WARNING(
                "Une école existe déjà — installation déjà initialisée."
            ))
            return

        with transaction.atomic():
            tenant = Tenant.objects.create(
                nom=data['ecole_nom'],
                code_etablissement=data.get('ecole_code', 'ETB').upper()[:10],
                ville=data.get('ecole_ville', ''),
                adresse=data.get('ecole_adresse', ''),
                telephone=data.get('ecole_telephone', ''),
                email=data.get('ecole_email', ''),
                rccm=data.get('ecole_rccm', ''),
                ninea=data.get('ecole_ninea', ''),
            )

            cle = Licence.generer_cle(tenant.rccm or tenant.nom[:6].upper())
            Licence.objects.create(
                tenant=tenant,
                cle_licence=cle,
                type='ESSAI',
                statut='ESSAI',
                date_debut=date.today(),
                date_fin=date.today() + relativedelta(days=30),
            )

            Exercice.objects.create(
                tenant=tenant,
                annee_scolaire=data['annee_scolaire'],
                date_debut=data['date_debut'],
                date_fin=data['date_fin'],
                devise='FCFA',
            )

            User.objects.create_user(
                email=data['admin_email'],
                password=data['admin_password'],
                nom=data['admin_nom'],
                prenom=data.get('admin_prenom', ''),
                role='ADMIN_ECOLE',
                tenant=tenant,
                actif=True,
            )

        self.stdout.write(self.style.SUCCESS(
            f"Installation OK — école « {tenant.nom} », clé licence : {cle}"
        ))
