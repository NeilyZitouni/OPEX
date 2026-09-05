# CLAUDE.md — `opex_intervenants`

**Module 3 — OPEX Intervenants / Smart Missions**
Appels à candidatures · Matching Mission-Expert · Exécution · Réputation

---

## ⚠️ LIRE AVANT TOUTE MODIFICATION

Ce module est le **troisième domaine métier** du Portail Digital du GIC OPEX Group.
Il se construit sur le moteur générique `opex_workflow`, exactement comme
`opex_innovation`.

### La règle qui gouverne tout le reste

> **Le module ne code aucun workflow. Il en configure deux.**

`opex.mission.request` et `opex.mission.application` **n'ont aucun champ
`state`**. Leur avancement est `workflow_instance_id.current_stage_id`, piloté par
une définition en data XML.

C'est la démonstration de tout le travail des deux modules précédents : un
troisième domaine métier, complet, sans une ligne de Python ajoutée au moteur.
Si quelqu'un ajoute un `state = fields.Selection(...)` « pour aller plus vite »,
cet argument tombe.

### Les deux machines à états sont SÉPARÉES

La spécification est catégorique :

> « La séparation des deux machines à états est obligatoire : l'avancement global
> de la mission ne doit pas être confondu avec le parcours individuel de chaque
> candidat. »

Donc **deux définitions de workflow, sur deux modèles distincts**. Une mission en
`SELECTION` peut avoir simultanément trois candidatures en `SHORTLISTED`, une en
`REJECTED` et deux en `APPLIED`. Ne jamais dériver l'un de l'autre.

C'est aussi le meilleur banc d'essai du moteur à ce jour : deux workflows qui
tournent en parallèle sur des objets liés.

---

## La machine à états de la mission — arbitrage rendu

Les deux documents fournis n'en donnaient pas la même. **La version retenue est
celle de `Specification_OPEX_Smart_Missions.md`, §12.1.** Arbitrage de l'auteur
des deux documents, il n'y a plus à y revenir.

### Mission — `opex.mission.request`

```
DRAFT → QUALIFIED → SOURCING → OPEN → SELECTION → AWARDED → CONTRACTING
      → IN_PROGRESS → DELIVERED → ACCEPTED → CLOSED
```

Branches : `ON_HOLD` · `CANCELLED` · `UNSUCCESSFUL`.

### Candidature — `opex.mission.application`

```
INVITED → VIEWED → INTERESTED → APPLIED → SCREENED → SHORTLISTED → SELECTED
```

Branches : `DECLINED` · `REJECTED` · `WITHDRAWN`.

⚠️ **`DECLINED` est réversible**, les trois autres fins ne le sont pas. Une
transition `reconsider : DECLINED → VIEWED` existe.

Raison : avec le §12.2, `DECLINED` est atteignable **dès `INVITED`**. Un expert
qui décline une invitation ciblée, sur un appel qui sera ensuite publié au
portail, doit pouvoir revenir. Sans cette transition, la contrainte
`unique(mission_id, partner_id)` lui ferme l'appel définitivement : le moteur
clôt l'instance en atteignant une étape `is_end` (`state = 'done'`), et
`_check_transition_allowed()` refuse alors tout, donc plus aucun chemin de
retour — et la contrainte SQL interdit une seconde candidature.

`SELECTED`, `REJECTED` et `WITHDRAWN` restent `is_end` : un candidat écarté par
le responsable ne se réinvite pas lui-même, et un retrait volontaire après
dépôt est un acte réfléchi.

### Correspondance avec le document UX

`Module3_OPEX_Intervenants.md` décrit les écrans avec d'autres noms d'états. Ils
ne sont **pas** repris comme étapes : ce sont des libellés d'affichage, à mettre
dans `user_label`, ou des sous-états qui n'ont pas besoin d'exister dans le
graphe.

| Document UX | Étape retenue |
|---|---|
| SUBMITTED | `QUALIFIED` (l'entrée dans le circuit de qualification) |
| VALIDATED | `QUALIFIED` |
| PUBLISHED · APPLICATIONS | `SOURCING` puis `OPEN` |
| CONTRACT_PENDING · CONTRACT_SIGNED | `AWARDED` puis `CONTRACTING` |
| SCHEDULED | `CONTRACTING` (fin) ou `IN_PROGRESS` (début) |
| DELIVERABLE_VALIDATION | `DELIVERED` |
| COMPLETED | `ACCEPTED` |
| INVOICED | `ACCEPTED` → `CLOSED`, la facturation étant une action, pas une étape |
| SUSPENDED | `ON_HOLD` |
| REJECTED | `UNSUCCESSFUL` |

⚠️ Cette table de correspondance vaut pour la **configuration**, pas pour l'UX :
les écrans du Module 3 restent la référence de ce que l'utilisateur lit et fait.
Un état de moins dans le graphe ne veut pas dire un écran de moins.

⚠️ En cas d'autre divergence entre les deux documents sur un point fonctionnel
— libellé d'écran, ordre des champs, contenu d'un formulaire —, le
`Module3_OPEX_Intervenants.md` fait foi : c'est le document UX détaillé. La
`Specification_OPEX_Smart_Missions.md` fait foi sur l'architecture, les états,
le scoring et le modèle de données.

---

## Documents de référence — dossier `docs/`

`ls docs/` avant de coder, et lire ce qui s'y trouve.

| Document | Autorité |
|---|---|
| `Module3_OPEX_Intervenants.md` | **Référence UX du métier** — 48 sections, écrans, règles métier |
| `Specification_OPEX_Smart_Missions.md` | Architecture, scoring, modèle de données cible, MVP |
| `product_backlog.md` | US-09 à US-14 (P1), US-19 et US-20 (P2), US-22 (P3) |
| `portail_digital_vision.pdf` | Domaine 3 — le contexte dans le portail global |
| `instance_smart_crowdfunding.md` | Les capacités du moteur, pour savoir ce qui est déjà disponible |

---

## Ce qui existe déjà et ne doit PAS être réécrit

C'est le point le plus important pour tenir les délais. Trois modules ont été
construits avant celui-ci.

| Besoin | Où c'est déjà fait |
|---|---|
| Moteur de workflow, règles, actions, rôles, audit trail | `opex_workflow` — E1 à E8 |
| Smart Matching Engine (critères pondérés, score, explication) | `opex_workflow` — `opex.matching.criteria` / `.candidate` / `.relation` |
| Profil Expert (compétences, CV, certifications) | `opex_innovation` — `opex.innovation.expert.profile` |
| Cloche de notification portail | `opex_membership` — `_opex_owned_record_ids()` à surcharger |
| Espace staff portail avec file par rôle | `opex_innovation/controllers/staff_portal.py` — le modèle à copier |
| Livrables avec versions et validation | `opex_innovation` — `opex.innovation.deliverable`, lui-même piloté par le moteur |

**Le profil expert n'est pas recréé.** `opex_intervenants` dépend
d'`opex_innovation` et enrichit le profil existant (Extension 3). Un expert du
Module 2 est un intervenant du Module 3 — la spécification l'exige : « Un expert
référencé ne ressaisit pas son profil permanent pour candidater. »

Manifeste : `'depends': ['base', 'mail', 'contacts', 'portal', 'website',
'project', 'sale', 'opex_workflow', 'opex_innovation']`.

⚠️ **Pas `opex_crowdfunding`.** Ce module est isolé par construction (c'est la
moitié texto de l'expérience de comparaison), et rien ne doit le référencer.

---

## Règles transversales — acquises sur les trois modules précédents

Chacune a coûté du temps. Elles s'appliquent ici sans discussion.

### 1. Collisions de nommage

- avec l'API interne d'Odoo : `category_id`, `_register`, `state`, `stage_id`,
  `name_get` sont pris. Une collision est masquée silencieusement et échoue au
  runtime.
- **entre modules** : deux modules qui héritent du même arbre `CustomerPortal` et
  nomment une méthode pareil → Odoo n'en garde qu'une, sans erreur. **Préfixe
  toutes les méthodes de controller** : `portal_intervenants_*`.
- **espace de noms des routes** : préfixe `/my/missions/*` et
  `/staff/missions/*`. Vérifie qu'aucune ne collisionne avec le natif `project`
  ni avec les deux autres modules.

### 2. Un contrôle d'accès = une seule fonction

`res.users._is_missions_staff()`, appelée par les routes **et** par les `t-if`
des tuiles. Les helpers d'appartenance (« cette mission est-elle la mienne ? »)
sont autre chose et peuvent être plusieurs.

### 3. « Présent dans le HTML » ≠ « visible à l'écran »

Un test qui vérifie `'texte' in body` passe alors que rien ne s'affiche. Et sa
réciproque : ne rends **jamais** dans le HTML une donnée réservée à un niveau
d'accès supérieur, même masquée en CSS.

### 4. Sous-types de message

`mail.mt_note` pour tout message interne, `mail.mt_comment` seulement pour ce que
le destinataire doit recevoir par email. Deux effets moins évidents : un
`mt_comment` part aussi aux **followers**, et la cloche portail filtre les notes
via `_get_search_domain_share()`.

### 5. Requêtes ORM dans un gabarit

Un `search()` ou `search_count()` en QWeb s'exécute sous l'identité du visiteur et
**fait tomber la page entière** en `AccessError`. Le contrôle vit dans le
controller. `sudo()` n'est pas la parade, c'est le même défaut en silencieux.

### 6. Contrat de `/my/counters`

Un compteur renvoyé sans nœud DOM correspondant tue tout le JavaScript de
l'accueil, pour tous les utilisateurs. `placeholder_count` dans le gabarit **et**
`if 'x_count' in counters` dans le controller — les deux, ou aucun. Un
`placeholder_count` n'appartient qu'à **une seule** tuile.

### 7. Tests qui passent sans rien prouver

- une assertion négative ne vaut que **précédée d'une assertion positive**
  prouvant que la page a bien été rendue
- `mapped()` sur un Many2one déduplique : un passage répété par une même étape y
  devient invisible
- un test du moteur ne doit jamais supposer qu'il est seul en base : borne les
  `search()` à ta propre définition
- **casse volontairement le code testé une fois** pour vérifier que le test rougit
- **une assertion sur une valeur dynamique ne doit pas contenir d'apostrophe** —
  payé à l'Extension 2. `t-out` échappe : « n'est » devient « n&#39;est » dans
  le HTML rendu, alors que le texte **statique** du gabarit, lui, n'est pas
  réécrit. Une assertion qui l'oublie échoue sur l'échappement et non sur le
  contenu — et, pire, l'inverse : elle peut passer sur un texte statique et
  masquer que la valeur dynamique ne s'affiche pas.
- **`exists()` n'applique aucune `ir.rule`** — payé à l'Extension 1. Il ne fait
  qu'un `SELECT id` : deux tests d'étanchéité écrits
  `assertFalse(record.with_user(autre).exists())` passaient au vert en ne
  prouvant que l'existence de la ligne en base. Une assertion d'étanchéité
  **lit un champ** et attend une `AccessError` :

  ```python
  with self.assertRaises(AccessError):
      record.with_user(autre).un_champ
  ```

  C'est la variante (a) ci-dessus vue de l'autre côté : l'absence n'est une
  preuve que si l'on a vérifié qu'on interrogeait bien la bonne chose.

### 8. Odoo 19

- `res.groups.privilege`, plus de `category_id`
- plus d'`attrs` ni de `states` dans les vues → `invisible="..."` / `readonly="..."`
- `<function>` dans un bloc `noupdate="1"` **ne s'exécute pas** à la mise à jour
- un `Many2many` à la fois **`related`** et `store=True` empêche le registre de
  démarrer, avec un message qui ne nomme pas le champ fautif.
  ⚠ **Précision mesurée à l'Extension 3** : avec **`compute`** au lieu de
  `related`, `store=True` charge sans erreur — le comodèle étant déclaré
  explicitement, Odoo sait nommer la table de liaison. Le crash est propre au
  couple `related` + `store`. Ne pas stocker un Many2many calculé reste
  souvent juste, mais pour une **autre** raison : un calcul qui dépend de la
  date du jour se fige au dernier recalcul
- `portal.portal_searchbar` ne rend `title` que dans sa branche `t-else`
- **une vue `search` refuse `expand` et `string` sur son `<group>`** — payé à
  l'Extension 1. La vue entière devient invalide et **le module ne se charge
  pas** ; le message parle de RelaxNG et ne nomme pas l'attribut fautif.
  Écrire `<group name="group_by">` nu. Corollaire : les `<field>` d'une vue
  `search` se déclarent tous avant les filtres.

### 9. Champs calculés — stockés et non stockés ne se mélangent pas

Payé à l'Extension 1, au tout premier chargement du module.

**Une méthode `compute` ne peut pas produire à la fois des champs stockés et des
champs non stockés.** Le registre refuse de démarrer
(`odoo/orm/registry.py:543`) :

> `inconsistent 'store' for computed fields, accessing X may recompute and
> update Y. Use distinct compute methods for stored and non-stored fields.`

La raison est concrète et vaut d'être retenue : **lire** un compteur
d'affichage déclencherait une **écriture** du compteur stocké, à un moment
quelconque et sous l'identité de n'importe quel lecteur.

Quatre compteurs de candidatures partageaient une méthode ; le stocké —
`selected_application_count`, le garde-fou de la règle 4 — a désormais la
sienne. Les deux méthodes partagent un helper qui lit la donnée une fois.

⚠ L'erreur remonte sous forme de `warnings.warn` escaladé, et la trace pointe
vers le module **`account`** en cours de chargement, pas vers le vôtre. On la
reconnaît au dernier cadre : `registry.py`, `field_computed`.

### 10. Une contrainte SQL empoisonne la transaction

Payé à l'Extension 3, sur le dépôt d'une compétence en double depuis le portail.

Une contrainte SQL (`models.Constraint`) ne se déclenche **pas** à `create()`
mais au `flush`. Quand elle saute, PostgreSQL passe la transaction entière en
état abandonné : tout ce qui suit reçoit *« current transaction is aborted »* —
**y compris le rendu de la page d'erreur**. Le client reçoit un 500 là où le
controller croyait afficher un message. Un `try/except` seul n'y change rien :
l'exception est bien attrapée, la transaction reste morte.

```python
try:
    with request.env.cr.savepoint():
        model.create(values).flush_recordset()   # ⚠ le flush DANS le savepoint
except (UserError, ValidationError) as refus:
    request.env.invalidate_all()                 # ⚠ le rollback ne vide pas le cache
    return str(refus)
```

`flush_recordset()` force l'INSERT à l'intérieur du savepoint, sans quoi
l'erreur surviendrait plus tard, hors de sa portée. `invalidate_all()` après le
rollback : celui-ci défait les écritures en base mais **pas** le cache de l'ORM,
qui contiendrait alors des valeurs jamais écrites.

C'est exactement le motif du moteur dans `_execute_actions()`
(`workflow_instance.py:805`).

### 11. `editable` est un nom réservé du rendu website

Payé à l'Extension 5, sur le formulaire de candidature.

`website/models/ir_http.py:399` pose dans le contexte de rendu :

```python
values['editable'] = request.env.uid and \
    request.env.user.has_group('website.group_website_designer')
```

C'est l'indicateur « l'éditeur de site est actif ». Il vaut donc **False pour
tout compte portail**, et il **écrase** une variable du même nom passée par un
controller — sans erreur, sans avertissement.

Symptôme observé : le formulaire ne s'affichait jamais, la page rendait
« votre candidature est déposée » alors que l'étape était bien celle où le
candidat doit écrire. Le libellé d'étape, lui, s'affichait correctement — ce
qui écartait toutes les pistes du côté du modèle.

Règle : **une variable de gabarit qui décide d'un affichage porte un nom
métier**, jamais un nom générique du framework. Ici `modifiable`. En cas de
doute sur un nom, `grep -rn "values\['<nom>'\]" addons/website/ addons/portal/`.

### 12. Une donnée réservée se filtre au modèle, pas au gabarit

Corollaire de la règle 3, mesuré à l'Extension 5 par régression volontaire.

En retirant le filtre de confidentialité du **dictionnaire** de la vue
publique, un seul test a rougi : celui qui inspecte le dictionnaire. Le
gabarit, lui, continuait de masquer client et budget par son propre `t-if`, et
la page rendue restait propre.

Autrement dit : **un test qui ne vérifie que le HTML ne garde pas la
confidentialité.** Il constate qu'aujourd'hui rien ne fuit ; il n'empêche pas
qu'un `t-out` ajouté un mardi publie ce que le modèle a déjà laissé sortir.

Les deux niveaux sont nécessaires et ne se remplacent pas :

- **au modèle** — la donnée réservée n'entre pas dans le dictionnaire. C'est la
  garde, et c'est elle qu'il faut tester en premier ;
- **au gabarit** — elle n'atteint pas la page. C'est la seconde barrière.

Et la clé masquée est **absente** du dictionnaire, pas mise à `False` : un
gabarit qui l'afficherait lèverait au premier rendu. Une erreur bruyante vaut
mieux qu'une fuite silencieuse.

### 14. Un sous-workflow est « terminé » dès la PREMIÈRE étape finale atteinte

Payé à l'Extension 7, sur la règle 5 du §39.

`do_transition()` pose `state = 'done'` en atteignant **n'importe quelle**
étape `is_end` (`workflow_instance.py:769`), et `_subworkflow_done()` teste
exactement `state = 'done'` (`workflow_instance.py:305`).

Conséquence, contre-intuitive et grave : marquer l'étape de **refus** d'un
sous-processus comme finale fait que `subworkflow_done('x')` devient vrai
**quand le sous-processus a échoué**. Une condition écrite pour exiger un
contrat validé laisserait alors démarrer une mission dont le contrat vient
d'être rejeté.

Règle : **un sous-workflow attendu par une condition n'a qu'une seule étape
`is_end`, celle du succès.** Les issues de refus bouclent vers l'amont.

⚠ **`_check_graph()` ne dit rien.** Deux étapes finales sont un graphe
parfaitement valide ; le validateur exige au moins une `is_end` et aucun
cul-de-sac (`workflow_definition.py:268-280`), pas l'unicité. Mesuré par
régression volontaire : la définition s'est publiée sans un mot, et seuls les
deux tests dédiés ont signalé le défaut. Rien, dans le configurateur, ne
préviendra celui qui coche la case.

Le corollaire vaut pour la surveillance : la configuration semée **réaffirme**
`is_end` à chaque mise à jour, par deux `<function name="write">` hors bloc
`noupdate`. La donnée du fichier est la référence, l'écran n'en est que la vue.

### 15. Un test qui interdit un mot interdit aussi qu'on en parle

Payé à l'Extension 7, dans la foulée de la précédente.

Un test de garde lisait le source d'un module entier et échouait s'il y
trouvait `do_transition` — l'idée étant qu'aucun déclencheur métier ne fasse
avancer un workflow. Il a rougi immédiatement, **sur sa propre documentation** :
le fichier explique en toutes lettres qu'il n'appelle pas `do_transition()`.

Le défaut n'est pas le faux positif, c'est ce qu'il pousse à faire. La
correction de moindre effort est de **supprimer l'explication** — donc de
perdre exactement ce qui rendait le module compréhensible, pour satisfaire un
test qui prétend le protéger.

Règle : **un test qui inspecte du source examine du code, pas de la prose.**
Retirer les docstrings et les commentaires avant l'examen
(`re.sub(r'("""|\'\'\')(?:.|\n)*?\1', '', source)` puis `#[^\n]*`), et itérer
sur les fonctions des classes du module plutôt que sur le fichier — c'est
d'ailleurs plus précis, et c'est ce que le test prétendait faire.

⚠ Et poser l'assertion positive qui va avec : `assertGreaterEqual(examined, N)`.
Une boucle de vérification qui ne trouve plus rien à vérifier passe au vert.

### 16. Un champ calculé non stocké n'est pas cherchable — et le module ne charge plus

Payé à l'Extension 8, sur le filtre « En retard » d'une vue `search`.

```
Unsearchable field "en_retard" in path "en_retard" in domain of
<filter name="en_retard"> ([('en_retard', '=', True)])
```

Ce n'est pas un avertissement : la vue devient invalide et **le module ne se
charge pas**. Le message, lui, est excellent — il nomme le champ et le filtre.

Deux issues, une seule bonne :

- **recopier la logique dans le domaine du filtre** — deux définitions du même
  concept, qui divergeront au premier ajustement, et sans que rien ne le
  signale ;
- **donner sa méthode de recherche au champ** (`search='_search_en_retard'`),
  qui traduit le calcul en domaine sur des colonnes réelles.

Le stockage n'est pas une option quand le calcul dépend de la date du jour : il
figerait la valeur au dernier recalcul, et un livrable deviendrait « en
retard » le jour où quelqu'un ouvre sa fiche.

⚠ Le corollaire : **un test doit comparer les deux**. `_compute` et `_search`
sont deux implémentations du même prédicat, et rien dans Odoo ne garantit
qu'elles répondent la même chose.

### 17. Un test de nommage doit porter sur le TYPE, pas seulement sur le nom

Payé à l'Extension 8, et c'est le bon genre de rouge.

`test_no_selection_field_describes_progress` refusait tout champ de
`opex.mission.request` nommé `state`, `etat`, `statut` ou **`avancement`**. Il
a rougi sur un `Integer` en pourcentage — l'avancement que l'intervenant
**déclare** dans son point du §21. Ce n'est pas un état : c'est une donnée que
quelqu'un a tapée, pas une position que le système dérive.

Deux corrections, parce qu'aucune ne suffisait :

- le champ s'appelle `avancement_declare`, ce qui dit ce qu'il est sans qu'on
  ait à le demander ;
- le critère du test est devenu **plus large**, pas plus permissif : un
  `Selection` portant l'un de ces noms est toujours refusé — `etape` et `phase`
  y ont été ajoutés, que l'ancienne liste laissait passer — et `state`, `etat`,
  `statut`, `status`, `stage_id` restent interdits **quel que soit le type**,
  parce que ces cinq-là ne désignent jamais autre chose.

La leçon générale : quand un test de garde rougit sur du code légitime, la
correction n'est pas de retirer le mot de la liste. C'est de se demander ce que
le test voulait vraiment interdire, et de l'écrire.

### 18. Renommer un champ cité par une vue héritée casse le rechargement

Payé à l'Extension 8, dans la foulée de la règle 17.

Renommer `avancement` en `avancement_declare` a fait échouer le `-u` suivant
sur la vue **mère**, pas sur la vue héritée :

```
Error while validating view near: … view_mission_request_form
Field "avancement" does not exist in model "opex.mission.request"
```

La cause : les fichiers de vues se chargent dans l'ordre du manifeste. Quand la
vue mère est réécrite, Odoo revalide son arbre complet — **avec les vues
héritées telles qu'elles sont encore en base**, c'est-à-dire l'ancienne
version, qui cite le champ disparu. L'enfant ne sera mis à jour que plus tard,
et ce plus tard n'arrive jamais.

La trace ne nomme ni la vue héritée fautive ni le module. On la reconnaît à ceci
que le champ cité n'existe **nulle part** dans le fichier incriminé.

Parade en développement : supprimer l'`ir.ui.view` périmée et son
`ir.model.data`, puis relancer le `-u`. En production, un renommage de champ
cité par une vue demande un script de migration — c'est la même cause.

### 19. Environnement

- **serveur fantôme sur le port 8069** : `SO_REUSEADDR` fait qu'une seconde
  instance se lie sans erreur et intercepte les requêtes. Lance les tests avec
  `--http-port=8072`. Symptôme : des échecs HTTP massifs et inexplicables, ou des
  routes neuves en 404.
- `--limit-time-real=0` pour les démonstrations, sinon le serveur meurt au bout
  de deux minutes quand un onglet reste ouvert
- **le SMTP n'est pas configuré** : aucun email ne part. Les notifications se
  vérifient dans la cloche et dans `mail.message`, pas dans une boîte de
  réception.
- ⚠ **`--test-tags` ne se lance pas depuis Git Bash.** MSYS convertit tout
  argument commençant par `/` en chemin Windows : `--test-tags "/opex_membership"`
  arrive en `C:/Program Files/Git/opex_membership`, Odoo journalise
  `Invalid tag …` en `ERROR`, **exécute zéro test** — et conclut par
  `0 failed, 0 error(s) of 0 tests`. La ligne finale ressemble à un succès.

  Un tag qui contient un `:` (`"/opex_membership:TestX"`) échappe à la
  conversion et fonctionne, ce qui rend le piège intermittent : la forme
  précise passe, la forme large ment. **Lancer les tests depuis PowerShell.**

### 20. Un test d'idempotence doit repasser par le chemin qu'il prétend rejouer

Payé à l'Extension 10, et c'est le bon genre de rouge — celui qui reste vert.

`test_an_evaluation_returned_then_validated_counts_once` affirmait vérifier
qu'une note n'est portée qu'une fois au profil. Régression volontaire : la
garde `if self.rating_id: return` retirée du déclencheur, le test **est resté
vert**.

La raison est dans le graphe, pas dans le test : l'étape de validation est
`is_end`, l'instance se clôt en l'atteignant, et le moteur n'y ramènera jamais
l'enregistrement. Le parcours que le test déroulait — soumettre, renvoyer,
reprendre, resoumettre, valider — ne franchit la transition de validation
**qu'une seule fois**. Il ne pouvait rien mesurer.

Deux corrections, parce qu'aucune ne suffisait :

- le test d'origine a été renommé pour ce qu'il prouve réellement — le renvoi
  ne porte aucune note, et la validation qui suit n'en porte qu'une ;
- un second test appelle le déclencheur **directement**, deux fois, parce que
  c'est le seul chemin par lequel un rejeu peut arriver.

La leçon générale : **avant d'écrire un test d'idempotence, se demander par
quel chemin le second passage arriverait.** S'il n'en existe aucun dans le
graphe, la garde protège autre chose — un script de reprise, une action
rejouée à la main, une transition ajoutée plus tard — et c'est cela qu'il faut
appeler. Un test qui ne peut pas échouer est plus dangereux qu'un test absent :
il occupe la place.

### 21. Un pictogramme ne porte jamais une décision

Payé à l'Extension 10, pendant le nettoyage typographique de tous les modules.

`_matching_check_eliminatoires()` distinguait deux sortes de motifs — ceux qui
écartent un candidat et ceux qui ne font qu'avertir — par un `⚠` en tête de
chaîne, testé au `startswith()`. Un balayage a retiré le caractère **des deux
côtés** : la comparaison est devenue `startswith("")`, vraie pour tout le
monde, et plus aucun candidat n'était écarté du vivier.

Le défaut ne ressemblait pas à une panne. La liste des propositions restait
pleine — plus pleine, même. Seuls trois tests dédiés l'ont signalé, et sur le
critère **éliminatoire** de certification, c'est-à-dire là où une erreur fait
entrer quelqu'un qui n'aurait pas dû.

Règle : **un caractère décoratif n'entre pas dans une condition.** Deux listes
distinctes, ou un booléen, ou un type — jamais un préfixe de chaîne. Le
corollaire vaut pour tout nettoyage de masse : ce qui se relit comme de la
présentation peut être de la logique, et seul un `-u` suivi de la suite
complète le dit.

### 22. Une URL de notification se résout pour le LECTEUR, pas pour l'objet

Payé à l'Extension 11, et trouvé **au navigateur** — aucun test ne l'a vu.

`_opex_notification_url()` déduisait le lien du seul modèle du message :
un message sur une candidature menait à `/my/candidatures/<id>`. C'était juste
tant qu'un message ne parvenait qu'au **propriétaire** de l'enregistrement.

La cloche du Module 1 a une seconde source — les messages **adressés
nommément**, y compris sur le dossier d'un autre. C'est ce qui la rend utile,
et c'est ce qui casse la déduction : le client prévenu qu'une candidature a été
déposée sur son appel cliquait, et tombait sur un **404**, l'`ir.rule`
réservant cet écran au candidat.

Le test qui existait vérifiait que l'URL commence par `/my/` — toujours vrai.
Les tests HTTP ne cliquent pas sur les liens de la cloche. Il a fallu ouvrir la
page.

Règle : **dès qu'un message peut atteindre quelqu'un d'autre que le
propriétaire du dossier, l'URL est fonction du couple (message, lecteur).**
Et le test qui la garde doit vérifier que le lecteur **peut y aller**, pas que
la chaîne ressemble à une URL de portail.

### 23. Un écran de configuration peut mentir — `website` surcharge le signup

Payé sur le parcours d'adhésion du Module 1, et c'est le pire cas de la
règle 3 : là où « présent dans le HTML ≠ visible à l'écran », ici **la valeur
affichée n'est pas la valeur appliquée**.

`website/models/res_users.py:66` surcharge `_get_signup_invitation_scope()` :

```python
def _get_signup_invitation_scope(self):
    current_website = self.env['website'].get_current_website()
    return current_website.auth_signup_uninvited or super()._…()
```

Le champ `auth_signup_uninvited` du **site web** prime donc sur le paramètre
système `auth_signup.invitation_scope`. Mesuré :

```
ir.config_parameter  auth_signup.invitation_scope = 'b2c'
website(1).auth_signup_uninvited             = 'b2b'
_get_signup_invitation_scope() == 'b2c'      →  False
```

Conséquence : `/web/signup` rendait un **404** pour tout le monde — connecté
ou non —, `auth_signup/controllers/main.py:43` refusant la route quand le
signup n'est pas ouvert. Trois entrées « Devenir membre » pointaient dessus.

⚠ Le symptôme ne ressemble pas à une erreur de configuration : l'écran
Paramètres affiche `b2c` et paraît confirmer que tout va bien. On cherche
alors du côté du code, des droits, de la session — partout sauf là.

Règle : **avant de croire un écran de configuration, lire la valeur par la
méthode qui la consomme**, pas par le paramètre qu'on croit être la source.
Au shell :

```python
env['res.users']._get_signup_invitation_scope()   # la vérité
env['ir.config_parameter'].get_param('auth_signup.invitation_scope')  # l'affichage
```

Corollaire retenu pour ce projet : **ne pas faire dépendre un parcours métier
d'un réglage que l'écran affiche faussement.** « Devenir membre » pointe
désormais sur `/my/membership/new`, route `auth='user'` — Odoo renvoie
l'anonyme au login avec son `redirect`, et aucun réglage de sécurité n'entre
dans l'équation.

### 24. Deux chemins sous un même libellé produisent un « parfois »

Payé sur le même parcours, et c'est ce qui a coûté le plus de temps au
diagnostic.

« Devenir membre » existait à **quatre** endroits — menu, accueil, annuaire,
portail — et portait **deux** URL différentes. Selon l'écran d'où l'on
cliquait, on obtenait un 404 ou un rebond silencieux. Le même geste, deux
symptômes : de quoi croire à un défaut intermittent, et chercher une cause
qui n'existe pas.

Règle : **un libellé, une URL.** Un test lit les gabarits et refuse qu'une
seconde apparaisse.

⚠ Le corollaire, qui a rougi au premier essai : quand la visibilité d'une
entrée de menu est portée par un greffon qui **filtre sur l'URL**
(`submenu.url == '…'`), changer l'URL sans changer le greffon fait cesser le
masquage — **en silence**. Le lien réapparaît alors pour ceux à qui il était
caché.

### 25. Un refus d'accès affiche son motif sur une page rendue

Payé sur le parcours d'adhésion, deux fois dans le même diagnostic.

**Un `redirect()` après un contrôle d'accès est indistinguable d'une panne.**
L'utilisateur clique, revient sur son profil, et rien ne lui dit pourquoi. Il
recommence, croit à un bug, et le signale comme tel — ce qui est exactement ce
qui s'est produit.

Règle : **tout refus d'accès rend une page qui porte son motif.** Pas de
`redirect('/my')` nu, pas de bannière posée sur une page que le refusé ne peut
pas lire.

⚠ Ce second point n'est pas théorique, il a été mesuré. La première correction
redirigeait vers `/my/membership?error=…` — la page des dossiers, qui affiche
déjà une bannière. Or **cette page porte le même garde-fou** : elle rebondit
vers `/my` pour qui n'a pas le droit de *lire* les dossiers, c'est-à-dire
précisément le compte qu'on vient de refuser. Le message se perdait en route,
et le rebond muet revenait par un autre chemin.

**Une page rendue ne peut pas se perdre.** C'est la seule forme qui tient.

Le motif doit **orienter**, pas seulement constater :

> Le dépôt d'un dossier d'adhésion se fait depuis un compte portail. Votre
> compte est un compte interne du cluster : il lit les dossiers, il n'en
> dépose pas. Demandez au Secrétariat d'ouvrir le dossier, ou connectez-vous
> avec le compte portail de votre organisation.

Et il ne doit rien divulguer : sur un enregistrement introuvable, un seul
message neutre — « ce dossier n'existe pas ou ne vous est pas accessible ».
Distinguer les deux cas dirait à un visiteur que l'objet existe (règle 3).

⚠ Le refus reste **une seule fonction**, appelée par la route et par le `t-if`
du bouton (règle 2). C'est en la dédoublant que le défaut est né : le bouton
testait une question, la route en testait deux.

### 26. Une collision de noms sur `CustomerPortal` casse aussi le voisin

Payé deux fois sur le parcours d'adhésion, et les deux symptômes ne se
ressemblaient pas. C'est la règle 1 mesurée, avec ce qu'elle ne disait pas.

**Entre nos modules.** `opex_innovation` dépend d'`opex_membership`, donc il
charge après, donc il gagne. Trois attributs y étaient homonymes :

| Nom | Ce qu'il faisait chez nous | Ce qu'il faisait une fois écrasé |
|---|---|---|
| `_current_draft` | cherchait un dossier d'adhésion | cherchait un projet d'innovation |
| `_STEP_FIELDS` | les champs des 7 écrans | ceux de l'innovation — **rien n'était enregistré** |
| `_save_step` | l'écriture du dossier | celle du projet |

Symptôme : `/my/membership/new` **bouclait sur son premier écran**, et chaque
tentative créait un dossier de plus. Rien, dans ce que voyait l'utilisateur, ne
désignait une collision de noms — c'est ce qui a rendu le diagnostic long.

⚠ Ce qui l'a tranché : une trace posée **dans** notre méthode ne s'est jamais
imprimée, alors que celle de son appelant s'imprimait. Une méthode qu'on
appelle et qui ne s'exécute pas est la signature de la fusion.

**Avec Odoo lui-même**, et celui-là est pire : le dégât est chez le voisin.
`opex_innovation.portal_my_projects` portait `/my/innovation` sous le nom
qu'emploie `project/ProjectCustomerPortal` pour `/my/projects`. La route native
**sortait du routing map** — 404 mesuré sur `/my/projects`, 200 sur
`/my/innovation`. Nous ne pouvions pas le voir : la route perdue n'est pas la
nôtre, aucun de nos tests ne la visite, et son module ne sait pas que nous
existons.

Règle : **préfixe par ton domaine tout attribut posé sur l'arbre
`CustomerPortal`** — pas seulement les routes, les helpers et les constantes de
classe aussi. `portal_innovation_my_projects`, `_membership_current_draft`.

La seule exception est le **point d'extension coopératif** — un nom que l'on
reprend **pour** relayer `super()`. `_prepare_home_portal_values` est défini par
sept de nos classes et sept classes natives ; chacune appelle la suivante, et
c'est le mécanisme d'extension d'Odoo.

⚠ **Une chaîne `super()` bien formée ne prouve rien sur ce qui la précède.**
`portal_my_projects` avait d'abord été classé « coopératif » parce que nos deux
classes se l'appelaient proprement — ce qui était vrai, et hors sujet : la
chaîne était interne à `opex_innovation`, et son **premier maillon** n'appelait
rien. C'est-à-dire écrasait le natif.

`opex_membership/tests/test_portal_collisions.py` tient les quatre faces, par
lecture **statique** du source — à l'exécution la classe est déjà fusionnée et
les noms écrasés ont disparu, donc il faut regarder avant :

1. aucun nom partagé entre nos quatre modules ;
2. aucun nom d'Odoo repris **sans** relayer `super()` ;
3. les trois noms du parcours d'adhésion sont préfixés, nommément ;
4. toute surcharge coopérative relaie bien `super()`.

⚠ Le relevé doit suivre l'héritage **indirect** : `InnovationHolderDashboard`
hérite d'`InnovationProjectPortal`, pas de `CustomerPortal`. Un walker qui ne
lit que les bases directes rate le second maillon d'une chaîne — donc
précisément celui qui donne l'illusion que tout va bien.

### 27. Une assertion d'URL compare une chaîne à la carte des routes

Payé sur `/my/intervenant`, et c'est la règle 22 poussée d'un cran.

Trois liens du Module 3 pointaient sous `/my/*` alors que l'espace de noms du
module est `/my/missions/*` (règle 1). Aucune de ces URL n'a jamais été
déclarée par un `@http.route` : elles rendaient un **404**.

Le pire des trois était **la branche candidat** de
`_application_notification_url()`. L'Extension 11 avait corrigé la branche
client — le défaut trouvé au navigateur — sans que celle du candidat soit mise
en cause : tout intervenant qui cliquait sur sa propre notification de cloche
tombait sur une page introuvable, depuis l'origine.

**Ce qui l'a laissé passer est le point de la règle.** Deux tests assertaient
l'URL, tous les deux ainsi :

```python
self.assertEqual(rendu, '/my/candidatures/%s' % application.id)
```

Les deux côtés de l'égalité sont construits par le même `%`. Ils sont donc faux
de la même façon, et l'égalité tient. Le test écrit **pour** garder cette
méthode a figé l'URL fautive au lieu de la signaler — corriger le code sans le
corriger l'aurait fait rougir.

Règle : **une assertion sur une URL la résout contre le routing map**, jamais
contre une chaîne que le test compose lui-même. La carte est construite par les
`@http.route` ; c'est la seule référence qui ne peut pas être fausse du même
côté que le code testé.

```python
adaptateur = self.env['ir.http'].routing_map().bind('localhost')
trouve, valeurs = adaptateur.match(url, method='GET')   # NotFound = 404
```

Et vérifier **quel** endpoint sert l'URL, pas seulement qu'il en existe un :
une URL qui résout vers un autre écran est un défaut différent et tout aussi
silencieux.

`opex_membership/tests/test_portal_links.py` généralise : toute URL `/my/*` ou
`/staff/*` écrite dans un gabarit, un modèle ou un `redirect()` doit
correspondre à une règle. 82 URL relevées sur les quatre modules.

⚠ Trois précautions, les trois payées en l'écrivant :

- **les chaînes d'un `@http.route` sont exclues du relevé** — elles *définissent*
  l'espace de noms, les confronter à lui-même ne prouve rien ;
- **l'interpolation QWeb se réduit avant l'ancre.** Couper à `#` d'abord
  transforme `t-attf-href="/my/…/candidature/#{a.id}"` en `/my/…/candidature`,
  une URL que personne n'a écrite : le test signalait cinq liens morts
  imaginaires ;
- **le relevé se borne aux modules installés dans cette base.**
  `opex_crowdfunding` vit sur la sienne ; ses routes ne sont pas dans ce
  routing map, et tous ses liens y paraissaient morts.

⚠ Ce que ce test **ne** dit pas : qu'une route existe ne veut pas dire que ce
lecteur-là y a droit. C'est la règle 22, et elle reste gardée séparément.

### 28. Une correction appliquée au xmlid n'atteint pas les copies par site

Payé sur « Devenir membre », **après** que la règle 24 eut été écrite et le
défaut réputé corrigé.

`website.menu` porte **deux** enregistrements par entrée : le modèle par défaut
(`website_id = False`, celui qui porte notre xmlid) et **une copie par site**,
sans xmlid, instanciée à la création du site. C'est la copie qui est servie au
visiteur.

L'URL avait été corrigée dans le fichier de données, et le `<function>` hors
bloc `noupdate` avait bien réaligné l'enregistrement nommé. Mesuré ensuite :

```
id=10   /my/membership/new                        <- le modèle, corrigé
id=9    /web/signup?redirect=/my/membership/new   <- le site 1, oublié
```

**La page publique affichait donc encore le lien mort**, pendant que le source,
le xmlid et le test qui les lit disaient tous que c'était réglé.

C'est le `noupdate` d'un cran plus loin : le drapeau protège l'enregistrement
porteur du xmlid, et **personne ne protège ses copies**. Un `<function>` qui ne
cite qu'un `ref()` ne suffit pas pour ce modèle.

Parade : `_opex_realign_website_copies()`, appelée par `<function>` hors bloc
`noupdate`. Elle part des entrées **déclarées** et réaligne celles qui portent
le même libellé sans xmlid — jamais d'une seconde liste d'URL écrite dans le
code, qui divergerait de la première.

⚠ Le corollaire de méthode, et c'est le plus important : **un test qui ne lit
que le source ne peut pas voir ce genre de défaut.** Celui qui gardait la
règle 24 lisait les fichiers XML et l'entrée porteuse du xmlid — les deux
étaient justes. Il a fallu interroger `website.menu` **en base** pour le
trouver.

Et quand un test lit la base, il se borne : les menus du site sont éditables
par l'utilisateur, et un test qui rougirait sur une entrée que quelqu'un a
créée pour ses besoins finit désactivé. Le relevé ne porte que sur les
**libellés que nos modules déclarent**.

### 29. Le critère d'exemption d'une chaîne coopérative est « qui dépend de lui »

Payé en écrivant `test_model_overrides.py`, et c'est la règle 20 sous un
quatrième jour.

Le test exige que toute surcharge d'une méthode partagée relaie son parent. Il
faut donc exempter le module qui **définit** le protocole — lui n'a personne à
relayer. Premier critère écrit : « ce module ne dépend d'aucun autre porteur ».

Régression volontaire : le relais défensif d'`opex_crowdfunding` coupé. **Le
test est resté vert.** Crowdfunding ne déclare aucun de nos modules à son
manifeste, il était donc classé racine — alors qu'il est une **feuille**. Rien
ne garantit son ordre de chargement face à `opex_membership`, et un maillon
muet y effacerait la cloche du Module 1. C'est exactement pourquoi il écrit
`getattr(super(), 'x', None)`.

Le bon critère est l'inverse : **un module n'est exempté que si un autre
porteur dépend de lui**, directement ou transitivement. `opex_membership` est
en amont d'`opex_innovation` et d'`opex_intervenants`, donc il est la racine.
Tous les autres relaient, y compris ceux qui ne dépendent de personne.

Corrigé, le test rougit sur la casse et nomme le module fautif.

⚠ Les **trois** formes de relais doivent être reconnues, sans quoi le test
signale du code correct — et un test bruyant finit désactivé :

| Forme | Quand |
|---|---|
| `super().x(...)` | l'ordinaire |
| `getattr(super(), 'x', None)` | parent **optionnel** — le module doit rester installable seul |
| aucune | le **définisseur**, et lui seul |

---

# Le modèle de données

Repris de la §15 de la spécification Smart Missions, adapté aux conventions du
projet.

## Objet central

### `opex.mission.request` — l'appel à mission

```python
_inherit = ['mail.thread', 'mail.activity.mixin', 'opex.workflow.mixin']
```

**Aucun champ `state`.**

| Bloc | Champs |
|---|---|
| Général (§4) | `name` (référence MIS-2026-001, séquence), `title`, `mission_type`, `client_id` (Many2one res.partner), `description`, `objectifs`, `resultats_attendus` |
| Opérationnel | `skill_ids`, `domaine_id`, `niveau_experience`, `localisation`, `mode_intervention` (présentiel / distanciel / hybride) |
| Temporel | `date_debut_souhaitee`, `date_fin_souhaitee`, `duree_estimee`, `date_limite_candidature` |
| Financier | `budget_estimatif` (Monetary), `type_remuneration`, `conditions_financieres` |
| Sourcing (§8) | `sourcing_mode` (matching / portail / hybride) |
| Confidentialité (§14) | `is_published`, `public_fields_only`, `nda_required` |
| Documents | `document_ids` — cahier des charges, techniques, complémentaires |

### `opex.mission.application` — la candidature

```python
_inherit = ['mail.thread', 'opex.workflow.mixin']
```

**Aucun champ `state`.** Sa propre définition de workflow.

`mission_id`, `partner_id`, `expert_profile_id`, `source` (matching / portail /
invitation / manuel), `motivation`, `methodologie`, `disponibilite`,
`delai_propose`, `tarif_propose`, `score` (Float), `score_detail` (Text),
`document_ids`.

⚠️ **Règle 3 du §39** : un intervenant ne peut pas déposer deux candidatures sur
le même appel. Contrainte SQL `unique(mission_id, partner_id)`, pas seulement un
contrôle applicatif.

## Les autres modèles

| Modèle | Rôle |
|---|---|
| `opex.mission.skill.requirement` | compétence + niveau requis + éliminatoire ou pondéré |
| `opex.mission.criteria` | critères de sélection, pondération configurable par type de mission |
| `opex.mission.deliverable` | livrables attendus, jalons, critères d'acceptation |
| `opex.mission.assignment` | affectation de l'intervenant retenu |
| `opex.mission.contract` | contrat, NDA, ordre de mission |
| `opex.service.acceptance` | service fait |
| `opex.expert.evaluation` | évaluation finale, alimente la réputation |

Et sur le profil expert existant (Extension 3) : `skill_ids`, `experience_ids`,
`certification_ids`, `availability_ids`, `rating_ids`.

⚠️ `opex.expert.skill` est la **ligne de qualification** du profil
(`expert_profile_id` + `competence_id` + `niveau` + `annees`), posée sur le
référentiel commun `opex.innovation.competence`. Ce n'est pas un référentiel de
compétences — voir la note de l'Extension 1.

---

# Les extensions

## Extension 1 — Socle : l'appel à mission et ses deux workflows ✅ FAITE

> **Livrée le 30/08/2026** — 78 tests, 0 échec. Voir « État d'avancement » plus
> bas pour ce qui a été décidé en route, et
> `opex_intervenants/docs/protocole_test_extension1.md` pour le déroulé manuel.
>
> ⚠ Trois points de la liste ci-dessous ont été **tranchés dans l'autre sens**
> pendant la réalisation, et ce sont ces arbitrages-là qui font foi :
> `initiator_role_id` reste **vide** (voir la note du point correspondant),
> il n'y a **pas** de référentiel de compétences neuf, et il y a **deux**
> groupes et non cinq.

**Objectif** : poser le modèle central et **les deux définitions de workflow**.
Rien d'autre.

- `opex.mission.request` avec les champs des quatre blocs du §4, héritant du
  mixin, **sans champ `state`**
- `opex.mission.application` idem, avec sa contrainte d'unicité
- référentiels : `opex.mission.type` (avec `multi_intervenants`, l'exception de
  la règle 4) et `opex.mission.domain` — semés en data, jamais codés en dur dans
  un `Selection` figé

  ⚠️ **Pas de référentiel de compétences neuf.** `skill_ids` pointe vers
  `opex.innovation.competence`, déjà là. Le moteur de matching compare une
  valeur du dossier à un **champ de `res.partner`**
  (`_score_candidate`, `workflow_instance.py:1077`), et
  `res.partner.expert_competence_ids` — `related` de
  `expert_profile_id.competence_ids` — pointe déjà sur ce référentiel. Avec un
  second référentiel, les deux ensembles ne se croiseraient que par coïncidence
  de libellé (`_as_set()` compare des chaînes normalisées) et divergeraient au
  premier renommage : le critère « Compétences 30 % » deviendrait faux **sans
  que rien ne le signale**.

  Corollaire : `opex.expert.skill` de l'Extension 3 n'est **pas** ce
  référentiel. C'est une **ligne de qualification** — `expert_profile_id`,
  `competence_id`, `niveau`, `annees` — posée sur le référentiel commun. Le nom
  désignait deux choses différentes dans les deux extensions ; il n'en désigne
  plus qu'une.
- séquence de référence `MIS-%(year)s-%%(###)s`
- **2 groupes** via `res.groups.privilege` : `group_mission_manager` et
  `group_mission_committee`. Le Secrétariat **réutilise**
  `opex_membership.group_secretariat` — c'est le même secrétariat, il instruit
  déjà les adhésions et les projets, et `opex_workflow.role_secretariat` y est
  rattaché par `opex_innovation`. Le client et l'intervenant n'ont **pas** de
  groupe : ce sont des comptes portail, leurs rôles s'attribuent dossier par
  dossier par une ligne `instance.actor`
- **les deux définitions en data XML** : `mission_request` et
  `mission_application`, avec leurs étapes, transitions, rôles et `user_label`
- ⚠️ **`initiator_role_id` laissé VIDE sur les deux définitions.** L'acteur est
  posé explicitement dans `create()`, depuis `client_id` / `partner_id`.

  L'instruction inverse qui figurait ici était fausse.
  `_grant_initiator_role()` donne le rôle à **`instance.initiator_id`,
  c'est-à-dire à l'utilisateur qui exécute le `create()`** — le moteur le
  documente lui-même comme une limite (`workflow_definition.py:89-97`). Or sur
  le canal matching c'est le **responsable** qui crée la candidature pour le
  compte de l'expert : il recevrait le rôle `intervenant` en accès **`full`**
  sur cette candidature. Même défaut sur la mission quand le secrétariat ouvre
  un appel pour un client (§9).

  `opex_innovation` a tranché pareil : `project_workflow.xml` ne renseigne pas
  `initiator_role_id`, et `InnovationProject.create()` pose l'acteur depuis
  `partner_id` (`innovation_project.py:259-268`). Seuls les workflows de demande
  de profil le renseignent, parce que là le déposant *est* toujours le sujet.
- vues back-office : liste, formulaire avec statusbar, recherche
- `tests/test_mission_request.py` versionné

⚠️ Vérifie qu'un dossier peut être déroulé **de bout en bout à la main dans le
back-office**, sur les deux workflows, avant de passer à la suite. Si le graphe
est faux, tout le reste s'écroule dessus.

---

## Extension 2 — La demande client ✅ FAITE

> **Livrée le 30/08/2026** — 103 tests au total, 0 échec. Protocole manuel :
> `opex_intervenants/docs/protocole_test_extension2.md`.
>
> Huit routes `/my/missions/*`, cinq écrans, un récapitulatif de soumission.
> Deux régressions volontaires ont été jouées : renommer une méthode en
> `portal_missions` **fait disparaître `/my/innovation/missions`** du routing
> map (deux tests rouges), et retirer la garde `in counters` fait renvoyer une
> clé non demandée (un test rouge).
>
> Le motif de retour au client et l'historique sont lus dans le journal du
> moteur, **sans champ recopié** : `complement_reason()` et
> `history_entries()`. Un champ serait écrasé au second retour.

**§6 et §7 du Module 3.**

Cinq écrans courts, jamais un formulaire monolithique : informations générales →
profil recherché → organisation → budget → documents.

- routes `/my/missions/new` et ses étapes, brouillon auto-sauvegardé
- tableau de bord client (§6) : mes demandes, appels en cours, missions en cours,
  missions terminées
- `create()` surchargé forçant `client_id = env.user.partner_id.id`
- **la demande n'est pas publiée automatiquement** (§8) : elle passe par une
  qualification du cluster

## Extension 3 — Le profil expert enrichi ✅ FAITE

> **Livrée le 30/08/2026** — 134 tests au total, 0 échec. Protocole manuel :
> `opex_intervenants/docs/protocole_test_extension3.md`.
>
> Les cinq modèles se rattachent à `opex.innovation.expert.profile`, **étendu
> par `_inherit`**. Aucun second profil : un test vérifie qu'aucun modèle
> `opex.expert.profile` n'existe et que les cinq pointent bien vers celui du
> Module 2.
>
> ⚠ **Le vrai livrable est sur `res.partner`** : huit champs calculés qui
> exposent le capital là où `_score_candidate()` sait lire. Sans eux,
> l'Extension 4 n'aurait rien à comparer, et on ne s'en apercevrait qu'à ce
> moment-là.
>
> **Deux régressions volontaires** : un `store=True` sur une cible de matching
> (test rouge), et le savepoint retiré de la création portail (500 au lieu du
> message).
>
> **Trois manques déclarés pour l'Extension 4** : pas de tarif journalier sur
> le profil (critère « Budget 10 % »), pas de langues côté expert (critère
> « Localisation / langue 5 % »), pas de justificatif joint à une certification.
> Aucun des trois n'est dans les cinq modèles du périmètre.

**§15 et §16 de la spécification Smart Missions.**

Étend `opex.innovation.expert.profile` — **ne le recrée pas**.

`opex.expert.skill` (**ligne de qualification** : `expert_profile_id` +
`competence_id` vers `opex.innovation.competence` + `niveau` + `annees` — pas un
référentiel, voir l'Extension 1), `opex.expert.experience`,
`opex.expert.certification`, `opex.expert.availability`, `opex.expert.rating`.

Et sur `res.partner`, les `related` que le matching sait lire : le moteur
compare **toujours** à un champ de `res.partner`, jamais au profil. C'est ce qui
rendra `reputation_score` (Extension 10) exploitable par le critère
« Réputation OPEX 10 % ».

C'est le capital que le matching interroge. Sans lui, l'Extension 4 n'a rien à
comparer.

## Extension 4 — Smart Matching Mission / Expert ✅ FAITE

> **Livrée le 30/08/2026** — 158 tests au total, 0 échec. Protocole manuel :
> `opex_intervenants/docs/protocole_test_extension4.md`.
>
> **Le scoring reste celui du moteur.** Ce module résout les critères, écarte
> les candidats qui ratent un obligatoire, puis appelle
> `instance._score_candidate()`. Un test lit le source du module et échoue s'il
> y trouve `_score_candidate`, `_compare` ou `_as_set`.
>
> ⚠ **Pourquoi `run_matching()` du moteur n'est pas utilisé** : il résout ses
> critères par `search([('definition_id', '=', …)])`, donc **tous** ceux de la
> définition. Avec des profils par type coexistant sous la même définition, un
> appel de formation serait noté avec les critères d'audit **et** les siens.
> Trois issues, une seule acceptable : ni modifier le moteur, ni réécrire un
> scoring, mais **lui passer le recordset de critères** — ce que
> `_score_candidate(partner, criteria)` accepte déjà.
>
> **Trois niveaux de pondération**, résolus **par famille** : défaut → type de
> mission → appel. Un type ne redéclare que ce qu'il change ; le reste est
> hérité.
>
> **`opex.mission.criteria` n'existe pas** comme modèle séparé, contrairement
> au tableau du modèle de données plus haut : `opex.matching.criteria` étendu
> de `family` + `mission_type_id` + `mission_id` + `is_eliminatoire` fait le
> travail, et un modèle distinct aurait forcé à réécrire le scoring pour lire
> ses poids.
>
> **Casse volontaire** : `eliminatoires = criteria.browse()` — deux tests
> rouges, dont le message dit le défaut en toutes lettres (« a été noté au lieu
> d'être écarté »).
>
> ⚠ **Dette D1** — le critère éliminatoire de certification compare du texte
> libre, sur un critère qui décide qui entre dans le vivier. Trois défaillances
> mesurées, correction identifiée, référentiel déjà disponible : voir la
> section **Dettes explicites** plus bas. À annoncer, pas à découvrir.
>
> **Limite laissée telle quelle, arbitrée le 30/08** : le message « le candidat
> ne renseigne pas ce champ » est ambigu sur la réputation — l'expert n'a pas
> omis sa note, il n'a jamais été évalué. Le message vient de `_compare()` ; on
> ne touche pas au moteur pour un libellé.

**§6 de Smart Missions.** Configure le moteur de matching existant, n'en écris
pas un second.

Critères : compétences 30 %, expérience 20 %, secteur 15 %, disponibilité 10 %,
budget 10 %, réputation OPEX 10 %, localisation/langue 5 % — **pondérations
configurables par type de mission**.

⚠️ **Les critères éliminatoires sont évalués AVANT le score pondéré.** Un
candidat qui ne remplit pas un critère obligatoire est écarté, pas mal noté.

⚠️ **Le score doit être explicable** : critères positifs, manquants, pénalisants.
Un score sans explication n'est pas défendable devant un jury.

Actions du responsable : Inviter · Écarter · Mettre en short-list · Consulter le
profil · Voir l'explication du score. **L'IA recommande, l'humain décide.**

### Arbitrages rendus le 30/08/2026, avant l'Extension 4

Quatre questions posées à la fin de l'Extension 3, quatre réponses. Elles font
foi ; ne pas les rouvrir.

**① Les critères éliminatoires passent par `action.matching_domain`.**
Le moteur n'a pas de notion de critère éliminatoire, et n'en aura pas :
`_score_candidate()` normalise sur la somme des poids applicables, il ne sait
pas écarter. `opex.workflow.action.matching_domain` restreint le **vivier
avant** le scoring (`workflow_action.py:127`) — « écarté, pas mal noté » se lit
alors « absent du vivier ». C'est exactement ce que demande le §11, **sans une
ligne de Python ajoutée au moteur**.

**② `tjm_indicatif` sur le profil expert.**
Le critère « Budget 10 % » a besoin d'un tarif **avant** que la candidature
existe — le matching tourne en amont. C'est un **indicatif** ; la candidature
portera le tarif ferme (`tarif_propose`, déjà là depuis l'Extension 1).

⚠ Conséquence à ne pas manquer : la mission porte un **budget total**
(`budget_estimatif`) et l'expert un **tarif journalier**. Les comparer
directement n'a aucun sens. Le moteur sait le faire sans modification, parce
que `source_expression` est évaluée par `safe_eval` :

```
source_expression : field('budget_estimatif') / (field('duree_estimee_jours') or 1)
target_field      : expert_tjm
match_mode        : lte          # candidat ≤ dossier (workflow_instance.py, _compare)
```

Le `or 1` n'est pas de la coquetterie : une durée non renseignée vaut 0 et la
division ferait échouer le critère — neutralisé et signalé dans l'explication,
mais pour une mauvaise raison.

**③ `langues` sur le profil expert**, en face du champ `langues` de la mission
(posé à l'Extension 1).

⚠ Deux champs `Char` de part et d'autre : `_as_set()` normalise en minuscules
et compare des chaînes, donc « Français » croise « français », mais **pas**
« FR ». Un référentiel serait plus robuste ; le `Char` est retenu pour le MVP,
par symétrie avec le champ déjà en place côté mission. Le risque est là, il est
assumé, et il se corrige par un référentiel des deux côtés le jour où le
cluster le demande.

**④ Justificatif de certification** : le champ existe, il reste **facultatif**.
Une certification non prouvée n'est pas bloquante pour le MVP, mais le champ
doit exister **avant** que des données soient saisies — le rétro-remplir
ensuite coûte plus cher que de le poser maintenant.

Les trois champs (② ③ ④) sont à ajouter **au début de l'Extension 4**, dans le
prolongement de l'Extension 3 : ce sont des données de profil, pas de la
configuration de matching.

## Extension 5 — Appel portail et candidature Lean ✅ FAITE

> **Livrée le 30/08/2026** — 185 tests au total, 0 échec. Protocole manuel :
> `opex_intervenants/docs/protocole_test_extension5.md`.
>
> **La vue publique est un dictionnaire à clés fermées**, jamais le recordset.
> Les clés masquées sont **absentes**, pas mises à `False` : un gabarit qui les
> afficherait lèverait au premier rendu.
>
> ⚠ **Le §12 du Module 3 et le §7 de la spécification se contredisent** sur le
> client et le budget. Ils se réconcilient par `public_fields_only`, réglé
> **par appel** depuis l'Extension 1 — ce n'est pas un arbitrage entre deux
> documents, c'est un paramétrage, et c'est le cluster qui le tient.
>
> ⚠ **Deux niveaux de la règle 1**, et ils diffèrent : **candidater** demande un
> profil quel que soit son avancement — sans quoi le « candidat externe » du §7
> ne pourrait pas entrer ; **entretenir son capital** demande un profil
> **activé**. `opex_mission_profile()` porte le premier, `expert_profile_id` le
> second.
>
> **Deux régressions volontaires** : le filtre de confidentialité retiré du
> dictionnaire, et l'enseignement qu'elle a donné — voir la règle 12.

**§7, §9, §12, §13.**

- vue publique contrôlée de l'appel — **une vue dédiée, pas l'objet interne
  complet**. Client, budget et documents sensibles peuvent rester masqués
- CTA « Je suis intéressé »
- **candidature Lean** : un expert référencé ne ressaisit **jamais** ses
  informations permanentes. Seules les données propres à la mission sont
  demandées — disponibilité, tarif, délai, approche, documents
- un candidat externe crée un mini-profil ; s'il est qualifié, il peut intégrer
  le référentiel

⚠️ **Règle 1 du §39** : on ne peut candidater que si on a le profil Expert. Vérifié
**côté serveur** sur la route, pas seulement par l'affichage du bouton.

## Extension 6 — Pool unique, qualification, short-list ✅ FAITE

> **Livrée le 30/08/2026.** Protocole manuel :
> `opex_intervenants/docs/protocole_test_extension6.md`.
>
> **Rien n'a été ajouté pour faire converger les candidatures** : elles
> convergent depuis l'Extension 1 — un modèle, une définition, un champ
> `source`. Cette extension ajoute ce qui manquait pour en tirer parti : la
> colonne de Kanban, les alertes, l'écran de comparaison.
>
> ⚠ **`records_draggable="0"` sur le Kanban**, et c'est le point de conception.
> Glisser une carte écrirait `pool_column` et court-circuiterait le moteur : ni
> rôle, ni condition, ni historique. C'est le seul endroit du module où
> l'ergonomie native d'Odoo aurait cassé la règle qui gouverne tout le reste.
>
> ⚠ **Les alertes d'éligibilité attrapent ce que le matching ne filtre pas.**
> Les critères éliminatoires de l'Extension 4 filtrent le **vivier du
> matching** ; un candidat arrivé par le **portail** ne passe par aucun vivier.
> Sans elles, il atteindrait la short-list sans que rien ne signale qu'il n'a
> pas la certification obligatoire — et les deux canaux du §8 ne seraient plus
> comparables, ce que le §21 exige. Elles rejouent **les critères de l'appel**,
> pas une liste réécrite.
>
> ⚠ **`pool_column` est une `Selection` calculée et stockée** — le champ qu'on
> nous reprochera en soutenance. Réponse : calculé depuis `workflow_stage_id`,
> `readonly`, jamais écrit nulle part, et il regroupe dix étapes en six colonnes
> parce que le §10 demande des colonnes, pas une frise. Même parti
> qu'`is_published`, validé à l'Extension 1. Trois tests le gardent.

**§10.** Toutes les candidatures convergent dans le même objet, quelle que soit
leur origine — le champ `source` les distingue, rien d'autre.

Kanban Nouveaux → Qualifiés → Short-list → Retenus, avec score, alertes
d'éligibilité et comparaison des profils.

C'est ici que la **seconde machine à états** prend tout son sens : chaque
candidature avance indépendamment, la mission reste en `SELECTION`.

## Extension 7 — Sélection, contrat, ordre de mission ✅ FAITE

> **Livrée le 31/08/2026** — 228 tests au total, 0 échec. Protocole manuel :
> `opex_intervenants/docs/protocole_test_extension7.md`.
>
> **C'est le jalon P0 du §20** : une mission naît d'un besoin client et aboutit
> à un intervenant sélectionné avec son contrat généré.
>
> ⚠ **Le sous-workflow `mission_contract` tourne sur `opex.mission.request`,
> pas sur `opex.mission.contract`**, et ce n'est pas un choix. La règle 5 a été
> écrite `subworkflow_done('mission_contract')` à l'Extension 1, et
> `_subworkflow_done()` cherche par `res_model` / `res_id`
> (`workflow_instance.py:305`). Posée sur le modèle du contrat, la définition
> ne serait jamais vue par l'instance de la mission : la condition renverrait
> `False` pour toujours, **sans erreur** — le helper est tolérant. Le contrat
> *document* est `opex.mission.contract` avec ses versions ; le contrat
> *processus* est ce sous-workflow.
>
> ⚠⚠ **`contract_validated` est la SEULE étape `is_end`** — la règle 14 des
> règles transversales, née ici. Une seconde étape finale ferait qu'un contrat
> **refusé** satisfait la règle 5.
>
> **Les effets du §13 passent par `set_field`**, sur un champ
> `operational_trigger` dont l'inverse dispatche par
> `getattr(self, '_trigger_%s' % code)` — le calque du `_execute_<action_type>`
> du moteur. Aucun des six types d'actions ne sait créer une affectation, et
> lui apprendre à le faire lui apprendrait le métier. La ligne de partage :
> **la configuration décide quelle transition déclenche quoi ; le Python
> n'implémente que l'effet.** Un test examine chaque méthode du fichier, sans
> ses docstrings, et échoue si l'une appelle `do_transition`.
>
> **Deux casses volontaires.** L'étape de révision marquée `is_end` — deux
> tests rouges, dont un message qui dit tout : `'done' != 'running'`. Et
> l'enseignement du test de source, qui rougissait sur **sa propre prose** :
> un test qui interdit un mot interdit aussi qu'on en parle, et aurait fini par
> faire supprimer l'explication plutôt que le défaut.
>
> **Trois tests de l'Extension 1 ont rougi, et c'était leur raison d'être** :
> `test_the_retained_expert_is_not_yet_actor_of_the_mission` (l'acteur est
> posé, il est réécrit), `test_the_deferred_rules_are_declared_but_not_attached`
> (la règle 5 a trouvé son objet ; les deux règles de livrables restent
> surveillées pour l'E8), et le parcours nominal, qui passe désormais par le
> cycle du §19.

**§13 de Smart Missions, §39 règles 4 et 5.**

Le passage à `SELECTED` déclenche, **par des actions configurées sur la
transition** et non par du Python métier : notification, collecte de pièces, NDA,
génération du contrat, ordre de mission, création du projet et des tâches,
calendrier, accès documentaire.

- template QWeb PDF pour l'ordre de mission et le contrat
- ⚠️ **Règle 4** : une seule candidature retenue par mission, sauf si le type de
  mission autorise explicitement plusieurs intervenants
- ⚠️ **Règle 5** : contrat non validé → mission non démarrable. C'est une
  **condition sur la transition**, pas un `if` dans une méthode

### Les trois arbitrages rendus pendant l'Extension 7

**① Les effets du §13 sont répartis sur trois transitions**, pas tous sur
`atr_select`. Le §13 dit « **selon configuration** » : c'est la spécification
elle-même qui laisse le placement au réglage.

| Transition | Ce qui se déclenche |
|---|---|
| `atr_select` | notification, affectation, acteur `intervenant` sur la mission, contrat + ordre de mission, NDA si l'appel l'exige |
| `mtr_start_contracting` | `launch_subworkflow` → cycle de validation, puis report des acteurs |
| `mtr_start_mission` | projet, tâches, échéances — **après** la règle 5 |

Le projet n'est pas créé à la sélection : `mission_contracting_failed`, posée à
l'Extension 1, laisserait un projet orphelin par tentative.

**② Les autres candidats ne sont PAS écartés automatiquement**, malgré le §17
(« Les autres candidats passent à Non retenu »).

`rejected` est `is_end`, donc irréversible. Les rejeter tous à la sélection
viderait `mission_back_to_selection` — « L'intervenant s'est désisté », posée à
l'Extension 1 parce que le §2.4 l'exige : on reviendrait en sélection sans un
seul candidat récupérable. Ils sont **signalés** au responsable par une note sur
la mission, qui les écarte quand le contrat est signé.

**③ La règle 4 est tenue à trois niveaux, et les trois disent la même chose à
trois publics.** Le premier seul serait une convention — il ne protège que le
chemin qui passe par la transition.

1. `rule_application_single_selection`, condition de transition (E1) —
   **l'explication**, lue avant le clic ;
2. `unique(application_id)` sur l'affectation — une candidature ne produit
   jamais deux affectations ;
3. `_check_single_assignment()` — le compte par mission confronté à
   `multi_intervenants`. L'exception étant portée par une **autre table**
   (`opex.mission.type`), un index partiel ne pouvait pas l'exprimer.

### Ce que `start_subworkflow()` ne fait pas, et qu'il fallait faire

**Il ne recopie aucun acteur.** `_start_for()` crée une instance neuve
(`workflow_instance.py:1261`). Sans report, deux dégâts silencieux : « Signature
refusée », ouverte au client et à l'intervenant, n'aurait jamais eu de porteur ;
et « Informer que le contrat est validé » n'aurait notifié personne —
`_partners_for_roles()` résout les acteurs **de l'instance visée**
(`workflow_instance.py:895`). D'où le déclencheur `contracting`, en séquence 20,
après le lancement.

### Limite d'environnement — à annoncer

**`wkhtmltopdf` est absent du poste.** `ir_actions_report.py:868` lève
« Unable to find Wkhtmltopdf ». Les deux rapports restent déclarés en
`qweb-pdf` — leur forme juste — et un bouton **Aperçu** ouvre
`/report/html/...`, la route native, qui rend le même gabarit sans binaire.
Même catégorie que le SMTP : une limite de machine, pas un défaut de module.

## Extension 8 — Exécution de la mission ✅ FAITE

> **Livrée le 31/08/2026** — 262 tests au total, 0 échec. Protocole manuel :
> `opex_intervenants/docs/protocole_test_extension8.md`.
>
> **Troisième définition du module, neuvième du projet.**
> `opex.mission.deliverable` porte le mixin et **aucun champ `state`**.
>
> ⚠ **Cinq étapes, pas quatre.** Le Schéma 9 du §23 intercale « En cours »
> entre « À faire » et « Soumise », et c'est le `Module3_OPEX_Intervenants.md`
> qui fait foi sur l'UX. Sans elle, « pas commencé » et « commencé, pas rendu »
> se confondent, et le §43 ne peut plus signaler un retard sur ce qui a
> réellement démarré. Cinq transitions aussi, dont deux pour la seule boucle de
> correction — c'est elle qui fait de ce cycle un graphe et non une séquence.
>
> **Le motif du refus est porté par la version archivée**, jamais par le
> livrable, et il est **relu dans le journal d'audit** au moment d'archiver
> plutôt que recopié au moment du refus. La leçon d'`opex_innovation`,
> appliquée telle quelle, y compris `_archive_current_version()` **avant**
> l'écriture et le `write()` verrouillé hors `sudo()`.
>
> **Casse volontaire** : archivage déplacé après l'écriture — deux tests
> rouges, dont le message dit `'v2.pdf' != 'v1.pdf'`.
>
> **Trois tests antérieurs ont rougi**, et les trois pour la bonne raison :
> `test_the_deferred_deliverable_rules_fail_closed` (leur champ existe
> désormais), `test_the_deferred_rules_are_attached…` (la condition de dépôt a
> pris sa place), et `test_no_selection_field_describes_progress` — celui-là
> mérite d'être lu, voir la règle 17.

**§40, §21 à §26.**

Mission, jalons, livrables, incidents. L'intervenant renseigne temps passé,
avancement, livrables, problèmes, prochaine étape.

Le cycle de vie d'un livrable est **lui-même un petit workflow** — réutilise le
pattern d'`opex_innovation`, ne le recode pas.

### Trois arbitrages rendus pendant l'Extension 8

**① Les jalons du §22 ne sont pas un modèle séparé.** « Une mission peut être
divisée en plusieurs étapes ; chaque étape peut avoir une date, un responsable,
un statut, un livrable. » Un objet de plus portant un statut dérivé de celui de
ses livrables serait un second récit de la même histoire — et c'est toujours le
second qui se désynchronise. Le jalon est un **libellé de regroupement**
(`jalon` + `sequence`) porté par le livrable.

**② L'incident porte un champ d'état, et c'est assumé.** Le Schéma 10 du §26
donne le cycle en entier : Ouvert → En traitement → Résolu. Linéaire, sans
chemin de refus, sans condition, sans rôle qui change. C'est exactement la
ligne de partage que le CLAUDE.md du moteur pose pour `roadmap.phase`.

Le champ s'appelle `traitement` — pas pour esquiver la règle, mais parce que
`state` est un nom pris par l'API interne d'Odoo. C'est bien un champ d'état,
il est nommé comme tel dans son libellé, et le critère est écrit dans la
docstring plutôt que découvert en soutenance.
`test_the_incident_is_a_counter_not_a_process` **verrouille le critère** : une
quatrième issue le fait rougir, et la conversation a lieu.

**③ La règle 6 du §39 reste rattachée à rien**, alors que son champ existe
désormais. `mission_request_workflow.xml` écrit sur `mtr_accept_service` que
« la règle 6 y sera rattachée par l'Extension 9 ». On ne déborde pas d'une
extension sur la suivante, même quand c'est techniquement possible. La
condition de **dépôt**, elle (`mission_deliverables_submitted`), est bien prise
en charge ici : elle garde « Soumettre les livrables ».

### La barre du §40 — une projection, pas un champ

> Demande ✓ — Appel ✓ — Sélection ✓ — Contrat ✓ — Mission ● — Validation ○ —
> Facturation ○ — Évaluation ○

`mission_progress_bar()` est une **méthode**, pas un champ stocké : rien ne
filtre ni n'agrège sur la barre, la stocker n'ajouterait qu'une valeur à
resynchroniser. C'est le même parti que `pool_column` (E6) à ceci près que
celui-là devait être groupable dans un Kanban, ce qui justifiait son stockage.

Deux points à défendre :

- ~~**Facturation et Évaluation n'ont aucune étape**~~ — le test a rougi à
  l'Extension 9, comme annoncé. `mission_close` s'appelant « Facturer et
  clôturer » et émettant désormais la commande de vente, une mission `closed`
  est une mission **facturée** : le jalon Facturation lui revient, et
  `validation` s'est resserré sur `accepted`. **Évaluation** n'a toujours
  aucune étape et reste `a_venir` même sur une mission payée ; elle figure
  quand même, le §40 en comptant huit, et le test la surveille jusqu'à
  l'Extension 10.
- **Une mission suspendue n'a aucun jalon `en_cours`.** `on_hold`, `cancelled`
  et `unsuccessful` ne sont sur aucun jalon : la mission est sortie de la ligne
  du §40, et la barre le dit au lieu d'inventer une position.

## Extension 9 — Service fait et facturation ✅ FAITE

> **Livrée le 01/09/2026** — 284 tests au total, 0 échec. Protocole manuel :
> `opex_intervenants/docs/protocole_test_extension9.md`.
>
> **Quatrième définition du module, dixième du projet.**
> `opex.service.acceptance` porte le mixin et **aucun champ `state`**.
>
> ⚠ **La règle 6 garde DEUX transitions, et c'est le même enregistrement de
> règle.** « Valider le service fait » sur la mission (le rattachement que
> l'Extension 1 avait annoncé) et « Valider (cluster) » sur le constat. Une
> règle jumelle écrite pour le constat aurait divergé au premier ajustement
> — c'est la règle 16 prise du bon côté. Ce qui le permet :
> `opex.service.acceptance.deliverable_unvalidated_count`, un `related` non
> stocké, `field()` résolvant sur l'enregistrement piloté.
>
> ⚠ **Le « Résultat » du §28 n'est pas un champ.** Le document dit « Le
> système enregistre : Date de validation, Validateur, Commentaire,
> Résultat » : les trois premiers sont dans le journal du moteur, le
> quatrième **est l'étape atteinte**. Les six champs de validation sont
> **calculés depuis l'historique**, jamais écrits — la leçon de l'Extension 8
> sur le motif de refus, appliquée une seconde fois. Un constat contesté puis
> revalidé passe deux fois par la même étape, et c'est la seconde qui compte.
>
> ⚠⚠ **`accepted` est la SEULE étape `is_end`** — règle 14. `disputed` boucle
> vers l'amont. Mesuré par régression volontaire : trois tests rouges, dont
> `'done' != 'running'` et la reprise devenue infranchissable — le client qui
> conteste aurait fermé la mission **définitivement**.
>
> **Seconde régression volontaire** : la règle 6 détachée de ses deux
> transitions — trois tests rouges, sous trois angles (la configuration, le
> comportement, et le veilleur de règle différée de l'Extension 1).
>
> **Trois tests antérieurs ont rougi, et les trois pour la bonne raison** :
> `test_the_validation_rule_stays_deferred_to_extension_9` (retourné),
> `test_the_last_two_milestones_wait_for_extensions_9_and_10` (Facturation a
> reçu son objet ; il ne surveille plus qu'Évaluation), et
> `test_the_deferred_rules_are_attached_when_their_object_exists`, qui affirme
> désormais les **deux** rattachements de la règle 6.

**§27, §28, §29 · US-14 du backlog.**

`opex.service.acceptance` : validation cluster, validation client, service fait,
puis `sale.order` pour la facturation.

⚠️ **Règle 6** : une mission n'est pas terminée tant que les livrables
obligatoires ne sont pas validés. Condition sur la transition.

### Trois arbitrages rendus pendant l'Extension 9

**① Le Schéma 12 n'est PAS une cinquième définition de workflow.**

> Mission validée → Facturation → Facture générée → En attente de paiement
> → Payée

Ces quatre cases **existent déjà**, et pas dans ce module : ce sont
`sale.order.state`, `sale.order.invoice_status` et
`account.move.payment_state`. Une définition parallèle serait un second récit
de la même histoire, et elle se désynchroniserait au premier paiement
enregistré depuis l'écran de banque — c'est-à-dire par le chemin normal.

La ligne de partage du moteur s'applique telle quelle : le constat a un
valideur, un chemin de contestation et une boucle de reprise, c'est un
**processus** ; la facturation est un **constat de ce qu'Odoo a fait**.
`test_the_invoicing_has_no_workflow_of_its_own` verrouille le critère.

C'est aussi ce que démontre le jalon Facturation de la barre du §40 : il est
le seul des huit que `workflow_stage_id` ne suffit pas à décrire, parce que
`payment_state` change **sans qu'une transition soit franchie**.

**② Le constat s'ouvre à « Soumettre les livrables », pas à « Valider le
service fait ».** Il *instruit* la validation finale : posé sur la transition
qui la conclut, il serait créé déjà validé et les deux passages du §28 —
cluster puis client — n'auraient nulle part où se dérouler. Idempotent, la
boucle de correction du §25 repassant par cette transition.

**③ La facturation tout entière est dans un savepoint** — règle 10. Une
écriture comptable qui échoue (journal manquant, compte de produit non
paramétré, exercice clos) laisse la transaction PostgreSQL abandonnée : *tout*
ce qui suit reçoit « current transaction is aborted », y compris
l'enregistrement de la transition en cours. Le parti : ou la facturation
aboutit entièrement, ou elle est annulée et **signalée dans le dossier**. Une
mission clôturée sans facture est un problème visible ; une transaction morte
est un 500.

`invoice_policy = 'order'` sur le produit de service, et ce n'est pas un
détail : en `'delivery'`, `_create_invoices()` refuserait de facturer une
quantité livrée nulle et la facturation échouerait sur **chaque** mission.

### Limite déclarée — propriétaire : Extension 11

**La validation du client se fait depuis le back-office.** Même arbitrage
qu'à l'Extension 7 pour la signature du contrat, et il est tenable parce que
le §27 autorise explicitement « le client **ou le responsable habilité** ».
C'est le canal qui manque, pas la fonction. Les droits sont déjà posés du bon
côté : le client lit le constat et ne peut pas cocher les quatre points du
cluster (`test_the_client_cannot_tick_the_cluster_checklist`).

## Extension 10 — Évaluations et réputation ✅ FAITE

> **Livrée le 01/09/2026** — 310 tests sur `opex_intervenants`, 0 échec ;
> 1048 tests sur les cinq modules après le nettoyage typographique, 0 échec.
> Protocole manuel : `opex_intervenants/docs/protocole_test_extension10.md`.
>
> **Cinquième définition du module, onzième du projet.**
> `opex.mission.evaluation` porte le mixin et aucun champ `state`.
>
> **Les deux règles sont des objets de configuration, pas du Python.** La
> règle 7 est une condition sur « Soumettre l'évaluation » ; la règle 8 est
> une action `set_field` sur « Valider l'évaluation ». Aucune des deux n'est
> un `if`.
>
> **Le « Résultat » du §28 avait déjà montré la voie, et le §30 la reprend** :
> ce que le document appelle un résultat est l'étape atteinte. Il n'y a pas
> de champ pour ça.
>
> **La boucle du §2 se referme sans une ligne nouvelle côté profil.**
> `opex.expert.rating` avait été créé vide à l'Extension 3 et
> `reputation_score` dépend déjà de `expert_rating_ids.note` : l'Extension 10
> crée les lignes, la réputation suit.
>
> **Une seule étape `is_end`** — `validated`. « Renvoyée à son auteur » boucle
> vers l'amont : une évaluation écartée sans retour ferait perdre la note
> d'une mission pour une phrase mal tournée, et le §32 compte sur ces notes.
>
> **Deux régressions volontaires, et la première a été instructive.** En
> retirant la garde d'idempotence du report au profil, le test censé la
> mesurer est **resté vert** : `validated` étant finale, le chemin qu'il
> déroulait ne repassait jamais par la validation. Le test a été scindé en
> deux — voir la règle 20 ci-dessous. La seconde (moyenne prise sur les dix
> critères au lieu des six applicables) a produit 1 échec et 14 erreurs, avec
> le message `3.0 != 5.0`, soit l'arithmétique exacte du défaut.
>
> **Un test antérieur a rougi** : celui qui affirmait que le jalon Évaluation
> attendait cette extension. Les huit jalons du §40 ont désormais tous leur
> objet.

**§30, §31, §32, §33.**

- évaluation client : qualité, délais, expertise, communication, pertinence,
  satisfaction — chacune /5
- évaluation cluster : respect du contrat, délais, qualité des livrables,
  professionnalisme, communication, procédures
- **réputation** calculée : note moyenne, missions réalisées, taux de
  satisfaction, respect des délais
- historique des missions par intervenant, avec visibilité contrôlée

⚠️ **Règle 7** : le client n'évalue qu'après la validation finale.
⚠️ **Règle 8** : une évaluation validée alimente le profil — c'est la boucle
d'apprentissage de la §2.

### Trois arbitrages rendus pendant l'Extension 10

**① Un seul modèle pour les deux grilles, séparées par `evaluateur`.** Le §30
et le §31 partagent deux critères sur six — le respect des délais et la
communication. Deux modèles auraient dupliqué la moitié des champs, le calcul
de la moyenne, le workflow et les droits. Le champ `evaluateur` sépare, et
`_criteria_fields()` décide des six applicables.

⚠ Le piège qui va avec, et il est réel : **la moyenne ne porte que sur les six
applicables**. Prise sur les dix champs du modèle, elle ferait chuter chaque
note de quatre zéros et le §32 hériterait de l'erreur en silence. Mesuré par
régression volontaire.

**② La règle 7 garde les deux grilles, pas seulement celle du client.** Le
texte de la règle nomme le client, mais son titre est général —
« L'évaluation intervient après la mission ». Une évaluation opérationnelle
rendue avant le service fait serait tout aussi prématurée. La condition lit
`mission_validee`, qui traverse jusqu'au constat du §28 : la « validation
finale » du document est celle-là, pas la clôture administrative.

**③ Le commentaire d'évaluation ne sort jamais.** Le §33 autorise à publier
certaines informations ; `is_public` n'ouvre que la note globale. Un
commentaire d'évaluation est un jugement nominatif sur une personne, et
l'historique public n'a pas à le porter. Le filtre est dans le dictionnaire,
pas dans le gabarit — leçon de l'Extension 5, règle 12.

### Limite déclarée — propriétaire : Extensions 11 et 12

Le client remplit sa grille **depuis le back-office**, comme il valide le
service fait depuis l'Extension 9. `public_reputation()` existe et est testée ;
la page d'annuaire qui la rend relève de l'Extension 12.

## Extension 11 — Tableaux de bord et notifications ✅ FAITE

> **Livrée le 01/09/2026** — 335 tests sur `opex_intervenants`, 0 échec.
> Protocole manuel : `opex_intervenants/docs/protocole_test_extension11.md`,
> jeu de données : `opex_intervenants/docs/seed_demo.py`.
>
> **Vérifiée dans un vrai navigateur, console ouverte, sous trois identités**
> — intervenant, responsable, client. C'est cette vérification, et elle seule,
> qui a trouvé le défaut décrit plus bas.
>
> **Les quatre espaces sont un `AbstractModel`**, `opex.mission.dashboard`.
> Chacun renvoie un dictionnaire à clés fermées, et aucun ne reçoit son
> périmètre du gabarit — c'est le modèle qui borne, ce qui est la seule façon
> de tenir « chacun voit ce qui le concerne » (§18).
>
> **Les seize notifications ajoutées sont toutes des actions `notify`.** Un
> test lit le source de tous les modèles, docstrings et commentaires retirés,
> et rougit si un `message_post` apparaît ailleurs que dans trois fichiers
> nommément autorisés — où il s'agit de comptes rendus posés sur le dossier,
> pas de notifications à un rôle.

**§34, §41, §42, §43 · §18 de Smart Missions.**

Quatre espaces : Responsable OPEX (Smart Work Queue), Intervenant, Candidat
externe, Client.

Priorisation §43 : Urgent · À traiter · Terminé.

Notifications : les trois listes du §34, **toutes par des actions `notify`
configurées sur les transitions**, jamais par des `message_post()` dispersés.

Et la surcharge de `_opex_owned_record_ids()` + `_opex_notification_url()` pour
que la cloche portail voie les missions et les candidatures.

### Le défaut que seul le navigateur pouvait montrer

Le §34 fait prévenir le client qu'une candidature a été déposée sur son appel.
Le message est posté **sur la candidature**, et `_opex_notification_url()`
renvoyait tout le monde vers `/my/candidatures/<id>` — un écran que
l'`ir.rule` du portail réserve au candidat. Le client cliquait sur sa
notification et tombait sur un **404**.

Aucun test ne pouvait le voir. Celui qui existait vérifiait que l'URL commence
par `/my/`, ce qui restait vrai ; les tests HTTP ne cliquent pas sur les liens
de la cloche. Il a fallu ouvrir la page, cliquer, et lire la 404.

La cause est propre à cette extension : jusqu'ici, un message ne parvenait
qu'au **propriétaire** de l'enregistrement, et l'URL pouvait se déduire du seul
modèle. La cloche montre désormais aussi ce qui est **adressé nommément** sur
le dossier d'un autre — c'est ce qui la rend utile, et c'est ce qui oblige à
résoudre le lien pour le **lecteur** et non pour l'objet.
`_application_notification_url()` le fait, et un test le maintient.

### Trois arbitrages rendus pendant l'Extension 11

**① Le client devient acteur des candidatures déposées sur ses appels.**
Sans cela, la notification « candidature reçue » du §34 serait partie dans le
vide : `_partners_for_roles()` résout les acteurs de l'instance visée et écarte
ceux dont l'accès vaut `none` — un rôle sans porteur ne notifie personne, sans
erreur ni trace.

Ce que cela ouvre : les notifications, et rien d'autre. Aucune transition du
workflow de la candidature n'est ouverte au rôle `client` — un test le
verrouille. Et l'`ir.rule` du portail borne toujours la lecture à
`partner_id = user.partner_id` : le client est prévenu, il n'ouvre pas le
dossier du candidat, ce que le §14 demande.

**② Le sous-type se choisit par destinataire, pas par action.** Sur « Déposer
ma candidature », trois messages partent : `comment` à l'intervenant, `note`
au client, `note` au responsable.

Le cas du client est celui qui a imposé la règle. Il n'est pas follower de la
candidature — mais l'intervenant l'est. En `comment`, le message destiné au
client serait parti **par email au candidat**, pour un message qui ne le
concerne pas. En `note`, il atteint quand même le client dans sa cloche, parce
que `_execute_notify()` passe toujours `partner_ids` et que la seconde source
de la cloche lit précisément ce champ.

**③ Deux items du §34 ne sont portés par aucune transition, et c'est déclaré.**
« Nouvel appel pertinent » vise un **segment** d'experts, pas les acteurs d'un
dossier — le §19 de la spécification le range lui-même dans les envois de
masse. « Retard » n'est pas un événement : il se constate en comparant une date
à aujourd'hui, et il est porté par la colonne Urgent du §43, où il reste
visible au lieu de passer une fois.

Les y forcer aurait demandé un `message_post()` dans un `create()` ou un cron —
c'est-à-dire exactement ce que le périmètre interdit.

## Extension 12 — Portail public et intégration finale ✅ FAITE

> **Livrée le 02/09/2026** — 352 tests sur `opex_intervenants`, 0 échec.
> Protocole manuel : `opex_intervenants/docs/protocole_test_extension12.md`,
> qui porte aussi **le parcours complet de bout en bout** du §48.
>
> **Vérifiée au navigateur** : `/opex` répond sans authentification, les
> quatre filtres du catalogue narrowent et se souviennent, `/staff/kpi`
> affiche les neuf critères du §21 en vert et refuse un compte portail.
>
> ⚠ **Correction de référence** : la ligne ci-dessus citait **US-24**. C'est
> une erreur — US-24 du backlog concerne « créer des groupes de travail et des
> forums de discussion privés », rattachée à `opex_membership` en P3. La
> bonne référence est **US-20**, « consulter un tableau de bord KPI global
> (Taux de réussite, Performance des experts) », rattachée à
> `opex_intervenants` en P2.

**US-20 du backlog, §48.**

- catalogue public `/missions` avec filtres
- page d'accueil unique du portail reliant les trois domaines : annuaire, projets
  d'innovation, appels à missions
- dashboard KPI global agrégeant les trois modules

### La liste de contrôle du §21 est devenue exécutable

`acceptance_checklist()` calcule les neuf critères depuis la configuration et
les données, et `/staff/kpi` les affiche avec, pour chacun, **ce qui
l'établit**. Un critère qui cesserait d'être tenu passerait en rouge à
l'écran, et `test_the_nine_acceptance_criteria_are_met` rougirait.

C'est le seul moyen d'éviter qu'une liste de contrôle vieillisse mieux que le
code qu'elle décrit.

### Trois arbitrages rendus pendant l'Extension 12

**① Le filtrage est dans le domaine de recherche, pas sur la liste rendue.**
Filtrer après coup obligerait à construire tout le catalogue pour en garder
trois lignes, et surtout à porter dans les vignettes des champs qui ne servent
qu'au filtre — c'est-à-dire à rouvrir ce que le §14 ferme.

**② Les listes déroulantes sont bornées à ce que le catalogue contient.**
Proposer un domaine sur lequel aucun appel n'est ouvert donne une liste vide
et laisse croire à une panne.

**③ Le taux de réussite se calcule sur ce qui a abouti**, pas sur ce qui
existe. Compter les missions en route au dénominateur ferait chuter le taux à
chaque appel publié, ce qui dirait le contraire de la vérité. Et il vaut
**zéro** quand rien n'a abouti — un cluster qui n'a terminé aucune mission n'a
pas un taux parfait, il n'en a pas.

### Une valeur illisible neutralise son filtre

`/missions?date_min=zz` rendait un **500** sur une page publique, ouverte à
tout visiteur : la chaîne atteignait le domaine de recherche et PostgreSQL
refusait la comparaison. Trouvé par le test qui envoie volontairement une
requête mal formée.

Les dates sont désormais validées dans le controller. Sur une page publique,
**ne pas filtrer vaut mieux que ne pas répondre** — la même asymétrie prudente
que `_evaluate_flag()` du moteur.

---

## Extension IA-0 — Le service d'assistance IA ✅ FAITE

> **Livrée le 02/09/2026** — **384 tests, 0 échec** sur les deux modules, dont
> **32 pour `opex_ai_core`** (22 pour le service, 10 pour la couche prompt).
> Aucun parsing réel : le service, son journal, ses prompts, son écran.
>
> ⚠ **Le service vit dans un module à lui, `opex_ai_core`.** Il a d'abord été
> écrit dans `opex_intervenants`, puis extrait avant que quoi que ce soit soit
> construit dessus — le backlog le prévoit pour l'US-23, qui appartient à
> `opex_membership`, et l'y laisser aurait obligé le Module 1 à dépendre du
> Module 3.
>
> `opex_intervenants` dépend d'`opex_ai_core`, jamais l'inverse. Le module de
> service ne dépend que de `base` : un service d'infrastructure qui
> dépendrait d'un module métier n'en serait plus un.
>
> ⚠ **Les prompts sont en données versionnées**, `opex.ai.prompt`, et le
> service expose `_call_prompt(code, values)` que les appelants utiliseront à
> la place de `_call()`. Aucune chaîne de prompt dans le code — y compris
> celle de l'essai de connexion, qui était pourtant la plus facile à
> justifier en dur.
>
> **Pas de bloc `noupdate` sur les prompts**, contrairement aux workflows.
> Ceux-là portent un état d'exécution — compteur de séquence, drapeau de
> publication, instances en cours — qu'un `-u` ne doit pas réinitialiser. Un
> prompt ne porte rien : le fichier est la référence, et un `-u` doit le
> redéployer. C'est ce que « versionné » veut dire.
>
> ⚠ **La spécification `Specification_OPEX_Smart_Expert_Onboarding.md`
> n'existe pas dans le dépôt.** Les §6, §8, §9, §12 et §24 n'ont pas pu être
> lus. Ils portent sur le parsing, la taxonomie et le contrôle qualité,
> c'est-à-dire sur IA-1 et suivantes ; le périmètre d'IA-0 était entièrement
> donné par le prompt. **Le document est à fournir avant IA-1.**

### Les quatre règles, et où elles sont vérifiées

| Règle | Test |
|---|---|
| Sans clé, `_call()` renvoie None sans lever | `test_without_a_key_the_call_returns_none_and_does_not_raise` + `::_no_http_call_is_attempted` |
| Un JSON illisible n'est jamais fatal | `test_an_unparsable_answer_is_logged_and_returns_none`, `::_a_fenced_json_block_is_accepted`, `::_an_answer_without_candidates_is_not_fatal` |
| Timeout dur et retry sur 429 | `test_a_429_is_retried_with_a_backoff`, `::_a_persistent_429_gives_up_after_three_attempts`, `::_a_timeout_returns_none_and_is_not_retried`, `::_the_hard_timeout_is_passed_to_the_request` |
| Aucune donnée métier en base | `test_the_call_writes_nothing_but_its_own_journal` |

Le journal est écrit dans les quatre cas d'échec, et c'est mesuré à chaque
fois.

### Le piège de la couche prompt, et pourquoi il compte

`str.format()` est la façon évidente de rendre un prompt à variables. Elle
casse sur exactement les prompts que ce module existe pour porter.

Tout prompt d'extraction contient un exemple du JSON attendu — c'est la seule
façon fiable d'obtenir du JSON d'un modèle de langage. Or
`'{"ok": true}'.format()` lève : Python y voit un champ de remplacement nommé
`"ok": true`.

`render()` substitue donc par expression régulière, en ne touchant qu'aux
`{nom_en_minuscules}`. Mesuré par régression volontaire : remettre
`str.format()` fait rougir cinq tests, avec le message `KeyError: '"ok"'`.

Corollaire tenu par le même code : une variable non fournie fait **refuser**
le rendu plutôt que d'envoyer `{cv_texte}` au modèle. Un prompt à moitié rendu
produit une réponse plausible et fausse, ce qui est le pire des deux mondes.

### Trois arbitrages rendus pendant IA-0

**① La seule écriture en base est le journal**, et il ne porte que des
métadonnées. Ni le prompt ni la réponse : un CV passé au service contient des
données personnelles, et un journal de supervision n'est pas un endroit où
les conserver. `test_the_journal_never_carries_the_prompt_or_the_answer`
verrouille le critère.

**② Le coût est estimé, le nombre de jetons est le fait.** Les tarifs sont
dans une table du service ; s'ils changent, les coûts passés se recalculent
depuis les compteurs, qui eux viennent du fournisseur. Un modèle inconnu est
estimé au tarif d'un « flash » — approximatif et assumé.

**③ Le journal porte la version du prompt**, et cinq points de sortie de
`_call()` l'écrivent. Ils passent par une fermeture plutôt que par cinq listes
d'arguments : c'est ce qui garantit qu'aucun cas d'échec n'oublie la version
ou l'objet de l'appel. Un journal incomplet à un seul endroit est exactement
celui qu'on consultera le jour de la panne.

Et `purpose` prend la valeur du code du prompt : le journal dit alors quelle
**fonctionnalité** a coûté quoi, pas « un appel à Gemini ». C'est la
différence entre un journal qu'on consulte et un journal qu'on subit.

### Ce que l'essai réel a appris, et qu'aucun test simulé n'aurait dit

Trois choses, dans l'ordre où elles sont apparues :

1. **`ListModels` ment.** Il a renvoyé 38 modèles, dont `gemini-2.5-flash`,
   qui répond ensuite « no longer available to new users ». La liste n'est pas
   une garantie ; seul l'appel en est une. C'est ce qui justifie le bouton
   « Tester la connexion » plutôt qu'une liste déroulante de modèles.
2. **Un modèle retiré répond 404**, sans message exploitable pour un
   administrateur. `_test_connection()` traduit désormais 404, 403 et 429 en
   phrases qui disent où chercher — et surtout qui **séparent la clé du droit
   de s'en servir**.
3. **Le retry a été vérifié contre la vraie API** : `gemini-pro-latest` répond
   429, le service a fait 3 tentatives en 3547 ms (les pauses 1 s + 2 s
   comprises) et a journalisé `rate_limited`. La règle 3 n'est pas seulement
   simulée.

### Limite d'environnement — à annoncer

**La clé fournie authentifie mais son projet Google est refusé en
génération** : `ListModels` répond 200, `generateContent` répond 403 « Your
project has been denied access » sur tous les modèles servis. C'est un réglage
de compte, pas de code — et le module se comporte exactement comme prévu face
à cela : il journalise, il rend None, et rien ne casse. Même catégorie que le
SMTP et `wkhtmltopdf`.

---

## Extension IA-1 — Trois axes et parsing du CV ✅ FAITE

> **Livrée le 03/09/2026** — **428 tests, 0 échec** sur les deux modules, dont
> 18 pour le parsing et 6 pour les axes du §9. Protocole manuel :
> `opex_intervenants/docs/protocole_test_extension_ia1.md`, qui porte aussi
> **le JSON rendu sur un CV réel**.
>
> ⚠ **La spécification `Specification_OPEX_Smart_Expert_Onboarding.md` n'est
> toujours pas dans le dépôt.** Les deux décisions structurantes ont été
> tranchées par l'auteur des documents, et elles font foi :
>
> - **§8, taxonomie** : l'IA **propose** un rapprochement vers
>   `opex.innovation.competence`, elle n'écrit jamais de texte libre en base.
>   Deux temps, à l'IA-2 : correspondance exacte ou par synonyme d'abord, sans
>   appel IA ; puis proposition de l'IA avec sa confiance. Une compétence non
>   rapprochée part en file « à arbitrer », et c'est comme cela que la
>   taxonomie s'enrichit.
> - **§9, niveau et confiance** : **trois axes distincts** sur
>   `opex.expert.skill` — `niveau` (métier), `source` (d'où vient
>   l'information), `confiance` (ce qu'elle vaut).
>
> **Si le document contredit l'une des deux quand il arrivera, le dire plutôt
> que de coder autour.**

### Le point qui compte : le matching ne lit que le confirmé

`res.partner.expert_skill_competence_ids` filtre désormais sur
`is_confirmed`. Sans ce filtre, une compétence proposée par l'IA à la lecture
d'un CV ferait matcher l'expert **dès l'extraction**, avant que quiconque se
soit prononcé.

Le défaut aurait été silencieux et flatteur : plus de compétences, donc de
meilleurs scores, donc des experts proposés sur des compétences que personne
n'a validées. Mesuré sur données réelles — 3 compétences déclarées, **1 seule
vue par le matching** — et par régression volontaire : le filtre retiré fait
rougir deux tests.

⚠ Le champ dépend explicitement de `is_confirmed`. Sans cette dépendance,
confirmer une compétence ne rendrait l'expert matchable qu'au prochain
recalcul — à un moment quelconque, et invisible.

### Le critère du §24, et la seule façon de le tenir

> « Le parsing ne transforme jamais une donnée incertaine en donnée validée
> sans traçabilité. »

Il se tient par **une** décision de conception : rien de ce que l'IA produit
n'entre dans les modèles du profil. Tout atterrit dans
`opex.expert.cv.proposal`, qui porte pour chaque élément sa valeur, sa
confiance, et **le passage exact du CV d'où elle vient**. La promotion est un
geste humain, et elle laisse `confirmed_by` et `confirmed_on`.

`test_the_parsing_never_produces_a_validated_datum` le vérifie sous trois
angles, et le troisième est celui qui compte : `opex.expert.skill` n'a pas
grossi d'une ligne. Les deux premiers — `source='ia'`, `confiance='propose'` —
décriraient encore un module qui écrirait aussi ailleurs.

**Régression volontaire** : confirmer d'office les propositions de confiance
≥ 0.9, le raccourci qu'on prendrait « parce que le modèle est sûr ». Deux
rouges, et le second est le plus instructif —
`AssertionError: res.users() != res.users(4732,)` : une proposition née
confirmée n'a **aucun `confirmed_by`**. La donnée serait validée sans que
personne l'ait validée, ce qui est mot pour mot ce que le §24 interdit.

### L'analyse est asynchrone, et `analyse` n'est pas un workflow

Un parsing prend dix à trente secondes. Une route qui attend cela est
inutilisable : le navigateur tourne, l'utilisateur recharge, et le second appel
repart pour trente secondes. Le dépôt crée l'enregistrement et rend la main ;
un `ir.cron` traite la file, cinq CV par passage, **chacun dans son propre
savepoint** — règle 10 appliquée à une file, sans quoi un document illisible
empêcherait les quatre autres d'être lus.

À analyser → en cours → analysé / échoué : aucun acteur, aucune condition,
aucun chemin de refus, rien à notifier. C'est la même ligne de partage que
l'incident du §26 (E8) et que `confiance` ci-dessous. Un compteur de file
d'attente n'est pas un processus métier.

⚠ La file **abandonne après trois tentatives**. Sans cette borne, elle
boucle sur le même document à chaque passage du cron, et chaque tour est
facturé. `action_reanalyse()` remet le compteur à zéro — c'est ce qui débloque
un CV après une correction de prompt ou un déblocage de quota.

### Trois arbitrages rendus pendant l'IA-1

**① Le défaut des lignes existantes est `expert` / `expert`, pas `ia`.**
À l'ajout d'une colonne, Odoo applique le défaut à toutes les lignes déjà en
base. Or celles-ci ont été saisies par l'expert depuis son portail à
l'Extension 3 : un défaut à « proposé par l'IA » aurait discrédité d'un coup
tout le capital déjà déclaré — et l'aurait retiré du matching par la même
occasion.

**② `confiance` est un compteur, pas un processus.** Proposé → confirmé →
vérifié est une progression, et la question méritait d'être posée. Trois
positions, aucun chemin de refus, aucune condition, aucun acteur qui change :
c'est la ligne de partage que le CLAUDE.md du moteur pose pour
`roadmap.phase`, et que l'Extension 8 a déjà appliquée à l'incident du §26.
`test_the_confidence_is_a_counter_not_a_process` verrouille le critère.

**③ Confirmer une proposition ne crée aucune compétence qualifiée.** C'est le
point qui surprend à l'écran, et il est voulu : la promotion supposerait un
rapprochement taxonomique, et un bouton qui écrirait un libellé libre dans
`opex.expert.skill` créerait exactement le référentiel parallèle que le §8
interdit. La dette D1 montre déjà ce que coûte de comparer du texte libre. Le
rapprochement est l'affaire de l'IA-2, et il a son propre écran.
`test_a_proposal_is_never_a_qualified_skill` verrouille le critère.

### Le schéma est fermé des deux côtés

Les neuf destinations du §6 sont nommées **une fois**, dans `DESTINATIONS` :
le schéma de validation, la `Selection` du modèle de proposition et l'écran y
lisent tous les trois. Trois listes divergeraient au premier ajout.

À l'intérieur d'un élément, seules `valeur`, `confidence` et `source_quote`
sont lues. « Un champ inattendu est ignoré, pas écrit » est plus fort qu'il n'y
paraît : sans cela, un modèle qui ajoute `salaire_souhaite` ou `note_interne`
verrait sa trouvaille traverser jusqu'à un écran, et personne ne saurait d'où
elle vient. **Le JSON brut, lui, garde tout** — c'est ce qui rend une
extraction ratée compréhensible sans rappeler le fournisseur, et c'est le §17.

⚠ La validation **ne lève jamais**. Une réponse mal formée donne zéro
proposition et un CV analysé, ce qui est une information, pas une panne.

### Deux pièges d'Odoo 19 rencontrés

- **`groups_id` est devenu `group_ids` sur `ir.ui.view`.** Le message est net
  — « Invalid field 'groups_id' in 'ir.ui.view' » — mais il remonte sous une
  `ParseError` qui affiche l'enregistrement entier.
- **Une vue héritée ne peut pas porter ses propres groupes** :
  « Inherited view cannot have 'groups' defined on the record. » C'est
  cohérent — une vue héritée n'est pas un écran, c'est une greffe. La
  restriction vit dans l'arbre, sur le bouton.

### Deux limites d'environnement — à annoncer

**Le back-office n'est pas vérifiable dans le navigateur piloté.**
L'extension d'automatisation casse le client web d'Odoo
(`window.chrome.runtime.sendMessage is not a function`) : une page **inchangée
depuis l'Extension 1** rend aussi blanc. Ce n'est pas propre à cette
extension. Les pages portail, rendues côté serveur, restent vérifiables — ce
sont elles qui ont servi aux Extensions 11 et 12.

**Le JSON du protocole est simulé, et il faut le dire.** Le projet Google
associé à la clé est toujours refusé en génération. Le CV réel a bien été
déposé — 152 208 octets en base64 — et l'appel réel bien tenté : le journal
porte `cv_parsing / http_error / 500 ms`, le CV est passé en « Analyse
impossible », et rien n'a été écrit. C'est le comportement attendu face à une
panne de fournisseur, et c'est la seule partie de la chaîne que la clé bloque.
Le reste — validation, écriture, traçabilité — est déroulé sur le vrai
document dans le protocole.

---

## Extension IA-2 — Taxonomie et normalisation ✅ FAITE

> **Livrée le 02/09/2026**, complétée le 04/09/2026 par la taxonomie du §8
> puis par la promotion — **51 tests pour l'IA-2, 0 échec**. Trois protocoles
> manuels : `docs/protocole_test_extension_ia2.md` (le rapprochement),
> `docs/protocole_test_extension_ia2_taxonomie.md` (la hiérarchie, le socle,
> les sept attributs) et `docs/protocole_test_promotion.md` (la chaîne
> bouclée, dont la vérification sur `expert_skill_competence_ids`).

### Pourquoi il n'y a pas de modèle `skill.catalog`

Le périmètre demandait « la taxonomie canonique — domaine, famille,
compétence, avec ses synonymes ». Trois des quatre existaient déjà, et le
quatrième — la compétence — **dans un autre module**.

Créer ici un second modèle de compétences canoniques aurait produit ce que le
§8 interdit et ce que la dette D1 documente : deux catalogues qui ne se
croisent que par coïncidence de libellé. Le Smart Matching lit
`res.partner.expert_skill_competence_ids`, qui pointe sur le référentiel du
Module 2 ; un catalogue parallèle l'aurait rendu **faux sans que rien ne le
signale**.

Ce qui est livré est donc bien la taxonomie du §8 — les deux niveaux
supérieurs sont neufs, la compétence est celle qui existait, et elle reçoit
son rangement par `_inherit` :

```
opex.skill.domain  →  opex.skill.family  →  opex.innovation.competence
                                              + opex.competence.synonyme
```

Pas une ligne du Module 2 ne change. `test_no_parallel_competence_model_was_created`
verrouille le critère.

⚠ `opex.innovation.competence` porte déjà un `domaine` en **texte libre** —
le motif exact de la dette D1. Il est conservé pour ne rien casser et devient
**alimenté** par la hiérarchie plutôt que saisi : sans cette recopie, l'écran
du Module 2 afficherait une compétence sans domaine et quelqu'un le
remplirait à la main.

### Le socle semé, et ce qu'il a cassé

Six domaines, seize familles, cinquante-quatre compétences, cinquante-sept
synonymes, tirés des types de mission de l'Extension 1. Un catalogue vide
enverrait tout en arbitrage dès le premier CV, et la file cesserait d'être
regardée.

**Deux tests de l'IA-2 ont rougi le jour du semis**, et c'était le bon genre
de rouge : ils créaient un synonyme « Audit SI » que le socle occupe
désormais, et la contrainte d'unicité sur la forme normalisée faisait échouer
leur *fixture*. C'est la règle 7 prise du bon côté — un test ne suppose jamais
qu'il est seul en base, et il choisit ses libellés en conséquence.

⚠ Le socle ne doit introduire **aucune collision de normalisation** : deux
libellés qui se normalisent pareil rendent le rapprochement ambigu, et
`resolve_label()` refuse alors de choisir. Un libellé pourtant présent au
catalogue partirait en arbitrage.
`test_the_seeded_catalogue_has_no_normalisation_collision` le garde.

### Les sept attributs du §8, et le point subtil du §9

`opex.expert.skill` en portait cinq. Les deux qui manquaient :

- **`derniere_pratique`** — un niveau Expert pratiqué il y a huit ans n'est
  pas un niveau Expert aujourd'hui. Colonne réelle, donc filtrable ; la
  lecture (`fraicheur`) est calculée et **non stockée**, parce qu'elle dépend
  de la date du jour et se figerait au dernier recalcul (règle 16) ;
- **la preuve** — `preuve_experience_ids` et `preuve_certification_ids`,
  rattachées aux pièces que le profil porte déjà. L'expert ne les redécrit
  pas.

C'est la preuve qui rend le §9 **opérant**. « Un niveau 4 auto-déclaré et un
niveau 4 confirmé par trois expériences et une certification ne valent pas la
même chose » : sans pièces rattachées, cette phrase reste une intention ; avec
elles, elle se compte. Et la conséquence pratique est le filtre `is_confirmed`
posé à l'IA-1 — un niveau Expert jamais confirmé ne fait matcher personne.

### La régression volontaire

Un raccourci dans `resolve_skills()` : créer la compétence au catalogue quand
la confiance de l'IA dépasse 95 %. **Trois rouges**, sous trois angles — le
comportement, le source, et le compte (`60 != 59`).

⚠ Le premier passage n'en a fait rougir que deux, et le manquant était le
test neuf : il passait `'confidence'` là où `_suggest()` lit `'confiance'`.
La clé anglaise valant zéro, le raccourci ne se déclenchait pas et le test ne
mesurait que le chemin sans suggestion. C'est la règle 20 sous un autre jour :
avant de croire un test de garde, se demander par quel chemin le défaut y
arriverait.

### La promotion — le maillon qui ferme la chaîne

```
CV déposé -> proposition extraite -> confirmée par l'expert
          -> compétence qualifiée -> visible par le matching
```

Les quatre premières flèches existaient depuis l'IA-1 et l'IA-2. La dernière
les relie, et c'est la seule qui écrive dans le capital de l'expert.

**`action_promote()` passe par `resolve_skills()`, jamais par un `create()`
sur le référentiel.** Un bouton qui écrirait un libellé libre au catalogue
créerait le catalogue parallèle que le §8 interdit. Corollaire : **une
proposition non rapprochée ne crée rien** — elle part en file d'arbitrage, et
c'est le cas le plus fréquent au début de la vie du catalogue.

**Les trois axes du §9 sont posés explicitement** : `source='cv'`,
`confiance='expert'`, et **la citation du CV en preuve**
(`preuve_citation` + `preuve_cv_id`). C'est ce triplet qui rend le §9
vérifiable sur une ligne issue d'un CV : `source` seul dirait la provenance
sans permettre de remonter au passage exact.

⚠ **Le niveau n'est pas déduit du CV.** Un modèle qui lit « dix ans d'audit »
propose volontiers « Expert », et personne ne l'a validé. Le déduire
refusionnerait les deux axes par la porte de derrière.

⚠⚠ **Une promotion ne rétrograde jamais une ligne vérifiée.** Une compétence
en `confiance='opex'` que la promotion ramènerait à `'expert'` perdrait le
travail de vérification **sans un mot**, et le §9 se dégraderait par le chemin
censé l'alimenter. C'est le défaut le plus discret de l'extension : il ne
casse rien, il abaisse une qualité. Sur une ligne existante, la promotion
**ajoute la preuve** et ne touche à rien d'autre.

**Régression volontaire** : `confiance='ia'` au lieu de `'expert'`. Deux
rouges, et le second est celui qui compte —

```
AssertionError: ... not found in opex.innovation.competence() :
La compétence promue n'atteint pas le champ que le Smart Matching
interroge : la chaîne n'est pas bouclée.
```

**La ligne était pourtant bien créée au profil.** Rien n'aurait semblé cassé à
l'écran ; elle était simplement invisible du matching, parce que
`expert_skill_competence_ids` filtre sur `is_confirmed`. C'est le genre de
défaut qui ne se voit pas en démonstration et qui se paie en production : des
experts qualifiés qui ne sortent jamais dans les propositions, sans une erreur
nulle part.

### Les deux décisions de l'auteur, et ce qu'elles impliquent

**Les synonymes sont un modèle séparé du Module 3**, `opex.competence.synonyme`,
qui référence `opex.innovation.competence`. Le Module 2 reste gelé. C'est moins
naturel qu'un champ sur la compétence — un synonyme est une propriété, pas un
objet — et c'est assumé : rouvrir un module présenté coûte plus que cette
indirection.

**L'arbitrage enrichit le catalogue du Module 2**, parce que le référentiel
doit rester unique — deux catalogues seraient la dette D1 en pire. Trois
garde-fous encadrent ce flux, pour qu'il soit décidé et non découvert :

- il passe par **une méthode nommée**, `action_add_to_catalogue`, et un test
  lit le source du module pour refuser tout autre `create()` sur
  `opex.innovation.competence` ;
- il **journalise** qui a décidé quoi, quand, depuis quel profil et quel
  document — la ligne d'arbitrage est à la fois la file et le journal ;
- il est **réservé au gestionnaire**, par `_is_missions_staff()` appelé dans le
  modèle et pas seulement sur l'écran.

### Le rapprochement en deux temps

1. **Correspondance exacte, sans appel IA** : forme normalisée contre le
   référentiel, puis contre la table de synonymes. Gratuite, et elle traite la
   majorité des libellés d'un CV.
2. **Proposition de l'IA avec sa confiance**, seulement pour ce que l'étape 1
   n'a pas su rattacher. Le code rendu est **vérifié contre le catalogue** : un
   modèle invente volontiers un code plausible.

Tout ce qui n'est pas reconnu à l'étape 1 part en file d'arbitrage, **y compris
ce que l'IA a proposé**. Une proposition à 95 % reste une proposition.

Second effet de l'étape 1, et le plus important : **le module reste utile sans
clé**. Un cluster qui n'active pas l'assistance garde le rapprochement exact et
la file. C'est la règle 1 du service vue depuis le métier.

### Le défaut trouvé en écrivant les tests

Deux tests ont rougi sur un `615 != 636` : la résolution renvoyait **une autre
compétence** que celle attendue. Le catalogue contenait « Audit des systemes
d'information » et « Audit des systèmes d'information » — deux entrées que la
normalisation rend identiques. La boucle renvoyait la première rencontrée, donc
l'une ou l'autre selon l'ordre de recherche.

L'expert aurait été qualifié sur une des deux au hasard, et le matching aurait
comparé à celle que la mission avait choisie. Deux fois sur trois, personne ne
se croise — sans qu'aucune erreur ne soit levée. **C'est le motif exact de la
dette D1**, sur un référentiel qu'on ne peut pas contraindre puisque le
Module 2 est gelé.

Correction : une correspondance ambiguë **refuse de choisir** et part en
arbitrage, où le gestionnaire voit les deux entrées et nettoie son catalogue.
`test_an_ambiguous_catalogue_refuses_to_choose` le garde.

### La normalisation, et la tentation qu'elle refuse

Minuscules, accents retirés, ponctuation réduite à un séparateur. Elle ne
retire **pas** les espaces : « ISO 27001 » et « ISO27001 » restent deux clés
distinctes, et c'est un synonyme qui les réunit.

Tout coller les ferait correspondre — ce qu'on veut — mais ferait aussi
correspondre « audit si » et « auditsi », donc n'importe quelle suite de mots
avec n'importe quelle autre à un espace près. Une correspondance approximative
se trompe en silence ; un synonyme manquant envoie le libellé en arbitrage, où
quelqu'un le voit.

---

# État d'avancement — au 04/09/2026

`opex_intervenants` **19.0.21.0.0** et `opex_ai_core` **19.0.1.0.0** ·
**515 tests, 0 échec** · installation propre, zéro avertissement au
rechargement. **Les douze extensions sont livrées**, plus les Extensions IA-0,
IA-1 et IA-2.

```
.\venv\Scripts\python.exe .\odoo\odoo-bin -c odoo.conf -d opex_mis_e1 ^
    -u opex_ai_core,opex_intervenants --test-enable ^
    --http-port=8072 --stop-after-init --limit-time-real=0
```

⚠ **`opex_intervenants` ne dépend ni d'`opex_ai_core`, ni de `sale`, ni de
`project`** — et les trois pour la même raison, qui est une décision
d'architecture et pas un oubli.

Ces modules ne sont pas disponibles sur l'instance de déploiement. Les
déclarer rendait `opex_intervenants` **non installable** : Odoo refuse un
module dont une dépendance est introuvable, et le refus est total — ni
portail, ni matching, ni workflows, pour trois fonctionnalités de bout de
chaîne.

Ils sont donc résolus au moment de l'appel, par deux ponts de même forme :
`opex.ai.bridge` (IA-1) et `opex.optional.backend`. C'est la règle 1 du
service portée d'un cran plus haut : si une clé absente ne doit bloquer aucun
parcours, un module absent non plus.

Corollaire, et c'est la discipline qui rend les ponts utiles : **aucun
`self.env['opex.ai.service']`, `['sale.order']` ou `['project.project']`
ailleurs que dans le pont correspondant.** Deux tests de source le
verrouillent. Sans cela, on découvrirait les endroits non protégés un par un,
en production — et les tests de dégradation resteraient verts pendant ce
temps, puisqu'ils simulent l'absence au niveau du pont.

Ce que le portail perd sans `sale` et `project` :
`opex_intervenants/docs/fonctions_desactivees.md`. La marche à suivre pour
rebrancher : la docstring de `models/optional_backends.py`, et

```
grep -rn "REBRANCHEMENT" models/ views/ data/ tests/
```

⚠⚠ **Le module est propre, mais il ne s'installera pas seul pour autant.** La
dépendance revient par la chaîne : `opex_innovation` déclare `project`, et
`opex_membership` déclare `sale`. Le blocage restant est **entièrement en
amont**, et il est du même genre — 2 champs `Many2one` et 2 appels côté
Module 2, 1 modèle hérité (`account.move`), 1 champ et 2 appels côté
Module 1. Il n'a pas été engagé : ces deux modules sont présentés et gelés,
les rouvrir est une décision, pas une conséquence.

Mesuré : sur ses **741 champs**, `opex_intervenants` n'en déclare plus **aucun**
dont le comodèle soit dans `sale.`, `project.`, `product.` ou `account.`.

Le portail compte désormais **six modules** : le moteur `opex_workflow`, les
trois domaines métier, `opex_crowdfunding` isolé par construction, et le
service `opex_ai_core`.

Les cinq modules du portail passent ensemble : **1048 tests, 0 échec**
(789 sur `opex_mis_e1` pour `opex_workflow`, `opex_membership`,
`opex_innovation` et `opex_intervenants` ; 259 sur `opex_cf_e1_test` pour
`opex_crowdfunding`).

**Le jalon P0 du §20 est atteint** : une mission naît d'un besoin client et
aboutit à un intervenant sélectionné avec son contrat généré, son ordre de
mission, son projet d'exécution et ses tâches.

| Extension | État | Preuve |
|---|---|---|
| 1 — Socle et les deux workflows | ✅ | `data/mission_request_workflow.xml` (14 étapes, 32 transitions), `data/mission_application_workflow.xml` (10 étapes, 20 transitions) |
| 2 — La demande client | ✅ | `controllers/portal.py`, `views/portal_templates.xml`, `tests/test_mission_portal.py` (25 tests HTTP) |
| 3 — Le profil expert enrichi | ✅ | `models/expert_capital.py` (5 modèles), `models/expert_profile.py` (`_inherit`), `models/res_partner.py` (8 cibles de matching), `controllers/expertise.py` |
| 4 — Smart Matching | ✅ | `data/matching_criteria.xml` (7 critères + 2 profils), `models/matching.py`, `controllers/staff.py`, `tests/test_matching.py` |
| 5 — Appel portail et candidature Lean | ✅ | `models/mission_public.py` (dictionnaires fermés), `controllers/public.py`, `controllers/candidature.py`, `tests/test_public_portal.py` |
| 6 — Pool unique et comparaison | ✅ | `models/mission_application_pool.py`, `views/application_pool_views.xml` (Kanban non glissable), écran `/staff/missions/<id>/pool`, `tests/test_pool.py` |
| 7 — Sélection, contrat, ordre de mission | ✅ | `data/mission_contract_workflow.xml` (6 étapes, 8 transitions), `data/mission_contracting_actions.xml` (8 actions sur 3 transitions), `models/mission_assignment.py`, `models/mission_contract.py`, `models/mission_operational.py`, `report/mission_contract_reports.xml`, `tests/test_contracting.py` (28 tests) |
| 8 — Exécution de la mission | ✅ | `data/mission_deliverable_workflow.xml` (5 étapes, 5 transitions), `models/mission_deliverable.py` (+ versions immuables), `models/mission_execution.py` (avancement, incidents), `models/mission_execution_request.py` (barre du §40), `tests/test_execution.py` (34 tests) |
| 9 — Service fait et facturation | ✅ | `data/service_acceptance_workflow.xml` (4 étapes, 4 transitions), `data/mission_invoicing_data.xml`, `models/service_acceptance.py`, `models/mission_invoicing.py`, `views/service_acceptance_views.xml`, `tests/test_service_acceptance.py` (21 tests) |
| 10 — Évaluations et réputation | ✅ | `data/mission_evaluation_workflow.xml` (4 étapes, 4 transitions), `models/mission_evaluation.py`, `models/expert_reputation.py` (§32 et §33), `views/mission_evaluation_views.xml`, `tests/test_evaluation.py` (26 tests) |
| 11 — Tableaux de bord et notifications | ✅ | `models/mission_dashboard.py` (les 4 espaces + §43), `models/res_partner_bell.py` (cloche coopérative), `models/mission_notifications.py`, `data/mission_notifications.xml` (16 actions sur 10 transitions), `controllers/dashboard.py`, `views/dashboard_templates.xml`, `tests/test_dashboard.py` (25 tests) |
| 12 — Portail public et intégration finale | ✅ | `models/portal_integration.py` (catalogue filtré, accueil, KPI, liste du §21), `controllers/integration.py`, `views/integration_templates.xml`, `tests/test_integration.py` (17 tests) |
| IA-0 — Le service d'assistance | ✅ | `opex_ai_core` entier : `models/ai_service.py` (les 4 règles), `models/ai_prompt.py` (`render()` par expression régulière), `models/ai_call_log.py`, `tests/` (32 tests) |
| IA-1 — Trois axes et parsing du CV | ✅ | `models/ai_bridge.py` (le pont sans dépendance), `models/expert_cv_source.py` (2 modèles, schéma fermé), `models/expert_skill_axes.py` (les 3 axes du §9), `data/ir_cron_cv_parsing.xml`, `opex_ai_core/data/prompts_cv.xml`, `tests/test_cv_parsing.py` (18 tests) + `tests/test_cv_axes.py` (6 tests) |
| IA-3 — Contrôle qualité assisté | ✅ | `models/expert_qualification_review.py` (les 7 contrôles, déterministe d'abord), `data/expert_qualification_workflow.xml` (10 étapes, 12 transitions, le rôle `qualification_control`), `opex_ai_core/data/prompts_qualification.xml`, `views/expert_qualification_views.xml`, `tests/test_qualification_review.py` (23 tests) |
| D1 — Référentiel de certifications | ✅ | `models/certification_catalog.py` (`_inherit` sur le référentiel du Module 1 + `porte`), `models/certification_resolution.py` (2 temps + file), `models/certification_axes.py` (les 3 axes + éligibilité), `models/mission_certification.py` (exigence conjonctive), `models/res_partner_certification.py` (la cible de matching), `models/matching.py` (`_matching_configuration_errors`), `data/certification_catalog.xml` (16 certifications, 27 synonymes), `tests/test_certification_d1.py` (24 tests) |
| IA-2 — Taxonomie et normalisation | ✅ | `models/skill_catalog.py` (domaine, famille, `_inherit` sur la compétence du Module 2), `data/skill_catalog.xml` (6 domaines, 16 familles, 54 compétences, 57 synonymes), `models/competence_synonyme.py`, `models/competence_resolution.py` (2 temps), `models/competence_arbitrage.py` (file + journal, seul point d'écriture au Module 2), `models/expert_skill_axes.py` (les 7 attributs du §8), `action_promote()` dans `models/expert_cv_source.py` (le maillon final), `tests/test_competence_taxonomy.py` (20) + `tests/test_skill_catalog.py` (18) + `tests/test_cv_promotion.py` (13) |
| Retrait de `sale`, `project` et `opex_ai_core` du manifeste | ✅ | `models/optional_backends.py` (le second pont), les blocs `REBRANCHEMENT` dans 4 modèles et 2 vues, `tests/test_optional_backends.py` (9 tests), `docs/fonctions_desactivees.md`, `docs/protocole_test_sans_sale_project.md` |

**Les deux graphes ont été déroulés de bout en bout par le chemin réel du
back-office** — bouton « Action » → wizard → confirmation, sous six identités
distinctes — et pas seulement par l'API du modèle. Les quatre boucles sont
franchies :

```
Mission     : draft → qualified → draft → qualified → sourcing → open
              → selection → awarded → contracting → in_progress → delivered
              → in_progress → delivered → accepted → closed
Candidature : invited → declined → viewed → interested → applied → screened
              → shortlisted → screened → shortlisted → selected
```

## Décisions prises pendant l'Extension 1

- **`initiator_role_id` vide sur les deux définitions** (arbitrage Q2), acteur
  posé dans `create()` depuis `client_id` / `partner_id`. Vérifié par
  régression volontaire : avec le champ renseigné, le responsable qui invite un
  expert reçoit bien le rôle `intervenant` en accès `full` sur la candidature
  d'un autre, et deux tests rougissent.
- **`declined` réversible** (arbitrage Q1) : transition `reconsider`, `declined`
  n'est pas `is_end`.
- **`invited` est l'entrée des deux canaux** (arbitrage Q3). La ligne
  d'historique `invited` d'une candidature portail est l'instant de création ;
  `source` la lève.
- **Aucun référentiel de compétences neuf** : `skill_ids` pointe vers
  `opex.innovation.competence`.
- **Deux groupes seulement**, plus `opex_membership.group_secretariat` réutilisé.
- **Aucune action sur les transitions.** Elles viendront avec les objets
  qu'elles manipulent — matching (E4), contrat (E7), notifications (E11) — et
  se rattacheront par `<function name="write">`.

## Trois choses apprises, remontées dans les règles transversales

Elles ne sont pas répétées ici : une leçon écrite à deux endroits finit par
diverger, et c'est la copie périmée qu'on lit. Voir plus haut —

- **règle 7**, dernier point : `exists()` n'applique aucune `ir.rule` ;
- **règle 8**, dernier point : une vue `search` refuse `expand` sur son `<group>` ;
- **règle 9** entière : une méthode `compute` ne mélange pas stocké et non stocké.

Les trois ont coûté un chargement raté ou un test vert menteur.

Deux autres se sont ajoutées à l'Extension 7 :

- **règle 14** : un sous-workflow est « terminé » dès la **première** étape
  finale atteinte — donc une étape de refus marquée `is_end` retourne la
  condition qui l'attend ;
- **règle 15** : un test qui inspecte du source examine du **code**, pas de la
  prose.

Trois autres à l'Extension 8 :

- **règle 16** : un champ calculé non stocké n'est pas cherchable, et une vue
  `search` qui le filtre empêche le module de charger ;
- **règle 17** : un test de nommage porte sur le **type**, pas seulement sur le
  nom — et quand il rougit sur du code légitime, on réécrit le critère, on ne
  retire pas le mot de la liste ;
- **règle 18** : renommer un champ cité par une vue héritée casse le
  rechargement **sur la vue mère**, et la trace ne nomme pas la coupable.

## Deux manques déclarés — les deux refermés par l'Extension 7

Ils sont conservés ici parce que le **mécanisme** vaut d'être retenu : les deux
avaient un test qui affirmait le manque et annonçait qu'il rougirait. Les deux
ont rougi le jour dit, et c'est ce qu'on leur demandait — signaler que l'état
du module a changé, plutôt que laisser une affirmation périmée passer au vert.

- ~~**Le rôle `intervenant` n'a aucun porteur sur l'instance de la mission.**~~
  Posé par `_grant_intervenant_actor_on_mission()` à la sélection, en accès
  `limited`. `test_the_retained_expert_is_not_yet_actor_of_the_mission` a été
  retourné en `test_the_retained_expert_becomes_actor_of_the_mission`.
- ~~**La règle 5 du §39 est déclarée et rattachée à rien.**~~ Rattachée à
  `mtr_start_mission` par `<function name="write">`, la définition
  `mission_contract` existant désormais.
- ~~**La règle 6 du §39 et le dépôt des livrables restent en attente.**~~ Les
  deux sont refermées : la condition de dépôt à l'Extension 8, la règle 6 à
  l'Extension 9 — et celle-ci sur **deux** transitions. Les trois règles
  différées de l'Extension 1 ont donc toutes trouvé leur objet, et les trois
  ont fait rougir le test qui les surveillait le jour dit.

  Ce qui reste, et qui vaut d'être gardé : elles sont écrites avec un défaut à
  1 (`field('x', 1) == 0`) pour être **fermées** tant que le champ n'existe
  pas — sans ce défaut, `False == 0` les ferait passer.
  `test_the_remaining_deferred_rule_still_uses_the_safe_default` interdit de
  retirer l'idiome maintenant qu'il ne sert plus, parce que c'est le modèle de
  la prochaine règle écrite ainsi.

---

## Extension IA-3 — Contrôle qualité assisté ✅ FAITE

> **Livrée le 05/09/2026** — 515 tests, 0 échec. Protocole manuel :
> `opex_intervenants/docs/protocole_test_extension_ia3.md`, qui porte aussi
> **la liste de ce que l'agent ne sait pas faire**.
>
> **Douzième définition du projet.** `opex.expert.qualification.review` porte
> le mixin et aucun champ `state`.
>
> ⚠ **La spécification Smart Expert Onboarding n'est toujours pas dans le
> dépôt.** Les §11 et §12 n'ont pas pu être relus ; le périmètre a été suivi
> tel que donné dans le prompt.

### Le principe, et comment il est tenu

    « La décision d'activation reste gouvernée par les règles OPEX. » (§12)

L'agent **prépare**, un humain tranche. Tenu à **trois** niveaux, et le
troisième est celui auquel on ne pense pas :

1. `action_run()` n'appelle jamais `do_transition()` — un test lit le source,
   docstrings retirées ;
2. **aucune transition du §11 ne porte de condition.** Une règle qui lirait
   `blocking_count` rendrait l'activation dépendante d'un avis sans qu'une
   ligne de Python ne l'écrive nulle part. C'est la forme que prendrait le
   défaut si quelqu'un voulait gagner du temps ;
3. **une anomalie d'IA ne peut pas être bloquante.** `_validate_ai_payload()`
   dégrade toute gravité `blocking` rendue par le modèle. `blocking` est ce
   que lit un contrôleur pressé ; laisser l'IA le poser reviendrait à lui
   faire prendre la décision.

### L'ordre des deux moitiés

Le **déterministe** tourne d'abord, en entier : champs manquants, dates
incohérentes, certifications expirées, doublons par email et téléphone (§16).
Il couvre quatre des sept contrôles en entier et la moitié vérifiable des
trois autres.

L'**IA** ne vient qu'ensuite, et n'instruit que trois contrôles — cohérence de
fond, compétences non justifiées, points à clarifier. Ce sont des jugements ;
les quatre autres se vérifient, et un `if` y est plus fiable.

Conséquence : **sans clé, le contrôle fonctionne.** Il perd la moitié qui
juge, il garde celle qui vérifie.

### Pourquoi la machine à états n'est pas sur le profil expert

Deux raisons mesurées, aucune n'est une préférence :

1. `opex.workflow.mixin.workflow_instance_id` est un **Many2one**, et
   `start_workflow()` refuse plutôt qu'il ne remplace. Le profil est déjà
   piloté par `profile_request` (Module 2) ;
2. étendre la définition du Module 2 ferait rougir un module **gelé** :
   `opex_innovation/tests/test_profiles.py` y verrouille `len(stage_ids) == 6`
   et `len(transition_ids) == 6`.

Le dossier de qualification porte donc le cycle, et c'est cohérent : ACTIVE,
SUSPENDED et ARCHIVED décrivent la vie de l'intervenant **après** la demande,
ce dont `profile_request` n'a aucune notion. La table de correspondance est
dans le fichier de données.

⚠ **`active` n'est pas une étape finale.** Seules `rejected` et `archived` le
sont. Une qualification close en `active` ne pourrait plus être suspendue —
règle 14.

### La régression volontaire, et le premier essai qui n'a rien prouvé

Le contrôle a été modifié pour poser le dossier en `qualified` à la fin de
`_run_once()`.

**Le premier essai est resté vert**, et c'est le plus instructif. La casse
était conditionnée à `if not anomalies:` et le profil du test n'est pas sans
anomalie — il n'a aucune pièce jointe, ce que `_check_conformite()` signale.
Le raccourci ne s'est jamais déclenché.

Rendue inconditionnelle :

```
FAIL: test_an_ai_advice_never_activates_a_profile
      opex.workflow.stage(434,) != opex.workflow.stage(429,) : Le contrôle a
      fait avancer le dossier : l'agent décide au lieu de préparer.
```

**Règle 20 sous un troisième jour** : avant de croire une régression
volontaire, vérifier qu'elle s'est déclenchée. Une casse qui ne s'exécute pas
ressemble exactement à un test qui protège.

### Deux gardes antérieures ont parlé

- `test_no_business_method_posts_a_notification_by_hand` (E11) a rougi sur
  l'avis. Elle demandait une justification, pas un contournement : l'avis est
  un **compte rendu posé sur le dossier**, pas une notification à un rôle —
  et il ne *peut pas* être une action `notify`, celles-ci se déclenchant sur
  une transition, ce que le contrôle ne franchit jamais. Le fichier est entré
  dans la liste nommée, avec cette raison ;
- la règle 16 a frappé de nouveau : `blocking_count` filtré dans une vue
  `search`. Ici le stockage est **légitime** — le compteur est une fonction
  pure de données stockées, rien n'y dépend de la date du jour.

### Le contrôle de date, et le chemin qu'il garde réellement

`opex.expert.experience._check_dates()` (Extension 3) refuse déjà une fin
antérieure au début : le cas **n'arrive jamais par l'écran**. La garde n'est
pas retirée — une contrainte Python ne s'applique qu'à l'ORM, et un import la
contourne. Le test l'éprouve donc **en écrivant en base**, faute de quoi il ne
mesurerait rien.

### Ce que l'agent ne sait pas faire

La liste complète est dans le protocole. Les quatre points à annoncer :

- il ne vérifie **aucune authenticité** — un justificatif joint, jamais
  authentifié ;
- il ne fait **aucun rapprochement de nom** pour les doublons : email et
  téléphone seulement. Une fausse alerte y fait **fusionner deux personnes** ;
- l'IA **n'a pas le CV** : elle juge sur ce que le parsing de l'IA-1 a déjà
  porté au profil, et ne reçoit ni email, ni téléphone, ni pièce jointe ;
- fusionner deux fiches, suspendre, archiver et arbitrer restent **entièrement
  humains**.

---

# Ordre d'implémentation

| Priorité | Extensions | Ce qu'on obtient |
|---|---|---|
| **P0 — le MVP du §20** | 1, 2, 3, 4, 5, 6, 7 | Créer une mission, matcher, publier, recevoir des candidatures des deux canaux, comparer, sélectionner |
| **P1** | 8, 9, 10 | Exécution, service fait, facturation, évaluation |
| **P2** | 11, 12 | Dashboards, portail public, intégration |

**Le jalon qui compte** : à la fin de l'Extension 7, une mission peut naître d'un
besoin client et aboutir à un intervenant sélectionné avec son contrat généré.
C'est le §20 P0 de la spécification, et c'est ce qui se démontre.

**Si le temps manque**, sacrifie dans cet ordre : 12, puis 11, puis 9. Ne
sacrifie jamais 4 (le matching explicable) ni 6 (le pool unique) — ce sont les
deux critères d'acceptation structurants du §21.

---

# Les critères d'acceptation du §21 — la liste de contrôle finale

**Les neuf sont tenus**, et chacun est prouvé par un test nommé. La liste est
aussi **calculée à l'exécution** par `acceptance_checklist()` et affichée sur
`/staff/kpi` : ce tableau-ci peut vieillir, celui-là non.

- [x] **une même mission peut activer Matching, Portail ou les deux, sans
      duplication de mission**
      → un seul modèle, un champ `sourcing_mode` dont la valeur `hybride`
      ouvre les deux canaux. Prouvé par
      `test_mission_application.py::test_both_channels_land_in_the_same_object`
      et par `test_pool.py::test_the_four_origins_land_in_the_same_object`.

- [x] **une candidature issue du matching et une candidature Web sont
      comparables dans le même écran**
      → un seul modèle, un champ `source`, l'écran
      `/staff/missions/<id>/pool`. Prouvé par
      `test_pool.py::test_the_comparison_row_has_the_same_shape_for_every_origin`
      — c'est la **comparabilité** qui est mesurée, pas seulement la
      cohabitation.

- [x] **un expert référencé ne ressaisit pas son profil permanent**
      → `_link_expert_profile()` rattache le profil du Module 2 à la création
      de la candidature. Prouvé par
      `test_mission_application.py::test_the_expert_profile_is_linked_without_being_retyped`
      et, côté écran, par
      `test_public_portal.py::test_the_lean_form_asks_nothing_permanent`.

- [x] **le responsable peut comprendre les raisons d'un score**
      → `score_detail`, alimenté par `_score_candidate()` du moteur. Prouvé
      par `test_matching.py::test_every_proposal_carries_its_explanation` et
      `::test_the_explanation_names_the_weight_of_each_criterion`.

- [x] **les critères éliminatoires sont distingués du scoring pondéré**
      → `is_eliminatoire`, évalué **avant** le score par
      `_matching_check_eliminatoires()`. Prouvé par
      `test_matching.py::test_an_eliminated_candidate_is_absent_not_badly_rated`
      et `::test_the_exclusion_is_explained` — les deux qui ont attrapé la
      régression du balayage typographique (règle 21).

- [x] **la sélection déclenche automatiquement contractualisation et
      exécution**
      → huit actions configurées sur trois transitions
      (`mission_contracting_actions.xml`). Prouvé par
      `test_contracting.py::test_the_selection_effects_are_configured_on_the_transition`,
      `::test_selecting_an_application_creates_the_assignment`,
      `::test_the_contract_and_the_order_are_generated_at_selection` et
      `::test_starting_the_mission_creates_the_project_and_its_tasks`.
      Le parcours entier est déroulé par `::test_the_full_mvp_journey`.

- [x] **les états Mission et Candidature sont indépendants**
      → deux définitions, deux modèles, aucun champ `state`. Prouvé par
      `test_mission_application.py::test_the_two_state_machines_are_independent`,
      par `test_pool.py::test_a_mission_in_selection_carries_applications_at_every_stage`
      et par
      `test_integration.py::test_the_two_state_machines_are_still_independent`,
      qui le **mesure sur un dossier** : une mission en `selection` portant
      simultanément une candidature `screened` et une `rejected`.

- [x] **données publiques et confidentielles d'une mission sont séparées**
      → `public_detail()` et `public_card()` sont des dictionnaires à clés
      fermées ; les clés réservées sont **absentes**, pas mises à `False`.
      Prouvé par
      `test_public_portal.py::test_the_public_view_returns_a_closed_dictionary`,
      `::test_a_restricted_call_leaks_neither_client_nor_budget` (régression
      volontaire de l'E5, d'où vient la règle 12) et par
      `test_integration.py::test_the_filtered_catalogue_still_hides_the_reserved_data`,
      qui vérifie que le filtrage ne rouvre pas ce que le §14 ferme.

- [x] **la clôture enrichit automatiquement l'historique et la réputation**
      → l'action `evaluation_trigger_reputation` crée un `opex.expert.rating`,
      dont `reputation_score` dépend. Prouvé par
      `test_evaluation.py::test_a_validated_evaluation_feeds_the_profile` et
      `::test_the_reputation_reaches_the_partner_for_the_matching`.

---

# Dettes explicites

À distinguer du hors-périmètre : ce sont des **faiblesses du code livré**, pas
des fonctions non écrites. Elles sont ici pour être **annoncées**, pas
découvertes.

**Une dette ouverte, D2 — connue et reportée sciemment.** D1 est refermée.

| # | Dette | Depuis | État | Coût estimé |
|---|---|---|---|---|
| **D2** | **28 gardes « personnel » rebondissent sans motif** (règle 25) | E4 à E12 | **ouverte, reportée sciemment** | ~1 h |

| # | Dette | Depuis | Refermée | Comment |
|---|---|---|---|---|
| ~~D1~~ | Le critère éliminatoire de certification comparait du **texte libre** | E4 | 04/09/2026 | Référentiel canonique des deux côtés, mode `intersect` conjonctif |

---

## D2 — Les gardes « personnel » rebondissent sans motif

**Ouverte, connue, et reportée sciemment.** Ce n'est pas un oubli : c'est un
arbitrage rendu le 05/09/2026, après le balayage complet des trois modules.

### Le compte exact

Un balayage de `redirect('/my')` dans les contrôleurs des trois modules a
trouvé **37 rebonds muets**, en trois familles :

| Famille | Nombre | État |
|---|---|---|
| `has_access` sur le parcours d'adhésion | 1 | **corrigée** le 05/09 |
| Enregistrement introuvable | 8 | **corrigées** le 05/09 |
| **Gardes « personnel »** | **28** | **ouvertes** |

Les 28, par module et par fichier :

| Module | Fichier | Nombre | Garde |
|---|---|---|---|
| `opex_membership` | `controllers/staff.py` | 9 | `_is_staff()` |
| `opex_innovation` | `controllers/staff_portal.py` | 7 | `_staff_user()` · `_profile_staff_user()` |
| `opex_innovation` | `controllers/matching_portal.py` | 2 | `_staff_user()` |
| `opex_innovation` | `controllers/dashboard.py` | 1 | `_staff_user()` |
| `opex_intervenants` | `controllers/staff.py` | 7 | `_intervenants_staff_user()` |
| `opex_intervenants` | `controllers/dashboard.py` | 1 | `_queue_staff_user()` |
| `opex_intervenants` | `controllers/integration.py` | 1 | `_kpi_staff_user()` |

**Total : 28** — `opex_membership` 9, `opex_innovation` 10,
`opex_intervenants` 9.

### Pourquoi elles attendent

Trois raisons, dans l'ordre où elles pèsent :

1. **On n'y arrive pas par hasard.** Ce sont des URL `/staff/…`. Un compte
   portail n'y atterrit que par un lien périmé partagé en interne — cas réel
   mais rare, contrairement au signet d'un candidat sur son propre dossier ;
2. **Deux des trois modules sont gelés et présentés.** Vingt-huit corrections
   dans `opex_membership` et `opex_innovation` demandent de rejouer leurs
   suites, et le gain ne le justifie pas maintenant ;
3. la correction est **mécanique** — le même helper que
   `_membership_file_not_found()`, avec un message générique.

### La correction, quand elle viendra

Un message unique et générique : « cet écran est réservé au personnel du
cluster ». Pas de détail sur le rôle manquant — inutile à qui n'est pas
concerné, et cela dirait à un portail quels rôles existent.

⚠ Ce que le report **ne** couvre pas : si l'un de ces écrans devient
accessible par un lien envoyé à un candidat — une notification, un email —, il
passe en tête. Le critère n'est pas le nombre, c'est la probabilité qu'un
non-initié y atterrisse.

---

## D1 — REFERMÉE le 04/09/2026

Conservée en entier : le **mécanisme** vaut d'être retenu, et la correction
n'est pas celle qui était planifiée.

### Ce qui a été fait

`opex.certification` du Module 1 est **étendu**, pas dupliqué — en créer un
second aurait été la dette elle-même, en pire. Un champ `porte`
(organisation / personne / les deux) permet à un référentiel unique de servir
les deux écrans sans les mélanger, ce qui était la nuance laissée ouverte
ci-dessous.

Le critère compare désormais `certification_ids` (appel) à
`expert_certification_ref_ids` (candidat), deux `Many2many` vers la même
table, en mode `intersect` **conjonctif**. Les trois défaillances tombent
ensemble.

### Ce que la planification n'avait pas prévu

**La conjonction n'était pas gratuite.** `intersect` du moteur teste
`bool(source & target)` — un **recoupement**. C'est juste pour un critère
pondéré et faux pour un éliminatoire : exiger deux normes revenait encore à
n'en exiger qu'une. Le moteur n'a pas de mode conjonctif et n'en aura pas ;
la conjonction est portée par un champ de configuration sur le critère,
`is_conjonctif`, et l'élimination appelle `_compare()` **une fois par valeur
attendue**. La comparaison reste celle du moteur.

**Le second manque, qui n'était pas dans la dette.**
`field('nom_mal_orthographie')` ne lève pas — le helper du moteur est tolérant
par conception. Le `False` traverse `_as_set()`, qui rend un ensemble vide, et
l'élimination conclut « cet appel n'exprime aucune attente » : **le critère
disparaît**. Une faute de frappe dans la configuration supprimait
silencieusement l'éliminatoire, et le vivier restait plein — le motif exact du
balayage typographique de la règle 21.

`_matching_configuration_errors()` vérifie donc, **avant** le lancement, que
les champs nommés par un critère éliminatoire existent. Le matching refuse de
tourner sinon : une liste qui contient des candidats qui auraient dû être
écartés est pire qu'une absence de liste.

⚠ Le cas voisin qu'il ne faut pas confondre : un appel qui n'exige aucune
certification n'écarte personne, et c'est juste. L'un est une expression
invalide, l'autre un dossier vide.

### Trois pièges rencontrés, tous silencieux

**`noupdate="1"` masque une modification, et deux fois dans cette
extension.** Le drapeau est porté par la ligne `ir.model.data`, pas par le
fichier : une fois posé, toute mise à jour de cet identifiant externe est
ignorée, **y compris depuis un autre module**. Les six normes du Module 1
restaient `porte = organisation`, et le critère continuait de comparer du
texte — avec tout le reste de l'extension en place. Sept tests rouges. La
parade est `<function>`, hors bloc `noupdate`.

**`is_valid` n'avait aucune `@api.depends`** (Extension 3) : Odoo ne
l'invalidait jamais à l'écriture, et une date d'expiration modifiée laissait
le champ en cache. `is_eligible` héritait de la valeur périmée. La dépendance
est redéclarée par `_inherit` ; le calcul, lui, n'est pas réécrit.

**`'!'` est unaire, et Odoo 19 normalise les booléens.**
`_search_is_eligible` recevait `operator='in'`, `value=OrderedSet([True])` —
jamais `'='`. Et `['!'] + domaine` ne nie que le premier terme. Les deux
ensemble rendaient **l'autre** ensemble : la recherche donnait « Texte libre »
là où le calcul donnait « CISA ». Ni erreur, ni ensemble vide. C'est le
corollaire de la règle 16, et c'est le test de comparaison des deux
implémentations qui l'a attrapé.

### La régression volontaire, et l'angle mort qu'elle a montré

Le mode ramené à `contains` — le raccourci exact de D1 — n'a fait rougir
**qu'un** test sur les trois défaillances. Bonne nouvelle : la protection
vient du référentiel, pas du mode. Angle mort : rien ne signalait que la
configuration avait été ramenée à l'état d'avant.
`test_the_eliminatory_criterion_compares_references_not_text` a été écrit à
cause de cette mesure, et il rougit sur `'contains' != 'intersect'`.

### Ce qui reste à faire, et qui est une file de travail

Les certifications saisies en **texte libre** avant cette extension ne sont
rapprochées par personne, et **ne comptent donc pour aucun critère**. C'est
une conséquence à annoncer, pas un défaut : un texte libre n'est comparable à
rien. Le filtre « Non rapprochées » est la file qui la vide.

### La note du §11 sur le contrôle « certifications requises »

Trois règles, posées par l'auteur, qui gouvernent ce contrôle :

1. **le référentiel canonique existe depuis D1** — il n'y a plus à en créer un ;
2. **le contrôle compare des références, jamais du texte libre** ;
3. **une certification non rapprochée n'est pas une non-conformité, c'est une
   file d'arbitrage — elle n'admet pas le candidat, elle nomme ce qu'on ne
   sait pas encore.**

Les trois sont tenues et testées.

⚠ La règle 3 avait d'abord été écrite sans sa seconde moitié, et la première
lecture qu'on en fait est fausse : « pas une non-conformité » ne veut pas dire
« donc admis ». Admettre une déclaration non rapprochée ferait franchir le
critère éliminatoire à un intitulé libre qui n'a **jamais été comparé à quoi
que ce soit** — c'est-à-dire rouvrirait la dette D1 par la porte de derrière.

Ce qui change n'est donc pas l'admission, mais le **motif** et ce qu'il
déclenche :

| Situation | Admis | Motif | Effet |
|---|---|---|---|
| détient, rapprochée | oui | — | — |
| ne détient pas | non | « il manque : … » | c'est une **réponse** |
| déclare, non rapprochée | non | « déclaration(s) non rapprochée(s), à arbitrer : … » | c'est une **question**, et elle part en file |

Une réponse se lit ; une question se traite. Les confondre faisait qu'un
responsable parcourant la liste des écartés ne pouvait pas savoir lequel des
deux il regardait — et qu'une question sans trace se reposait à chaque appel,
sur chaque candidat, sans que personne ne la voie jamais.

⚠ Une certification **périmée** et non rapprochée ne pose aucune question :
même rapprochée, elle ne compterait pas. Elle reste une non-conformité, et
n'encombre pas la file.

**Où vit la distinction.** `_matching_check_eliminatoires()` ne connaît aucune
famille de critère en particulier : elle appelle
`_matching_unresolved_declarations()`, neutre par défaut. La connaissance des
certifications vit dans `mission_certification.py`, qui la surcharge. Le
fichier du matching reste générique.

**Régression volontaire** : la distinction retirée — `en_attente = []`. Deux
rouges, et le premier dit tout :

```
FAIL: test_an_unmatched_declaration_is_not_a_missing_certification
      'Certification exigée — il manque : ISO 27001 Lead Auditor'
   == 'Certification exigée — il manque : ISO 27001 Lead Auditor'
      : « ne détient pas » et « déclare sans rapprochement » reçoivent le
        même motif : une réponse et une question sont confondues.

FAIL: test_an_unmatched_declaration_goes_to_the_arbitration_queue
      0 != 1 : la déclaration non rapprochée n'est pas partie en file.
```

---

## D1 — l'énoncé d'origine, conservé pour le mécanisme

## D1 — La certification éliminatoire compare du texte libre

**Pourquoi c'est une dette et pas un détail** : ce critère est **éliminatoire**.
Il ne fait pas perdre des points, il décide **qui entre dans le vivier**. Une
erreur de comparaison ne dégrade pas un classement — elle fait disparaître un
candidat, ou en laisse entrer un qui n'aurait pas dû.

### Le mécanisme

Des deux côtés, un champ texte : `opex.mission.request.certifications_souhaitees`
et `res.partner.expert_certification_names`. Le moteur normalise
(`_as_set()` : `str(x).strip().lower()`) puis compare en mode `contains`, dont
la règle est :

```python
ok = any(s in t or t in s for s in source for t in target)
```

**L'inclusion est testée dans les deux sens.** C'est voulu dans un sens, faux
dans l'autre.

### Trois défaillances, mesurées

**① Le trop permissif** — un expert qui déclare `ISO 27001` **passe** un critère
qui exige `ISO 27001 Lead Auditor` : `"iso 27001" in "iso 27001 lead auditor"`
est vrai. Constaté sur le jeu de démonstration de l'E4 : Amina Cherif, sans le
Lead Auditor, a été proposée.

**② Le trop restrictif, et c'est le plus grave sur un éliminatoire** — un expert
qui écrit `ISO27001` sans espace, ou `ISO 27001:2022`, ne croise plus rien.
Aucune des deux chaînes ne contient l'autre : il est **écarté du vivier** pour
une faute de frappe. Un candidat qualifié disparaît, et seule la note des
écartés le signale.

**③ Le cumul impossible** — `_as_set()` sur une chaîne ne la découpe pas : elle
donne **un seul jeton**. Un appel qui exige `ISO 27001, ISO 9001` produit donc
un unique élément `"iso 27001, iso 9001"`, et un expert n'ayant que `ISO 27001`
le satisfait par inclusion. **Exiger deux certifications revient à n'en exiger
au plus qu'une.** C'est la défaillance la moins visible des trois.

### La correction

Un **référentiel des deux côtés**, et le critère passe en `intersect` — le mode
qui compare des ensembles et non des chaînes. Les trois défaillances tombent
ensemble : plus d'inclusion partielle, plus de sensibilité à l'orthographe,
et le cumul redevient un vrai « et ».

⚠ **Le référentiel existe déjà** : `opex.certification` (Module 1,
`opex_membership/models/opex_certification.py`), six normes ISO semées dans
`data/certifications.xml`. Même raisonnement que pour
`opex.innovation.competence` — un second référentiel ne croiserait le premier
que par coïncidence de libellé.

**Une nuance à trancher avant de l'appliquer** : `opex.certification` porte
aujourd'hui des certifications **d'organisation** (« l'entreprise est ISO 9001 »)
et le §B du Module 1 s'en sert ainsi. Ici il s'agit de certifications
**de personne** (« Karim est Lead Auditor »). Le modèle est minimal — un
libellé, rien d'autre — donc il peut porter les deux ; mais les mélanger dans
une même liste déroulante mérite un accord, pas une décision de développeur.

Trois pas, dans cet ordre :

1. `opex.expert.certification.certification_id` → `opex.certification`, en
   gardant `name` pour la saisie libre pendant la transition ;
2. `opex.mission.request.certification_ids` (Many2many) à côté de
   `certifications_souhaitees` ;
3. le critère `mis_certification_audit` passe en
   `source_expression: field('certification_ids')`,
   `target_field: expert_certification_ref_ids`, `match_mode: intersect`.

Rien de tout cela ne touche `opex_workflow` : c'est une configuration et deux
champs.

### En attendant

Le critère **fonctionne** et fait ce que le §21 demande — il écarte au lieu de
mal noter, et la note des écartés dit pourquoi. Sa fragilité est de
**vocabulaire**, pas de mécanisme. Tant que le cluster saisit les intitulés de
façon homogène, il tient.

---

# Hors périmètre — assumé, à documenter

- **matching sémantique IA** (V2 du §20) — le scoring est pondéré et explicable,
  c'est ce que la spécification demande pour le MVP
- **apprentissage à partir des missions passées** (V2)
- signature électronique cryptographique — confirmation horodatée, comme sur les
  modules précédents
- data room
- intégration bancaire réelle

---

# Méthode de travail

1. **Un prompt = une extension.** Jamais deux.
2. **État des lieux écrit avant tout code.**
3. **Arrêt pour test utilisateur** après chaque extension — l'utilisateur teste
   à l'écran, pas seulement les tests automatiques.
4. **Commit seulement après validation humaine**, et `git add <chemin>` : un
   `git commit -a` ignore les fichiers non suivis.
5. **Ce fichier mis à jour** après chaque rapport.
6. **Tests dans `tests/` versionné**, dès l'Extension 1.
7. **Tests lancés avec `--http-port=8072`.**
