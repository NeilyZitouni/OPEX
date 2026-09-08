# Notes de version — Portail Digital du GIC OPEX Group

## Période couverte

**Du 5 août 2026 au 7 septembre 2026** — soit l'intégralité de l'histoire du
projet.

Le dépôt ne comporte **aucune étiquette de version ni aucune release antérieure** :
cette note est donc la première, et elle couvre les 31 enregistrements de travail
depuis la création du dépôt jusqu'au dernier en date.

| Composant | Version |
|---|---|
| Moteur de processus | 19.0.1.8.0 |
| Module 1 — Adhésion et vie du cluster | 19.0.1.19.1 |
| Module 2 — Innovation Booster | 19.0.1.24.0 |
| Module 3 — Smart Missions | 19.0.21.0.0 |
| Module de comparaison — Smart Crowdfunding | 19.0.1.0.0 |
| Service d'assistance IA | 19.0.1.0.0 |

*Ces numéros ont été relevés à la fois dans les fichiers du dépôt et dans la base
de données d'exécution ; ils concordent.*

---

## Résumé

Cette version livre le **portail digital complet du cluster GIC OPEX Group** :
six composants logiciels, 1 288 tests automatisés, trois domaines métier ouverts
au public et un moteur de processus générique sur lequel ils reposent tous.

Le fil conducteur du projet tient en une phrase : **les processus métier ne sont
pas programmés, ils sont paramétrés.** Le parcours d'une demande d'adhésion, la
vie d'un projet d'innovation, le cycle d'une mission d'expertise sont décrits dans
des écrans de configuration, pas dans du code. **Treize processus tournent
aujourd'hui sur ce principe** — six dans le domaine de l'innovation, sept dans
celui des missions — et un test automatisé vérifie qu'aucun vocabulaire métier ne
s'est glissé dans le moteur pour les accueillir.

Concrètement, un utilisateur peut désormais, **entièrement depuis le site web** :

- demander à adhérer au cluster, suivre l'instruction de son dossier, signer la
  charte, payer sa cotisation et consulter l'annuaire des membres ;
- déposer un projet d'innovation, le voir évalué par un comité, recevoir une
  demande de correction, être mis en relation avec un expert ou un investisseur,
  et suivre son accompagnement ;
- publier un appel à mission, recevoir et comparer des candidatures venues de
  quatre canaux différents, sélectionner un intervenant, produire son contrat,
  suivre ses livrables, prononcer le service fait et l'évaluer.

Une **assistance par intelligence artificielle** complète le dispositif pour
l'accueil des intervenants : lecture de CV, rapprochement avec un référentiel de
compétences, contrôle qualité d'un profil. Elle est conçue pour **proposer et
jamais décider** — et pour que son absence n'empêche rien.

---

## Ce que chaque composant apporte

### Le moteur de processus

C'est la fondation, et c'est la partie la plus réutilisable du projet.

Un administrateur peut désormais **décrire un processus métier complet sans écrire
une ligne de programme** : les étapes, les chemins entre elles, qui a le droit
d'emprunter quel chemin, les conditions à remplir, et ce qui doit se déclencher
au passage. Le moteur se charge du reste : contrôle des droits, motifs
obligatoires, journal d'audit inaltérable, relances automatiques quand un dossier
traîne.

Six types d'effets peuvent être attachés à un changement d'étape : prévenir des
acteurs, inscrire une valeur, créer une tâche, envoyer un courriel, démarrer un
sous-processus, lancer une mise en correspondance.

Le moteur inclut aussi un **système de mise en correspondance pondéré** — c'est
lui qui rapproche un projet d'un investisseur, ou une mission d'un expert — dont
la particularité est de **toujours expliquer son score** : quels critères ont été
satisfaits, lesquels manquaient, lesquels ont pénalisé. Un classement qu'on ne
peut pas justifier n'est pas défendable.

**La preuve que le principe tient :** un même processus de financement participatif
a été construit deux fois, une fois programmé « en dur » et une fois configuré sur
le moteur. Puis on a demandé aux deux d'accueillir une étape supplémentaire avec
trois conditions. Côté moteur, l'opération se fait **par simple paramétrage**, et
un test automatisé vérifie qu'aucun vocabulaire métier ne s'est glissé dans le
code du moteur au passage.

### Module 1 — Adhésion et vie du cluster

Un candidat dépose son dossier d'adhésion en **sept écrans successifs**, avec
sauvegarde automatique entre chaque : il peut s'interrompre et reprendre. Il joint
ses pièces, soumet, et voit son dossier progresser. S'il manque quelque chose,
il reçoit une demande de correction et renvoie son dossier corrigé.

Côté cluster, le secrétariat instruit, le comité d'admission rend un avis, le
comité de pilotage décide — **trois rôles distincts, avec trois vues distinctes du
même dossier**. Tout se fait depuis le site, sans passer par l'écran de gestion.

Une fois l'adhérent actif, sa cotisation est générée automatiquement. Il la
consulte, la renouvelle, dépose sa preuve de paiement, télécharge son reçu. Les
cotisations échues sont relancées automatiquement chaque jour.

Le module apporte enfin l'**animation du réseau** : annuaire public filtrable,
fiche publique par membre, page de présentation du cluster, et un espace réservé
aux membres regroupant actualités, événements avec inscription, formations avec
inscription, bibliothèque documentaire et groupes de travail.

### Module 2 — Innovation Booster

Premier domaine métier construit **entièrement sur le moteur** — aucun
enchaînement d'étapes n'y est programmé.

Un porteur de projet dépose son dossier en cinq écrans. Le projet suit ensuite un
parcours à quinze étapes : contrôle administratif, qualification, évaluation par
un comité sur une grille structurée, décision, et le cas échéant **remédiation** —
c'est-à-dire une demande de correction ciblée, avec retour du porteur, plutôt
qu'un simple refus.

La confidentialité des avis d'évaluation est tenue : un évaluateur ne voit pas
l'avis de son voisin, et le porteur ne reçoit que ce que le comité a décidé de
lui communiquer.

Vient ensuite la mise en correspondance : le projet est rapproché d'experts et
d'investisseurs sur sept critères pondérés, chacun avec son explication. Les
experts et investisseurs disposent d'un espace « mes opportunités » où ils
consultent et manifestent leur intérêt.

L'accompagnement s'organise en **feuille de route par phases**, avec des livrables
qui suivent eux-mêmes un cycle de validation à versions successives : dépôt,
examen, demande de correction, nouvelle version, validation. Le projet se conclut
par une évaluation finale que le porteur remplit depuis le portail.

Dix-neuf notifications jalonnent ce parcours, **toutes déclenchées par la
configuration** : personne n'a besoin de chercher dans le code pourquoi un message
est parti.

### Module 3 — Smart Missions

Le domaine le plus étendu du projet, et celui qui démontre le mieux la valeur du
moteur : **deux processus tournent en parallèle sur des objets liés**, et ne se
dérivent jamais l'un de l'autre. L'avancement d'un appel à mission et le parcours
individuel de chaque candidature sont deux histoires distinctes — un appel en
phase de sélection porte simultanément des candidatures en liste restreinte,
d'autres écartées, d'autres tout juste déposées.

**Pour le client.** Il exprime son besoin en cinq écrans, suit ses demandes, ses
appels en cours, ses missions en cours et terminées depuis un tableau de bord
dédié. Sa demande n'est pas publiée automatiquement : elle passe par une
qualification du cluster.

**Pour le cluster.** Le responsable qualifie l'appel, choisit son mode de sourcing
— recherche ciblée, publication au portail, ou les deux — et lance la mise en
correspondance. Celle-ci évalue les candidats sur sept critères pondérés,
ajustables par type de mission et même appel par appel. Deux points sont
structurants :

- **les critères éliminatoires sont traités avant le score.** Un candidat qui ne
  détient pas une certification obligatoire est **écarté du vivier**, pas mal
  noté — et le motif de son exclusion est écrit ;
- **le score s'explique toujours.** Le responsable voit ce qui a compté, ce qui
  manquait, et le poids de chaque critère.

**Pour l'intervenant.** Un expert déjà référencé au cluster **ne ressaisit jamais
son profil permanent** pour candidater : seules les données propres à la mission
lui sont demandées — disponibilité, tarif, délai, approche. Un candidat externe,
lui, crée un mini-profil et peut ensuite intégrer le référentiel. Il entretient
son capital professionnel — compétences, expériences, certifications,
disponibilités — depuis son espace portail.

**Le vivier est unique.** Que la candidature vienne de la recherche ciblée, du
portail public, d'une invitation ou d'une saisie manuelle, elle atterrit dans le
même objet et se compare dans le même écran. C'est un critère d'acceptation du
projet, et il est vérifié par un test qui mesure la **comparabilité**, pas
seulement la cohabitation.

**Après la sélection**, la chaîne se déroule : affectation, contrat et ordre de
mission générés, signature depuis le portail des deux côtés, démarrage de la
mission — automatiquement à la date convenue —, suivi des livrables avec versions
et motifs de refus, points d'avancement, incidents, puis constat de service fait
avec double validation (cluster, puis client) et possibilité de contestation.

**La boucle se referme** par l'évaluation croisée : le client note l'intervenant
sur six critères, le cluster sur six autres. Une évaluation validée alimente la
réputation de l'intervenant, qui alimente à son tour la mise en correspondance des
missions suivantes.

Quatre tableaux de bord distincts — responsable, intervenant, candidat externe,
client — et une file de travail priorisée (Urgent / À traiter / Terminé) complètent
l'ensemble, avec une page d'accueil unique reliant les trois domaines du portail.

### Assistance par intelligence artificielle

Trois fonctions, toutes conçues sur le même principe : **l'IA prépare, l'humain
tranche.**

1. **Lecture de CV.** Un CV déposé est analysé et neuf catégories d'informations en
   sont extraites. Rien de ce que produit l'IA n'entre directement dans le profil :
   tout atterrit dans des **propositions**, chacune portant sa valeur, son degré de
   confiance, et **la citation exacte du passage du CV d'où elle vient**. La
   promotion en donnée validée est un geste humain, tracé.

2. **Rapprochement avec le référentiel de compétences.** Un libellé de CV est
   d'abord rapproché **sans aucun appel à l'IA** — correspondance exacte, puis table
   de synonymes. L'IA n'intervient que pour ce qui n'a pas été reconnu, et sa
   proposition reste une proposition. Ce qui n'est rapproché ni dans un cas ni dans
   l'autre part en **file d'arbitrage**, où un gestionnaire décide — et c'est ainsi
   que le référentiel s'enrichit. Conséquence importante : **le portail reste
   pleinement utile sans clé d'API.**

3. **Contrôle qualité d'un profil.** Sept contrôles, dont quatre entièrement
   déterministes (champs manquants, dates incohérentes, certifications expirées,
   doublons) qui s'exécutent **avant** tout appel à l'IA. Trois autres relèvent du
   jugement et sont instruits par l'IA. Trois garde-fous encadrent l'ensemble : le
   contrôle ne fait jamais avancer un dossier, aucune décision d'activation ne
   dépend d'un avis d'IA, et **un signalement produit par l'IA ne peut jamais être
   bloquant**.

Le service d'appel lui-même est un composant à part, sans métier. Sa règle
première : **sans clé d'API, il renvoie « rien » et ne lève aucune erreur.** Aucun
parcours métier ne peut être interrompu par l'absence d'IA. Il journalise chaque
appel — usage, coût estimé, durée — mais **ne conserve ni la question ni la
réponse** : un CV contient des données personnelles, et un journal de supervision
n'est pas un endroit où les garder.

### Module de comparaison — Smart Crowdfunding

Ce composant n'est pas un domaine métier de plus. C'est **la moitié d'une
expérience** : le même processus de financement participatif, implémenté
délibérément « à l'ancienne » — états codés en dur, transitions programmées — pour
être mis en regard du même processus configuré sur le moteur.

Il est fonctionnellement complet : dépôt express, portail porteur, pré-analyse à
quatre issues, dossier progressif à branches, contrôle qualité à trois issues,
décision du dirigeant à trois routes, mise en correspondance financière sur dix
critères, accompagnement avec missions et jalons, mise en relation contrôlée avec
les acteurs financiers, décision du financeur, closing avec échéancier et
versements, quatre interfaces d'acteurs et file de travail.

Il est **isolé par construction** : il ne dépend d'aucun autre composant du
portail, ce qui est la condition de validité de la comparaison.

---

## Corrections notables

Ces corrections portent sur des défauts réels, observés, qui avaient une
conséquence pour un utilisateur. Les ajustements techniques mineurs ne sont pas
listés.

**Un lien de notification menait à une page inexistante.** La cloche du portail
prévient le client qu'une candidature a été déposée sur son appel. Le lien de cette
notification était déduit du type de document concerné et menait donc vers l'écran
du candidat — un écran auquel le client n'a pas accès. Il obtenait une erreur 404.
Le lien est désormais résolu **en fonction du lecteur**, et non du document.
Ce défaut n'était visible qu'en cliquant réellement dans un navigateur : les tests
automatisés vérifiaient que le lien ressemblait à une adresse de portail, ce qui
était vrai.

**Trois liens du Module 3 renvoyaient une erreur 404 depuis l'origine du module.**
Notamment celui que tout intervenant recevait dans sa propre notification. Les
adresses n'avaient jamais été déclarées. Un contrôle automatisé confronte
désormais **chaque adresse écrite dans le projet — dans les pages, les modèles
et les redirections — à la liste réelle des adresses enregistrées par le
serveur**, sur l'ensemble des composants installés.

Le point à retenir dépasse le défaut lui-même : deux tests censés protéger cette
adresse la validaient en la **reconstruisant de la même façon que le code testé**.
Les deux côtés de la comparaison étaient donc faux de la même manière, et
l'égalité tenait. Corriger le code sans corriger le test aurait fait rougir le
test.

**Le bouton « Devenir membre » ne fonctionnait pas, et pas toujours de la même
façon.** Deux causes s'additionnaient. D'abord, le même intitulé existait à quatre
endroits avec deux adresses différentes, ce qui produisait un comportement
apparemment aléatoire. Ensuite, l'écran de configuration d'Odoo affichait un
réglage d'inscription qui **n'était pas celui réellement appliqué** — le site web
en surcharge un autre. Le parcours ne dépend plus d'aucun réglage d'inscription.
Enfin, la correction avait d'abord été appliquée à l'entrée de menu de référence
sans atteindre **sa copie propre au site**, qui est celle réellement servie au
visiteur : la page publique affichait encore le lien mort alors que tout le reste
disait le contraire.

**Des refus d'accès étaient indistinguables d'une panne.** Un utilisateur sans les
droits requis était silencieusement renvoyé sur son profil, sans un mot. Il
recommençait, croyait à un bug, et le signalait comme tel — ce qui s'est
effectivement produit. Neuf de ces cas affichent désormais une page portant leur
motif, formulé pour **orienter** et non seulement constater. Trente et un cas
subsistent sur des écrans internes ; voir « Limites connues ».

**Un formulaire de candidature ne s'affichait jamais.** La page annonçait que la
candidature était déposée alors que l'étape était bien celle où le candidat doit
écrire. La cause : une variable d'affichage portait un nom générique du
framework, qui l'écrasait silencieusement.

**Un dépôt en double faisait tomber la page en erreur 500** au lieu d'afficher un
message. Une contrainte de base de données rejetée place la transaction entière
en état abandonné — y compris le rendu de la page d'erreur. Le motif correct est
désormais appliqué partout où une contrainte peut se déclencher depuis le portail.

**Une valeur de filtre illisible faisait tomber une page publique.** Sur le
catalogue des missions, ouvert à tout visiteur, une date mal formée atteignait la
requête de recherche et provoquait une erreur 500. Sur une page publique, **ne pas
filtrer vaut mieux que ne pas répondre** : les valeurs sont désormais validées et
un filtre illisible est ignoré.

**Une correspondance ambiguë choisissait au hasard.** Le référentiel de
compétences contenait deux entrées que la normalisation rend identiques (l'une
accentuée, l'autre non). Un expert était qualifié sur l'une des deux
indifféremment, et la mise en correspondance comparait à celle que la mission
avait choisie : deux fois sur trois, personne ne se croisait — sans qu'aucune
erreur ne soit levée. Une correspondance ambiguë **refuse désormais de choisir** et
part en arbitrage.

**Le critère de certification obligatoire comparait du texte libre**, avec trois
défaillances mesurées : un candidat déclarant une certification de niveau inférieur
passait ; un candidat écrivant le même intitulé sans espace était écarté à tort ;
et exiger deux certifications revenait à n'en exiger qu'une. Un référentiel
canonique est désormais utilisé des deux côtés, avec exigence cumulative. Cette
dette technique était **annoncée dans la documentation avant d'être refermée**,
pas découverte.

**Une faute de frappe dans la configuration supprimait silencieusement un critère
éliminatoire**, laissant entrer des candidats qui auraient dû être écartés. La mise
en correspondance **refuse désormais de s'exécuter** si un critère éliminatoire
désigne un champ inexistant : une liste contenant des candidats qui n'auraient pas
dû y être est pire qu'une absence de liste.

**Un caractère décoratif portait une décision.** Un nettoyage typographique
généralisé a retiré un symbole d'avertissement qui servait, sans que ce soit
apparent, à distinguer les motifs éliminatoires des simples avertissements. Plus
aucun candidat n'était écarté du vivier — et rien ne ressemblait à une panne : la
liste des propositions était simplement plus fournie. Seuls trois tests dédiés
l'ont signalé.

**Une fuite de notifications internes vers les adhérents** a été corrigée dans le
Module 1 : des messages destinés à l'instruction interne partaient au candidat.

---

## Limites connues et dette technique assumée

Cette section est volontairement complète. Aucun de ces points n'est un défaut
caché : tous sont documentés dans le dépôt.

### Ce qui est désactivé sur le serveur cible

Trois composants d'Odoo ne sont pas disponibles sur l'instance de déploiement. Les
exiger aurait rendu le Module 3 **totalement non installable** — Odoo refuse en
bloc un composant dont une dépendance manque. Ils sont donc résolus au moment de
l'appel, et leur absence **éteint** des fonctions sans en casser aucune.

| Absent | Conséquence | Ce qui continue de fonctionner |
|---|---|---|
| Module **Ventes** | Aucune commande de vente ni facture n'est émise à la clôture d'une mission | Tout le processus de service fait : constat, double validation, contestation, reprise, clôture |
| Module **Projets** | Aucun projet ni tâche n'est créé au démarrage d'une mission | Tout le suivi d'exécution — livrables, avancement, incidents — qui ne passe pas par les tâches d'Odoo |

Dans les deux cas, **le dossier dit ce qui n'a pas eu lieu** : une note est déposée
sur la mission, et la situation affiche « Facturation indisponible » plutôt que
« Non facturée ». La distinction est volontaire : la première phrase décrit un
portail qui ne sait pas facturer, la seconde une mission qu'on n'a pas encore
facturée.

⚠ **Le Module 3 est propre de ces dépendances, mais il ne s'installera pas seul
pour autant** : elles reviennent par la chaîne, le Module 2 déclarant « Projets »
et le Module 1 déclarant « Ventes ». Le travail restant est en amont, de même
nature et de moindre ampleur. Il n'a pas été engagé parce que ces deux modules
sont gelés depuis leur présentation.

### Fonctions accessibles au personnel uniquement

Ces fonctions existent, sont testées, mais ne sont pilotables que depuis l'écran
de gestion — pas depuis le site web :

- **toute la chaîne d'assistance IA** : dépôt de CV, propositions extraites,
  promotion, file d'arbitrage des libellés, contrôle qualité d'un profil. Un
  expert ne dépose pas son CV lui-même ;
- dans le Module 2 : le **suivi détaillé du financement**, l'**industrialisation**
  et le **bilan de clôture** d'un projet. Le porteur voit ces phases comme jalons
  d'avancement, sans écran de détail ;
- dans le Module 1 : les **comités** et l'**assemblée générale** ;
- dans le module de comparaison : l'écran web du personnel est **en lecture
  seule** — la saisie du dossier, les fiches de contrôle, la correspondance
  financière, l'accompagnement et le closing se font en gestion.

### Fonction à l'état d'ébauche

Les **votes en assemblée générale** (Module 1) existent sous forme d'ébauche
déclarée comme telle dans le code : sans comptage des voix, sans bulletin, sans
ouverture ni fermeture de scrutin. **À ne pas présenter comme disponible.**

### Livrable manquant

Le **document de synthèse comparatif** entre le processus programmé et le processus
configuré — le procès-verbal chiffré mettant en regard fichiers modifiés, lignes
de code, temps passé et compétence requise — **n'est pas dans le dépôt**. Les deux
moitiés de l'expérience sont réalisées et testées de part et d'autre, et l'opération
de référence (ajouter une étape « Demo Day » avec trois conditions) est automatisée
des deux côtés. **Seule la mise en regard chiffrée reste à écrire**, et c'est le
livrable final annoncé du projet.

### Dette technique ouverte

| Sujet | Impact | Statut |
|---|---|---|
| **31 écrans réservés au personnel renvoient sans explication** un utilisateur non habilité | Faible : ce sont des adresses internes, on n'y arrive pas par hasard | Reportée sciemment. Le critère de déclenchement est posé : si l'un devient atteignable par un lien envoyé à un candidat, il passe en tête |
| Le **lien entre une action et une étape n'est pas modifiable à l'écran** dans le moteur | Cette opération demande de modifier un fichier de configuration | Ouverte **volontairement**, pour préserver la validité de la mesure comparative, qui exige que le code du moteur n'ait pas changé |
| Le moteur **ne sait pas notifier une personne nommément**, seulement un rôle | Un envoi de message écrit à la main subsiste dans le Module 2 | Ouverte, même raison |
| Les certifications saisies en **texte libre avant** la mise en place du référentiel ne sont rapprochées par personne, et ne comptent donc pour aucun critère | Conséquence à annoncer, pas un défaut : un texte libre n'est comparable à rien | Une file « Non rapprochées » est prévue pour la vider |
| **Couverture de tests du Module 1** : 27 tests, dont 16 transversaux. Cotisations, paiements, annuaire, événements et espace cluster n'ont **aucun test automatisé dédié** | Ces fonctions ont été validées par essais manuels documentés | Le module étant gelé, l'ajout de tests demanderait de le rouvrir |

### Limites de poste, sans rapport avec le code

- **Aucun serveur d'envoi d'e-mails n'est configuré** : aucune notification ne part
  par courriel. Elles se vérifient dans la cloche du portail.
- **Le convertisseur PDF est installé sur le poste mais absent du chemin
  d'exécution** où Odoo va le chercher : les contrats et ordres de mission
  s'affichent en aperçu web au lieu d'un PDF. La correction est une ligne de
  configuration système.
- **Le projet Google associé à la clé d'API est refusé en génération** : les appels
  à l'IA n'aboutissent pas. Le module se comporte comme prévu — il journalise, ne
  rend rien, et rien ne casse.
- **Le fichier de démarrage par conteneurs est invalide** : sa première ligne
  s'écrit `ervices:` au lieu de `services:`. Correction : un caractère. Défaut
  introduit par le dernier enregistrement du dépôt.

### Hors périmètre — exclusions décidées

Aucun de ces points n'est un manque ; chacun dispose de son point d'extension.

Mise en correspondance sémantique par IA et apprentissage automatique (le score est
délibérément **pondéré et explicable** — un score inexplicable serait un défaut, pas
une qualité) · apprentissage à partir des missions passées · signature électronique
cryptographique, remplacée par une confirmation horodatée · salle de données
sécurisée · intégration bancaire réelle · éditeur graphique de processus · envoi de
SMS · agent IA de contrôle qualité **autonome** — celui qui est livré prépare et ne
décide jamais.

---

## Écarts entre la documentation de projet et le code livré

La documentation interne du projet a été relue au regard du code. Sept écarts ont
été relevés, **dont deux en faveur du code** :

1. Trois fonctions annoncées comme « accessibles en gestion seulement » — signature
   du contrat, validation du service fait par le client, remplissage de la grille
   d'évaluation — **ont en réalité un écran portail**, ajouté le 6 septembre.
2. Le module de comparaison annonce un périmètre réduit ; **les douze extensions
   sont en fait réalisées et testées**.
3. Le démarrage automatique des missions à échéance, livré le 7 septembre, **n'est
   documenté nulle part**.
4. La dette « refus d'accès sans motif » est chiffrée à 28 cas ; le compte réel est
   de **31**.
5. Les totaux de tests annoncés (515 et 1 048) sont périmés ; les comptes réels
   sont de **523** et **1 256** — **1 288** en incluant le service d'IA.
6. La version du moteur est annoncée à `19.0.1.15.0` ; la version réelle est
   `19.0.1.8.0`.
7. Le convertisseur PDF est annoncé « absent du poste » ; il est en réalité
   **installé mais hors du chemin d'exécution**.

Ces écarts s'expliquent par le rythme des trois derniers jours de développement,
postérieurs à la dernière mise à jour de la documentation.

---

## Vérification de cette version

La suite de tests a été **réellement exécutée** le 8 septembre 2026, et non
seulement dénombrée.

```
Portail (moteur, Modules 1-2-3, service IA)
    0 failed, 0 error(s) of 1029 tests

Module de comparaison, sur sa base dédiée
    0 failed, 0 error(s) of  259 tests
```

**Soit 1 288 tests exécutés, aucun échec.**

Le nombre de tests exécutés correspond exactement, composant par composant, au
nombre de tests présents dans les fichiers source — aucune suite n'a été
silencieusement ignorée :

| Composant | Tests |
|---|---|
| Moteur de processus | 164 |
| Module 1 — Adhésion et vie du cluster | 27 |
| Module 2 — Innovation Booster | 315 |
| Module 3 — Smart Missions | 491 |
| Service d'assistance IA | 32 |
| Module de comparaison | 259 |
| **Total** | **1 288** |

Le rechargement complet des composants — 76 modules, natifs d'Odoo compris —
s'est fait **sans le moindre avertissement**.

*Note de lecture : le journal contient quelques lignes d'erreur applicative. Ce
sont des erreurs **volontairement provoquées** par des tests qui vérifient que le
système les refuse bien. Seule la ligne de décompte finale fait foi.*

---

## Prochaines étapes suggérées

Par ordre de rapport sur l'effort :

1. **Corriger le fichier de démarrage par conteneurs** — un caractère, et le
   déploiement redevient possible.
2. **Ajouter le convertisseur PDF au chemin d'exécution** — une ligne, et les
   contrats et ordres de mission s'impriment.
3. **Écrire le document de synthèse comparatif** — c'est le livrable final annoncé
   du projet ; les deux moitiés de la mesure existent déjà.
4. **Mettre la documentation de projet à jour** sur les sept écarts relevés
   ci-dessus, en particulier les trois limites qui ne sont plus des limites.
5. **Refermer la dette des 31 refus d'accès muets** (environ une heure).
