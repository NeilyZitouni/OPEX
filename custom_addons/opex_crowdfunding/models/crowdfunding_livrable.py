from odoo import _, fields, models
from odoo.exceptions import UserError


class OpexCrowdfundingLivrable(models.Model):
    """Un livrable de mission (section 11).

    C'est lui qui porte le « service fait » : un accompagnement n'est pas
    terminé parce que les dates sont passées, mais parce que les livrables
    attendus ont été remis et validés.
    """

    _name = 'opex.crowdfunding.livrable'
    _description = "Livrable de mission"
    _order = 'id'

    mission_id = fields.Many2one(
        'opex.crowdfunding.mission', string="Mission",
        required=True, ondelete='cascade', index=True,
    )
    name = fields.Char(string="Livrable", required=True)
    description = fields.Text(string="Description")
    fichier = fields.Binary(string="Fichier", attachment=True)
    fichier_filename = fields.Char(string="Nom du fichier")
    date_remise = fields.Datetime(string="Remis le", readonly=True)
    state = fields.Selection([
        ('attendu', "Attendu"),
        ('remis',   "Remis"),
        ('valide',  "Validé"),
        ('refuse',  "Refusé"),
    ], string="État", default='attendu', required=True)
    commentaire = fields.Text(string="Commentaire")

    def action_remettre(self):
        """L'expert remet son livrable."""
        for livrable in self:
            if livrable.state not in ('attendu', 'refuse'):
                raise UserError(_("Ce livrable a déjà été remis."))
            livrable.state = 'remis'
            livrable.date_remise = fields.Datetime.now()
        return True

    def action_valider(self):
        """Le comité constate que le livrable convient."""
        self.mission_id.project_id._ensure_ceo()
        for livrable in self:
            if livrable.state != 'remis':
                raise UserError(_(
                    "On ne valide qu'un livrable remis ; celui-ci ne l'est pas."))
            livrable.state = 'valide'
        return True

    def action_refuser(self):
        """Le comité renvoie le livrable à son auteur."""
        self.mission_id.project_id._ensure_ceo()
        for livrable in self:
            if livrable.state != 'remis':
                raise UserError(_(
                    "On ne refuse qu'un livrable remis ; celui-ci ne l'est pas."))
            if not (livrable.commentaire or '').strip():
                raise UserError(_(
                    "Dites pourquoi le livrable est refusé : l'expert doit "
                    "savoir quoi reprendre."))
            livrable.state = 'refuse'
        return True
