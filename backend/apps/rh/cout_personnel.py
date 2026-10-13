"""Coût annuel du personnel — ce que l'exercice coûte à l'établissement en
salaires et charges patronales, pour les dirigeants.

Un seul calendrier : celui de la paie (`mois_de_paie`), le même que la dette
au personnel. Pour chaque employé et chaque mois où il est dans l'école :
  - un bulletin VALIDÉ ou PAYÉ existe → son coût employeur réel (RÉALISÉ) ;
  - sinon → le bulletin que donnerait sa fiche (base + sursalaire + transport),
    calculé par PaieCalculateur, charges patronales comprises (PRÉVU).
Le coût annuel est la somme des deux : il reste juste en cours d'année, et
devient entièrement réalisé quand tous les bulletins sont validés.
"""
from decimal import Decimal

from .dette_personnel import _present, exercice_courant, mois_de_paie


def _f(v):
    return round(float(v or 0), 2)


def cout_annuel(tenant, exercice=None):
    from .models import BulletinPaie, Employe
    from .services import PaieCalculateur

    exercice = exercice or exercice_courant(tenant)
    calendrier = mois_de_paie(exercice) if exercice else []
    vide = {'brut': 0.0, 'charges_patronales': 0.0, 'cout_total': 0.0,
            'realise': 0.0, 'prevu': 0.0}
    if not calendrier:
        return {'exercice': None, 'nb_mois': 0, 'lignes': [], 'totaux': dict(vide, nb_employes=0)}

    bulletins = {}
    for b in (BulletinPaie.objects
              .filter(tenant=tenant, statut__in=('VALIDE', 'PAYE'))
              .only('employe_id', 'mois', 'annee', 'salaire_brut',
                    'total_charges_patronales', 'cout_total_employeur')):
        bulletins[(b.employe_id, b.annee, b.mois)] = b

    lignes = []
    for e in Employe.objects.filter(tenant=tenant).select_related('tenant'):
        mois = [(a, m) for a, m in calendrier if _present(e, a, m)]
        if not mois:
            continue
        brut = charges = realise = prevu = Decimal('0')
        nb_realises = 0
        projection = None
        for a, m in mois:
            b = bulletins.get((e.id, a, m))
            if b:
                brut += b.salaire_brut
                charges += b.total_charges_patronales
                realise += b.cout_total_employeur
                nb_realises += 1
                continue
            if projection is None:
                # Le même pour chaque mois restant : la fiche ne change pas
                # d'un mois à l'autre. Aucune avance (avance_ids=[]) : une
                # avance ne coûte rien de plus, elle est retenue sur le net.
                try:
                    projection = PaieCalculateur.calculer_bulletin(
                        e, m, a, sursalaire=e.sursalaire,
                        prime_transport=e.prime_transport, avance_ids=[])
                except ValueError:
                    projection = {}
            if projection:
                brut += projection['salaire_brut']
                charges += projection['total_charges_patronales']
                prevu += projection['cout_total_employeur']
        cout = realise + prevu
        if cout <= 0:
            continue
        lignes.append({
            'id': str(e.id), 'matricule': e.matricule, 'nom_complet': e.nom_complet,
            'poste': e.poste, 'type_employe': e.type_employe, 'statut': e.statut,
            'mensuel_fiche': _f(e.salaire_base + e.sursalaire + e.prime_transport),
            'nb_mois': len(mois), 'nb_mois_realises': nb_realises,
            'brut': _f(brut), 'charges_patronales': _f(charges),
            'realise': _f(realise), 'prevu': _f(prevu), 'cout_total': _f(cout),
        })

    totaux = {k: round(sum(l[k] for l in lignes), 2) for k in vide}
    totaux['nb_employes'] = len(lignes)
    return {
        'exercice': exercice.annee_scolaire,
        'nb_mois': len(calendrier),
        'premier_mois': '%02d/%d' % (calendrier[0][1], calendrier[0][0]),
        'dernier_mois': '%02d/%d' % (calendrier[-1][1], calendrier[-1][0]),
        'lignes': lignes,
        'totaux': totaux,
    }
