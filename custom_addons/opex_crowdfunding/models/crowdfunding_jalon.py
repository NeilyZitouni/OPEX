from odoo import fields, models


class OpexCrowdfundingJalon(models.Model):
    """Un jalon de mission (section 11).

    Le point de contrôle intermédiaire : ce qui doit être atteint, quand, et
    ce qu'on en constate. Sans jalons, une mission de trois mois ne se pilote
    qu'à son échéance.
    """

    _name = 'opex.crowdfunding.jalon'
    _description = "Jalon de mission"
    _order = 'date_prevue, id'

    mission_id = fields.Many2one(
        'opex.crowdfunding.mission', string="Mission",
        required=True, ondelete='cascade', index=True,
    )
    name = fields.Char(string="Jalon", required=True)
    date_prevue = fields.Date(string="Échéance")
    state = fields.Selection([
        ('prevu',   "Prévu"),
        ('atteint', "Atteint"),
        ('manque',  "Manqué"),
    ], string="État", default='prevu', required=True)
    commentaire = fields.Text(string="Commentaire")
