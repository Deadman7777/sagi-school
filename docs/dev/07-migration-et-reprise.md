# 7 — Migration et reprise de données

Une école qui bascule sur SAGI SCHOOL a déjà une histoire : des élèves, des
règlements encaissés, parfois des années entières dans un cahier ou un tableur.
La reprise de cet historique est **la partie la plus délicate du produit**.
C'est aussi celle qui a produit le plus d'incidents.

## Le danger central

> Un montant encaissé **avant** la bascule ne doit **jamais** être saisi comme un
> paiement ordinaire.

Sinon la trésorerie et le compte de résultat gonflent de tout l'historique de
l'école. L'argent est déjà dans les soldes d'ouverture de l'exercice : le
recompter revient à l'encaisser deux fois.

## Les trois mécanismes, et quand utiliser lequel

| Mécanisme | Ce qu'il fait | Code | Trésorerie touchée |
|---|---|---|---|
| **Paiement de reprise** | Reconstitue le « déjà payé » d'un élève | `apps/paiements/reprise.py` | **Non** — passe par le 890 |
| **Import du journal de caisse** | Injecte l'historique agrégé d'une école | `apps/comptabilite/management/commands/import_journal_caisse.py` | Oui — c'est le vrai historique |
| **Report des reliquats** | Reconduit les impayés d'un exercice au suivant | `apps/paiements/report_reliquats.py` | Non — à-nouveaux de bilan |

### Paiement de reprise

Mode `REPRISE`, absent des formulaires de saisie. Écritures :

```
411 D / 706 C     créance et produit scolarité (résultat de l'exercice)
890 D / 411 C     règlement par le bilan d'ouverture — PAS par la trésorerie
```

La `source` reste `PAIEMENT`, ce qui fait que l'annulation standard fonctionne
sans code particulier.

Côté interface, cela s'appelle **« Corriger le déjà payé (reprise) »**, depuis la
fiche de l'élève.

### Report des reliquats

```
411 D / 890 C     dans le NOUVEL exercice, à sa date d'ouverture
```

Aucun produit : il a été constaté l'année d'origine. L'exercice source n'est
jamais touché — une année clôturée reste en lecture seule, et le report peut donc
être joué **après coup** sur un exercice déjà clôturé, ce qui est le cas courant.

> **Le report est idempotent.** Le rejouer ne duplique ni les fiches ni les
> écritures. C'est un outil de rattrapage, utilisable autant de fois que
> nécessaire.

Plus tard, l'encaissement du reliquat solde cette créance (`trésorerie D / 411 C`)
**sans 706** — voir `Paiement.montant_reliquat` et le document 5.

### Neutralisation des reprises

Quand l'historique a été importé en agrégats **et** que des reprises par élève
sont saisies, le produit `706` est compté deux fois. La neutralisation
(`apps/comptabilite/neutralisation.py`) l'annule par `706 D / 890 C`.

Elle est **recalculée en entier à chaque appel**, jamais ajoutée. Voir le
document 5 et la docstring du module : la version qui empilait a mis les
recettes d'une école à zéro.

## Import Excel des élèves

`apps/eleves/` — endpoints `import-template/` et `import-excel/`.

Deux colonnes déterminantes dans le modèle :

- **impayé antérieur** — la dette reprise, avec son origine ;
- **« à jour » / « dette »** — l'état de l'élève à la bascule.

Le matricule est attribué par le système, pas repris du fichier. L'ancien
matricule de l'école est conservé dans `Eleve.matricule_ancien` pour que les
carnets papier et les anciens reçus restent exploitables.

## Les commandes de réparation

Elles existent parce que des écoles réelles se sont retrouvées dans des états
incohérents. Chacune est **idempotente** et documentée dans sa propre docstring.

```
apps/comptabilite/management/commands/
    recaler_reste_du_shoumoul.py        recalage du reste dû
    recaler_tresorerie_migration.py     recalage de la trésorerie migrée
    reclasser_charges_migration.py      reventilation des charges reprises
    reconcilier_migration_produits.py   réconciliation des produits
    reparer_annulations_orphelines.py   contre-écritures sans original
    reparer_neutralisation_reprises.py  neutralisations empilées
    import_journal_caisse.py            import de l'historique agrégé

apps/paiements/management/commands/
    reporter_reliquats.py               report des impayés

apps/eleves/management/commands/
    rebaser_matricules.py               passage au format promo
    marquer_anciens.py                  marquage des anciens élèves
```

> Avant d'écrire une nouvelle commande de réparation, **lisez celles-ci**. Le
> plus souvent, l'une d'elles couvre déjà le cas, ou en donne le patron : lire
> l'état, dire ce qui va changer, changer, dire ce qui a changé.

## Santé de la migration

Un écran dédié existe dans Paramètres, alimenté par
`/api/eleves/sante-migration/`. Il liste les incohérences détectables : élèves
sans section, reprises sans origine, écarts entre le dû et l'échéancier.

C'est le premier endroit à regarder quand une école migrée se plaint de chiffres
faux — avant d'ouvrir le journal.

## La classe de bug « une école oui, l'autre non »

C'est **la** signature d'un problème de migration. Un comportement qui marche
chez une école et pas chez sa voisine vient presque toujours de l'une de ces
différences :

| Différence | Ce qu'elle casse |
|---|---|
| Plusieurs exercices, dont des clôturés | Une fiche pointe encore l'ancien exercice |
| Des pièces avec un préfixe autre que `REC` | La numérotation, si elle trie alphabétiquement |
| Des élèves sans classe | Les moyennes et les bulletins |
| Des sections dont le nom coïncide avec une classe | Masque les bugs de rapprochement par nom |
| Un historique agrégé importé | La double comptabilisation des produits |

Le test `backend/apps/tenants/tests_deux_ecoles.py` existe pour cette raison :
il monte deux écoles aux caractéristiques différentes et vérifie que la règle
tient pour les deux. **Étendez-le** plutôt que d'écrire un test sur une seule
école.

> **Règle d'or** : tout ce qui concerne un élève se lit et s'écrit sur **son**
> exercice — celui de sa fiche — jamais sur « le dernier exercice ouvert de
> l'école ». Les deux coïncident pour une école née dans le logiciel, et
> divergent pour une école migrée. Voir `apps/paiements/views.py`,
> `PaiementViewSet.perform_create`.
