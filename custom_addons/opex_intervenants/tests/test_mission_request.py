from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import tagged
from odoo.tools import mute_logger

from .common import MISSION_CODE, MissionCase

#: Le parcours nominal, du brouillon à la clôture : transition, acteur, étape
#: atteinte. Écrit ici plutôt que déduit de la configuration — un test qui se
#: relit lui-même ne vérifie rien.
NOMINAL_PATH = [
    ('mission_submit', 'client_user', 'qualified'),
    ('mission_start_sourcing', 'manager', 'sourcing'),
    ('mission_open_applications', 'manager', 'open'),
    ('mission_close_applications', 'manager', 'selection'),
    ('mission_award', 'decideur', 'awarded'),
    ('mission_start_contracting', 'secretariat', 'contracting'),
    # Depuis l'Extension 7, cette transition porte la règle 5 du §39 : le
    # contrat doit être validé. Le test intercale donc le cycle du §19 —
    # `_validate_the_contract()` — juste avant. C'est le graphe qui a changé,
    # pas le test : sans cette étape, la mission ne démarre plus, et c'est
    # exactement ce que la règle exige.
    ('mission_start', 'manager', 'in_progress'),
    ('mission_deliver', 'manager', 'delivered'),
    # Depuis l'Extension 9, cette transition porte la règle 6 du §39 **et**
    # la condition que le constat du §28 ait été prononcé. Le test intercale
    # donc le cycle du service fait — `_run_service_acceptance_cycle()` — juste
    # avant, comme il intercale déjà celui du contrat avant `mission_start`.
    # Deux processus s'ouvrent maintenant en cours de route et doivent se
    # conclure avant que la mission continue : c'est ce que valent ces deux
    # lignes de commentaire.
    ('mission_accept_service', 'manager', 'accepted'),
    ('mission_close', 'secretariat', 'closed'),
]


@tagged('post_install', '-at_install')
class TestMissionRequest(MissionCase):
    """Extension 1 — l'appel à mission et sa machine à états configurée."""

    #
    # LA RÈGLE QUI GOUVERNE TOUT LE RESTE
    #

    def test_the_mission_has_no_state_field(self):
        """LA règle du module. Un `state` ici et la démonstration s'effondre.

        Le module ne code aucun workflow, il en configure deux. L'avancement
        d'une mission est `workflow_stage_id`, related sur l'instance, et rien
        d'autre.
        """
        self.assertNotIn('state', self.Mission._fields)
        self.assertIn('workflow_instance_id', self.Mission._fields)
        self.assertIn('workflow_stage_id', self.Mission._fields)

    #: Les noms qu'un champ d'état prendrait s'il revenait sous un pseudonyme.
    _SUSPECT_NAMES = (
        'state', 'etat', 'statut', 'status', 'avancement', 'progression',
        'etape', 'phase', 'stage_id',
    )

    def test_no_field_describes_the_progress_of_the_mission(self):
        """Le corollaire de la règle : l'avancement est porté par le workflow.

        **Ce test a été affiné à l'Extension 8, et dans le sens du plus
        strict.** Il refusait les noms suspects quel que soit le type du
        champ, et il a rougi sur `avancement` — un **Integer** en pourcentage,
        déclaré par l'intervenant dans son point d'avancement (§21). Ce n'est
        pas un état : c'est une donnée que quelqu'un a tapée, pas une position
        que le système dérive.

        Deux corrections plutôt qu'une, parce qu'aucune ne suffisait seule :

        - le champ de la mission s'appelle désormais `avancement_declare`, ce
          qui dit ce qu'il est sans qu'on ait à le demander ;
        - le critère du test est celui qui compte. Un `Selection` portant l'un
          de ces noms est **toujours** refusé, quel qu'en soit le prétexte ; un
          champ de valeur portant `state`, `etat` ou `statut` l'est aussi,
          parce que ces trois-là ne désignent jamais autre chose.

        Le test est ainsi **plus large** qu'avant : `etape` et `phase` en
        `Selection` seraient désormais attrapés, alors que l'ancienne liste les
        laissait passer.
        """
        fields_ = self.Mission._fields

        for suspect in self._SUSPECT_NAMES:
            field = fields_.get(suspect)
            self.assertFalse(
                field is not None and field.type == 'selection',
                "Le champ `%s` est un Selection : c'est un état codé en dur, "
                "et l'avancement d'une mission est porté par le workflow."
                % suspect)

        for absolute in ('state', 'etat', 'statut', 'status', 'stage_id'):
            self.assertNotIn(
                absolute, fields_,
                "Le champ `%s` ne désigne jamais autre chose qu'un état."
                % absolute)

    #
    # LA DÉFINITION CONFIGURÉE
    #

    def test_the_definition_is_published(self):
        """Le piège du `<function>` dans un bloc `noupdate`.

        `_tag_function` saute silencieusement un `<function>` en `noupdate`
        lors d'une mise à jour : la définition resterait en brouillon, donc
        introuvable par `start_workflow()`, sans qu'aucune erreur ne le
        signale. `_get_for_code` ne retient que les définitions publiées — si
        cette ligne passe, la publication a bien été rejouée.
        """
        self.assertEqual(self.mission_definition.state, 'published')
        self.assertEqual(self.mission_definition.code, MISSION_CODE)
        self.assertEqual(
            self.mission_definition.model_name, 'opex.mission.request')

    def test_fourteen_stages_and_thirty_two_transitions(self):
        definition = self.mission_definition
        self.assertEqual(len(definition.stage_ids), 14)
        self.assertEqual(len(definition.transition_ids), 32)

    def test_the_eleven_stages_of_the_specification_are_present(self):
        """§12.1, à la lettre : les onze étapes plus les trois branches."""
        expected = {
            'draft', 'qualified', 'sourcing', 'open', 'selection', 'awarded',
            'contracting', 'in_progress', 'delivered', 'accepted', 'closed',
            'on_hold', 'cancelled', 'unsuccessful',
        }
        codes = set(self.mission_definition.stage_ids.mapped('code'))
        self.assertEqual(codes, expected)

    def test_the_graph_is_valid(self):
        """Le moteur revalide : une seule entrée, des fins, aucun cul-de-sac."""
        self.assertTrue(self.mission_definition.sudo()._check_graph())

    def test_one_start_and_three_ends(self):
        stages = self.mission_definition.stage_ids
        self.assertEqual(stages.filtered('is_start').mapped('code'), ['draft'])
        self.assertEqual(
            set(stages.filtered('is_end').mapped('code')),
            {'closed', 'cancelled', 'unsuccessful'})

    def test_on_hold_is_not_terminal_and_has_two_ways_back(self):
        """Une suspension qui ne se lève pas est un cul-de-sac déguisé.

        Deux reprises distinctes, et non une : une mission suspendue pendant la
        validation de ses livrables ne doit pas repartir en exécution.
        """
        on_hold = self.mission_definition.stage_ids.filtered(
            lambda s: s.code == 'on_hold')
        self.assertFalse(on_hold.is_end)
        targets = set(on_hold.transition_out_ids.mapped('target_stage_id.code'))
        self.assertEqual(targets, {'in_progress', 'delivered', 'cancelled'})

    def test_every_stage_has_a_user_label(self):
        """Le client ne lit jamais un code technique.

        C'est ce qui permet à la table de correspondance du CLAUDE.md de tenir :
        les noms d'états du document UX survivent en libellés d'affichage.
        """
        without = self.mission_definition.stage_ids.filtered(
            lambda s: not s.user_label)
        self.assertFalse(
            without,
            "Étapes sans libellé utilisateur : %s"
            % ", ".join(without.mapped('code')))

    def test_the_selection_stage_has_four_exits(self):
        """Une étape à une seule sortie ferait de ce graphe une file."""
        selection = self.mission_definition.stage_ids.filtered(
            lambda s: s.code == 'selection')
        self.assertEqual(len(selection.transition_out_ids), 4)

    def test_every_refusal_requires_a_written_reason(self):
        """Sans motif, l'intéressé reçoit une décision qu'il ne peut pas corriger."""
        must_explain = {
            'mission_request_complement', 'mission_reject_request',
            'mission_sourcing_unsuccessful', 'mission_open_unsuccessful',
            'mission_selection_unsuccessful', 'mission_back_to_selection',
            'mission_reopen', 'mission_contracting_failed',
            'mission_request_corrections', 'mission_hold_progress',
            'mission_hold_delivered', 'mission_cancel_progress',
            'mission_cancel_hold', 'mission_award', 'mission_close',
        }
        for code in must_explain:
            transition = self._transition(self.mission_definition, code)
            self.assertTrue(
                transition.requires_comment,
                "La transition « %s » devrait exiger un motif écrit." % code)

    #
    # UN TEST DU MOTEUR N'EST JAMAIS SEUL EN BASE
    #

    def test_stage_codes_are_shared_with_other_modules(self):
        """La preuve que borner les `search()` n'est pas une précaution théorique.

        `opex_innovation` publie sept définitions et utilise lui aussi le code
        `draft`. Un `search([('code', '=', 'draft')])` non borné en ramène donc
        plusieurs, et un test qui s'y fierait mesurerait l'étape d'un autre
        module. Toutes les recherches de cette suite passent par
        `_transition()`, qui filtre sur la définition.
        """
        globally = self.Stage.sudo().search([('code', '=', 'draft')])
        self.assertGreater(
            len(globally), 1,
            "Si ce test échoue, c'est que les autres modules ne sont pas "
            "installés : il perd alors sa valeur de garde-fou.")
        ours = globally.filtered(
            lambda s: s.definition_id == self.mission_definition)
        self.assertEqual(len(ours), 1)

    #
    # LA CRÉATION
    #

    def test_the_reference_comes_from_the_sequence(self):
        """Le préfixe, l'année, et un compteur numérique. Pas une longueur.

        Ce test affirmait `len(name) == len("MIS-2026-0001")`, et il a rougi
        avec `14 != 13` le jour où le compteur a dépassé 9999 : la séquence
        passe alors à cinq chiffres, ce qui est le comportement correct.

        Le défaut n'était pas dans la séquence, il était dans le test : il
        mesurait une longueur qui dépend du **nombre de missions que la base
        contient**, c'est-à-dire de tout ce que d'autres tests et jeux de
        démonstration y ont mis. Un test du moteur n'est jamais seul en base,
        et cela vaut aussi pour les compteurs.

        Ce qui compte et qui ne périmera pas : le préfixe, l'année en cours,
        et un suffixe entièrement numérique d'au moins quatre chiffres - le
        `padding` posé à l'Extension 1.
        """
        mission = self._new_mission()
        year = fields.Date.context_today(self.Mission).year
        prefix = "MIS-%s-" % year

        self.assertTrue(
            mission.name.startswith(prefix),
            "Référence inattendue : %s" % mission.name)

        compteur = mission.name[len(prefix):]
        self.assertTrue(
            compteur.isdigit(),
            "Le suffixe de « %s » n'est pas un compteur." % mission.name)
        self.assertGreaterEqual(
            len(compteur), 4,
            "Le `padding` de la séquence est tombé sous quatre chiffres.")

    def test_two_missions_get_two_references(self):
        first = self._new_mission()
        second = self._new_mission()
        self.assertNotEqual(first.name, second.name)

    def test_the_display_name_is_the_header_of_the_ux_document(self):
        """§40 : « MISSION #MIS-2026-001 — Audit cybersécurité »."""
        mission = self._new_mission()
        self.assertEqual(
            mission.display_name, "%s — Audit cybersécurité" % mission.name)

    def test_the_workflow_starts_on_creation(self):
        mission = self._new_mission()
        self.assertTrue(mission.workflow_instance_id)
        self.assertEqual(mission.workflow_definition_id, self.mission_definition)
        self.assertEqual(self._stage(mission), 'draft')
        self.assertEqual(mission.workflow_state, 'running')

    def test_create_forces_the_client_for_a_portal_user(self):
        """Le verrou du Module 1, reconduit : ne pas afficher un champ ne
        protège de rien, c'est le serveur qui doit le réécrire."""
        mission = self._new_mission(
            user=self.client_user,
            client_id=self.other_client.partner_id.id,
        )
        self.assertEqual(
            mission.sudo().client_id, self.client_user.partner_id,
            "Un compte portail a réussi à déposer une demande au nom d'un autre.")

    def test_an_internal_user_may_open_a_call_for_a_client(self):
        """§9 — le gestionnaire ouvre l'appel pour le compte du client."""
        mission = self._new_mission(user=self.manager)
        self.assertEqual(mission.client_id, self.client_user.partner_id)

    #
    # L'ACTEUR EST POSÉ DEPUIS `client_id`, PAS DEPUIS LE CRÉATEUR
    #

    def test_the_client_is_actor_and_the_creator_is_not(self):
        """La raison pour laquelle `initiator_role_id` est laissé vide.

        Le moteur poserait l'acteur sur celui qui exécute le `create()`
        (`workflow_definition.py:89-97`). Quand le gestionnaire ouvre un appel
        pour un client, c'est **lui** qui recevrait le rôle `client` en accès
        `full` sur ce dossier.

        Assertion positive d'abord — le client est bien acteur — puis
        l'assertion négative, qui ne vaudrait rien seule.
        """
        mission = self._new_mission(user=self.manager)
        actors = mission.sudo().workflow_instance_id.actor_ids

        client_lines = actors.filtered(
            lambda a: a.user_id == self.client_user)
        self.assertEqual(len(client_lines), 1)
        self.assertEqual(client_lines.role_id.code, 'client')
        self.assertEqual(client_lines.access_level, 'full')

        self.assertFalse(
            actors.filtered(lambda a: a.user_id == self.manager),
            "Le créateur a hérité d'un rôle d'acteur sur le dossier d'un autre.")

    def test_the_retained_expert_becomes_actor_of_the_mission(self):
        """Ce test a rougi, et c'était sa raison d'être.

        L'Extension 1 l'avait écrit à l'envers, sous le nom
        `test_the_retained_expert_is_not_yet_actor_of_the_mission`, en
        annonçant qu'il rougirait à l'Extension 7 — un manque déclaré, avec
        son propriétaire, plutôt qu'un manque masqué. L'Extension 7 a posé
        l'acteur, il a rougi, il est réécrit.

        C'est le même mécanisme que
        `test_the_orphans_are_exactly_the_three_of_extension_16` du Module 2 :
        une assertion sur l'état du module doit **changer** quand cet état
        change, jamais rester vraie par omission.

        Le détail de la portée — `limited` sur la mission, `full` sur la
        candidature — est vérifié par `test_contracting.py`, qui possède le
        sujet. Ici, seul le fait compte.
        """
        mission = self._new_mission()
        self._open_the_call(mission)
        application = self._select_the_application(
            self._new_application(mission))
        self.assertEqual(self._stage(application), 'selected')

        mission_actors = mission.sudo().workflow_instance_id.actor_ids
        self.assertTrue(
            mission_actors.filtered(lambda a: a.role_id.code == 'client'),
            "Le client doit être acteur de la mission dès sa création.")
        self.assertTrue(
            mission_actors.filtered(lambda a: a.role_id.code == 'intervenant'),
            "L'intervenant retenu n'est pas acteur de la mission : les "
            "transitions qui lui sont ouvertes — « Démarrer la mission », "
            "« Soumettre les livrables » — restent hors de sa portée.")

        application_actors = \
            application.sudo().workflow_instance_id.actor_ids
        self.assertTrue(
            application_actors.filtered(
                lambda a: a.role_id.code == 'intervenant'),
            "L'intervenant doit être acteur de sa propre candidature.")

    def test_the_definition_declares_no_initiator_role(self):
        """Le corollaire, vérifié sur la configuration elle-même."""
        self.assertFalse(
            self.mission_definition.sudo().initiator_role_id,
            "`initiator_role_id` renseigné : le créateur héritera du rôle du "
            "client sur les appels ouverts pour le compte d'un tiers.")

    def test_the_client_reads_his_own_instance_without_sudo(self):
        """La ligne d'acteur sert à quelque chose : elle ouvre le dossier.

        Assertion positive puis négative — un autre client portail, lui, ne
        doit rien voir.

        La négative **lit un champ**, elle n'appelle pas `exists()`.
        `exists()` ne fait qu'un `SELECT id` et n'applique **aucune**
        `ir.rule` : écrit avec lui, ce test passait au vert en prouvant
        seulement que la ligne existe en base. C'est exactement l'assertion
        négative sans valeur du §7 du CLAUDE.md, et elle m'a eu.
        """
        mission = self._new_mission()
        instance = mission.workflow_instance_id

        as_client = instance.with_user(self.client_user)
        self.assertEqual(as_client.current_stage_id.code, 'draft')

        with self.assertRaises(AccessError):
            instance.with_user(self.other_client).current_stage_id

    #
    # LE PARCOURS COMPLET
    #

    def test_the_nominal_path_runs_end_to_end(self):
        """Le critère d'arrêt de l'Extension 1, automatisé.

        Dix transitions, six acteurs différents, deux workflows en parallèle :
        la mission ne peut atteindre `awarded` que si une candidature a été
        retenue de son côté.
        """
        mission = self._new_mission()
        application = None

        for code, actor_name, expected_stage in NOMINAL_PATH:
            # Les candidatures se déposent pendant que l'appel est ouvert.
            if code == 'mission_close_applications':
                application = self._new_application(mission)
                self._select_the_application(application)

            # La règle 5 du §39, rattachée par l'Extension 7 : sans un
            # contrat validé, « Démarrer la mission » refuse. Le cycle du §19
            # se déroule donc ici, sur le sous-workflow lancé à l'étape
            # précédente.
            if code == 'mission_start':
                self._run_contract_cycle(mission)

            # La règle 6 du §39 et la condition du constat, rattachées par
            # l'Extension 9 : sans un service fait validé par le cluster puis
            # par le client, « Valider le service fait » refuse.
            if code == 'mission_accept_service':
                self._run_service_acceptance_cycle(mission)

            self._do(mission, code, getattr(self, actor_name),
                     comment="Étape franchie par le test.")
            self.assertEqual(
                self._stage(mission), expected_stage,
                "Après « %s », la mission devrait être en « %s »."
                % (code, expected_stage))

        self.assertEqual(mission.sudo().workflow_state, 'done')
        self.assertTrue(mission.sudo().workflow_instance_id.date_end)
        # La candidature, elle, a sa propre fin, atteinte séparément.
        self.assertEqual(self._stage(application), 'selected')

    def test_the_complement_loop_passes_twice_through_draft(self):
        """La boucle du Schéma 3, que ni le §38 ni le §12.1 ne nomment.

        Comptée sur une compréhension : `mapped()` sur un Many2one déduplique
        et rendrait le second passage invisible — le test serait vert et ne
        vérifierait rien.
        """
        mission = self._new_mission()
        self._do(mission, 'mission_submit', self.client_user)
        self._do(mission, 'mission_request_complement', self.secretariat,
                 comment="Le périmètre technique n'est pas décrit.")
        self.assertEqual(self._stage(mission), 'draft')

        self._do(mission, 'mission_submit', self.client_user)
        self.assertEqual(self._stage(mission), 'qualified')

        visited = self._visited(mission)
        self.assertEqual(
            visited.count('draft'), 2,
            "Le dossier doit être passé deux fois par le brouillon : "
            "à l'ouverture, puis au retour du complément. Historique : %s"
            % visited)
        self.assertEqual(visited.count('qualified'), 2)

    def test_the_client_recovers_the_right_to_write_after_a_complement(self):
        """La boucle n'aurait aucun intérêt si le retour ne rendait pas la main.

        C'est la raison pour laquelle le retour se fait en `draft` et non dans
        une étape dédiée : l'`ir.rule` d'écriture y est déjà bornée.
        """
        mission = self._new_mission(user=self.client_user)
        self._do(mission, 'mission_submit', self.client_user)

        with self.assertRaises(AccessError):
            mission.with_user(self.client_user).write({'objectifs': "Modifié"})

        self._do(mission, 'mission_request_complement', self.secretariat,
                 comment="Précisez les objectifs.")
        mission.with_user(self.client_user).write({'objectifs': "Objectifs précisés."})
        self.assertEqual(mission.sudo().objectifs, "Objectifs précisés.")

    def test_the_corrections_loop_returns_to_execution(self):
        """§25 — le responsable renvoie les livrables à corriger."""
        mission = self._run_to_stage('delivered')
        self._do(mission, 'mission_request_corrections', self.manager,
                 comment="Le rapport ne couvre pas le périmètre réseau.")
        self.assertEqual(self._stage(mission), 'in_progress')

        self._do(mission, 'mission_deliver', self.manager)
        visited = self._visited(mission)
        self.assertEqual(visited.count('in_progress'), 2)
        self.assertEqual(visited.count('delivered'), 2)

    def test_the_suspension_can_be_lifted_where_it_started(self):
        mission = self._run_to_stage('delivered')
        self._do(mission, 'mission_hold_delivered', self.manager,
                 comment="Le client est indisponible jusqu'au mois prochain.")
        self.assertEqual(self._stage(mission), 'on_hold')

        self._do(mission, 'mission_resume_delivered', self.manager)
        self.assertEqual(self._stage(mission), 'delivered')

    #
    # LES CONDITIONS
    #

    def test_submission_is_blocked_while_the_file_is_incomplete(self):
        # On retire les compétences et non les objectifs : `objectifs` est
        # `required=True`, donc la création échouerait en base avant que la
        # condition de transition ait la moindre occasion de se prononcer. Le
        # champ retiré doit être facultatif au niveau du modèle et exigé au
        # niveau du processus — c'est précisément ce que la règle apporte.
        mission = self._new_mission(skill_ids=[(6, 0, [])])
        with self.assertRaises(UserError) as error:
            self._do(mission, 'mission_submit', self.client_user)
        self.assertIn("Complétez le titre", str(error.exception))
        self.assertEqual(self._stage(mission), 'draft')

    def test_publication_is_blocked_without_a_deadline(self):
        mission = self._new_mission(date_limite_candidature=False)
        self._do(mission, 'mission_submit', self.client_user)
        with self.assertRaises(UserError) as error:
            self._do(mission, 'mission_start_sourcing', self.manager)
        self.assertIn("date limite de candidature", str(error.exception))

    def test_publication_is_blocked_when_the_deadline_has_passed(self):
        """La condition qui existe parce que `safe_eval` n'a pas de date.

        `_BUILTINS` n'expose ni `datetime` ni `time` : une expression ne peut
        pas comparer à aujourd'hui. Le fait est calculé par le modèle, dans un
        champ **non stocké** — donc réévalué à chaque lecture.
        """
        mission = self._new_mission()
        self._do(mission, 'mission_submit', self.client_user)
        yesterday = fields.Date.context_today(self.Mission) - timedelta(days=1)
        mission.sudo().write({
            'date_debut_souhaitee': False,
            'date_fin_souhaitee': False,
            'date_limite_candidature': yesterday,
        })
        self.assertFalse(mission.sudo().date_limite_is_open)

        with self.assertRaises(UserError) as error:
            self._do(mission, 'mission_start_sourcing', self.manager)
        self.assertIn("déjà passée", str(error.exception))

    def test_closing_applications_needs_at_least_one(self):
        mission = self._new_mission()
        self._open_the_call(mission)
        with self.assertRaises(UserError) as error:
            self._do(mission, 'mission_close_applications', self.manager)
        self.assertIn("Aucune candidature", str(error.exception))

    def test_an_invitation_is_not_a_received_application(self):
        """Les trois premières étapes ne comptent pas comme une candidature.

        Une invitation envoyée n'ouvre pas le droit de clore les candidatures :
        « candidatures reçues » du §15 commence au dépôt.
        """
        mission = self._new_mission()
        self._open_the_call(mission)
        self._new_application(mission)

        self.assertEqual(mission.sudo().application_count, 1)
        self.assertEqual(mission.sudo().received_application_count, 0)
        with self.assertRaises(UserError):
            self._do(mission, 'mission_close_applications', self.manager)

    #
    # RÈGLE 4 DU §39 — LE POINT DE CONTACT ENTRE LES DEUX MACHINES
    #

    def test_award_is_blocked_without_a_selected_application(self):
        mission = self._new_mission()
        self._open_the_call(mission)
        self._apply(self._new_application(mission))
        self._do(mission, 'mission_close_applications', self.manager)

        with self.assertRaises(UserError) as error:
            self._do(mission, 'mission_award', self.decideur, comment="Choix.")
        self.assertIn("Retenez d'abord une candidature", str(error.exception))

    def test_award_is_blocked_with_two_selected_applications(self):
        """Règle 4 : une seule candidature retenue, sauf type multi-intervenants.

        La seconde sélection est bloquée côté candidature ; on force donc l'état
        en base pour vérifier que la mission refuse aussi. Les deux verrous
        existent, et c'est voulu : celui de la candidature empêche le geste,
        celui de la mission rattrape une donnée incohérente.
        """
        mission = self._new_mission()
        self._open_the_call(mission)
        first = self._select_the_application(self._new_application(mission))
        second = self._new_application(
            mission, partner=self.other_intervenant.partner_id)
        self._apply(second, user=self.other_intervenant)
        self._do(second, 'application_screen', self.manager)
        self._do(second, 'application_shortlist', self.manager)

        # Premier verrou : la candidature refuse la seconde sélection.
        with self.assertRaises(UserError):
            self._do(second, 'application_select', self.decideur,
                     comment="Second choix.")
        self.assertEqual(self._stage(second), 'shortlisted')

        # On force l'étape en base pour éprouver le **second** verrou, celui de
        # la mission. Les deux existent, et c'est voulu : celui de la
        # candidature empêche le geste, celui de la mission rattrape une donnée
        # devenue incohérente — reprise, import, correction manuelle.
        selected_stage = first.sudo().workflow_stage_id
        second.sudo().workflow_instance_id.write(
            {'current_stage_id': selected_stage.id})
        mission.invalidate_recordset()
        self.assertEqual(mission.sudo().selected_application_count, 2)

        self._do(mission, 'mission_close_applications', self.manager)
        with self.assertRaises(UserError) as error:
            self._do(mission, 'mission_award', self.decideur, comment="Choix.")
        self.assertIn("un seul intervenant", str(error.exception))

    def test_award_accepts_several_when_the_type_allows_it(self):
        """L'exception explicite de la règle 4, portée par le référentiel."""
        mission = self._new_mission(mission_type_id=self.mission_type_multi.id)
        self._open_the_call(mission)
        self._select_the_application(self._new_application(mission))
        self._select_the_application(
            self._new_application(
                mission, partner=self.other_intervenant.partner_id),
            user=self.other_intervenant)

        mission.invalidate_recordset()
        self.assertEqual(mission.sudo().selected_application_count, 2)
        self._do(mission, 'mission_close_applications', self.manager)
        self._do(mission, 'mission_award', self.decideur,
                 comment="Deux formateurs retenus.")
        self.assertEqual(self._stage(mission), 'awarded')

    #
    # LES RÔLES
    #

    def test_the_client_cannot_publish_his_own_call(self):
        """§8 : « une demande créée par le client ne devient pas
        automatiquement publique »."""
        mission = self._new_mission()
        self._do(mission, 'mission_submit', self.client_user)
        with self.assertRaises(UserError) as error:
            self._do(mission, 'mission_start_sourcing', self.client_user)
        self.assertIn("réservée", str(error.exception))
        self.assertEqual(self._stage(mission), 'qualified')

    def test_the_manager_cannot_award_alone(self):
        """L'attribution appartient au comité, pas au responsable."""
        mission = self._new_mission()
        self._open_the_call(mission)
        self._select_the_application(self._new_application(mission))
        self._do(mission, 'mission_close_applications', self.manager)

        with self.assertRaises(UserError):
            self._do(mission, 'mission_award', self.manager, comment="Choix.")
        self._do(mission, 'mission_award', self.decideur, comment="Choix.")
        self.assertEqual(self._stage(mission), 'awarded')

    def test_a_refusal_without_a_reason_is_refused(self):
        mission = self._new_mission()
        self._do(mission, 'mission_submit', self.client_user)
        with self.assertRaises(UserError) as error:
            self._do(mission, 'mission_reject_request', self.manager)
        self.assertIn("motif écrit", str(error.exception))

    #
    # `is_published` — LA PROJECTION, PAS UN SECOND ÉTAT
    #

    def test_is_published_follows_the_workflow(self):
        mission = self._new_mission()
        self.assertFalse(mission.is_published)

        self._do(mission, 'mission_submit', self.client_user)
        self.assertFalse(mission.sudo().is_published)

        self._do(mission, 'mission_start_sourcing', self.manager)
        self.assertTrue(mission.sudo().is_published)

        self._do(mission, 'mission_open_applications', self.manager)
        self.assertTrue(mission.sudo().is_published)

    def test_is_published_is_computed_and_stored(self):
        """Stocké pour être filtrable, calculé pour ne pas pouvoir mentir."""
        field = self.Mission._fields['is_published']
        self.assertTrue(field.compute)
        self.assertTrue(field.store)
        self.assertTrue(field.readonly)

    #
    # CONTRAINTES DE DONNÉES
    #

    @mute_logger('odoo.sql_db')
    def test_the_end_date_cannot_precede_the_start_date(self):
        today = fields.Date.context_today(self.Mission)
        with self.assertRaises(ValidationError):
            self._new_mission(
                date_debut_souhaitee=today + timedelta(days=60),
                date_fin_souhaitee=today + timedelta(days=45),
                date_limite_candidature=today + timedelta(days=30),
            )

    @mute_logger('odoo.sql_db')
    def test_the_deadline_cannot_follow_the_start_date(self):
        today = fields.Date.context_today(self.Mission)
        with self.assertRaises(ValidationError):
            self._new_mission(
                date_debut_souhaitee=today + timedelta(days=10),
                date_fin_souhaitee=today + timedelta(days=60),
                date_limite_candidature=today + timedelta(days=30),
            )

    #
    # LES TROIS RÈGLES DIFFÉRÉES
    #

    def test_the_deferred_rules_are_attached_when_their_object_exists(self):
        """Ce test a rougi à l'Extension 7, et c'était sa raison d'être.

        Il affirmait que les **trois** règles différées étaient déclarées et
        rattachées à rien. La règle 5 a trouvé son objet — la définition
        `mission_contract` existe — et l'affirmation est devenue fausse. Elle
        n'est pas retirée : elle est retournée, règle par règle, et il reste
        deux règles à surveiller pour l'Extension 8.

        La raison d'origine tient toujours pour ces deux-là :
        `field('deliverable_pending_count', 1)` vaut 1 tant que le champ
        n'existe pas, donc la condition est **fermée**. Attachée maintenant,
        elle rendrait « Soumettre les livrables » infranchissable.
        """
        Rule = self.env['opex.workflow.rule'].sudo()
        transitions = self.mission_definition.sudo().transition_ids

        def attached_to(code):
            rule = Rule.search([('code', '=', code)])
            self.assertEqual(len(rule), 1, "Règle « %s » absente." % code)
            return transitions.filtered(lambda t: rule in t.condition_ids)

        # La règle 5 : son objet existe depuis l'Extension 7, elle est en place.
        self.assertEqual(
            attached_to('mission_contract_validated').mapped('code'),
            ['mission_start'],
            "La règle 5 du §39 n'est pas — ou plus — la garde de "
            "« Démarrer la mission ».")

        # La condition de dépôt : son champ existe depuis l'Extension 8.
        self.assertEqual(
            attached_to('mission_deliverables_submitted').mapped('code'),
            ['mission_deliver'],
            "La condition de dépôt des livrables n'est pas — ou plus — la "
            "garde de « Soumettre les livrables ».")

        # La règle 6 a trouvé son objet à l'Extension 9, et ce test a rougi
        # ce jour-là — c'est ce qu'on lui demandait. Il n'est pas retiré, il
        # est **retourné** : il affirme désormais le rattachement, et il
        # rougira de nouveau si quelqu'un le défait.
        #
        # Et il en affirme **deux**. Le même enregistrement de règle garde
        # « Valider le service fait » sur la mission et « Valider (cluster) »
        # sur le constat — les deux endroits où « terminé » se décide. Une
        # règle jumelle écrite pour le constat aurait divergé de celle-ci au
        # premier ajustement, sans que rien ne le signale (règle 16).
        self.assertEqual(
            attached_to('mission_deliverables_validated').mapped('code'),
            ['mission_accept_service'],
            "La règle 6 du §39 n'est pas — ou plus — la garde de « Valider le "
            "service fait ».")

        acceptance_definition = self.env['opex.workflow.definition'].sudo() \
            ._get_for_code('mission_service_acceptance')
        rule = Rule.search([('code', '=', 'mission_deliverables_validated')])
        guarded = acceptance_definition.transition_ids.filtered(
            lambda t: rule in t.condition_ids)
        self.assertEqual(
            guarded.mapped('code'), ['service_validate_cluster'],
            "La règle 6 ne garde plus la validation du cluster : le constat "
            "de service fait pourrait être prononcé sur des livrables non "
            "validés.")

    def test_a_condition_on_a_missing_field_fails_closed(self):
        """Une condition qu'on ne sait pas évaluer refuse, elle n'autorise pas.

        **Ce test a été réécrit à l'Extension 8.** Il portait sur les deux
        règles de livrables et vérifiait qu'elles étaient fermées *faute de
        champ*. Leur champ existe désormais : l'affirmation est devenue
        fausse, le test a rougi, et c'est ce qu'on lui demandait.

        Ce qui reste — et qui, lui, ne périmera pas — c'est **l'idiome** :
        `_field(name, default)` renvoie son défaut quand le champ n'existe pas
        (`workflow_instance.py:251`), et le défaut choisi décide de ce qui se
        passe pendant qu'on attend l'extension suivante.

        Le test le démontre dans les deux sens, sur un champ qui n'existera
        jamais. Sans le défaut à 1, la comparaison est `False == 0` — vrai en
        Python — et une condition censée protéger une transition la laisse
        passer, sans le dire.
        """
        mission = self._new_mission()
        instance = mission.sudo().workflow_instance_id

        # Sans défaut : le piège. La condition passe alors qu'elle ne sait rien.
        self.assertTrue(
            instance._evaluate_expression(
                "field('un_champ_qui_n_existe_pas') == 0"),
            "Le piège `False == 0` a disparu : relire cette note avant de "
            "retirer les défauts des règles différées.")

        # Avec un défaut à 1 : elle refuse, ce qui est le côté sûr.
        self.assertFalse(
            instance._evaluate_expression(
                "field('un_champ_qui_n_existe_pas', 1) == 0"),
            "Une condition portant sur un champ absent devrait refuser.")

    def test_the_remaining_deferred_rule_still_uses_the_safe_default(self):
        """La règle 6 attend l'Extension 9 avec son défaut intact.

        Son champ existe depuis l'Extension 8, donc le défaut ne sert plus à
        rien aujourd'hui — mais le retirer ferait de l'expression un piège
        pour la prochaine règle écrite sur le même modèle. Il reste, et ce
        test dit pourquoi.
        """
        rule = self.env['opex.workflow.rule'].sudo().search(
            [('code', '=', 'mission_deliverables_validated')])
        self.assertEqual(len(rule), 1)
        self.assertIn(
            "', 1)", rule.expression,
            "La règle 6 a perdu son défaut de repli : écrite "
            "`field('x') == 0`, elle passerait sur un champ absent.")

    # ------------------------------------------------------------
    # Utilitaire
    # ------------------------------------------------------------

    def _run_to_stage(self, target_code):
        """Déroule le parcours nominal jusqu'à l'étape demandée.

        Deux cycles s'intercalent dans le parcours, et pour la même raison :
        une transition porte une condition qu'un autre processus doit d'abord
        satisfaire.

        - le cycle du §19 avant « Démarrer la mission » (règle 5, Extension 7) ;
        - le cycle du §28 avant « Valider le service fait » (règle 6 et constat
          de service fait, Extension 9).

        Dans les deux cas c'est le graphe qui a changé, pas le test.
        """
        mission = self._new_mission()
        for code, actor_name, stage in NOMINAL_PATH:
            if code == 'mission_close_applications':
                self._select_the_application(self._new_application(mission))
            if code == 'mission_start':
                self._run_contract_cycle(mission)
            if code == 'mission_accept_service':
                self._run_service_acceptance_cycle(mission)
            self._do(mission, code, getattr(self, actor_name),
                     comment="Étape franchie par le test.")
            if stage == target_code:
                return mission
        raise AssertionError("Étape « %s » absente du parcours." % target_code)
