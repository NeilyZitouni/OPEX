{
    'name': "OPEX Membership",

    'summary': "Gestion des adhérents, cotisations et vie du cluster GIC OPEX Group",

    'description': """
Module OPEX Membership (POC)
=============================
Gère le réseau et les adhérents du cluster GIC OPEX Group : adhésion,
cotisations, paiements, annuaire des membres et événements du cluster.
    """,

    'author': "DELTALOG",
    'website': "https://www.deltalog-conseil.com",

    'category': 'Services/Membership',
    'version': '19.0.1.19.1',

    # `calendar` : l'agenda natif vers lequel les événements du cluster sont
    # reflétés (Extension 2). Ajouter cette dépendance installe l'application
    # Calendrier si elle ne l'est pas déjà.
    'depends': ['base', 'mail', 'sale', 'portal', 'website', 'calendar'],

    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'data/membership_categories.xml',
        'data/certifications.xml',
        'data/ir_cron.xml',
        'data/website_menu.xml',
        'views/opex_membership_category_views.xml',
        'views/opex_membership_subcategory_views.xml',
        'views/opex_certification_views.xml',
        'views/res_partner_views.xml',
        'views/opex_membership_file_views.xml',
        'views/opex_subscription_views.xml',
        'views/opex_payment_views.xml',
        'views/opex_cluster_event_views.xml',
        'views/opex_membership_menus.xml',
        'views/opex_cluster_life_views.xml',
        'views/portal_templates.xml',
        'views/parcours_templates.xml',
        'views/notification_templates.xml',
        'views/subscription_portal_templates.xml',
        'views/cluster_portal_templates.xml',
        'views/dashboard_templates.xml',
        'views/directory_templates.xml',
        'views/website_homepage.xml',
        'views/staff_templates.xml',
        'views/website_menu_templates.xml',
    ],

    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
