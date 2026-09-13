"""Diagnostic du courriel des demandes de renouvellement.

    python manage.py tester_courriel --settings=config.settings.cloud

Affiche la configuration (sans le mot de passe) et envoie un message de test à
LICENCE_SUPPORT_EMAIL, en montrant l'erreur exacte au lieu de l'avaler.
"""
from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Envoie un courriel de test au support HADY GESMAN et affiche l'erreur éventuelle."

    def handle(self, *args, **options):
        from apps.licences.renouvellement import destinataire, smtp_configure
        self.stdout.write(f"EMAIL_BACKEND       = {settings.EMAIL_BACKEND}")
        self.stdout.write(f"EMAIL_HOST          = {getattr(settings, 'EMAIL_HOST', '')}")
        self.stdout.write(f"EMAIL_PORT          = {getattr(settings, 'EMAIL_PORT', '')}")
        self.stdout.write(f"EMAIL_USE_TLS       = {getattr(settings, 'EMAIL_USE_TLS', '')}")
        self.stdout.write(f"EMAIL_HOST_USER     = {getattr(settings, 'EMAIL_HOST_USER', '')}")
        self.stdout.write(f"EMAIL_HOST_PASSWORD = {'(renseigné)' if getattr(settings, 'EMAIL_HOST_PASSWORD', '') else '(VIDE)'}")
        self.stdout.write(f"DEFAULT_FROM_EMAIL  = {getattr(settings, 'DEFAULT_FROM_EMAIL', '')}")
        self.stdout.write(f"Destinataire        = {destinataire()}")
        if not smtp_configure():
            self.stdout.write(self.style.ERROR(
                "SMTP NON configuré : EMAIL_BACKEND doit être smtp et EMAIL_HOST renseigné dans le .env."))
            return
        try:
            EmailMessage("[SAGI SCHOOL] Test d'envoi — demandes de renouvellement",
                         "Si vous lisez ce message, les demandes de renouvellement arrivent bien.",
                         getattr(settings, 'DEFAULT_FROM_EMAIL', None) or settings.EMAIL_HOST_USER,
                         [destinataire()]).send(fail_silently=False)
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"ÉCHEC : {type(exc).__name__}: {exc}"))
            return
        self.stdout.write(self.style.SUCCESS("Courriel de test envoyé. Vérifiez la boîte (et les indésirables)."))
