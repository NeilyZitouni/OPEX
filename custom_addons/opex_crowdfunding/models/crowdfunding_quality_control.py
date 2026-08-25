from odoo import api, fields, models


class OpexCrowdfundingQualityControl(models.Model):
    """Le contrôle qualité d'un dossier — le Quality Gate de la section 8.

    Le document annonce une trajectoire :

        Contrôle humain → Contrôle assisté par IA → Agent IA autonome
        sous supervision CEO

    et pose la contrainte : « le remplacement futur du contrôleur par un agent
    IA ne doit nécessiter aucune modification du workflow métier ; seul le type
    d'acteur exécutant l'activité change. »

    Ce modèle est donc écrit pour être rempli indifféremment par une personne
    ou par un programme :

    * les six vérifications sont des données, pas des jugements en dur ;
    * `_avis_suggere()` isole la logique de contrôle en un seul endroit — c'est
      la méthode qu'un agent remplacerait, et elle ne connaît rien du workflow ;
    * `controlled_by_id` est un `res.users` quelconque : un agent IA serait un
      utilisateur technique du groupe Contrôle Qualité, et rien d'autre ne
      bougerait.

    Aucune transition du projet ne regarde *qui* a rempli ce contrôle.
    """

    _name = 'opex.crowdfunding.quality.control'
    _description = "Contrôle qualité d'un dossier"
    _order = 'id desc'
    _rec_name = 'project_id'

    project_id = fields.Many2one(
        'opex.crowdfunding.project', string="Projet",
        required=True, ondelete='cascade', index=True,
    )

    # ------------------------------------------------------------------
    # Les six vérifications de la section 8
    # ------------------------------------------------------------------
    completude = fields.Boolean(string="Dossier complet")
    coherence = fields.Boolean(string="Informations cohérentes")
    qualite_informations = fields.Boolean(string="Qualité des informations suffisante")
    conformite_criteres = fields.Boolean(string="Conforme aux critères")
    justificatifs = fields.Boolean(string="Justificatifs présents")
    anomalies = fields.Text(
        string="Anomalies relevées",
        help="Ce que le porteur doit corriger, ou ce que le comité doit savoir. "
             "Exigé dès que l'avis n'est pas « Conforme ».",
    )

    # ------------------------------------------------------------------
    # L'avis
    # ------------------------------------------------------------------
    # Quatre valeurs, mais trois branches : « Alerte » et « Non conforme »
    # remontent toutes deux au comité CEO sans faire bouger le dossier.
    # L'infographie les réunit d'ailleurs dans une seule sortie rouge. Le
    # contrôle qualité n'écarte jamais un projet de lui-même : « la décision
    # métier finale reste portée par le workflow et les acteurs autorisés ».
    avis = fields.Selection([
        ('ok',           "Conforme"),
        ('a_completer',  "À compléter"),
        ('alerte',       "Alerte"),
        ('non_conforme', "Non conforme"),
    ], string="Avis")

    avis_suggere = fields.Selection(
        selection=lambda self: self._fields['avis'].selection,
        string="Avis suggéré", compute='_compute_avis_suggere',
        help="Déduit des six vérifications. Le contrôleur reste libre de "
             "retenir un autre avis — c'est une aide, pas une décision.",
    )

    controlled_by_id = fields.Many2one('res.users', string="Contrôlé par", readonly=True)
    date = fields.Datetime(string="Date du contrôle", readonly=True)

    @api.depends('completude', 'coherence', 'qualite_informations',
                 'conformite_criteres', 'justificatifs', 'anomalies')
    def _compute_avis_suggere(self):
        for control in self:
            control.avis_suggere = control._avis_suggere()

    def _avis_suggere(self):
        """La logique de contrôle, isolée — le seul endroit qui juge.

        C'est cette méthode qu'un agent IA remplacerait le jour venu : elle
        prend des vérifications en entrée et rend un avis, sans rien savoir du
        workflow, des états, ni des boutons. Les trois transitions du projet,
        elles, ne l'appellent pas — elles se contentent de lire l'avis retenu.

        Les règles, dans l'ordre de priorité :

        * il manque des pièces ou des informations → le porteur peut corriger,
          c'est « À compléter » ;
        * le dossier ne respecte pas les critères → « Non conforme », le comité
          tranchera ;
        * incohérence ou informations douteuses → « Alerte » ;
        * une anomalie relevée sans autre défaut → « Alerte » quand même : on
          ne signale pas une anomalie pour la classer sans suite.
        """
        self.ensure_one()
        if not self.completude or not self.justificatifs:
            return 'a_completer'
        if not self.conformite_criteres:
            return 'non_conforme'
        if not self.coherence or not self.qualite_informations:
            return 'alerte'
        if (self.anomalies or '').strip():
            return 'alerte'
        return 'ok'
