"""L'écran de configuration de l'assistance IA.

`res.config.settings` et non un modèle à nous : les champs déclarés avec
`config_parameter=` lisent et écrivent `ir.config_parameter` tout seuls. Un
modèle maison aurait dupliqué ce mécanisme, et surtout aurait créé une seconde
table où la clé se serait retrouvée stockée.

L'écran est réservé à `base.group_system`. C'est le groupe qui a déjà accès aux
paramètres système : quiconque peut lire `ir.config_parameter` peut de toute
façon lire la clé, et prétendre la protéger d'un administrateur serait une
illusion de sécurité.
"""

from odoo import _, api, fields, models


class AiSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    opex_ai_provider = fields.Selection(
        [('gemini', "Google Gemini")],
        string="Fournisseur d'IA",
        config_parameter='opex_ai.provider',
        default='gemini',
        help="Un second fournisseur est une méthode `_call_<nom>` de plus "
             "dans `opex.ai.service`, et une valeur de plus dans cette liste. "
             "Aucun appelant ne change.",
    )
    #: Le masquage est un attribut de **vue** (`password="True"` sur le
    #: `<field>`), pas un paramètre de champ : Odoo 19 refuse `password=True`
    #: ici et le signale par un avertissement au chargement.
    #:
    #: La clé reste de toute façon lisible par un administrateur dans les
    #: paramètres système. C'est inévitable, et c'est pourquoi l'écran est
    #: réservé à ce groupe : le masquage protège d'un regard par-dessus
    #: l'épaule, pas d'un administrateur.
    opex_ai_api_key = fields.Char(
        string="Clé API",
        config_parameter='opex_ai.api_key',
        help="Stockée dans `ir.config_parameter`, jamais dans le code ni dans "
             "un fichier de données versionné. Sans elle, le module "
             "fonctionne en saisie manuelle.",
    )
    opex_ai_model = fields.Char(
        string="Modèle",
        config_parameter='opex_ai.model',
        default='gemini-3.6-flash',
        help="Le nom exact attendu par l'API du fournisseur. Un modèle "
             "retiré répond 404 sans message explicite : le bouton de test "
             "sait reconnaître ce cas et le dire en clair. La liste des "
             "modèles servis par votre clé se demande à l'API.",
    )

    opex_ai_configured = fields.Boolean(
        string="Assistance IA active",
        compute='_compute_opex_ai_configured',
        help="Une clé est enregistrée. C'est cette question que posent les "
             "écrans avant d'afficher un bouton d'extraction.",
    )

    @api.depends('opex_ai_api_key')
    def _compute_opex_ai_configured(self):
        for settings in self:
            settings.opex_ai_configured = bool(
                (settings.opex_ai_api_key or '').strip())

    def action_opex_ai_test_connection(self):
        """Enregistre, puis fait un aller-retour réel.

        `set_values()` d'abord, et c'est délibéré : sans lui, le bouton
        testerait l'ancienne clé pendant que l'utilisateur regarde la
        nouvelle qu'il vient de taper. Un test qui ne teste pas ce qu'on voit
        à l'écran est pire qu'absent.

        Le résultat s'affiche en notification plutôt qu'en `UserError` : une
        erreur ferme le formulaire et fait perdre la saisie, alors qu'ici
        l'échec est une information, pas un incident.
        """
        self.ensure_one()
        self.set_values()

        ok, message = self.env['opex.ai.service']._test_connection()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Assistance IA") if ok else _("Connexion refusée"),
                'message': message,
                'type': 'success' if ok else 'warning',
                'sticky': not ok,
            },
        }

    def action_opex_ai_view_logs(self):
        self.ensure_one()
        return self.env['ir.actions.act_window']._for_xml_id(
            'opex_intervenants.action_ai_call_log')
