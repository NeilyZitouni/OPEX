"""IA-1 : les trois axes du §9 sur une compétence qualifiée.

Niveau, source et confiance répondent à trois questions différentes, et le
matching n'en lit qu'une. La lecture du CV elle-même est ailleurs, dans
`test_cv_parsing.py`.
"""

from odoo.tests.common import tagged

from .common import MissionCase


@tagged('post_install', '-at_install')
class TestSkillAxes(MissionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Profile = cls.env['opex.innovation.expert.profile']
        cls.Skill = cls.env['opex.expert.skill']

    def _profile(self):
        """Un profil expert activé, comme à l'Extension 10.

        Le lien sur le partenaire est ce qui distingue « avoir déposé un
        profil » de « être référencé au vivier » : sans lui, aucun des champs
        de matching de `res.partner` ne voit le profil.
        """
        partner = self.intervenant.partner_id
        profile = self.Profile.sudo().search(
            [('partner_id', '=', partner.id)], limit=1)
        if not profile:
            profile = self.Profile.sudo().create({'partner_id': partner.id})
        partner.sudo().expert_profile_id = profile.id
        return profile

    def _skill(self, profile, **overrides):
        values = {
            'profile_id': profile.id,
            'competence_id': self.competence.id,
            'niveau': 'confirme',
        }
        values.update(overrides)
        return self.Skill.sudo().create(values)

    #
    # §9 - les trois axes
    #

    def test_a_qualified_skill_carries_three_axes(self):
        """Niveau, source, confiance : trois questions, trois champs.

        Les confondre rendrait impossible de distinguer « junior, extrait
        avec certitude » de « expert, extrait avec doute » - et c'est le
        second cas que le §12 doit remonter.
        """
        fields_ = self.Skill._fields
        for axis in ('niveau', 'source', 'confiance'):
            self.assertIn(axis, fields_)

        self.assertEqual(
            [value for value, _label in fields_['source'].selection],
            ['cv', 'expert', 'opex', 'mission'])
        self.assertEqual(
            [value for value, _label in fields_['confiance'].selection],
            ['ia', 'expert', 'opex'])

    def test_the_existing_lines_are_declared_by_the_expert(self):
        """Le défaut choisi pour les lignes déjà en base.

        Elles ont été saisies par l'expert depuis son espace portail à
        l'Extension 3. Un défaut à « proposé par l'IA » aurait discrédité d'un
        coup tout le capital déjà déclaré, et l'aurait retiré du matching par
        la même occasion.
        """
        skill = self._skill(self._profile())
        self.assertEqual(skill.source, 'expert')
        self.assertEqual(skill.confiance, 'expert')
        self.assertTrue(skill.is_confirmed)

    def test_the_confidence_is_a_counter_not_a_process(self):
        """Trois positions, aucun chemin de refus : un compteur.

        Proposé -> confirmé -> vérifié est une progression, et la question
        mérite d'être posée. C'est la ligne de partage que le CLAUDE.md du
        moteur pose pour `roadmap.phase` et que l'Extension 8 a appliquée à
        l'incident du §26.

        Ce test verrouille le critère : une quatrième position, ou un
        workflow sur ce modèle, et la conversation a lieu.
        """
        self.assertNotIn(
            'workflow_instance_id', self.Skill._fields,
            "La ligne de compétence a reçu un workflow : mettez à jour ce "
            "test et le CLAUDE.md, la décision a changé.")
        self.assertEqual(
            len(self.Skill._fields['confiance'].selection), 3,
            "Le cycle de confiance a gagné une issue : ce n'est plus un "
            "compteur mais un processus.")

    def test_confirming_does_not_touch_the_level_or_the_source(self):
        """Ce qui change, c'est ce que l'information vaut.

        Pas ce qu'elle dit, pas d'où elle vient. Les trois axes sont
        indépendants, et un `action_confirm` qui remonterait le niveau serait
        exactement la confusion que le §9 interdit.
        """
        skill = self._skill(
            self._profile(), niveau='debutant', source='cv', confiance='ia')
        skill.action_confirm()

        self.assertEqual(skill.confiance, 'expert')
        self.assertEqual(skill.niveau, 'debutant')
        self.assertEqual(skill.source, 'cv')

    #
    # La conséquence sur le matching
    #

    def test_an_unconfirmed_skill_does_not_reach_the_matching(self):
        """Le point qui compte de toute l'IA-1.

        Sans ce filtre, une compétence proposée par l'IA à la lecture d'un CV
        ferait matcher l'expert dès l'extraction, avant que quiconque se soit
        prononcé. Le défaut aurait été silencieux et flatteur : plus de
        compétences, donc de meilleurs scores.
        """
        profile = self._profile()
        partner = profile.partner_id

        skill = self._skill(profile, source='cv', confiance='ia')
        partner.invalidate_recordset()
        self.assertNotIn(
            self.competence, partner.sudo().expert_skill_competence_ids,
            "Une compétence proposée par l'IA entre dans le matching sans "
            "que personne l'ait confirmée.")

        # Assertion positive : une fois confirmée, elle y entre.
        skill.action_confirm()
        partner.invalidate_recordset()
        self.assertIn(
            self.competence, partner.sudo().expert_skill_competence_ids)

    def test_confirming_makes_the_expert_matchable_immediately(self):
        """La dépendance de recalcul, sans laquelle le filtre serait un piège.

        Le champ de matching dépend de `is_confirmed`. Sans cette dépendance,
        confirmer une compétence ne rendrait l'expert matchable qu'au
        prochain recalcul - c'est-à-dire à un moment quelconque, et invisible.
        """
        profile = self._profile()
        partner = profile.partner_id
        skill = self._skill(profile, source='cv', confiance='ia')

        self.assertNotIn(
            self.competence, partner.sudo().expert_skill_competence_ids)
        skill.confiance = 'expert'
        # Pas d'invalidation manuelle : c'est tout l'objet du test.
        self.assertIn(
            self.competence, partner.sudo().expert_skill_competence_ids,
            "Le champ de matching ne dépend pas de `is_confirmed`.")

