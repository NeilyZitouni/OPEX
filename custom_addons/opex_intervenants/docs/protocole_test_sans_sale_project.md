# Protocole de vérification — le module sans `sale`, `project` ni `opex_ai_core`

Ce protocole vérifie deux choses distinctes, et il faut les tenir séparées :

1. **le module s'installe** sans les trois modules retirés du manifeste ;
2. **ce qui reste fonctionne**, et ce qui est éteint le dit au lieu de casser.

Ce qui est perdu est décrit dans `docs/fonctions_desactivees.md`.

---

## 0 — Installation sur une base neuve

```
cd C:\Users\User\Desktop\stageDeltaLog

.\venv\Scripts\python.exe .\odoo\odoo-bin -c odoo.conf -d opex_demo ^
    -i opex_intervenants ^
    --http-port=8072 --stop-after-init --log-level=warn
```

Attendu : **aucune ligne `WARNING` ni `ERROR` d'Odoo**, et le processus
se termine avec un code de sortie 0.

Puis pour lancer le serveur :

```
.\venv\Scripts\python.exe .\odoo\odoo-bin -c odoo.conf -d opex_demo ^
    --http-port=8072 --limit-time-real=0
```

Le port 8072 n'est pas une préférence : voir la règle 19 du CLAUDE.md. Et
`--limit-time-real=0` évite que le serveur meure au bout de deux minutes quand
un onglet reste ouvert.

⚠ **Sur cette machine, `sale` et `project` seront quand même installés.** Ce
n'est pas un défaut du module : ils sont amenés par `opex_membership` et
`opex_innovation`, dont `opex_intervenants` dépend. Voir le §5 de
`fonctions_desactivees.md`. Pour vérifier ce qui est réellement installé :

```
.\venv\Scripts\python.exe .\odoo\odoo-bin shell -c odoo.conf -d opex_demo ^
    --http-port=8079 --shell-interface=python
>>> env['ir.module.module'].search([('name','in',['sale','project'])]).mapped('state')
```

## 1 — Le manifeste ne les redemande pas

```
.\venv\Scripts\python.exe .\odoo\odoo-bin -c odoo.conf -d opex_demo ^
    -u opex_intervenants --test-enable ^
    --test-tags "/opex_intervenants:TestOptionalBackends" ^
    --http-port=8072 --stop-after-init --log-level=test
```

- [ ] 9 tests, 0 échec.

Deux d'entre eux sont des gardes et méritent d'être connus :

- `test_the_manifest_declares_neither_sale_nor_project` rougit si l'un des
  trois noms revient dans `depends`. Il reviendrait sans bruit : ajouter un
  nom à une liste pour faire marcher un écran est le geste le plus naturel du
  monde, et le module redeviendrait non installable sans qu'on le sache ;
- `test_no_model_reaches_these_models_outside_the_bridge` lit le source de
  tous les modèles, docstrings et commentaires retirés, et refuse un
  `self.env['sale.order']` écrit ailleurs que dans le pont. Sans lui, les
  tests de dégradation resteraient verts pendant qu'un chemin non protégé
  casserait à l'installation.

## 2 — La suite complète

```
.\venv\Scripts\python.exe .\odoo\odoo-bin -c odoo.conf -d opex_demo ^
    -u opex_intervenants --test-enable ^
    --test-tags "/opex_intervenants" ^
    --http-port=8072 --stop-after-init --log-level=test
```

- [ ] 0 échec.

Le nombre de tests joués **dépend de ce qui est installé** :

| Base | Total | Annoncés absents | Mesuré ? |
|---|---|---|---|
| `sale` + `project` + `opex_ai_core` | 437 | 0 | oui — `opex_mis_e1` |
| `sale` + `project`, sans `opex_ai_core` | 405 | 0 (les tests IA passent par le pont) | oui — `opex_nodeps` |
| sans `sale` ni `project` | 437 | 6 attendus | **non** — voir ci-dessous |

⚠ La troisième ligne est une **projection, pas une mesure**. Aucune base de ce
poste ne permet de l'établir : `sale` et `project` y sont toujours installés,
amenés par `opex_membership` et `opex_innovation`. Les six `skipTest` sont
posés et lisibles dans le source ; leur déclenchement effectif se constatera au
premier déploiement sur l'instance cible.

Les six qui s'annoncent absents portent sur la facturation du §29 et sur le
projet d'exécution du §13. Ils ne sont **pas supprimés** : ils décrivent ce que
le module fait quand les modules sont là, et se remettent à tourner
d'eux-mêmes le jour de l'installation. Un `skipTest` est visible dans la
sortie ; un test effacé ne l'est pas.

## 3 — Le parcours métier, à l'écran

C'est le cœur de la vérification : **le processus doit être entier**.

Se connecter en gestionnaire des missions (`group_mission_manager`).

- [ ] **Missions → Appels à mission** : créer un appel, le qualifier, le
      publier. La statusbar avance.
- [ ] **Matching** : lancer le matching, lire un score et son explication.
      Vérifier qu'un candidat écarté par un critère éliminatoire est
      **absent**, pas mal noté.
- [ ] **Pool** (`/staff/missions/<id>/pool`) : les candidatures des deux
      canaux, dans le même écran, avec la même forme de ligne.
- [ ] **Sélection** : retenir une candidature. L'affectation est créée, le
      contrat et l'ordre de mission sont générés.
- [ ] **Contrat** : dérouler le sous-workflow jusqu'à « Contrat validé ».
- [ ] **Démarrage** : « Démarrer la mission ». La mission passe bien à
      `in_progress`.
- [ ] **Livrables** : déposer, faire corriger, valider. Le motif de refus est
      sur la version archivée.
- [ ] **Service fait** : cocher les quatre points du cluster, valider cluster
      puis client.
- [ ] **Clôture** : « Facturer et clôturer ». La mission passe à `closed`.
- [ ] **Évaluation** : remplir une grille, la valider. La réputation de
      l'intervenant bouge.

Aucune de ces étapes ne dépend des modules retirés.

## 4 — Ce qui est éteint le dit

C'est le point que le §3 ne couvre pas, et le seul qu'on risque de découvrir
en démonstration.

⚠ Ces deux vérifications ne sont observables **que sur une instance où `sale`
et `project` sont réellement absents**. Sur le poste de développement, elles
sont couvertes par `TestOptionalBackends`, qui simule l'absence au niveau du
pont — c'est-à-dire au seul endroit par lequel le module y accède.

### Au démarrage de la mission, sans `project`

- [ ] la mission passe quand même à `in_progress` ;
- [ ] le fil de discussion porte une note qui **nomme le module** (« Projet
      (project) ») et **dit où se fait le suivi à la place** (onglet
      Exécution) ;
- [ ] sur l'affectation, le bouton « Tâches » est masqué et le champ
      « Projet d'exécution » est remplacé par un encart qui explique pourquoi
      il est vide.

Un champ vide ne dit rien ; l'encart, lui, dit ce qui manque.

### À la clôture, sans `sale`

- [ ] la mission passe quand même à `closed` ;
- [ ] le fil porte une note qui nomme « Ventes (sale) », **rappelle le montant
      à facturer**, et dit que la facturation est à établir hors du portail ;
- [ ] sur la fiche mission, « Situation de facturation » affiche
      **« Facturation indisponible (module Ventes absent) »** — et non
      « Non facturée » ;
- [ ] les montants facturés ne s'affichent pas. Un « 0,00 € » se lirait comme
      un impayé ;
- [ ] sur le constat, les boutons « Commande » et « Factures » sont masqués.

### Sans `opex_ai_core`

- [ ] **Capital des intervenants → CV déposés** : le dépôt fonctionne, l'état
      passe à « Analyse impossible » après le cron, avec son motif ;
- [ ] **Taxonomie** : un libellé qui correspond exactement au référentiel ou à
      un synonyme est rapproché **sans appel** ; les autres partent en file
      d'arbitrage. C'est le temps 1 de l'IA-2, et il ne demande aucune clé.

## 5 — Les neuf critères du §21

```
/staff/kpi
```

- [ ] les neuf sont en vert.

Aucun ne dépend de `sale` ni de `project` — le sixième, « la sélection
déclenche contractualisation et exécution », vérifie l'existence de la
définition `mission_contract`, qui est un modèle à nous.

C'est la vérification à faire en dernier, et c'est celle à montrer : elle est
calculée à l'exécution, pas recopiée d'un tableau.

---

## Le retour en arrière

Le jour où `sale` sera disponible :

```
grep -rn "REBRANCHEMENT" models/ views/ data/ tests/
```

Chaque bloc rappelle le code d'origine et pourquoi il comptait. Aucune donnée
n'est à migrer. Voir le §6 de `docs/fonctions_desactivees.md`.
