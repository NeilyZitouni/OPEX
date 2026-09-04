from odoo.exceptions import AccessError, UserError
from odoo.tests.common import tagged
from odoo.tools import mute_logger

from .common import APPLICATION_CODE, MissionCase

#: Le parcours nominal d'une candidature : transition, acteur, étape atteinte.
NOMINAL_PATH = [
    ('application_view', 'intervenant', 'viewed'),
    ('application_express_interest', 'intervenant', 'interested'),
    ('application_apply', 'intervenant', 'applied'),
    ('application_screen', 'manager', 'screened'),
    ('application_shortlist', 'manager', 'shortlisted'),
    ('application_select', 'decideur', 'selected'),
]


@tagged('post_install', '-at_install')
class TestMissionApplication(MissionCase):
    """Extension 1 — la seconde machine à états, sur un second modèle."""

    def setUp(self):
        super().setUp()
        # Un appel ouvert aux candidatures, pour toute la suite.
        self.mission = self._new_mission()
        self._open_the_call(self.mission)

    #
    # LA RÈGLE
    #

    def test_the_application_has_no_state_field(self):
        """Le second modèle sans `state`. Deux workflows, zéro champ d'état."""
        self.assertNotIn('state', self.Application._fields)
        self.assertIn('workflow_instance_id', self.Application._fields)
        self.assertIn('workflow_stage_id', self.Application._fields)

    def test_no_selection_field_describes_progress(self):
        for suspect in ('state', 'etat', 'statut', 'status', 'avancement', 'stage_id'):
            self.assertNotIn(
                suspect, self.Application._fields,
                "Le champ « %s » ressemble à un état codé en dur." % suspect)

    def test_the_two_definitions_are_distinct(self):
        """« La séparation des deux machines à états est obligatoire. »"""
        self.assertNotEqual(
            self.mission_definition, self.application_definition)
        self.assertEqual(
            self.application_definition.model_name, 'opex.mission.application')
        self.assertEqual(
            self.mission_definition.model_name, 'opex.mission.request')

    #
    # LA DÉFINITION CONFIGURÉE
    #

    def test_the_definition_is_published(self):
        self.assertEqual(self.application_definition.state, 'published')
        self.assertEqual(self.application_definition.code, APPLICATION_CODE)

    def test_ten_stages_and_twenty_transitions(self):
        definition = self.application_definition
        self.assertEqual(len(definition.stage_ids), 10)
        self.assertEqual(len(definition.transition_ids), 20)

    def test_the_seven_stages_of_the_specification_are_present(self):
        """§12.2, à la lettre : les sept étapes plus les trois branches."""
        expected = {
            'invited', 'viewed', 'interested', 'applied', 'screened',
            'shortlisted', 'selected', 'declined', 'rejected', 'withdrawn',
        }
        codes = set(self.application_definition.stage_ids.mapped('code'))
        self.assertEqual(codes, expected)

    def test_the_graph_is_valid(self):
        self.assertTrue(self.application_definition.sudo()._check_graph())

    def test_every_stage_has_a_user_label(self):
        without = self.application_definition.stage_ids.filtered(
            lambda s: not s.user_label)
        self.assertFalse(
            without,
            "Étapes sans libellé utilisateur : %s"
            % ", ".join(without.mapped('code')))

    def test_invited_is_the_only_entry_point(self):
        """Une seule `is_start`, et c'est la contrainte qui a dicté le reste.

        Le moteur n'en admet qu'une (`_check_graph`), or le §8 a deux canaux
        d'alimentation. `invited` est donc l'entrée des deux : le matching y
        pose une invitation, le portail y pose l'instant de création — et
        `source` distingue les deux.
        """
        starts = self.application_definition.stage_ids.filtered('is_start')
        self.assertEqual(starts.mapped('code'), ['invited'])

    def test_declined_is_reversible_and_the_three_other_ends_are_not(self):
        """L'arbitrage rendu sur `declined`.

        Avec le §12.2, `declined` est atteignable dès `invited`. Un refus
        d'invitation ne doit pas fermer définitivement un appel qui sera publié
        au portail — d'autant que `unique(mission_id, partner_id)` interdit une
        seconde candidature. `declined` porte donc une sortie et n'est pas
        terminale ; les trois autres fins le restent.
        """
        stages = self.application_definition.stage_ids
        ends = set(stages.filtered('is_end').mapped('code'))
        self.assertEqual(ends, {'selected', 'rejected', 'withdrawn'})

        declined = stages.filtered(lambda s: s.code == 'declined')
        self.assertFalse(declined.is_end)
        self.assertEqual(
            declined.transition_out_ids.mapped('target_stage_id.code'),
            ['viewed'])

    def test_the_shortlist_stage_has_four_exits(self):
        shortlisted = self.application_definition.stage_ids.filtered(
            lambda s: s.code == 'shortlisted')
        self.assertEqual(len(shortlisted.transition_out_ids), 4)

    def test_the_direct_rejection_of_the_schema_5_exists(self):
        """« Soumise → Non retenue » : la voie des candidatures inéligibles."""
        transition = self._transition(
            self.application_definition, 'application_reject_applied')
        self.assertEqual(transition.source_stage_id.code, 'applied')
        self.assertEqual(transition.target_stage_id.code, 'rejected')
        self.assertTrue(transition.requires_comment)

    def test_the_definition_declares_no_initiator_role(self):
        """Le cas le plus net des deux : sur le canal matching, c'est le
        responsable qui crée la candidature d'un autre."""
        self.assertFalse(
            self.application_definition.sudo().initiator_role_id,
            "`initiator_role_id` renseigné : le responsable qui invite un "
            "expert héritera du rôle intervenant sur la candidature de celui-ci.")

    #
    # LA CRÉATION
    #

    def test_the_workflow_starts_on_invited(self):
        application = self._new_application(self.mission)
        self.assertTrue(application.workflow_instance_id)
        self.assertEqual(self._stage(application), 'invited')
        self.assertEqual(
            application.workflow_definition_id, self.application_definition)

    def test_create_forces_the_partner_for_a_portal_user(self):
        application = self._new_application(
            self.mission,
            partner=self.other_intervenant.partner_id,
            user=self.intervenant,
        )
        self.assertEqual(
            application.sudo().partner_id, self.intervenant.partner_id,
            "Un compte portail a réussi à candidater au nom d'un autre.")

    @mute_logger('odoo.sql_db')
    def test_the_same_expert_cannot_apply_twice(self):
        """Règle 3 du §39, au niveau SQL et pas seulement applicatif.

        Une contrainte applicative se contourne par un import, par un script ou
        par une requête forgée. Celle-ci ne se contourne pas.
        """
        self._new_application(self.mission)
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self._new_application(self.mission)

    def test_the_same_expert_may_apply_to_another_call(self):
        """« Un intervenant peut avoir plusieurs candidatures » — l'autre
        moitié de la règle 3, qu'une contrainte trop large casserait."""
        other_mission = self._new_mission()
        self._open_the_call(other_mission)
        first = self._new_application(self.mission)
        second = self._new_application(other_mission)
        self.assertNotEqual(first, second)

    #
    # L'ACTEUR EST POSÉ DEPUIS `partner_id`, PAS DEPUIS LE CRÉATEUR
    #

    def test_the_candidate_is_actor_and_the_inviting_manager_is_not(self):
        """La preuve de l'arbitrage Q2, sur le canal où il compte vraiment.

        Le responsable invite : il crée la candidature d'un autre. Avec
        `initiator_role_id`, il recevrait le rôle `intervenant` en accès `full`
        sur ce dossier.

        Assertion positive d'abord — l'intervenant est bien acteur — puis
        l'assertion négative.
        """
        application = self._new_application(
            self.mission, user=self.manager, source='matching')
        actors = application.sudo().workflow_instance_id.actor_ids

        candidate_lines = actors.filtered(
            lambda a: a.user_id == self.intervenant)
        self.assertEqual(len(candidate_lines), 1)
        self.assertEqual(candidate_lines.role_id.code, 'intervenant')
        self.assertEqual(candidate_lines.access_level, 'full')

        self.assertFalse(
            actors.filtered(lambda a: a.user_id == self.manager),
            "Le responsable qui invite a hérité du rôle intervenant sur la "
            "candidature d'un autre.")

    def test_the_candidate_reads_his_own_application_and_not_the_others(self):
        mine = self._new_application(self.mission)
        other = self._new_application(
            self.mission, partner=self.other_intervenant.partner_id)

        as_candidate = mine.with_user(self.intervenant)
        self.assertEqual(as_candidate.partner_id, self.intervenant.partner_id)

        # On **lit un champ**, on n'appelle pas `exists()` : celui-ci ne fait
        # qu'un `SELECT id` et n'applique aucune `ir.rule`. Écrite avec
        # `exists()`, l'assertion passait au vert sans rien prouver.
        with self.assertRaises(AccessError):
            other.with_user(self.intervenant).partner_id

    def test_the_expert_profile_is_linked_without_being_retyped(self):
        """« Un expert référencé ne ressaisit pas son profil permanent. »"""
        profile = self.env['opex.innovation.expert.profile'].sudo().create({
            'partner_id': self.intervenant.partner_id.id,
            'domaine_expertise': "Cybersécurité",
            'annees_experience': 15,
        })
        self.intervenant.partner_id.sudo().expert_profile_id = profile.id

        application = self._new_application(self.mission)
        self.assertEqual(application.sudo().expert_profile_id, profile)

    def test_a_candidate_without_a_profile_is_still_accepted(self):
        """Le candidat externe du §7 n'a pas encore de profil : sa candidature
        existe quand même, et il se qualifiera à l'Extension 5."""
        application = self._new_application(self.mission)
        self.assertFalse(application.sudo().expert_profile_id)
        self.assertEqual(self._stage(application), 'invited')

    #
    # LE PARCOURS COMPLET
    #

    def test_the_nominal_path_runs_end_to_end(self):
        application = self._new_application(self.mission)
        for code, actor_name, expected_stage in NOMINAL_PATH:
            if code == 'application_apply':
                self._fill_lean_form(application)
            self._do(application, code, getattr(self, actor_name),
                     comment="Étape franchie par le test.")
            self.assertEqual(
                self._stage(application), expected_stage,
                "Après « %s », la candidature devrait être en « %s »."
                % (code, expected_stage))
        self.assertEqual(application.sudo().workflow_state, 'done')

    def test_reconsider_reopens_a_declined_application(self):
        """Le chemin de retour, et la raison pour laquelle il existe.

        Sans lui, l'instance serait close (`state = 'done'`),
        `_check_transition_allowed()` refuserait tout, et la contrainte SQL
        interdirait une seconde candidature : l'appel serait fermé pour de bon.
        """
        application = self._new_application(self.mission, source='matching')
        self._do(application, 'application_decline_invitation', self.intervenant)
        self.assertEqual(self._stage(application), 'declined')
        # L'instance reste ouverte : `declined` n'est pas une étape finale.
        self.assertEqual(application.sudo().workflow_state, 'running')

        self._do(application, 'application_reconsider', self.intervenant)
        self.assertEqual(self._stage(application), 'viewed')

        self._fill_lean_form(application)
        self._do(application, 'application_express_interest', self.intervenant)
        self._do(application, 'application_apply', self.intervenant)
        self.assertEqual(self._stage(application), 'applied')

        visited = self._visited(application)
        self.assertEqual(
            visited.count('viewed'), 1,
            "Historique : %s" % visited)
        self.assertIn('declined', visited)

    def test_the_shortlist_loop_passes_twice_through_screened(self):
        """Le décideur renvoie une candidature à l'analyse.

        Compté sur une compréhension : `mapped()` dédupliquerait le second
        passage et le test serait vert sans rien vérifier.
        """
        application = self._new_application(self.mission)
        self._apply(application)
        self._do(application, 'application_screen', self.manager)
        self._do(application, 'application_shortlist', self.manager)
        self._do(application, 'application_back_to_screened', self.decideur)
        self.assertEqual(self._stage(application), 'screened')
        self._do(application, 'application_shortlist', self.manager)

        visited = self._visited(application)
        self.assertEqual(
            visited.count('screened'), 2,
            "La candidature doit être passée deux fois par l'analyse. "
            "Historique : %s" % visited)
        self.assertEqual(visited.count('shortlisted'), 2)

    #
    # LA CANDIDATURE LEAN
    #

    def test_apply_is_blocked_while_the_lean_form_is_incomplete(self):
        application = self._new_application(self.mission)
        self._do(application, 'application_view', self.intervenant)
        self._do(application, 'application_express_interest', self.intervenant)

        with self.assertRaises(UserError) as error:
            self._do(application, 'application_apply', self.intervenant)
        self.assertIn("disponibilité", str(error.exception))
        self.assertEqual(self._stage(application), 'interested')

    def test_the_candidate_writes_only_while_he_is_expected(self):
        """`interested` est la seule étape où l'`ir.rule` lui rend la main.

        Assertion positive puis négative : il écrit tant qu'il est attendu, il
        ne réécrit plus une fois la candidature déposée — la version examinée
        doit être celle que le responsable a lue.
        """
        application = self._new_application(self.mission, user=self.intervenant)
        self._do(application, 'application_view', self.intervenant)
        self._do(application, 'application_express_interest', self.intervenant)

        self._fill_lean_form(application, user=self.intervenant)
        self.assertEqual(application.sudo().disponibilite, 'oui')

        self._do(application, 'application_apply', self.intervenant)
        with self.assertRaises(AccessError):
            application.with_user(self.intervenant).write(
                {'tarif_propose': 1.0})

    #
    # RÈGLE 4 DU §39, VUE DEPUIS LA CANDIDATURE
    #

    def test_a_second_selection_is_blocked(self):
        first = self._select_the_application(
            self._new_application(self.mission))
        self.assertEqual(self._stage(first), 'selected')

        second = self._new_application(
            self.mission, partner=self.other_intervenant.partner_id)
        self._apply(second, user=self.other_intervenant)
        self._do(second, 'application_screen', self.manager)
        self._do(second, 'application_shortlist', self.manager)

        with self.assertRaises(UserError) as error:
            self._do(second, 'application_select', self.decideur,
                     comment="Second choix.")
        self.assertIn("déjà retenue", str(error.exception))
        self.assertEqual(self._stage(second), 'shortlisted')

    def test_a_second_selection_is_allowed_when_the_type_permits_it(self):
        mission = self._new_mission(mission_type_id=self.mission_type_multi.id)
        self._open_the_call(mission)
        self._select_the_application(self._new_application(mission))
        second = self._select_the_application(
            self._new_application(
                mission, partner=self.other_intervenant.partner_id),
            user=self.other_intervenant)
        self.assertEqual(self._stage(second), 'selected')

    #
    # L'INDÉPENDANCE DES DEUX MACHINES — LE TEST QUI COMPTE
    #

    def test_the_two_state_machines_are_independent(self):
        """Le septième critère d'acceptation du §21.

        « L'avancement global de la mission ne doit pas être confondu avec le
        parcours individuel de chaque candidat. »

        Une mission en `selection` porte simultanément trois candidatures dans
        trois étapes différentes. On fait avancer l'une : ni la mission ni les
        deux autres ne bougent. Puis on fait avancer la mission : aucune
        candidature ne bouge.
        """
        deposee = self._new_application(self.mission)
        self._apply(deposee)

        analysee = self._new_application(
            self.mission, partner=self.other_intervenant.partner_id)
        self._apply(analysee, user=self.other_intervenant)
        self._do(analysee, 'application_screen', self.manager)

        ecartee = self._new_application(
            self.mission, partner=self.other_client.partner_id)
        self._do(ecartee, 'application_reject_invited', self.manager,
                 comment="Profil sans rapport avec le besoin.")

        self._do(self.mission, 'mission_close_applications', self.manager)

        # Trois candidatures, trois étapes, une seule mission
        self.assertEqual(self._stage(self.mission), 'selection')
        self.assertEqual(self._stage(deposee), 'applied')
        self.assertEqual(self._stage(analysee), 'screened')
        self.assertEqual(self._stage(ecartee), 'rejected')

        # Faire avancer une candidature ne bouge rien d'autre
        self._do(analysee, 'application_shortlist', self.manager)
        self.assertEqual(self._stage(analysee), 'shortlisted')
        self.assertEqual(
            self._stage(self.mission), 'selection',
            "La mission a suivi l'avancement d'une de ses candidatures.")
        self.assertEqual(self._stage(deposee), 'applied')
        self.assertEqual(self._stage(ecartee), 'rejected')

        # Faire avancer la mission ne bouge aucune candidature
        self._do(analysee, 'application_select', self.decideur,
                 comment="Meilleur profil.")
        self._do(self.mission, 'mission_award', self.decideur,
                 comment="Attribution au candidat retenu.")
        self.assertEqual(self._stage(self.mission), 'awarded')
        self.assertEqual(
            self._stage(deposee), 'applied',
            "L'attribution de la mission a modifié une candidature qui n'y "
            "était pour rien.")
        self.assertEqual(self._stage(ecartee), 'rejected')
        self.assertEqual(self._stage(analysee), 'selected')

    def test_the_two_instances_are_distinct_records(self):
        """Deux objets, deux instances, deux historiques."""
        application = self._new_application(self.mission)
        self.assertNotEqual(
            self.mission.sudo().workflow_instance_id,
            application.sudo().workflow_instance_id)
        self.assertEqual(
            application.sudo().workflow_instance_id.res_model,
            'opex.mission.application')
        self.assertEqual(
            self.mission.sudo().workflow_instance_id.res_model,
            'opex.mission.request')

    #
    # LE POOL UNIQUE — §10
    #

    def test_both_channels_land_in_the_same_object(self):
        """Deuxième critère d'acceptation du §21 : comparables dans le même
        écran. Une seule table, un seul workflow, un champ `source`."""
        from_matching = self._new_application(
            self.mission, user=self.manager, source='matching')
        from_portal = self._new_application(
            self.mission, partner=self.other_intervenant.partner_id,
            user=self.manager, source='portail')

        self.assertEqual(from_matching._name, from_portal._name)
        self.assertEqual(
            from_matching.sudo().workflow_definition_id,
            from_portal.sudo().workflow_definition_id)
        self.assertEqual(self._stage(from_matching), 'invited')
        self.assertEqual(self._stage(from_portal), 'invited')

        pool = self.Application.sudo().search(
            [('mission_id', '=', self.mission.id)])
        self.assertEqual(len(pool), 2)
        self.assertEqual(
            set(pool.mapped('source')), {'matching', 'portail'})

    #
    # LES RÔLES
    #

    def test_the_candidate_cannot_shortlist_himself(self):
        application = self._new_application(self.mission)
        self._apply(application)
        with self.assertRaises(UserError) as error:
            self._do(application, 'application_screen', self.intervenant)
        self.assertIn("réservée", str(error.exception))

    def test_the_manager_cannot_select_alone(self):
        application = self._new_application(self.mission)
        self._apply(application)
        self._do(application, 'application_screen', self.manager)
        self._do(application, 'application_shortlist', self.manager)
        with self.assertRaises(UserError):
            self._do(application, 'application_select', self.manager,
                     comment="Choix.")
        self._do(application, 'application_select', self.decideur,
                 comment="Choix.")
        self.assertEqual(self._stage(application), 'selected')

    def test_rejections_require_a_written_reason(self):
        must_explain = {
            'application_reject_invited', 'application_reject_viewed',
            'application_reject_interested', 'application_reject_applied',
            'application_reject_screened', 'application_reject_shortlisted',
            'application_select',
        }
        for code in must_explain:
            transition = self._transition(self.application_definition, code)
            self.assertTrue(
                transition.requires_comment,
                "La transition « %s » devrait exiger un motif écrit." % code)
