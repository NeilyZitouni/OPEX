from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_member = fields.Boolean(string="Est membre du cluster")
    categorie_membre_id = fields.Many2one(
        'opex.membership.category',
        string="Catégorie de membre",
        ondelete='restrict',
    )
    secteur_activite = fields.Char(string="Secteur d'activité")
    wilaya = fields.Char(string="Wilaya")
    date_adhesion = fields.Date(string="Date d'adhésion")
    membership_file_ids = fields.One2many(
        'opex.membership.file', 'partner_id', string="Dossiers d'adhésion"
    )
    subscription_ids = fields.One2many(
        'opex.subscription', 'partner_id', string="Cotisations"
    )
    is_published_directory = fields.Boolean(string="Publié dans l'annuaire public")
    event_ids = fields.Many2many(
        'opex.cluster.event', 'event_partner_rel', 'partner_id', 'event_id',
        string="Événements",
    )

    def get_public_profile(self):
        """Champs exposables dans l'annuaire public des membres."""
        self.ensure_one()
        return {
            'name': self.name,
            'secteur_activite': self.secteur_activite,
            'wilaya': self.wilaya,
            'categorie_membre_id': self.categorie_membre_id.name if self.categorie_membre_id else False,
        }
