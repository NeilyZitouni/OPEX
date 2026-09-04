# Protocole de test manuel — Extension 4 : le Smart Matching

Se met dans la peau du **responsable de mission**. Comptez 30 minutes.

Quatre choses à prouver, et ce sont quatre critères d'acceptation du §21 :
les pondérations sont **configurables**, les critères éliminatoires **écartent
au lieu de mal noter**, le score est **explicable**, et **rien ne décide à la
place de l'humain**.

---

## 0. Préparer

### 0.1 Le serveur

```bash
cd C:/Users/User/Desktop/stageDeltaLog
venv/Scripts/python.exe odoo/odoo-bin -c odoo.conf -d opex_mis_demo \
    --http-port=8072 --limit-time-real=0
```

### 0.2 Trois intervenants contrastés

Le matching ne se démontre pas avec un seul candidat. Il en faut trois, qui
diffèrent **sur des critères différents** — sinon le classement ne prouve rien.

Créer trois comptes portail avec un profil expert **activé** (voir §0.2 du
protocole de l'Extension 3), puis renseigner leur capital depuis
`/my/missions/expertise` :

| | Karim | Amina | Samir |
|---|---|---|---|
| Compétences | Cybersécurité, Réseaux | Cybersécurité | Cybersécurité, Réseaux |
| Séniorité (expérience) | Senior | Junior | Senior |
| Domaine pratiqué | Cybersécurité | Cybersécurité | Cybersécurité |
| Disponibilité en cours | oui | **non** | oui |
| TJM indicatif | 18 000 | **32 000** | 15 000 |
| Wilaya (fiche contact) | Alger | **Oran** | Alger |
| Certification | **ISO 27001 Lead Auditor** | ISO 27001 | **aucune** |

Le TJM et les langues sont sur le **profil expert** (back-office, ou le champ
ajouté à l'Extension 4). La wilaya est sur la **fiche contact**.

### 0.3 Un appel à mission publiable

En `manager`, créer un appel **de type Audit** :

| Champ | Valeur |
|---|---|
| Titre | Audit cybersécurité |
| Domaine | Cybersécurité |
| Compétences | Cybersécurité **et** Réseaux |
| Niveau d'expérience | Senior |
| Wilaya | Alger |
| Budget estimatif | 300 000 |
| Durée estimée | 15 jours |
| **Certifications souhaitées** | `ISO 27001 Lead Auditor` |
| Date limite | dans 30 jours |

---

## 1. Les sept critères du §11

`OPEX Intervenants → Configuration → Critères de matching`.

> Sept lignes au **profil par défaut** — le filtre est actif à l'ouverture.
> La colonne Poids totalise **100** : 30 · 20 · 15 · 10 · 10 · 10 · 5.

Retirer le filtre « Profil par défaut », grouper par **Type de mission**.

> Trois lignes sous **Formation** (compétences 40, secteur 5, disponibilité
> 15) et une sous **Audit** (Certification exigée), en rouge.
>
> Les autres familles ne sont **pas** redéclarées sous Formation : elles sont
> héritées du défaut. Sans cela, chaque nouveau type obligerait à recopier les
> sept.

---

## 2. Éliminatoire : écarté, pas mal noté

Ouvrir l'appel → onglet **Smart Matching** → **Lancer le Smart Matching**.

> **Deux** propositions : Karim et Amina. **Samir n'y est pas.**
>
> Un encart gris : *« 1 intervenant écarté par un critère éliminatoire »*,
> avec le motif — `Samir Haddad — Certification exigée — le candidat ne
> renseigne pas ce champ`.

**C'est le point à vérifier vraiment** : Samir a les meilleures compétences et
le TJM le plus bas. S'il apparaissait en bas de liste avec un score médiocre,
le critère serait **pondéré**, pas éliminatoire. Il doit être **absent**.

> Vérifier aussi qu'il n'a **aucune ligne** dans la liste des candidats
> proposés en bas de l'onglet — pas même avec l'état « Exclu ».

### 2.1 Un critère obligatoire que l'appel n'exprime pas ne s'applique pas

Vider **Certifications souhaitées** sur l'appel, relancer le matching.

> **Trois** propositions, zéro écarté. Samir revient.
>
> Sans ce garde-fou, `_compare()` répondrait « aucune attente exprimée sur le
> dossier » — donc faux — et **tout le vivier** serait écarté : une liste vide,
> et rien pour l'expliquer. Le §6 dit « obligatoires ou préférentiels **selon la
> mission** ».

Remettre `ISO 27001 Lead Auditor` avant de continuer.

---

## 3. L'explication du score

Aller sur l'écran responsable : `/staff/missions` → **Smart Matching** sur
l'appel.

> En haut, **les critères appliqués** avant la liste : un score ne se lit pas
> sans savoir sur quoi il porte. Chaque ligne indique ce qui est comparé
> (`field('skill_ids')` ↔ `expert_skill_competence_ids`), le poids en
> pourcentage, et un badge **Pondéré** ou **Éliminatoire**.

Déplier **« Voir l'explication du score »** sur Karim.

> Vous devez lire exactement ceci (aux valeurs près) :

```
Critères appliqués : 7 pondérés (Compétences recherchées 30 %, Niveau
d'expérience 20 %, Expérience du domaine 15 %, Disponibilité 10 %, Budget 10 %,
Réputation OPEX 10 %, Localisation et langue 5 %), 1 éliminatoire(s).
Obligatoires remplis : Certification exigée.
Score 90 % — 90 point(s) sur 100

Compétences recherchées (poids 30) — cybersécurité, réseaux ↔ cybersécurité, réseaux
Niveau d'expérience (poids 20) — senior ↔ senior
Expérience du domaine (poids 15) — cybersécurité ↔ cybersécurité
Disponibilité (poids 10) — true ↔ true
Budget (poids 10) — 20000.0 ↔ 18000.0
Réputation OPEX (poids 10) — le candidat ne renseigne pas ce champ
Localisation et langue (poids 5) — alger ↔ alger
```

> **Chaque point du score se rattache à un critère nommé**, avec ce qui a été
> comparé de part et d'autre. C'est ce qui rend un 90 % défendable.
>
> La ligne Budget lit `20000.0 ↔ 18000.0` : le **budget journalier** de la
> mission (300 000 ÷ 15) contre le TJM de l'expert. Pas le budget total.

Déplier celle d'Amina (45 %).

> Cinq `` qui disent chacun **pourquoi** : junior au lieu de senior,
> indisponible, 32 000 au lieu de 20 000, Oran au lieu d'Alger.
>
> Un responsable peut expliquer l'écart entre 90 et 45 sans ouvrir un seul
> autre écran. C'est le quatrième critère d'acceptation du §21.

---

## 4. Les pondérations sont configurables

### 4.1 Par type de mission

Créer un **second appel identique**, mais de type **Formation**, et sans
certification exigée. Lancer le matching.

> Les critères affichés en haut ne sont plus les mêmes : compétences **40 %**,
> secteur **5 %**, disponibilité **15 %** — et le badge « Profil *Formation* ».
>
> Les scores changent. Amina, qui n'a qu'une compétence sur deux, recule
> davantage : les compétences pèsent maintenant 40 au lieu de 30.

### 4.2 Par appel

Revenir sur l'appel **Audit**, onglet Smart Matching →
**Personnaliser les critères de cet appel**.

> Une liste apparaît, **pré-remplie avec le profil du type** — pas vide. On
> ajuste, on ne recommence pas.

Mettre **Compétences** à 60, relancer le matching.

> Les scores bougent. Et **l'explication le dit** : l'en-tête recalcule les
> pourcentages sur la nouvelle somme.
>
> Le badge en haut passe à **« Pondérations propres à cet appel »**.

Vérifier qu'un **autre** appel du même type n'a pas bougé.

> Il affiche toujours 30 %. Les trois niveaux — défaut, type, appel — sont
> bien indépendants.

---

## 5. L'IA recommande, l'humain décide

Sur l'écran responsable, noter l'**état de l'appel** avant toute action
(« Candidatures en cours », ou ce qu'il est).

### 5.1 Les cinq actions du §6

| Action | Attendu |
|---|---|
| **Consulter le profil** | La page montre le capital **que le matching a comparé** — compétences, expériences, certifications. Pas la fiche complète du contact |
| **Mettre en short-list** | Le badge passe à **Retenu**. Aucune candidature créée |
| **Écarter** | Badge **Écarté** |
| **Revenir sur ma décision** | Retour à **Proposé** |
| **Inviter** | Voir ci-dessous |

### 5.2 « Inviter » — et ce que cela ne fait pas

Inviter Karim.

> Une **candidature** est créée : `OPEX Intervenants → Candidatures`, origine
> **Smart Matching**, état **Nouvelle opportunité** (`invited`).
>
> **L'état de l'appel n'a pas bougé.** La candidature naît sur sa propre
> machine à états ; la mission reste où elle est. C'est l'indépendance des deux
> workflows, vérifiée depuis l'Extension 1.
>
> Le score et son explication sont **recopiés sur la candidature**. Relancer
> le matching ne les réécrit pas : la décision a été prise sur ces chiffres-là.

### 5.3 Une décision humaine survit à un nouveau passage

Écarter Amina, puis **relancer le matching**.

> Amina est toujours **Écartée**. Un nouveau passage remplace les propositions
> non arbitrées, jamais les décisions.

### 5.4 Rien n'est automatique

> Parcourir l'appel : **aucune transition n'a été franchie** par le matching.
> Vérifier dans l'historique du dossier (`Smart Workflow → Instances`) :
> aucune ligne n'a été ajoutée par le lancement du matching.

---

## 6. Contrôle final

| Point | Où | Attendu |
|---|---|---|
| Le moteur n'est pas réécrit | `git diff opex_workflow/` | **zéro ligne modifiée** |
| Les critères d'`opex_innovation` sont intacts | Configuration → Critères, sans le domaine | leurs `Type de mission` et `Éliminatoire` sont vides |
| Le matching d'`opex_innovation` marche toujours | un projet accepté → Lancer le matching | propose toujours experts, mentors, investisseurs |
| L'écran est réservé | `/staff/missions` en compte `client` | redirection vers `/my` |

---

## Ce que ce protocole ne teste pas, et pourquoi

- **Le lancement automatique du matching** (§19 : « mission qualifiée →
  lancement automatique si activé »). Ici c'est un bouton. L'automatisme
  demande une action de transition, ce qui relève de l'Extension 11 avec les
  autres automatisations.
- **Le matching sémantique** : hors périmètre, V2 du §20. « Matching
  intelligent » ici veut dire scoring pondéré et explicable.
- **La réputation** : le critère existe et pèse 10 %, mais il ne rapporte à
  personne tant que l'Extension 10 n'a pas alimenté `opex.expert.rating`. Vous
  le verrez en `` sur **tous** les candidats — c'est honnête : on ne récompense
  pas une réputation qui n'existe pas.

### Deux limites connues, à regarder pendant le test

1. **Le message « le candidat ne renseigne pas ce champ » est ambigu** sur la
   réputation : l'expert n'a pas *omis* sa note, il n'a jamais été évalué. Le
   message vient du moteur ; le changer demanderait de toucher `opex_workflow`.
2. **La certification se compare en texte libre**, en mode « contient ». Un
   expert qui déclare `ISO 27001` **passe** un critère qui exige
   `ISO 27001 Lead Auditor` : la comparaison teste l'inclusion dans les deux
   sens. C'est exactement la fragilité signalée à l'Extension 3 — un référentiel
   de certifications la lèverait. À arbitrer si le cluster veut un éliminatoire
   strict.
