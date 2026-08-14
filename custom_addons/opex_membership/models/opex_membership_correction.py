from odoo import fields, models


class OpexMembershipCorrection(models.Model):
    """Demande de correction adressée au candidat (section 19 de la spécification UX).

    Le dossier repart en « Correction demandée » avec, tracé, *quel* document
    pose problème et *pourquoi* — le candidat doit pouvoir agir sans avoir à
    deviner. Le flux complet (formulaire staff, ré-upload, re-soumission) est
    l'objet de l'Extension 11 ; ce modèle en est le support de données.
    """

    _name = 'opex.membership.correction'
    _description = "Demande de correction"
    _order = 'date_demande desc, id desc'

    file_id = fields.Many2one(
        'opex.membership.file',
        string="Dossier d'adhésion",
        required=True,
        ondelete='cascade',
        index=True,
    )
    document_id = fields.Many2one(
        'opex.membership.document',
        string="Document concerné",
        ondelete='set null',
        help="Pièce à corriger ; vide si la correction porte sur les informations saisies.",
    )
    motif = fields.Char(string="Motif", required=True)
    commentaire = fields.Text(string="Commentaire")
    date_demande = fields.Datetime(string="Demandée le", default=fields.Datetime.now)
    resolved = fields.Boolean(
        string="Traitée",
        default=False,
        help="Passe à Vrai quand le candidat re-soumet son dossier corrigé.",
    )
