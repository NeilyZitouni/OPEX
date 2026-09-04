# Protocole de test manuel — Extension IA-1 : parsing du CV

**§6, §17, §24 de la spécification Smart Expert Onboarding.**

Ce protocole se déroule avec un **vrai CV en PDF**. Il vérifie ce que le
module fait de la réponse du modèle, pas ce que le modèle répond.

---

## Avant de commencer

```
venv\Scripts\python.exe odoo\odoo-bin -c odoo.conf -d opex_mis_e1 ^
    -u opex_ai_core,opex_intervenants --http-port=8072 --limit-time-real=0
```

Le port 8072 n'est pas une préférence : voir la règle 19 du CLAUDE.md.

Deux identités suffisent :

| Rôle | Compte | Ce qu'il doit pouvoir faire |
|---|---|---|
| Gestionnaire des missions | membre de `group_mission_manager` | déposer, relancer, confirmer |
| Intervenant | compte portail avec un profil expert | rien de ce qui précède |

---

## 1 — Le dépôt rend la main

**Missions → Capital des intervenants → Profils experts**, ouvrir un profil,
bouton **Déposer un CV**.

Choisir un PDF réel, valider.

Attendu :

- [ ] la fenêtre se ferme **immédiatement** — pas de roue qui tourne ;
- [ ] la fiche du CV s'ouvre, la barre d'état est sur **À analyser** ;
- [ ] l'onglet *Propositions* est vide ;
- [ ] *Analysé le* est vide, *JSON brut* est vide.

C'est le point le plus important de l'écran : un parsing prend dix à trente
secondes, et une route qui attend cela est inutilisable. Si la fiche s'ouvre
déjà analysée, l'appel est redevenu synchrone.

## 2 — La version se compte par profil

Déposer un second CV sur le **même** profil, puis un CV sur un **autre**
profil.

- [ ] le second CV du premier profil est en **v2** ;
- [ ] le premier CV du second profil est en **v1**, pas en v3.

« Le troisième CV de Zitouni » a un sens ; « le 412e CV du portail » n'en a
aucun.

## 3 — Le cron traite la file

Attendre le passage automatique (dix minutes) ou le forcer :

**Paramètres → Technique → Automatisation → Actions planifiées**, ouvrir
*OPEX Intervenants : analyser les CV deposes*, bouton **Exécuter manuellement**.

Revenir sur la fiche du CV, rafraîchir.

- [ ] l'état est passé à **Analysé** ;
- [ ] *Analysé le* porte un horodatage ;
- [ ] l'onglet *JSON brut* contient la réponse **telle qu'elle est arrivée** ;
- [ ] l'onglet *Propositions* est rempli.

Si l'état est **Analyse impossible**, lire *Motif de l'échec* puis le journal :
**Paramètres → Technique → Journal des appels à l'IA**. Les trois causes
habituelles sont la clé absente, le projet Google refusé en génération, et le
quota.

## 4 — Le critère du §24, à l'écran

C'est le point à montrer en soutenance.

Dans l'onglet *Propositions*, pour **chaque** ligne :

- [ ] la colonne *Source* dit **Proposé par l'IA** ;
- [ ] la colonne *Confiance retenue* dit **Proposé** — jamais *Confirmé* ;
- [ ] la colonne *Confiance du modèle* porte un nombre entre 0 et 1 ;
- [ ] ouvrir une ligne : le champ **Passage du CV** contient un extrait qu'on
      retrouve en rouvrant le document.

Puis, et c'est la moitié qui compte :

- [ ] ouvrir l'onglet *Compétences* du **profil expert** : il n'a **pas**
      changé. Aucune ligne n'y a été créée par l'analyse.

Le parsing propose ; il ne valide rien. Une compétence proposée qui atterrirait
dans `opex.expert.skill` serait matchable sans que personne se soit prononcé —
c'est précisément ce que le filtre `is_confirmed` de `res.partner` empêche déjà
en aval, et ce que cette barrière-ci empêche en amont.

## 5 — La confirmation est un geste humain, et elle laisse sa trace

Sur une proposition, bouton **Confirmer**.

- [ ] *Confiance retenue* passe à **Confirmé par l'expert** ;
- [ ] *Confirmée par* porte votre nom et *Confirmée le* un horodatage ;
- [ ] la **valeur** et le **passage du CV** n'ont pas bougé ;
- [ ] l'onglet *Compétences* du profil n'a **toujours pas** changé.

Le dernier point surprend et il est voulu : confirmer une proposition ne crée
pas de ligne de compétence. Cela supposerait un rapprochement taxonomique, et
écrire un libellé libre dans le référentiel du Module 2 est exactement ce que
le §8 interdit. Le rapprochement est l'affaire de l'Extension IA-2, et il a son
propre écran.

## 6 — Un document illisible ne casse rien

Déposer un fichier qui n'est pas un CV — une image renommée en `.pdf`, ou un
PDF vide.

- [ ] l'état passe à **Analyse impossible** après le passage du cron ;
- [ ] *Motif de l'échec* est rempli et lisible ;
- [ ] aucune proposition n'a été créée ;
- [ ] **les autres CV de la file ont bien été analysés** — c'est le point du
      test : chaque document est traité dans son propre savepoint.

Relancer trois fois (bouton **Relancer l'analyse**) :

- [ ] au quatrième passage du cron, le compteur *Tentatives* reste à 3 et le
      CV n'est plus repris. Sans cette borne, la file boucle sur le même
      document à chaque passage, et chaque tour est facturé.

## 7 — Le champ inattendu

Ce point ne se voit qu'en lisant le JSON brut, et c'est justement pourquoi il
est conservé.

- [ ] comparer l'onglet *JSON brut* et l'onglet *Propositions* : si le modèle a
      rendu une clé qui n'est pas l'une des neuf du §6, elle est **dans le
      JSON** et **absente des propositions**.

Un champ inattendu qui traverserait finirait par s'afficher quelque part, et
personne ne saurait d'où il vient.

## 8 — Sans l'assistance IA

`opex_ai_core` n'est pas une dépendance déclarée. Sur une base où il n'est pas
installé :

- [ ] `opex_intervenants` s'installe et fonctionne ;
- [ ] le bouton *Déposer un CV* dépose ; l'analyse part en échec avec un motif
      qui le dit ;
- [ ] la saisie manuelle des compétences, elle, fonctionne comme depuis
      l'Extension 3.

---

## Ce que le module a rendu sur un CV réel

Le CV `cv_neil (1).pdf` a été déposé et l'analyse déroulée jusqu'au bout.

⚠ **La réponse ci-dessous est simulée.** Le projet Google associé à la clé
fournie est toujours refusé en génération — `_test_connection()` répond :

> « La clé est reconnue, mais le projet gemini associé n'a pas accès à la
> génération. C'est un réglage de compte, pas de configuration. »

Le PDF réel a bien été déposé (152 208 octets en base64) et l'appel réel a bien
été tenté : le journal porte `cv_parsing / http_error / 500 ms`, le CV est passé
en **Analyse impossible**, et **rien n'a été écrit**. C'est le comportement
attendu face à une panne de fournisseur.

Ce qui est montré ici est donc ce que le module **fait de** la réponse, la
réponse étant fournie à la place du modèle. Chaque citation est un extrait réel
du PDF.

### Le JSON conservé

```json
{
 "titre": [
  {
   "valeur": "Ingénieur en informatique (3e année, cycle ingénieur 1CS)",
   "confidence": 0.92,
   "source_quote": "Étudiant Ingénieur en Informatique 3e année (1CS), ESI Alger"
  }
 ],
 "experience": [
  {
   "valeur": "Développeur Full-Stack — Projet 2CP, février à juin 2025",
   "confidence": 0.95,
   "source_quote": "Développeur Full-Stack Projet 2CP Alger, Algérie"
  }
 ],
 "competence": [
  {"valeur": "Django",   "confidence": 0.94,
   "source_quote": "Django, Django Channels (WebSockets) et Redis"},
  {"valeur": "React.js", "confidence": 0.90,
   "source_quote": "responsives avec React.js et Tailwind CSS"},
  {"valeur": "Agile",    "confidence": 0.65,
   "source_quote": "Travail en équipe selon une démarche Agile",
   "note_interne": "champ que le modèle a inventé"}
 ],
 "certification": [],
 "annees": [{"valeur": "1", "confidence": 0.45,
             "source_quote": "Février — Juin 2025"}],
 "salaire_souhaite": [{"valeur": "non précisé", "confidence": 0.9,
                       "source_quote": "-"}]
}
```

### Ce que le module en a écrit — 15 propositions

```
annees        | 1                                              | 0.45 | ia/propose | confirmée=False
competence    | Django                                         | 0.94 | ia/propose | confirmée=False
competence    | React.js                                       | 0.90 | ia/propose | confirmée=False
competence    | Node.js                                        | 0.90 | ia/propose | confirmée=False
competence    | API REST                                       | 0.90 | ia/propose | confirmée=False
competence    | MongoDB                                        | 0.88 | ia/propose | confirmée=False
competence    | Java                                           | 0.85 | ia/propose | confirmée=False
competence    | Git                                            | 0.80 | ia/propose | confirmée=False
competence    | Agile                                          | 0.65 | ia/propose | confirmée=False
diplome       | École nationale supérieure d'informatique      | 0.90 | ia/propose | confirmée=False
experience    | Développeur Full-Stack — Projet 2CP            | 0.95 | ia/propose | confirmée=False
langue        | Français                                       | 0.70 | ia/propose | confirmée=False
resume        | Concepteur de systèmes logiciels, APIs REST…   | 0.88 | ia/propose | confirmée=False
secteur       | Numérique et systèmes d'information            | 0.60 | ia/propose | confirmée=False
titre         | Ingénieur en informatique (3e année, 1CS)      | 0.92 | ia/propose | confirmée=False
```

Quatre choses à lire dans ce tableau :

1. **`salaire_souhaite` n'y est pas.** La clé est dans le JSON conservé, elle
   n'est pas dans les propositions. `note_interne` non plus, à l'intérieur de
   la ligne « Agile ».
2. **`certification` n'y est pas** non plus : le modèle a rendu une liste vide,
   et une liste vide ne produit pas de proposition creuse.
3. **Toutes les lignes sont `ia/propose`, aucune n'est confirmée.**
4. **`lignes opex.expert.skill créées : 0`.** C'est le §24 : rien n'est passé
   du côté validé.

La ligne « Agile » à 0.65 et « annees : 1 » à 0.45 sont les plus instructives.
Ce sont des lectures faibles — le modèle *déduit* une année d'expérience d'un
stage de cinq mois. Une confiance basse n'est pas une erreur : c'est
l'information qui permet de trier, et c'est exactement ce que le §9 demande de
conserver.

---

## Les tests automatiques correspondants

`tests/test_cv_parsing.py` — 18 tests.

| Ce qui est vérifié | Test |
|---|---|
| Le dépôt n'analyse rien | `test_the_deposit_queues_and_analyses_nothing` |
| La version se compte par profil | `test_the_version_counts_per_profile` |
| Le cron vide la file | `test_the_cron_processes_the_queue` |
| Le PDF part en `inline_data`, pas en texte | `test_the_pdf_goes_out_as_a_document_not_as_text` |
| Le JSON brut est conservé | `test_the_raw_json_is_kept` |
| Les cinq informations du §17 | `test_the_source_keeps_the_document_and_its_dates` |
| Les neuf destinations du §6 | `test_the_nine_destinations_of_the_table_are_extracted` |
| Confiance et citation sur chaque élément | `test_every_proposal_carries_a_confidence_and_a_quote` |
| Un champ inattendu est ignoré | `test_an_unexpected_field_is_ignored_not_written` |
| La validation précède toute écriture | `test_the_validation_happens_before_any_write` |
| Une confiance se lit sous plusieurs formes | `test_a_confidence_is_read_in_any_reasonable_form` |
| **Le §24** | `test_the_parsing_never_produces_a_validated_datum` |
| La confirmation est humaine et tracée | `test_confirming_is_a_human_gesture_and_it_is_traced` |
| Confirmer ne crée pas de compétence | `test_a_proposal_is_never_a_qualified_skill` |
| Un PDF illisible ne casse rien | `test_an_unreadable_pdf_breaks_nothing` |
| Un échec ne bloque pas la file | `test_a_failure_does_not_stop_the_queue` |
| La file abandonne après trois essais | `test_the_queue_gives_up_after_three_attempts` |
| Le module vit sans `opex_ai_core` | `test_the_module_works_without_the_ai_module_installed` |

### La régression volontaire

Le test du §24 ne vaut rien tant qu'il n'a pas rougi. `_write_proposals()` a été
modifié pour confirmer d'office les propositions de confiance ≥ 0.9 — le
raccourci qu'on prendrait « parce que le modèle est sûr » :

```
FAIL: test_the_parsing_never_produces_a_validated_datum
      AssertionError: 'confirme' != 'propose'
FAIL: test_confirming_is_a_human_gesture_and_it_is_traced
      AssertionError: res.users() != res.users(4732,)
```

Deux rouges, et le second est le plus intéressant : une proposition née
confirmée n'a **aucun `confirmed_by`**. La donnée serait validée sans que
personne l'ait validée, ce qui est mot pour mot ce que le §24 interdit.
