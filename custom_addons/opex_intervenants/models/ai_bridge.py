"""Le pont vers le service d'IA, sans dépendance déclarée.

`opex_intervenants` ne déclare pas `opex_ai_core` dans son manifeste : le
portail doit rester livrable sans assistance IA. Le service est donc résolu
**au moment de l'appel**, et son absence se comporte exactement comme une clé
absente - journalisée si possible, et None.

C'est la règle 1 du service portée d'un cran plus haut. Elle disait : une clé
absente ne bloque aucun parcours. Elle dit maintenant : un module absent non
plus.

CE QUE CE PONT N'EST PAS

Ce n'est pas une réimplémentation dégradée du service. Quand `opex_ai_core`
n'est pas installé, il n'y a pas d'IA du tout - le module bascule en saisie
manuelle, ce qu'il sait faire depuis l'Extension 3. Aucune logique de
repli n'est écrite ici, et c'est ce qui garde ce fichier lisible.

POURQUOI `self.env.get()` ET PAS UN `try: import`

Un module Odoo peut être présent sur le disque et non installé sur la base.
Seul le registre le sait, et `self.env` est le registre. Un import Python
réussirait sur un module désinstallé et donnerait un modèle sans table.
"""

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

AI_SERVICE = 'opex.ai.service'
AI_PROMPT = 'opex.ai.prompt'


class AiBridge(models.AbstractModel):
    """Le point de passage unique vers l'assistance IA.

    Tout appel du module passe par ici. Un test lit le source et refuse un
    `self.env['opex.ai.service']` écrit ailleurs : sans cette discipline, le
    jour où `opex_ai_core` n'est pas installé, on découvrirait les endroits
    non protégés un par un, en production.
    """

    _name = 'opex.ai.bridge'
    _description = "Accès à l'assistance IA, si elle est installée"

    @api.model
    def _ai_available(self):
        """L'assistance est-elle installée **et** configurée ?

        Deux questions en une, et c'est voulu : de l'extérieur, un module
        absent et une clé absente donnent le même résultat - pas d'IA. Les
        distinguer n'aurait de sens que pour un administrateur, et celui-là
        lit l'écran de configuration.
        """
        service = self.env.get(AI_SERVICE)
        if service is None:
            return False
        return service._is_configured()

    @api.model
    def _ai_call_prompt(self, code, values=None, document=None):
        """Appelle un prompt nommé. Rend un dict, ou None.

        Signature identique à `opex.ai.service._call_prompt()` : les appelants
        écrivent contre le pont exactement comme ils écriraient contre le
        service, et le jour où la dépendance serait rétablie, seul ce fichier
        changerait.

        Ne lève jamais. Trois raisons de rendre None, et l'appelant n'a pas à
        les distinguer : le module n'est pas installé, aucune clé n'est
        configurée, ou l'appel a échoué.
        """
        service = self.env.get(AI_SERVICE)
        if service is None:
            _logger.info(
                "opex_intervenants: `opex_ai_core` n'est pas installé ; le "
                "prompt « %s » n'a pas été appelé. Saisie manuelle.", code)
            return None
        return service._call_prompt(code, values=values, document=document)

    @api.model
    def _ai_prompt_exists(self, code):
        """Le prompt est-il livré ? Utile aux écrans et aux tests.

        Un prompt manquant n'est pas une panne d'exécution mais une panne de
        configuration : mieux vaut le voir avant de proposer un bouton.
        """
        prompt = self.env.get(AI_PROMPT)
        if prompt is None:
            return False
        return bool(prompt.sudo().search_count([('code', '=', code)]))
