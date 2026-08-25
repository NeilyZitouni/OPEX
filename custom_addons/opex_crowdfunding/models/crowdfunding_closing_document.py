from odoo import _, fields, models
from odoo.exceptions import UserError


class OpexCrowdfundingClosingDocument(models.Model):
    """Une pièce du dossier de closing (section 15).

    Convention, pacte, échéancier : ce que la nature de l'opération exige.
    Une pièce déposée n'est pas une pièce validée — c'est le comité qui la
    valide, et la signature attend que toutes le soient.
    """

    _name = 'opex.crowdfunding.closing.document'
    _description = "Document de closing"
    _order = 'id'

    closing_id = fields.Many2one(
        'opex.crowdfunding.closing', string="Closing",
        required=True, ondelete='cascade', index=True,
    )
    name = fields.Char(string="Document", required=True)
    fichier = fields.Binary(string="Fichier", attachment=True)
    fichier_filename = fields.Char(string="Nom du fichier")
    valide = fields.Boolean(string="Validé", readonly=True)
    date_validation = fields.Datetime(string="Validé le", readonly=True)
    commentaire = fields.Text(string="Commentaire")

    def action_valider(self):
        self.closing_id.project_id._ensure_ceo()
        for document in self:
            if not document.fichier:
                raise UserError(_(
                    "Déposez le fichier de « %s » avant de le valider.",
                    document.name))
            document.valide = True
            document.date_validation = fields.Datetime.now()
        return True
