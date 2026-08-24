from odoo import _, http
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal


class InnovationProjectPortal(CustomerPortal):
    """Dépôt d'un projet en cinq écrans, avec brouillon automatique.

    Le parcours reprend le mécanisme validé sur le dossier d'adhésion du
    Module 1 : le projet est créé **dès le premier écran**, chaque écran fait un
    `write()` partiel, et l'identifiant ne circule que dans l'URL des écrans
    suivants — jamais dans un champ caché du formulaire.

    ⚠ **Écart au principe du module, assumé et signalé.**

    Ces écrans sont des gabarits QWeb écrits à la main, non les formulaires
    dynamiques de l'Extension 6. Le moteur en est capable ; ce n'est pas lui qui
    manque. Ce sont les sections 5 à 9 du PDF qui décrivent des écrans très
    dessinés — groupes de champs, textes d'aide propres à chaque question,
    listes de cases à cocher, choix Oui/Non révélant un bloc entier — que le
    rendu générique produirait en beaucoup moins bien.

    Le formulaire dynamique reste le bon outil pour ce qu'il vise : le
    « dossier progressif » dont le contenu **dépend des réponses**, c'est-à-dire
    le questionnaire d'après-GO de Smart Crowdfunding. Ici, les cinq écrans sont
    les mêmes pour tout le monde.
    """

    #: L'enchaînement des écrans vit ici, en un seul endroit : « écran suivant »
    #: et « écran précédent » s'en déduisent. Ajouter une étape est une ligne.
    _STEPS = (
        ('general', "Informations générales", '/my/innovation/new'),
        ('marche', "Marché et modèle économique", '/my/innovation/%s/marche'),
        ('equipe', "Équipe", '/my/innovation/%s/equipe'),
        ('besoins', "Besoins du projet", '/my/innovation/%s/besoins'),
        ('documents', "Pièces jointes", '/my/innovation/%s/documents'),
        ('recap', "Récapitulatif", '/my/innovation/%s/recap'),
    )

    #: Champs que chaque écran a le droit d'écrire. Listes fermées : un champ
    #: absent d'ici ne peut pas être écrit par le portail, quelle que soit la
    #: clé envoyée. C'est la même protection que la liste blanche du parcours
    #: d'adhésion du Module 1.
    _STEP_FIELDS = {
        'general': (
            'name', 'resume', 'probleme', 'solution', 'secteur', 'maturite'),
        'marche': (
            'marche_cible', 'besoin_marche', 'concurrence',
            'proposition_valeur', 'modele_economique', 'potentiel_commercial'),
        'equipe': (),
        'besoins': (
            'type_financement', 'utilisation_prevue'),
        'documents': (),
        'recap': (),
    }

    # ------------------------------------------------------------
    # Résolution du projet — toujours côté serveur
    # ------------------------------------------------------------

    def _own_projects(self):
        """Projets du porteur connecté, résolus depuis `partner_id`.

        Aucun identifiant reçu du client n'est utilisé directement : il est
        cherché **dans** cet ensemble. Une valeur forgée ne désigne donc rien.
        """
        return request.env['opex.innovation.project'].sudo().search(
            [('partner_id', '=', request.env.user.partner_id.id)],
            order='create_date desc')

    def _own_project(self, project_id):
        return self._own_projects().filtered(lambda p: p.id == project_id)[:1]

    def _current_draft(self):
        """Brouillon en cours du porteur, s'il y en a un.

        Sert au message de reprise : « vous avez un projet en cours de
        saisie ». Restreint à l'étape `draft` — un projet déjà soumis ne doit
        plus être réécrit par ces écrans, même en rejouant une URL.
        """
        return self._own_projects().filtered(
            lambda p: p.workflow_stage_id.code == 'draft')[:1]

    def _step_values(self, project, step, **extra):
        index = [code for code, _label, _url in self._STEPS].index(step)
        values = self._prepare_portal_layout_values()
        values.update({
            'project': project,
            'steps': self._STEPS,
            'step': step,
            'step_index': index,
            'page_name': 'innovation_project',
        })
        values.update(extra)
        return values

    def _save_step(self, project, step, post):
        """Écriture partielle : seuls les champs de l'écran courant.

        C'est ce qui rend chaque validation indépendante — quitter en cours de
        route ne perd que ce qui n'a pas encore été envoyé.
        """
        values = {
            name: (post.get(name) or '').strip()
            for name in self._STEP_FIELDS.get(step, ())
            if isinstance(post.get(name), str)
        }
        if step == 'besoins':
            values['besoin_financement'] = bool(post.get('besoin_financement'))
            raw = (post.get('montant_recherche') or '').replace(',', '.').strip()
            try:
                values['montant_recherche'] = float(raw) if raw else 0.0
            except ValueError:
                values['montant_recherche'] = 0.0
            for field_name, key in (
                ('besoin_competence_ids', 'competence_ids'),
                ('besoin_accompagnement_ids', 'accompagnement_ids'),
            ):
                ids = [
                    int(value) for value in request.httprequest.form.getlist(key)
                    if value.isdigit()
                ]
                values[field_name] = [(6, 0, ids)]
        if values:
            project.sudo().write(values)

    # ------------------------------------------------------------
    # Section 4 — Mes projets
    # ------------------------------------------------------------

    @http.route(['/my/innovation'], type='http', auth='user', website=True)
    def portal_my_projects(self, **kw):
        projects = self._own_projects()
        return request.render('opex_innovation.portal_my_projects', {
            'projects': projects,
            'draft': self._current_draft(),
            'page_name': 'innovation_project',
        })

    # ------------------------------------------------------------
    # Écran 1 — Informations générales
    # ------------------------------------------------------------

    @http.route(['/my/innovation/new'], type='http', auth='user', website=True,
                methods=['GET', 'POST'])
    def portal_project_new(self, **post):
        """Le brouillon automatique commence ici.

        Le projet est créé dès la validation du premier écran, à l'étape
        `draft`. Le porteur n'a donc jamais à « tout finir d'un coup » : ce qui
        est saisi est enregistré.
        """
        partner = request.env.user.partner_id
        if not partner.is_member:
            return request.render('opex_innovation.portal_project_not_member', {
                'page_name': 'innovation_project',
            })

        draft = self._current_draft()

        if request.httprequest.method == 'POST':
            name = (post.get('name') or '').strip()
            if not name:
                return request.render(
                    'opex_innovation.portal_project_step_general',
                    self._step_values(
                        draft, 'general',
                        error=_("Le nom du projet est obligatoire.")))
            if draft:
                project = draft
                self._save_step(project, 'general', post)
            else:
                # `partner_id` volontairement absent : le `create()` du modèle
                # l'impose côté serveur pour un utilisateur portail, et c'est
                # lui qui démarre le workflow.
                values = {
                    field: (post.get(field) or '').strip()
                    for field in self._STEP_FIELDS['general']
                    if isinstance(post.get(field), str)
                }
                project = request.env['opex.innovation.project'].create(values)
            return request.redirect('/my/innovation/%s/marche' % project.id)

        return request.render(
            'opex_innovation.portal_project_step_general',
            self._step_values(draft, 'general', error=None))

    # ------------------------------------------------------------
    # Écrans 2 à 5 — un même squelette
    # ------------------------------------------------------------

    def _handle_step(self, project_id, step, next_url, template, **post):
        """Corps commun des écrans intermédiaires.

        Un seul endroit qui vérifie l'appartenance du projet et son
        éditabilité : quatre copies de ce contrôle finiraient par diverger, et
        c'est celle qu'on aurait oubliée qui recevrait la requête forgée.
        """
        project = self._own_project(project_id)
        if not project:
            return request.redirect('/my/innovation')
        if project.workflow_stage_id.code not in (
                'draft', 'complement_requested', 'remediation'):
            return request.redirect('/my/innovation')

        if request.httprequest.method == 'POST':
            self._save_step(project, step, post)
            return request.redirect(next_url % project.id)

        return request.render(
            template, self._step_values(project, step, error=None))

    @http.route(['/my/innovation/<int:project_id>/marche'], type='http',
                auth='user', website=True, methods=['GET', 'POST'])
    def portal_project_marche(self, project_id, **post):
        return self._handle_step(
            project_id, 'marche', '/my/innovation/%s/equipe',
            'opex_innovation.portal_project_step_marche', **post)

    @http.route(['/my/innovation/<int:project_id>/equipe'], type='http',
                auth='user', website=True, methods=['GET', 'POST'])
    def portal_project_equipe(self, project_id, **post):
        project = self._own_project(project_id)
        if not project:
            return request.redirect('/my/innovation')

        if request.httprequest.method == 'POST':
            if post.get('action') == 'add' and (post.get('member_name') or '').strip():
                request.env['opex.innovation.team.member'].sudo().create({
                    'project_id': project.id,
                    'name': post.get('member_name').strip(),
                    'fonction': (post.get('member_fonction') or '').strip(),
                    'competence': (post.get('member_competence') or '').strip(),
                    'experience': (post.get('member_experience') or '').strip(),
                })
                return request.redirect('/my/innovation/%s/equipe' % project.id)
            if post.get('action') == 'remove':
                # L'identifiant vient du client : on le cherche **dans** les
                # membres de ce projet plutôt que de le parcourir directement.
                raw = (post.get('member_id') or '')
                member = project.team_member_ids.filtered(
                    lambda m: str(m.id) == raw)
                member.sudo().unlink()
                return request.redirect('/my/innovation/%s/equipe' % project.id)
            return request.redirect('/my/innovation/%s/besoins' % project.id)

        return request.render(
            'opex_innovation.portal_project_step_equipe',
            self._step_values(project, 'equipe', error=None))

    @http.route(['/my/innovation/<int:project_id>/besoins'], type='http',
                auth='user', website=True, methods=['GET', 'POST'])
    def portal_project_besoins(self, project_id, **post):
        project = self._own_project(project_id)
        if not project:
            return request.redirect('/my/innovation')

        if request.httprequest.method == 'POST':
            self._save_step(project, 'besoins', post)
            return request.redirect('/my/innovation/%s/documents' % project.id)

        return request.render(
            'opex_innovation.portal_project_step_besoins',
            self._step_values(
                project, 'besoins', error=None,
                competences=request.env['opex.innovation.competence'].sudo()
                .search([('active', '=', True)])))

    @http.route(['/my/innovation/<int:project_id>/documents'], type='http',
                auth='user', website=True, methods=['GET', 'POST'])
    def portal_project_documents(self, project_id, **post):
        project = self._own_project(project_id)
        if not project:
            return request.redirect('/my/innovation')

        error = None
        if request.httprequest.method == 'POST':
            if post.get('action') == 'add':
                error = self._add_document(project, post)
                if not error:
                    return request.redirect(
                        '/my/innovation/%s/documents' % project.id)
            elif post.get('action') == 'remove':
                raw = (post.get('document_id') or '')
                project.document_ids.filtered(
                    lambda d: str(d.id) == raw).sudo().unlink()
                return request.redirect(
                    '/my/innovation/%s/documents' % project.id)
            else:
                return request.redirect('/my/innovation/%s/recap' % project.id)

        Document = request.env['opex.innovation.document']
        return request.render(
            'opex_innovation.portal_project_step_documents',
            self._step_values(
                project, 'documents', error=error,
                document_types=Document._fields['document_type'].selection))

    def _add_document(self, project, post):
        """Dépose une pièce, et rend lisible le refus des contrôles du modèle.

        Les quatre contrôles — extension, taille, fichier vide, doublon — sont
        sur le modèle et non ici : un dépôt par le back-office ou par une
        requête forgée passe par les mêmes règles. Le controller ne fait que
        traduire l'erreur en message de page au lieu d'une erreur serveur.
        """
        import base64

        from odoo.exceptions import UserError

        upload = request.httprequest.files.get('file')
        url = (post.get('url') or '').strip()
        document_type = post.get('document_type') or 'autre'
        name = (post.get('name') or '').strip()

        if not name:
            return _("Donnez un libellé à la pièce.")
        if not url and (not upload or not upload.filename):
            return _("Choisissez un fichier ou indiquez un lien.")

        values = {
            'project_id': project.id,
            'name': name,
            'document_type': document_type,
            'url': url or False,
        }
        if upload and upload.filename:
            content = upload.read()
            values.update({
                'filename': upload.filename,
                'file': base64.b64encode(content) if content else False,
            })
        try:
            request.env['opex.innovation.document'].sudo().create(values)
        except UserError as error:
            return str(error)
        return None

    # ------------------------------------------------------------
    # Écran 6 — Récapitulatif et soumission
    # ------------------------------------------------------------

    @http.route(['/my/innovation/<int:project_id>/recap'], type='http',
                auth='user', website=True, methods=['GET', 'POST'])
    def portal_project_recap(self, project_id, **post):
        """Récapitulatif, avertissement, puis soumission.

        ⚠ La soumission passe par `workflow_do_transition()`, donc par l'unique
        contrôle d'accès du moteur et par les conditions configurées. Le
        controller ne décide pas que le projet peut partir : il le demande, et
        rend le refus lisible.
        """
        from odoo.exceptions import UserError

        project = self._own_project(project_id)
        if not project:
            return request.redirect('/my/innovation')

        error = None
        if request.httprequest.method == 'POST':
            if not post.get('confirm'):
                error = _(
                    "Cochez la case de confirmation pour soumettre votre projet.")
            else:
                transition = project.workflow_definition_id.sudo()\
                    .transition_ids.filtered(lambda t: t.code == 'submit')
                try:
                    project.workflow_do_transition(transition)
                    return request.redirect('/my/innovation/%s' % project.id)
                except UserError as blocked:
                    error = str(blocked)

        return request.render(
            'opex_innovation.portal_project_step_recap',
            self._step_values(
                project, 'recap', error=error,
                summary=project.qualification_summary()))

    # ------------------------------------------------------------
    # Suivi
    # ------------------------------------------------------------

    @http.route(['/my/innovation/<int:project_id>/resubmit'], type='http',
                auth='user', website=True, methods=['POST'])
    def portal_project_resubmit(self, project_id, **post):
        """Renvoie le dossier après correction — retour vers le contrôle.

        La transition est cherchée **dans** celles que le moteur propose au
        porteur : le controller ne décide pas que le dossier peut repartir, il
        le demande. Le retour vers `under_review` est décrit dans la
        configuration, pas ici.
        """
        from odoo.exceptions import UserError

        project = self._own_project(project_id)
        if not project:
            return request.redirect('/my/innovation')

        raw = (post.get('transition_id') or '').strip()
        allowed = project.workflow_instance_id.available_transitions()
        transition = allowed.filtered(lambda t: str(t.id) == raw)[:1]
        if transition:
            try:
                project.workflow_do_transition(transition)
                # Le motif est soldé : il a été traité, il n'a plus à
                # s'afficher en évidence.
                project.sudo().motif_complement = False
            except UserError:
                pass
        return request.redirect('/my/innovation/%s' % project.id)

    @http.route(['/my/innovation/<int:project_id>'], type='http', auth='user',
                website=True)
    def portal_project_detail(self, project_id, **kw):
        project = self._own_project(project_id)
        if not project:
            return request.redirect('/my/innovation')
        return request.render('opex_innovation.portal_project_detail', {
            'project': project,
            # La progression est rendue par le gabarit générique du moteur :
            # le métier n'écrit pas sa propre version de « où en est mon
            # dossier ».
            'instance': project.workflow_instance_id,
            'page_name': 'innovation_project',
        })


class InnovationRemediationPortal(CustomerPortal):
    """Section 18 — le porteur traite les points demandés et resoumet."""

    def _own_project(self, project_id):
        return request.env['opex.innovation.project'].sudo().search([
            ('partner_id', '=', request.env.user.partner_id.id),
            ('id', '=', project_id),
        ], limit=1)

    @http.route(['/my/innovation/<int:project_id>/remediation'], type='http',
                auth='user', website=True, methods=['GET', 'POST'])
    def portal_remediation(self, project_id, **post):
        """Affiche les points à corriger, puis resoumet en versionnant.

        ⚠ La resoumission passe par le moteur : la transition est cherchée
        dans celles qu'il propose au porteur. Le controller ne décide pas que
        le dossier peut repartir.
        """
        from odoo.exceptions import UserError

        project = self._own_project(project_id)
        if not project:
            return request.redirect('/my/innovation')

        remediation = project.pending_remediation_id
        if not remediation:
            return request.redirect('/my/innovation/%s' % project.id)

        error = None
        if request.httprequest.method == 'POST':
            allowed = project.workflow_instance_id.available_transitions()
            transition = allowed.filtered(
                lambda t: t.code == 'resubmit_after_remediation')[:1]
            if not transition:
                error = _(
                    "La resoumission n'est pas ouverte à cette étape du dossier.")
            else:
                # L'archive **d'abord**, la transition ensuite : on fige ce que
                # le comité a demandé de corriger, pas ce qu'il verra après.
                project.snapshot_version(
                    remediation=remediation,
                    reponse=(post.get('reponse') or '').strip())
                try:
                    project.workflow_do_transition(transition)
                    return request.redirect('/my/innovation/%s' % project.id)
                except UserError as blocked:
                    error = str(blocked)

        return request.render('opex_innovation.portal_remediation', {
            'project': project,
            'instance': project.workflow_instance_id,
            'remediation': remediation,
            'error': error,
            'page_name': 'innovation_project',
        })
