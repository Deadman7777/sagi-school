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
    ).select_related('section', 'exercice').prefetch_related('abonnements__service')

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

    # 3. Stats financières — MÊME calcul que le compte de résultat et que le
    # tableau de bord (apps/comptabilite/resultat.py).
    #
    # Ce récapitulatif totalisait le débit brut des seules écritures
    # source='CHARGE'. Une charge écrit quatre lignes — 6xx débit, 401 crédit,
    # 401 débit, 5xx crédit — donc le débit brut comptait chaque dépense DEUX
    # fois ; et la paie, les amortissements et les intérêts d'emprunt, portés
    # par d'autres sources, en étaient absents. L'écran où le directeur valide
    # sa fin d'année annonçait ainsi 14 331 300 de charges pour 46 496 494
    # réelles, et un résultat presque deux fois trop élevé.
    from apps.comptabilite.resultat import totaux_resultat

    paiements = Paiement.objects.filter(tenant=tenant, exercice=exercice)
    totaux         = totaux_resultat(journal)
    total_recettes = totaux['total_produits']
    total_charges  = totaux['total_charges']

    return {
        'peut_cloturer':   len(problemes) == 0,
        'problemes':       problemes,
        'warnings':        warnings,
        'stats': {
            'total_recettes':  total_recettes,
            'total_charges':   total_charges,
            'resultat_net':    totaux['resultat_net'],
            'eleves_total':    eleves.count(),
            'eleves_impayes':  eleves_impayes,
            'montant_impaye':  montant_impaye,
            'nb_paiements':    paiements.count(),
            'total_debit':     total_debit,
            'total_credit':    total_credit,
        }
    }


def cloturer_exercice(exercice, creer_suivant=True, reporter_impayes=True):
    """
    Clôture l'exercice et optionnellement crée le suivant.

    `reporter_impayes` reconduit les restes dus sur le nouvel exercice
    (réinscription des élèves concernés + à-nouveaux 411/890). Sans effet si
    le nouvel exercice n'est pas créé — le report reste alors jouable après
    coup, l'exercice clôturé n'étant jamais modifié (voir report_reliquats).
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

        # Trésorerie reportée sur le nouvel exercice : le solde RÉEL de chaque
        # poste, lu au journal (apps/comptabilite/tresorerie.py) — le même
        # calcul que « Trésorerie par canal » du tableau de bord.
        #
        # Le report se faisait sur « recettes − charges », c'est-à-dire un
        # RÉSULTAT et non une trésorerie : il ignorait les décaissements de
        # paie, les investissements et les remboursements d'emprunt, et versait
        # le tout dans la caisse en remettant banque et mobile money à zéro.
        # Une école ouvrait donc son année suivante sur des soldes faux.
        from apps.comptabilite.tresorerie import soldes_cloture
        soldes = soldes_cloture(exercice)

        nouvel_exercice = Exercice.objects.create(
            tenant             = exercice.tenant,
            annee_scolaire     = nouvelle_annee,
            date_debut         = exercice.date_fin + datetime.timedelta(days=1),
            date_fin           = exercice.date_fin + relativedelta(years=1),
            solde_initial_caisse = max(soldes['caisse'], 0),
            solde_initial_banque = max(soldes['banque'], 0),
            solde_initial_mobile = max(soldes['mobile'], 0),
            devise             = exercice.devise,
            cloture            = False,
        )

    report = None
    if nouvel_exercice and reporter_impayes:
        from .report_reliquats import reporter_reliquats
        report = reporter_reliquats(exercice, nouvel_exercice)

    return {
        'exercice_cloture': exercice.annee_scolaire,
        'nouvel_exercice':  nouvel_exercice.annee_scolaire if nouvel_exercice else None,
        'date_cloture':     str(exercice.date_cloture),
        'report_reliquats': report,
    }
