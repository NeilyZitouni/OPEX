from odoo import fields, models


class OpexCrowdfundingClarification(models.Model):
    """Une question ciblée posée au porteur (section 6, issue « À clarifier »).

    « Poser 1..N questions ciblées » : le dossier n'est ni refusé ni accepté,
    il manque une information précise. Le porteur répond depuis son portail et
    le dossier repart en pré-analyse.
    """

    _name = 'opex.crowdfunding.clarification'
    _description = "Question de clarification"
    _order = 'id'
    _rec_name = 'question'

    project_id = fields.Many2one(
        'opex.crowdfunding.project', string="Projet",
        required=True, ondelete='cascade', index=True,
    )
    question = fields.Text(string="Question", required=True)
    reponse = fields.Text(string="Réponse du porteur")

    # `draft` : le comité rédige ses questions, le porteur ne les voit pas
    # encore. Elles ne partent qu'au moment où `action_clarify()` est appelée
    # — sans quoi une question à moitié écrite arriverait au porteur.
    state = fields.Selection([
        ('draft',    "En préparation"),
        ('asked',    "Posée"),
        ('answered', "Répondue"),
    ], string="État", default='draft', required=True)
