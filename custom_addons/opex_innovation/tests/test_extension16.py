import base64
import re

from odoo.exceptions import UserError
from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged

FICHIER = base64.b64encode(b"contenu du livrable")
FICHIER_V2 = base64.b64encode(b"contenu corrige")


class Extension16Case(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.innovation.project']
        cls.Accompagnement = cls.env['opex.innovation.accompagnement']
        cls.Deliverable = cls.env['opex.innovation.deliverable']
        cls.Template = cls.env['opex.innovation.roadmap.template']

        cls.porteur = new_test_user(
            cls.env, login='e16_porteur', password='e16_porteur',
            groups='base.group_portal')
        cls.porteur.partner_id.sudo().write({'is_member': True})
        cls.secretariat = new_test_user(
            cls.env, login='e16_secr', password='e16_secr',
            groups='base.group_user,opex_membership.group_secretariat')
        cls.comite = new_test_user(
            cls.env, login='e16_comite', password='e16_comite',
            groups='base.group_user,opex_innovation.group_comite_evaluation')
        cls.ceo = new_test_user(
            cls.env, login='e16_ceo', password='e16_ceo',
            groups='base.group_user,opex_innovation.group_innovation_manager')
        cls.expert = new_test_user(
            cls.env, login='e16_expert', password='e16_expert',
            groups='base.group_portal')
        cls.expert.partner_id.sudo().is_expert = True
        cls.intrus = new_test_user(
            cls.env, login='e16_intrus', password='e16_intrus',
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
        for code, actor in (
            ('submit', 'porteur'), ('take_in_charge', 'secretariat'),
            ('qualify', 'secretariat'), ('evaluate_directly', 'comite'),
            ('accept', 'comite'), ('start_matching', 'ceo'),
            ('start_accompagnement', 'ceo'), ('start_financement', 'ceo'),
            ('start_industrialisation', 'ceo'), ('close', 'ceo'),
        ):
            self._do(project, code, actor)
            if project.workflow_stage_id.code == target:
                return project
        return project

    def _accompagnement(self):
        project = self._advance_to(self._project(), 'matching')
        return self.Accompagnement.sudo().open_for(
            project, expert=self.expert.partner_id)

    def _deliverable(self, accompagnement=None, **values):
        accompagnement = accompagnement or self._accompagnement()
        base = {
            'accompagnement_id': accompagnement.id,
            'name': "Business model",
        }
        base.update(values)
        return self.Deliverable.sudo().create(base)

    def _dtr(self, deliverable, code):
        return deliverable.workflow_definition_id.transition_ids.filtered(
            lambda t: t.code == code)


@tagged('post_install', '-at_install')
class TestAccompagnement(Extension16Case):
    """Section 21 — l'espace dédié au projet."""

    def test_it_cannot_be_opened_too_early(self):
        project = self._project()
        with self.assertRaises(UserError) as error:
            self.Accompagnement.sudo().open_for(project)
        self.assertIn("matching", str(error.exception).lower())

    def test_opening_it_twice_returns_the_same_record(self):
        project = self._advance_to(self._project(), 'matching')
        first = self.Accompagnement.sudo().open_for(project)
        second = self.Accompagnement.sudo().open_for(project)
        self.assertEqual(first, second)

    def test_it_creates_the_odoo_workspace_and_links_it_back(self):
        """Section 21 : « on crée un espace dédié au projet ».

        `project_id` sur le projet d'innovation est resté délibérément vide
        depuis l'Extension 10 : un `project.project` créé au dépôt aurait
        produit un projet vide pour chaque candidature, y compris celles qui
        n'aboutissent pas.
        """
        project = self._advance_to(self._project(), 'matching')
        self.assertFalse(project.project_id)

        accompagnement = self.Accompagnement.sudo().open_for(project)
        self.assertTrue(accompagnement.task_project_id)
        self.assertEqual(project.project_id, accompagnement.task_project_id)
        self.assertEqual(accompagnement.task_project_id.partner_id,
                         self.porteur.partner_id)


@tagged('post_install', '-at_install')
class TestRoadmap(Extension16Case):
    """Section 22 — les quatre phases, configurables."""

    def test_the_four_phases_are_a_referential_not_a_hard_coded_list(self):
        codes = set(self.Template.search([]).mapped('code'))
        for expected in ('validation', 'produit', 'marche',
                         'industrialisation'):
            self.assertIn(expected, codes)

    def test_a_new_accompaniment_gets_the_roadmap(self):
        accompagnement = self._accompagnement()
        self.assertEqual(
            [p.code for p in accompagnement.phase_ids.sorted('sequence')],
            ['validation', 'produit', 'marche', 'industrialisation'])
        self.assertTrue(
            all(p.state == 'todo' for p in accompagnement.phase_ids))

    def test_a_fifth_phase_needs_no_development(self):
        """Le périmètre l'exige explicitement : configurables, pas codées."""
        self.Template.sudo().create({
            'name': "Certification",
            'code': 'certification',
            'sequence': 35,
        })
        accompagnement = self._accompagnement()
        self.assertIn('certification', accompagnement.phase_ids.mapped('code'))

    def test_the_roadmap_is_a_copy_not_a_reference(self):
        """Modifier le référentiel ne doit pas réécrire une roadmap en cours.

        Sans cela, le porteur verrait ses phases changer de nom sous ses yeux.
        Le référentiel décide de ce qu'on propose au démarrage, pas de ce qui a
        été convenu.
        """
        accompagnement = self._accompagnement()
        phase = accompagnement.phase_ids.filtered(
            lambda p: p.code == 'validation')
        self.assertEqual(phase.name, "Validation")

        self.Template.search([('code', '=', 'validation')]).sudo().name = \
            "Validation renommée"
        phase.invalidate_recordset(['name'])
        self.assertEqual(phase.name, "Validation")

    def test_the_progression_counts_phases_and_deliverables(self):
        """Section 21 : « Progression 80 % »."""
        accompagnement = self._accompagnement()
        self.assertEqual(accompagnement.progression, 0.0)

        # 4 phases, 0 livrable : deux phases faites → 50 %.
        phases = accompagnement.phase_ids.sorted('sequence')
        phases[0].action_done()
        phases[1].action_done()
        accompagnement.invalidate_recordset(['progression'])
        self.assertAlmostEqual(accompagnement.progression, 50.0, places=1)


@tagged('post_install', '-at_install')
class TestDeliverableWorkflow(Extension16Case):
    """Sections 23 et 24 — le cycle de vie, porté par le moteur."""

    def test_the_deliverable_has_no_state_field(self):
        """La règle, sur le modèle où elle était le plus tentante.

        Un `state` à quatre valeurs aurait fait l'affaire et aurait été plus
        court à écrire. C'est précisément le cas que le périmètre demande de
        confier au moteur.
        """
        suspects = [name for name in self.Deliverable._fields
                    if name in ('state', 'etat', 'statut')]
        self.assertFalse(suspects,
                         "Champs d'état trouvés : %s" % ", ".join(suspects))
        self.assertIn('workflow_stage_id', self.Deliverable._fields)

    def test_it_is_the_fifth_engine_instance(self):
        definition = self.env['opex.workflow.definition']._get_for_code(
            'innovation_deliverable')
        self.assertEqual(definition.state, 'published')
        self.assertEqual(definition.model_name, 'opex.innovation.deliverable')
        self.assertTrue(definition._check_graph())
        self.assertEqual(len(definition.stage_ids), 4)
        self.assertEqual(len(definition.transition_ids), 4)

    def test_a_new_deliverable_starts_at_todo(self):
        deliverable = self._deliverable()
        self.assertEqual(deliverable.workflow_stage_id.code, 'todo')
        self.assertEqual(deliverable.version, 1)

    def test_depositing_without_a_file_is_refused(self):
        deliverable = self._deliverable()
        with self.assertRaises(UserError) as error:
            deliverable.with_user(self.porteur).workflow_do_transition(
                self._dtr(deliverable, 'deliverable_submit'))
        self.assertIn("fichier", str(error.exception).lower())

    def test_the_holder_deposits_and_the_expert_validates(self):
        deliverable = self._deliverable(file=FICHIER, filename="bm.pdf")
        deliverable.with_user(self.porteur).workflow_do_transition(
            self._dtr(deliverable, 'deliverable_submit'))
        self.assertEqual(deliverable.workflow_stage_id.code, 'submitted')

        deliverable.with_user(self.expert).workflow_do_transition(
            self._dtr(deliverable, 'deliverable_validate'))
        self.assertEqual(deliverable.workflow_stage_id.code, 'validated')
        self.assertEqual(deliverable.workflow_state, 'done')

    def test_the_holder_cannot_validate_his_own_deliverable(self):
        deliverable = self._deliverable(file=FICHIER, filename="bm.pdf")
        deliverable.with_user(self.porteur).workflow_do_transition(
            self._dtr(deliverable, 'deliverable_submit'))

        with self.assertRaises(UserError) as error:
            deliverable.with_user(self.porteur).workflow_do_transition(
                self._dtr(deliverable, 'deliverable_validate'))
        self.assertIn("réservée", str(error.exception).lower())

    def test_requesting_a_correction_demands_a_motive(self):
        """Section 24 croisée avec la section 18 : « demander une correction »
        sans dire laquelle renvoie au « améliorez votre projet » proscrit."""
        deliverable = self._deliverable(file=FICHIER, filename="bm.pdf")
        deliverable.with_user(self.porteur).workflow_do_transition(
            self._dtr(deliverable, 'deliverable_submit'))

        with self.assertRaises(UserError):
            deliverable.with_user(self.expert).workflow_do_transition(
                self._dtr(deliverable, 'deliverable_request_correction'),
                comment="")

    def test_a_stranger_sees_nothing_of_the_deliverable(self):
        """Être expert du cluster ne donne accès à rien : c'est la ligne
        d'acteur sur CE livrable qui ouvre la porte."""
        deliverable = self._deliverable(file=FICHIER, filename="bm.pdf")

        # Positive d'abord : l'expert désigné, lui, y accède.
        lisible = self.Deliverable.with_user(self.expert).search(
            [('id', '=', deliverable.id)])
        self.assertIn(deliverable, lisible)

        invisible = self.Deliverable.with_user(self.intrus).search(
            [('id', '=', deliverable.id)])
        self.assertFalse(invisible)


@tagged('post_install', '-at_install')
class TestDeliverableHistory(Extension16Case):
    """Section 24 — « L'historique est conservé »."""

    def _refused(self, motif="Le modèle économique n'est pas chiffré."):
        deliverable = self._deliverable(file=FICHIER, filename="bm.pdf")
        deliverable.with_user(self.porteur).workflow_do_transition(
            self._dtr(deliverable, 'deliverable_submit'))
        deliverable.with_user(self.expert).workflow_do_transition(
            self._dtr(deliverable, 'deliverable_request_correction'),
            comment=motif)
        return deliverable

    def test_a_new_version_archives_the_refused_one(self):
        deliverable = self._refused()
        self.assertEqual(deliverable.workflow_stage_id.code,
                         'correction_requested')
        self.assertFalse(deliverable.history_ids)

        deliverable.submit_new_version(
            file=FICHIER_V2, filename="bm-v2.pdf", user=self.porteur)

        self.assertEqual(deliverable.version, 2)
        self.assertEqual(deliverable.workflow_stage_id.code, 'submitted')
        self.assertEqual(len(deliverable.history_ids), 1)

        archive = deliverable.history_ids
        self.assertEqual(archive.version, 1)
        self.assertEqual(archive.filename, "bm.pdf")
        self.assertIn("pas chiffré", archive.motif_correction)

    def test_the_archive_keeps_the_old_file_not_the_new_one(self):
        """L'ordre compte : on fige **avant** d'écrire.

        Après, le champ `file` porte déjà le nouveau contenu et la version
        archivée serait un double de la version courante. L'historique
        existerait, et ne contiendrait rien d'utile.
        """
        deliverable = self._refused()
        deliverable.submit_new_version(
            file=FICHIER_V2, filename="bm-v2.pdf", user=self.porteur)

        self.assertEqual(deliverable.file, FICHIER_V2)
        self.assertEqual(deliverable.history_ids.file, FICHIER)

    def test_an_archived_version_cannot_be_rewritten(self):
        deliverable = self._refused()
        deliverable.submit_new_version(
            file=FICHIER_V2, filename="bm-v2.pdf", user=self.porteur)

        with self.assertRaises(UserError):
            deliverable.history_ids.with_user(self.ceo).write(
                {'motif_correction': "Autre chose."})

    def test_two_refusals_keep_two_distinct_motives(self):
        """Le motif est stocké **sur la version refusée**, pas sur le
        livrable — sinon le second refus écraserait le premier, c'est-à-dire
        justement ce que l'historique doit montrer.

        Les corrections sont relues en compréhension : `mapped()` sur un
        Many2one dédoublonnerait, et le second passage par
        `correction_requested` disparaîtrait.
        """
        deliverable = self._refused("Premier motif : chiffrage absent.")
        deliverable.submit_new_version(
            file=FICHIER_V2, filename="v2.pdf", user=self.porteur)
        deliverable.with_user(self.expert).workflow_do_transition(
            self._dtr(deliverable, 'deliverable_request_correction'),
            comment="Second motif : sources manquantes.")
        deliverable.submit_new_version(
            file=FICHIER, filename="v3.pdf", user=self.porteur)

        self.assertEqual(deliverable.version, 3)
        self.assertEqual(len(deliverable.history_ids), 2)

        motifs = deliverable.history_ids.sorted('version').mapped(
            'motif_correction')
        self.assertIn("chiffrage absent", motifs[0])
        self.assertIn("sources manquantes", motifs[1])

        corrections = deliverable.correction_history()
        self.assertEqual(len(corrections), 2,
                         "Les deux refus doivent apparaître, pas un seul.")

    def test_a_new_version_is_refused_outside_a_correction(self):
        deliverable = self._deliverable(file=FICHIER, filename="bm.pdf")
        with self.assertRaises(UserError) as error:
            deliverable.submit_new_version(user=self.porteur)
        self.assertIn("correction", str(error.exception).lower())


@tagged('post_install', '-at_install')
class TestSeamsClosed(Extension16Case):
    """Les trois coutures que les Extensions 17, 18 et 19 avaient laissées."""

    def test_the_three_orphan_notifications_are_now_attached(self):
        """10. 11. 12. étaient configurées et rattachées à rien depuis l'Extension 18.

        `notification_inventory()` les signalait comme orphelines. Il ne doit
        plus en rester **aucune**.
        """
        inventory = self.Project.notification_inventory()
        orphelines = {row['code'] for row in inventory if row['orpheline']}
        self.assertFalse(
            orphelines,
            "Notifications encore orphelines : %s" % ", ".join(sorted(orphelines)))

        attaches = {row['code']: row['transitions'] for row in inventory}
        self.assertIn('deliverable_submit',
                      attaches['innovation_notify_nouveau_livrable'])
        self.assertIn('deliverable_resubmit',
                      attaches['innovation_notify_nouveau_livrable'])
        self.assertIn('deliverable_validate',
                      attaches['innovation_notify_livrable_valide'])
        self.assertIn('deliverable_request_correction',
                      attaches['innovation_notify_correction_demandee'])

    def test_the_closure_counts_validated_deliverables(self):
        """Le bilan comptait les documents du projet, faute de livrables."""
        accompagnement = self._accompagnement()
        project = accompagnement.project_id

        valide = self._deliverable(accompagnement, name="Business model",
                                   file=FICHIER, filename="bm.pdf")
        valide.with_user(self.porteur).workflow_do_transition(
            self._dtr(valide, 'deliverable_submit'))
        valide.with_user(self.expert).workflow_do_transition(
            self._dtr(valide, 'deliverable_validate'))

        # Un second livrable déposé mais pas validé : il ne compte pas.
        self._deliverable(accompagnement, name="Étude marché",
                          file=FICHIER, filename="em.pdf")

        for code, actor in (('start_accompagnement', 'ceo'),
                            ('start_financement', 'ceo'),
                            ('start_industrialisation', 'ceo'),
                            ('close', 'ceo')):
            self._do(project, code, actor)

        closure = self.env['opex.innovation.closure'].sudo().generate_for(
            project)
        self.assertEqual(closure.livrable_count, 1)

    def test_the_industrialisation_points_at_real_deliverables(self):
        accompagnement = self._accompagnement()
        project = accompagnement.project_id
        deliverable = self._deliverable(accompagnement, file=FICHIER,
                                        filename="bm.pdf")

        for code, actor in (('start_accompagnement', 'ceo'),
                            ('start_financement', 'ceo')):
            self._do(project, code, actor)

        industrialisation = self.env[
            'opex.innovation.industrialisation'].sudo().open_for(project)
        self.assertIn(deliverable, industrialisation.livrable_ids)
        # Non validé : il ne compte pas encore.
        self.assertEqual(industrialisation.livrable_count, 0)


@tagged('post_install', '-at_install')
class TestDeliverablePortal(HttpCase):
    """Le porteur dépose, l'expert valide — pour de bon, en HTTP."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.innovation.project']
        cls.Accompagnement = cls.env['opex.innovation.accompagnement']
        cls.Deliverable = cls.env['opex.innovation.deliverable']

        cls.porteur = new_test_user(
            cls.env, login='e16p_porteur', password='e16p_porteur',
            groups='base.group_portal')
        cls.porteur.partner_id.sudo().write({'is_member': True})
        cls.secretariat = new_test_user(
            cls.env, login='e16p_secr', password='e16p_secr',
            groups='base.group_user,opex_membership.group_secretariat')
        cls.comite = new_test_user(
            cls.env, login='e16p_comite', password='e16p_comite',
            groups='base.group_user,opex_innovation.group_comite_evaluation')
        cls.ceo = new_test_user(
            cls.env, login='e16p_ceo', password='e16p_ceo',
            groups='base.group_user,opex_innovation.group_innovation_manager')
        cls.expert = new_test_user(
            cls.env, login='e16p_expert', password='e16p_expert',
            groups='base.group_portal')
        cls.expert.partner_id.sudo().is_expert = True
        cls.intrus = new_test_user(
            cls.env, login='e16p_intrus', password='e16p_intrus',
            groups='base.group_portal')

        cls.actors = {
            'porteur': cls.porteur, 'secretariat': cls.secretariat,
            'comite': cls.comite, 'ceo': cls.ceo,
        }

    @staticmethod
    def _flat(text):
        return re.sub(r'\s+', ' ', text or '')

    def _deliverable(self):
        project = self.Project.sudo().create({
            'partner_id': self.porteur.partner_id.id,
            'name': "Smart Factory",
            'resume': "Une usine pilotée par l'IA.",
            'probleme': "Arrêts imprévus.",
            'solution': "Maintenance prédictive.",
            'secteur': 'industrie',
            'maturite': 'mvp',
        })
        for code, actor in (('submit', 'porteur'),
                            ('take_in_charge', 'secretariat'),
                            ('qualify', 'secretariat'),
                            ('evaluate_directly', 'comite'),
                            ('accept', 'comite'), ('start_matching', 'ceo')):
            transition = project.workflow_definition_id.transition_ids.filtered(
                lambda t: t.code == code)
            project.with_user(self.actors[actor]).workflow_do_transition(
                transition, comment="Décision motivée.")
        accompagnement = self.Accompagnement.sudo().open_for(
            project, expert=self.expert.partner_id)
        return self.Deliverable.sudo().create({
            'accompagnement_id': accompagnement.id,
            'name': "Business model",
            'file': FICHIER,
            'filename': "bm.pdf",
        })

    def test_the_expert_sees_the_deliverable_and_its_two_buttons(self):
        deliverable = self._deliverable()
        deliverable.with_user(self.porteur).workflow_do_transition(
            deliverable.workflow_definition_id.transition_ids.filtered(
                lambda t: t.code == 'deliverable_submit'))

        self.authenticate('e16p_expert', 'e16p_expert')
        response = self.url_open(
            '/my/innovation/deliverable/%s' % deliverable.id)
        self.assertEqual(response.status_code, 200)
        flat = self._flat(response.text)

        # Positive d'abord : la page est bien rendue.
        self.assertIn("Business model", flat)
        self.assertIn("Nouveau livrable à vérifier", flat)
        self.assertIn("Valider", flat)
        self.assertIn("Demander une correction", flat)

    def test_a_stranger_is_turned_away_server_side(self):
        deliverable = self._deliverable()

        # Positive d'abord : le destinataire légitime accède.
        self.authenticate('e16p_porteur', 'e16p_porteur')
        response = self.url_open(
            '/my/innovation/deliverable/%s' % deliverable.id)
        self.assertIn("Business model", self._flat(response.text))

        self.authenticate('e16p_intrus', 'e16p_intrus')
        response = self.url_open(
            '/my/innovation/deliverable/%s' % deliverable.id)
        self.assertEqual(response.status_code, 200)
        raw = response.text
        self.assertNotIn("Business model", raw)
        self.assertNotIn("bm.pdf", raw)

    def test_the_holder_never_sees_the_validation_buttons(self):
        deliverable = self._deliverable()
        deliverable.with_user(self.porteur).workflow_do_transition(
            deliverable.workflow_definition_id.transition_ids.filtered(
                lambda t: t.code == 'deliverable_submit'))

        self.authenticate('e16p_porteur', 'e16p_porteur')
        response = self.url_open(
            '/my/innovation/deliverable/%s' % deliverable.id)
        raw = response.text

        # Positive d'abord : sans elle, une 500 passerait ce test au vert.
        self.assertIn("Business model", self._flat(raw))
        self.assertNotIn("Nouveau livrable à vérifier", raw)
        self.assertNotIn("deliverable_validate", raw)

    def test_the_expert_dashboard_lists_what_awaits_him(self):
        """La couture de l'Extension 19 refermée : l'encart « Extension 16 non
        réalisée » est remplacé par les vrais livrables."""
        deliverable = self._deliverable()
        deliverable.with_user(self.porteur).workflow_do_transition(
            deliverable.workflow_definition_id.transition_ids.filtered(
                lambda t: t.code == 'deliverable_submit'))

        self.authenticate('e16p_expert', 'e16p_expert')
        response = self.url_open('/my/innovation/missions')
        self.assertEqual(response.status_code, 200)
        flat = self._flat(response.text)

        self.assertIn("Mes livrables à vérifier", flat)
        self.assertIn("Business model", flat)
        self.assertNotIn("Extension 16", flat)
