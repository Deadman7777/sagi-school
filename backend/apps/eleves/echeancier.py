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

Les frais d'entrée (inscription pour un nouvel élève, renouvellement pour un
ancien quand l'école en pratique un), l'uniforme, les fournitures et les
services à paiement unique ne sont pas mensuels : ils forment une ligne « hors
mensualité » à part, sinon ils gonfleraient arbitrairement le mois où ils ont
été réglés. Cette ligne porte sa propre échéance : immédiate pour une
inscription, au mois fixé par l'école pour un renouvellement.

La dette des années antérieures (`reliquat_anterieur`) reste hors de cet
échéancier — elle a son propre suivi, et la mélanger ferait passer toute une
école migrée pour débitrice de l'année en cours.
"""
NOMS_MOIS = {1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
             5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
             9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'}

# Attribut où `precharger` dépose les paiements actifs d'un élève. Sa présence
# évite une requête par fiche : indispensable dès qu'on parcourt une école
# entière (tableau de bord, liste des élèves, campagne de rappels).
PREFETCH_PAIEMENTS = 'paiements_echeancier'


def precharger(qs):
    """Prépare un queryset d'élèves pour un parcours d'échéanciers.

    Sans cela, construire l'échéancier de 500 élèves fait plusieurs milliers
    de requêtes — le tableau de bord d'une école moyenne s'écroule. Quatre
    sources se cachaient derrière une simple boucle : les paiements, la prise
    en charge par un organisme (relue à chaque propriété qui la consulte), ce
    que l'organisme a versé, et le reliquat déjà encaissé.
    """
    from django.db.models import DecimalField, Prefetch, Q, Sum, Value
    from django.db.models.functions import Coalesce

    from apps.paiements.models import Paiement

    actif    = Q(paiements__statut='ACTIF')
    organism = actif & Q(paiements__organisme__isnull=False)

    # `tenant` : l'échéancier y lit le réglage d'exigibilité de chaque mois.
    return qs.select_related('tenant', 'section', 'exercice', 'classe').prefetch_related(
        'abonnements__service',
        # `pec_organisme` parcourt cette relation, et les propriétés qui en
        # dépendent l'appellent chacune à leur tour.
        'prises_en_charge_organisme__organisme',
        Prefetch('paiements',
                 queryset=Paiement.objects.filter(statut='ACTIF').only(
                     'eleve_id', 'montant_inscription', 'montant_mensualite',
                     'montant_uniforme', 'montant_fournitures', 'montant_cantine',
                     'montant_divers', 'mois_regles', 'services_regles'),
                 to_attr=PREFETCH_PAIEMENTS),
    ).annotate(
        # Noms attendus par les propriétés du modèle, qui les préfèrent à
        # leur propre requête.
        paye_organisme_sql=Coalesce(
            Sum('paiements__montant_inscription', filter=organism) +
            Sum('paiements__montant_mensualite',  filter=organism) +
            Sum('paiements__montant_uniforme',    filter=organism) +
            Sum('paiements__montant_fournitures', filter=organism) +
            Sum('paiements__montant_cantine',     filter=organism) +
            Sum('paiements__montant_divers',      filter=organism),
            Value(0), output_field=DecimalField()),
        reliquat_paye_sql=Coalesce(
            Sum('paiements__montant_reliquat', filter=actif),
            Value(0), output_field=DecimalField()),
    )


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


def _mois_precedent(annee, mois):
    return (annee - 1, 12) if mois == 1 else (annee, mois - 1)


def _dernier_jour(annee, mois):
    import calendar
    return calendar.monthrange(annee, mois)[1]


def date_exigibilite(tenant, annee, mois):
    """Date à partir de laquelle la mensualité d'un mois est réclamable.

    C'est LE réglage qui décide de ce qu'une famille voit comme « en retard ».
    Les écoles ne collectent pas au même moment :

      ANTICIPE   — on paie avant le mois. L'échéance tombe le mois PRÉCÉDENT
                   (Shoumoul : juillet se règle avant que juillet commence).
      DEBUT_MOIS — exigible dès le mois entamé. Comportement historique, et
                   défaut, pour qu'aucune école ne voie ses chiffres bouger
                   sans avoir touché au réglage.
      FIN_MOIS   — exigible une fois le mois consommé, donc le mois SUIVANT.

    Le jour est plafonné au dernier jour réel du mois : un 28 par défaut évite
    déjà le problème, mais une école qui saisit 28 en février doit obtenir le
    28 février, pas une erreur.
    """
    import datetime

    mode = getattr(tenant, 'echeance_mensualite', 'DEBUT_MOIS') or 'DEBUT_MOIS'
    jour = int(getattr(tenant, 'jour_echeance', 1) or 1)

    if mode == 'ANTICIPE':
        annee, mois = _mois_precedent(annee, mois)
    elif mode == 'FIN_MOIS':
        annee, mois = (annee + 1, 1) if mois == 12 else (annee, mois + 1)

    return datetime.date(annee, mois, min(jour, _dernier_jour(annee, mois)))


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
    # La synthèse est rendue quand même, à zéro : une absence de clé ferait
    # planter tout appelant qui lit la synthèse sans connaître ce cas.
    if eleve.fiche_creance or not eleve.exercice_id:
        return {'lignes': [], 'hors_mensualite': None,
                'totaux': {'du': 0.0, 'paye': 0.0, 'reste': 0.0},
                'synthese': {
                    'organisme_nom': '', 'part_organisme': 0.0,
                    'reste_organisme': 0.0, 'total_restant_du_famille': 0.0,
                    'retards': 0.0, 'retards_famille': 0.0,
                    'impaye_anterieur': 0.0, 'total_anterieurs': 0.0,
                    'total_exigible_famille': 0.0,
                    'mois_a_venir': 0.0, 'total_restant_du': 0.0}}

    exercice = eleve.exercice
    mois = mois_factures(eleve)
    svc_mensuel, svc_uniques = _services(eleve)

    # Le dû de chaque mois vient de la fiche : montant saisi s'il existe,
    # tarif ordinaire sinon. Une seule définition, partagée avec
    # total_attendu — sans quoi le détail contredirait son propre total.
    lignes = {m: {'mois': m, 'nom': NOMS_MOIS.get(m, str(m)),
                  'annee': _annee_du_mois(exercice, m),
                  'du': eleve.du_du_mois(m),
                  'montant_saisi': str(m) in (eleve.montants_mois or {}),
                  'paye': 0.0}
              for m in mois}

    # ── Hors mensualité : inscription et frais uniques ────────────────────
    du_hors = eleve.du_hors_mensualite

    paye_hors = 0.0
    non_imputes = 0.0     # mensualités payées sans mois désigné

    regles = getattr(eleve, PREFETCH_PAIEMENTS, None)
    if regles is None:
        regles = Paiement.objects.filter(
            tenant=eleve.tenant, exercice=exercice,
            eleve=eleve, statut='ACTIF').only(
            'montant_inscription', 'montant_mensualite', 'montant_uniforme',
            'montant_fournitures', 'montant_cantine', 'montant_divers',
            'mois_regles', 'services_regles')

    for p in regles:
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

    # Correction manuelle de l'école : elle FAIT FOI sur la répartition.
    # Son total est verrouillé côté API sur le montant réellement encaissé, donc
    # la somme des lignes continue d'égaler le total payé.
    manuelle = {int(k): float(v) for k, v in (eleve.imputation_mois or {}).items()
                if int(k) in lignes}
    if manuelle:
        for m in lignes:
            lignes[m]['paye'] = manuelle.get(m, 0.0)
        non_imputes = 0.0

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

    # Mois encaissés dès l'inscription : leur échéance est la date d'entrée de
    # l'élève, pas leur tour dans le calendrier. Une école qui prend la
    # dernière mensualité à l'inscription la réclame en septembre, pas en juin.
    tenant = eleve.tenant
    entree = eleve.date_entree or eleve.date_inscription or exercice.date_debut
    a_inscription = set()
    if mois:
        if getattr(tenant, 'premier_mois_a_inscription', False):
            a_inscription.add(mois[0])
        if getattr(tenant, 'dernier_mois_a_inscription', False):
            a_inscription.add(mois[-1])

    # L'horloge des retards S'ARRÊTE à la date de sortie : un élève parti en
    # mars ne doit pas voir ses arriérés grossir jusqu'en décembre. Sans ce
    # plafond, toute fiche d'abandon finit CRITIQUE et l'alerte ne veut plus
    # rien dire.
    reference = today
    if eleve.date_sortie and eleve.date_sortie < today:
        reference = eleve.date_sortie

    sortie = []
    for m in mois:
        ligne = lignes[m]
        paye = round(ligne['paye'], 2)
        reste = round(max(ligne['du'] - paye, 0.0), 2)
        exigible = (entree if m in a_inscription
                    else date_exigibilite(tenant, ligne['annee'], m))
        sortie.append({
            **ligne,
            'paye':       paye,
            'reste':      reste,
            'exigible_le': exigible,
            'a_inscription': m in a_inscription,
            'echu':       exigible <= reference,
            'statut': 'SOLDE' if reste <= 0 else ('PARTIEL' if paye > 0 else 'IMPAYE'),
        })

    paye_hors = round(min(paye_hors, du_hors) if du_hors else paye_hors, 2)
    # Un daara ouvre souvent sa campagne de renouvellement bien après la rentrée
    # (« à partir de janvier »). Avant ce mois, la somme est due mais pas encore
    # réclamable : la compter dans les retards ferait apparaître TOUS les anciens
    # élèves en défaut dès le premier jour de l'exercice, et la liste de relance
    # ne servirait plus à rien. L'inscription, elle, reste exigible à l'entrée.
    exigible_hors = None
    if eleve.renouvellement_du and tenant.mois_renouvellement:
        m = int(tenant.mois_renouvellement)
        exigible_hors = datetime.date(_annee_du_mois(exercice, m), m, 1)
    hors = {
        # Une CLÉ, pas un libellé : sinon la ligne serait en français dans un
        # tableau arabe (même règle que sante_migration).
        'cle':     'hors_mensualite',
        # Le nom que l'école donne à son renouvellement — une saisie libre, donc
        # intraduisible : elle prime sur la clé. VIDE hors renouvellement, pour
        # que « Inscription » reste traduit et n'apparaisse pas en français dans
        # un tableau arabe.
        'libelle': eleve.libelle_frais_entree if eleve.renouvellement_du else '',
        'du':      du_hors,
        'paye':    paye_hors,
        'reste':   round(max(du_hors - paye_hors, 0.0), 2),
        'exigible_le': exigible_hors,
        'echu':    exigible_hors is None or exigible_hors <= reference,
    }

    # ── Synthèse pour la famille ──────────────────────────────────────────
    # Ce qui est EXIGIBLE aujourd'hui, séparé de ce qui viendra à échéance :
    # un parent doit voir d'un coup d'œil ce qu'on lui réclame maintenant, et
    # ne pas le confondre avec le total de l'année. Les frais d'entrée suivent
    # leur propre échéance : dès l'entrée pour une inscription, au mois fixé par
    # l'école pour un renouvellement différé.
    retards = round((hors['reste'] if hors['echu'] else 0.0)
                    + sum(l['reste'] for l in sortie if l['echu']), 2)
    a_venir = round((0.0 if hors['echu'] else hors['reste'])
                    + sum(l['reste'] for l in sortie if not l['echu']), 2)
    anterieur = round(float(eleve.reliquat_restant or 0), 2)

    return {
        'lignes':          sortie,
        'hors_mensualite': hors,
        'totaux': {
            'du':    round(du_hors + sum(l['du'] for l in sortie), 2),
            'paye':  round(paye_hors + sum(l['paye'] for l in sortie), 2),
            'reste': round(hors['reste'] + sum(l['reste'] for l in sortie), 2),
        },
        'synthese': {
            # Part prise en charge par un organisme (bourse) : elle ne
            # disparaît pas du dû, elle change de débiteur. La distinguer est
            # indispensable dans un document remis aux parents — leur annoncer
            # la dette de l'État serait à la fois faux et blessant.
            'organisme_nom':      (eleve.pec_organisme.organisme.nom
                                   if eleve.pec_organisme else ''),
            'part_organisme':     eleve.part_organisme,
            'reste_organisme':    eleve.reste_organisme,
            # Ce que la FAMILLE devra sur l'année, ardoise comprise.
            'total_restant_du_famille': round(
                max(retards + anterieur + a_venir - eleve.reste_organisme, 0.0), 2),
            # Scolarité échue et non réglée, année en cours.
            'retards':            retards,
            # Les mêmes retards, nets de ce que l'organisme n'a pas encore
            # versé. C'est CE montant qui déclenche une relance : une famille
            # n'a pas à être appelée parce que l'État tarde à payer sa bourse.
            'retards_famille':    round(max(retards - eleve.reste_organisme, 0.0), 2),
            # Tout ce qui est exigible aujourd'hui de la FAMILLE, ardoise comprise.
            'total_exigible_famille': round(
                max(retards + anterieur - eleve.reste_organisme, 0.0), 2),
            # Ardoise des exercices antérieurs, nette de ce qui a déjà été réglé.
            'impaye_anterieur':   anterieur,
            # Tout ce qui est exigible aujourd'hui.
            'total_anterieurs':   round(retards + anterieur, 2),
            # Mensualités des mois non encore échus.
            'mois_a_venir':       a_venir,
            # Ce que la famille devra sur l'année entière, ardoise comprise.
            'total_restant_du':   round(retards + anterieur + a_venir, 2),
        },
    }


# ── Alerte de paiement ────────────────────────────────────────────────────
# Seuil en francs : sous 1 FCFA, c'est un arrondi, pas une dette. Sans lui, un
# centime résiduel ferait apparaître une famille soldée dans la liste d'appels.
SEUIL_ALERTE = 1.0

POIDS_ALERTE = {'CRITIQUE': 0, 'URGENT': 1, 'ATTENTION': 2, 'OK': 3, 'A_JOUR': 4}


def alerte_depuis_echeancier(ech):
    """Traduit un échéancier en alerte de relance.

    Rend {niveau, nb_mois, montant, mois} où `montant` est ce que la FAMILLE
    doit réellement aujourd'hui et `mois` les mois échus qu'elle n'a pas
    soldés — les vrais, pas les derniers du calendrier.

    Niveaux, inchangés :
      A_JOUR    rien d'exigible, rien à venir
      OK        à jour, mais il reste des mois non échus
      ATTENTION 1 mois de retard (ou des frais d'entrée impayés)
      URGENT    2 mois
      CRITIQUE  3 mois ou plus

    Une dette d'un exercice antérieur ne fixe pas le niveau — elle a son
    propre suivi — mais elle entre dans le montant réclamé, parce que c'est
    bien cette somme-là qu'on demande à la famille.
    """
    synth = ech['synthese']
    montant = synth['total_exigible_famille']
    if montant < SEUIL_ALERTE:
        # « OK » veut dire : rien d'exigible, mais la famille devra encore
        # quelque chose plus tard. Un boursier intégral, lui, ne devra jamais
        # rien — c'est A_JOUR, et le reste à venir appartient à l'organisme.
        return {'niveau': 'OK' if synth['total_restant_du_famille'] >= SEUIL_ALERTE
                          else 'A_JOUR',
                'nb_mois': 0, 'montant': 0.0, 'mois': []}

    impayes = [l for l in ech['lignes'] if l['echu'] and l['reste'] >= SEUIL_ALERTE]
    nb = len(impayes)
    if nb >= 3:
        niveau = 'CRITIQUE'
    elif nb == 2:
        niveau = 'URGENT'
    else:
        # nb == 0 : seuls l'inscription ou une ardoise restent dus. C'est
        # exigible, donc ça se signale — au niveau le plus bas.
        niveau = 'ATTENTION'
    return {'niveau': niveau, 'nb_mois': nb, 'montant': montant,
            'mois': [l['nom'] for l in impayes]}
