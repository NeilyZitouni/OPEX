from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request


class InnovationStaffPortal(http.Controller):
    """Écrans du personnel : contrôle administratif et qualification.

    ⚠ **Le contrôle d'accès staff est une seule fonction**, `_staff_user()`,
    appelée par toutes les routes `/staff/innovation/*`. Une vérification
    recopiée finit par en oublier une occurrence — et c'est celle-là qui reçoit
    la requête forgée. C'est la règle transversale héritée du Module 1, et elle
    a déjà été payée une fois.
    """

    #: Groupes qui ouvrent les écrans de contrôle. Table plutôt que suite de
    #: `has_group()` : ajouter un profil habilité est une ligne.
    _STAFF_GROUPS = (
        'opex_membership.group_secretariat',
        'opex_innovation.group_innovation_manager',
        'opex_innovation.group_comite_evaluation',
    )

    def _staff_user(self):
        """L'utilisateur connecté s'il est habilité, sinon un recordset vide.

        Renvoie plutôt que de lever : une route qui lève affiche une page
        d'erreur technique ; une route qui redirige garde l'utilisateur dans
        son espace. Le refus reste total dans les deux cas.
        """
        user = request.env.user
        if any(user.sudo()._has_group(group) for group in self._STAFF_GROUPS):
            return user
        return request.env['res.users'].browse()

    def _staff_projects(self):
        """Les projets que **ce** membre du personnel doit voir.

        Le filtrage suit le rôle, pas le groupe : le secrétariat voit ce qui
        attend un contrôle, le comité ce qui attend une évaluation. Un
        gestionnaire voit tout — c'est le sens de son groupe.

        Lecture en `sudo()` **après** le contrôle d'habilitation : les `ir.rule`
        du moteur accordent la visibilité par ligne d'acteur, or le personnel
        tient son rôle d'un groupe et n'est acteur d'aucun dossier. Sans cela,
        le secrétariat aurait une file de travail vide.
        """
        user = self._staff_user()
        if not user:
            return request.env['opex.innovation.project'].browse()

        Project = request.env['opex.innovation.project'].sudo()
        stages = []
        if user.sudo()._has_group('opex_membership.group_secretariat'):
            stages += ['submitted', 'under_review', 'complement_requested']
        if user.sudo()._has_group('opex_innovation.group_comite_evaluation'):
            stages += ['qualified', 'evaluation', 'resubmitted']
        if user.sudo()._has_group('opex_innovation.group_innovation_manager'):
            return Project.search([('workflow_state', '=', 'running')])

        return Project.search([('workflow_stage_id.code', 'in', stages)])

    def _staff_project(self, project_id):
        """Un projet précis, borné au périmètre du personnel connecté."""
        return self._staff_projects().filtered(
            lambda p: p.id == project_id)[:1]

    # ------------------------------------------------------------
    # Section 13 — La file de contrôle
    # ------------------------------------------------------------

    @http.route(['/staff/innovation'], type='http', auth='user', website=True)
    def staff_projects(self, **kw):
        if not self._staff_user():
            return request.redirect('/my')
        projects = self._staff_projects()
        return request.render('opex_innovation.staff_projects', {
            'projects': projects,
            'page_name': 'staff_innovation',
        })

    # ------------------------------------------------------------
    # Section 13 — Le dossier vu par le contrôleur
    # ------------------------------------------------------------

    @http.route(['/staff/innovation/<int:project_id>'], type='http',
                auth='user', website=True)
    def staff_project_detail(self, project_id, **kw):
        """Tout ce que le secrétariat doit voir pour contrôler.

        « Il voit : Projet, Porteur, Organisation, Secteur, Description,
        Documents, Besoins, Financement, Historique. » La page les rassemble
        sur un seul écran : un contrôle qui oblige à naviguer entre quatre
        onglets se fait mal.
        """
        if not self._staff_user():
            return request.redirect('/my')
        project = self._staff_project(project_id)
        if not project:
            return request.redirect('/staff/innovation')

        instance = project.workflow_instance_id
        return request.render('opex_innovation.staff_project_detail', {
            'project': project,
            'instance': instance,
            # Les actions possibles viennent du moteur, pas d'une liste écrite
            # ici : le jour où le processus change, cet écran suit.
            'options': instance.transition_options(user=request.env.user),
            'summary': project.qualification_summary(),
            'error': kw.get('error'),
            'page_name': 'staff_innovation',
        })

    # ------------------------------------------------------------
    # Les deux issues du contrôle
    # ------------------------------------------------------------

    @http.route(['/staff/innovation/<int:project_id>/transition'], type='http',
                auth='user', website=True, methods=['POST'])
    def staff_project_transition(self, project_id, **post):
        """Franchit une transition depuis l'écran de contrôle.

        ⚠ Aucun contrôle de droit n'est réécrit ici. La transition est cherchée
        **dans** celles que le moteur propose à cet utilisateur, puis franchie
        par `do_transition()`, qui repasse par `_check_transition_allowed()`.
        Le motif obligatoire est exigé par la configuration
        (`requires_comment`), pas par ce controller.
        """
        if not self._staff_user():
            return request.redirect('/my')
        project = self._staff_project(project_id)
        if not project:
            return request.redirect('/staff/innovation')

        raw = (post.get('transition_id') or '').strip()
        allowed = project.workflow_instance_id.available_transitions(
            user=request.env.user)
        transition = allowed.filtered(lambda t: str(t.id) == raw)[:1]
        if not transition:
            return self._back(project, _(
                "Cette action n'est plus disponible sur ce dossier."))

        comment = (post.get('comment') or '').strip()
        try:
            project.workflow_do_transition(transition, comment=comment)
        except UserError as error:
            return self._back(project, str(error))

        # Le motif du complément est recopié sur le projet pour que le porteur
        # le lise en évidence, sans avoir à parcourir l'historique.
        if transition.code == 'request_complement':
            project.sudo().motif_complement = comment

        return request.redirect('/staff/innovation/%s' % project.id)

    def _back(self, project, message):
        from urllib.parse import quote
        return request.redirect(
            '/staff/innovation/%s?error=%s' % (project.id, quote(message)))
