# Protocole de test manuel — Extension 11

**Tableaux de bord et notifications** : les quatre espaces du §18, la
priorisation du §43, les trois listes du §34 et la cloche du portail.

Durée : ~35 min. Base `opex_mis_e1`.

```
.\venv\Scripts\python.exe .\odoo\odoo-bin -c odoo.conf -d opex_mis_e1 ^
    -u opex_intervenants --http-port=8072 --limit-time-real=0
```

**Comptes de démonstration** — créés par le script de peuplement, mot de passe
`demo1234` pour tous :

| Compte | Rôle | Espace du §18 |
|---|---|---|
| `demo_client` | portail | Client |
| `demo_expert` | portail | Intervenant, et candidat externe |
| `demo_manager` | Responsable de mission | Smart Work Queue |
| `demo_comite` | Comité de sélection | — |
| `demo_secretariat` | Secrétariat | — |

Si la base est vierge, rejouer le peuplement :

```
.\venv\Scripts\python.exe .\odoo\odoo-bin shell -c odoo.conf -d opex_mis_e1 ^
    --no-http < custom_addons\opex_intervenants\docs\seed_demo.py
```

Il crée les cinq comptes et trois missions dans trois états différents — une
menée jusqu'à l'exécution avec un livrable en retard, une demande fraîche à
qualifier, un appel ouvert avec une candidature déposée. Sans elles, les files
du §43 sont vides et le protocole ne montre rien. Le script est idempotent sur
les comptes ; relancé, il ajoute trois missions de plus.

**Ce protocole se fait console ouverte** (F12, onglet Console). C'est la seule
façon de vérifier le contrat de `/my/counters` : une clé de trop et tout le
JavaScript de l'accueil tombe, sans que le HTML rendu change d'un caractère.

---

## Partie 1 — Le contrat de `/my/counters` (5 min)

**C'est le point le plus fragile de l'extension, et il ne se voit qu'ici.**

1. Se connecter en `demo_expert`, aller sur `/my`, **console ouverte**.

**À vérifier** :

- aucune erreur dans la console. Les seuls messages acceptables viennent de
  `chrome-extension://...` — ce sont les extensions du navigateur, pas la
  page ;
- les quatre tuiles OPEX Intervenants sont présentes : *demander une
  intervention*, *mon espace*, *mon expertise*, *mes candidatures* ;
- les tuiles des autres modules sont là aussi — *Mes profils*, *OPEX
  Innovation*, *Mes évaluations*. Si elles ont disparu, la surcharge de
  `_prepare_home_portal_values()` n'appelle plus `super()`.

2. Onglet **Réseau**, filtrer sur `counters`, recharger la page.

**À vérifier** : la réponse de `/my/counters` ne contient **que** les clés
demandées. Une clé renvoyée sans nœud `[data-placeholder_count]`
correspondant fait lever `portal_home_counters.js`, ce qui rejette le
`Promise.all` et tue tout le JavaScript de l'accueil — pour tous les
utilisateurs, pas seulement pour la tuile fautive.

Les quatre clés du module sont `intervenants_mission_count`,
`intervenants_candidature_count`, `intervenants_expertise_count` et
`intervenants_espace_count`. Un test structurel exige la bijection entre les
clés que les controllers servent et les `placeholder_count` que les gabarits
posent ; il rougit si l'une des deux moitiés bouge seule.

---

## Partie 2 — L'espace intervenant, §41 (5 min)

Toujours en `demo_expert` : **Mon espace** ou `/my/intervenant`.

**À vérifier** — les cinq indicateurs du §41, dans l'ordre du document :

| Indicateur | Ce qu'il compte |
|---|---|
| Appels pertinents | les appels ouverts et publiés où il n'a **pas** déjà candidaté |
| Candidatures en cours | ses candidatures non refusées, non retirées |
| Missions en cours | ses affectations dont la mission tourne |
| Missions terminées | ses affectations dont la mission est validée ou clôturée |
| Note moyenne | sa réputation, celle du §32 |

Puis les quatre actions rapides, et la file **Ce qui vous attend**.

⚠ Un appel où il a déjà candidaté n'est **pas** compté en « appels
pertinents » : il est déjà dans la colonne d'à côté, et l'y compter deux fois
gonflerait le chiffre que l'expert regarde en premier.

---

## Partie 3 — La Smart Work Queue, §42 et §43 (8 min)

Se déconnecter, se connecter en `demo_manager`, aller sur `/staff/queue`
(ou depuis `/staff/missions`, bouton **Smart Work Queue**).

**À vérifier** — les sept indicateurs du §42 : demandes à traiter, appels
actifs, candidatures, missions en cours, livrables à valider, contrats en
attente, missions à clôturer.

Puis la priorisation du §43, en trois colonnes :

| Niveau | Ce qui doit y figurer |
|---|---|
| **Urgent** | livrable en retard, contrat en attente depuis plus de 3 jours, mission arrivant à échéance |
| **À traiter** | nouvelle candidature, nouvelle demande, livrable soumis |
| **Terminé** | mission validée, contrat signé, facture payée |

**Le test qui compte** : se reconnecter en `demo_client`, aller sur
`/my/missions`, descendre jusqu'à **Ce qui vous attend**.

La colonne **À traiter** du client doit afficher **« Rien en attente »**, alors
que celle du responsable montre la même candidature. C'est le §18 en une
image : « chacun voit ce qui le concerne ». Une candidature déposée n'est pas
une tâche du client — c'est le cluster qui la qualifie, et l'y ranger lui
donnerait une tâche qu'il ne peut pas exécuter.

Le livrable en retard, lui, figure dans les **trois** files — celle du
responsable, celle de l'intervenant qui doit le produire, celle du client qui
l'attend. C'est le même fait vu de trois côtés, et c'est correct.

---

## Partie 4 — Les trois listes du §34 (10 min)

Toujours en `demo_client` : cliquer sur la **cloche**, en haut à droite.

**À vérifier** — la liste du client du §34 s'y lit en toutes lettres :

- « Votre demande d'intervention est enregistrée. » — *demande reçue*
- « Votre demande est validée. » — *demande validée*
- « Une candidature a été déposée sur votre appel à mission. » — *candidature
  reçue*
- « Le contrat et l'ordre de mission sont disponibles pour signature. » —
  *contrat à valider*
- « Un livrable de votre mission vient d'être déposé. » — *livrable à valider*
- « La mission est terminée. » — *mission terminée*
- « Évaluez l'intervenant ayant réalisé votre mission. » — *évaluation à
  effectuer*

**Cliquer sur « Une candidature a été déposée »**.

**À vérifier** : le lien mène à la **fiche de la mission**, pas à la
candidature. C'est un défaut qui a été trouvé au navigateur et corrigé : le
message est posté sur la candidature, et le lien envoyait le client vers
`/my/candidatures/<id>` — un écran que l'`ir.rule` réserve au candidat. Il
tombait sur un **404**. L'URL se résout désormais pour le **lecteur**.

Se reconnecter en `demo_expert`, ouvrir la cloche : la liste de l'intervenant
du §34 s'y trouve — candidature déposée, présélection, sélection, contrat
disponible, livrable accepté ou refusé, mission terminée, évaluation.

⚠ **Aucun de ces messages n'est un `message_post()` écrit à la main.** Tous
sont des actions `notify` configurées sur les transitions. Pour le vérifier :
menu **Configuration → Workflows** du module `opex_workflow`, ouvrir une
transition — « Déposer ma candidature » par exemple — et regarder son onglet
Actions. On peut en détacher une sans toucher à une ligne de Python.

Un test lit le source de tous les modèles, sans les docstrings ni les
commentaires, et rougit si un `message_post` apparaît ailleurs que dans les
trois fichiers nommément autorisés — où il s'agit de comptes rendus posés sur
le dossier, pas de notifications à un rôle.

---

## Partie 5 — Le sous-type, et pourquoi il change (5 min)

Toujours en `demo_expert`, ouvrir sa candidature dans le back-office (compte
`demo_manager`, menu **Candidatures**), onglet du chatter.

**À vérifier** : sur la transition « Déposer ma candidature », trois messages
ont été postés, et pas avec le même sous-type.

| Destinataire | Sous-type | Pourquoi |
|---|---|---|
| l'intervenant | `comment` | c'est sa candidature, il doit recevoir l'accusé |
| le client | `note` | il n'est pas follower, mais **l'intervenant l'est** |
| le responsable | `note` | message interne |

Le cas du client est celui qui a imposé la règle : en `comment`, le message
destiné au client serait parti **par email au candidat**, pour un message qui
ne le concerne pas. En `note`, il atteint quand même le client dans sa cloche,
parce que `_execute_notify()` passe toujours `partner_ids` et que la seconde
source de la cloche lit précisément ce champ.

---

## Partie 6 — Le candidat externe, §18 (2 min)

En `demo_expert`, aller sur `/my/candidatures`.

« Catalogue public des missions, filtres, fiche mission, candidature courte et
**suivi de statut** » — les quatre premiers relèvent des Extensions 5 et 12 ;
le suivi est ici et existait déjà.

**À vérifier** : le candidat externe n'a **pas** de file du §43. C'est
délibéré — rien de ce qu'il pourrait y lire ne lui appartient : les urgences
d'un dossier sont celles de ceux qui l'instruisent.

---

## Ce que ce protocole ne couvre pas — à annoncer

**Deux items du §34 ne sont portés par aucune transition, et c'est déclaré.**

- **« Nouvel appel pertinent »** (liste intervenant) vise un *segment*
  d'experts, pas les acteurs d'un dossier. `_partners_for_roles()` résout les
  acteurs de l'instance ; un envoi à un segment n'en a aucun. Le §19 de la
  spécification le range d'ailleurs dans « notification aux segments
  d'experts pertinents » — c'est un envoi de masse, pas une action de
  transition. L'invitation ciblée par le matching, elle, existe depuis
  l'Extension 4.
- **« Retard »** (liste gestionnaire) n'est pas un événement de transition :
  il se constate en comparant une date à aujourd'hui. Il est porté par la
  colonne **Urgent** du §43, où il est visible en permanence plutôt qu'une
  fois au passage.

**Le mail ne part pas.** Le SMTP n'est pas configuré sur le poste. Les
notifications se vérifient dans la cloche et dans `mail.message` — c'est
précisément ce que fait ce protocole.

**Les quatre espaces sont des écrans de lecture.** Aucun n'ouvre de transition
que son acteur n'avait pas déjà ailleurs.
