from urllib.parse import quote

from odoo import _, http
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.http import request


class CrowdfundingStaffPortal(http.Controller):
    """Espace de traitement du Smart Crowdfunding, côté site web.

    **Écran de démonstration, pas remplacement du back-office.** Il porte la
    file de travail et les décisions qui tiennent en un bouton, pour qu'une
    démonstration ne quitte jamais le site. Ce qu'il ne couvre pas
    délibérément — matching financier, accompagnement, closing, chatter,
    filtres, et toute saisie riche — est listé dans le CLAUDE.md du module, et
    chaque fiche porte un lien vers le back-office pour ces cas-là.

    **Contrôle d'accès, deux niveaux, tous deux côté serveur :**

    1. `res.users._is_crowdfunding_staff()` en première ligne de **chaque**
       route — le point de contrôle de rôle unique du module (règle
       transversale 2), le même que celui qui décide de la tuile d'accueil ;
    2. `_crowdfunding_staff_project()`, qui ne retrouve un dossier qu'**à
       travers la file du rôle connecté**. Un identifiant forgé ne remonte donc
       rien, plutôt que de lever une erreur d'accès.

    Aucun `t-if` de gabarit ne sert de garde, et aucun droit de transition
    n'est rejugé ici : les méthodes du modèle gardent leurs `_ensure_ceo()` et
    `_ensure_quality_control()`, ce controller demande et rend le refus lisible.

    Nommage préfixé (règle transversale 1 bis) : cette classe descend de
    `http.Controller` et non de `CustomerPortal`, mais les noms de méthodes
    restent distincts de ceux des espaces de traitement des autres modules —
    `opex_membership` a `staff_membership_files`, `opex_innovation`
    `staff_projects`. Un homonyme ferait disparaître la route sans erreur.
    """

    # ------------------------------------------------------------------
    # La file de chaque rôle
    # ------------------------------------------------------------------
    def _crowdfunding_staff_user(self):
        """L'utilisateur s'il instruit les dossiers, sinon un recordset vide.

        Renvoie plutôt que de lever : une route qui lève affiche une page
        d'erreur technique, une route qui redirige garde l'utilisateur dans son
        espace. Le refus est total dans les deux cas.
        """
        user = request.env.user
        return user if user._is_crowdfunding_staff() else request.env['res.users'].browse()

    def _crowdfunding_staff_queues(self):
        """Les files du rôle connecté : libellé, domaine, et compteur.

        Les domaines ne sont **pas réécrits ici**. Ils viennent des six files
        de `opex.crowdfunding.work.queue`, celles-là mêmes que la Smart Work
        Queue du back-office compte et ouvre. Une seconde définition finirait
        par diverger, et le portail annoncerait autre chose que le back-office
        sur les mêmes dossiers.

        Deux des six ne portent pas sur des dossiers — « investisseurs en
        attente » compte des `opex.crowdfunding.relation`, « accompagnements en
        retard » des `opex.crowdfunding.accompagnement`. Elles sont affichées
        en compteur seul : leur traitement relève des écrans que cette page ne
        couvre pas.
        """
        Queue = request.env['opex.crowdfunding.work.queue'].sudo()
        Project = request.env['opex.crowdfunding.project'].sudo()
        user = request.env.user

        files = []
        if user.sudo()._has_group('opex_crowdfunding.group_quality_control'):
            # La file du Contrôle Qualité réunit ce que la Smart Work Queue
            # appelle « contrôles en anomalie » et les dossiers qui attendent
            # un **premier** contrôle — ces derniers n'ont pas de file nommée
            # dans le back-office, et une file qui ne montrerait que les
            # anomalies priverait le rôle de son travail principal.
            files.append({
                'code': 'quality_gate',
                'nom': _("Dossiers au contrôle qualité"),
                'aide': _("Complétude, cohérence, conformité, anomalies."),
                # `Domain.OR` et non `odoo.osv.expression.OR` : déprécié en
                # 19.0 (« use odoo.fields.Domain »), et l'avertissement sort à
                # chaque appel.
                'domaine': Domain.OR([
                    Queue._domaine_controles_anomalie(),
                    [('state', '=', 'quality_gate')],
                ]),
            })
        if user.sudo()._has_group('opex_crowdfunding.group_ceo'):
            files += [
                {'code': 'prequalifications',
                 'nom': _("Préqualifications"),
                 'aide': _("Dossiers déposés qui attendent un GO, une "
                           "clarification, une orientation ou un refus."),
                 'domaine': Queue._domaine_prequalifications()},
                {'code': 'decisions_ceo',
                 'nom': _("Décisions du comité"),
                 'aide': _("Dossiers à l'étude : Investment Ready, maturation "
                           "ou non retenu."),
                 'domaine': Queue._domaine_decisions_ceo()},
                {'code': 'matchings',
                 'nom': _("Matchings à valider"),
                 'aide': _("La liste des acteurs financiers s'arrête depuis le "
                           "back-office."),
                 'domaine': Queue._domaine_matchings_a_valider()},
            ]

        for file in files:
            file['projets'] = Project.search(
                file['domaine'], order='write_date desc, id desc')
        return files

    def _crowdfunding_staff_compteurs_hors_dossier(self):
        """Les deux files qui ne portent pas sur des dossiers, en compteur."""
        Queue = request.env['opex.crowdfunding.work.queue'].sudo()
        if not request.env.user.sudo()._has_group('opex_crowdfunding.group_ceo'):
            return []
        return [
            {'nom': _("Investisseurs en attente"),
             'nombre': request.env['opex.crowdfunding.relation'].sudo().search_count(
                 Queue._domaine_investisseurs_en_attente())},
            {'nom': _("Accompagnements en retard"),
             'nombre': request.env['opex.crowdfunding.accompagnement'].sudo().search_count(
                 Queue._domaine_accompagnements_en_retard())},
        ]

    def _crowdfunding_staff_projects(self):
        """Tous les dossiers des files du rôle, dédoublonnés."""
        projets = request.env['opex.crowdfunding.project'].sudo().browse()
        for file in self._crowdfunding_staff_queues():
            projets |= file['projets']
        return projets

    def _crowdfunding_staff_project(self, project_id):
        """Un dossier précis, **borné à la file du rôle connecté**.

        C'est ici que se joue le refus d'un identifiant forgé : le dossier
        n'est pas cherché puis contrôlé, il est cherché *dans* l'ensemble
        autorisé. Un Contrôle Qualité qui demande un dossier à l'étude du
        comité ne remonte rien.
        """
        return self._crowdfunding_staff_projects().filtered(
            lambda p: p.id == project_id)[:1]

    # ------------------------------------------------------------------
    # Les actions ouvertes à ce rôle, à cette étape
    # ------------------------------------------------------------------
    #: Étape → actions proposées. Chaque entrée nomme la méthode du **modèle**
    #: qui décide : ce controller n'a pas de logique de transition, il traduit
    #: un bouton en appel. `motif` marque les décisions que le modèle refuse
    #: sans texte — le champ est écrit avant l'appel, et c'est toujours le
    #: modèle qui refuse s'il est vide.
    _CROWDFUNDING_STAFF_ACTIONS = {
        'depot_express': (
            ('action_start_pre_analyse', "Démarrer la pré-analyse", 'ceo', False),
        ),
        'pre_analyse': (
            ('action_go', "GO — dossier à compléter", 'ceo', False),
            ('action_clarify', "À clarifier — envoyer les questions", 'ceo', False),
            ('action_orientation', "Orienter vers un accompagnement", 'ceo', False),
            ('action_no_go', "NO GO — clôturer le dossier", 'ceo', True),
        ),
        'quality_gate': (
            ('action_quality_ok', "Conforme — transmettre au comité", 'quality', False),
            ('action_quality_complement', "À compléter — renvoyer au porteur", 'quality', False),
            ('action_quality_alerte', "Alerte — signaler au comité", 'quality', False),
        ),
        'etude_decision': (
            ('action_route_investment_ready', "Route A — Investment Ready", 'ceo', False),
            ('action_route_maturation', "Route B — maturation nécessaire", 'ceo', False),
            ('action_route_rejected', "Route C — non retenu", 'ceo', True),
        ),
        'reevaluation': (
            ('action_retour_matching', "Renvoyer au Demo Day", 'ceo', False),
        ),
        'demo_day': (
            ('action_valider_demo_day', "Valider le Demo Day", 'ceo', False),
        ),
        'closing': (
            ('action_close', "Clôturer le dossier", 'ceo', False),
        ),
    }

    def _crowdfunding_staff_actions(self, project):
        """Ce que **ce** rôle peut faire sur **ce** dossier, à son étape.

        Liste d'affichage et de routage, pas d'autorisation : le modèle
        revérifie le rôle (`_ensure_ceo`, `_ensure_quality_control`) et l'état
        à chaque appel. Une action absente d'ici et forgée en POST est refusée
        par le modèle, avec son message.
        """
        user = request.env.user
        roles = set()
        if user.sudo()._has_group('opex_crowdfunding.group_ceo'):
            roles.add('ceo')
        if user.sudo()._has_group('opex_crowdfunding.group_quality_control'):
            roles.add('quality')
        return [
            {'code': code, 'libelle': libelle, 'motif': motif}
            for code, libelle, role, motif
            in self._CROWDFUNDING_STAFF_ACTIONS.get(project.state, ())
            if role in roles
        ]

    # ------------------------------------------------------------------
    # Route 1 — la file
    # ------------------------------------------------------------------
    @http.route(['/staff/crowdfunding'], type='http', auth='user', website=True)
    def staff_crowdfunding_files(self, **kw):
        if not self._crowdfunding_staff_user():
            return request.redirect('/my')
        return request.render('opex_crowdfunding.staff_crowdfunding_files', {
            'files': self._crowdfunding_staff_queues(),
            'compteurs': self._crowdfunding_staff_compteurs_hors_dossier(),
            'page_name': 'staff_crowdfunding',
        })

    # ------------------------------------------------------------------
    # Route 2 — la fiche, en lecture seule
    # ------------------------------------------------------------------
    @http.route(['/staff/crowdfunding/<int:project_id>'], type='http',
                auth='user', website=True)
    def staff_crowdfunding_file(self, project_id, **kw):
        if not self._crowdfunding_staff_user():
            return request.redirect('/my')
        project = self._crowdfunding_staff_project(project_id)
        if not project:
            return request.redirect('/staff/crowdfunding')

        return request.render('opex_crowdfunding.staff_crowdfunding_file', {
            'project': project,
            'actions': self._crowdfunding_staff_actions(project),
            'historique': project._portal_historique(),
            'error': kw.get('error'),
            'page_name': 'staff_crowdfunding',
        })

    # ------------------------------------------------------------------
    # Route 3 — l'action
    # ------------------------------------------------------------------
    @http.route(['/staff/crowdfunding/<int:project_id>/action'], type='http',
                auth='user', website=True, methods=['POST'])
    def staff_crowdfunding_action(self, project_id, **post):
        """Exécute une décision, en déléguant au modèle.

        Trois barrières, dans cet ordre : le rôle, l'appartenance du dossier
        à la file du rôle, puis la méthode du modèle elle-même. Le nom de
        méthode reçu du navigateur n'est jamais appelé tel quel : il est
        cherché dans la table des actions ouvertes à ce rôle à cette étape.
        """
        if not self._crowdfunding_staff_user():
            return request.redirect('/my')
        project = self._crowdfunding_staff_project(project_id)
        if not project:
            return request.redirect('/staff/crowdfunding')

        ouvertes = {a['code']: a for a in self._crowdfunding_staff_actions(project)}
        action = ouvertes.get(post.get('action'))
        if not action:
            return request.redirect('/staff/crowdfunding/%s' % project.id)

        try:
            with request.env.cr.savepoint():
                if action['motif']:
                    # Le modèle refuse un motif vide : on ne fait que le poser.
                    project.motif_rejet = (post.get('motif') or '').strip()
                getattr(project, action['code'])()
        except UserError as refus:
            return request.redirect(
                '/staff/crowdfunding/%s?error=%s' % (
                    project.id, quote(refus.args[0])))
        return request.redirect('/staff/crowdfunding/%s' % project.id)
