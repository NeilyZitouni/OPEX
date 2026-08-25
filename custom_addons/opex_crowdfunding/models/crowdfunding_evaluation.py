from odoo import api, fields, models
from odoo.exceptions import ValidationError


class OpexCrowdfundingEvaluation(models.Model):
    """L'évaluation qui clôt l'accompagnement (section 11).

    Dernière étape du sous-processus, après le service fait. Elle porte sur
    l'accompagnement, et peut viser une mission en particulier quand plusieurs
    experts sont intervenus.
    """

    _name = 'opex.crowdfunding.evaluation'
    _description = "Évaluation d'un accompagnement"
    _order = 'id desc'
    _rec_name = 'accompagnement_id'

    accompagnement_id = fields.Many2one(
        'opex.crowdfunding.accompagnement', string="Accompagnement",
        required=True, ondelete='cascade', index=True,
    )
    mission_id = fields.Many2one(
        'opex.crowdfunding.mission', string="Mission évaluée",
        ondelete='set null',
        help="Facultatif : laisser vide pour évaluer l'accompagnement dans son ensemble.",
    )
    note = fields.Integer(string="Note", help="Sur 5.")
    commentaire = fields.Text(string="Commentaire")
    evaluated_by_id = fields.Many2one(
        'res.users', string="Évaluée par", default=lambda self: self.env.user)
    date = fields.Datetime(string="Date", default=fields.Datetime.now)

    @api.constrains('note')
    def _check_note(self):
        for evaluation in self:
            if not 0 <= evaluation.note <= 5:
                raise ValidationError(
                    "La note d'une évaluation va de 0 à 5.")
