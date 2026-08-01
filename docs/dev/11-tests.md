# 11 — Tests

**636 fonctions de test réparties dans 50 modules**, dont environ **590
exécutées** par `manage.py test apps` — l'écart vient des tests de `core/`, hors
du chemin `apps`, et des deux modules qui échouent au chargement (voir plus bas).
Comptez une centaine de secondes.

Ce n'est pas une couverture exhaustive : c'est une collection de **garde-fous
contre des bugs qui sont réellement survenus**.

## Lancer les tests

```bash
cd backend
./venv/bin/python manage.py test apps                    # tout
./venv/bin/python manage.py test apps.comptabilite       # une application
./venv/bin/python manage.py test apps.dashboard.tests_coherence_resultat
```

Sur SQLite (instance jetable, document 2) :

```bash
export PYTHONPATH=/tmp/demo:$PWD DJANGO_SETTINGS_MODULE=demo_settings
./venv/bin/python manage.py test apps --settings=demo_settings
```

### Deux erreurs attendues

```
ERROR: eleves.tests (unittest.loader._FailedTest)
ERROR: gmrf.tests (unittest.loader._FailedTest)
```

Ces deux-là sont **préexistantes et sans rapport avec votre code** : le
chargeur de tests découvre ces modules comme modules de premier niveau
(`gmrf.tests` au lieu de `apps.gmrf.tests`), et les modèles se plaignent alors
de ne pas avoir de `app_label`. Vérifiez qu'il n'y en a que deux, et que le
nombre de tests exécutés n'a pas baissé.

`config.settings.local` exclut la debug-toolbar quand `test` est dans
`sys.argv` : elle force `DEBUG=False` et casse la collecte.

## La convention de nommage

Un fichier `tests.py` par application **plus** des modules dédiés, nommés d'après
le comportement qu'ils protègent :

```
apps/comptabilite/tests_compte_resultat_net.py
apps/comptabilite/tests_neutralisation.py
apps/comptabilite/tests_annulations_orphelines.py
apps/comptabilite/tests_bilan_equilibre.py
apps/dashboard/tests_coherence_resultat.py
apps/dashboard/tests_alertes_coherence.py
apps/eleves/tests_echeancier.py
apps/eleves/tests_matricules.py
apps/paiements/tests_no_piece_sequence.py
apps/tenants/tests_deux_ecoles.py
core/test_tenant_isolation.py
```

Le nom doit dire **ce qui est protégé**, pas quel fichier est testé. Quand un
bug est corrigé, le test qui l'empêche de revenir porte son nom.

## La règle qui compte : tester la cohérence, pas des montants

C'est la leçon la plus chère de ce produit. Trois écrans différents affichaient
« le résultat de l'exercice », chacun avec son propre calcul, et les trois
divergeaient. Aucun test ne l'a vu, parce que chacun vérifiait un montant en dur
sur son écran.

**Un test utile compare deux écrans**, il ne relit pas une constante :

```python
def test_meme_resultat_net_sur_les_deux_ecrans(self):
    self._ecritures_d_une_annee()
    kpis = self.client.get('/api/dashboard/kpis/')
    cr   = self.client.get('/api/comptabilite/compte-resultat/')
    self.assertEqual(kpis.data['kpis']['resultat_net'], cr.data['resultat_net'])
```

Ce test survit à un changement de barème, de tarif ou de jeu de données. Un
`assertEqual(resultat, 26_553_506)` ne survit à rien et ne prouve rien.

Voir `apps/dashboard/tests_coherence_resultat.py` pour le patron complet.

## Le test à deux écoles

`apps/tenants/tests_deux_ecoles.py` monte **deux établissements aux
caractéristiques différentes** et vérifie que la règle tient pour les deux.

C'est la parade à la classe de bug la plus fréquente du produit : « ça marche
chez une école, pas chez l'autre » (document 7). Une règle vérifiée sur une seule
école ne prouve rien — la deuxième a un exercice clôturé, des pièces `REP-`, des
élèves sans classe, ou un historique migré.

**Étendez ce fichier** plutôt que d'ajouter un test sur une école isolée.

## Écrire un test qui touche à l'argent

Le patron, tiré des tests existants :

```python
class MonTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nom='Les Palmiers')
        self.user = User.objects.create_user('dir@x.sn', 'x', nom='D',
                                             role='ADMIN_ECOLE', tenant=self.tenant)
        self.client.force_authenticate(self.user)
        self.ex = Exercice.objects.create(tenant=self.tenant, annee_scolaire='2025-2026',
                                          cloture=False, date_debut=..., date_fin=...)

    def _je(self, compte, debit, credit, source):
        return JournalEntry.objects.create(
            tenant=self.tenant, exercice=self.ex, no_piece='X',
            date_ecriture=self.ex.date_debut, no_compte=compte,
            debit=debit, credit=credit, source=source, ordre=1)
```

Trois assertions à envisager systématiquement :

1. **Débit = crédit** sur la pièce produite.
2. **La grandeur affectée reste identique** entre les écrans qui l'affichent.
3. **L'opération est idempotente** si elle est censée l'être (report, réparation,
   neutralisation) : la jouer deux fois donne le même état.

## Vérifier qu'un test sert à quelque chose

Un test qui passe avant **et** après votre correction ne protège rien. Le
réflexe, avant de committer :

```bash
git stash          # met de côté la correction
./venv/bin/python manage.py test apps.mon.test_module   # doit ÉCHOUER
git stash pop
./venv/bin/python manage.py test apps.mon.test_module   # doit PASSER
```

Si le test passe dans les deux cas, il ne teste pas ce que vous croyez.

## Ce qui n'est pas couvert par les tests

À vérifier à la main, systématiquement :

- **Le rendu des PDF** — aucun test ne détecte une mise en page cassée
  (document 9).
- **Le frontend** — il existe quelques `.spec.ts`, la couverture est faible.
- **L'installation Windows** — testez sur une machine virtuelle vierge avant
  toute livraison qui touche à Electron ou aux dépendances Python.
- **Les traductions** — une clé manquante s'affiche en brut à l'écran, aucun test
  ne le voit.
