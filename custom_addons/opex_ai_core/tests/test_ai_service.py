"""Les quatre règles non négociables du service d'IA, éprouvées.

Aucun de ces tests n'appelle le réseau. `requests.post` est remplacé par une
fonction de test : un test qui dépendrait d'Internet échouerait le jour d'une
coupure et, pire, passerait au vert le jour où le fournisseur répondrait par
hasard ce qu'on attend.

Ce que ces tests ne prouvent donc pas : que l'API de Gemini répond comme on le
croit. Cela se vérifie par le bouton « Tester la connexion » de l'écran de
configuration, qui fait un vrai aller-retour - c'est la partie 2 du protocole
manuel.
"""

import json
from unittest.mock import patch

import requests

from odoo.tests.common import TransactionCase, tagged


class FakeResponse:
    """Le minimum de `requests.Response` que le service utilise."""

    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload or {})

    def json(self):
        if self._payload is None:
            raise ValueError("pas de JSON")
        return self._payload


def gemini_answer(text, prompt_tokens=12, completion_tokens=8):
    """Une réponse Gemini bien formée, portant ce texte."""
    return {
        'candidates': [{'content': {'parts': [{'text': text}]}}],
        'usageMetadata': {
            'promptTokenCount': prompt_tokens,
            'candidatesTokenCount': completion_tokens,
            'totalTokenCount': prompt_tokens + completion_tokens,
        },
    }


@tagged('post_install', '-at_install')
class TestAiService(TransactionCase):
    """Extension IA-0 - le service, son journal, et ses quatre garanties."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Service = cls.env['opex.ai.service']
        cls.Log = cls.env['opex.ai.call.log']
        cls.params = cls.env['ir.config_parameter'].sudo()

    def _configure(self, api_key='cle-de-test', model='gemini-2.0-flash',
                   provider='gemini'):
        self.params.set_param('opex_ai.api_key', api_key)
        self.params.set_param('opex_ai.model', model)
        self.params.set_param('opex_ai.provider', provider)

    def _logs(self):
        """Les lignes de journal écrites par le test en cours.

        Bornées au motif du test : la base n'est jamais vide, et un
        `search([])` finirait par compter les appels de quelqu'un d'autre.
        """
        return self.Log.sudo().search([('purpose', '=', 'test_ia0')])

    #
    # Règle 1 - sans clé, None, et pas d'exception
    #

    def test_without_a_key_the_call_returns_none_and_does_not_raise(self):
        """La règle qui gouverne toutes les autres.

        Le module doit fonctionner en saisie manuelle. Une clé absente est un
        état de fonctionnement normal, pas une panne : si `_call()` levait,
        chaque écran appelant devrait l'entourer d'un try/except, et le
        premier qui l'oublierait casserait un parcours utilisateur.
        """
        self.params.set_param('opex_ai.api_key', '')

        result = self.Service._call("Peu importe.", purpose='test_ia0')

        self.assertIsNone(result)
        journal = self._logs()
        self.assertEqual(len(journal), 1, "Le journal n'a pas été écrit.")
        self.assertFalse(journal.success)
        self.assertEqual(journal.error_type, 'no_key')

    def test_without_a_key_no_http_call_is_attempted(self):
        """On ne part pas au réseau pour se faire refuser.

        Sans cette vérification, la règle 1 tiendrait par accident : l'appel
        échouerait faute d'authentification plutôt que faute de clé, et il
        aurait coûté un aller-retour et 60 secondes de timeout possible.
        """
        self.params.set_param('opex_ai.api_key', '')
        with patch.object(requests, 'post') as post:
            self.Service._call("Peu importe.", purpose='test_ia0')
        post.assert_not_called()

    def test_the_service_says_whether_it_is_configured(self):
        """La question que posent les écrans, sans lire la clé."""
        self.params.set_param('opex_ai.api_key', '')
        self.assertFalse(self.Service._is_configured())
        self._configure()
        self.assertTrue(self.Service._is_configured())

    #
    # Règle 2 - un JSON illisible n'est jamais fatal
    #

    def test_an_unparsable_answer_is_logged_and_returns_none(self):
        self._configure()
        answer = gemini_answer("Bonjour ! Voici ce que j'ai compris…")

        with patch.object(requests, 'post',
                          return_value=FakeResponse(payload=answer)):
            result = self.Service._call("Extrais.", purpose='test_ia0')

        self.assertIsNone(result)
        journal = self._logs()
        self.assertEqual(len(journal), 1)
        self.assertFalse(journal.success)
        self.assertEqual(journal.error_type, 'invalid_json')
        # Les jetons sont journalisés quand même : l'appel a été facturé,
        # qu'on ait su lire la réponse ou non.
        self.assertEqual(journal.total_tokens, 20)

    def test_a_fenced_json_block_is_accepted(self):
        """Les modèles encadrent leur JSON d'eux-mêmes.

        Le nettoyer est le travail du service. Le laisser à chaque appelant
        serait la même ligne recopiée partout, et oubliée une fois.
        """
        self._configure()
        answer = gemini_answer('```json\n{"nom": "Zitouni"}\n```')

        with patch.object(requests, 'post',
                          return_value=FakeResponse(payload=answer)):
            result = self.Service._call("Extrais.", purpose='test_ia0')

        self.assertEqual(result, {'nom': "Zitouni"})
        self.assertTrue(self._logs().success)

    def test_a_json_list_is_wrapped_rather_than_rejected(self):
        """Le contrat annonce un dictionnaire, et il est tenu."""
        self._configure()
        answer = gemini_answer('[{"competence": "Audit SI"}]')

        with patch.object(requests, 'post',
                          return_value=FakeResponse(payload=answer)):
            result = self.Service._call("Extrais.", purpose='test_ia0')

        self.assertEqual(result, {'items': [{'competence': "Audit SI"}]})

    def test_an_answer_without_candidates_is_not_fatal(self):
        """Un blocage de sécurité renvoie un corps valide et vide.

        `data['candidates'][0]` lèverait alors une `IndexError` - exactement
        ce que la règle 2 interdit.
        """
        self._configure()
        with patch.object(requests, 'post', return_value=FakeResponse(
                payload={'promptFeedback': {'blockReason': 'SAFETY'}})):
            result = self.Service._call("Extrais.", purpose='test_ia0')

        self.assertIsNone(result)
        self.assertEqual(self._logs().error_type, 'empty_response')

    #
    # Règle 3 - timeout dur et retry sur 429
    #

    def test_a_429_is_retried_with_a_backoff(self):
        """Le palier gratuit de Gemini limite les requêtes par minute.

        Sans retry, une démonstration à deux appels rapprochés échoue. Le
        test vérifie les trois choses qui comptent : qu'on retente, qu'on
        finit par réussir, et que le nombre de tentatives est journalisé -
        sans quoi on ne saurait jamais qu'on frôle le quota.
        """
        self._configure()
        responses = [
            FakeResponse(status_code=429, text="quota"),
            FakeResponse(payload=gemini_answer('{"ok": true}')),
        ]

        with patch.object(requests, 'post', side_effect=responses) as post, \
                patch('time.sleep') as sleep:
            result = self.Service._call("Extrais.", purpose='test_ia0')

        self.assertEqual(result, {'ok': True})
        self.assertEqual(post.call_count, 2)
        # La pause a bien eu lieu, et elle est exponentielle.
        sleep.assert_called_once_with(1)

        journal = self._logs()
        self.assertTrue(journal.success)
        self.assertEqual(journal.attempts, 2)

    def test_a_persistent_429_gives_up_after_three_attempts(self):
        """On retente, on ne s'acharne pas.

        Trois tentatives au plus : au-delà, l'utilisateur a quitté l'écran.
        """
        self._configure()
        with patch.object(requests, 'post', return_value=FakeResponse(
                status_code=429, text="quota")) as post, \
                patch('time.sleep'):
            result = self.Service._call("Extrais.", purpose='test_ia0')

        self.assertIsNone(result)
        self.assertEqual(post.call_count, 3)
        journal = self._logs()
        self.assertEqual(journal.error_type, 'rate_limited')
        self.assertEqual(journal.attempts, 3)

    def test_a_timeout_returns_none_and_is_not_retried(self):
        """Un fournisseur qui met plus d'une minute en mettra autant ensuite.

        Le retry est pour le quota, pas pour la lenteur : réessayer trois
        fois un timeout de 60 secondes fait attendre trois minutes.
        """
        self._configure()
        with patch.object(requests, 'post',
                          side_effect=requests.Timeout()) as post:
            result = self.Service._call("Extrais.", purpose='test_ia0')

        self.assertIsNone(result)
        self.assertEqual(post.call_count, 1)
        journal = self._logs()
        self.assertEqual(journal.error_type, 'timeout')
        self.assertFalse(journal.success)

    def test_the_hard_timeout_is_passed_to_the_request(self):
        """Le timeout ne sert à rien s'il n'atteint pas `requests`.

        Défaut classique et silencieux : la constante existe, elle est
        documentée, et personne ne l'a branchée. Sans timeout, `requests`
        attend indéfiniment et c'est le worker Odoo qui est bloqué.
        """
        self._configure()
        with patch.object(requests, 'post', return_value=FakeResponse(
                payload=gemini_answer('{"ok": true}'))) as post:
            self.Service._call("Extrais.", purpose='test_ia0')

        self.assertEqual(post.call_args.kwargs['timeout'], 60)

    def test_an_http_error_is_not_retried(self):
        """Une clé invalide le restera : la retenter coûte sans rien changer."""
        self._configure()
        with patch.object(requests, 'post', return_value=FakeResponse(
                status_code=403, text="clé invalide")) as post:
            result = self.Service._call("Extrais.", purpose='test_ia0')

        self.assertIsNone(result)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(self._logs().error_type, 'http_error')

    #
    # Règle 4 - aucune donnée métier n'entre en base
    #

    def test_the_call_writes_nothing_but_its_own_journal(self):
        """La règle 4, mesurée plutôt qu'affirmée.

        On compte les enregistrements des modèles que le service pourrait
        être tenté d'alimenter - profil expert, compétences qualifiées,
        candidatures - avant et après un appel réussi. Le service rend un
        dictionnaire ; c'est l'appelant qui décidera d'en faire quelque
        chose, et c'est lui qu'on tiendra responsable de ce qu'il écrit.
        """
        self._configure()
        watched = ('opex.innovation.expert.profile', 'opex.expert.skill',
                   'opex.mission.application')
        before = {name: self.env[name].sudo().search_count([])
                  for name in watched}

        answer = gemini_answer(
            '{"nom": "Zitouni", "competences": ["Audit SI", "ISO 27001"]}')
        with patch.object(requests, 'post',
                          return_value=FakeResponse(payload=answer)):
            result = self.Service._call("Extrais le CV.", purpose='test_ia0')

        self.assertEqual(result['nom'], "Zitouni")
        for name in watched:
            self.assertEqual(
                self.env[name].sudo().search_count([]), before[name],
                "`_call()` a écrit dans « %s » : le service doit rendre un "
                "dictionnaire, pas alimenter la base." % name)

    def test_the_service_exposes_one_public_method(self):
        """« Une méthode `_call()`, et rien d'autre d'exposé. »

        Test de garde : le jour où quelqu'un ajoute une méthode publique au
        service, la conversation a lieu. Les appelants ne doivent connaître
        que `_call()` - c'est ce qui permet de changer de fournisseur sans
        toucher à personne.
        """
        public = [
            name for name in vars(type(self.Service))
            if not name.startswith('_') and callable(
                getattr(type(self.Service), name, None))
        ]
        self.assertEqual(
            public, [],
            "Le service expose %s en plus de `_call()`." % public)

    #
    # Le journal
    #

    def test_the_journal_never_carries_the_prompt_or_the_answer(self):
        """Un CV contient des données personnelles.

        Le journal sert à comprendre une panne et à suivre un budget, pas à
        rejouer un appel. Ce test verrouille le critère : le jour où
        quelqu'un ajoute un champ `prompt` pour déboguer plus vite, la
        conversation a lieu.
        """
        fields_ = self.Log._fields
        for suspect in ('prompt', 'response', 'answer', 'payload', 'body',
                        'document', 'content'):
            self.assertNotIn(
                suspect, fields_,
                "Le journal porte « %s » : le contenu des appels n'a pas à "
                "être conservé." % suspect)

    def test_the_journal_estimates_a_cost_from_the_tokens(self):
        """Le fait est le nombre de jetons ; le coût n'en est que la conversion.

        Le test cite le tarif pour que le modifier oblige à revenir ici.
        """
        self._configure(model='gemini-2.0-flash')
        answer = gemini_answer('{"ok": true}',
                               prompt_tokens=1_000_000,
                               completion_tokens=1_000_000)

        with patch.object(requests, 'post',
                          return_value=FakeResponse(payload=answer)):
            self.Service._call("Extrais.", purpose='test_ia0')

        journal = self._logs()
        # 1 M de jetons envoyés à 0,10 $ + 1 M reçus à 0,40 $.
        self.assertAlmostEqual(journal.cost_estimate, 0.50, places=6)

    def test_an_unknown_provider_is_logged_not_raised(self):
        """Ajouter un fournisseur est une méthode de plus.

        En attendant qu'elle existe, une valeur inconnue se comporte comme
        une clé absente : journalisée, et None. Le dispatch par `getattr` est
        le même idiome que `_execute_<action_type>` du moteur.
        """
        self._configure(provider='un_fournisseur_qui_nexiste_pas')
        with patch.object(requests, 'post') as post:
            result = self.Service._call("Extrais.", purpose='test_ia0')

        self.assertIsNone(result)
        post.assert_not_called()
        self.assertEqual(self._logs().error_type, 'no_provider')

    def test_a_journal_failure_never_breaks_the_call(self):
        """Il serait absurde qu'un appel réussi échoue parce qu'on n'a pas su
        écrire qu'il avait réussi."""
        self._configure()
        answer = gemini_answer('{"ok": true}')

        with patch.object(requests, 'post',
                          return_value=FakeResponse(payload=answer)), \
                patch.object(type(self.Log), 'create',
                             side_effect=Exception("disque plein")):
            result = self.Service._call("Extrais.", purpose='test_ia0')

        self.assertEqual(result, {'ok': True})

    #
    # L'écran de configuration
    #

    def test_the_connection_test_reports_the_absence_of_a_key(self):
        self.params.set_param('opex_ai.api_key', '')
        ok, message = self.Service._test_connection()
        self.assertFalse(ok)
        self.assertIn("saisie manuelle", message)

    def test_the_connection_test_succeeds_on_a_well_formed_answer(self):
        self._configure()
        with patch.object(requests, 'post', return_value=FakeResponse(
                payload=gemini_answer('{"ok": true}'))):
            ok, message = self.Service._test_connection()

        self.assertTrue(ok)
        self.assertIn("gemini-2.0-flash", message)

    def test_the_connection_test_never_shows_the_key(self):
        """Un message d'erreur qui recopie la clé finit dans une capture d'écran."""
        self._configure(api_key='SECRET-A-NE-PAS-AFFICHER')
        with patch.object(requests, 'post', return_value=FakeResponse(
                status_code=403, text="invalid api key")):
            ok, message = self.Service._test_connection()

        self.assertFalse(ok)
        self.assertNotIn('SECRET-A-NE-PAS-AFFICHER', message)

    #: Ce à quoi ressemble une vraie clé de fournisseur. `AIza...` est
    #: l'ancien format Google, `AQ.Ab8...` le nouveau.
    _REAL_KEY_SHAPES = (
        r"AIza[0-9A-Za-z_\-]{30,}",
        r"AQ\.[0-9A-Za-z_\-]{30,}",
    )
    #: Les valeurs qui trahissent une fixture. Une clé de test n'est pas une
    #: clé : la refuser reviendrait à interdire d'écrire un test du service.
    _PLACEHOLDER_MARKS = ('test', 'fake', 'dummy', 'exemple', 'xxx', 'secret')

    def test_no_versioned_file_carries_a_real_api_key(self):
        """« Jamais dans le code, jamais dans un fichier de données versionné. »

        Un dépôt Git conserve tout : une clé committée reste compromise même
        après avoir été retirée.

        Ce test a d'abord rougi sur du code parfaitement légitime - la
        fixture `set_param('opex_ai.api_key', 'cle-de-test')` de la suite
        voisine. Le réflexe aurait été de sortir `tests/` du périmètre ; ç'
        aurait été le mauvais correctif, puisque c'est justement dans un
        fichier de test qu'une vraie clé finit par se glisser un jour de
        débogage.

        Le critère a donc été réécrit plutôt qu'élargi, et il est **plus
        strict** qu'avant sur ce qui compte : les deux formats de clé Google
        sont refusés partout, sans exception ; une affectation littérale du
        paramètre n'est tolérée que si la valeur se reconnaît comme une
        fixture. Une chaîne longue et anonyme est refusée.
        """
        import os
        import re

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        shapes = re.compile("|".join(self._REAL_KEY_SHAPES))
        assignment = re.compile(
            r"opex_ai\.api_key['\"]\s*,\s*['\"]([^'\"]*)['\"]")

        examined = 0
        for folder, _dirs, names in os.walk(root):
            if '__pycache__' in folder:
                continue
            for name in names:
                if not name.endswith(('.py', '.xml', '.csv', '.md')):
                    continue
                path = os.path.join(folder, name)
                with open(path, encoding='utf-8', errors='ignore') as handle:
                    content = handle.read()
                examined += 1

                self.assertIsNone(
                    shapes.search(content),
                    "Une clé au format d'un fournisseur est présente dans "
                    "« %s »." % name)

                for value in assignment.findall(content):
                    looks_like_fixture = (
                        len(value) < 20
                        or any(mark in value.lower()
                               for mark in self._PLACEHOLDER_MARKS))
                    self.assertTrue(
                        looks_like_fixture,
                        "« %s » affecte une valeur longue et anonyme à "
                        "`opex_ai.api_key` : si c'est une fixture, "
                        "nommez-la comme telle." % name)

        self.assertGreater(
            examined, 8,
            "La boucle n'a presque rien lu : le chemin du module est "
            "probablement faux, et ce test passerait au vert sans vérifier.")
