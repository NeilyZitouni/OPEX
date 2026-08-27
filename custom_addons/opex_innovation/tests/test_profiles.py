from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestProfiles(TransactionCase):
    """Extension 9 — le premier workflow **configuré** du projet.

    C'est le banc d'essai du moteur avant le workflow projet à quinze étapes.
    Si le processus décrit en data XML ne tourne pas parfaitement ici, il ne
    tournera pas là-bas non plus.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Expert = cls.env['opex.innovation.expert.profile']
        cls.Investor = cls.env['opex.innovation.investor.profile']
        cls.Definition = cls.env['opex.workflow.definition']

        cls.secretariat = new_test_user(
            cls.env, login='inno_secr',
            groups='base.group_user,opex_membership.group_secretariat')

        cls.member_user = new_test_user(
            cls.env, login='inno_member', groups='base.group_portal')
        cls.member = cls.member_user.partner_id
        cls.member.sudo().write({'is_member': True})

    # ------------------------------------------------------------
    # La définition configurée
    # ------------------------------------------------------------

    def test_the_workflow_is_configured_not_coded(self):
        """Six étapes et six transitions, décrites en données.

        ⚠ La consigne annonçait « cinq étapes, quatre transitions ». Le
        schéma 2 du PDF en demande davantage : la boucle
        Complément → Resoumission → Contrôle en fait partie, et c'est elle qui
        prouve qu'on gère un graphe et non une séquence. Le PDF fait foi.
        """
        definition = self.Definition._get_for_code('profile_request')
        self.assertEqual(definition.state, 'published')
        self.assertEqual(len(definition.stage_ids), 6)
        self.assertEqual(len(definition.transition_ids), 6)
        self.assertTrue(definition._check_graph())

    def test_the_same_process_serves_two_models(self):
        expert_wf = self.Definition._get_for_code('profile_request')
        investor_wf = self.Definition._get_for_code('profile_request_investor')

        self.assertEqual(expert_wf.model_name, 'opex.innovation.expert.profile')
        self.assertEqual(investor_wf.model_name,
                         'opex.innovation.investor.profile')
        # Mêmes étapes, mêmes codes : un seul processus, deux modèles.
        self.assertEqual(
            set(expert_wf.stage_ids.mapped('code')),
            set(investor_wf.stage_ids.mapped('code')))

    def test_no_business_model_carries_a_state_field(self):
        """Le point qui décide de tout : l'état vient du moteur.

        Un `state = fields.Selection(...)` décrivant l'avancement sur l'un de
        ces modèles annulerait la démonstration entière du projet.
        """
        for model in (self.Expert, self.Investor):
            with self.subTest(model=model._name):
                self.assertNotIn('state', model._fields)
                self.assertIn('workflow_stage_id', model._fields)

    def test_three_stages_have_two_or_more_outgoing_transitions(self):
        """Le contrôle a trois sorties : complément, validation, refus."""
        definition = self.Definition._get_for_code('profile_request')
        review = definition.stage_ids.filtered(lambda s: s.code == 'review')
        outgoing = definition.transition_ids.filtered(
            lambda t: t.source_stage_id == review)
        self.assertEqual(len(outgoing), 3)

    # ------------------------------------------------------------
    # Le parcours complet, boucle comprise
    # ------------------------------------------------------------

    def _expert_request(self):
        """La demande est créée **par le membre**, comme au portail.

        ⚠ Ce test posait ici la ligne d'acteur à la main, et c'est ce geste qui
        a masqué le bug pendant toute l'Extension 9 : `create()` ne la posait
        pas, le portail non plus, et le déposant réel ne pouvait pas soumettre
        sa propre demande. Le test, lui, était vert.

        Deux corrections, indissociables : la création passe par
        `with_user(member_user)` — le `create()` en `self.env` s'exécutait en
        administrateur, ce qui n'est le parcours de personne — et plus rien
        n'est posé à la main. L'acteur doit venir du moteur, via
        `definition.initiator_role_id`. S'il n'en vient pas, ce test échoue,
        et c'est exactement ce qu'on lui demande.
        """
        return self.Expert.with_user(self.member_user).create({
            'domaine_expertise': "Industrie 4.0",
        })

    def _transition(self, profile, code):
        """Retrouve une transition par son code, **en lisant la configuration
        sous `sudo()`**.

        Depuis que les demandes sont créées par le membre — et non plus en
        administrateur —, `profile` est lié à un environnement portail. Or un
        compte portail n'a aucun droit de lecture sur
        `opex.workflow.transition` : le graphe est du paramétrage moteur, pas
        une donnée d'utilisateur.

        Ce n'est pas un manque de droits à corriger. Le portail réel ne lit
        jamais la configuration lui-même : il passe par
        `available_transitions()`, qui la lit sous `sudo()` et ne lui rend que
        le résultat (`workflow_instance.py`, la note sur `sudo()` de la
        configuration). Seul ce helper de test y accède directement, et c'est
        à lui de se placer au bon niveau.
        """
        return profile.sudo().workflow_definition_id.transition_ids.filtered(
            lambda t: t.code == code)

    def _do(self, profile, code, user, comment=False):
        """Franchit une transition **sous l'identité de l'acteur attendu**.

        Le workflow configuré porte de vrais rôles : l'administrateur ne peut
        pas soumettre à la place du membre, ni le membre valider à la place du
        Secrétariat. Un test qui déroulerait tout en admin ne mesurerait rien —
        il échouerait sur le premier contrôle de rôle, ce qui est précisément
        ce qui s'est passé au premier passage.
        """
        return profile.with_user(user).workflow_do_transition(
            self._transition(profile, code), comment=comment)

    def _stage_code(self, profile):
        return profile.workflow_stage_id.code

    def test_creating_a_request_starts_the_workflow(self):
        profile = self._expert_request()
        self.assertTrue(profile.workflow_instance_id)
        self.assertEqual(self._stage_code(profile), 'draft')
        self.assertEqual(profile.workflow_state, 'running')
        self.assertEqual(profile.workflow_stage_label, "Compléter ma demande")

    def test_the_depositor_is_actor_of_his_own_request(self):
        """Le test qui manquait — et qui aurait évité la régression.

        `role_porteur` n'a pas de groupe : personne ne le porte en permanence.
        Sans ligne d'acteur, le déposant n'a aucun rôle sur sa propre demande
        et `available_transitions()` lui renvoie une liste vide. Le dossier
        n'est pas en erreur, il est simplement sans issue — et rien ne le dit.

        On vérifie donc la cause (la ligne d'acteur) **et** sa conséquence
        observable (le bouton que le déposant voit).
        """
        profile = self._expert_request()
        porteur = self.env.ref('opex_workflow.role_porteur')

        actors = profile.workflow_instance_id.sudo().actor_ids
        self.assertEqual(len(actors), 1)
        self.assertEqual(actors.role_id, porteur)
        self.assertEqual(actors.user_id, self.member_user)
        self.assertEqual(actors.access_level, 'full')

        # La conséquence : le déposant voit bien sa transition de soumission.
        available = profile.workflow_instance_id.available_transitions(
            user=self.member_user)
        self.assertEqual(available.mapped('code'), ['submit'])

    def test_the_engine_places_the_actor_no_module_code_does(self):
        """La correction est dans le moteur, pas recopiée dans chaque `create()`.

        C'est tout l'objet du champ : un module métier qui démarre un workflow
        ne doit rien avoir à écrire, donc rien à oublier. Si quelqu'un vide
        `initiator_role_id` en croyant que le rattachement vit ailleurs, ce
        test le lui dit.
        """
        for code in ('profile_request', 'profile_request_investor'):
            with self.subTest(definition=code):
                definition = self.Definition._get_for_code(code)
                self.assertEqual(
                    definition.initiator_role_id,
                    self.env.ref('opex_workflow.role_porteur'))

    def test_submission_is_blocked_until_the_cv_is_joined(self):
        """La condition `has_document('cv')` s'appuie sur les conventions du
        moteur — aucune ligne de Python ne l'implémente."""
        profile = self._expert_request()
        submit = self._transition(profile, 'submit')

        with self.assertRaises(UserError) as error:
            profile.with_user(self.member_user).workflow_do_transition(submit)
        self.assertIn("CV", str(error.exception))

        self.env['opex.innovation.profile.document'].create({
            'name': "CV.pdf", 'document_type': 'cv',
            'expert_profile_id': profile.id, 'file': b'Y3Y=',
        })
        self._do(profile, 'submit', self.member_user)
        self.assertEqual(self._stage_code(profile), 'submitted')

    def _submitted_request(self):
        profile = self._expert_request()
        self.env['opex.innovation.profile.document'].create({
            'name': "CV.pdf", 'document_type': 'cv',
            'expert_profile_id': profile.id, 'file': b'Y3Y=',
        })
        self._do(profile, 'submit', self.member_user)
        self._do(profile, 'take_in_charge', self.secretariat)
        return profile

    def test_full_path_with_the_complement_loop(self):
        """Le parcours entier, en passant par la boucle de retour.

        C'est le scénario qui distingue un graphe d'une séquence linéaire : le
        dossier revient au contrôle après correction, et il n'y a nulle part un
        compteur de passages ni un `if` pour l'autoriser.
        """
        profile = self._submitted_request()
        self.assertEqual(self._stage_code(profile), 'review')

        # Aller : le contrôleur demande un complément, motif obligatoire.
        with self.assertRaises(UserError):
            self._do(profile, 'request_complement', self.secretariat)
        self._do(profile, 'request_complement', self.secretariat,
                 comment="Merci de joindre vos diplômes.")
        self.assertEqual(self._stage_code(profile), 'complement_requested')
        self.assertEqual(profile.workflow_stage_label,
                         "Action requise sur votre demande")

        # Retour : le membre renvoie sa demande.
        self._do(profile, 'resubmit', self.member_user)
        self.assertEqual(self._stage_code(profile), 'review')

        # Validation.
        self._do(profile, 'validate', self.secretariat)
        self.assertEqual(self._stage_code(profile), 'validated')
        self.assertEqual(profile.workflow_state, 'done')

    def test_validation_activates_the_profile_on_the_partner(self):
        """L'activation est une **action configurée**, pas un `if` métier."""
        profile = self._submitted_request()
        self.assertFalse(self.member.is_expert)

        self._do(profile, 'validate', self.secretariat)

        self.assertTrue(profile.profile_activated)
        self.assertTrue(self.member.is_expert)
        self.assertEqual(self.member.expert_profile_id, profile)

    def test_refusal_closes_without_activating(self):
        profile = self._submitted_request()
        self._do(profile, 'refuse', self.secretariat,
                 comment="Dossier insuffisant.")
        self.assertEqual(self._stage_code(profile), 'refused')
        self.assertEqual(profile.workflow_state, 'done')
        self.assertFalse(profile.profile_activated)
        self.assertFalse(self.member.is_expert)

    def test_history_records_the_whole_path(self):
        profile = self._submitted_request()
        self._do(profile, 'validate', self.secretariat)
        entries = profile.workflow_instance_id.history_ids
        # Entrée + soumission + prise en charge + validation.
        self.assertGreaterEqual(len(entries), 4)
        with self.assertRaises(UserError):
            entries[0].sudo().write({'comment': "réécriture"})

    # ------------------------------------------------------------
    # Rôles
    # ------------------------------------------------------------

    def test_the_member_cannot_validate_his_own_request(self):
        """Le rôle Secrétariat est adossé au groupe du Module 1."""
        profile = self._submitted_request()
        validate = self._transition(profile, 'validate')
        self.assertFalse(
            profile.workflow_instance_id._check_transition_allowed(
                validate, user=self.member_user))

    def test_the_secretariat_holds_its_role_through_the_group(self):
        profile = self._submitted_request()
        validate = self._transition(profile, 'validate')
        self.assertTrue(
            profile.workflow_instance_id._check_transition_allowed(
                validate, user=self.secretariat))

    # ------------------------------------------------------------
    # Profils cumulables (Modification 2)
    # ------------------------------------------------------------

    def test_profiles_are_cumulative(self):
        """Membre + Expert + Investisseur simultanément.

        Trois booléens indépendants : une Selection exclusive obligerait à
        choisir, et c'est précisément ce que le portail refuse.
        """
        self.member.sudo().write({'is_expert': True, 'is_investor': True})
        self.assertTrue(self.member.is_member)
        self.assertTrue(self.member.is_expert)
        self.assertTrue(self.member.is_investor)

    # ------------------------------------------------------------
    # Activation automatique par catégorie (Modification 1)
    # ------------------------------------------------------------

    def _member_in_category(self, subcategory_xmlid, login):
        user = new_test_user(self.env, login=login, groups='base.group_portal')
        partner = user.partner_id
        partner.sudo().write({
            'subcategory_id': self.env.ref(subcategory_xmlid).id,
            'is_member': True,
        })
        return partner

    def test_partners_sponsors_category_opens_the_investor_profile(self):
        partner = self._member_in_category(
            'opex_membership.subcategory_banque', 'inno_bank')
        self.assertTrue(partner.is_investor)
        self.assertFalse(partner.is_expert)

    def test_experts_consultants_category_opens_the_expert_profile(self):
        partner = self._member_in_category(
            'opex_membership.subcategory_cabinet', 'inno_cabinet')
        self.assertTrue(partner.is_expert)
        self.assertFalse(partner.is_investor)

    def test_other_categories_open_nothing(self):
        partner = self._member_in_category(
            'opex_membership.subcategory_pme_pmi', 'inno_pme')
        self.assertFalse(partner.is_expert)
        self.assertFalse(partner.is_investor)

    def test_a_non_member_gets_nothing_even_in_the_right_category(self):
        user = new_test_user(
            self.env, login='inno_candidate', groups='base.group_portal')
        user.partner_id.sudo().subcategory_id = self.env.ref(
            'opex_membership.subcategory_banque').id
        self.assertFalse(user.partner_id.is_investor)

    def test_the_membership_module_is_not_modified(self):
        """Le point d'accroche est `write()` sur res.partner, pas
        `_activate_membership()` du Module 1."""
        source = self.env['opex.membership.file']._activate_membership.__code__
        names = source.co_names
        self.assertNotIn('is_expert', names)
        self.assertNotIn('is_investor', names)

    def test_a_profile_is_never_revoked_automatically(self):
        """Activation automatique, jamais révocation automatique."""
        partner = self._member_in_category(
            'opex_membership.subcategory_banque', 'inno_switch')
        self.assertTrue(partner.is_investor)
        partner.sudo().subcategory_id = self.env.ref(
            'opex_membership.subcategory_pme_pmi').id
        self.assertTrue(partner.is_investor)

    # ------------------------------------------------------------
    # Boutons masqués ET verrou serveur
    # ------------------------------------------------------------

    def test_button_is_hidden_once_the_profile_exists(self):
        self.assertTrue(self.member.opex_can_request_expert())
        self.member.sudo().is_expert = True
        self.assertFalse(self.member.opex_can_request_expert())

    def test_button_is_hidden_while_a_request_is_pending(self):
        self.assertTrue(self.member.opex_can_request_expert())
        self._expert_request()
        self.assertFalse(self.member.opex_can_request_expert())

    def test_button_is_hidden_for_a_non_member(self):
        user = new_test_user(
            self.env, login='inno_visitor', groups='base.group_portal')
        self.assertFalse(user.partner_id.opex_can_request_expert())

    def test_server_refuses_a_duplicate_even_if_the_button_was_bypassed(self):
        """⚠ Le `t-if` masque, il n'interdit pas.

        Une requête forgée n'a jamais vu le gabarit. C'est le bug symétrique
        déjà rencontré sur le Module 1 — « Devenir membre » resté visible pour
        un membre actif — et ce qui manquait n'était pas le `t-if`.
        """
        self._expert_request()
        with self.assertRaises(UserError) as error:
            self.member.opex_check_can_request('expert')
        self.assertIn("déjà en cours", str(error.exception))

    def test_database_constraint_is_the_last_line_of_defence(self):
        self._expert_request()
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.Expert.create({'partner_id': self.member.id})

    def test_a_portal_user_cannot_create_a_request_for_someone_else(self):
        """`create()` impose `partner_id`, quelle que soit la valeur envoyée."""
        other = new_test_user(
            self.env, login='inno_other', groups='base.group_portal')
        profile = self.Expert.with_user(self.member_user).create({
            'partner_id': other.partner_id.id,
            'domaine_expertise': "Tentative",
        })
        self.assertEqual(profile.partner_id, self.member)

    def test_a_portal_user_does_not_see_the_requests_of_others(self):
        self._expert_request()
        other = new_test_user(
            self.env, login='inno_nosy', groups='base.group_portal')
        self.assertFalse(self.Expert.with_user(other).search([]))

    def test_a_portal_user_cannot_edit_a_submitted_request(self):
        profile = self._submitted_request()
        self.env.invalidate_all()
        with self.assertRaises(AccessError):
            profile.with_user(self.member_user).write(
                {'domaine_expertise': "Modifié après coup"})

    # ------------------------------------------------------------
    # Le profil Investisseur suit le même chemin
    # ------------------------------------------------------------

    def test_investor_request_runs_the_same_process(self):
        profile = self.Investor.with_user(self.member_user).create({
            'type_investisseur': 'fonds',
        })

        self.assertEqual(profile.workflow_stage_id.code, 'draft')
        self._do(profile, 'submit', self.member_user)
        self._do(profile, 'take_in_charge', self.secretariat)
        self._do(profile, 'validate', self.secretariat)

        self.assertTrue(self.member.is_investor)
        self.assertEqual(self.member.investor_profile_id, profile)

    def test_investor_ticket_range_is_checked(self):
        with self.assertRaises(UserError):
            self.Investor.create({
                'partner_id': self.member.id,
                'montant_min': 5000000,
                'montant_max': 1000,
            })
