from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestSmartMatching(TransactionCase):
    """Extension 4 — le Smart Matching, **configuré** et non réécrit.

    Quatre exigences à prouver, et elles sont toutes des critères
    d'acceptation du §21 :

    1. les pondérations sont configurables **par type de mission ou par appel** ;
    2. les critères éliminatoires sont évalués **avant** le score pondéré, et
       un candidat qui en rate un est **écarté**, pas mal noté ;
    3. le score est **explicable** — stocké, lisible, rattaché aux critères ;
    4. **aucune transition n'est déclenchée par un score**, nulle part.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Mission = cls.env['opex.mission.request']
        cls.Criteria = cls.env['opex.matching.criteria']
        cls.Candidate = cls.env['opex.matching.candidate']
        cls.Application = cls.env['opex.mission.application']

        cls.definition = cls.env['opex.workflow.definition']._get_for_code(
            'mission_request')
        cls.audit = cls.env.ref('opex_intervenants.mission_type_audit')
        cls.formation = cls.env.ref('opex_intervenants.mission_type_formation')
        cls.conseil = cls.env.ref('opex_intervenants.mission_type_conseil')
        cls.domaine = cls.env.ref(
            'opex_intervenants.mission_domain_cybersecurite')
        cls.autre_domaine = cls.env.ref(
            'opex_intervenants.mission_domain_finance')

        cls.client_user = new_test_user(
            cls.env, login='sm_client', groups='base.group_portal')
        cls.manager = new_test_user(
            cls.env, login='sm_manager',
            groups='base.group_user,opex_intervenants.group_mission_manager')

        cls.competence = cls.env['opex.innovation.competence'].create(
            {'name': "Cybersécurité", 'code': 'sm_cyber'})
        cls.autre_competence = cls.env['opex.innovation.competence'].create(
            {'name': "Comptabilité", 'code': 'sm_compta'})

    # ------------------------------------------------------------
    # Fabriques
    # ------------------------------------------------------------

    @classmethod
    def _today(cls, **delta):
        return fields.Date.context_today(cls.env['opex.mission.request']) \
            + timedelta(**delta)

    def _expert(self, login, competences=None, domaine=None, seniorite='senior',
                dispo=True, tjm=20000.0, certifications=None, wilaya="Alger"):
        """Un intervenant complet, prêt à être noté."""
        user = new_test_user(
            self.env, login=login, groups='base.group_portal')
        user.partner_id.sudo().write({'wilaya': wilaya})
        profile = self.env['opex.innovation.expert.profile'].sudo().create({
            'partner_id': user.partner_id.id,
            'domaine_expertise': "Sécurité",
            'annees_experience': 12,
            'tjm_indicatif': tjm,
            'langues': "Français, Anglais",
        })
        profile.action_activate_profile()

        for competence in (competences or []):
            self.env['opex.expert.skill'].sudo().create({
                'profile_id': profile.id,
                'competence_id': competence.id,
                'niveau': 'expert', 'annees': 10,
            })
        self.env['opex.expert.experience'].sudo().create({
            'profile_id': profile.id, 'name': "Mission passée",
            'domaine_id': (domaine or self.domaine).id,
            'mission_type_id': self.audit.id,
            'seniorite': seniorite,
        })
        if dispo:
            self.env['opex.expert.availability'].sudo().create({
                'profile_id': profile.id,
                'date_debut': self._today(days=-1),
                'date_fin': self._today(days=90),
                'taux': 100,
            })
        # D1 : la certification est **rapprochée** au référentiel. Un
        # intitulé libre n'entre plus dans le critère éliminatoire, et c'est
        # tout l'objet de la dette refermée - il n'était comparable à rien.
        Synonyme = self.env['opex.certification.synonyme']
        for intitule in (certifications or []):
            canonique = Synonyme.resolve_label(intitule)
            self.assertTrue(
                canonique,
                "« %s » n'est pas au référentiel : le scénario du test ne "
                "mesurerait rien." % intitule)
            self.env['opex.expert.certification'].sudo().create({
                'profile_id': profile.id, 'name': intitule,
                'certification_id': canonique.id,
                'source': 'expert', 'confiance': 'expert',
                'date_expiration': self._today(days=365),
            })
        user.partner_id.invalidate_recordset()
        return user.partner_id

    def _mission(self, mission_type=None, **overrides):
        values = {
            'title': "Audit cybersécurité",
            'mission_type_id': (mission_type or self.audit).id,
            'client_id': self.client_user.partner_id.id,
            'description': "Audit du SI.", 'objectifs': "Cartographier.",
            'domaine_id': self.domaine.id,
            'skill_ids': [(6, 0, self.competence.ids)],
            'niveau_experience': 'senior',
            'wilaya': "Alger",
            'budget_estimatif': 300000.0,
            'duree_estimee_jours': 15,
            'date_limite_candidature': self._today(days=30),
        }
        values.update(overrides)
        return self.Mission.create(values)

    def _family_weights(self, mission):
        return {c.family: c.weight for c in mission.matching_criteria()}

    #
    # ON N'A PAS ÉCRIT UN SECOND MOTEUR
    #

    def test_the_module_defines_no_scoring_of_its_own(self):
        """Le calcul reste celui d'`opex_workflow`.

        Ce module résout des critères et écarte des candidats ; il ne note pas.
        Si `_score_candidate` ou `_compare` étaient redéfinis ici, la
        démonstration « on configure, on ne réécrit pas » tomberait.
        """
        import inspect

        from odoo.addons.opex_intervenants.models import matching

        source = inspect.getsource(matching)
        for interdit in ('def _score_candidate', 'def _compare',
                         'def _as_set'):
            self.assertNotIn(
                interdit, source,
                "Ce module redéfinit « %s » : le scoring du moteur est "
                "réécrit." % interdit)

    def test_the_engine_criteria_model_is_only_extended(self):
        """Trois champs ajoutés par `_inherit`, aucun comportement changé.

        Les critères d'`opex_innovation` les portent aussi, vides, et sa
        résolution passe par `run_matching()` qui ne les lit jamais.
        """
        champs = self.Criteria._fields
        for name in ('family', 'mission_type_id', 'mission_id',
                     'is_eliminatoire'):
            self.assertIn(name, champs)
        for name in ('weight', 'source_expression', 'target_field',
                     'match_mode', 'definition_id'):
            self.assertIn(name, champs, "Champ du moteur disparu : %s" % name)

        innovation = self.Criteria.sudo().search(
            [('definition_id.code', '=', 'innovation_project')], limit=1)
        if innovation:
            self.assertFalse(innovation.mission_type_id)
            self.assertFalse(innovation.is_eliminatoire)

    #
    # LES SEPT CRITÈRES DU §11
    #

    def test_the_seven_criteria_carry_the_specification_weights(self):
        mission = self._mission(mission_type=self.conseil)
        poids = self._family_weights(mission)
        self.assertEqual(poids, {
            'competences': 30.0, 'experience': 20.0, 'secteur': 15.0,
            'disponibilite': 10.0, 'budget': 10.0, 'reputation': 10.0,
            'localisation': 5.0,
        })
        self.assertEqual(sum(poids.values()), 100.0)

    #
    # PONDÉRATIONS CONFIGURABLES — §11
    #

    def test_a_mission_type_profile_overrides_by_family(self):
        """« Configurables par type de mission. »

        Et **par famille** : le profil Formation ne redéclare que trois
        critères, les quatre autres restent hérités du défaut. Sans cela,
        chaque nouveau type obligerait à recopier les sept.
        """
        audit = self._family_weights(self._mission(mission_type=self.audit))
        formation = self._family_weights(
            self._mission(mission_type=self.formation))

        self.assertEqual(audit['competences'], 30.0)
        self.assertEqual(formation['competences'], 40.0)
        self.assertEqual(formation['secteur'], 5.0)
        self.assertEqual(formation['disponibilite'], 15.0)
        # Les familles non redéclarées sont héritées, pas perdues.
        self.assertEqual(formation['budget'], audit['budget'])
        self.assertEqual(formation['reputation'], audit['reputation'])
        self.assertEqual(formation['localisation'], audit['localisation'])

    def test_a_mission_may_carry_its_own_weights(self):
        """« …ou par appel. » Le troisième niveau, qui l'emporte sur les deux."""
        mission = self._mission(mission_type=self.formation)
        mission.action_customise_matching_criteria()
        self.assertTrue(mission.matching_is_customised)

        propre = mission.matching_criteria_ids.filtered(
            lambda c: c.family == 'competences')
        self.assertEqual(len(propre), 1)
        self.assertEqual(propre.weight, 40.0, "Le profil du type n'a pas été "
                                              "recopié comme point de départ.")

        propre.weight = 60.0
        mission.invalidate_recordset()
        self.assertEqual(self._family_weights(mission)['competences'], 60.0)

        # …et l'appel voisin, du même type, n'a pas bougé.
        voisin = self._mission(mission_type=self.formation)
        self.assertEqual(self._family_weights(voisin)['competences'], 40.0)

    def test_customising_twice_is_refused(self):
        mission = self._mission()
        mission.action_customise_matching_criteria()
        with self.assertRaises(UserError):
            mission.action_customise_matching_criteria()

    def test_the_weights_change_the_ranking(self):
        """La configurabilité n'a d'intérêt que si elle change le classement.

        Deux experts : l'un a la compétence mais pas le domaine, l'autre
        l'inverse. En audit, le domaine pèse 15 et la compétence 30 ; en
        formation, 5 et 40. Le second doit reculer.
        """
        competent = self._expert(
            'sm_competent', competences=[self.competence],
            domaine=self.autre_domaine)
        sectoriel = self._expert(
            'sm_sectoriel', competences=[self.autre_competence],
            domaine=self.domaine)

        scores = {}
        for mission_type in (self.audit, self.formation):
            mission = self._mission(mission_type=mission_type,
                                    certifications_souhaitees=False)
            mission.run_smart_matching()
            scores[mission_type.code] = {
                c.partner_id: c.score for c in mission.matching_candidate_ids
            }

        # L'écart entre les deux se creuse quand les compétences passent de
        # 30 % à 40 % et le secteur de 15 % à 5 %.
        ecart_audit = (scores['audit'][competent]
                       - scores['audit'][sectoriel])
        ecart_formation = (scores['formation'][competent]
                           - scores['formation'][sectoriel])
        self.assertGreater(
            ecart_formation, ecart_audit,
            "Changer les pondérations n'a pas changé le classement : la "
            "configurabilité du §11 n'est pas effective.")

    #
    # LES CRITÈRES ÉLIMINATOIRES — AVANT LE SCORE
    #

    def test_an_eliminated_candidate_is_absent_not_badly_rated(self):
        """Le critère d'acceptation du §21, dans sa formulation exacte.

        « Un candidat qui ne remplit pas un critère obligatoire est écarté, pas
        mal noté. » Donc : **absent de la liste**, et pas présent avec un petit
        score.
        """
        certifie = self._expert(
            'sm_certifie', competences=[self.competence],
            certifications=["ISO 27001"])
        non_certifie = self._expert(
            'sm_non_certifie', competences=[self.competence])

        # D1 : l'exigence est une **référence**, plus un texte.
        mission = self._mission(certifications_souhaitees=False)
        mission.sudo().certification_ids = [(6, 0, self.env.ref(
            'opex_membership.certification_iso_27001').ids)]
        mission.run_smart_matching()

        proposes = mission.matching_candidate_ids.partner_id
        # Assertion positive d'abord : le certifié est bien là.
        self.assertIn(certifie, proposes)
        # …et l'autre n'y est pas **du tout**.
        self.assertNotIn(
            non_certifie, proposes,
            "Un candidat sans la certification obligatoire a été noté au lieu "
            "d'être écarté.")
        self.assertFalse(
            self.Candidate.sudo().search([
                ('instance_id', '=', mission.workflow_instance_id.id),
                ('partner_id', '=', non_certifie.id),
            ]),
            "L'écarté a quand même une ligne de candidat : il est mal noté, "
            "pas écarté.")

    def test_the_exclusion_is_explained(self):
        """Un responsable qui ne voit pas un expert attendu doit savoir pourquoi.

        Sans ce compte rendu, un critère éliminatoire mal réglé est
        indétectable : la liste est simplement plus courte.
        """
        self._expert('sm_sans_certif', competences=[self.competence])
        mission = self._mission(certifications_souhaitees=False)
        mission.sudo().certification_ids = [(6, 0, self.env.ref(
            'opex_membership.certification_iso_27001').ids)]
        mission.run_smart_matching()

        self.assertEqual(mission.matching_excluded_count, 1)
        self.assertIn("Certification exigée", mission.matching_excluded_note)

    def test_an_eliminatory_criterion_the_mission_does_not_express_is_ignored(self):
        """Le défaut qui aurait vidé le vivier.

        Le critère éliminatoire du type Audit lit
        `certifications_souhaitees`. Si l'appel ne demande **aucune**
        certification, `_compare()` répond « aucune attente exprimée sur le
        dossier », donc faux, donc tout le monde serait écarté et la liste
        serait vide sans que rien ne l'explique.

        Le §6 dit « obligatoires ou préférentiels **selon la mission** » : un
        critère que l'appel n'exprime pas ne s'applique pas.
        """
        expert = self._expert('sm_libre', competences=[self.competence])
        mission = self._mission(certifications_souhaitees=False)
        mission.run_smart_matching()

        self.assertIn(expert, mission.matching_candidate_ids.partner_id)
        self.assertEqual(mission.matching_excluded_count, 0)

    def test_an_eliminatory_criterion_carries_no_weight(self):
        """Il n'entre pas dans la somme des poids : il écarte, il ne note pas."""
        mission = self._mission(mission_type=self.audit)
        criteres = mission.matching_criteria()
        eliminatoires = criteres.filtered('is_eliminatoire')
        self.assertTrue(eliminatoires, "Le profil Audit n'a plus de critère "
                                       "éliminatoire : le test ne prouve rien.")
        self.assertEqual(sum(eliminatoires.mapped('weight')), 0.0)
        self.assertEqual(sum((criteres - eliminatoires).mapped('weight')), 100.0)

    def test_the_vivier_excludes_non_experts(self):
        """La forme la plus grossière de l'éliminatoire : on ne note pas
        quelqu'un qui n'est pas un intervenant."""
        self._expert('sm_dans_vivier', competences=[self.competence])
        quidam = new_test_user(
            self.env, login='sm_quidam', groups='base.group_portal')
        mission = self._mission(certifications_souhaitees=False)
        self.assertNotIn(quidam.partner_id, mission._matching_vivier())

    def test_an_existing_candidate_is_not_proposed_again(self):
        expert = self._expert('sm_deja', competences=[self.competence])
        mission = self._mission(certifications_souhaitees=False)
        self.Application.create({
            'mission_id': mission.id, 'partner_id': expert.id,
            'source': 'portail',
        })
        self.assertNotIn(expert, mission._matching_vivier())

    #
    # LE SCORE EST EXPLICABLE — §21
    #

    def test_every_proposal_carries_its_explanation(self):
        """« Le responsable peut comprendre les raisons d'un score. »

        Le moteur rend `detail` obligatoire au niveau du modèle ; on vérifie
        ici qu'il contient réellement de quoi défendre le score, critère par
        critère.
        """
        self._expert('sm_explique', competences=[self.competence])
        mission = self._mission(certifications_souhaitees=False)
        mission.run_smart_matching()

        candidat = mission.matching_candidate_ids[:1]
        self.assertTrue(candidat)
        detail = candidat.detail
        self.assertTrue(detail)

        # L'en-tête dit sur quoi le candidat a été jugé…
        self.assertIn("Critères appliqués", detail)
        # …le corps, ce qu'il en a rempli, critère par critère.
        self.assertIn("Compétences recherchées", detail)
        self.assertIn("Score", detail)
        # Positifs et manquants sont distingués.
        self.assertTrue('' in detail or '' in detail,
                        "L'explication ne distingue pas ce qui est rempli de "
                        "ce qui manque.")

    def test_the_explanation_names_the_weight_of_each_criterion(self):
        self._expert('sm_poids', competences=[self.competence])
        mission = self._mission(certifications_souhaitees=False)
        mission.run_smart_matching()
        detail = mission.matching_candidate_ids[:1].detail
        self.assertIn("poids", detail)
        self.assertIn("30", detail)

    def test_the_explanation_is_stored_not_recomputed(self):
        """Elle est figée au moment du calcul : c'est la trace de ce qui a été
        comparé, pas une reconstitution."""
        self.assertTrue(self.Candidate._fields['detail'].store)
        self.assertTrue(self.Candidate._fields['detail'].required)

    #
    # L'IA RECOMMANDE, L'HUMAIN DÉCIDE
    #

    def test_matching_moves_no_stage(self):
        """Aucune transition déclenchée par un score, nulle part."""
        self._expert('sm_neutre', competences=[self.competence])
        mission = self._mission(certifications_souhaitees=False)
        avant = mission.workflow_stage_id.code
        mission.run_smart_matching()
        mission.invalidate_recordset()
        self.assertEqual(mission.workflow_stage_id.code, avant)
        self.assertEqual(mission.workflow_stage_id.code, 'draft')

    def test_no_transition_condition_reads_a_score(self):
        """La preuve par la configuration : aucune règle du workflow mission ne
        lit un score de matching."""
        for transition in self.definition.sudo().transition_ids:
            for rule in transition.condition_ids:
                self.assertNotIn(
                    'score', (rule.expression or '').lower(),
                    "La transition « %s » est conditionnée par un score : "
                    "l'IA déciderait à la place de l'humain." % transition.code)

    def test_inviting_creates_an_application_and_moves_nothing(self):
        """« Inviter » est un geste humain, et il n'engage que la candidature.

        La candidature naît sur **sa propre** machine à états ; l'appel reste
        où il est. C'est l'indépendance des deux workflows.
        """
        expert = self._expert('sm_invite', competences=[self.competence])
        mission = self._mission(certifications_souhaitees=False)
        mission.run_smart_matching()
        candidat = mission.matching_candidate_ids.filtered(
            lambda c: c.partner_id == expert)

        etape_avant = mission.workflow_stage_id.code
        candidat.action_invite_to_mission()

        application = self.Application.sudo().search([
            ('mission_id', '=', mission.id), ('partner_id', '=', expert.id)])
        self.assertEqual(len(application), 1)
        self.assertEqual(application.source, 'matching')
        self.assertEqual(application.workflow_stage_id.code, 'invited')
        self.assertEqual(application.matching_candidate_id, candidat)
        self.assertEqual(candidat.state, 'accepted')

        mission.invalidate_recordset()
        self.assertEqual(mission.workflow_stage_id.code, etape_avant)

    def test_the_score_is_frozen_on_the_application(self):
        """Recalculer le matching ne réécrit pas ce sur quoi la décision a été
        prise."""
        expert = self._expert('sm_fige', competences=[self.competence])
        mission = self._mission(certifications_souhaitees=False)
        mission.run_smart_matching()
        candidat = mission.matching_candidate_ids.filtered(
            lambda c: c.partner_id == expert)
        candidat.action_invite_to_mission()

        application = self.Application.sudo().search([
            ('mission_id', '=', mission.id), ('partner_id', '=', expert.id)])
        score_initial = application.score
        self.assertTrue(application.score_detail)

        # Le capital change, le matching est relancé…
        mission.write({'skill_ids': [(6, 0, self.autre_competence.ids)]})
        mission.run_smart_matching()
        application.invalidate_recordset()
        # …la candidature garde le score sur lequel on l'a invitée.
        self.assertEqual(application.score, score_initial)

    def test_a_human_decision_survives_a_new_run(self):
        """Relancer le matching n'efface pas un arbitrage."""
        expert = self._expert('sm_arbitre', competences=[self.competence])
        mission = self._mission(certifications_souhaitees=False)
        mission.run_smart_matching()
        candidat = mission.matching_candidate_ids.filtered(
            lambda c: c.partner_id == expert)
        candidat.action_reject()

        mission.run_smart_matching()
        mission.invalidate_recordset()
        survivant = mission.matching_candidate_ids.filtered(
            lambda c: c.partner_id == expert)
        self.assertEqual(len(survivant), 1)
        self.assertEqual(
            survivant.state, 'rejected',
            "Un nouveau passage du matching a effacé une décision humaine.")

    #
    # LES GARDE-FOUS
    #

    def test_matching_without_criteria_is_refused_with_a_reason(self):
        mission = self._mission()
        mission.matching_criteria().sudo().write({'active': False})
        mission.invalidate_recordset()
        with self.assertRaises(UserError) as error:
            mission.run_smart_matching()
        self.assertIn("critère de matching", str(error.exception))

    def test_the_budget_criterion_compares_daily_rates(self):
        """L'arbitrage du 30/08, vérifié.

        La mission porte un budget **total**, l'expert un tarif **journalier**.
        300 000 sur 15 jours = 20 000 par jour : un expert à 20 000 passe, un
        expert à 50 000 non.
        """
        abordable = self._expert(
            'sm_abordable', competences=[self.competence], tjm=20000.0)
        cher = self._expert(
            'sm_cher', competences=[self.competence], tjm=50000.0)
        mission = self._mission(certifications_souhaitees=False,
                                budget_estimatif=300000.0,
                                duree_estimee_jours=15)
        mission.run_smart_matching()

        scores = {c.partner_id: c.score for c in mission.matching_candidate_ids}
        self.assertGreater(
            scores[abordable], scores[cher],
            "Le critère budget ne distingue pas les deux : la division par la "
            "durée n'est pas appliquée.")

    def test_a_zero_duration_does_not_break_the_budget_criterion(self):
        """Le `or 1` de l'expression : une durée non renseignée ne doit pas
        faire échouer le critère pour une raison sans rapport avec le
        candidat."""
        self._expert('sm_sans_duree', competences=[self.competence])
        mission = self._mission(certifications_souhaitees=False,
                                duree_estimee_jours=0)
        proposes = mission.run_smart_matching()
        self.assertTrue(proposes)
        self.assertNotIn("non évalué", proposes[:1].detail)
