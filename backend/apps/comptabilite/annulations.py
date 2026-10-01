"""Paiements annulés : sans effet sur les comptes de synthèse.

Annuler un règlement passe une extourne (`ANNUL_PAIEMENT`) qui inverse les
écritures d'origine (`PAIEMENT`). Le solde de chaque compte revient à ce qu'il
était, mais les deux pièces restaient dans les cumuls : un reçu de 50 000
saisi puis annulé ajoutait 100 000 au débit ET au crédit du 411, du 706 et de
la caisse. La direction lisait un 411 « gonflé » par des opérations qui
n'ont jamais eu lieu.

Le grand livre et la balance écartent donc la paire entière. Le journal, lui,
la garde : c'est la trace de l'erreur et de sa correction.

On n'écarte une paire que si elle se compense EXACTEMENT, compte par compte,
dans l'exercice. Une extourne partielle, doublée ou passée sur un autre
exercice laisse un reste réel : elle reste visible, sinon le grand livre
cacherait un écart.
"""
from collections import defaultdict

from django.db.models import Sum

from .models import JournalEntry

SOURCES_PAIRE = ('PAIEMENT', 'ANNUL_PAIEMENT')


def paiements_annules_compenses(tenant, exercice):
    """Ids des paiements dont l'écriture et l'extourne s'annulent dans l'exercice."""
    annules = set(JournalEntry.objects.filter(
        tenant=tenant, exercice=exercice, source='ANNUL_PAIEMENT',
        source_id__isnull=False).values_list('source_id', flat=True))
    if not annules:
        return set()

    nets = defaultdict(dict)
    a_origine = set()
    for r in (JournalEntry.objects
              .filter(tenant=tenant, exercice=exercice,
                      source__in=SOURCES_PAIRE, source_id__in=annules)
              .values('source_id', 'source', 'no_compte')
              .annotate(d=Sum('debit'), c=Sum('credit'))):
        if r['source'] == 'PAIEMENT':
            a_origine.add(r['source_id'])
        par_compte = nets[r['source_id']]
        par_compte[r['no_compte']] = (par_compte.get(r['no_compte'], 0)
                                      + float(r['d'] or 0) - float(r['c'] or 0))

    return {sid for sid in a_origine
            if all(abs(v) < 0.005 for v in nets[sid].values())}


def sans_paiements_annules(qs, tenant, exercice):
    """`qs` (écritures d'un exercice) sans les paires paiement annulé / extourne."""
    ids = paiements_annules_compenses(tenant, exercice)
    if not ids:
        return qs
    return qs.exclude(source__in=SOURCES_PAIRE, source_id__in=ids)
