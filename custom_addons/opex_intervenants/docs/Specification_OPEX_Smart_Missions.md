<!--
  Extraction texte de : Specification_OPEX_Smart_Missions_Appel_Candidatures-4Students.pdf
  Source : custom_addons/opex_membership/docs/ (le PDF fait foi)
  Les schemas ne sont pas extractibles en texte : voir docs/schemas/.
-->

<!-- page 1 -->
CEO & DELTALOG  S.Babaci 29 -08-2026 notes de cadrage du module 3 (ZN et KA)  
OPEX Group — Spécification OPEX Smart Missions — Août 2026  OPEX GROUP  
Spécification fonctionnelle & conception  
OPEX Smart Missions  
Appels à candidatures · Matching Mission / Expert · Portail Web  
 
 
Version de conception — Août 2026  
Cible technique : Odoo 19 + services transversaux IA / scoring / dashboard

<!-- page 2 -->
CEO & DELTALOG  S.Babaci 29 -08-2026 notes de cadrage du module 3 (ZN et KA)  
OPEX Group — Spécification OPEX Smart Missions — Août 2026  1. Objet et positionnement  
OPEX Smart Missions est le composant du Portail Digital CEO dédié à la mobilisation d’experts, consultants, 
formateurs, mentors et autres intervenants. Il couvre le cycle depuis l’expression d’un besoin jusqu’à la sélecti on, la 
contractualisation, l’exécution, le service fait et l’évaluation.  
Le principe de conception retenu est de créer un objet métier unique « Mission » puis d’offrir deux méthodes 
complémentaires de sourcing :  
 matching intelligent avec les experts dé jà référencés et  
 appel à candidatures publié sur le portail Web. Les deux canaux alimentent un même pool de candidats et 
convergent vers un workflow unique de qualification et de sélection.  
2. Objectifs de conception  
 Réduire le délai entre l’expression  du besoin et l’identification des meilleurs intervenants.  
 Capitaliser sur le référentiel d’experts OPEX sans demander aux experts connus de ressaisir leur CV.  
 Ouvrir certaines missions au marché via le portail Web afin d’élargir et enrichir le réseau.  
 Fournir un scoring explicable d’aide à la décision, tout en conservant la décision finale humaine.  
 Garantir confidentialité, traçabilité, séparation des rôles et visibilité contrôlée des informations.  
 Réutiliser au maximum les fonctions natives Odoo 19 pour d ocuments, agenda, communication, projets, 
facturation et enquêtes.  
 Créer une boucle d’apprentissage : chaque mission réalisée enrichit le profil et la réputation de l’expert.  
3. Architecture fonctionnelle  
BESOIN / MISSION  
        ↓ 
Qualification OPEX  
        ↓ 
┌───────────────────────┬────────────────────────┐  
│ A. SMART MATCHING     │ B. APPEL PORTAIL WEB  │ 
│ Experts r éférenc és    │ Candidats ouverts     │ 
└───────────┬───────────┴───────────┬────────────┘  
            └───────────┬───────────┘  
                        ↓ 
                 POOL DE CANDIDATS  
                        ↓ 
        Éligibilit é → Scoring → Short -list 
                        ↓ 
                  Décision humaine  
                        ↓ 
       NDA / Contrat / Ordre de mission  
                        ↓ 
             Exécution + Livrables  
                        ↓ 
                  Service fait  
                        ↓ 
          Facturation / Paiement  
                        ↓ 
                    Évaluation  
                        ↓ 
              Profil expert enrichi

<!-- page 3 -->
CEO & DELTALOG  S.Babaci 29 -08-2026 notes de cadrage du module 3 (ZN et KA)  
OPEX Group — Spécification OPEX Smart Missions — Août 2026  4. Acteurs  
Acteur  Responsabilités principales  
Client / Entreprise  Exprime le besoin, précise les objectifs, peut participer à la sélection et valide le service rendu.  
Responsable OPEX / Cluster  Qualifie la mission, choisit la stratégie de sourcing, valide la short -list et pilote la sélection.  
Expert référencé  Reçoit les opportunités ciblées, déclare son intérêt, disponibilité, tarif et approche.  
Candidat externe  Découvre une mission publique, crée un mini -profil et soumet sa candidature.  
Comité / Décideur  Compare les candidats et prend ou valide la décision finale selon les règles de la mission.  
Système / IA  Matching, contrôles, scoring, recommandations, notifications et automatisations ; ne remplace pas la 
décision autor isée. 
 
5. Création Lean d’une mission  
La création est organisée en quatre écrans courts afin d’éviter un formulaire monolithique.  
Étape  Contenu  Sortie  
1. Besoin  Titre, contexte, objectif, type d’intervention, description libre. Une IA peut proposer 
domaine, compétences et niveau d’expertise.  Mission brouillon 
structurée  
2. Conditions  Période, durée, lieu/distanciel, langues, budget/TJM, confidentialité, critères 
obligatoires.  Contraintes de sourcing  
3. Livrables  Livrables attendus, jalons éventuels, critères d’acceptation.  Base du futur service fait  
4. Sourcing  Matching ciblé, appel ouvert ou mode hybride.  Lancement du sourcing  
 
6. Méthode A — Smart Matching Mission / Expert  
Le moteur confronte les exigences de la mission aux profils expe rts du référentiel OPEX. Le matching doit être 
explicable : le score global est accompagné des critères positifs, manquants ou pénalisants.  
Critère  Exemples  
Compétences  Lean, ISO, finance, cybersécurité, marketing, data, formation…  
Expérience  Nombre d’années, missions similaires, séniorité.  
Secteur  Industrie, santé, services, énergie, agroalimentaire…  
Contraintes  Disponibilité, localisation/mobilité, langue, budget/TJM.  
Qualité / réputation  Évaluations précédentes, respect des délais, livrables acceptés.  
Certifications  Critères obligatoires ou préférentiels selon la mission.  
 
Actions du responsable : Inviter · Écarter · Mettre en short -list · Consulter le profil · Voir l’explication du score.  
7. Méthode B — Appel à candidatures Portail Web  
La m ême mission peut être publiée dans une rubrique « Opportunités / Missions OPEX ». Une vue publique contrôlée 
expose uniquement les informations autorisées. Le client, le budget ou les documents sensibles peuvent rester 
masqués jusqu’à une étape ultérieure.  
CTA principal : « Je suis intéressé ».  
Un expert déjà connecté utilise son profil existant. Un candidat externe crée un mini -profil puis fournit les 
informations nécessaires à la candidature. S’il est qualifié, son profil peut intégrer le référentiel expe rts OPEX.

<!-- page 4 -->
CEO & DELTALOG  S.Babaci 29 -08-2026 notes de cadrage du module 3 (ZN et KA)  
OPEX Group — Spécification OPEX Smart Missions — Août 2026  8. Mode hybride — stratégie recommandée  
Le mode hybride combine les deux méthodes : invitation immédiate des experts présentant les meilleurs matchs et 
publication simultanée ou différée sur le portail. Fonctionnellement, il ne constitue pas un t roisième moteur : il active 
les deux canaux d’alimentation du même pool de candidats.  
9. Candidature Lean  
Pour un expert référencé, la candidature ne redemande jamais les informations permanentes déjà connues (identité, 
CV, compétences, certifications, historique). Seules les données propres à la mission sont demandées.  
Champ  Règle  
Disponibilité  Obligatoire ; Oui / Non / Partielle selon paramétrage.  
Proposition financière  TJM, forfait ou montant selon le type de mission.  
Délai de mobilisation  Optionnel ou obligatoire selon la mission.  
Approche proposée  Texte court ou note méthodologique.  
Documents complémentaires  Facultatifs ou imposés par les critères.  
Acceptation conditions  Consentements, confidentialité, règles de candidature.  
 
10. Pool unique, qualification et short -list 
Toutes les candidatures convergent dans un objet unique, indépendamment de leur origine. Chaque candidature porte 
une source : matching, portail, invitation directe ou ajout manuel.  
Le responsable dispose d’un Kanban : N ouveaux → Qualifi és → Short -list → Retenus, avec acc ès au score, aux 
alertes d ’éligibilit é et à la comparaison des profils.  
11. Scoring et aide à la décision  
Le scoring combine règles déterministes et, en V2, analyse sémantique IA. Les critères éliminatoir es sont évalués 
avant le score pondéré. L’IA recommande ; la sélection reste effectuée ou validée par l’acteur autorisé.  
Composante  Pondération indicative  
Compétences  30 % 
Expérience  20 % 
Expérience secteur  15 % 
Disponibilité  10 % 
Budget  10 % 
Réputation OPEX  10 % 
Localisation / langue  5 % 
 
Les pondérations sont configurables par type de mission ou par appel.  
12. États et workflows  
12.1 État de la mission  
DRAFT → QUALIFIED → SOURCING → OPEN → SELECTION → AWARDED → CONTRACTING → IN_PROGRESS → 
DELIVERED → ACCEPTED → CLOSED  
Branches : ON_HOLD · CANCELLED · UNSUCCESSFUL.

<!-- page 5 -->
CEO & DELTALOG  S.Babaci 29 -08-2026 notes de cadrage du module 3 (ZN et KA)  
OPEX Group — Spécification OPEX Smart Missions — Août 2026  12.2 État de la candidature  
INVITED → VIEWED → INTERESTED → APPLIED → SCREENED → SHORTLISTED → SELECTED  
Branches : DECLINED · REJECTED · WITHDRAWN.  
La séparation des deux machines  à états est obligatoire : l’avancement global de la mission ne doit pas être confondu 
avec le parcours individuel de chaque candidat.  
13. Sélection et déclenchement opérationnel  
Le passage d’une candidature à SELECTED déclenche, selon configuration : noti fication, collecte de pièces, NDA, 
génération du contrat, ordre de mission, création du projet/tâches, calendrier et accès documentaire.  
Les livrables définis lors de la création de la mission sont repris dans le suivi d’exécution puis dans le processus de  
service fait.  
14. Confidentialité et visibilité  
 La publication publique utilise une vue dédiée de la mission et non l’objet interne complet.  
 Les informations sensibles sont classées par niveau de visibilité.  
 Le candidat n’accède qu’aux données nécessaires  à sa décision et à sa candidature.  
 Un NDA peut conditionner l’accès à une data room ou à des documents détaillés.  
 Les décisions, changements d’état, consultations et documents doivent être auditables.  
15. Modèle de données cible  
Objet  Rôle 
res.partner  Référentiel unique des personnes et organisations.  
expert.profile  Extension métier du profil expert.  
expert.skill / experience / certification / 
availability / rating  Capital de compétences et données utilisées par le matching.  
mission.request  Objet central : besoin / mission.  
mission.skill.requirement  Compétences et niveaux requis.  
mission.criteria  Critères obligatoires et pondérés.  
mission.deliverable  Livrables, jalons et critères d’acceptation.  
mission.match  Résultat du matching mission -expert et explication du score.  
mission.application  Candidature unique, quelle que soit sa source.  
application.answer / score / document  Réponses, scoring et pièces propres à la candidature.  
mission.assignment  Affectation de l’expert sélectionné à la mission.  
service.acceptance  Validation du service fait.  
expert.evaluation  Évaluation finale alimentant la réputation.  
 
16. Relations principales  
res.partner  
   └──  expert.profile  
        ├──  skills  
        ├──  experiences  
        ├──  certifications  
        ├──  availability  
        └──  ratings

<!-- page 6 -->
CEO & DELTALOG  S.Babaci 29 -08-2026 notes de cadrage du module 3 (ZN et KA)  
OPEX Group — Spécification OPEX Smart Missions — Août 2026   
mission.request  
   ├──  requirements  
   ├──  criteria  
   ├──  deliverables  
   ├──  documents  
   ├──  mission.match ───────  expert.profile  
   └──  mission.application ─ expert.profile  
             ↓ 
      mission.assi gnment  
             ↓ 
     contract / project  
             ↓ 
        deliverables  
             ↓ 
      service.acceptance  
             ↓ 
      invoice / payment  
             ↓ 
      expert.evaluation  
17. Répartition Odoo natif / Custom OPEX  
Odoo 19 natif à  privilégier  Développement OPEX  
Contacts / res.partner  Profil expert enrichi  
Documents  Mission et exigences  
Discuss / Mail  Matching et explication du score  
Calendar  Candidature et pool candidats  
Project / Tasks  Workflow métier / règles de sélection  
Sale / Accounting  Portail public des missions  
Survey  Dashboards spécifiques et scoring  
 
18. UX cible par acteur  
Acteur  Écran / expérience principale  
Responsable OPEX  Smart Work Queue, missions à qualifier, matchings à valider, candidatures à traiter, décisions en attente.  
Expert  Opportunités recommandées, taux de match, prochaine action, candidatures et missions en cours.  
Candidat externe  Catalogue public des missions, filtres, fiche mission, candidature courte et suivi de statut.  
Client  Besoin, short -list autorisée, sélection/validation selon droits, avancement et service fait.  
 
19. Automatisations et notifications  
 Mission qualifiée → lancement automatique du matching si activ é. 
 Match supérieur à un seuil → proposition d ’invitation au responsabl e ou invitation automatique selon règle.  
 Publication → notification aux segments d ’experts pertinents.  
 Nouvelle candidature → précontr ôle d’éligibilit é et calcul du score.  
 Échéance proche → relance des experts invit és n’ayant pas r épondu.  
 Sélection → lance ment du sous -processus de contractualisation.

<!-- page 7 -->
CEO & DELTALOG  S.Babaci 29 -08-2026 notes de cadrage du module 3 (ZN et KA)  
OPEX Group — Spécification OPEX Smart Missions — Août 2026   Livrable déposé → demande de validation.  
 Service fait → facturation / paiement selon r ègles.  
 Clôture → enqu ête client + évaluation expert + mise à jour de r éputation.  
20. MVP recommandé  
Priorité MVP  Capacité  
P0 Création Lean et qualification d’une mission.  
P0 Profil expert structuré et compétences.  
P0 Matching par règles et score explicable.  
P0 Invitation ciblée d’experts.  
P0 Publication sur le portail Web.  
P0 Candidature Lean expert connu / candidat externe.  
P0 Pool candidat, Kanban, comparaison et short -list. 
P0 Sélection et déclenchement de la mission.  
P1 NDA, contrat et ordre de mission automatisés.  
P1 Livrables, service fait, évaluation.  
V2 Matching sémantique IA et analyse de l’approche.  
V2 Apprentissage à partir des missions passées et recommandation prédictive.  
 
21. Critères d’acceptation structurants  
 Une même mission peut activer Matching, Portail ou les deux sans duplication de mission.  
 Une candidature provenant du matching et une candi dature Web sont comparables dans le même écran.  
 Un expert référencé ne ressaisit pas son profil permanent pour candidater.  
 Le responsable peut comprendre les raisons d’un score de matching.  
 Les critères éliminatoires sont distingués du scoring pondéré.  
 La sélection d’un expert peut déclencher automatiquement contractualisation et exécution.  
 Les états Mission et Candidature sont indépendants.  
 Les données publiques et confidentielles d’une mission sont séparées.  
 La clôture d’une mission enrichit automatiqueme nt l’historique et la réputation de l’expert.
