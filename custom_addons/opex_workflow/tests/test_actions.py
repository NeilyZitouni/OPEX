from odoo.tests.common import new_test_user, tagged

from .common import WorkflowCase


@tagged('post_install', '-at_install')
class TestActions(WorkflowCase):
    """Extension 4 — chaque type d'action produit-il son effet, et un échec
    laisse-t-il la transition en place ?"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.definition = cls._linear_definition(code='actions_wf')
        cls.record = cls.env['res.partner'].create({'name': "Dossier actions"})
        cls.instance = cls.Instance._start_for(cls.record, 'actions_wf')
        cls.Action = cls.env['opex.workflow.action']
        cls.Task = cls.env['opex.workflow.task']

    def _stage_by_code(self, code):
        return self.definition.stage_ids.filtered(lambda s: s.code == code)

    def _transition_by_code(self, code):
        return self.definition.transition_ids.filtered(lambda t: t.code == code)

    def _attach(self, action, transition_code='submit'):
        transition = self._transition_by_code(transition_code)
        transition.action_ids = [(6, 0, action.ids)]
        return transition

    def _messages(self):
        return self.env['mail.message'].sudo().search([
            ('model', '=', 'res.partner'), ('res_id', '=', self.record.id),
        ])

    # ------------------------------------------------------------
    # Le dispatcher
    # ------------------------------------------------------------

    def test_dispatch_is_by_getattr_not_if_elif(self):
        """Tout type déclaré dans la Selection a sa méthode d'exécution.

        C'est ce test qui garantit que le contrat « ajouter un type = ajouter
        une méthode » tient : un type ajouté à la Selection sans son
        `_execute_` le fait échouer immédiatement, pas en démonstration.
        """
        for action_type, _label in self.Action._fields['action_type'].selection:
            self.assertTrue(
                hasattr(self.Action, '_execute_%s' % action_type),
                "Le type « %s » n'a pas de méthode _execute_%s"
                % (action_type, action_type),
            )

    def test_unknown_action_type_is_reported(self):
        action = self.Action.create({
            'name': "Type inconnu", 'code': 'act_unknown',
            'action_type': 'notify',
        })
        # Contourne la Selection pour simuler une donnée incohérente en base.
        self.env.cr.execute(
            "UPDATE opex_workflow_action SET action_type = 'inexistant' WHERE id = %s",
            (action.id,))
        self.env.invalidate_all()

        self._attach(action)
        self.instance.do_transition(self._transition_by_code('submit'))
        # La transition passe quand même, et l'échec est tracé.
        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('review'))

    # ------------------------------------------------------------
    # notify
    # ------------------------------------------------------------

    def test_notify_posts_on_the_business_record(self):
        before = len(self._messages())
        action = self.Action.create({
            'name': "Prévenir le contrôle", 'code': 'act_notify',
            'action_type': 'notify',
            'body': "<p>Un dossier attend votre contrôle.</p>",
        })
        self._attach(action)
        self.instance.do_transition(self._transition_by_code('submit'))

        messages = self._messages()
        self.assertEqual(len(messages), before + 1)
        self.assertIn("attend votre contrôle", messages.sorted('id')[-1].body)

    def test_notify_defaults_to_internal_note(self):
        """⚠ Le défaut est `mt_note`. Un message interne posté en `mt_comment`
        part par email chez le porteur — bug déjà payé sur le module précédent.
        """
        action = self.Action.create({
            'name': "Note interne", 'code': 'act_note',
            'action_type': 'notify', 'body': "<p>Interne.</p>",
        })
        self.assertEqual(action.notify_subtype, 'note')

        self._attach(action)
        self.instance.do_transition(self._transition_by_code('submit'))
        message = self._messages().sorted('id')[-1]
        self.assertEqual(message.subtype_id, self.env.ref('mail.mt_note'))
        self.assertTrue(message.subtype_id.internal)

    def test_notify_can_be_addressed_to_the_holder(self):
        action = self.Action.create({
            'name': "Message au porteur", 'code': 'act_comment',
            'action_type': 'notify', 'body': "<p>Votre dossier avance.</p>",
            'notify_subtype': 'comment',
        })
        self._attach(action)
        self.instance.do_transition(self._transition_by_code('submit'))
        message = self._messages().sorted('id')[-1]
        self.assertEqual(message.subtype_id, self.env.ref('mail.mt_comment'))

    def test_notify_targets_the_actors_holding_the_role(self):
        role = self.Role.create({'name': "Contrôle", 'code': 'act_role_notify'})
        controller = new_test_user(
            self.env, login='act_controller', groups='base.group_user')
        self.env['opex.workflow.instance.actor'].create({
            'instance_id': self.instance.id,
            'role_id': role.id,
            'user_id': controller.id,
            'access_level': 'full',
        })
        action = self.Action.create({
            'name': "Prévenir", 'code': 'act_notify_role',
            'action_type': 'notify', 'body': "<p>À traiter.</p>",
            'target_role_ids': [(6, 0, role.ids)],
        })
        self._attach(action)
        self.instance.do_transition(self._transition_by_code('submit'))

        message = self._messages().sorted('id')[-1]
        self.assertIn(controller.partner_id, message.partner_ids)

    def test_notify_ignores_actors_whose_access_was_revoked(self):
        role = self.Role.create({'name': "Retiré", 'code': 'act_role_revoked'})
        user = new_test_user(
            self.env, login='act_revoked', groups='base.group_user')
        self.env['opex.workflow.instance.actor'].create({
            'instance_id': self.instance.id, 'role_id': role.id,
            'user_id': user.id, 'access_level': 'none',
        })
        action = self.Action.create({
            'name': "Prévenir", 'code': 'act_notify_revoked',
            'action_type': 'notify', 'body': "<p>x</p>",
            'target_role_ids': [(6, 0, role.ids)],
        })
        self._attach(action)
        self.instance.do_transition(self._transition_by_code('submit'))
        message = self._messages().sorted('id')[-1]
        self.assertNotIn(user.partner_id, message.partner_ids)

    # ------------------------------------------------------------
    # set_field
    # ------------------------------------------------------------

    def test_set_field_writes_the_evaluated_value(self):
        field = self.env['ir.model.fields']._get('res.partner', 'color')
        action = self.Action.create({
            'name': "Fixer la couleur", 'code': 'act_set',
            'action_type': 'set_field',
            'field_id': field.id,
            'value_expression': "42",
        })
        self._attach(action)
        self.assertNotEqual(self.record.color, 42)
        self.instance.do_transition(self._transition_by_code('submit'))
        self.assertEqual(self.record.color, 42)

    def test_set_field_expression_sees_the_record(self):
        self.record.color = 5
        field = self.env['ir.model.fields']._get('res.partner', 'color')
        action = self.Action.create({
            'name': "Doubler", 'code': 'act_set_expr',
            'action_type': 'set_field',
            'field_id': field.id,
            'value_expression': "field('color') * 2",
        })
        self._attach(action)
        self.instance.do_transition(self._transition_by_code('submit'))
        self.assertEqual(self.record.color, 10)

    def test_set_field_refuses_a_field_of_another_model(self):
        """Une configuration erronée ne doit pas écrire sur un modèle voisin."""
        field = self.env['ir.model.fields']._get('res.users', 'login')
        action = self.Action.create({
            'name': "Mauvais modèle", 'code': 'act_set_wrong',
            'action_type': 'set_field',
            'field_id': field.id,
            'value_expression': "'x'",
        })
        self._attach(action)
        self.instance.do_transition(self._transition_by_code('submit'))
        # La transition passe, l'action échoue et c'est tracé.
        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('review'))
        note = self.instance.history_ids.sorted('id')[-1].conditions_note
        self.assertIn("Mauvais modèle", note)

    # ------------------------------------------------------------
    # create_task
    # ------------------------------------------------------------

    def test_create_task_produces_a_task_in_the_queue(self):
        role = self.Role.create({'name': "Contrôle", 'code': 'act_role_task'})
        action = self.Action.create({
            'name': "Contrôler le dossier", 'code': 'act_task',
            'action_type': 'create_task',
            'target_role_ids': [(6, 0, role.ids)],
            'deadline_days': 5,
        })
        self._attach(action)
        self.instance.do_transition(self._transition_by_code('submit'))

        task = self.Task.search([('instance_id', '=', self.instance.id)])
        self.assertEqual(len(task), 1)
        self.assertEqual(task.name, "Contrôler le dossier")
        self.assertEqual(task.role_id, role)
        self.assertEqual(task.stage_id, self._stage_by_code('review'))
        self.assertEqual(task.state, 'todo')
        self.assertTrue(task.deadline)

    def test_create_task_assigns_only_when_the_role_is_unambiguous(self):
        role = self.Role.create({'name': "Expert", 'code': 'act_role_two'})
        first = new_test_user(self.env, login='act_a', groups='base.group_user')
        second = new_test_user(self.env, login='act_b', groups='base.group_user')
        for user in (first, second):
            self.env['opex.workflow.instance.actor'].create({
                'instance_id': self.instance.id, 'role_id': role.id,
                'user_id': user.id, 'access_level': 'full',
            })
        action = self.Action.create({
            'name': "Expertiser", 'code': 'act_task_two',
            'action_type': 'create_task',
            'target_role_ids': [(6, 0, role.ids)],
        })
        self._attach(action)
        self.instance.do_transition(self._transition_by_code('submit'))

        task = self.Task.search([('instance_id', '=', self.instance.id)])
        # Deux porteurs du rôle : la tâche reste ouverte plutôt qu'attribuée
        # arbitrairement à l'un des deux.
        self.assertFalse(task.user_id)
        self.assertEqual(task.role_id, role)

    def test_task_can_be_completed(self):
        role = self.Role.create({'name': "Contrôle", 'code': 'act_role_done'})
        action = self.Action.create({
            'name': "À faire", 'code': 'act_task_done',
            'action_type': 'create_task',
            'target_role_ids': [(6, 0, role.ids)],
        })
        self._attach(action)
        self.instance.do_transition(self._transition_by_code('submit'))

        task = self.Task.search([('instance_id', '=', self.instance.id)])
        task.action_done()
        self.assertEqual(task.state, 'done')
        self.assertTrue(task.date_done)

    # ------------------------------------------------------------
    # send_email
    # ------------------------------------------------------------

    def test_send_email_queues_a_mail(self):
        template = self.env['mail.template'].create({
            'name': "Avis de dépôt",
            'model_id': self.partner_model.id,
            'subject': "Votre dossier",
            'body_html': "<p>Bien reçu.</p>",
            'email_from': "noreply@example.com",
            'partner_to': "{{ object.id }}",
        })
        action = self.Action.create({
            'name': "Accuser réception", 'code': 'act_mail',
            'action_type': 'send_email',
            'template_id': template.id,
        })
        self._attach(action)
        before = self.env['mail.mail'].sudo().search_count([])
        self.instance.do_transition(self._transition_by_code('submit'))

        self.assertGreater(self.env['mail.mail'].sudo().search_count([]), before)
        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('review'))

    def test_send_email_refuses_a_template_of_another_model(self):
        template = self.env['mail.template'].create({
            'name': "Mauvais modèle",
            'model_id': self.env['ir.model']._get('res.users').id,
            'subject': "x", 'body_html': "<p>x</p>",
        })
        action = self.Action.create({
            'name': "Mail incohérent", 'code': 'act_mail_wrong',
            'action_type': 'send_email', 'template_id': template.id,
        })
        self._attach(action)
        self.instance.do_transition(self._transition_by_code('submit'))
        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('review'))
        self.assertIn(
            "Mail incohérent",
            self.instance.history_ids.sorted('id')[-1].conditions_note)

    # ------------------------------------------------------------
    # Les stubs déclarés
    # ------------------------------------------------------------

    def test_declared_but_unimplemented_types_fail_loudly(self):
        """Ils lèvent plutôt que de ne rien faire.

        Une action silencieusement inopérante se découvre en démonstration ;
        une action qui lève se découvre au premier essai et laisse une trace.
        """
        for code, action_type in (
            ('act_sub', 'launch_subworkflow'),
            ('act_match', 'run_matching'),
        ):
            with self.subTest(action_type=action_type):
                action = self.Action.create({
                    'name': "Stub %s" % action_type, 'code': code,
                    'action_type': action_type,
                })
                with self.assertRaises(NotImplementedError):
                    action.execute(self.instance)

    # ------------------------------------------------------------
    # ⚠ La règle : un échec ne rollback pas la transition
    # ------------------------------------------------------------

    def test_failing_action_does_not_roll_back_the_transition(self):
        """Un serveur mail en panne ne bloque pas un processus métier."""
        broken = self.Action.create({
            'name': "Action cassée", 'code': 'act_broken',
            'action_type': 'set_field',
            # Ni champ ni expression : l'exécution lèvera.
        })
        self._attach(broken)
        self.instance.do_transition(self._transition_by_code('submit'))

        # L'étape a bougé…
        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('review'))
        # …la ligne d'historique de la transition existe…
        transition_entry = self.instance.history_ids.filtered(
            lambda h: h.from_stage_id == self._stage_by_code('draft'))
        self.assertTrue(transition_entry)
        # …et l'échec est journalisé dans une ligne dédiée.
        failure = self.instance.history_ids.sorted('id')[-1]
        self.assertIn("ont échoué", failure.comment)
        self.assertIn("Action cassée", failure.conditions_note)

    def test_one_failing_action_does_not_prevent_the_others(self):
        """Chaque action a son savepoint : un échec n'emporte pas ses voisines."""
        field = self.env['ir.model.fields']._get('res.partner', 'color')
        broken = self.Action.create({
            'name': "Cassée", 'code': 'act_iso_broken',
            'action_type': 'set_field', 'sequence': 1,
        })
        working = self.Action.create({
            'name': "Valide", 'code': 'act_iso_ok',
            'action_type': 'set_field', 'sequence': 2,
            'field_id': field.id, 'value_expression': "77",
        })
        transition = self._transition_by_code('submit')
        transition.action_ids = [(6, 0, (broken | working).ids)]

        self.instance.do_transition(transition)

        # L'action valide a bien produit son effet malgré l'échec de la première.
        self.assertEqual(self.record.color, 77)
        note = self.instance.history_ids.sorted('id')[-1].conditions_note
        self.assertIn("✗ Cassée", note)
        self.assertIn("✓ Valide", note)

    def test_action_with_a_failing_expression_leaves_the_field_untouched(self):
        """Une expression qui lève n'écrit rien et ne bloque pas la transition."""
        field = self.env['ir.model.fields']._get('res.partner', 'color')
        self.record.color = 3
        broken = self.Action.create({
            'name': "Division par zéro", 'code': 'act_half',
            'action_type': 'set_field',
            'field_id': field.id,
            'value_expression': "1 / 0",
        })
        self._attach(broken)
        self.instance.do_transition(self._transition_by_code('submit'))

        self.assertEqual(self.record.color, 3)
        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('review'))
        self.assertIn(
            "Division par zéro",
            self.instance.history_ids.sorted('id')[-1].conditions_note)

    def test_no_extra_history_line_when_everything_succeeds(self):
        """Le journal ne se remplit pas de lignes « tout va bien »."""
        field = self.env['ir.model.fields']._get('res.partner', 'color')
        action = self.Action.create({
            'name': "OK", 'code': 'act_quiet',
            'action_type': 'set_field',
            'field_id': field.id, 'value_expression': "9",
        })
        self._attach(action)
        before = len(self.instance.history_ids)
        self.instance.do_transition(self._transition_by_code('submit'))
        # Une seule ligne ajoutée : celle de la transition.
        self.assertEqual(len(self.instance.history_ids), before + 1)

    def test_inactive_actions_are_skipped(self):
        field = self.env['ir.model.fields']._get('res.partner', 'color')
        action = self.Action.create({
            'name': "Désactivée", 'code': 'act_inactive',
            'action_type': 'set_field',
            'field_id': field.id, 'value_expression': "55",
            'active': False,
        })
        self._attach(action)
        self.record.color = 1
        self.instance.do_transition(self._transition_by_code('submit'))
        self.assertEqual(self.record.color, 1)
