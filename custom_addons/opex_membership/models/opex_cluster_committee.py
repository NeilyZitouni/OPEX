from odoo import fields, models


class OpexClusterCommittee(models.Model):
    """Comité du cluster (section 39 de la spécification UX).

    Deux réutilisations plutôt que deux modèles de plus :

    - `meeting_ids` pointe vers `opex.cluster.event`, qui porte déjà le type
      « Réunion » et sa synchronisation avec l'agenda natif (Extension 2). Une
      réunion de comité est un événement du cluster ; un modèle
      `opex.cluster.meeting` distinct aurait dupliqué la même forme de données
      et perdu le miroir agenda au passage.
    - `document_ids` pointe vers la bibliothèque `opex.cluster.document`, comme
      pour les assemblées : un document reste un document.
    """

    _name = 'opex.cluster.committee'
    _description = "Comité du cluster"
    _order = 'name'

    name = fields.Char(string="Nom", required=True)
    description = fields.Text(string="Mission")
    member_ids = fields.Many2many('res.partner', string="Membres")
    document_ids = fields.Many2many('opex.cluster.document', string="Documents")
    meeting_ids = fields.Many2many(
        'opex.cluster.event',
        'cluster_committee_event_rel', 'committee_id', 'event_id',
        string="Réunions",
        domain="[('type', '=', 'meeting')]",
    )
