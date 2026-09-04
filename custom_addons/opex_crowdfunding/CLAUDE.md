# CLAUDE.md — `opex_crowdfunding`

**Smart Crowdfunding — implémentation texto (workflow codé en dur)**

---

## LIRE AVANT TOUTE MODIFICATION

Ce module implémente **littéralement** le processus décrit dans
`../opex_membership/docs/Instance Smart Crowdfunding - CEO Smart Workflow (1).md` :
dix étapes, des états en dur, des méthodes de transition en Python. C'est
volontaire.

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

### Règle d'isolation — la plus importante de ce fichier

Le même développeur construit les deux modules. Le risque est donc la
contamination, dans les deux sens.

1. **`opex_crowdfunding` n'importe RIEN de `opex_workflow`.** Pas dans le
   manifeste, pas dans un `import`, pas dans une vue héritée. Vérifiable :

   ```bash
   grep -rn "opex_workflow\|opex\.workflow" opex_crowdfunding/ \
       --include='*.py' --include='*.xml' --include='*.csv'
   ```

   doit ne rien renvoyer.

   La commande est **bornée au code**. Écrite sans `--include`, elle
   remonterait les quatre occurrences de ce fichier-ci — celles de la règle
   qu'elle est censée vérifier — et renverrait donc toujours quelque chose. Une
   vérification qui ne peut jamais passer au vert est une vérification qu'on
   apprend à ignorer.
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

## Documents de référence

**Il n'y a pas de `docs/` dans ce module.** Les documents sont partagés et
vivent dans `../opex_membership/docs/`. Fais `ls ../opex_membership/docs/` et lis
ce qui s'y trouve avant de coder — les noms exacts, espaces et parenthèses
compris :

- **`Instance Smart Crowdfunding - CEO Smart Workflow (1).md`** — la spécification
  de ce module, section par section. C'est le document à implémenter **texto** :
  les sections 4 à 15 sont les dix étapes, la section 16 décrit les quatre
  interfaces utilisateur, la section 18 est le test final.
- **`INFOGRAPHIE-scf-1.png`** — le diagramme du workflow en haut de l'image est la
  vue de référence du processus, avec le détail des sorties de chaque étape. Elle
  est **plus précise que le texte sur les branchements** : c'est elle qui montre
  que le Quality Gate a quatre avis mais trois branches, et que l'étape 6 se
  dédouble en 6A (matching direct) et 6B (recommandation maturation).

  Son panneau central « STRUCTURE DE DONNÉES » contient une colonne intitulée
  **« WORKFLOW (MOTEUR GÉNÉRIQUE) »** — Workflow Definition, Stage, Transition,
  Rule, Instance History, Task. **Cette colonne décrit l'autre module.** La lire
  comme un modèle à implémenter ici tuerait l'expérience. Les colonnes qui
  concernent ce module sont RÉFÉRENTIELS, ENTITÉS MÉTIER, MATCHING & RELATIONS et
  ACCOMPAGNEMENT ; le workflow, lui, est remplacé par un `Selection` et des
  méthodes.
- **`PORTAIL DIGITAL DU GIC OPEX GROUP(Deltalog).pdf`** et
  **`Portail Digital du GIC OPEX Group rev1.0.pdf`** — le cahier des charges
  DELTALOG et la vision du portail, pour le contexte.
- `Diagrammes UML (1).pdf` — **inexploitable** : les images en sont uniformément
  noires. Ne pas perdre de temps dessus.
- `Module2_OPEX_Innovation_UX.pdf`, `MODULE1_OPEX_MEMBERSHIP_UX .pdf`,
  `_Product Backlog .md` — concernent les autres modules du portail.

En cas de divergence entre ce fichier et le document source sur un point
fonctionnel, **le document source fait foi**. Ce fichier donne la traduction
technique.

---

## Règles transversales — héritées de `opex_membership`

Payées cher sur le module précédent. Elles s'appliquent ici aussi.

1. **Collisions de nommage avec l'API interne d'Odoo.** `category_id`, `_register`,
   `stage_id`, `name_get` sont déjà pris à divers endroits. Une collision est
   souvent masquée silencieusement et échoue au runtime, pas au chargement.

   **1 bis — la même règle vaut entre nos propres modules, sur les controllers
   portail.** Découvert le 26/08 : `/my/projects` renvoyait 404 alors que le
   controller existait, était importé et que ses 12 templates étaient en base.
   `_generate_routing_rules()` (`odoo/http.py`) fusionne **toutes les classes
   feuilles d'un même arbre de controller** en une seule
   (`Ctrl = type(name, tuple(reversed(leaf_controllers)), {})`). `CustomerPortal`
   étant l'ancêtre commun de ce module, d'`opex_membership`, d'`opex_innovation`
   et du natif `project`, un nom partagé n'existe **qu'en un exemplaire** :

   - méthode de route → ses URL **disparaissent du routing map** (`portal_my_projects`
     et `portal_project_new` étaient pris par `opex_innovation` ; `/my/projects`,
     `/my/projects/page/<n>` et `/my/projects/new` sont tombés en 404, et le
     `/my/projects` du module natif `project` avec eux) ;
   - helper ou attribut de classe → **c'est le code du voisin qui s'exécute**.
     Mesuré sur la classe fusionnée : `_current_draft`, `_own_project`,
     `_save_step`, `_STEP_FIELDS` résolvaient vers `opex_innovation`,
     `_render_step` vers `opex_membership`, `_items_per_page` vers
     `opex_membership.ClusterPortal` (20 au lieu de 80).

   Ni erreur, ni avertissement. Seul le routing map réel le montre —
   `env['ir.http'].routing_map(key=1)`, pas la relecture du code.

   La ligne de partage est `super()` : une surcharge coopérative d'un hook natif
   (`_prepare_home_portal_values()`) traverse la MRO et s'exécute en chaîne —
   rien à craindre de ce côté. Le dégât ne touche que ce qui est défini
   indépendamment dans deux modules sans relayer `super()` : routes, helpers,
   constantes.

   **D'où la règle appliquée ici sans exception** : routes sous
   `/my/crowdfunding/…`, méthodes `portal_crowdfunding_*`, helpers
   `_crowdfunding_*`, constantes `_CROWDFUNDING_*`. Un nouveau point d'entrée
   qui ne respecte pas ce préfixe est un 404 en puissance.
2. **Un contrôle d'accès = une seule fonction, jamais recopiée.** Ici :
   `_is_ceo()`, `_is_quality_control()`, `_project_access_denied()`. Une
   vérification dupliquée finit par en oublier une occurrence.

   **Écart refermé le 26/08.** Ce qui manquait n'était pas la fusion des
   trois helpers d'appartenance — `_crowdfunding_own_project()`,
   `_crowdfunding_relation_du_partenaire()`,
   `_crowdfunding_mission_de_l_expert()` répondent à trois questions
   différentes, sur trois modèles différents (« ce projet est-il le mien ? »,
   « cette relation est-elle la mienne ? », « cette mission m'est-elle
   confiée ? ») ; les réunir aurait obscurci le code sans rien protéger de plus.
   Ils restent en place.

   Ce qui manquait, c'est le contrôle **de rôle** : « suis-je habilité à
   instruire ? ». Il n'existait nulle part, et il est désormais unique —
   `res.users._is_crowdfunding_staff()` (`models/res_users.py`), sur
   `group_ceo` + `group_quality_control`, appelé par la tuile d'accueil du
   portail. Posé sur `res.users` et non dans le controller pour qu'un gabarit
   puisse l'appeler : une liste de groupes recopiée dans un `t-if` aurait
   divergé de celle de la route au premier rôle ajouté. `opex_innovation` a
   reçu le même traitement (`_is_innovation_staff()`, que `_staff_user()`
   interroge au lieu de refaire le test), `opex_membership` l'avait déjà
   (`_is_opex_staff()`).

   **2 bis — un `search()` dans un gabarit fait tomber la page d'un autre.**
   Payé ici le 26/08 : un compte du **comité d'évaluation** (`opex_innovation`,
   utilisateur interne) recevait un **403 sur `/my`** — *« You are not allowed
   to access 'Projet Smart Crowdfunding' »*. La cause était notre tuile
   d'accueil, qui comptait ses projets en QWeb :

   ```xml
   <t t-set="count" t-value="request.env['opex.crowdfunding.project'].search_count(...)"/>
   ```

   Un `search_count()` en QWeb s'exécute **sous l'identité du visiteur**. Nos
   ACL n'ouvrent `opex.crowdfunding.project` qu'à `group_ceo`,
   `group_quality_control` et `base.group_portal` — c'est correct, un comité
   d'évaluation n'a rien à y lire. Mais l'`AccessError` levée en plein rendu
   emportait **l'accueil du portail entier**, celui de tous les modules.
   Le controller, lui, faisait déjà le contrôle proprement
   (`if not Project.has_access('read'): redirect('/my')`) — et renvoyait donc
   vers une page qui plantait.

   **Le contrôle d'accès vit dans le controller, jamais dans le gabarit.** Les
   trois compteurs sont passés dans `_prepare_home_portal_values()`, gardés par
   `has_access('read')`, qui répond au lieu de lever. Et **`sudo()` n'est pas la
   parade** : les tuiles « opportunités » et « missions » l'utilisaient, ce qui
   n'échouait pas mais supprimait ACL *et* `ir.rule` sans laisser de trace.
   Elles comptent maintenant sans `sudo()`.

   Ne jamais corriger ce genre de 403 en élargissant l'ACL : si un rôle n'a
   pas accès au modèle, c'est en général qu'il ne devrait pas y toucher.
   **2 ter — le contrat de `/my/counters` est une condition de fonctionnement.**
   Payé le 26/08, dans la foulée du correctif précédent. Un compteur de tuile se
   déclare **des deux côtés, ou d'aucun** : `placeholder_count` dans le gabarit
   (qui pose le nœud `[data-placeholder_count]`), et `if 'x_count' in counters:`
   dans `_prepare_home_portal_values()`. `portal_home_counters.js` fait pour
   *chaque clé reçue* `querySelector(...).textContent = …` ; une clé sans nœud
   donne `null`, la boucle lève, le `Promise.all` est rejeté et **tout le
   JavaScript de l'accueil meurt** — compteurs vides, tuiles jamais démasquées,
   boîte « Oops! » — pour **tous** les utilisateurs, pas seulement ceux de ce
   module. Nos trois compteurs calculés sans regarder `counters` ont suffi.
3. **« Présent dans le HTML » ≠ « visible à l'écran ».** Un test qui vérifie
   `'texte' in body` passe alors que l'utilisateur ne voit rien.

   **2 quater — un `placeholder_count` n'appartient qu'à une seule tuile.**
   Corollaire, payé le 27/08 côté `opex_innovation` : deux tuiles déclaraient le
   même compteur. `portal_home_counters.js` le résout par `querySelector()`, qui
   ne renvoie que le **premier** nœud — la seconde tuile n'était démasquée qu'au
   rechargement suivant, via le cache de session, donc jamais au moment où
   quelqu'un découvre son espace. Un compteur, une tuile, et le domaine du
   compteur est exactement celui de l'écran qu'il annonce. Vérification :
   `grep -rn 'placeholder_count"' --include='*.xml' opex_*/views/ | sort` — aucun
   nom ne doit sortir deux fois.

   **2 quinquies — `portal_searchbar` n'affiche pas toujours le `title` posé.**
   Il n'est rendu que dans la branche `t-else`, quand `breadcrumbs_searchbar` est
   **faux**. Nos écrans le mettent à vrai : le libellé visible vient alors du fil
   d'Ariane (`portal.portal_breadcrumbs`), et le `t-set="title"` de la searchbar
   ne sert à rien. Constaté le 27/08 en renommant `/my/crowdfunding` — le titre
   changé n'apparaissait nulle part, gabarit pourtant juste. **Un libellé qui ne
   s'affiche pas : lire la page rendue, pas le gabarit.**

   **3 bis — le spinner qui reste EST le symptôme.**
   `portal_home_counters.js` supprime `.o_portal_doc_spinner` **après** le
   `Promise.all`. Un spinner encore visible sur l'accueil = une promesse
   rejetée. Il figurait sur mes captures pendant deux tours sans être relevé :
   **spinner figé ⇒ ouvrir la console avant de conclure.**

   **3 ter — un test HTTP ne verra jamais une erreur JavaScript.**
   `url_open()` et `requests.get()` lisent le HTML **du serveur** ; ils passent
   au vert pendant qu'une exception JS vide la page. Screenshot d'un HTML
   sauvegardé : même limite, les RPC ne partent pas. Tout écran portail qui
   dépend du JS — compteurs, démasquage de tuiles, interactions `Colibri` — se
   vérifie **dans un vrai navigateur, console ouverte, session réelle**.
4. **`mail.mt_note` pour tout message interne.** `mail.mt_comment` uniquement pour
   ce que le porteur doit recevoir par email. Bug déjà rencontré et corrigé.

   **4 bis — Ce module est HORS de la cloche portail, et c'est un choix.**

   Le portail a une cloche de notification, servie par `opex_membership` : les
   comptes portail ne supportent pas la cloche native d'Odoo, interdite en base
   par `CHECK (notification_type = 'email' OR NOT share)`. Elle lit les
   `mail.message` posés sur les enregistrements d'un contact, via
   `res.partner._opex_owned_record_ids()`.

   **Les 41 `message_post()` de ce module n'y apparaissent pas.** Un porteur
   Smart Crowdfunding ne reçoit donc aucune notification à l'écran : ni cloche,
   ni email (voir la limite SMTP ci-dessous). Il découvre l'avancement de son
   dossier en rouvrant `/my/crowdfunding/<id>`, où l'historique est complet.

   **Pourquoi ce n'est pas corrigé.** La surcharge existe pourtant, écrite et
   correcte, dans `models/res_partner.py` — mais elle est **inatteignable**.
   Mesuré le 28/08, le MRO de `res.partner` est :

   ```
   opex_innovation → opex_membership → opex_crowdfunding
   ```

   et la méthode d'`opex_membership` est l'implémentation d'origine : elle
   renvoie un dictionnaire littéral **sans relayer `super()`**. La chaîne
   s'arrête chez elle. L'ordre du MRO suit l'ordre de chargement, lui-même issu
   du graphe de dépendances : ce module ne dépendant de rien, il est chargé en
   premier, donc placé en dernier.

   La seule façon de le rendre actif est de le charger **après**
   `opex_membership`, c'est-à-dire d'ajouter cette dépendance au manifeste.
   **Arbitrage rendu le 28/08 : non.** La règle d'isolation est le fondement de
   la comparaison entre les deux approches ; on ne peut pas présenter deux
   modules « indépendants, sauf pour les notifications ». Le coût est réel et
   assumé, et il se dit tel quel en soutenance.

   Le code est conservé, avec son avertissement en tête de docstring, parce
   qu'il devient actif sans une ligne de plus le jour où la dépendance serait
   acceptée.

   **4 ter — Aucune notification email n'est délivrée dans cet
   environnement.** `odoo.conf` pointe `smtp_server = localhost:25`, où rien
   n'écoute. Mesuré le 28/08 : 48 `mail.notification` et 68 `mail.mail` en
   `exception`. À annoncer avant toute démonstration. Ce qui fonctionne côté
   personnel : la cloche **native** d'Odoo, activée en données depuis le 28/08
   pour le Comité CEO et le Contrôle Qualité
   (`res.users._opex_crowdfunding_enable_inbox()`, appelée par un
   `<function>` de `security/security.xml`).
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

**Section 5 du document.** — *Faite le 24/08. 14 tests dans
`tests/test_extension1.py`, tous verts, vérifiés falsifiables.*

`opex.crowdfunding.project` avec les informations minimales — et **rien de plus** :
`partner_id`, `porteur_type` (Selection : personne physique, startup, entreprise,
groupe, association, autre personne morale), `name` (titre du projet), `probleme`
(Text), `solution` (Text), `secteur`, `maturite`, `besoin_type` (Selection :
financement, accompagnement, partenariat…), `montant_indicatif` (Monetary),
`pitch_document` (Binary, **facultatif**).

Le principe du *progressive commitment* est le cœur du document : on ne demande
que le minimum nécessaire pour décider de l'étape suivante. Ne pas ajouter ici les
champs du dossier complet « puisqu'on y sera de toute façon » — ce serait passer à
côté de la spécification.

**Groupes** via `res.groups.privilege` : `group_ceo`, `group_quality_control`,
`group_expert`, `group_financial_actor`. Le porteur utilise `base.group_portal`.

**Méthode** `action_submit()` : `draft → depot_express`.

**Tests versionnés dans `tests/`** dès cette extension.

---

## Extension 2 — Portail porteur

**Sections 5 (UX) et 16.** — *Faite le 25/08. 23 tests dans
`tests/test_extension2.py` (portail + sécurité), 37 au total, tous verts.*

Piège du portail confirmé dans le code d'Odoo 19 : `portal.portal_docs_entry`
rend la tuile avec `d-none`, et `portal_home_counters.js` ne la réaffiche que si
le compteur revient **strictement positif**. Une tuile posée avec
`placeholder_count` est donc invisible pour qui n'a encore rien déposé —
exactement le porteur qu'on attend. Ici : `config_card="True"`, compteur calculé
dans le gabarit, et un test qui vérifie l'absence de `d-none` sur la carte.

Routes : `/my/crowdfunding`, `/my/crowdfunding/new`, `/my/crowdfunding/<id>`.

**Renommées le 26/08** (correctif du 404, cf. règle transversale 1 bis). Tout
l'espace de noms du portail est passé sous `/my/crowdfunding/…` : les projets à
la racine, `/my/crowdfunding/opportunities/…` pour l'acteur financier,
`/my/crowdfunding/missions/…` pour l'expert. Les anciens chemins `/my/projects`,
`/my/opportunities` et `/my/missions` ne sont **pas** conservés en redirection —
ils appartiennent à l'espace de noms générique qui a causé la collision.

Le CTA est **« Présenter mon projet »**, jamais « Constituer mon dossier de
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
apparaît. — *Faite le 25/08. 23 tests dans `tests/test_extension3.py`, 60 au
total, tous verts.*

Ajouté hors liste, parce que l'étape n'avait pas de porte d'entrée :
`action_start_pre_analyse()` (`depot_express` → `pre_analyse`). Sans elle un
dossier déposé restait indéfiniment en « Demande déposée ».

Piège Odoo rencontré : le nom de table auto-généré du Many2many
préqualification ↔ critères fait 64 caractères, une de trop pour PostgreSQL, et
**le registre refuse de démarrer** avec un message sans rapport apparent. Table
nommée à la main (`opex_cf_prequalification_criteria_rel`).

**Deuxième zone paramétrable imposée par la spécification** : « selon des
critères configurables » (§6). Les sept critères sont semés en données, pas
écrits dans le code — comme la contrepartie de l'Extension 8. À faire figurer
tel quel dans le document de comparaison : le module texto n'est pas 100 % en
dur, et le dire renforce la comparaison au lieu de l'affaiblir.

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

Écris bien quatre méthodes distinctes, pas une méthode avec un paramètre
`resultat`. C'est la manière texto, et c'est aussi ce qui rendra visible, à la fin,
le coût d'une cinquième issue.

---

## Extension 4 — Dossier progressif

**Section 7.** Le formulaire complémentaire, demandé **uniquement après un GO**.
— *Faite le 25/08. 17 tests dans `tests/test_extension4.py`, 77 au total, tous
verts.*

Le décompte du **coût d'un quatrième type de besoin** est dans la docstring de
`_champs_dossier_requis()` : **cinq fichiers, ≈ 114 lignes**, chiffres comptés
sur la branche « sponsor » et non estimés. Les questionnaires sponsor et
financement public sont des déductions — le document ne les détaille pas.

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

**Section 8.** — *Faite le 25/08. 23 tests dans `tests/test_extension5.py`, 100
au total, tous verts.*

**Quatre avis, trois sorties** : `alerte` et `non_conforme` empruntent la même
transition (`action_quality_alerte`), conformément au bloc RÉSULTAT de
l'infographie qui les réunit en une seule sortie rouge. Le contrôle qualité
signale, il n'écarte jamais un projet lui-même.

La contrainte « remplaçable par un agent IA » est tenue par `_avis_suggere()`,
seule méthode qui juge, et par l'absence totale de contrôle d'identité dans les
trois transitions. Un test le prouve : la fiche remplie par un contrôleur peut
être conclue par un autre.

Sortie d'une alerte : le dossier reste en `quality_gate` et un **second
contrôle** le débloque. Le document ne dit pas ce que le comité fait d'une
alerte ; c'est le seul chemin de sortie implémenté.

`opex.crowdfunding.quality.control` : `project_id`, `controlled_by_id`, `date`, et
les vérifications du document — complétude, cohérence, qualité des informations,
conformité aux critères, anomalies, présence des justificatifs.

Avis structuré à **quatre valeurs** : `ok` / `a_completer` / `alerte` /
`non_conforme`.

Transitions : Conforme → `etude_decision` · À compléter → `quality_complement`
(retour porteur) · Alerte → notification CEO, dossier maintenu en `quality_gate`.

Le document précise que le contrôleur humain sera un jour remplacé par un agent
IA « sans modification du workflow métier ». En version texto, ça veut dire une
chose concrète : `action_quality_ok()` ne doit pas vérifier *qui* l'appelle au-delà
du groupe. Isole la logique de contrôle dans une méthode dédiée pour que le
remplacement reste possible.

---

## Extension 6 — Étude et décision CEO

**Section 9.** Trois routes, trois méthodes. — *Faite le 25/08. 17 tests dans
`tests/test_extension6.py`, 117 au total, tous verts.*

« Reste dans le pipeline » a été rendu mesurable : champ `in_pipeline`
(calculé, stocké) dérivé de `_ETATS_HORS_PIPELINE`, et le filtre « En cours » de
la vue de recherche s'appuie dessus au lieu de recopier une liste d'états. Un
test vérifie le filtre lui-même — c'est le seul moyen d'empêcher un futur
tableau de bord de ranger la maturation avec les refus.

`test_aucune_route_n_en_appelle_une_autre` lit le source des trois méthodes et
échoue si l'une cite le nom d'une autre. C'est la forme testable de « les routes
B et C ne partagent aucun code ».

Seul `_ensure_ceo()` est commun aux trois routes — la règle transversale n°2
interdit de recopier un contrôle d'accès. Les préconditions d'état, elles, sont
écrites trois fois.

| Route | Méthode | Effet |
|---|---|---|
| A — Investment Ready | `action_route_investment_ready()` | → `matching_financier` |
| B — Maturation nécessaire | `action_route_maturation()` | → `accompagnement` |
| C — Non retenu | `action_route_rejected()` | → `rejected`, motif obligatoire |

« Le rejet ne doit pas être confondu avec la maturation. Un projet intéressant
mais insuffisamment mature reste dans le pipeline. » Les routes B et C ne partagent
aucun code, et un projet en route B reste visible dans tous les tableaux de bord.

---

## Extension 7 — Smart Matching financier

**Section 10.** — *Faite le 25/08, alors qu'elle avait été sacrifiée le 24/08.
Le périmètre arrêté plus haut est donc dépassé d'une extension : la boucle de 8
et le benchmark (12) restent à faire. 22 tests dans `tests/test_extension7.py`,
139 au total, tous verts.*

Dix critères pondérés (20/15/15/10/8/8/6/6/6/6 = 100), une méthode
`_critere_*` chacun, rendant sa contribution **et son explication**. Aucun
apprentissage : `detail` reconstitue le score ligne par ligne, et un test vérifie
que la somme des contributions écrites égale bien le score affiché.

Le profil d'acteur financier vit sur `res.partner`, tous champs préfixés
`cf_` : Membership étend le même modèle, et une collision y serait silencieuse
au chargement puis fatale au runtime.

Deux critères sont **déduits du secteur** (impact, technologie) faute de champ
dédié dans le dépôt express — ajouter ces champs aurait alourdi le formulaire du
porteur pour deux critères sur dix. Simplification assumée, à mentionner si le
jury creuse.

« Le matching est une recommandation » : aucune méthode du modèle candidat ne
touche à l'état du projet. Seul `action_validate_matching()`, geste explicite du
comité, met en relation.

`opex.crowdfunding.matching.candidate` : `project_id`, `partner_id`,
`candidate_type` (investisseur, fonds, programme public, sponsor, banque,
partenaire stratégique), `score` (Float), `detail` (Text — **l'explication du
score**), `state` (`proposed`/`validated`/`excluded`/`added_manually`).

Critères pondérés, codés en dur : type de financement, secteur, ticket
d'investissement, stade du projet, localisation, appétence au risque, type de
porteur, impact, technologie, historique.

« Le matching est une **recommandation**. » Le CEO peut Valider / Modifier /
Exclure / Ajouter un acteur. Aucune transition automatique sur la base d'un score.

Le champ `detail` est obligatoire : un score de 91 % sans explication n'est pas
défendable devant un jury.

---

## Extension 8 — Accompagnement CEO

**Sections 11 et 12.** La partie la plus riche du module — c'est un sous-processus
complet. — *Faite en entier le 25/08 (et pas seulement sa boucle, comme le
périmètre du 24/08 le prévoyait). 32 tests dans `tests/test_extension8.py`, 171
au total, tous verts.*

**Les trois déclencheurs ne se comportent pas de la même façon**, et c'est
délibéré : la recommandation du comité (route B) fait basculer le dossier dans
l'étape « Accompagnement CEO » du parcours principal ; la condition d'un acteur
financier et la demande du porteur ouvrent un **sous-workflow qui tourne à
côté**, sans dérouter le dossier. Un porteur qui demande de l'aide pendant que
son dossier est au contrôle qualité ne doit pas sortir du contrôle qualité.

La boucle est complète et testée de bout en bout : étude → route B →
accompagnement → service fait → réévaluation → **retour au matching financier**.

Le « service fait » a un sens vérifié : toutes les missions terminées, tous
les livrables validés. Sinon la formule ne voudrait rien dire.

**Zone paramétrable imposée** (la seconde après les critères de pré-analyse) :
`opex.crowdfunding.compensation.type`, neuf types semés en données. Un test
structurel vérifie que le champ reste un Many2one vers ce référentiel — si
quelqu'un le remplace un jour par un `Selection` « c'est plus simple », il aura
codé en dur le modèle économique, ce que la section 12 interdit.

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

### La contrepartie ne se code pas en dur

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

**Section 13.** Le point le plus sensible du module côté confidentialité. —
*Faite le 25/08. 23 tests dans `tests/test_extension9.py`, 194 au total, tous
verts.*

**Le contrôle vit dans une seule méthode**, `relation._portal_payload()`, qui
renvoie `(gabarit, valeurs)`. Les trois niveaux ne se distinguent pas par des
`t-if` : chaque gabarit ne reçoit que les valeurs de son niveau. Ni la relation
ni le projet ne sont passés au gabarit — avec l'enregistrement en main, un
`t-out="relation.project_id.name"` contournerait tout le filtrage.

Aucun droit d'écriture portail sur `opex.crowdfunding.relation` : avec
`perm_write` à 1, une requête forgée poserait `niveau_acces = 'full'` sur sa
propre relation. Les deux gestes autorisés passent par des méthodes appelées par
le contrôleur après vérification d'appartenance.

**Piège n°6, variante coûteuse — trouvée en falsifiant, pas en relisant.**
Le test central cherchait les données réservées dans le HTML brut… avec des
chaînes contenant une apostrophe. QWeb rend `'` en `&#39;` : l'assertion ne
pouvait donc jamais échouer. Une fuite volontaire (`titre` passé au gabarit puis
masqué en `d-none`) est passée **au vert**. Corrigé en déséchappant la réponse
avant la recherche (`html.unescape`) ; la même fuite fait maintenant tomber
3 tests.

**Règle à retenir pour les extensions suivantes** : toute assertion négative sur
du HTML doit porter sur du texte déséchappé, et tout `assertNotIn` doit être
prouvé falsifiable avant d'être cru.

> Le matching ne signifie pas automatiquement partage du dossier complet.

Séquence : match → teaser anonymisé → expression d'intérêt → autorisation de partage
→ NDA si nécessaire → dossier détaillé → meeting / data room.

`opex.crowdfunding.relation` : `project_id`, `partner_id`, `niveau_acces`
(`teaser`/`limited`/`full`), `autorise_par_id`, `nda_signe` (Boolean),
`date_autorisation`.

Le teaser est **anonymisé** : ne rends jamais dans le HTML de la page teaser les
informations réservées au niveau supérieur, même masquées par CSS. Ici, « présent
dans le HTML » suffirait à violer la confidentialité.

Le contrôle du niveau d'accès est **une seule fonction**, appelée par toutes les
routes concernées (règle transversale 2).

---

## Extension 10 — Décision de l'acteur financier, closing et suivi

**Sections 14 et 15.** — *Faite le 25/08. 28 tests dans
`tests/test_extension10.py`, 222 au total, tous verts.*

Cinq méthodes sur `opex.crowdfunding.relation`, une par bouton. Un test vérifie
qu'**aucun code d'état** n'apparaît dans le HTML de l'écran acteur (recherche sur
le HTML déséchappé, leçon de l'Extension 9). Les boutons n'apparaissent qu'à
partir du dossier limité : au teaser, l'acteur n'a rien lu qui permette de
décider.

« Demander accompagnement CEO » rebranche sur le déclencheur n°2 de
l'Extension 8. **Défaut trouvé en le branchant** : `action_accompagnement_
demande_financeur()` cherchait le demandeur parmi les candidats au matching, et
ne le trouvait pas quand la demande venait d'une relation. La méthode accepte
maintenant le `partner` que l'appelant connaît.

La nature de l'opération commande ses exigences (`EXIGENCES_PAR_TYPE`) :
documents, échéancier, reporting. `action_close()` refuse tant qu'elles ne sont
pas satisfaites — « clôturé » veut dire quelque chose. Une huitième nature = une
entrée dans la table + une valeur de Selection + un redéploiement.

Cinq actions simples côté acteur financier — il ne doit pas avoir à comprendre le
workflow interne :

```
Intéressé   ? Besoin d'informations   ↗ Demander accompagnement CEO
↔ Proposer un rendez-vous   Non intéressé
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

**Section 16.** — *Faite le 26/08. 25 tests dans `tests/test_extension11.py`,
247 au total, tous verts. **Fin du module fonctionnel** : reste l'Extension 12,
le benchmark.*

Les quatre écrans sont vérifiés avec **un compte de chaque acteur**, et un
garde commun (`_assert_aucun_code_etat`) balaye chaque page à la recherche des
onze codes d'états — sur le HTML déséchappé, attributs `href`/`action` retirés
(une route nommée `/accompagnement/demander` n'expose pas un état).

Six décisions passées en `mt_comment` (GO, orientation, routes A et B,
clarifications, refus). Le **motif** d'un refus reste en `mt_note` : le porteur
reçoit la décision, pas l'argumentaire d'instruction. Choix réversible d'une
ligne, signalé dans le code.

Smart Work Queue : six compteurs, six domaines définis **une seule fois** et
utilisés pour compter et pour ouvrir. Le test compare le compteur au domaine que
le **bouton** ouvre — première version tautologique, corrigée — et garnit chaque
file, sans quoi il passerait au vert avec six zéros.

**Deux pièges Odoo 19 découverts ici :**
1. `target="inline"` n'existe plus sur `ir.actions.act_window` : le module refuse
   de s'installer, avec un `ParseError` qui ne nomme pas la valeur fautive.
2. **Odoo désactive le suivi des champs pour un enregistrement créé dans la
   transaction courante.** Créer un projet puis changer son état dans le même
   test ne laisse aucune trace, et tout historique bâti dessus paraît vide sans
   que rien ne soit cassé. En production les deux gestes sont dans deux
   requêtes ; en test, il faut vider le marqueur
   (`cr.precommit.data.pop('mail.tracking.<modèle>')`) puis
   `cr.precommit.run()`.

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

Fais cette mesure **honnêtement**. Ne gonfle pas artificiellement le coût côté
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

## Périmètre arrêté le 24/08

Le budget réel a été tranché : **1, 2, 3, 4, 5, 6, la boucle de réévaluation de
8, et 12.** Le reste est annoncé comme non fait.

| Décision | Motif |
|---|---|
| **7 sacrifiée en entier** | Le scoring pondéré est ce sur quoi le module générique doit briller ; le refaire ici en dur coûte cher pour une démonstration que la comparaison n'exploitera pas. L'état `matching_financier` reste, la transition y mène, le moteur de matching non. |
| **4 gardée avec ses trois branches** | C'est précisément ce que le benchmark mesure. Ne pas la replier sur un questionnaire unique. |
| **Le quatrième type de besoin sera ajouté et chronométré**, pas estimé en commentaire | Un coût réel face à zéro dans le module générique vaut mieux qu'une estimation. Cela remplace la consigne « note en commentaire ce que ça coûterait » de l'Extension 4. |
| **8 réduite à sa boucle** | La boucle accompagnement → réévaluation → matching est ce qui distingue le processus d'une séquence linéaire. Le sous-processus complet (missions, jalons, livrables, évaluation) ne l'est pas. |
| **12 non sacrifiable** | C'est elle qui fait de ce module la moitié d'une expérience plutôt qu'un second module métier. |
| **9, 10, 11 hors périmètre** | Conformément à l'ordre de sacrifice ci-dessus. |

La zone paramétrable de l'Extension 8 — `compensation.type`, la contrepartie
que le document interdit de coder en dur — **reste dans le périmètre et ira telle
quelle dans le document de comparaison**. C'est le seul endroit où la
spécification impose du paramétrable dans le module texto ; le taire rendrait la
comparaison moins honnête.

---

# `/staff/crowdfunding` — un écran de démonstration, et ce qu'il ne couvre pas

**À dire tel quel en soutenance.** Ajouté le 27/08, après avoir d'abord
tranché l'inverse (tuile pointant sur le back-office) : la démonstration ne doit
pas quitter le site. Trois routes, calquées sur `/staff/innovation` :

| Route | Contenu |
|---|---|
| `/staff/crowdfunding` | la file, filtrée par rôle |
| `/staff/crowdfunding/<id>` | le dossier **en lecture seule** + les décisions ouvertes à ce rôle à cette étape |
| `/staff/crowdfunding/<id>/action` | l'exécution, POST, déléguée à la méthode du modèle |

**Les files réutilisent les six domaines de `opex.crowdfunding.work.queue`**,
sans les réécrire : la même définition compte dans le back-office et liste dans
le portail. Deux nuances :

- la file du **Contrôle Qualité** ajoute `state = quality_gate` à
  `_domaine_controles_anomalie()`. Les six files du back-office n'ont pas de
  file « dossiers attendant un premier contrôle » ; s'en tenir aux anomalies
  aurait privé le rôle de son travail principal ;
- « investisseurs en attente » et « accompagnements en retard » portent sur
  `relation` et `accompagnement`, pas sur des dossiers : affichées **en
  compteur seul**, avec la mention qu'elles se traitent au back-office.

**Contrôle d'accès** : `res.users._is_crowdfunding_staff()` en première ligne
de chaque route, puis `_crowdfunding_staff_project()` qui ne retrouve un
dossier qu'**à travers la file du rôle** — un identifiant forgé ne remonte rien
plutôt que de lever. Le nom de méthode reçu en POST n'est jamais appelé tel
quel : il est cherché dans la table des actions ouvertes à ce rôle à cette
étape, et le modèle revérifie ensuite (`_ensure_ceo`,
`_ensure_quality_control`). Aucun `t-if` ne sert de garde.

## Ce que cet écran NE fait PAS — la liste à connaître avant de le montrer

1. **Aucune saisie du dossier.** Le formulaire back-office du projet compte
   **144 champs** ; ici tout est en lecture seule. Corriger une donnée impose
   le back-office.
2. **Ni la préqualification, ni la fiche de contrôle qualité.** Les sept
   critères, le commentaire, le résultat d'un côté ; les cinq cases, les
   anomalies et l'avis à quatre valeurs de l'autre — **saisis au back-office**.
   Les boutons du portail ne font que *conclure* : `action_quality_ok()` exige
   une fiche dont l'avis correspond déjà (`_ensure_quality_gate_control`), et
   `action_clarify()` exige au moins une question déjà rédigée. Sans elles, le
   bouton renvoie le message du modèle — c'est voulu, pas un bug.
3. **Le matching financier n'y est pas.** Valider / modifier / exclure /
   ajouter un acteur, les scores et leur explication : back-office. L'étape
   `matching_financier` apparaît dans la file du comité, sans bouton.
4. **L'accompagnement n'y est pas** : missions, jalons, livrables,
   contrepartie — quatre modèles liés.
5. **Le closing n'y est pas** : documents à valider un par un, échéancier,
   versements, suivi post-financement.
6. **Pas de chatter** : ni suivi, ni relance, ni pièce jointe. L'historique
   affiché est celui du porteur (`_portal_historique()`, `mt_comment` +
   changements d'état) — **pas** le journal d'instruction complet.
7. **Pas de filtres, de regroupements, de tri, d'export, ni de vue liste
   éditable.** La vue de recherche du back-office (filtre « En cours », par
   étape, par secteur) n'a pas d'équivalent.
8. **Pas d'activités planifiées** (`mail.activity`) ni de rappels.

Chaque fiche porte en bas un lien discret **« Ouvrir dans le back-office »**
vers ces huit cas. Le jury ne le verra pas si la démonstration se déroule bien.

**Coût accepté** : un second jeu de contrôles d'accès à tenir d'accord avec
les ACL et les groupes des menus. Il est réduit au minimum — le controller
délègue toute décision au modèle — mais il existe, et c'est l'argument qui
avait fait préférer le back-office le 26/08.

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
