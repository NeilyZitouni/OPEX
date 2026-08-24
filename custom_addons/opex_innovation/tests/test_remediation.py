import re

from odoo.exceptions import UserError
from odoo.tests.common import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestRemediation(HttpCase):
    """Extension 14 — décision du comité, remédiation, versions."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.innovation.project']
        cls.Remediation = cls.env['opex.innovation.remediation']
        cls.Point = cls.env['opex.innovation.remediation.point']

        cls.porteur = new_test_user(
            cls.env, login='rm_porteur', password='rm_porteur',
            groups='base.group_portal')
        cls.porteur.partner_id.sudo().write({'is_member': True})
        cls.secretariat = new_test_user(
            cls.env, login='rm_secr', password='rm_secr',
            groups='base.group_user,opex_membership.group_secretariat')
        cls.comite = new_test_user(
            cls.env, login='rm_comite', password='rm_comite',
            groups='base.group_user,opex_innovation.group_comite_evaluation')

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

    def _in_evaluation(self):
        project = self.Project.sudo().create({
            'partner_id': self.porteur.partner_id.id,
            'name': "Smart Factory",
            'resume': "Version initiale du résumé.",
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
        project.with_user(self.comite).workflow_do_transition(
            self._transition(project, 'evaluate_directly'))
        return project

    # ------------------------------------------------------------
    # Les trois décisions, toutes motivées
    # ------------------------------------------------------------

    def test_the_three_decisions_all_require_a_reason(self):
        """Une décision sans motif laisse le porteur sans rien à corriger."""
        project = self._in_evaluation()
        for code in ('accept', 'adjourn', 'reject'):
            with self.subTest(decision=code):
                transition = self._transition(project, code)
                self.assertTrue(transition.requires_comment)

    def test_a_decision_without_a_reason_is_refused(self):
        project = self._in_evaluation()
        with self.assertRaises(UserError) as error:
            project.with_user(self.comite).workflow_do_transition(
                self._transition(project, 'reject'))
        self.assertIn("motif", str(error.exception))

    def test_rejection_closes_the_project_with_its_reason(self):
        project = self._in_evaluation()
        project.with_user(self.comite).workflow_do_transition(
            self._transition(project, 'reject'),
            comment="Hors des priorités du cluster.")

        self.assertEqual(project.workflow_stage_id.code, 'rejected')
        self.assertEqual(project.workflow_state, 'done')
        entry = project.workflow_instance_id.history_ids.filtered(
            lambda h: h.to_stage_id.code == 'rejected')
        self.assertIn("priorités", entry.comment)

    # ------------------------------------------------------------
    # Les deux pouvoirs supplémentaires du comité
    # ------------------------------------------------------------

    def test_the_committee_can_ask_for_more_information(self):
        """« Demander des informations complémentaires » est une transition."""
        project = self._in_evaluation()
        project.with_user(self.comite).workflow_do_transition(
            self._transition(project, 'committee_ask_info'),
            comment="Merci de préciser vos prévisions financières.")
        self.assertEqual(
            project.workflow_stage_id.code, 'complement_requested')

    def test_the_committee_can_ask_for_a_new_evaluation(self):
        project = self._in_evaluation()
        project.with_user(self.comite).workflow_do_transition(
            self._transition(project, 'committee_new_evaluation'),
            comment="Un avis complémentaire est nécessaire.")
        self.assertEqual(project.workflow_stage_id.code, 'qualified')

    def test_evaluation_now_has_five_exits(self):
        """Trois décisions plus deux demandes — cinq transitions, aucun `if`."""
        project = self._in_evaluation()
        options = project.workflow_instance_id.transition_options(
            user=self.comite)
        codes = {option['transition'].code for option in options}
        self.assertEqual(codes, {
            'accept', 'adjourn', 'reject',
            'committee_ask_info', 'committee_new_evaluation',
        })

    # ------------------------------------------------------------
    # ⚠ Une remédiation sans point ne part pas
    # ------------------------------------------------------------

    def test_a_remediation_without_a_point_is_refused(self):
        """« Le cluster ne dit pas *améliorez votre projet*. »"""
        project = self._in_evaluation()
        with self.assertRaises(UserError) as error:
            self.Remediation.sudo().create({'project_id': project.id})
        self.assertIn("au moins un point", str(error.exception))

    def test_emptying_the_points_afterwards_is_refused_too(self):
        """La contrainte est sur le modèle, pas seulement à la création."""
        project = self._in_evaluation()
        remediation = project.request_remediation(
            self.Point.search([('code', '=', 'etude_marche')]).ids)
        with self.assertRaises(UserError):
            remediation.sudo().point_ids = [(5, 0, 0)]

    def test_the_seeded_points_cover_the_specification(self):
        codes = set(self.Point.search([]).mapped('code'))
        for expected in ('etude_marche', 'modele_economique', 'preuve_concept',
                         'besoin_financement', 'probleme_besoin', 'solution',
                         'prototype', 'faisabilite', 'equipe', 'marche'):
            self.assertIn(expected, codes)

    def test_a_remediation_records_what_must_be_corrected(self):
        project = self._in_evaluation()
        points = self.Point.search(
            [('code', 'in', ['modele_economique', 'preuve_concept'])])
        remediation = project.request_remediation(
            points.ids, commentaire="Le modèle économique reste flou.")

        self.assertEqual(remediation.point_ids, points)
        self.assertIn("flou", remediation.commentaire_comite)
        self.assertFalse(remediation.resolved)
        self.assertEqual(project.pending_remediation_id, remediation)

    # ------------------------------------------------------------
    # Le tour complet de la boucle
    # ------------------------------------------------------------

    def _adjourned(self):
        project = self._in_evaluation()
        points = self.Point.search(
            [('code', 'in', ['modele_economique', 'preuve_concept'])])
        remediation = project.request_remediation(
            points.ids, commentaire="Le modèle économique reste flou.")
        project.with_user(self.comite).workflow_do_transition(
            self._transition(project, 'adjourn'),
            comment="Projet prometteur mais à retravailler.")
        return project, remediation

    def test_adjourning_moves_to_remediation(self):
        project, _remediation = self._adjourned()
        self.assertEqual(project.workflow_stage_id.code, 'remediation')
        self.assertEqual(
            project.workflow_stage_label, "Améliorations demandées")

    def test_the_holder_sees_the_points_in_clear(self):
        project, _remediation = self._adjourned()
        self.authenticate('rm_porteur', 'rm_porteur')
        body = self.url_open(
            '/my/innovation/%s/remediation' % project.id).text

        self.assertIn("Détailler le modèle économique", body)
        self.assertIn("Ajouter une preuve de concept", body)
        self.assertIn("Le modèle économique reste flou.", body)
        # …et pas les points qu'on ne lui demande pas.
        self.assertNotIn("Renforcer l'équipe", body)

    def test_the_holder_corrects_and_resubmits(self):
        project, remediation = self._adjourned()
        self.authenticate('rm_porteur', 'rm_porteur')

        # Il corrige…
        self._post('/my/innovation/%s/marche' % project.id, {
            'marche_cible': "Industriels algériens",
            'modele_economique': 'abonnement',
        })
        # …puis resoumet.
        self._post('/my/innovation/%s/remediation' % project.id, {
            'reponse': "Le modèle économique est maintenant détaillé."})

        project.invalidate_recordset()
        self.assertEqual(project.workflow_stage_id.code, 'resubmitted')
        remediation.invalidate_recordset()
        self.assertTrue(remediation.resolved)
        self.assertIn("détaillé", remediation.reponse_porteur)

    def test_the_full_loop_returns_to_evaluation(self):
        """Le tour complet : évaluation → ajourné → remédiation → resoumis →
        évaluation."""
        project, _remediation = self._adjourned()
        project.with_user(self.porteur).workflow_do_transition(
            self._transition(project, 'resubmit_after_remediation'))
        self.assertEqual(project.workflow_stage_id.code, 'resubmitted')

        project.with_user(self.comite).workflow_do_transition(
            self._transition(project, 'reevaluate'))
        self.assertEqual(project.workflow_stage_id.code, 'evaluation')

        # L'historique porte les deux passages.
        visited = [
            entry.to_stage_id.code
            for entry in project.workflow_instance_id.history_ids
        ]
        self.assertEqual(visited.count('evaluation'), 2)

    # ------------------------------------------------------------
    # ⚠ Historique des versions conservé
    # ------------------------------------------------------------

    def test_resubmission_archives_the_previous_version(self):
        project, remediation = self._adjourned()
        self.assertEqual(project.current_version, 1)
        self.assertFalse(project.version_ids)

        self.authenticate('rm_porteur', 'rm_porteur')
        self._post('/my/innovation/%s/remediation' % project.id, {
            'reponse': "Corrections apportées."})

        project.invalidate_recordset()
        self.assertEqual(len(project.version_ids), 1)
        self.assertEqual(project.current_version, 2)

        snapshot = project.version_ids
        self.assertEqual(snapshot.version, 1)
        self.assertEqual(snapshot.remediation_id, remediation)
        self.assertIn("Corrections apportées.", snapshot.reponse_porteur)

    def test_the_archive_keeps_the_dossier_as_it_was(self):
        """⚠ Le point de la section 18 : l'ancienne version reste consultable.

        L'archive est une **copie figée**, pas un lien : elle ne suit pas les
        modifications ultérieures du projet. C'est tout son intérêt.
        """
        project, _remediation = self._adjourned()
        self.assertEqual(project.resume, "Version initiale du résumé.")

        project.snapshot_version()

        # Le porteur réécrit son dossier…
        project.sudo().resume = "Version entièrement réécrite."
        snapshot = project.version_ids[0]

        # …et l'archive garde l'ancien texte.
        self.assertEqual(snapshot.resume, "Version initiale du résumé.")
        self.assertEqual(project.resume, "Version entièrement réécrite.")

    def test_an_archived_version_cannot_be_rewritten(self):
        project, _remediation = self._adjourned()
        project.snapshot_version()
        snapshot = project.version_ids[0]

        with self.assertRaises(UserError) as error:
            snapshot.with_user(self.comite).write({'resume': "Réécriture"})
        self.assertIn("ne peut pas être modifiée", str(error.exception))

    def test_two_loops_produce_two_versions(self):
        project, _remediation = self._adjourned()

        # Premier tour.
        project.snapshot_version(remediation=project.pending_remediation_id)
        project.with_user(self.porteur).workflow_do_transition(
            self._transition(project, 'resubmit_after_remediation'))
        project.with_user(self.comite).workflow_do_transition(
            self._transition(project, 'reevaluate'))

        # Second ajournement.
        points = self.Point.search([('code', '=', 'equipe')])
        project.request_remediation(points.ids, commentaire="Équipe à renforcer.")
        project.with_user(self.comite).workflow_do_transition(
            self._transition(project, 'adjourn'), comment="Second tour.")
        project.snapshot_version(remediation=project.pending_remediation_id)

        project.invalidate_recordset()
        self.assertEqual(len(project.version_ids), 2)
        self.assertEqual(
            sorted(project.version_ids.mapped('version')), [1, 2])
        self.assertEqual(project.current_version, 3)

    def test_the_holder_sees_his_previous_versions(self):
        project, _remediation = self._adjourned()
        project.snapshot_version(remediation=project.pending_remediation_id)
        project.with_user(self.porteur).workflow_do_transition(
            self._transition(project, 'resubmit_after_remediation'))
        project.with_user(self.comite).workflow_do_transition(
            self._transition(project, 'reevaluate'))

        points = self.Point.search([('code', '=', 'equipe')])
        project.request_remediation(points.ids)
        project.with_user(self.comite).workflow_do_transition(
            self._transition(project, 'adjourn'), comment="Second tour.")

        self.authenticate('rm_porteur', 'rm_porteur')
        body = self.url_open(
            '/my/innovation/%s/remediation' % project.id).text
        self.assertIn("Versions précédentes", body)
