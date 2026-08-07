from odoo import _, fields, models


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

    def _cotisation_product_name(self):
        self.ensure_one()
        return _("Cotisation — %s") % self.name

    def _get_cotisation_product(self):
        """Cherche ou crée le product.product de service facturant cette catégorie.

        Le produit est nommé d'après la catégorie ("Cotisation — Adhérent") et son
        prix est resynchronisé sur `montant_cotisation` à chaque appel, afin qu'une
        modification du barème se répercute sur les prochaines cotisations.
        """
        self.ensure_one()
        name = self._cotisation_product_name()
        product = self.env['product.product'].sudo().search(
            [('name', '=', name), ('type', '=', 'service')], limit=1
        )
        if product:
            if product.list_price != self.montant_cotisation:
                product.list_price = self.montant_cotisation
            return product
        return self.env['product.product'].sudo().create({
            'name': name,
            'type': 'service',
            'invoice_policy': 'order',
            'list_price': self.montant_cotisation,
            'sale_ok': True,
            'purchase_ok': False,
            # Pas de taxe sur la cotisation : le total de la commande doit rester
            # égal au montant de cotisation paramétré sur la catégorie.
            'taxes_id': [fields.Command.clear()],
        })
