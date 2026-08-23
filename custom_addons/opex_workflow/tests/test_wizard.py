from odoo.exceptions import UserError
from odoo.tests.common import new_test_user, tagged

from .common import WorkflowCase


@tagged('post_install', '-at_install')
class TestTransitionWizard(WorkflowCase):
    """Extension 3 — le wizard propose-t-il exactement ce qu'il faut ?"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.definition = cls._linear_definition(code='wizard_wf')
        cls.record = cls.env['res.partner'].create({'name': "Dossier wizard"})
        cls.instance = cls.Instance._start_for(cls.record, 'wizard_wf')
        cls.Wizard = cls.env['opex.workflow.transition.wizard']

    def _stage_by_code(self, code):
        return self.definition.stage_ids.filtered(lambda s: s.code == code)

    def _transition_by_code(self, code):
        return self.definition.transition_ids.filtered(lambda t: t.code == code)

    def _open(self, transition, instance=None, user=None):
        """Crée le wizard avec une action déjà choisie.

        `transition_id` est `required=True` : l'enregistrement transient ne peut
        pas naître sans valeur. À l'écran ce n'est pas gênant — le client rend
        le formulaire et ne crée l'enregistrement qu'à la confirmation, une fois
        l'utilisateur ayant choisi. En test il faut donc fournir le choix dès la
        création, comme le fait le client.
        """
        instance = instance or self.instance
        model = self.Wizard.with_user(user) if user else self.Wizard
        return model.with_context(default_instance_id=instance.id).create({
            'instance_id': instance.id,
            'transition_id': str(transition.id),
        })

    def _options(self, instance=None, user=None):
        """Les valeurs proposées par la Selection, telles que l'écran les voit."""
        instance = instance or self.instance
        model = self.Wizard.with_user(user) if user else self.Wizard
        return model.with_context(
            default_instance_id=instance.id)._selection_transitions()

    # ------------------------------------------------------------
    # Le wizard liste les transitions disponibles, et seulement celles-là
    # ------------------------------------------------------------

    def test_wizard_lists_exactly_the_available_transitions(self):
        # Depuis « Brouillon », une seule sortie.
        self.assertEqual(
            [value for value, _label in self._options()],
            [str(self._transition_by_code('submit').id)],
        )

        self.instance.do_transition(self._transition_by_code('submit'))

        # Depuis « Contrôle », deux sorties — et pas celle de l'étape précédente.
        proposed = {value for value, _label in self._options()}
        self.assertEqual(
            proposed, {str(self._transition_by_code('validate').id), str(self._transition_by_code('reject').id)})
        self.assertNotIn(str(self._transition_by_code('submit').id), proposed)

    def test_wizard_hides_transitions_the_user_has_no_role_for(self):
        """Accès au dossier, mais pas le rôle : la transition n'est pas proposée.

        L'observateur est **acteur du dossier** — sans ligne d'acteur il ne
        pourrait même pas le lire (Extension 5), et le test mesurerait un refus
        d'accès au lieu d'un refus de rôle. Les deux couches sont distinctes :
        voir un dossier n'est pas pouvoir le faire avancer.
        """
        role = self.Role.create({
            'name': "Contrôleur",
            'code': 'wizard_role',
            'group_id': self.env.ref('base.group_system').id,
        })
        observer_role = self.Role.create({
            'name': "Observateur", 'code': 'wizard_role_observer'})
        self._transition_by_code('submit').allowed_role_ids = [(6, 0, role.ids)]

        outsider = new_test_user(
            self.env, login='wizard_outsider', groups='base.group_user')
        self.instance.add_actor(observer_role, outsider, 'limited')

        self.assertEqual(self._options(user=outsider), [])
        self.assertTrue(self._options())

    def test_wizard_refuses_to_open_when_nothing_is_possible(self):
        """Une liste déroulante vide n'explique rien ; un message, si."""
        role = self.Role.create({'name': "Comité", 'code': 'wizard_role_none'})
        observer_role = self.Role.create({
            'name': "Observateur", 'code': 'wizard_role_none_observer'})
        self._transition_by_code('submit').allowed_role_ids = [(6, 0, role.ids)]

        outsider = new_test_user(
            self.env, login='wizard_nothing', groups='base.group_user')
        self.instance.add_actor(observer_role, outsider, 'limited')

        with self.assertRaises(UserError) as error:
            self.instance.with_user(outsider).action_open_transition_wizard()
        self.assertIn("Brouillon", str(error.exception))

    def test_wizard_refuses_to_open_on_a_closed_instance(self):
        self.instance.do_transition(self._transition_by_code('submit'))
        self.instance.do_transition(self._transition_by_code('validate'))
        self.assertEqual(self.instance.state, 'done')

        with self.assertRaises(UserError):
            self.instance.action_open_transition_wizard()

    # ------------------------------------------------------------
    # Une transition bloquée est proposée, mais refusée à la confirmation
    # ------------------------------------------------------------

    def test_blocked_transition_is_offered_then_refused_with_its_message(self):
        rule = self._rule(
            'wizard_block',
            "field('color') >= 70",
            message="La note doit atteindre 70.",
        )
        self._transition_by_code('submit').condition_ids = [(6, 0, rule.ids)]
        self.record.color = 10

        # ⚠ Elle est **proposée**, avec son motif dans le libellé.
        options = self._options()
        self.assertEqual(len(options), 1)
        value, label = options[0]
        self.assertEqual(value, str(self._transition_by_code('submit').id))
        self.assertIn("La note doit atteindre 70.", label)
        self.assertIn("indisponible", label)

        # Le wizard signale le blocage avant même la confirmation.
        wizard = self._open(self._transition_by_code('submit'))
        self.assertTrue(wizard.is_blocked)
        self.assertIn("La note doit atteindre 70.", wizard.blocking_reason)

        # Et la confirmation échoue avec le message de la règle.
        with self.assertRaises(UserError) as error:
            wizard.action_confirm()
        self.assertIn("La note doit atteindre 70.", str(error.exception))
        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('draft'))

        # Le dossier progresse : le libellé se nettoie et la confirmation passe.
        self.record.color = 80
        self.assertNotIn("indisponible", self._options()[0][1])
        wizard = self._open(self._transition_by_code('submit'))
        self.assertFalse(wizard.is_blocked)
        wizard.action_confirm()
        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('review'))

    # ------------------------------------------------------------
    # Confirmation nominale et commentaire
    # ------------------------------------------------------------

    def test_confirm_moves_the_record_and_writes_history(self):
        wizard = self._open(self._transition_by_code('submit'))
        wizard.comment = "Dossier complet."
        wizard.action_confirm()

        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('review'))
        entry = self.instance.history_ids.filtered(
            lambda h: h.transition_id == self._transition_by_code('submit'))
        self.assertEqual(entry.comment, "Dossier complet.")

    def test_requires_comment_is_reported_and_enforced(self):
        self.instance.do_transition(self._transition_by_code('submit'))
        wizard = self._open(self._transition_by_code('reject'))

        # Le champ devient obligatoire à l'écran…
        self.assertTrue(wizard.requires_comment)

        # …et le serveur refuse quand même si on passe outre.
        with self.assertRaises(UserError) as error:
            wizard.action_confirm()
        self.assertIn("motif", str(error.exception))

        wizard.comment = "Hors périmètre."
        wizard.action_confirm()
        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('rejected'))
        self.assertEqual(self.instance.state, 'done')

    def test_requires_comment_is_false_on_a_free_transition(self):
        wizard = self._open(self._transition_by_code('submit'))
        self.assertFalse(wizard.requires_comment)

    # ------------------------------------------------------------
    # Le wizard ne rouvre pas de porte dérobée
    # ------------------------------------------------------------

    def test_forged_transition_id_cannot_move_the_record(self):
        """Une transition d'un autre workflow, injectée dans le champ.

        Deux défenses la couvrent : la `Selection` n'accepte que les valeurs
        calculées côté serveur, et `_selected_transition()` cherche
        l'identifiant *dans* l'ensemble autorisé plutôt que de l'utiliser pour
        naviguer. Le test n'affirme pas laquelle des deux a joué — il affirme la
        propriété qui compte : le dossier n'a pas bougé.
        """
        other = self._linear_definition(code='wizard_other')
        foreign = other.transition_ids.filtered(lambda t: t.code == 'submit')

        wizard = self._open(self._transition_by_code('submit'))
        with self.assertRaises(Exception):
            wizard.transition_id = str(foreign.id)
            wizard.action_confirm()
        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('draft'))

    def test_confirm_does_not_bypass_role_control(self):
        """Le wizard ne rejuge rien : il repasse par le contrôle d'accès unique.

        Le wizard est créé par un utilisateur qui **porte** le rôle, puis
        confirmé par un utilisateur qui ne le porte pas. Si `action_confirm()`
        se fiait à la liste calculée à l'ouverture plutôt qu'à
        `_check_transition_allowed()`, la transition passerait.
        """
        role = self.Role.create({
            'name': "Contrôleur",
            'code': 'wizard_bypass',
            'group_id': self.env.ref('base.group_system').id,
        })
        self._transition_by_code('submit').allowed_role_ids = [(6, 0, role.ids)]
        observer_role = self.Role.create({
            'name': "Observateur", 'code': 'wizard_bypass_observer'})
        outsider = new_test_user(
            self.env, login='wizard_forger', groups='base.group_user')
        self.instance.add_actor(observer_role, outsider, 'limited')

        wizard = self._open(self._transition_by_code('submit'))
        self.env.invalidate_all()
        with self.assertRaises(Exception):
            wizard.with_user(outsider).action_confirm()
        self.assertEqual(self.instance.current_stage_id, self._stage_by_code('draft'))
