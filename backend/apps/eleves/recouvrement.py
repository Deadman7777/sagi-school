"""Le recouvrement de l'année : attendu, payé, reste, taux. Un seul calcul.

Le tableau de bord et le suivi mensuel l'établissaient chacun de leur côté.
Le premier ne comptait que les élèves présents ; le second additionnait aussi
les règlements des élèves partis. Même école, même jour : 15 051 000 F
d'impayés sur l'un, 14 791 000 F sur l'autre. Une direction qui voit deux
chiffres ne croit plus aucun des deux.

Le périmètre est celui du module Élèves : les élèves PRÉSENTS (ni sortis, ni
fiches de créance). Ce qu'un élève parti a versé reste une recette de l'année,
visible dans la trésorerie et les encaissements — mais il ne compte ni dans
l'attendu ni dans le recouvrement, puisqu'on ne lui réclame plus rien.
"""
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce

from .models import Eleve
from .parcours import eleves_presents


def eleves_avec_paye(tenant, exercice):
    """Les élèves présents, chacun avec ce qu'il a réglé (`paye_recouvrement`)."""
    actif = Q(paiements__statut='ACTIF')
    return (eleves_presents(Eleve.objects.filter(tenant=tenant, exercice=exercice))
            .annotate(paye_recouvrement=Coalesce(
                Sum('paiements__montant_inscription', filter=actif) +
                Sum('paiements__montant_mensualite', filter=actif) +
                Sum('paiements__montant_uniforme', filter=actif) +
                Sum('paiements__montant_fournitures', filter=actif) +
                Sum('paiements__montant_cantine', filter=actif) +
                Sum('paiements__montant_divers', filter=actif),
                Value(0), output_field=DecimalField()))
            .select_related('section', 'exercice', 'tenant', 'classe')
            .prefetch_related('abonnements__service', 'formules_eleve__formule',
                              'prises_en_charge_organisme__organisme'))


def totaux(eleves):
    """Totaux d'une liste d'élèves annotée par `eleves_avec_paye`."""
    attendu = sum(float(e.total_attendu) for e in eleves)
    paye = sum(float(e.paye_recouvrement or 0) for e in eleves)
    return {
        'nb_eleves': len(eleves),
        'total_attendu': round(attendu, 2),
        'total_paye': round(paye, 2),
        # Un trop-perçu ne masque pas l'impayé d'un autre : le reste se compte
        # élève par élève, comme sur la liste et à la clôture.
        'reste': round(sum(max(float(e.total_attendu) - float(e.paye_recouvrement or 0), 0.0)
                           for e in eleves), 2),
        'taux': round(paye / attendu * 100, 1) if attendu > 0 else 0,
    }


def recouvrement(tenant, exercice):
    return totaux(list(eleves_avec_paye(tenant, exercice)))
