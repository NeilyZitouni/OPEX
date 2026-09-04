# Protocole de test manuel — Dette D1 : le référentiel de certifications

Deux manques qui étaient le même, vus des deux bouts :

- le critère éliminatoire de certification comparait **du texte libre** ;
- les certifications extraites d'un CV ne se promouvaient pas, faute de ce
  référentiel.

---

## Avant de commencer

```
venv\Scripts\python.exe odoo\odoo-bin -c odoo.conf -d opex_mis_e1 ^
    -u opex_intervenants --http-port=8072 --limit-time-real=0
```

Un compte membre de `group_mission_manager` suffit.

---

## 1 — Le référentiel est celui du Module 1, étendu

**Missions → Configuration → Certifications → Référentiel**

- [ ] les six normes ISO du Module 1 y sont, avec la portée **Organisation et
      personne** — une entreprise se certifie ISO 27001, et un auditeur aussi ;
- [ ] seize certifications de personne s'y ajoutent : Lead Auditor, Lead
      Implementer, CISA, CISSP, CISM, PMP, PRINCE2, PSM…
- [ ] grouper par **Portée** : les trois groupes sont peuplés.

Puis **Adhésions → Configuration → Certifications** (Module 1) :

- [ ] **c'est la même liste.** Un second référentiel serait exactement la dette
      D1 — deux ensembles qui ne se croisent que par coïncidence de libellé.

⚠ Le point d'architecture : un référentiel, **deux vues**. L'annuaire du
Module 1 propose les certifications d'organisation, le profil expert celles de
personne, et une norme qui vaut des deux côtés est déclarée telle une fois.
C'est ce que `porte` permet, et c'est ce qui évitait d'avoir à trancher entre
deux modèles.

## 2 — Les synonymes, et ce qu'ils ne relient pas

Ouvrir **ISO 27001 — Sécurité de l'information**, onglet *Synonymes*.

- [ ] « ISO 27001 », « ISO27001 » et « ISO 27001:2022 » y figurent.

Ce sont les trois écritures qui, avant D1, faisaient **disparaître** un
candidat qualifié : aucune ne contenait l'intitulé complet, et l'inclusion de
chaînes ne croisait rien.

Ouvrir maintenant **ISO 27001 Lead Auditor**.

- [ ] ses synonymes sont « LA 27001 », « Lead Auditor ISO 27001 »,
      « Auditeur principal ISO 27001 » ;
- [ ] **aucun synonyme ne relie les deux fiches.**

C'est le point le plus important de l'écran. Ce sont deux qualifications
distinctes : la norme atteste une connaissance, le Lead Auditor atteste la
qualification à conduire un audit de certification. Un synonyme entre les deux
rétablirait la dette.

## 3 — **LE TEST QUI COMPTE** : proche n'est pas pareil

Créer un appel à mission de type **Audit**, et lui exiger **ISO 27001 Lead
Auditor** (champ *Certifications exigées*).

Créer deux intervenants :

| | Karim | Amina |
|---|---|---|
| Certification déclarée | ISO 27001 **Lead Auditor** | ISO 27001 |
| Rapprochée | oui | oui |
| Confiance | Confirmé | Confirmé |
| Expiration | dans un an | dans un an |

Lancer le matching sur l'appel.

- [ ] **Karim est proposé** ;
- [ ] **Amina est absente de la liste** ;
- [ ] la note *Écartés par un critère éliminatoire* la nomme et dit ce qui
      manque.

C'est le scénario exact de la dette : sur le jeu de démonstration de
l'Extension 4, Amina Cherif était proposée parce que
`"iso 27001" in "iso 27001 lead auditor"` est vrai.

⚠ L'ordre des deux vérifications compte. Sans le cas de Karim, un critère qui
écarterait **tout le monde** donnerait le même écran et passerait pour une
réussite.

## 4 — Les deux autres défaillances

**L'orthographe ne fait plus disparaître personne.** Sur la fiche d'Amina,
écrire son intitulé « ISO27001 » sans espace, puis rapprocher.

- [ ] la ligne pointe toujours vers la même certification canonique ;
- [ ] son éligibilité ne change pas.

Le rapprochement se fait **avant** la comparaison : quelle que soit
l'écriture, la ligne porte la même référence.

**Exiger deux certifications veut dire les deux.** Sur l'appel, exiger
**ISO 27001** *et* **ISO 9001**. Donner à un intervenant la première
seulement.

- [ ] il est **écarté**, et le motif nomme ISO 9001 ;
- [ ] en lui donnant la seconde, il passe.

Avant D1, `_as_set()` sur une chaîne ne la découpait pas : « ISO 27001,
ISO 9001 » produisait **un seul jeton**, et n'exigeait au plus qu'une des
deux.

## 5 — Le cas qui a causé la dette : la configuration muette

C'est la vérification à faire lire à votre encadrant.

**Missions → Configuration → Critères de matching**, ouvrir
« Certification exigée » et remplacer son expression source par
`field('certification_idz')` — une faute de frappe.

Relancer le matching sur l'appel du point 3.

- [ ] **le matching refuse de tourner**, avec un message qui nomme le champ
      inexistant et le critère.

Avant, `field('nom_mal_orthographie')` **ne levait pas** : le helper du moteur
est tolérant par conception et rend `False`. Ce `False` traversait `_as_set()`,
qui rendait un ensemble vide, et l'élimination concluait « cet appel n'exprime
aucune attente » — donc n'écartait personne.

Une faute de frappe **supprimait le critère**, sans erreur, sans
avertissement, et le vivier restait plein. Plus plein, même. C'est le motif
exact du balayage typographique de la règle 21 : le symptôme ne ressemble pas
à une panne.

Remettre `field('certification_ids')`.

- [ ] le matching repart, et Amina est de nouveau écartée.

⚠ Le cas voisin qu'il ne faut **pas** confondre : un appel qui n'exige aucune
certification n'écarte personne, et c'est juste — le §6 dit « obligatoires ou
préférentiels **selon la mission** ». Le vérifier :

- [ ] vider *Certifications exigées* sur l'appel, relancer : tout le monde
      passe le critère, et aucun message d'erreur.

Les distinguer est tout l'objet du contrôle de configuration : l'un est une
expression invalide, l'autre un dossier vide.

## 6 — La promotion d'une certification extraite d'un CV

Déposer un CV mentionnant une certification (protocole IA-1), le faire
analyser, puis dans l'onglet *Propositions* :

- [ ] une ligne de destination **Certification** apparaît ;
- [ ] la confirmer, puis **Promouvoir**.

Sur la ligne créée (**Certifications → Certifications des intervenants**) :

- [ ] **Source** = *CV analysé* ;
- [ ] **Confiance** = *Confirmé par l'expert* ;
- [ ] **Passage du CV** contient l'extrait, **CV d'origine** nomme le document ;
- [ ] l'intitulé **lu** est conservé à côté de la certification canonique —
      c'est ce qui permet de contester un rapprochement ;
- [ ] la colonne **Comptée** est **vide**.

⚠ Ce dernier point surprend et c'est le bon comportement. Un CV dit rarement
la date d'expiration. La ligne est confirmée mais pas encore comptée :
`is_eligible` exige en plus qu'elle soit **valable**. Supposer une validité
perpétuelle sur un critère éliminatoire reviendrait à admettre à tort.

- [ ] renseigner la date d'expiration : la colonne **Comptée** se coche, et la
      certification entre dans le vivier.

Puis avec un libellé absent du référentiel :

- [ ] la promotion ne crée **rien** au profil ;
- [ ] **le référentiel n'a pas grossi** ;
- [ ] la ligne part dans **Certifications → À arbitrer**, décision *En
      attente*.

## 7 — L'arbitrage, et ce qu'il réserve

Dans **À arbitrer**, sur une ligne en attente :

- [ ] **Rattacher** : le libellé devient synonyme de la cible ;
- [ ] **Ajouter au référentiel** : la certification est créée, portée
      *Personne*, et le libellé d'origine devient synonyme ;
- [ ] **Écarter** : la ligne reste, avec sa trace.

Avec un compte **intervenant** :

- [ ] les trois boutons sont refusés. Le contrôle est dans le modèle, pas
      seulement sur l'écran : le référentiel décide de l'éligibilité aux
      appels, il ne s'enrichit pas par le portail.

## 8 — Ce qui n'est pas rapproché ne compte pas

**Certifications des intervenants**, filtre **Non rapprochées** (actif par
défaut).

- [ ] les certifications saisies en texte libre avant cette extension y sont ;
- [ ] leur colonne **Comptée** est vide.

C'est une conséquence à annoncer, pas un défaut : une certification en texte
libre n'est comparable à rien. Mais c'est une file qu'il faut vider — sinon
les certifications déclarées avant D1 ne comptent plus pour aucun appel.

---

## Les tests automatiques correspondants

`tests/test_certification_d1.py` — 21 tests.

| Ce qui est vérifié | Test |
|---|---|
| **Proche mais différente est écartée** | `test_a_close_but_different_certification_is_rejected` |
| La configuration compare des références | `test_the_eliminatory_criterion_compares_references_not_text` |
| Une variante d'écriture n'exclut plus | `test_a_spelling_variant_no_longer_excludes_a_qualified_expert` |
| Exiger deux, c'est exiger les deux | `test_requiring_two_certifications_requires_both` |
| **Un critère mal orthographié arrête le matching** | `test_a_misspelled_criterion_stops_the_matching_instead_of_the_exclusion` |
| Un champ candidat inexistant écarte | `test_a_misspelled_target_field_excludes_instead_of_admitting` |
| Une exigence vide n'écarte personne | `test_an_empty_requirement_excludes_nobody` |
| Le référentiel du Module 1 est étendu | `test_the_module_one_referential_is_extended_not_duplicated` |
| Les deux portées ne se mélangent pas | `test_the_two_scopes_do_not_mix` |
| Aucune collision de normalisation | `test_the_seeded_certifications_have_no_normalisation_collision` |
| Aucun synonyme ne relie deux qualifications | `test_no_synonym_bridges_two_distinct_qualifications` |
| Un référentiel ambigu refuse de choisir | `test_an_ambiguous_referential_refuses_to_choose` |
| La promotion passe par le référentiel | `test_a_certification_proposal_is_promoted_through_the_referential` |
| Inconnue : rien créé, arbitrage | `test_an_unknown_certification_creates_nothing_and_goes_to_arbitration` |
| Une promue attend sa validité | `test_a_promoted_certification_waits_for_its_validity` |
| La chaîne atteint le critère | `test_the_promoted_certification_reaches_the_matching` |
| Une expirée sort du vivier | `test_an_expired_certification_leaves_the_pool` |
| Calcul et recherche s'accordent | `test_the_eligibility_search_matches_its_computation` |

### La régression volontaire, et ce qu'elle a révélé

Le mode de comparaison a été ramené à `contains` — le raccourci exact de D1 —
et un synonyme reliant les deux fiches a été ajouté.

**Un seul test a rougi**, et ce n'était pas celui qui compte :

```
FAIL: test_requiring_two_certifications_requires_both
      AssertionError: True is not false
```

C'est une bonne nouvelle et un angle mort. Bonne nouvelle : **la protection
vient du référentiel, pas du mode de comparaison** — même en `contains`, les
deux libellés canoniques (« ISO 27001 — Sécurité de l'information » et
« ISO 27001 Lead Auditor ») ne s'incluent ni l'un ni l'autre, et l'élimination
reste juste.

Angle mort : rien ne signalait que la configuration avait été ramenée à l'état
d'avant. `test_the_eliminatory_criterion_compares_references_not_text` a été
écrit **à cause de cette mesure**, et il rougit immédiatement :

```
FAIL: test_the_eliminatory_criterion_compares_references_not_text
      AssertionError: 'contains' != 'intersect'
```

Deux rouges au second passage, l'un sur le comportement, l'autre sur la
configuration.

### Deux pièges rencontrés, et tous deux silencieux

**`noupdate="1"` masque une modification, deux fois.** Le drapeau est porté par
la ligne `ir.model.data`, pas par le fichier qui l'écrit : une fois posé,
toute mise à jour ultérieure de cet identifiant externe est ignorée, **y
compris depuis un autre module**.

- les six normes du Module 1 restaient `porte = organisation` ;
- le critère continuait de comparer du texte libre, avec tout le reste de
  l'extension en place.

Aucune erreur, aucun avertissement, et le comportement d'avant. Sept tests
rouges au premier passage. La parade est `<function>`, hors bloc `noupdate`.

**`'!'` est unaire, et Odoo 19 normalise les booléens.**
`_search_is_eligible` recevait `operator='in'`, `value=OrderedSet([True])` —
jamais `'='`. Et `['!'] + domaine` ne nie que le premier terme :
`['!', A, B, C]` vaut `(NON A) ET B ET C`.

Les deux ensemble rendaient un résultat qui ressemblait à une réponse : la
recherche donnait « Texte libre » là où le calcul donnait « CISA ». Pas une
erreur, pas un ensemble vide — **l'autre** ensemble. C'est exactement le
corollaire de la règle 16, et c'est
`test_the_eligibility_search_matches_its_computation` qui l'a attrapé.
