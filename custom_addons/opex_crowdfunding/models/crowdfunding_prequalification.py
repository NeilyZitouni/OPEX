from odoo import fields, models


class OpexCrowdfundingPrequalification(models.Model):
    """La pré-analyse d'un projet par le comité CEO (section 6).

    Une préqualification par passage en pré-analyse : un dossier revenu de
    clarification en reçoit une nouvelle, et l'historique des deux reste
    lisible côté CEO.
    """

    _name = 'opex.crowdfunding.prequalification'
    _description = "Pré-analyse d'un projet"
    _order = 'id desc'
    _rec_name = 'project_id'

    project_id = fields.Many2one(
        'opex.crowdfunding.project', string="Projet",
        required=True, ondelete='cascade', index=True,
    )
    # Table de liaison nommée à la main : concaténés, les deux noms de modèles
    # donnent `opex_crowdfunding_criteria_opex_crowdfunding_prequalification_rel`,
    # soit 64 caractères — un de trop pour PostgreSQL, et le registre refuse de
    # démarrer. Le symptôme n'a rien à voir avec la cause, d'où ce commentaire.
    criteria_ids = fields.Many2many(
        'opex.crowdfunding.criteria', string="Critères satisfaits",
        relation='opex_cf_prequalification_criteria_rel',
        column1='prequalification_id', column2='criteria_id',
        help="Les critères de validation préliminaire que le dossier remplit.",
    )
    commentaire = fields.Text(string="Commentaire")

    # Renseignés par les méthodes de transition, jamais à la main : l'issue
    # d'une pré-analyse est le résultat d'une décision tracée, pas d'une
    # saisie libre.
    resultat = fields.Selection([
        ('go',          "GO"),
        ('clarify',     "À clarifier"),
        ('no_go',       "NO GO"),
        ('orientation', "Orientation"),
    ], string="Résultat", readonly=True)
    evaluated_by_id = fields.Many2one('res.users', string="Évaluée par", readonly=True)
    date = fields.Datetime(string="Date", readonly=True)
