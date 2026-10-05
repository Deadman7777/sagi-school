"""Moteur des obligations fiscales de l'établissement.

Pour chaque obligation décrite en base (models.ObligationFiscale) :
  1. applicable ? — selon le profil fiscal (forme, statut, régime, but
     lucratif, TVA, locaux, employeur) ;
  2. exonérée ? — exonération du profil couvrant la date de clôture ;
  3. combien ? — selon sa formule, avec les paramètres en vigueur à la date
     de clôture de l'exercice (un exercice passé garde les taux de son temps).

La sortie garde la forme historique de l'écran Fiscal (code, libellé,
description, base, taux, montant, périodicité, échéance, statut,
comptabilisable, déjà comptabilisé, comptes), enrichie de la référence
légale, du drapeau « à vérifier » et du motif d'exonération.
"""
import datetime

from django.db.models import Sum

from .models import ObligationFiscale, ProfilFiscal
from .parametres import parametre, valeur_parametre


def profil_de(tenant):
    """Le profil fiscal de l'école (créé au premier appel, valeurs par défaut :
    établissement privé à but lucratif, régime réel — le comportement d'avant
    le profil)."""
    profil, _ = ProfilFiscal.objects.get_or_create(tenant=tenant)
    return profil


def _employeur(tenant, donnees):
    return donnees.get('masse_salariale', 0) > 0


def applicable(obligation, profil, donnees):
    c = obligation.conditions or {}
    if c.get('formes') and profil.forme_juridique not in c['formes']:
        return False
    if profil.forme_juridique in c.get('exclure_formes', []):
        return False
    if c.get('regimes') and profil.regime not in c['regimes']:
        return False
    if profil.regime in c.get('exclure_regimes', []):
        return False
    if c.get('statuts') and profil.statut not in c['statuts']:
        return False
    for cle in ('but_lucratif', 'assujetti_tva', 'proprietaire_locaux'):
        if cle in c and bool(getattr(profil, cle)) != bool(c[cle]):
            return False
    if c.get('employeur') and not _employeur(profil.tenant, donnees):
        return False
    return True


def exoneration(obligation, profil, date):
    """L'exonération du profil qui couvre cette obligation à cette date, ou None."""
    for e in profil.exonerations or []:
        if (e.get('obligation') or '').upper() != obligation.code:
            continue
        debut = e.get('date_debut')
        fin = e.get('date_fin')
        if debut and str(date) < str(debut):
            continue
        if fin and str(date) > str(fin):
            continue
        return e
    return None


def _taux_lisible(valeur):
    return f"{valeur:g} %".replace('.', ',')


def _fcfa(x):
    return f"{x:,.0f}".replace(',', ' ')


def _tva_nette(tenant, exercice):
    from apps.comptabilite.models import JournalEntry
    j = JournalEntry.objects.filter(tenant=tenant, exercice=exercice)
    col = j.filter(no_compte__startswith='443').aggregate(d=Sum('debit'), c=Sum('credit'))
    ded = j.filter(no_compte__startswith='445').aggregate(d=Sum('debit'), c=Sum('credit'))
    collectee = float(col['c'] or 0) - float(col['d'] or 0)
    deductible = float(ded['d'] or 0) - float(ded['c'] or 0)
    return collectee, deductible


def calculer(tenant, exercice, donnees, deja_comptabilise):
    """Liste des obligations, au format de l'écran Fiscal."""
    profil = profil_de(tenant)
    date = exercice.date_fin
    produits, resultat = donnees['produits'], donnees['resultat']
    sortie = []
    for ob in ObligationFiscale.objects.filter(actif=True):
        p = ob.parametres or {}

        def val(cle, defaut=None):
            return valeur_parametre(p[cle], tenant, date, defaut) if cle in p else defaut

        refs = [parametre(code, tenant, date) for code in p.values()]
        a_verifier = ob.a_verifier or any(r is not None and r.a_verifier for r in refs)
        ligne = {
            'code': ob.code, 'libelle': ob.libelle, 'description': ob.description,
            'base': None, 'taux': '—', 'montant': None, 'periodicite': ob.periodicite or '—',
            'echeance': ob.echeance or '—', 'statut': 'INFO', 'comptabilisable': False,
            'deja_comptabilise': deja_comptabilise(ob.code) if ob.compte_debit else 0,
            'comptes': ({'debit': ob.compte_debit, 'credit': ob.compte_credit, 'libelle': ob.libelle}
                        if ob.compte_debit else None),
            'reference': ob.reference, 'a_verifier': a_verifier, 'exoneration': None,
        }
        if not applicable(ob, profil, donnees):
            ligne.update(statut='NON_APPLICABLE', montant=0,
                         description=ob.message_non_applicable or ob.description)
            # Historique : la TVA s'affichait « exonérée » pour l'enseignement.
            if ob.code == 'TVA':
                ligne.update(statut='EXONERE', taux=f"Exonéré ({_taux_lisible(val('taux', 18))} sur activités taxables)")
            sortie.append(ligne)
            continue
        exo = exoneration(ob, profil, date)
        if exo is not None:
            ligne.update(statut='EXONERE', montant=0, exoneration=exo,
                         description=f"Exonéré : {exo.get('motif', '')}"
                                     + (f" ({exo['reference']})" if exo.get('reference') else ''))
            sortie.append(ligne)
            continue

        f = ob.formule
        if f == 'IS_IMF':
            taux = float(val('taux', 30))
            imf_t = float(val('minimum_taux', 0.5))
            plancher = float(val('minimum_plancher', 500000))
            plafond = float(val('minimum_plafond', 5000000))
            is_calc = round(max(0.0, resultat) * taux / 100, 0)
            imf = round(min(max(produits * imf_t / 100, plancher), plafond), 0) if produits > 0 else plancher
            du = max(is_calc, imf)
            ligne.update(
                base=resultat if is_calc >= imf else produits, montant=du, statut='ESTIMATION',
                comptabilisable=True, taux=f"{_taux_lisible(taux)} (ou IMF {_taux_lisible(imf_t)})",
                description=(f"IS {_taux_lisible(taux)} du résultat estimé ({_fcfa(resultat)} FCFA) = "
                             f"{_fcfa(is_calc)} FCFA ; minimum forfaitaire ({_taux_lisible(imf_t)} des "
                             f"produits, plancher {_fcfa(plancher)}, plafond {_fcfa(plafond)}) = "
                             f"{_fcfa(imf)} FCFA. Le montant dû est le plus élevé des deux."))
        elif f == 'MASSE_SALARIALE':
            taux = float(val('taux', 3))
            bulletins = donnees.get('source_paie') == 'BULLETINS'
            montant = donnees['cfce'] if bulletins else round(donnees['masse_salariale'] * taux / 100, 2)
            ligne.update(base=donnees['masse_salariale'], taux=_taux_lisible(taux), montant=montant,
                         statut='BULLETINS' if bulletins else 'ESTIMATION',
                         comptabilisable=not bulletins,
                         description=ob.description + ('' if bulletins else
                                                       " Validez les bulletins de paie (module RH) pour des montants réels."))
        elif f == 'TVA':
            collectee, deductible = _tva_nette(tenant, exercice)
            ligne.update(base=collectee, taux=_taux_lisible(float(val('taux', 18))),
                         montant=round(max(collectee - deductible, 0), 0), statut='ESTIMATION',
                         description=f"TVA facturée {_fcfa(collectee)} − TVA déductible "
                                     f"{_fcfa(deductible)} FCFA sur l'exercice. {ob.description}")
        elif f == 'SAISIE':
            ligne.update(statut='A_SAISIR', comptabilisable=bool(ob.compte_debit),
                         taux='Selon avis d’imposition')
        elif f == 'RH':
            ligne.update(base=donnees['masse_salariale'], statut='GERE_PAR_RH',
                         taux='Barème IR / taux IPRES-CSS')
        elif f == 'TAUX':
            taux = float(val('taux', 0))
            base = produits if ob.base == 'PRODUITS' else resultat if ob.base == 'RESULTAT' \
                else donnees.get('masse_salariale', 0)
            ligne.update(base=base, taux=_taux_lisible(taux), montant=round(base * taux / 100, 0),
                         statut='ESTIMATION', comptabilisable=bool(ob.compte_debit))
        else:                                         # INFO
            if 'taux' in p:
                ligne['taux'] = _taux_lisible(float(val('taux', 0)))
        sortie.append(ligne)
    return sortie


def comptes_obligation(code):
    ob = ObligationFiscale.objects.filter(code=code.upper(), actif=True).first()
    if ob is None or not ob.compte_debit:
        return None
    return {'debit': ob.compte_debit, 'credit': ob.compte_credit, 'libelle': ob.libelle}
