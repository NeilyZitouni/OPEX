import base64
from urllib.parse import quote

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import content_disposition, request

from .portal import InnovationProfilePortal


class InnovationStaffPortal(http.Controller):
    """Écrans du personnel : contrôle administratif et qualification.

    **Le contrôle d'accès staff est une seule fonction**, `_staff_user()`,
    appelée par toutes les routes `/staff/innovation/*`. Une vérification
    recopiée finit par en oublier une occurrence — et c'est celle-là qui reçoit
    la requête forgée. C'est la règle transversale héritée du Module 1, et elle
    a déjà été payée une fois.
    """

    def _staff_user(self):
        """L'utilisateur connecté s'il est habilité, sinon un recordset vide.

        Renvoie plutôt que de lever : une route qui lève affiche une page
        d'erreur technique ; une route qui redirige garde l'utilisateur dans
        son espace. Le refus reste total dans les deux cas.

        La liste des groupes habilités n'est plus ici mais sur
        `res.users._is_innovation_staff()` : un gabarit ne peut pas appeler un
        helper de controller, et la tuile « Espace d'évaluation » de l'accueil
        du portail doit poser exactement la même question que ces routes. Deux
        listes auraient fini par diverger — la tuile visible pour un rôle que
        la route refuse, ou l'inverse.
        """
        user = request.env.user
        return user if user._is_innovation_staff() else request.env['res.users'].browse()

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

        Aucun contrôle de droit n'est réécrit ici. La transition est cherchée
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
        return request.redirect(
            '/staff/innovation/%s?error=%s' % (project.id, quote(message)))


class InnovationProfileStaffPortal(http.Controller):
    """Le pendant staff des demandes de profil Expert et Investisseur.

    Calqué sur `InnovationStaffPortal` ci-dessus, et pour la même raison :
    `rule_instance_internal` borne les utilisateurs internes aux dossiers
    **dont ils sont acteurs**, or le Secrétariat tient son rôle d'un
    **groupe** et n'est acteur d'aucune demande. Sans lecture en `sudo()`
    après contrôle d'habilitation, sa file serait vide et le processus sans
    issue — c'est exactement ce qui bloquait les demandes de profil jusqu'ici.

    L'ordre compte : on vérifie **puis** on lit en `sudo()`. L'inverse —
    lire d'abord — donnerait tous les dossiers à tout le monde.
    """

    #: Importée plutôt que recopiée : la correspondance type → modèle est
    #: déjà déclarée côté porteur, et deux copies finiraient par diverger le
    #: jour où un troisième profil apparaît.
    _PROFILE_MODELS = InnovationProfilePortal._PROFILE_MODELS

    _PROFILE_LABELS = {'expert': "Expert", 'investor': "Investisseur"}

    #: Ce que le Secrétariat a à traiter. `complement_requested` y figure bien
    #: que la balle soit dans le camp du membre : le contrôleur doit voir ce
    #: qu'il a demandé et ce qui n'est pas revenu, sinon un dossier en attente
    #: de complément disparaît de son écran et personne ne le relance.
    _SECRETARIAT_STAGES = ('submitted', 'review', 'complement_requested')

    def _profile_staff_user(self):
        """L'utilisateur connecté s'il instruit les dossiers, sinon vide.

        Ce n'est pas un second contrôle d'accès : la politique vit dans
        `res.users._is_innovation_staff()`, l'unique endroit qui dit quels
        groupes instruisent — le même que celui qu'interroge `_staff_user()`
        des projets et le `t-if` de la tuile portail. On ne redéclare ici
        aucune liste de groupes.

        Renvoie plutôt que de lever : une route qui lève affiche une page
        d'erreur technique, une route qui redirige garde l'utilisateur dans
        son espace. Le refus est total dans les deux cas.
        """
        user = request.env.user
        return user if user._is_innovation_staff() else \
            request.env['res.users'].browse()

    def _profile_requests(self):
        """Les demandes que **ce** membre du personnel doit voir.

        Les deux modèles sont interrogés séparément — le moteur pilote par
        `res_model`/`res_id`, il n'exige pas que les objets se ressemblent —
        puis rassemblés en une seule file : un contrôleur a une file de
        travail, pas deux écrans à surveiller.
        """
        user = self._profile_staff_user()
        if not user:
            return []

        manager = user.sudo()._has_group('opex_innovation.group_innovation_manager')
        secretariat = user.sudo()._has_group('opex_membership.group_secretariat')
        if not (manager or secretariat):
            return []

        domain = ([('workflow_state', '=', 'running')] if manager
                  else [('workflow_stage_id.code', 'in', self._SECRETARIAT_STAGES)])

        demandes = []
        for profile_type, model in self._PROFILE_MODELS.items():
            for profile in request.env[model].sudo().search(domain):
                demandes.append({
                    'type': profile_type,
                    'label': self._PROFILE_LABELS[profile_type],
                    'profile': profile,
                })
        # Le plus ancien en premier : une file de travail se traite dans
        # l'ordre d'arrivée, pas dans l'ordre des identifiants techniques.
        return sorted(demandes, key=lambda d: d['profile'].create_date)

    def _profile_request(self, profile_type, profile_id):
        """Une demande précise, bornée au périmètre du personnel connecté.

        Résolue **dans** la file plutôt que par un `browse()` direct : c'est
        le même filtre qui décide de ce qu'on voit en liste et de ce qu'on
        peut ouvrir. Un identifiant deviné ne donne donc rien de plus que la
        liste n'en montrait.
        """
        for demande in self._profile_requests():
            if demande['type'] == profile_type \
                    and demande['profile'].id == profile_id:
                return demande
        return None

    def _profile_back(self, profile_type, profile_id, message=None):
        url = '/staff/innovation/profiles/%s/%s' % (profile_type, profile_id)
        if message:
            url += '?error=%s' % quote(str(message))
        return request.redirect(url)

    # ------------------------------------------------------------
    # La file des demandes
    # ------------------------------------------------------------

    @http.route(['/staff/innovation/profiles'], type='http', auth='user',
                website=True)
    def staff_profile_queue(self, **kw):
        if not self._profile_staff_user():
            return request.redirect('/my')
        return request.render('opex_innovation.staff_profile_queue', {
            'demandes': self._profile_requests(),
            'page_name': 'staff_innovation_profiles',
        })

    # ------------------------------------------------------------
    # Le détail d'une demande
    # ------------------------------------------------------------

    @http.route(['/staff/innovation/profiles/<string:profile_type>/<int:profile_id>'],
                type='http', auth='user', website=True)
    def staff_profile_detail(self, profile_type, profile_id, **kw):
        if not self._profile_staff_user():
            return request.redirect('/my')
        demande = self._profile_request(profile_type, profile_id)
        if not demande:
            return request.redirect('/staff/innovation/profiles')

        profile = demande['profile']
        instance = profile.workflow_instance_id
        return request.render('opex_innovation.staff_profile_detail', {
            'demande': demande,
            'profile': profile,
            'profile_type': profile_type,
            'instance': instance,
            # Les actions viennent du moteur, pas d'une liste écrite ici : le
            # jour où le processus change, cet écran suit sans être touché.
            'options': instance.transition_options(user=request.env.user),
            'error': kw.get('error'),
            'page_name': 'staff_innovation_profiles',
        })

    # ------------------------------------------------------------
    # Consultation d'une pièce jointe
    # ------------------------------------------------------------

    @http.route(['/staff/innovation/profiles/<string:profile_type>'
                 '/<int:profile_id>/document/<int:document_id>'],
                type='http', auth='user')
    def staff_profile_document(self, profile_type, profile_id, document_id, **kw):
        """Sert une pièce jointe au contrôleur.

        La pièce est résolue **à travers la demande**, jamais par un
        `browse()` sur l'identifiant reçu. Un identifiant forgé ne peut donc
        pas servir à extraire le justificatif d'un autre dossier : il faut
        déjà que la demande soit dans le périmètre du contrôleur, et que la
        pièce lui appartienne.
        """
        if not self._profile_staff_user():
            return request.redirect('/my')
        demande = self._profile_request(profile_type, profile_id)
        if not demande:
            return request.redirect('/staff/innovation/profiles')

        document = demande['profile'].document_ids.filtered(
            lambda d: d.id == document_id)[:1]
        if not document or not document.file:
            return self._profile_back(profile_type, profile_id,
                                      _("Cette pièce est introuvable."))

        contenu = base64.b64decode(document.file)
        nom = document.filename or document.name or 'justificatif'
        return request.make_response(contenu, headers=[
            # `octet-stream` et pièce jointe : on ne rend pas dans la page un
            # fichier déposé par un tiers. Un HTML ou un SVG servi en ligne
            # s'exécuterait dans la session du contrôleur.
            ('Content-Type', 'application/octet-stream'),
            ('Content-Length', str(len(contenu))),
            ('Content-Disposition', content_disposition(nom)),
        ])

    # ------------------------------------------------------------
    # Les décisions du Secrétariat
    # ------------------------------------------------------------

    @http.route(['/staff/innovation/profiles/<string:profile_type>'
                 '/<int:profile_id>/transition'],
                type='http', auth='user', website=True, methods=['POST'])
    def staff_profile_transition(self, profile_type, profile_id, **post):
        """Franchit une transition depuis l'écran de contrôle.

        Aucun droit n'est rejugé ici, exactement comme côté porteur. La
        transition est cherchée parmi celles que le moteur propose à cet
        utilisateur, puis franchie par `workflow_do_transition()`, qui
        repasse par `_check_transition_allowed()`. Le motif obligatoire est
        exigé par la configuration (`requires_comment`) et refusé par
        `do_transition()`, pas par ce controller — le `required` du gabarit
        n'est qu'un confort d'écran.
        """
        if not self._profile_staff_user():
            return request.redirect('/my')
        demande = self._profile_request(profile_type, profile_id)
        if not demande:
            return request.redirect('/staff/innovation/profiles')

        profile = demande['profile']
        raw = (post.get('transition_id') or '').strip()
        allowed = profile.workflow_instance_id.available_transitions(
            user=request.env.user)
        transition = allowed.filtered(lambda t: str(t.id) == raw)[:1]
        if not transition:
            return self._profile_back(profile_type, profile_id, _(
                "Cette action n'est plus disponible sur cette demande."))

        comment = (post.get('comment') or '').strip()
        try:
            profile.workflow_do_transition(transition, comment=comment)
            # Le motif est recopié sur la demande pour que le membre le lise
            # en évidence, sans avoir à parcourir l'historique. La méthode
            # existe déjà sur les deux profils : on ne réécrit pas le champ à
            # la main depuis un controller.
            if transition.code == 'request_complement':
                profile.action_record_complement(comment)
        except UserError as refus:
            return self._profile_back(profile_type, profile_id, refus)

        return self._profile_back(profile_type, profile_id)
