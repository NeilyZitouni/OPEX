{
    'name': "OPEX Smart Crowdfunding",

    'summary': "Instance Smart Crowdfunding — implémentation texto du CEO Smart Workflow",

    'description': """
Smart Crowdfunding (implémentation texto)
=========================================
Implémente littéralement le processus décrit dans
« Instance Smart Crowdfunding - CEO Smart Workflow » : dix étapes, des états en
dur dans un Selection, des méthodes de transition en Python.

C'est volontaire. Ce module est la moitié d'une expérience : le même processus
est construit une seconde fois, par configuration, dans le module générique.
La comparaison des deux est le livrable.
    """,

    'author': "DELTALOG",
    'website': "https://www.deltalog-conseil.com",

    'category': 'Services/Crowdfunding',
    'version': '19.0.1.0.0',

    # Règle d'isolation : aucune dépendance vers un autre module OPEX — ni le
    # moteur générique, ni Membership. Ce module s'installe seul.
    # (Le nom du moteur n'est pas écrit ici : la commande de vérification de la
    # règle grep les sources, elle doit pouvoir passer au vert.)
    'depends': ['base', 'mail', 'contacts', 'portal', 'website'],

    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'data/criteria.xml',
        'data/compensation_types.xml',
        'views/crowdfunding_accompagnement_views.xml',
        'views/crowdfunding_work_queue_views.xml',
        'views/crowdfunding_project_views.xml',
        'views/crowdfunding_criteria_views.xml',
        'views/res_partner_views.xml',
        'views/crowdfunding_menus.xml',
        'views/portal_templates.xml',
    ],

    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
