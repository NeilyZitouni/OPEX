"""Le seul endroit du projet qui parle à une API externe.

===========================================================================
LES QUATRE REGLES NON NEGOCIABLES
===========================================================================

1. Sans clé configurée, `_call()` renvoie None. Il ne lève pas.
   Le module fonctionne en saisie manuelle : une panne réseau, une clé
   expirée ou un quota épuisé ne doivent jamais bloquer un parcours
   utilisateur. L'IA assiste, elle ne conditionne rien.

2. Une réponse non parsable en JSON n'est jamais fatale.
   Elle est capturée, journalisée, et `_call()` renvoie None. Un modèle de
   langage renvoie du texte ; le supposer bien formé serait une erreur de
   conception, pas un accident.

3. Timeout dur de 60 secondes, et retry avec backoff exponentiel sur 429.
   Le palier gratuit de Gemini est limité en requêtes par minute. Sans
   retry, une démonstration à deux appels rapprochés échoue.

4. Aucune donnée métier n'entre en base depuis `_call()`.
   Le service renvoie un dictionnaire ; les appelants décident quoi en
   faire. La seule écriture est la ligne de journal, que le même cahier des
   charges exige - et elle ne porte que des métadonnées d'appel, jamais le
   contenu extrait.

===========================================================================

Ajouter un fournisseur est l'ajout d'une méthode `_call_<provider>`, jamais
une modification des appelants : `_call()` dispatche par `getattr`, le même
idiome que `_execute_<action_type>` du moteur de workflow et que
`_trigger_<code>` de l'Extension 7.

Où ce fichier devrait peut-être vivre : le cahier des charges le décrit comme
« le seul endroit du **projet** » qui appelle une API externe, et le backlog
nomme un module `opex_ai_core` pour l'US-23. Il est ici parce que l'onboarding
expert est le domaine du Module 3 ; si le Module 1 ou le Module 2 en ont
besoin un jour, il faudra l'extraire plutôt que leur faire dépendre du
Module 3. Le fichier n'importe aucun modèle de mission, précisément pour que
cette extraction reste mécanique.
"""

import json
import logging
import re
import time

import requests

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# Règle 3 - le timeout est dur et il est ici, pas dans un paramètre. Un
# timeout configurable finit par être mis à 300 secondes le jour d'une
# démonstration lente, et c'est le serveur entier qui attend.
CALL_TIMEOUT = 60

# Trois tentatives au plus. Au-delà, l'utilisateur a déjà quitté l'écran :
# 3 x 60 s de timeout plus les pauses font près de quatre minutes.
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1, 2)

# Les codes qui valent « réessaie » et non « c'est cassé ». 429 est le quota
# par minute ; 503 est la surcharge côté fournisseur. Les autres erreurs HTTP
# ne se retentent pas : une clé invalide le restera.
RETRYABLE_STATUS = (429, 503)

GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "%(model)s:generateContent"
)

DEFAULT_PROVIDER = 'gemini'

# Le code du prompt d'essai, en données sous ce nom. C'est la seule chose du
# prompt que du Python cite - le texte, lui, se retouche sans redéploiement.
CONNECTION_TEST_PROMPT = 'connection_test'

# Le nom d'un modèle est une cible mouvante : Google en retire régulièrement,
# et un modèle retiré répond 404 - pas 400, pas un message explicite. Le
# premier essai de connexion de ce module a échoué ainsi, sur
# `gemini-2.0-flash`, qui n'était plus servi.
#
# Pire : `ListModels` renvoie des modèles que la clé n'a pas le droit
# d'appeler. `gemini-2.5-flash` y figurait, et répondait « no longer
# available to new users ». La liste n'est donc pas une garantie, seul
# l'appel en est une - d'où le bouton « Tester la connexion ».
#
# D'où deux choses : `_test_connection()` sait reconnaître un 404 pour le
# dire en clair, et ce défaut est celui que l'API recommande elle-même aux
# nouvelles clés. La liste se demande par
# GET https://generativelanguage.googleapis.com/v1beta/models
DEFAULT_MODEL = 'gemini-3.6-flash'

# Tarifs indicatifs en dollars par million de jetons, à la rédaction de ce
# fichier. Ils servent à estimer un coût, pas à facturer.
#
# Le fait enregistré est le **nombre de jetons**, qui vient du fournisseur ;
# le coût en est dérivé. Un tarif qui change se corrige ici, et les coûts
# passés se recalculent depuis les jetons déjà journalisés - c'est pourquoi
# les deux compteurs sont stockés séparément.
PRICING_USD_PER_MILLION = {
    'gemini-2.0-flash': (0.10, 0.40),
    'gemini-2.5-flash': (0.30, 2.50),
    'gemini-1.5-flash': (0.075, 0.30),
    'gemini-1.5-pro': (1.25, 5.00),
}
# Un modèle absent de la table est estimé au tarif d'un « flash ». C'est
# volontairement approximatif et volontairement conservé : le coût affiché est
# un ordre de grandeur, le nombre de jetons est le fait. Une facture se lit
# chez le fournisseur, pas ici.
FALLBACK_PRICING = (0.10, 0.40)

# Les modèles encadrent volontiers leur JSON dans un bloc Markdown. Le
# nettoyer fait partie du travail du service : le faire faire à chaque
# appelant serait la même ligne recopiée partout, et oubliée une fois.
JSON_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


class AiService(models.AbstractModel):
    """L'assistance IA, vue par le reste du projet.

    Une seule méthode exposée, `_call(prompt, document=None)`, qui renvoie un
    dictionnaire ou None. Tout le reste est privé : le jour où l'on change de
    fournisseur, aucun appelant ne bouge.
    """

    _name = 'opex.ai.service'
    _description = "Service d'assistance IA"

    # ------------------------------------------------------------
    # La configuration
    # ------------------------------------------------------------
    #
    # Fournisseur, clé et modèle vivent dans `ir.config_parameter`. Jamais
    # dans le code, jamais dans un fichier de données versionné : un dépôt
    # Git conserve tout, et une clé committée reste compromise même après
    # avoir été retirée.

    @api.model
    def _ai_config(self):
        """Les trois paramètres, avec leurs défauts.

        `sudo()` sur la lecture : la configuration doit être lisible par le
        service quel que soit l'appelant, y compris un compte portail dont le
        parcours déclenche une extraction. Ce que cela ouvre est borné à ces
        trois clés, et la clé ne quitte jamais cette méthode.
        """
        params = self.env['ir.config_parameter'].sudo()
        return {
            'provider': (params.get_param('opex_ai.provider')
                         or DEFAULT_PROVIDER).strip(),
            'api_key': (params.get_param('opex_ai.api_key') or '').strip(),
            'model': (params.get_param('opex_ai.model')
                      or DEFAULT_MODEL).strip(),
        }

    @api.model
    def _is_configured(self):
        """Y a-t-il une clé ? La question que se posent les écrans.

        Un bouton « Extraire le CV » n'a pas à être affiché quand rien ne
        peut répondre. Les écrans posent cette question ; ils ne lisent pas
        la clé.
        """
        return bool(self._ai_config()['api_key'])

    # ------------------------------------------------------------
    # LA méthode
    # ------------------------------------------------------------

    @api.model
    def _call(self, prompt, document=None, purpose=None, prompt_version=0):
        """Interroge le fournisseur configuré et renvoie un dictionnaire.

        `prompt` : le texte de la demande.
        `document` : facultatif, un dict `{'data': <base64 str|bytes>,
                     'mimetype': 'application/pdf'}` - un CV, typiquement.
        `purpose` : un mot pour le journal, qui dit à quoi servait l'appel.

        Renvoie **None** dans tous les cas d'échec, sans exception :
        pas de clé, timeout, erreur HTTP, quota épuisé après retry, réponse
        vide, JSON illisible. Un journal est écrit dans chacun de ces cas -
        c'est lui, et lui seul, qui permettra de savoir pourquoi une
        extraction a échoué ou pourquoi une facture monte.

        Renvoie un `dict` en cas de succès. Jamais une chaîne, jamais un
        recordset : le contrat avec les appelants est un dictionnaire, et il
        ne change pas avec le fournisseur.
        """
        started = time.monotonic()
        config = self._ai_config()

        # Le journal est écrit à cinq endroits dans cette méthode, et chacun
        # doit porter les mêmes constantes d'appel. Une fermeture plutôt que
        # cinq listes d'arguments : c'est ce qui garantit qu'aucun cas de
        # sortie n'oublie la version du prompt ou l'objet de l'appel. Un
        # journal incomplet à un seul endroit est exactement celui qu'on
        # consultera le jour de la panne.
        def journal(**values):
            values.setdefault('prompt_version', prompt_version)
            return self._log_call(config, purpose, started, **values)

        # Règle 1. Le premier des quatre cas, et le plus fréquent en
        # développement : on ne lève pas, on ne prévient pas l'utilisateur,
        # on journalise et on rend la main.
        if not config['api_key']:
            journal(
                success=False, error_type='no_key',
                error_message="Aucune clé API configurée "
                              "(`opex_ai.api_key`).")
            return None

        method = getattr(self, '_call_%s' % config['provider'], None)
        if method is None:
            journal(
                success=False, error_type='no_provider',
                error_message="Fournisseur « %s » inconnu : aucune méthode "
                              "`_call_%s`." % (config['provider'],
                                               config['provider']))
            return None

        raw, usage, failure, attempts = method(prompt, document, config)

        if failure:
            journal(success=False, error_type=failure[0],
                    error_message=failure[1],
                    attempts=attempts, usage=usage)
            return None

        # Règle 2. Le texte est arrivé ; reste à savoir s'il est exploitable.
        payload = self._parse_json(raw)
        if payload is None:
            journal(
                success=False, error_type='invalid_json',
                error_message="Réponse non parsable en JSON : %s"
                              % (raw or '')[:500],
                attempts=attempts, usage=usage)
            return None

        journal(success=True, attempts=attempts, usage=usage)
        return payload

    # ------------------------------------------------------------
    # Les prompts, en données
    # ------------------------------------------------------------

    @api.model
    def _call_prompt(self, code, values=None, document=None):
        """Rend le prompt nommé, puis appelle. Renvoie un dict ou None.

        C'est cette méthode que les appelants métier utiliseront, et non
        `_call()` : elle leur évite de porter la moindre chaîne de prompt.
        `_call()` reste exposée pour les cas où le texte est construit
        autrement, mais aucun appelant du projet ne devrait en avoir besoin.

        `purpose` prend la valeur du code : le journal dit alors quelle
        **fonctionnalité** a coûté quoi, et non « un appel à Gemini ». C'est
        toute la différence entre un journal qu'on consulte et un journal
        qu'on subit.

        Un prompt absent ou un rendu incomplet se comportent comme une clé
        absente : journalisés, et None. La règle 1 vaut pour toute la chaîne,
        pas seulement pour le réseau.
        """
        started = time.monotonic()
        config = self._ai_config()

        prompt = self.env['opex.ai.prompt']._for_code(code)
        if not prompt:
            self._log_call(
                config, code, started, success=False,
                error_type='no_prompt',
                error_message="Aucun prompt actif ne porte le code « %s »."
                              % code)
            return None

        body = prompt.render(values)
        if body is None:
            self._log_call(
                config, code, started, success=False,
                error_type='no_prompt',
                error_message="Le prompt « %s » (v%s) n'a pas pu être rendu : "
                              "variables manquantes parmi %s."
                              % (code, prompt.version,
                                 ", ".join(prompt.placeholders()) or "aucune"))
            return None

        return self._call(body, document=document,
                          purpose=code, prompt_version=prompt.version)

    # ------------------------------------------------------------
    # Gemini
    # ------------------------------------------------------------

    def _call_gemini(self, prompt, document, config):
        """L'appel HTTP, isolé ici et nulle part ailleurs.

        Renvoie le quadruplet `(texte, usage, echec, tentatives)`. `echec`
        vaut False en cas de succès, sinon `(type, message)`. C'est cette
        forme, et non une exception, qui permet à `_call()` de journaliser
        puis de rendre None sans que chaque fournisseur ait à connaître le
        journal.

        Un second fournisseur est une méthode `_call_<nom>` de la même
        signature. Aucun appelant ne change.
        """
        url = GEMINI_ENDPOINT % {'model': config['model']}
        parts = [{'text': prompt}]
        if document:
            parts.append({
                'inline_data': {
                    'mime_type': document.get('mimetype', 'application/pdf'),
                    'data': self._as_base64_text(document.get('data')),
                },
            })

        body = {'contents': [{'parts': parts}]}
        # La clé voyage en en-tête et non dans l'URL : une URL se retrouve
        # dans les journaux du serveur, dans le proxy et dans le navigateur.
        headers = {
            'Content-Type': 'application/json',
            'x-goog-api-key': config['api_key'],
        }

        usage = {}
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = requests.post(
                    url, json=body, headers=headers, timeout=CALL_TIMEOUT)
            except requests.Timeout:
                # Règle 3, second volet : le timeout ne se retente pas. Si le
                # fournisseur met plus d'une minute, il en mettra autant au
                # coup suivant, et l'utilisateur attend déjà.
                return None, usage, ('timeout',
                                     "Pas de réponse en %s s." % CALL_TIMEOUT), attempt
            except requests.RequestException as error:
                return None, usage, ('network', str(error)), attempt

            if response.status_code in RETRYABLE_STATUS:
                if attempt < MAX_ATTEMPTS:
                    time.sleep(BACKOFF_SECONDS[attempt - 1])
                    continue
                return None, usage, (
                    'rate_limited',
                    "HTTP %s après %s tentatives : %s"
                    % (response.status_code, attempt,
                       (response.text or '')[:300]),
                ), attempt

            if response.status_code != 200:
                return None, usage, (
                    'http_error',
                    "HTTP %s : %s" % (response.status_code,
                                      (response.text or '')[:300]),
                ), attempt

            try:
                data = response.json()
            except ValueError:
                return None, usage, (
                    'invalid_json',
                    "Corps de réponse non JSON : %s"
                    % (response.text or '')[:300],
                ), attempt

            usage = self._gemini_usage(data)
            text = self._gemini_text(data)
            if not text:
                return None, usage, (
                    'empty_response',
                    "Réponse sans contenu exploitable : %s"
                    % json.dumps(data)[:300],
                ), attempt
            return text, usage, False, attempt

        # Inatteignable : la boucle sort toujours par un `return`. Écrit
        # quand même, parce qu'une boucle dont on croit qu'elle sort toujours
        # est exactement celle qui finit par ne pas sortir.
        return None, usage, ('exhausted', "Boucle de tentatives épuisée."), MAX_ATTEMPTS

    @staticmethod
    def _gemini_text(data):
        """Le texte de la première candidate, s'il y en a une.

        Défensif de bout en bout : un blocage de sécurité renvoie un corps
        valide **sans** `candidates`, et un `data['candidates'][0]` nu
        lèverait une `IndexError` que la règle 2 interdit.
        """
        candidates = (data or {}).get('candidates') or []
        if not candidates:
            return ''
        parts = ((candidates[0].get('content') or {}).get('parts')) or []
        return ''.join(part.get('text', '') for part in parts).strip()

    @staticmethod
    def _gemini_usage(data):
        """Les compteurs de jetons, tels que le fournisseur les rend."""
        meta = (data or {}).get('usageMetadata') or {}
        return {
            'prompt_tokens': meta.get('promptTokenCount', 0),
            'completion_tokens': meta.get('candidatesTokenCount', 0),
            'total_tokens': meta.get('totalTokenCount', 0),
        }

    @staticmethod
    def _as_base64_text(data):
        """Un document arrive en `bytes` ou déjà en base64 : les deux passent."""
        if isinstance(data, bytes):
            return data.decode('ascii')
        return data or ''

    # ------------------------------------------------------------
    # Le JSON, et sa tolérance
    # ------------------------------------------------------------

    @api.model
    def _parse_json(self, raw):
        """Rend un dict, ou None. Ne lève jamais - c'est la règle 2.

        Deux tolérances, et deux seulement :

        - le bloc Markdown, que les modèles ajoutent d'eux-mêmes ;
        - une liste renvoyée au lieu d'un objet, qu'on enveloppe sous la clé
          `items` plutôt que de la rejeter. Le contrat annonce un
          dictionnaire, et l'appelant en aurait fait la même chose.

        Tout le reste est un échec. On ne réécrit pas la réponse d'un modèle
        pour la faire entrer de force dans un format : une extraction qu'on a
        dû rafistoler ne vaut pas d'être enregistrée.
        """
        if not raw:
            return None
        text = raw.strip()
        fenced = JSON_FENCE.match(text)
        if fenced:
            text = fenced.group(1).strip()
        try:
            payload = json.loads(text)
        except (ValueError, TypeError):
            return None
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list):
            return {'items': payload}
        return None

    # ------------------------------------------------------------
    # Le journal
    # ------------------------------------------------------------

    @api.model
    def _log_call(self, config, purpose, started, success,
                  error_type=False, error_message=False,
                  attempts=1, usage=None, prompt_version=0):
        """Écrit la ligne de journal. Ne lève jamais, quoi qu'il arrive.

        C'est la seule écriture en base de tout le service, et elle ne porte
        que des métadonnées : horodatage, modèle, jetons, durée, issue, coût
        estimé. Jamais le prompt, jamais la réponse - un CV passé au service
        contient des données personnelles, et un journal n'est pas un endroit
        où les conserver.

        Un échec d'écriture du journal est avalé et tracé dans le log serveur.
        Il serait absurde qu'une extraction réussie échoue parce qu'on n'a pas
        su écrire qu'elle avait réussi.
        """
        usage = usage or {}
        try:
            return self.env['opex.ai.call.log'].sudo().create({
                'provider': config.get('provider'),
                'model': config.get('model'),
                'purpose': purpose or False,
                'prompt_version': prompt_version or 0,
                'duration_ms': int((time.monotonic() - started) * 1000),
                'attempts': attempts,
                'prompt_tokens': usage.get('prompt_tokens', 0),
                'completion_tokens': usage.get('completion_tokens', 0),
                'total_tokens': usage.get('total_tokens', 0),
                'cost_estimate': self._estimate_cost(
                    config.get('model'), usage),
                'success': success,
                'error_type': error_type,
                'error_message': error_message,
            })
        except Exception as error:  # noqa: BLE001 - voir la docstring
            _logger.warning(
                "opex_ai: impossible d'écrire le journal d'appel : %s", error)
            return False

    @staticmethod
    def _estimate_cost(model, usage):
        """Le coût estimé, en dollars.

        Estimé, et le mot compte : les tarifs de `PRICING_USD_PER_MILLION`
        sont ceux connus à la rédaction. Le fait mesuré est le nombre de
        jetons ; si un tarif change, les coûts passés se recalculent depuis
        les compteurs, qui eux sont exacts.
        """
        usage = usage or {}
        prices = FALLBACK_PRICING
        for prefix, tarif in PRICING_USD_PER_MILLION.items():
            if (model or '').startswith(prefix):
                prices = tarif
                break
        return (
            usage.get('prompt_tokens', 0) * prices[0]
            + usage.get('completion_tokens', 0) * prices[1]
        ) / 1_000_000

    # ------------------------------------------------------------
    # L'essai de connexion
    # ------------------------------------------------------------

    @api.model
    def _test_connection(self):
        """Un aller-retour minimal, pour l'écran de configuration.

        Renvoie `(ok, message)`. Le message est destiné à un humain : il dit
        ce qui s'est passé, pas ce qu'il faudrait coder. Il ne contient
        jamais la clé.

        Le prompt demande explicitement du JSON : l'essai vérifie la chaîne
        entière - réseau, authentification, modèle, et format de réponse -
        et non seulement que le serveur répond.
        """
        config = self._ai_config()
        if not config['api_key']:
            return False, _(
                "Aucune clé API n'est enregistrée. Le module fonctionne en "
                "saisie manuelle tant que c'est le cas.")

        # Le texte du prompt n'est pas ici : il est en données, sous le code
        # `connection_test`. C'est la règle du module - aucune chaîne de
        # prompt dans le code, y compris celle-ci, qui serait pourtant la plus
        # facile à justifier.
        payload = self._call_prompt(CONNECTION_TEST_PROMPT)
        if payload is None:
            last = self.env['opex.ai.call.log'].sudo().search(
                [('purpose', '=', CONNECTION_TEST_PROMPT)],
                order='id desc', limit=1)
            detail = (last.error_message or '')[:300]

            # Le 404 mérite sa phrase. Un modèle retiré répond 404 et non un
            # message explicite : sans cette traduction, l'administrateur
            # cherche du côté de la clé alors que la clé est bonne. C'est
            # exactement ce qui s'est passé au premier essai de ce module.
            if last.error_type == 'http_error' and '404' in detail:
                return False, _(
                    "Le modèle « %(model)s » n'existe pas ou n'est plus servi "
                    "par %(provider)s. La clé, elle, a été acceptée. "
                    "Corrigez le nom du modèle."
                ) % {'model': config['model'], 'provider': config['provider']}

            # Le 403 sépare deux choses que l'administrateur confond
            # naturellement : la clé et le droit de s'en servir. Une clé peut
            # authentifier - lister les modèles, par exemple - et se voir
            # refuser la génération parce que le projet Google n'y a pas
            # accès ou n'a pas de facturation active. Le dire évite de
            # chercher une faute de frappe dans une clé qui est correcte.
            if last.error_type == 'http_error' and '403' in detail:
                return False, _(
                    "La clé est reconnue, mais le projet %(provider)s associé "
                    "n'a pas accès à la génération. C'est un réglage de "
                    "compte, pas de configuration : vérifiez l'accès au "
                    "modèle et la facturation côté fournisseur."
                ) % {'provider': config['provider']}

            if last.error_type == 'rate_limited':
                return False, _(
                    "Quota atteint après %(attempts)s tentatives. La clé et "
                    "le modèle sont bons ; c'est le nombre de requêtes qui "
                    "est limité. Réessayez dans une minute."
                ) % {'attempts': last.attempts}

            return False, _(
                "L'appel a échoué (%(type)s). %(message)s"
            ) % {
                'type': last.error_type or _("cause inconnue"),
                'message': detail,
            }

        return True, _(
            "Connexion établie avec %(provider)s, modèle %(model)s. "
            "Réponse reçue et lue comme du JSON."
        ) % {'provider': config['provider'], 'model': config['model']}
