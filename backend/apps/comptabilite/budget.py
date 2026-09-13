"""Budget prévisionnel — calculs partagés.

Le réalisé d'une ligne de budget était calculé dans la vue du budget. Le cahier
mensuel et le tableau de bord en ont besoin aussi : trois recopies finiraient
par diverger (cf. un seul calcul par grandeur). Il n'existe plus qu'ici.
"""
from django.db.models import Sum
from django.db.models.functions import ExtractMonth

from .models import JournalEntry

MOIS_CHAMPS = ['m01', 'm02', 'm03', 'm04', 'm05', 'm06',
               'm07', 'm08', 'm09', 'm10', 'm11', 'm12']


def realise_par_mois(tenant, exercice, ligne):
    """Réalisé NET par mois d'une ligne de budget : débits − crédits, pour
    que les annulations/modifications par contre-écriture (crédit sur le
    6xx) soient bien déduites.

    CE QUI COMPTE dépend du mode de la ligne (`mode_realise`) :

      COMPTE      tout ce qui passe sur le compte et ses sous-comptes.
                  C'est le comportement d'origine, et il reste le défaut.
      IMPUTATION  seulement les écritures rattachées À CETTE ligne. C'est la
                  réponse au cas où un même 6xx sert à des dépenses
                  budgétées et à d'autres qui ne le sont pas.
      PAIE        seulement les écritures de paie sur le compte. Un salaire
                  saisi à la main à côté du bulletin ne le compte pas deux
                  fois.

    Si la ligne porte un projet (budget analytique), le réalisé est filtré
    sur ce projet — sinon on agrège tout le compte (budget général)."""
    if ligne.mode_realise == 'IMPUTATION':
        qs = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice, budget_ligne=ligne)
    else:
        sources = (('PAIE',) if ligne.mode_realise == 'PAIE'
                   else ('CHARGE', 'PAIE', 'BUDGET'))
        qs = JournalEntry.objects.filter(
            tenant=tenant, exercice=exercice, source__in=sources,
            no_compte__startswith=ligne.no_compte,
        )
        if ligne.projet_id is not None:
            qs = qs.filter(projet_id=ligne.projet_id)
    qs = qs.annotate(
        mois=ExtractMonth('date_ecriture')
    ).values('mois').annotate(d=Sum('debit'), c=Sum('credit'))
    return {r['mois']: float(r['d'] or 0) - float(r['c'] or 0) for r in qs}

