<!--
  Extraction texte de : Module3_OPEX_Intervenants (1).pdf
  Source : custom_addons/opex_membership/docs/ (le PDF fait foi)
  Les schemas ne sont pas extractibles en texte : voir docs/schemas/.
-->

<!-- page 1 -->
GIC OPEX GROUP  
Portail — Spécifications fonctionnelles  
MODULE 3 — OPEX INTERVENANTS  
Appels & Interventions  
KASSAB Mohamed Amine & ZITOUNI Neil  
Document enrichi de schémas et diagrammes professionnels — contenu original inchangé

<!-- page 2 -->
3.3 OPEX Intervenants — Appels & Interventions  
Le module OPEX Intervenants constitue le module opérationnel de la plateforme. Il permet de gérer 
l'ensemble du cycle de vie d'une mission réalisée par un expert, un consultant ou un intervenant du cluster.  
Le module couvre le processus complet :  
Besoin du client → Création de l'appel à mission → Diffusion → Candidatures → Sélection → Contrat → 
Préparation → Réalisation → Validation → Facturation → Évaluation → Réputation de l'intervenant  
Il est destiné à transformer une demande de service en une mission structurée, suivie et traçable, tout en 
permettant au cluster de gérer les intervenants et d'améliorer progressivement leur réputation grâce aux 
évaluations réalisées après les missions.

<!-- page 3 -->
Schéma 1 — Cycle de vie complet d'une mission  
Les types de missions peuvent notamment être :  
● Audit  
● Conseil  
● Expertise  
● Formation  
● Coaching  
● Mentoring

<!-- page 4 -->
1. Objectif du module  
L'objectif principal est de permettre au cluster de gérer les missions de manière centralisée, depuis 
l'expression du besoin jusqu'à la clôture de la mission.  
Le module doit permettre :  
● au client d'exprimer son besoin  
● au cluster de transformer ce besoin en appel à mission  
● au système d'identifier les intervenants pertinents  
● aux experts/intervenants de consulter les appels et de candidater  
● au cluster de comparer les candidatures  
● au responsable de sélectionner l'intervenant  
● de générer le contrat correspondant  
● de suivre l'exécution de la mission  
● de valider les livrables  
● de gérer la facturation  
● d'évaluer l'intervenant  
● d'alimenter automatiquement son profil de réputation

<!-- page 5 -->
2. Acteurs du module  
Le module repose sur plusieurs acteurs.  
 
Schéma 2 — Les 5 acteurs du module OPEX Intervenants  
2.1 Client  
Le client est l'organisation qui a besoin d'une intervention. Il peut :  
● créer une demande  
● décrire son besoin  
● préciser le type de mission  
● définir les objectifs  
● indiquer les compétences recherchées  
● définir la période souhaitée  
● définir le budget  
● consulter l'état de sa demande  
● suivre la mission  
● valider les livrables  
● évaluer l'intervenant  
2.2 Secrétariat / Gestionnaire du cluster  
Le secrétariat joue un rôle central dans la gestion administrative. Il peut :  
● vérifier les demandes  
● créer ou valider les appels à mission  
● contrôler les informations  
● suivre les candidatures

<!-- page 6 -->
● gérer les contrats  
● suivre les échéances  
● contrôler les documents  
● suivre la facturation  
● clôturer administrativement les missions  
2.3 Responsable de mission  
Le responsable de mission est chargé de la partie opérationnelle. Il peut :  
● analyser le besoin  
● définir les critères de sélection  
● consulter les candidatures  
● comparer les intervenants  
● participer au choix de l'intervenant  
● suivre l'avancement  
● contrôler les livrables  
● valider les différentes étapes  
3.4 Expert / Consultant / Intervenant  
L'intervenant est la personne ou l'organisation qui réalise la mission.  
Dans la logique définie précédemment dans le portail :  
La catégorie Experts / Consultants donne automatiquement le profil expert.  
Un membre d'une autre catégorie ayant obtenu le statut Expert peut également participer aux missions 
correspondant à ses compétences.  
L'intervenant peut :  
● consulter les appels pertinents  
● consulter les détails d'une mission  
● déposer une candidature  
● proposer une méthodologie  
● proposer un délai  
● proposer un tarif  
● joindre des documents  
● suivre sa candidature  
● accepter ou refuser une mission attribuée  
● consulter son contrat  
● suivre la mission  
● déposer ses livrables  
● consulter son évaluation  
● suivre sa réputation  
3.5 Administrateur  
L'administrateur possède les droits techniques et fonctionnels nécessaires pour :  
● gérer les utilisateurs  
● gérer les rôles  
● gérer les paramètres

<!-- page 7 -->
● gérer les référentiels  
● contrôler les droits d'accès  
● superviser les données du module

<!-- page 8 -->
4. Concept central : l'appel à mission  
L'appel à mission est l'objet central du module. Il représente une mission que le cluster souhaite confier à un 
intervenant.  
Un appel doit contenir au minimum :  
Informations générales  
● Référence de la mission  
● Titre  
● Type de mission  
● Client  
● Description  
● Objectifs  
● Résultats attendus  
Informations opérationnelles  
● Compétences recherchées  
● Domaine d'expertise  
● Niveau d'expérience souhaité  
● Localisation  
Mode d'intervention :  
○ Présentiel  
○ Distanciel  
○ Hybride  
Informations temporelles  
● Date de début souhaitée  
● Date de fin souhaitée  
● Durée estimée  
● Date limite de candidature  
Informations financières  
● Budget estimatif  
● Type de rémunération  
● Conditions financières  
Documents  
● Cahier des charges  
● Documents techniques  
● Documents complémentaires  
5. UX — Vue générale du module  
Le module doit être organisé autour d'un espace OPEX Intervenants. Le menu principal peut être structuré 
comme suit :  
OPEX INTERVENANTS  
● Tableau de bord

<!-- page 9 -->
● Appels à mission  
○ Tous  
○ Brouillons  
○ Publiés  
○ En candidature  
○ En sélection  
○ Clôturés  
● Mes candidatures  
● Missions  
○ À venir  
○ En cours  
○ En validation  
○ Terminées  
● Contrats  
● Livrables  
● Facturation  
● Évaluations  
Les menus affichés doivent dépendre du rôle de l'utilisateur.  
6. Tableau de bord client  
Le client doit disposer d'un tableau de bord simple.  
Indicateur  Valeur  
Mes demandes  3 
Appels en cours  2 
Missions en cours  1 
Missions terminées  5 
 
Actions principales : + Créer une demande de mission, ainsi que Voir mes missions / Voir mes appels / Voir 
les contrats / Voir les factures.

<!-- page 10 -->
7. Création d'une demande de mission  
Le client clique sur « Créer une demande de mission ». Un formulaire est affiché.  
Étape 1 — Informations générales  
● Titre de la mission *  
● Type de mission *  
● Description *  
● Objectifs *  
Étape 2 — Profil recherché  
● Domaine *  
● Compétences recherchées *  
● Expérience minimale  
● Certifications souhaitées  
Étape 3 — Organisation  
● Date souhaitée de début  
● Date souhaitée de fin  
● Localisation  
● Mode d'intervention  
Étape 4 — Budget  
● Budget estimatif  
● Modalités financières  
Étape 5 — Documents  
● Cahier des charges  
● Documents complémentaires  
Puis : Soumettre la demande  
8. Validation de la demande  
Une demande créée par le client ne devient pas automatiquement publique. Elle passe d'abord par une 
étape de contrôle.

<!-- page 11 -->
Schéma 3 — Workflow de validation de la demande  
Si le dossier est incomplet, le client reçoit une notification lui indiquant les éléments à compléter.  
9. Création de l'appel à mission  
Après validation de la demande, le gestionnaire peut créer l'appel à mission. Le système reprend 
automatiquement les informations déjà saisies.  
Le gestionnaire peut encore modifier :  
● le titre  
● les critères  
● les compétences  
● le budget  
● les dates  
● les documents  
● la date limite de candidature  
Puis : Publier l'appel  
10. Diffusion automatique  
Une fois l'appel publié, le système recherche les intervenants correspondant aux critères. Le matching peut 
prendre en compte :  
● compétences  
● domaine  
● expérience  
● certifications

<!-- page 12 -->
● type de mission  
● localisation  
● disponibilité  
● historique des missions  
 
Schéma 4 — Diffusion automatique et matching des intervenants  
11. Notification des intervenants  
Les intervenants pertinents reçoivent une notification, par exemple : « Nouvel appel à mission 
correspondant à votre profil ».  
Champ  Exemple  
Mission  Audit cybersécurité  
Client  Entreprise XYZ  
Durée  15 jours  
Date limite  10 septembre  
Budget  ... 
 
Actions : Consulter / Candidater

<!-- page 13 -->
12. Consultation d'un appel  
L'intervenant ouvre l'appel. La page doit présenter clairement :  
Informations  
● Client  
● Type de mission  
● Description  
● Objectifs  
● Compétences recherchées  
● Dates  
● Durée  
● Localisation  
● Budget indicatif  
Documents  
Les documents associés doivent être téléchargeables selon les droits de l'utilisateur.  
Actions  
Candidater ou : Ne pas candidater  
13. Candidature  
L'intervenant clique sur « Candidater ». Il remplit un formulaire.  
Informations  
● Motivation  
● Méthodologie proposée  
● Disponibilité  
● Délai proposé  
● Tarif proposé  
Documents  
Il peut joindre :  
● CV 
● portfolio  
● références  
● proposition technique  
● proposition financière  
● certifications  
Puis : Envoyer la candidature  
14. Statut de la candidature  
Chaque candidature possède un statut.

<!-- page 14 -->
Schéma 5 — Statuts d'une candidature  
L'intervenant peut consulter uniquement l'état de sa propre candidature selon les règles de confidentialité.  
15. Réception des candidatures  
Le responsable dispose d'un espace « Candidatures reçues ». Exemple :  
Intervenant  Expérience  Tarif  Disponibilité  Score  
Expert A  8 ans  250k  Disponible  91 
Expert B  5 ans  180k  Disponible  84 
Cabinet C  10 ans  300k  Partielle  89 
 
L'objectif est de faciliter la comparaison.  
16. Comparaison des candidatures  
Le système peut proposer une comparaison basée sur plusieurs critères. Exemple :  
● adéquation des compétences  
● expérience  
● disponibilité  
● tarif  
● réputation  
● historique des missions  
● évaluations précédentes  
Le système peut produire un score indicatif.  
⚠️ Ce score constitue une aide à la décision.

<!-- page 15 -->
La sélection finale reste réalisée par les responsables habilités du cluster.

<!-- page 16 -->
17. Sélection de l'intervenant  
Le responsable sélectionne une candidature.  
 
Schéma 6 — Workflow de sélection  
Les autres candidats passent à « Non retenu ». Ils peuvent recevoir une notification.  
18. Génération du contrat  
Après sélection, le système génère automatiquement un contrat à partir d'un modèle. Le contrat reprend 
notamment :  
● client  
● intervenant  
● mission  
● description  
● dates  
● durée  
● montant  
● conditions  
● livrables  
● modalités de validation  
Le contrat peut être généré sous forme de document.  
19. Validation du contrat

<!-- page 17 -->
Schéma 7 — Workflow de validation du contrat  
Chaque version doit pouvoir être tracée.  
20. Démarrage de la mission  
Une fois le contrat validé : Mission planifiée. La mission devient active à la date prévue.  
Le tableau de bord affiche : Mission « Audit cybersécurité » — Statut : À venir — Début : 01/09/2026 — Fin : 
15/09/2026.  
21. Suivi de la mission  
Pendant la mission, le responsable et le client peuvent suivre :  
● progression  
● étapes  
● livrables  
● échéances  
● commentaires  
● documents  
● réunions  
● problèmes éventuels

<!-- page 18 -->
22. Plan de mission  
Une mission peut être divisée en plusieurs étapes. Exemple :  
 
Schéma 8 — Plan de mission en 5 étapes  
Chaque étape peut avoir : une date, un responsable, un statut, un livrable.  
23. Statuts d'une étape  
 
Schéma 9 — Cycle de statuts d'une étape

<!-- page 19 -->
24. Livrables  
L'intervenant peut déposer les livrables directement dans la mission. Exemple : + Ajouter un livrable.  
Formulaire : Nom, Description, Type, Date, Fichier.  
Le responsable reçoit une notification : « Un nouveau livrable a été soumis pour validation. »  
25. Validation des livrables  
Le responsable consulte le document. Deux possibilités :  
Validation : Livrable soumis → Validé  
Correction : Livrable soumis → Corrections demandées → Intervenant → Nouvelle version  
L'historique des versions doit être conservé.  
26. Gestion des incidents / retards  
Pendant une mission, le responsable peut signaler :  
● retard  
● blocage  
● problème de disponibilité  
● problème de livrable  
● problème contractuel  
Exemple : Incident #001 — Type : Retard — Description : Livrable intermédiaire non reçu — Priorité : 
Moyenne — Statut : Ouvert.  
 
Schéma 10 — Cycle de traitement d'un incident  
27. Fin de la mission

<!-- page 20 -->
Schéma 11 — De la fin de mission à l'évaluation  
Le client ou le responsable habilité valide la réalisation.  
28. Validation finale  
La validation finale confirme que :  
● les objectifs ont été atteints  
● les livrables sont complets  
● les corrections ont été effectuées  
● la prestation correspond au contrat  
Le système enregistre : Date de validation, Validateur, Commentaire, Résultat.  
29. Facturation  
 
Schéma 12 — Processus de facturation  
Les informations peuvent reprendre automatiquement :  
● client  
● intervenant  
● référence de mission  
● montant  
● prestations  
● date

<!-- page 21 -->


<!-- page 22 -->
30. Évaluation du client  
Une fois la mission terminée, le client reçoit une demande : « Évaluez l'intervenant ayant réalisé votre 
mission. »  
L'évaluation peut porter sur :  
Critère  Score  
Qualité du travail  /5 
Respect des délais  /5 
Expertise  /5 
Communication  /5 
Pertinence des recommandations  /5 
Satisfaction générale  /5 
 
Et : Commentaire. L'évaluation est ensuite enregistrée dans l'historique de l'intervenant.  
31. Évaluation de l'intervenant par le cluster  
En complément du retour client, le cluster peut avoir sa propre évaluation opérationnelle. Elle peut prendre 
en compte :  
● respect du contrat  
● respect des délais  
● qualité des livrables  
● professionnalisme  
● communication  
● respect des procédures  
Cette évaluation peut être réalisée par le responsable de mission ou un responsable habilité.  
32. Réputation de l'intervenant  
Les évaluations alimentent progressivement le profil de l'intervenant. Le profil peut afficher :  
Indicateur  Valeur  
Note  ★★★★★  4.7 / 5  
Missions réalisées  18 
Missions terminées  17 
Taux de satisfaction  94 %  
Respect des délais  96 %  
 
L'objectif est de construire un historique de réputation basé sur les missions réellement réalisées.  
33. Historique des missions  
Chaque intervenant possède un historique. Exemple :  
● Audit — Entreprise A → Terminée  
● Formation — Entreprise B → Terminée  
● Conseil — Entreprise C → En cours  
● Coaching — Entreprise D → À venir  
Selon les droits, certaines informations peuvent être visibles publiquement et d'autres rester confidentielles.

<!-- page 23 -->
34. Notifications  
Le système doit notifier les acteurs lors des événements importants.  
Client  
● demande reçue  
● demande validée  
● candidature reçue  
● intervenant sélectionné  
● contrat à valider  
● livrable à valider  
● mission terminée  
● évaluation à effectuer  
Intervenant  
● nouvel appel pertinent  
● candidature reçue  
● candidature présélectionnée  
● candidature retenue  
● candidature refusée  
● contrat disponible  
● contrat validé  
● livrable accepté/refusé  
● mission terminée  
● nouvelle évaluation  
Gestionnaire  
● nouvelle demande  
● demande nécessitant une validation  
● nouvelles candidatures  
● contrat en attente  
● retard  
● livrable soumis  
● mission à clôturer  
35. Workflow global du module  
Le workflow complet peut être résumé en trois phases successives :  
Phase 1 — Du besoin client à la publication de l'appel

<!-- page 24 -->
Schéma 13a — Phase 1 : besoin, vérification, appel, publication  
Phase 2 — De la diffusion à la validation du contrat

<!-- page 25 -->
Schéma 13b — Phase 2 : matching, candidatures, sélection, contrat  
Phase 3 — De la mission à la réputation

<!-- page 26 -->
Schéma 13c — Phase 3 : réalisation, validation, facturation, évaluation, réputation

<!-- page 27 -->
36. Lean Process du module  
L'objectif du Lean Process est de réduire les opérations manuelles inutiles.  
Avant  
Un processus classique pourrait être : Client → Email → Secrétariat → Recherche d'experts → Emails aux 
experts → Réception CV → Excel → Comparaison manuelle → Choix → Word → Contrat → Email → Suivi 
Excel → Documents par email → Facturation → Évaluation.  
Cela crée :  
● perte d'information  
● doublons  
● manque de traçabilité  
● erreurs  
● délais importants  
37. Processus Lean proposé  
Le module centralise le processus :  
1. Client  
2. Demande structurée  
3. Validation  
4. Appel  
5. Matching automatique  
6. Candidatures centralisées  
7. Comparaison  
8. Sélection  
9. Contrat automatique  
10. Mission  
11. Livrables  
12. Validation  
13. Facturation  
14. Évaluation  
15. Réputation  
Chaque étape est enregistrée dans le système.  
Comparaison synthétique du processus avant / après :

<!-- page 28 -->
Schéma 14a — Processus AVANT (dispersé, manuel)

<!-- page 29 -->
Schéma 14b — Processus APRÈS (centralisé, Lean)

<!-- page 30 -->
38. Machine à états de la mission  
Pour l'implémentation, la mission doit posséder un état clairement défini.  
 
Schéma 15 — Machine à états de la mission

<!-- page 31 -->
Des états secondaires peuvent gérer : CANCELLED, REJECTED, SUSPENDED.

<!-- page 32 -->
39. Règles métier importantes  
Règle 1 — Un intervenant doit avoir le profil approprié  
Un utilisateur ne peut candidater à une mission que s'il possède le statut/profil Expert / Intervenant requis.  
Règle 2 — Une candidature appartient à un seul appel  
Une candidature doit être liée à : 1 appel + 1 intervenant.  
Règle 3 — Un intervenant peut avoir plusieurs candidatures  
Mais il ne peut pas déposer deux fois la même candidature pour le même appel.  
Règle 4 — Une mission ne peut avoir qu'un intervenant sélectionné  
Plusieurs candidatures peuvent exister, mais une seule devient la candidature retenue pour la mission, sauf 
si le modèle de mission autorise explicitement plusieurs intervenants.  
Règle 5 — Le contrat doit être validé avant le démarrage  
Contrat non validé → Mission non démarrée  
Règle 6 — Les livrables doivent être validés avant la clôture  
Une mission ne doit pas être considérée comme complètement terminée tant que les livrables obligatoires 
ne sont pas validés.  
Règle 7 — L'évaluation intervient après la mission  
Le client ne peut normalement évaluer la mission qu'après sa validation finale.  
Règle 8 — Les évaluations alimentent la réputation  
Une évaluation validée est associée au profil de l'intervenant.  
Règle 9 — Traçabilité  
Les actions importantes doivent être historisées :  
● création  
● modification  
● validation  
● sélection  
● contrat  
● livrables  
● validation  
● facturation  
● évaluation

<!-- page 33 -->
40. UX — Fiche d'une mission  
La fiche d'une mission doit être organisée pour que l'utilisateur comprenne immédiatement son état.  
En-tête : MISSION #MIS -2026 -001 — Audit cybersécurité — Client : Entreprise XYZ — Statut : 🟢 En cours  
Barre de progression : Demande ✓ — Appel ✓ — Sélection ✓ — Contrat ✓ — Mission ● — Validation ○ — 
Facturation ○ — Évaluation ○  
Cela permet à l'utilisateur de comprendre où se trouve la mission dans son cycle de vie.  
41. UX — Espace intervenant  
L'intervenant doit avoir une interface centrée sur ses missions.  
Indicateur  Valeur  
Appels pertinents  5 
Candidatures en cours  2 
Missions en cours  1 
Missions terminées  12 
Note moyenne  4.7 
 
Actions rapides : Voir les appels, Mes candidatures, Mes missions, Mes contrats, Mes livrables, Ma 
réputation.  
42. UX — Espace gestionnaire  
Le gestionnaire doit avoir une vue globale :  
Indicateur  Valeur  
Demandes à traiter  4 
Appels actifs  7 
Candidatures  23 
Missions en cours  8 
Livrables à valider  5 
Contrats en attente  3 
Missions à clôturer  2 
 
Cela permet au cluster de détecter rapidement les actions prioritaires.  
43. UX — Priorisation des actions  
Le système peut mettre en évidence :  
🔴 Urgent  
● Contrat en attente depuis 3 jours  
● Livrable en retard  
● Mission arrivant à échéance  
🟠 À traiter  
● Nouvelle candidature  
● Nouvelle demande  
● Livrable soumis  
🟢 Terminé

<!-- page 34 -->
● Mission validée  
● Contrat signé  
● Facture payée

<!-- page 35 -->
44. Architecture fonctionnelle  
Le module peut être organisé autour des objets suivants :  
 
Schéma 16 — Architecture fonctionnelle du module  
45. Relations entre les objets  
La logique métier peut être représentée ainsi :  
 
Schéma 17 — Relations entre les objets métier  
46. Automatisations  
Plusieurs actions doivent être automatisées.  
Publication — Lorsqu'un appel est publié :  
Appel publié → Matching → Intervenants pertinents → Notifications  
Sélection — Lorsqu'une candidature est sélectionnée :

<!-- page 36 -->
Candidature sélectionnée → Création mission → Génération contrat → Notification  
Contrat — Lorsque le contrat est validé :  
Contrat validé → Mission activable  
Livrable — Lorsqu'un livrable est déposé :  
Livrable soumis → Notification responsable  
Fin de mission — Lorsqu'une mission est terminée :  
Mission terminée → Demande d'évaluation → Mise à jour réputation

<!-- page 37 -->
47. Expérience utilisateur — Principe général  
Le module doit suivre une logique « une action → une conséquence claire ». Par exemple :  
Publier l'appel → Les intervenants pertinents sont informés  
Sélectionner l'intervenant → Le contrat est préparé  
Valider le contrat → La mission peut démarrer  
Déposer le livrable → Le responsable est notifié  
Valider la mission → Facturation + évaluation  
Cette logique réduit la complexité pour les utilisateurs.  
48. Objectif final du module  
À terme, OPEX Intervenants doit permettre au cluster de passer d'une gestion dispersée des prestations à 
une gestion centralisée et traçable.  
Le résultat attendu est :  
« Un espace unique permettant de gérer une mission depuis l'expression du besoin jusqu'à l'évaluation de 
l'intervenant. »  
Le cycle complet devient :

<!-- page 38 -->
Schéma 18 — Cycle complet : du besoin à la réputation
