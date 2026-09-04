import base64

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged

#: Ordre exact du parcours nominal, du dépôt à la clôture.
NOMINAL_PATH = [
    ('submit', 'porteur', 'submitted'),
    ('take_in_charge', 'secretariat', 'under_review'),
    ('qualify', 'secretariat', 'qualified'),
    ('evaluate_with_experts', 'comite', 'evaluation'),
    ('accept', 'comite', 'accepted'),
    ('start_matching', 'ceo', 'matching'),
    ('start_accompagnement', 'ceo', 'accompagnement'),
    ('start_financement', 'ceo', 'financement'),
    ('start_industrialisation', 'ceo', 'industrialisation'),
    ('close', 'ceo', 'closed'),
]


@tagged('post_install', '-at_install')
class TestInnovationProject(TransactionCase):
    """Extension 10 — le workflow projet, quinze étapes, décrit en données."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.innovation.project']
        cls.Document = cls.env['opex.innovation.document']
        cls.Definition = cls.env['opex.workflow.definition']

        cls.porteur = new_test_user(
            cls.env, login='proj_porteur', groups='base.group_portal')
        cls.porteur.partner_id.sudo().write({'is_member': True})
        cls.secretariat = new_test_user(
            cls.env, login='proj_secr',
            groups='base.group_user,opex_membership.group_secretariat')
        cls.comite = new_test_user(
            cls.env, login='proj_comite',
            groups='base.group_user,opex_innovation.group_comite_evaluation')
        cls.ceo = new_test_user(
            cls.env, login='proj_ceo',
            groups='base.group_user,opex_innovation.group_innovation_manager')

        cls.actors = {
            'porteur': cls.porteur,
            'secretariat': cls.secretariat,
            'comite': cls.comite,
            'ceo': cls.ceo,
        }

    # ------------------------------------------------------------
    # Les deux règles qui définissent le travail
    # ------------------------------------------------------------

    def test_the_project_has_no_state_field(self):
        """LA règle. Un `state` ici et la démonstration s'effondre."""
        self.assertNotIn('state', self.Project._fields)
        self.assertIn('workflow_stage_id', self.Project._fields)
        self.assertIn('workflow_instance_id', self.Project._fields)

    def test_the_project_does_not_inherit_project_project(self):
        """`project.project` apporterait son propre `stage_id`, en collision
        frontale avec nos étapes."""
        self.assertNotIn('project.project', self.Project._inherit)
        # Le lien existe, mais c'est un champ optionnel.
        self.assertIn('project_id', self.Project._fields)
        self.assertEqual(
            self.Project._fields['project_id'].comodel_name, 'project.project')

    # ------------------------------------------------------------
    # La définition configurée
    # ------------------------------------------------------------

    def test_fifteen_stages_are_configured(self):
        definition = self.Definition._get_for_code('innovation_project')
        self.assertEqual(definition.state, 'published')
        self.assertEqual(len(definition.stage_ids), 15)
        self.assertTrue(definition._check_graph())

    def test_every_stage_has_a_user_label(self):
        """Section 35 : le porteur ne lit jamais un code technique."""
        definition = self.Definition._get_for_code('innovation_project')
        without = definition.stage_ids.filtered(lambda s: not s.user_label)
        self.assertFalse(
            without, "Étapes sans libellé utilisateur : %s"
            % ", ".join(without.mapped('code')))

    def test_two_end_stages(self):
        """Une clôture réussie et un refus sont deux fins."""
        definition = self.Definition._get_for_code('innovation_project')
        ends = definition.stage_ids.filtered('is_end')
        self.assertEqual(set(ends.mapped('code')), {'closed', 'rejected'})

    # --- Les trois points à ne pas simplifier ---

    def test_administrative_control_has_two_exits_and_a_return(self):
        definition = self.Definition._get_for_code('innovation_project')
        review = definition.stage_ids.filtered(lambda s: s.code == 'under_review')
        outgoing = definition.transition_ids.filtered(
            lambda t: t.source_stage_id == review)
        self.assertEqual(
            set(outgoing.mapped('target_stage_id.code')),
            {'qualified', 'complement_requested'})

        # …et le retour vers le contrôle.
        back = definition.transition_ids.filtered(
            lambda t: t.source_stage_id.code == 'complement_requested')
        self.assertEqual(back.target_stage_id.code, 'under_review')

    def test_committee_decision_has_three_exits(self):
        """Les **trois décisions** de la section 17 : accepté, ajourné, refusé.

        L'Extension 14 a ajouté deux transitions supplémentaires depuis la même
        étape — « demander des informations complémentaires » et « demander une
        nouvelle évaluation ». Ce ne sont pas des décisions : le dossier reste
        en cours. On vérifie donc les trois décisions par leur code, et non le
        nombre total de sorties, qui a vocation à grandir.
        """
        definition = self.Definition._get_for_code('innovation_project')
        outgoing = definition.transition_ids.filtered(
            lambda t: t.source_stage_id.code == 'evaluation')

        decisions = outgoing.filtered(
            lambda t: t.code in ('accept', 'adjourn', 'reject'))
        self.assertEqual(len(decisions), 3)
        self.assertEqual(
            set(decisions.mapped('target_stage_id.code')),
            {'accepted', 'remediation', 'rejected'})

        # Toutes les sorties du comité exigent un motif écrit : une décision
        # sans justification laisse le porteur sans rien à corriger.
        self.assertTrue(all(outgoing.mapped('requires_comment')))

    def test_the_remediation_loop_exists(self):
        """remediation → resubmitted → evaluation.

        C'est elle qui prouve qu'on gère un graphe et non une séquence.
        """
        definition = self.Definition._get_for_code('innovation_project')
        step_one = definition.transition_ids.filtered(
            lambda t: t.source_stage_id.code == 'remediation')
        self.assertEqual(step_one.target_stage_id.code, 'resubmitted')
        step_two = definition.transition_ids.filtered(
            lambda t: t.source_stage_id.code == 'resubmitted')
        self.assertEqual(step_two.target_stage_id.code, 'evaluation')

    def test_qualified_has_the_two_evaluation_scenarios(self):
        """Schéma 6 : avec évaluateurs, ou évaluation directe par le comité.

        Deux transitions, pas une seule avec un `if` dedans.
        """
        definition = self.Definition._get_for_code('innovation_project')
        outgoing = definition.transition_ids.filtered(
            lambda t: t.source_stage_id.code == 'qualified')
        self.assertEqual(len(outgoing), 2)
        self.assertEqual(set(outgoing.mapped('target_stage_id.code')), {'evaluation'})

    # ------------------------------------------------------------
    # Le projet
    # ------------------------------------------------------------

    def _project(self, **values):
        base = {
            'partner_id': self.porteur.partner_id.id,
            'name': "Smart Factory",
            'resume': "Une usine pilotée par l'IA.",
            'probleme': "Les lignes de production s'arrêtent sans prévenir.",
            'solution': "Maintenance prédictive par capteurs.",
            'secteur': 'industrie',
            'maturite': 'mvp',
        }
        base.update(values)
        return self.Project.create(base)

    def _do(self, project, code, actor, comment="Décision motivée."):
        transition = project.workflow_definition_id.transition_ids.filtered(
            lambda t: t.code == code)
        self.assertTrue(transition, "Transition « %s » introuvable" % code)
        return project.with_user(self.actors[actor]).workflow_do_transition(
            transition, comment=comment)

    def _evaluation(self, project, total, state='submitted', evaluator=None):
        """Crée un avis dont le total vaut `total`, via la vraie grille.

        Depuis l'Extension 13, `score_total` est **calculé** depuis les six
        critères et `evaluator_id` est requis : on ne peut plus écrire une note
        directement. Le barème est réparti sur les critères à 20 points, ce qui
        suffit à atteindre n'importe quel total jusqu'à 80.
        """
        criteria = {}
        remaining = total
        for name in ('score_innovation', 'score_pertinence',
                     'score_faisabilite', 'score_marche'):
            criteria[name] = min(20, remaining)
            remaining -= criteria[name]
        for name in ('score_equipe', 'score_impact'):
            criteria[name] = min(10, remaining)
            remaining -= criteria[name]
        self.assertEqual(remaining, 0, "Total %s hors barème" % total)

        values = {
            'project_id': project.id,
            'evaluator_id': (evaluator or self.comite).partner_id.id,
            'state': state,
        }
        values.update(criteria)
        return self.env['opex.innovation.evaluation'].sudo().create(values)

    def _stage(self, project):
        return project.workflow_stage_id.code

    def test_creating_a_project_starts_the_workflow(self):
        project = self._project()
        self.assertTrue(project.workflow_instance_id)
        self.assertEqual(self._stage(project), 'draft')
        self.assertEqual(project.workflow_stage_label, "Compléter mon projet")

    def test_holder_information_comes_from_the_profile(self):
        """« Le porteur ne doit pas ressaisir inutilement. »"""
        partner = self.porteur.partner_id
        partner.sudo().write({
            'email': "porteur@exemple.dz",
            'wilaya': "Alger",
            'secteur_activite': "industrie",
        })
        project = self._project()
        self.assertEqual(project.email, "porteur@exemple.dz")
        self.assertEqual(project.wilaya, "Alger")
        self.assertEqual(project.secteur_porteur, "industrie")

    def test_submission_is_blocked_while_the_file_is_incomplete(self):
        project = self._project(resume=False)
        with self.assertRaises(UserError) as error:
            self._do(project, 'submit', 'porteur')
        self.assertIn("résumé", str(error.exception).lower())

    # ------------------------------------------------------------
    # LE TEST DE FIN D'EXTENSION
    # ------------------------------------------------------------

    def test_full_path_from_draft_to_closed_through_remediation(self):
        """Le parcours complet, en passant **une fois** par la remédiation.

        « Si ça marche ici, tout le reste n'est que de l'interface. »

        Chaque transition est franchie par l'acteur qui porte réellement le
        rôle : le porteur ne qualifie pas, le secrétariat ne décide pas, le
        comité ne clôture pas.
        """
        project = self._project()

        # Dépôt et contrôle administratif.
        self._do(project, 'submit', 'porteur')
        self.assertEqual(self._stage(project), 'submitted')
        self._do(project, 'take_in_charge', 'secretariat')
        self.assertEqual(self._stage(project), 'under_review')

        # Première boucle : le dossier repart au porteur, puis revient.
        self._do(project, 'request_complement', 'secretariat',
                 comment="Merci de joindre le business plan.")
        self.assertEqual(self._stage(project), 'complement_requested')
        self.assertEqual(project.workflow_stage_label,
                         "Action requise sur votre projet")
        self._do(project, 'resubmit_after_complement', 'porteur')
        self.assertEqual(self._stage(project), 'under_review')

        # Qualification puis évaluation.
        self._do(project, 'qualify', 'secretariat')
        self.assertEqual(self._stage(project), 'qualified')
        self._do(project, 'evaluate_with_experts', 'comite')
        self.assertEqual(self._stage(project), 'evaluation')

        # Seconde boucle : ajournement, remédiation, nouvelle évaluation.
        self._do(project, 'adjourn', 'comite',
                 comment="Le modèle économique doit être détaillé.")
        self.assertEqual(self._stage(project), 'remediation')
        self._do(project, 'resubmit_after_remediation', 'porteur')
        self.assertEqual(self._stage(project), 'resubmitted')
        self._do(project, 'reevaluate', 'comite')
        self.assertEqual(self._stage(project), 'evaluation')

        # Décision favorable, puis la suite du parcours.
        self._do(project, 'accept', 'comite', comment="Projet convaincant.")
        self.assertEqual(self._stage(project), 'accepted')
        for code, actor, expected in NOMINAL_PATH[5:]:
            self._do(project, code, actor)
            self.assertEqual(self._stage(project), expected)

        self.assertEqual(self._stage(project), 'closed')
        self.assertEqual(project.workflow_state, 'done')
        self.assertTrue(project.workflow_instance_id.date_end)

        # L'audit porte le parcours entier, boucles comprises.
        history = project.workflow_instance_id.history_ids
        self.assertGreaterEqual(len(history), 16)
        # Pas de `mapped('to_stage_id.code')` : `to_stage_id` est un Many2one,
        # l'intermédiaire est donc un **recordset**, qui déduplique. Le passage
        # deux fois par la même étape y devient invisible — exactement ce que
        # ce test cherche à constater.
        visited = [entry.to_stage_id.code for entry in history]
        self.assertEqual(visited.count('under_review'), 2)
        self.assertEqual(visited.count('evaluation'), 2)

    def test_the_rejection_path_closes_the_project(self):
        project = self._project()
        self._do(project, 'submit', 'porteur')
        self._do(project, 'take_in_charge', 'secretariat')
        self._do(project, 'qualify', 'secretariat')
        self._do(project, 'evaluate_directly', 'comite')
        self._do(project, 'reject', 'comite', comment="Hors périmètre du cluster.")

        self.assertEqual(self._stage(project), 'rejected')
        self.assertEqual(project.workflow_state, 'done')

    def test_roles_are_enforced_along_the_path(self):
        """Le porteur ne qualifie pas son propre dossier."""
        project = self._project()
        self._do(project, 'submit', 'porteur')
        self._do(project, 'take_in_charge', 'secretariat')

        qualify = project.workflow_definition_id.transition_ids.filtered(
            lambda t: t.code == 'qualify')
        self.assertFalse(
            project.workflow_instance_id._check_transition_allowed(
                qualify, user=self.porteur))

    # ------------------------------------------------------------
    # score et ceo_approval — les noms convenus
    # ------------------------------------------------------------

    def test_score_is_the_average_of_submitted_evaluations(self):
        project = self._project()
        self._evaluation(project, 80, evaluator=self.comite)
        self._evaluation(project, 60, evaluator=self.secretariat)
        project.invalidate_recordset()
        self.assertEqual(project.score, 70)

    def test_unsubmitted_evaluations_do_not_lower_the_score(self):
        """Un avis à moitié rempli ne doit pas bloquer une transition."""
        project = self._project()
        self._evaluation(project, 80, evaluator=self.comite)
        self._evaluation(project, 0, state='in_progress',
                         evaluator=self.secretariat)
        project.invalidate_recordset()
        self.assertEqual(project.score, 80)

    def test_the_acceptance_test_conditions_are_expressible(self):
        """Les trois conditions du test Demo Day, telles quelles.

        Elles ne sont attachées à aucune transition pour l'instant : c'est
        précisément le geste que le test d'acceptation demandera de faire
        depuis l'interface.
        """
        project = self._project()
        instance = project.workflow_instance_id

        project.ceo_approval = True
        self._evaluation(project, 75, evaluator=self.comite)
        project.invalidate_recordset()
        self.Document.create({
            'project_id': project.id, 'name': "Pitch.pdf",
            'document_type': 'pitch_deck', 'filename': "Pitch.pdf",
            'file': base64.b64encode(b'PITCH'),
        })

        self.assertTrue(instance._evaluate_flag("record.ceo_approval == True"))
        self.assertTrue(instance._evaluate_flag("has_document('pitch_deck')"))
        self.assertTrue(instance._evaluate_flag("field('score') >= 70"))

    # ------------------------------------------------------------
    # Les quatre contrôles de la section 9
    # ------------------------------------------------------------

    def _document(self, project, **values):
        base = {
            'project_id': project.id,
            'name': "Business plan",
            'document_type': 'business_plan',
            'filename': "bp.pdf",
            'file': base64.b64encode(b'CONTENU'),
        }
        base.update(values)
        return self.Document.create(base)

    def test_document_without_file_or_link_is_refused(self):
        project = self._project()
        with self.assertRaises(UserError) as error:
            self._document(project, file=False, filename=False)
        self.assertIn("ni fichier ni lien", str(error.exception))

    def test_empty_file_is_refused(self):
        project = self._project()
        with self.assertRaises(UserError) as error:
            self._document(project, file=base64.b64encode(b''))
        self.assertIn("vide", str(error.exception))

    def test_wrong_extension_is_refused_with_the_accepted_ones(self):
        project = self._project()
        with self.assertRaises(UserError) as error:
            self._document(project, filename="bp.exe")
        message = str(error.exception)
        self.assertIn(".exe", message)
        self.assertIn(".pdf", message)

    def test_oversized_file_is_refused(self):
        project = self._project()
        oversized = base64.b64encode(b'x' * (self.Document.MAX_SIZE_BYTES + 1))
        with self.assertRaises(UserError) as error:
            self._document(project, file=oversized)
        self.assertIn("limite", str(error.exception))

    def test_duplicate_document_is_refused(self):
        project = self._project()
        self._document(project)
        with self.assertRaises(UserError) as error:
            self._document(project, name="Business plan bis")
        self.assertIn("existe déjà", str(error.exception))

    def test_a_new_version_is_not_a_duplicate(self):
        project = self._project()
        self._document(project)
        self.assertTrue(self._document(project, version=2))

    def test_a_link_only_document_is_accepted_for_video(self):
        project = self._project()
        self.assertTrue(self._document(
            project, document_type='video', name="Démo",
            file=False, filename=False, url="https://exemple.dz/demo"))

    # ------------------------------------------------------------
    # Sécurité portail
    # ------------------------------------------------------------

    def test_a_portal_user_cannot_deposit_for_someone_else(self):
        other = new_test_user(
            self.env, login='proj_other', groups='base.group_portal')
        project = self.Project.with_user(self.porteur).create({
            'partner_id': other.partner_id.id,
            'name': "Tentative",
        })
        self.assertEqual(project.partner_id, self.porteur.partner_id)

    def test_a_portal_user_does_not_see_the_projects_of_others(self):
        self._project()
        other = new_test_user(
            self.env, login='proj_nosy', groups='base.group_portal')
        self.assertFalse(self.Project.with_user(other).search([]))

    def test_a_portal_user_cannot_edit_a_submitted_project(self):
        project = self._project()
        self._do(project, 'submit', 'porteur')
        self.env.invalidate_all()
        with self.assertRaises(AccessError):
            project.with_user(self.porteur).write({'name': "Renommé après coup"})

    def test_the_holder_can_edit_during_remediation(self):
        """La remédiation attend justement des corrections du porteur."""
        project = self._project()
        self._do(project, 'submit', 'porteur')
        self._do(project, 'take_in_charge', 'secretariat')
        self._do(project, 'qualify', 'secretariat')
        self._do(project, 'evaluate_directly', 'comite')
        self._do(project, 'adjourn', 'comite', comment="À revoir.")

        self.env.invalidate_all()
        project.with_user(self.porteur).write({'resume': "Version améliorée."})
        self.assertEqual(project.resume, "Version améliorée.")

    # ------------------------------------------------------------
    # Restitution
    # ------------------------------------------------------------

    def test_progress_is_readable_without_technical_codes(self):
        project = self._project()
        self._do(project, 'submit', 'porteur')
        steps = project.workflow_instance_id.progress_steps()
        labels = [step['label'] for step in steps]
        self.assertIn("Compléter mon projet", labels)
        self.assertIn("Projet déposé", labels)
        self.assertNotIn('draft', labels)
        self.assertNotIn('under_review', labels)

    def test_qualification_summary_reads_as_a_sheet(self):
        project = self._project(besoin_financement=True)
        summary = dict(project.qualification_summary())
        self.assertEqual(summary["Secteur"], "Industrie")
        self.assertEqual(summary["Maturité"], "MVP")
        self.assertEqual(summary["Besoin financement"], "Oui")
