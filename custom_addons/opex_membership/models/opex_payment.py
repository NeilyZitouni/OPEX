from odoo import fields, models


class OpexPayment(models.Model):
    _name = 'opex.payment'
    _description = 'Paiement'
    _order = 'date_paiement desc'

    subscription_id = fields.Many2one(
        'opex.subscription',
        string="Cotisation",
        required=True,
        ondelete='cascade',
    )
    currency_id = fields.Many2one(
        related='subscription_id.currency_id',
        string="Devise",
        store=True,
        readonly=True,
    )
    montant = fields.Monetary(string="Montant", required=True)
    date_paiement = fields.Datetime(string="Date de paiement", default=fields.Datetime.now)
    reference_transaction = fields.Char(string="Référence transaction")
    mode_paiement = fields.Selection(
        [
            ('card', 'Carte'),
            ('transfer', 'Virement'),
            ('cash', 'Espèces'),
        ],
        string="Mode de paiement",
        required=True,
        default='transfer',
    )
