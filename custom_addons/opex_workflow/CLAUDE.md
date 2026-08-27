# CLAUDE.md — `opex_workflow` + `opex_innovation`

**Moteur générique CEO Smart Workflow & Module 2 — OPEX Innovation (Innovation Booster)**

---

## ⚠️ LIRE INTÉGRALEMENT AVANT TOUTE MODIFICATION

Ce document couvre **deux modules Odoo 19 distincts**, développés dans cet ordre :

| Module | Rôle | Contient |
|---|---|---|
| `opex_workflow` | **Moteur générique** — aucune logique métier | Extensions 1 à 8 |
| `opex_innovation` | **Module 2 du portail** — le métier de l'Innovation Booster | Extensions 9 à 20 |

Le module `opex_membership` (Module 1) **existe déjà, fonctionne, et est sur le point
d'être présenté à l'encadrant**. Il est gelé. Aucune extension ci-dessous ne le
modifie ; `opex_innovation` en dépend et étend `res.partner`, sans jamais toucher à
ses modèles ni à son workflow.

### La règle qui gouverne tout le reste

> **Le moteur ne sait rien du métier. Le métier ne code aucun workflow.**

Si tu écris dans `opex_workflow` une ligne mentionnant « projet », « investisseur »,
« pitch deck » ou « comité d'évaluation », tu casses sa raison d'être.

Si tu écris dans `opex_innovation` un champ `state = fields.Selection([...])`
décrivant l'avancement du projet, tu casses la démonstration entière. **Le modèle
`opex.innovation.project` n'a pas de champ d'état.** Son état, c'est
`workflow_instance_id.current_stage_id`, piloté par une configuration.

---

## Le contexte de la répartition (mail Dr. Babaci, 22/08)

> 1. Partie workflow tel que défini : **Kassab** — implémenter texto — module à part
> 2. Partie 2 : **un module générique pour créer un workflow similaire (Zitouni)** — module à part
>
> 3-4 jours de travail avec IA

Il y a donc deux versions du **même** processus, construites en parallèle :

- **Version texto (Kassab)** — `opex_crowdfunding` : le workflow Smart Crowdfunding
  codé en dur, états et transitions écrits en Python. Rapide, direct, non
  réutilisable.
- **Version générique (Zitouni, ce document)** — `opex_workflow` + `opex_innovation` :
  un moteur configurable, dont OPEX Innovation est la **première instance complète**
  et Smart Crowdfunding la **seconde**, obtenue sans une ligne de Python
  supplémentaire.

C'est la comparaison des deux qui fait la valeur du travail. Kassab démontre le
processus, toi tu démontres la capacité à en produire n'importe lequel.

### Le critère d'acceptation — section 18 du document Smart Crowdfunding

> « Ajoutez une étape **Demo Day** entre Accompagnement et Matching Investisseurs.
> Elle nécessite l'accord du CEO, une présentation Pitch Deck et une note ≥ 70/100. »
> Réalisable **depuis le configurateur, sans modifier le code Python du moteur.**

Chaque décision technique se tranche en se demandant : est-ce que ça rend ce test
plus ou moins réalisable ?

### Contrat d'interface avec Kassab — à convenir avant de coder

Aucune dépendance croisée dans les `__manifest__.py` : les deux modules s'installent
séparément.

| | Kassab | Zitouni |
|---|---|---|
| Modules | `opex_crowdfunding` | `opex_workflow`, `opex_innovation` |
| Préfixe modèles | `opex.crowdfunding.*` | `opex.workflow.*`, `opex.innovation.*` |
| Préfixe groupes | `opex_crowdfunding.group_*` | `opex_workflow.group_*`, `opex_innovation.group_*` |

**Codes d'étapes communs**, à utiliser à l'identique des deux côtés :

```
depot_express · pre_analyse · dossier_progressif · quality_gate · etude_decision
matching_financier · accompagnement · mise_en_relation · decision_financeur · closing
```

**Noms de champs métier communs** : `score` (Integer, /100), `ceo_approval`
(Boolean), et un moyen homogène de tester la présence d'un document.

Payoff : en fin de projet, **son** objet métier tourne sur **ton** moteur sans
recoder son workflow. Un quart d'heure de coordination, la démonstration de
généricité la plus forte qu'on puisse faire devant un jury.

---

## Documents de référence — dossier `docs/`

À lire avant de coder. En cas de divergence avec ce fichier sur un point de
**contenu fonctionnel** (libellé d'écran, ordre des champs, texte affiché), le PDF
fait foi ; ce fichier donne la traduction technique.

| Fichier | Autorité |
|---|---|
| `module2_innovation_ux.pdf` | **Référence principale du métier.** 37 sections + 11 schémas |
| `instance_smart_crowdfunding.md` | La seconde instance ; sections 17 et 18 = capacités attendues + test |
| `infographie_scf.png` | **Modèle conceptuel de données du moteur** — fait foi pour le nommage des entités |
| `portail_digital_vision.pdf` | Vision globale, les 3 domaines, le socle commun |
| `product_backlog.md` | US-06 à US-08, US-17, US-18 (Module 2) |
| `module1_ux_valide.pdf` | Module 1, pour comprendre les conventions déjà retenues |

---

## Règles transversales — héritées de `opex_membership`

Payées cher sur le module précédent. Elles s'appliquent ici sans discussion.

### 1. Collisions de nommage avec l'API interne d'Odoo

`category_id`, `_register`, `state`, `sequence`, `name_get`, `stage_id` sont déjà
pris à divers endroits. Une collision est souvent **masquée silencieusement** et
échoue au runtime, pas au chargement.

Conséquences concrètes ici :
- Tous les champs du mixin sont préfixés `workflow_`. Sans exception.
- Ne jamais ajouter `category_id` sur `res.partner` (champ natif des tags).
- Ne pas nommer un champ `stage_id` sur un modèle métier : `project.project` et
  plusieurs modèles natifs l'utilisent déjà.

#### 1 bis. La règle vaut aussi **entre nos propres modules** — controllers portail

Découvert le 26/08 en cherchant pourquoi `/my/projects` renvoyait 404.

`_generate_routing_rules()` (`odoo/http.py`) fusionne **toutes les classes
feuilles d'un même arbre de controller** en une seule classe dynamique :

```python
Ctrl = type(name, tuple(reversed(leaf_controllers)), {})
```

`portal.CustomerPortal` est l'ancêtre commun de `opex_membership`,
`opex_innovation`, `opex_crowdfunding` **et** du natif `project`. Leurs
controllers n'en forment donc qu'un seul à l'exécution. Conséquence : pour un
**nom donné**, il n'existe qu'un exemplaire, celui qui gagne la MRO —

- **une méthode de route** : ses URL disparaissent purement et simplement du
  routing map. `portal_my_projects` était défini dans `project`,
  `opex_crowdfunding` et `opex_innovation` ; seul `/my/innovation` a survécu,
  `/my/projects` est tombé en 404 — y compris celui du module natif.
- **un helper ou un attribut de classe** : c'est l'implémentation d'un autre
  module qui s'exécute. Mesuré sur la classe fusionnée : `_current_draft`,
  `_own_project`, `_save_step` et `_STEP_FIELDS` résolvaient tous vers
  `opex_innovation`, `_render_step` vers `opex_membership`, et
  `_items_per_page` vers `opex_membership.ClusterPortal`.

**Ni erreur, ni avertissement, ni au chargement ni au runtime.** Le module
paraît installé, ses templates existent, ses imports sont bons — et la moitié
de son portail exécute le code du voisin. Aucun test unitaire ne l'attrape :
seul le routing map réel (`env['ir.http'].routing_map()`) le montre.

**La ligne de partage, c'est `super()`.** Une surcharge coopérative d'un hook
natif — `_prepare_home_portal_values()`, qui commence par
`super()._prepare_home_portal_values(counters)` — traverse la MRO de la classe
fusionnée et **s'exécute en chaîne** : `opex_membership` et `opex_innovation`
la surchargent tous les deux, et les deux tournent. C'est le mécanisme prévu,
il n'y a rien à corriger là. Le dégât ne concerne que les méthodes qui
n'appellent **pas** `super()` — une route, un helper, une constante définie
indépendamment dans deux modules : la première de la MRO existe, les autres
n'existent tout simplement pas.

Règle : **tout ce qu'un controller portail définit sans passer par `super()`
est préfixé au nom du module** — routes (`/my/<module>/…`), méthodes
(`portal_<module>_*`), helpers (`_<module>_*`), constantes (`_<MODULE>_*`).
Les hooks natifs qu'Odoo appelle lui-même gardent leur nom, à condition de
relayer `super()`.

Vérification, sur une base à jour :

```python
router = env['ir.http'].routing_map(key=1)
sorted(str(r.rule) for r in router.iter_rules() if '/my/' in str(r.rule))
```

### 2. Un contrôle d'accès = une seule fonction, jamais recopié

Ici : « cet utilisateur peut-il déclencher cette transition ? » existe en **un seul
endroit**, `opex.workflow.instance._check_transition_allowed()`, appelé par le
back-office, le wizard, le portail et les tests. Une vérification dupliquée finit
par en oublier une occurrence — et c'est celle-là qui reçoit la requête forgée.

#### 2 bis. Un `search()` dans un gabarit fait tomber la page d'un autre

Découvert le 26/08 : un compte du comité d'évaluation recevait un **403 sur
`/my`**, l'accueil du portail — `You are not allowed to access 'Projet Smart
Crowdfunding' (opex.crowdfunding.project) records`. Ni le comité, ni `/my`
n'ont pourtant quoi que ce soit à voir avec le module Crowdfunding.

En cause, une tuile greffée sur `portal.portal_my_home` qui comptait dans le
gabarit :

```xml
<t t-set="count"
   t-value="request.env['opex.crowdfunding.project'].search_count(
                [('partner_id', '=', request.env.user.partner_id.id)]) or ''"/>
```

Un `search()` / `search_count()` posé en QWeb **s'exécute sous l'identité du
visiteur**. Sans ligne `ir.model.access` pour son groupe, il lève `AccessError`
au milieu du rendu, et c'est **la page entière** qui part en 403 — pas la tuile.
Une greffe sur un gabarit partagé fait donc tomber la page de tous les autres
modules. Aucun test unitaire ne l'attrape : il faut charger `/my` avec un compte
de chaque rôle.

**Le contrôle d'accès vit dans le controller, jamais dans le gabarit.** Le
compteur se calcule dans `_prepare_home_portal_values()`, gardé par
`has_access('read')` qui répond au lieu de lever :

```python
values['x_count'] = X.search_count(domain) if X.has_access('read') else 0
```

Corollaire : `sudo()` dans un gabarit n'est pas la parade. Il empêche l'erreur
en supprimant *tout* contrôle — ACL et `ir.rule` — sans laisser de trace. Deux
tuiles du même module le faisaient ; elles comptent désormais dans le controller
sans `sudo()`, les `ir.rule` bornant déjà le résultat au contact connecté.

Reste admis dans un gabarit : l'introspection de champs
(`dict(record._fields['state'].selection)`), et l'appel d'une méthode métier qui
porte elle-même sa garde (`user._is_innovation_staff()`,
`partner.sudo().opex_can_apply_membership()`) — ni l'une ni l'autre n'interroge
un modèle sous une identité qui pourrait ne pas y avoir droit.

#### 2 ter. Le contrat de `/my/counters` est une condition de fonctionnement

Payé le 26/08, dans la foulée du correctif de 2 bis. Un compteur de tuile
portail se déclare des deux côtés :

- **gabarit** : `<t t-set="placeholder_count" t-value="'x_count'"/>` pose le
  nœud `[data-placeholder_count='x_count']` ;
- **controller** : `_prepare_home_portal_values()` ne renseigne `values['x_count']`
  **que si `'x_count' in counters`**.

Les deux, ou aucun. `portal_home_counters.js` (lignes 33-37) fait, pour
**chaque clé reçue** :

```js
this.el.querySelector(`[data-placeholder_count='${counterName}']`).textContent = …
```

Une clé sans nœud ⇒ `null.textContent` ⇒ la boucle lève ⇒ le `Promise.all`
est rejeté ⇒ **tout le JavaScript de l'accueil meurt** : aucun compteur
rempli, aucune tuile démasquée, et une boîte « Oops! » par-dessus la page.
Pas seulement la tuile fautive, pas seulement son module, pas seulement le
rôle concerné : **tous les utilisateurs**, sur `/my` et `/my/home`.

Trois compteurs calculés sans regarder `counters` ont suffi. Le `if … in
counters` des modules natifs n'est donc pas un style d'écriture à imiter,
c'est ce qui fait tenir la page.

#### 2 ter bis. Un `placeholder_count` n'appartient qu'à une seule tuile

Corollaire du précédent, payé le 27/08. Deux tuiles d'`opex_innovation`
— « mes missions » et « mes opportunités » — déclaraient le même
`innovation_opportunity_count`, au motif raisonnable que les deux écrans lisent
les mêmes propositions.

`portal_home_counters.js` résout chaque compteur ainsi :

```js
const el = this.el.querySelector(`[data-placeholder_count='${counterName}']`);
```

`querySelector` renvoie le **premier** nœud, jamais les deux. La seconde tuile
n'était donc pas démasquée au premier chargement ; elle n'apparaissait qu'au
suivant, quand `force_show` la révélait depuis
`request.session['portal_counters']`. Un utilisateur qui arrive sur son espace
pour la première fois ne voit pas la moitié de ce qui le concerne, et
l'anomalie s'efface d'elle-même dès qu'on recharge — donc dès qu'on cherche à
la reproduire.

Règle : **un compteur, une tuile, un domaine**. Deux écrans qui montrent des
choses différentes ont deux compteurs, même s'ils lisent la même table — et le
domaine du compteur est exactement celui de l'écran qu'il annonce, sans quoi la
tuile promet un nombre que la page ne contient pas.

Le balayage qui le vérifie, sur les trois modules :

```bash
grep -rn "placeholder_count\"" --include='*.xml' opex_*/views/ | sort
```

Aucun compteur ne doit apparaître deux fois.

#### 2 quater. Le spinner qui reste EST un symptôme, pas un détail

`portal_home_counters.js` supprime `.o_portal_doc_spinner` **après** le
`Promise.all` (ligne 49). Un spinner encore visible sur l'accueil du portail
signifie donc qu'une promesse a été rejetée — le JS est mort avant la fin.

Il était présent sur mes propres captures pendant deux tours sans que je le
relève. **Un spinner figé sur une capture ⇒ ouvrir la console avant de
conclure quoi que ce soit.**

#### 2 quinquies. Un test HTTP ne verra jamais une erreur JavaScript

`requests.get()` et `url_open()` d'`HttpCase` lisent le HTML **rendu par le
serveur**. Ils voient les tuiles, leurs classes, leurs liens — et passent au
vert pendant qu'une exception JS vide la page dans un vrai navigateur. La
capture d'écran d'un HTML sauvegardé ne vaut pas mieux : les RPC ne partent
pas, l'erreur ne se produit pas.

Un écran portail qui dépend de JavaScript — compteurs, tuiles démasquées,
interactions `Colibri` — se vérifie **dans un navigateur, console ouverte,
avec une vraie session**. Le reste ne prouve que le HTML.

#### 2 sexies. `portal_searchbar` n'affiche pas toujours le `title` qu'on lui pose

`portal.portal_searchbar` (`odoo/addons/portal/views/portal_templates.xml:311`) :

```xml
<t t-if="breadcrumbs_searchbar">
    <t t-call="portal.portal_breadcrumbs"/>
</t>
<span t-else="" class="navbar-brand mb-0 h1 me-auto" t-esc="title or 'No title'"/>
```

Le titre n'est rendu que dans la branche **`t-else`**. Une page qui pose
`breadcrumbs_searchbar = True` — la plupart des nôtres — affiche son fil
d'Ariane à la place, et son `<t t-set="title">` ne sert **à rien**. Le libellé
visible est alors celui du `portal.portal_breadcrumbs`, à modifier là.

Trouvé le 27/08 en renommant l'écran `/my/crowdfunding` : le titre changé dans
la searchbar n'apparaissait nulle part, et le gabarit avait pourtant l'air
juste. **Un libellé qui ne s'affiche pas alors que le gabarit le pose : lire la
page rendue, pas le gabarit.**

### 3. « Présent dans le HTML » ≠ « visible à l'écran »

Un bouton de transition rendu mais masqué, un bloc caché par un `t-if` sur un
référentiel vide, une tuile portail en `d-none` : un test qui vérifie
`'texte' in response.body` passe alors que l'utilisateur ne voit rien. Vérifie le
rendu réel avec de vraies données. Quand un état vide est légitime, affiche un
message explicite plutôt que de masquer silencieusement.

### 4. Sous-type de message : `mail.mt_note` pour l'interne

Bug déjà rencontré et corrigé sur `opex_membership` : des messages de coordination
interne partaient par email chez le candidat. Tout `message_post()` destiné au
personnel utilise `mail.mt_note`. `mail.mt_comment` uniquement pour ce que le
porteur doit réellement recevoir.

### 5. Spécificités Odoo 19 déjà rencontrées

- `res.groups.category_id` n'existe plus → `res.groups.privilege`
- `attrs` et `states` n'existent plus dans les vues → `invisible="..."` /
  `readonly="..."` directement sur le champ
- Vérifier `pip`/dépendances : ne pas ajouter `documents` au manifeste (absent de
  certaines installations Community)

### 6. Un test vert qui ne prouve rien — trois variantes du même piège

Les trois ont été rencontrées pendant le Bloc B. Chaque fois, la suite était au
vert et ne vérifiait rien. C'est le mode de défaillance le plus coûteux du
projet : un test rouge se corrige, un test vert menteur se découvre en
démonstration.

**a) Une assertion négative ne vaut que précédée d'une assertion positive.**

```python
self.assertNotIn("score", response.text)          # passe sur une page 500
```

Le test de confidentialité des avis passait au vert sur une erreur serveur : la
page d'erreur ne contient évidemment pas les scores des autres évaluateurs.
Toujours prouver d'abord que la page a bien été rendue :

```python
self.assertEqual(response.status_code, 200)
self.assertIn("Mon évaluation", response.text)    # la page est bien là
self.assertNotIn("score", response.text)          # et elle ne fuit pas
```

Vaut pour tout `assertNotIn`, `assertFalse(search(...))`, `assertEqual(len(x), 0)` :
l'absence n'est une preuve que si la présence de l'entourage est établie.

**b) `mapped()` sur un Many2one déduplique.**

`instance.history_ids.mapped('to_stage_id.code')` passe par un recordset
intermédiaire : deux passages par la même étape n'en font qu'un. Un test censé
vérifier une boucle de remédiation — retour au porteur, correction, nouvelle
soumission — ne vérifiait donc rien du tout. Pour compter des passages, écrire
une compréhension :

```python
visited = [h.to_stage_id.code for h in instance.history_ids.sorted('id')]
self.assertEqual(visited.count('accompagnement'), 2)
```

Règle : `mapped()` répond à « quelles valeurs apparaissent », jamais à
« combien de fois » ni « dans quel ordre ».

**c) Un test du moteur n'est jamais seul dans la base.**

Un test d'`opex_workflow` cherchait son critère de matching par
`search([('code', '=', 'competences')])`. Tant que le moteur était seul, cela
marchait. Le jour où `opex_innovation` a semé un critère de même code, le
`search` en a renvoyé deux et le score est tombé de 100 % à 20 % — un échec
dans le moteur, causé par une donnée métier, sur du code qui n'avait pas bougé.

Tout `search()` d'un test se borne à son propre périmètre :

```python
self.Criteria.search([
    ('definition_id', '=', self.definition.id),   # ⚠ la borne
    ('code', '=', 'competences'),
])
```

Corollaire de la règle qui gouverne tout le reste : si le moteur ignore le
métier, ses tests doivent ignorer que le métier existe — donc ne jamais
supposer qu'il n'existe pas.

### 7. Un `Many2many` à la fois `related` et `store=True` empêche le registre de démarrer

```python
expert_competence_ids = fields.Many2many(
    'opex.innovation.competence',
    related='expert_profile_id.competence_ids',
    store=True,          # ⚠ le registre ne se charge plus
)
```

Odoo échoue au chargement avec :

```
AttributeError: 'NoneType' object has no attribute 'isidentifier'
```

Le message **ne nomme pas le champ fautif**, ni le modèle, ni le module : la
trace pointe vers le code de construction des tables de liaison. Un `Many2many`
stocké exige un nom de table de relation, qu'Odoo sait déduire des deux modèles
mais pas d'une chaîne `related`. Il n'y a donc rien à lire dans l'erreur — on
la reconnaît, ou on bissecte à la main.

Retirer `store=True`. Le stockage n'apporte d'ailleurs presque jamais rien
ici : un `related` non stocké ne coûte qu'une traversée de relation.

### 8. `<function>` dans un bloc `noupdate="1"` ne s'exécute pas à la mise à jour

Le piège le plus coûteux du chargement de données, parce qu'il **marche à
l'installation** et échoue partout ailleurs — c'est-à-dire qu'on le découvre le
jour de la démonstration.

`odoo/tools/convert.py`, `_tag_function` :

```python
def _tag_function(self, rec):
    if self.noupdate and self.mode != 'init':
        return                     # ⚠ silencieusement sauté
```

Une définition de workflow publiée depuis l'intérieur de son bloc `noupdate`
reste donc **en brouillon** après le premier `-u`. Pire : lorsqu'un fichier de
données est ajouté à un module déjà installé, ses `<record>` sont créés mais son
`<function>` ne tourne pas — la configuration existe et n'est jamais activée.

Le `<function>` se place **hors** du bloc, directement sous `<odoo>` :

```xml
<odoo>
    <data noupdate="1">
        <record id="wf_smart_crowdfunding" model="opex.workflow.definition">…</record>
    </data>

    <function model="opex.workflow.definition" name="action_publish"
              eval="[[ref('wf_smart_crowdfunding')]]"/>
</odoo>
```

`_tag_root` dispatche `<function>` comme n'importe quel autre tag, et le
`noupdate` hérité de `<odoo>` vaut `False` : il s'exécute à chaque mise à jour.
Rejouer une publication est de toute façon idempotent, et revalide le graphe —
une configuration devenue incohérente fait alors échouer le déploiement au lieu
de se découvrir en démonstration.

**Le même piège a deux autres faces**, rencontrées aux Extensions 10, 12, 15, 17
et 20 :

- un `<record>` qui redéfinit un enregistrement **existant** est ignoré à la
  mise à jour, parce que le drapeau `noupdate` est stocké **par enregistrement**
  dans `ir_model_data` et hérité du module qui l'a créé. Pour modifier un
  enregistrement semé ailleurs — rattacher une action à une transition, par
  exemple — il faut un `<function name="write">` hors bloc `noupdate` ;
- l'ordre des fichiers du manifeste compte : un `Command.set` écrase ce qu'un
  fichier précédent avait posé. Utiliser `Command.link` quand on ajoute à une
  configuration existante plutôt qu'on ne la remplace.

**Vérification** : forcer l'état à `draft` en base, relancer un simple `-u`, et
constater que la définition est republiée. Un test le fait
(`test_the_definition_is_published`), mais il ne détecte le cas qu'après un
premier chargement réussi — la vérification manuelle reste la seule preuve
complète.

---

# BLOC A — Le moteur générique `opex_workflow`

Traduction directe du bloc « WORKFLOW (MOTEUR GÉNÉRIQUE) » de l'infographie et des
10 « aspects génériques à développer ».

Manifeste : `'depends': ['base', 'mail']` — **rien d'autre**. Un moteur qui dépend
de `sale` ou de `website` n'est pas un moteur.

---

## Extension 1 — Le configurateur

**Objectif** : décrire un workflow complet depuis l'interface Odoo, et refuser un
graphe incohérent. Aucune exécution à ce stade.

### `opex.workflow.definition`

| Champ | Type | Rôle |
|---|---|---|
| `name` | Char, requis | |
| `code` | Char, requis, unique | `innovation_project`, `smart_crowdfunding` |
| `description` | Text | |
| `model_id` | Many2one `ir.model`, requis | Le modèle métier piloté |
| `model_name` | Char, related `model_id.model`, stored | |
| `version` | Integer, défaut 1 | |
| `state` | Selection `draft`/`published`/`archived` | |
| `active` | Boolean | |
| `stage_ids`, `transition_ids` | One2many | |

`action_publish()` appelle `_check_graph()`, qui vérifie :
- exactement **une** étape `is_start`
- **au moins une** étape `is_end`
- aucune étape inatteignable depuis le départ
- toute transition relie deux étapes de la même définition

Le message d'erreur doit **nommer les étapes fautives**, pas dire « graphe
invalide ». Un designer doit pouvoir corriger sans lire le code.

`action_new_version()` duplique la définition en `version + 1` et archive
l'ancienne. Les instances en cours restent rattachées à la version sous laquelle
elles ont démarré — c'est ce qui rend l'audit trail honnête six mois plus tard.

### `opex.workflow.stage`

`definition_id`, `name`, `code` (unique par définition), `sequence`, `is_start`,
`is_end`, `description`, `actor_role_ids` (Many2many role), `sla_days` (Integer),
`form_id` (Many2one form, Extension 6).

Plus un champ décisif :

- **`user_label`** (Char) — ce que l'utilisateur final lit. « Compléter mon
  dossier », jamais `dossier_progressif`.

C'est la traduction directe du principe UX de la section 16 du document
Smart Crowdfunding et de la section 35 du PDF Module 2 : le workflow système peut
être complexe, ce que l'utilisateur lit ne doit pas l'être.

### `opex.workflow.transition`

`definition_id`, `source_stage_id`, `target_stage_id`, `name` (**le libellé du
bouton** : « Valider », « Demander un complément », « Ajourner »), `code`,
`sequence`, `allowed_role_ids`, `condition_ids` (Many2many rule), `action_ids`
(Many2many action), `requires_comment` (Boolean).

⚠️ **Plusieurs transitions partent d'une même étape.** C'est ce qui produit le
GO / À CLARIFIER / NO GO / ORIENTATION de la pré-analyse et le
ACCEPTÉ / AJOURNÉ / REFUSÉ du comité d'évaluation. Ne jamais supposer qu'une étape
n'a qu'une sortie.

### `opex.workflow.rule`

`name`, `code`, `expression` (Text, requis), `message` (Char, requis — affiché quand
la condition bloque), `active`.

### `opex.workflow.role`

`name`, `code`, `description`, `group_id` (Many2one `res.groups`, optionnel).

Référentiel **global**, pas propre à une définition : Porteur, Secrétariat, Comité,
Expert, Investisseur, CEO se réutilisent d'un workflow à l'autre. `group_id` fait le
pont vers la sécurité Odoo quand le rôle correspond à un groupe permanent ; il reste
vide pour les rôles attribués au cas par cas (l'expert *de ce projet-là*).

### `opex.workflow.action`

Crée le modèle avec `name`, `sequence`, `action_type` (Selection) et ses paramètres.
**N'implémente aucune exécution** — c'est l'Extension 4.

### Sécurité

Deux groupes via `res.groups.privilege` :
- `group_workflow_designer` — CRUD sur toute la configuration. **Écrire une
  expression de règle, c'est écrire du code** : groupe technique, restreint.
- `group_workflow_manager` — lecture des définitions, vue complète des instances,
  peut forcer une transition (tracée comme telle dans l'historique).

### Vues

Menu « Smart Workflow ». Formulaire de définition avec notebook Étapes /
Transitions / Instances, bouton **« Valider le graphe »**. C'est **l'écran du test
d'acceptation** : il doit être utilisable par quelqu'un qui ne lit pas de Python.
Aide contextuelle et exemples d'expressions dans le `help` du champ `expression`.

### Tests — `tests/test_definition.py`, versionné dans le module

Graphe valide accepté · deux étapes de départ refusé · étape orpheline refusée avec
son nom dans le message · transition inter-définitions refusée.

⚠️ **Les tests vivent dans `tests/` versionné dès le premier jour.** C'est le fil
resté ouvert sur `opex_membership`, où ils vivaient dans un répertoire temporaire
effacé à chaque session. Ne pas reproduire l'erreur.

---

## Extension 2 — L'exécution

**Objectif** : un enregistrement métier avance réellement d'étape en étape, en
respectant les conditions.

### `opex.workflow.instance`

`definition_id`, `res_model` (Char), `res_id` (Integer), `resource_ref` (Reference,
computed — navigation en back-office), `current_stage_id`, `state`
(`running`/`done`/`cancelled`), `initiator_id`, `date_start`, `date_end`,
`actor_ids`, `history_ids`.

`res_model` / `res_id` plutôt qu'un Many2one : c'est ce qui rend le moteur
utilisable sur **n'importe quel** modèle, y compris natif Odoo.

### `opex.workflow.history` — l'audit trail

`instance_id`, `from_stage_id`, `to_stage_id`, `transition_id`, `user_id`, `date`,
`comment`, `conditions_note` (Text — le résultat de chaque condition au moment du
passage).

**Lecture seule pour tout le monde, administrateur compris.** Surcharge `write()` et
`unlink()` pour lever une `UserError` explicite. Un journal d'audit modifiable ne
vaut rien.

### `opex.workflow.mixin` (AbstractModel) — le point de branchement

```python
class WorkflowMixin(models.AbstractModel):
    _name = 'opex.workflow.mixin'
    _description = "Objet piloté par un workflow"

    workflow_instance_id  = fields.Many2one('opex.workflow.instance', readonly=True, copy=False)
    workflow_stage_id     = fields.Many2one(related='workflow_instance_id.current_stage_id', store=True)
    workflow_stage_label  = fields.Char(related='workflow_stage_id.user_label')
    workflow_definition_id = fields.Many2one(related='workflow_instance_id.definition_id')

    def start_workflow(self, definition_code): ...
    def action_workflow_transition(self): ...   # ouvre le wizard
```

Rendre un modèle pilotable devient **une ligne** dans *son* module :

```python
_inherit = ['mail.thread', 'opex.workflow.mixin']
```

### La logique centrale

- **`available_transitions(user=None)`** — les transitions partant de l'étape
  courante que les rôles de cet utilisateur autorisent. Elle **ne filtre pas sur les
  conditions** : une transition dont une condition échoue reste visible mais
  désactivée, accompagnée du `message` de la règle qui bloque. Une transition qui
  disparaît sans explication laisse l'utilisateur bloqué sans savoir pourquoi.
- **`_check_transition_allowed(transition, user)`** — LA fonction unique de contrôle
  d'accès (règle transversale 2). Aucune autre vérification de droit de transition
  ailleurs dans le code, nulle part.
- **`do_transition(transition, comment=False)`** — contrôle d'accès → évaluation des
  conditions → écriture de l'étape → écriture de l'historique → exécution des
  actions → clôture si `target_stage_id.is_end`.

### Évaluation des règles

```python
from odoo.tools.safe_eval import safe_eval

ctx = {
    'record':   record,
    'instance': instance,
    'user':     self.env.user,
    'stage':    instance.current_stage_id,
    'has_document': instance._has_document,   # has_document('pitch_deck')
    'field':        instance._field,          # field('score'), tolérant à l'absence
}
```

Trois exigences non négociables :

1. **`safe_eval` uniquement, jamais `eval()`.**
2. **Une expression qui lève une exception ne casse jamais la page** : capture, log,
   condition considérée **fausse**, `message` de la règle affiché. Un moteur
   configurable dont une faute de frappe blanchit l'écran est inutilisable.
3. **L'échec est lisible** : l'utilisateur voit *quelle* condition a échoué, pas un
   « action impossible » opaque.

Les trois conditions du test Demo Day s'écrivent alors :

```python
record.ceo_approval == True
has_document('pitch_deck')
field('score') >= 70
```

### Tests

Transition nominale · refusée par rôle · bloquée par condition puis débloquée ·
historique immuable · expression invalide qui ne casse rien.

---

## Extension 3 — Wizard de transition et UI générique

**Objectif** : rendre les transitions utilisables dans l'interface, sans JavaScript.

⚠️ **Piège Odoo à ne pas contourner par de l'OWL.** Des boutons dont le nombre et le
libellé dépendent de la donnée ne se déclarent pas statiquement en XML. Un composant
OWL custom coûterait une journée et demie sur quatre et serait fragile en démo.

**Décision arrêtée, à ne pas rouvrir** : un bouton unique **« Action »** ouvrant un
wizard `opex.workflow.transition.wizard` :
- Selection des transitions disponibles, chacune avec son état
  (disponible / bloquée + motif)
- champ commentaire (obligatoire si `requires_comment`)
- bouton Confirmer

Plus un `statusbar` pour la visualisation :

```xml
<field name="workflow_stage_id" widget="statusbar"
       options="{'clickable': false}"
       domain="[('definition_id', '=', workflow_definition_id)]"/>
```

Le statusbar donne le « où j'en suis », le wizard donne le « que puis-je faire ».
Ensemble, ça couvre le besoin sans une ligne de JavaScript.

---

## Extension 4 — Moteur d'actions et work queue

**Objectif** : le workflow *fait* des choses, et chaque acteur voit ce qui le
concerne.

### `opex.workflow.action` — exécution

Dispatcher par `getattr` vers `_execute_<action_type>()`. **Surtout pas une chaîne
de `if/elif`** : ajouter un type plus tard doit être l'ajout d'une méthode, rien
d'autre.

| Type | Effet |
|---|---|
| `notify` | `message_post()` sur l'objet métier, destinataires = acteurs portant `target_role_ids`. ⚠️ `mail.mt_note` pour l'interne |
| `set_field` | Écrit une valeur sur l'objet métier (`field_id` + `value_expression` évaluée comme une règle) |
| `create_task` | Crée un `opex.workflow.task` assigné à un rôle, avec échéance |
| `send_email` | Via un `mail.template` |
| `launch_subworkflow` | Démarre une seconde instance sur le même enregistrement (Extension 8) |
| `run_matching` | Déclenche le Smart Matching (Extension 7) |

**Règle** : les actions s'exécutent **après** le changement d'étape et **ne peuvent
pas l'annuler**. Une action qui échoue est journalisée dans l'historique, elle ne
rollback pas la transition — sinon un serveur mail en panne bloque tout le processus
métier.

### `opex.workflow.task`

`instance_id`, `stage_id`, `name`, `role_id`, `user_id`, `deadline`,
`state` (`todo`/`done`/`cancelled`).

Vue « Mes tâches » filtrée sur l'utilisateur connecté + vue agrégée par étape pour
les managers. C'est la **SMART WORK QUEUE** de la section 16 : chaque acteur voit ce
qu'il a à traiter, jamais le graphe complet.

---

## Extension 5 — Rôles et droits dynamiques

**Objectif** : implémenter le principe de visibilité de la section 3 du document
Smart Crowdfunding et de la section 32 du PDF Module 2.

> Identité + rôle + relation au dossier + étape → droits d'accès

### `opex.workflow.instance.actor`

`instance_id`, `role_id`, `user_id` (ou `partner_id`), `access_level`
(Selection `none`/`limited`/`full`), `date_granted`, `granted_by_id`.

Être enregistré comme investisseur ne donne pas accès à tous les projets ; c'est la
ligne `instance.actor` qui donne accès à **ce** dossier-là. C'est exactement ce
qu'exige la section 26 du PDF Module 2 : « L'investisseur ne voit pas tous les
projets. Il voit uniquement les projets proposés. »

### `ir.rule`

Sur `instance`, `history` et `task`, pour le groupe portail :

```python
"[('actor_ids.user_id', '=', user.id)]"
```

⚠️ **Teste avec un vrai compte non-admin.** Les `ir.rule` ne se voient pas en
administrateur — exactement le piège qui a coûté du temps sur le Module 1.

---

## Extension 6 — Formulaires dynamiques

**Objectif** : le « dossier progressif » (section 7 Smart Crowdfunding) et le dépôt
multi-étapes du Module 2 (sections 5 à 9) sans coder un formulaire par étape.

### `opex.workflow.form` / `opex.workflow.form.field`

- `form` : `name`, `code`, `definition_id`, `stage_id`
- `form.field` : `form_id`, `field_id` (Many2one `ir.model.fields`), `sequence`,
  `label_override`, `help_text`, `required_expression`, `visible_expression`,
  `widget_hint`

Le moteur doit permettre : **Étape → Type de projet → Type de besoin → formulaire
dynamique.** `required_expression` et `visible_expression` sont évaluées comme des
règles, avec le même contexte et la même tolérance aux erreurs.

Rendu QWeb générique côté portail : une page par formulaire, sauvegarde partielle à
chaque validation d'étape (le brouillon automatique).

---

## Extension 7 — Smart Matching Engine

**Objectif** : le bloc « MATCHING & RELATIONS » de l'infographie, réutilisé par la
section 19 du PDF Module 2 (Matching IA) et la section 10 de Smart Crowdfunding.

### Modèles

| Modèle | Champs |
|---|---|
| `opex.matching.criteria` | `definition_id`, `name`, `code`, `type` (secteur/compétence/localisation/maturité/montant/…), `weight` (Float), `source_expression`, `target_field`, `active` |
| `opex.matching.candidate` | `instance_id`, `partner_id`, `candidate_type` (`expert`/`mentor`/`investisseur`/`sponsor`), `score` (Float), `detail` (Text — **l'explication du score**), `state` (`proposed`/`accepted`/`rejected`/`excluded`) |
| `opex.matching.relation` | `instance_id`, `partner_id`, `access_level`, `authorized_by_id`, `nda_signed` (Boolean), `date` |

### Règles de conception

- Le matching est **une recommandation, jamais une décision**. Le résultat est une
  liste de candidats scorés que le responsable peut **Valider / Modifier / Exclure /
  Ajouter**. C'est écrit noir sur blanc dans les deux documents sources : « L'IA
  recommande. Elle ne doit pas automatiquement décider seule. »
- Le champ `detail` est obligatoire : un score de 87 % sans explication n'est pas
  défendable devant un jury. Stocke la contribution de chaque critère.
- Scoring pondéré simple (somme de correspondances × poids, normalisée). **Pas de
  modèle de machine learning** — hors périmètre, et le document ne le demande pas.
  « IA » ici veut dire scoring explicable.
- `opex.matching.relation` porte la **mise en relation contrôlée** de la section 13
  Smart Crowdfunding : le match ne donne pas accès au dossier complet. Teaser →
  intérêt → autorisation → NDA → dossier détaillé.

---

## Extension 8 — Sous-workflows, SLA, portail générique

**Objectif** : les trois dernières capacités transverses de l'infographie.

- **Sous-workflows** : action `launch_subworkflow` démarrant une instance d'une
  autre définition sur le même enregistrement ; helper de condition
  `subworkflow_done('code')`. C'est ce qui rend l'Accompagnement réutilisable entre
  OPEX Innovation et Smart Crowdfunding.
- **SLA & relances** : cron lisant `stage.sla_days`, marquant les instances en
  retard, notifiant le rôle attendu. Alimente le compteur « 3 accompagnements en
  retard » de la work queue CEO.
- **Portail générique** : template QWeb affichant la progression via
  `stage.user_label` et la prochaine action attendue — la maquette « Porteur » de la
  section 16, réutilisable par n'importe quel module métier.

**Fin du Bloc A.** À ce stade, le moteur est complet et le test Demo Day doit passer.
Ne pas continuer tant qu'il ne passe pas.

---

# BLOC B — Le module métier `opex_innovation`

Manifeste : `'depends': ['base', 'mail', 'contacts', 'portal', 'website',
'opex_workflow', 'opex_membership']`.

Toutes les sections référencées ci-dessous renvoient à `module2_innovation_ux.pdf`.

---

## Extension 9 — Profils Expert / Investisseur (Modifications 1 à 6 du PDF)

**Objectif** : le Module 1 devient la source des profils métier — Membre, Expert,
Investisseur. Le Module 2 ne recrée pas ces utilisateurs, il exploite les profils
existants.

### Décision d'architecture à assumer

Le PDF titre cette partie « Modifications à apporter au Module 1 ». **On ne les
implémente pas dans `opex_membership`** : ce module est gelé avant sa présentation à
l'encadrant. On étend `res.partner` **depuis `opex_innovation`**.

Le référentiel reste unique (un seul `res.partner`, aucune duplication — l'exigence
réelle du PDF est respectée), et le Module 1 reste présentable sans régression. À
mentionner explicitement comme écart assumé dans la note de cadrage.

### Extension de `res.partner`

`is_expert` (Boolean), `is_investor` (Boolean), `expert_profile_id`,
`investor_profile_id`.

**Profils cumulables** : un même compte peut être Membre + Expert + Investisseur.
Ce sont trois booléens indépendants, jamais une Selection exclusive.

Activation automatique après validation de l'adhésion (Modification 1) :
- catégorie **Partenaires / Sponsors** → profil Investisseur activé
- catégorie **Experts / Consultants** → profil Expert activé

Implémenté par un `@api.depends` ou un override dans `opex_innovation`, **jamais** en
modifiant `_activate_membership()` du Module 1.

### `opex.innovation.expert.profile`

Modification 4 : `domaine_expertise`, `specialites`, `fonction`,
`annees_experience`, `competence_ids` (Many2many), `experiences_pro` (Text),
`projets_realises` (Text), `experiences_conseil` (Text), `experience_mentoring`
(Text), `description_expertise` (Text), `document_ids` (CV, diplômes,
certifications, attestations, portfolio, références).

### `opex.innovation.investor.profile`

Modification 5 : `type_investisseur`, `secteur_ids`, `domaines_investissement`,
`types_projets_recherches`, `stade_maturite_recherche`, `zone_geographique`,
`montant_min` / `montant_max`, `experience_investissement`, `preferences` (Text),
`presentation` (Text), `document_ids`.

### Le premier workflow configuré — et c'est le point important

Les deux profils partagent le workflow de la Modification 4/5 :

```
Brouillon → Soumis → En contrôle → { Complément demandé → Resoumission | Refusé | Validé → Profil activé }
```

**Ce workflow n'est pas codé.** C'est une définition `opex_workflow` configurée en
data XML, sur le modèle `opex.innovation.expert.profile`. Cinq étapes, quatre
transitions — le banc d'essai idéal du moteur avant de s'attaquer au workflow projet
à treize étapes. Si celui-ci ne tourne pas parfaitement, ne pas passer à
l'Extension 10.

Les deux profils héritent donc de `opex.workflow.mixin`.

### Boutons « Devenir Expert » / « Devenir Investisseur »

Modification 3 : affichés dans l'espace personnel après validation de l'adhésion,
**masqués si le profil existe déjà**.

⚠️ Bug symétrique déjà rencontré sur le Module 1 (« Devenir membre » resté visible
pour un membre actif). Le `t-if` conditionne l'affichage, mais la route vérifie
**aussi** côté serveur qu'un second profil n'est pas créé en doublon.

---

## Extension 10 — Le modèle projet et sa définition de workflow

**Objectif** : poser `opex.innovation.project` et sa machine à états — **sous forme
de configuration**.

### `opex.innovation.project`

```python
class InnovationProject(models.Model):
    _name = 'opex.innovation.project'
    _description = "Projet d'innovation"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'opex.workflow.mixin']
```

⚠️ **N'hérite PAS de `project.project`**, malgré le Product Backlog. Raisons :
`project.project` apporte ses propres `stage_id`, tâches et vues Kanban, qui entrent
en collision frontale avec nos étapes de workflow (règle transversale 1). À la place,
un champ `project_id` (Many2one `project.project`, optionnel), alimenté **au
démarrage de l'accompagnement** (Extension 16) — c'est là que le projet devient un
vrai projet à piloter. Écart à documenter dans la note de cadrage : mieux justifié
que l'héritage.

**Aucun champ `state`.** L'état du projet, c'est `workflow_stage_id`. C'est la
démonstration entière du travail — la première personne qui ajoute un
`state = fields.Selection(...)` « juste pour aller plus vite » annule le projet.

### Champs — sections 5 à 9

| Section | Champs |
|---|---|
| **1. Porteur** (5) | `partner_id`, `organisation_id`, `email`, `telephone`, `wilaya`, `secteur_porteur` — **récupérés de `res.partner`, jamais ressaisis** |
| **1. Projet** (5) | `name`, `resume` (Text), `probleme` (Text), `solution` (Text), `secteur` (Selection : industrie, énergie, numérique, agriculture, santé, environnement, transport, autre), `maturite` (Selection : idée, prototype, MVP, produit développé, premiers clients, commercialisation, industrialisation) |
| **2. Marché** (6) | `marche_cible`, `besoin_marche`, `concurrence`, `proposition_valeur`, `modele_economique` (Selection), `potentiel_commercial` (Selection : local/national/international) |
| **3. Équipe** (7) | `team_member_ids` → `opex.innovation.team.member` (`name`, `fonction`, `competence`, `experience`) |
| **4. Besoins** (8) | `besoin_competence_ids` (Many2many), `besoin_accompagnement_ids` (Many2many), `besoin_financement` (Boolean), `montant_recherche` (Monetary), `type_financement`, `utilisation_prevue` (Text) |
| **5. Documents** (9) | `document_ids` → `opex.innovation.document` |

**Le champ `score`** (Integer, /100, computed depuis les évaluations) et
**`ceo_approval`** (Boolean) : noms convenus avec Kassab, utilisés par les conditions
de transition.

### `opex.innovation.document`

`project_id`, `name`, `document_type` (Selection : `business_plan`, `pitch_deck`,
`mvp`, `video`, `prototype`, `etude_marche`, `previsions_financieres`, `brevet`,
`poc`, `presentation_technique`, `autre`), `file` (Binary), `url` (pour la vidéo),
`version` (Integer), `is_required` (computed).

Le système contrôle : extension, taille, fichier vide, doublons (section 9).

### La définition de workflow `innovation_project` — data XML

Étapes, avec leur `user_label` de la section 35 :

| `code` | `name` | `user_label` (ce que le porteur lit) |
|---|---|---|
| `draft` | Brouillon | Compléter mon projet |
| `submitted` | Soumis | Projet déposé |
| `under_review` | Contrôle administratif | Contrôle en cours |
| `complement_requested` | Complément demandé | **Action requise sur votre projet** |
| `qualified` | Qualifié | Contrôle terminé |
| `evaluation` | En évaluation | Évaluation en cours |
| `remediation` | Remédiation | Améliorations demandées |
| `resubmitted` | Resoumis | Nouvelle évaluation en cours |
| `accepted` | Accepté | Projet accepté |
| `matching` | Matching | Recherche de partenaires |
| `accompagnement` | Accompagnement | Accompagnement en cours |
| `financement` | Financement | Financement en cours |
| `industrialisation` | Industrialisation | Industrialisation |
| `closed` | Clôturé | Projet clôturé (`is_end`) |
| `rejected` | Refusé | Projet refusé (`is_end`) |

Transitions — schéma 10. Les trois points à ne pas simplifier :
- le contrôle administratif a **deux** sorties (conforme → qualifié / incomplet →
  complément demandé), avec **retour** vers le contrôle après resoumission
- la décision du comité a **trois** sorties : accepté / ajourné / refusé
- **la boucle remédiation → resoumission → évaluation existe** : c'est elle qui
  prouve qu'on gère un graphe et pas une séquence linéaire

**Test de fin d'extension** : dérouler le parcours complet à la main dans le
back-office, du brouillon à la clôture, en passant une fois par la boucle de
remédiation. Si ça marche ici, tout le reste n'est que de l'interface.

---

## Extension 11 — Dépôt du projet, parcours porteur en 5 étapes

**Sections 4 à 12.** Le formulaire éclaté en écrans réels, avec brouillon
auto-sauvegardé.

Routes portail :

| Route | Contenu |
|---|---|
| `/my/innovation` | « Mes projets » — tableau Projet / Catégorie / État / Dernière MAJ / Action (section 4) |
| `/my/innovation/new` | Étape 1 — Informations générales |
| `/my/innovation/<id>/marche` | Étape 2 — Marché et modèle économique |
| `/my/innovation/<id>/equipe` | Étape 3 — Équipe |
| `/my/innovation/<id>/besoins` | Étape 4 — Besoins (**la plus importante pour le matching**) |
| `/my/innovation/<id>/documents` | Étape 5 — Pièces jointes |
| `/my/innovation/<id>/recap` | Récapitulatif + confirmation + [Soumettre le projet] |

**Brouillon automatique** : le projet est créé dès la première étape (étape `draft`),
chaque écran fait un `write()` partiel. Message de reprise si le porteur revient sur
un brouillon existant. C'est exactement le mécanisme validé sur le Module 1 —
réutilise le même pattern, il fonctionne.

**Avertissement avant soumission** (section 11) : une fois soumis, certaines
informations ne seront plus modifiables pendant l'évaluation. Le porteur confirme.

Idéalement, ces écrans sont rendus par les **formulaires dynamiques de
l'Extension 6**. Si le temps manque, des templates QWeb classiques sont acceptables —
mais alors dis-le explicitement dans le rapport, c'est un écart au principe.

### Sécurité

`create()` surchargé : force `partner_id = env.user.partner_id.id` quelle que soit la
valeur envoyée. `ir.rule` scopée sur le partner. Même protection que sur
`opex.membership.file` — le pattern est éprouvé, recopie-le.

---

## Extension 12 — Contrôle administratif et qualification

**Sections 13 et 14.**

Route staff `/staff/innovation` : liste des projets à contrôler, filtrée par rôle.

Le secrétariat vérifie : informations complètes, documents lisibles, porteur
autorisé, cohérence du dossier, présence des éléments nécessaires. Deux issues :

- **Conforme** → transition vers `qualified`
- **Incomplet** → « Demander un complément » avec **motif obligatoire**
  (`requires_comment = True` sur la transition), transition vers
  `complement_requested`. Le porteur reçoit « Action requise sur votre projet »,
  corrige, resoumet → retour à `under_review`.

**Qualification** (section 14) : fiche synthétique — Secteur, Maturité, Potentiel
marché, Besoin financement, Besoin expertise. Une vue, pas un nouveau modèle.

---

## Extension 13 — Évaluateurs et grille d'évaluation

**Section 15.** La partie la plus subtile du module ; lis la section en entier avant
de coder.

### Le principe à respecter à la lettre

> « Les évaluateurs apportent une expertise complémentaire lorsque le Comité
> d'évaluation estime qu'elle est nécessaire. Leur intervention est **optionnelle**,
> leur avis est **consultatif** et la décision finale appartient **exclusivement** au
> Comité d'évaluation. »

Le workflow doit supporter **deux scénarios** (schéma 6) : avec évaluateurs
(Scénario A) et sans (Scénario B, évaluation directe par le comité). Deux transitions
depuis `qualified`, pas une seule avec un `if` dedans.

⚠️ **Expert ≠ évaluateur.** Le rôle « Expert » sur le portail est un profil du vivier.
Une personne devient évaluateur uniquement quand elle est **désignée pour un projet
donné** — c'est-à-dire quand une ligne `opex.workflow.instance.actor` est créée avec
le rôle `evaluateur` sur cette instance. C'est exactement l'usage des droits
dynamiques de l'Extension 5.

### `opex.innovation.evaluation`

`project_id`, `evaluator_id` (Many2one `res.partner`), `state`
(`requested`/`in_progress`/`submitted`), et la grille :

| Critère | Champ | Max |
|---|---|---|
| Innovation | `score_innovation` | 20 |
| Pertinence du besoin | `score_pertinence` | 20 |
| Faisabilité technique et opérationnelle | `score_faisabilite` | 20 |
| Potentiel du marché | `score_marche` | 20 |
| Équipe | `score_equipe` | 10 |
| Impact attendu | `score_impact` | 10 |
| **Total** | `score_total` (computed) | **100** |

Plus : `commentaires`, `observations`, `points_forts`, `points_faibles`,
`risques`, `recommandations`, `propositions_amelioration` (Text).

`opex.innovation.project.score` = moyenne des `score_total` soumis. **C'est le champ
que lit la condition `field('score') >= 70`** du test Demo Day.

### Confidentialité des avis — schéma 7

> « Chaque évaluateur travaille indépendamment. Il ne peut pas consulter les avis ou
> les scores des autres évaluateurs avant la finalisation de son propre avis. »

`ir.rule` sur `opex.innovation.evaluation` :

```python
"['|', ('evaluator_id', '=', user.partner_id.id), ('state', '=', 'submitted')]"
```

⚠️ Et **côté template** : ne jamais rendre les autres avis dans le HTML de la page
d'un évaluateur, même masqués. Règle transversale 3 à l'envers — ici, « présent dans
le HTML » suffirait à violer la confidentialité, quand bien même rien ne s'afficherait.
C'est le point de sécurité le plus sensible de tout le module.

---

## Extension 14 — Décision du comité et remédiation

**Sections 17 et 18.**

Trois transitions depuis `evaluation`, toutes avec `requires_comment = True` :

| Transition | Cible | Suite |
|---|---|---|
| **Accepté** | `accepted` | → Matching IA → Accompagnement |
| **Ajourné** | `remediation` | → Remédiation → Nouvelle soumission |
| **Refusé** | `rejected` | Clôture, notification motivée |

Le comité peut aussi : demander des informations complémentaires, demander une
nouvelle évaluation, ne pas retenir l'avis, décider différemment de la
recommandation. Ce sont des transitions supplémentaires, pas des cas particuliers
codés.

### `opex.innovation.remediation` — section 18

Le cluster ne dit pas « améliorez votre projet », il précise **quoi** corriger :

`project_id`, `point_ids` (Many2many `opex.innovation.remediation.point` :
étude de marché, modèle économique, preuve de concept, besoin de financement,
problème/besoin, solution, prototype, faisabilité, équipe), `commentaire_comite`
(Text), `date_demande`, `resolved`.

**Historique des versions conservé** : chaque resoumission crée une nouvelle version
du dossier, l'ancienne reste consultable. Le PDF l'exige explicitement.

---

## Extension 15 — Matching IA

**Sections 19 et 20.** Configure le moteur de l'Extension 7 pour ce module — sans
écrire de nouveau code de scoring.

Critères analysés : secteur, compétences recherchées, localisation, niveau de
maturité, besoins d'accompagnement, besoin de financement, technologies.

Résultat, trois catégories de candidats : **Experts recommandés**, **Mentors**,
**Investisseurs**, avec leur score et son explication.

> ⚠️ « L'IA recommande. Elle ne doit pas automatiquement décider seule. »
> Le responsable OPEX doit pouvoir **Accepter / Modifier / Ignorer**.

Le matching est déclenché par une action `run_matching` sur la transition
`accepted → matching`. Aucun appel automatique ailleurs.

**Notification de matching** (section 20) : l'expert reçoit « Une opportunité
d'accompagnement vous a été proposée » et voit Projet, Secteur, Résumé, Besoin, Rôle
proposé, Durée estimée — **seulement les informations auxquelles il a droit**, via
`instance.actor.access_level = 'limited'`. Boutons [Je suis intéressé] / [Je ne suis
pas disponible].

---

## Extension 16 — Accompagnement, roadmap, livrables

**Sections 21 à 24.**

### `opex.innovation.accompagnement`

`project_id`, `expert_id`, `mentor_id`, `date_debut`, `date_fin`, `objectifs`
(Text), `progression` (Float, computed).

C'est ici qu'on crée le `project.project` lié (`project_id` sur le projet
d'innovation), si on veut brancher la gestion de projet native d'Odoo.

### `opex.innovation.roadmap.phase`

`accompagnement_id`, `name`, `sequence`, `state`. Les quatre phases de la
section 22 : Validation, Produit, Marché, Industrialisation — configurables, pas
codées en dur.

### `opex.innovation.deliverable`

`accompagnement_id`, `name`, `deadline`, `state` (`todo`/`submitted`/`validated`/
`correction_requested`), `file`, `version`, `history_ids`.

Section 24 : l'expert reçoit « Nouveau livrable à vérifier », peut **Valider** ou
**Demander une correction**. Si correction → nouvelle version → validation.
**L'historique est conservé.**

Le cycle de vie d'un livrable est lui-même un petit workflow — utilise le moteur
plutôt que des `if` sur `state`. Quatre étapes, trois transitions. C'est le genre de
réutilisation qui justifie tout le Bloc A.

---

## Extension 17 — Financement, espace investisseur, industrialisation, clôture

**Sections 25 à 29.**

### Suivi du financement (25)

`financement_recherche` (Monetary), `financement_obtenu` (Monetary),
`progression_financement` (Float, computed). Parcours : besoin → matching
investisseurs → intérêt → échange/analyse → financement.

### Espace investisseur (26)

Route `/my/innovation/opportunities`. L'investisseur voit **uniquement les projets
qui lui sont proposés**, avec les informations autorisées : Secteur, Maturité,
Potentiel, Financement recherché. Boutons [Voir le projet] [Manifester mon intérêt].

Le filtrage passe par `instance.actor`, vérifié **côté serveur** sur chaque route.
Jamais un simple masquage de template.

### Industrialisation (27) et clôture (28)

Suivi : état d'industrialisation, partenaires, livrables, financement, échéances,
résultats. À la clôture, génération d'un bilan : date de dépôt, date d'acceptation,
durée d'accompagnement, experts impliqués, financement obtenu, livrables réalisés,
résultat final.

### Évaluation finale (29)

`opex.innovation.final.evaluation` : le porteur évalue l'accompagnement, le cluster
évalue pertinence, qualité du mentorat, résultats, respect des délais. Alimente le
dashboard et, plus tard, les mécanismes de recommandation.

---

## Extension 18 — Notifications, historique, droits

**Sections 30 à 32.**

### Notifications (30)

Portail + email, **pas de SMS** (décision reprise du Module 1). Les 14 déclencheurs :
projet soumis, complément demandé, projet qualifié, projet évalué, décision du
comité, remédiation demandée, projet accepté, matching proposé, expert intéressé,
nouveau livrable, livrable validé, correction demandée, évolution du financement,
projet clôturé.

Chacun est une **action `notify` configurée sur une transition**, pas un
`message_post()` dispersé dans le code métier. C'est la différence entre un module
maintenable et un module où il faut chercher à quinze endroits pourquoi un email
part.

⚠️ `mail.mt_note` pour tout ce qui est interne. Bug déjà rencontré et corrigé sur le
Module 1.

### Historique (31)

Déjà fourni par `opex.workflow.history` (Extension 2), rien à recoder. Il suffit
d'un bloc QWeb en lecture seule sur la page portail — `opex.innovation.project`
n'hérite pas de `portal.mixin`, donc le chatter natif ne s'y affiche pas. Même
problème et même solution que sur le Module 1, réutilise le pattern.

### Droits (32)

Le tableau de la section 32 se configure entièrement en `instance.actor` +
`ir.rule`, sans code métier :

| Acteur | Voit |
|---|---|
| Porteur | Ses projets, documents, évaluations communiquées, accompagnement, livrables, financement |
| Secrétariat | Projets soumis, contrôles, documents, workflow |
| Comité | Projets à évaluer, documents nécessaires, grilles, historique |
| Expert/Mentor | Projets affectés, informations autorisées, roadmap, livrables |
| Investisseur | Projets proposés, informations financières autorisées, progression |

---

## Extension 19 — Portail porteur et tableaux de bord

**Sections 3 et 35.** La règle d'or, identique à celle du Module 1 :

> **L'utilisateur ne doit pas voir la complexité interne.**

La carte « MON PROJET » affiche la progression en `user_label`, pas en codes
techniques :

```
Smart Factory
✓ Déposé
✓ Contrôle terminé
● Évaluation en cours
○ Décision
○ Accompagnement
○ Financement
○ Industrialisation

Dernière action : « Votre projet est actuellement évalué. »
[ Consulter mon projet ]
```

Le back-office, lui, peut être aussi détaillé qu'on veut.

Dashboards : porteur (`/my/innovation`), gestionnaire (`/staff/innovation/dashboard`
— projets par étape, délais, alertes), expert (mes missions, mes livrables),
investisseur (mes opportunités).

---

## Extension 20 — Smart Crowdfunding, seconde instance

**Objectif** : la démonstration finale. Configurer un second workflow complet
**sans ajouter une ligne de Python**.

Fichier `data/smart_crowdfunding.xml` dans `opex_innovation` (ou un module
`opex_crowdfunding_config` séparé) configurant les 10 étapes du document source, sur
le même modèle `opex.innovation.project` ou sur un modèle jouet.

Points à ne pas simplifier :
- la pré-analyse a **quatre** sorties : GO, À clarifier, NO GO, Orientation
- le Quality Gate a **trois** sorties : Conforme, À compléter, Alerte
- la boucle Accompagnement → Réévaluation → Matching existe

Puis **le test d'acceptation, réalisé à la main, chronométré, documenté avec
captures** : ajouter l'étape Demo Day et ses trois conditions depuis le
configurateur.

Le livrable final est un procès-verbal contenant, en pièce jointe, un `git diff` sur
`opex_workflow/` montrant **zéro ligne modifiée**. C'est la preuve matérielle qui
répond exactement à la question posée en section 18.

---

# État d'avancement — au 24/08/2026

`opex_workflow` **19.0.1.15.0** · `opex_innovation` **19.0.1.23.0**
Suite complète : **443 tests, 0 échec** sur les deux modules.

| Extension | État | Preuve |
|---|---|---|
| 1 — Configurateur | ✅ | `models/workflow_definition.py`, `_stage.py`, `_transition.py`, `_rule.py`, `_role.py`, `_action.py` |
| 2 — Exécution | ✅ | `models/workflow_instance.py`, `_history.py`, `_mixin.py` |
| 3 — Wizard et UI générique | ✅ | `wizard/workflow_transition_wizard.py` |
| 4 — Actions et work queue | ✅ | dispatch par `getattr`, `models/workflow_task.py` |
| 5 — Droits dynamiques | ✅ | `instance.actor`, `security/ir_rule.xml` |
| 6 — Formulaires dynamiques | ✅ | `models/workflow_form.py` |
| 7 — Smart Matching | ✅ | `models/matching.py` |
| 8 — Sous-workflows, SLA, portail | ✅ | `start_subworkflow()`, `_cron_check_sla()` |
| 9 — Profils Expert / Investisseur | ✅ | `opex_innovation/models/expert_profile.py`, `investor_profile.py` |
| 10 — Modèle projet | ✅ | `innovation_project.py`, `data/project_workflow.xml` (15 étapes) |
| 11 — Parcours de dépôt | ✅ | `controllers/project_portal.py` |
| 12 — Contrôle et qualification | ✅ | `controllers/staff_portal.py` |
| 13 — Évaluateurs | ✅ | `models/evaluation.py` |
| 14 — Décision et remédiation | ✅ | `models/remediation.py` |
| 15 — Matching IA configuré | ✅ | `data/matching_criteria.xml` |
| 16 — Accompagnement, roadmap, livrables | ✅ | `accompagnement.py`, `deliverable.py`, `data/deliverable_workflow.xml`, `data/roadmap_phases.xml` |
| 17 — Financement, investisseur, industrialisation, clôture | ✅ | `financement.py`, `industrialisation.py`, `closure.py`, `final_evaluation.py`, `investor_portal.py` |
| 18 — Notifications, historique, droits | ✅ | `data/notifications.xml` (14 déclencheurs), `models/notifications.py` |
| 19 — Portail et tableaux de bord | ✅ | `models/milestone.py`, `controllers/dashboard.py` |
| 20 — Smart Crowdfunding, seconde instance | ✅ | `data/smart_crowdfunding.xml` — 14 étapes, 23 transitions, 0 ligne de Python au moteur |

## ✅ Extension 16 — les trois coutures, refermées

Les trois manques que les Extensions 17, 18 et 19 signalaient — et **affichaient
à l'écran** plutôt que de les masquer — sont refermés, exactement comme annoncé :

1. **§28, bilan de clôture** — `livrable_count` comptait les
   `opex.innovation.document` du projet. Il compte désormais les livrables
   **validés**, et eux seuls. Un livrable déposé mais refusé n'a pas été réalisé.
2. **§30, notifications** — ⑩ Nouveau livrable, ⑪ Livrable validé, ⑫ Correction
   demandée étaient configurées et rattachées à rien. Elles sont branchées sur
   le workflow des livrables par trois `<function>`, **sans qu'aucune ait été
   réécrite** : mêmes enregistrements, même corps, même sous-type. Il ne reste
   aucune orpheline.
3. **§35, tableau de bord expert** — l'encart annonçant que la fonctionnalité
   relevait de l'Extension 16 est remplacé par la liste réelle des livrables à
   vérifier, filtrée sur `instance.actor`.

C'est l'assertion `test_the_orphans_are_exactly_the_three_of_extension_16` qui a
rougi le jour où l'Extension 16 a été faite — elle a signalé que l'état du module
avait changé, au lieu de laisser une affirmation périmée passer au vert. Elle a
été réécrite en `test_no_trigger_is_left_orphan`, doublée d'un test qui vérifie
que les trois sont branchées **sur le bon workflow** : accrochées par erreur à
une transition du parcours projet, elles ne seraient pas orphelines non plus, et
partiraient au mauvais moment.

**Le module n'a plus de trou fonctionnel déclaré.**

### Le livrable, cinquième instance du moteur

`opex.innovation.deliverable` porte le mixin et **aucun champ `state`** —
quatre étapes, quatre transitions, configurées dans
`data/deliverable_workflow.xml`.

Sept définitions tournent maintenant sur six modèles distincts :
`profile_request`, `profile_request_investor`, `innovation_project`,
`smart_crowdfunding`, `innovation_industrialisation`, `innovation_deliverable`,
`demo_dossier`. Zéro ligne de Python ajoutée au moteur pour aucune.

⚠ **La phase de roadmap, elle, garde un champ `state`**, et c'est la ligne de
partage à retenir : une phase est une case à trois positions, sans acteur, sans
condition, sans notification, sans chemin de refus et sans historique. Lui donner
une instance de workflow serait de la cérémonie pour un compteur d'avancement. Un
livrable, lui, a un valideur, un chemin de rejet, des versions successives et des
notifications à chaque passage — c'est un processus.

## Deux corrections d'une ligne, identifiées et non faites

Volontairement laissées de côté pour préserver la mesure du test d'acceptation
(Extension 20), qui exige zéro octet modifié dans `opex_workflow/` :

- **`action_ids` n'est exposé dans aucune vue du configurateur.** Ni dans la
  liste imbriquée des transitions, ni ailleurs — `opex.workflow.transition` et
  `opex.workflow.stage` n'ont pas de vue formulaire propre. Conséquence : on ne
  peut pas déplacer une action d'une transition à l'autre à la souris. Découvert
  en écrivant le protocole Demo Day écran par écran ; aucun test automatisé ne
  pouvait le voir, puisque l'ORM écrit `action_ids` sans difficulté.
  → une ligne de XML de vue.
- **`_execute_notify` ne sait pas adresser un destinataire nommé**, seulement
  des rôles. C'est ce qui laisse subsister l'unique `message_post()` en dur du
  module métier, dans `propose_to_candidate()` : une action configurée
  notifierait tous les experts déjà proposés sur le dossier, y compris ceux qui
  ont déjà répondu. → un argument facultatif sur `execute()`.

---

# Ordre d'implémentation

Strict, chaque extension dépendant des précédentes.

| Jour | Extensions | Jalon de fin de journée |
|---|---|---|
| **J1** | 1, 2 | Un workflow se décrit, se valide, et un enregistrement avance d'étape |
| **J2** | 3, 4, 5 | Wizard, actions, droits dynamiques testés avec un compte non-admin |
| **J3** | 9, 10 | Profils Expert/Investisseur (petit workflow) puis le workflow projet complet, déroulé à la main |
| **J4** | 11, 12, 13, 14 | Le parcours métier de bout en bout : dépôt → contrôle → évaluation → décision → remédiation |
| **J5+** | 6, 7, 8, 15, 16, 17, 18, 19 | Formulaires dynamiques, matching, accompagnement, notifications, portail |
| **Final** | 20 | Smart Crowdfunding configuré + PV du test Demo Day |

L'encadrant a dit « 3-4 jours ». Ce plan en compte davantage : **le Bloc A plus les
Extensions 9, 10 et le squelette de 11-14 constituent un livrable défendable à J4**,
avec le reste annoncé comme la suite. Mieux vaut quatre extensions irréprochables et
un périmètre annoncé que douze à moitié faites.

**Priorité absolue si le temps manque** : Extensions 1, 2, 3, 10 et 20. C'est le
chemin minimal qui fait passer le test d'acceptation — c'est-à-dire qui répond à ce
que l'encadrant a explicitement demandé.

---

# Hors périmètre — assumé, à documenter, jamais à découvrir en soutenance

Chacun a son point d'extension prévu dans le modèle de données :

- **Vraie IA / machine learning** — le « Matching IA » est un scoring pondéré
  explicable. Le document ne demande rien d'autre, et un score inexplicable serait un
  défaut, pas une qualité
- **Agent IA Quality Control** — l'architecture le permet (un acteur automatisé est
  un acteur comme un autre) ; rien n'est implémenté
- **Signature électronique cryptographique** — confirmation horodatée, comme sur le
  Module 1
- **Éditeur graphique de workflow** — la configuration se fait en listes Odoo
- **Votes en AG, Module 3 (Intervenants)** — hors sujet ici

Le point à défendre : chacun de ces ajouts est une **extension**, pas une réécriture.
C'est précisément ce que le test Demo Day démontre.

---

# Méthode de travail

Le pattern éprouvé sur `opex_membership`, à reconduire sans exception :

1. **Un prompt = une extension.** Jamais deux.
2. **État des lieux écrit avant tout code** — que Claude Code lise l'existant et
   annonce ce qu'il va faire avant de le faire.
3. **Arrêt pour test utilisateur** après chaque extension.
4. **Commit seulement après validation humaine.**
5. **Ce fichier mis à jour après chaque rapport.** Il est la source de vérité, pas
   l'historique de conversation.
6. **Tests dans `tests/` versionné**, dès la première extension.

Sur un moteur générique, la tentation de tout construire d'un coup est plus forte que
sur un module métier, parce que les entités sont fortement couplées. C'est
exactement pour ça qu'il faut y résister : une régression dans `do_transition()`
casse **tous** les workflows à la fois, et le diagnostic après coup coûte une
journée.
