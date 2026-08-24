import re

from odoo.tests.common import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestStaffControl(HttpCase):
    """Extension 12 — contrôle administratif et qualification."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.innovation.project']

        cls.member = new_test_user(
            cls.env, login='sc_member', password='sc_member',
            groups='base.group_portal')
        cls.member.partner_id.sudo().write({'is_member': True})

        cls.secretariat = new_test_user(
            cls.env, login='sc_secr', password='sc_secr',
            groups='base.group_user,opex_membership.group_secretariat')
        cls.comite = new_test_user(
            cls.env, login='sc_comite', password='sc_comite',
            groups='base.group_user,opex_innovation.group_comite_evaluation')
        cls.intruder = new_test_user(
            cls.env, login='sc_intruder', password='sc_intruder',
            groups='base.group_user')

    def _csrf(self):
        """Jeton CSRF extrait d'une page réellement rendue.

        `ir.http._get_csrf_token()` n'existe pas : le jeton est lié à la
        session HTTP, pas au registre. Odoo l'écrit dans le script d'amorçage
        de chaque page ; on le lit là où le navigateur le lirait.
        """
        page = self.url_open('/my').text
        match = re.search(r'csrf_token: "([^"]+)"', page)
        self.assertTrue(match, "Jeton CSRF introuvable dans la page")
        return match.group(1)

    def _post(self, url, data=None):
        payload = {'csrf_token': self._csrf()}
        payload.update(data or {})
        return self.url_open(url, data=payload)

    def _project(self, **values):
        base = {
            'partner_id': self.member.partner_id.id,
            'name': "Smart Factory",
            'resume': "Une usine pilotée par l'IA.",
            'probleme': "Arrêts imprévus.",
            'solution': "Maintenance prédictive.",
            'secteur': 'industrie',
            'maturite': 'mvp',
            'besoin_financement': True,
            'montant_recherche': 500000,
        }
        base.update(values)
        return self.Project.sudo().create(base)

    def _transition(self, project, code):
        return project.workflow_definition_id.sudo().transition_ids.filtered(
            lambda t: t.code == code)

    def _submitted(self):
        """Un projet arrivé à l'étape de contrôle."""
        project = self._project()
        project.with_user(self.member).workflow_do_transition(
            self._transition(project, 'submit'))
        project.with_user(self.secretariat).workflow_do_transition(
            self._transition(project, 'take_in_charge'))
        return project

    # ------------------------------------------------------------
    # Le contrôle d'accès, unique
    # ------------------------------------------------------------

    def test_an_ordinary_internal_user_is_refused(self):
        self._submitted()
        self.authenticate('sc_intruder', 'sc_intruder')
        response = self.url_open('/staff/innovation', allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))

    def test_a_portal_member_is_refused(self):
        self._submitted()
        self.authenticate('sc_member', 'sc_member')
        response = self.url_open('/staff/innovation', allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))

    def test_the_detail_route_is_protected_too(self):
        """Le même contrôle sur toutes les routes, pas seulement la liste."""
        project = self._submitted()
        self.authenticate('sc_intruder', 'sc_intruder')
        response = self.url_open(
            '/staff/innovation/%s' % project.id, allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))

    def test_the_transition_route_is_protected_too(self):
        project = self._submitted()
        stage_before = project.workflow_stage_id

        self.authenticate('sc_intruder', 'sc_intruder')
        self._post('/staff/innovation/%s/transition' % project.id, {
            'transition_id': str(self._transition(project, 'qualify').id)})

        project.invalidate_recordset()
        self.assertEqual(project.workflow_stage_id, stage_before)

    # ------------------------------------------------------------
    # La file, filtrée par rôle
    # ------------------------------------------------------------

    def test_the_secretariat_sees_what_awaits_a_control(self):
        project = self._submitted()
        self.authenticate('sc_secr', 'sc_secr')
        body = self.url_open('/staff/innovation').text
        self.assertIn(project.name, body)

    def test_the_committee_does_not_see_what_is_still_under_control(self):
        """La file suit le rôle : chacun voit ce qui l'attend, lui."""
        project = self._submitted()
        self.authenticate('sc_comite', 'sc_comite')
        body = self.url_open('/staff/innovation').text
        self.assertNotIn(project.name, body)

    def test_the_committee_sees_it_once_qualified(self):
        project = self._submitted()
        project.with_user(self.secretariat).workflow_do_transition(
            self._transition(project, 'qualify'))

        self.authenticate('sc_comite', 'sc_comite')
        body = self.url_open('/staff/innovation').text
        self.assertIn(project.name, body)

    # ------------------------------------------------------------
    # Section 13 — Ce que le contrôleur doit voir
    # ------------------------------------------------------------

    def test_the_detail_page_shows_everything_needed_to_control(self):
        project = self._submitted()
        self.env['opex.innovation.team.member'].sudo().create({
            'project_id': project.id, 'name': "Amine", 'fonction': "CTO"})

        self.authenticate('sc_secr', 'sc_secr')
        body = self.url_open('/staff/innovation/%s' % project.id).text

        for expected in (
            project.name,
            project.partner_id.display_name,
            "Résumé", "Problème", "Solution",
            "Pièces jointes", "Besoins et financement",
            "Historique", "Amine",
        ):
            self.assertIn(expected, body)

    def test_missing_documents_are_pointed_out(self):
        project = self._submitted()
        self.authenticate('sc_secr', 'sc_secr')
        body = self.url_open('/staff/innovation/%s' % project.id).text
        self.assertIn("Aucune pièce jointe", body)

    # ------------------------------------------------------------
    # Section 14 — La fiche de qualification
    # ------------------------------------------------------------

    def test_the_qualification_sheet_is_a_view_not_a_model(self):
        """Aucun modèle « qualification » n'existe : c'est un écran."""
        self.assertNotIn('opex.innovation.qualification', self.env)

        project = self._submitted()
        self.authenticate('sc_secr', 'sc_secr')
        body = self.url_open('/staff/innovation/%s' % project.id).text

        self.assertIn("Fiche de qualification", body)
        for expected in ("Secteur", "Maturité", "Potentiel marché",
                         "Besoin financement", "Besoin expertise"):
            self.assertIn(expected, body)

    # ------------------------------------------------------------
    # Les deux issues du contrôle
    # ------------------------------------------------------------

    def test_both_exits_are_offered_at_the_control_stage(self):
        project = self._submitted()
        self.authenticate('sc_secr', 'sc_secr')
        body = self.url_open('/staff/innovation/%s' % project.id).text
        self.assertIn("Dossier conforme", body)
        self.assertIn("Demander un complément", body)

    def test_conform_moves_the_project_to_qualified(self):
        project = self._submitted()
        self.authenticate('sc_secr', 'sc_secr')
        self._post('/staff/innovation/%s/transition' % project.id, {
            'transition_id': str(self._transition(project, 'qualify').id)})

        project.invalidate_recordset()
        self.assertEqual(project.workflow_stage_id.code, 'qualified')

    def test_complement_requires_a_reason(self):
        """`requires_comment` vient de la configuration, pas du controller."""
        project = self._submitted()
        self.authenticate('sc_secr', 'sc_secr')
        self._post('/staff/innovation/%s/transition' % project.id, {
            'transition_id': str(
                self._transition(project, 'request_complement').id),
            'comment': '   ',
        })

        project.invalidate_recordset()
        self.assertEqual(project.workflow_stage_id.code, 'under_review')

    def test_complement_with_a_reason_moves_and_records_it(self):
        project = self._submitted()
        self.authenticate('sc_secr', 'sc_secr')
        self._post('/staff/innovation/%s/transition' % project.id, {
            'transition_id': str(
                self._transition(project, 'request_complement').id),
            'comment': "Merci d'ajouter le business plan détaillé.",
        })

        project.invalidate_recordset()
        self.assertEqual(project.workflow_stage_id.code, 'complement_requested')
        self.assertIn("business plan", project.motif_complement)

    # ------------------------------------------------------------
    # Côté porteur — le retour et la resoumission
    # ------------------------------------------------------------

    def _with_complement(self):
        project = self._submitted()
        project.with_user(self.secretariat).workflow_do_transition(
            self._transition(project, 'request_complement'),
            comment="Merci d'ajouter le business plan détaillé.")
        project.sudo().motif_complement = "Merci d'ajouter le business plan détaillé."
        return project

    def test_the_holder_sees_the_reason_prominently(self):
        project = self._with_complement()
        self.authenticate('sc_member', 'sc_member')
        body = self.url_open('/my/innovation/%s' % project.id).text

        self.assertIn("Action requise sur votre projet", body)
        self.assertIn("business plan", body)

    def test_the_holder_can_correct_and_resubmit(self):
        project = self._with_complement()
        self.authenticate('sc_member', 'sc_member')

        # Il corrige…
        self._post('/my/innovation/%s/marche' % project.id, {
            'marche_cible': "Industriels algériens"})
        project.invalidate_recordset()
        self.assertEqual(project.marche_cible, "Industriels algériens")

        # …puis renvoie : RETOUR vers le contrôle.
        transition = self._transition(project, 'resubmit_after_complement')
        self._post('/my/innovation/%s/resubmit' % project.id, {
            'transition_id': str(transition.id)})

        project.invalidate_recordset()
        self.assertEqual(project.workflow_stage_id.code, 'under_review')
        self.assertFalse(project.motif_complement)

    def test_the_project_comes_back_in_the_secretariat_queue(self):
        project = self._with_complement()
        transition = self._transition(project, 'resubmit_after_complement')
        project.with_user(self.member).workflow_do_transition(transition)

        self.authenticate('sc_secr', 'sc_secr')
        body = self.url_open('/staff/innovation').text
        self.assertIn(project.name, body)

    def test_the_history_records_both_passages_through_control(self):
        project = self._with_complement()
        transition = self._transition(project, 'resubmit_after_complement')
        project.with_user(self.member).workflow_do_transition(transition)

        # Liste et non `mapped()` : un Many2one dédupliquerait les passages.
        visited = [
            entry.to_stage_id.code
            for entry in project.workflow_instance_id.history_ids
        ]
        self.assertEqual(visited.count('under_review'), 2)
