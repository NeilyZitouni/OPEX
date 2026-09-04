# Protocole de test manuel — La promotion, et la chaîne bouclée

```
CV déposé → proposition extraite → confirmée par l'expert
          → compétence qualifiée → visible par le matching
```

Les quatre premières flèches existaient. Ce protocole vérifie la dernière,
et surtout **qu'elles sont attachées**.

---

## Avant de commencer

```
venv\Scripts\python.exe odoo\odoo-bin -c odoo.conf -d opex_mis_e1 ^
    -u opex_intervenants --http-port=8072 --limit-time-real=0
```

Le port 8072 n'est pas une préférence : voir la règle 19 du CLAUDE.md.

Un compte membre de `group_mission_manager` suffit.

---

## 1 — Le point de départ : rien dans le vivier

**Missions → Capital des intervenants → Profils experts**, ouvrir un profil.

- [ ] onglet *Compétences* : noter ce qu'il contient.

Puis ouvrir la **fiche contact** du même intervenant (bouton *Intervenant* ou
menu Contacts) et repérer le champ des compétences lues par le matching.

- [ ] noter son contenu. **C'est la référence** : c'est lui qu'on regardera à
      la fin.

Si le champ n'est pas visible sur la fiche, l'ouvrir par le mode développeur
(*Voir les champs*) ou vérifier au shell :

```python
partner.expert_skill_competence_ids.mapped('name')
```

## 2 — Déposer et analyser un CV

Suivre le protocole IA-1 : bouton **Déposer un CV**, puis forcer le cron
*OPEX Intervenants : analyser les CV deposes*.

- [ ] l'état passe à **Analysé** ;
- [ ] l'onglet *Propositions* est rempli ;
- [ ] chaque ligne porte **Proposé par l'IA** et une colonne **Promotion** à
      **Non promue**.

⚠ Le bouton **Promouvoir** n'apparaît pas encore. C'est voulu : une
proposition non confirmée ne se promeut pas — le §24 ne se contourne pas par
la promotion.

## 3 — Confirmer, puis promouvoir : deux gestes

Sur une ligne de destination **Compétence**, cliquer **Confirmer**.

- [ ] la ligne passe à **Confirmé par l'expert**, avec son auteur et son
      horodatage ;
- [ ] **le bouton Promouvoir apparaît maintenant.**

Les deux gestes sont séparés, et c'est délibéré : confirmer dit « je l'ai bien
écrit dans mon CV », promouvoir dit « et cela doit compter dans le vivier ».
La première affirmation est de l'expert, la seconde engage le matching.

Cliquer **Promouvoir**.

- [ ] la colonne *Promotion* passe à **Promue au profil** ;
- [ ] le bouton **Voir la compétence** apparaît.

## 4 — Les trois axes du §9 sur la ligne créée

Cliquer **Voir la compétence** — ou
**Capital des intervenants → Compétences qualifiées**.

Sur la fiche :

- [ ] **Source** = *CV analysé* — d'où vient l'information ;
- [ ] **Confiance** = *Confirmé par l'expert* — ce qu'elle vaut ;
- [ ] **Confirmée** est cochée ;
- [ ] onglet *Preuves — §8* : le champ **Passage du CV** contient l'extrait
      exact, et **CV d'origine** nomme le document et sa version.

C'est ce triplet qui rend le §9 **vérifiable** sur une ligne issue d'un CV.
`Source = CV analysé` seul dirait la provenance sans permettre de remonter au
passage ; avec la citation, on rouvre le document et on lit.

- [ ] **Niveau** : c'est la valeur par défaut, pas une déduction du CV.

Ce point surprend et il est voulu. Un modèle qui lit « dix ans d'audit »
propose volontiers « Expert », et personne ne l'a validé. Le §9 sépare le
niveau métier de ce que vaut l'information ; déduire le niveau du CV les
refusionnerait par la porte de derrière. L'expert ajuste.

## 5 — **LA VÉRIFICATION QUI COMPTE** : le matching voit-il la compétence ?

C'est le seul point qui prouve que la chaîne est bouclée. Les précédents
vérifient un maillon ; celui-ci vérifie qu'ils sont attachés.

Rouvrir la **fiche contact** de l'intervenant, champ
`expert_skill_competence_ids`.

- [ ] **la compétence promue y figure**, alors qu'elle n'y était pas au
      point 1.

Au shell, si le champ n'est pas affiché :

```python
partner = env['res.partner'].browse(<id>)
partner.expert_skill_competence_ids.mapped('name')
```

Puis la conséquence métier, qui est la raison d'être de tout ce travail :

- [ ] ouvrir un appel à mission dont les compétences recherchées incluent
      celle qui vient d'être promue ;
- [ ] lancer le matching ;
- [ ] **l'intervenant apparaît dans les propositions**, et l'explication de
      son score nomme la compétence.

Si le champ du contact reste vide, la chaîne est rompue et le coupable est
identifiable : `expert_skill_competence_ids` filtre sur `is_confirmed`, qui
dépend de `confiance`. Une promotion qui poserait `confiance = 'ia'` créerait
la ligne **sans** la rendre visible — le défaut le plus discret possible, et
c'est exactement ce que la régression volontaire a mesuré.

## 6 — Une proposition non rapprochée ne crée rien

C'est le cas le plus fréquent au début de la vie du catalogue, et c'est celui
qui l'enrichit.

Déposer un CV portant une compétence absente du catalogue et de ses synonymes
— par exemple « Pilotage de drones agricoles en zone aride ». Confirmer, puis
promouvoir.

- [ ] la colonne *Promotion* passe à **En attente d'arbitrage** ;
- [ ] le bouton **Voir l'arbitrage** apparaît ;
- [ ] **aucune ligne n'a été créée au profil** — vérifier l'onglet
      *Compétences* ;
- [ ] **le catalogue n'a pas grossi** — comparer le compte avant et après.

Puis dans **Compétences à arbitrer** :

- [ ] la ligne y est, décision **En attente**, avec le profil et le document
      d'où elle vient ;
- [ ] le gestionnaire peut la rattacher ou l'ajouter au catalogue, avec sa
      famille de rangement.

La promotion passe par `resolve_skills()`, jamais par un `create()` sur le
référentiel. Un bouton qui écrirait un libellé libre au catalogue créerait le
catalogue parallèle que le §8 interdit, et le matching comparerait des
ensembles qui ne se croisent que par coïncidence d'orthographe.

## 7 — Les deux gardes qui ne se voient pas

**Promouvoir deux fois.** Recliquer *Promouvoir* sur une ligne déjà promue —
ou promouvoir en masse une liste qui en contient une.

- [ ] une seule compétence au profil, aucune erreur.

Le chemin du second passage est banal : deux clics, une liste, un script de
reprise. Sans la garde, la contrainte `unique(profile_id, competence_id)`
ferait sauter la transaction entière plutôt que de ne rien faire.

**Promouvoir sur une compétence déjà vérifiée par OPEX.** Prendre une ligne
existante, passer sa confiance à *Vérifié par OPEX*, puis promouvoir une
proposition qui désigne la même compétence.

- [ ] la confiance **reste** *Vérifié par OPEX* ;
- [ ] la source reste celle d'origine ;
- [ ] **la citation du CV est ajoutée** en preuve.

C'est le défaut le plus discret de cette extension : il ne casse rien, il
**abaisse une qualité**. Une ligne vérifiée que la promotion ramènerait à
« confirmé par l'expert » perdrait ce travail sans un mot, et le §9 se
dégraderait par le chemin censé l'alimenter.

## 8 — Ce qui ne se promeut pas

Sur une proposition de destination **Langue**, **Diplôme** ou **Certification** :

- [ ] confirmer la ligne ;
- [ ] **le bouton Promouvoir n'apparaît pas.**

Les huit autres destinations n'ont pas de modèle qui les attende avec un
rapprochement taxonomique. Les promouvoir demanderait un référentiel par
destination — c'est la dette D1 pour les certifications, et ce n'est pas ici.
Le refus est explicite plutôt que silencieux : appelée par script, la méthode
lève un message qui dit pourquoi.

---

## Les tests automatiques correspondants

`tests/test_cv_promotion.py` — 13 tests.

| Ce qui est vérifié | Test |
|---|---|
| **La chaîne est bouclée jusqu'au matching** | `test_the_promoted_skill_reaches_the_matching` |
| Les trois axes du §9 sont posés | `test_the_promoted_skill_carries_the_three_axes` |
| Le niveau n'est pas déduit du CV | `test_the_promotion_does_not_invent_a_level` |
| La proposition garde le lien | `test_the_proposal_keeps_the_link_to_what_it_produced` |
| Un synonyme est promu sans appel IA | `test_a_synonym_is_promoted_without_calling_the_ai` |
| Non rapprochée : rien créé, file d'arbitrage | `test_an_unmatched_proposal_creates_nothing_and_goes_to_arbitration` |
| La ligne d'arbitrage dit d'où elle vient | `test_the_arbitration_line_carries_the_profile_and_the_document` |
| Non confirmée : refus | `test_an_unconfirmed_proposal_cannot_be_promoted` |
| Seules les compétences se promeuvent | `test_only_competences_are_promotable` |
| Promouvoir deux fois donne une ligne | `test_promoting_twice_produces_one_skill` |
| Sur une ligne existante, la preuve s'ajoute | `test_promoting_onto_an_existing_skill_adds_the_proof` |
| Aucune rétrogradation d'une ligne vérifiée | `test_a_promotion_never_downgrades_a_verified_skill` |
| Le catalogue n'est jamais écrit | `test_the_promotion_writes_no_competence_in_the_catalogue` |

### La régression volontaire

La promotion a été modifiée pour poser `confiance = 'ia'` au lieu de
`'expert'` — le raccourci qu'on prendrait en pensant que « la ligne vient de
l'IA, donc sa confiance est `ia` ». C'est faux : `source` dit d'où vient
l'information, `confiance` dit ce qu'elle vaut, et l'expert l'a confirmée.

```
FAIL: test_the_promoted_skill_carries_the_three_axes
      AssertionError: 'ia' != 'expert'

FAIL: test_the_promoted_skill_reaches_the_matching
      AssertionError: opex.innovation.competence(865,) not found in
      opex.innovation.competence() : La compétence promue n'atteint pas le
      champ que le Smart Matching interroge : la chaîne n'est pas bouclée.
```

Le second est celui qui compte, et il est instructif : **la ligne était bien
créée au profil.** Rien n'aurait semblé cassé à l'écran — l'onglet
*Compétences* la montrait. Elle était simplement invisible du matching, parce
que `expert_skill_competence_ids` filtre sur `is_confirmed`, qui dépend de
`confiance`.

C'est le genre de défaut qui ne se voit pas en démonstration et qui se paie en
production : des experts qualifiés qui ne sortent jamais dans les propositions,
sans une erreur nulle part.
