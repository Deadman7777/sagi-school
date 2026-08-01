# 9 — Documents PDF

Reçus, bulletins scolaires, bulletins de paie, certificats, états financiers,
listes : tout ce que l'école imprime est produit par **xhtml2pdf** à partir d'un
gabarit Django.

## Où c'est

```
backend/templates/pdf/
├── base.html                 en-tête, pied, styles communs — hérité par tous
├── fonts/                    DejaVuSans.ttf, Amiri-Regular.ttf
├── recu_paiement.html        reçu A4
├── recu_ticket.html          reçu 80 mm (imprimante thermique)
├── bulletin.html             bulletin de notes
├── bulletin_paie.html        bulletin de paie
├── certificat_scolarite.html
├── fiche_eleve.html · situation_eleve.html · parcours_eleve.html
├── eleves.html · liste_classe.html
├── journal.html · grand_livre.html · balance.html
├── bilan.html · compte_resultat.html · tableau_flux.html · notes_annexes.html
├── budget.html · charges.html · investissement.html
├── gmrf_natt.html · gmrf_pret.html
└── rapport_daara.html        rapport de mémorisation, bilingue arabe-français
```

Les vues qui les rendent : `apps/comptabilite/pdf_views.py`,
`apps/gmrf/pdf_views.py`, et des vues dédiées dans `apps/eleves`,
`apps/paiements`, `apps/academique`, `apps/rh`, `apps/daara`.

## Pourquoi xhtml2pdf et pas WeasyPrint

Le produit utilisait WeasyPrint, qui rend bien mieux. Il a été abandonné parce
qu'il dépend de bibliothèques système (Cairo, Pango, GDK-PixBuf) **impossibles à
embarquer proprement dans un installateur Windows**. xhtml2pdf est du Python pur :
il s'installe avec `pip` et suit l'application partout.

Le prix à payer est un moteur de rendu limité. D'où les règles qui suivent.

## Les règles de xhtml2pdf

Elles ne sont pas négociables : chacune vient d'un document cassé en production.

**Pas de tableaux imbriqués.** Un `<table>` dans un `<td>` produit une mise en
page aléatoire ou une page blanche. Utilisez des tableaux successifs.

**Pas de flexbox, pas de grid, pas de `position`.** Le moteur ne les connaît pas.
La mise en page se fait avec des tableaux — comme en 2003.

**Les largeurs en pourcentage n'incluent pas le remplissage.** xhtml2pdf
**ajoute** le `padding` à la largeur au lieu de l'y comprendre. Au-delà de sept
colonnes, la dernière sort de la page. `base.html` fournit une classe `.dense`
qui réduit le remplissage pour que la somme tienne dans la largeur utile.

**Les styles posés sur `<tr>` sont ignorés.** Un `background` ou un `color`
déclaré sur une ligne est écrasé par le CSS des cellules. **Stylez toujours les
`<td>`**, jamais le `<tr>` — c'est ce qui rendait les lignes de totaux
illisibles, texte clair sur fond clair.

**Évitez les polices à chasse fixe et les couleurs claires.** Le rendu à
l'impression est plus faible qu'à l'écran ; un gris qui passe sur un moniteur
devient illisible sur papier.

## Le piège des commentaires Django

```django
{# un commentaire
   sur plusieurs lignes #}
```

**Ce commentaire ressort dans le PDF.** La syntaxe `{# … #}` n'est mono-ligne
que dans certains contextes de rendu ; ici, le contenu fuit dans le document.
Utilisez `{% comment %}` … `{% endcomment %}`, ou pas de commentaire du tout.

> **Corollaire, et c'est la règle la plus importante de ce document : après
> toute modification d'un gabarit PDF, générez le document et REGARDEZ-LE.**
> Aucun test unitaire ne détecte une mise en page cassée. Le rendu se vérifie à
> l'œil.

```bash
# Générer et ouvrir un PDF depuis le shell Django
./venv/bin/python manage.py shell -c "
from rest_framework.test import APIClient
from apps.users.models import User
from apps.paiements.models import Paiement
c = APIClient(); c.force_authenticate(user=User.objects.get(email='dir@test.sn'))
p = Paiement.objects.first()
r = c.get(f'/api/paiements/paiements/{p.id}/recu-pdf/')
open('/tmp/recu.pdf','wb').write(r.content)"
```

Puis `pdftoppm -png -r 110 /tmp/recu.pdf /tmp/recu` pour l'examiner page par page.

## Logo et identité de l'établissement

Le logo est stocké **en base**, dans `Tenant.logo`, sous forme de data URI base64
(`data:image/png;base64,...`). Ce choix permet de fonctionner à l'identique en
local et en cloud, et xhtml2pdf sait embarquer un data URI directement.

`base.html` reprend automatiquement le logo, le nom, la ville, le RCCM, le NINEA
et le numéro d'autorisation d'ouverture. **Ne les recopiez pas dans un gabarit
enfant** : ils y étaient dupliqués et le nom de l'école apparaissait deux fois.

## Arabe et documents bilingues

`rapport_daara.html` mêle arabe et français. Trois éléments le rendent possible :

- la police **Amiri** (`templates/pdf/fonts/Amiri-Regular.ttf`, licence OFL) ;
- `arabic-reshaper`, qui recompose les formes contextuelles des lettres ;
- `python-bidi`, qui applique l'algorithme bidirectionnel.

Sans ces deux bibliothèques, l'arabe sort en lettres isolées et à l'envers.

## Ajouter un document

1. Créer le gabarit dans `templates/pdf/`, en étendant `base.html`.
2. Écrire la vue qui construit le contexte et rend le PDF, à côté des autres
   vues PDF de l'application.
3. **Générer le document et le regarder.** Sur A4 et, si l'école imprime des
   reçus, sur 80 mm.
4. Vérifier qu'il tient dans la largeur avec un jeu de données réel — pas trois
   lignes de test : une école qui a 200 élèves et des noms longs.
