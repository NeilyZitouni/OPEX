from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import new_test_user, tagged

from .common import WorkflowCase


@tagged('post_install', '-at_install')
class TestTransverse(WorkflowCase):
    """Extension 8 — sous-workflows, SLA, portail générique."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.main = cls._linear_definition(code='trans_main')
        cls.record = cls.env['res.partner'].create({'name': "Dossier transverse"})
        cls.instance = cls.Instance._start_for(cls.record, 'trans_main')

        # Un sous-processus court, réutilisable : deux étapes, une transition.
        cls.sub = cls._definition(code='trans_sub', name="Accompagnement")
        cls.sub_start = cls._stage(cls.sub, 'ouvert', "Ouvert", is_start=True,
                                   user_label="Accompagnement en cours")
        cls.sub_end = cls._stage(cls.sub, 'clos', "Clos", is_end=True,
                                 sequence=20, user_label="Accompagnement terminé")
        cls.sub_transition = cls._transition(
            cls.sub, 'cloturer', cls.sub_start, cls.sub_end, "Clôturer")
        cls.sub.action_publish()

    def _stage_by_code(self, code):
        return self.main.stage_ids.filtered(lambda s: s.code == code)

    def _transition_by_code(self, code):
        return self.main.transition_ids.filtered(lambda t: t.code == code)

    # ------------------------------------------------------------
    # Sous-workflows
    # ------------------------------------------------------------

    def test_subworkflow_starts_on_the_same_record(self):
        child = self.instance.start_subworkflow('trans_sub')

        self.assertEqual(child.res_model, self.instance.res_model)
        self.assertEqual(child.res_id, self.instance.res_id)
        self.assertEqual(child.definition_id, self.sub)
        self.assertEqual(child.current_stage_id, self.sub_start)
        self.assertEqual(child.parent_instance_id, self.instance)
        self.assertIn(child, self.instance.child_instance_ids)

    def test_subworkflow_has_its_own_life(self):
        """Il ne fait pas avancer le parent : ce sont deux processus."""
        child = self.instance.start_subworkflow('trans_sub')
        stage_before = self.instance.current_stage_id

        child.do_transition(self.sub_transition)

        self.assertEqual(child.state, 'done')
        self.assertEqual(self.instance.current_stage_id, stage_before)
        self.assertEqual(self.instance.state, 'running')

    def test_subworkflow_cannot_be_started_twice(self):
        self.instance.start_subworkflow('trans_sub')
        with self.assertRaises(UserError) as error:
            self.instance.start_subworkflow('trans_sub')
        self.assertIn("déjà en cours", str(error.exception))

    def test_subworkflow_can_be_restarted_once_finished(self):
        child = self.instance.start_subworkflow('trans_sub')
        child.do_transition(self.sub_transition)
        # Terminé, il ne bloque plus un second passage — la réévaluation d'un
        # accompagnement est un cas prévu par les documents sources.
        self.assertTrue(self.instance.start_subworkflow('trans_sub'))

    # ------------------------------------------------------------
    # subworkflow_done()
    # ------------------------------------------------------------

    def test_subworkflow_done_answers_correctly(self):
        self.assertFalse(self.instance._subworkflow_done('trans_sub'))

        child = self.instance.start_subworkflow('trans_sub')
        # Démarré mais pas fini : toujours faux.
        self.assertFalse(self.instance._subworkflow_done('trans_sub'))

        child.do_transition(self.sub_transition)
        self.assertTrue(self.instance._subworkflow_done('trans_sub'))

    def test_subworkflow_done_is_tolerant_to_unknown_codes(self):
        self.assertFalse(self.instance._subworkflow_done('inexistant'))

    def test_subworkflow_done_gates_a_transition(self):
        """Le cas d'usage : une étape attend la fin d'un sous-processus."""
        rule = self._rule(
            'accompagnement_fini',
            "subworkflow_done('trans_sub')",
            message="L'accompagnement doit être terminé.",
        )
        submit = self._transition_by_code('submit')
        submit.condition_ids = [(6, 0, rule.ids)]

        with self.assertRaises(UserError) as error:
            self.instance.do_transition(submit)
        self.assertIn("accompagnement doit être terminé", str(error.exception).lower())

        child = self.instance.start_subworkflow('trans_sub')
        child.do_transition(self.sub_transition)

        self.instance.do_transition(submit)
        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('review'))

    def test_launch_subworkflow_action_no_longer_raises(self):
        action = self.env['opex.workflow.action'].create({
            'name': "Lancer l'accompagnement", 'code': 'act_sub_ok',
            'action_type': 'launch_subworkflow',
            'sub_definition_id': self.sub.id,
        })
        detail = action.execute(self.instance)
        self.assertIn("Accompagnement", detail)
        self.assertTrue(self.instance.child_instance_ids)

    def test_launch_subworkflow_without_target_is_reported(self):
        action = self.env['opex.workflow.action'].create({
            'name': "Sans cible", 'code': 'act_sub_empty',
            'action_type': 'launch_subworkflow',
        })
        with self.assertRaises(UserError):
            action.execute(self.instance)

    # ------------------------------------------------------------
    # SLA
    # ------------------------------------------------------------

    def _make_late(self, days=5):
        """Recule l'entrée dans l'étape pour dépasser le délai."""
        self._stage_by_code('draft').sla_days = 2
        self.instance.sudo().write({
            'date_stage_start': fields.Datetime.now() - timedelta(days=days),
        })

    def test_sla_deadline_follows_the_stage(self):
        self._stage_by_code('draft').sla_days = 3
        self.instance.sudo().date_stage_start = fields.Datetime.now()
        self.assertTrue(self.instance.sla_deadline)

        # Une étape sans délai n'a pas d'échéance.
        self._stage_by_code('draft').sla_days = 0
        self.assertFalse(self.instance.sla_deadline)

    def test_cron_marks_late_instances(self):
        self._make_late()
        self.assertFalse(self.instance.is_late)

        self.Instance._cron_check_sla()

        self.assertTrue(self.instance.is_late)

    def test_cron_leaves_on_time_instances_alone(self):
        self._stage_by_code('draft').sla_days = 30
        self.instance.sudo().date_stage_start = fields.Datetime.now()
        self.Instance._cron_check_sla()
        self.assertFalse(self.instance.is_late)

    def test_cron_clears_the_flag_when_the_delay_no_longer_applies(self):
        self._make_late()
        self.Instance._cron_check_sla()
        self.assertTrue(self.instance.is_late)

        # Le délai est rallongé : le dossier n'est plus en retard.
        self._stage_by_code('draft').sla_days = 90
        self.Instance._cron_check_sla()
        self.assertFalse(self.instance.is_late)

    def test_transition_clears_the_late_flag(self):
        """Changer d'étape remet le compteur à zéro."""
        self._make_late()
        self.Instance._cron_check_sla()
        self.assertTrue(self.instance.is_late)

        self.instance.do_transition(self._transition_by_code('submit'))

        self.assertFalse(self.instance.is_late)
        self.assertFalse(self.instance.sla_notified_stage_id)

    def test_cron_notifies_the_expected_role_once_per_stage(self):
        role = self.Role.create({'name': "Secrétariat", 'code': 'trans_secr'})
        user = new_test_user(
            self.env, login='trans_secr_user', groups='base.group_user')
        self.instance.add_actor(role, user, 'full')
        self._stage_by_code('draft').actor_role_ids = [(6, 0, role.ids)]
        self._make_late()

        Message = self.env['mail.message'].sudo()
        domain = [('model', '=', 'res.partner'), ('res_id', '=', self.record.id)]
        before = Message.search_count(domain)

        self.Instance._cron_check_sla()
        after_first = Message.search_count(domain)
        self.assertEqual(after_first, before + 1)

        message = Message.search(domain, order='id desc', limit=1)
        self.assertIn(user.partner_id, message.partner_ids)
        # Relance interne : le porteur n'a pas à recevoir un email parce que
        # le secrétariat est en retard.
        self.assertEqual(message.subtype_id, self.env.ref('mail.mt_note'))

        # Deuxième passage du cron : pas de seconde alerte.
        self.Instance._cron_check_sla()
        self.assertEqual(Message.search_count(domain), after_first)

    def test_cron_does_not_touch_closed_instances(self):
        self.instance.do_transition(self._transition_by_code('submit'))
        self.instance.do_transition(self._transition_by_code('validate'))
        self.assertEqual(self.instance.state, 'done')

        self._stage_by_code('done').sla_days = 1
        self.instance.sudo().date_stage_start = fields.Datetime.now() - timedelta(days=9)
        self.Instance._cron_check_sla()
        self.assertFalse(self.instance.is_late)

    # ------------------------------------------------------------
    # Portail générique
    # ------------------------------------------------------------

    def test_progress_steps_use_the_user_label(self):
        steps = self.instance.progress_steps()
        labels = [step['label'] for step in steps]
        self.assertIn("Compléter mon dossier", labels)
        # Aucun code technique n'est exposé.
        self.assertNotIn('draft', labels)
        self.assertNotIn('review', labels)

    def test_progress_marks_done_current_and_upcoming(self):
        self.instance.do_transition(self._transition_by_code('submit'))
        by_code = {
            step['stage'].code: step['state']
            for step in self.instance.progress_steps()
        }
        self.assertEqual(by_code['draft'], 'done')
        self.assertEqual(by_code['review'], 'current')
        self.assertEqual(by_code['done'], 'upcoming')

    def test_progress_reads_history_not_sequence(self):
        """Le processus est un graphe, pas une file.

        « Refusé » porte une séquence supérieure à « Clôturé » sans être sur le
        chemin parcouru : le déduire d'un numéro d'ordre mentirait.
        """
        self.instance.do_transition(self._transition_by_code('submit'))
        self.instance.do_transition(
            self._transition_by_code('reject'), comment="Hors périmètre.")
        by_code = {
            step['stage'].code: step['state']
            for step in self.instance.progress_steps()
        }
        self.assertEqual(by_code['rejected'], 'current')
        self.assertEqual(by_code['done'], 'upcoming')

    def test_next_action_label_is_written_for_a_reader(self):
        label = self.instance.next_action_label()
        self.assertIn("Soumettre", label)
        self.assertNotIn('submit', label)

    def test_next_action_label_explains_a_blockage(self):
        rule = self._rule(
            'attente', "False", message="Le dossier attend une pièce.")
        self._transition_by_code('submit').condition_ids = [(6, 0, rule.ids)]
        self.assertIn("attend une pièce", self.instance.next_action_label())

    def test_next_action_label_on_a_closed_file(self):
        self.instance.do_transition(self._transition_by_code('submit'))
        self.instance.do_transition(self._transition_by_code('validate'))
        self.assertIn("clôturé", self.instance.next_action_label().lower())

    def test_portal_progress_template_renders_labels_not_codes(self):
        html = str(self.env['ir.qweb']._render(
            'opex_workflow.workflow_portal_progress',
            {'instance': self.instance},
        ))
        self.assertIn("Compléter mon dossier", html)
        self.assertIn("Soumettre", html)
        # Le gabarit ne doit laisser filtrer aucun code d'étape.
        self.assertNotIn('>draft<', html)
        self.assertNotIn('>review<', html)
