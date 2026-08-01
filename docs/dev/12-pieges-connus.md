# 12 — Registre des pièges connus

Chaque entrée correspond à un incident **réellement survenu en production**.
Format : le symptôme tel qu'il se manifeste, la cause, et la règle qui empêche
de le reproduire.

Lisez ce document en entier une fois. Relisez l'entrée correspondante dès qu'un
symptôme vous paraît familier — il l'est probablement.

---

## A. Chiffres faux

### A1. Deux écrans, deux résultats

**Symptôme.** Le tableau de bord annonce un bénéfice de 61 194 350 F ; le compte
de résultat, 31 391 766 F. Sur les mêmes écritures.

**Cause.** Chaque écran refaisait son propre calcul. Le tableau de bord filtrait
les charges sur `source__in=('CHARGE','BUDGET','MIGRATION')` : la paie, les
dotations aux amortissements et les intérêts d'emprunt, portés par d'autres
sources, tombaient hors du total.

**Règle.** Une grandeur financière a **un seul calcul**, dans un module partagé.
`apps/comptabilite/resultat.py` pour produits / charges / résultat,
`apps/comptabilite/tresorerie.py` pour les soldes. Ne réagrégez jamais à la main
dans une vue. Et ne filtrez **jamais** un total sur `source` : filtrez sur les
comptes.

### A2. L'écran de clôture comptait les charges en double

**Symptôme.** Le récapitulatif présenté juste avant de clôturer l'exercice
affichait 14 331 300 F de charges là où le compte de résultat en trouvait
46 496 494 F.

**Cause.** Il sommait le **débit brut** des écritures `source='CHARGE'`. Une
charge écrit quatre lignes — `6xx D`, `401 C`, `401 D`, `5xx C` — donc le débit
total valait deux fois la dépense. Et la paie n'y était pas du tout.

**Règle.** Le débit brut d'un jeu d'écritures n'est jamais un montant métier.
Passez par `totaux_resultat()`.

### A3. La trésorerie reportée n'était pas une trésorerie

**Symptôme.** Une école ouvrait son année suivante sur des soldes faux, tout en
banque à zéro.

**Cause.** Le solde reporté partait de « recettes − charges », c'est-à-dire d'un
**résultat**. Il ignorait les investissements, les remboursements d'emprunt et
les décaissements de paie, et versait le tout dans la caisse.

**Règle.** Une trésorerie se lit sur les **comptes de trésorerie** du journal,
jamais sur un résultat. `tresorerie.soldes_cloture(exercice)`.

### A4. Bilan « déséquilibré » alors que le journal est juste

**Symptôme.** Total actif ≠ total passif, de l'exact montant d'une subvention
d'investissement, avec un grand livre équilibré au franc près.

**Cause.** Les comptes `10` à `14` — capital, réserves, report à nouveau,
**subventions d'investissement** — n'étaient ramassés par aucune rubrique du
passif.

**Règle.** Quand un bilan ne tombe pas juste, comparez d'abord la somme des
débits et des crédits du journal. Si elle est nulle, le problème est dans la
**présentation** du bilan, pas dans les écritures : un préfixe de compte manque
quelque part.

### A5. Le total des recettes tombé à zéro

**Symptôme.** Le tableau de bord d'une école migrée affiche 0 F de recettes.

**Cause.** Les corrections de reprise depuis l'interface **empilaient** une
écriture de neutralisation `706 D` à chaque passage sans retirer la précédente.
Au bout de quelques corrections, ces débits orphelins dépassaient le produit
migré.

**Règle.** Une écriture de correction se **recalcule en entier**, jamais ne
s'ajoute. Voir `apps/comptabilite/neutralisation.py` — et ancrez le périmètre de
suppression sur le **numéro de pièce**, pas seulement sur la `source`, que
d'autres traitements partagent.

### A6. Un produit compté deux fois

**Symptôme.** Le compte de résultat gonfle sans raison.

**Cause.** Un encaissement qui constate un produit `706` alors qu'il ne devrait
pas : encaissement d'un **reliquat** d'exercice antérieur (le produit a été
constaté l'année d'origine) ou versement d'un **organisme boursier** (le produit
l'a été à l'attribution de la bourse).

**Règle.** Seule `part_exercice` constate un produit. Voir la docstring de
`lignes_paiement` dans `apps/paiements/ecritures.py`.

---

## B. Multi-tenant

### B1. Le premier reçu de la deuxième école part en 500

**Symptôme.** `IntegrityError` sur chaque encaissement d'une école nouvellement
créée.

**Cause.** Une contrainte d'unicité **globale** sur un champ séquentiel généré
par école. Le `REC-0001` de la deuxième école entre en collision avec celui de
la première.

**Règle.** `UniqueConstraint(fields=['tenant', 'champ'])`, toujours. Jamais
`unique=True` seul sur un champ séquentiel.

### B2. Une école lit les données d'une autre

**Cause.** Une fonction `get_tenant()` locale à une application, ou une lecture
directe de l'en-tête `X-Tenant-ID`.

**Règle.** `from core.tenant import get_tenant`, et rien d'autre. L'en-tête n'est
digne de confiance que pour un `SUPER_ADMIN`.

### B3. Un écran plante pour le super-administrateur

**Cause.** Une vue qui suppose que tout utilisateur a un tenant. Le `SUPER_ADMIN`
n'en a pas.

**Règle.** Prévoyez le cas `tenant is None` : erreur explicite ou redirection
vers `/api/dashboard/superadmin/`.

---

## C. Numérotation et identifiants

### C1. La séquence de reçus repart en arrière

**Symptôme.** Après une reprise de migration, chaque encaissement part en 500,
définitivement. L'école voisine, elle, va bien.

**Cause.** `Max('no_piece')` retourne le maximum **lexicographique** :
`max('REC-0100', 'REP-0005')` vaut `'REP-0005'` parce que « P » suit « C ». Le
même piège se déclenche au passage de `9999` à `10000`.

**Règle.** `prochain_no_piece(tenant, prefixe)` — le calcul se fait sur des
nombres, sur une séquence commune à tous les préfixes, et vérifie que le numéro
retenu est libre.

### C2. Le matricule ne dit rien de la promo

**Cause.** L'ancien format utilisait l'année **civile** du jour de saisie et un
compteur global. Deux élèves d'une même promo saisis en septembre puis en
janvier portaient deux années différentes.

**Règle.** Format `AAAA-CODE-NNNN` ancré sur l'**entrée dans l'établissement**.
Attribué une fois, recopié à chaque réinscription. `apps/eleves/matricules.py`,
commande `rebaser_matricules` pour l'existant.

### C3. `date_inscription` n'est pas une date d'entrée

**Cause.** `date_inscription` est **repositionnée à chaque exercice** pour le
calcul du prorata. Elle ne peut pas servir de référence historique.

**Règle.** Utilisez `date_entree` et `annee_entree`, figées à vie.

---

## D. Django REST Framework

### D1. Toute création renvoie 400 sur un champ généré

**Cause.** DRF 3.15 rend **obligatoires** les champs qui participent à une
`UniqueConstraint`. Un `matricule` ou un `no_piece` généré côté serveur devient
requis à l'entrée.

**Règle.** Déclarez-le `read_only` ou `required=False` dans le serializer. Voir
`apps/eleves/serializers.py`.

### D2. `request.tenant` vaut `None` dans un middleware

**Cause.** `TenantMiddleware` s'exécute avant l'authentification DRF. Il pose un
`SimpleLazyObject` qui ne se résout qu'à la première lecture, dans la vue.

**Règle.** Ne lisez pas le tenant avant que DRF ait authentifié.

---

## E. Écoles migrées

### E1. « Ça marche chez une école, pas chez l'autre »

C'est la **signature** d'un problème lié à la migration. Les différences qui
comptent : plusieurs exercices dont des clôturés, des pièces avec un autre
préfixe que `REC`, des élèves sans classe, un historique agrégé importé.

**Règle.** Tout ce qui concerne un élève se lit et s'écrit sur **son** exercice
— celui de sa fiche — jamais sur « le dernier exercice ouvert de l'école ».
Écrivez le test dans `apps/tenants/tests_deux_ecoles.py`.

### E2. Les moyennes et les bulletins sont vides

**Symptôme.** L'écran Résultats ne renvoie aucun élève, puis le bulletin annonce
« Aucune note calculée » alors que les notes sont bien en base.

**Cause.** Le calcul rapprochait les élèves d'une classe **par nom de section**
(`section__nom__iexact=classe.nom`). Cela ne tombe juste que si une section porte
le nom d'une classe. Dès que les sections sont les niveaux tarifaires
(Maternelle, Élémentaire) et les classes les vraies classes (CI, CE2, CM2),
aucun élève ne ressortait.

**Règle.** La **classe de l'élève** fait foi (`Eleve.classe`). Le nom de section
ne sert que de repli pour les fiches anciennes sans classe posée.

---

## F. Windows et poste local

### F1. `UnicodeDecodeError` sur l'octet `0xe9` au démarrage

**Cause.** Un message d'erreur PostgreSQL **en français** (`lc_messages` en
WIN1252) que Python essaie de lire en UTF-8. Le vrai message, masqué, est « la
base de données n'existe pas ».

**Règle.** L'application **ne crée pas** la base. Seul `install_win.ps1` le fait.

### F2. `pkg_resources` introuvable malgré `pip install`

**Règle.** Un shim minimal est embarqué dans
`backend/pkg_resources/__init__.py`, trouvé en premier dans `sys.path` quand
`manage.py` s'exécute depuis `backend/`. **Ne le supprimez pas.**

### F3. Erreur `debug_toolbar` sur un poste client

**Cause.** `manage.py` prend `config.settings.local` par défaut, qui charge la
debug-toolbar — absente en production.

**Règle.** Sur un poste client, toujours
`--settings=config.settings.production`.

### F4. L'assistant d'installation réapparaît après une mise à jour

**Cause.** La mise à jour a écrasé `config/settings/production.py`, dont
l'existence est le drapeau « déjà installé ».

**Règle.** Ressaisir **les mêmes** identifiants de base. `init_installation` est
idempotente : elle ne recrée pas d'école fictive et rien n'est perdu.

### F5. Un fichier Electron absent du `.exe`

**Cause.** Il n'a pas été ajouté à la liste `files` de `electron/package.json`.
En développement, il est là ; dans le paquet, non.

**Règle.** Tout nouveau fichier Electron s'ajoute explicitement à `files`.

---

## G. Interface

### G1. Un `p-select` se ferme dès qu'on fait défiler

**Règle.** `appendTo="body"` et `[overlayOptions]="overlayNoHideOnScroll"`, un
écouteur qui renvoie `false` pour l'événement `scroll`.

### G2. La première ligne d'une boîte de dialogue est rognée

**Cause.** Une classe locale nommée `.grid` entre en collision avec PrimeFlex,
dont les marges négatives rognent le contenu.

**Règle.** Jamais de classe `.grid` locale. La convention est `.form-grid`.

### G3. Des clés de traduction brutes après un déploiement

**Cause.** Le navigateur sert `fr.json` depuis son cache.

**Règle.** Les traductions sont chargées avec `?v=BUILD_ID`. **Incrémentez
`frontend/src/build-id.ts` à chaque livraison touchant aux traductions.**

### G4. Un module reste invisible après un changement de licence

**Cause.** `modules` est une revendication du **jeton JWT**, figée à l'émission.

**Règle.** Le client doit se déconnecter et se reconnecter. C'est la première
question à poser en support.

---

## H. Documents PDF

### H1. Un commentaire apparaît dans le document

**Cause.** `{# … #}` sur plusieurs lignes fuit dans le rendu.

**Règle.** `{% comment %}` … `{% endcomment %}`, et **regardez le PDF généré**
après toute modification de gabarit.

### H2. Les lignes de totaux sont illisibles

**Cause.** Un `background` ou un `color` posé sur `<tr>` : xhtml2pdf l'ignore et
laisse le CSS des cellules gagner.

**Règle.** Stylez les `<td>`, jamais le `<tr>`. Évitez les couleurs claires et
les polices à chasse fixe, dont le rendu papier est plus faible qu'à l'écran.

### H3. La dernière colonne sort de la page

**Cause.** xhtml2pdf **ajoute** le remplissage aux largeurs en pourcentage au
lieu de l'y inclure.

**Règle.** Utilisez la classe `.dense` de `templates/pdf/base.html` au-delà de
sept colonnes.

---

## I. Déploiement

### I1. Le frontend déployé ne change rien

**Cause.** Le build a été déposé dans `/var/www/sagi-app`, qui n'est servi par
rien.

**Règle.** La cible est
`/opt/sagi-school/frontend/dist/frontend/browser`. Purgez ensuite le cache
Cloudflare.

### I2. La version du paquet ne correspond à rien

**Cause.** `electron/package.json` dérive ; la chaîne l'écrase depuis le tag git
au moment du build.

**Règle.** Le tag git fait foi. `git describe --tags`.

---

## Ajouter une entrée

Quand vous corrigez un bug non trivial :

1. Écrivez le test qui l'empêche de revenir, et **vérifiez qu'il échoue** sans
   la correction.
2. Racontez le bug dans un commentaire à l'endroit du code concerné — c'est le
   style dominant de ce dépôt, et c'est ce qui vous sauvera dans deux ans.
3. Ajoutez une entrée ici : symptôme, cause, règle.
