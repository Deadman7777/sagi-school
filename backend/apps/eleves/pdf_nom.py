"""Noms de fichiers PDF lisibles et sûrs.

« Famille NDIAYE » → « situation_FamilleNDIAYE » : ASCII sans espaces, valable
dans un en-tête HTTP comme dans un nom de fichier Windows, et reconnaissable
parmi dix téléchargements du même jour.
"""
import re
import unicodedata


def nom_fichier(prefixe, libelle):
    nom = unicodedata.normalize('NFD', libelle or '')
    nom = re.sub(r'[^A-Za-z0-9-]', '', nom.encode('ascii', 'ignore').decode())
    return f'{prefixe}_{nom}' if nom else prefixe
