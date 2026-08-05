from odoo import fields, models


class OpexClusterEvent(models.Model):
    _name = 'opex.cluster.event'
    _description = 'Événement du cluster'
    _order = 'date_debut desc'

    name = fields.Char(string="Titre", required=True)
    date_debut = fields.Datetime(string="Date de début", required=True)
    date_fin = fields.Datetime(string="Date de fin")
    lieu = fields.Char(string="Lieu")
    type = fields.Selection(
        [
            ('training', 'Formation'),
            ('general_assembly', 'Assemblée générale'),
            ('forum', 'Forum'),
            ('meeting', 'Réunion'),
        ],
        string="Type",
        required=True,
    )
    partner_ids = fields.Many2many(
        'res.partner', 'event_partner_rel', 'event_id', 'partner_id',
        string="Participants",
    )
