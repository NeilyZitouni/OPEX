from odoo import api, fields, models


class OpexClusterAssembly(models.Model):
    """Assemblée générale du cluster (section 40 de la spécification UX).

    `document_ids` réutilise la bibliothèque du cluster, comme les comités :
    l'ordre du jour et le compte rendu d'une AG sont des documents du cluster,
    pas une famille de pièces à part.
    """

    _name = 'opex.cluster.assembly'
    _description = "Assemblée générale"
    _order = 'date desc, id desc'

    name = fields.Char(
        string="Intitulé", compute='_compute_name', store=True, readonly=False)
    date = fields.Datetime(string="Date", required=True)
    agenda = fields.Text(string="Ordre du jour")
    document_ids = fields.Many2many('opex.cluster.document', string="Documents")
    # Participants effectifs de la séance : une simple liste de contacts, sans
    # état par ligne. C'est une forme de données différente de l'inscription
    # aux événements et formations (qui, elle, porte inscrit/présent) — les
    # fusionner n'aurait pas simplifié, seulement rendu l'inscription ambiguë.
    participant_ids = fields.Many2many('res.partner', string="Participants")
    decisions = fields.Text(string="Décisions")
    report = fields.Binary(string="Compte rendu", attachment=True)
    report_filename = fields.Char(string="Nom du compte rendu")
    vote_ids = fields.One2many('opex.cluster.vote', 'assembly_id', string="Votes")

    @api.depends('date')
    def _compute_name(self):
        for record in self:
            if not record.name:
                record.name = (
                    "Assemblée générale du %s" % record.date.strftime('%d/%m/%Y')
                    if record.date else "Assemblée générale"
                )
