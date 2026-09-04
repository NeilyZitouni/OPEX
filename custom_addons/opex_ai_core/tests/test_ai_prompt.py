"""La couche prompt : en données, et rendue sans casser le JSON d'exemple."""

import os
import re
from unittest.mock import patch

import requests

from odoo.tests.common import TransactionCase, tagged

from .test_ai_service import FakeResponse, gemini_answer


@tagged('post_install', '-at_install')
class TestAiPrompt(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Prompt = cls.env['opex.ai.prompt']
        cls.Service = cls.env['opex.ai.service']
        cls.Log = cls.env['opex.ai.call.log']
        cls.params = cls.env['ir.config_parameter'].sudo()

    def _configure(self):
        self.params.set_param('opex_ai.api_key', 'cle-de-test')
        self.params.set_param('opex_ai.model', 'gemini-2.0-flash')
        self.params.set_param('opex_ai.provider', 'gemini')

    #
    # Le rendu
    #

    def test_a_json_example_in_the_body_is_left_alone(self):
        """Le piège que `str.format()` aurait posé.

        Tout prompt d'extraction contient un exemple du JSON attendu - c'est
        la seule façon fiable d'obtenir du JSON d'un modèle de langage. Or
        `'{"ok": true}'.format()` lève : Python y voit un champ de
        remplacement nommé `"ok": true`.

        Autrement dit, la méthode de rendu la plus évidente aurait cassé sur
        exactement les prompts que ce module existe pour porter.
        """
        prompt = self.Prompt.create({
            'code': 'test_json_example',
            'name': "Avec un exemple JSON",
            'body': 'Extrais {champ} et réponds par {"nom": "...", "age": 0}.',
        })
        self.assertEqual(prompt.placeholders(), ['champ'])

        rendered = prompt.render({'champ': "le nom"})
        self.assertIn('{"nom": "...", "age": 0}', rendered)
        self.assertIn("Extrais le nom", rendered)

    def test_a_missing_variable_refuses_the_render(self):
        """Refuser plutôt que rendre partiellement.

        Un prompt envoyé avec `{cv_texte}` en toutes lettres produit une
        réponse plausible et fausse : le pire des deux mondes. Un rendu
        refusé, lui, se voit dans le journal.
        """
        prompt = self.Prompt.create({
            'code': 'test_missing',
            'name': "Deux variables",
            'body': "Analyse {cv_texte} pour le poste {poste}.",
        })
        self.assertEqual(prompt.placeholders(), ['cv_texte', 'poste'])
        self.assertIsNone(prompt.render({'cv_texte': "…"}))

        # Assertion positive : avec les deux, il rend.
        self.assertEqual(
            prompt.render({'cv_texte': "un CV", 'poste': "auditeur"}),
            "Analyse un CV pour le poste auditeur.")

    def test_two_prompts_cannot_share_a_code(self):
        """Le code est la seule partie citée par du Python.

        Contrainte SQL et non contrôle applicatif : deux prompts de même code
        rendraient `_for_code()` non déterministe, et l'appelant recevrait
        l'un ou l'autre selon l'ordre d'insertion.

        L'idiome est celui du projet : `assertRaises(Exception)` dans un
        savepoint. Une contrainte SQL ne se déclenche pas à `create()` mais au
        flush, et sans savepoint la transaction entière serait abandonnée -
        tout ce qui suivrait recevrait « current transaction is aborted ».
        """
        from odoo.tools import mute_logger

        self.Prompt.create({
            'code': 'test_unique', 'name': "Premier", 'body': "Bonjour."})
        with mute_logger('odoo.sql_db'), self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.Prompt.create({
                    'code': 'test_unique', 'name': "Second",
                    'body': "Bonsoir."}).flush_recordset()

    #
    # Le branchement sur le service
    #

    def test_the_connection_test_goes_through_the_data_prompt(self):
        """Aucune chaîne de prompt dans le code, y compris celle-ci.

        C'était la plus facile à justifier en dur : une phrase, jamais
        modifiée. Elle est en données comme les autres - une exception
        « juste cette fois » est exactement comme ça qu'une règle s'érode.
        """
        self._configure()
        with patch.object(requests, 'post', return_value=FakeResponse(
                payload=gemini_answer('{"ok": true}'))):
            ok, _message = self.Service._test_connection()

        self.assertTrue(ok)
        log = self.Log.sudo().search(
            [('purpose', '=', 'connection_test')], order='id desc', limit=1)
        self.assertTrue(
            log, "L'essai de connexion n'est pas passé par le prompt nommé.")
        self.assertEqual(log.prompt_version, 1)

    def test_the_journal_carries_the_prompt_version(self):
        """Savoir qu'une extraction a mal tourné ne suffit pas.

        Une formulation se retouche souvent. Sans la version, on ne saurait
        pas laquelle a produit quoi.
        """
        self._configure()
        prompt = self.Prompt.create({
            'code': 'test_version', 'name': "Versionné", 'version': 7,
            'body': "Réponds par du JSON."})

        with patch.object(requests, 'post', return_value=FakeResponse(
                payload=gemini_answer('{"ok": true}'))):
            result = self.Service._call_prompt(prompt.code)

        self.assertEqual(result, {'ok': True})
        log = self.Log.sudo().search(
            [('purpose', '=', 'test_version')], order='id desc', limit=1)
        self.assertEqual(log.prompt_version, 7)

    def test_an_unknown_prompt_is_logged_and_returns_none(self):
        """La règle 1 vaut pour toute la chaîne, pas seulement le réseau.

        Un prompt absent est une panne de configuration. Elle ne doit pas
        bloquer un parcours : journalisée, et None.
        """
        self._configure()
        with patch.object(requests, 'post') as post:
            result = self.Service._call_prompt('un_prompt_qui_nexiste_pas')

        self.assertIsNone(result)
        post.assert_not_called()
        log = self.Log.sudo().search(
            [('purpose', '=', 'un_prompt_qui_nexiste_pas')],
            order='id desc', limit=1)
        self.assertEqual(log.error_type, 'no_prompt')

    def test_an_unrenderable_prompt_never_reaches_the_network(self):
        """On ne paie pas un appel qu'on sait mal formé."""
        self._configure()
        self.Prompt.create({
            'code': 'test_unrendered', 'name': "Avec variable",
            'body': "Analyse {cv_texte}."})

        with patch.object(requests, 'post') as post:
            result = self.Service._call_prompt('test_unrendered', values={})

        self.assertIsNone(result)
        post.assert_not_called()
        log = self.Log.sudo().search(
            [('purpose', '=', 'test_unrendered')], order='id desc', limit=1)
        self.assertEqual(log.error_type, 'no_prompt')
        self.assertIn("cv_texte", log.error_message)

    def test_the_purpose_is_the_prompt_code(self):
        """Le journal doit dire quelle fonctionnalité coûte cher.

        « un appel à Gemini » ne se regroupe pas. Le code du prompt, si.
        """
        self._configure()
        self.Prompt.create({
            'code': 'test_purpose', 'name': "Objet", 'body': "Bonjour."})

        with patch.object(requests, 'post', return_value=FakeResponse(
                payload=gemini_answer('{"ok": true}'))):
            self.Service._call_prompt('test_purpose')

        log = self.Log.sudo().search(
            [('purpose', '=', 'test_purpose')], order='id desc', limit=1)
        self.assertTrue(log)

    #
    # La règle : rien en dur
    #

    def test_no_prompt_text_is_hardcoded_in_the_module(self):
        """Test de garde sur le source, docstrings et commentaires retirés.

        On cherche les formulations qui trahissent un prompt écrit en dur :
        une consigne adressée à un modèle. Le critère est volontairement
        étroit - un test de source trop large finit par interdire qu'on parle
        de ce qu'il protège, leçon de l'Extension 7.

        L'assertion positive qui va avec : la boucle doit avoir lu des
        fichiers. Une boucle qui n'en trouve plus passerait au vert sans rien
        vérifier.
        """
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        models_dir = os.path.join(root, 'models')

        suspects = re.compile(
            r"['\"][^'\"]*(?:Réponds |Extrais |Analyse le |Tu es un )",
            re.IGNORECASE)

        examined = 0
        for name in sorted(os.listdir(models_dir)):
            if not name.endswith('.py'):
                continue
            path = os.path.join(models_dir, name)
            with open(path, encoding='utf-8') as handle:
                source = handle.read()
            source = re.sub(r'("""|\'\'\')(?:.|\n)*?\1', '', source)
            source = re.sub(r'#[^\n]*', '', source)
            examined += 1
            match = suspects.search(source)
            self.assertIsNone(
                match,
                "« %s » semble porter un prompt en dur : %s"
                % (name, match.group(0) if match else ''))

        self.assertGreaterEqual(
            examined, 4,
            "La boucle n'a presque rien lu : le chemin des modèles est "
            "probablement faux.")

    def test_the_shipped_prompts_are_all_renderable(self):
        """Un prompt livré dont les variables ne se voient pas est inutile.

        Le test rend chaque prompt du module avec des valeurs d'exemple. Il
        rougira si l'un d'eux devient irrendable - une accolade mal fermée,
        typiquement.
        """
        prompts = self.Prompt.sudo().search([])
        self.assertTrue(prompts, "Aucun prompt livré.")
        for prompt in prompts:
            sample = {name: "x" for name in prompt.placeholders()}
            self.assertIsNotNone(
                prompt.render(sample),
                "Le prompt « %s » n'est pas rendable." % prompt.code)
