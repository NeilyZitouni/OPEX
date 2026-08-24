import html
import re

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestEvaluation(HttpCase):
    

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.innovation.project']
        cls.Evaluation = cls.env['opex.innovation.evaluation']

        cls.porteur = new_test_user(
            cls.env, login='ev_porteur', password='ev_porteur',
            groups='base.group_portal')
        cls.porteur.partner_id.sudo().write({'is_member': True})
        cls.secretariat = new_test_user(
            cls.env, login='ev_secr', password='ev_secr',
            groups='base.group_user,opex_membership.group_secretariat')
        cls.comite = new_test_user(
            cls.env, login='ev_comite', password='ev_comite',
            groups='base.group_user,opex_innovation.group_comite_evaluation')

        # Deux évaluateurs — le minimum pour que la confidentialité ait un sens.
        cls.alice = new_test_user(
            cls.env, login='ev_alice', password='ev_alice',
            groups='base.group_portal')
        cls.bob = new_test_user(
            cls.env, login='ev_bob', password='ev_bob',
            groups='base.group_portal')
        # Un expert du vivier, jamais désigné : le témoin.
        cls.carol = new_test_user(
            cls.env, login='ev_carol', password='ev_carol',
            groups='base.group_portal')
        cls.carol.partner_id.sudo().write({'is_expert': True})

    def _csrf(self):
        page = self.url_open('/my').text
        match = re.search(r'csrf_token: "([^"]+)"', page)
        self.assertTrue(match, "Jeton CSRF introuvable")
        return match.group(1)

    @staticmethod
    def _readable(text):
        """Le HTML rendu, entités décodées et blancs normalisés.

        Une apostrophe française sort en `&#39;` et une phrase du gabarit est
        coupée par les retours à la ligne de la source. Chercher le texte tel
        qu'on le lit à l'écran demande donc de défaire les deux — sinon
        l'assertion échoue sur une question d'encodage et non de contenu.

        ⚠ Cela vaut pour les assertions **positives**. Les assertions négatives
        d'un test de confidentialité doivent porter sur le HTML **brut** : une
        donnée présente sous forme échappée reste une donnée présente.
        """
        return " ".join(html.unescape(text).split())

    def _post(self, url, data=None):
        payload = {'csrf_token': self._csrf()}
        payload.update(data or {})
        return self.url_open(url, data=payload)

    def _transition(self, project, code):
        return project.workflow_definition_id.sudo().transition_ids.filtered(
            lambda t: t.code == code)

    def _qualified_project(self):
        project = self.Project.sudo().create({
            'partner_id': self.porteur.partner_id.id,
            'name': "Smart Factory",
            'resume': "Une usine pilotée par l'IA.",
            'probleme': "Arrêts imprévus.",
            'solution': "Maintenance prédictive.",
            'secteur': 'industrie',
            'maturite': 'mvp',
        })
        project.with_user(self.porteur).workflow_do_transition(
            self._transition(project, 'submit'))
        project.with_user(self.secretariat).workflow_do_transition(
            self._transition(project, 'take_in_charge'))
        project.with_user(self.secretariat).workflow_do_transition(
            self._transition(project, 'qualify'))
        return project

    # ------------------------------------------------------------
    # Deux scénarios, deux transitions
    # ------------------------------------------------------------

    def test_two_distinct_transitions_leave_qualified(self):
        """Schéma 6 : avec évaluateurs, ou évaluation directe.

        Deux transitions, pas une seule avec un `if` dedans. Le comité choisit
        en cliquant, pas en remplissant un champ que du code interpréterait.
        """
        project = self._qualified_project()
        options = project.workflow_instance_id.transition_options(
            user=self.comite)
        codes = {option['transition'].code for option in options}
        self.assertEqual(codes, {'evaluate_with_experts', 'evaluate_directly'})

    def test_scenario_b_needs_no_evaluator_at_all(self):
        """« Tous les projets ne nécessitent pas une expertise externe. »"""
        project = self._qualified_project()
        project.with_user(self.comite).workflow_do_transition(
            self._transition(project, 'evaluate_directly'))

        self.assertEqual(project.workflow_stage_id.code, 'evaluation')
        self.assertFalse(project.evaluation_ids)

        project.with_user(self.comite).workflow_do_transition(
            self._transition(project, 'accept'), comment="Dossier convaincant.")
        self.assertEqual(project.workflow_stage_id.code, 'accepted')

    # ------------------------------------------------------------
    # Expert ≠ évaluateur
    # ------------------------------------------------------------

    def test_being_an_expert_opens_no_project(self):
        """Le rôle « Expert » est un profil du vivier, pas un accès."""
        project = self._qualified_project()
        self.assertTrue(self.carol.partner_id.is_expert)
        self.assertFalse(
            project.workflow_instance_id._has_access(self.carol, 'limited'))
        self.assertFalse(
            self.Project.with_user(self.carol).search([]))

    def test_designation_is_what_opens_the_file(self):
        project = self._qualified_project()
        self.assertFalse(
            project.workflow_instance_id._has_access(self.alice, 'limited'))

        project.designate_evaluator(self.alice.partner_id)

        self.assertTrue(
            project.workflow_instance_id._has_access(self.alice, 'limited'))
        # …au niveau « limité » : le périmètre de sa mission, pas le dossier
        # entier.
        self.assertFalse(
            project.workflow_instance_id._has_access(self.alice, 'full'))

    def test_designation_creates_both_the_opinion_and_the_actor_line(self):
        project = self._qualified_project()
        evaluation = project.designate_evaluator(self.alice.partner_id)

        self.assertEqual(evaluation.state, 'requested')
        self.assertEqual(evaluation.project_id, project)

        role = self.env.ref('opex_innovation.role_evaluateur')
        actors = project.workflow_instance_id.sudo().actor_ids.filtered(
            lambda a: a.role_id == role and a.user_id == self.alice)
        self.assertTrue(actors)

    def test_the_same_evaluator_is_not_solicited_twice(self):
        project = self._qualified_project()
        project.designate_evaluator(self.alice.partner_id)
        with self.assertRaises(UserError) as error:
            project.designate_evaluator(self.alice.partner_id)
        self.assertIn("déjà sollicité", str(error.exception))

    def test_revoking_closes_the_access(self):
        project = self._qualified_project()
        project.designate_evaluator(self.alice.partner_id)
        self.assertTrue(
            project.workflow_instance_id._has_access(self.alice, 'limited'))

        project.revoke_evaluator(self.alice.partner_id)
        self.assertFalse(
            project.workflow_instance_id._has_access(self.alice, 'limited'))

    # ------------------------------------------------------------
    # La grille
    # ------------------------------------------------------------

    def _with_two_evaluators(self):
        project = self._qualified_project()
        project.with_user(self.comite).workflow_do_transition(
            self._transition(project, 'evaluate_with_experts'))
        alice = project.designate_evaluator(self.alice.partner_id)
        bob = project.designate_evaluator(self.bob.partner_id)
        return project, alice, bob

    def test_total_is_the_sum_of_the_six_criteria(self):
        project, alice, _bob = self._with_two_evaluators()
        alice.sudo().write({
            'score_innovation': 18, 'score_pertinence': 16,
            'score_faisabilite': 15, 'score_marche': 14,
            'score_equipe': 8, 'score_impact': 9,
        })
        self.assertEqual(alice.score_total, 80)

    def test_each_criterion_is_capped_at_its_own_maximum(self):
        project, alice, _bob = self._with_two_evaluators()
        with self.assertRaises(UserError) as error:
            alice.sudo().score_equipe = 15  # maximum 10
        self.assertIn("entre 0 et 10", str(error.exception))

        with self.assertRaises(UserError):
            alice.sudo().score_innovation = 21  # maximum 20

    def test_project_score_is_the_average_of_submitted_opinions(self):
        """⚠ C'est ce champ que lit `field('score') >= 70` du test final."""
        project, alice, bob = self._with_two_evaluators()
        alice.sudo().write({'score_innovation': 20, 'score_pertinence': 20,
                            'score_faisabilite': 20, 'score_marche': 20,
                            'score_equipe': 10, 'score_impact': 10})
        alice.sudo().action_submit()
        bob.sudo().write({'score_innovation': 12, 'score_pertinence': 12,
                          'score_faisabilite': 12, 'score_marche': 12,
                          'score_equipe': 6, 'score_impact': 6})
        bob.sudo().action_submit()

        project.invalidate_recordset()
        self.assertEqual(project.score, 80)  # (100 + 60) / 2

    def test_an_unsubmitted_opinion_does_not_weigh_on_the_score(self):
        project, alice, bob = self._with_two_evaluators()
        alice.sudo().write({'score_innovation': 20, 'score_pertinence': 20,
                            'score_faisabilite': 20, 'score_marche': 20,
                            'score_equipe': 10, 'score_impact': 10})
        alice.sudo().action_submit()
        # Bob a commencé mais n'a rien rendu : sa note ne compte pas.
        bob.sudo().write({'score_innovation': 1, 'state': 'in_progress'})

        project.invalidate_recordset()
        self.assertEqual(project.score, 100)

    def test_a_submitted_opinion_is_frozen(self):
        project, alice, _bob = self._with_two_evaluators()
        alice.sudo().action_submit()
        with self.assertRaises(UserError) as error:
            alice.with_user(self.alice).write({'commentaires': "Je me ravise."})
        self.assertIn("plus être modifié", str(error.exception))

    # ------------------------------------------------------------
    # ⚠ CONFIDENTIALITÉ — le test central
    # ------------------------------------------------------------

    def test_an_evaluator_does_not_see_the_opinion_of_another(self):
        """Deux évaluateurs, chacun aveugle à l'autre tant qu'il n'a pas rendu."""
        project, alice, bob = self._with_two_evaluators()
        bob.sudo().write({
            'score_innovation': 3,
            'commentaires': "SECRET DE BOB",
        })
        bob.sudo().action_submit()

        # Alice n'a pas rendu : elle ne voit que le sien.
        visible = project.visible_evaluations(self.alice)
        self.assertEqual(visible, alice)
        self.assertNotIn(bob, visible)

    def test_once_submitted_an_evaluator_sees_the_other_submitted_ones(self):
        project, alice, bob = self._with_two_evaluators()
        bob.sudo().action_submit()
        alice.sudo().action_submit()

        visible = project.visible_evaluations(self.alice)
        self.assertIn(alice, visible)
        self.assertIn(bob, visible)

    def test_the_committee_sees_every_opinion(self):
        project, alice, bob = self._with_two_evaluators()
        visible = project.visible_evaluations(self.comite)
        self.assertIn(alice, visible)
        self.assertIn(bob, visible)

    def test_someone_who_is_not_an_evaluator_sees_nothing(self):
        project, _alice, _bob = self._with_two_evaluators()
        self.assertFalse(project.visible_evaluations(self.carol))

    def test_the_evaluator_page_never_renders_another_opinion(self):
        """⚠ LE test de sécurité de l'extension.

        « Présent dans le HTML » suffirait à violer la confidentialité : un
        évaluateur curieux ouvre la source de la page. On vérifie donc le HTML
        produit, pas ce qui s'affiche.
        """
        project, alice, bob = self._with_two_evaluators()
        bob.sudo().write({
            'score_innovation': 3,
            'commentaires': "SECRET DE BOB",
            'points_faibles': "FAIBLESSE VUE PAR BOB",
        })
        bob.sudo().action_submit()

        alice.sudo().write({'commentaires': "Note personnelle d'Alice"})

        self.authenticate('ev_alice', 'ev_alice')
        raw = self.url_open('/my/innovation/evaluation/%s' % alice.id).text

        # Sa propre page fonctionne — assertion positive, sur le texte lisible.
        # Sans elle, les trois absences ci-dessous passeraient aussi sur une
        # page d'erreur 500, qui ne contient rien du tout.
        self.assertIn("Note personnelle d'Alice", self._readable(raw))
        self.assertIn("Smart Factory", self._readable(raw))

        # …et rien de Bob n'y figure, ni visible ni masqué.
        # ⚠ Sur le HTML **brut** : une donnée échappée reste une donnée
        # présente, et se lit dans la source de la page.
        self.assertNotIn("SECRET DE BOB", raw)
        self.assertNotIn("FAIBLESSE VUE PAR BOB", raw)
        self.assertNotIn(self.bob.partner_id.name, raw)

    def test_an_evaluator_cannot_reach_another_opinion_by_its_id(self):
        project, _alice, bob = self._with_two_evaluators()
        bob.sudo().write({'commentaires': "SECRET DE BOB"})

        self.authenticate('ev_alice', 'ev_alice')
        response = self.url_open(
            '/my/innovation/evaluation/%s' % bob.id, allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))

    def test_the_database_rule_blocks_an_unsubmitted_opinion(self):
        """Le plancher de la base, indépendamment des écrans."""
        project, _alice, bob = self._with_two_evaluators()
        bob.sudo().write({'commentaires': "SECRET DE BOB"})

        self.env.invalidate_all()
        visible = self.Evaluation.with_user(self.alice).search([])
        self.assertNotIn(bob, visible)

    def test_a_non_evaluator_portal_user_reads_no_opinion_at_all(self):
        project, alice, bob = self._with_two_evaluators()
        alice.sudo().action_submit()

        self.env.invalidate_all()
        # Carol n'est désignée sur aucun projet : même les avis rendus lui
        # sont inutiles, elle n'accède pas au dossier.
        self.assertFalse(
            self.Project.with_user(self.carol).search([]))

    # ------------------------------------------------------------
    # L'avis reste consultatif
    # ------------------------------------------------------------

    def test_submitting_an_opinion_triggers_no_transition(self):
        """L'avis ne décide de rien : le comité décide."""
        project, alice, _bob = self._with_two_evaluators()
        stage_before = project.workflow_stage_id

        alice.sudo().write({'score_innovation': 20, 'score_pertinence': 20,
                            'score_faisabilite': 20, 'score_marche': 20,
                            'score_equipe': 10, 'score_impact': 10})
        alice.sudo().action_submit()

        project.invalidate_recordset()
        self.assertEqual(project.workflow_stage_id, stage_before)
        self.assertEqual(project.workflow_state, 'running')

    def test_the_committee_can_decide_against_the_opinion(self):
        """« Le Comité n'est pas obligé de suivre l'avis ou la note. »"""
        project, alice, _bob = self._with_two_evaluators()
        alice.sudo().write({'score_innovation': 20, 'score_pertinence': 20,
                            'score_faisabilite': 20, 'score_marche': 20,
                            'score_equipe': 10, 'score_impact': 10})
        alice.sudo().action_submit()
        project.invalidate_recordset()
        self.assertEqual(project.score, 100)

        # Note maximale, et le comité refuse quand même. Rien ne l'en empêche.
        project.with_user(self.comite).workflow_do_transition(
            self._transition(project, 'reject'),
            comment="Hors des priorités du cluster cette année.")
        self.assertEqual(project.workflow_stage_id.code, 'rejected')

    def test_an_evaluator_cannot_move_the_project(self):
        project, _alice, _bob = self._with_two_evaluators()
        accept = self._transition(project, 'accept')
        self.assertFalse(
            project.workflow_instance_id._check_transition_allowed(
                accept, user=self.alice))

    # ------------------------------------------------------------
    # Le portail de l'évaluateur
    # ------------------------------------------------------------

    def test_the_evaluator_sees_his_assignments(self):
        project, _alice, _bob = self._with_two_evaluators()
        self.authenticate('ev_alice', 'ev_alice')
        body = self.url_open('/my/innovation/evaluations').text
        self.assertIn("Smart Factory", body)

    def test_the_grid_can_be_filled_and_submitted_from_the_portal(self):
        project, alice, _bob = self._with_two_evaluators()
        self.authenticate('ev_alice', 'ev_alice')

        self._post('/my/innovation/evaluation/%s' % alice.id, {
            'score_innovation': '18', 'score_pertinence': '16',
            'score_faisabilite': '15', 'score_marche': '14',
            'score_equipe': '8', 'score_impact': '9',
            'points_forts': "Équipe solide.",
            'action': 'submit',
        })

        alice.invalidate_recordset()
        self.assertEqual(alice.state, 'submitted')
        self.assertEqual(alice.score_total, 80)
        self.assertEqual(alice.points_forts, "Équipe solide.")

    def test_a_draft_can_be_saved_without_submitting(self):
        project, alice, _bob = self._with_two_evaluators()
        self.authenticate('ev_alice', 'ev_alice')

        self._post('/my/innovation/evaluation/%s' % alice.id, {
            'score_innovation': '12', 'action': 'save'})

        alice.invalidate_recordset()
        self.assertEqual(alice.state, 'in_progress')
        self.assertEqual(alice.score_innovation, 12)

    def test_a_submitted_grid_can_no_longer_be_posted(self):
        project, alice, _bob = self._with_two_evaluators()
        alice.sudo().write({'score_innovation': 10})
        alice.sudo().action_submit()

        self.authenticate('ev_alice', 'ev_alice')
        self._post('/my/innovation/evaluation/%s' % alice.id, {
            'score_innovation': '20', 'action': 'save'})

        alice.invalidate_recordset()
        self.assertEqual(alice.score_innovation, 10)
