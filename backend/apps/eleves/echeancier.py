"""Échéancier d'un élève — ce qui est dû mois par mois, et ce qui reste.

Le suivi financier ne disait jusqu'ici qu'un total : « reste à payer
91 000 FCFA ». Une famille qui règle au mois ne peut rien en faire — elle ne
sait ni quels mois sont soldés, ni combien il manque sur celui en cours. Ce
module déroule le dû en lignes mensuelles, en face desquelles il place ce qui
a été encaissé.

Deux règles d'imputation, dans cet ordre :

  1. Un paiement qui DÉSIGNE ses mois (`Paiement.mois_regles`) est réparti sur
     eux à parts égales — même convention que la ventilation de l'école
     (`eleves/views.py`), pour que les deux écrans racontent la même histoire.
  2. Une mensualité payée sans préciser de mois s'impute sur les mois dus les
     PLUS ANCIENS encore ouverts. C'est ce que fait une école qui encaisse
     sans détailler, et surtout c'est la seule façon que la somme des lignes
     égale le total payé : une ligne de détail ne doit jamais contredire le
     total auquel elle participe.

L'inscription, l'uniforme, les fournitures et les services à paiement unique
ne sont pas mensuels : ils forment une ligne « hors mensualité » à part, sinon
ils gonfleraient arbitrairement le mois où ils ont été réglés.

La dette des années antérieures (`reliquat_anterieur`) reste hors de cet
échéancier — elle a son propre suivi, et la mélanger ferait passer toute une
école migrée pour débitrice de l'année en cours.
"""
NOMS_MOIS = {1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
             5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
             9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'}


def mois_factures(eleve):
    """Les numéros de mois réellement facturés à cet élève, dans l'ordre.

    Mois saisis par l'école s'il y en a ; sinon on déroule le prorata, qui ne
    donne qu'un NOMBRE, en calendrier à partir de la fin de l'exercice.
    """
    if eleve.mois_dus:
        return sorted(int(m) for m in eleve.mois_dus)
    if not eleve.exercice_id:
        return []
    nb = eleve.nb_mensualites_dues
    debut = eleve.exercice.date_debut.month
    premier = eleve.exercice.nb_mensualites - nb
    return [((debut - 1 + premier + i) % 12) + 1 for i in range(nb)]


def _annee_du_mois(exercice, num):
    """Année civile d'un mois de l'exercice (une année scolaire est à cheval)."""
    debut = exercice.date_debut
    return debut.year if num >= debut.month else debut.year + 1


def _services(eleve):
    """(montant mensuel, [(mois|None, montant)] pour les services uniques)."""
    mensuel, uniques = 0.0, []
    for ab in eleve.abonnements.all():
        s = ab.service
        if s.periodicite == 'MENSUEL':
            mensuel += float(s.montant or 0)
        else:
            uniques.append((s.mois_unique, float(s.montant or 0)))
    return mensuel, uniques


def construire_echeancier(eleve, today=None):
    """Rend {'lignes', 'hors_mensualite', 'totaux'} pour une fiche élève.

    `lignes` : une par mois facturé — {mois, nom, annee, du, paye, reste,
    statut, echu}. `statut` vaut SOLDE / PARTIEL / IMPAYE.
    """
    import datetime

    from apps.paiements.models import Paiement

    today = today or datetime.date.today()

    # Une fiche de créance ne doit rien au titre de l'année : pas d'échéancier.
    if eleve.fiche_creance or not eleve.exercice_id:
        return {'lignes': [], 'hors_mensualite': None,
                'totaux': {'du': 0.0, 'paye': 0.0, 'reste': 0.0}}

    exercice = eleve.exercice
    mois = mois_factures(eleve)
    svc_mensuel, svc_uniques = _services(eleve)
    mensualite = eleve.frais_mensualite_effectif      # déjà nette de la PEC
    du_mensuel = round(mensualite + svc_mensuel, 2)

    lignes = {m: {'mois': m, 'nom': NOMS_MOIS.get(m, str(m)),
                  'annee': _annee_du_mois(exercice, m),
                  'du': du_mensuel, 'paye': 0.0}
              for m in mois}

    # ── Hors mensualité : inscription et frais uniques ────────────────────
    section = eleve.section
    du_hors = 0.0
    if section:
        du_hors += max(float(section.frais_inscription or 0)
                       - eleve.montant_pec_inscription, 0.0)
        du_hors += float(section.frais_uniforme or 0)
        du_hors += float(section.frais_fournitures or 0)
    du_hors += sum(montant for _, montant in svc_uniques)
    du_hors = round(du_hors, 2)

    paye_hors = 0.0
    non_imputes = 0.0     # mensualités payées sans mois désigné

    for p in Paiement.objects.filter(
            tenant=eleve.tenant, exercice=exercice,
            eleve=eleve, statut='ACTIF').only(
            'montant_inscription', 'montant_mensualite', 'montant_uniforme',
            'montant_fournitures', 'montant_cantine', 'montant_divers',
            'mois_regles', 'services_regles'):
        paye_hors += (float(p.montant_inscription or 0)
                      + float(p.montant_uniforme or 0)
                      + float(p.montant_fournitures or 0))
        svc = sum(float(s.get('montant') or 0) for s in (p.services_regles or []))
        divers_manuel = max(0.0, float(p.montant_divers or 0) - svc)
        paye_hors += divers_manuel + float(p.montant_cantine or 0)

        montant_mois = float(p.montant_mensualite or 0) + svc
        designes = [int(x) for x in (p.mois_regles or []) if int(x) in lignes]
        if designes:
            part = montant_mois / len(designes)
            for m in designes:
                lignes[m]['paye'] += part
        else:
            non_imputes += montant_mois

    # Règle 2 : le reliquat non désigné solde les mois les plus anciens.
    for m in mois:
        if non_imputes <= 0:
            break
        manque = lignes[m]['du'] - lignes[m]['paye']
        if manque <= 0:
            continue
        pris = min(manque, non_imputes)
        lignes[m]['paye'] += pris
        non_imputes -= pris
    # Ce qui dépasse le dû de l'année est une avance : on la porte sur le
    # dernier mois plutôt que de la perdre, sinon la somme des lignes serait
    # inférieure au total payé.
    if non_imputes > 0 and mois:
        lignes[mois[-1]]['paye'] += non_imputes

    sortie = []
    for m in mois:
        ligne = lignes[m]
        paye = round(ligne['paye'], 2)
        reste = round(max(ligne['du'] - paye, 0.0), 2)
        echu = datetime.date(ligne['annee'], m, 1) <= today
        sortie.append({
            **ligne,
            'paye':   paye,
            'reste':  reste,
            'echu':   echu,
            'statut': 'SOLDE' if reste <= 0 else ('PARTIEL' if paye > 0 else 'IMPAYE'),
        })

    paye_hors = round(min(paye_hors, du_hors) if du_hors else paye_hors, 2)
    hors = {
        'libelle': 'Inscription et frais uniques',
        'du':      du_hors,
        'paye':    paye_hors,
        'reste':   round(max(du_hors - paye_hors, 0.0), 2),
    }

    return {
        'lignes':          sortie,
        'hors_mensualite': hors,
        'totaux': {
            'du':    round(du_hors + sum(l['du'] for l in sortie), 2),
            'paye':  round(paye_hors + sum(l['paye'] for l in sortie), 2),
            'reste': round(hors['reste'] + sum(l['reste'] for l in sortie), 2),
        },
    }
