from odoo import api, fields, models


class OpexMembershipDocument(models.Model):
    """Pièce du dossier d'adhésion (section E de la spécification UX).

    Remplace le `Many2many('ir.attachment')` brut du dossier : une pièce n'est
    pas qu'un fichier, elle a un *type*, et c'est ce type qui décide si elle est
    obligatoire. Sans lui, le Secrétariat ne peut pas dire « il manque le
    registre de commerce » — il ne voit qu'une liste de fichiers.
    """

    _name = 'opex.membership.document'
    _description = "Pièce du dossier d'adhésion"
    _order = 'membership_file_id, document_type, id'

    # Types obligatoires selon la section E. La spécification note que la liste
    # exacte reste « à confirmer » avec le règlement d'adhésion : elle est donc
    # centralisée ici plutôt que dispersée dans les contrôles du workflow.
    REQUIRED_TYPES = ('registre_commerce', 'statuts')

    name = fields.Char(string="Libellé", required=True)
    membership_file_id = fields.Many2one(
        'opex.membership.file',
        string="Dossier d'adhésion",
        required=True,
        ondelete='cascade',
        index=True,
    )
    document_type = fields.Selection(
        [
            ('registre_commerce', "Registre de commerce"),
            ('statuts', "Statuts de l'organisation"),
            ('presentation_entreprise', "Présentation de l'entreprise"),
            ('certification', "Certification"),
            ('autre', "Autre document"),
        ],
        string="Type de pièce",
        required=True,
        default='autre',
    )
    file = fields.Binary(string="Fichier", attachment=True, required=True)
    filename = fields.Char(string="Nom du fichier")
    is_required = fields.Boolean(
        string="Pièce obligatoire",
        compute='_compute_is_required',
        store=True,
        help="Dérivé du type de pièce : registre de commerce et statuts sont exigés.",
    )
    date_depot = fields.Datetime(string="Déposée le", default=fields.Datetime.now)

    @api.depends('document_type')
    def _compute_is_required(self):
        for record in self:
            record.is_required = record.document_type in self.REQUIRED_TYPES

    @api.model
    def _required_type_labels(self):
        """Libellés des pièces obligatoires, pour les messages d'erreur et les vues."""
        labels = dict(self._fields['document_type'].selection)
        return {key: labels[key] for key in self.REQUIRED_TYPES}
