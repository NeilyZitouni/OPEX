from odoo import _, fields, models
from odoo.exceptions import UserError


class OpexCrowdfundingMission(models.Model):
    """La mission confiée à un expert (section 11).

    « Cela réutilise directement la logique déjà prévue dans le portail pour
    les experts : sélection, contractualisation, mission, suivi, validation et
    évaluation. » L'expert accepte ou décline — les deux boutons de la section
    16 — puis rend ses livrables aux jalons convenus.
    """

    _name = 'opex.crowdfunding.mission'
    _description = "Mission d'expert"
    _order = 'id'
    _rec_name = 'objectif'

    accompagnement_id = fields.Many2one(
        'opex.crowdfunding.accompagnement', string="Accompagnement",
        required=True, ondelete='cascade', index=True,
    )
    project_id = fields.Many2one(
        related='accompagnement_id.project_id', string="Projet", store=True)
    expert_id = fields.Many2one(
        'res.partner', string="Expert", required=True, ondelete='restrict',
        domain="[('cf_is_expert', '=', True)]",
    )
    objectif = fields.Text(string="Objectif de la mission", required=True)
    date_debut = fields.Date(string="Début")
    date_fin = fields.Date(string="Fin prévue")

    # La contrepartie de l'expert suit le même principe que celle du CEO : le
    # modèle économique reste en données.
    contrepartie_type_id = fields.Many2one(
        'opex.crowdfunding.compensation.type', string="Contrepartie",
        ondelete='restrict')
    contrepartie = fields.Text(string="Détail de la contrepartie")

    state = fields.Selection([
        ('proposee',  "Proposée"),
        ('acceptee',  "Acceptée"),
        ('declinee',  "Déclinée"),
        ('terminee',  "Terminée"),
    ], string="État", default='proposee', required=True)

    jalon_ids = fields.One2many(
        'opex.crowdfunding.jalon', 'mission_id', string="Jalons")
    livrable_ids = fields.One2many(
        'opex.crowdfunding.livrable', 'mission_id', string="Livrables")

    def _portal_payload(self):
        """Ce que l'expert voit de sa mission — et rien de plus.

        Même principe que la mise en relation : le gabarit ne reçoit pas
        l'enregistrement, seulement des valeurs choisies ici. Un expert
        mandaté sur un go-to-market n'a pas à lire le plan de financement du
        porteur.
        """
        self.ensure_one()
        return {
            'mission_id': self.id,
            'projet': self.project_id.name,
            'objectif': self.objectif or '',
            'date_debut': self.date_debut,
            'date_fin': self.date_fin,
            'contrepartie': self.contrepartie_type_id.name or '',
            'contrepartie_detail': self.contrepartie or '',
            'etat': self._label_state(),
            'a_repondre': self.state == 'proposee',
            'jalons': [
                {'libelle': jalon.name, 'echeance': jalon.date_prevue,
                 'etat': dict(jalon._fields['state']._description_selection(self.env))[jalon.state]}
                for jalon in self.jalon_ids
            ],
            'livrables': [
                {'libelle': livrable.name,
                 'etat': dict(livrable._fields['state']._description_selection(self.env))[livrable.state],
                 'commentaire': livrable.commentaire or ''}
                for livrable in self.livrable_ids
            ],
        }

    def _label_state(self):
        self.ensure_one()
        return dict(
            self._fields['state']._description_selection(self.env)
        )[self.state]

    def action_accept(self):
        """L'expert accepte la mission — bouton [Accepter] de la section 16."""
        for mission in self:
            mission._ensure_state('proposee')
            mission.state = 'acceptee'
        return True

    def action_decline(self):
        """L'expert décline — bouton [Décliner] de la section 16."""
        for mission in self:
            mission._ensure_state('proposee')
            mission.state = 'declinee'
        return True

    def action_terminate(self):
        """Mission terminée : tous les livrables attendus sont validés."""
        for mission in self:
            mission._ensure_state('acceptee')
            non_valides = mission.livrable_ids.filtered(lambda l: l.state != 'valide')
            if non_valides:
                raise UserError(_(
                    "%s livrable(s) de cette mission ne sont pas validés.",
                    len(non_valides)))
            mission.state = 'terminee'
        return True

    def _ensure_state(self, attendu):
        self.ensure_one()
        if self.state != attendu:
            raise UserError(_(
                "Cette mission est à l'état « %s » : l'action demandée ne s'y "
                "applique pas.",
                dict(self._fields['state']._description_selection(self.env))[self.state]))
