from odoo import fields, models


class OpexCrowdfundingSuivi(models.Model):
    """Une entrée du suivi post-financement (section 15).

    « Le dossier devient alors un projet suivi plutôt qu'une simple
    candidature » : sans journal, la phrase ne serait qu'une intention. Un
    point d'étape, une remontée de reporting, une alerte — datés, et lisibles
    par le porteur.
    """

    _name = 'opex.crowdfunding.suivi'
    _description = "Suivi post-financement"
    _order = 'date desc, id desc'

    closing_id = fields.Many2one(
        'opex.crowdfunding.closing', string="Closing",
        required=True, ondelete='cascade', index=True,
    )
    date = fields.Date(string="Date", required=True,
                       default=fields.Date.context_today)
    name = fields.Char(string="Point de suivi", required=True)
    commentaire = fields.Text(string="Commentaire")
    auteur_id = fields.Many2one(
        'res.users', string="Saisi par", default=lambda self: self.env.user)
