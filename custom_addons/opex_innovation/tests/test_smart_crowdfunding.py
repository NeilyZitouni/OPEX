from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged

#: Les dix étapes nommées au cahier des charges, dans l'ordre du § 4.
#: Écrites ici plutôt que déduites de la configuration : un test qui relit la
#: donnée qu'il vérifie ne vérifie rien.
CANONICAL_STAGES = [
    'depot_express', 'pre_analyse', 'dossier_progressif', 'quality_gate',
    'etude_decision', 'matching_financier', 'accompagnement',
    'mise_en_relation', 'decision_financeur', 'closing',
]


class SmartCrowdfundingCase(TransactionCase):
    """Socle commun : un dossier engagé dans le Smart Crowdfunding.

    ⚠ Le projet porte **deux** instances : celle du parcours d'innovation,
    démarrée par `create()`, et celle du Smart Crowdfunding, démarrée ici. Le
    couplage `res_model`/`res_id` le permet ; le champ `workflow_instance_id`
    du mixin, lui, n'en désigne qu'une. On pilote donc l'instance Smart
    Crowdfunding directement, sans passer par le mixin.

    C'est la limite identifiée : un enregistrement suivant deux processus à la
    fois n'a pas d'étape courante unique. On duplique la configuration plutôt
    que de refactorer le couplage — la limite sera annoncée telle quelle.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.innovation.project']
        cls.Definition = cls.env['opex.workflow.definition']
        cls.Instance = cls.env['opex.workflow.instance']
        cls.Stage = cls.env['opex.workflow.stage']
        cls.Transition = cls.env['opex.workflow.transition']
        cls.Rule = cls.env['opex.workflow.rule']

        cls.definition = cls.Definition._get_for_code('smart_crowdfunding')

        cls.porteur = new_test_user(
            cls.env, login='scf_porteur', groups='base.group_portal')
        cls.porteur.partner_id.sudo().write({'is_member': True})
        cls.ceo = new_test_user(
            cls.env, login='scf_ceo',
            groups='base.group_user,opex_innovation.group_innovation_manager')
        cls.qualite = new_test_user(
            cls.env, login='scf_qualite',
            groups='base.group_user,opex_membership.group_secretariat')
        cls.expert = new_test_user(
            cls.env, login='scf_expert', groups='base.group_portal')
        cls.financeur = new_test_user(
            cls.env, login='scf_financeur', groups='base.group_portal')

        cls.role_porteur = cls.env.ref('opex_workflow.role_porteur')
        cls.role_ceo = cls.env.ref('opex_workflow.role_ceo')
        cls.role_expert = cls.env.ref('opex_workflow.role_expert')
        cls.role_investisseur = cls.env.ref('opex_workflow.role_investisseur')
        cls.role_qualite = cls.env.ref('opex_innovation.role_controle_qualite')

    def _project(self, **values):
        base = {
            'partner_id': self.porteur.partner_id.id,
            'name': "SmartFactory DZ",
            'resume': "Une usine pilotée par l'IA.",
            'probleme': "Les lignes s'arrêtent sans prévenir.",
            'solution': "Maintenance prédictive par capteurs.",
            'secteur': 'industrie',
            'maturite': 'mvp',
            'besoin_financement': True,
            'montant_recherche': 5000000,
        }
        base.update(values)
        return self.Project.create(base)

    def _engage(self, project):
        """Démarre l'instance Smart Crowdfunding et y désigne les cinq acteurs."""
        instance = self.Instance._start_for(project, 'smart_crowdfunding')
        for role, user in (
            (self.role_porteur, self.porteur),
            (self.role_ceo, self.ceo),
            (self.role_qualite, self.qualite),
            (self.role_expert, self.expert),
            (self.role_investisseur, self.financeur),
        ):
            instance.add_actor(role, user, access_level='full')
        return instance

    def _transition(self, code):
        transition = self.definition.transition_ids.filtered(
            lambda t: t.code == code)
        self.assertTrue(transition, "Transition « %s » introuvable." % code)
        return transition

    def _outgoing(self, stage_code):
        return self.definition.transition_ids.filtered(
            lambda t: t.source_stage_id.code == stage_code)

    def _do(self, instance, user, code, comment="Décision motivée."):
        return instance.with_user(user).do_transition(
            self._transition(code), comment=comment)

    def _document(self, project, document_type):
        return self.env['opex.innovation.document'].sudo().create({
            'project_id': project.id,
            'name': "Pièce %s" % document_type,
            'document_type': document_type,
            'url': "https://exemple.dz/%s.pdf" % document_type,
        })

    def _score(self, project, total):
        """Donne au projet une note réelle, par la vraie grille d'évaluation."""
        criteria, remaining = {}, total
        for name in ('score_innovation', 'score_pertinence',
                     'score_faisabilite', 'score_marche'):
            criteria[name] = min(20, remaining)
            remaining -= criteria[name]
        for name in ('score_equipe', 'score_impact'):
            criteria[name] = min(10, remaining)
            remaining -= criteria[name]
        self.assertEqual(remaining, 0, "Total %s hors barème." % total)
        values = {
            'project_id': project.id,
            'evaluator_id': self.ceo.partner_id.id,
            'state': 'submitted',
        }
        values.update(criteria)
        self.env['opex.innovation.evaluation'].sudo().create(values)
        project.invalidate_recordset(['score'])
        return project.score


@tagged('post_install', '-at_install')
class TestSmartCrowdfundingConfiguration(SmartCrowdfundingCase):
    """Partie 1 — le processus du document, configuré en données seules."""

    # ------------------------------------------------------------
    # La définition existe et est utilisable
    # ------------------------------------------------------------

    def test_the_definition_is_published(self):
        """⚠ Le piège de l'Extension 10, vérifié ici.

        Odoo n'exécute pas les `<function>` d'un bloc `noupdate="1"` lors d'une
        mise à jour. Publier depuis l'intérieur du bloc marcherait à
        l'installation et laisserait la définition en brouillon après le
        premier `-u` — c'est-à-dire précisément le jour de la démonstration.
        Le `<function>` est donc hors du bloc, et ce test le constate.
        """
        self.assertEqual(self.definition.state, 'published')
        self.assertEqual(
            self.definition.model_name, 'opex.innovation.project')

    def test_the_graph_is_coherent(self):
        self.assertTrue(self.definition._check_graph())

    def test_the_ten_canonical_stages_are_configured(self):
        """Codes communs avec l'implémentation « texto » : c'est ce qui rendra
        la comparaison lisible sans avoir à traduire un vocabulaire."""
        configured = set(self.definition.stage_ids.mapped('code'))
        missing = [code for code in CANONICAL_STAGES if code not in configured]
        self.assertFalse(missing, "Étapes manquantes : %s" % ", ".join(missing))

    def test_every_stage_speaks_to_its_actor(self):
        """§ 16 : « chaque acteur voit son propre workflow »."""
        without = self.definition.stage_ids.filtered(lambda s: not s.user_label)
        self.assertFalse(
            without, "Étapes sans libellé utilisateur : %s"
            % ", ".join(without.mapped('code')))

    def test_the_call_to_action_is_the_one_the_document_demands(self):
        """§ 5 : « Présenter mon projet », et non « Constituer mon dossier de
        financement ». Le document en fait un point d'UX explicite."""
        self.assertEqual(self._transition('presenter').name,
                         "Présenter mon projet")

    # ------------------------------------------------------------
    # Point 1 à ne pas simplifier — quatre sorties de pré-analyse
    # ------------------------------------------------------------

    def test_pre_analysis_has_exactly_four_exits(self):
        outgoing = self._outgoing('pre_analyse')
        self.assertEqual(
            len(outgoing), 4,
            "Sorties trouvées : %s" % ", ".join(outgoing.mapped('code')))
        self.assertEqual(
            set(outgoing.mapped('code')),
            {'go', 'a_clarifier', 'no_go', 'orientation'})

    def test_the_four_exits_lead_to_four_different_places(self):
        """Quatre transitions qui aboutiraient au même endroit seraient un
        Go/No-Go déguisé."""
        targets = {t.code: t.target_stage_id.code
                   for t in self._outgoing('pre_analyse')}
        self.assertEqual(targets, {
            'go': 'dossier_progressif',
            'a_clarifier': 'clarification',
            'no_go': 'rejected',
            'orientation': 'accompagnement',
        })

    def test_orientation_is_not_a_rejection(self):
        """§ 9 : « Le rejet ne doit pas être confondu avec la maturation. »"""
        orientation = self._transition('orientation')
        self.assertFalse(orientation.target_stage_id.is_end)
        self.assertTrue(self._transition('no_go').target_stage_id.is_end)

    def test_a_negative_decision_always_demands_a_motive(self):
        for code in ('a_clarifier', 'no_go', 'orientation'):
            self.assertTrue(
                self._transition(code).requires_comment,
                "« %s » devrait exiger un motif." % code)

    # ------------------------------------------------------------
    # Point 2 à ne pas simplifier — trois sorties du Quality Gate
    # ------------------------------------------------------------

    def test_quality_gate_has_exactly_three_exits(self):
        outgoing = self._outgoing('quality_gate')
        self.assertEqual(
            len(outgoing), 3,
            "Sorties trouvées : %s" % ", ".join(outgoing.mapped('code')))
        self.assertEqual(
            set(outgoing.mapped('code')),
            {'qg_conforme', 'qg_a_completer', 'qg_alerte'})

    def test_the_alert_does_not_move_the_file(self):
        """§ 8 : « Alerte → CEO », le dossier reste au contrôle.

        Une transition dont la source et la cible sont la même étape. Le moteur
        n'a rien de spécial pour ça, et c'est bien le point : le cas n'a pas
        demandé de code.
        """
        alerte = self._transition('qg_alerte')
        self.assertEqual(alerte.source_stage_id, alerte.target_stage_id)
        self.assertEqual(alerte.source_stage_id.code, 'quality_gate')

    def test_the_alert_reaches_the_ceo(self):
        actions = self._transition('qg_alerte').action_ids
        self.assertTrue(actions, "L'alerte ne déclenche aucune action.")
        self.assertIn(
            self.role_ceo,
            actions.mapped('target_role_ids'),
            "L'alerte doit notifier le CEO.")

    def test_the_quality_gate_belongs_to_the_quality_controller(self):
        """§ 8 : le remplacement futur du contrôleur par un agent IA « ne doit
        nécessiter aucune modification du workflow métier ». Possible ici parce
        que l'acteur est une donnée : on change le titulaire du rôle."""
        for transition in self._outgoing('quality_gate'):
            self.assertEqual(transition.allowed_role_ids, self.role_qualite)

    # ------------------------------------------------------------
    # Point 3 à ne pas simplifier — la boucle de maturation
    # ------------------------------------------------------------

    def test_the_maturation_loop_exists(self):
        """Accompagnement → Réévaluation → Matching, et le retour en arrière.

        ⚠ Volontairement écrit en compréhension et non avec `mapped()` : sur
        un Many2one, `mapped()` déduplique, et une boucle qui repasse par la
        même étape y devient invisible. Un test écrit avec `mapped()` passerait
        au vert sur un graphe où la boucle n'existe pas.
        """
        arcs = [(t.source_stage_id.code, t.target_stage_id.code)
                for t in self.definition.transition_ids]
        self.assertIn(('accompagnement', 'reevaluation'), arcs)
        self.assertIn(('reevaluation', 'matching_financier'), arcs)
        self.assertIn(('reevaluation', 'accompagnement'), arcs)

    def test_accompaniment_has_the_three_entries_of_the_document(self):
        """§ 11 : recommandation CEO, demande de l'acteur financier, et
        orientation dès la pré-analyse."""
        incoming = {t.code for t in self.definition.transition_ids
                    if t.target_stage_id.code == 'accompagnement'}
        self.assertEqual(incoming, {
            'orientation', 'route_maturation', 'financeur_accompagnement',
            'reevaluation_ko',
        })

    def test_the_study_offers_the_three_routes(self):
        targets = {t.code: t.target_stage_id.code
                   for t in self._outgoing('etude_decision')}
        self.assertEqual(targets, {
            'route_investment_ready': 'matching_financier',
            'route_maturation': 'accompagnement',
            'route_non_retenu': 'rejected',
        })

    # ------------------------------------------------------------
    # Les conditions et les actions sont réellement branchées
    # ------------------------------------------------------------

    def test_at_least_two_transitions_carry_a_real_condition(self):
        guarded = self.definition.transition_ids.filtered('condition_ids')
        self.assertGreaterEqual(len(guarded), 2)

    def test_at_least_two_transitions_carry_a_real_action(self):
        acting = self.definition.transition_ids.filtered('action_ids')
        self.assertGreaterEqual(len(acting), 2)

    def test_an_incomplete_express_deposit_is_refused(self):
        project = self._project(secteur=False)
        instance = self._engage(project)
        with self.assertRaises(UserError) as error:
            self._do(instance, self.porteur, 'presenter')
        self.assertIn("secteur", str(error.exception).lower())

    def test_the_progressive_file_is_gated_on_the_business_plan(self):
        project = self._project()
        instance = self._engage(project)
        self._do(instance, self.porteur, 'presenter')
        self._do(instance, self.ceo, 'go')
        project.sudo().write({
            'marche_cible': "Industriels de l'agroalimentaire.",
            'proposition_valeur': "Moins d'arrêts non planifiés.",
        })

        # Sans business plan, la condition refuse et le dit.
        with self.assertRaises(UserError) as error:
            self._do(instance, self.porteur, 'soumettre_dossier')
        self.assertIn("business plan", str(error.exception).lower())

        # Le document déposé, la même transition passe.
        self._document(project, 'business_plan')
        self._do(instance, self.porteur, 'soumettre_dossier')
        self.assertEqual(instance.current_stage_id.code, 'quality_gate')

    def test_the_financial_matching_needs_a_figure(self):
        project = self._project(montant_recherche=0)
        instance = self._engage(project)
        instance.sudo().current_stage_id = self.definition.stage_ids.filtered(
            lambda s: s.code == 'etude_decision')
        with self.assertRaises(UserError) as error:
            self._do(instance, self.ceo, 'route_investment_ready')
        self.assertIn("montant", str(error.exception).lower())

    def test_the_matching_action_looks_for_financial_actors_only(self):
        """§ 10 : le vivier des acteurs financiers, pas celui des experts."""
        action = self.env.ref('opex_innovation.scf_action_matching')
        self.assertEqual(action.action_type, 'run_matching')
        self.assertEqual(action.matching_candidate_type, 'investisseur')
        self.assertIn('is_investor', action.matching_domain or '')

    def test_the_matching_has_criteria_of_its_own(self):
        """Régression : les critères appartiennent à **une** définition.

        Sans ce bloc de configuration, l'action de matching se déclenchait,
        levait « aucun critère n'est configuré », et cet échec était journalisé
        sans annuler la transition — règle voulue de l'Extension 4. Le dossier
        arrivait donc en matching avec une liste de candidats vide et aucun
        message à l'écran. Trouvé en exécutant le parcours ; invisible à la
        relecture.

        ⚠ Le `search` est borné à cette définition : les critères du parcours
        d'innovation portent des codes voisins, et un `search` global en
        renverrait un mélange.
        """
        criteria = self.env['opex.matching.criteria'].search([
            ('definition_id', '=', self.definition.id),
        ])
        self.assertGreaterEqual(len(criteria), 5)
        # Le § 10 fait du ticket le critère dimensionnant : c'est lui qui doit
        # peser le plus.
        heaviest = max(criteria, key=lambda c: c.weight)
        self.assertEqual(heaviest.code, 'scf_ticket')
        self.assertEqual(heaviest.match_mode, 'gte')

    def test_the_alert_is_written_in_the_history(self):
        """Un email se perd ; une transition est datée. C'est la différence
        entre une alerte et une trace d'alerte."""
        project = self._project()
        instance = self._engage(project)
        self._do(instance, self.porteur, 'presenter')
        self._do(instance, self.ceo, 'go')
        project.sudo().write({
            'marche_cible': "Industriels.",
            'proposition_valeur': "Moins d'arrêts.",
        })
        self._document(project, 'business_plan')
        self._do(instance, self.porteur, 'soumettre_dossier')

        before = len(instance.history_ids)
        self._do(instance, self.qualite, 'qg_alerte',
                 comment="Prévisions financières incohérentes.")
        self.assertEqual(len(instance.history_ids), before + 1)
        self.assertEqual(instance.current_stage_id.code, 'quality_gate')

        # ⚠ `history_ids[0]` n'est pas la dernière ligne : l'ordre d'un
        # One2many est celui du comodèle, et plusieurs lignes créées dans la
        # même transaction partagent la même `date`. Le tri se fait donc sur
        # `id`, explicitement — sinon le test lit l'entrée d'ouverture du
        # dossier et compare le mauvais commentaire.
        last = instance.history_ids.sorted('id')[-1]
        self.assertIn("incohérentes", last.comment)
        self.assertEqual(last.to_stage_id.code, 'quality_gate')

    # ------------------------------------------------------------
    # Le parcours nominal, de bout en bout
    # ------------------------------------------------------------

    def test_the_nominal_path_runs_from_deposit_to_closing(self):
        project = self._project()
        instance = self._engage(project)

        self._do(instance, self.porteur, 'presenter')
        self.assertEqual(instance.current_stage_id.code, 'pre_analyse')

        self._do(instance, self.ceo, 'go')
        project.sudo().write({
            'marche_cible': "Industriels de l'agroalimentaire.",
            'proposition_valeur': "Moins d'arrêts non planifiés.",
        })
        self._document(project, 'business_plan')

        self._do(instance, self.porteur, 'soumettre_dossier')
        self._do(instance, self.qualite, 'qg_conforme')
        self._do(instance, self.ceo, 'route_investment_ready')
        self._do(instance, self.ceo, 'mettre_en_relation')
        self._do(instance, self.ceo, 'transmettre_financeur')
        self._do(instance, self.financeur, 'financeur_interesse')

        self.assertEqual(instance.current_stage_id.code, 'closing')
        self.assertEqual(instance.state, 'done')

    def test_the_maturation_path_runs_and_comes_back(self):
        """La boucle du § 9 route B, parcourue pour de bon.

        ⚠ Les étapes traversées sont collectées en compréhension. Avec
        `mapped('to_stage_id.code')`, le second passage par `accompagnement`
        disparaîtrait du résultat et le test ne prouverait plus rien.
        """
        project = self._project()
        instance = self._engage(project)

        self._do(instance, self.porteur, 'presenter')
        self._do(instance, self.ceo, 'orientation',
                 comment="Potentiel réel, maturité insuffisante.")
        self.assertEqual(instance.current_stage_id.code, 'accompagnement')

        self._do(instance, self.expert, 'fin_accompagnement')
        self._do(instance, self.ceo, 'reevaluation_ko',
                 comment="Le modèle économique reste flou.")
        self.assertEqual(instance.current_stage_id.code, 'accompagnement')

        self._do(instance, self.expert, 'fin_accompagnement')
        self._do(instance, self.ceo, 'reevaluation_ok')
        self.assertEqual(instance.current_stage_id.code, 'matching_financier')

        visited = [h.to_stage_id.code
                   for h in instance.history_ids.sorted('id')]
        self.assertEqual(visited.count('accompagnement'), 2)
        self.assertEqual(visited.count('reevaluation'), 2)

    def test_the_financier_can_send_the_file_back_to_accompaniment(self):
        """§ 14 : « ↗ Intéressé sous condition d'accompagnement CEO ». Le
        financeur choisit une action simple ; le moteur en fait une transition,
        il n'a pas à comprendre le workflow interne."""
        project = self._project()
        instance = self._engage(project)
        instance.sudo().current_stage_id = self.definition.stage_ids.filtered(
            lambda s: s.code == 'decision_financeur')

        self._do(instance, self.financeur, 'financeur_accompagnement',
                 comment="Intéressé si le go-to-market est consolidé.")
        self.assertEqual(instance.current_stage_id.code, 'accompagnement')

    # ------------------------------------------------------------
    # Le moteur ne sait toujours rien du métier
    # ------------------------------------------------------------

    def test_the_engine_never_compares_anything_to_a_business_code(self):
        """Deux processus, un moteur, aucun cas particulier pour l'un ni l'autre.

        La première version de ce test cherchait le vocabulaire métier dans le
        texte des fichiers du moteur. Elle tombait sur l'aide du champ `code` :

            "Exemple : innovation_project, smart_crowdfunding."

        Une aide de champ n'est pas un couplage — le moteur ne teste jamais
        cette valeur, il l'affiche. Le test ne mesurait donc pas ce qu'il
        prétendait mesurer, et la seule façon de le faire passer aurait été
        d'appauvrir une aide utile.

        Ce qui compte n'est pas que le mot apparaisse, c'est que le moteur
        **décide** à partir de lui. On cherche donc les comparaisons : un
        `if stage.code == 'quality_gate'` quelque part dans `opex_workflow`
        signerait la fin de la démonstration, et c'est cela qu'on veut voir.
        """
        import ast
        import inspect
        import os

        import odoo.addons.opex_workflow as engine

        engine_dir = os.path.dirname(inspect.getfile(engine))
        vocabulary = {
            'crowdfunding', 'smart_crowdfunding', 'quality_gate',
            'pre_analyse', 'depot_express', 'dossier_progressif',
            'etude_decision', 'matching_financier', 'mise_en_relation',
            'decision_financeur', 'closing', 'demo_day',
            'innovation_project',
        }

        offences = []
        scanned = 0
        for root, _dirs, files in os.walk(engine_dir):
            if 'tests' in root.split(os.sep):
                continue
            for filename in sorted(files):
                if not filename.endswith('.py'):
                    continue
                path = os.path.join(root, filename)
                with open(path, encoding='utf-8') as handle:
                    tree = ast.parse(handle.read(), filename=filename)
                scanned += 1
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Compare):
                        continue
                    for operand in [node.left, *node.comparators]:
                        if (isinstance(operand, ast.Constant)
                                and isinstance(operand.value, str)
                                and operand.value.lower() in vocabulary):
                            offences.append("%s:%s — « %s »" % (
                                filename, node.lineno, operand.value))

        # ⚠ Assertion positive d'abord : sans elle, un `engine_dir` erroné
        # donnerait zéro fichier parcouru, zéro infraction, et un test vert qui
        # ne prouve rien.
        self.assertGreaterEqual(scanned, 5,
                                "Le moteur n'a pas été parcouru (%s fichiers)."
                                % scanned)
        self.assertFalse(
            offences,
            "Le moteur décide à partir d'un code métier : %s"
            % " ; ".join(offences))


@tagged('post_install', '-at_install')
class TestDemoDayAcceptance(SmartCrowdfundingCase):
    """Partie 2 — le critère de démonstration du § 18, exécuté.

    > « Ajoutez une étape Demo Day entre Accompagnement et Matching
    >   Investisseurs. Elle nécessite l'accord du CEO, une présentation Pitch
    >   Deck et une note ≥ 70/100. »

    Ce que fait `_configure_demo_day()` est **exactement** ce que décrit le
    protocole manuel remis avec cette extension : cinq écrans, les mêmes
    champs, les mêmes valeurs. La différence est le moyen d'écriture — l'ORM
    ici, le formulaire là — pas la nature de l'opération.

    ⚠ Aucun `import` de `opex_workflow` ici, aucun appel à une méthode que le
    moteur n'exposait pas déjà. Tout passe par `create()` et `write()` sur les
    modèles de configuration. C'est la définition littérale de « depuis le
    configurateur, sans modifier le code Python du moteur ».
    """

    def _configure_demo_day(self):
        """Les cinq manipulations du protocole, dans l'ordre."""

        # Écran 1 — trois règles métier.
        rules = self.Rule.create([
            {
                'name': "Accord du CEO",
                'code': 'demo_day_ceo_approval',
                'expression': "record.ceo_approval == True",
                'message': "L'accord du CEO n'a pas encore été donné.",
            },
            {
                'name': "Pitch Deck présenté",
                'code': 'demo_day_pitch_deck',
                'expression': "has_document('pitch_deck')",
                'message': "Le Pitch Deck du Demo Day n'a pas été déposé.",
            },
            {
                'name': "Note ≥ 70/100",
                'code': 'demo_day_score_70',
                'expression': "field('score') >= 70",
                'message': "Le projet doit avoir obtenu au moins 70/100.",
            },
        ])

        # Écran 2 — la nouvelle étape.
        demo_day = self.Stage.create({
            'definition_id': self.definition.id,
            'code': 'demo_day',
            'name': "Demo Day",
            'user_label': "Préparer mon Demo Day",
            'sequence': 95,
            'actor_role_ids': [(6, 0, self.role_porteur.ids)],
        })

        # Écran 3 — on détourne l'arc existant vers la nouvelle étape.
        #
        # ⚠ Aucune écriture sur `action_ids` ici, et c'est une contrainte, pas
        # un choix : `action_ids` n'est exposé dans aucune vue du
        # configurateur. Une manipulation que ce test ferait sans effort et que
        # l'opérateur du protocole manuel ne pourrait pas reproduire
        # invaliderait la démonstration. Le test s'interdit donc ce que
        # l'interface interdit.
        self._transition('reevaluation_ok').write({
            'name': "Projet mûr — convoquer le Demo Day",
            'target_stage_id': demo_day.id,
        })

        # Écran 4 — la nouvelle transition, portant les trois conditions.
        matching = self.definition.stage_ids.filtered(
            lambda s: s.code == 'matching_financier')
        self.Transition.create({
            'definition_id': self.definition.id,
            'code': 'demo_day_valide',
            'name': "Demo Day validé — passer au matching",
            'source_stage_id': demo_day.id,
            'target_stage_id': matching.id,
            'sequence': 165,
            'allowed_role_ids': [(6, 0, self.role_ceo.ids)],
            'condition_ids': [(6, 0, rules.ids)],
        })

        # Écran 5 — republication : le graphe est revalidé.
        self.definition.action_publish()
        return demo_day

    def _bring_to_demo_day(self, project, instance):
        self._do(instance, self.porteur, 'presenter')
        self._do(instance, self.ceo, 'orientation', comment="À maturer.")
        self._do(instance, self.expert, 'fin_accompagnement')
        self._do(instance, self.ceo, 'reevaluation_ok')

    # ------------------------------------------------------------

    def test_the_new_stage_sits_between_accompaniment_and_matching(self):
        self._configure_demo_day()
        arcs = [(t.source_stage_id.code, t.target_stage_id.code)
                for t in self.definition.transition_ids]
        self.assertIn(('accompagnement', 'reevaluation'), arcs)
        self.assertIn(('reevaluation', 'demo_day'), arcs)
        self.assertIn(('demo_day', 'matching_financier'), arcs)
        # Et l'ancien raccourci n'existe plus.
        self.assertNotIn(('reevaluation', 'matching_financier'), arcs)

    def test_the_graph_remains_coherent_after_the_insertion(self):
        self._configure_demo_day()
        self.assertTrue(self.definition._check_graph())
        self.assertEqual(self.definition.state, 'published')

    def test_a_file_now_stops_at_the_demo_day(self):
        self._configure_demo_day()
        project = self._project()
        instance = self._engage(project)
        self._bring_to_demo_day(project, instance)
        self.assertEqual(instance.current_stage_id.code, 'demo_day')

    def test_each_of_the_three_conditions_blocks_on_its_own(self):
        """Trois refus, trois messages distincts. Un test qui n'en vérifierait
        qu'un passerait au vert sur une condition oubliée."""
        self._configure_demo_day()
        project = self._project()
        instance = self._engage(project)
        self._bring_to_demo_day(project, instance)
        transition = self._transition('demo_day_valide')

        # 1. Rien n'est réuni : le CEO n'a pas approuvé.
        with self.assertRaises(UserError) as error:
            instance.with_user(self.ceo).do_transition(transition)
        self.assertIn("ceo", str(error.exception).lower())

        # 2. Accord donné, mais pas de Pitch Deck.
        project.sudo().ceo_approval = True
        with self.assertRaises(UserError) as error:
            instance.with_user(self.ceo).do_transition(transition)
        self.assertIn("pitch deck", str(error.exception).lower())

        # 3. Pitch Deck déposé, mais la note est insuffisante.
        self._document(project, 'pitch_deck')
        self.assertEqual(self._score(project, 60), 60)
        with self.assertRaises(UserError) as error:
            instance.with_user(self.ceo).do_transition(transition)
        self.assertIn("70", str(error.exception))

    def test_the_three_conditions_met_open_the_matching(self):
        self._configure_demo_day()
        project = self._project()
        instance = self._engage(project)
        self._bring_to_demo_day(project, instance)

        project.sudo().ceo_approval = True
        self._document(project, 'pitch_deck')
        self.assertGreaterEqual(self._score(project, 80), 70)

        self._do(instance, self.ceo, 'demo_day_valide')
        self.assertEqual(instance.current_stage_id.code, 'matching_financier')

    def test_the_demo_day_is_reserved_to_the_ceo(self):
        """« Elle nécessite l'accord du CEO » : le porteur ne se valide pas
        lui-même, même toutes conditions réunies."""
        self._configure_demo_day()
        project = self._project()
        instance = self._engage(project)
        self._bring_to_demo_day(project, instance)

        project.sudo().ceo_approval = True
        self._document(project, 'pitch_deck')
        self._score(project, 80)

        with self.assertRaises(UserError) as error:
            self._do(instance, self.porteur, 'demo_day_valide')
        self.assertIn("réservée", str(error.exception).lower())

    def test_the_whole_operation_touches_only_fields_the_ui_exposes(self):
        """⚠ Le test qui garde le protocole manuel honnête.

        Ce qui suit énumère les champs que les cinq écrans modifient, et
        vérifie qu'ils sont tous présents dans une vue du configurateur. Si
        quelqu'un « améliore » un jour `_configure_demo_day()` en écrivant un
        champ que l'interface n'expose pas, ce test le refusera — au lieu de
        laisser la démonstration passer au vert sur une opération que l'on ne
        sait pas reproduire à la souris.

        `action_ids` est le champ qui manque : la configuration Smart
        Crowdfunding est donc écrite pour ne jamais avoir à y toucher.
        """
        touched = {
            'opex.workflow.rule': {'name', 'code', 'expression', 'message'},
            'opex.workflow.stage': {'code', 'name', 'user_label', 'sequence',
                                    'actor_role_ids'},
            'opex.workflow.transition': {'code', 'name', 'source_stage_id',
                                         'target_stage_id', 'sequence',
                                         'allowed_role_ids', 'condition_ids'},
        }
        View = self.env['ir.ui.view'].sudo()

        def _arch(views):
            return "".join(str(view.arch_db or '') for view in views)

        # Les étapes et les transitions n'ont pas de vue propre : elles
        # s'éditent dans les listes imbriquées du formulaire de définition.
        configurator = _arch(View.search([
            ('model', '=', 'opex.workflow.definition'),
            ('type', '=', 'form'),
        ]))

        for model, field_names in touched.items():
            arch = _arch(View.search([('model', '=', model)])) + configurator

            self.assertIn('name="name"', arch,
                          "Aucune vue trouvée pour %s." % model)
            missing = [f for f in sorted(field_names)
                       if 'name="%s"' % f not in arch]
            self.assertFalse(
                missing,
                "%s : champs modifiés par le protocole mais absents du "
                "configurateur : %s" % (model, ", ".join(missing)))

    def test_the_matching_stays_available_on_demand(self):
        """§ 10 : le CEO lance la recherche quand il le décide.

        C'est ce placement — l'action sur une transition qui boucle sur
        l'étape de matching, et non sur l'arc qui y mène — qui rend
        l'insertion du Demo Day faisable sans jamais toucher à `action_ids`.
        """
        self._configure_demo_day()
        relancer = self._transition('relancer_matching')
        self.assertEqual(relancer.source_stage_id, relancer.target_stage_id)
        self.assertTrue(relancer.action_ids)
        self.assertFalse(self._transition('reevaluation_ok').action_ids)

    def test_files_already_running_are_not_disturbed(self):
        """Question de recette : que deviennent les dossiers en cours ?

        Ils continuent. Le nouveau chemin ne s'applique qu'aux transitions
        franchies après la reconfiguration — aucune migration de données, aucun
        dossier bloqué à une étape qui n'existait pas à son ouverture.
        """
        project = self._project()
        instance = self._engage(project)
        self._do(instance, self.porteur, 'presenter')
        self._do(instance, self.ceo, 'orientation', comment="À maturer.")

        self._configure_demo_day()

        self.assertEqual(instance.current_stage_id.code, 'accompagnement')
        self._do(instance, self.expert, 'fin_accompagnement')
        self._do(instance, self.ceo, 'reevaluation_ok')
        self.assertEqual(instance.current_stage_id.code, 'demo_day')
