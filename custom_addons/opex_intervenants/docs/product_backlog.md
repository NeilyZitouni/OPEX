# **Product Backlog**

Priorité 1 : Must Have (Indispensables au lancement du portail)

|ID|User Story (En tant|Description technique|Module|
|---|---|---|---|
||que...)|(Je veux...)|associé|
|US-01|Visiteur / Membre|Créer un compte et<br>déposer un dossier<br>d'adhésion complet.|opex_membershi<br>p|
|US-02|Secrétariat|Gérer le workfow<br>d'adhésion (Contrôle,<br>Comité, COPIL,<br>Activation).<br>(Back-ofce)|opex_membershi<br>p|
|US-03|Adhérent|Payer ma cotisation en<br>ligne et recevoir un reçu<br>fscal.|opex_membershi<br>p|
|US-04|Membre|Mettre à jour mon profl<br>public (Photo,|opex_membershi<br>p|
|||Compétences, Secteur,<br>Wilaya).||
|US-05|Gestionnaire Cluster|Paramétrer les|opex_membershi|
|||catégories de membres|p|



|||et les montants de<br>cotisation.(Back-ofce)||
|---|---|---|---|
|US-06|Porteur de projet|Déposer un projet<br>d'innovation (Business<br>Plan, Pitch, MVP).|opex_innovatio<br>n|
|US-07|Comité d'évaluation|Qualifer et évaluer les<br>projets déposés.|opex_innovatio<br>n|
|US-08|Porteur de projet|Participer aux sessions<br>de remédiation<br>(coaching) après un<br>ajournement.|opex_innovatio<br>n|
|US-09|Gestionnaire Cluster|Créer un Appel à<br>mission et le publier.|opex_intervena<br>nts|
|US-10|Expert / Consultant|Consulter la liste des<br>appels sur le portail web<br>et postuler en ligne.|opex_intervena<br>nts|
|US-11|Gestionnaire Cluster|Visualiser les<br>candidatures classées<br>par Score IA et<br>sélectionner un expert.|opex_intervena<br>nts|
|US-12|Système (IA)|Générer<br>automatiquement|opex_intervena<br>nts|



|||l'Ordre de mission et le<br>contrat (PDF).||
|---|---|---|---|
|US-13|Expert|Renseigner<br>l'avancement de ma<br>mission (Temps passé,<br>Livrables).|opex_intervena<br>nts|
|US-14|Gestionnaire Cluster|Valider le "Service Fait"<br>et déclencher la<br>facturation au client.|opex_intervena<br>nts|
|Priorité 2 : S|hould Have (Améliorations|et fonctionnalités avancées)||
|ID|User Story (En tant<br>que...)|Description technique<br>(Je veux...)|Module<br>associé|
|US-15|Gestionnaire Cluster|Gérer les relances<br>automatiques de<br>cotisations par<br>email/SMS.|opex_membershi<br>p|
|US-16|Adhérent / Visiteur|Rechercher des<br>membres via l'annuaire<br>multicritère (Secteur,<br>Expertise).|opex_membershi<br>p|
|US-17|Investisseur|Recevoir des<br>recommandations de|opex_innovatio<br>n|



|||projets via le Matching<br>IA.||
|---|---|---|---|
|US-18|Porteur de projet|Suivre l'état de mon<br>projet (Qualifcation,<br>Évaluation,<br>Accompagnement).|opex_innovatio<br>n|
|US-19|Client|Valider le "Service Fait"<br>de la mission et noter<br>l'expert (Évaluation).|opex_intervena<br>nts|
|US-20|Gestionnaire Cluster|Consulter un tableau de<br>bord KPI global (Taux de<br>réussite, Performance<br>des experts).|opex_intervena<br>nts|
|Priorité 3 : C|ould Have (Fonctionnalités|à déployer en phase 2)||
|ID|User Story (En tant<br>que...)|Description technique<br>(Je veux...)|Module<br>associé|
|US-21|Membre|Participer aux<br>Assemblées Générales<br>et aux votes|opex_membershi<br>p|
|||électroniques.||



|US-22|Expert|Consulter un tableau de|opex_intervena|
|---|---|---|---|
|||bord personnalisé (Mes|nts|
|||missions, Mes||
|||paiements, Mes<br>évaluations).||
|US-23|Gestionnaire Cluster|Utiliser l'IA générative<br>(GPT) pour rédiger les|opex_ai_core|
|||synthèses de rapport||
|||COPIL/AG.||
|US-24|Membre|Créer des groupes de|opex_membershi|
|||travail et des forums de|p|
|||discussion privés.||



# **Sprint Planning (Projet Complet en 3 Sprints)**

_Durée totale estimée : 30 jours (3 sprints). Charge de travail : 9H/jour._

Sprint 1 : Module 1 – OPEX Membership (Socle et Communauté)

Objectif du sprint : Mettre en place l'infrastructure utilisateur, l'adhésion, les cotisations, et créer les premières pages web publiques (Annuaire).

- Jour 1-2 (18h) : _Création du socle_ .

   - Générez la structure de <mark>opex_membership</mark> (Modèles Python :

      - <mark>CategorieMembre, DossierAdhesion)</mark> .

   - Configurez l'environnement Odoo 19 et la sécurité de base (Permissions : Membre, Secrétariat, COPIL).

- Jour 3-4 (18h) : _Workflow d'adhésion_ .

   - Générez les vues Odoo (Formulaire de dépôt de dossier, Kanban de gestion pour le secrétariat) et le workflow d'état (Dépôt -> EnContrôle -> EnComité -> ValidéCOPIL -> Actif).

- Jour 5-6 (18h) : _Finances & Cotisations_ .

   - Connectez le modèle <mark>Cotisation</mark> au module <mark>sale.order</mark> d'Odoo pour la facturation, le paiement, et la génération des reçus.

   - Générez les relances automatiques (via <mark>mail)</mark> .

- Jour 7-8 (18h) : _Annuaire & Vie du Cluster_ .

   - Créez l'Annuaire public (Recherche multicritère : Secteur, Wilaya, Expertise).

   - Générez l'intégration des événements ( <mark>calendar.event)</mark> .

- Jour 9-10 (18h) : _Intégration Frontend (Portail)_ .

   - Générez les pages web publiques : <mark>/annuaire</mark> (consultation) et

      - <mark>/mon-compte.</mark>

   - Validation du Sprint 1 : Un nouvel utilisateur peut s'inscrire, payer, et apparaître dans l'annuaire.

Sprint 2 : Module 2 – OPEX Innovation (Projets et Matching IA)

Objectif du sprint : Créer l'écosystème de gestion des projets d'innovation et intégrer le moteur d'IA.

- Jour 11-12 (18h) : _Modèles des Projets_ .

   - Générez le module <mark>opex_innovation</mark> avec le modèle <mark>ProjetInnovation</mark> (héritant de <mark>project.project)</mark> .

   - Générez les fichiers associés : <mark>BusinessPlan, Pitch, MVP</mark> (attachés via <mark>documents.document)</mark> .

- Jour 13-14 (18h) : _Workflow de Qualification_ .

   - Générez le workflow de décision (Dépôt -> Qualifié -> EnÉvaluation -> Pitch -> Accepté/Refusé/Ajourné).

   - Créez les vues Kanban pour le Comité d'évaluation.

- Jour 15-16 (18h) : _Boucle de Remédiation & Accompagnement_ .

   - Générez le modèle <mark>Accompagnement</mark> (avec sessions de Coaching/Mentoring).

   - Créez le mécanisme de réévaluation des projets "Ajournés".

- Jour 17-18 (18h) : _Service IA de Matching_ .

   - Écrivez un service Python ( <mark>opex_ai_service.py)</mark> qui compare les compétences d'un projet avec les tags des experts/investisseurs.

   - Générez le déclencheur automatique de ce service lorsqu'un projet est accepté.

- Jour 19-20 (18h) : _Connectivité IA & Tableau de bord_ .

   - Générez la page web pour les investisseurs listant les projets recommandés par l'IA.

   - Validation du Sprint 2 : Un porteur peut déposer un projet, le comité le qualifie, et l'IA propose des experts à la fin du processus.

Sprint 3 : Module 3 – OPEX Intervenants (Missions & Intégration Finale du Site Web)

Objectif du sprint : Développer la gestion des appels à experts, les missions opérationnelles, et connecter tous les modules au portail web global.

## Jour 21-22 (18h) : _Modèles de Gestion des Appels_ .

   - Générez le module <mark>opex_intervenants</mark> avec les modèles <mark>AppelMission, Candidature</mark> et le workflow (Brouillon -> Publié -> Mission).

- Jour 23-24 (18h) : _Portail Web (Processus de Candidature)_ .

   - Générez les routes web (Controllers) : <mark>/appels</mark> (liste des missions) et <mark>/appel/<id></mark> (détail).

   - Créez le Formulaire de candidature express (< 2 minutes) pour les experts.

- Jour 25-26 (18h) : _Scoring IA & Tableau de bord de Sélection_ .

   - Intégrez la fonction de Scoring IA aux candidatures (calcul du score basé sur disponibilité, tarif, compétences).

   - Générez le Tableau de bord de comparaison pour le Gestionnaire (trié par Score IA).

- Jour 27-28 (18h) : _Automatisation Contractuelle & Facturation_ .

   - Générez le template QWeb pour l'Ordre de mission (PDF).

   - Connectez le workflow à <mark>sale.order</mark> pour la facturation finale lors du "Service Fait".

- Jour 29-30 (18h) : _INTÉGRATION FINALE DU SITE WEB & DASHBOARD GLOBAL_ .

   - Connectez le Module 1, 2 et 3 : Le site web public doit maintenant afficher (via des onglets ou une navigation) : l'annuaire, les projets publics, et les appels à missions.

   - Créez la page d'accueil unique du portail.

- Générez le dashboard KPI global (pour le gestionnaire) qui agglomère les données des 3 modules (Nombre de membres, Projets en cours, Taux de réussite des missions).

- Validation Finale : Test de bout en bout complet : Membre -> Porteur -> Gestionnaire -> Expert -> Client. Tout le site web est interconnecté.

