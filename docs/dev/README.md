# Documentation technique — SAGI SCHOOL

Cette documentation s'adresse à **un développeur qui reprend le produit sans
personne à qui demander**. Elle part du principe que vous savez programmer, mais
que vous ne connaissez ni ce code, ni le métier, ni les décisions prises avant
vous.

Elle répond à trois questions, dans cet ordre : *comment ça marche*, *pourquoi
c'est fait comme ça*, et *qu'est-ce qui a déjà cassé*.

---

## Ce qu'est SAGI SCHOOL

Un logiciel de gestion d'établissement scolaire, édité par **HADY GESMAN**,
destiné aux écoles privées et aux daaras (écoles coraniques) du Sénégal.

Il couvre les élèves, les encaissements de scolarité, une comptabilité
**SYSCOHADA Révisé** complète, la paie au barème sénégalais, les notes et
bulletins, la mobilisation de ressources (dons, subventions, tontines, prêts) et
la gouvernance par projet.

Deux modes de déploiement, **le même code** :

- **local** — une application de bureau installée dans l'école, qui fonctionne
  sans internet ;
- **cloud** — un navigateur qui pointe sur les serveurs de HADY GESMAN.

---

## Ordre de lecture

Les trois premiers documents sont indispensables avant de toucher au code. Les
suivants se lisent au besoin.

| | Document | Lire quand |
|---|---|---|
| 1 | [Architecture](01-architecture.md) | Toujours, en premier |
| 2 | [Monter un poste de développement](02-poste-de-developpement.md) | Toujours, en deuxième |
| 3 | [Modèle de données et invariants](03-modele-de-donnees.md) | Toujours, en troisième |
| 4 | [Multi-tenant, authentification et rôles](04-multi-tenant-et-roles.md) | Avant d'écrire la moindre vue |
| 5 | [Moteur comptable](05-moteur-comptable.md) | Avant de toucher à l'argent |
| 6 | [Licences et modules](06-licences-et-modules.md) | Pour comprendre le gating |
| 7 | [Migration et reprise de données](07-migration-et-reprise.md) | Quand une école bascule sur le produit |
| 8 | [Frontend Angular](08-frontend.md) | Pour travailler côté interface |
| 9 | [Documents PDF](09-documents-pdf.md) | Pour toucher aux reçus, bulletins, états |
| 10 | [Build et déploiement](10-build-et-deploiement.md) | Pour livrer une version |
| 11 | [Tests](11-tests.md) | Avant d'ouvrir une pull request |
| 12 | [Registre des pièges connus](12-pieges-connus.md) | **Quand quelque chose ne marche pas** |

Le document 12 est celui qui vous fera gagner le plus de temps. Il recense les
bugs qui sont réellement survenus en production, leur cause, et la règle qui
évite de les reproduire. Lisez-le une fois en entier, même sans problème à
résoudre.

---

## Ce que cette documentation ne contient pas

**Le détail des règles métier.** Il est dans le code, en français, dans les
docstrings des modules. Ce sont elles qui font foi : elles vivent avec le code
et sont mises à jour avec lui. Cette documentation vous dit *où chercher*, elle
ne recopie pas.

Les docstrings les plus denses, à lire absolument :

```
backend/apps/paiements/ecritures.py       écritures d'un encaissement
backend/apps/paiements/numerotation.py    numérotation des pièces
backend/apps/eleves/matricules.py         attribution du matricule
backend/apps/comptabilite/resultat.py     produits, charges, résultat
backend/apps/comptabilite/tresorerie.py   modes de règlement et soldes
backend/apps/comptabilite/neutralisation.py  reprises de migration
backend/core/tenant.py                    isolation des écoles
```

**Le mode d'emploi du logiciel.** Il existe et il est ailleurs :
`docs/guide-formation-sagi-school.pdf`. Un développeur qui n'a jamais vu le
produit tourner devrait le parcourir avant de coder — comprendre ce qu'une
directrice d'école attend de l'écran fait écrire un meilleur code.

**Le déploiement cloud pas à pas.** Il est dans `backend/deploy/DEPLOY.md`,
maintenu à part parce qu'il change au rythme de l'hébergeur.

---

## Conventions de ce dépôt

**Tout est en français** — code, commentaires, noms de variables métier,
messages d'erreur, commits. Ce n'est pas une préférence esthétique : les
utilisateurs sont francophones, le métier est francophone (SYSCOHADA, IPRES,
CFCE, NINEA, RCCM), et un `montant_mensualite` se relit sans traduction. Les
mots anglais restent là où ils sont techniques (`request`, `queryset`, `signal`).

**Les commentaires expliquent le pourquoi, pas le quoi.** Le style dominant du
dépôt est de raconter le bug qui a motivé le code. Si vous corrigez quelque
chose de subtil, écrivez la même chose : ce qui se passait avant, pourquoi
c'était faux, et ce qui garantit que ça ne revienne pas.

**Les messages de commit décrivent l'effet, pas le fichier.** `Fix(paiements):
le reliquat d'une échéance se réclame à la suivante` plutôt que
`Fix: update views.py`. Le corps du message porte le contexte.
