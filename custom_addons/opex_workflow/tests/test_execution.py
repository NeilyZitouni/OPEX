from odoo.exceptions import UserError
from odoo.tests.common import new_test_user, tagged

from .common import WorkflowCase


@tagged('post_install', '-at_install')
class TestExecution(WorkflowCase):
    """Extension 2 — un enregistrement avance-t-il réellement, et sous contrôle ?

    Tous les tests tournent sur `res.partner`, modèle natif que le moteur n'a
    jamais vu : le moteur pilote un modèle qui n'hérite même pas du mixin.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.definition = cls._linear_definition(code='exec_wf')
        cls.record = cls.env['res.partner'].create({'name': "Dossier de test"})
        cls.instance = cls.Instance._start_for(cls.record, 'exec_wf')

    def _stage_by_code(self, code):
        return self.definition.stage_ids.filtered(lambda s: s.code == code)

    def _transition_by_code(self, code):
        return self.definition.transition_ids.filtered(lambda t: t.code == code)

    # ------------------------------------------------------------
    # 1. Transition nominale
    # ------------------------------------------------------------

    def test_start_places_record_on_start_stage(self):
        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('draft'))
        self.assertEqual(self.instance.state, 'running')
        self.assertEqual(self.instance.res_model, 'res.partner')
        self.assertEqual(self.instance.res_id, self.record.id)
        self.assertEqual(self.instance._get_record(), self.record)

        # Le journal s'ouvre sur l'entrée dans le processus, pas sur la
        # deuxième étape.
        self.assertEqual(len(self.instance.history_ids), 1)
        entry = self.instance.history_ids
        self.assertFalse(entry.from_stage_id)
        self.assertEqual(entry.to_stage_id, self._stage_by_code('draft'))

    def test_nominal_transition(self):
        submit = self._transition_by_code('submit')
        self.instance.do_transition(submit)

        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('review'))
        self.assertEqual(self.instance.state, 'running')
        self.assertEqual(len(self.instance.history_ids), 2)

        entry = self.instance.history_ids.filtered(lambda h: h.transition_id == submit)
        self.assertEqual(entry.from_stage_id, self._stage_by_code('draft'))
        self.assertEqual(entry.to_stage_id, self._stage_by_code('review'))
        self.assertEqual(entry.user_id, self.env.user)
        self.assertFalse(entry.forced)

    def test_reaching_end_stage_closes_instance(self):
        self.instance.do_transition(self._transition_by_code('submit'))
        self.instance.do_transition(self._transition_by_code('validate'))

        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('done'))
        self.assertEqual(self.instance.state, 'done')
        self.assertTrue(self.instance.date_end)

        # Un dossier clos n'accepte plus rien.
        self.assertFalse(self.instance.available_transitions())
        with self.assertRaises(UserError):
            self.instance.do_transition(self._transition_by_code('validate'))

    def test_transition_from_wrong_stage_refused(self):
        """« Valider » part de Contrôle : elle est impossible depuis Brouillon."""
        with self.assertRaises(UserError) as error:
            self.instance.do_transition(self._transition_by_code('validate'))
        self.assertIn("Brouillon", str(error.exception))

    def test_available_transitions_lists_all_outgoing(self):
        self.instance.do_transition(self._transition_by_code('submit'))
        codes = set(self.instance.available_transitions().mapped('code'))
        # Deux sorties depuis « Contrôle » : le moteur ne suppose jamais qu'une
        # étape n'en a qu'une.
        self.assertEqual(codes, {'validate', 'reject'})

    def test_required_comment_is_enforced(self):
        self.instance.do_transition(self._transition_by_code('submit'))
        reject = self._transition_by_code('reject')

        with self.assertRaises(UserError) as error:
            self.instance.do_transition(reject)
        self.assertIn("motif", str(error.exception))

        self.instance.do_transition(reject, comment="Dossier hors périmètre.")
        entry = self.instance.history_ids.filtered(lambda h: h.transition_id == reject)
        self.assertEqual(entry.comment, "Dossier hors périmètre.")

    # ------------------------------------------------------------
    # 2. Refusée par rôle
    # ------------------------------------------------------------

    def test_transition_refused_by_role(self):
        """Refus **de rôle**, à ne pas confondre avec un refus d'accès.

        L'utilisateur reçoit une ligne d'acteur, donc l'accès au dossier : sans
        elle, les `ir.rule` de l'Extension 5 lui refuseraient la lecture et le
        test mesurerait la mauvaise chose.

        `invalidate_all()` avant de changer d'utilisateur : le cache de l'ORM
        est **partagé entre environnements** d'une même transaction. Un
        enregistrement déjà lu en administrateur est resservi depuis le cache
        sans repasser par les règles — c'est la version discrète du piège
        « les ir.rule ne se voient pas en admin ».
        """
        role = self.Role.create({
            'name': "Contrôleur",
            'code': 'test_controleur',
            'group_id': self.env.ref('base.group_system').id,
        })
        observer_role = self.Role.create({
            'name': "Observateur", 'code': 'test_observateur'})
        submit = self._transition_by_code('submit')
        submit.allowed_role_ids = [(6, 0, role.ids)]

        outsider = new_test_user(
            self.env, login='wf_outsider', groups='base.group_user')
        self.instance.add_actor(observer_role, outsider, 'limited')

        # Il ne porte pas le rôle : la transition ne lui est pas proposée…
        self.assertNotIn(
            submit, self.instance.available_transitions(user=outsider))
        self.assertFalse(
            self.instance._check_transition_allowed(submit, user=outsider))

        # …et forcer l'appel échoue avec un message qui nomme le rôle attendu.
        self.env.invalidate_all()
        with self.assertRaises(UserError) as error:
            self.instance.with_user(outsider).do_transition(submit)
        self.assertIn("Contrôleur", str(error.exception))

        # L'étape n'a pas bougé.
        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('draft'))

    def test_role_holder_may_transition(self):
        role = self.Role.create({
            'name': "Contrôleur",
            'code': 'test_controleur_ok',
            'group_id': self.env.ref('base.group_system').id,
        })
        submit = self._transition_by_code('submit')
        submit.allowed_role_ids = [(6, 0, role.ids)]

        insider = new_test_user(
            self.env, login='wf_insider',
            groups='base.group_user,base.group_system')
        self.instance.add_actor(role, insider, 'full')

        self.assertIn(submit, self.instance.available_transitions(user=insider))
        self.instance.with_user(insider).do_transition(submit)
        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('review'))

    def test_actor_line_grants_role_on_this_instance_only(self):
        """Le rôle porté par une ligne d'acteur ne vaut que pour ce dossier."""
        role = self.Role.create({'name': "Expert du dossier", 'code': 'test_expert'})
        submit = self._transition_by_code('submit')
        submit.allowed_role_ids = [(6, 0, role.ids)]

        expert = new_test_user(
            self.env, login='wf_expert', groups='base.group_user')

        other_record = self.env['res.partner'].create({'name': "Autre dossier"})
        other_instance = self.Instance._start_for(other_record, 'exec_wf')

        self.env['opex.workflow.instance.actor'].create({
            'instance_id': self.instance.id,
            'role_id': role.id,
            'user_id': expert.id,
            'access_level': 'full',
        })

        self.assertTrue(
            self.instance._check_transition_allowed(submit, user=expert))
        self.assertFalse(
            other_instance._check_transition_allowed(submit, user=expert))

    def test_actor_without_access_does_not_carry_the_role(self):
        role = self.Role.create({'name': "Retiré", 'code': 'test_retire'})
        submit = self._transition_by_code('submit')
        submit.allowed_role_ids = [(6, 0, role.ids)]

        user = new_test_user(self.env, login='wf_revoked', groups='base.group_user')
        self.env['opex.workflow.instance.actor'].create({
            'instance_id': self.instance.id,
            'role_id': role.id,
            'user_id': user.id,
            'access_level': 'none',
        })
        self.assertFalse(
            self.instance._check_transition_allowed(submit, user=user))

    def test_manager_forces_transition_and_it_is_traced(self):
        role = self.Role.create({'name': "Comité", 'code': 'test_comite'})
        submit = self._transition_by_code('submit')
        submit.allowed_role_ids = [(6, 0, role.ids)]

        manager = new_test_user(
            self.env, login='wf_manager',
            groups='base.group_user,opex_workflow.group_workflow_manager')

        self.instance.with_user(manager).do_transition(submit)
        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('review'))

        entry = self.instance.history_ids.filtered(lambda h: h.transition_id == submit)
        # Le contournement est filtrable, pas noyé dans un commentaire.
        self.assertTrue(entry.forced)
        self.assertEqual(entry.user_id, manager)

    # ------------------------------------------------------------
    # 3. Bloquée par condition, puis débloquée
    # ------------------------------------------------------------

    def test_condition_blocks_then_releases(self):
        rule = self._rule(
            'test_color_min',
            "field('color') >= 70",
            message="La note doit atteindre 70.",
        )
        submit = self._transition_by_code('submit')
        submit.condition_ids = [(6, 0, rule.ids)]

        self.record.color = 10
        with self.assertRaises(UserError) as error:
            self.instance.do_transition(submit)
        self.assertIn("La note doit atteindre 70.", str(error.exception))
        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('draft'))

        # ⚠ La transition reste **visible** : elle n'a pas disparu de la liste.
        self.assertIn(submit, self.instance.available_transitions())
        option = self.instance.transition_options()[0]
        self.assertEqual(option['transition'], submit)
        self.assertFalse(option['available'])
        self.assertIn("La note doit atteindre 70.", option['reason'])

        # Le dossier progresse, la transition se débloque.
        self.record.color = 80
        option = self.instance.transition_options()[0]
        self.assertTrue(option['available'])
        self.instance.do_transition(submit)
        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('review'))

    def test_all_failing_conditions_reported_together(self):
        first = self._rule('test_cond_a', "field('color') >= 70", "Note insuffisante.")
        second = self._rule('test_cond_b', "record.is_company", "Doit être une société.")
        submit = self._transition_by_code('submit')
        submit.condition_ids = [(6, 0, (first | second).ids)]

        self.record.write({'color': 0, 'is_company': False})
        with self.assertRaises(UserError) as error:
            self.instance.do_transition(submit)
        message = str(error.exception)
        self.assertIn("Note insuffisante.", message)
        self.assertIn("Doit être une société.", message)

    def test_conditions_note_records_each_result(self):
        passing = self._rule('test_note_ok', "field('color') >= 5", "Trop bas.")
        submit = self._transition_by_code('submit')
        submit.condition_ids = [(6, 0, passing.ids)]
        self.record.color = 9

        self.instance.do_transition(submit)
        entry = self.instance.history_ids.filtered(lambda h: h.transition_id == submit)
        self.assertIn("test_note_ok", entry.conditions_note)
        self.assertIn("✓", entry.conditions_note)

    def test_has_document_is_tolerant_on_a_model_without_documents(self):
        """`res.partner` n'a pas de documents : la condition est fausse, pas
        cassée."""
        rule = self._rule(
            'test_doc', "has_document('un_type_quelconque')", "Pièce manquante.")
        submit = self._transition_by_code('submit')
        submit.condition_ids = [(6, 0, rule.ids)]

        self.assertFalse(self.instance._has_document('un_type_quelconque'))
        with self.assertRaises(UserError) as error:
            self.instance.do_transition(submit)
        self.assertIn("Pièce manquante.", str(error.exception))

    def test_field_helper_tolerates_missing_field(self):
        self.assertEqual(self.instance._field('name'), "Dossier de test")
        self.assertFalse(self.instance._field('champ_qui_nexiste_pas'))
        self.assertEqual(
            self.instance._field('champ_qui_nexiste_pas', default=42), 42)

    # ------------------------------------------------------------
    # 4. Historique immuable
    # ------------------------------------------------------------

    def test_history_cannot_be_written(self):
        entry = self.instance.history_ids[0]
        with self.assertRaises(UserError):
            entry.comment = "réécriture"

    def test_history_cannot_be_deleted(self):
        entry = self.instance.history_ids[0]
        with self.assertRaises(UserError):
            entry.unlink()

    def test_history_is_immutable_even_for_superuser(self):
        """Le point entier du journal d'audit : personne n'y touche.

        `sudo()` élève les droits ; il ne contourne pas une surcharge de
        `write()`. C'est la différence entre un contrôle par ACL — qu'un
        administrateur franchit — et un contrôle par le modèle.
        """
        entry = self.instance.history_ids[0]
        with self.assertRaises(UserError):
            entry.sudo().write({'comment': "réécriture admin"})
        with self.assertRaises(UserError):
            entry.sudo().unlink()
        with self.assertRaises(UserError):
            entry.with_user(self.env.ref('base.user_admin')).write({'comment': "x"})

    # ------------------------------------------------------------
    # 5. Expression invalide qui ne casse rien
    # ------------------------------------------------------------

    def test_invalid_expression_does_not_break_anything(self):
        """Une faute de frappe dans une règle bloque la transition, sans plus.

        Elle ne remonte aucune exception à l'appelant : ni au calcul de la
        liste des actions possibles (donc la page s'affiche), ni au passage de
        la transition (donc l'utilisateur lit le message de la règle, pas une
        trace Python).
        """
        broken = self._rule(
            'test_broken',
            "record.champ_inexistant.methode_inexistante()",
            message="Condition non vérifiable pour le moment.",
        )
        submit = self._transition_by_code('submit')
        submit.condition_ids = [(6, 0, broken.ids)]

        # La liste des actions se calcule sans lever.
        options = self.instance.transition_options()
        self.assertEqual(len(options), 1)
        self.assertFalse(options[0]['available'])
        self.assertIn("Condition non vérifiable", options[0]['reason'])

        # Le passage échoue proprement, avec le message de la règle.
        with self.assertRaises(UserError) as error:
            self.instance.do_transition(submit)
        self.assertIn("Condition non vérifiable pour le moment.", str(error.exception))
        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('draft'))

    def test_syntax_error_in_expression_is_survivable(self):
        broken = self._rule(
            'test_syntax', "field('color' >= ", message="Règle mal écrite.")
        submit = self._transition_by_code('submit')
        submit.condition_ids = [(6, 0, broken.ids)]

        passed, error = self.instance._evaluate_rule(broken)
        self.assertFalse(passed)
        self.assertTrue(error)
        self.assertFalse(self.instance.transition_options()[0]['available'])

    def test_expression_cannot_reach_dangerous_builtins(self):
        """`safe_eval` et non `eval()` : la démonstration en une ligne."""
        dangerous = self._rule(
            'test_import',
            "__import__('os').system('echo pwned')",
            message="Expression refusée.",
        )
        passed, error = self.instance._evaluate_rule(dangerous)
        self.assertFalse(passed)
        self.assertTrue(error)

    def test_evaluation_context_is_rebuilt_for_each_rule(self):
        """`safe_eval` **mute** le dictionnaire qu'on lui passe : il y réinjecte
        les variables créées pendant l'évaluation.

        Un contexte partagé entre deux règles ferait donc hériter la seconde des
        variables de la première, et le résultat dépendrait de l'ordre
        d'évaluation. Chaque appel doit repartir d'un dictionnaire neuf.
        """
        first = self.instance._evaluation_context()
        second = self.instance._evaluation_context()
        self.assertIsNot(first, second)

        first['variable_parasite'] = True
        self.assertNotIn('variable_parasite', self.instance._evaluation_context())

    # ------------------------------------------------------------
    # Le mixin
    # ------------------------------------------------------------

    def test_engine_runs_without_the_mixin(self):
        """`res.partner` n'hérite pas du mixin, et le workflow tourne quand même.

        Le mixin est du confort ; `res_model`/`res_id` est le mécanisme. C'est
        ce qui rend le moteur utilisable sur n'importe quel modèle Odoo, y
        compris ceux qu'on ne peut pas modifier.
        """
        self.assertNotIn('workflow_instance_id', self.env['res.partner']._fields)
        self.instance.do_transition(self._transition_by_code('submit'))
        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('review'))

    def test_start_refuses_a_model_mismatch(self):
        users_model = self.env['ir.model']._get('res.users')
        definition = self._definition(code='users_wf', model=users_model)
        self._stage(definition, 'start', is_start=True)
        end = self._stage(definition, 'end', is_end=True)
        self._transition(
            definition, 'go', definition.stage_ids[0], end)
        definition.action_publish()

        with self.assertRaises(UserError) as error:
            self.Instance._start_for(self.record, 'users_wf')
        self.assertIn('res.users', str(error.exception))

    def test_cancel_stops_the_instance_and_is_traced(self):
        before = len(self.instance.history_ids)
        self.instance.action_cancel()
        self.assertEqual(self.instance.state, 'cancelled')
        self.assertTrue(self.instance.date_end)
        self.assertEqual(len(self.instance.history_ids), before + 1)
        self.assertFalse(self.instance.available_transitions())
