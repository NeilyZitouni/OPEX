{
    'name': "OPEX Innovation",

    'summary': "Module 2 du portail GIC OPEX Group — Innovation Booster",

    'description': """
OPEX Innovation (Innovation Booster)
====================================
Profils Expert et Investisseur, projets d'innovation, évaluation,
accompagnement et financement.

Ce module ne code aucun workflow. Les processus sont **configurés** sur le
moteur `opex_workflow` : c'est là toute la démonstration. Un modèle métier de ce
module qui porterait un `state = fields.Selection(...)` décrivant son
avancement annulerait le travail.
    """,

    'author': "DELTALOG",
    'website': "https://www.deltalog-conseil.com",

    'category': 'Services/Innovation',
    # Monotone, pas chronologique par numéro d'extension. L'Extension 17 est
    # écrite après la 20 ; revenir à 19.0.1.17.0 serait un retour en arrière de
    # version, qu'Odoo interprète comme « rien à faire ».
    'version': '19.0.1.24.0',

    # `opex_membership` : le Module 1 est la **source des profils métier**. On
    # en dépend pour lire ses catégories d'adhésion, jamais pour le modifier —
    # il est gelé avant sa présentation.
    'depends': [
        'base', 'mail', 'contacts', 'portal', 'website',
        'opex_workflow', 'opex_membership', 'project',
    ],

    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'data/innovation_roles.xml',
        'data/profile_workflow.xml',
        'data/remediation_points.xml',
        'data/project_workflow.xml',
        'data/matching_criteria.xml',
        # Seconde instance du moteur, configurée en données seules. Chargée
        # après `project_workflow.xml` : elle réutilise ses rôles.
        'data/smart_crowdfunding.xml',
        # Extension 17 — troisième instance du moteur, sur un modèle qui n'est
        # pas le projet.
        'data/industrialisation_workflow.xml',
        # Extension 18 — chargé en dernier des données : il rebranche les
        # actions de transitions posées par les fichiers précédents.
        'data/notifications.xml',
        # Extension 19 — les jalons lisibles par le porteur.
        'data/milestones.xml',
        # Extension 16 — cinquième instance du moteur. Chargée **après**
        # `notifications.xml` : elle y rebranche les trois actions 10. 11. 12. restées
        # orphelines faute de transitions auxquelles les accrocher.
        'data/roadmap_phases.xml',
        'data/deliverable_workflow.xml',
        'views/innovation_project_views.xml',
        'views/expert_profile_views.xml',
        'views/investor_profile_views.xml',
        'views/res_partner_views.xml',
        'views/portal_templates.xml',
        'views/project_portal_templates.xml',
        'views/staff_templates.xml',
        'views/evaluation_views.xml',
        'views/evaluation_templates.xml',
        'views/remediation_views.xml',
        'views/remediation_templates.xml',
        'views/matching_templates.xml',
        'views/innovation_menus.xml',
        # Extension 17 — chargé après les menus : il s'y raccroche.
        'views/extension17_views.xml',
        'views/investor_templates.xml',
        # Extension 19 — hérite de `staff_projects` : chargé après lui.
        'views/dashboard_templates.xml',
        # Extension 16 — se raccroche aux menus.
        'views/accompagnement_views.xml',
        'views/deliverable_templates.xml',
    ],

    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
