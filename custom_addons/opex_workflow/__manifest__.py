{
    'name': "OPEX Smart Workflow",

    'summary': "Moteur générique de workflow — définition, exécution, audit",

    'description': """
OPEX Smart Workflow — moteur générique
======================================
Décrit un processus métier sous forme de données (définition, étapes,
transitions, règles, rôles, actions) et le fait exécuter par n'importe quel
modèle Odoo, natif ou custom.

Le moteur ne contient aucune logique métier : il ne connaît ni « projet », ni
« investisseur », ni « pitch deck ». Un module métier le pilote en héritant de
`opex.workflow.mixin` et en configurant sa définition en données.
    """,

    'author': "DELTALOG",
    'website': "https://www.deltalog-conseil.com",

    'category': 'Services/Workflow',
    'version': '19.0.1.8.0',

    # Un moteur qui dépend de `sale` ou de `website` n'est pas un moteur.
    #
    # `mail` : le suivi (`tracking=True`) des définitions et le `message_post()`
    #          des actions de notification.
    # `portal` : **écart assumé** au « base + mail, rien d'autre » de la
    #          spécification, ajouté en Extension 6. Les formulaires dynamiques
    #          doivent se rendre sur une vraie page portail, et le portail
    #          générique de l'Extension 8 en aura besoin de toute façon.
    #          `portal` ne tire que de l'infrastructure — web, http_routing,
    #          mail, auth_signup — et aucun module métier : la règle visait
    #          `sale` et `website`, elle est respectée dans son intention.
    'depends': ['base', 'mail', 'portal'],

    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'data/workflow_roles.xml',
        'data/ir_cron.xml',
        'wizard/workflow_transition_wizard_views.xml',
        'views/workflow_definition_views.xml',
        'views/workflow_referential_views.xml',
        'views/workflow_form_views.xml',
        'views/workflow_form_templates.xml',
        'views/workflow_instance_views.xml',
        'views/workflow_task_views.xml',
        'views/matching_views.xml',
        'views/workflow_portal_templates.xml',
        'views/workflow_menus.xml',
    ],

    'demo': [
        'demo/workflow_demo.xml',
    ],

    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
