{
    'name': "OPEX AI Core",

    'summary': "Le service d'assistance IA du portail GIC OPEX Group",

    'description': """
OPEX AI Core
============

Le seul endroit du projet qui parle à une API externe.

Un `AbstractModel` `opex.ai.service` expose une méthode, `_call()`, qui rend un
dictionnaire ou None. Un journal `opex.ai.call.log` enregistre chaque appel.
Les prompts vivent en données versionnées, jamais en dur dans le code.

POURQUOI UN MODULE A PART

Ce service a d'abord été écrit dans `opex_intervenants`, où l'onboarding
expert avait besoin de lui. Il en a été extrait avant que quoi que ce soit
soit construit dessus, et pour une raison précise : le backlog prévoit
`opex_ai_core` pour l'US-23, qui est une fonctionnalité d'`opex_membership`.
Laisser le service dans le Module 3 aurait obligé le Module 1 à en dépendre le
jour où il aurait voulu de l'IA - une inversion de dépendance que rien
n'aurait justifiée.

L'extraction était mécanique tant qu'aucun fichier `ai_*.py` n'importait de
modèle métier. Elle ne le serait pas restée.

CE QUE CE MODULE NE FAIT PAS

Il n'extrait rien, il ne décide rien, il n'écrit aucune donnée métier. Il
appelle un fournisseur et rend ce qu'il a reçu. Les modules appelants
décident de ce qu'ils en font, et ce sont eux qu'on tiendra responsables de ce
qu'ils écrivent en base.
""",

    'author': "DELTALOG",
    'website': "https://www.deltalog-conseil.com",

    'category': 'Technical',
    'version': '19.0.1.0.0',

    # `base` et rien d'autre. Un service d'infrastructure qui dépendrait d'un
    # module métier ne serait plus un service d'infrastructure - c'est
    # exactement la faute qu'on vient de corriger en l'extrayant.
    'depends': ['base'],

    'data': [
        'security/ir.model.access.csv',
        # Les prompts avant les vues : rien ne les référence encore, mais
        # l'ordre dit la dépendance.
        'data/ai_prompts.xml',
        # LES PROMPTS METIER VIVENT ICI, ET C'EST UNE CONSEQUENCE ASSUMEE.
        #
        # Ils étaient d'abord dans `opex_intervenants`, au motif qu'un prompt
        # métier appartient au module qui a le métier. Cet argument tenait
        # tant que le Module 3 déclarait `opex_ai_core` en dépendance.
        #
        # Il ne la déclare plus : le portail doit rester livrable sans
        # assistance IA. Or un `<record model="opex.ai.prompt">` ne peut être
        # chargé que par un module qui connaît ce modèle. Les prompts
        # descendent donc ici.
        #
        # Ce que cela coûte : écrire un prompt pour un nouveau domaine demande
        # de toucher ce module. Ce que cela préserve : les modules métier
        # s'installent sans lui. Le second compte plus - un prompt est du
        # texte, une dépendance est structurelle.
        #
        # Ce module ne référence toujours aucun modèle métier : ces fichiers
        # ne portent que des chaînes de caractères.
        'data/prompts_cv.xml',
        'data/prompts_taxonomy.xml',
        'data/prompts_qualification.xml',
        'views/ai_views.xml',
    ],

    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
