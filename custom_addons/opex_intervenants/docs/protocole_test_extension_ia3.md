# Protocole de test manuel — IA-3 : contrôle qualité assisté

**§11 et §12 de la spécification Smart Expert Onboarding.**

⚠ **La spécification n'est toujours pas dans le dépôt.** Les §11 et §12 n'ont
pas pu être relus ; ce qui est livré suit le périmètre donné dans le prompt —
les sept contrôles, la machine à états, et la règle du §12. Si le document
contredit un point quand il arrivera, le dire plutôt que de coder autour.

---

## Avant de commencer

```
venv\Scripts\python.exe odoo\odoo-bin -c odoo.conf -d opex_mis_e1 ^
    -u opex_ai_core,opex_intervenants --http-port=8072 --limit-time-real=0
```

Un compte membre de `group_mission_manager` suffit.

---

## 1 — La machine à états du §11

**Missions → Configuration → Qualification → Dossiers de qualification**

Créer un dossier sur un profil expert existant.

- [ ] la barre d'état montre les positions du §11 : Inscrit, Profil en cours
      de saisie, Profil soumis, Contrôle qualité, À compléter, Qualifié,
      Actif, Suspendu, Refusé, Archivé ;
- [ ] le dossier démarre sur **Inscrit** ;
- [ ] la fiche ne porte **aucun champ d'état** — l'avancement est
      `workflow_stage_id`, comme aux onze autres définitions.

Puis, dans **Configuration → Workflows** (module `opex_workflow`), ouvrir
`expert_qualification` :

- [ ] toutes les transitions de contrôle sont tenues par le rôle **Contrôle
      qualité**, jamais par un groupe d'utilisateurs.

C'est ce qui permet de remplacer le contrôleur humain par un agent autonome
sans toucher au workflow : seul le **porteur** du rôle change.

- [ ] **Actif n'est pas une étape finale.** Seules Refusé et Archivé le sont.
      Une qualification close en Actif ne pourrait plus être suspendue —
      `do_transition()` pose `state = 'done'` en atteignant une étape `is_end`,
      et le moteur refuse alors tout.

## 2 — Les contrôles déterministes, sans aucun appel

C'est la moitié qui compte le plus, et elle ne coûte rien.

Sur un profil expert, introduire quatre défauts :

1. laisser **des champs vides** (domaine, fonction, description) ;
2. ajouter une expérience dont le **début est dans le futur** ;
3. ajouter une certification **expirée** ;
4. créer un second contact avec **le même email**.

Sur le dossier, cliquer **Lancer le contrôle**.

- [ ] l'onglet *Anomalies* se remplit ;
- [ ] chaque ligne porte l'origine **Contrôle déterministe** ;
- [ ] les contrôles touchés sont *Identité*, *Complétude du profil*,
      *Cohérence CV / profil* et *Certifications requises* ;
- [ ] le doublon par email est **bloquant** — deux fiches pour une même
      personne dispersent sa réputation, qui se calcule par partenaire.

⚠ **Aucun appel n'a été fait.** Le vérifier : **Paramètres → Technique →
Journal des appels à l'IA** — aucune ligne neuve si le profil ne déclenche pas
la seconde moitié.

## 3 — Sans clé, le contrôle fonctionne quand même

C'est la règle 1 du service portée au métier, et c'est ce qui rend le module
livrable à un cluster qui n'active pas l'IA.

Désactiver la clé (**Paramètres → OPEX — Assistance IA**), relancer le
contrôle.

- [ ] les anomalies déterministes sont **toutes là** ;
- [ ] *Assistance IA sollicitée* est décoché ;
- [ ] le champ **Pourquoi l'IA n'a pas été sollicitée** l'explique en une
      phrase.

Le contrôle perd la moitié qui **juge**, il garde celle qui **vérifie**.

## 4 — L'IA, ensuite et seulement ensuite

Avec une clé active, sur un profil qui déclare « 20 ans d'expérience » et ne
liste que trois ans d'expériences :

- [ ] une anomalie apparaît avec l'origine **Assistance IA** ;
- [ ] sa gravité est *Information* ou *À vérifier* — **jamais Bloquant** ;
- [ ] elle porte une justification qui cite ce qui la fait dire.

⚠ Une anomalie d'IA **ne peut pas** être bloquante, et ce n'est pas une
politesse : `blocking` est ce que lit un contrôleur pressé. Laisser l'IA le
poser reviendrait à lui faire prendre une décision d'activation. Le code
dégrade toute gravité `blocking` rendue par le modèle.

- [ ] l'IA n'instruit que trois contrôles : *Cohérence*, *Compétences clés*,
      *Références*. Les quatre autres sont entièrement déterministes — un
      modèle de langage y serait moins fiable qu'un `if`.

## 5 — **LE POINT QUI GOUVERNE** : l'avis ne décide rien

C'est la vérification à faire lire à votre encadrant.

Sur un dossier **sans aucune anomalie bloquante**, relancer le contrôle.

- [ ] l'avis est produit, la recommandation s'affiche ;
- [ ] **le dossier n'a pas changé d'étape.** Il reste où il était.

Puis lire la recommandation :

- [ ] elle se termine par « La décision reste au contrôleur » ;
- [ ] elle n'écrit jamais « à activer », « profil conforme » ni « à refuser ».
      Elle **suggère**.

Pour faire avancer le dossier, il faut le bouton **Action** — celui du moteur,
qui ouvre le wizard de transition et demande qui agit.

⚠ Vérifier aussi l'absence de raccourci par la configuration :
**Configuration → Workflows → expert_qualification**, onglet des transitions.

- [ ] **aucune transition ne porte de condition.** Une règle qui lirait
      `blocking_count` rendrait l'activation dépendante d'un avis, sans
      qu'aucune ligne de Python ne l'écrive nulle part. C'est la forme que
      prendrait le défaut si quelqu'un voulait gagner du temps.

## 6 — L'avis est une note interne

Onglet du chatter, sur le dossier.

- [ ] l'avis y figure, avec la liste des anomalies et la recommandation ;
- [ ] c'est une **note interne** (fond gris), pas un message ;
- [ ] les balises s'affichent rendues, pas en clair.

`mail.mt_note` et jamais `mt_comment` : un `mt_comment` partirait par email
aux followers, dont l'intervenant — qui recevrait la liste des anomalies
relevées sur son propre dossier avant que quiconque l'ait instruit.

## 7 — La file du §20

**Dossiers de qualification**, filtres :

- [ ] **À contrôler** : les dossiers jamais passés au contrôle ;
- [ ] **Avec anomalie bloquante** ;
- [ ] **Contrôlés sans assistance IA** — utile pour savoir ce qui devra être
      repassé le jour où la clé sera active.

- [ ] relancer un contrôle après correction : l'avis précédent est
      **remplacé**, pas accumulé. Sinon on ne saurait plus ce qui vaut
      aujourd'hui.

---

## Ce que l'agent ne sait PAS faire

À annoncer, pas à découvrir en démonstration.

### Il ne décide rien, et c'est voulu

- il **n'active** aucun profil, ne le qualifie pas, ne le refuse pas ;
- il ne franchit **aucune** transition ;
- aucune condition de workflow ne lit ce qu'il produit.

Ce n'est pas une limite technique, c'est le §12 : « la décision d'activation
reste gouvernée par les règles OPEX ».

### Ce que le déterministe ne couvre pas

- **l'authenticité d'une pièce** — il vérifie qu'un justificatif est joint,
  jamais qu'il est authentique. Aucune lecture de document, aucune
  vérification d'un numéro de certification auprès de l'organisme ;
- **l'identité réelle** — il détecte un doublon probable par email ou
  téléphone. Il ne fait **aucun** rapprochement de nom : « Mohamed Amine » et
  « M. Amine » se ressemblent trop pour qu'un rapprochement automatique soit
  défendable, et une fausse alerte sur un doublon fait **fusionner deux
  personnes** ;
- **les numéros courts** — moins de huit chiffres n'identifie personne, et
  chercher dessus ferait remonter tout l'annuaire ;
- **les références** — il constate qu'il y a des expériences, il n'appelle
  personne pour les vérifier.

### Ce que l'IA ne couvre pas

- elle n'a **pas le CV**. Elle juge sur le profil déclaré, les compétences,
  les expériences et les certifications — pas sur le document. Le rapprochement
  CV / profil du §11 est donc instruit sur ce que le parsing de l'IA-1 a
  **déjà porté au profil**, pas sur le texte brut ;
- elle ne reçoit **ni email, ni téléphone, ni pièce jointe**. Le jugement
  demandé porte sur la cohérence d'un parcours ; envoyer des données
  personnelles à un tiers pour une question qui ne les demande pas serait
  disproportionné ;
- elle ne peut poser **aucune anomalie bloquante** ;
- elle ne peut instruire que **trois** des sept contrôles.

### Ce qui reste à un humain, entièrement

- juger si un profil incomplet mérite un complément ou un refus ;
- décider de suspendre ou d'archiver ;
- trancher un doublon probable — fusionner deux fiches est irréversible ;
- arbitrer une certification non rapprochée (file de D1).

### Limites d'environnement

- **Le projet Google associé à la clé est refusé en génération.** La seconde
  moitié du contrôle n'a donc pas été éprouvée contre l'API réelle ; elle l'a
  été contre des réponses simulées, y compris les cas où le modèle invente un
  contrôle ou pose une gravité bloquante ;
- le back-office n'est pas vérifiable dans le navigateur piloté (limite
  connue depuis l'IA-1).

---

## Les tests automatiques correspondants

`tests/test_qualification_review.py` — 23 tests.

| Ce qui est vérifié | Test |
|---|---|
| **Un avis n'active jamais un profil** | `test_an_ai_advice_never_activates_a_profile` |
| Aucune condition ne lit un avis | `test_no_transition_condition_reads_what_the_control_produces` |
| Le contrôle n'appelle jamais `do_transition` | `test_the_control_never_calls_do_transition` |
| **Date incohérente trouvée sans IA** | `test_the_deterministic_checks_find_an_inconsistent_date` |
| **Certification expirée trouvée sans IA** | `test_the_deterministic_checks_find_an_expired_certification` |
| **Doublon probable détecté** | `test_a_probable_duplicate_is_detected_before_creation` |
| Un numéro court ne crée pas de fausse alerte | `test_a_short_phone_number_raises_no_duplicate` |
| **Sans clé, le déterministe tourne** | `test_the_deterministic_checks_run_without_any_api_key` |
| Une réponse illisible n'est pas fatale | `test_an_unusable_ai_answer_is_not_fatal` |
| Une anomalie d'IA n'est jamais bloquante | `test_an_ai_anomaly_can_never_be_blocking` |
| L'IA ne peut pas inventer un contrôle | `test_the_ai_cannot_invent_a_control` |
| L'avis est une note interne | `test_the_advice_is_posted_as_an_internal_note` |
| La recommandation ne décide pas | `test_the_recommendation_never_decides` |
| Un second passage remplace l'avis | `test_running_twice_replaces_the_advice` |
| Aucun champ `state` | `test_the_review_has_no_state_field` |
| Les dix positions du §11 | `test_the_state_machine_has_the_ten_positions_of_section_11` |
| Actif n'est pas final | `test_active_is_not_a_final_stage` |
| Le workflow du Module 2 est intact | `test_the_module_two_profile_workflow_is_untouched` |
| Rien ne suppose un contrôleur humain | `test_nothing_assumes_the_controller_is_a_person` |
| La file du §20 est un dictionnaire fermé | `test_the_work_queue_is_a_closed_dictionary` |

### La régression volontaire, et le premier essai qui n'a rien prouvé

Le contrôle a été modifié pour poser le dossier en `qualified` à la fin de
`_run_once()` — le raccourci qu'on prendrait en pensant « aucune anomalie,
autant qualifier tout de suite ».

**Le premier essai est resté vert**, et c'est le plus instructif. La casse
était conditionnée à `if not anomalies:` et le profil du test n'est pas sans
anomalie : il n'a aucune pièce jointe, ce que `_check_conformite()` signale en
`warning`. Le raccourci ne s'est donc jamais déclenché, et le test de garde
n'a rien mesuré.

Rendue inconditionnelle, elle donne :

```
FAIL: test_an_ai_advice_never_activates_a_profile
      AssertionError: opex.workflow.stage(434,) != opex.workflow.stage(429,)
      : Le contrôle a fait avancer le dossier : l'agent décide au lieu de
        préparer, ce que le §12 interdit.
```

C'est la règle 20 sous un troisième jour : **avant de croire une régression
volontaire, vérifier qu'elle s'est déclenchée.** Une casse qui ne s'exécute
pas ressemble exactement à un test qui protège.

### Le contrôle de date, et le chemin qu'il garde réellement

`opex.expert.experience._check_dates()` (Extension 3) refuse déjà une fin
antérieure au début. Le cas **n'arrive jamais par l'écran** — et une garde qui
ne peut pas se déclencher est un test qui occupe la place.

Elle n'est pas retirée pour autant : une contrainte Python ne s'applique qu'à
l'ORM, et un import, une reprise ou une migration la contournent. Le test
l'éprouve donc **en écrivant en base**, faute de quoi il ne mesurerait rien.
Le cas « début dans le futur », lui, n'est contraint par personne et s'atteint
normalement.
