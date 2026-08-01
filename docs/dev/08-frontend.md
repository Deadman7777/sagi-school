# 8 — Frontend Angular

Angular moderne : composants **standalone**, **signals** pour l'état, chargement
paresseux des routes. PrimeNG pour les composants, PrimeFlex pour la grille,
ngx-translate pour l'internationalisation.

Les conventions de style détaillées sont dans `frontend/.claude/CLAUDE.md`
(strict typing, `input()`/`output()`, `inject()`, contrôle de flux natif `@if`
et `@for`, `OnPush`). Ce document couvre ce qui est propre à SAGI SCHOOL.

## Structure

```
frontend/src/app/
├── app.routes.ts            toutes les routes, chargées paresseusement
├── layout/shell/            barre latérale, en-tête, filtrage par licence
├── core/
│   ├── guards/              authGuard, licenceGuard
│   ├── interceptors/        authInterceptor (JWT + X-Tenant-ID)
│   ├── services/            un service par domaine métier
│   └── models/
├── features/                un dossier par module — miroir des apps Django
└── shared/
```

`features/` reflète les applications Django : `eleves`, `paiements`,
`comptabilite`, `academique`, `rh`, `fiscal`, `gmrf`, `gouvernance`,
`suivi-mensuel`, `parametres`, `licences`, `ma-licence`, `dashboard`, `auth`.

## Le patron dominant : un gros composant par module

Chaque module est **un seul composant**, souvent long (1 000 à 3 000 lignes),
avec son template en ligne et ses onglets gérés par un signal :

```typescript
onglet = signal<'journal' | 'grand-livre' | 'balance' | ...>('journal');
```

Les onglets sont des `<button class="tab-btn">` qui appellent une méthode de
chargement puis positionnent le signal.

Ce n'est pas le découpage qu'on enseigne, et c'est assumé : ces écrans sont
denses, fortement couplés à un seul service, et la navigation par onglets ne
justifie pas une hiérarchie de composants. **Si vous refactorez, faites-le pour
une raison mesurable**, pas par principe — et pas sur plusieurs modules à la
fois.

## Les trois modes de sélection d'exercice

Beaucoup d'écrans acceptent `?exercice=<id>` pour consulter une année clôturée
**en lecture seule**. Côté backend, cela se traduit par `get_exercice(tenant,
request)` sur les vues de lecture, et `get_exercice(tenant)` — sans `request` —
sur les vues d'écriture, qui restent donc toujours sur l'exercice actif.

Ne passez jamais `request` à `get_exercice` dans une vue qui écrit.

## Internationalisation

Trois langues : **français** (défaut), **arabe** (passe l'interface en
droite-à-gauche, pour les daaras) et **anglais**.

Fichiers : `frontend/src/assets/i18n/{fr,ar,en}.json` — **1 160 lignes chacun,
et ils doivent rester alignés**. Une clé ajoutée dans `fr.json` et oubliée
ailleurs affiche la clé brute à l'écran.

> **Cache-busting obligatoire.** Les traductions sont chargées avec
> `?v=BUILD_ID` (`frontend/src/app/app.config.ts`, constante dans
> `frontend/src/build-id.ts`). Sans cela, un navigateur qui a mis `fr.json` en
> cache continue d'afficher les anciennes clés après un déploiement. **Changez
> `BUILD_ID` à chaque livraison qui touche aux traductions.**

## Thème clair et sombre

`core/services/theme.service.ts`. Le choix est persisté dans `localStorage`
(`sagi-theme`) et appliqué par une classe sur `<body>` — `theme-dark` ou
`theme-light` — qui redéfinit les jetons CSS de `styles.scss`.

Écrivez toujours vos styles avec les jetons (`var(--bg)`, `var(--surface)`,
`var(--text)`, `var(--border)`), jamais avec des couleurs en dur : sinon votre
écran sera illisible dans l'autre thème.

## Deux pièges PrimeNG qui ont coûté cher

### Le `p-select` qui se ferme au défilement

Dans une boîte de dialogue, un `p-select` se referme dès qu'on fait défiler.
La parade, présente partout dans `academique.component.ts` :

```html
<p-select appendTo="body" [overlayOptions]="overlayNoHideOnScroll" ...>
```

où `overlayNoHideOnScroll` fournit un écouteur qui renvoie `false` pour
l'événement `scroll`.

### La classe `.grid` de PrimeFlex

**N'utilisez jamais une classe locale nommée `.grid`.** Les marges négatives de
PrimeFlex rognent la première ligne des boîtes de dialogue. La convention du
projet est `.form-grid`.

## Communication avec l'API

`core/services/api.service.ts` centralise l'URL de base, tirée de
`environments/environment*.ts` :

| Fichier | `mode` | `apiUrl` |
|---|---|---|
| `environment.ts` (dev) | `local` | `http://127.0.0.1:8765/api` |
| `environment.prod.ts` | `local` | `/api` — Django sert le frontend |
| `environment.cloud.ts` | `cloud` | `https://api.sagi-school.com/api` |

`core/services/app-mode.service.ts` expose `isLocal()` / `isCloud()` pour les
rares écrans qui diffèrent — par exemple la demande de renouvellement de
licence, qui part par SMTP en cloud et par `mailto:` en local.

## Ajouter un module

1. Créer l'application Django et ses routes `/api/<module>/`.
2. Ajouter le service dans `core/services/`.
3. Créer `features/<module>/<module>.component.ts`.
4. Déclarer la route dans `app.routes.ts`, **enfant du shell**, chargée
   paresseusement.
5. Ajouter l'entrée de menu dans `layout/shell/shell.component.ts`.
6. **Ajouter la route dans `Licence.MODULES_PAR_TYPE`** pour les formules
   concernées — sinon le module reste invisible, y compris pour vous.
7. Ajouter les clés de traduction dans **les trois** fichiers i18n.
8. Incrémenter `BUILD_ID`.
