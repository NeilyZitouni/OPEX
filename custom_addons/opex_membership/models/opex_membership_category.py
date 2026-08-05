from odoo import fields, models


class OpexMembershipCategory(models.Model):
    _name = 'opex.membership.category'
    _description = "Catégorie d'adhésion"
    _order = 'name'

    name = fields.Char(
        string="Nom",
        required=True,
        help="Adhérent, Associé, Partenaire/Sponsor, Expert...",
    )
    currency_id = fields.Many2one(
        'res.currency',
        string="Devise",
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    montant_cotisation = fields.Monetary(
        string="Montant de la cotisation",
        currency_field='currency_id',
    )
    droits_acces = fields.Text(string="Droits d'accès")
