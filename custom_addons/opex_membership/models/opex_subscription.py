from odoo import _, fields, models
from odoo.exceptions import UserError


class OpexSubscription(models.Model):
    _name = 'opex.subscription'
    _description = 'Cotisation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_echeance desc'

    partner_id = fields.Many2one(
        'res.partner',
        string="Membre",
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string="Devise",
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    montant = fields.Monetary(string="Montant", required=True)
    date_emission = fields.Date(string="Date d'émission", default=fields.Date.context_today)
    date_echeance = fields.Date(string="Date d'échéance")
    state = fields.Selection(
        [
            ('waiting', 'En attente'),
            ('paid', 'Payée'),
            ('late', 'En retard'),
            ('cancelled', 'Annulée'),
        ],
        string="État",
        default='waiting',
        required=True,
        tracking=True,
    )
    payment_ids = fields.One2many('opex.payment', 'subscription_id', string="Paiements")
    membership_file_id = fields.Many2one(
        'opex.membership.file',
        string="Dossier d'adhésion",
        readonly=True,
        ondelete='set null',
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string="Devis/Commande de cotisation",
        readonly=True,
    )

    def write(self, vals):
        res = super().write(vals)
        if vals.get('state') == 'paid':
            self._trigger_membership_activation()
        return res

    def _trigger_membership_activation(self):
        """Une cotisation soldée active le dossier d'adhésion validé par le COPIL.

        Vaut quelle que soit l'origine du paiement : facture Odoo réglée
        (sale.order) ou paiement hors Odoo saisi via opex.payment.
        """
        for rec in self:
            membership_file = rec.membership_file_id
            if not membership_file:
                membership_file = self.env['opex.membership.file'].search([
                    ('partner_id', '=', rec.partner_id.id),
                    ('state', '=', 'validated'),
                ], limit=1)
            membership_file.filtered(
                lambda f: f.state == 'validated'
            )._activate_membership()

    def _state_label(self):
        self.ensure_one()
        return dict(self._fields['state'].selection).get(self.state)

    def action_generate_reminder(self):
        """genererRelances : envoie une relance si la cotisation est En retard."""
        for rec in self:
            if rec.state != 'late':
                raise UserError(_(
                    "Une relance ne peut être envoyée que pour une cotisation "
                    "En retard. La cotisation de %s est actuellement à l'état « %s »."
                ) % (rec.partner_id.name, rec._state_label()))
            rec.message_post(body=_(
                "Relance envoyée à %s pour la cotisation de %s (échéance : %s)."
            ) % (rec.partner_id.name, rec.montant, rec.date_echeance))

    def action_register_payment(self, montant=None, mode_paiement='transfer',
                                 reference_transaction=False, date_paiement=None):
        """enregistrerPaiement : crée un opex.payment lié, passe l'état à Payée si le montant couvre la cotisation."""
        for rec in self:
            if rec.state == 'cancelled':
                raise UserError(_(
                    "Impossible d'enregistrer un paiement : la cotisation de "
                    "%s est annulée."
                ) % rec.partner_id.name)
            if rec.state == 'paid':
                raise UserError(_(
                    "La cotisation de %s est déjà soldée."
                ) % rec.partner_id.name)
            amount = montant if montant is not None else (
                rec.montant - sum(rec.payment_ids.mapped('montant'))
            )
            if amount <= 0:
                raise UserError(_("Le montant du paiement doit être positif."))
            self.env['opex.payment'].create({
                'subscription_id': rec.id,
                'montant': amount,
                'date_paiement': date_paiement or fields.Datetime.now(),
                'reference_transaction': reference_transaction,
                'mode_paiement': mode_paiement,
            })
            total_paid = sum(rec.payment_ids.mapped('montant'))
            if total_paid >= rec.montant:
                rec.state = 'paid'
