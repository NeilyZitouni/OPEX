from odoo import api, fields, models


class OpexClusterGroup(models.Model):
    """Forum ou groupe de travail du cluster (section 38 de la spécification UX)."""

    _name = 'opex.cluster.group'
    _description = "Forum / groupe du cluster"
    _order = 'name'

    name = fields.Char(string="Nom", required=True)
    description = fields.Text(string="Description")
    member_ids = fields.Many2many('res.partner', string="Membres")
    member_count = fields.Integer(
        string="Nombre de membres", compute='_compute_member_count')

    @api.depends('member_ids')
    def _compute_member_count(self):
        for record in self:
            record.member_count = len(record.member_ids)
