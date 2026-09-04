import html
import re

from odoo.tests.common import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestMatchingConfiguration(HttpCase):
    """Extension 15 — le matching **configuré** pour ce module.

    Cette extension ne doit écrire aucun scoring : le moteur de l'Extension 7
    fait le calcul, ces tests vérifient que la configuration lui dit ce qu'il
    faut comparer.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.innovation.project']
        cls.Candidate = cls.env['opex.matching.candidate']
        cls.Criteria = cls.env['opex.matching.criteria']
        cls.Competence = cls.env['opex.innovation.competence']

        cls.porteur = new_test_user(
            cls.env, login='mt_porteur', password='mt_porteur',
            groups='base.group_portal')
        cls.porteur.partner_id.sudo().write(
            {'is_member': True, 'wilaya': "Alger"})
        cls.secretariat = new_test_user(
            cls.env, login='mt_secr', password='mt_secr',
            groups='base.group_user,opex_membership.group_secretariat')
        cls.comite = new_test_user(
            cls.env, login='mt_comite', password='mt_comite',
            groups='base.group_user,opex_innovation.group_comite_evaluation')
        cls.ceo = new_test_user(
            cls.env, login='mt_ceo', password='mt_ceo',
            groups='base.group_user,opex_innovation.group_innovation_manager')

        cls.ia = cls.Competence.create({'name': "IA", 'code': 'ia'})
        cls.iot = cls.Competence.create({'name': "IoT", 'code': 'iot'})

        # Un expert pertinent, un expert hors sujet, un investisseur.
        cls.expert = cls._make_expert(cls, 'mt_expert', cls.ia, "Alger",
                                      "industrie")
        cls.expert_hs = cls._make_expert(cls, 'mt_expert_hs', cls.iot, "Oran",
                                         "agriculture")
        cls.investor = cls._make_investor(cls, 'mt_investor', cls.ia, 1000000)

    def _make_expert(self, login, competence, wilaya, domaine):
        user = new_test_user(
            self.env, login=login, password=login, groups='base.group_portal')
        profile = self.env['opex.innovation.expert.profile'].sudo().create({
            'partner_id': user.partner_id.id,
            'domaine_expertise': domaine,
            'competence_ids': [(6, 0, competence.ids)],
        })
        user.partner_id.sudo().write({
            'is_expert': True,
            'expert_profile_id': profile.id,
            'wilaya': wilaya,
        })
        return user

    def _make_investor(self, login, secteur, montant_max):
        user = new_test_user(
            self.env, login=login, password=login, groups='base.group_portal')
        profile = self.env['opex.innovation.investor.profile'].sudo().create({
            'partner_id': user.partner_id.id,
            'type_investisseur': 'fonds',
            'secteur_ids': [(6, 0, secteur.ids)],
            'stade_maturite_recherche': 'mvp',
            'montant_max': montant_max,
        })
        user.partner_id.sudo().write({
            'is_investor': True,
            'investor_profile_id': profile.id,
        })
        return user

    def _csrf(self):
        match = re.search(r'csrf_token: "([^"]+)"', self.url_open('/my').text)
        self.assertTrue(match, "Jeton CSRF introuvable")
        return match.group(1)

    def _post(self, url, data=None):
        payload = {'csrf_token': self._csrf()}
        payload.update(data or {})
        return self.url_open(url, data=payload)

    def _transition(self, project, code):
        return project.workflow_definition_id.sudo().transition_ids.filtered(
            lambda t: t.code == code)

    def _accepted_project(self):
        project = self.Project.sudo().create({
            'partner_id': self.porteur.partner_id.id,
            'name': "Smart Factory",
            'resume': "Une usine pilotée par l'IA.",
            'probleme': "Arrêts imprévus.",
            'solution': "Maintenance prédictive.",
            'secteur': 'industrie',
            'maturite': 'mvp',
            'besoin_financement': True,
            'montant_recherche': 500000,
            'besoin_competence_ids': [(6, 0, self.ia.ids)],
            'besoin_accompagnement_ids': [(6, 0, self.ia.ids)],
        })
        for code, user in (
            ('submit', self.porteur), ('take_in_charge', self.secretariat),
            ('qualify', self.secretariat), ('evaluate_directly', self.comite),
        ):
            project.with_user(user).workflow_do_transition(
                self._transition(project, code))
        project.with_user(self.comite).workflow_do_transition(
            self._transition(project, 'accept'), comment="Convaincant.")
        return project

    # ------------------------------------------------------------
    # La configuration, pas du code
    # ------------------------------------------------------------

    def test_the_seven_criteria_are_configured(self):
        """Les sept critères de la section 19, en données."""
        definition = self.env['opex.workflow.definition']._get_for_code(
            'innovation_project')
        codes = set(self.Criteria.search(
            [('definition_id', '=', definition.id)]).mapped('code'))
        for expected in ('secteur', 'competences', 'localisation', 'maturite',
                         'accompagnement', 'financement', 'technologies'):
            self.assertIn(expected, codes)

    def test_the_business_module_writes_no_scoring(self):
        """Le scoring reste dans le moteur.

        Ce module configure ; il ne recalcule pas. Un `_score_` défini ici
        signifierait qu'on a réécrit ce que l'Extension 7 fait déjà.
        """
        import os

        import odoo.addons.opex_innovation as module
        root = os.path.dirname(module.__file__)
        offenders = []
        for directory, _dirs, filenames in os.walk(root):
            if 'tests' in directory.split(os.sep) or '__pycache__' in directory:
                continue
            for filename in filenames:
                if not filename.endswith('.py'):
                    continue
                path = os.path.join(directory, filename)
                with open(path, encoding='utf-8') as handle:
                    for number, line in enumerate(handle, start=1):
                        if 'def _score_candidate' in line or 'def run_matching' in line:
                            offenders.append('%s:%s' % (filename, number))
        self.assertFalse(
            offenders,
            "Le module métier réimplémente le scoring : %s" % offenders)

    def test_three_actions_produce_the_three_categories(self):
        """Le moteur cherche un type par exécution : trois actions, pas une
        extension du moteur."""
        transition = self.env.ref('opex_innovation.ptr_start_matching')
        types = set(transition.action_ids.filtered(
            lambda a: a.action_type == 'run_matching'
        ).mapped('matching_candidate_type'))
        self.assertEqual(types, {'expert', 'mentor', 'investisseur'})

    def test_each_action_restricts_its_own_pool(self):
        """Sans `matching_domain`, les trois recherches proposeraient les
        mêmes contacts."""
        for xmlid, expected in (
            ('opex_innovation.action_matching_experts', 'is_expert'),
            ('opex_innovation.action_matching_investisseurs', 'is_investor'),
        ):
            with self.subTest(action=xmlid):
                action = self.env.ref(xmlid)
                self.assertIn(expected, action.matching_domain)

    # ------------------------------------------------------------
    # Le matching produit ses trois listes
    # ------------------------------------------------------------

    def test_the_transition_produces_the_three_categories(self):
        project = self._accepted_project()
        project.with_user(self.ceo).workflow_do_transition(
            self._transition(project, 'start_matching'))

        candidates = self.Candidate.sudo().search(
            [('instance_id', '=', project.workflow_instance_id.id)])
        self.assertTrue(candidates)
        self.assertEqual(
            set(candidates.mapped('candidate_type')),
            {'expert', 'mentor', 'investisseur'})

    def test_the_relevant_expert_scores_above_the_irrelevant_one(self):
        project = self._accepted_project()
        project.with_user(self.ceo).workflow_do_transition(
            self._transition(project, 'start_matching'))

        experts = self.Candidate.sudo().search([
            ('instance_id', '=', project.workflow_instance_id.id),
            ('candidate_type', '=', 'expert'),
        ])
        scores = {c.partner_id: c.score for c in experts}
        self.assertGreater(
            scores.get(self.expert.partner_id, 0),
            scores.get(self.expert_hs.partner_id, 0))

    def test_investors_are_not_proposed_as_experts(self):
        project = self._accepted_project()
        project.with_user(self.ceo).workflow_do_transition(
            self._transition(project, 'start_matching'))

        experts = self.Candidate.sudo().search([
            ('instance_id', '=', project.workflow_instance_id.id),
            ('candidate_type', '=', 'expert'),
        ])
        self.assertNotIn(self.investor.partner_id, experts.mapped('partner_id'))

    def test_every_candidate_carries_its_explanation(self):
        """Un score sans explication n'est pas défendable."""
        project = self._accepted_project()
        project.with_user(self.ceo).workflow_do_transition(
            self._transition(project, 'start_matching'))

        candidates = self.Candidate.sudo().search(
            [('instance_id', '=', project.workflow_instance_id.id)])
        for candidate in candidates:
            self.assertTrue(candidate.detail)
            self.assertIn("Score", candidate.detail)

    # ------------------------------------------------------------
    # L'IA recommande, elle ne décide pas
    # ------------------------------------------------------------

    def test_matching_moves_the_project_only_by_the_asked_transition(self):
        project = self._accepted_project()
        project.with_user(self.ceo).workflow_do_transition(
            self._transition(project, 'start_matching'))

        # La transition demandée a eu lieu, et **une seule**.
        self.assertEqual(project.workflow_stage_id.code, 'matching')
        self.assertEqual(project.workflow_state, 'running')

    def test_accepting_a_candidate_does_not_move_the_project(self):
        project = self._accepted_project()
        project.with_user(self.ceo).workflow_do_transition(
            self._transition(project, 'start_matching'))
        stage_before = project.workflow_stage_id

        candidate = self.Candidate.sudo().search([
            ('instance_id', '=', project.workflow_instance_id.id)], limit=1)
        candidate.action_accept()
        project.propose_to_candidate(candidate)

        project.invalidate_recordset()
        self.assertEqual(project.workflow_stage_id, stage_before)

    def test_a_candidate_response_moves_nothing_either(self):
        project = self._accepted_project()
        project.with_user(self.ceo).workflow_do_transition(
            self._transition(project, 'start_matching'))
        stage_before = project.workflow_stage_id

        candidate = self.Candidate.sudo().search([
            ('instance_id', '=', project.workflow_instance_id.id)], limit=1)
        candidate.action_interested()

        project.invalidate_recordset()
        self.assertEqual(candidate.candidate_response, 'interested')
        self.assertEqual(project.workflow_stage_id, stage_before)

    # ------------------------------------------------------------
    # Section 20 — l'accès limité du candidat
    # ------------------------------------------------------------

    def _proposed(self):
        project = self._accepted_project()
        project.with_user(self.ceo).workflow_do_transition(
            self._transition(project, 'start_matching'))
        candidate = self.Candidate.sudo().search([
            ('instance_id', '=', project.workflow_instance_id.id),
            ('candidate_type', '=', 'expert'),
            ('partner_id', '=', self.expert.partner_id.id),
        ], limit=1)
        candidate.action_accept()
        project.propose_to_candidate(candidate)
        return project, candidate

    def test_the_proposal_opens_a_limited_access_only(self):
        project, _candidate = self._proposed()
        instance = project.workflow_instance_id
        self.assertTrue(instance._has_access(self.expert, 'limited'))
        self.assertFalse(instance._has_access(self.expert, 'full'))

    def test_a_candidate_not_retained_gets_no_access(self):
        project, _candidate = self._proposed()
        self.assertFalse(
            project.workflow_instance_id._has_access(self.expert_hs, 'limited'))

    def test_the_teaser_exposes_only_the_allowed_fields(self):
        """Section 20 : « seulement les informations auxquelles il a droit ».

        Le gabarit reçoit un dictionnaire, pas le projet : un champ non listé
        ne peut pas être rendu par inadvertance.
        """
        project, candidate = self._proposed()
        teaser = self.Project._matching_teaser(candidate)
        self.assertEqual(
            set(teaser) - {'candidate'},
            {'projet', 'secteur', 'resume', 'besoin', 'role', 'duree', 'score'})

    def test_the_opportunity_page_hides_the_financial_details(self):
        project, _candidate = self._proposed()
        project.sudo().write({
            'montant_recherche': 987654,
            'concurrence': "CONCURRENCE CONFIDENTIELLE",
        })

        self.authenticate('mt_expert', 'mt_expert')
        raw = self.url_open('/my/innovation/opportunities').text

        # Ce à quoi il a droit…
        readable = " ".join(html.unescape(raw).split())
        self.assertIn("Smart Factory", readable)
        self.assertIn("opportunité d'accompagnement", readable)
        # …et rien d'autre. Sur le HTML brut : une donnée échappée reste une
        # donnée présente.
        self.assertNotIn("987654", raw)
        self.assertNotIn("CONCURRENCE CONFIDENTIELLE", raw)

    def test_the_candidate_answers_from_the_portal(self):
        project, candidate = self._proposed()
        self.authenticate('mt_expert', 'mt_expert')

        self._post(
            '/my/innovation/opportunities/%s/respond' % candidate.id,
            {'response': 'interested'})

        candidate.invalidate_recordset()
        self.assertEqual(candidate.candidate_response, 'interested')
        self.assertTrue(candidate.date_response)

    def test_a_candidate_cannot_answer_for_another(self):
        project, candidate = self._proposed()
        self.authenticate('mt_expert_hs', 'mt_expert_hs')

        self._post(
            '/my/innovation/opportunities/%s/respond' % candidate.id,
            {'response': 'declined'})

        candidate.invalidate_recordset()
        self.assertEqual(candidate.candidate_response, 'pending')

    # ------------------------------------------------------------
    # L'écran du responsable
    # ------------------------------------------------------------

    def test_the_responsible_sees_the_three_lists_with_explanations(self):
        project = self._accepted_project()
        project.with_user(self.ceo).workflow_do_transition(
            self._transition(project, 'start_matching'))

        self.authenticate('mt_ceo', 'mt_ceo')
        body = self.url_open(
            '/staff/innovation/%s/matching' % project.id).text

        self.assertIn("Experts recommandés", body)
        self.assertIn("Investisseurs recommandés", body)
        self.assertIn("Comment ce score a été obtenu", body)
        self.assertIn("recommande, il ne décide pas", body)

    def test_the_responsible_can_decide_from_the_screen(self):
        project = self._accepted_project()
        project.with_user(self.ceo).workflow_do_transition(
            self._transition(project, 'start_matching'))
        candidate = self.Candidate.sudo().search([
            ('instance_id', '=', project.workflow_instance_id.id)], limit=1)

        self.authenticate('mt_ceo', 'mt_ceo')
        self._post('/staff/innovation/%s/matching/decide' % project.id,
                   {'candidate_id': str(candidate.id), 'decision': 'exclude'})

        candidate.invalidate_recordset()
        self.assertEqual(candidate.state, 'excluded')

    def test_the_matching_screen_is_staff_only(self):
        project = self._accepted_project()
        self.authenticate('mt_porteur', 'mt_porteur')
        response = self.url_open(
            '/staff/innovation/%s/matching' % project.id, allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))
