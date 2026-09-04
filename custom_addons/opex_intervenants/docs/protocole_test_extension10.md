# Protocole de test manuel — Extension 10

**Évaluations et réputation** : les grilles des §30 et §31, les indicateurs du
§32, l'historique du §33, et les règles 7 et 8 du §39.

Durée : ~25 min. Base `opex_mis_e1`.

```
.\venv\Scripts\python.exe .\odoo\odoo-bin -c odoo.conf -d opex_mis_e1 ^
    -u opex_intervenants --limit-time-real=0
```

**Point de départ** : une mission clôturée. Le protocole de l'Extension 9 y
mène ; si vous en avez déjà une, reprenez-la.

**Prérequis** : l'intervenant retenu doit avoir un profil expert **rattaché à
sa fiche partenaire**. C'est le lien `Profil expert` sur le contact, posé par
le Module 2 à l'activation du profil. Sans lui, les notes seront enregistrées
mais aucun indicateur du §32 ne bougera — et c'est le comportement voulu :
être noté ne fait pas entrer au vivier.

---

## Partie 1 — Les deux grilles s'ouvrent à la clôture (5 min)

**§30 et §31.**

1. Sur la mission clôturée, onglet **Évaluations**.

**À vérifier** :

- deux évaluations existent, **EVA-2026-0001** et **EVA-2026-0002** ;
- l'une est de type *Client (§30)*, l'autre *Cluster (§31)* ;
- les deux sont à l'étape *Action requise : évaluer la mission* ;
- le bandeau annonce que deux évaluations ne sont pas encore validées.

Personne ne les a créées. C'est une action `set_field` sur la transition
« Facturer et clôturer », à côté de celle qui émet la facture. L'Extension 1
avait écrit sur cette transition que « l'Extension 10 y rattachera la demande
d'évaluation ».

2. Ouvrir la grille client : elle porte les **six critères du §30** — qualité
   du travail, respect des délais, expertise, communication, pertinence des
   recommandations, satisfaction générale.

3. Ouvrir la grille cluster : **six critères différents** — respect du
   contrat, respect des délais, qualité des livrables, professionnalisme,
   communication, respect des procédures.

Les deux grilles partagent deux critères et vivent sur le même modèle. Les
quatre champs de l'autre grille sont masqués et restent à zéro ; la moyenne
ne porte que sur les six applicables. Une moyenne sur les dix ferait chuter
chaque note de quatre zéros — mesuré par régression volontaire, le message du
test dit `3.0 != 5.0`.

---

## Partie 2 — La règle 7 du §39 (5 min)

**« Le client ne peut normalement évaluer la mission qu'après sa validation
finale. »**

Sur une mission clôturée, la règle est déjà satisfaite. Pour la voir jouer, il
faut une évaluation créée à la main sur une mission qui n'en est pas là — et
c'est précisément le chemin qu'une condition garde et qu'un contrôle placé
dans le déclencheur laisserait passer.

1. Menu **OPEX Intervenants → Évaluations → Nouveau**.
2. Choisir une mission **en cours** (pas encore validée), un intervenant, type
   *Client*.
3. Noter les six critères.
4. Action → **Soumettre l'évaluation**.

   Attendu : **refus** —

   > L'évaluation ne peut être rendue qu'après la validation finale de la
   > mission (règle 7 du §39).

   Et un bandeau orange le disait déjà en haut de la fiche.

**À noter** : la règle garde les **deux** grilles, pas seulement celle du
client. Le titre de la règle 7 est général — « L'évaluation intervient après
la mission » —, et une évaluation opérationnelle rendue avant le service fait
serait tout aussi prématurée.

5. Sur la même fiche, effacer une note (la mettre à zéro) et retenter :

   > Les six critères de la grille doivent être notés de 1 à 5 avant de
   > soumettre l'évaluation.

Deux conditions distinctes sur la même transition, deux messages distincts.

---

## Partie 3 — Le renvoi pour complément (5 min)

Revenir sur la grille client de la mission clôturée.

1. Noter les six critères, écrire un commentaire, Action → **Soumettre
   l'évaluation**.
2. Compte responsable : Action → **Renvoyer pour complément** (commentaire
   obligatoire).

**À vérifier** :

- l'évaluation est à *À compléter* ;
- l'instance n'est **pas** close : le bouton Action est toujours là ;
- le profil de l'intervenant n'a reçu **aucune note** — la règle 8 parle
  d'évaluation *validée*.

3. Action → **Reprendre l'évaluation**, corriger, resoumettre, puis compte
   responsable : Action → **Valider l'évaluation**.

Une évaluation écartée sans retour possible ferait perdre la note d'une
mission pour une phrase mal tournée, et le §32 compte sur ces notes. C'est
pourquoi *Renvoyée à son auteur* n'est pas une étape finale.

---

## Partie 4 — La règle 8 et la boucle du §2 (5 min)

**« Une évaluation validée est associée au profil de l'intervenant. »**

1. Ouvrir la fiche du **contact** de l'intervenant, puis son **profil
   expert**, onglet **Réputation — §32**.

**À vérifier** :

| Indicateur | Attendu |
|---|---|
| Réputation | la moyenne de la grille validée |
| Nombre d'évaluations | 1 |
| Missions réalisées | 1 |
| Missions terminées | 1 |
| Taux de satisfaction | la note ramenée sur cent |
| Respect des délais | 100 % si la note de délais est 4 ou 5 |

2. La liste **Évaluations reçues** porte une ligne, avec sa mission et sa
   source.

Cette ligne est un `opex.expert.rating`, le modèle que l'Extension 3 avait
créé **vide** en annonçant que l'Extension 10 le remplirait. Rien n'a été
ajouté à ce modèle ni au calcul de `reputation_score` : la note remonte parce
que la ligne existe. C'est la boucle d'apprentissage du §2, et elle se
referme sans une ligne de code nouvelle du côté du profil.

3. Valider aussi la grille cluster : le nombre d'évaluations passe à 2 et la
   réputation devient la moyenne des deux. Les deux évaluations sont
   indépendantes et se cumulent.

4. Le taux de satisfaction suit l'exemple du document : le §32 affiche 4,7 sur
   5 et 94 %.

---

## Partie 5 — L'historique et sa visibilité (3 min)

**§33.**

Le §33 se lit par deux méthodes plutôt que par un écran dédié — l'annuaire
public relève de l'Extension 12. Depuis un shell Odoo :

```python
profile = env['opex.innovation.expert.profile'].search(
    [('partner_id.name', 'ilike', 'nom de l intervenant')], limit=1)

profile.mission_history(public=True)
profile.mission_history(public=False)
profile.public_reputation()
```

**À vérifier** : la version publique porte le type de mission, le domaine,
l'année et l'issue. Elle ne porte **ni** le client, **ni** le montant, **ni**
la référence, **ni** les notes détaillées — et ces clés sont **absentes** du
dictionnaire, pas mises à `False`.

C'est la leçon de l'Extension 5, mesurée là-bas par régression volontaire : un
gabarit qui masque suffit à ce qu'aujourd'hui rien ne fuie, il n'empêche pas
qu'un champ ajouté un mardi publie ce que le modèle a déjà laissé sortir. Le
filtre est donc dans le dictionnaire.

**Et le commentaire ne sort jamais.** Cocher « Visible dans l'historique
public » sur une évaluation n'ouvre que la note globale. Un commentaire
d'évaluation est un jugement nominatif ; le §33 autorise à publier des
informations, pas celle-là.

---

## Partie 6 — La barre du §40 est complète (2 min)

Sur la fiche de la mission, une fois les deux évaluations validées :

```
Demande [x] Appel [x] Sélection [x] Contrat [x] Mission [x]
Validation [x] Facturation [x] Évaluation [x]
```

Les huit jalons du §40 ont désormais tous leur objet.

**À vérifier** : l'étape de la mission n'a pas bougé — elle est restée
`closed` — et pourtant deux jalons ont changé. Ce sont les deux seuls que
l'étape du workflow ne suffit pas à décrire : la facture se règle et les
grilles se valident sans qu'aucune transition de la mission soit franchie.

C'est la démonstration, en un écran, de pourquoi ni la facturation ni les
évaluations ne sont pilotées par le graphe de la mission.

---

## Ce que ce protocole ne couvre pas — à annoncer

**Le client remplit sa grille depuis le back-office.** Même arbitrage qu'aux
Extensions 7 et 9 : l'écran portail relève de l'Extension 11. Les droits sont
déjà posés du bon côté — le client écrit sa grille tant qu'elle n'est pas
rendue, ne lit pas celle du cluster, et ne la réécrit plus une fois soumise.

**L'annuaire public n'affiche pas encore la réputation.** `public_reputation()`
existe et est testée ; la page qui la rend relève de l'Extension 12.

**Le mail ne part pas.** Le SMTP n'est pas configuré : les trois notifications
de cette extension — évaluation reçue, évaluation validée, renvoi pour
complément — se vérifient dans la cloche et dans `mail.message`.
