import ast
import os

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import WorkflowCase


@tagged('post_install', '-at_install')
class TestDefinition(WorkflowCase):
    """Extension 1 — le configurateur refuse-t-il un graphe incohérent ?"""

    def test_valid_graph_is_accepted(self):
        definition = self._linear_definition(publish=False)
        self.assertTrue(definition._check_graph())
        definition.action_publish()
        self.assertEqual(definition.state, 'published')

    def test_two_start_stages_rejected(self):
        definition = self._definition()
        self._stage(definition, 'a', "Première", is_start=True)
        self._stage(definition, 'b', "Seconde", is_start=True, is_end=True)

        with self.assertRaises(UserError) as error:
            definition.action_publish()
        message = str(error.exception)
        # Les deux étapes fautives sont nommées : un designer doit pouvoir
        # corriger sans lire le code.
        self.assertIn("Première", message)
        self.assertIn("Seconde", message)
        self.assertEqual(definition.state, 'draft')

    def test_no_start_stage_rejected(self):
        definition = self._definition()
        self._stage(definition, 'a', "Unique", is_end=True)
        with self.assertRaises(UserError) as error:
            definition.action_publish()
        self.assertIn("Étape de départ", str(error.exception))

    def test_no_end_stage_rejected(self):
        definition = self._definition()
        start = self._stage(definition, 'a', "Départ", is_start=True)
        second = self._stage(definition, 'b', "Suite")
        self._transition(definition, 't', start, second)
        with self.assertRaises(UserError) as error:
            definition.action_publish()
        self.assertIn("Étape finale", str(error.exception))

    def test_orphan_stage_rejected_and_named(self):
        definition = self._definition()
        start = self._stage(definition, 'start', "Départ", is_start=True)
        end = self._stage(definition, 'end', "Fin", is_end=True)
        self._stage(definition, 'lost', "Étape oubliée")
        self._transition(definition, 't', start, end)

        with self.assertRaises(UserError) as error:
            definition.action_publish()
        self.assertIn("Étape oubliée", str(error.exception))

    def test_dead_end_stage_rejected(self):
        """L'erreur exacte que produit l'insertion d'une étape intermédiaire.

        On crée l'étape et la transition qui y mène, on oublie celle qui en
        repart : c'est le geste du test d'acceptation, et c'est le contrôle qui
        l'attrape avant que le premier dossier s'y retrouve coincé.
        """
        definition = self._definition()
        start = self._stage(definition, 'start', "Départ", is_start=True)
        middle = self._stage(definition, 'demo_day', "Demo Day")
        end = self._stage(definition, 'end', "Fin", is_end=True)
        self._transition(definition, 't1', start, middle)
        self._transition(definition, 't2', start, end)

        with self.assertRaises(UserError) as error:
            definition.action_publish()
        message = str(error.exception)
        self.assertIn("Demo Day", message)
        self.assertIn("transition sortante", message)

    def test_cross_definition_transition_rejected(self):
        first = self._definition(code='wf_one')
        start = self._stage(first, 'start', "Départ", is_start=True)
        self._stage(first, 'end', "Fin", is_end=True)

        other = self._definition(code='wf_two')
        foreign_stage = self._stage(other, 'ailleurs', "Ailleurs", is_end=True)

        self.Transition.create({
            'definition_id': first.id,
            'code': 'cross',
            'name': "Transition croisée",
            'source_stage_id': start.id,
            'target_stage_id': foreign_stage.id,
        })

        with self.assertRaises(UserError) as error:
            first.action_publish()
        self.assertIn("Transition croisée", str(error.exception))

    def test_all_errors_reported_at_once(self):
        """Un graphe à deux défauts les signale tous les deux du premier coup."""
        definition = self._definition()
        self._stage(definition, 'a', "Alpha", is_start=True)
        self._stage(definition, 'b', "Beta", is_start=True)
        with self.assertRaises(UserError) as error:
            definition.action_publish()
        message = str(error.exception)
        self.assertIn("Étape de départ", message)
        self.assertIn("Étape finale", message)

    # ------------------------------------------------------------
    # Unicité — le test qui attrape la régression `_sql_constraints`
    # ------------------------------------------------------------

    def test_definition_code_unique_per_version(self):
        self._definition(code='dup')
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self._definition(code='dup')

    def test_stage_code_unique_within_definition(self):
        definition = self._definition()
        self._stage(definition, 'same')
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self._stage(definition, 'same')

    def test_same_stage_code_allowed_across_definitions(self):
        first = self._definition(code='wf_a')
        second = self._definition(code='wf_b')
        self._stage(first, 'draft')
        # Le même code d'étape dans deux workflows différents est légitime :
        # c'est même la base du contrat de codes communs entre modules.
        self.assertTrue(self._stage(second, 'draft'))

    # ------------------------------------------------------------
    # Versionnage
    # ------------------------------------------------------------

    def test_new_version_rewires_transitions_on_copied_stages(self):
        """La v2 doit être autonome : aucune de ses transitions ne doit
        pointer vers une étape de la v1."""
        definition = self._linear_definition(code='versioned')
        definition.action_new_version()

        new = self.Definition.search(
            [('code', '=', 'versioned'), ('version', '=', 2)])
        self.assertEqual(len(new), 1)
        self.assertEqual(len(new.stage_ids), len(definition.stage_ids))
        self.assertEqual(len(new.transition_ids), len(definition.transition_ids))

        old_stage_ids = set(definition.stage_ids.ids)
        for transition in new.transition_ids:
            self.assertNotIn(transition.source_stage_id.id, old_stage_ids)
            self.assertNotIn(transition.target_stage_id.id, old_stage_ids)
            self.assertEqual(transition.source_stage_id.definition_id, new)
            self.assertEqual(transition.target_stage_id.definition_id, new)

        self.assertEqual(definition.state, 'archived')
        self.assertFalse(definition.active)
        self.assertTrue(new._check_graph())

    def test_new_version_takes_the_code_offline_until_published(self):
        """⚠ Comportement à connaître, conforme à la spécification.

        `action_new_version()` archive l'ancienne version **immédiatement**.
        Entre cet instant et la publication de la v2, aucune version n'est
        résolvable : `start_workflow()` échoue pour tout **nouvel**
        enregistrement.

        Les instances **déjà en cours** ne sont pas affectées — elles portent
        une clé étrangère vers la définition archivée et continuent de tourner
        sous elle, ce qui est précisément ce qui rend l'audit trail honnête six
        mois plus tard.

        Ce test existe pour que cette fenêtre soit documentée et visible, plutôt
        que découverte en production un jour de bascule de version.
        """
        definition = self._linear_definition(code='resolved')
        record = self.env['res.partner'].create({'name': "Dossier en cours"})
        instance = self.Instance._start_for(record, 'resolved')

        definition.action_new_version()
        new = self.Definition.search(
            [('code', '=', 'resolved'), ('version', '=', 2)])
        self.assertEqual(len(new), 1)
        self.assertEqual(new.state, 'draft')

        # Fenêtre d'indisponibilité : plus aucune version publiée.
        with self.assertRaises(UserError):
            self.Definition._get_for_code('resolved')

        # …mais le dossier déjà engagé continue sous sa version d'origine.
        self.assertEqual(instance.definition_id, definition)
        self.assertEqual(instance.state, 'running')
        self.assertTrue(instance.available_transitions())

        # La publication de la v2 referme la fenêtre.
        new.action_publish()
        self.assertEqual(self.Definition._get_for_code('resolved'), new)
        self.assertEqual(instance.definition_id, definition)

    def test_get_for_code_unknown_is_explicit(self):
        with self.assertRaises(UserError) as error:
            self.Definition._get_for_code('inexistant')
        self.assertIn("inexistant", str(error.exception))

    def test_unpublished_definition_is_not_resolvable(self):
        self._linear_definition(code='still_draft', publish=False)
        with self.assertRaises(UserError):
            self.Definition._get_for_code('still_draft')

    # ------------------------------------------------------------
    # La propriété qui garantit le test d'acceptation
    # ------------------------------------------------------------

    #: Termes métier des documents sources. Aucun ne doit apparaître comme
    #: identifiant ou comme littéral exact dans le code exécutable du moteur.
    #:
    #: ⚠ `score` a été **retiré** de cette liste en Extension 7, et c'est une
    #: distinction de fond, pas un assouplissement : le score d'un candidat de
    #: matching est une primitive du moteur — tout système de scoring en a un —
    #: alors que le score du *projet*, celui que lit `field('score') >= 70`,
    #: reste une donnée de configuration que le moteur ne nomme nulle part.
    BUSINESS_VOCABULARY = {
        'pitch_deck', 'business_plan', 'ceo_approval',
        'depot_express', 'pre_analyse', 'dossier_progressif', 'quality_gate',
        'etude_decision', 'matching_financier', 'accompagnement',
        'mise_en_relation', 'decision_financeur', 'closing',
        'investisseur', 'porteur', 'remediation', 'evaluateur',
    }

    #: ⚠ Brèche connue et assumée, à rouvrir si elle gêne.
    #:
    #: Le périmètre de l'Extension 7 impose `candidate_type` en Selection avec
    #: les valeurs expert / mentor / investisseur / sponsor. « Investisseur »
    #: est du vocabulaire métier, et il est ici dans du code exécutable — c'est
    #: la seule entorse à la règle « le moteur ne sait rien du métier » dans
    #: tout le module.
    #:
    #: Elle est listée nommément plutôt que dissoute dans la liste ci-dessus,
    #: pour qu'elle reste visible et qu'un ajout ultérieur ne passe pas
    #: inaperçu derrière elle.
    #:
    #: La correction propre, si on la veut : remplacer la Selection par un
    #: Many2one vers `opex.workflow.role`, dont le référentiel porte déjà
    #: Expert et Investisseur en **données** — ce qui est déjà admis. Le code
    #: du moteur redeviendrait alors muet sur le métier.
    KNOWN_VOCABULARY_BREACHES = {
        ('models/matching.py', 'investisseur'),
        ('models/workflow_action.py', 'investisseur'),
    }

    def test_engine_contains_no_business_vocabulary(self):
        """Le moteur ne doit nommer aucun terme métier dans son code exécutable.

        C'est la traduction exécutable de la règle « le moteur ne sait rien du
        métier ». Si ce test passe tous les jours, le `git diff` vide sur
        `opex_workflow/` le jour du test d'acceptation est acquis par
        construction et non par chance.

        L'analyse passe par l'AST et non par une recherche de texte, pour
        distinguer deux choses que `grep` confond :

        - `if stage.code == 'accompagnement'` — un identifiant ou un littéral
          **exact**, c'est-à-dire du métier codé en dur : refusé ;
        - « exemple : has_document('pitch_deck') » dans une aide ou une
          docstring — de la documentation qui illustre un usage : accepté, et
          même souhaitable, puisque c'est ce que lira la personne qui configure.

        Les fichiers de `tests/` sont exclus : ils nomment `res.partner` et ses
        champs natifs, ce qui est précisément leur rôle.
        """
        module_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        offenders = []

        for directory, _dirs, filenames in os.walk(module_root):
            parts = directory.split(os.sep)
            if 'tests' in parts or '__pycache__' in parts:
                continue
            for filename in sorted(filenames):
                if not filename.endswith('.py'):
                    continue
                path = os.path.join(directory, filename)
                relative = os.path.relpath(path, module_root)
                with open(path, encoding='utf-8') as handle:
                    tree = ast.parse(handle.read(), filename=relative)

                for node in ast.walk(tree):
                    found = None
                    if isinstance(node, ast.Name):
                        found = node.id
                    elif isinstance(node, ast.Attribute):
                        found = node.attr
                    elif isinstance(node, ast.keyword):
                        found = node.arg
                    elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                        found = node.name
                    elif isinstance(node, ast.arg):
                        found = node.arg
                    elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                        # Littéral **exact** seulement : une aide contextuelle
                        # qui cite un exemple reste un texte, pas une constante
                        # métier.
                        found = node.value

                    if not found or found.lower() not in self.BUSINESS_VOCABULARY:
                        continue
                    breach = (relative.replace(os.sep, '/'), found.lower())
                    if breach in self.KNOWN_VOCABULARY_BREACHES:
                        continue
                    offenders.append('%s:%s: %s' % (
                        relative, getattr(node, 'lineno', '?'), found))

        self.assertFalse(offenders, "\n".join(
            ["Vocabulaire métier trouvé dans le code exécutable du moteur :"]
            + sorted(set(offenders))))
