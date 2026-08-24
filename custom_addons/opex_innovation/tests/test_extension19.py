import re

from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged

#: Les sept jalons de la section 35, dans l'ordre. Écrits ici plutôt que relus
#: depuis la base : un test qui relit la donnée qu'il vérifie ne vérifie rien.
SECTION_35 = [
    'depose', 'controle', 'evaluation', 'decision',
    'accompagnement', 'financement', 'industrialisation',
]


class Extension19Case(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.innovation.project']
        cls.Milestone = cls.env['opex.innovation.milestone']

        cls.porteur = new_test_user(
            cls.env, login='e19_porteur', password='e19_porteur',
            groups='base.group_portal')
        cls.porteur.partner_id.sudo().write({'is_member': True})
        cls.secretariat = new_test_user(
            cls.env, login='e19_secr', password='e19_secr',
            groups='base.group_user,opex_membership.group_secretariat')
        cls.comite = new_test_user(
            cls.env, login='e19_comite', password='e19_comite',
            groups='base.group_user,opex_innovation.group_comite_evaluation')
        cls.ceo = new_test_user(
            cls.env, login='e19_ceo', password='e19_ceo',
            groups='base.group_user,opex_innovation.group_innovation_manager')

        cls.actors = {
            'porteur': cls.porteur, 'secretariat': cls.secretariat,
            'comite': cls.comite, 'ceo': cls.ceo,
        }

    def _project(self, **values):
        base = {
            'partner_id': self.porteur.partner_id.id,
            'name': "Smart Factory",
            'resume': "Une usine pilotée par l'IA.",
            'probleme': "Arrêts imprévus.",
            'solution': "Maintenance prédictive.",
            'secteur': 'industrie',
            'maturite': 'mvp',
        }
        base.update(values)
        return self.Project.sudo().create(base)

    def _do(self, project, code, actor, comment="Décision motivée."):
        transition = project.workflow_definition_id.transition_ids.filtered(
            lambda t: t.code == code)
        self.assertTrue(transition, "Transition « %s » introuvable." % code)
        return project.with_user(self.actors[actor]).workflow_do_transition(
            transition, comment=comment)

    def _states(self, project):
        return {step['code']: step['state'] for step in project.milestones()}


@tagged('post_install', '-at_install')
class TestMilestones(Extension19Case):
    """Section 35 — sept jalons, jamais quinze étapes."""

    def test_the_seven_milestones_of_section_35_are_configured(self):
        definition = self.env['opex.workflow.definition']._get_for_code(
            'innovation_project')
        # ⚠ Borné à cette définition : le Smart Crowdfunding et
        # l'industrialisation tournent dans la même base.
        milestones = self.Milestone.search(
            [('definition_id', '=', definition.id)], order='sequence')
        self.assertEqual([m.code for m in milestones], SECTION_35)

    def test_the_card_shows_seven_lines_not_fifteen(self):
        """La règle d'or : l'utilisateur ne voit pas la complexité interne."""
        project = self._project()
        definition = project.workflow_definition_id

        self.assertEqual(len(definition.stage_ids), 15)
        self.assertEqual(len(project.milestones()), 7)

    def test_no_milestone_label_is_a_technical_code(self):
        project = self._project()
        codes = set(project.workflow_definition_id.stage_ids.mapped('code'))
        for step in project.milestones():
            self.assertNotIn(
                step['label'], codes,
                "Le jalon « %s » affiche un code d'étape." % step['label'])

    def test_a_new_project_sits_on_the_first_milestone(self):
        states = self._states(self._project())
        self.assertEqual(states['depose'], 'current')
        self.assertEqual(states['controle'], 'upcoming')
        self.assertEqual(states['industrialisation'], 'upcoming')

    def test_the_card_of_section_35_word_for_word(self):
        """L'exemple du document, reproduit exactement.

            ✓ Déposé
            ✓ Contrôle terminé
            ● Évaluation en cours
            ○ Décision
            ○ Accompagnement
            ○ Financement
            ○ Industrialisation
        """
        project = self._project()
        for code, actor in (('submit', 'porteur'),
                            ('take_in_charge', 'secretariat'),
                            ('qualify', 'secretariat'),
                            ('evaluate_directly', 'comite')):
            self._do(project, code, actor)

        self.assertEqual(self._states(project), {
            'depose': 'done',
            'controle': 'done',
            'evaluation': 'current',
            'decision': 'upcoming',
            'accompagnement': 'upcoming',
            'financement': 'upcoming',
            'industrialisation': 'upcoming',
        })
        self.assertEqual(project.milestone_message(),
                         "Votre projet est actuellement évalué.")

    def test_a_skipped_milestone_still_reads_as_passed(self):
        """Le comité peut évaluer directement, sans passer par les experts.

        Afficher « Évaluation » comme à venir à un porteur déjà accepté serait
        incompréhensible. Le porteur lit une progression, pas un journal —
        l'historique exact reste consultable en dessous.
        """
        project = self._project()
        for code, actor in (('submit', 'porteur'),
                            ('take_in_charge', 'secretariat'),
                            ('qualify', 'secretariat'),
                            ('evaluate_directly', 'comite'),
                            ('accept', 'comite')):
            self._do(project, code, actor)

        states = self._states(project)
        self.assertEqual(states['decision'], 'current')
        self.assertEqual(states['evaluation'], 'done')
        self.assertEqual(states['controle'], 'done')

    def test_a_rejected_project_has_no_current_milestone(self):
        """⚠ Sans la règle « dossier clos », un projet refusé afficherait
        « Décision » comme étape en cours pour toujours."""
        project = self._project()
        for code, actor in (('submit', 'porteur'),
                            ('take_in_charge', 'secretariat'),
                            ('qualify', 'secretariat'),
                            ('evaluate_directly', 'comite')):
            self._do(project, code, actor)
        self._do(project, 'reject', 'comite', comment="Hors périmètre.")

        states = self._states(project)
        self.assertNotIn('current', states.values())
        self.assertEqual(states['decision'], 'done')
        self.assertEqual(states['financement'], 'upcoming')

    def test_internal_round_trips_never_appear_on_the_card(self):
        """`complement_requested` n'est rattaché à aucun jalon.

        L'afficher ferait apparaître et disparaître une ligne au gré des
        allers-retours — la complexité interne que la section 35 masque. Le
        porteur voit l'alerte « Action requise » et l'historique complet ; sa
        carte, elle, reste stable.
        """
        project = self._project()
        self._do(project, 'submit', 'porteur')
        self._do(project, 'take_in_charge', 'secretariat')

        avant = self._states(project)
        self._do(project, 'request_complement', 'secretariat',
                 comment="Il manque le business plan.")

        self.assertEqual(project.workflow_stage_id.code, 'complement_requested')
        # La carte n'a pas bougé : sept lignes, mêmes états.
        self.assertEqual(len(project.milestones()), 7)
        self.assertEqual(self._states(project), avant)

    def test_the_mapping_is_data_not_code(self):
        """Ajouter une étape ne demande pas de rouvrir un fichier Python.

        Ce que ce test écrit, un utilisateur métier l'obtient au configurateur —
        exactement comme le Demo Day de l'Extension 20.
        """
        definition = self.env['opex.workflow.definition']._get_for_code(
            'innovation_project')
        stage = self.env['opex.workflow.stage'].create({
            'definition_id': definition.id,
            'code': 'demo_day',
            'name': "Demo Day",
            'user_label': "Préparer mon Demo Day",
            'sequence': 205,
        })
        jalon = self.Milestone.search([
            ('definition_id', '=', definition.id),
            ('code', '=', 'accompagnement'),
        ], limit=1)
        jalon.write({'stage_ids': [(4, stage.id)]})

        project = self._project()
        project.workflow_instance_id.sudo().current_stage_id = stage.id
        self.assertEqual(self._states(project)['accompagnement'], 'current')

    def test_the_message_falls_back_to_the_engine(self):
        """Un jalon sans phrase configurée n'affiche pas une case vide : le
        moteur sait déjà dire ce qu'on attend de l'utilisateur."""
        project = self._project()
        jalon = self.Milestone.search([('code', '=', 'depose')], limit=1)
        jalon.sudo().message = False
        message = project.milestone_message(self.porteur)
        self.assertTrue(message)
        self.assertNotEqual(message, "")


@tagged('post_install', '-at_install')
class TestPortalTilesAreActuallyVisible(HttpCase):
    """⚠ Le piège du Module 1, retrouvé intact sur les quatre tuiles.

    `portal.portal_docs_entry` ajoute `d-none` à toute entrée qui ne fournit ni
    `placeholder_count` non nul, ni `config_card`. La tuile est donc **présente
    dans le HTML** et **invisible à l'écran**.

    Un test qui vérifierait `'Mes projets' in response.text` passerait au vert
    sur une page où l'utilisateur ne voit rien. Ces tests-ci lisent la classe
    CSS du conteneur, pas la présence du texte.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.innovation.project']
        cls.Candidate = cls.env['opex.matching.candidate']

        cls.porteur = new_test_user(
            cls.env, login='e19t_porteur', password='e19t_porteur',
            groups='base.group_portal')
        cls.porteur.partner_id.sudo().write({'is_member': True})

    @staticmethod
    def _card_classes(html, url):
        """Les classes CSS du conteneur de la tuile menant à `url`.

        Le gabarit natif produit :
            <div class="o_portal_index_card d-none col-md-6 order-2">
                <a href="/my/innovation" ...>
        La classe se lit donc juste après le marqueur, et l'URL un peu plus loin
        dans le même bloc.
        """
        for part in html.split('o_portal_index_card')[1:]:
            classes = part.split('"')[0]
            if ('href="%s"' % url) in part[:800]:
                return classes
        return None

    def test_the_projects_tile_is_visible_even_with_no_project(self):
        """Le cas qui compte : un porteur qui n'a rien déposé.

        C'est exactement celui pour qui la tuile disparaîtrait, et exactement
        celui qui en a besoin pour trouver « Déposer un nouveau projet ».
        """
        self.authenticate('e19t_porteur', 'e19t_porteur')
        response = self.url_open('/my')
        self.assertEqual(response.status_code, 200)

        classes = self._card_classes(response.text, '/my/innovation')
        # Positive d'abord : la tuile existe bien dans la page.
        self.assertIsNotNone(
            classes, "Tuile « Mes projets d'innovation » absente de /my.")
        self.assertNotIn(
            'd-none', classes,
            "La tuile est rendue mais invisible (classes : %s)." % classes)

    def test_the_profiles_tile_is_visible_too(self):
        self.authenticate('e19t_porteur', 'e19t_porteur')
        response = self.url_open('/my')
        classes = self._card_classes(response.text, '/my/innovation/profiles')
        self.assertIsNotNone(classes, "Tuile « Mes profils » absente de /my.")
        self.assertNotIn('d-none', classes)

    def test_the_opportunities_tile_appears_once_there_is_one(self):
        """Celle-ci **doit** se masquer à zéro, et réapparaître ensuite.

        Le comportement natif est le bon ici : un membre à qui aucun projet
        n'est proposé n'a rien à consulter. Ce test vérifie les deux moitiés —
        masquée sans proposition, visible avec.
        """
        self.authenticate('e19t_porteur', 'e19t_porteur')

        # Sans proposition : masquée.
        self.make_jsonrpc_request(
            '/my/counters', {'counters': ['innovation_opportunity_count']})
        response = self.url_open('/my')
        classes = self._card_classes(
            response.text, '/my/innovation/opportunities')
        self.assertIsNotNone(classes)
        self.assertIn('d-none', classes)

        # Avec une proposition retenue : visible.
        project = self.Project.sudo().create({
            'partner_id': self.env.ref('base.partner_admin').id,
            'name': "Smart Factory",
            'resume': "Une usine pilotée par l'IA.",
            'probleme': "Arrêts imprévus.",
            'solution': "Maintenance prédictive.",
            'secteur': 'industrie',
            'maturite': 'mvp',
        })
        candidate = self.Candidate.sudo().create({
            'instance_id': project.workflow_instance_id.id,
            'partner_id': self.porteur.partner_id.id,
            'candidate_type': 'investisseur',
            'score': 80.0,
            'detail': "Secteur compatible.",
        })
        candidate.action_accept()
        project.sudo().propose_to_candidate(candidate)

        counters = self.make_jsonrpc_request(
            '/my/counters', {'counters': ['innovation_opportunity_count']})
        self.assertEqual(counters.get('innovation_opportunity_count'), 1)

        response = self.url_open('/my')
        classes = self._card_classes(
            response.text, '/my/innovation/opportunities')
        self.assertIsNotNone(classes)
        self.assertNotIn(
            'd-none', classes,
            "La tuile reste invisible malgré une opportunité (classes : %s)."
            % classes)


@tagged('post_install', '-at_install')
class TestHolderDashboard(HttpCase):
    """Le tableau de bord du porteur, rendu pour de bon."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.innovation.project']
        cls.porteur = new_test_user(
            cls.env, login='e19d_porteur', password='e19d_porteur',
            groups='base.group_portal')
        cls.porteur.partner_id.sudo().write({'is_member': True})
        cls.secretariat = new_test_user(
            cls.env, login='e19d_secr', password='e19d_secr',
            groups='base.group_user,opex_membership.group_secretariat')
        cls.comite = new_test_user(
            cls.env, login='e19d_comite', password='e19d_comite',
            groups='base.group_user,opex_innovation.group_comite_evaluation')

    @staticmethod
    def _flat(text):
        return re.sub(r'\s+', ' ', text or '')

    def _project_in_evaluation(self):
        project = self.Project.sudo().create({
            'partner_id': self.porteur.partner_id.id,
            'name': "Smart Factory",
            'resume': "Une usine pilotée par l'IA.",
            'probleme': "Arrêts imprévus.",
            'solution': "Maintenance prédictive.",
            'secteur': 'industrie',
            'maturite': 'mvp',
        })
        for code, user in (('submit', self.porteur),
                           ('take_in_charge', self.secretariat),
                           ('qualify', self.secretariat),
                           ('evaluate_directly', self.comite)):
            transition = project.workflow_definition_id.transition_ids.filtered(
                lambda t: t.code == code)
            project.with_user(user).workflow_do_transition(transition)
        return project

    def test_the_card_renders_the_seven_milestones(self):
        self._project_in_evaluation()
        self.authenticate('e19d_porteur', 'e19d_porteur')
        response = self.url_open('/my/innovation')
        self.assertEqual(response.status_code, 200)
        flat = self._flat(response.text)

        # Positive d'abord : la page est bien rendue.
        self.assertIn("Smart Factory", flat)
        for label in ("Déposé", "Contrôle terminé", "Évaluation",
                      "Décision", "Accompagnement", "Financement",
                      "Industrialisation"):
            self.assertIn(label, flat, "Jalon « %s » absent de la carte." % label)

        self.assertIn("Votre projet est actuellement évalué.", flat)
        self.assertIn("Consulter mon projet", flat)

    def test_the_card_never_shows_a_technical_stage_code(self):
        """La règle d'or, vérifiée sur le HTML brut."""
        self._project_in_evaluation()
        self.authenticate('e19d_porteur', 'e19d_porteur')
        response = self.url_open('/my/innovation')
        raw = response.text

        # Positive d'abord.
        self.assertIn("Smart Factory", raw)
        for code in ('under_review', 'evaluate_directly',
                     'complement_requested', 'workflow_stage_id'):
            self.assertNotIn(
                code, raw, "Code technique « %s » rendu au porteur." % code)


@tagged('post_install', '-at_install')
class TestStaffDashboard(HttpCase):
    """Le tableau de bord du gestionnaire — le back-office a le droit d'être
    détaillé."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.innovation.project']
        cls.porteur = new_test_user(
            cls.env, login='e19s_porteur', password='e19s_porteur',
            groups='base.group_portal')
        cls.porteur.partner_id.sudo().write({'is_member': True})
        cls.secretariat = new_test_user(
            cls.env, login='e19s_secr', password='e19s_secr',
            groups='base.group_user,opex_membership.group_secretariat')
        cls.comite = new_test_user(
            cls.env, login='e19s_comite', password='e19s_comite',
            groups='base.group_user,opex_innovation.group_comite_evaluation')
        cls.ceo = new_test_user(
            cls.env, login='e19s_ceo', password='e19s_ceo',
            groups='base.group_user,opex_innovation.group_innovation_manager')
        cls.intrus = new_test_user(
            cls.env, login='e19s_intrus', password='e19s_intrus',
            groups='base.group_user')

    @staticmethod
    def _flat(text):
        return re.sub(r'\s+', ' ', text or '')

    def _submitted_project(self, name="Smart Factory"):
        project = self.Project.sudo().create({
            'partner_id': self.porteur.partner_id.id,
            'name': name,
            'resume': "Une usine pilotée par l'IA.",
            'probleme': "Arrêts imprévus.",
            'solution': "Maintenance prédictive.",
            'secteur': 'industrie',
            'maturite': 'mvp',
        })
        transition = project.workflow_definition_id.transition_ids.filtered(
            lambda t: t.code == 'submit')
        project.with_user(self.porteur).workflow_do_transition(transition)
        return project

    def test_the_dashboard_counts_projects_by_stage(self):
        self._submitted_project("Alpha")
        self._submitted_project("Beta")

        self.authenticate('e19s_ceo', 'e19s_ceo')
        response = self.url_open('/staff/innovation/dashboard')
        self.assertEqual(response.status_code, 200)
        flat = self._flat(response.text)

        self.assertIn("Projets par étape", flat)
        self.assertIn("Délais", flat)
        self.assertIn("Alertes", flat)
        # Le back-office a le droit aux codes techniques.
        self.assertIn("submitted", flat)

    def test_two_projects_at_the_same_stage_count_as_two(self):
        """⚠ `mapped()` sur un Many2one dédoublonne : deux projets à la même
        étape n'en feraient qu'un. Le comptage se fait à part."""
        self._submitted_project("Alpha")
        self._submitted_project("Beta")

        from odoo.addons.opex_innovation.controllers.dashboard import (
            InnovationStaffDashboard,
        )
        projects = self.Project.sudo().search(
            [('workflow_stage_id.code', '=', 'submitted')])
        rows = InnovationStaffDashboard()._by_stage(projects)
        submitted = [r for r in rows if r['code'] == 'submitted'][:1]
        self.assertTrue(submitted)
        self.assertEqual(submitted[0]['count'], len(projects))
        self.assertGreaterEqual(submitted[0]['count'], 2)

    def test_an_alert_names_the_file_it_points_at(self):
        """« 3 anomalies » sans dire lesquelles obligerait à les chercher."""
        project = self._submitted_project()
        for code, user in (('take_in_charge', self.secretariat),
                           ('qualify', self.secretariat),
                           ('evaluate_directly', self.comite)):
            transition = project.workflow_definition_id.transition_ids.filtered(
                lambda t: t.code == code)
            project.with_user(user).workflow_do_transition(transition)
        self.assertEqual(project.workflow_stage_id.code, 'evaluation')

        self.authenticate('e19s_ceo', 'e19s_ceo')
        response = self.url_open('/staff/innovation/dashboard')
        flat = self._flat(response.text)

        self.assertIn("Évaluation sans avis rendu", flat)
        self.assertIn("Smart Factory", flat)

    def test_the_dashboard_refuses_a_non_staff_user(self):
        self._submitted_project()
        self.authenticate('e19s_intrus', 'e19s_intrus')
        response = self.url_open('/staff/innovation/dashboard')
        self.assertEqual(response.status_code, 200)
        raw = response.text
        self.assertNotIn("Projets par étape", raw)
        self.assertNotIn("Smart Factory", raw)
