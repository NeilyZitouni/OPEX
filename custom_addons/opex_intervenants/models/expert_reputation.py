"""La réputation du §32 et l'historique du §33.

Le §32 veut cinq indicateurs sur le profil : note, missions réalisées, missions
terminées, taux de satisfaction, respect des délais. Le premier existe depuis
l'Extension 3 - `reputation_score`, moyenne des `opex.expert.rating` - et se
remplit tout seul maintenant que l'Extension 10 crée ces lignes. Les quatre
autres sont ici.

« L'objectif est de construire un historique de réputation basé sur les
missions réellement réalisées. » C'est la phrase qui commande le calcul :
on compte des affectations, pas des candidatures.
"""

from odoo import api, fields, models

# Les étapes de la mission qui valent « réellement réalisée ». Une mission
# annulée ou infructueuse n'entre dans aucun compteur : elle n'a rien produit
# dont l'intervenant puisse se prévaloir, et l'y faire figurer gonflerait son
# volume sans rien dire de son travail.
PERFORMED_STAGES = ('in_progress', 'delivered', 'accepted', 'closed')
COMPLETED_STAGES = ('accepted', 'closed')

# Les étapes qui rangent une mission dans l'historique du §33.
HISTORY_LABELS = {
    'awarded': "À venir",
    'contracting': "À venir",
    'in_progress': "En cours",
    'delivered': "En cours",
    'accepted': "Terminée",
    'closed': "Terminée",
    'on_hold': "Suspendue",
    'cancelled': "Annulée",
}


class ExpertProfileReputation(models.Model):
    """Les quatre indicateurs du §32 que l'Extension 3 n'avait pas.

    Aucun n'est stocké, et c'est délibéré : ils dépendent de l'avancement des
    missions, qui change sans que le profil soit touché. Stockés, ils
    afficheraient le compte du jour où quelqu'un a ouvert la fiche.

    `reputation_score`, lui, reste stocké - il est trié et filtré par le
    matching, et il ne dépend que des notes reçues.
    """

    _inherit = 'opex.innovation.expert.profile'

    mission_realisee_count = fields.Integer(
        string="Missions réalisées", compute='_compute_reputation_facts')
    mission_terminee_count = fields.Integer(
        string="Missions terminées", compute='_compute_reputation_facts')
    satisfaction_rate = fields.Integer(
        string="Taux de satisfaction (%)", compute='_compute_reputation_facts',
        help="La note moyenne ramenée sur 100. Le §32 donne l'exemple : "
             "4,7 sur 5 s'y lit 94 %.")
    delay_compliance_rate = fields.Integer(
        string="Respect des délais (%)", compute='_compute_reputation_facts',
        help="Part des évaluations où le respect des délais a été noté 4 ou 5.")

    @api.depends('partner_id', 'expert_rating_ids.note',
                 'expert_rating_ids.respect_delais')
    def _compute_reputation_facts(self):
        for profile in self:
            assignments = profile._performed_assignments()
            profile.mission_realisee_count = len(assignments)
            profile.mission_terminee_count = len(assignments.filtered(
                lambda a: a.mission_id.workflow_stage_id.code
                in COMPLETED_STAGES))

            ratings = profile.expert_rating_ids
            profile.satisfaction_rate = round(
                profile.reputation_score / 5 * 100) if ratings else 0
            profile.delay_compliance_rate = round(
                len(ratings.filtered('respect_delais')) / len(ratings) * 100
            ) if ratings else 0

    def _performed_assignments(self):
        """Les affectations dont la mission a réellement démarré.

        `sudo()` : la réputation d'un intervenant se lit depuis son profil, y
        compris par quelqu'un qui n'a pas accès aux missions concernées. Ce
        sont les chiffres qui sortent, jamais les dossiers - c'est
        `mission_history()` qui décide de ce qui est montré.
        """
        self.ensure_one()
        if not self.partner_id:
            return self.env['opex.mission.assignment'].sudo().browse()
        return self.env['opex.mission.assignment'].sudo().search([
            ('partner_id', '=', self.partner_id.id),
            ('active', '=', True),
            ('mission_id.workflow_stage_id.code', 'in', PERFORMED_STAGES),
        ])

    def reputation_summary(self):
        """Les cinq indicateurs du §32, dans l'ordre du tableau."""
        self.ensure_one()
        return {
            'note': self.reputation_score,
            'missions_realisees': self.mission_realisee_count,
            'missions_terminees': self.mission_terminee_count,
            'satisfaction': self.satisfaction_rate,
            'respect_delais': self.delay_compliance_rate,
            'evaluations': self.rating_count,
        }

    def mission_history(self, public=True):
        """L'historique du §33, en deux versions.

        « Selon les droits, certaines informations peuvent être visibles
        publiquement et d'autres rester confidentielles. »

        Le filtre est ici, dans le dictionnaire, et pas dans le gabarit. La
        raison a été mesurée à l'Extension 5 par régression volontaire : un
        gabarit qui masque suffit à ce qu'aujourd'hui rien ne fuie, il
        n'empêche pas qu'un champ ajouté un mardi publie ce que le modèle a
        déjà laissé sortir.

        Les clés réservées sont donc absentes de la version publique, pas
        mises à False : un gabarit qui les afficherait lèverait au premier
        rendu, ce qui vaut mieux qu'une fuite silencieuse.
        """
        self.ensure_one()
        entries = []
        for assignment in self._performed_assignments().sorted(
                key=lambda a: (a.date_debut or fields.Date.today(), a.id),
                reverse=True):
            mission = assignment.mission_id
            entry = {
                'type': mission.mission_type_id.name or '',
                'domaine': mission.domaine_id.name or '',
                'annee': assignment.date_debut.year if assignment.date_debut
                         else False,
                'issue': HISTORY_LABELS.get(
                    mission.workflow_stage_id.code, "En cours"),
            }
            if not public:
                entry.update({
                    'reference': mission.name,
                    'titre': mission.title or '',
                    'client': mission.client_id.display_name or '',
                    'montant': assignment.montant_total,
                    'notes': self._history_notes(mission),
                })
            entries.append(entry)
        return entries

    def _history_notes(self, mission):
        """Les notes obtenues sur cette mission, si elles sont validées."""
        self.ensure_one()
        return [
            {'source': rating.source, 'note': rating.note}
            for rating in self.expert_rating_ids
            if rating.mission_id == mission
        ]

    def public_reputation(self):
        """Ce que l'annuaire peut afficher d'un intervenant.

        La note globale et les volumes sortent ; le détail des grilles, les
        commentaires et les clients ne sortent jamais par cette porte. Les
        commentaires d'évaluation ne figurent dans aucune des deux versions -
        `is_public` n'ouvre que la note.
        """
        self.ensure_one()
        return {
            'note': self.reputation_score,
            'evaluations_publiques': len(self._public_ratings()),
            'missions_terminees': self.mission_terminee_count,
            'satisfaction': self.satisfaction_rate,
            'historique': self.mission_history(public=True),
        }

    def _public_ratings(self):
        """Les notes que le cluster a rendues publiques - §33."""
        self.ensure_one()
        evaluations = self.env['opex.mission.evaluation'].sudo().search([
            ('expert_profile_id', '=', self.id),
            ('is_public', '=', True),
        ])
        return evaluations.mapped('rating_id')


class PartnerReputation(models.Model):
    """Les indicateurs du §32 portés jusqu'au partenaire.

    Même motif qu'à l'Extension 3 : le moteur de matching compare toujours un
    champ de `res.partner`, jamais un champ du profil. `expert_reputation` y
    est déjà ; les trois volumes le rejoignent pour qu'un critère puisse un
    jour exiger un minimum de missions terminées sans qu'on ait à toucher au
    moteur.
    """

    _inherit = 'res.partner'

    expert_missions_terminees = fields.Integer(
        string="Missions terminées", compute='_compute_partner_reputation')
    expert_satisfaction = fields.Integer(
        string="Taux de satisfaction (%)", compute='_compute_partner_reputation')
    expert_respect_delais = fields.Integer(
        string="Respect des délais (%)", compute='_compute_partner_reputation')

    @api.depends('expert_profile_id',
                 'expert_profile_id.reputation_score',
                 'expert_profile_id.expert_rating_ids.respect_delais')
    def _compute_partner_reputation(self):
        for partner in self:
            profile = partner.sudo().expert_profile_id
            partner.expert_missions_terminees = \
                profile.mission_terminee_count if profile else 0
            partner.expert_satisfaction = \
                profile.satisfaction_rate if profile else 0
            partner.expert_respect_delais = \
                profile.delay_compliance_rate if profile else 0
