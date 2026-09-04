from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import tagged

from .common import MissionCase

EVALUATION_CODE = 'mission_evaluation'


@tagged('post_install', '-at_install')
class TestEvaluation(MissionCase):
    """Extension 10 - évaluations, réputation, historique."""

    def _closed_mission(self, **overrides):
        """Une mission clôturée : ses évaluations viennent de s'ouvrir."""
        mission = self._new_mission(**overrides)
        self._open_the_call(mission)
        self._select_the_application(self._new_application(mission))
        self._do(mission, 'mission_close_applications', self.manager)
        self._do(mission, 'mission_award', self.decideur,
                 comment="Candidature retenue par le comité.")
        self._validate_the_contract(mission)
        self._do(mission, 'mission_start', self.manager)
        self._do(mission, 'mission_deliver', self.manager)
        self._run_service_acceptance_cycle(mission)
        self._do(mission, 'mission_accept_service', self.manager)
        self._do(mission, 'mission_close', self.secretariat,
                 comment="Mission clôturée par le test.")
        mission.invalidate_recordset()
        return mission

    def _evaluation(self, mission, evaluateur):
        return mission.sudo().evaluation_ids.filtered(
            lambda e: e.evaluateur == evaluateur)

    def _fill(self, evaluation, score=4, **overrides):
        """Remplit les six critères applicables à cette grille."""
        values = {name: score for name in evaluation._criteria_fields()}
        values.update(overrides)
        values.setdefault('commentaire', "Prestation conforme aux attentes.")
        evaluation.sudo().write(values)
        return evaluation

    def _validate(self, evaluation, user=None):
        self._do(evaluation, 'evaluation_submit', user or self.client_user)
        self._do(evaluation, 'evaluation_validate', self.manager)
        return evaluation

    def _expert_profile(self):
        """Le profil expert de l'intervenant du socle de test, activé.

        Le lien `res.partner.expert_profile_id` n'est pas déduit du profil :
        c'est le Module 2 qui le pose au moment de l'activation, et c'est lui
        qui distingue « avoir déposé un profil » de « être référencé au
        vivier ». Un profil créé sans ce lien existe, mais aucun des huit
        champs de matching de `res.partner` ne le voit — ce qui est le
        comportement voulu, et ce que ce helper doit donc reproduire.
        """
        Profile = self.env['opex.innovation.expert.profile'].sudo()
        partner = self.intervenant.partner_id
        existing = Profile.search([('partner_id', '=', partner.id)], limit=1)
        profile = existing or Profile.create({'partner_id': partner.id})
        partner.sudo().expert_profile_id = profile.id
        return profile

    # La règle du module

    def test_the_evaluation_has_no_state_field(self):
        fields_ = self.env['opex.mission.evaluation']._fields
        for suspect in ('state', 'etat', 'statut', 'status', 'stage_id',
                        'avancement', 'phase', 'etape'):
            self.assertNotIn(
                suspect, fields_,
                "L'évaluation porte « %s » : son parcours doit être "
                "`workflow_stage_id`." % suspect)
        self.assertIn('workflow_instance_id', fields_)

    def test_the_evaluation_workflow_is_a_graph_not_a_sequence(self):
        """Quatre étapes, quatre transitions, une seule finale.

        Le renvoi pour complément et sa reprise sont ce qui distingue ce cycle
        d'une file d'attente. Sans eux, une évaluation mal remplie serait
        soit validée telle quelle, soit perdue.
        """
        definition = self.Definition._get_for_code(EVALUATION_CODE)
        self.assertEqual(definition.state, 'published')
        self.assertEqual(definition.model_name, 'opex.mission.evaluation')

        self.assertEqual(
            set(definition.stage_ids.mapped('code')),
            {'pending', 'submitted', 'returned', 'validated'})

        transitions = set(definition.transition_ids.mapped('code'))
        self.assertIn('evaluation_return', transitions)
        self.assertIn('evaluation_resume', transitions)

        finals = definition.stage_ids.filtered('is_end')
        self.assertEqual(
            [stage.code for stage in finals], ['validated'],
            "Plus d'une étape finale : une évaluation renvoyée à son auteur "
            "ne pourrait plus revenir, et la note de la mission serait perdue.")

    # Les deux grilles

    def test_the_two_grids_open_at_closing(self):
        """§30 et §31 : une grille client et une grille cluster."""
        mission = self._closed_mission()
        evaluations = mission.sudo().evaluation_ids

        self.assertEqual(len(evaluations), 2)
        self.assertEqual(
            set(evaluations.mapped('evaluateur')), {'client', 'cluster'})
        self.assertEqual(
            set(evaluations.mapped('partner_id')),
            {self.intervenant.partner_id})
        for evaluation in evaluations:
            self.assertEqual(self._stage(evaluation), 'pending')
            self.assertTrue(evaluation.name.startswith('EVA-'))

    def test_each_grid_carries_the_six_criteria_of_its_section(self):
        """Les deux listes du document, à la lettre et dans son ordre."""
        mission = self._closed_mission()
        client = self._evaluation(mission, 'client')
        cluster = self._evaluation(mission, 'cluster')

        self.assertEqual(
            [entry['libelle'] for entry in client.evaluation_grid()],
            ["Qualité du travail", "Respect des délais", "Expertise",
             "Communication", "Pertinence des recommandations",
             "Satisfaction générale"])
        self.assertEqual(
            [entry['libelle'] for entry in cluster.evaluation_grid()],
            ["Respect du contrat", "Respect des délais",
             "Qualité des livrables", "Professionnalisme", "Communication",
             "Respect des procédures"])

    def test_the_overall_score_averages_the_applicable_criteria_only(self):
        """Les quatre critères de l'autre grille ne comptent pas.

        Les deux grilles partagent deux champs et vivent sur le même modèle.
        Une moyenne prise sur les dix champs ferait chuter chaque note de
        quatre zéros, et le §32 hériterait de l'erreur.
        """
        mission = self._closed_mission()
        client = self._fill(self._evaluation(mission, 'client'), score=5)

        client.invalidate_recordset()
        self.assertEqual(client.note_globale, 5.0)
        self.assertTrue(client.grille_complete)
        # Les champs de la grille cluster sont bien restés à zéro.
        self.assertEqual(client.note_contrat, 0)

    def test_an_incomplete_grid_cannot_be_submitted(self):
        mission = self._closed_mission()
        client = self._evaluation(mission, 'client')
        self._fill(client, score=4, note_satisfaction=0)

        with self.assertRaises(UserError) as refus:
            self._do(client, 'evaluation_submit', self.client_user)
        self.assertIn("six critères", str(refus.exception))

        client.sudo().note_satisfaction = 4
        self._do(client, 'evaluation_submit', self.client_user)
        self.assertEqual(self._stage(client), 'submitted')

    def test_a_score_outside_the_scale_is_refused(self):
        mission = self._closed_mission()
        client = self._evaluation(mission, 'client')
        with self.assertRaises(ValidationError):
            client.sudo().note_qualite = 6

    # Règle 7

    def test_the_client_cannot_evaluate_before_the_final_validation(self):
        """Règle 7 : condition de transition, pas contrôle applicatif.

        La grille est créée à la clôture, donc après la validation finale.
        Pour éprouver la règle il faut une évaluation créée à la main, ce que
        le back-office permet : c'est précisément le chemin qu'une condition
        garde et qu'un `if` dans le déclencheur laisserait passer.
        """
        mission = self._new_mission()
        self._open_the_call(mission)
        self._select_the_application(self._new_application(mission))

        evaluation = self.env['opex.mission.evaluation'].sudo().create({
            'mission_id': mission.id,
            'partner_id': self.intervenant.partner_id.id,
            'evaluateur': 'client',
        })
        self._fill(evaluation)
        self.assertFalse(evaluation.mission_validee)

        with self.assertRaises(UserError) as refus:
            self._do(evaluation, 'evaluation_submit', self.manager)
        self.assertIn("validation finale", str(refus.exception))
        self.assertEqual(self._stage(evaluation), 'pending')

    def test_the_rule_seven_is_attached_to_the_submission(self):
        """La lecture de la configuration, à côté de la mesure.

        Vérifier qu'une règle bloque ne dit pas qu'elle est au bon endroit, et
        vérifier qu'elle est rattachée ne dit pas qu'elle bloque. Les deux
        tests se tiennent.
        """
        definition = self.Definition._get_for_code(EVALUATION_CODE)
        transition = self._transition(definition, 'evaluation_submit')
        codes = {rule.code for rule in transition.sudo().condition_ids}
        self.assertIn('evaluation_after_final_validation', codes)
        self.assertIn('evaluation_complete', codes)

    # Règle 8

    def test_a_validated_evaluation_feeds_the_profile(self):
        """Règle 8, et la boucle d'apprentissage du §2.

        `opex.expert.rating` a été créé vide à l'Extension 3 en annonçant que
        celle-ci le remplirait. Rien n'a été ajouté à ce modèle ni au calcul de
        `reputation_score` : la note remonte parce que la ligne existe.
        """
        profile = self._expert_profile()
        self.assertEqual(profile.reputation_score, 0.0)

        mission = self._closed_mission()
        client = self._fill(self._evaluation(mission, 'client'), score=4)
        self._validate(client)

        client.invalidate_recordset()
        profile.invalidate_recordset()

        self.assertTrue(client.rating_id)
        self.assertEqual(client.rating_id.profile_id, profile)
        self.assertEqual(client.rating_id.source, 'client')
        self.assertEqual(client.rating_id.mission_id, mission)
        self.assertEqual(profile.reputation_score, 4.0)
        self.assertEqual(profile.rating_count, 1)

    def test_the_two_grids_both_count_in_the_reputation(self):
        """Les deux évaluations sont indépendantes et se cumulent."""
        profile = self._expert_profile()
        mission = self._closed_mission()

        self._validate(self._fill(self._evaluation(mission, 'client'), score=5))
        self._validate(
            self._fill(self._evaluation(mission, 'cluster'), score=3),
            user=self.manager)

        profile.invalidate_recordset()
        self.assertEqual(profile.rating_count, 2)
        self.assertEqual(profile.reputation_score, 4.0)

    def test_a_returned_evaluation_produces_one_note_and_only_at_the_end(self):
        """L'aller-retour du §30 ne laisse qu'une note, portée au bon moment.

        Ce test a d'abord été écrit comme un test d'idempotence, et une
        régression volontaire a montré qu'il n'en était pas un : en retirant
        la garde de `_trigger_reputation()`, il restait vert. La raison est
        dans le graphe - `validated` est finale, l'instance se clôt en
        l'atteignant, et la transition de validation ne peut pas être franchie
        deux fois. Le chemin qu'il déroule ne repassait donc jamais par elle.

        Il mesure désormais ce qu'il déroule vraiment : le renvoi pour
        complément ne porte aucune note au profil, et la validation qui suit
        n'en porte qu'une. L'idempotence, elle, a son propre test.
        """
        profile = self._expert_profile()
        mission = self._closed_mission()
        client = self._fill(self._evaluation(mission, 'client'), score=4)

        self._do(client, 'evaluation_submit', self.client_user)
        self._do(client, 'evaluation_return', self.manager,
                 comment="Merci de préciser le commentaire.")

        profile.invalidate_recordset()
        self.assertEqual(
            profile.rating_count, 0,
            "Une évaluation renvoyée à son auteur a déjà noté le profil.")

        self._do(client, 'evaluation_resume', self.client_user)
        self._do(client, 'evaluation_submit', self.client_user)
        self._do(client, 'evaluation_validate', self.manager)

        profile.invalidate_recordset()
        self.assertEqual(profile.rating_count, 1)

    def test_the_note_is_carried_to_the_profile_only_once(self):
        """L'idempotence du report, éprouvée là où elle joue vraiment.

        Le workflow ne peut pas valider deux fois - `validated` est finale.
        La garde protège donc d'autre chose : une action rejouée à la main, un
        script de reprise, une transition ajoutée un jour vers cette étape. On
        l'appelle directement, parce que c'est le seul chemin qui existe.

        Sans elle, rien ne casserait : la moyenne se déplacerait, et personne
        ne saurait pourquoi.
        """
        profile = self._expert_profile()
        mission = self._closed_mission()
        client = self._validate(
            self._fill(self._evaluation(mission, 'client'), score=4))

        rating = client.rating_id
        self.assertTrue(rating)

        client.sudo()._trigger_reputation()
        client.sudo()._trigger_reputation()

        profile.invalidate_recordset()
        self.assertEqual(
            profile.rating_count, 1,
            "Le report a créé une note par appel : la réputation dérive à "
            "chaque rejeu.")
        self.assertEqual(client.rating_id, rating)

    def test_a_pending_evaluation_does_not_feed_the_profile(self):
        """Règle 8 : c'est l'évaluation *validée* qui alimente le profil."""
        profile = self._expert_profile()
        mission = self._closed_mission()
        client = self._fill(self._evaluation(mission, 'client'), score=5)
        self._do(client, 'evaluation_submit', self.client_user)

        profile.invalidate_recordset()
        self.assertEqual(profile.rating_count, 0)
        self.assertEqual(profile.reputation_score, 0.0)

    # §32

    def test_the_reputation_summary_has_the_five_indicators(self):
        """Le tableau du §32, dans son ordre."""
        profile = self._expert_profile()
        mission = self._closed_mission()
        self._validate(self._fill(self._evaluation(mission, 'client'), score=5))

        profile.invalidate_recordset()
        summary = profile.reputation_summary()
        self.assertEqual(
            list(summary),
            ['note', 'missions_realisees', 'missions_terminees',
             'satisfaction', 'respect_delais', 'evaluations'])
        self.assertEqual(summary['note'], 5.0)
        self.assertEqual(summary['missions_realisees'], 1)
        self.assertEqual(summary['missions_terminees'], 1)
        self.assertEqual(summary['satisfaction'], 100)
        self.assertEqual(summary['respect_delais'], 100)

    def test_the_satisfaction_rate_follows_the_example_of_the_document(self):
        """Le §32 affiche 4,7 sur 5 et 94 % : c'est la note ramenée sur cent."""
        profile = self._expert_profile()
        self.env['opex.expert.rating'].sudo().create({
            'profile_id': profile.id,
            'source': 'client',
            'note': 4.7,
        })
        profile.invalidate_recordset()
        self.assertEqual(profile.reputation_score, 4.7)
        self.assertEqual(profile.satisfaction_rate, 94)

    def test_only_the_missions_really_performed_are_counted(self):
        """« Un historique de réputation basé sur les missions réellement
        réalisées. »

        Une candidature retenue puis une mission annulée avant démarrage ne
        compte pas : elle n'a rien produit dont l'intervenant puisse se
        prévaloir.
        """
        profile = self._expert_profile()

        cancelled = self._new_mission()
        self._open_the_call(cancelled)
        self._select_the_application(self._new_application(cancelled))
        self._do(cancelled, 'mission_close_applications', self.manager)
        self._do(cancelled, 'mission_award', self.decideur,
                 comment="Retenue.")
        self._do(cancelled, 'mission_cancel_awarded', self.manager,
                 comment="Le client se retire.")

        profile.invalidate_recordset()
        self.assertEqual(profile.mission_realisee_count, 0)

        # Assertion positive : une mission réellement menée, elle, compte.
        self._closed_mission()
        profile.invalidate_recordset()
        self.assertEqual(profile.mission_realisee_count, 1)
        self.assertEqual(profile.mission_terminee_count, 1)

    def test_the_delay_compliance_reads_the_delay_criterion(self):
        """Le pourcentage du §32 vient de la note portée sur les délais.

        Le seuil est nommé dans le module (`DELAY_COMPLIANCE_THRESHOLD`) : une
        note de 4 ou 5 vaut délai tenu. Ce test le cite pour que le changer
        oblige à revenir ici.
        """
        profile = self._expert_profile()
        mission = self._closed_mission()

        self._validate(self._fill(
            self._evaluation(mission, 'client'), score=5, note_delais=2))
        profile.invalidate_recordset()
        self.assertEqual(profile.delay_compliance_rate, 0)

        self._validate(
            self._fill(self._evaluation(mission, 'cluster'), score=4),
            user=self.manager)
        profile.invalidate_recordset()
        self.assertEqual(profile.delay_compliance_rate, 50)

    def test_the_reputation_reaches_the_partner_for_the_matching(self):
        """Le moteur compare toujours un champ de `res.partner`.

        `expert_reputation` y était depuis l'Extension 3 et valait zéro faute
        d'évaluations. Il porte enfin une valeur, et les trois volumes du §32
        le rejoignent.
        """
        profile = self._expert_profile()
        mission = self._closed_mission()
        self._validate(self._fill(self._evaluation(mission, 'client'), score=4))

        partner = self.intervenant.partner_id
        partner.invalidate_recordset()
        self.assertEqual(partner.sudo().expert_reputation, 4.0)
        self.assertEqual(partner.sudo().expert_missions_terminees, 1)
        self.assertEqual(partner.sudo().expert_satisfaction, 80)

    # §33

    def test_the_public_history_hides_the_client_and_the_amounts(self):
        """§33 : le filtre est dans le dictionnaire, pas dans le gabarit.

        Les clés réservées sont absentes de la version publique, pas mises à
        False : un gabarit qui les afficherait lèverait au premier rendu, ce
        qui vaut mieux qu'une fuite silencieuse.
        """
        profile = self._expert_profile()
        self._closed_mission()
        profile.invalidate_recordset()

        public = profile.mission_history(public=True)
        self.assertEqual(len(public), 1)
        entry = public[0]

        # Assertion positive d'abord : l'entrée existe et dit quelque chose.
        self.assertEqual(entry['issue'], "Terminée")
        self.assertTrue(entry['type'])

        for reserved in ('client', 'montant', 'reference', 'titre', 'notes'):
            self.assertNotIn(
                reserved, entry,
                "« %s » sort dans l'historique public." % reserved)

    def test_the_private_history_carries_what_the_staff_needs(self):
        profile = self._expert_profile()
        mission = self._closed_mission()
        profile.invalidate_recordset()

        entry = profile.mission_history(public=False)[0]
        self.assertEqual(entry['reference'], mission.name)
        self.assertEqual(entry['client'], self.client_user.partner_id.display_name)
        self.assertTrue(entry['montant'] > 0)

    def test_the_public_reputation_never_exposes_the_comments(self):
        """La case « visible publiquement » n'ouvre que la note.

        Un commentaire d'évaluation est un jugement nominatif. Le §33 autorise
        à publier des informations, pas à publier celle-là.
        """
        profile = self._expert_profile()
        mission = self._closed_mission()
        client = self._fill(
            self._evaluation(mission, 'client'), score=5,
            commentaire="Excellent, mais souvent injoignable le vendredi.")
        self._validate(client)
        client.sudo().is_public = True

        profile.invalidate_recordset()
        public = profile.public_reputation()

        self.assertEqual(public['note'], 5.0)
        self.assertEqual(public['evaluations_publiques'], 1)
        rendered = str(public)
        self.assertNotIn("injoignable", rendered)

    # §40

    def test_the_evaluation_milestone_completes_the_progress_bar(self):
        """Le dernier jalon du §40 trouve son objet.

        Ce test remplace `test_the_last_milestone_waits_for_extension_10`, qui
        affirmait le contraire et a rougi comme prévu.
        """
        mission = self._closed_mission()

        bar = {step['code']: step['etat'] for step in
               mission.sudo().mission_progress_bar()}
        self.assertEqual(bar['evaluation'], 'a_venir')

        for evaluation in mission.sudo().evaluation_ids:
            self._fill(evaluation, score=4)
            self._validate(
                evaluation,
                user=self.client_user if evaluation.evaluateur == 'client'
                else self.manager)

        mission.invalidate_recordset()
        # L'étape de la mission n'a pas bougé, et pourtant le jalon est fait.
        self.assertEqual(self._stage(mission), 'closed')
        bar = {step['code']: step['etat'] for step in
               mission.sudo().mission_progress_bar()}
        self.assertEqual(bar['evaluation'], 'fait')

    # Étanchéité

    def test_the_expert_cannot_read_an_evaluation_before_it_is_validated(self):
        """La délibération n'est pas publique, la décision l'est.

        On lit un champ et on attend une AccessError : `exists()` n'applique
        aucune ir.rule.
        """
        mission = self._closed_mission()
        cluster = self._fill(self._evaluation(mission, 'cluster'), score=2)

        with self.assertRaises(AccessError):
            cluster.with_user(self.intervenant).note_globale

        self._validate(cluster, user=self.manager)
        # Assertion positive : une fois validée, elle lui est lisible.
        self.assertEqual(
            cluster.with_user(self.intervenant).note_globale, 2.0)

    def test_the_client_does_not_read_the_cluster_grid(self):
        """§31 juge aussi le respect des procédures internes."""
        mission = self._closed_mission()
        cluster = self._validate(
            self._fill(self._evaluation(mission, 'cluster'), score=4),
            user=self.manager)

        with self.assertRaises(AccessError):
            cluster.with_user(self.client_user).note_procedures

    def test_the_client_cannot_rewrite_a_submitted_evaluation(self):
        """La note examinée doit être celle qui a été lue."""
        mission = self._closed_mission()
        client = self._fill(self._evaluation(mission, 'client'), score=4)
        self._do(client, 'evaluation_submit', self.client_user)

        with self.assertRaises(AccessError):
            client.with_user(self.client_user).write({'note_qualite': 5})
