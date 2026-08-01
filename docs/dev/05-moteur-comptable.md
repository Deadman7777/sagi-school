# 5 — Moteur comptable

La comptabilité de SAGI SCHOOL est conforme au **SYSCOHADA Révisé** (référentiel
OHADA, en vigueur au Sénégal). Ce document explique comment elle est produite —
pas comment elle se lit, ce qui est l'affaire du guide utilisateur.

## La règle fondatrice

> **Aucune écriture ne se saisit à la main. Chaque opération métier produit ses
> écritures dans le même appel que l'opération elle-même.**

Il n'existe pas d'écran de saisie d'écriture, et il ne faut pas en ajouter. Le
module Comptabilité est un module de **lecture** : journal, grand livre, balance,
états financiers. Ce qu'il affiche descend des autres modules.

Conséquence pour vous : si vous ajoutez une opération qui touche à l'argent,
c'est **votre** code qui doit écrire les écritures, dans la même transaction.
Sinon la trésorerie et le résultat de l'école deviennent faux, silencieusement.

## Qui produit quoi

| Opération | Où c'est écrit | `source` |
|---|---|---|
| Encaissement de scolarité | `apps/paiements/ecritures.py` + `views.py` | `PAIEMENT` |
| Annulation / modification d'un règlement | `apps/paiements/views.py` | `ANNUL_PAIEMENT` |
| Attribution d'une bourse | `apps/eleves/creances_organisme.py` | `CREANCE_ORGANISME` |
| Charge de fonctionnement | `apps/comptabilite/views.py` (`ChargeView`) | `CHARGE` |
| Ligne de budget comptabilisée | `apps/comptabilite/views.py` | `BUDGET` |
| Immobilisation, amortissement | `apps/comptabilite/views.py` | `INVEST`, `AMORT` |
| Bulletin de paie validé | `apps/rh/services.py` (`generer_ecritures_paie`) | `PAIE` |
| Avance sur salaire | `apps/rh/views.py` | `AVANCE` |
| Don, subvention, tontine, prêt | `apps/gmrf/services.py` | `GMRF_*` |
| Provision, transfert interne, régularisation | `apps/gouvernance/services.py` | `PROVISION`, `TRANSFERT`, `RAPPRO_REG` |
| Obligation fiscale comptabilisée | `apps/fiscal/views.py` | `RECETTE` |
| Reprise de migration | `apps/paiements/reprise.py` | `MIGRATION` |
| Report des reliquats à la clôture | `apps/paiements/report_reliquats.py` | `REPORT_RELIQUAT` |

## Anatomie d'un encaissement

L'exemple à comprendre en premier. `apps/paiements/ecritures.py`, fonction
`lignes_paiement`.

Une famille règle 68 000 F en espèces, dont 68 000 F au titre de l'année en
cours :

```
1  411   D 68 000   Créance scolarité — Ndeye Camara - REC-0845
2  706   C 68 000   Créance scolarité — Ndeye Camara - REC-0845
3  571   D 68 000   Règlement Caisse — Ndeye Camara - REC-0845
4  411   C 68 000   Règlement — Ndeye Camara - REC-0845
```

On constate d'abord la créance et le produit, puis on encaisse et on solde la
créance. Ce n'est pas un détour inutile : c'est ce qui rend le compte 411 lisible
à tout moment, et ce qui permet de payer en plusieurs fois.

### Les deux cas qui ne constatent aucun produit

C'est le cœur de la subtilité, et la source de plusieurs bugs passés.

**Le reliquat d'un exercice antérieur.** Son produit a été comptabilisé l'année
d'origine, sa créance reportée en à-nouveaux. L'encaissement se contente de
solder le 411. Écrire un 706 ici compterait le produit **deux fois**.

**Le versement d'un organisme boursier.** Sa créance a été constatée à
l'attribution de la bourse (`4112 D / 706 C`). L'encaissement solde le `4112`.
Même raison.

D'où la signature :

```python
lignes_paiement(total, part_exercice, ventilation, libelle, organisme=False)
```

`part_exercice` = `total − montant_reliquat`. C'est **elle seule** qui constate
un produit.

## Multi-mode : un règlement, plusieurs canaux

`apps/comptabilite/tresorerie.py` est la **source unique de vérité** de la
correspondance mode → compte :

```python
COMPTE_MODE = {
    'ESPECE':       ('571',  'Caisse'),
    'WAVE':         ('5521', 'Wave'),
    'ORANGE_MONEY': ('5522', 'Orange Money'),
    'FREE_MONEY':   ('5523', 'Free Money'),
    'VIREMENT':     ('521',  'Banque'),
    'CHEQUE':       ('521',  'Banque'),
}
```

Un règlement peut être ventilé sur plusieurs modes (`Paiement.modes_reglement`).
`normaliser_ventilation()` valide et normalise la ventilation ;
`lignes_tresorerie()` produit les lignes, dans le sens voulu (débit pour un
encaissement, crédit pour un décaissement).

Ne recopiez jamais cette table ailleurs. Elle a été dupliquée dans plusieurs
vues par le passé, et les copies ont divergé.

## Les calculs partagés

Deux modules centralisent des grandeurs que **plusieurs écrans** affichent. Ils
existent parce que chaque duplication a fini par diverger.

### `apps/comptabilite/resultat.py`

```python
totaux_resultat(entries) -> {'total_produits', 'total_charges', 'resultat_net'}
```

- Produits : classe 7, plus le HAO positif (82, 84, 86, 88)
- Charges : classe 6, plus le HAO positif (81, 83, 87, 89)
- Compte `890` exclu — bilan d'ouverture de migration, ni produit ni charge
- Chaque compte compte **net** (crédit − débit pour un produit, l'inverse pour
  une charge), pour absorber annulations et neutralisations

Utilisé par le compte de résultat, le tableau de bord et l'écran de clôture.
**Toute nouvelle vue affichant un résultat doit passer par là.**

### `apps/comptabilite/tresorerie.py`

```python
soldes_cloture(exercice) -> {'caisse', 'banque', 'mobile', 'total'}
```

Solde d'ouverture de l'exercice + mouvements nets du journal sur les comptes de
trésorerie. Utilisé par le report sur le nouvel exercice à la clôture, et par
le même calcul que « Trésorerie par canal » du tableau de bord.

> **Ne recalculez jamais une trésorerie par « recettes − charges ».** C'est un
> *résultat*, pas une trésorerie : cela ignore les investissements, les
> remboursements d'emprunt et les décaissements de paie. Ce bug a existé.

## Annulations : rien ne s'efface

Une annulation écrit des **contre-écritures** de sens inverse, avec une `source`
`ANNUL_*` et une pièce dédiée. Une modification enchaîne annulation puis
nouvelles écritures. Le journal garde les trois jeux.

Un garde-fou existe : avant d'annuler, le code vérifie qu'une annulation n'a pas
déjà été écrite pour cet objet (`JournalEntry.objects.filter(source='ANNUL_...',
source_id=...)`), sinon une double annulation créerait un produit fantôme.

## Migration : la neutralisation

`apps/comptabilite/neutralisation.py` — lisez la docstring en entier, elle
raconte l'incident qui a mis le total des recettes d'une école à zéro.

Le résumé : quand l'historique d'une école est importé sous forme d'agrégats
(journal de caisse), les produits sont déjà au grand livre. Les reprises par
élève re-créditent `706` pour reconstituer le « déjà payé » de chacun. Sans
contrepartie, le produit serait compté deux fois — d'où une neutralisation
`706 D / 890 C`.

> **La neutralisation est recalculée en entier à chaque appel, jamais ajoutée.**
> Corriger la reprise d'un élève dix fois doit laisser **une** paire
> d'écritures. La version qui empilait les débits a fini par dépasser le produit
> migré et faire tomber les recettes à zéro.

Le périmètre de suppression est ancré sur le **numéro de pièce** (`RECAL-REP`)
et pas seulement sur la `source` : le recalage de trésorerie partage la même
source et ne doit pas être emporté.

## Le plan comptable

`apps/comptabilite/management/commands/init_plan_comptable.py` — 125 comptes
SYSCOHADA Révisé, créés par école. Les comptes marqués `est_systeme` ne sont pas
supprimables.

Comptes que vous croiserez constamment :

| Compte | Signification |
|---|---|
| `411` | Clients — créances sur les familles |
| `4112` | Créances sur les organismes payeurs (bourses) |
| `571` | Caisse |
| `521` | Banque |
| `5521` / `5522` / `5523` | Wave / Orange Money / Free Money |
| `706` | Prestations de services — la scolarité |
| `401` / `404` | Fournisseurs ordinaires / d'immobilisations |
| `661` / `664` | Salaires / charges patronales |
| `681` | Dotations aux amortissements |
| `890` | Bilan d'ouverture (migration) — **hors résultat** |

## Ajouter une opération qui touche à l'argent

La marche à suivre :

1. Écrire la fonction qui produit les lignes dans un module `services.py` ou
   `ecritures.py` — **pas dans la vue**. Elle doit être testable sans requête HTTP.
2. Choisir une `source` explicite et l'ajouter au tableau de ce document.
3. Générer le numéro de pièce via `prochain_no_piece(tenant, prefixe)`.
4. Écrire les écritures dans la même transaction que l'objet métier.
5. Prévoir l'annulation : contre-écritures `ANNUL_*`, avec garde-fou contre la
   double annulation.
6. Appeler `log_audit`.
7. Écrire un test qui vérifie que **débit = crédit** sur la pièce produite, et
   que la grandeur affectée reste cohérente entre les écrans qui l'affichent.
