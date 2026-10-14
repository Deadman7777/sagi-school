"""La grille tarifaire officielle — la seule du côté serveur.

**Pourquoi ce fichier existe.** Jusqu'ici les tarifs ne vivaient qu'en trois
endroits qui ne se parlent pas : l'écran Licences du frontend, le site vitrine,
et les documents commerciaux. Tant qu'un devis se rédigeait à la main, cela
passait. Dès lors que nos serveurs en produisent un, il leur faut une source —
et surtout, il ne faut pas que ce soit une quatrième.

C'est le même principe que `apps/assistant/perimetre.py` : ce qui engage
l'entreprise est produit par le logiciel, jamais récité de mémoire. Un montant
inventé se retrouve sur une pièce que le client signe, et il faut alors
l'honorer.

**Source des chiffres.** Catalogue officiel des offres et tarifs 2026-2027, et
Annexe A « Conditions commerciales des licences » (HG-COM-006-V01). Les deux
concordent : 25 000 / 50 000 / 90 000 / 20 000 F CFA par mois, essai gratuit
trente jours.

**Un écart connu, à trancher par la direction.** La remise de 10 % sur le
paiement annuel est appliquée par l'écran Licences depuis toujours, mais elle
**ne figure dans aucun des deux documents officiels** : ils mentionnent le
paiement annuel comme une modalité, sans réduction. Elle est donc reprise ici
telle qu'elle est pratiquée — un devis qui contredirait ce que l'application
facture serait pire — mais elle est réglable, et le devis l'imprime sur une
ligne à part plutôt que de la fondre dans un prix. Rien ne doit être remisé
sans que cela se voie.
"""
from decimal import Decimal

from django.conf import settings

# Prix mensuel par type de licence, en francs CFA.
TARIFS_MENSUEL = {
    'ESSAI':        Decimal('0'),
    'BASIC':        Decimal('25000'),
    'PRO':          Decimal('50000'),
    'AVANCE':       Decimal('90000'),
    'TAXAWU_DAARA': Decimal('20000'),
}

CYCLES = [
    ('MENSUEL', 'Mensuel'),
    ('ANNUEL',  'Annuel (12 mois)'),
]

# « Les devis sont valables trente (30) jours à compter de leur date
# d'émission. » — Catalogue officiel, section Conditions commerciales.
VALIDITE_DEVIS_JOURS = 30

# Les moyens de paiement, tels qu'ils sont annoncés au catalogue. Repris à
# l'identique sur le devis : un client qui découvre à la signature qu'un moyen
# annoncé n'est pas accepté a raison de s'en étonner.
MOYENS_PAIEMENT = ('Virement bancaire', 'Chèque', 'Wave', 'Orange Money',
                   'Espèces dans les limites prévues par la réglementation')

REFERENCE_CATALOGUE = 'HG-COM-006-V01'


# Brochure 2026-2027 « Remises de prépaiement » : 8 % pour un paiement de six
# mois. Le forfait de déploiement (installation + paramétrage + formation) est
# de 100 000 F quelle que soit la licence ; la migration des données part de
# 50 000 F (« à partir de » : un plancher, que la proposition peut relever).
REMISE_SEMESTRIELLE_DEFAUT = '0.08'
FRAIS_INSTALLATION = Decimal('100000')
FRAIS_MIGRATION_MIN = Decimal('50000')


def remise_semestrielle():
    """La part remisée sur un paiement de six mois (brochure 2026-2027)."""
    return Decimal(str(getattr(settings, 'REMISE_SEMESTRIELLE', REMISE_SEMESTRIELLE_DEFAUT)))


def formules(prix_mensuel, taux_semestriel, taux_annuel, installation, migration):
    """Les trois formules d'une proposition commerciale, chiffrées côte à côte.

    Mêmes règles que la proposition HG-IDM-2026 : les remises portent sur la
    LICENCE seule ; le forfait d'installation est dû une fois quelle que soit
    la formule ; la migration est une option, hors des totaux de base.
    Tout en francs entiers.
    """
    D = lambda x: Decimal(str(x or 0))
    p, ts, ta = D(prix_mensuel), D(taux_semestriel), D(taux_annuel)
    inst, migr = D(installation), D(migration)
    un = Decimal('1')

    brut_s, brut_a = p * 6, p * 12
    remise_s = (brut_s * ts).quantize(un)
    remise_a = (brut_a * ta).quantize(un)
    net_s, net_a = brut_s - remise_s, brut_a - remise_a
    total_m, total_s, total_a = p + inst, net_s + inst, net_a + inst
    tranche_1 = (total_a / 2).quantize(un)

    sur_12 = {'MENSUELLE': p * 12 + inst, 'SEMESTRIELLE': net_s * 2 + inst,
              'ANNUELLE': net_a + inst}
    i = lambda x: int(x)
    return {
        'prix_mensuel': i(p), 'installation': i(inst), 'migration': i(migr),
        'taux_semestriel': float(ts), 'taux_annuel': float(ta),
        'mensuelle':    {'licence': i(p), 'remise': 0, 'net': i(p), 'equivalent': i(p),
                         'total': i(total_m)},
        'semestrielle': {'licence': i(brut_s), 'remise': i(remise_s), 'net': i(net_s),
                         'equivalent': i((net_s / 6).quantize(un)), 'total': i(total_s)},
        'annuelle':     {'licence': i(brut_a), 'remise': i(remise_a), 'net': i(net_a),
                         'equivalent': i((net_a / 12).quantize(un)), 'total': i(total_a)},
        'tranches': [i(tranche_1), i(total_a - tranche_1)],
        'sur_12_mois': [{'formule': f, 'sans_migration': i(v), 'avec_migration': i(v + migr),
                         'economie': i(sur_12['MENSUELLE'] - v)} for f, v in sur_12.items()],
    }


def remise_annuelle():
    """La part remisée sur un paiement annuel. Voir l'en-tête du module."""
    return Decimal(str(getattr(settings, 'REMISE_ANNUELLE', '0.10')))


def tarif_mensuel(type_licence):
    return TARIFS_MENSUEL.get(type_licence, Decimal('0'))


def chiffrer(type_licence, cycle='ANNUEL', mois=12):
    """Le chiffrage d'une licence, poste par poste.

    Rend un dictionnaire plutôt qu'un total : un devis doit montrer comment on
    arrive au montant, et le client doit pouvoir refaire l'addition. Un total
    seul, c'est un prix à croire.

    Les montants sont des entiers de francs — le franc CFA n'a pas de
    subdivision, et un devis qui afficherait 243 000,50 F serait faux.
    """
    mois = max(int(mois or 0), 0)
    unitaire = tarif_mensuel(type_licence)
    brut = unitaire * mois

    part = remise_annuelle() if cycle == 'ANNUEL' else Decimal('0')
    remise = (brut * part).quantize(Decimal('1'))

    return {
        'type_licence':   type_licence,
        'cycle':          cycle,
        'mois':           mois,
        'prix_mensuel':   unitaire.quantize(Decimal('1')),
        'montant_brut':   brut.quantize(Decimal('1')),
        'taux_remise':    part,
        'montant_remise': remise,
        'montant_net':    (brut - remise).quantize(Decimal('1')),
    }


def catalogue_public():
    """La grille telle qu'elle est servie au frontend et au site vitrine.

    Le périmètre de chaque licence vient du CODE, pas du catalogue commercial :
    celui-ci annonce une « gestion des emplois du temps » qui n'existe pas.
    C'est la même règle que pour l'assistant — voir
    `apps/assistant/perimetre.py`.
    """
    from apps.assistant.perimetre import modules_de
    from .models import Licence

    return {
        'reference': REFERENCE_CATALOGUE,
        'validite_devis_jours': VALIDITE_DEVIS_JOURS,
        'taux_remise_annuelle': float(remise_annuelle()),
        'moyens_paiement': list(MOYENS_PAIEMENT),
        'licences': [{
            'code':          code,
            'libelle':       libelle,
            'prix_mensuel':  int(tarif_mensuel(code)),
            'modules':       [{'nom': nom, 'detail': detail}
                              for nom, detail in modules_de(code)],
        } for code, libelle in Licence.TYPE_CHOICES],
        'cycles': [{'code': code, 'libelle': libelle} for code, libelle in CYCLES],
    }
