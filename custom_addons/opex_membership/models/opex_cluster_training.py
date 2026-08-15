from odoo import _, api, fields, models
from odoo.exceptions import UserError


class OpexClusterTraining(models.Model):
    """Formation proposée par le cluster (section 36 de la spécification UX)."""

    _name = 'opex.cluster.training'
    _description = "Formation du cluster"
    _order = 'date desc, id desc'

    name = fields.Char(string="Intitulé", required=True)
    date = fields.Datetime(string="Date")
    duration = fields.Float(string="Durée (heures)")
    seats_total = fields.Integer(string="Places totales")
    seats_available = fields.Integer(
        string="Places disponibles",
        compute='_compute_seats_available',
        help="Places restantes = places totales moins les inscriptions enregistrées.",
    )
    registration_ids = fields.One2many(
        'opex.cluster.event.registration', 'training_id', string="Inscriptions")

    @api.depends('seats_total', 'registration_ids')
    def _compute_seats_available(self):
        """Jamais négatif : une formation complète affiche zéro, pas un déficit."""
        for record in self:
            record.seats_available = max(
                0, record.seats_total - len(record.registration_ids))

    def action_register(self, partner):
        """Inscrit un participant, si la formation n'est pas complète.

        Le contrôle des places vit ici, pas dans le controller : c'est une règle
        de la formation, et le bouton désactivé côté portail n'est qu'un confort
        d'affichage — une requête forgée retombe sur cette vérification.
        """
        self.ensure_one()
        Registration = self.env['opex.cluster.event.registration']
        existing = Registration._existing_registration(partner, training=self)
        if existing:
            return existing
        if self.seats_available <= 0:
            raise UserError(_(
                "La formation « %s » est complète : il n'y a plus de place "
                "disponible."
            ) % self.name)
        return Registration._register_participant(partner, training=self)
