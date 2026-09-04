# Fonctions désactivées sur l'instance de déploiement

**À annoncer, pas à découvrir en démonstration.**

`opex_intervenants` ne déclare plus `sale`, `project` ni `opex_ai_core` au
manifeste. Ces trois modules ne sont pas disponibles sur l'instance cible, et
les exiger rendait le module **non installable** — Odoo refuse un module dont
une dépendance est introuvable, et le refus est total : ni portail, ni
matching, ni workflows, pour trois fonctionnalités de bout de chaîne.

Ils sont donc résolus au moment de l'appel. Leur absence **éteint** des
fonctionnalités ; elle n'en casse aucune, et le dossier dit à chaque fois ce
qui n'a pas eu lieu.

---

## Le résumé, en une phrase

Le parcours métier est entier — de la demande client à l'évaluation de
l'intervenant. Ce qui manque est **l'émission comptable** au bout de la chaîne
et **le miroir de l'exécution dans l'outil de gestion de projet d'Odoo**. Les
deux sont des sorties vers d'autres modules, pas des étapes du processus.

---

## 1. Sans `sale` — la facturation du §29

### Ce qui ne se fait plus

| Fonction | Où elle se voyait | Ce qui se passe maintenant |
|---|---|---|
| Création de la commande de vente à la clôture | transition « Facturer et clôturer » | rien n'est émis ; une note est postée sur la mission |
| Génération de la facture client | `sale.order._create_invoices()` | aucune facture |
| Suivi du paiement (Schéma 12) | `facture_generee`, `facture_payee`, `montant_facture`, `montant_restant_du` | restent à `False` / `0,00` |
| Boutons « Commande » et « Factures » | fiche du constat de service fait | masqués |
| Jalon **Facturation** de la barre du §40 | fiche mission | s'arrête à `en_cours`, n'atteint jamais `fait` |
| Ligne « Facture payée » de la file Terminé (§43) | tableau de bord responsable | toujours vide |

### Ce qui continue de fonctionner

**Tout le §27 et le §28**, c'est-à-dire le processus lui-même :

- le constat de service fait s'ouvre à la remise des livrables ;
- les quatre points de la checklist cluster ;
- la validation cluster puis la validation client ;
- la contestation et la boucle de reprise ;
- **la règle 6 du §39** — une mission n'est pas terminée tant que les livrables
  obligatoires ne sont pas validés — qui est une condition de transition et ne
  dépend d'aucun module comptable ;
- la clôture de la mission, qui **aboutit**.

C'est la distinction à tenir en soutenance : le constat de service fait est un
**processus**, il est là ; la facturation est un **constat de ce qu'Odoo a
fait**, et c'est Odoo qui manque.

### Ce que voit le gestionnaire

À la clôture, une note est postée sur la mission :

> La mission est clôturée. **Aucune commande de vente n'a été émise** : le
> module Ventes (sale) n'est pas installé sur cette instance.
> Montant à facturer au client : **12 000,00 €**. La facturation est à établir
> hors du portail, puis à reporter sur le constat de service fait.

Et la situation de facturation affiche « **Facturation indisponible (module
Ventes absent)** », pas « Non facturée ». La distinction est volontaire : la
première phrase décrit un portail qui ne sait pas facturer, la seconde une
mission qu'on n'a pas encore facturée. Les confondre ferait chercher une
commande manquante là où c'est le module qui l'est.

---

## 2. Sans `project` — le projet d'exécution du §13

### Ce qui ne se fait plus

| Fonction | Ce qui se passe maintenant |
|---|---|
| Création du `project.project` au démarrage | rien ; une note est postée |
| Création des tâches tirées de `resultats_attendus` | aucune tâche |
| Échéances des tâches, vue calendrier native | sans objet |
| Bouton statistique « Tâches » sur l'affectation | masqué, `task_count` vaut 0 |

### Ce qui continue de fonctionner

**Toute l'Extension 8**, c'est-à-dire le suivi d'exécution réel :

- `opex.mission.deliverable` et son cycle de vie à cinq étapes ;
- les versions de livrables et le motif de refus porté par la version
  archivée ;
- les points d'avancement du §21 — temps passé, avancement déclaré, prochaine
  étape ;
- les incidents du §26 ;
- la barre du §40.

Le suivi de mission ne passait pas par `project.task` : il passe par nos
propres modèles. C'est la seule raison pour laquelle cette perte est
supportable, et c'est ce que dit la note postée au démarrage.

---

## 3. Sans `opex_ai_core` — l'assistance IA

| Fonction | Ce qui se passe maintenant |
|---|---|
| Parsing du CV (IA-1) | le dépôt fonctionne ; l'analyse part en « Analyse impossible » avec son motif |
| Proposition de rapprochement par l'IA (IA-2, temps 2) | aucune proposition |

**Le rapprochement taxonomique du temps 1 fonctionne** : correspondance exacte
sur le référentiel, puis sur la table de synonymes, puis file d'arbitrage. Il
ne demande aucun appel, et il traite la majorité des libellés d'un CV. C'était
déjà l'argument de l'IA-2 : *le module reste utile sans clé.*

---

## 4. Ce qui n'est PAS touché

À dire explicitement, parce que c'est l'essentiel du module :

- les **deux machines à états** et leurs deux définitions ;
- le **Smart Matching** et son explication de score ;
- le **pool unique** et l'écran de comparaison ;
- la **candidature Lean** et le portail public ;
- la **sélection**, l'**affectation** et le **contrat** — le contrat est un
  modèle à nous, `opex.mission.contract`, et son sous-workflow tourne ;
- les **livrables**, les **incidents**, les **évaluations**, la **réputation** ;
- les **quatre tableaux de bord** et les **seize notifications** ;
- les **neuf critères d'acceptation du §21**, qui restent tous verts sur
  `/staff/kpi` — aucun ne dépend de `sale` ni de `project`.

---

## 5. Le point qui reste bloquant, et qui n'est pas dans ce module

⚠ **`opex_intervenants` est propre, mais il ne s'installera pas seul pour
autant.** La dépendance revient par la chaîne :

```
opex_intervenants
  └── opex_innovation      →  depends: 'project'
        └── opex_membership →  depends: 'sale'
```

Vérifié : `opex_intervenants` ne déclare plus **aucun** champ dont le comodèle
soit dans `sale.`, `project.`, `product.` ou `account.` — sur ses 741 champs.
Le blocage restant est entièrement en amont, et il est du même genre :

| Module | Ce qui bloque | Volume |
|---|---|---|
| `opex_membership` | `_inherit = 'account.move'` · `Many2one('sale.order')` sur `opex.subscription` · émission de cotisation | 1 modèle hérité, 1 champ, 2 appels |
| `opex_innovation` | `Many2one('project.project')` sur `opex.innovation.accompagnement` et sur `opex.innovation.project` | 2 champs, 2 appels |

C'est le même travail que celui qui vient d'être fait ici, à une échelle plus
petite. Il n'a pas été engagé parce que ces deux modules sont présentés et
gelés : les rouvrir est une décision, pas une conséquence.

---

## 6. Comment rebrancher, le jour où `sale` sera disponible

Trois gestes :

1. remettre `'project', 'sale'` dans `depends` du manifeste ;
2. rétablir le produit de service avec son `invoice_policy = 'order'` —
   `data/mission_invoicing_data.xml` conserve le fragment. ⚠ En `'delivery'`,
   `_create_invoices()` refuserait de facturer une quantité livrée nulle et la
   facturation échouerait sur **chaque** mission ;
3. suivre les blocs marqués `REBRANCHEMENT` :

```
grep -rn "REBRANCHEMENT" models/ views/ data/ tests/
```

Chacun rappelle le code d'origine et **pourquoi** il comptait. Les deux
`@api.depends` amputés sont les plus importants : sans eux, un paiement
enregistré depuis l'écran de banque et une tâche ajoutée à un projet ne
remonteraient qu'au prochain recalcul, c'est-à-dire à un moment quelconque.

Aucune donnée n'est à migrer : `sale_order_ref` et `project_ref` conservent les
identifiants, et le produit de service reprend le même identifiant externe.

Les tests reviennent d'eux-mêmes — ils s'annoncent absents par `skipTest` tant
que le modèle n'est pas au registre, et se remettent à tourner à
l'installation, sans qu'on ait à se souvenir de les décommenter.
