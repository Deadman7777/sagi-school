"""Images des documents PDF du guide : reçu, certificat, bulletins, proforma…

Les documents sont demandés à l'API de la démonstration, exactement comme
l'application le fait, puis la première page est rendue en image.

Usage, depuis backend/ :

    DJANGO_SETTINGS_MODULE=config.settings.demo \\
        python ../docs/formation/documents.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent.parent / 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.demo')

import django  # noqa: E402

django.setup()

from PIL import Image  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

from apps.academique.models import Classe  # noqa: E402
from apps.eleves.models import Eleve  # noqa: E402
from apps.paiements.models import Paiement, Proforma  # noqa: E402
from apps.rh.models import BulletinPaie  # noqa: E402
from apps.users.models import User  # noqa: E402

SORTIE = ICI / 'captures'

client = APIClient()
client.force_authenticate(User.objects.get(email='directrice@lespalmiers.sn'))


def rendre(nom, url, largeur=1240):
    reponse = client.get(url)
    if reponse.status_code != 200 or not reponse.get('Content-Type', '').startswith('application/pdf'):
        raise SystemExit(f'{nom} : {url} → {reponse.status_code} {reponse.get("Content-Type")}')
    contenu = b''.join(reponse.streaming_content) if reponse.streaming else reponse.content
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / 'doc.pdf'
        pdf.write_bytes(contenu)
        subprocess.run(['pdftoppm', '-f', '1', '-l', '1', '-r', '150', '-png',
                        str(pdf), str(Path(tmp) / 'page')], check=True)
        png = next(Path(tmp).glob('page*.png'))
        image = Image.open(png).convert('RGB')
        if image.width > largeur:
            image = image.resize((largeur, round(image.height * largeur / image.width)),
                                 Image.LANCZOS)
        image.save(SORTIE / f'{nom}.webp', 'WEBP', quality=85, method=6)
    print('  ✓', nom)


# L'élève qu'on suit dans tout le guide : une fille de la famille FALL.
eleve = Eleve.objects.filter(nom_complet__endswith='FALL', section__nom='Élémentaire') \
    .order_by('numero').first()
paiement = Paiement.objects.filter(eleve=eleve, statut='ACTIF').exclude(mois_regles=[]) \
    .order_by('-date_paiement').first()
cm2 = Classe.objects.get(nom='CM2')

rendre('doc-recu-a5', f'/api/paiements/paiements/{paiement.id}/recu-pdf/?taille=A5')
rendre('doc-recu-ticket', f'/api/paiements/paiements/{paiement.id}/recu-pdf/?taille=80MM', 600)
rendre('doc-certificat', f'/api/eleves/{eleve.id}/certificat/')
rendre('doc-bulletins-classe', f'/api/academique/bulletins-classe/{cm2.id}/T1/', 1600)
rendre('doc-bulletin-paie',
       f'/api/rh/bulletins/{BulletinPaie.objects.filter(statut="VALIDE").order_by("-annee", "-mois").first().id}/pdf/')
rendre('doc-proforma', f'/api/paiements/proformas/{Proforma.objects.order_by("numero").first().id}/pdf/')
