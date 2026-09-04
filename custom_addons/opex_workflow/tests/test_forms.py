from odoo.tests.common import tagged

from .common import WorkflowCase


@tagged('post_install', '-at_install')
class TestDynamicForms(WorkflowCase):
    """Extension 6 — un formulaire décrit en données se comporte-t-il bien ?"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.definition = cls._linear_definition(code='form_wf')
        cls.draft_stage = cls.definition.stage_ids.filtered(
            lambda s: s.code == 'draft')
        cls.record = cls.env['res.partner'].create({'name': "Dossier formulaire"})
        cls.instance = cls.Instance._start_for(cls.record, 'form_wf')

        cls.Form = cls.env['opex.workflow.form']
        cls.FormField = cls.env['opex.workflow.form.field']

        cls.form = cls.Form.create({
            'name': "Informations générales",
            'code': 'infos',
            'definition_id': cls.definition.id,
            'stage_id': cls.draft_stage.id,
        })
        cls.draft_stage.form_id = cls.form.id

    @classmethod
    def _field(cls, model, name):
        return cls.env['ir.model.fields']._get(model, name)

    def _line(self, name, **values):
        base = {
            'form_id': self.form.id,
            'field_id': self._field('res.partner', name).id,
        }
        base.update(values)
        return self.FormField.create(base)

    def _rendered_html(self):
        """Le HTML réellement produit par le gabarit générique."""
        return self.env['ir.qweb']._render(
            'opex_workflow.workflow_dynamic_form_fields',
            {'fields': self.form.render_values(self.instance)},
        )

    # ------------------------------------------------------------
    # Le lien étape → formulaire, différé depuis l'Extension 1
    # ------------------------------------------------------------

    def test_stage_carries_its_form(self):
        self.assertEqual(self.draft_stage.form_id, self.form)
        self.assertEqual(self.Form.form_for_stage(self.instance), self.form)

    # ------------------------------------------------------------
    # Champ conditionnellement requis
    # ------------------------------------------------------------

    def test_conditionally_required_blocks_then_releases(self):
        """La condition vraie rend le champ obligatoire ; fausse, il passe."""
        self._line('comment', required_expression="field('is_company')")

        # Condition fausse : la validation passe même sans saisie.
        self.record.is_company = False
        self.assertFalse(self.form.required_field_lines(self.instance))
        self.assertEqual(self.form.validate(self.instance, {}), [])

        # Condition vraie : la validation refuse et nomme le champ.
        self.record.is_company = True
        required = self.form.required_field_lines(self.instance)
        self.assertEqual(len(required), 1)
        errors = self.form.validate(self.instance, {})
        self.assertEqual(len(errors), 1)
        self.assertIn("obligatoire", errors[0])

        # Renseigné, ça repasse.
        self.assertEqual(
            self.form.validate(self.instance, {'wf_comment': "Une réponse"}), [])

    def test_blank_string_does_not_satisfy_a_required_field(self):
        self._line('comment', required_expression="True")
        self.assertTrue(self.form.validate(self.instance, {'wf_comment': "   "}))

    def test_save_with_validation_refuses_and_writes_nothing(self):
        self._line('comment', required_expression="True")
        self._line('website')

        errors = self.form.save(
            self.instance, {'wf_website': "https://exemple.dz"}, partial=False)
        self.assertTrue(errors)
        # Rien n'est écrit tant que la validation échoue.
        self.assertFalse(self.record.website)

    # ------------------------------------------------------------
    # Champ conditionnellement invisible : ABSENT du HTML
    # ------------------------------------------------------------

    def test_invisible_field_is_not_rendered_at_all(self):
        """Pas rendu, et pas seulement masqué en CSS.

        C'est la propriété de sécurité de l'extension. Un champ présent dans la
        source de la page se lit avec l'inspecteur du navigateur, quel que soit
        le `display: none` qui l'accompagne. On vérifie donc le HTML produit,
        pas l'apparence.
        """
        self._line('website')  # toujours visible
        self._line('comment', visible_expression="field('is_company')")

        self.record.is_company = False
        html = str(self._rendered_html())
        self.assertIn('wf_website', html)
        self.assertNotIn('wf_comment', html)
        # Ni masquage, ni champ caché : le nom n'apparaît nulle part.
        self.assertNotIn('display:none', html.replace(' ', ''))
        self.assertNotIn('type="hidden"', html)

        self.record.is_company = True
        html = str(self._rendered_html())
        self.assertIn('wf_comment', html)

    def test_invisible_field_is_absent_from_the_server_side_list(self):
        line = self._line('comment', visible_expression="False")
        self.assertNotIn(line, self.form.visible_field_lines(self.instance))

    def test_invisible_field_is_never_required(self):
        """Exiger un champ qu'on ne montre pas enferme l'utilisateur."""
        self._line(
            'comment',
            visible_expression="False",
            required_expression="True",
        )
        self.assertFalse(self.form.required_field_lines(self.instance))
        self.assertEqual(self.form.validate(self.instance, {}), [])

    def test_forged_post_cannot_write_an_invisible_field(self):
        """Le POST ne décide pas de ce qui est écrit ; la configuration si.

        Même protection que le `create()` qui force `partner_id` : la liste des
        champs inscriptibles est recalculée côté serveur, jamais déduite des
        clés reçues.
        """
        self._line('website')
        self._line('comment', visible_expression="False")

        self.form.save(self.instance, {
            'wf_website': "https://exemple.dz",
            'wf_comment': "Injecté",
        })
        self.assertEqual(self.record.website, "https://exemple.dz")
        self.assertFalse(self.record.comment)

    def test_forged_post_cannot_write_a_field_absent_from_the_form(self):
        self._line('website')
        self.record.function = "Directeur"
        self.form.save(self.instance, {
            'wf_website': "https://exemple.dz",
            'wf_function': "Piraté",
        })
        self.assertEqual(self.record.function, "Directeur")

    def test_readonly_field_is_rendered_but_not_written(self):
        self.record.website = "https://origine.dz"
        self._line('website', readonly=True)
        html = str(self._rendered_html())
        self.assertIn('wf_website', html)
        self.assertIn('readonly', html)

        self.form.save(self.instance, {'wf_website': "https://tentative.dz"})
        self.assertEqual(self.record.website, "https://origine.dz")

    # ------------------------------------------------------------
    # Tolérance aux expressions fautives — même règle qu'en Extension 2
    # ------------------------------------------------------------

    def test_broken_visible_expression_hides_the_field(self):
        """Fail-closed : un champ affiché par erreur peut divulguer."""
        line = self._line(
            'comment', visible_expression="record.champ_inexistant.foo()")
        self.assertNotIn(line, self.form.visible_field_lines(self.instance))
        self.assertNotIn('wf_comment', str(self._rendered_html()))

    def test_broken_required_expression_leaves_the_field_optional(self):
        """Fail-open : bloquer tout le monde sur une faute de frappe serait pire."""
        self._line('comment', required_expression="1 / 0")
        self.assertFalse(self.form.required_field_lines(self.instance))
        self.assertEqual(self.form.validate(self.instance, {}), [])

    def test_a_broken_expression_never_breaks_the_page(self):
        self._line('website')
        self._line('comment', visible_expression="syntaxe ((( invalide")
        # Le rendu aboutit malgré tout.
        self.assertIn('wf_website', str(self._rendered_html()))

    # ------------------------------------------------------------
    # Brouillon automatique et conversion
    # ------------------------------------------------------------

    def test_partial_save_accepts_an_incomplete_form(self):
        """Le porteur doit pouvoir partir et revenir sans rien perdre."""
        self._line('comment', required_expression="True")
        self._line('website')

        errors = self.form.save(
            self.instance, {'wf_website': "https://exemple.dz"}, partial=True)
        self.assertEqual(errors, [])
        self.assertEqual(self.record.website, "https://exemple.dz")

    def test_partial_save_leaves_untouched_fields_alone(self):
        self.record.website = "https://origine.dz"
        self._line('website')
        self._line('comment')
        self.form.save(self.instance, {'wf_comment': "Note"})
        self.assertEqual(self.record.website, "https://origine.dz")
        self.assertEqual(self.record.comment, "<p>Note</p>")

    def test_values_are_converted_to_the_field_type(self):
        self._line('color')          # Integer
        self._line('is_company')     # Boolean
        self.form.save(self.instance, {
            'wf_color': "42",
            'wf_is_company': "on",
        })
        self.assertEqual(self.record.color, 42)
        self.assertIs(self.record.is_company, True)

    def test_unticked_checkbox_is_false(self):
        self.record.is_company = True
        self._line('is_company')
        # Une case décochée n'est pas envoyée par le navigateur : le champ
        # n'apparaît pas dans le POST et ne doit donc pas être réécrit.
        self.form.save(self.instance, {})
        self.assertIs(self.record.is_company, True)
        # Envoyée vide, elle vaut False.
        self.form.save(self.instance, {'wf_is_company': ""})
        self.assertIs(self.record.is_company, False)

    def test_unconvertible_number_does_not_break_the_draft(self):
        self._line('color')
        self.assertEqual(self.form.save(self.instance, {'wf_color': "abc"}), [])
        self.assertEqual(self.record.color, 0)

    # ------------------------------------------------------------
    # Le cas d'usage visé : étape → réponse → formulaire adapté
    # ------------------------------------------------------------

    def test_answering_one_field_reveals_the_next(self):
        """« Étape → type de besoin → formulaire adapté », sans template dédié.

        C'est le dossier progressif : le questionnaire se déplie au fur et à
        mesure des réponses, et la seule chose écrite pour l'obtenir est une
        expression dans une ligne de configuration.
        """
        self._line('is_company', sequence=10)
        self._line(
            'website', sequence=20,
            visible_expression="field('is_company')",
            required_expression="field('is_company')",
        )

        self.record.is_company = False
        self.assertEqual(len(self.form.visible_field_lines(self.instance)), 1)

        # Le porteur répond « oui » : le champ suivant apparaît, et devient requis.
        self.form.save(self.instance, {'wf_is_company': "on"})
        visible = self.form.visible_field_lines(self.instance)
        self.assertEqual(len(visible), 2)
        self.assertTrue(self.form.validate(self.instance, {}))
