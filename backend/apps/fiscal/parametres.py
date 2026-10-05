"""Lecture des paramètres fiscaux datés (voir models.ParametreFiscal).

Ordre de recherche, à une date donnée : la surcharge de l'école, puis la
valeur nationale, puis le défaut passé par l'appelant. Le paramètre retenu
est celui dont la date d'effet est la plus récente sans dépasser la date (et
dont la date de fin, s'il en a une, n'est pas passée).
"""
import datetime
from decimal import Decimal

from django.db.models import Q


def parametre(code, tenant=None, date=None):
    """Le ParametreFiscal en vigueur, ou None."""
    from .models import ParametreFiscal
    date = date or datetime.date.today()
    base = (ParametreFiscal.objects.filter(code=code, date_effet__lte=date)
            .filter(Q(date_fin__isnull=True) | Q(date_fin__gte=date)).order_by('-date_effet'))
    if tenant is not None:
        p = base.filter(tenant=tenant).first()
        if p is not None:
            return p
    return base.filter(tenant__isnull=True).first()


def valeur_parametre(code, tenant=None, date=None, defaut=None):
    p = parametre(code, tenant, date)
    if p is None:
        return defaut
    v = Decimal(p.valeur)
    return int(v) if v == v.to_integral_value() else float(v)
