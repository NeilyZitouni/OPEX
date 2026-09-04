# Protocole de test manuel — Extension 6 : le pool de candidatures

Se met dans la peau du **responsable de mission**. Comptez 25 minutes.

Deux choses à prouver, et la seconde est celle qui porte tout le travail depuis
l'Extension 1 : **les candidatures des deux canaux sont comparables dans le même
écran**, et **les deux machines à états sont indépendantes**.

---

## 0. Préparer

### 0.1 Le serveur

```bash
cd C:/Users/User/Desktop/stageDeltaLog
venv/Scripts/python.exe odoo/odoo-bin -c odoo.conf -d opex_mis_demo \
    --http-port=8072 --limit-time-real=0
```

### 0.2 Un appel, et six candidats contrastés

Le pool ne se démontre pas avec deux candidats identiques. Il en faut six, qui
diffèrent **sur des choses différentes** — sinon la comparaison ne montre rien.

Reprendre l'appel **Audit cybersécurité** des protocoles précédents (type
**Audit**, compétences Cybersécurité + Réseaux, budget 300 000 sur 15 jours,
certification exigée `ISO 27001 Lead Auditor`), amené à **Candidatures en
cours**.

Puis six intervenants, profil expert **activé** (§0.2 du protocole E3) :

| | Compétences | Dispo | TJM | Certification | Arrivée par |
|---|---|---|---|---|---|
| **Karim** | Cyber + Réseaux | oui | 18 000 | ISO 27001 Lead Auditor | **matching** (Inviter) |
| **Amina** | Cyber | non | 32 000 | ISO 27001 | **portail** |
| **Samir** | Cyber + Réseaux | oui | 15 000 | **aucune** | **portail** |
| **Leïla** | Cyber | oui | 20 000 | ISO 27001 Lead Auditor | **portail** |
| **Yacine** | Réseaux | oui | 12 000 | ISO 27001 Lead Auditor | **invitation** (créée à la main) |
| **Nadia** | Cyber + Réseaux | oui | 19 000 | ISO 27001 Lead Auditor | **portail** |

> **Samir est le candidat qui compte.** Il n'a pas la certification
> obligatoire : le Smart Matching l'écarte du vivier (protocole E4, §2), mais
> **rien ne l'empêche de candidater par le portail**. C'est ce que les alertes
> doivent attraper.

Amener chaque candidature au moins jusqu'à **Candidature envoyée**, sauf Yacine
qu'on laisse en **Nouvelle opportunité**.

---

## 1. Le pool unique — un seul objet, quatre origines

`OPEX Intervenants → Pool de candidatures`, filtrer sur l'appel.

> Les six candidatures sont là, **dans la même liste**, quelle que soit leur
> origine.
>
> La colonne **Origine** est la seule chose qui les distingue : `Smart
> Matching`, `Portail Web`, `Invitation directe`. Pas de second modèle, pas de
> second écran.

Basculer en vue **Kanban**.

> **Six colonnes** : En attente du candidat · **Nouveaux · Qualifiés ·
> Short-list · Retenus** · Sans suite.
>
> Les quatre du milieu sont celles du §10. Les deux autres existent parce que le
> pool les contient forcément : une invitation pas encore honorée, et ce qui est
> sorti. Les cacher obligerait à changer de filtre pour relancer Yacine.
>
> **Toutes les colonnes s'affichent, même vides.** Un Kanban dont les colonnes
> apparaissent au fur et à mesure ne se lit pas comme un processus.
>
> Chaque carte porte : le candidat, son **score**, son **origine**, son
> **étape réelle** du workflow, et ses **alertes**.

### 1.1 Le point à ne pas manquer : la carte ne se glisse pas

Essayer de **glisser** une carte de « Nouveaux » vers « Qualifiés ».

> **Impossible.** Le Kanban est en `records_draggable="0"`.
>
> C'est délibéré et c'est le seul endroit du module où l'ergonomie native
> d'Odoo aurait cassé la règle qui gouverne tout le reste. Glisser une carte
> écrirait la colonne directement : **ni contrôle de rôle, ni condition, ni
> ligne d'historique**. Les transitions se franchissent par le bouton
> « Action », qui passe par le contrôle d'accès unique du moteur.

Ouvrir une candidature, cliquer **Action**.

> Le wizard propose les transitions ouvertes à **votre rôle**, à partir de
> l'étape courante. La carte change de colonne **après**, parce que l'étape a
> changé — pas l'inverse.

---

## 2. L'écran de comparaison — §10

`/staff/missions/<id>/pool`, ou le bouton **Pool** depuis `/staff/missions`.

### 2.1 Les colonnes en tête

> Les six colonnes en résumé, avec leur nombre de candidats.

### 2.2 Le tableau

> **Une seule ligne par candidat, les mêmes colonnes pour tous** : candidat,
> origine, étape, score, disponibilité, délai, tarif, séniorité, réputation,
> alertes.
>
> **C'est le deuxième critère d'acceptation du §21** : « une candidature issue
> du matching et une candidature Web sont comparables dans le même écran ».
> Regardez la ligne de Karim (matching) et celle de Nadia (portail) : mêmes
> colonnes, mêmes unités. L'origine est une colonne comme une autre.

> La ligne de **Samir** est **rouge**.

### 2.3 Les alertes d'éligibilité

Sous chaque candidat, la bande d'alertes.

| Candidat | Attendu |
|---|---|
| **Samir** | **Critère obligatoire non rempli** — la certification exigée |
| **Amina** | Candidat déclaré non disponible · tarif au-dessus du budget (32 000 pour un budget journalier de 20 000) · compétences partiellement couvertes |
| **Yacine** | Aucune compétence recherchée déclarée *(il n'a que Réseaux)* |
| **Karim, Nadia** | **OK**, aucune alerte |

> **L'alerte de Samir est la raison d'être de cet écran.** Le critère
> éliminatoire de l'Extension 4 filtre le **vivier du matching** ; un candidat
> arrivé par le portail ne passe par aucun vivier. Sans cette alerte, il
> arriverait en short-list sans que rien ne le signale — et les deux canaux du
> §8 ne seraient plus comparables.
>
> Et les alertes **ne bloquent pas** : Samir peut être short-listé si le
> responsable le décide. « La sélection finale reste réalisée par les
> responsables habilités du cluster » (§16).

> **Karim et Nadia n'ont aucune alerte.** Vérifiez-le : des alertes qui
> crient sur tout le monde ne discriminent plus rien.

### 2.4 L'explication du score

Déplier **« Explication du score de Karim »**.

> Le texte de l'Extension 4, critère par critère, avec les poids. Score,
> alertes et comparaison au même endroit — c'est exactement ce que le §10
> demande.
>
> Les candidats arrivés par le **portail** n'ont pas de score tant qu'ils ne
> sont pas **qualifiés** : une alerte le dit (« Candidature non scorée »).

### 2.5 Les actions

> Les boutons d'action viennent du **moteur** : ils changent selon l'étape du
> candidat et selon **votre rôle**. En `manager`, « Retenir cette candidature »
> n'apparaît pas — elle appartient au comité.

Se reconnecter en **`decideur`** et rouvrir l'écran.

> « Retenir cette candidature » apparaît sur les short-listés.

---

## 3. L'indépendance des deux machines

**C'est le test qui porte tout le travail depuis l'Extension 1.**

### 3.1 Six étapes, une seule mission

Amener les six candidatures à six étapes **différentes** :

| Candidat | Étape visée | Comment |
|---|---|---|
| Yacine | **Nouvelle opportunité** | ne rien faire |
| Amina | **Appel consulté** | `Action → Consulter l'appel` |
| Samir | **Candidature envoyée** | déjà fait |
| Leïla | **Candidature en cours d'analyse** | `Action → Qualifier` |
| Karim | **Vous êtes présélectionné** | Qualifier puis Mettre en short-list |
| Nadia | **Candidature non retenue** | `Action → Ne pas retenir` + motif |

Puis, sur **l'appel** : `Action → Clore les candidatures`.

> L'appel passe en **Sélection en cours**.

Rouvrir `/staff/missions/<id>/pool`.

> **Six candidatures, six étapes différentes, sous un appel en Sélection.**
> Le bandeau en tête affiche l'étape de l'appel, les lignes celles des
> candidats. Ils ne bougent pas ensemble.

### 3.2 Faire avancer une candidature ne bouge pas l'appel

En `decideur`, retenir **Karim**.

> Karim passe en **Candidature retenue**.
> **L'appel est toujours en Sélection en cours.** Relevez-le sur le bandeau.
> Les cinq autres candidatures n'ont pas bougé.

### 3.3 Faire avancer l'appel ne bouge pas les candidatures

Sur l'appel : `Action → Attribuer la mission` (motif obligatoire).

> L'appel passe en **Intervenant retenu**.
> **Les six candidatures sont exactement où elles étaient.** Yacine est
> toujours en « Nouvelle opportunité », Amina en « Appel consulté », Nadia en
> « Non retenue ».

### 3.4 La preuve en base

`Smart Workflow → Instances`, filtrer sur l'appel et ses candidatures.

> **Sept instances distinctes** : une pour l'appel, six pour les
> candidatures. Chacune avec son propre historique, ses propres acteurs, sa
> propre étape courante.
>
> C'est la démonstration du §12.2 : « la séparation des deux machines à états
> est obligatoire ». Elle n'est pas une intention, elle est mesurable.

---

## 4. Contrôle final

| Point | Où | Attendu |
|---|---|---|
| Un seul modèle | `Pool de candidatures`, grouper par Origine | quatre groupes, une seule liste |
| La colonne suit l'étape | qualifier un candidat | la carte change de colonne **après** la transition |
| La colonne ne s'écrit pas | glisser une carte | impossible |
| Historique complet | instance d'une candidature | une ligne par transition, avec motif |
| Le moteur n'est pas touché | `git diff opex_workflow/` | **zéro ligne** |

---

## Ce que ce protocole ne teste pas, et pourquoi

- **La sélection et son déclenchement** (contrat, ordre de mission, projet) :
  Extension 7. Ici, « Retenir cette candidature » fait avancer la candidature,
  et « Attribuer la mission » l'appel — rien de plus.
- **Les notifications aux non-retenus** (§17) : Extension 11, par des actions
  `notify` configurées sur les transitions.
- **Aucun email ne part** : SMTP absent.

### Une limite connue, à regarder pendant le test

`pool_column` est un champ **`Selection` calculé et stocké**. C'est le champ
qu'on nous reprochera en soutenance — « vous aviez dit : aucun champ d'état ».

La réponse tient en trois points, et le protocole les rend vérifiables :

1. il est **calculé** depuis `workflow_stage_id`, jamais écrit — §1.1 le montre,
   la carte ne se glisse pas ;
2. il est **readonly** au niveau du modèle : aucune écriture nulle part, et un
   test l'assert ;
3. il regroupe **dix** étapes en **six** colonnes parce que le §10 demande des
   colonnes, pas une frise — et la carte affiche toujours l'étape réelle.

C'est le même parti qu'`is_published` sur l'appel, validé à l'Extension 1.
L'avancement reste porté par le workflow, et par lui seul.
