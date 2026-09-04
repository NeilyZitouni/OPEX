"""Le journal des appels à l'IA.

Sans lui, on ne saura jamais pourquoi une facture monte ni pourquoi une
extraction a échoué. Ce sont deux questions qu'on se pose toujours après coup,
c'est-à-dire quand il est trop tard pour instrumenter.

Ce que le journal porte : des métadonnées. Horodatage, modèle, jetons, durée,
issue, coût estimé.

Ce qu'il ne porte pas, et ne doit jamais porter : le prompt et la réponse. Un
CV passé au service contient des données personnelles, et un journal de
supervision n'est pas un endroit où les conserver. Le message d'erreur est
tronqué à quelques centaines de caractères pour la même raison - il sert à
reconnaître une panne, pas à rejouer l'appel.
"""

from odoo import api, fields, models


class AiCallLog(models.Model):
    """Une ligne par appel, réussi ou non.

    Aucun champ d'état : un appel n'a pas d'avancement. Il a eu lieu, et il a
    réussi ou échoué. C'est un fait daté, pas un processus - la ligne de
    partage que le CLAUDE.md du moteur pose pour `roadmap.phase`.
    """

    _name = 'opex.ai.call.log'
    _description = "Journal des appels à l'IA"
    _order = 'date desc, id desc'
    _rec_name = 'display_name'

    date = fields.Datetime(
        string="Horodatage", default=fields.Datetime.now, readonly=True,
        index=True)
    provider = fields.Char(string="Fournisseur", readonly=True)
    model = fields.Char(string="Modèle", readonly=True, index=True)
    purpose = fields.Char(
        string="Objet de l'appel", readonly=True, index=True,
        help="Ce à quoi servait l'appel. Quand l'appel passe par un prompt "
             "nommé, c'est son code : le journal dit alors quelle "
             "fonctionnalité coûte cher, et non « un appel à Gemini ».")
    prompt_version = fields.Integer(
        string="Version du prompt", readonly=True,
        help="Celle du prompt au moment de l'appel. Sans elle, on saurait "
             "qu'une extraction a mal tourné sans pouvoir dire avec quelle "
             "formulation - et une formulation, ça se retouche souvent.")

    duration_ms = fields.Integer(string="Durée (ms)", readonly=True)
    attempts = fields.Integer(
        string="Tentatives", readonly=True, default=1,
        help="Plus d'une signifie que le quota par minute a été atteint et "
             "que le retry a joué.")

    prompt_tokens = fields.Integer(string="Jetons envoyés", readonly=True)
    completion_tokens = fields.Integer(string="Jetons reçus", readonly=True)
    total_tokens = fields.Integer(string="Jetons au total", readonly=True)

    #: En dollars. Estimé depuis les jetons et un tarif inscrit dans le
    #: service : c'est le nombre de jetons qui est le fait, le coût n'en est
    #: que la conversion. Un tarif qui change se corrige à un endroit, et les
    #: lignes passées restent recalculables.
    cost_estimate = fields.Float(
        string="Coût estimé (USD)", digits=(12, 6), readonly=True)

    success = fields.Boolean(string="Réussi", readonly=True, index=True)
    error_type = fields.Selection(
        [
            ('no_key', "Aucune clé configurée"),
            ('no_provider', "Fournisseur inconnu"),
            ('no_prompt', "Prompt absent ou non rendu"),
            ('timeout', "Délai dépassé"),
            ('network', "Erreur réseau"),
            ('rate_limited', "Quota atteint"),
            ('http_error', "Erreur HTTP"),
            ('empty_response', "Réponse vide"),
            ('invalid_json', "Réponse non parsable"),
            ('exhausted', "Tentatives épuisées"),
        ],
        string="Type d'échec",
        readonly=True,
        help="Vide quand l'appel a réussi. C'est ce champ qu'on regroupe "
             "pour savoir si une panne est du réseau, du quota ou du format.",
    )
    error_message = fields.Text(string="Détail", readonly=True)

    @api.depends('date', 'model', 'success')
    def _compute_display_name(self):
        for log in self:
            log.display_name = "%s — %s (%s)" % (
                log.date or '',
                log.model or '',
                "ok" if log.success else (log.error_type or "échec"),
            )
