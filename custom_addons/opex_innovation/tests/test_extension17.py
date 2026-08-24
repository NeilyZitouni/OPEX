import re
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged

MONTANT = 500000


class Extension17Case(TransactionCase):
    """Socle : un projet mené jusqu'où l'Extension 17 commence."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.innovation.project']
        cls.Industrialisation = cls.env['opex.innovation.industrialisation']
        cls.Closure = cls.env['opex.innovation.closure']
        cls.FinalEvaluation = cls.env['opex.innovation.final.evaluation']
        cls.Candidate = cls.env['opex.matching.candidate']

        cls.porteur = new_test_user(
            cls.env, login='e17_porteur', password='e17_porteur',
            groups='base.group_portal')
        cls.porteur.partner_id.sudo().write({'is_member': True})
        cls.secretariat = new_test_user(
            cls.env, login='e17_secr', password='e17_secr',
            groups='base.group_user,opex_membership.group_secretariat')
        cls.comite = new_test_user(
            cls.env, login='e17_comite', password='e17_comite',
            groups='base.group_user,opex_innovation.group_comite_evaluation')
        cls.ceo = new_test_user(
            cls.env, login='e17_ceo', password='e17_ceo',
            groups='base.group_user,opex_innovation.group_innovation_manager')
        cls.investisseur = new_test_user(
            cls.env, login='e17_investisseur', password='e17_investisseur',
            groups='base.group_portal')
        cls.expert = new_test_user(
            cls.env, login='e17_expert', password='e17_expert',
            groups='base.group_portal')

        cls.actors = {
            'porteur': cls.porteur, 'secretariat': cls.secretariat,
            'comite': cls.comite, 'ceo': cls.ceo,
        }

    def _project(self, **values):
        base = {
            'partner_id': self.porteur.partner_id.id,
            'name': "Smart Factory",
            'resume': "Une usine pilotée par l'IA.",
            'probleme': "Arrêts imprévus.",
            'solution': "Maintenance prédictive.",
            'secteur': 'industrie',
            'maturite': 'mvp',
            'potentiel_commercial': 'national',
            'besoin_financement': True,
            'montant_recherche': MONTANT,
        }
        base.update(values)
        return self.Project.sudo().create(base)

    def _do(self, project, code, actor, comment="Décision motivée."):
        transition = project.workflow_definition_id.transition_ids.filtered(
            lambda t: t.code == code)
        self.assertTrue(transition, "Transition « %s » introuvable." % code)
        return project.with_user(self.actors[actor]).workflow_do_transition(
            transition, comment=comment)

    def _advance_to(self, project, target):
        """Déroule le parcours nominal jusqu'à l'étape voulue."""
        path = [
            ('submit', 'porteur'), ('take_in_charge', 'secretariat'),
            ('qualify', 'secretariat'), ('evaluate_directly', 'comite'),
            ('accept', 'comite'), ('start_matching', 'ceo'),
            ('start_accompagnement', 'ceo'), ('start_financement', 'ceo'),
            ('start_industrialisation', 'ceo'), ('close', 'ceo'),
        ]
        for code, actor in path:
            self._do(project, code, actor)
            if project.workflow_stage_id.code == target:
                return project
        return project


@tagged('post_install', '-at_install')
class TestFinancement(Extension17Case):
    """Section 25 — le suivi du financement."""

    def test_the_alias_shares_the_storage_of_the_existing_field(self):
        """⚠ Le point qui aurait pu faire deux vérités.

        Le cahier des charges nomme le champ `financement_recherche` ; le
        montant recherché existe déjà sous `montant_recherche` depuis la
        section 9, et le matching financier le lit. Deux champs distincts
        auraient donné deux réponses à « de combien ce projet a-t-il besoin »,
        et le matching se serait trompé sans rien signaler.
        """
        project = self._project()
        self.assertEqual(project.financement_recherche, MONTANT)

        project.sudo().financement_recherche = 750000
        self.assertEqual(project.montant_recherche, 750000)

        project.sudo().montant_recherche = 300000
        self.assertEqual(project.financement_recherche, 300000)

    def test_the_progression_is_the_covered_share(self):
        project = self._project()
        project.sudo().financement_obtenu = 300000
        self.assertEqual(project.progression_financement, 60.0)

    def test_a_project_without_a_figure_shows_no_progression(self):
        """Sans dénominateur il n'y a pas de progression : 0 % est la seule
        réponse qui ne raconte rien de faux."""
        project = self._project(besoin_financement=False, montant_recherche=0)
        project.sudo().financement_obtenu = 100000
        self.assertEqual(project.progression_financement, 0.0)

    def test_an_overfunded_project_stays_at_one_hundred(self):
        project = self._project()
        project.sudo().financement_obtenu = MONTANT * 2
        self.assertEqual(project.progression_financement, 100.0)
        # Le dépassement reste lisible dans les montants eux-mêmes.
        self.assertEqual(project.financement_obtenu, MONTANT * 2)

    def test_the_funding_path_is_deduced_never_stored(self):
        """Le parcours du § 25 se recalcule à chaque affichage.

        Un champ `etape_financement` aurait été plus simple à lire, et faux dès
        qu'un investisseur répond sans que personne ne pense à le mettre à jour.
        """
        self.assertNotIn('etape_financement', self.Project._fields)

        project = self._project()
        steps = project.financement_steps()
        self.assertEqual(
            [s['code'] for s in steps],
            ['besoin', 'matching', 'interet', 'echange', 'finance'])

        # Le besoin est déclaré : première étape franchie, la suivante en cours.
        by_code = {s['code']: s['state'] for s in steps}
        self.assertEqual(by_code['besoin'], 'done')
        self.assertEqual(by_code['matching'], 'current')

    def test_the_path_advances_as_the_facts_appear(self):
        project = self._advance_to(self._project(), 'matching')
        instance = project.workflow_instance_id

        candidate = self.Candidate.sudo().create({
            'instance_id': instance.id,
            'partner_id': self.investisseur.partner_id.id,
            'candidate_type': 'investisseur',
            'score': 80.0,
            'detail': "Secteur compatible.",
            'state': 'accepted',
        })
        by_code = {s['code']: s['state']
                   for s in project.financement_steps()}
        self.assertEqual(by_code['matching'], 'done')
        self.assertEqual(by_code['interet'], 'current')

        candidate.action_interested()
        by_code = {s['code']: s['state']
                   for s in project.financement_steps()}
        self.assertEqual(by_code['interet'], 'done')

        project.sudo().financement_obtenu = MONTANT
        by_code = {s['code']: s['state']
                   for s in project.financement_steps()}
        self.assertEqual(by_code['finance'], 'done')


@tagged('post_install', '-at_install')
class TestIndustrialisation(Extension17Case):
    """Section 27 — l'industrialisation, pilotée par le moteur."""

    def test_the_model_has_no_state_field(self):
        """⚠ Le piège que ce modèle aurait pu tendre.

        La section 27 demande de suivre « l'état d'industrialisation ». Un
        `industrialisation_etat = fields.Selection([...])` aurait fait l'affaire
        et serait passé sous le test qui garde le projet : celui-ci cherche un
        champ nommé `state`, il n'aurait rien vu sous un autre nom.

        On vérifie donc l'absence de **tout** champ ressemblant à une machine à
        états, et la présence de celui du moteur.
        """
        suspects = [
            name for name in self.Industrialisation._fields
            if name in ('state', 'etat', 'industrialisation_etat', 'statut')
        ]
        self.assertFalse(
            suspects, "Champs d'état trouvés : %s" % ", ".join(suspects))
        self.assertIn('workflow_stage_id', self.Industrialisation._fields)

    def test_its_workflow_is_published_and_runs_on_its_own_model(self):
        """Troisième instance du moteur — et la première sur un modèle qui
        n'est pas `opex.innovation.project`."""
        definition = self.env['opex.workflow.definition']._get_for_code(
            'innovation_industrialisation')
        self.assertEqual(definition.state, 'published')
        self.assertEqual(
            definition.model_name, 'opex.innovation.industrialisation')
        self.assertTrue(definition._check_graph())

    def test_it_cannot_be_opened_too_early(self):
        project = self._advance_to(self._project(), 'accompagnement')
        with self.assertRaises(UserError) as error:
            self.Industrialisation.sudo().open_for(project)
        self.assertIn("financement", str(error.exception).lower())

    def test_opening_it_twice_returns_the_same_record(self):
        project = self._advance_to(self._project(), 'financement')
        first = self.Industrialisation.sudo().open_for(project)
        second = self.Industrialisation.sudo().open_for(project)
        self.assertEqual(first, second)

    def test_it_starts_at_the_configured_first_stage(self):
        project = self._advance_to(self._project(), 'financement')
        industrialisation = self.Industrialisation.sudo().open_for(project)
        self.assertTrue(industrialisation.workflow_instance_id)
        self.assertEqual(
            industrialisation.workflow_stage_id.code, 'preparation')
        self.assertEqual(
            industrialisation.workflow_stage_label,
            "Préparer l'industrialisation")

    def test_the_pilot_run_demands_a_partner(self):
        project = self._advance_to(self._project(), 'financement')
        industrialisation = self.Industrialisation.sudo().open_for(project)
        instance = industrialisation.workflow_instance_id

        def _transition(code):
            return industrialisation.workflow_definition_id.transition_ids\
                .filtered(lambda t: t.code == code)

        instance.with_user(self.porteur).do_transition(
            _transition('indus_chercher_partenaires'))

        with self.assertRaises(UserError) as error:
            instance.with_user(self.porteur).do_transition(
                _transition('indus_lancer_pilote'))
        self.assertIn("partenaire", str(error.exception).lower())

        industrialisation.sudo().partenaire_ids = [
            (6, 0, self.ceo.partner_id.ids)]
        instance.with_user(self.porteur).do_transition(
            _transition('indus_lancer_pilote'))
        self.assertEqual(industrialisation.workflow_stage_id.code, 'pilote')

    def test_the_deployment_demands_half_the_funding(self):
        project = self._advance_to(self._project(), 'financement')
        industrialisation = self.Industrialisation.sudo().open_for(project)
        instance = industrialisation.workflow_instance_id

        def _transition(code):
            return industrialisation.workflow_definition_id.transition_ids\
                .filtered(lambda t: t.code == code)

        industrialisation.sudo().partenaire_ids = [
            (6, 0, self.ceo.partner_id.ids)]
        instance.with_user(self.porteur).do_transition(
            _transition('indus_chercher_partenaires'))
        instance.with_user(self.porteur).do_transition(
            _transition('indus_lancer_pilote'))

        with self.assertRaises(UserError) as error:
            instance.with_user(self.ceo).do_transition(
                _transition('indus_deployer'))
        self.assertIn("moitié", str(error.exception).lower())

        project.sudo().financement_obtenu = MONTANT * 0.6
        instance.with_user(self.ceo).do_transition(
            _transition('indus_deployer'))
        self.assertEqual(industrialisation.workflow_stage_id.code,
                         'deploiement')

    def test_a_new_stage_can_be_inserted_without_touching_this_module(self):
        """Le test d'acceptation du Demo Day, rejoué sur ce processus-ci.

        Ce que ce test écrit, un utilisateur métier l'obtient au configurateur.
        Rien ici n'importe `opex_innovation` : ce sont des `create()` sur les
        modèles de configuration du moteur.
        """
        definition = self.env['opex.workflow.definition']._get_for_code(
            'innovation_industrialisation')
        pilote = definition.stage_ids.filtered(lambda s: s.code == 'pilote')
        deploiement = definition.stage_ids.filtered(
            lambda s: s.code == 'deploiement')

        certification = self.env['opex.workflow.stage'].create({
            'definition_id': definition.id,
            'code': 'certification',
            'name': "Certification",
            'user_label': "Certification en cours",
            'sequence': 35,
        })
        definition.transition_ids.filtered(
            lambda t: t.code == 'indus_deployer'
        ).write({'target_stage_id': certification.id})
        self.env['opex.workflow.transition'].create({
            'definition_id': definition.id,
            'code': 'indus_certifie',
            'name': "Certification obtenue",
            'source_stage_id': certification.id,
            'target_stage_id': deploiement.id,
            'allowed_role_ids': [
                (6, 0, self.env.ref('opex_workflow.role_ceo').ids)],
        })

        self.assertTrue(definition._check_graph())
        arcs = [(t.source_stage_id.code, t.target_stage_id.code)
                for t in definition.transition_ids]
        self.assertIn((pilote.code, 'certification'), arcs)
        self.assertIn(('certification', 'deploiement'), arcs)


@tagged('post_install', '-at_install')
class TestClosure(Extension17Case):
    """Section 28 — le bilan de clôture."""

    def _closed_project(self):
        project = self._advance_to(self._project(), 'closed')
        self.assertEqual(project.workflow_instance_id.state, 'done')
        return project

    def test_the_report_refuses_an_open_file(self):
        project = self._advance_to(self._project(), 'accompagnement')
        with self.assertRaises(UserError) as error:
            self.Closure.sudo().generate_for(project)
        self.assertIn("clôture", str(error.exception).lower())

    def test_it_refuses_to_be_generated_twice(self):
        project = self._closed_project()
        self.Closure.sudo().generate_for(project)
        with self.assertRaises(UserError) as error:
            self.Closure.sudo().generate_for(project)
        self.assertIn("déjà", str(error.exception).lower())

    def test_the_seven_lines_of_the_report(self):
        project = self._closed_project()
        project.sudo().financement_obtenu = 300000
        closure = self.Closure.sudo().generate_for(
            project, resultat_final='reussi', synthese="Objectifs atteints.")

        self.assertTrue(closure.date_depot)
        self.assertTrue(closure.date_acceptation)
        self.assertGreaterEqual(closure.duree_accompagnement_jours, 0)
        self.assertEqual(closure.financement_obtenu, 300000)
        self.assertEqual(closure.livrable_count, len(project.document_ids))
        self.assertEqual(closure.resultat_final, 'reussi')
        self.assertEqual(closure.project_name, project.name)

    def test_the_report_is_frozen(self):
        """Un bilan qui change n'est pas un bilan."""
        project = self._closed_project()
        closure = self.Closure.generate_for(project)
        with self.assertRaises(UserError):
            closure.with_user(self.ceo).write({'resultat_final': 'abandonne'})

    def test_it_does_not_follow_the_project_afterwards(self):
        """Figé veut dire figé : corriger le projet ne réécrit pas le bilan."""
        project = self._closed_project()
        project.sudo().financement_obtenu = 300000
        closure = self.Closure.sudo().generate_for(project)

        project.sudo().financement_obtenu = 999999
        self.assertEqual(closure.financement_obtenu, 300000)

    def test_the_duration_counts_every_stay_not_the_distinct_stages(self):
        """⚠ Le piège `mapped()`, sur le calcul qui en dépend le plus.

        Un projet qui repasse par l'accompagnement après une réévaluation y
        entre deux fois. `mapped('to_stage_id.code')` dédoublonnerait sur un
        Many2one : le second séjour disparaîtrait et la durée serait
        sous-évaluée sans que rien ne le signale.

        On fabrique donc l'historique d'un double séjour et on vérifie que les
        deux sont comptés.
        """
        project = self._closed_project()
        instance = project.workflow_instance_id
        History = self.env['opex.workflow.history'].sudo()
        stages = project.workflow_definition_id.stage_ids
        accompagnement = stages.filtered(lambda s: s.code == 'accompagnement')
        matching = stages.filtered(lambda s: s.code == 'matching')

        # Deux séjours de 10 jours chacun, séparés par un retour au matching.
        #
        # ⚠ La date est posée **à la création**. Le journal d'audit du moteur
        # refuse toute écriture ultérieure, administrateur compris — écrire
        # `ligne.date = ...` lève une `UserError`. C'est la garantie qui donne
        # sa valeur à l'historique, et elle vaut aussi contre les tests.
        base = fields.Datetime.now()
        sejours = [
            (100, accompagnement), (90, matching),
            (80, accompagnement), (70, matching),
        ]
        for jours, stage in sejours:
            History.create({
                'instance_id': instance.id,
                'to_stage_id': stage.id,
                'user_id': self.ceo.id,
                'date': base - timedelta(days=jours),
            })

        facts = self.Closure._read_history(instance)
        self.assertGreaterEqual(
            facts['duree_accompagnement'], 20,
            "Les deux séjours en accompagnement doivent être comptés, "
            "pas les étapes distinctes.")

        # Et la preuve que le piège est bien celui-là : dédoublonner ne verrait
        # qu'une seule entrée en accompagnement.
        codes = [line.to_stage_id.code
                 for line in instance.history_ids.sorted('id')]
        self.assertEqual(codes.count('accompagnement'), 3,
                         "Un séjour d'origine plus les deux fabriqués.")
        self.assertEqual(
            len(set(instance.history_ids.mapped('to_stage_id.code'))),
            len(set(codes)),
            "mapped() ne renvoie que les étapes distinctes — c'est le piège.")

    def test_the_experts_are_read_from_the_engine_actors(self):
        project = self._closed_project()
        instance = project.workflow_instance_id
        role = self.env.ref('opex_workflow.role_expert')
        instance.add_actor(role, self.expert, 'limited')

        closure = self.Closure.sudo().generate_for(project)
        self.assertIn(self.expert.partner_id, closure.expert_ids)


@tagged('post_install', '-at_install')
class TestFinalEvaluation(Extension17Case):
    """Section 29 — l'évaluation finale."""

    def _closed_project(self):
        return self._advance_to(self._project(), 'closed')

    def test_nobody_evaluates_before_the_file_is_closed(self):
        project = self._advance_to(self._project(), 'accompagnement')
        self.assertFalse(project.can_evaluate_finally(self.porteur))
        self.assertFalse(project.can_evaluate_finally(self.ceo))

    def test_the_two_sides_are_recognised(self):
        project = self._closed_project()
        self.assertEqual(project.can_evaluate_finally(self.porteur), 'porteur')
        self.assertEqual(project.can_evaluate_finally(self.ceo), 'cluster')
        self.assertEqual(project.can_evaluate_finally(self.comite), 'cluster')
        # Un tiers n'évalue rien.
        self.assertFalse(project.can_evaluate_finally(self.investisseur))

    def test_the_side_is_deduced_never_taken_from_the_form(self):
        """⚠ Le point de sécurité de cette section.

        `submit_final_evaluation()` reçoit un dictionnaire venu du formulaire.
        Si le côté y était lu, un porteur pourrait déposer l'avis du cluster
        sur l'accompagnement qu'il a lui-même reçu — et l'écart entre les deux
        avis, seul renseignement que la section produise, deviendrait un
        monologue.
        """
        project = self._closed_project()
        evaluation = project.submit_final_evaluation(
            notes={
                'note_pertinence': 4, 'note_mentorat': 5,
                'note_resultats': 3, 'note_delais': 4,
                # La tentative : un champ « side » glissé dans le formulaire.
                'side': 'cluster', 'author_side': 'cluster',
            },
            commentaire="Accompagnement utile.",
            user=self.porteur,
        )
        self.assertEqual(evaluation.author_side, 'porteur')
        self.assertEqual(evaluation.author_id, self.porteur.partner_id)

    def test_the_global_note_is_the_average_of_the_four(self):
        project = self._closed_project()
        evaluation = project.submit_final_evaluation(
            notes={'note_pertinence': 4, 'note_mentorat': 5,
                   'note_resultats': 3, 'note_delais': 4},
            user=self.ceo)
        self.assertEqual(evaluation.author_side, 'cluster')
        self.assertAlmostEqual(evaluation.note_globale, 4.0, places=2)

    def test_a_note_outside_the_scale_is_refused(self):
        project = self._closed_project()
        with self.assertRaises(UserError) as error:
            project.submit_final_evaluation(
                notes={'note_pertinence': 9, 'note_mentorat': 5,
                       'note_resultats': 3, 'note_delais': 4},
                user=self.ceo)
        self.assertIn("0 à 5", str(error.exception))

    def test_a_submitted_evaluation_cannot_be_reworked(self):
        project = self._closed_project()
        project.submit_final_evaluation(
            notes={'note_pertinence': 4, 'note_mentorat': 4,
                   'note_resultats': 4, 'note_delais': 4},
            user=self.porteur)
        with self.assertRaises(UserError) as error:
            project.submit_final_evaluation(
                notes={'note_pertinence': 1, 'note_mentorat': 1,
                       'note_resultats': 1, 'note_delais': 1},
                user=self.porteur)
        self.assertIn("déjà", str(error.exception).lower())

    def test_the_holder_never_reads_the_cluster_verdict(self):
        """Deux avis indépendants, ou bien un avis et un commentaire."""
        project = self._closed_project()
        project.submit_final_evaluation(
            notes={'note_pertinence': 5, 'note_mentorat': 5,
                   'note_resultats': 5, 'note_delais': 5},
            commentaire="Très satisfait.", user=self.porteur)
        project.submit_final_evaluation(
            notes={'note_pertinence': 2, 'note_mentorat': 2,
                   'note_resultats': 2, 'note_delais': 1},
            commentaire="Porteur peu réactif.", user=self.ceo)

        # Assertion positive d'abord : sans elle, une liste vide passerait le
        # test sans rien prouver.
        vu_par_porteur = project.visible_final_evaluations(self.porteur)
        self.assertEqual(len(vu_par_porteur), 1)
        self.assertEqual(vu_par_porteur.author_side, 'porteur')
        self.assertNotIn(
            'cluster', vu_par_porteur.mapped('author_side'))

        vu_par_cluster = project.visible_final_evaluations(self.ceo)
        self.assertEqual(len(vu_par_cluster), 2)

    def test_the_database_locks_it_too(self):
        """La barrière applicative n'est pas seule : l'`ir.rule` borne aussi."""
        project = self._closed_project()
        project.submit_final_evaluation(
            notes={'note_pertinence': 2, 'note_mentorat': 2,
                   'note_resultats': 2, 'note_delais': 2},
            commentaire="Réservé.", user=self.ceo)

        lisible = self.FinalEvaluation.with_user(self.porteur).search([
            ('project_id', '=', project.id)])
        self.assertFalse(
            lisible, "Le porteur ne doit pas lire l'avis du cluster en base.")


@tagged('post_install', '-at_install')
class TestInvestorSpace(HttpCase):
    """Section 26 — l'espace investisseur, vérifié côté serveur."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.innovation.project']
        cls.Candidate = cls.env['opex.matching.candidate']

        cls.porteur = new_test_user(
            cls.env, login='e17i_porteur', password='e17i_porteur',
            groups='base.group_portal')
        cls.porteur.partner_id.sudo().write({'is_member': True})
        cls.secretariat = new_test_user(
            cls.env, login='e17i_secr', password='e17i_secr',
            groups='base.group_user,opex_membership.group_secretariat')
        cls.comite = new_test_user(
            cls.env, login='e17i_comite', password='e17i_comite',
            groups='base.group_user,opex_innovation.group_comite_evaluation')
        cls.ceo = new_test_user(
            cls.env, login='e17i_ceo', password='e17i_ceo',
            groups='base.group_user,opex_innovation.group_innovation_manager')
        cls.investisseur = new_test_user(
            cls.env, login='e17i_inv', password='e17i_inv',
            groups='base.group_portal')
        cls.investisseur.partner_id.sudo().is_investor = True
        cls.autre_investisseur = new_test_user(
            cls.env, login='e17i_inv2', password='e17i_inv2',
            groups='base.group_portal')
        cls.autre_investisseur.partner_id.sudo().is_investor = True
        cls.expert = new_test_user(
            cls.env, login='e17i_expert', password='e17i_expert',
            groups='base.group_portal')
        cls.expert.partner_id.sudo().is_expert = True

        cls.actors = {
            'porteur': cls.porteur, 'secretariat': cls.secretariat,
            'comite': cls.comite, 'ceo': cls.ceo,
        }

    def _project(self):
        project = self.Project.sudo().create({
            'partner_id': self.porteur.partner_id.id,
            'name': "Smart Factory",
            'resume': "Une usine pilotée par l'IA.",
            'probleme': "Arrêts imprévus.",
            'solution': "Maintenance prédictive.",
            'marche_cible': "Agroalimentaire algérien.",
            'proposition_valeur': "Moins d'arrêts non planifiés.",
            'secteur': 'industrie',
            'maturite': 'mvp',
            'potentiel_commercial': 'national',
            'besoin_financement': True,
            'montant_recherche': MONTANT,
        })
        for code, actor in (
            ('submit', 'porteur'), ('take_in_charge', 'secretariat'),
            ('qualify', 'secretariat'), ('evaluate_directly', 'comite'),
            ('accept', 'comite'), ('start_matching', 'ceo'),
        ):
            transition = project.workflow_definition_id.transition_ids.filtered(
                lambda t: t.code == code)
            project.with_user(self.actors[actor]).workflow_do_transition(
                transition, comment="Décision motivée.")
        return project

    def _propose(self, project, user, candidate_type='investisseur'):
        candidate = self.Candidate.sudo().search([
            ('instance_id', '=', project.workflow_instance_id.id),
            ('partner_id', '=', user.partner_id.id),
            ('candidate_type', '=', candidate_type),
        ], limit=1)
        if not candidate:
            candidate = self.Candidate.sudo().create({
                'instance_id': project.workflow_instance_id.id,
                'partner_id': user.partner_id.id,
                'candidate_type': candidate_type,
                'score': 84.0,
                'detail': "Secteur et ticket compatibles.",
            })
        candidate.sudo().action_accept()
        project.sudo().propose_to_candidate(candidate)
        return candidate

    @staticmethod
    def _flat(text):
        """Le HTML rendu coupe les lignes où il veut ; les assertions non."""
        return re.sub(r'\s+', ' ', text or '')

    # ------------------------------------------------------------

    def test_the_investor_sees_the_four_authorised_informations(self):
        project = self._project()
        self._propose(project, self.investisseur)

        self.authenticate('e17i_inv', 'e17i_inv')
        response = self.url_open('/my/innovation/opportunities')
        self.assertEqual(response.status_code, 200)
        body = self._flat(response.text)

        # Positive d'abord : la page existe et parle bien du projet.
        self.assertIn("Smart Factory", body)
        # Les quatre informations de la section 26.
        self.assertIn("Secteur", body)
        self.assertIn("Maturité", body)
        self.assertIn("Potentiel", body)
        self.assertIn("Financement recherché", body)
        # Les deux boutons.
        self.assertIn("Voir le projet", body)
        self.assertIn("Manifester mon intérêt", body)

    def test_an_expert_never_receives_the_funding_target(self):
        """⚠ Section 32 : les informations financières sont **autorisées à
        l'acteur financier**, pas à tout candidat.

        `_matching_teaser()` ne met les clés financières dans le dictionnaire
        que pour un investisseur ou un sponsor. Le montant recherché n'est donc
        pas masqué en CSS sur la page d'un expert : il n'y est pas.
        """
        project = self._project()
        self._propose(project, self.expert, candidate_type='expert')

        self.authenticate('e17i_expert', 'e17i_expert')
        response = self.url_open('/my/innovation/opportunities')
        self.assertEqual(response.status_code, 200)

        raw = response.text
        body = self._flat(raw)
        # Positive d'abord : sans elle, une page 500 passerait ce test au vert.
        self.assertIn("Smart Factory", body)
        self.assertIn("Rôle proposé", body)

        self.assertNotIn("Financement recherché", body)
        self.assertNotIn("Potentiel", body)
        for forme in ("500000", "500 000", "500,000"):
            self.assertNotIn(forme, raw,
                             "Le montant fuit sous la forme « %s »." % forme)

    def test_an_investor_sees_nothing_of_a_project_not_proposed_to_them(self):
        project = self._project()
        self._propose(project, self.investisseur)

        self.authenticate('e17i_inv2', 'e17i_inv2')
        response = self.url_open('/my/innovation/opportunities')
        self.assertEqual(response.status_code, 200)

        raw = response.text
        # Positive d'abord : la page s'est bien rendue, avec son message vide.
        self.assertIn("Aucune opportunité", self._flat(raw))
        self.assertNotIn("Smart Factory", raw)

    def test_the_detail_route_refuses_a_stranger_server_side(self):
        """Le contrôle est **serveur**, avant tout rendu.

        Un gabarit qui masquerait le contenu laisserait la page se construire
        avec les données dedans : il suffirait d'en lire la source.
        """
        project = self._project()
        candidate = self._propose(project, self.investisseur)

        # Le destinataire légitime accède — assertion positive qui donne son
        # sens au refus suivant.
        self.authenticate('e17i_inv', 'e17i_inv')
        response = self.url_open(
            '/my/innovation/opportunity/%s' % candidate.id)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Smart Factory", self._flat(response.text))
        self.assertIn("Marché cible", self._flat(response.text))

        # Le second investisseur, à qui rien n'a été proposé, est renvoyé.
        self.authenticate('e17i_inv2', 'e17i_inv2')
        response = self.url_open(
            '/my/innovation/opportunity/%s' % candidate.id)
        self.assertEqual(response.status_code, 200)
        raw = response.text
        self.assertIn("Aucune opportunité", self._flat(raw))
        self.assertNotIn("Smart Factory", raw)
        self.assertNotIn("Marché cible", raw)

    def test_revoking_the_actor_closes_the_door_immediately(self):
        """⚠ Le trou que l'Extension 15 laissait ouvert.

        Le filtre ne consultait que la table des candidats : `partner_id` et
        `state = 'accepted'`. Retirer l'investisseur du dossier supprime sa
        ligne `instance.actor` mais laisse sa candidature à `accepted` — le
        dossier serait donc resté visible à quelqu'un à qui on venait de le
        fermer.

        Depuis, `_my_proposals()` interroge en second `instance._has_access()`,
        qui est la seule fonction de visibilité du moteur.
        """
        project = self._project()
        candidate = self._propose(project, self.investisseur)
        instance = project.workflow_instance_id

        # Positive d'abord : l'accès existe avant la révocation.
        self.authenticate('e17i_inv', 'e17i_inv')
        response = self.url_open('/my/innovation/opportunities')
        self.assertIn("Smart Factory", self._flat(response.text))

        role = self.env.ref('opex_workflow.role_investisseur')
        instance.sudo().remove_actor(role, self.investisseur)

        # La candidature, elle, est toujours « retenue » : c'est bien le
        # second filtre qui ferme la porte.
        self.assertEqual(candidate.state, 'accepted')

        response = self.url_open('/my/innovation/opportunities')
        self.assertEqual(response.status_code, 200)
        raw = response.text
        self.assertIn("Aucune opportunité", self._flat(raw))
        self.assertNotIn("Smart Factory", raw)

        response = self.url_open(
            '/my/innovation/opportunity/%s' % candidate.id)
        self.assertNotIn("Marché cible", response.text)

    def test_the_holder_identity_is_never_in_the_investor_page(self):
        """La section 26 liste ce que l'investisseur voit. Le porteur n'y est
        pas, et son adresse électronique encore moins."""
        project = self._project()
        self.porteur.partner_id.sudo().write({
            'email': "porteur.secret@exemple.dz"})
        candidate = self._propose(project, self.investisseur)

        self.authenticate('e17i_inv', 'e17i_inv')
        response = self.url_open(
            '/my/innovation/opportunity/%s' % candidate.id)
        self.assertEqual(response.status_code, 200)
        raw = response.text
        self.assertIn("Smart Factory", self._flat(raw))
        self.assertNotIn("porteur.secret@exemple.dz", raw)

    def test_manifesting_interest_records_the_response(self):
        project = self._project()
        candidate = self._propose(project, self.investisseur)

        self.authenticate('e17i_inv', 'e17i_inv')
        page = self.url_open('/my/innovation/opportunities')
        token = re.search(
            r'name="csrf_token"\s+value="([^"]+)"', page.text)
        self.assertTrue(token, "Jeton CSRF introuvable dans la page.")

        response = self.url_open(
            '/my/innovation/opportunities/%s/respond' % candidate.id,
            data={'response': 'interested',
                  'csrf_token': token.group(1)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(candidate.candidate_response, 'interested')
