# Protocole de test manuel — IA-2 : taxonomie et normalisation

**§8 et §9 de la spécification Smart Expert Onboarding.**

Ce protocole vérifie la taxonomie du §8, son socle semé, le rapprochement en
deux temps, la file d'arbitrage, et les sept attributs du tableau du §8.

⚠ **La spécification `Specification_OPEX_Smart_Expert_Onboarding.md` n'est
toujours pas dans le dépôt.** Les §8 et §9 n'ont pas pu être relus ; ce qui est
livré suit les deux arbitrages rendus par l'auteur en début d'IA-2, rappelés
plus bas. Si le document les contredit quand il arrivera, le dire plutôt que
de coder autour.

---

## Avant de commencer

```
venv\Scripts\python.exe odoo\odoo-bin -c odoo.conf -d opex_mis_e1 ^
    -u opex_intervenants --http-port=8072 --limit-time-real=0
```

Le port 8072 n'est pas une préférence : voir la règle 19 du CLAUDE.md.

Un seul compte suffit pour l'essentiel : un membre de
`group_mission_manager`. Un compte intervenant sert au point 6.

---

## 1 — Le socle est là

**Missions → Configuration → Taxonomie des compétences → Domaines**

- [ ] six domaines : Audit et contrôle, Systèmes d'information, QHSE,
      Management et organisation, Finance et juridique, Ingénierie et
      industrie ;
- [ ] chacun affiche son nombre de familles et de compétences ;
- [ ] ouvrir « Systèmes d'information » : quatre familles dans l'onglet, et le
      bouton statistique compte ses compétences.

**→ Familles** — seize, groupées par domaine.

**→ Catalogue** — cinquante-quatre compétences, groupées par domaine.

- [ ] le filtre **À classer** est vide, ou ne contient que des compétences
      créées avant cette extension. C'est une file de rangement, pas une
      erreur : une compétence sans famille reste utilisable.
- [ ] le filtre **Sans synonyme** montre celles qui n'ont aucune variante
      connue. Ce sont elles qui enverront des libellés en arbitrage.

## 2 — Le premier temps du rapprochement : gratuit et déterministe

Ouvrir une compétence du catalogue, par exemple **Protection des données
personnelles**, onglet *Synonymes*.

- [ ] « RGPD » et « GDPR » y figurent, origine **Livré avec le catalogue**.

C'est tout l'enjeu de l'étape 1 : un CV écrit « RGPD », le catalogue porte
« Protection des données personnelles », et les deux se rejoignent **sans
appel**. Sans le synonyme, le libellé partirait en arbitrage alors que la
réponse est connue — la file deviendrait illisible et le gestionnaire
cesserait de la regarder.

Vérifier de même :

- [ ] **Mise en conformité ISO 27001** porte trois synonymes : « ISO 27001 »,
      « ISO27001 » et « SMSI ».

Les deux premiers sont **deux entrées distinctes**, et c'est voulu. La
normalisation ne colle pas les espaces : si elle le faisait, « audit si » et
« auditsi » correspondraient — donc n'importe quelle suite de mots avec
n'importe quelle autre à un espace près. Une correspondance approximative se
trompe en silence ; un synonyme manquant envoie en arbitrage, où quelqu'un le
voit.

## 3 — Le second temps : l'IA propose, elle n'écrit pas

**Missions → Capital des intervenants → Compétences à arbitrer**

Sans clé d'IA configurée, ou avec `opex_ai_core` non installé, le second temps
ne s'exécute pas — et c'est le point à retenir : **le module reste utile sans
clé.** L'étape 1 et la file continuent de fonctionner.

Avec une clé active, déposer un CV portant un libellé absent du catalogue
(voir le protocole IA-1), puis :

- [ ] la ligne apparaît dans la file, décision **En attente** ;
- [ ] si l'IA a proposé un rapprochement, la ligne porte la compétence
      suggérée, sa **confiance** et sa **justification** ;
- [ ] **la ligne attend quand même un humain.** Une proposition à 99 % reste
      une proposition.

⚠ Le point à montrer en soutenance : **le catalogue n'a pas grossi.** Ouvrir
le catalogue avant et après — le compte est le même. Enrichir la taxonomie est
une décision humaine ; une IA qui écrit au catalogue le fait diverger en trois
mois, et le matching devient faux sans que rien ne le signale.

## 4 — L'arbitrage enrichit la taxonomie

Sur une ligne en attente, trois issues.

**Rattacher** à une compétence existante :

- [ ] la ligne passe à **Rattachée** et porte qui a décidé, quand ;
- [ ] le libellé d'origine devient **synonyme** de la compétence choisie. Sans
      cela, la même variante d'écriture repartirait en arbitrage alors que la
      question vient d'être tranchée.

**Ajouter au catalogue** :

- [ ] renseigner d'abord **Famille de rangement**. Une compétence créée sans
      famille part dans « À classer », et cette file-là, personne ne la vide ;
- [ ] la compétence est créée, rangée dans la famille, et son domaine suit ;
- [ ] le champ texte *Domaine* hérité du Module 2 est renseigné lui aussi —
      sinon l'écran du Module 2 afficherait une compétence sans domaine et
      quelqu'un le remplirait à la main, en texte libre, ce que cette
      extension existe pour éviter ;
- [ ] le libellé d'origine devient synonyme, origine **Issu d'un arbitrage**.

**Écarter** :

- [ ] la ligne passe à **Écartée** et **reste dans la file**. Un CV contient
      des intitulés de poste et des noms d'outils ; les écarter est une
      réponse à part entière, et la trace évite de rejuger le même libellé au
      CV suivant.

Puis, avec un compte **intervenant** :

- [ ] les trois boutons sont refusés. Le contrôle est dans le **modèle**
      (`_is_missions_staff()`), pas seulement sur l'écran : il vaut aussi pour
      un script ou une requête forgée.

## 5 — Les sept attributs du §8

**Capital des intervenants → Profils experts**, ouvrir un profil, onglet
*Compétences*, ouvrir une ligne.

Les sept y sont :

| Attribut du §8 | Champ |
|---|---|
| compétence canonique | *Compétence* — vers le référentiel, jamais du texte libre |
| niveau | *Niveau* — Débutant, Intermédiaire, Confirmé, Expert |
| années | *Années de pratique* |
| dernière pratique | *Dernière pratique* |
| source | *Source* — CV analysé, déclaré, saisi par OPEX, mission réalisée |
| preuve | *Missions* et *Certifications qui l'attestent* |
| confiance | *Confiance* — proposé IA, confirmé expert, vérifié OPEX |

- [ ] renseigner *Dernière pratique* à il y a six mois : **Fraîcheur** affiche
      « Pratiquée récemment » ;
- [ ] la remettre à il y a huit ans : « Dormante ». Un niveau Expert pratiqué
      il y a huit ans n'est pas un niveau Expert aujourd'hui.

## 6 — Le point subtil du §9 : deux axes, pas un

C'est la vérification qui compte le plus, et elle se fait à l'écran.

Créer **deux** lignes de compétence sur le même profil, toutes deux au niveau
**Expert** :

| | Ligne A | Ligne B |
|---|---|---|
| Niveau | Expert | Expert |
| Source | CV analysé | Mission réalisée |
| Confiance | Proposé par l'IA | Vérifié par OPEX |
| Preuve | aucune | 3 missions + 1 certification |

- [ ] les deux affichent le même niveau ;
- [ ] *Pièces à l'appui* vaut 0 pour A et 4 pour B ;
- [ ] la case **Confirmée** est décochée sur A, cochée sur B.

Puis, et c'est la conséquence pratique :

- [ ] ouvrir la fiche **contact** de l'intervenant, champ des compétences lues
      par le matching : **seule la ligne B y figure.**

Un niveau 4 auto-déclaré et un niveau 4 confirmé par trois expériences et une
certification ne valent pas la même chose, et le matching le voit. Fusionner
les deux axes en un seul champ aurait rendu cette distinction impossible.

Enfin, faire varier l'un et vérifier que l'autre ne bouge pas :

- [ ] passer la ligne A de Débutant à Expert : la **confiance** ne change pas ;
- [ ] passer sa confiance à « Vérifié par OPEX » : le **niveau** ne change pas,
      la source non plus, et la ligne entre dans le matching.

## 7 — Le catalogue ne se dédouble pas

**Missions → Configuration → Taxonomie → Catalogue**, puis
**Innovation → Configuration → Compétences** (Module 2).

- [ ] c'est **la même liste**. Un second catalogue serait la dette D1 en pire :
      le Smart Matching lit celui du Module 2, et deux ensembles ne se
      croiseraient que par coïncidence de libellé.

---

## Les deux arbitrages de l'auteur, et ce qu'ils impliquent

Rappelés ici parce qu'ils expliquent la seule décision de conception qui
surprend.

**Les synonymes sont un modèle séparé du Module 3.** `opex.competence.synonyme`
référence `opex.innovation.competence`. Le Module 2 reste gelé.

**L'arbitrage enrichit le catalogue du Module 2**, parce que le référentiel
doit rester unique.

C'est pourquoi il n'y a **pas** de modèle `skill.catalog` portant des
compétences. La lecture littérale du périmètre aurait créé un second
référentiel canonique — celui que le §8 interdit et que la dette D1 documente.
La taxonomie livrée est bien celle du §8 :

```
opex.skill.domain  →  opex.skill.family  →  opex.innovation.competence
                                              + opex.competence.synonyme
```

Les deux niveaux supérieurs sont neufs, la compétence est celle qui existait,
et elle reçoit son rangement par `_inherit`. Pas une ligne du Module 2 ne
change. `test_no_parallel_competence_model_was_created` verrouille le critère.

---

## Les tests automatiques correspondants

`tests/test_skill_catalog.py` — 18 tests · `tests/test_competence_taxonomy.py`
— 20 tests.

| Ce qui est vérifié | Test |
|---|---|
| La hiérarchie a ses trois niveaux | `test_the_taxonomy_has_its_three_levels` |
| Aucun catalogue parallèle | `test_no_parallel_competence_model_was_created` |
| Une compétence sans famille est une file | `test_a_competence_without_a_family_is_a_queue_not_an_error` |
| Le socle couvre le cluster | `test_the_seeded_catalogue_covers_the_cluster` |
| Aucune collision de normalisation | `test_the_seeded_catalogue_has_no_normalisation_collision` |
| **Un synonyme se rapproche sans appel IA** | `test_a_seeded_synonym_resolves_without_calling_the_ai` |
| Le sigle collé se rapproche aussi | `test_an_acronym_without_a_space_still_resolves` |
| **Un libellé inconnu part en arbitrage** | `test_an_unknown_label_goes_to_arbitration` |
| **L'IA n'écrit jamais au catalogue** | `test_the_ai_never_writes_in_the_catalogue` |
| Enrichir est réservé au gestionnaire | `test_enriching_the_catalogue_is_reserved_to_the_manager` |
| La compétence ajoutée est rangée | `test_the_manager_files_the_new_competence_in_a_family` |
| Les sept attributs du §8 | `test_a_qualified_skill_carries_the_seven_attributes` |
| La preuve rend le §9 opérant | `test_the_evidence_is_what_makes_section_9_operative` |
| La fraîcheur lit la dernière pratique | `test_the_freshness_reads_the_last_practice` |
| **Niveau et confiance restent indépendants** | `test_level_and_confidence_stay_independent` |
| Un Expert non confirmé ne matche pas | `test_an_expert_level_proposed_by_the_ai_does_not_reach_the_matching` |

### La régression volontaire

Un raccourci a été introduit dans `resolve_skills()` : créer la compétence au
catalogue quand la confiance de l'IA dépasse 95 %. C'est exactement le geste
qu'on ferait « parce que le modèle est sûr ».

```
FAIL: test_an_ai_proposal_still_goes_through_the_arbitration_queue
      AssertionError: False is not true : Une proposition de l'IA contourne
      la file d'arbitrage.
FAIL: test_the_catalogue_has_a_single_write_point_in_the_module
      AssertionError: « competence_resolution.py » écrit dans le référentiel
      du Module 2 : ce flux passe par `action_add_to_catalogue`, et par lui
      seul.
FAIL: test_the_ai_never_writes_in_the_catalogue
      AssertionError: 60 != 59 : Le service IA a créé une compétence au
      catalogue.
```

Trois rouges, sous trois angles : le comportement, le source, et le compte.

⚠ **Le premier passage de cette casse n'a fait rougir que deux tests sur
trois**, et le troisième était le mien. La raison est instructive : le test
passait `'confidence'` là où `_suggest()` lit `'confiance'`. La clé anglaise
valant zéro, le raccourci ne se déclenchait pas et le test ne mesurait que le
chemin sans suggestion. Corrigé, et une assertion sur
`suggestion_confiance >= 90` interdit désormais qu'il repasse au vert sans
avoir lu la confiance.

C'est la règle 20 du CLAUDE.md sous un autre jour : avant de croire un test de
garde, se demander par quel chemin le défaut y arriverait.
