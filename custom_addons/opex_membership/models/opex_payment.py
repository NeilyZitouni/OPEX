from odoo import _, api, fields, models
from odoo.exceptions import UserError


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
    # `paid` par défaut : un paiement saisi par le Secrétariat constate un
    # encaissement déjà vérifié. Seule la preuve déposée par le candidat naît
    # « à vérifier », et c'est `create()` qui l'impose — pas le formulaire.
    state = fields.Selection(
        [
            ('to_verify', 'À vérifier'),
            ('paid', 'Confirmé'),
            ('rejected', 'Rejeté'),
        ],
        string="État",
        default='paid',
        required=True,
    )
    justificatif = fields.Binary(string="Justificatif", attachment=True)
    justificatif_filename = fields.Char(string="Nom du justificatif")
    motif_rejet = fields.Char(string="Motif du rejet")
    date_verification = fields.Datetime(string="Vérifié le", readonly=True)

    def _state_label(self):
        self.ensure_one()
        return dict(self._fields['state'].selection).get(self.state)

    @api.model_create_multi
    def create(self, vals_list):
        """Une preuve déposée par un candidat naît toujours « à vérifier ».

        Le formulaire du portail est rempli côté navigateur : laisser passer un
        `state` venu de là permettrait à un candidat de déclarer sa cotisation
        soldée sans que personne ne contrôle son justificatif.
        """
        if self.env.user._is_portal():
            for vals in vals_list:
                vals['state'] = 'to_verify'
                vals['motif_rejet'] = False
        return super().create(vals_list)

    def action_confirm(self):
        """Le Secrétariat valide la preuve de paiement.

        Le passage du dossier à la signature n'est pas déclenché ici : solder
        la cotisation suffit, `opex.subscription.write()` s'en charge déjà pour
        tous les modes de règlement (cf. `_trigger_membership_activation`).
        """
        for rec in self:
            if rec.state != 'to_verify':
                raise UserError(_(
                    "Seule une preuve de paiement à vérifier peut être "
                    "confirmée. Ce paiement est « %s »."
                ) % rec._state_label())
            rec.write({
                'state': 'paid',
                'motif_rejet': False,
                'date_verification': fields.Datetime.now(),
            })
            rec.subscription_id._reconcile_payments()

    def action_reject(self, motif):
        """Le Secrétariat rejette la preuve : le dossier retourne en attente de paiement."""
        self.ensure_one()
        if self.state != 'to_verify':
            raise UserError(_(
                "Seule une preuve de paiement à vérifier peut être rejetée. "
                "Ce paiement est « %s »."
            ) % self._state_label())
        if not (motif or '').strip():
            raise UserError(_(
                "Indiquez le motif du rejet : c'est ce texte que le candidat "
                "recevra pour corriger sa preuve."
            ))
        self.write({
            'state': 'rejected',
            'motif_rejet': motif.strip(),
            'date_verification': fields.Datetime.now(),
        })
        self.subscription_id.membership_file_id.action_reject_payment(motif=self.motif_rejet)
