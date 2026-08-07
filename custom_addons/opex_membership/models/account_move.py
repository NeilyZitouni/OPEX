from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _invoice_paid_hook(self):
        """Solde automatiquement la cotisation quand sa facture est encaissée.

        Odoo appelle ce hook au lettrage de la facture (ou à sa validation si le
        montant est nul). On remonte facture -> ligne de commande -> sale.order
        pour retrouver l'`opex.subscription` correspondante.
        """
        res = super()._invoice_paid_hook()
        orders = self.filtered(lambda m: m.is_invoice()) \
            .invoice_line_ids.sale_line_ids.order_id
        if orders:
            subscriptions = self.env['opex.subscription'].sudo().search([
                ('sale_order_id', 'in', orders.ids),
                ('state', 'in', ('waiting', 'late')),
            ])
            subscriptions.write({'state': 'paid'})
        return res
