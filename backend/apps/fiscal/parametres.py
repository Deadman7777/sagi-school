"""Paramètres fiscaux datés — complété au lot fiscal (voir models.ParametreFiscal)."""

DEFAUTS = {
    'TVA_TAUX_NORMAL': 18,
}


def valeur_parametre(code, tenant=None, date=None, defaut=None):
    return DEFAUTS.get(code, defaut)
