# Protocole de test manuel — Extension 7

**Sélection, affectation, contrat, ordre de mission.**
C'est le **jalon P0 du §20** : une mission naît d'un besoin client et aboutit à
un intervenant sélectionné avec son contrat généré.

Durée : ~35 min. Base `opex_mis_e1`.

```
.\venv\Scripts\python.exe .\odoo\odoo-bin -c odoo.conf -d opex_mis_e1 ^
    -u opex_intervenants --limit-time-real=0
```

`--limit-time-real=0` : sinon le serveur meurt au bout de deux minutes dès
qu'un onglet reste ouvert.

---

## À savoir avant de commencer

**`wkhtmltopdf` n'est pas installé sur ce poste.** Le bouton natif
« Imprimer » d'Odoo lèvera *« Unable to find Wkhtmltopdf on this system »*.
C'est une limite de machine, pas du module : les deux rapports sont déclarés
en `qweb-pdf` et produiront un PDF le jour où le paquet sera là.

Le bouton **« Aperçu »** de la fiche ouvre le même gabarit en HTML, par la
route native `/report/html/...`, et fonctionne aujourd'hui. **C'est celui du
protocole.**

Même catégorie que le SMTP absent : à annoncer, pas à découvrir.

---

## Partie 1 — Le parcours jusqu'à la sélection (10 min)

Reprend les extensions 1 à 6 ; l'objet ici est d'arriver à une candidature
retenue.

1. Compte **client** → `/my/missions/new`, déposer une demande complète.
   Cocher **NDA exigé** dans l'écran Confidentialité — on le vérifiera plus loin.
2. Compte **secrétariat** → back-office, *Appels à mission* → Action →
   **Lancer le sourcing**, puis **Ouvrir les candidatures**.
3. Compte **intervenant** → `/missions`, l'appel, **Je suis intéressé**,
   remplir la candidature Lean, déposer.
4. Compte **responsable** → *Pool de candidatures* → qualifier, mettre en
   short-list.
5. Compte **comité** → Action → **Retenir cette candidature**, avec un motif.

**À vérifier immédiatement après le clic**, sur la fiche de la candidature :

| Point | Attendu |
|---|---|
| Chatter de la candidature | un message « Votre candidature est retenue » |
| *Affectations* (menu) | une ligne, avec le tarif et la durée **recopiés** |
| *Contrats et ordres de mission* | **trois** pièces : contrat, ordre de mission, **NDA** |
| Chatter de la **mission** | une note listant les candidatures restées ouvertes |

Le NDA n'apparaît que parce que l'appel l'exige. Refaire le parcours sans
cocher la case : deux pièces seulement.

**Aucun autre candidat n'a été écarté automatiquement.** C'est un arbitrage,
pas un oubli — voir la partie 5.

---

## Partie 2 — La règle 4, aux trois niveaux (7 min)

> « Une mission ne peut avoir qu'un intervenant sélectionné, sauf si le modèle
> de mission l'autorise explicitement. »

**1. Le niveau qui explique.** Faire monter un second candidat jusqu'en
short-list sur le même appel, puis Action → **Retenir cette candidature**.

Attendu : refus, et le message nomme la sortie de secours —
*« … cochez Plusieurs intervenants sur le type de mission »*. Le candidat reste
en short-list.

**2. Le niveau qui garantit.** *Affectations* → **Nouveau**, saisir la même
mission avec un autre intervenant, enregistrer.

Attendu : refus par la contrainte, message citant la règle 4. C'est ce niveau
qui tient face à un import ou à une requête forgée — le premier ne protège que
le chemin qui passe par la transition.

**3. L'exception.** Créer un appel de type **Formation** (`multi_intervenants`),
y retenir deux candidats.

Attendu : les deux passent, deux affectations. Les deux niveaux s'effacent
**ensemble** — ils lisent le même réglage.

---

## Partie 3 — La contractualisation (10 min)

1. Sur la mission : Action → **Attribuer la mission** (motif obligatoire), puis
   Action → **Lancer la contractualisation**.

2. Ouvrir l'onglet **Contractualisation** de la fiche.

   | Point | Attendu |
   |---|---|
   | L'encart bleu | « Contractualisation : **Contrat en préparation** » |
   | Le bouton | « Faire avancer la contractualisation » |
   | La barre d'état en haut | inchangée, sur **Contractualisation** |

   **Deux boutons d'action sur la même page, et c'est voulu.** Celui de
   l'en-tête fait avancer la *mission* ; celui de l'onglet fait avancer la
   *contractualisation*. Ce sont deux instances de workflow sur le même
   enregistrement.

3. **Essayer de démarrer la mission maintenant** : Action → **Démarrer la
   mission**.

   Attendu — **c'est la règle 5 du §39** :

   > Le contrat n'est pas validé : la mission ne peut pas démarrer
   > (règle 5 du §39).

   La mission ne bouge pas. Ce n'est pas un `if` dans une méthode : c'est une
   condition sur la transition, et le moteur en consigne le résultat dans
   l'historique.

4. Dérouler le cycle du §19, par le bouton de l'onglet :
   **Soumettre à relecture** → **Envoyer à la signature**.

   « Envoyer à la signature » refuse si le contrat n'a ni dates ni montant.
   Pour le voir : ouvrir la pièce, vider le **Montant**, réessayer.

5. Ouvrir le **contrat** (menu *Contrats et ordres de mission*, filtre
   « Version en vigueur »). Cliquer **Aperçu**.

   Attendu : le document du §18 — parties, objet, durée, montant, livrables,
   modalités de validation, et un bloc signatures portant
   **« En attente de signature »** des deux côtés.

   Une case cochée d'avance sur un document qu'on fait signer serait un faux.

6. Toujours sur la pièce : **Enregistrer la signature du client**, puis
   **… de l'intervenant**. Les deux dates apparaissent, nominatives.

   Avant de signer les deux, essayer **Signatures recueillies** depuis
   l'onglet Contractualisation : refus, *« Le contrat n'est pas signé des deux
   côtés »*.

7. **Signatures recueillies** → **Valider le contrat**.

   Attendu : l'encart passe à « **Contrat validé — la mission peut démarrer** »,
   et le client comme l'intervenant reçoivent un message.

---

## Partie 4 — Le piège du refus (5 min)

**C'est le point de conception de l'extension.** À faire sur un **second**
appel, mené jusqu'à « Contrat en relecture ».

1. Onglet Contractualisation → **Demander une révision**, avec un motif.
2. L'encart affiche « Révision du contrat demandée ».
3. **Essayer Action → Démarrer la mission.**

   Attendu : **refus**, avec le message de la règle 5.

Pourquoi c'est le point qui compte : le moteur pose `state = 'done'` en
atteignant **n'importe quelle** étape finale, et `subworkflow_done()` teste
exactement `state = 'done'`. Si « Révision demandée » était marquée finale, un
contrat **refusé** satisfairait la règle 5 — la mission démarrerait parce que
sa contractualisation a échoué.

Une seule case cochée par mégarde suffirait, et **`_check_graph()` ne dirait
rien** : deux étapes finales sont un graphe parfaitement valide. C'est mesuré —
la casse a été jouée, la définition s'est publiée sans un mot, et seuls les
deux tests dédiés l'ont signalée.

4. Revenir : **Nouvelle version préparée**, puis reprendre le cycle.

---

## Partie 5 — Le démarrage et l'exécution (5 min)

Sur le premier appel, contrat validé :

1. Action → **Démarrer la mission**. Elle passe en **Mission en cours**.

2. Ouvrir l'**affectation** : le bouton *Tâches* apparaît.

   | Point | Attendu |
   |---|---|
   | Un projet | nommé comme la mission, rattaché au client |
   | Les tâches | « Cadrage et lancement », une par ligne de **Résultats attendus**, « Remise des livrables » |
   | Les échéances | toutes datées — c'est le « calendrier » du §13 |
   | L'assignation | l'intervenant retenu |

   Les tâches intermédiaires viennent de ce que **le client a écrit**. C'est
   provisoire et assumé : l'Extension 8 posera `opex.mission.deliverable`, et
   c'est de là qu'elles viendront.

3. **Aucun projet n'existait avant.** Le §13 range la création du projet
   parmi les effets de la sélection, mais dit « selon configuration » : placée
   là, chaque contractualisation échouée aurait laissé un projet orphelin.

4. **L'intervenant est maintenant acteur de la mission.** Ouvrir l'instance
   (*Smart Workflow → Dossiers*), onglet Acteurs : une ligne `intervenant`, en
   accès **limited**. C'est le manque que l'Extension 1 avait déclaré, refermé.

---

## Partie 6 — L'indépendance des deux machines, jusqu'au bout (3 min)

Sur la mission menée en `in_progress` :

| Point | Attendu |
|---|---|
| Étape de la mission | **Mission en cours** |
| Étape de la candidature retenue | **Retenu** — elle n'a pas bougé |
| Instances sur ces deux enregistrements | **trois** : `mission_request`, `mission_application`, `mission_contract` |

Trois processus vivent en même temps sur deux enregistrements, et aucun ne
dérive d'un autre. C'est la démonstration du module à son point le plus dense.

Pour le voir : *Smart Workflow → Dossiers*, filtrer sur la mission.

---

## Ce que ce protocole ne couvre pas

- **La signature depuis le portail.** Elle est enregistrée depuis le
  back-office, horodatée et nominative. L'écran portail relève de
  l'Extension 11 ; le droit d'écriture n'a pas été ouvert avant que cet écran
  existe.
- **Le PDF.** Voir l'avertissement en tête.
- **Les livrables et le service fait.** Extensions 8 et 9. Les règles 6 du §39
  restent déclarées et rattachées à rien, volontairement — elles sont
  **fermées** par défaut tant que leur champ n'existe pas.
