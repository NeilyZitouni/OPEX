from datetime import timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError


class OpexMembershipFile(models.Model):
    _name = 'opex.membership.file'
    _description = "Dossier d'adhésion"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_depot desc'

    partner_id = fields.Many2one(
        'res.partner',
        string="Membre",
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    category_id = fields.Many2one(
        'opex.membership.category',
        string="Catégorie demandée",
        tracking=True,
        help="Catégorie d'adhésion souhaitée ; détermine le montant de la cotisation. "
             "À défaut, celle du contact est utilisée.",
    )
    date_depot = fields.Datetime(string="Date de dépôt", default=fields.Datetime.now)
    document_ids = fields.Many2many('ir.attachment', string="Documents joints")
    subscription_ids = fields.One2many(
        'opex.subscription', 'membership_file_id', string="Cotisations"
    )
    signature_date = fields.Date(string="Date de signature de la charte")
    state = fields.Selection(
        [
            ('draft', 'Brouillon'),
            ('control', 'En contrôle'),
            ('committee', 'En comité'),
            ('validated', 'Validé COPIL'),
            ('active', 'Actif'),
        ],
        string="État",
        default='draft',
        required=True,
        tracking=True,
    )

    def _state_label(self):
        self.ensure_one()
        return dict(self._fields['state'].selection).get(self.state)

    def action_submit(self):
        """soumettreDossier : Brouillon -> En contrôle."""
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_(
                    "Seul un dossier à l'état Brouillon peut être soumis. "
                    "Ce dossier est actuellement à l'état « %s »."
                ) % rec._state_label())
            rec.state = 'control'

    def action_validate_secretariat(self):
        """validerParSecretariat : En contrôle -> En comité, uniquement si le dossier est complet."""
        for rec in self:
            if rec.state != 'control':
                raise UserError(_(
                    "Seul un dossier En contrôle peut être validé par le secrétariat. "
                    "Ce dossier est actuellement à l'état « %s »."
                ) % rec._state_label())
            if not rec.document_ids:
                raise UserError(_(
                    "Le dossier de %s est incomplet : aucun document n'est joint. "
                    "Il ne peut pas être transmis au comité d'admission tant que "
                    "le dossier n'est pas complet."
                ) % rec.partner_id.name)
            rec.state = 'committee'

    def action_validate_copil(self):
        """validerParCOPIL : En comité -> Validé COPIL, puis chaîne le workflow système."""
        for rec in self:
            if rec.state != 'committee':
                raise UserError(_(
                    "Seul un dossier En comité peut être validé par le COPIL. "
                    "Ce dossier est actuellement à l'état « %s »."
                ) % rec._state_label())
            rec.state = 'validated'
            rec.action_create_subscription()

    def _get_category(self):
        """Catégorie facturée : celle demandée sur le dossier, sinon celle du contact."""
        self.ensure_one()
        return self.category_id or self.partner_id.categorie_membre_id

    def action_create_subscription(self):
        """Émet la cotisation via la facturation native Odoo (sale.order).

        Le dossier reste à l'état Validé COPIL : c'est l'encaissement effectif de
        la commande qui déclenchera l'activation (cf. `_activate_membership`).
        """
        self.ensure_one()
        partner = self.partner_id
        category = self._get_category()
        if not category:
            raise UserError(_(
                "Impossible de générer la cotisation : %s n'a pas de catégorie "
                "de membre définie (avec un montant de cotisation associé)."
            ) % partner.name)

        product = category._get_cotisation_product()
        order = self.env['sale.order'].sudo().create({
            'partner_id': partner.id,
            'order_line': [fields.Command.create({
                'product_id': product.id,
                'product_uom_qty': 1,
            })],
        })

        today = fields.Date.context_today(self)
        subscription = self.env['opex.subscription'].create({
            'partner_id': partner.id,
            'membership_file_id': self.id,
            'sale_order_id': order.id,
            'currency_id': category.currency_id.id,
            'montant': product.list_price,
            'date_emission': today,
            'date_echeance': today + timedelta(days=30),
        })
        order.action_confirm()
        return subscription

    def _activate_membership(self):
        """Signature de la charte -> activation -> publication annuaire.

        Appelé automatiquement quand la cotisation liée passe à l'état Payée.
        """
        for rec in self:
            rec.write({
                'signature_date': fields.Date.context_today(rec),
                'state': 'active',
            })
            rec.partner_id.write({
                'is_member': True,
                'is_published_directory': True,
            })
