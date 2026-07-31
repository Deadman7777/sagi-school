"""Numérotation des pièces d'une école.

Le numéro suivant se calcule sur des NOMBRES, jamais sur l'ordre alphabétique.

Le calcul historique prenait `Max('no_piece')`, c'est-à-dire le maximum
lexicographique de la colonne :

    max('REC-0100', 'REP-0005') == 'REP-0005'      # « P » vient après « C »

Une école ayant fait une reprise de migration — pièces `REP-NNNN`, rangées dans
la même table que les reçus — tôt dans sa vie, puis cent encaissements, voyait
donc la séquence repartir de 5. Le reçu suivant s'appelait `REC-0006`, déjà pris,
et l'insertion violait `uniq_no_piece_par_tenant` : 500 sur CHAQUE encaissement,
définitivement. L'école voisine, sans reprise, n'avait que des `REC-` — son
maximum alphabétique coïncidait avec son maximum numérique, et tout marchait.

Le même piège guette dès que deux préfixes cohabitent, ou au passage de 9999 à
10000 (`'REC-10000' < 'REC-9999'`).
"""
import re

# Dernier groupe de chiffres de la pièce : « RAN-2025-0007 » → 7.
_DERNIER_NOMBRE = re.compile(r'(\d+)(?!.*\d)')


def prochain_no_piece(tenant, prefixe='REC'):
    """Prochaine pièce libre de cette école, sur la séquence numérique commune.

    La séquence est partagée par tous les préfixes (REC, REP…) : les pièces
    d'une école se suivent, quelle que soit leur origine.

    Le numéro retenu est vérifié libre avant d'être rendu. Des données migrées à
    la main peuvent porter n'importe quel format ; aucune n'a à provoquer un 500
    sur l'encaissement suivant.
    """
    from .models import Paiement

    pieces = list(Paiement.objects.filter(tenant=tenant)
                  .values_list('no_piece', flat=True))
    numeros = [int(m.group(1)) for p in pieces
               if (m := _DERNIER_NOMBRE.search(p or ''))]
    suivant = max(numeros, default=0) + 1

    pris = set(pieces)
    while (no_piece := f"{prefixe}-{suivant:04d}") in pris:
        suivant += 1
    return no_piece
