from odoo.exceptions import AccessError
from odoo.tests.common import new_test_user, tagged

from .common import WorkflowCase


@tagged('post_install', '-at_install')
class TestDynamicAccess(WorkflowCase):
    """Extension 5 — identité + rôle + relation au dossier → droits d'accès.

    **Tous les tests passent par de vrais comptes non-admin.** Une `ir.rule`
    ne se voit pas en administrateur : `base.group_system` les contourne
    toutes. Un test écrit en admin passerait en affirmant exactement rien.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.definition = cls._linear_definition(code='access_wf')

        cls.role_porteur = cls.env.ref('opex_workflow.role_porteur')
        cls.role_expert = cls.env.ref('opex_workflow.role_expert')

        # Trois comptes portail strictement identiques du point de vue des
        # groupes Odoo. Seul leur rattachement au dossier les distinguera.
        cls.porteur = new_test_user(
            cls.env, login='acc_porteur', groups='base.group_portal')
        cls.expert = new_test_user(
            cls.env, login='acc_expert', groups='base.group_portal')
        cls.etranger = new_test_user(
            cls.env, login='acc_etranger', groups='base.group_portal')

        cls.record = cls.env['res.partner'].create({'name': "Dossier suivi"})
        cls.instance = cls.Instance._start_for(cls.record, 'access_wf')

        cls.other_record = cls.env['res.partner'].create({'name': "Dossier voisin"})
        cls.other_instance = cls.Instance._start_for(cls.other_record, 'access_wf')

        cls.instance.add_actor(cls.role_porteur, cls.porteur, 'full')
        cls.instance.add_actor(cls.role_expert, cls.expert, 'limited')

    def _visible_instances(self, user):
        return self.Instance.with_user(user).search([])

    # ------------------------------------------------------------
    # _has_access — le point unique
    # ------------------------------------------------------------

    def test_has_access_follows_the_actor_line(self):
        self.assertTrue(self.instance._has_access(self.porteur, 'full'))
        self.assertTrue(self.instance._has_access(self.expert, 'limited'))
        self.assertFalse(self.instance._has_access(self.etranger, 'limited'))

    def test_limited_actor_does_not_reach_full_level(self):
        """« Limité » n'est pas « complet » : c'est toute la section 13 du
        document source — le match ne donne pas le dossier entier."""
        self.assertTrue(self.instance._has_access(self.expert, 'limited'))
        self.assertFalse(self.instance._has_access(self.expert, 'full'))

    def test_access_is_per_instance_not_per_profile(self):
        """Être expert ne donne accès à aucun dossier ; la ligne d'acteur donne
        accès à celui-ci."""
        self.assertTrue(self.instance._has_access(self.expert, 'limited'))
        self.assertFalse(self.other_instance._has_access(self.expert, 'limited'))

    def test_workflow_manager_sees_everything(self):
        manager = new_test_user(
            self.env, login='acc_manager',
            groups='base.group_user,opex_workflow.group_workflow_manager')
        self.assertTrue(self.instance._has_access(manager, 'full'))
        self.assertTrue(self.other_instance._has_access(manager, 'full'))

    # ------------------------------------------------------------
    # ir.rule — avec de vrais comptes portail
    # ------------------------------------------------------------

    def test_portal_actor_sees_only_his_own_instance(self):
        visible = self._visible_instances(self.porteur)
        self.assertIn(self.instance, visible)
        self.assertNotIn(self.other_instance, visible)

    def test_two_actors_on_the_same_instance_both_see_it(self):
        """Deux rôles différents, un même dossier : chacun le voit."""
        self.assertIn(self.instance, self._visible_instances(self.porteur))
        self.assertIn(self.instance, self._visible_instances(self.expert))

    def test_user_without_actor_line_sees_nothing_at_all(self):
        self.assertFalse(self._visible_instances(self.etranger))

    def test_reading_a_foreign_instance_is_refused(self):
        """Le filtrage n'est pas qu'un `search` : la lecture directe échoue.

        C'est la différence entre masquer une ligne dans une liste et interdire
        l'accès. Un identifiant deviné ne doit rien donner.
        """
        with self.assertRaises(AccessError):
            self.other_instance.with_user(self.porteur).read(['definition_id'])

    def test_history_is_scoped_by_cascade(self):
        own = self.env['opex.workflow.history'].with_user(self.porteur).search([])
        self.assertTrue(own)
        self.assertEqual(set(own.mapped('instance_id')), {self.instance})

    def test_task_is_scoped_by_cascade(self):
        Task = self.env['opex.workflow.task'].sudo()
        mine = Task.create({
            'instance_id': self.instance.id,
            'name': "À traiter", 'role_id': self.role_expert.id,
        })
        Task.create({
            'instance_id': self.other_instance.id,
            'name': "Ailleurs", 'role_id': self.role_expert.id,
        })
        visible = self.env['opex.workflow.task'].with_user(self.expert).search([])
        self.assertEqual(visible, mine)

    def test_actor_lines_are_scoped_too(self):
        Actor = self.env['opex.workflow.instance.actor']
        visible = Actor.with_user(self.porteur).search([])
        self.assertEqual(set(visible.mapped('instance_id')), {self.instance})

    def test_portal_cannot_write_on_an_instance_it_reads(self):
        """Voir n'est pas modifier : la règle portail est en lecture seule."""
        with self.assertRaises(AccessError):
            self.instance.with_user(self.porteur).write({'state': 'done'})

    # ------------------------------------------------------------
    # Révocation
    # ------------------------------------------------------------

    def test_revoking_access_hides_the_instance_immediately(self):
        self.assertIn(self.instance, self._visible_instances(self.expert))
        self.instance.remove_actor(self.role_expert, self.expert)
        self.assertNotIn(self.instance, self._visible_instances(self.expert))

    def test_revocation_keeps_the_trace(self):
        self.instance.remove_actor(self.role_expert, self.expert)
        line = self.instance.sudo().actor_ids.filtered(
            lambda a: a.user_id == self.expert)
        self.assertTrue(line, "La ligne doit rester pour l'audit")
        self.assertEqual(line.access_level, 'none')
        self.assertTrue(line.date_granted)
        self.assertTrue(line.granted_by_id)

    def test_revoked_actor_does_not_carry_the_role_anymore(self):
        self.assertIn(self.role_expert, self.instance._user_roles(self.expert))
        self.instance.remove_actor(self.role_expert, self.expert)
        self.assertNotIn(self.role_expert, self.instance._user_roles(self.expert))

    def test_revocation_of_one_actor_does_not_affect_the_others(self):
        """Le piège du domaine à deux conditions sur un One2many.

        Écrite `['&', ('actor_ids.user_id','=',user.id),
        ('actor_ids.access_level','!=','none')]`, la règle serait fausse : les
        deux conditions seraient satisfaites par deux lignes différentes, et
        l'expert révoqué garderait l'accès parce que le porteur, lui, l'a
        encore. Ce test échoue si quelqu'un « simplifie » vers `actor_ids`.
        """
        self.instance.remove_actor(self.role_expert, self.expert)
        self.assertNotIn(self.instance, self._visible_instances(self.expert))
        # Le porteur, toujours actif sur le même dossier, n'est pas affecté.
        self.assertIn(self.instance, self._visible_instances(self.porteur))

    # ------------------------------------------------------------
    # add_actor / remove_actor
    # ------------------------------------------------------------

    def test_add_actor_opens_access_and_is_idempotent(self):
        self.assertFalse(self._visible_instances(self.etranger))
        self.instance.add_actor(self.role_expert, self.etranger, 'limited')
        self.assertIn(self.instance, self._visible_instances(self.etranger))

        # Rappelée, elle relève le niveau sans créer de doublon.
        before = len(self.instance.sudo().actor_ids)
        self.instance.add_actor(self.role_expert, self.etranger, 'full')
        self.assertEqual(len(self.instance.sudo().actor_ids), before)
        self.assertTrue(self.instance._has_access(self.etranger, 'full'))

    def test_re_adding_a_revoked_actor_restores_access(self):
        self.instance.remove_actor(self.role_expert, self.expert)
        self.assertNotIn(self.instance, self._visible_instances(self.expert))
        self.instance.add_actor(self.role_expert, self.expert, 'limited')
        self.assertIn(self.instance, self._visible_instances(self.expert))

    def test_remove_actor_can_erase_when_asked(self):
        self.instance.remove_actor(self.role_expert, self.expert, keep_trace=False)
        self.assertFalse(self.instance.sudo().actor_ids.filtered(
            lambda a: a.user_id == self.expert))

    # ------------------------------------------------------------
    # Utilisateurs internes non gestionnaires
    # ------------------------------------------------------------

    def test_plain_internal_user_is_scoped_like_a_portal_user(self):
        """Un contrôleur est un utilisateur interne, pas un administrateur.

        Sans règle sur `base.group_user`, il lirait tous les dossiers de la
        base — le trou le plus facile à laisser, parce qu'invisible en admin.
        """
        internal = new_test_user(
            self.env, login='acc_internal', groups='base.group_user')
        self.assertFalse(self._visible_instances(internal))

        self.instance.add_actor(self.role_expert, internal, 'limited')
        visible = self._visible_instances(internal)
        self.assertIn(self.instance, visible)
        self.assertNotIn(self.other_instance, visible)

    def test_internal_user_sees_a_task_assigned_to_him_without_actor_line(self):
        """La work queue confie un travail précis, pas l'accès au dossier."""
        internal = new_test_user(
            self.env, login='acc_tasked', groups='base.group_user')
        task = self.env['opex.workflow.task'].sudo().create({
            'instance_id': self.instance.id,
            'name': "Traiter ceci",
            'role_id': self.role_expert.id,
            'user_id': internal.id,
        })
        visible = self.env['opex.workflow.task'].with_user(internal).search([])
        self.assertEqual(visible, task)
        # …sans pour autant lui ouvrir le dossier lui-même.
        self.assertFalse(self._visible_instances(internal))

    # ------------------------------------------------------------
    # initiator_role_id — l'acteur que le métier ne doit plus poser
    # ------------------------------------------------------------

    def _initiator_definition(self, code, role=None):
        definition = self._linear_definition(code=code, publish=False)
        definition.initiator_role_id = (role or self.role_porteur).id
        definition.action_publish()
        return definition

    def test_the_initiator_becomes_actor_of_the_instance_he_starts(self):
        """Le correctif de cause : le moteur pose la ligne, pas le métier.

        Le rôle Porteur n'a pas de groupe. Tant que la ligne d'acteur relevait
        du `create()` de chaque module métier, l'oubli était muet et le
        déposant se retrouvait sans aucune transition sur son propre dossier.
        """
        self._initiator_definition('initiator_wf')
        record = self.env['res.partner'].create({'name': "Dossier initié"})
        instance = self.Instance.with_user(self.porteur)._start_for(
            record, 'initiator_wf')

        actors = instance.sudo().actor_ids
        self.assertEqual(len(actors), 1)
        self.assertEqual(actors.role_id, self.role_porteur)
        self.assertEqual(actors.user_id, self.porteur)
        self.assertEqual(actors.access_level, 'full')
        # La conséquence observable : le dossier lui est visible et agissable.
        self.assertTrue(instance._has_access(self.porteur, 'full'))

    def test_without_the_field_the_engine_places_nothing(self):
        """Un processus ouvert par un tiers pour le compte d'un autre.

        Y poser l'initiateur donnerait un accès complet à celui qui ouvre le
        dossier — le CEO sur un suivi d'industrialisation, par exemple. Le
        champ vide doit donc rester strictement sans effet.
        """
        record = self.env['res.partner'].create({'name': "Dossier tiers"})
        instance = self.Instance.with_user(self.porteur)._start_for(
            record, 'access_wf')
        self.assertFalse(instance.sudo().actor_ids)

    def test_the_public_user_never_becomes_actor(self):
        """Le compte public est partagé par tous les visiteurs.

        Lui donner un rôle sur un dossier l'ouvrirait à n'importe qui.
        """
        self._initiator_definition('initiator_public_wf')
        record = self.env['res.partner'].create({'name': "Dossier public"})
        instance = self.Instance._start_for(record, 'initiator_public_wf')

        # `initiator_id` réécrit plutôt que `_start_for()` appelé sous le compte
        # public : celui-ci n'a aucun droit de lecture sur la configuration du
        # moteur, et le test échouerait sur l'ACL avant d'atteindre la garde
        # qu'il prétend vérifier.
        instance.sudo().actor_ids.unlink()
        instance.sudo().initiator_id = self.env.ref('base.public_user')

        self.assertFalse(instance._grant_initiator_role())
        self.assertFalse(instance.sudo().actor_ids)

    def test_backfill_repairs_instances_started_before_the_field_existed(self):
        """Un correctif qui ne vaut que pour l'avenir laisse des dossiers morts.

        Les demandes déjà déposées sont nées sans acteur : sans rattrapage,
        leurs déposants resteraient définitivement bloqués.
        """
        definition = self._initiator_definition('initiator_backfill_wf')
        record = self.env['res.partner'].create({'name': "Dossier ancien"})
        instance = self.Instance.with_user(self.porteur)._start_for(
            record, 'initiator_backfill_wf')

        # On remet l'instance dans l'état d'avant le correctif.
        instance.sudo().actor_ids.unlink()
        self.assertFalse(instance.sudo().actor_ids)

        repaired = self.Instance._backfill_missing_initiator_actors(
            definition_codes=[definition.code])

        self.assertEqual(repaired, 1)
        self.assertEqual(instance.sudo().actor_ids.user_id, self.porteur)
        # Idempotent : un second passage ne recrée rien.
        self.assertEqual(
            self.Instance._backfill_missing_initiator_actors(
                definition_codes=[definition.code]), 0)

    def test_backfill_ignores_instances_whose_record_is_gone(self):
        """Une instance orpheline n'a personne à qui ouvrir quoi que ce soit."""
        definition = self._initiator_definition('initiator_orphan_wf')
        record = self.env['res.partner'].create({'name': "Dossier supprimé"})
        instance = self.Instance.with_user(self.porteur)._start_for(
            record, 'initiator_orphan_wf')
        instance.sudo().actor_ids.unlink()
        record.unlink()

        self.assertEqual(
            self.Instance._backfill_missing_initiator_actors(
                definition_codes=[definition.code]), 0)
        self.assertFalse(instance.sudo().actor_ids)
