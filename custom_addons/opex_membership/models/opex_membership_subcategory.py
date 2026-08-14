from odoo import _, api, fields, models


class OpexMembershipSubcategory(models.Model):
    """Sous-catégorie d'adhésion (PME/PMI, Université, Banque, Cabinet...).

    C'est elle, et non la catégorie, qui porte désormais le barème : la
    spécification UX (section 3) impose une structure Catégorie → Sous-catégorie
    entièrement paramétrable, pour que le GIC puisse ajouter une sous-catégorie
    sans toucher au code.
    """

    _name = 'opex.membership.subcategory'
    _description = "Sous-catégorie d'adhésion"
    _order = 'category_id, sequence, name'

    name = fields.Char(
        string="Nom",
        required=True,
        help="PME / PMI, Université, Incubateur, Banque, Expert ACEO...",
    )
    sequence = fields.Integer(string="Séquence", default=10)
    category_id = fields.Many2one(
        'opex.membership.category',
        string="Catégorie",
        required=True,
        ondelete='cascade',
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
        help="Barème annuel appliqué aux dossiers de cette sous-catégorie.",
    )
    critere_eligibilite = fields.Char(
        string="Critère d'éligibilité",
        help="Condition d'appartenance à la sous-catégorie, ex. « 50 à 2000 salariés ».",
    )

    @api.depends('name', 'category_id.name')
    def _compute_display_name(self):
        """« Membres adhérents / PME – PMI » : la sous-catégorie seule est ambiguë.

        Les listes déroulantes du portail et les pages staff n'affichent qu'un
        seul champ ; y faire figurer la catégorie évite d'avoir à la porter
        séparément partout.
        """
        for record in self:
            if record.category_id:
                record.display_name = "%s / %s" % (record.category_id.name, record.name)
            else:
                record.display_name = record.name

    def _cotisation_product_name(self):
        self.ensure_one()
        return _("Cotisation — %s") % self.name

    def _get_cotisation_product(self):
        """Cherche ou crée le product.product de service facturant cette sous-catégorie.

        Le produit est nommé d'après la sous-catégorie ("Cotisation — PME / PMI")
        et son prix est resynchronisé sur `montant_cotisation` à chaque appel,
        afin qu'une modification du barème se répercute sur les prochaines
        cotisations.
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
            # égal au montant de cotisation paramétré sur la sous-catégorie.
            'taxes_id': [fields.Command.clear()],
        })
