from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import tagged

from .common import MissionCase

CONTRACT_CODE = 'mission_contract'


@tagged('post_install', '-at_install')
class TestContracting(MissionCase):
    """Extension 7 — sélection, affectation, contrat, ordre de mission.

    C'est le jalon P0 du §20 : une mission naît d'un besoin client et aboutit
    à un intervenant sélectionné avec son contrat généré.
    """

    # ------------------------------------------------------------
    # Fabriques propres à l'extension
    # ------------------------------------------------------------

    def _award_the_mission(self, mission=None, **overrides):
        """Du brouillon à « Mission attribuée », avec un intervenant retenu."""
        mission = mission or self._new_mission(**overrides)
        self._open_the_call(mission)
        application = self._select_the_application(
            self._new_application(mission))
        self._do(mission, 'mission_close_applications', self.manager)
        self._do(mission, 'mission_award', self.decideur,
                 comment="Candidature retenue par le comité.")
        return mission, application

    # `_contract_instance`, `_do_contract` et `_validate_the_contract` vivent
    # dans `common.py` : le parcours nominal de l'Extension 1 en dépend
    # désormais, la règle 5 étant rattachée à « Démarrer la mission ».

    #
    # LA RÈGLE QUI GOUVERNE TOUT LE RESTE, SUR LES DEUX NOUVEAUX MODÈLES
    #

    def test_neither_the_assignment_nor_the_contract_has_a_state_field(self):
        """Les deux nouveaux modèles suivent la règle des deux modèles centraux.

        L'affectation n'a pas d'avancement propre — le sien se lit sur la
        mission. La pièce contractuelle non plus : son cycle de validation est
        le sous-workflow `mission_contract`.

        On vérifie aussi les synonymes. Un `state` renommé `etat` ou
        `statut` serait le même défaut sous un autre nom.
        """
        for model_name in ('opex.mission.assignment', 'opex.mission.contract'):
            fields = self.env[model_name]._fields
            for suspect in ('state', 'etat', 'statut', 'stage', 'avancement'):
                self.assertNotIn(
                    suspect, fields,
                    "« %s » porte un champ « %s » : l'avancement se lit sur "
                    "le workflow, pas sur le modèle." % (model_name, suspect))

    #
    # §13 — LE DÉCLENCHEMENT EST CONFIGURÉ, PAS CODÉ
    #

    def test_the_selection_effects_are_configured_on_the_transition(self):
        """La configuration **est** la preuve.

        Si ces actions n'étaient pas sur la transition, les effets du §13
        seraient déclenchés depuis du Python quelque part, et il faudrait le
        chercher. Le test lit donc la configuration, pas le résultat : c'est
        elle qui doit porter la décision.
        """
        transition = self._transition(
            self.application_definition, 'application_select')
        codes = {action.code for action in transition.sudo().action_ids}

        self.assertIn('application_notify_selected', codes)
        self.assertIn('application_trigger_selection', codes)
        self.assertIn('application_task_contract', codes)

        trigger = transition.sudo().action_ids.filtered(
            lambda a: a.code == 'application_trigger_selection')
        self.assertEqual(trigger.action_type, 'set_field')
        self.assertEqual(trigger.field_id.name, 'operational_trigger')
        self.assertEqual(trigger.field_id.model, 'opex.mission.application')

    def test_the_trigger_keeps_no_memory(self):
        """Un déclencheur, pas un état : il ne conserve aucune valeur.

        Assertion positive d'abord — l'effet a bien eu lieu — sans quoi
        « le champ est faux » serait aussi vrai sur une transition qui n'a
        rien déclenché du tout.
        """
        mission, application = self._award_the_mission()
        self.assertTrue(
            application.sudo().assignment_id,
            "La sélection n'a produit aucune affectation.")
        self.assertFalse(
            application.sudo().operational_trigger,
            "Le déclencheur a gardé sa valeur : c'est un état déguisé.")

    def test_no_operational_method_moves_a_workflow(self):
        """La ligne à ne pas franchir, vérifiée sur le **code**.

        Le Python implémente les effets ; il ne décide jamais d'une
        transition. Un `do_transition()` dans un déclencheur rendrait la
        configuration décorative — le workflow avancerait tout seul, et
        « l'IA recommande, l'humain décide » ne voudrait plus rien dire.

        Docstrings et commentaires sont **retirés avant l'examen**, et
        c'est le test lui-même qui l'a appris : écrit en `grep` sur le
        fichier, il rougissait sur sa propre prose — le module explique
        justement, en toutes lettres, qu'il n'appelle pas `do_transition()`.
        Un test qui interdit un mot interdit aussi qu'on en parle, et il
        aurait fini par faire supprimer l'explication plutôt que le défaut.

        Chaque méthode définie dans `mission_operational.py` est examinée,
        pas seulement les `_trigger_*` : ce sont leurs helpers qui feraient le
        travail, si quelqu'un devait le faire.
        """
        import inspect
        import re

        from ..models import mission_operational

        def code_only(function):
            """Le corps, sans docstring ni commentaire."""
            source = inspect.getsource(function)
            source = re.sub(r'("""|\'\'\')(?:.|\n)*?\1', '', source)
            return re.sub(r'#[^\n]*', '', source)

        forbidden = ('do_transition', 'workflow_do_transition',
                     'current_stage_id =', "write({'workflow_")
        examined = 0

        for klass in vars(mission_operational).values():
            if not inspect.isclass(klass) \
                    or klass.__module__ != mission_operational.__name__:
                continue
            for name, attribute in vars(klass).items():
                if not inspect.isfunction(attribute):
                    continue
                examined += 1
                body = code_only(attribute)
                for word in forbidden:
                    self.assertNotIn(
                        word, body,
                        "`%s.%s` contient « %s » : un déclencheur fait "
                        "avancer un workflow au lieu de se contenter de son "
                        "effet." % (klass.__name__, name, word))

        # L'assertion positive, sans laquelle la boucle ci-dessus passerait
        # au vert sur zéro méthode examinée — le mode de défaillance le plus
        # coûteux du projet.
        self.assertGreaterEqual(
            examined, 10,
            "Seules %s méthodes ont été examinées : la boucle ne trouve plus "
            "le code qu'elle est censée garder." % examined)

    #
    # §15 — L'AFFECTATION
    #

    def test_selecting_an_application_creates_the_assignment(self):
        mission, application = self._award_the_mission()
        assignment = self.env['opex.mission.assignment'].sudo().search(
            [('mission_id', '=', mission.id)])

        self.assertEqual(len(assignment), 1)
        self.assertEqual(assignment.partner_id, self.intervenant.partner_id)
        self.assertEqual(assignment.application_id, application)
        # Les conditions sont **recopiées** depuis la candidature retenue.
        self.assertEqual(assignment.tarif, 25000.0)
        self.assertEqual(assignment.type_tarif, 'tjm')
        self.assertEqual(assignment.duree_jours, 15)
        self.assertEqual(assignment.montant_total, 25000.0 * 15)

    def test_the_assignment_is_not_created_twice(self):
        """Rejouer la sélection ne double rien.

        Une candidature peut redescendre en short-list puis être retenue de
        nouveau — la transition `application_back_to_screened` existe. Le
        déclencheur doit être idempotent, sans quoi une hésitation du décideur
        produirait deux affectations et deux contrats.
        """
        mission, application = self._award_the_mission()
        application.sudo()._trigger_selection()
        application.sudo()._trigger_selection()

        self.assertEqual(
            self.env['opex.mission.assignment'].sudo().search_count(
                [('mission_id', '=', mission.id)]), 1)
        self.assertEqual(
            self.env['opex.mission.contract'].sudo().search_count(
                [('mission_id', '=', mission.id)]), 2)

    #
    # LE MANQUE DÉCLARÉ À L'EXTENSION 1, REFERMÉ ICI
    #

    def test_the_retained_expert_becomes_actor_of_the_mission(self):
        """L'inverse exact de ce que l'Extension 1 consignait.

        Elle avait écrit `test_the_retained_expert_is_not_yet_actor_of_the_
        mission` en annonçant qu'il rougirait ici. Il a rougi, et il a été
        réécrit — c'est le comportement qu'on lui demandait : signaler que
        l'état du module a changé plutôt que laisser une affirmation périmée
        passer au vert.

        L'accès est `limited` : le retenu voit le dossier de la mission et
        peut la faire avancer, il n'en dispose pas. Le `full` reste ce que sa
        candidature lui donne.
        """
        mission, application = self._award_the_mission()
        actors = mission.sudo().workflow_instance_id.actor_ids

        lines = actors.filtered(
            lambda a: a.role_id.code == 'intervenant'
            and a.user_id == self.intervenant)
        self.assertEqual(
            len(lines), 1,
            "L'intervenant retenu n'est pas acteur de la mission : les "
            "transitions qui lui sont ouvertes restent hors de sa portée.")
        self.assertEqual(lines.access_level, 'limited')

        # Il reste `full` sur sa propre candidature — les deux instances sont
        # distinctes, et les droits qu'elles portent aussi.
        own = application.sudo().workflow_instance_id.actor_ids.filtered(
            lambda a: a.role_id.code == 'intervenant')
        self.assertEqual(own.access_level, 'full')

    def test_only_the_retained_expert_becomes_actor(self):
        """Un candidat écarté ne gagne aucun droit sur la mission."""
        mission = self._new_mission()
        self._open_the_call(mission)
        retained = self._new_application(mission)
        other = self._new_application(
            mission, partner=self.other_intervenant.partner_id)
        self._apply(other, user=self.other_intervenant)
        self._select_the_application(retained)

        actors = mission.sudo().workflow_instance_id.actor_ids
        self.assertTrue(
            actors.filtered(lambda a: a.user_id == self.intervenant),
            "Le retenu doit être acteur de la mission.")
        self.assertFalse(
            actors.filtered(lambda a: a.user_id == self.other_intervenant),
            "Un candidat non retenu est devenu acteur de la mission.")

    #
    # RÈGLE 4 DU §39 — UNE CONTRAINTE, PAS UNE CONVENTION
    #

    def test_rule_4_a_second_selection_is_refused_and_explained(self):
        """Le premier niveau : la condition de la transition.

        C'est celui qui **explique**. Le décideur lit pourquoi avant d'avoir
        cliqué, et le message nomme la sortie de secours — autoriser plusieurs
        intervenants sur le type de mission.
        """
        mission = self._new_mission()
        self._open_the_call(mission)
        self._select_the_application(self._new_application(mission))

        second = self._new_application(
            mission, partner=self.other_intervenant.partner_id)
        self._apply(second, user=self.other_intervenant)
        self._do(second, 'application_screen', self.manager)
        self._do(second, 'application_shortlist', self.manager)

        with self.assertRaises(UserError) as refus:
            self._do(second, 'application_select', self.decideur,
                     comment="Second choix.")
        self.assertIn("règle 4", str(refus.exception))
        self.assertEqual(self._stage(second), 'shortlisted')

    def test_rule_4_is_also_a_constraint_on_the_assignment(self):
        """Le second niveau : la garantie.

        La condition de transition ne protège que le chemin qui passe par la
        transition. Un import, un script ou une requête forgée créeraient une
        seconde affectation sans jamais la croiser. La contrainte, elle, ne se
        contourne pas.
        """
        mission, _application = self._award_the_mission()
        with self.assertRaises(ValidationError) as refus:
            self.env['opex.mission.assignment'].sudo().create({
                'mission_id': mission.id,
                'application_id': self._new_application(
                    mission, partner=self.other_intervenant.partner_id).id,
                'partner_id': self.other_intervenant.partner_id.id,
            })
        self.assertIn("règle 4", str(refus.exception))

    def test_rule_4_the_exception_is_carried_by_the_mission_type(self):
        """L'exception du §39 : « sauf si le modèle de mission l'autorise ».

        Sur un type `multi_intervenants`, les deux niveaux s'effacent
        ensemble — la condition passe et la contrainte accepte. Deux
        mécanismes distincts qui liraient deux réglages différents finiraient
        par se contredire.
        """
        mission = self._new_mission(mission_type_id=self.mission_type_multi.id)
        self.assertTrue(mission.type_multi_intervenants)
        self._open_the_call(mission)

        self._select_the_application(self._new_application(mission))
        second = self._new_application(
            mission, partner=self.other_intervenant.partner_id)
        self._select_the_application(second, user=self.other_intervenant)

        self.assertEqual(self._stage(second), 'selected')
        self.assertEqual(
            self.env['opex.mission.assignment'].sudo().search_count(
                [('mission_id', '=', mission.id)]), 2)

    #
    # §18 — LE CONTRAT ET L'ORDRE DE MISSION
    #

    def test_the_contract_and_the_order_are_generated_at_selection(self):
        """« Après sélection, le système génère automatiquement un contrat. »"""
        mission, _application = self._award_the_mission()
        pieces = self.env['opex.mission.contract'].sudo().search(
            [('mission_id', '=', mission.id)])

        self.assertEqual(
            {piece.contract_type for piece in pieces},
            {'contrat', 'ordre_mission'})

        contract = pieces.filtered(lambda c: c.contract_type == 'contrat')
        self.assertTrue(contract.name.startswith("CTR-"))
        self.assertEqual(contract.version, 1)
        self.assertTrue(contract.current_version)
        # Le contenu du §18, repris du dossier et non inventé.
        self.assertEqual(contract.client_id, self.client_user.partner_id)
        self.assertEqual(contract.partner_id, self.intervenant.partner_id)
        self.assertEqual(contract.montant, 25000.0 * 15)
        self.assertEqual(contract.duree_jours, 15)
        self.assertTrue(contract.objet)
        self.assertTrue(contract.modalites_validation)

    def test_the_nda_is_generated_only_when_the_call_requires_it(self):
        """Une pièce que personne ne signera fait douter des autres."""
        without, _a = self._award_the_mission()
        self.assertFalse(
            self.env['opex.mission.contract'].sudo().search_count([
                ('mission_id', '=', without.id),
                ('contract_type', '=', 'nda'),
            ]),
            "Un NDA a été produit sur un appel qui n'en exige pas.")

        with_nda = self._new_mission(nda_required=True)
        self._award_the_mission(mission=with_nda)
        self.assertEqual(
            self.env['opex.mission.contract'].sudo().search_count([
                ('mission_id', '=', with_nda.id),
                ('contract_type', '=', 'nda'),
            ]), 1)

    def test_the_two_reports_render(self):
        """Les deux gabarits du §18 et du §20 rendent bien un document.

        Le rendu **HTML**, pas le PDF : `wkhtmltopdf` est absent du poste et
        `ir_actions_report.py:868` lève. Le gabarit, lui, est le même dans les
        deux cas — c'est lui qu'on vérifie, et c'est tout ce que le module
        possède. Le binaire est une dépendance de la machine.

        Les assertions portent sur du texte **statique** du gabarit ou sur
        des valeurs sans apostrophe : `t-out` échappe, et « n'est » devient
        « n&#39;est » dans le HTML rendu.
        """
        mission, _application = self._award_the_mission()
        pieces = self.env['opex.mission.contract'].sudo().search(
            [('mission_id', '=', mission.id)])
        contract = pieces.filtered(lambda c: c.contract_type == 'contrat')
        order = pieces.filtered(lambda c: c.contract_type == 'ordre_mission')

        Report = self.env['ir.actions.report'].sudo()

        html = Report._render_qweb_html(
            'opex_intervenants.report_mission_contract_document',
            contract.ids)[0].decode()
        self.assertIn("Contrat de prestation de mission", html)
        self.assertIn(contract.name, html)
        self.assertIn("Modalités de validation", html)
        self.assertIn("En attente de signature", html)

        html = Report._render_qweb_html(
            'opex_intervenants.report_mission_order_document',
            order.ids)[0].decode()
        self.assertIn("Ordre de mission", html)
        self.assertIn(mission.name, html)

    #
    # §19 — LE SOUS-WORKFLOW DE CONTRACTUALISATION
    #

    def test_starting_contracting_launches_the_subworkflow(self):
        mission, _application = self._award_the_mission()
        self.assertFalse(self._contract_instance(mission))

        self._do(mission, 'mission_start_contracting', self.secretariat)
        instance = self._contract_instance(mission)

        self.assertTrue(instance)
        self.assertEqual(instance.definition_id.code, CONTRACT_CODE)
        self.assertEqual(instance.res_model, 'opex.mission.request')
        self.assertEqual(instance.res_id, mission.id)
        self.assertEqual(instance.state, 'running')
        self.assertEqual(instance.current_stage_id.code, 'contract_preparation')
        # Et l'instance principale n'a pas bougé de place.
        self.assertEqual(mission.sudo().workflow_instance_id.definition_id.code,
                         'mission_request')

    def test_the_subworkflow_runs_on_the_mission_record(self):
        """Ce que la règle 5 impose au modèle piloté.

        `subworkflow_done('mission_contract')` cherche par `res_model` /
        `res_id`. Posée sur `opex.mission.contract`, la définition ne serait
        jamais vue par l'instance de la mission : la condition renverrait
        `False` pour toujours, sans erreur, et la règle 5 serait morte.
        """
        definition = self.Definition._get_for_code(CONTRACT_CODE)
        self.assertEqual(definition.model_name, 'opex.mission.request')

    def test_the_contract_actors_are_carried_over(self):
        """`start_subworkflow()` ne recopie aucun acteur — donc on le fait.

        Sans ce report, deux dégâts silencieux : « Signature refusée »
        n'apparaîtrait ni au client ni à l'intervenant, et la notification de
        validation ne partirait à personne — `_partners_for_roles()` résout
        les acteurs de l'instance visée.
        """
        mission, _application = self._award_the_mission()
        self._do(mission, 'mission_start_contracting', self.secretariat)

        actors = self._contract_instance(mission).actor_ids
        by_role = {actor.role_id.code: actor.user_id for actor in actors}
        self.assertEqual(by_role.get('client'), self.client_user)
        self.assertEqual(by_role.get('intervenant'), self.intervenant)

    def test_the_contract_conditions_block_and_explain(self):
        """Une transition bloquée dit pourquoi, elle ne disparaît pas."""
        mission, _application = self._award_the_mission()
        self._do(mission, 'mission_start_contracting', self.secretariat)
        self._do_contract(mission, 'contract_submit_review', self.secretariat)
        self._do_contract(mission, 'contract_send_to_sign', self.manager)

        with self.assertRaises(UserError) as refus:
            self._do_contract(mission, 'contract_sign', self.manager)
        self.assertIn("signé des deux côtés", str(refus.exception))

        contract = mission.sudo().contract_id
        contract.action_sign_client()
        contract.action_sign_intervenant()
        mission.invalidate_recordset()
        self.assertTrue(mission.sudo().contract_fully_signed)

        self._do_contract(mission, 'contract_sign', self.manager)
        self.assertEqual(
            self._contract_instance(mission).current_stage_id.code,
            'contract_signed')

    #
    # LE PIÈGE : `is_end` ET `subworkflow_done`
    #

    def test_the_validated_stage_is_the_only_final_one(self):
        """Le point de conception de toute l'extension.

        `do_transition()` pose `state = 'done'` en atteignant **n'importe
        quelle** étape `is_end` (`workflow_instance.py:769`), et
        `_subworkflow_done()` teste exactement `state = 'done'`. Marquer
        « Révision demandée » comme finale ferait donc qu'un contrat
        **refusé** satisfait la règle 5 : la mission démarrerait parce que sa
        contractualisation a échoué.

        Une seule case cochée par mégarde retourne la règle contre ce qu'elle
        protège, et rien à l'écran ne le dirait.
        """
        definition = self.Definition._get_for_code(CONTRACT_CODE)
        finals = definition.stage_ids.filtered('is_end')
        self.assertEqual(
            [stage.code for stage in finals], ['contract_validated'],
            "Le sous-workflow du contrat a plus d'une étape finale : une "
            "issue autre que la validation rendrait `subworkflow_done` vrai, "
            "et la règle 5 laisserait démarrer une mission non contractée.")

    def test_a_revision_does_not_unlock_the_mission(self):
        """La version comportementale du test précédent.

        Le test ci-dessus lit la configuration ; celui-ci fait vivre le refus
        et vérifie qu'il ne débloque rien. Les deux sont nécessaires : le
        premier dit *pourquoi*, le second prouve que c'est vrai à l'exécution.
        """
        mission, _application = self._award_the_mission()
        self._do(mission, 'mission_start_contracting', self.secretariat)
        self._do_contract(mission, 'contract_submit_review', self.secretariat)
        self._do_contract(mission, 'contract_request_revision', self.manager,
                          comment="Le montant ne correspond pas au devis.")

        instance = self._contract_instance(mission)
        self.assertEqual(instance.current_stage_id.code, 'contract_revision')
        self.assertEqual(
            instance.state, 'running',
            "Une révision a clos le sous-workflow : la règle 5 passerait.")
        self.assertFalse(
            mission.sudo().workflow_instance_id._subworkflow_done(CONTRACT_CODE))

        with self.assertRaises(UserError):
            self._do(mission, 'mission_start', self.manager)
        self.assertEqual(self._stage(mission), 'contracting')

    #
    # RÈGLE 5 DU §39 — UNE CONDITION SUR LA TRANSITION
    #

    def test_rule_5_is_attached_to_the_transition(self):
        """La règle 5 vit dans la configuration, pas dans une méthode.

        Elle a été **déclarée** à l'Extension 1 et laissée rattachée à rien,
        faute d'une définition `mission_contract` : `subworkflow_done()` aurait
        renvoyé `False` pour toujours. Elle prend sa place ici.
        """
        transition = self._transition(self.mission_definition, 'mission_start')
        codes = {rule.code for rule in transition.sudo().condition_ids}
        self.assertIn(
            'mission_contract_validated', codes,
            "« Démarrer la mission » ne porte pas la condition de la règle 5.")

    def test_rule_5_the_mission_cannot_start_without_a_validated_contract(self):
        """« Contrat non validé → Mission non démarrée. »"""
        mission, _application = self._award_the_mission()
        self._do(mission, 'mission_start_contracting', self.secretariat)

        with self.assertRaises(UserError) as refus:
            self._do(mission, 'mission_start', self.manager)
        self.assertIn("règle 5", str(refus.exception))
        self.assertEqual(self._stage(mission), 'contracting')

    def test_rule_5_the_validated_contract_unlocks_the_mission(self):
        """L'assertion positive, sans laquelle la précédente ne vaut rien.

        Un test qui ne prouve que le refus passerait au vert sur une
        transition cassée pour n'importe quelle autre raison.
        """
        mission, _application = self._award_the_mission()
        self._validate_the_contract(mission)

        instance = self._contract_instance(mission)
        self.assertEqual(instance.current_stage_id.code, 'contract_validated')
        self.assertEqual(instance.state, 'done')

        self._do(mission, 'mission_start', self.manager)
        self.assertEqual(self._stage(mission), 'in_progress')

    #
    # §13 — PROJET, TÂCHES ET CALENDRIER
    #

    def test_starting_the_mission_creates_the_project_and_its_tasks(self):
        self._require_backend('project.project', "Projet d'exécution du §13")
        mission, _application = self._award_the_mission(
            resultats_attendus="Rapport de vulnérabilités\nPlan de remédiation")
        self._validate_the_contract(mission)
        self._do(mission, 'mission_start', self.manager)

        assignment = mission.sudo().assignment_id
        project = assignment._project()
        self.assertTrue(project, "Aucun projet d'exécution créé.")
        self.assertEqual(project.partner_id, self.client_user.partner_id)

        names = [task.name for task in project.sudo().task_ids]
        # Les tâches intermédiaires viennent du dossier, pas d'un modèle figé.
        self.assertIn("Rapport de vulnérabilités", names)
        self.assertIn("Plan de remédiation", names)
        self.assertEqual(len(names), 4)

        # Le « calendrier » du §13 : des tâches datées.
        self.assertTrue(
            all(task.date_deadline for task in project.sudo().task_ids),
            "Une tâche sans échéance n'apparaît dans aucun calendrier.")

    def test_no_project_is_created_before_the_contract_is_validated(self):
        """Le corollaire du placement choisi.

        Le §13 range la création du projet parmi les effets de la sélection,
        mais dit « selon configuration ». Placée là, chaque contractualisation
        échouée — `mission_contracting_failed`, posée à l'Extension 1 —
        laisserait un projet orphelin.
        """
        mission, _application = self._award_the_mission()
        self._do(mission, 'mission_start_contracting', self.secretariat)
        # `project_ref` plutôt que `_project()` : ce test doit rougir même
        # sans le module `project`, et c'est bien ce qu'on veut. Il affirme
        # qu'aucun projet n'est créé trop tôt - une affirmation qui reste
        # vérifiable, et vraie, quand la création est éteinte.
        self.assertFalse(
            mission.sudo().assignment_id.project_ref,
            "Un projet a été créé avant que le contrat soit validé.")

    #
    # §17 — L'ARBITRAGE SUR LES AUTRES CANDIDATS
    #

    def test_the_other_candidates_are_signalled_not_rejected(self):
        """Le §17 dit « les autres passent à Non retenu ». On ne le fait pas.

        `rejected` est `is_end`, donc irréversible. Les rejeter tous à la
        sélection viderait `mission_back_to_selection` — « L'intervenant s'est
        désisté », posée à l'Extension 1 parce que le §2.4 l'exige : on
        reviendrait en sélection sans un seul candidat récupérable.

        Ils sont donc signalés au responsable, qui les écarte quand le contrat
        est signé. L'humain décide, y compris de ne pas décider tout de suite.
        """
        mission = self._new_mission()
        self._open_the_call(mission)
        other = self._new_application(
            mission, partner=self.other_intervenant.partner_id)
        self._apply(other, user=self.other_intervenant)
        self._select_the_application(self._new_application(mission))

        self.assertEqual(
            self._stage(other), 'applied',
            "Une candidature concurrente a été écartée automatiquement : le "
            "chemin de retour après désistement n'a plus de candidat.")

        bodies = " ".join(
            message.body or ''
            for message in mission.sudo().message_ids)
        self.assertIn(self.other_intervenant.partner_id.name, bodies)

    #
    # LA SÉPARATION DES DEUX MACHINES, JUSQU'AU BOUT
    #

    def test_three_instances_run_on_two_records_without_interfering(self):
        """La démonstration du module, à son point le plus dense.

        Trois instances vivent en même temps : le parcours de la mission, le
        parcours de la candidature, et la contractualisation. Les deux
        dernières ne dérivent ni l'une de l'autre ni de la première.
        """
        mission, application = self._award_the_mission()
        self._validate_the_contract(mission)
        self._do(mission, 'mission_start', self.manager)

        self.assertEqual(self._stage(mission), 'in_progress')
        self.assertEqual(
            self._stage(application), 'selected',
            "La candidature a bougé parce que la mission a démarré : les deux "
            "machines ne sont plus indépendantes.")

        instances = self.env['opex.workflow.instance'].sudo().search([
            '|',
            '&', ('res_model', '=', 'opex.mission.request'),
                 ('res_id', '=', mission.id),
            '&', ('res_model', '=', 'opex.mission.application'),
                 ('res_id', '=', application.id),
        ])
        self.assertEqual(len(instances), 3)
        self.assertEqual(
            {instance.definition_id.code for instance in instances},
            {'mission_request', 'mission_application', 'mission_contract'})

    #
    # LE JALON DU MVP — §20 P0
    #

    def test_the_full_mvp_journey(self):
        """Du besoin client à l'intervenant sélectionné avec son contrat.

        C'est la phrase du §20 prise au mot, et c'est ce qui se démontre : la
        demande naît chez le client, l'appel est publié, la candidature entre,
        elle est comparée, retenue, contractualisée, et la mission démarre.
        """
        mission = self._new_mission(user=self.client_user)
        self.assertEqual(self._stage(mission), 'draft')

        self._open_the_call(mission)
        self.assertTrue(mission.sudo().is_published)

        application = self._new_application(mission, user=self.intervenant)
        self._select_the_application(application)
        self._do(mission, 'mission_close_applications', self.manager)
        self._do(mission, 'mission_award', self.decideur,
                 comment="Candidature retenue par le comité.")

        assignment = mission.sudo().assignment_id
        self.assertTrue(assignment)
        self.assertTrue(mission.sudo().contract_id)

        self._validate_the_contract(mission)
        self._do(mission, 'mission_start', self.manager)

        self.assertEqual(self._stage(mission), 'in_progress')
        # Le projet d'exécution n'est pas une étape du parcours : la mission
        # démarre avec ou sans le module `project`. On ne l'affirme donc que
        # s'il est là - sans quoi ce test, qui déroule le MVP du §20 tout
        # entier, rougirait pour une fonctionnalité de confort.
        if self.env.get('project.project') is not None:
            self.assertTrue(assignment._project())
        self.assertTrue(mission.sudo().contract_fully_signed)
