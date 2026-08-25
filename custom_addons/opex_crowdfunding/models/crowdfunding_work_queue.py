from datetime import timedelta

from odoo import _, api, fields, models

#: Au-delà de ce délai, une demande d'accompagnement que personne n'a prise en
#: main est considérée comme en retard. Le document ne fixe pas de SLA : c'est
#: une convention du module, écrite ici et nulle part ailleurs.
DELAI_PRISE_EN_CHARGE = 14


class OpexCrowdfundingWorkQueue(models.TransientModel):
    """La SMART WORK QUEUE du comité CEO (section 16).

    « Ne pas demander à l'utilisateur de piloter le workflow. Le workflow doit
    guider l'utilisateur. » Le comité n'ouvre pas la liste des projets pour y
    chercher ce qui l'attend : la file lui dit combien de dossiers attendent
    quoi, et chaque compteur ouvre la liste filtrée correspondante.

    Modèle transitoire : rien n'est stocké, tout est compté à l'ouverture.
    """

    _name = 'opex.crowdfunding.work.queue'
    _description = "Smart Work Queue du comité CEO"

    prequalifications = fields.Integer(
        string="Préqualifications", compute='_compute_queue')
    controles_anomalie = fields.Integer(
        string="Contrôles en anomalie", compute='_compute_queue')
    decisions_ceo = fields.Integer(
        string="Décisions CEO", compute='_compute_queue')
    matchings_a_valider = fields.Integer(
        string="Matchings à valider", compute='_compute_queue')
    investisseurs_en_attente = fields.Integer(
        string="Investisseurs en attente", compute='_compute_queue')
    accompagnements_en_retard = fields.Integer(
        string="Accompagnements en retard", compute='_compute_queue')

    # ------------------------------------------------------------------
    # Les six domaines, définis une fois, utilisés pour compter et pour ouvrir
    # ------------------------------------------------------------------
    # Un compteur qui ne mène pas exactement à ce qu'il a compté est pire
    # qu'inutile : le comité perdrait confiance à la première ligne manquante.
    # D'où une seule définition par file.

    def _domaine_prequalifications(self):
        """Les dossiers déposés qui attendent la qualification du comité."""
        return [('state', 'in', ('depot_express', 'pre_analyse'))]

    def _domaine_controles_anomalie(self):
        """Les dossiers bloqués au Quality Gate sur une alerte."""
        return [
            ('state', '=', 'quality_gate'),
            ('quality_control_ids.avis', 'in', ('alerte', 'non_conforme')),
        ]

    def _domaine_decisions_ceo(self):
        return [('state', '=', 'etude_decision')]

    def _domaine_matchings_a_valider(self):
        return [('state', '=', 'matching_financier')]

    def _domaine_investisseurs_en_attente(self):
        """Les acteurs qui ont bougé et attendent une réponse.

        Deux cas : celui qui a exprimé son intérêt sans que le porteur ait
        autorisé le partage, et celui qui a posé une question ou proposé un
        rendez-vous.
        """
        return [
            '|',
            '&', ('interet_exprime', '=', True), ('niveau_acces', '=', 'teaser'),
            ('decision', 'in', ('informations', 'rendez_vous')),
        ]

    def _domaine_accompagnements_en_retard(self):
        """Deux retards distincts, réunis dans une seule file.

        Un accompagnement demandé que personne n'a pris en main depuis deux
        semaines, et un accompagnement actif dont une mission a dépassé son
        échéance sans être terminée.
        """
        limite = fields.Datetime.now() - timedelta(days=DELAI_PRISE_EN_CHARGE)
        return [
            '|',
            '&', ('state', '=', 'demande'), ('create_date', '<', limite),
            '&', ('state', '=', 'actif'),
            '&', ('mission_ids.state', '=', 'acceptee'),
            ('mission_ids.date_fin', '<', fields.Date.context_today(self)),
        ]

    @api.depends_context('uid')
    def _compute_queue(self):
        Project = self.env['opex.crowdfunding.project']
        Relation = self.env['opex.crowdfunding.relation']
        Accompagnement = self.env['opex.crowdfunding.accompagnement']
        for queue in self:
            queue.prequalifications = Project.search_count(
                queue._domaine_prequalifications())
            queue.controles_anomalie = Project.search_count(
                queue._domaine_controles_anomalie())
            queue.decisions_ceo = Project.search_count(
                queue._domaine_decisions_ceo())
            queue.matchings_a_valider = Project.search_count(
                queue._domaine_matchings_a_valider())
            queue.investisseurs_en_attente = Relation.search_count(
                queue._domaine_investisseurs_en_attente())
            queue.accompagnements_en_retard = Accompagnement.search_count(
                queue._domaine_accompagnements_en_retard())

    # ------------------------------------------------------------------
    # Chaque compteur ouvre la liste qu'il a comptée
    # ------------------------------------------------------------------
    def _ouvrir(self, nom, modele, domaine):
        return {
            'type': 'ir.actions.act_window',
            'name': nom,
            'res_model': modele,
            'view_mode': 'list,form',
            'domain': domaine,
            'context': {'create': False},
        }

    def action_open_prequalifications(self):
        return self._ouvrir(_("Préqualifications"),
                            'opex.crowdfunding.project',
                            self._domaine_prequalifications())

    def action_open_controles_anomalie(self):
        return self._ouvrir(_("Contrôles en anomalie"),
                            'opex.crowdfunding.project',
                            self._domaine_controles_anomalie())

    def action_open_decisions_ceo(self):
        return self._ouvrir(_("Décisions CEO"),
                            'opex.crowdfunding.project',
                            self._domaine_decisions_ceo())

    def action_open_matchings_a_valider(self):
        return self._ouvrir(_("Matchings à valider"),
                            'opex.crowdfunding.project',
                            self._domaine_matchings_a_valider())

    def action_open_investisseurs_en_attente(self):
        return self._ouvrir(_("Investisseurs en attente"),
                            'opex.crowdfunding.relation',
                            self._domaine_investisseurs_en_attente())

    def action_open_accompagnements_en_retard(self):
        return self._ouvrir(_("Accompagnements en retard"),
                            'opex.crowdfunding.accompagnement',
                            self._domaine_accompagnements_en_retard())
