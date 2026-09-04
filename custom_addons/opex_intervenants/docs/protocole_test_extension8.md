# Protocole de test manuel — Extension 8

**Exécution de la mission** : livrables, points d'avancement, incidents, et la
barre de progression du §40.

Durée : ~30 min. Base `opex_mis_e1`.

```
.\venv\Scripts\python.exe .\odoo\odoo-bin -c odoo.conf -d opex_mis_e1 ^
    -u opex_intervenants --limit-time-real=0
```

**Point de départ** : une mission en `Mission en cours`. Le protocole de
l'Extension 7 y mène ; si vous en avez déjà une, reprenez-la.

---

## Partie 1 — Le plan de mission (5 min)

**§22.** Sur la fiche de l'appel, onglet **Suivi d'exécution**.

1. Ajouter trois livrables dans la liste :

   | Jalon | Intitulé | Obligatoire | Échéance |
   |---|---|---|---|
   | Phase 1 — Cadrage | Note de cadrage | | dans 5 jours |
   | Phase 2 — Analyse | Rapport de vulnérabilités | | **hier** |
   | Phase 3 — Restitution | Support de présentation | | dans 20 jours |

2. Ouvrir le premier : il porte une **barre d'état à cinq positions** —
   À faire · En cours · Soumis · Corrections demandées · Validé — et un bouton
   **Action**.

   C'est la troisième définition de workflow du module et la neuvième du
   projet. Le cycle d'un livrable n'est pas un `Selection` avec des `if`
   autour : c'est une configuration, comme le reste.

3. Remplir **Critères d'acceptation** sur le premier. Le §22 les veut écrits
   **avant** le dépôt : ils évitent le « ce n'est pas ce que j'attendais »
   auquel l'intervenant n'a pas de réponse.

**À vérifier** : le second livrable, dont l'échéance est passée, apparaît en
**rouge** dans la liste et affiche un bandeau rouge sur sa fiche. C'est le
Urgent du §43.

---

## Partie 2 — Le dépôt et la validation (5 min)

**§24.**

1. Compte **intervenant** ou responsable, sur « Note de cadrage » :
   Action → **Commencer**. L'étape passe à *En cours*.

2. Action → **Soumettre à validation**, **sans joindre de fichier**.

   Attendu : refus —

   > Joignez le fichier du livrable avant de le soumettre à validation.

3. Joindre un fichier (onglet *Fichier*), puis **Soumettre à validation**.

   **À vérifier dans le chatter** : *« Un nouveau livrable a été soumis pour
   validation. »* — c'est le §24, tenu par une **action configurée** sur la
   transition, pas par un `message_post()` planté dans le code.

4. Compte **responsable** : Action → **Valider**.

   L'intervenant reçoit un message. En `comment` et non en `note` : la
   cloche portail écarte les `mt_note`, un compte portail ne verrait rien.

---

## Partie 3 — L'historique des versions (8 min)

**§25 — c'est le point de conception de l'extension.**

Sur « Rapport de vulnérabilités » : le commencer, joindre un fichier nommé
**`v1.pdf`**, le soumettre.

1. Compte **responsable** : Action → **Demander une correction**.
   Le motif est **obligatoire** — saisir : *« Le périmètre réseau manque. »*

2. Déposer la version 2. Deux chemins, tous deux valides :
   - depuis le back-office : remplacer le fichier par `v2.pdf`, puis
     Action → **Déposer une nouvelle version** ;
   - par la méthode `submit_new_version()`, qui fait les deux d'un coup.

3. Demander une **seconde** correction, avec un motif **différent** :
   *« Les recommandations ne sont pas hiérarchisées. »* Déposer `v3.pdf`.

4. Ouvrir l'onglet **Versions précédentes**.

   **À vérifier, et c'est tout l'enjeu** :

   | Version | Fichier | Motif |
   |---|---|---|
   | 1 | `v1.pdf` | Le périmètre réseau manque. |
   | 2 | `v2.pdf` | Les recommandations ne sont pas hiérarchisées. |

   **Chaque motif est sur sa version.** S'il vivait sur le livrable, le
   second aurait écrasé le premier et l'on ne saurait plus ce qui avait été
   reproché d'abord — c'est-à-dire justement ce que le §25 demande de
   conserver. C'est la leçon d'`opex_innovation`, reprise telle quelle.

   **Et v1 porte bien `v1.pdf`**, pas `v2.pdf`. L'archivage a lieu *avant*
   l'écriture ; l'inverse produirait un historique qui existe et ne contient
   rien d'utile — le pire des deux mondes, parce qu'on le croirait bon. La
   régression a été jouée : deux tests rouges, dont le message dit
   `'v2.pdf' != 'v1.pdf'`.

5. Ouvrir une version archivée et tenter de modifier son motif.

   Attendu : refus — *« Une version archivée d'un livrable ne peut pas être
   modifiée. »* Une archive modifiable ne prouve rien.

---

## Partie 4 — La condition de dépôt (4 min)

**Règle différée de l'Extension 1, qui trouve son champ ici.**

1. Sur la fiche de l'appel, onglet *Suivi d'exécution*, encadré
   **Garde-fous des règles 5 et 6 du §39** : « Livrables obligatoires non
   déposés » doit valoir **1** (le rapport est validé, la note de cadrage
   aussi, mais si vous avez suivi le protocole il en reste un).

   Sinon, ajouter un livrable **obligatoire** neuf pour la démonstration.

2. Action → **Soumettre les livrables**.

   Attendu : refus —

   > Tous les livrables obligatoires n'ont pas été déposés.

3. Déposer ce livrable, puis réessayer : la mission passe en
   **Livrables soumis**.

4. Vérifier que le livrable **facultatif** (« Support de présentation »,
   non déposé) n'a rien bloqué. Le §39 dit « les livrables **obligatoires** » :
   un document de confort qui bloquerait une transition ne serait jamais
   déposé par personne.

---

## Partie 5 — Le point d'avancement et les incidents (5 min)

**§21 et §26.**

1. Onglet *Suivi d'exécution* → **Points d'avancement** → ajouter une ligne :
   temps passé `3,5` jours, avancement `40 %`, travaux réalisés, **problèmes
   rencontrés**, prochaine étape.

2. Ajouter un second point à une date plus récente, avancement `65 %`, temps
   `2` jours.

   **À vérifier** en haut de l'onglet : *Avancement déclaré* = **65 %** (le
   dernier, pas la somme) et *Temps passé* = **5,5 jours** (la somme).

   Le temps se cumule, l'avancement se remplace. Les confondre donnerait
   105 %.

3. **Incidents** → ajouter : type *Retard*, priorité *Haute*, description
   *« Livrable intermédiaire non reçu. »*

   La référence est attribuée automatiquement — `INC-2026-0001`, l'exemple du
   §26.

4. Ouvrir l'incident : barre **Ouvert · En traitement · Résolu**, avec
   *Prendre en charge* puis *Marquer résolu*.

   **C'est un champ `Selection`, pas un workflow, et c'est assumé.** Le
   Schéma 10 du §26 donne un cycle linéaire : pas de chemin de refus, pas de
   condition, pas de rôle qui change. C'est la ligne de partage que le
   CLAUDE.md du moteur pose pour `roadmap.phase` — un compteur à trois
   positions n'est pas un processus. Un test verrouille le critère : si
   quelqu'un ajoute une quatrième issue, il rougit et la conversation a lieu.

5. Compte **intervenant** : essayer de créer un incident.

   Attendu : refus. Le §26 réserve le signalement au responsable ; l'intervenant
   décrit ses difficultés dans « Problèmes rencontrés » de son point
   d'avancement.

---

## Partie 6 — La barre de progression du §40 (3 min)

Compte **client**, sur `/my/missions/<id>`.

**À vérifier en haut de la page**, les huit jalons du document :

```
Demande   Appel   Sélection   Contrat   Mission
Validation   Facturation   Évaluation
```

Trois choses à regarder :

1. **Huit jalons, pas six.** Facturation et Évaluation n'ont aucune étape dans
   le graphe : elles attendent les Extensions 9 et 10. Elles figurent quand
   même — le §40 en compte huit, en afficher six ferait croire qu'on a réduit
   le périmètre. Un test le consigne et rougira quand l'Extension 9 leur
   donnera leur objet.

2. **Elle ne remplace pas** la liste « Où en est ma demande » juste en dessous.
   Les deux répondent à deux questions : la barre dit *où l'on en est dans le
   cycle de vie*, la liste dit *ce qu'il reste à faire sur ce dossier-ci*.

3. **Suspendre la mission** (Action → *Suspendre la mission*, motif
   obligatoire), puis recharger la page du client.

   Attendu : **aucun jalon n'est **. Une mission suspendue n'est pas
   « quelque part » sur la ligne du §40 — elle en est sortie, et la barre le
   dit au lieu d'inventer une position. Reprendre ensuite avec
   *Reprendre la mission*.

---

## Ce que ce protocole ne couvre pas

- **L'écran portail de dépôt d'un livrable.** Le dépôt se fait aujourd'hui
  depuis le back-office. L'espace intervenant du §41 relève de l'Extension 11 ;
  les `ir.rule` sont déjà posées pour lui (l'intervenant écrit tant qu'il est
  attendu, plus après).
- **Le service fait et la facturation** — Extension 9. La règle 6 du §39 a
  désormais son champ (`deliverable_unvalidated_count`) mais **reste rattachée
  à rien** : `mission_request_workflow.xml` dit sur « Valider le service fait »
  que c'est l'affaire de l'Extension 9, et on ne déborde pas.
- **Les notifications par email** : le SMTP n'est pas configuré. Elles se
  vérifient dans le chatter et dans la cloche portail.
