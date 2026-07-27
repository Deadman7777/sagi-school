"""Santé de la migration — état de complétude des données reprises.

Une migration ne se termine pas le jour de l'installation : l'école arrive
avec ce qu'elle a, et complète ensuite. Encore faut-il qu'elle sache ce qui
reste à compléter, sinon les trous se découvrent six mois plus tard, au
moment d'éditer un bilan.

Ce module ne corrige rien : il compte, et dit où aller. Chaque contrôle rend
une clé (le front l'habille dans la langue de l'utilisateur), un décompte, et
un niveau :

    ok        rien à faire
    info      normal en début d'année, à surveiller
    attention à traiter avant de s'appuyer sur les chiffres

Il n'y a délibérément AUCUN niveau bloquant : rien ici n'empêche de
travailler, c'est une liste de courses, pas un barrage.
"""
import re

from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce

from .models import Eleve, Section

# Matricule au format promo : AAAA-CODE-NNNN (voir matricules.py)
FORMAT_PROMO = re.compile(r'^\d{4}-[A-Z0-9]+-\d+$')


def _controle(cle, niveau, nb, total=None, montant=None):
    return {'cle': cle, 'niveau': niveau, 'nb': nb,
            'total': total, 'montant': montant}


def diagnostiquer(tenant, exercice):
    """Rend {'exercice', 'nb_eleves', 'controles': [...], 'nb_a_traiter'}."""
    from apps.comptabilite.models import JournalEntry

    def zero(expr):
        return Coalesce(expr, Value(0), output_field=DecimalField())

    actif = Q(paiements__statut='ACTIF')
    eleves = list(
        Eleve.objects.filter(tenant=tenant, exercice=exercice, fiche_creance=False)
        .select_related('section', 'exercice')
        .prefetch_related('abonnements__service')
        .annotate(
            nb_paiements=Count('paiements', filter=actif),
            total_paye_sql=zero(
                Sum('paiements__montant_inscription', filter=actif) +
                Sum('paiements__montant_mensualite',  filter=actif) +
                Sum('paiements__montant_uniforme',    filter=actif) +
                Sum('paiements__montant_fournitures', filter=actif) +
                Sum('paiements__montant_cantine',     filter=actif) +
                Sum('paiements__montant_divers',      filter=actif)),
            reliquat_paye_sql=zero(Sum('paiements__montant_reliquat', filter=actif)),
        ))
    total = len(eleves)
    controles = []

    # 1. Situation financière jamais décrite : ni encaissement, ni reprise, ni
    #    ardoise. En début d'année c'est normal ; sur une école migrée en cours
    #    d'année, ce sont les élèves dont on ne sait rien.
    sans_situation = sum(1 for e in eleves
                         if not e.nb_paiements and not float(e.reliquat_anterieur or 0))
    controles.append(_controle(
        'situation_financiere', 'info' if sans_situation else 'ok',
        sans_situation, total))

    # 2. Ardoises des années d'avant déjà saisies.
    avec_ardoise = [e for e in eleves if float(e.reliquat_anterieur or 0) > 0]
    controles.append(_controle(
        'impayes_anterieurs', 'ok', len(avec_ardoise), total,
        montant=round(sum(float(e.reliquat_anterieur) for e in avec_ardoise), 2)))

    # 3. Identité d'entrée incomplète → il reste à passer rebaser_matricules.
    sans_entree = sum(1 for e in eleves
                      if not e.annee_entree or not e.date_entree
                      or not FORMAT_PROMO.match(e.matricule or ''))
    controles.append(_controle(
        'identite_entree', 'attention' if sans_entree else 'ok', sans_entree, total))

    # 4. Sections sans tarif : tout élève qui y est rattaché doit 0 FCFA. Erreur
    #    de migration classique, et parfaitement silencieuse.
    sections_muettes = Section.objects.filter(
        tenant=tenant, frais_inscription=0, frais_mensualite=0,
        frais_uniforme=0, frais_fournitures=0)
    nb_sections_muettes = sections_muettes.count()
    eleves_sans_tarif = sum(1 for e in eleves if e.section and float(e.total_attendu) == 0)
    controles.append(_controle(
        'sections_sans_tarif', 'attention' if nb_sections_muettes else 'ok',
        nb_sections_muettes, Section.objects.filter(tenant=tenant).count()))

    # 5. Élèves sans section : leur dû ne peut pas être calculé du tout.
    sans_section = sum(1 for e in eleves if not e.section_id)
    controles.append(_controle(
        'sans_section', 'attention' if sans_section else 'ok', sans_section, total))

    # 6. Équilibre du journal — le contrôle comptable de base. Un écart signale
    #    une reprise ou un recalage qui a mal tourné.
    agg = JournalEntry.objects.filter(tenant=tenant, exercice=exercice).aggregate(
        d=Sum('debit'), c=Sum('credit'))
    ecart = round(float(agg['d'] or 0) - float(agg['c'] or 0), 2)
    controles.append(_controle(
        'journal_equilibre', 'attention' if abs(ecart) > 1 else 'ok',
        0, montant=abs(ecart)))

    # 7. Net des produits (classe 70) négatif — impossible comptablement, et
    #    parfaitement silencieux : le tableau de bord borne le total à 0 et
    #    affiche « Total Recettes : 0 » sans rien signaler. C'est resté invisible
    #    des mois chez Shoumoul, où des neutralisations de migration empilées
    #    débitaient 46 M contre 30 M de crédits.
    agg70 = JournalEntry.objects.filter(
        tenant=tenant, exercice=exercice, no_compte__startswith='70'
    ).aggregate(d=Sum('debit'), c=Sum('credit'))
    net70 = round(float(agg70['c'] or 0) - float(agg70['d'] or 0), 2)
    controles.append(_controle(
        'produits_negatifs', 'attention' if net70 < 0 else 'ok',
        0, montant=abs(net70) if net70 < 0 else 0))

    # Créances totales à recouvrer, fiches de créance des sortis comprises :
    # c'est l'argent réellement dû à l'école, tous élèves confondus.
    creances = 0.0
    for e in eleves:
        e._total_paye_cache = e.total_paye_sql
        creances += max(e.reste_a_payer_global, 0.0)
    for fiche in Eleve.objects.filter(tenant=tenant, exercice=exercice,
                                      fiche_creance=True).annotate(
            reliquat_paye_sql=zero(Sum('paiements__montant_reliquat', filter=actif))):
        creances += fiche.reliquat_restant

    return {
        'exercice':       exercice.annee_scolaire,
        'nb_eleves':      total,
        'nb_a_traiter':   sum(1 for c in controles if c['niveau'] == 'attention'),
        'eleves_sans_tarif': eleves_sans_tarif,
        'total_creances': round(creances, 2),
        'controles':      controles,
    }
