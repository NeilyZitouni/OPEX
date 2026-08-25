import base64

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.portal.controllers.portal import pager as portal_pager


class CrowdfundingCustomerPortal(CustomerPortal):
    """Espace porteur : présenter un projet, puis suivre son avancement.

    Le porteur arrive par le flux natif d'inscription et se trouve dans
    `base.group_portal` : personne n'a besoin de créer son projet à sa place.

    Aucun identifiant venu du client n'est utilisé tel quel. Les projets sont
    toujours retrouvés depuis `env.user.partner_id` ; l'identifiant reçu en URL
    n'est jamais lu directement, il est cherché *dans* cet ensemble. La règle
    d'enregistrement (`ir.rule`) et la surcharge de `create()` restent le
    filet : elles protègent la base même si un écran oublie un contrôle.
    """

    #: Champs saisis à chaque écran. Une seule table : elle décide à la fois de
    #: ce que l'écran affiche et de ce que le `write()` accepte, de sorte qu'un
    #: champ ajouté au gabarit sans l'être ici est ignoré côté serveur.
    _STEP_FIELDS = {
        'projet': ('name', 'porteur_type', 'probleme', 'solution'),
        'besoin': ('secteur', 'maturite', 'besoin_type', 'montant_indicatif'),
    }

    # ------------------------------------------------------------------
    # Résolution des projets du porteur connecté
    # ------------------------------------------------------------------
    def _own_projects_domain(self):
        """Filtre applicatif ; la règle d'enregistrement le garantit en base."""
        return [('partner_id', '=', request.env.user.partner_id.id)]

    def _own_project(self, project_id):
        """Projet du porteur connecté, en `sudo()`, ou recordset vide.

        La recherche part du contact connecté : un identifiant forgé ne
        remonte rien plutôt que de déclencher une erreur d'accès.
        """
        return request.env['opex.crowdfunding.project'].sudo().search(
            self._own_projects_domain() + [('id', '=', project_id)], limit=1)

    def _current_draft(self):
        """Le brouillon en cours du porteur, ou recordset vide.

        Un seul brouillon à la fois : le porteur qui revient reprend celui
        qu'il a laissé plutôt que d'en semer des copies vides.
        """
        return request.env['opex.crowdfunding.project'].sudo().search(
            self._own_projects_domain() + [('state', '=', 'draft')],
            order='id desc', limit=1)

    # ------------------------------------------------------------------
    # Saisie
    # ------------------------------------------------------------------
    def _clean_step_values(self, step, post):
        """Valeurs propres d'un écran : rien que ses champs, rien d'invalide.

        Les `Selection` sont vérifiées contre leurs valeurs autorisées et le
        montant contre son format : un POST forgé se voit ignoré, là où une
        écriture directe ferait remonter une erreur brute au porteur.
        """
        Project = request.env['opex.crowdfunding.project']
        descriptions = Project.fields_get(self._STEP_FIELDS[step])
        values = {}
        for nom in self._STEP_FIELDS[step]:
            if nom not in post:
                continue
            brut = post.get(nom)
            if not isinstance(brut, str):
                continue
            brut = brut.strip()
            type_champ = descriptions[nom]['type']
            if type_champ == 'selection':
                autorisees = [code for code, _libelle in descriptions[nom]['selection']]
                if brut in autorisees:
                    values[nom] = brut
                elif not brut:
                    values[nom] = False
            elif type_champ == 'monetary':
                values[nom] = self._parse_amount(brut)
            else:
                values[nom] = brut
        return values

    def _parse_amount(self, brut):
        """Montant indicatif saisi à la main : « 2 500 000,50 » compris."""
        nettoye = brut.replace(' ', '').replace(' ', '').replace(',', '.')
        try:
            return float(nettoye) if nettoye else 0.0
        except ValueError:
            return 0.0

    def _store_pitch(self, project, fichier):
        """Document facultatif. Un champ vide ne doit pas effacer l'existant."""
        if not fichier or not getattr(fichier, 'filename', None):
            return
        project.write({
            'pitch_document': base64.b64encode(fichier.read()),
            'pitch_filename': fichier.filename,
        })

    # ------------------------------------------------------------------
    # Liste — /my/projects
    # ------------------------------------------------------------------
    @http.route(['/my/projects', '/my/projects/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_my_projects(self, page=1, **kw):
        Project = request.env['opex.crowdfunding.project']
        if not Project.has_access('read'):
            return request.redirect('/my')

        domain = self._own_projects_domain()
        pager_values = portal_pager(
            url='/my/projects',
            total=Project.sudo().search_count(domain),
            page=page,
            step=self._items_per_page,
        )
        projects = Project.sudo().search(
            domain, order='create_date desc, id desc',
            limit=self._items_per_page, offset=pager_values['offset'])

        values = self._prepare_portal_layout_values()
        values.update({
            'projects': projects,
            # Le fil d'Ariane teste `project` : le poser explicitement évite
            # de dépendre du sort réservé à une variable non définie.
            'project': False,
            'draft': self._current_draft(),
            'page_name': 'crowdfunding',
            'pager': pager_values,
            'default_url': '/my/projects',
        })
        return request.render('opex_crowdfunding.portal_my_projects', values)

    # ------------------------------------------------------------------
    # Dépôt — /my/projects/new
    # ------------------------------------------------------------------
    # Deux écrans. Le projet est créé en base dès la validation du premier :
    # à partir de là, tout est `write()` partiel, et quitter la page ne perd
    # que ce qui n'a pas encore été envoyé.

    def _render_step(self, step, project, **extra):
        values = self._prepare_portal_layout_values()
        values.update({
            'step': step,
            'project': project,
            'page_name': 'crowdfunding_new',
            'error': None,
            'reprise': False,
            # Ce que le porteur venait de taper, réaffiché tel quel quand
            # l'écran est renvoyé avec une erreur : personne ne doit ressaisir
            # sa présentation parce qu'il a oublié le titre.
            'saisie': {},
        })
        values.update(extra)
        return request.render('opex_crowdfunding.portal_project_form', values)

    @http.route(['/my/projects/new'], type='http', auth='user', website=True,
                methods=['GET', 'POST'])
    def portal_project_new(self, **post):
        """Écran 1 — le projet. Crée le brouillon à la première validation."""
        project = self._current_draft()

        if request.httprequest.method == 'POST':
            values = self._clean_step_values('projet', post)
            if not values.get('name') and not project.name:
                return self._render_step(
                    'projet', project, saisie=post,
                    error=_("Donnez un titre à votre projet pour pouvoir "
                            "enregistrer votre saisie."))
            if project:
                project.write(values)
            else:
                # Première saisie : c'est ici que naît le brouillon. `create()`
                # force `partner_id` et `state` côté modèle, quoi qu'envoie le
                # navigateur.
                project = request.env['opex.crowdfunding.project'].sudo().create(values)
            return request.redirect('/my/projects/new/besoin')

        # Le porteur qui revient reprend son brouillon, et on le lui dit.
        return self._render_step('projet', project, reprise=bool(project))

    @http.route(['/my/projects/new/besoin'], type='http', auth='user', website=True,
                methods=['GET', 'POST'])
    def portal_project_new_besoin(self, **post):
        """Écran 2 — le besoin, puis « Présenter mon projet »."""
        project = self._current_draft()
        if not project:
            return request.redirect('/my/projects/new')

        if request.httprequest.method == 'POST':
            project.write(self._clean_step_values('besoin', post))
            self._store_pitch(project, request.httprequest.files.get('pitch_document'))
            if post.get('enregistrer'):
                return request.redirect('/my/projects/%s' % project.id)
            # `action_submit()` vérifie lui-même les informations minimales :
            # la règle reste dans le modèle, cet écran ne la rejoue pas.
            try:
                with request.env.cr.savepoint():
                    project.action_submit()
            except UserError as error:
                return self._render_step('besoin', project, error=error.args[0])
            return request.redirect('/my/projects/%s' % project.id)

        return self._render_step('besoin', project)

    # ------------------------------------------------------------------
    # Suivi — /my/projects/<id>
    # ------------------------------------------------------------------
    @http.route(['/my/projects/<int:project_id>'], type='http', auth='user', website=True)
    def portal_project_page(self, project_id, **kw):
        project = self._own_project(project_id)
        if not project:
            return request.redirect('/my/projects')

        values = self._prepare_portal_layout_values()
        values.update({
            'project': project,
            'progress': project._portal_progress(),
            'next_action': project._portal_next_action(),
            # La page est rendue en `sudo()` : c'est ici, et pas dans le
            # gabarit, qu'on écarte les questions encore en préparation côté
            # comité. Le porteur ne doit pas lire une question à moitié écrite.
            'echanges': project.clarification_ids.filtered(lambda c: c.state != 'draft'),
            'demande_complement': project._portal_demande_complement(),
            'accompagnement': project._accompagnement_en_cours(),
            # « À tout moment autorisé du parcours » : c'est le modèle qui dit
            # lesquels, le gabarit ne fait qu'afficher ou non le bouton.
            'peut_demander_accompagnement': (
                project.state in project._ETATS_DEMANDE_ACCOMPAGNEMENT
                and not project._accompagnement_en_cours()
            ),
            'page_name': 'crowdfunding',
        })
        return request.render('opex_crowdfunding.portal_project_page', values)

    # ------------------------------------------------------------------
    # Dossier complémentaire — /my/projects/<id>/dossier
    # ------------------------------------------------------------------
    #: Les champs que chaque questionnaire accepte en écriture. Comme pour le
    #: dépôt : ce qui n'est pas listé ici est ignoré, même si un champ traîne
    #: dans le gabarit ou dans un POST forgé.
    #
    #: ⚠ Un quatrième type de besoin ajoute une entrée ici et une dans
    #: `_DOSSIER_DOCUMENTS`. Le décompte complet des cinq fichiers à toucher
    #: est dans `_champs_dossier_requis()`, côté modèle.
    _DOSSIER_FIELDS = {
        'investisseur': (
            'business_model', 'marche', 'traction', 'equipe', 'besoin_financier',
            'utilisation_fonds', 'valorisation', 'previsions_financieres',
        ),
        'sponsor': (
            'sponsor_objectif', 'sponsor_public_cible', 'sponsor_visibilite',
            'sponsor_retombees', 'sponsor_budget', 'sponsor_calendrier',
            'sponsor_partenaires',
        ),
        'financement_public': (
            'public_dispositif', 'public_eligibilite', 'public_montant',
            'public_plan_financement', 'public_impact', 'public_conformite',
            'public_calendrier',
        ),
    }

    #: Le document du questionnaire : champ binaire, champ du nom de fichier.
    _DOSSIER_DOCUMENTS = {
        'investisseur':       ('pitch_deck', 'pitch_deck_filename'),
        'sponsor':            ('sponsor_document', 'sponsor_document_filename'),
        'financement_public': ('public_document', 'public_document_filename'),
    }

    def _clean_dossier_values(self, project, post):
        """Valeurs propres du questionnaire correspondant au besoin exprimé."""
        champs = self._DOSSIER_FIELDS.get(project.besoin_type, ())
        Project = request.env['opex.crowdfunding.project']
        descriptions = Project.fields_get(champs) if champs else {}
        values = {}
        for nom in champs:
            brut = post.get(nom)
            if not isinstance(brut, str):
                continue
            brut = brut.strip()
            if descriptions[nom]['type'] == 'monetary':
                values[nom] = self._parse_amount(brut)
            else:
                values[nom] = brut
        return values

    def _store_dossier_document(self, project, post_files):
        """Document du questionnaire. Champ vide = document conservé."""
        paire = self._DOSSIER_DOCUMENTS.get(project.besoin_type)
        if not paire:
            return
        champ_binaire, champ_nom = paire
        fichier = post_files.get(champ_binaire)
        if not fichier or not getattr(fichier, 'filename', None):
            return
        project.write({
            champ_binaire: base64.b64encode(fichier.read()),
            champ_nom: fichier.filename,
        })

    @http.route(['/my/projects/<int:project_id>/dossier'],
                type='http', auth='user', website=True, methods=['GET', 'POST'])
    def portal_project_dossier(self, project_id, **post):
        """Le questionnaire complémentaire, demandé seulement après un GO.

        Trois besoins, trois questionnaires : l'aiguillage se fait sur
        `besoin_type`, ici comme dans le gabarit.
        """
        project = self._own_project(project_id)
        if not project:
            return request.redirect('/my/projects')
        # Le même écran sert deux fois : après le GO, puis quand le contrôle
        # qualité demande des compléments. C'est le même questionnaire, ce
        # n'est pas le même acte métier — d'où deux transitions distinctes.
        if project.state not in ('dossier_progressif', 'quality_complement'):
            return request.redirect('/my/projects/%s' % project.id)

        erreur = None
        if request.httprequest.method == 'POST':
            # Écriture d'abord, dans tous les cas : le porteur peut revenir
            # finir plus tard, rien de ce qu'il a tapé n'est perdu.
            depuis_complement = project.state == 'quality_complement'
            project.write(self._clean_dossier_values(project, post))
            self._store_dossier_document(project, request.httprequest.files)
            if post.get('enregistrer'):
                return request.redirect('/my/projects/%s' % project.id)
            try:
                with request.env.cr.savepoint():
                    if depuis_complement:
                        project.action_submit_complement()
                    else:
                        project.action_submit_dossier()
            except UserError as error:
                erreur = error.args[0]
            else:
                return request.redirect('/my/projects/%s' % project.id)

        values = self._prepare_portal_layout_values()
        values.update({
            'project': project,
            'demande_complement': project._portal_demande_complement(),
            'error': erreur,
            'page_name': 'crowdfunding',
        })
        return request.render('opex_crowdfunding.portal_project_dossier', values)

    # ------------------------------------------------------------------
    # Mise en relation contrôlée — section 13
    # ------------------------------------------------------------------
    # Côté acteur financier. Aucune de ces routes ne compose ce qu'elle
    # affiche : elles délèguent toutes à `relation._portal_payload()`, la
    # seule méthode qui décide de ce qu'un niveau d'accès autorise. Une
    # vérification recopiée ici finirait par diverger, et ce serait cette
    # copie-là qui recevrait la requête forgée.

    def _relation_du_partenaire(self, relation_id):
        """La relation du contact connecté, en `sudo()`, ou recordset vide.

        Retrouvée depuis `env.user.partner_id`, jamais depuis l'identifiant
        seul : un identifiant forgé ne remonte rien.
        """
        return request.env['opex.crowdfunding.relation'].sudo().search([
            ('id', '=', relation_id),
            ('partner_id', '=', request.env.user.partner_id.id),
        ], limit=1)

    @http.route(['/my/opportunities'], type='http', auth='user', website=True)
    def portal_my_opportunities(self, **kw):
        """Les dossiers auxquels cet acteur a accès, à quelque niveau que ce soit."""
        relations = request.env['opex.crowdfunding.relation'].sudo().search(
            [('partner_id', '=', request.env.user.partner_id.id)])

        values = self._prepare_portal_layout_values()
        values.update({
            # Le résumé de liste passe lui aussi par le contrôle d'accès :
            # même ici, un dossier au teaser ne donne que sa référence.
            'opportunites': [
                relation._portal_payload()[1] for relation in relations
            ],
            'page_name': 'opportunities',
        })
        return request.render('opex_crowdfunding.portal_my_opportunities', values)

    @http.route(['/my/opportunities/<int:relation_id>'],
                type='http', auth='user', website=True)
    def portal_opportunity(self, relation_id, **kw):
        relation = self._relation_du_partenaire(relation_id)
        if not relation:
            return request.redirect('/my/opportunities')

        gabarit, valeurs = relation._portal_payload()
        rendu = self._prepare_portal_layout_values()
        rendu.update(valeurs)
        rendu['page_name'] = 'opportunities'
        return request.render(gabarit, rendu)

    @http.route(['/my/opportunities/<int:relation_id>/interet'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_opportunity_interet(self, relation_id, **post):
        """« Ça m'intéresse » — et rien d'autre ne s'ouvre pour autant."""
        relation = self._relation_du_partenaire(relation_id)
        if not relation:
            return request.redirect('/my/opportunities')
        try:
            with request.env.cr.savepoint():
                relation.action_exprimer_interet()
        except UserError:
            pass
        return request.redirect('/my/opportunities/%s' % relation.id)

    # ------------------------------------------------------------------
    # L'écran de l'expert — section 16
    # ------------------------------------------------------------------
    def _mission_de_l_expert(self, mission_id):
        """La mission confiée au contact connecté, ou recordset vide."""
        return request.env['opex.crowdfunding.mission'].sudo().search([
            ('id', '=', mission_id),
            ('expert_id', '=', request.env.user.partner_id.id),
        ], limit=1)

    @http.route(['/my/missions'], type='http', auth='user', website=True)
    def portal_my_missions(self, **kw):
        missions = request.env['opex.crowdfunding.mission'].sudo().search(
            [('expert_id', '=', request.env.user.partner_id.id)], order='id desc')

        values = self._prepare_portal_layout_values()
        values.update({
            'missions': [mission._portal_payload() for mission in missions],
            'page_name': 'missions',
        })
        return request.render('opex_crowdfunding.portal_my_missions', values)

    @http.route(['/my/missions/<int:mission_id>/reponse'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_mission_reponse(self, mission_id, **post):
        """[Accepter] [Décliner] — les deux seuls gestes de la section 16."""
        mission = self._mission_de_l_expert(mission_id)
        if not mission:
            return request.redirect('/my/missions')
        try:
            with request.env.cr.savepoint():
                if post.get('reponse') == 'accepter':
                    mission.action_accept()
                elif post.get('reponse') == 'decliner':
                    mission.action_decline()
        except UserError:
            pass
        return request.redirect('/my/missions')

    # ------------------------------------------------------------------
    # L'historique du porteur — l'audit trail, côté portail
    # ------------------------------------------------------------------
    @http.route(['/my/projects/<int:project_id>/historique'],
                type='http', auth='user', website=True)
    def portal_project_historique(self, project_id, **kw):
        project = self._own_project(project_id)
        if not project:
            return request.redirect('/my/projects')

        values = self._prepare_portal_layout_values()
        values.update({
            'project': project,
            'historique': project._portal_historique(),
            'page_name': 'crowdfunding',
        })
        return request.render('opex_crowdfunding.portal_project_historique', values)

    # ------------------------------------------------------------------
    # Les cinq décisions de l'acteur financier — section 14
    # ------------------------------------------------------------------
    #: Le bouton cliqué, et la méthode qui traduit ce choix en transition.
    #: L'acteur n'envoie jamais un état : il envoie « intéressé » ou « pas
    #: intéressé », et c'est le modèle qui sait ce que ça implique.
    _DECISIONS = {
        'interesse':      'action_decision_interesse',
        'informations':   'action_decision_informations',
        'accompagnement': 'action_decision_accompagnement',
        'rendez_vous':    'action_decision_rendez_vous',
        'non_interesse':  'action_decision_non_interesse',
    }

    @http.route(['/my/opportunities/<int:relation_id>/decision'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_opportunity_decision(self, relation_id, **post):
        relation = self._relation_du_partenaire(relation_id)
        if not relation:
            return request.redirect('/my/opportunities')

        methode = self._DECISIONS.get(post.get('choix'))
        if not methode:
            return request.redirect('/my/opportunities/%s' % relation.id)

        arguments = {}
        if methode == 'action_decision_informations':
            arguments['message'] = post.get('message')
        elif methode == 'action_decision_rendez_vous':
            arguments['message'] = post.get('message')
            arguments['date_rendez_vous'] = post.get('date_rendez_vous') or False
        try:
            with request.env.cr.savepoint():
                getattr(relation, methode)(**arguments)
        except UserError:
            pass
        return request.redirect('/my/opportunities/%s' % relation.id)

    # ------------------------------------------------------------------
    # Le projet suivi — section 15
    # ------------------------------------------------------------------
    @http.route(['/my/projects/<int:project_id>/financement'],
                type='http', auth='user', website=True)
    def portal_project_financement(self, project_id, **kw):
        """« Le dossier devient un projet suivi plutôt qu'une candidature. »"""
        project = self._own_project(project_id)
        if not project:
            return request.redirect('/my/projects')
        closing = project._current_closing()
        if not closing:
            return request.redirect('/my/projects/%s' % project.id)

        values = self._prepare_portal_layout_values()
        values.update({
            'project': project,
            # Le contenu est composé par le modèle, comme pour les niveaux
            # d'accès : le gabarit ne reçoit que des valeurs déjà choisies.
            'financement': closing._portal_suivi(),
            'page_name': 'crowdfunding',
        })
        return request.render('opex_crowdfunding.portal_project_financement', values)

    # ------------------------------------------------------------------
    # Côté porteur : c'est lui qui autorise le partage
    # ------------------------------------------------------------------
    @http.route(['/my/projects/<int:project_id>/relations'],
                type='http', auth='user', website=True)
    def portal_project_relations(self, project_id, **kw):
        project = self._own_project(project_id)
        if not project:
            return request.redirect('/my/projects')

        values = self._prepare_portal_layout_values()
        values.update({
            'project': project,
            # Le porteur voit qui s'intéresse à son dossier et jusqu'où il l'a
            # ouvert. C'est son dossier : aucune anonymisation de ce côté-ci.
            'relations': project.relation_ids,
            'page_name': 'crowdfunding',
        })
        return request.render('opex_crowdfunding.portal_project_relations', values)

    @http.route(['/my/projects/<int:project_id>/relations/<int:relation_id>/autoriser'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_project_relation_autoriser(self, project_id, relation_id, **post):
        """Le porteur autorise le partage de son dossier avec un acteur."""
        project = self._own_project(project_id)
        if not project:
            return request.redirect('/my/projects')
        relation = project.relation_ids.filtered(lambda r: r.id == relation_id)
        if relation:
            try:
                with request.env.cr.savepoint():
                    relation.action_autoriser_partage()
            except UserError:
                pass
        return request.redirect('/my/projects/%s/relations' % project.id)

    # ------------------------------------------------------------------
    # Accompagnement CEO — sections 11 et 12
    # ------------------------------------------------------------------
    @http.route(['/my/projects/<int:project_id>/accompagnement/demander'],
                type='http', auth='user', website=True, methods=['GET', 'POST'])
    def portal_accompagnement_demander(self, project_id, **post):
        """Déclencheur 3 — « Être accompagné par CEO », à l'initiative du porteur.

        Le dossier ne quitte pas son étape : la demande ouvre un sous-workflow
        à côté du parcours principal (section 11, cas 3).
        """
        project = self._own_project(project_id)
        if not project:
            return request.redirect('/my/projects')

        erreur = None
        if request.httprequest.method == 'POST':
            try:
                with request.env.cr.savepoint():
                    project.action_accompagnement_demande_porteur(
                        demande=(post.get('demande') or '').strip())
            except UserError as error:
                erreur = error.args[0]
            else:
                return request.redirect('/my/projects/%s' % project.id)

        values = self._prepare_portal_layout_values()
        values.update({
            'project': project,
            'error': erreur,
            'page_name': 'crowdfunding',
        })
        return request.render(
            'opex_crowdfunding.portal_accompagnement_demande', values)

    @http.route(['/my/projects/<int:project_id>/accompagnement'],
                type='http', auth='user', website=True, methods=['GET', 'POST'])
    def portal_accompagnement(self, project_id, **post):
        """La proposition d'accompagnement, et la réponse du porteur.

        Section 12 : la convention acceptée est la précondition du passage à
        l'accompagnement actif. C'est ici, et nulle part ailleurs, que le
        porteur la donne.
        """
        project = self._own_project(project_id)
        if not project:
            return request.redirect('/my/projects')
        accompagnement = project._accompagnement_en_cours()
        if not accompagnement:
            return request.redirect('/my/projects/%s' % project.id)

        erreur = None
        if request.httprequest.method == 'POST' and accompagnement.state == 'propose':
            try:
                with request.env.cr.savepoint():
                    if post.get('refuser'):
                        accompagnement.action_refuse_convention()
                    else:
                        # Le porteur pose lui-même la précondition ; le comité
                        # ne fait ensuite que la constater.
                        accompagnement.convention_acceptee = True
                        accompagnement.action_accept_convention()
            except UserError as error:
                erreur = error.args[0]
            else:
                return request.redirect('/my/projects/%s' % project.id)

        values = self._prepare_portal_layout_values()
        values.update({
            'project': project,
            'accompagnement': accompagnement,
            'error': erreur,
            'page_name': 'crowdfunding',
        })
        return request.render('opex_crowdfunding.portal_accompagnement', values)

    # ------------------------------------------------------------------
    # Clarifications — /my/projects/<id>/clarifications
    # ------------------------------------------------------------------
    @http.route(['/my/projects/<int:project_id>/clarifications'],
                type='http', auth='user', website=True, methods=['GET', 'POST'])
    def portal_project_clarifications(self, project_id, **post):
        """Le porteur répond aux questions ciblées du comité (section 6).

        Les réponses sont enregistrées au fil de l'eau : un porteur qui ne
        répond qu'à deux questions sur trois retrouve ses deux réponses en
        revenant. Le dossier ne repart au comité que lorsqu'il ne reste plus
        rien sans réponse — et c'est le modèle qui en juge.
        """
        project = self._own_project(project_id)
        if not project:
            return request.redirect('/my/projects')
        if project.state != 'clarification':
            # Rien à répondre : on renvoie le porteur sur le suivi de son
            # projet, qui lui dira où il en est.
            return request.redirect('/my/projects/%s' % project.id)

        erreur = None
        if request.httprequest.method == 'POST':
            for clarification in project.clarification_ids:
                if clarification.state != 'asked':
                    continue
                reponse = (post.get('reponse_%s' % clarification.id) or '').strip()
                if reponse:
                    clarification.write({'reponse': reponse, 'state': 'answered'})
            try:
                with request.env.cr.savepoint():
                    project.action_clarifications_answered()
            except UserError as error:
                erreur = error.args[0]
            else:
                return request.redirect('/my/projects/%s' % project.id)

        values = self._prepare_portal_layout_values()
        values.update({
            'project': project,
            'clarifications': project.clarification_ids.filtered(
                lambda c: c.state != 'draft'),
            'error': erreur,
            'page_name': 'crowdfunding',
        })
        return request.render('opex_crowdfunding.portal_project_clarifications', values)
