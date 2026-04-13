"""
Service de clôture d'exercice — SAGI SCHOOL
"""
from django.utils import timezone
from django.db.models import Sum
from .models import Exercice, Paiement
from apps.eleves.models import Eleve
from apps.comptabilite.models import JournalEntry


def verifier_avant_cloture(exercice):
    """
    Retourne une liste de problèmes bloquants avant clôture.
    """
    problemes = []
    warnings  = []

    tenant = exercice.tenant

    # 1. Vérifier équilibre du journal
    journal = JournalEntry.objects.filter(tenant=tenant, exercice=exercice)
    total_debit  = float(journal.aggregate(t=Sum('debit'))['t']  or 0)
    total_credit = float(journal.aggregate(t=Sum('credit'))['t'] or 0)
    ecart = abs(total_debit - total_credit)
    if ecart > 1:
        problemes.append(f"Journal déséquilibré — écart de {ecart:,.0f} FCFA entre débit et crédit")

    # 2. Compter élèves avec solde impayé
    eleves = Eleve.objects.filter(tenant=tenant, exercice=exercice).annotate(
        total_paye_sql=Sum('paiements__montant_inscription') +
                       Sum('paiements__montant_mensualite')  +
                       Sum('paiements__montant_uniforme')    +
                       Sum('paiements__montant_fournitures') +
                       Sum('paiements__montant_cantine')     +
                       Sum('paiements__montant_divers')
    ).select_related('section')

    eleves_impayes = 0
    montant_impaye = 0
    for e in eleves:
        reste = float(e.total_attendu) - float(e.total_paye_sql or 0)
        if reste > 0:
            eleves_impayes += 1
            montant_impaye += reste

    if eleves_impayes > 0:
        warnings.append(
            f"{eleves_impayes} élève(s) ont un solde impayé — "
            f"total: {montant_impaye:,.0f} FCFA"
        )

    # 3. Stats financières
    paiements      = Paiement.objects.filter(tenant=tenant, exercice=exercice)
    total_recettes = float(paiements.aggregate(
        t=Sum('montant_inscription') + Sum('montant_mensualite') +
          Sum('montant_uniforme')    + Sum('montant_fournitures') +
          Sum('montant_cantine')     + Sum('montant_divers')
    )['t'] or 0)

    total_charges = float(JournalEntry.objects.filter(
        tenant=tenant, exercice=exercice, source='CHARGE'
    ).aggregate(t=Sum('debit'))['t'] or 0)

    return {
        'peut_cloturer':   len(problemes) == 0,
        'problemes':       problemes,
        'warnings':        warnings,
        'stats': {
            'total_recettes':  total_recettes,
            'total_charges':   total_charges,
            'resultat_net':    total_recettes - total_charges,
            'eleves_total':    eleves.count(),
            'eleves_impayes':  eleves_impayes,
            'montant_impaye':  montant_impaye,
            'nb_paiements':    paiements.count(),
            'total_debit':     total_debit,
            'total_credit':    total_credit,
        }
    }


def cloturer_exercice(exercice, creer_suivant=True):
    """
    Clôture l'exercice et optionnellement crée le suivant.
    """
    from dateutil.relativedelta import relativedelta
    import datetime

    # Clôturer
    exercice.cloture      = True
    exercice.date_cloture = timezone.now()
    exercice.save()

    nouvel_exercice = None

    if creer_suivant:
        # Parser l'année scolaire ex: "2025-2026" → "2026-2027"
        try:
            annees        = exercice.annee_scolaire.split('-')
            annee1        = int(annees[0]) + 1
            annee2        = int(annees[1]) + 1
            nouvelle_annee = f"{annee1}-{annee2}"
        except Exception:
            nouvelle_annee = f"Exercice {timezone.now().year + 1}"

        # Solde de clôture = trésorerie finale
        from apps.dashboard.views import sum_paiements
        paiements      = Paiement.objects.filter(tenant=exercice.tenant, exercice=exercice)
        total_recettes = sum_paiements(paiements)
        total_charges  = float(JournalEntry.objects.filter(
            tenant=exercice.tenant, exercice=exercice, source='CHARGE'
        ).aggregate(t=Sum('debit'))['t'] or 0)

        solde_final = (float(exercice.solde_initial_caisse +
                             exercice.solde_initial_banque +
                             exercice.solde_initial_mobile) +
                       total_recettes - total_charges)

        nouvel_exercice = Exercice.objects.create(
            tenant             = exercice.tenant,
            annee_scolaire     = nouvelle_annee,
            date_debut         = exercice.date_fin + datetime.timedelta(days=1),
            date_fin           = exercice.date_fin + relativedelta(years=1),
            solde_initial_caisse = max(solde_final, 0),
            solde_initial_banque = 0,
            solde_initial_mobile = 0,
            devise             = exercice.devise,
            cloture            = False,
        )

    return {
        'exercice_cloture': exercice.annee_scolaire,
        'nouvel_exercice':  nouvel_exercice.annee_scolaire if nouvel_exercice else None,
        'date_cloture':     str(exercice.date_cloture),
    }
