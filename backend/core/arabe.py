"""Texte arabe dans les PDF xhtml2pdf.

ReportLab, sous xhtml2pdf, ne sait ni lier les lettres arabes entre elles ni
inverser le sens d'écriture : tout texte arabe doit être pré-formé avant d'entrer
dans le gabarit, et la police Amiri (OFL) embarquée via @font-face.
"""
import os

from django.conf import settings

FONT_DIR = os.path.join(settings.BASE_DIR, 'templates', 'pdf', 'fonts')
POLICE_ARABE = 'Amiri-Regular.ttf'
POLICE_LATINE = 'DejaVuSans.ttf'


def est_arabe(texte):
    """Le texte contient-il de l'arabe ? Sert à choisir la police d'une cellule
    dans un document par ailleurs latin (une matière nommée en arabe)."""
    return any('\u0600' <= c <= '\u06ff' or '\ufb50' <= c <= '\ufeff' for c in str(texte or ''))


def shape_ar(text):
    """Pré-forme l'arabe (ligatures + ordre visuel RTL) pour xhtml2pdf/ReportLab,
    qui ne savent ni façonner ni inverser. Échoue en douceur sur le texte brut."""
    if not text:
        return ''
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(str(text)))
    except Exception:
        return text


def font_link_callback(uri, rel):
    """Résout url('xxx.ttf') du @font-face vers le fichier embarqué."""
    if uri.endswith('.ttf'):
        return os.path.join(FONT_DIR, os.path.basename(uri))
    return uri
