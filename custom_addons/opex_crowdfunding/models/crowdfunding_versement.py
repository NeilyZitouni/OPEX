from odoo import _, fields, models
from odoo.exceptions import UserError


class OpexCrowdfundingVersement(models.Model):
    """Une tranche de versement (section 15).

    Hors périmètre assumé : aucun mouvement bancaire réel n'est déclenché. Ce
    modèle enregistre l'échéancier convenu et ce qui a effectivement été versé
    — c'est ce qui fait du dossier un projet suivi.
    """

    _name = 'opex.crowdfunding.versement'
    _description = "Versement d'un financement"
    _order = 'date_prevue, id'

    closing_id = fields.Many2one(
        'opex.crowdfunding.closing', string="Closing",
        required=True, ondelete='cascade', index=True,
    )
    name = fields.Char(string="Tranche", required=True)
    montant = fields.Monetary(string="Montant", currency_field='currency_id')
    currency_id = fields.Many2one(
        related='closing_id.currency_id', string="Devise", readonly=True)
    date_prevue = fields.Date(string="Échéance prévue")
    date_versement = fields.Date(string="Versé le", readonly=True)
    state = fields.Selection([
        ('prevu', "Prévu"),
        ('verse', "Versé"),
        ('annule', "Annulé"),
    ], string="État", default='prevu', required=True)

    def action_constater_versement(self):
        """Le comité constate qu'une tranche a été versée."""
        self.closing_id.project_id._ensure_ceo()
        for versement in self:
            if versement.state != 'prevu':
                raise UserError(_("Cette tranche n'est plus en attente."))
            versement.state = 'verse'
            versement.date_versement = fields.Date.context_today(versement)
        return True

    def _label_state(self):
        self.ensure_one()
        return dict(
            self._fields['state']._description_selection(self.env)
        )[self.state]
