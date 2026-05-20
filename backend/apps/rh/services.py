"""
Service de calcul de paie SYSCOHADA — Convention Collective Enseignement Privé Sénégal (2018).
"""
from decimal import Decimal, ROUND_HALF_UP
import datetime


# Convention collective : seuils et majorations heures sup par niveau
NIVEAUX_CONFIG = {
    'PRESCOLAIRE': {
        'max': 30,
        'paliers': [(31, 33, '0.15'), (34, 35, '0.30'), (36, None, '0.40')],
    },
    'ELEMENTAIRE': {
        'max': 30,
        'paliers': [(31, 33, '0.15'), (34, 35, '0.30'), (36, None, '0.40')],
    },
    'MOYEN': {
        'max': 22,
        'paliers': [(23, 23, '0.15'), (24, 24, '0.25'), (25, None, '0.40')],
    },
    'SECONDAIRE': {
        'max': 18,
        'paliers': [(19, 22, '0.15'), (23, 25, '0.25'), (26, None, '0.40')],
    },
    'SUPERIEUR': {
        'max': 18,
        'paliers': [(19, 22, '0.15'), (23, 25, '0.25'), (26, None, '0.40')],
    },
}

COMPTES_PAIEMENT = {
    'BANQUE':       '521',
    'WAVE':         '5521',
    'ORANGE_MONEY': '5522',
    'FREE_MONEY':   '5523',
    'WIZALL':       '5524',
    'CAISSE':       '571',
    'AUTRE':        '571',
}


def _d(v):
    return Decimal(str(v))


def _arrondi(v):
    return _d(v).quantize(Decimal('1'), rounding=ROUND_HALF_UP)


def _compte_paiement(mode):
    return COMPTES_PAIEMENT.get(mode, '571')


class PaieCalculateur:

    @staticmethod
    def calculer_heures_sup(salaire_base, nb_heures_effectuees, niveau_enseignement):
        """
        Retourne le montant mensuel des heures supplémentaires.
        nb_heures_effectuees : heures effectuées par semaine.
        Formule : nb_h_tier × (salaire_base / max_heures) × (1 + taux_majoration)
        Le facteur 4.33 (semaines/mois) s'annule entre taux_horaire et nb_heures mensuelles.
        """
        config = NIVEAUX_CONFIG.get(niveau_enseignement)
        if not config or nb_heures_effectuees <= config['max']:
            return Decimal('0')

        max_h = _d(config['max'])
        base  = _d(salaire_base)
        nh    = int(nb_heures_effectuees)
        montant = Decimal('0')

        for h_min, h_max, taux_str in config['paliers']:
            if nh < h_min:
                break
            h_upper = min(nh, h_max) if h_max is not None else nh
            nb_h    = _d(h_upper - h_min + 1)
            montant += nb_h * (base / max_h) * (1 + _d(taux_str))

        return _arrondi(montant)

    @staticmethod
    def calculer_ir(salaire_brut, nb_enfants, situation_matrimoniale, ipres_salarie, params):
        """
        Calcul IR mensuel retenu à la source (barème progressif annualisé).
        Abattement frais pro : 30 %.
        """
        brut    = _d(salaire_brut)
        ipres_s = _d(ipres_salarie)

        base_mensuelle = brut * _d('0.70') - ipres_s
        if base_mensuelle <= 0:
            return Decimal('0')

        base_annuelle = base_mensuelle * 12
        ir_brut = Decimal('0')

        for tranche in params.tranches_ir:
            t_min = _d(tranche['min'])
            t_max = _d(tranche['max']) if tranche['max'] is not None else None
            taux  = _d(tranche['taux']) / 100

            if base_annuelle <= t_min:
                break
            upper    = min(base_annuelle, t_max) if t_max is not None else base_annuelle
            ir_brut += (upper - t_min) * taux

        # Réduction charges de famille
        est_marie = situation_matrimoniale in ('MARIE', 'VEUF', 'DIVORCE')
        reduction = Decimal('0')
        if est_marie or nb_enfants >= 1:
            reduction = _d('100000')
            extra = nb_enfants if est_marie else max(0, nb_enfants - 1)
            reduction += _d(extra) * _d('50000')

        reduction = min(reduction, ir_brut * _d('0.5'))
        ir_annuel = max(ir_brut - reduction, Decimal('0'))
        return _arrondi(ir_annuel / 12)

    @classmethod
    def calculer_bulletin(cls, employe, mois, annee, nb_heures_effectuees=0, **kwargs):
        """
        Calcule toutes les lignes d'un bulletin de paie sans persister.
        Retourne un dict prêt à être passé à BulletinPaie(**data).
        """
        from .models import ParametresFiscaux, AvanceSalaire

        try:
            params = ParametresFiscaux.objects.get(annee=annee)
        except ParametresFiscaux.DoesNotExist:
            params = ParametresFiscaux.objects.order_by('-annee').first()
            if not params:
                raise ValueError(f"Aucun paramètre fiscal disponible pour {annee}. "
                                 "Lancez : python manage.py init_parametres_fiscaux")

        base = _d(employe.salaire_base)

        heures_sup = cls.calculer_heures_sup(
            base, nb_heures_effectuees, employe.niveau_enseignement
        ) if nb_heures_effectuees else Decimal('0')

        indemnite_sujetion  = _d(kwargs.get('indemnite_sujetion', 0))
        indemnite_logement  = _d(kwargs.get('indemnite_logement', 0))
        primes_diverses     = _d(kwargs.get('primes_diverses', 0))
        avantages_nature    = _d(kwargs.get('avantages_nature', 0))
        opposition_saisie   = _d(kwargs.get('opposition_saisie', 0))
        autres_retenues_ext = _d(kwargs.get('autres_retenues', 0))
        mode_pmt            = kwargs.get('mode_paiement_effectif', employe.mode_paiement)

        # Allocation salaire unique
        est_marie = employe.situation_matrimoniale in ('MARIE', 'VEUF', 'DIVORCE')
        if est_marie or employe.nb_enfants >= 1:
            alloc = params.allocation_salaire_unique_base
            alloc += _d(employe.nb_enfants) * params.allocation_par_enfant
            alloc = min(alloc, params.plafond_allocation)
        else:
            alloc = Decimal('0')

        prime_transport = params.prime_transport

        salaire_brut = (
            base + heures_sup + indemnite_sujetion + indemnite_logement
            + alloc + prime_transport + primes_diverses + avantages_nature
        )

        # IPRES général
        base_ipres_g      = min(salaire_brut, params.plafond_ipres_general)
        ipres_g_sal       = _arrondi(base_ipres_g * params.taux_ipres_general_salarie / 100)
        ipres_g_pat       = _arrondi(base_ipres_g * params.taux_ipres_general_patronal / 100)

        # IPRES cadre
        ipres_c_sal = ipres_c_pat = Decimal('0')
        if employe.est_cadre:
            base_ipres_c = min(salaire_brut, params.plafond_ipres_cadre)
            ipres_c_sal  = _arrondi(base_ipres_c * params.taux_ipres_cadre_salarie / 100)
            ipres_c_pat  = _arrondi(base_ipres_c * params.taux_ipres_cadre_patronal / 100)

        ipres_salarie_total = ipres_g_sal + ipres_c_sal

        ir = cls.calculer_ir(
            salaire_brut, employe.nb_enfants, employe.situation_matrimoniale,
            ipres_salarie_total, params
        )

        # Avances à imputer
        avance_ids = kwargs.get('avance_ids', [])
        avances_qs = AvanceSalaire.objects.filter(
            tenant=employe.tenant, employe=employe, statut='EN_ATTENTE'
        )
        if avance_ids:
            avances_qs = avances_qs.filter(id__in=avance_ids)
        elif not kwargs.get('inclure_avances', False):
            avances_qs = avances_qs.none()

        avance_montant = sum((_d(a.montant) for a in avances_qs), Decimal('0'))

        total_retenues = (
            ipres_g_sal + ipres_c_sal + ir
            + avance_montant + opposition_saisie + autres_retenues_ext
        )

        # Charges patronales
        base_css = min(salaire_brut, params.plafond_css)
        css  = _arrondi(base_css * params.taux_css_prestations_familiales / 100)
        atmp = _arrondi(base_css * params.taux_atmp / 100)
        cfce = _arrondi(salaire_brut * params.taux_cfce / 100)
        total_charges_pat = ipres_g_pat + ipres_c_pat + css + atmp + cfce

        net_a_payer  = salaire_brut - total_retenues
        cout_total   = salaire_brut + total_charges_pat

        return {
            'parametres_fiscaux':          params,
            'mois':                        mois,
            'annee':                       annee,
            # gains
            'salaire_base':                base,
            'nb_heures_sup':               _d(nb_heures_effectuees),
            'heures_sup_montant':          heures_sup,
            'indemnite_sujetion':          indemnite_sujetion,
            'indemnite_logement':          indemnite_logement,
            'allocation_salaire_unique':   alloc,
            'prime_transport':             prime_transport,
            'primes_diverses':             primes_diverses,
            'avantages_nature':            avantages_nature,
            'salaire_brut':                salaire_brut,
            # retenues
            'ipres_general_salarie':       ipres_g_sal,
            'ipres_cadre_salarie':         ipres_c_sal,
            'ir_retenu':                   ir,
            'avance_sur_salaire':          avance_montant,
            'opposition_saisie':           opposition_saisie,
            'autres_retenues':             autres_retenues_ext,
            'total_retenues_salariales':   total_retenues,
            # charges patronales
            'ipres_general_patronal':      ipres_g_pat,
            'ipres_cadre_patronal':        ipres_c_pat,
            'css_prestations_familiales':  css,
            'atmp':                        atmp,
            'cfce':                        cfce,
            'total_charges_patronales':    total_charges_pat,
            # résultat
            'net_a_payer':                 net_a_payer,
            'cout_total_employeur':        cout_total,
            'mode_paiement_effectif':      mode_pmt,
            # interne
            '_avances_qs':                 avances_qs,
        }

    @classmethod
    def creer_bulletin(cls, employe, mois, annee, nb_heures_effectuees=0, **kwargs):
        from .models import BulletinPaie
        data = cls.calculer_bulletin(employe, mois, annee, nb_heures_effectuees, **kwargs)
        avances_qs = data.pop('_avances_qs')
        bulletin = BulletinPaie.objects.create(
            tenant=employe.tenant,
            employe=employe,
            **data,
        )
        if avances_qs.exists():
            bulletin.avances.set(avances_qs)
        return bulletin


def generer_ecriture_avance(avance, tenant):
    """Comptabilise le décaissement d'une avance : D 421 / C compte_paiement."""
    from apps.comptabilite.models import JournalEntry
    from apps.paiements.models import Exercice

    exercice = Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()
    if not exercice:
        return

    ref   = avance.no_piece or f"AVA-{avance.employe.matricule}-{avance.id.hex[:6].upper()}"
    date  = avance.date_avance
    label = f"Avance sur salaire {avance.employe.nom_complet}"
    cpt   = _compte_paiement(avance.mode_paiement)

    JournalEntry.objects.bulk_create([
        JournalEntry(
            tenant=tenant, exercice=exercice, no_piece=ref, date_ecriture=date,
            no_compte='421', libelle=label,
            debit=avance.montant, credit=0,
            source='AVANCE', source_id=avance.id, ordre=1,
        ),
        JournalEntry(
            tenant=tenant, exercice=exercice, no_piece=ref, date_ecriture=date,
            no_compte=cpt, libelle=label,
            debit=0, credit=avance.montant,
            source='AVANCE', source_id=avance.id, ordre=2,
        ),
    ])


def generer_ecritures_paie(bulletin, tenant):
    """Génère les écritures SYSCOHADA complètes lors de la validation du bulletin."""
    from apps.comptabilite.models import JournalEntry
    from apps.paiements.models import Exercice

    exercice = Exercice.objects.filter(tenant=tenant, cloture=False).order_by('-date_debut').first()
    if not exercice:
        return

    ref   = f"PAIE-{bulletin.employe.matricule}-{bulletin.mois:02d}/{bulletin.annee}"
    date  = datetime.date(bulletin.annee, bulletin.mois, 1)
    emp   = bulletin.employe.nom_complet
    sid   = bulletin.id
    ordre = [0]

    def entry(compte, libelle, debit=Decimal('0'), credit=Decimal('0')):
        ordre[0] += 1
        return JournalEntry(
            tenant=tenant, exercice=exercice,
            no_piece=ref, date_ecriture=date,
            no_compte=compte, libelle=libelle,
            debit=_d(debit), credit=_d(credit),
            source='PAIE', source_id=sid, ordre=ordre[0],
        )

    rows = []

    # — Étape 1 : salaire brut —
    rows += [
        entry('661', f"Salaires {emp} {bulletin.mois:02d}/{bulletin.annee}", debit=bulletin.salaire_brut),
        entry('422', f"Rémunération due {emp} {bulletin.mois:02d}/{bulletin.annee}", credit=bulletin.salaire_brut),
    ]

    # — Étape 2 : retenues salariales —
    ipres_sal = _d(bulletin.ipres_general_salarie) + _d(bulletin.ipres_cadre_salarie)
    if ipres_sal > 0:
        rows += [
            entry('422', f"IPRES salarié {emp}", debit=ipres_sal),
            entry('4313', f"IPRES salarié {emp}", credit=ipres_sal),
        ]

    if _d(bulletin.ir_retenu) > 0:
        rows += [
            entry('422', f"IR retenu {emp}", debit=bulletin.ir_retenu),
            entry('4472', f"IR retenu {emp}", credit=bulletin.ir_retenu),
        ]

    if _d(bulletin.avance_sur_salaire) > 0:
        rows += [
            entry('422', f"Apurement avance {emp}", debit=bulletin.avance_sur_salaire),
            entry('421', f"Apurement avance {emp}", credit=bulletin.avance_sur_salaire),
        ]

    if _d(bulletin.opposition_saisie) > 0:
        rows += [
            entry('422', f"Opposition/saisie {emp}", debit=bulletin.opposition_saisie),
            entry('423', f"Opposition/saisie {emp}", credit=bulletin.opposition_saisie),
        ]

    # — Étape 3 : charges patronales —
    ipres_pat = _d(bulletin.ipres_general_patronal) + _d(bulletin.ipres_cadre_patronal)
    if ipres_pat > 0:
        rows += [
            entry('6641', f"IPRES patronal {emp}", debit=ipres_pat),
            entry('4313', f"IPRES patronal {emp}", credit=ipres_pat),
        ]

    if _d(bulletin.css_prestations_familiales) > 0:
        rows += [
            entry('6641', f"CSS prestations fam. {emp}", debit=bulletin.css_prestations_familiales),
            entry('4311', f"CSS prestations fam. {emp}", credit=bulletin.css_prestations_familiales),
        ]

    if _d(bulletin.atmp) > 0:
        rows += [
            entry('6641', f"ATMP {emp}", debit=bulletin.atmp),
            entry('4312', f"ATMP {emp}", credit=bulletin.atmp),
        ]

    if _d(bulletin.cfce) > 0:
        rows += [
            entry('6413', f"CFCE {emp}", debit=bulletin.cfce),
            entry('4421', f"CFCE {emp}", credit=bulletin.cfce),
        ]

    # — Étape 4 : net à payer —
    cpt = _compte_paiement(bulletin.mode_paiement_effectif)
    rows += [
        entry('422', f"Net à payer {emp} {bulletin.mois:02d}/{bulletin.annee}", debit=bulletin.net_a_payer),
        entry(cpt,   f"Paiement salaire {emp} {bulletin.mois:02d}/{bulletin.annee}", credit=bulletin.net_a_payer),
    ]

    JournalEntry.objects.bulk_create(rows)

    # Marquer les avances comme imputées
    bulletin.avances.filter(statut='EN_ATTENTE').update(statut='IMPUTE')
