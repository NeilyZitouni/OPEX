{
    'name': "OPEX Intervenants",

    'summary': "Module 3 du portail GIC OPEX Group — Smart Missions",

    'description': """
OPEX Intervenants / Smart Missions
==================================

Appels à candidatures, matching mission / expert, exécution des missions,
réputation des intervenants.

Ce module ne code aucun workflow. Il en configure deux, sur le moteur
opex_workflow : l'avancement d'une mission et le parcours d'une candidature.
Ni opex.mission.request ni opex.mission.application ne portent de champ state
- c'est là toute la démonstration des deux modules précédents. Un
state = fields.Selection(...) ajouté pour aller plus vite l'annulerait, et un
test l'interdit explicitement.

Les deux machines à états sont séparées, sur deux modèles distincts : une
mission en sélection porte simultanément des candidatures short-listées,
écartées et déposées, et aucune des deux ne se dérive de l'autre.
""",

    'author': "DELTALOG",
    'website': "https://www.deltalog-conseil.com",

    'category': 'Services/Missions',
    # Monotone. Cette version referme la dette D1 : le critere eliminatoire
    # de certification compare des references canoniques au lieu de texte
    # libre, et les certifications extraites d'un CV se promeuvent.
    'version': '19.0.21.0.0',

    # `opex_innovation` : le profil expert et le référentiel de compétences
    # viennent de là et ne sont pas recréés. « Un expert référencé ne ressaisit
    # pas son profil permanent pour candidater. »
    #
    # Pas `opex_crowdfunding` : ce module est isolé par construction, rien ne
    # doit le référencer.
    #
    # PAS `opex_ai_core`, PAS `sale`, PAS `project` — et les trois pour la
    # même raison, qui est une décision d'architecture et pas un oubli.
    #
    # Ces trois modules ne sont pas disponibles sur l'instance de
    # déploiement. Les déclarer ici rendait `opex_intervenants` **non
    # installable** : Odoo refuse un module dont une dépendance est
    # introuvable, et le refus est total — ni portail, ni matching, ni
    # workflows, pour trois fonctionnalités de bout de chaîne.
    #
    # Ils sont donc résolus **au moment de l'appel** :
    #
    #   - `opex_ai_core` par `opex.ai.bridge` (Extension IA-1) ;
    #   - `sale` et `project` par `opex.optional.backend`.
    #
    # C'est la règle 1 du service d'IA portée d'un cran plus haut : si une clé
    # absente ne doit bloquer aucun parcours, un module absent non plus.
    #
    # Ce que le portail perd sans `sale` et `project` est décrit dans
    # `docs/fonctions_desactivees.md`, et la marche à suivre pour rebrancher
    # est dans la docstring de `models/optional_backends.py`. Les points de
    # rebranchement se listent par :
    #
    #     grep -rn "REBRANCHEMENT" models/ views/ data/ tests/
    'depends': [
        'base', 'mail', 'contacts', 'portal', 'website',
        'opex_workflow', 'opex_innovation',
    ],

    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'data/mission_sequence.xml',
        # Les rôles rattachent les groupes ci-dessus au référentiel du moteur :
        # chargés après la sécurité, avant les workflows qui s'en servent.
        'data/mission_roles.xml',
        'data/mission_referentials.xml',
        'data/mission_request_workflow.xml',
        'data/mission_application_workflow.xml',
        'views/mission_referential_views.xml',
        'views/mission_request_views.xml',
        'views/mission_application_views.xml',
        # Chargé en dernier des vues back-office : les actions ci-dessus s'y
        # raccrochent.
        'views/mission_menus.xml',
        # Extension 2 — le parcours client au portail. Séparé du back-office :
        # ces gabarits se greffent sur `portal.portal_my_home`, pas sur nos
        # propres actions.
        'views/portal_templates.xml',
        # Extension 3 — le capital de l'intervenant. Chargé **après**
        # `mission_menus.xml` : le menu « Capital des intervenants » s'accroche
        # à `menu_intervenants_root`, qui y est défini.
        'views/expert_capital_views.xml',
        'views/expert_portal_templates.xml',
        # Extension 4 — le Smart Matching. `matching_criteria.xml` est chargé
        # après `mission_referentials.xml` : les profils par type référencent
        # `mission_type_formation` et `mission_type_audit`.
        'data/matching_criteria.xml',
        'views/matching_views.xml',
        'views/staff_templates.xml',
        # Extension 5 — la rubrique publique et la candidature Lean.
        # `public_templates.xml` pose une entrée de menu `website.menu` :
        # chargé après les autres vues, il ne dépend d'aucune action.
        'views/public_templates.xml',
        'views/candidature_templates.xml',
        # Extension 6 — le pool unique. Chargé après
        # `mission_application_views.xml` (il hérite de sa liste et de sa
        # recherche) et après `mission_menus.xml` (le menu s'y raccroche).
        'views/application_pool_views.xml',
        # Extension 7 — sélection et contractualisation.
        #
        # L'ordre de ces trois fichiers est une condition de fonctionnement,
        # pas une préférence :
        #
        #   1. `mission_contract_workflow.xml` crée la définition
        #      `mission_contract` et sa séquence ;
        #   2. `mission_contracting_actions.xml` la référence
        #      (`sub_definition_id`) et rattache la règle 5 à une transition de
        #      l'Extension 1 par `<function name="write">` ;
        #   3. `mission_contract_views.xml` hérite de
        #      `view_mission_request_form`, définie plus haut.
        'data/mission_contract_workflow.xml',
        'data/mission_contracting_actions.xml',
        'report/mission_contract_reports.xml',
        'views/mission_contract_views.xml',
        # Extension 8 — l'exécution. `mission_deliverable_workflow.xml` doit
        # être chargé après `mission_request_workflow.xml` : il rattache la
        # condition de dépôt à `mtr_deliver` par `<function name="write">`.
        'data/mission_deliverable_workflow.xml',
        'views/mission_execution_views.xml',
        # Extension 9 — service fait et facturation.
        #
        # L'ordre de ces trois fichiers est une condition de fonctionnement :
        #
        #   1. `mission_invoicing_data.xml` crée le produit de service que
        #      `_create_sale_order()` référence par `env.ref()` ;
        #   2. `service_acceptance_workflow.xml` crée la définition, puis
        #      rattache par `<function name="write">` la règle 6 — déclarée à
        #      l'Extension 1 — à `mtr_accept_service` et à sa propre
        #      « Valider (cluster) », et la facturation à `mtr_close` ;
        #   3. `service_acceptance_views.xml` hérite de
        #      `view_mission_request_form`, définie bien plus haut.
        'data/mission_invoicing_data.xml',
        'data/service_acceptance_workflow.xml',
        'views/service_acceptance_views.xml',
        # Extension 10 - évaluations et réputation. La définition rattache par
        # `<function name="write">` l'ouverture des évaluations à
        # « Facturer et clôturer », posée à l'Extension 1 ; les vues héritent
        # du formulaire de l'appel et de celui du profil expert.
        'data/mission_evaluation_workflow.xml',
        'views/mission_evaluation_views.xml',
        # Extension 11 - tableaux de bord et notifications.
        #
        # `mission_notifications.xml` est chargé après les cinq définitions :
        # il rattache des actions à des transitions posées par les Extensions 1
        # et 7, ce qui suppose qu'elles existent.
        #
        # `dashboard_templates.xml` hérite de `portal_my_missions`
        # (Extension 2) et de `staff_missions` (Extension 4) : il vient donc
        # après `portal_templates.xml` et `staff_templates.xml`.
        'data/mission_notifications.xml',
        'views/dashboard_templates.xml',
        # Extension 12 - l'intégration finale. Chargé en dernier de tout :
        # `integration_templates.xml` hérite de `public_missions`
        # (Extension 5) et de `staff_work_queue` (Extension 11).
        'views/integration_templates.xml',
        # Extension IA-1 - les trois axes du §9 et la lecture d'un CV du §6.
        #
        # Ni prompt ni raccourci vers le journal ici : les deux supposeraient
        # de connaître des modèles d'`opex_ai_core`, qui n'est pas une
        # dépendance. Les prompts sont livrés par ce module-là ; le journal se
        # consulte depuis Paramètres.
        #
        # `expert_cv_views.xml` hérite de `view_expert_profile_form_capital`
        # (Extension 3) : chargé après elle.
        # Le démarrage des missions à leur date de début contractuelle.
        # Après les workflows : il référence `mission_start`, qui est déclarée
        # par `mission_request_workflow.xml`.
        'data/ir_cron_mission_autostart.xml',
        'data/ir_cron_cv_parsing.xml',
        'views/expert_cv_views.xml',
        # Extension IA-2 - la taxonomie du §8 et le rapprochement en deux temps.
        #
        # `skill_catalog.xml` avant les vues : il seme les domaines, les
        # familles, les competences et leurs synonymes, que les ecrans
        # affichent. Il est aussi charge apres `mission_referentials.xml`,
        # dont il partage l'esprit - un referentiel se seme, il ne se code pas.
        'data/skill_catalog.xml',
        'views/skill_catalog_views.xml',
        # Dette D1 - le referentiel de certifications. Charge APRES
        # `matching_criteria.xml` : le critere eliminatoire y reference
        # desormais `certification_ids` et `expert_certification_ref_ids`,
        # et la requalification des six normes du Module 1 doit avoir eu lieu
        # avant qu'un ecran les propose.
        'data/certification_catalog.xml',
        'views/certification_catalog_views.xml',
        # Extension IA-3 - le controle qualite assiste. La definition est
        # chargee apres `mission_roles.xml` (elle y ajoute un role) et apres
        # les modeles de capital, qu'elle controle.
        'data/expert_qualification_workflow.xml',
        'views/expert_qualification_views.xml',
        'views/competence_taxonomy_views.xml',
    ],

    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
