# Checklist des fonctionnalités — Portail Digital du GIC OPEX Group

**Date d'établissement :** 8 septembre 2026
**Périmètre :** les six modules `opex_*` du dépôt (`custom_addons/`)
**Dernier commit couvert :** `ff359c9` — 7 septembre 2026

---

## Comment cette liste a été établie

Chaque ligne a été vérifiée **contre le code source, les tests automatisés et les
adresses web réellement déclarées**, et non contre la documentation de projet.
Concrètement, quatre vérifications ont été faites pour chaque bloc :

1. le ou les fichiers de modèle de données existent et déclarent bien les objets
   annoncés ;
2. une adresse web (« route ») est effectivement enregistrée quand la
   fonctionnalité est censée être accessible depuis le portail ;
3. des tests automatisés portent sur la fonctionnalité, et leur nombre est relevé ;
4. la suite de tests complète a été **exécutée** sur les bases de données du poste
   (résultat en fin de document).

Quand la documentation de projet et le code divergent, l'écart est signalé
explicitement dans la section **« Écarts entre la documentation et le code »**
plutôt que tranché en silence.

**Point préalable, vérifié :** l'espace de travail est **propre** — aucun fichier
modifié ou non enregistré. Tout ce qui est décrit ci-dessous est bien versionné
dans le dépôt. Le cas « fait mais pas enregistré » ne se présente donc nulle part.

### Légende

| Symbole | Signification |
|---|---|
| ✅ | **Terminé** — codé, testé, et accessible depuis le site web quand la fonction s'adresse à un utilisateur externe |
| 🟡 | **Partiel** — la fonction existe mais avec une restriction précisée en clair (accessible seulement depuis l'interface d'administration, non testée, dépendante d'un composant absent…) |
| ❌ | **Non fait** — absent du code, ou présent seulement à l'état d'ébauche |
| 🔒 | **Limite déclarée** — fonction volontairement bornée, décision documentée et assumée |
| ⛔ | **Hors périmètre** — explicitement exclu du projet |

### Deux mots de vocabulaire

Le projet distingue en permanence deux interfaces, et la distinction porte
l'essentiel des mentions « partiel » de cette liste :

- **le portail** — le site web public, celui que voient les adhérents, les
  porteurs de projet, les intervenants et les clients ;
- **l'interface d'administration** (« back-office ») — l'écran de gestion
  d'Odoo, réservé au personnel du cluster.

Une fonction disponible seulement en interface d'administration est **utilisable**,
mais par le personnel uniquement : un adhérent ou un intervenant ne peut pas s'en
servir lui-même.

---

## Vue d'ensemble

Le portail est composé de six modules. Cinq forment le portail proprement dit ;
le sixième est un module de comparaison, volontairement isolé.

| Module | Rôle | Objets métier | Tests automatisés | État global |
|---|---|---|---|---|
| Moteur de processus | Décrit et exécute les processus métier sous forme de paramétrage | 16 | 164 | ✅ |
| Module 1 — Adhésion et vie du cluster | Adhésion, cotisations, annuaire, animation du réseau | 18 | 27 | 🟡 |
| Module 2 — Innovation Booster | Projets d'innovation, évaluation, accompagnement, financement | 20 | 315 | ✅ |
| Module 3 — Smart Missions | Appels à mission, sélection d'intervenants, exécution, réputation | 35 | 491 | ✅ |
| Module de comparaison (Crowdfunding) | Le même processus codé « en dur », pour mesure comparative | 18 | 259 | ✅ |
| Service d'assistance IA | Point d'appel unique vers un modèle de langage | 3 | 32 | ✅ |

**Total : 1 288 tests automatisés déclarés, 110 objets métier.**

---

# 1. Le moteur de processus (`opex_workflow`)

C'est la pièce centrale du projet. Un « processus » — le parcours d'une demande
d'adhésion, la vie d'un projet d'innovation, le cycle d'une mission — n'est pas
programmé : il est **décrit sous forme de données**, dans des écrans de
paramétrage. Les modules métier ne codent donc aucun enchaînement d'étapes.

| Fonctionnalité | État | Vérification |
|---|---|---|
| Configurateur de processus : définitions, étapes, transitions, rôles, règles, actions | ✅ | 16 modèles de données, 16 tests dédiés |
| Contrôle de cohérence d'un processus avant publication (aucune étape sans issue, au moins une étape finale) | ✅ | Refus de publication testé |
| Exécution : avancement d'un dossier, contrôle des droits à chaque passage | ✅ | 26 tests |
| Journal d'audit — qui a fait avancer quoi, quand, avec quel motif | ✅ | Historique consultable, jamais modifiable |
| Assistant de changement d'étape avec motif obligatoire quand la configuration l'exige | ✅ | 10 tests |
| Six types d'actions déclenchables sur un changement d'étape : notifier, écrire une valeur, créer une tâche, envoyer un email, démarrer un sous-processus, lancer une mise en correspondance | ✅ | 21 tests |
| File de travail par rôle | ✅ | |
| Droits d'accès attribués dossier par dossier, selon le rôle tenu sur ce dossier | ✅ | 26 tests, 10 règles d'accès |
| Formulaires de saisie configurables, rendus au portail | ✅ | 19 tests |
| Moteur de mise en correspondance pondéré, avec explication du score | ✅ | 23 tests |
| Sous-processus imbriqués | ✅ | Utilisé par le Module 3 pour la contractualisation |
| Surveillance des délais (relance automatique quotidienne) | ✅ | Tâche planifiée active |
| Portail générique : un dossier piloté par le moteur est consultable par son porteur | ✅ | |
| **Déplacer une action d'une étape à l'autre à la souris** | 🟡 | Le lien entre une action et une transition n'est exposé dans **aucun écran de paramétrage** : cette opération se fait aujourd'hui en modifiant un fichier de configuration. Vérifié : aucune mention dans les 9 fichiers de vues du moteur. Correction estimée à quelques lignes. |
| **Notifier une personne nommément** (et non un rôle) | 🟡 | Le moteur n'adresse ses notifications qu'à des **rôles**. Conséquence mesurée : le Module 2 conserve un envoi de message écrit à la main pour prévenir un expert précis. |

**Décision structurante à connaître :** ces deux manques ont été **identifiés et
volontairement laissés en l'état**, pour préserver la validité d'une mesure
comparative (voir §5) qui exige que le code du moteur n'ait pas été modifié.
Ce n'est pas un oubli.

---

# 2. Module 1 — Adhésion et vie du cluster (`opex_membership`)

Le module le plus ancien du projet, **gelé** depuis sa présentation : il n'est
plus modifié, et les modules suivants l'étendent depuis chez eux plutôt que d'y
toucher.

## 2.1 Adhésion

| Fonctionnalité | État | Vérification |
|---|---|---|
| Dépôt d'un dossier d'adhésion en 7 écrans successifs (accueil, organisation, activité, représentant, compléments, documents, récapitulatif) | ✅ | 7 adresses web déclarées, brouillon sauvegardé entre les écrans |
| Reprise d'un dossier commencé | ✅ | |
| Dépôt de pièces justificatives | ✅ | |
| Soumission, puis renvoi après demande de correction | ✅ | |
| Charte d'adhésion : consultation, signature horodatée, téléchargement | ✅ | 3 adresses dédiées |
| Instruction par le secrétariat depuis le portail (validation, demande de correction) | ✅ | 9 adresses `/staff/...` |
| Avis du comité d'admission, décision du comité de pilotage | ✅ | 3 rôles distincts, 9 règles d'accès |
| Confirmation de paiement et enregistrement d'un règlement par le personnel | ✅ | |
| Message d'explication en cas de refus d'accès (au lieu d'un renvoi silencieux) | ✅ | Couvert par le fichier de tests du parcours de dépôt (11 tests), dont plusieurs portent nommément sur le motif affiché |

## 2.2 Cotisations et paiements

| Fonctionnalité | État | Vérification |
|---|---|---|
| Génération automatique de la cotisation à l'activation d'un adhérent | ✅ | |
| Consultation de ses cotisations depuis le portail | ✅ | |
| Renouvellement | ✅ | |
| Justificatif / reçu téléchargeable | ✅ | |
| Dépôt d'une preuve de paiement | ✅ | |
| Relances automatiques des cotisations échues | ✅ | Tâche planifiée quotidienne |

## 2.3 Annuaire et animation du réseau

| Fonctionnalité | État | Vérification |
|---|---|---|
| Annuaire public des membres, filtrable | ✅ | `/opex/directory`, pagination |
| Fiche publique d'un membre | ✅ | |
| Page publique de présentation du cluster | ✅ | `/cluster` |
| Actualités du cluster (espace réservé aux membres) | ✅ | |
| Événements : consultation et inscription | ✅ | |
| Formations : consultation et inscription | ✅ | |
| Bibliothèque documentaire | ✅ | |
| Groupes de travail (consultation) | ✅ | |
| Reflet des événements dans l'agenda natif d'Odoo | ✅ | |
| **Comités** (composition, réunions) | 🟡 | Objets présents et gérés **en interface d'administration seulement** : aucun écran portail. Un membre ne consulte pas la composition d'un comité depuis le site. |
| **Assemblée générale** | 🟡 | Même situation : administration seulement. |
| **Votes en assemblée générale** | ❌ | **Ébauche déclarée comme telle dans le code** : le modèle existe (« stub, non implémenté »), sans comptage des voix, sans bulletin, sans ouverture/fermeture de scrutin. À ne pas présenter comme disponible. |

## 2.4 Transversal

| Fonctionnalité | État | Vérification |
|---|---|---|
| Cloche de notification du portail, alimentée par les trois modules métier | ✅ | Protocole d'extension respecté par tous les modules (test dédié) |
| Tableau de bord du personnel | ✅ | `/staff/dashboard` |
| Scripts de migration de base de données entre versions | ✅ | 2 jeux de scripts |

## 2.5 Le point de vigilance de ce module

| Sujet | État | Détail |
|---|---|---|
| **Couverture de tests** | 🟡 | **27 tests seulement**, dont 16 portent sur des règles transversales (collisions de noms, liens morts, compteurs du portail) et 11 sur le seul parcours de dépôt. **Les cotisations, les paiements, l'annuaire, les événements et l'espace cluster n'ont aucun test automatisé dédié.** Ces fonctions ont été validées par des essais manuels documentés, pas par la suite automatique. C'est le principal écart de maturité entre ce module et les deux suivants (315 et 491 tests). |

---

# 3. Module 2 — Innovation Booster (`opex_innovation`)

Premier module métier construit **entièrement sur le moteur de processus** :
aucun enchaînement d'étapes n'y est programmé.

## 3.1 Profils

| Fonctionnalité | État | Vérification |
|---|---|---|
| Demande de profil Expert, instruite par un processus dédié | ✅ | Processus configuré, 31 tests |
| Demande de profil Investisseur, processus séparé | ✅ | |
| Dépôt de pièces à l'appui d'une demande de profil | ✅ | |
| Écrans d'instruction pour le personnel | ✅ | `/staff/innovation/profiles/...` |

## 3.2 Projets d'innovation

| Fonctionnalité | État | Vérification |
|---|---|---|
| Dépôt d'un projet en 5 écrans (marché, équipe, besoins, documents, récapitulatif) | ✅ | 21 tests de parcours |
| Processus projet à 15 étapes, entièrement configuré | ✅ | 19 transitions |
| Versions successives d'un projet | ✅ | |
| Contrôle administratif et qualification par le personnel | ✅ | 18 tests |
| Grille d'évaluation par le comité, avec confidentialité des avis | ✅ | 27 tests |
| Décision du comité et **boucle de remédiation** | ✅ | 19 tests |
| Renvoi d'un projet corrigé | ✅ | |

## 3.3 Mise en correspondance, accompagnement, financement

| Fonctionnalité | État | Vérification |
|---|---|---|
| Mise en correspondance projet ↔ expert / investisseur, avec explication du score | ✅ | 7 critères configurés, 20 tests |
| Espace « mes opportunités » pour l'expert et l'investisseur | ✅ | |
| Accompagnement : feuille de route par phases | ✅ | 28 tests |
| Livrables d'accompagnement, avec versions et cycle de validation | ✅ | Processus dédié |
| Espace investisseur : consultation d'une opportunité, manifestation d'intérêt | ✅ | |
| Évaluation finale d'un projet, remplie depuis le portail | ✅ | 36 tests |
| **Suivi du financement** (montants levés, échéances) | 🟡 | Le porteur voit « Financement » comme **jalon d'avancement** sur son tableau de bord, mais **le détail du financement n'a pas d'écran portail** : il est tenu en interface d'administration. |
| **Industrialisation** | 🟡 | Processus configuré (7 étapes) et écrans d'administration présents ; **aucun écran portail**. |
| **Bilan de clôture d'un projet** | 🟡 | Idem : administration seulement. Le porteur voit la clôture, pas le bilan. |

## 3.4 Transversal

| Fonctionnalité | État | Vérification |
|---|---|---|
| Notifications entièrement déclenchées par la configuration des processus | ✅ | 19 actions de notification configurées, couvrant les 14 événements métier annoncés. Aucune notification écrite à la main, sauf le cas signalé au §1 |
| Historique lisible par le porteur, en langage courant | ✅ | Jalons configurés, jamais de codes techniques à l'écran |
| Tableau de bord porteur | ✅ | `/my/innovation` |
| Tableau de bord gestionnaire | ✅ | `/staff/innovation/dashboard` |
| Droits d'accès des cinq acteurs (porteur, secrétariat, comité, expert, investisseur) | ✅ | 28 règles d'accès |

## 3.5 La seconde instance du moteur

| Fonctionnalité | État | Vérification |
|---|---|---|
| Un second processus complet (« Smart Crowdfunding ») configuré **sans une ligne de programmation** | ✅ | 14 étapes, 23 transitions, en données uniquement |
| Test d'acceptation : ajouter une étape « Demo Day » avec trois conditions, par simple paramétrage | ✅ | Automatisé (37 tests) ; un test vérifie en outre qu'aucun vocabulaire métier n'a été introduit dans le moteur |

---

# 4. Module 3 — Smart Missions (`opex_intervenants`)

Le module le plus étendu du projet : 35 objets métier, 491 tests, 7 processus
configurés. Il fait tourner **deux machines à états en parallèle** — l'avancement
d'un appel à mission et le parcours individuel de chaque candidature — sans jamais
dériver l'une de l'autre.

## 4.1 L'appel à mission et la demande client

| Fonctionnalité | État | Vérification |
|---|---|---|
| Processus « appel à mission » : 14 étapes, 32 transitions | ✅ | Configuré en données |
| Processus « candidature » : 10 étapes, 20 transitions, indépendant du premier | ✅ | Configuré en données |
| Dépôt d'une demande par le client en 5 écrans + récapitulatif | ✅ | 25 tests de parcours |
| Brouillon sauvegardé automatiquement entre les écrans | ✅ | |
| Tableau de bord client (mes demandes, appels en cours, missions en cours, terminées) | ✅ | |
| Qualification et publication d'un appel **depuis le portail** par le responsable | ✅ | Ajouté après coup ; les boutons sont déduits du moteur, jamais codés dans l'affichage |
| Référentiels : 6 types de mission, 8 domaines | ✅ | Semés en données, non figés dans le code |

## 4.2 Le capital de l'intervenant

| Fonctionnalité | État | Vérification |
|---|---|---|
| Enrichissement du profil Expert existant (aucun second profil créé) | ✅ | 30 tests |
| Compétences qualifiées : niveau, années, preuve, fraîcheur | ✅ | 7 attributs |
| Expériences, certifications, disponibilités, notations | ✅ | 4 objets |
| Saisie de ces quatre blocs **depuis le portail** par l'intervenant | ✅ | `/my/missions/expertise` |
| Exposition de ce capital au moteur de correspondance | ✅ | 8 champs calculés |

## 4.3 Mise en correspondance mission / expert

| Fonctionnalité | État | Vérification |
|---|---|---|
| 7 critères pondérés (compétences 30 %, expérience 20 %, secteur 15 %, disponibilité 10 %, budget 10 %, réputation 10 %, localisation 5 %) | ✅ | 11 critères configurés au total, dont 3 variantes pour les missions de formation |
| Pondérations ajustables par type de mission **et** par appel | ✅ | 3 niveaux résolus par famille |
| Critères **éliminatoires** évalués avant le score : un candidat qui échoue est **écarté**, pas mal noté | ✅ | 24 tests |
| Explication du score : critères satisfaits, manquants, pénalisants | ✅ | |
| Refus de lancer la correspondance si un critère éliminatoire cite un champ inexistant | ✅ | Une faute de frappe supprimait silencieusement le filtre : le cas est désormais bloqué |
| Écrans du responsable : lancer, consulter, inviter, écarter, mettre en liste restreinte, voir l'explication | ✅ | 4 adresses `/staff/missions/<id>/matching/...` |

## 4.4 Publication, candidature, comparaison

| Fonctionnalité | État | Vérification |
|---|---|---|
| Catalogue public des appels, sans authentification | ✅ | `/missions` |
| Fiche publique d'un appel, avec **filtrage de confidentialité au niveau des données** (le client et le budget peuvent rester masqués) | ✅ | 28 tests ; le filtrage est fait sur les données, pas seulement à l'affichage |
| Téléchargement des documents publics d'un appel | ✅ | |
| Candidature allégée : un expert référencé **ne ressaisit jamais** ses informations permanentes | ✅ | Critère d'acceptation testé |
| Création d'un mini-profil par un candidat externe | ✅ | |
| Retrait volontaire d'une candidature | ✅ | |
| Vivier unique : les candidatures des 4 origines (correspondance, portail, invitation, saisie manuelle) atterrissent dans le **même objet**, comparables dans le même écran | ✅ | 15 tests ; critère d'acceptation structurant |
| Tableau de comparaison des candidatures | ✅ | `/staff/missions/<id>/pool` |
| Alertes d'éligibilité sur les candidatures arrivées par le portail (qui ne passent par aucun filtre amont) | ✅ | |

## 4.5 Sélection, contrat, exécution

| Fonctionnalité | État | Vérification |
|---|---|---|
| Sélection d'un intervenant, avec règle « un seul retenu sauf mission multi-intervenants » tenue à 3 niveaux | ✅ | 28 tests |
| Affectation créée automatiquement | ✅ | 8 actions configurées sur 3 transitions |
| Sous-processus de contractualisation (6 étapes) | ✅ | |
| Contrat et ordre de mission : documents générés | 🟡 | **Voir 4.9** : le générateur de PDF n'est pas accessible ; un aperçu HTML est proposé à la place |
| Signature / refus de signature **depuis le portail**, des deux côtés | ✅ | `/my/missions/contrats` — écran ajouté après la documentation |
| Règle « contrat non validé ⇒ mission non démarrable », posée comme condition de passage et non comme test programmé | ✅ | |
| Démarrage automatique d'une mission à sa date contractuelle | ✅ | Tâche planifiée quotidienne, 8 tests. **Premier automatisme du projet qui fait avancer un dossier** : il ne peut rien faire qu'un responsable n'aurait pu faire en cliquant |
| Livrables de mission : cycle de vie à 5 étapes, versions, motif de refus porté par la version archivée | ✅ | 34 tests |
| Points d'avancement de l'intervenant (temps passé, avancement déclaré, prochaine étape) | ✅ | |
| Incidents | ✅ | Compteur à 3 positions, choix documenté et verrouillé par un test |
| Barre de progression en 8 jalons | ✅ | Calculée, jamais stockée |

## 4.6 Service fait, facturation, évaluation

| Fonctionnalité | État | Vérification |
|---|---|---|
| Constat de service fait : validation par le cluster puis par le client, contestation possible, boucle de reprise | ✅ | 21 tests |
| Règle « mission non terminée tant que les livrables obligatoires ne sont pas validés » | ✅ | Condition de passage, portée par une seule règle réutilisée sur deux transitions |
| Validation / contestation **par le client depuis le portail** | ✅ | `/my/missions/services` — **limite déclarée refermée après la documentation** |
| Facturation : commande de vente et facture | 🟡 | **Voir 4.9** : désactivée, le module de vente n'étant pas déclaré |
| Évaluation du client (6 critères) et évaluation du cluster (6 critères) | ✅ | 26 tests |
| Remplissage de la grille **depuis le portail** | ✅ | `/my/missions/evaluations` — **limite déclarée refermée après la documentation** |
| Règle « le client n'évalue qu'après la validation finale » | ✅ | Condition de passage |
| Réputation calculée (note moyenne, missions réalisées, satisfaction, respect des délais) | ✅ | Une évaluation validée alimente le profil, qui alimente à son tour la correspondance |

## 4.7 Tableaux de bord et intégration

| Fonctionnalité | État | Vérification |
|---|---|---|
| Quatre espaces distincts : responsable, intervenant, candidat externe, client | ✅ | 25 tests |
| File de travail priorisée (Urgent / À traiter / Terminé) | ✅ | `/staff/queue` |
| Notifications configurées sur les transitions | ✅ | 14 dans le fichier dédié aux tableaux de bord, **29 au total** sur l'ensemble des 7 processus du module. Un test refuse toute notification écrite à la main hors de trois fichiers nommés |
| Cloche du portail alimentée par les missions et les candidatures | ✅ | L'adresse du lien est résolue **pour le lecteur**, pas pour l'objet — un défaut réel avait été trouvé ici (voir Corrections) |
| Page d'accueil unique reliant les trois domaines | ✅ | `/opex` |
| Tableau de bord d'indicateurs, avec les 9 critères d'acceptation **calculés à l'exécution** | ✅ | `/staff/kpi` — un critère qui cesserait d'être tenu passerait au rouge à l'écran |

## 4.8 Assistance par intelligence artificielle

| Fonctionnalité | État | Vérification |
|---|---|---|
| Lecture automatique d'un CV et extraction de 9 catégories d'informations | 🟡 | Fonctionne, mais **administration seulement** : aucun écran ne permet à un expert de déposer son CV depuis le portail. Vérifié : aucun gabarit portail ne mentionne cet objet. |
| Rien de ce que produit l'IA n'entre directement dans le profil : tout passe par des **propositions** portant leur confiance et la citation exacte du CV | ✅ | 18 tests ; règle vérifiée sous 3 angles |
| Promotion d'une proposition en compétence qualifiée par un geste humain, tracé | ✅ | 13 tests |
| Taxonomie de compétences : 6 domaines, 16 familles, 54 compétences, 57 synonymes | ✅ | Semée en données |
| Rapprochement d'un libellé en deux temps : correspondance exacte puis synonymes (**sans appel à l'IA**), puis proposition de l'IA | ✅ | 38 tests ; le module **reste utile sans clé d'API** |
| File d'arbitrage pour les libellés non rapprochés, seul point d'écriture vers le référentiel commun | 🟡 | **Administration seulement.** |
| Référentiel de certifications : 16 certifications, 27 synonymes, exigence cumulative | ✅ | 24 tests ; referme une dette technique documentée |
| Contrôle qualité assisté d'un profil : 7 contrôles, la moitié déterministe d'abord, l'IA ensuite | 🟡 | **Administration seulement.** L'agent **prépare**, un humain tranche : aucun avis de l'IA ne peut être bloquant, et aucune transition ne dépend de son avis. 23 tests. |
| Service d'appel au modèle de langage : sans clé, l'appel renvoie « rien » et ne casse jamais un parcours | ✅ | Voir §6 |

**Point d'ensemble sur ce bloc :** toute la chaîne d'assistance IA (dépôt de CV,
propositions, promotion, arbitrage, contrôle qualité) est **fonctionnelle mais
administrée depuis l'interface de gestion**. Aucun de ces écrans n'est ouvert à
l'expert lui-même. C'est le principal écart entre ce bloc et le reste du Module 3,
qui est très largement exposé au portail.

## 4.9 Fonctions désactivées par des dépendances absentes 🔒

Ce point est **assumé et documenté** dans le dépôt
(`opex_intervenants/docs/fonctions_desactivees.md`). Trois composants ne sont pas
disponibles sur le serveur cible ; les déclarer aurait rendu le module
**totalement non installable** — ni portail, ni correspondance, ni processus, pour
trois fonctions de bout de chaîne. Ils sont donc résolus au moment de l'appel.

| Composant absent | Ce qui est éteint | Ce qui continue de fonctionner |
|---|---|---|
| Module **Ventes** | Émission de la commande de vente et de la facture à la clôture ; suivi du paiement ; jalon « Facturation » de la barre de progression | **Tout le processus de service fait** : constat, double validation, contestation, boucle de reprise, clôture de la mission |
| Module **Projets** | Création d'un projet et de ses tâches au démarrage de la mission | **Tout le suivi d'exécution** : livrables, versions, points d'avancement, incidents — qui passent par les objets du module, pas par les tâches d'Odoo |
| Service **IA** | Lecture de CV, proposition de rapprochement par l'IA | Le rapprochement exact et par synonymes, et la file d'arbitrage |

Dans les deux premiers cas, le dossier **dit** ce qui n'a pas eu lieu : une note
est déposée sur la mission, et la situation affiche « Facturation indisponible
(module Ventes absent) » plutôt que « Non facturée » — la distinction est
volontaire.

**Vérifié :** sur l'ensemble de ses champs, le Module 3 ne déclare plus **aucun**
lien vers un objet des modules Ventes, Projets, Produits ou Comptabilité.
9 tests couvrent le fonctionnement dégradé.

⚠ **Ce module est propre, mais il ne s'installera pas seul pour autant** : la
dépendance revient par la chaîne, le Module 2 déclarant « Projets » et le Module 1
déclarant « Ventes ». Le travail restant est **entièrement en amont**, et il est
du même ordre de grandeur (2 champs et 2 appels côté Module 2 ; 1 objet hérité,
1 champ et 2 appels côté Module 1). Il n'a pas été engagé parce que ces deux
modules sont gelés.

## 4.10 Génération de documents PDF 🔒

| Sujet | État | Détail |
|---|---|---|
| Contrat et ordre de mission en PDF | 🟡 | Les deux documents sont déclarés dans leur forme correcte et leur contenu est complet. Le convertisseur PDF (`wkhtmltopdf`) **est installé sur le poste mais absent du chemin d'exécution du système**, où Odoo va le chercher. Conséquence : la génération PDF échoue, et un bouton « Aperçu » ouvre le même document au format web. **C'est une limite de poste, pas de code — et sa correction est une ligne de configuration système.** |

---

# 5. Module de comparaison — Smart Crowdfunding (`opex_crowdfunding`)

Ce module n'est pas un module métier de plus : c'est **la moitié d'une
expérience**. Le même processus de financement participatif y est implémenté
« à l'ancienne » — états codés en dur, méthodes de transition programmées — pour
être comparé au même processus configuré sur le moteur. **La comparaison est le
livrable.**

Il est isolé par construction : il ne dépend d'aucun autre module du portail.

| Fonctionnalité | État | Vérification |
|---|---|---|
| Dépôt express d'un projet | ✅ | 14 tests |
| Portail porteur | ✅ | 23 tests |
| Pré-analyse à 4 issues (Go / à clarifier / No Go / réorientation) | ✅ | 23 tests |
| Dossier progressif à branches selon le type de besoin | ✅ | 17 tests |
| Contrôle qualité à 3 issues | ✅ | 23 tests |
| Étude et décision du dirigeant, à 3 routes | ✅ | 17 tests |
| **Mise en correspondance financière sur 10 critères** | ✅ | 22 tests |
| Accompagnement, missions, jalons, livrables, contrepartie paramétrable | ✅ | 32 tests |
| Mise en relation contrôlée avec les acteurs financiers | ✅ | 23 tests |
| Décision du financeur, closing, échéancier, versements, suivi | ✅ | 28 tests |
| Quatre interfaces d'acteurs et file de travail | ✅ | 25 tests |
| **Mesure comparative « Demo Day »** — ajouter une étape avec trois conditions | ✅ | 12 tests côté module codé, et l'opération équivalente est **exécutée par simple paramétrage** côté moteur (test dédié dans le Module 2) |
| **Document de synthèse comparatif (le procès-verbal chiffré des deux colonnes)** | ❌ | **Absent du dépôt.** Les deux moitiés de l'expérience sont réalisées et testées ; la mise en regard chiffrée — fichiers modifiés, lignes de code, temps passé, compétence requise — n'est écrite nulle part. **C'est le livrable final annoncé du projet, et c'est le seul manque véritablement structurant de cette liste.** |

## Ce que l'écran de démonstration de ce module ne fait pas 🔒

Liste assumée et documentée, à connaître avant toute démonstration : l'écran web
du personnel est **en lecture seule**. Ne s'y font pas — et se font en interface
d'administration : la saisie du dossier (144 champs), la fiche de préqualification,
la fiche de contrôle qualité, la correspondance financière, l'accompagnement, le
closing, les fils de discussion, les filtres et exports, les activités planifiées.

---

# 6. Service d'assistance IA (`opex_ai_core`)

Module d'infrastructure, sans métier, extrait volontairement pour qu'un module
métier ne devienne jamais la dépendance d'un autre.

| Fonctionnalité | État | Vérification |
|---|---|---|
| Point d'appel unique vers un modèle de langage | ✅ | 22 tests |
| **Sans clé d'API, l'appel renvoie « rien » et ne lève aucune erreur** | ✅ | Aucun parcours métier ne peut être bloqué par l'absence d'IA |
| Une réponse illisible n'est jamais fatale | ✅ | 3 tests |
| Délai maximal et nouvelle tentative en cas de saturation du fournisseur | ✅ | Vérifié aussi **contre l'API réelle** : 3 tentatives en 3,5 s, journalisées |
| Aucune donnée métier écrite en base par le service | ✅ | Test dédié |
| Journal des appels : usage, coût estimé, durée, version du prompt utilisé | ✅ | |
| **Le journal ne conserve ni la question ni la réponse** — un CV contient des données personnelles | ✅ | Test dédié |
| Prompts en données versionnées, jamais écrits dans le code | ✅ | 10 tests |
| Bouton « Tester la connexion » traduisant les erreurs du fournisseur en phrases exploitables | ✅ | |

## Limite d'environnement 🔒

**La clé d'API fournie authentifie correctement, mais le projet Google associé est
refusé en génération** : la liste des modèles répond, la génération répond « accès
refusé » sur tous les modèles. C'est un réglage de compte, pas de code — et le
module se comporte exactement comme prévu face à cela : il journalise, il ne rend
rien, et rien ne casse.

---

# 7. Écarts entre la documentation et le code

Cette section existe parce que la consigne était de vérifier le code plutôt que
de recopier la documentation. Sept écarts ont été relevés. **Aucun n'est grave**,
mais tous méritent d'être connus avant une relecture du dossier de projet.

| # | Ce que dit la documentation | Ce que fait le code | Portée |
|---|---|---|---|
| 1 | Trois fonctions sont annoncées comme « limites déclarées, accessibles depuis l'administration seulement » : la signature du contrat, la validation du service fait par le client, le remplissage de la grille d'évaluation | **Les trois ont un écran portail**, ajouté le 6 septembre. La documentation n'a pas été mise à jour. | La réalité est **meilleure** que la documentation |
| 2 | La dette technique « refus d'accès sans motif » est chiffrée à **28** cas | Le compte réel est de **31**. L'écran des missions est passé de 7 à 10 depuis le relevé, de nouveaux écrans ayant été ajoutés. | Dette légèrement sous-estimée |
| 3 | Le module de comparaison annonce un périmètre réduit : « extensions 9, 10 et 11 hors périmètre » | **Les douze extensions sont réalisées et testées** (259 tests, dont 76 sur les trois annoncées comme abandonnées). | La réalité est **meilleure** que la documentation |
| 4 | Le démarrage automatique des missions à échéance | **N'est décrit nulle part** dans la documentation de projet : livré le 7 septembre, après la dernière mise à jour. 242 lignes, 8 tests. | Fonction non documentée |
| 5 | Le nombre total de tests est donné à 515 (Module 3 + service IA) et 1 048 (les cinq modules du portail) | Les comptes réels sont de **523** et **1 256** (**1 288** en incluant le service IA). Les suites ont grossi après la dernière mise à jour. | Chiffres périmés |
| 6 | La version du moteur est annoncée à `19.0.1.15.0` | La version réelle, en fichier et en base, est `19.0.1.8.0`. | Erreur de saisie sans conséquence |
| 7 | Le convertisseur PDF est annoncé « absent du poste » | Il **est installé** (`C:\Program Files\wkhtmltopdf`), mais **absent du chemin d'exécution**, donc introuvable pour Odoo. Le symptôme est le même, la correction est plus simple que documentée. | Diagnostic à affiner |

**Défaut à part, trouvé pendant cette vérification :**

| Sujet | État | Détail |
|---|---|---|
| Fichier de démarrage par conteneurs (`docker-compose.yml`) | ❌ | Le fichier commence par `ervices:` au lieu de `services:` — la première lettre manque. **Le fichier est donc invalide et le démarrage par conteneurs échouera.** Introduit par le dernier commit du dépôt (7 septembre). Correction : un caractère. |

---

# 8. Dettes techniques assumées

| # | Dette | Depuis | État | Coût estimé |
|---|---|---|---|---|
| D1 | Le critère éliminatoire de certification comparait du **texte libre** — trois défaillances mesurées, dont l'admission d'un candidat non certifié | Extension 4 | ✅ **Refermée** le 4 septembre par un référentiel canonique des deux côtés | — |
| D2 | **31 écrans réservés au personnel renvoient l'utilisateur non habilité sur son profil sans un mot d'explication** — indistinguable d'une panne | Extensions 4 à 12 | ❌ **Ouverte, reportée sciemment** | ~1 h |
| D3 | Le lien entre une action et une transition n'est exposé dans aucun écran de paramétrage du moteur | Origine | ❌ Ouverte, **volontairement**, pour préserver la mesure comparative | quelques lignes |
| D4 | Le moteur ne sait pas notifier une personne nommément, seulement un rôle | Origine | ❌ Ouverte, même raison | un paramètre |

**Sur D2 — pourquoi elle attend.** Trois raisons, dans l'ordre où elles pèsent :
on n'arrive pas sur ces adresses par hasard (ce sont des écrans internes) ; deux
des trois modules concernés sont gelés et présentés, et corriger chez eux impose
de rejouer leurs suites de tests ; la correction est mécanique et déjà écrite
ailleurs. **Le critère de déclenchement est posé** : si l'un de ces écrans devient
atteignable par un lien envoyé à un candidat, il passe en tête.

---

# 9. Hors périmètre — assumé et déclaré ⛔

Aucun de ces points n'est un manque : ce sont des exclusions décidées, chacune
avec son point d'extension prévu.

| Exclusion | Motif retenu |
|---|---|
| Mise en correspondance sémantique par IA / apprentissage automatique | Le score est **pondéré et explicable** ; un score inexplicable serait un défaut, pas une qualité |
| Apprentissage à partir des missions passées | Version 2 |
| Signature électronique cryptographique | Remplacée par une confirmation horodatée, dans les trois modules |
| Salle de données sécurisée (« data room ») | Version 2 |
| Intégration bancaire réelle, versements réels | Version 2 |
| Éditeur graphique de processus | La configuration se fait par listes |
| Envoi de SMS | Décision reprise du Module 1 |
| Agent IA de contrôle qualité **autonome** | L'architecture le permet ; l'agent livré **prépare** et ne décide jamais |

---

# 10. Limites d'environnement du poste 🔒

À distinguer des défauts de code : le module se comporte correctement face à
chacune, mais la fonction ne peut pas être démontrée sur ce poste.

| Limite | Conséquence | Nature |
|---|---|---|
| **Aucun serveur d'envoi d'e-mails configuré** | Aucune notification ne part par courriel. Les notifications se vérifient dans la cloche du portail et dans le journal des messages. | Poste |
| **Convertisseur PDF hors du chemin d'exécution** | Pas de PDF ; un aperçu web rend le même document. | Poste |
| **Projet Google refusé en génération** | Les appels à l'IA renvoient « rien ». Le module journalise et poursuit. | Compte fournisseur |
| **L'extension d'automatisation du navigateur casse l'interface d'administration d'Odoo** | Les écrans d'administration ne sont pas vérifiables par navigateur piloté ; ils le sont manuellement. Les écrans du portail, rendus côté serveur, restent vérifiables. | Outillage |

---

# 11. Résultat de l'exécution des tests

La suite complète a été **réellement exécutée** le 8 septembre 2026 sur les bases
de données du poste, et non simplement dénombrée dans les fichiers.

## Les cinq composants du portail

```
0 failed, 0 error(s) of 1029 tests
```

| Composant | Tests exécutés | Échecs |
|---|---|---|
| Moteur de processus | 164 | 0 |
| Module 1 — Adhésion et vie du cluster | 27 | 0 |
| Module 2 — Innovation Booster | 315 | 0 |
| Module 3 — Smart Missions | 491 | 0 |
| Service d'assistance IA | 32 | 0 |
| **Total** | **1 029** | **0** |

Le nombre de tests exécutés correspond **exactement** au nombre de tests
dénombrés dans les fichiers source, module par module : aucune suite n'a été
silencieusement ignorée.

Le rechargement complet des cinq composants s'est également fait **sans le moindre
avertissement** — 76 modules chargés, y compris les composants natifs d'Odoo.

## Module de comparaison

Exécuté sur sa base dédiée, ce module étant isolé par construction.

```
0 failed, 0 error(s) of 259 tests
```

| Composant | Tests exécutés | Échecs |
|---|---|---|
| Module de comparaison — Smart Crowdfunding | 259 | 0 |

## Total général

**1 288 tests exécutés, 0 échec, 0 erreur.**

## Remarque de lecture du journal

Le journal d'exécution contient neuf lignes d'erreur applicative. **Aucune n'est un
échec de test** : ce sont des erreurs **volontairement provoquées** par des tests
qui vérifient que le système les refuse bien (division par zéro, action mal
configurée, doublon en base, modèle d'email inadapté…). Le décompte officiel en fin
d'exécution — `0 failed, 0 error(s)` — est la seule ligne qui fait foi.
