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

### 2. Un contrôle d'accès = une seule fonction, jamais recopié

Ici : « cet utilisateur peut-il déclencher cette transition ? » existe en **un seul
endroit**, `opex.workflow.instance._check_transition_allowed()`, appelé par le
back-office, le wizard, le portail et les tests. Une vérification dupliquée finit
par en oublier une occurrence — et c'est celle-là qui reçoit la requête forgée.

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
# CLAUDE.md — `opex_crowdfunding`

**Smart Crowdfunding — implémentation texto (workflow codé en dur)**

---

## ⚠️ LIRE AVANT TOUTE MODIFICATION

Ce module implémente **littéralement** le processus décrit dans
`docs/instance_smart_crowdfunding.md` : dix étapes, des états en dur, des méthodes
de transition en Python. C'est volontaire.

### Ce module est la moitié d'une expérience

Mail de Dr. S. Babaci, CEO DELTALOG, du 22/08 :

> 1. Partie workflow tel que défini (dans le document et le workflow) : Kassab —
>    **implémenter texto** — module à part
> 2. Partie 2 un module générique pour créer un workflow similaire (Zitouni) —
>    module à part
>
> 3-4 jours de travail avec IA

Deux modules construisent le **même** processus par deux chemins opposés :

| | `opex_crowdfunding` (ce module) | `opex_workflow` + `opex_innovation` |
|---|---|---|
| Le workflow est… | du code Python | de la configuration en base |
| Ajouter une étape coûte… | un développeur, une migration, un redéploiement | quelques minutes dans une interface |
| Réutilisable pour un autre processus ? | non | oui |
| Temps de mise en œuvre | court | plus long |
| Lisibilité du processus dans le code | directe | indirecte |

**Le module texto n'est pas le mauvais élève de l'histoire.** Il est plus rapide à
écrire, plus simple à lire, et parfaitement légitime pour un processus qui ne
changera pas. C'est en le construisant honnêtement — et pas en le sabotant — que la
comparaison finale a une valeur.

### ⛔ Règle d'isolation — la plus importante de ce fichier

Le même développeur construit les deux modules. Le risque est donc la
contamination, dans les deux sens.

1. **`opex_crowdfunding` n'importe RIEN de `opex_workflow`.** Pas dans le
   manifeste, pas dans un `import`, pas dans une vue héritée. Vérifiable :
   `grep -r "opex_workflow\|opex\.workflow" opex_crowdfunding/` doit ne rien
   renvoyer.
2. **Aucun copier-coller entre les deux modules**, dans aucun sens. Un même
   problème résolu deux fois différemment, c'est exactement la donnée qu'on
   cherche.
3. **Sessions Claude Code séparées.** Ne jamais travailler sur les deux modules
   dans la même session : le contexte de l'un déteint sur l'autre.
4. Ce module **n'a pas de champ workflow générique**, pas de table de transitions,
   pas de moteur de règles. S'il commence à en avoir, il est en train de devenir
   l'autre module et l'expérience est morte.

### Ordre recommandé : ce module d'abord

Il est le plus rapide (1 à 1,5 jour) et il devient le **cahier des charges
exécutable** du module générique : tout ce qu'il fait, l'autre devra le reproduire
par configuration. Il donne aussi une démo qui tourne dès le premier jour, ce qui
sécurise la présentation quoi qu'il arrive ensuite.

---

## Documents de référence — dossier `docs/`

Fais un `ls docs/` et lis ce qui s'y trouve avant de coder. En particulier :

- **`instance_smart_crowdfunding.md`** — la spécification de ce module, section par
  section. C'est le document à implémenter **texto** : les sections 4 à 15 sont les
  dix étapes, la section 16 décrit les quatre interfaces utilisateur, la section 18
  est le test final.
- **L'infographie** — le diagramme du workflow en haut de l'image est la vue de
  référence du processus, avec le détail des sorties de chaque étape.
- Le cahier des charges DELTALOG et la vision du portail, pour le contexte.

En cas de divergence entre ce fichier et le document source sur un point
fonctionnel, **le document source fait foi**. Ce fichier donne la traduction
technique.

---

## Règles transversales — héritées de `opex_membership`

Payées cher sur le module précédent. Elles s'appliquent ici aussi.

1. **Collisions de nommage avec l'API interne d'Odoo.** `category_id`, `_register`,
   `stage_id`, `name_get` sont déjà pris à divers endroits. Une collision est
   souvent masquée silencieusement et échoue au runtime, pas au chargement.
2. **Un contrôle d'accès = une seule fonction, jamais recopiée.** Ici :
   `_is_ceo()`, `_is_quality_control()`, `_project_access_denied()`. Une
   vérification dupliquée finit par en oublier une occurrence.
3. **« Présent dans le HTML » ≠ « visible à l'écran ».** Un test qui vérifie
   `'texte' in body` passe alors que l'utilisateur ne voit rien.
4. **`mail.mt_note` pour tout message interne.** `mail.mt_comment` uniquement pour
   ce que le porteur doit recevoir par email. Bug déjà rencontré et corrigé.
5. **Odoo 19** : `res.groups.privilege` (plus de `category_id` sur `res.groups`) ;
   plus d'`attrs` ni de `states` dans les vues → `invisible="..."` /
   `readonly="..."` directement.

Manifeste : `'depends': ['base', 'mail', 'contacts', 'portal', 'website']`.
Pas `opex_membership` (indépendance), pas `opex_workflow` (règle d'isolation).

---

# Le modèle central

## `opex.crowdfunding.project`

```python
_inherit = ['mail.thread', 'mail.activity.mixin']
```

Le champ qui définit tout le module — **c'est ici que le workflow est codé en dur**,
et c'est assumé :

```python
state = fields.Selection([
    ('draft',              "Brouillon"),
    ('depot_express',      "Demande déposée"),
    ('pre_analyse',        "Pré-analyse"),
    ('clarification',      "Clarification demandée"),
    ('dossier_progressif', "Dossier à compléter"),
    ('quality_gate',       "Contrôle qualité"),
    ('quality_complement', "Complément demandé"),
    ('etude_decision',     "Étude CEO"),
    ('accompagnement',     "Accompagnement CEO"),
    ('reevaluation',       "Réévaluation"),
    ('matching_financier', "Matching financier"),
    ('mise_en_relation',   "Mise en relation"),
    ('decision_financeur', "Décision de l'acteur financier"),
    ('closing',            "Closing"),
    ('closed',             "Clôturé"),
    ('rejected',           "Non retenu"),
], default='draft', tracking=True)
```

Les codes d'étapes sont **identiques** à ceux configurés dans le module générique.
C'est ce qui rendra la comparaison finale possible sans ambiguïté.

Plus deux champs dont les noms sont eux aussi communs aux deux modules, parce que le
test final s'appuie dessus : **`score`** (Integer, /100) et **`ceo_approval`**
(Boolean).

---

# Les extensions

## Extension 1 — Socle et Dépôt Express

**Section 5 du document.**

`opex.crowdfunding.project` avec les informations minimales — et **rien de plus** :
`partner_id`, `porteur_type` (Selection : personne physique, startup, entreprise,
groupe, association, autre personne morale), `name` (titre du projet), `probleme`
(Text), `solution` (Text), `secteur`, `maturite`, `besoin_type` (Selection :
financement, accompagnement, partenariat…), `montant_indicatif` (Monetary),
`pitch_document` (Binary, **facultatif**).

⚠️ Le principe du *progressive commitment* est le cœur du document : on ne demande
que le minimum nécessaire pour décider de l'étape suivante. Ne pas ajouter ici les
champs du dossier complet « puisqu'on y sera de toute façon » — ce serait passer à
côté de la spécification.

**Groupes** via `res.groups.privilege` : `group_ceo`, `group_quality_control`,
`group_expert`, `group_financial_actor`. Le porteur utilise `base.group_portal`.

**Méthode** `action_submit()` : `draft → depot_express`.

**Tests versionnés dans `tests/`** dès cette extension.

---

## Extension 2 — Portail porteur

**Sections 5 (UX) et 16.**

Routes : `/my/projects`, `/my/projects/new`, `/my/projects/<id>`.

⚠️ Le CTA est **« Présenter mon projet »**, jamais « Constituer mon dossier de
financement ». Le document insiste explicitement dessus : le libellé conditionne le
taux de dépôt.

Brouillon auto-sauvegardé (créé dès la première étape, `write()` partiel ensuite).

Sécurité : `create()` surchargé forçant `partner_id = env.user.partner_id.id` quelle
que soit la valeur envoyée, `ir.rule` scopée sur le partner. Le pattern existe déjà
dans `opex_membership`, recopie-le.

Vue « Mon projet » de la section 16 : la progression en libellés lisibles et **la
prochaine action attendue**, pas les codes d'états.

---

## Extension 3 — Pré-analyse et Go / No Go

**Section 6.** La première étape où la nature « multi-sorties » du processus
apparaît.

`opex.crowdfunding.prequalification` : `project_id`, `criteria_ids`, `commentaire`,
`resultat`, `evaluated_by_id`, `date`.

Critères **paramétrables** (`opex.crowdfunding.criteria`, semé en data) : adéquation
avec les domaines CEO, potentiel, caractère innovant, faisabilité apparente,
maturité minimale, besoin identifiable, crédibilité du porteur.

**Quatre méthodes de transition, une par issue :**

| Méthode | Effet |
|---|---|
| `action_go()` | → `dossier_progressif` |
| `action_clarify()` | → `clarification`, crée 1..N questions ciblées |
| `action_no_go()` | → `rejected`, motif obligatoire |
| `action_orientation()` | → `accompagnement` (maturation conseillée) |

`opex.crowdfunding.clarification` : `project_id`, `question`, `reponse`, `state`.
Le porteur répond, le dossier revient en `pre_analyse`.

⚠️ Écris bien quatre méthodes distinctes, pas une méthode avec un paramètre
`resultat`. C'est la manière texto, et c'est aussi ce qui rendra visible, à la fin,
le coût d'une cinquième issue.

---

## Extension 4 — Dossier progressif

**Section 7.** Le formulaire complémentaire, demandé **uniquement après un GO**.

Le document est explicite : le questionnaire dépend du besoin.

- besoin = investisseur → business model, marché, traction, équipe, besoin
  financier, utilisation des fonds, valorisation, prévisions financières, pitch deck
- besoin = sponsor → questionnaire différent
- besoin = financement public → encore un autre parcours

**En version texto, ça se code** : trois groupes de champs sur le modèle, trois
templates, et une condition `t-if` sur `besoin_type` pour afficher le bon.

Note dans le code, en commentaire, ce que ça coûterait d'ajouter un quatrième type
de besoin. Ce commentaire servira au document de comparaison final.

---

## Extension 5 — Quality Gate

**Section 8.**

`opex.crowdfunding.quality.control` : `project_id`, `controlled_by_id`, `date`, et
les vérifications du document — complétude, cohérence, qualité des informations,
conformité aux critères, anomalies, présence des justificatifs.

Avis structuré à **quatre valeurs** : `ok` / `a_completer` / `alerte` /
`non_conforme`.

Transitions : Conforme → `etude_decision` · À compléter → `quality_complement`
(retour porteur) · Alerte → notification CEO, dossier maintenu en `quality_gate`.

⚠️ Le document précise que le contrôleur humain sera un jour remplacé par un agent
IA « sans modification du workflow métier ». En version texto, ça veut dire une
chose concrète : `action_quality_ok()` ne doit pas vérifier *qui* l'appelle au-delà
du groupe. Isole la logique de contrôle dans une méthode dédiée pour que le
remplacement reste possible.

---

## Extension 6 — Étude et décision CEO

**Section 9.** Trois routes, trois méthodes.

| Route | Méthode | Effet |
|---|---|---|
| A — Investment Ready | `action_route_investment_ready()` | → `matching_financier` |
| B — Maturation nécessaire | `action_route_maturation()` | → `accompagnement` |
| C — Non retenu | `action_route_rejected()` | → `rejected`, motif obligatoire |

⚠️ « Le rejet ne doit pas être confondu avec la maturation. Un projet intéressant
mais insuffisamment mature reste dans le pipeline. » Les routes B et C ne partagent
aucun code, et un projet en route B reste visible dans tous les tableaux de bord.

---

## Extension 7 — Smart Matching financier

**Section 10.**

`opex.crowdfunding.matching.candidate` : `project_id`, `partner_id`,
`candidate_type` (investisseur, fonds, programme public, sponsor, banque,
partenaire stratégique), `score` (Float), `detail` (Text — **l'explication du
score**), `state` (`proposed`/`validated`/`excluded`/`added_manually`).

Critères pondérés, codés en dur : type de financement, secteur, ticket
d'investissement, stade du projet, localisation, appétence au risque, type de
porteur, impact, technologie, historique.

⚠️ « Le matching est une **recommandation**. » Le CEO peut Valider / Modifier /
Exclure / Ajouter un acteur. Aucune transition automatique sur la base d'un score.

Le champ `detail` est obligatoire : un score de 91 % sans explication n'est pas
défendable devant un jury.

---

## Extension 8 — Accompagnement CEO

**Sections 11 et 12.** La partie la plus riche du module — c'est un sous-processus
complet.

**Trois déclencheurs**, à implémenter tous les trois :
1. recommandation CEO (route B de l'étude)
2. demande de l'acteur financier (« intéressé sous condition d'accompagnement »)
3. demande directe du porteur, à tout moment autorisé du parcours

Le sous-processus : demande → diagnostic → proposition → contrepartie/conditions →
acceptation → matching expert(s) → mission → jalons → livrables → service fait →
évaluation.

Modèles : `opex.crowdfunding.accompagnement`, `opex.crowdfunding.mission`
(`expert_id`, `objectif`, `dates`, `contrepartie`), `opex.crowdfunding.jalon`,
`opex.crowdfunding.livrable`, `opex.crowdfunding.evaluation`.

### ⚠️ La contrepartie ne se code pas en dur

Le document est catégorique : « Le workflow ne doit pas coder en dur le modèle
économique. » Crée `opex.crowdfunding.compensation.type` semé en data — forfait,
commission au succès, success fee, participation, abonnement, prestation,
sponsoring, gratuité dans le cadre d'un programme, autre convention.

Précondition de la transition « accompagnement proposé → accompagnement actif » :
`convention_acceptee == True`.

C'est le seul endroit du module où la spécification demande explicitement de la
configuration plutôt que du code. Intéressant à relever dans le document de
comparaison : même l'approche texto a ses zones où le paramétrable s'impose.

À la fin : `action_reevaluation()` → `reevaluation`, puis retour vers
`matching_financier`. **La boucle doit exister** — c'est ce qui distingue ce
processus d'une séquence linéaire.

---

## Extension 9 — Mise en relation contrôlée

**Section 13.** Le point le plus sensible du module côté confidentialité.

> Le matching ne signifie pas automatiquement partage du dossier complet.

Séquence : match → teaser anonymisé → expression d'intérêt → autorisation de partage
→ NDA si nécessaire → dossier détaillé → meeting / data room.

`opex.crowdfunding.relation` : `project_id`, `partner_id`, `niveau_acces`
(`teaser`/`limited`/`full`), `autorise_par_id`, `nda_signe` (Boolean),
`date_autorisation`.

⚠️ Le teaser est **anonymisé** : ne rends jamais dans le HTML de la page teaser les
informations réservées au niveau supérieur, même masquées par CSS. Ici, « présent
dans le HTML » suffirait à violer la confidentialité.

Le contrôle du niveau d'accès est **une seule fonction**, appelée par toutes les
routes concernées (règle transversale 2).

---

## Extension 10 — Décision de l'acteur financier, closing et suivi

**Sections 14 et 15.**

Cinq actions simples côté acteur financier — il ne doit pas avoir à comprendre le
workflow interne :

```
★ Intéressé   ? Besoin d'informations   ↗ Demander accompagnement CEO
↔ Proposer un rendez-vous   ✕ Non intéressé
```

Chacune est une méthode qui traduit le choix en transition appropriée.
« Demander accompagnement CEO » renvoie vers le sous-processus de l'Extension 8 —
c'est le déclencheur n°2.

**Closing** (section 15) : `type_operation` (investissement, partenariat,
financement public, sponsoring, prêt, convention, autre), puis documents,
validations, signature, jalons, versements, reporting, engagements du porteur, suivi
post-financement.

> « Le dossier devient alors un projet suivi plutôt qu'une simple candidature. »

---

## Extension 11 — Les quatre interfaces et la Smart Work Queue

**Section 16.** Le principe :

> **Ne pas demander à l'utilisateur de piloter le workflow. Le workflow doit guider
> l'utilisateur.**

Quatre vues distinctes, chacune ne montrant que ce qui concerne son acteur :

- **Porteur** : progression en libellés lisibles + « Votre prochaine action »
- **Investisseur** : « 3 projets correspondent à vos critères », avec scores
- **Expert** : « Nouvelle mission proposée » + [Accepter] [Décliner]
- **CEO** : la **SMART WORK QUEUE** — préqualifications, contrôles en anomalie,
  décisions CEO, matchings à valider, investisseurs en attente, accompagnements en
  retard

Plus : notifications (portail + email, pas de SMS) et **audit trail** — historique
complet de qui a fait quoi, quand, pourquoi.

---

## Extension 12 — Le benchmark Demo Day

**Section 18 du document.** Ce n'est pas une extension de développement, c'est une
**mesure**. C'est le livrable qui donne son sens à tout le reste.

Applique au module texto exactement la demande faite aux stagiaires :

> « Ajoutez une étape Demo Day entre Accompagnement et Matching Investisseurs. Elle
> nécessite l'accord du CEO, une présentation Pitch Deck et une note ≥ 70/100. »

Fais-le réellement, proprement, et **mesure** :

| Métrique | À relever |
|---|---|
| Fichiers modifiés | `git diff --stat` |
| Lignes de Python ajoutées/modifiées | idem |
| Vues XML touchées | |
| Migration de données nécessaire ? | pour les dossiers déjà en base |
| Redémarrage / mise à jour du module ? | |
| Temps réel passé | chronométré |
| Compétence requise | développeur Odoo, ou utilisateur métier ? |

Puis la même demande dans le module générique, mesurée de la même façon.

Le tableau comparatif des deux colonnes **est** le résultat du travail. C'est lui
qui répond à la question que l'encadrant a posée en écrivant la section 18.

⚠️ Fais cette mesure **honnêtement**. Ne gonfle pas artificiellement le coût côté
texto : le résultat est déjà suffisamment net sans être forcé, et un jury repère
immédiatement une comparaison arrangée.

---

# Ordre d'implémentation

| Séquence | Extensions | Jalon |
|---|---|---|
| 1 | 1, 2 | Un porteur dépose un projet et suit son état |
| 2 | 3, 4, 5 | Pré-analyse à 4 issues, dossier progressif, Quality Gate |
| 3 | 6, 7 | Décision CEO à 3 routes, matching scoré |
| 4 | 8 | Accompagnement complet avec sa boucle de réévaluation |
| 5 | 9, 10 | Mise en relation contrôlée, décision financeur, closing |
| 6 | 11 | Les quatre interfaces, work queue, notifications, audit |
| 7 | 12 | Le benchmark |

**Si le temps manque** : les extensions 1, 3, 5, 6 et 8 constituent la colonne
vertébrale démontrable. Les extensions 9, 10 et 11 sont ce qu'on sacrifie en
premier, en l'annonçant.

---

# Hors périmètre — assumé

- Agent IA de contrôle qualité (le document le situe explicitement « à terme »)
- Signature électronique cryptographique — confirmation horodatée, comme sur le
  Module 1
- Data room, versements réels, intégration bancaire
- Apprentissage automatique sur le matching — le scoring est pondéré et explicable

---

# Méthode de travail

1. **Un prompt = une extension.** Jamais deux.
2. **État des lieux écrit avant tout code.**
3. **Arrêt pour test utilisateur** après chaque extension.
4. **Commit seulement après validation humaine.**
5. **Ce fichier mis à jour après chaque rapport.**
6. **Tests dans `tests/` versionné**, dès l'Extension 1.
7. **Jamais dans la même session que `opex_workflow`.** Règle d'isolation.