# Guide de formation SAGI SCHOOL — source

Deux sources séparées :

- `guide.html` — le **Guide d'utilisation**, remis aux écoles ;
- `manuel-formateur.html` — le **Manuel du formateur**, document interne
  HADY GESMAN, qui ne doit jamais être remis à une école.

Les captures (`captures/*.webp`) et les polices (`assets/`) restent à côté ;
`build.py` produit les fichiers distribués.

## Refaire le guide pour une nouvelle version

1. **Démonstration** (école fictive, SQLite jetable), depuis `backend/` :

       rm -f demo.sqlite3
       python manage.py migrate --settings=config.settings.demo
       python scripts/seed_demo.py
       python manage.py runserver 8765 --settings=config.settings.demo

2. **Frontend** de développement, depuis `frontend/` (il pointe sur 8765) :

       npx ng serve --port 4300

3. **Captures d'écran**, depuis `docs/formation/` (une première fois : `npm install`) :

       node captures.mjs            # toutes
       node captures.mjs eleves     # seulement celles dont le nom contient « eleves »

4. **Documents PDF** (reçu, certificat, bulletins, proforma), depuis `backend/` :

       python ../docs/formation/documents.py

5. **Texte** : modifier `guide.html` (ou `manuel-formateur.html`). Les nouveautés d'une version portent
   `<span class="nouveau">Nouveau</span>` ; retirer les pastilles de l'édition
   précédente.

6. **Construction**, depuis la racine du dépôt (Chrome et Ghostscript requis) :

       python3 docs/formation/build.py

   Produit, chacun autonome : `docs/guide-utilisateur-sagi-school.html` et
   `.pdf` (plus une copie du guide seul dans `sama_assistant_hady/`), et
   `docs/manuel-formateur-sagi-school.html` et `.pdf`. Le script refuse de
   construire si le manuel formateur apparaît dans le guide utilisateur.

## Règles

- Aucune donnée d'école cliente : tout vient de `seed_demo.py`.
- Chaque chiffre cité dans le texte doit se lire sur une capture ou se
  recalculer à partir des tarifs de la démonstration.
- Regarder chaque capture avant de l'utiliser : une clé de traduction brute
  ou une carte illisible est un défaut du logiciel, à corriger à la source.
