"""Garde du soir : l'enfant récupéré après l'heure limite est facturé.

Règle d'une école (sept. 2026) : récupération jusqu'à 17h30, tolérance jusqu'à
17h45. À partir de 17h45, chaque tranche entamée est due au tarif (1 000 F) :
la première va de l'heure limite à l'heure pleine suivante (17h30 → 18h00), les
suivantes suivent l'horloge (18h00 → 19h00, 19h00 → 20h00…).

    départ 17h40 → toléré ; 17h45–18h00 → 1 tranche ; 18h01–19h00 → 2 ; 19h01–20h00 → 3.

Heures et tarif sont réglés par l'école (Tenant.garde_soir_*). Le dû naît de
la saisie et s'ajoute au mois où il tombe (`Eleve.du_du_mois`) : fiche,
guichet, alertes et cahier mensuel le lisent sans calcul à part.
"""
import datetime
import math
from collections import defaultdict
from decimal import Decimal

from .models import Eleve, GardeSoir

PREFETCH_GARDES = 'gardes_soir_echeancier'


class GardeSoirErreur(ValueError):
    """Opération refusée, avec un message destiné à l'utilisateur."""


def _minutes(heure):
    return heure.hour * 60 + heure.minute


def tranches_dues(depart, limite, facturation_a):
    """Nombre de tranches dues pour un départ à `depart` (0 si toléré)."""
    if _minutes(depart) < _minutes(facturation_a) or _minutes(depart) <= _minutes(limite):
        return 0
    premiere_fin = (limite.hour + 1) * 60          # heure pleine qui suit la limite
    if _minutes(depart) <= premiere_fin:
        return 1
    return 1 + math.ceil((_minutes(depart) - premiere_fin) / 60)


def _gardes(eleve):
    cache = getattr(eleve, PREFETCH_GARDES, None)
    if cache is not None:
        return cache
    if not eleve.pk:
        return []
    return list(GardeSoir.objects.filter(tenant_id=eleve.tenant_id, eleve=eleve)
                .only('date', 'heure_depart', 'tranches', 'montant'))


def _par_mois(eleve):
    cache = getattr(eleve, '_garde_soir_par_mois', None)
    if cache is None:
        cache = defaultdict(list)
        for g in _gardes(eleve):
            cache[g.date.month].append(g)
        eleve._garde_soir_par_mois = cache
    return cache


def _du_mois(eleve, mois):
    from .echeancier import _annee_du_mois
    soirs = _par_mois(eleve).get(int(mois), [])
    if eleve.exercice_id:
        annee = _annee_du_mois(eleve.exercice, int(mois))
        soirs = [g for g in soirs if g.date.year == annee]
    return soirs


def du_garde_soir_du_mois(eleve, mois):
    return float(sum((g.montant for g in _du_mois(eleve, mois)), Decimal('0')))


def mois_avec_garde_soir(eleve):
    return sorted(m for m, soirs in _par_mois(eleve).items() if soirs)


def detail_du_mois(eleve, mois):
    soirs = sorted(_du_mois(eleve, mois), key=lambda g: g.date)
    return {'nb_soirs': len(soirs), 'tranches': sum(g.tranches for g in soirs),
            'montant': float(sum((g.montant for g in soirs), Decimal('0')))}


def reglages(tenant):
    return {'actif': tenant.garde_soir_actif, 'limite': tenant.garde_soir_heure_limite,
            'facturation_a': tenant.garde_soir_facturation_a, 'tarif': float(tenant.garde_soir_tarif)}


def _exercice(tenant):
    from .garderie import exercice_courant
    return exercice_courant(tenant)


def _verifier_jour(exercice, jour):
    if exercice is None:
        raise GardeSoirErreur("Aucun exercice ouvert.")
    if jour > datetime.date.today():
        raise GardeSoirErreur("On ne saisit pas un soir à venir.")
    if not exercice.date_debut <= jour <= exercice.date_fin:
        raise GardeSoirErreur(f"Le {jour:%d/%m/%Y} est hors de l'année scolaire {exercice.annee_scolaire}.")


def enregistrer(tenant, eleve_id, jour, depart, auteur=''):
    """Enregistre (ou corrige) l'heure de départ d'un enfant ce soir-là."""
    if not tenant.garde_soir_actif:
        raise GardeSoirErreur("La garde du soir n'est pas activée (Paramètres → École).")
    exercice = _exercice(tenant)
    _verifier_jour(exercice, jour)
    from .parcours import eleves_presents
    eleve = eleves_presents(Eleve.objects.filter(tenant=tenant, exercice=exercice, pk=eleve_id)).first()
    if eleve is None:
        raise GardeSoirErreur("Élève introuvable parmi les inscrits de l'année.")
    n = tranches_dues(depart, tenant.garde_soir_heure_limite, tenant.garde_soir_facturation_a)
    if n == 0:
        GardeSoir.objects.filter(tenant=tenant, eleve=eleve, date=jour).delete()
        raise GardeSoirErreur(
            f"Départ à {depart:%H:%M} : dans la tolérance (facturation à partir de "
            f"{tenant.garde_soir_facturation_a:%H:%M}), rien à facturer.")
    garde, _ = GardeSoir.objects.update_or_create(
        tenant=tenant, eleve=eleve, date=jour,
        defaults={'heure_depart': depart, 'tranches': n, 'montant': tenant.garde_soir_tarif * n,
                  'saisi_par': auteur})
    return garde


def soirs_du_jour(tenant, jour):
    return [{'id': str(g.id), 'eleve': str(g.eleve_id), 'nom_complet': g.eleve.nom_complet,
             'classe': g.eleve.classe.nom if g.eleve.classe_id else (g.eleve.section.nom if g.eleve.section_id else ''),
             'heure_depart': g.heure_depart.strftime('%H:%M'), 'tranches': g.tranches, 'montant': float(g.montant)}
            for g in GardeSoir.objects.filter(tenant=tenant, date=jour)
            .select_related('eleve__classe', 'eleve__section').order_by('heure_depart')]


def recap_du_mois(tenant, mois):
    """Par enfant : soirs, tranches et montant du mois, et ce qui reste dû.

    Le reste vient de l'échéancier, la même source que la fiche et le guichet :
    l'école encaisse sur place, elle doit voir ici ce qu'il reste à prendre.
    """
    from .echeancier import construire_echeancier
    from .tri import cle_nom
    exercice = _exercice(tenant)
    if exercice is None:
        raise GardeSoirErreur("Aucun exercice ouvert.")
    from .echeancier import _annee_du_mois
    annee = _annee_du_mois(exercice, int(mois))
    lignes = defaultdict(lambda: {'nb_soirs': 0, 'tranches': 0, 'montant': 0.0})
    noms = {}
    for g in (GardeSoir.objects.filter(tenant=tenant, eleve__exercice=exercice, date__year=annee, date__month=mois)
              .select_related('eleve')):
        l = lignes[g.eleve_id]
        l['nb_soirs'] += 1
        l['tranches'] += g.tranches
        l['montant'] += float(g.montant)
        noms[g.eleve_id] = g.eleve.nom_complet
    enfants = []
    for eid, valeurs in lignes.items():
        eleve = Eleve.objects.select_related('section', 'exercice', 'tenant', 'classe').get(pk=eid)
        ligne = next((l for l in construire_echeancier(eleve)['lignes'] if l['mois'] == int(mois)), None)
        enfants.append({'eleve': str(eid), 'nom_complet': noms[eid], **valeurs,
                        'du_mois': ligne['du'] if ligne else 0.0,
                        'paye_mois': ligne['paye'] if ligne else 0.0,
                        'reste_mois': ligne['reste'] if ligne else 0.0})
    enfants.sort(key=lambda x: cle_nom(x['nom_complet']))
    return {'mois': int(mois), 'enfants': enfants,
            'total': round(sum(e['montant'] for e in enfants), 2),
            'total_reste': round(sum(e['reste_mois'] for e in enfants), 2)}
