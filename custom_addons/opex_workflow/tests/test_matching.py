from odoo.exceptions import UserError
from odoo.tests.common import new_test_user, tagged

from .common import WorkflowCase


@tagged('post_install', '-at_install')
class TestMatching(WorkflowCase):
    """Extension 7 — le score est-il juste, explicable, et sans effet de bord ?"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.definition = cls._linear_definition(code='match_wf')
        cls.Criteria = cls.env['opex.matching.criteria']
        cls.Candidate = cls.env['opex.matching.candidate']
        cls.Relation = cls.env['opex.matching.relation']

        # Le dossier attend l'industrie, à Alger.
        cls.record = cls.env['res.partner'].create({
            'name': "Projet Smart Factory",
            'function': "industrie",
            'city': "Alger",
        })
        cls.instance = cls.Instance._start_for(cls.record, 'match_wf')

        # Trois candidats : parfait, partiel, hors sujet.
        cls.perfect = cls.env['res.partner'].create({
            'name': "Expert Industrie Alger",
            'function': "industrie",
            'city': "Alger",
        })
        cls.partial = cls.env['res.partner'].create({
            'name': "Expert Industrie Oran",
            'function': "industrie",
            'city': "Oran",
        })
        cls.unrelated = cls.env['res.partner'].create({
            'name': "Expert Agriculture Oran",
            'function': "agriculture",
            'city': "Oran",
        })
        cls.pool = cls.perfect | cls.partial | cls.unrelated

    def _criterion(self, code, source, target, weight=1.0, **values):
        base = {
            'definition_id': self.definition.id,
            'name': code.replace('_', ' ').capitalize(),
            'code': code,
            'source_expression': source,
            'target_field': target,
            'weight': weight,
        }
        base.update(values)
        return self.Criteria.create(base)

    def _default_criteria(self):
        return (
            self._criterion('secteur', "field('function')",
                            'function', weight=3.0)
            | self._criterion('localisation', "field('city')", 'city', weight=1.0)
        )

    # ------------------------------------------------------------
    # Le calcul
    # ------------------------------------------------------------

    def test_score_is_weighted_and_normalised(self):
        """Somme des poids satisfaits ÷ somme des poids applicables."""
        criteria = self._default_criteria()

        score, _detail = self.instance._score_candidate(self.perfect, criteria)
        self.assertAlmostEqual(score, 100.0, places=2)

        # Secteur (3) satisfait, localisation (1) non → 3/4 = 75 %.
        score, _detail = self.instance._score_candidate(self.partial, criteria)
        self.assertAlmostEqual(score, 75.0, places=2)

        score, _detail = self.instance._score_candidate(self.unrelated, criteria)
        self.assertAlmostEqual(score, 0.0, places=2)

    def test_weights_only_matter_by_their_ratio(self):
        """Multiplier tous les poids par le même facteur ne change rien.

        C'est ce que veut dire « normalisé » : le score est une proportion, pas
        une somme. Un configurateur qui saisit 30 et 10 obtient le même
        classement qu'avec 3 et 1, et n'a donc pas à se soucier de l'échelle.

        Les poids sont réaffectés **par code** et non par ordre de tri : un test
        qui dépend de l'ordre alphabétique inverserait silencieusement le
        rapport le jour où un critère est renommé.
        """
        criteria = self._default_criteria()
        before, _d = self.instance._score_candidate(self.partial, criteria)

        by_code = {criterion.code: criterion for criterion in criteria}
        by_code['secteur'].weight = 30.0
        by_code['localisation'].weight = 10.0

        after, _d = self.instance._score_candidate(self.partial, criteria)
        self.assertAlmostEqual(before, 75.0, places=2)
        self.assertAlmostEqual(after, before, places=2)

    def test_candidates_are_ordered_by_score(self):
        self._default_criteria()
        candidates = self.instance.run_matching(partners=self.pool)
        self.assertEqual(
            candidates.sorted('score', reverse=True).mapped('partner_id'),
            self.perfect | self.partial | self.unrelated,
        )

    def test_min_score_filters_out_the_weakest(self):
        self._default_criteria()
        candidates = self.instance.run_matching(partners=self.pool, min_score=50.0)
        self.assertEqual(
            set(candidates.mapped('partner_id')), {self.perfect, self.partial})

    def test_limit_keeps_the_best_ones(self):
        self._default_criteria()
        candidates = self.instance.run_matching(partners=self.pool, limit=1)
        self.assertEqual(candidates.partner_id, self.perfect)

    def test_intersect_mode_matches_on_any_common_value(self):
        self._criterion(
            'competences', "['ia', 'iot']", 'category_id',
            match_mode='intersect')
        tag = self.env['res.partner.category'].create({'name': "IA"})
        self.perfect.category_id = [(6, 0, tag.ids)]

        # Recherche **bornée à cette définition**.
        #
        # Chercher par `code` seul parcourait toute la base : depuis que le
        # module métier sème ses propres critères, un code aussi banal que
        # « competences » en ramenait deux — celui du test et celui du métier —
        # et le score portait sur les deux. Un test du moteur ne doit jamais
        # supposer qu'il est seul dans la base.
        score, detail = self.instance._score_candidate(
            self.perfect,
            self.Criteria.search([
                ('definition_id', '=', self.definition.id),
                ('code', '=', 'competences'),
            ]))
        self.assertAlmostEqual(score, 100.0, places=2)
        self.assertIn("", detail)

    # ------------------------------------------------------------
    # Le détail est obligatoire et explique le score
    # ------------------------------------------------------------

    def test_detail_lists_every_criterion_with_its_weight(self):
        """Un score de 87 % sans explication n'est pas défendable."""
        self._default_criteria()
        candidates = self.instance.run_matching(partners=self.pool)
        candidate = candidates.filtered(lambda c: c.partner_id == self.partial)

        detail = candidate.detail
        self.assertTrue(detail)
        # Chaque critère y figure, avec son issue et son poids.
        self.assertIn("Secteur", detail)
        self.assertIn("Localisation", detail)
        self.assertIn("", detail)
        self.assertIn("", detail)
        self.assertIn("poids 3", detail)
        # Et le total est lisible sans recalcul.
        self.assertIn("75", detail)

    def test_detail_shows_the_compared_values(self):
        self._default_criteria()
        score, detail = self.instance._score_candidate(
            self.partial, self.Criteria.search([('definition_id', '=', self.definition.id)]))
        self.assertIn("alger", detail.lower())
        self.assertIn("oran", detail.lower())

    def test_detail_is_required_by_the_model(self):
        """La contrainte est dans le schéma, pas seulement dans la convention."""
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.Candidate.create({
                    'instance_id': self.instance.id,
                    'partner_id': self.perfect.id,
                    'candidate_type': 'expert',
                    'score': 87.0,
                })

    # ------------------------------------------------------------
    # Tolérance : un critère fautif ne fausse pas le classement
    # ------------------------------------------------------------

    def test_broken_criterion_is_neutralised_not_counted_as_failure(self):
        """Le pénaliser ferait chuter tout le monde également et rendrait le
        classement dépendant d'une faute de configuration."""
        self._criterion('secteur', "field('function')",
                        'function', weight=1.0)
        self._criterion('casse', "record.champ_inexistant.foo()", 'city',
                        weight=99.0)
        criteria = self.Criteria.search([('definition_id', '=', self.definition.id)])

        score, detail = self.instance._score_candidate(self.perfect, criteria)
        # Seul le critère lisible compte : 1/1 = 100 %.
        self.assertAlmostEqual(score, 100.0, places=2)
        self.assertIn("non évalué", detail)

    def test_unknown_target_field_is_reported_not_fatal(self):
        self._criterion('inconnu', "field('function')", 'champ_absent')
        criteria = self.Criteria.search([('definition_id', '=', self.definition.id)])
        score, detail = self.instance._score_candidate(self.perfect, criteria)
        self.assertAlmostEqual(score, 0.0, places=2)
        self.assertIn("n'existe pas", detail)

    def test_matching_without_criteria_is_explicit(self):
        with self.assertRaises(UserError) as error:
            self.instance.run_matching(partners=self.pool)
        self.assertIn("critère", str(error.exception))

    # ------------------------------------------------------------
    # L'IA recommande, elle ne décide pas
    # ------------------------------------------------------------

    def test_matching_triggers_no_transition(self):
        """Aucune transition ne se déclenche sur la base d'un score."""
        self._default_criteria()
        stage_before = self.instance.current_stage_id
        history_before = len(self.instance.history_ids)

        self.instance.run_matching(partners=self.pool)

        self.assertEqual(self.instance.current_stage_id, stage_before)
        self.assertEqual(self.instance.state, 'running')
        self.assertEqual(len(self.instance.history_ids), history_before)

    def test_matching_writes_nothing_on_the_business_record(self):
        self._default_criteria()
        before = self.record.read()[0]
        self.instance.run_matching(partners=self.pool)
        self.assertEqual(self.record.read()[0], before)

    def test_accepting_a_candidate_does_not_move_the_record(self):
        self._default_criteria()
        candidates = self.instance.run_matching(partners=self.pool)
        stage_before = self.instance.current_stage_id

        candidates[0].action_accept()

        self.assertEqual(candidates[0].state, 'accepted')
        self.assertEqual(self.instance.current_stage_id, stage_before)

    def test_the_four_human_decisions_are_available(self):
        self._default_criteria()
        candidate = self.instance.run_matching(partners=self.pool, limit=1)

        candidate.action_accept()
        self.assertEqual(candidate.state, 'accepted')
        self.assertEqual(candidate.decided_by_id, self.env.user)
        self.assertTrue(candidate.decision_date)

        candidate.action_reject()
        self.assertEqual(candidate.state, 'rejected')
        candidate.action_exclude()
        self.assertEqual(candidate.state, 'excluded')
        candidate.action_reset()
        self.assertEqual(candidate.state, 'proposed')

    def test_a_manual_candidate_can_be_added(self):
        """« Ajouter » fait partie des quatre gestes du responsable."""
        outsider = self.env['res.partner'].create({'name': "Choix du responsable"})
        candidate = self.Candidate.create({
            'instance_id': self.instance.id,
            'partner_id': outsider.id,
            'candidate_type': 'expert',
            'detail': "Ajouté à la main par le responsable.",
            'added_manually': True,
            'state': 'accepted',
        })
        self.assertTrue(candidate.added_manually)

    def test_rerunning_matching_preserves_human_arbitrations(self):
        """Relancer le calcul ne doit pas effacer une décision prise."""
        self._default_criteria()
        candidates = self.instance.run_matching(partners=self.pool)
        kept = candidates.filtered(lambda c: c.partner_id == self.partial)
        kept.action_accept()

        self.instance.run_matching(partners=self.pool)

        self.assertTrue(kept.exists())
        self.assertEqual(kept.state, 'accepted')
        # Et il n'est pas proposé une seconde fois.
        self.assertEqual(len(self.Candidate.search([
            ('instance_id', '=', self.instance.id),
            ('partner_id', '=', self.partial.id),
        ])), 1)

    # ------------------------------------------------------------
    # L'action run_matching (le stub de l'Extension 4)
    # ------------------------------------------------------------

    def test_run_matching_action_no_longer_raises(self):
        self._default_criteria()
        action = self.env['opex.workflow.action'].create({
            'name': "Chercher des experts", 'code': 'act_match_ok',
            'action_type': 'run_matching',
            'matching_candidate_type': 'expert',
            'matching_limit': 2,
        })
        detail = action.execute(self.instance)
        self.assertIn("2", detail)
        self.assertEqual(len(self.Candidate.search(
            [('instance_id', '=', self.instance.id)])), 2)

    def test_run_matching_action_does_not_advance_the_workflow(self):
        self._default_criteria()
        transition = self.definition.transition_ids.filtered(
            lambda t: t.code == 'submit')
        action = self.env['opex.workflow.action'].create({
            'name': "Matching", 'code': 'act_match_side',
            'action_type': 'run_matching',
        })
        transition.action_ids = [(6, 0, action.ids)]

        self.instance.do_transition(transition)

        # La transition demandée a eu lieu — une seule, celle qu'on a demandée.
        self.assertEqual(
            self.instance.current_stage_id,
            self.definition.stage_ids.filtered(lambda s: s.code == 'review'))
        self.assertTrue(self.Candidate.search(
            [('instance_id', '=', self.instance.id)]))
        # Et aucune transition supplémentaire n'a été déclenchée par les scores.
        self.assertEqual(self.instance.state, 'running')

    # ------------------------------------------------------------
    # Mise en relation contrôlée
    # ------------------------------------------------------------

    def test_teaser_level_does_not_open_the_file(self):
        """Le match ne signifie pas partage du dossier complet."""
        relation = self.Relation.create({
            'instance_id': self.instance.id,
            'partner_id': self.perfect.id,
        })
        self.assertEqual(relation.access_level, 'teaser')
        with self.assertRaises(UserError) as error:
            relation.action_grant_workflow_access(
                self.env.ref('opex_workflow.role_expert'))
        self.assertIn("teaser", str(error.exception).lower())

    def test_granting_access_goes_through_add_actor(self):
        # `new_test_user` plutôt qu'un `create()` à la main : la création d'un
        # utilisateur traverse auth_signup et mail, qui exigent des champs que
        # ce test n'a aucune raison de connaître.
        user = new_test_user(
            self.env, login='match_expert', groups='base.group_portal')
        relation = self.Relation.create({
            'instance_id': self.instance.id,
            'partner_id': user.partner_id.id,
            'access_level': 'limited',
        })
        relation.action_grant_workflow_access(
            self.env.ref('opex_workflow.role_expert'))
        self.assertTrue(self.instance._has_access(user, 'limited'))

    def test_nda_is_recorded_with_its_date(self):
        relation = self.Relation.create({
            'instance_id': self.instance.id,
            'partner_id': self.perfect.id,
        })
        self.assertFalse(relation.nda_signed)
        relation.action_sign_nda()
        self.assertTrue(relation.nda_signed)
        self.assertTrue(relation.nda_date)
