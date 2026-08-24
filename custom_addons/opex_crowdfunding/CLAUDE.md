# CLAUDE.md — `opex_crowdfunding`

**Smart Crowdfunding — implémentation texto (workflow codé en dur)**

---

## ⚠️ LIRE AVANT TOUTE MODIFICATION

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

### ⛔ Règle d'isolation — la plus importante de ce fichier

Le même développeur construit les deux modules. Le risque est donc la
contamination, dans les deux sens.

1. **`opex_crowdfunding` n'importe RIEN de `opex_workflow`.** Pas dans le
   manifeste, pas dans un `import`, pas dans une vue héritée. Vérifiable :

   ```bash
   grep -rn "opex_workflow\|opex\.workflow" opex_crowdfunding/ \
       --include='*.py' --include='*.xml' --include='*.csv'
   ```

   doit ne rien renvoyer.

   ⚠ La commande est **bornée au code**. Écrite sans `--include`, elle
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

⚠ **Il n'y a pas de `docs/` dans ce module.** Les documents sont partagés et
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

  ⚠ Son panneau central « STRUCTURE DE DONNÉES » contient une colonne intitulée
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
