from odoo import _, api, fields, models
from odoo.exceptions import UserError

#: Code du rôle porté par un évaluateur **sur un projet donné**.
#:
#: Expert ≠ évaluateur. Le rôle « Expert » du portail est un profil du
#: vivier ; on devient évaluateur uniquement quand on est **désigné pour ce
#: projet-là**, c'est-à-dire quand une ligne `instance.actor` porte ce rôle sur
#: cette instance. C'est exactement l'usage des droits dynamiques.
EVALUATOR_ROLE = 'opex_innovation.role_evaluateur'


class InnovationEvaluation(models.Model):
    """Avis **consultatif** d'un évaluateur sur un projet — section 15.

    Trois mots de la spécification gouvernent tout ce fichier :

    - **optionnelle** : le comité peut décider de se passer d'évaluateurs. Deux
      transitions distinctes partent de « Qualifié », pas une seule avec un
      `if` dedans.
    - **consultatif** : rien ici ne déclenche de transition, et aucune décision
      ne se prend en lisant un score. Le comité peut ne pas retenir l'avis.
    - **exclusivement** : la décision finale appartient au comité. Ce modèle ne
      porte aucune décision, seulement des observations.
    """

    _name = 'opex.innovation.evaluation'
    _description = "Évaluation d'un projet d'innovation"
    _order = 'project_id, id'
    _rec_name = 'evaluator_id'

    project_id = fields.Many2one(
        'opex.innovation.project',
        string="Projet",
        required=True,
        ondelete='cascade',
        index=True,
    )
    evaluator_id = fields.Many2one(
        'res.partner',
        string="Évaluateur",
        required=True,
        ondelete='cascade',
        index=True,
    )
    state = fields.Selection(
        [
            ('requested', "Demandée"),
            ('in_progress', "En cours"),
            ('submitted', "Rendue"),
        ],
        string="État de l'avis",
        default='requested',
        required=True,
        index=True,
        help="État de **l'avis**, pas du projet. Le projet n'a pas d'état : il "
             "a une étape de workflow.",
    )
    date_requested = fields.Datetime(
        string="Sollicité le", default=fields.Datetime.now, readonly=True)
    date_submitted = fields.Datetime(string="Rendu le", readonly=True)

    # ------------------------------------------------------------
    # La grille de la section 15
    # ------------------------------------------------------------

    #: Barème, à un seul endroit : les contraintes, l'affichage et le total
    #: le lisent tous ici. Trois copies du chiffre 20 finiraient par diverger.
    _CRITERIA = {
        'score_innovation': 20,
        'score_pertinence': 20,
        'score_faisabilite': 20,
        'score_marche': 20,
        'score_equipe': 10,
        'score_impact': 10,
    }

    score_innovation = fields.Integer(string="Innovation", help="Sur 20.")
    score_pertinence = fields.Integer(
        string="Pertinence du besoin", help="Sur 20.")
    score_faisabilite = fields.Integer(
        string="Faisabilité technique et opérationnelle", help="Sur 20.")
    score_marche = fields.Integer(string="Potentiel du marché", help="Sur 20.")
    score_equipe = fields.Integer(string="Équipe", help="Sur 10.")
    score_impact = fields.Integer(string="Impact attendu", help="Sur 10.")

    score_total = fields.Integer(
        string="Total",
        compute='_compute_score_total',
        store=True,
        help="Somme des six critères, sur 100.",
    )

    # ------------------------------------------------------------
    # Ce que l'évaluateur peut fournir en plus de la note
    # ------------------------------------------------------------

    commentaires = fields.Text(string="Commentaires")
    observations = fields.Text(string="Observations")
    points_forts = fields.Text(string="Points forts")
    points_faibles = fields.Text(string="Points faibles")
    risques = fields.Text(string="Risques identifiés")
    recommandations = fields.Text(string="Recommandations")
    propositions_amelioration = fields.Text(string="Propositions d'amélioration")

    _evaluator_uniq = models.Constraint(
        'unique(project_id, evaluator_id)',
        "Cet évaluateur est déjà sollicité sur ce projet.",
    )

    @api.depends(*_CRITERIA)
    def _compute_score_total(self):
        for evaluation in self:
            evaluation.score_total = sum(
                evaluation[name] for name in self._CRITERIA)

    @api.constrains(*_CRITERIA)
    def _check_scores(self):
        labels = {name: self._fields[name].string for name in self._CRITERIA}
        for evaluation in self:
            for name, maximum in self._CRITERIA.items():
                value = evaluation[name]
                if not 0 <= value <= maximum:
                    raise UserError(_(
                        "« %(critere)s » doit être compris entre 0 et "
                        "%(max)s (valeur reçue : %(valeur)s)."
                    ) % {
                        'critere': labels[name],
                        'max': maximum,
                        'valeur': value,
                    })

    @api.depends('evaluator_id', 'project_id')
    def _compute_display_name(self):
        for evaluation in self:
            evaluation.display_name = _("Avis de %(evaluateur)s — %(projet)s") % {
                'evaluateur': evaluation.evaluator_id.display_name or '',
                'projet': evaluation.project_id.name or '',
            }

    # ------------------------------------------------------------
    # Cycle de vie de l'avis
    # ------------------------------------------------------------

    def action_start(self):
        for evaluation in self:
            if evaluation.state == 'requested':
                evaluation.state = 'in_progress'
        return True

    def action_submit(self):
        """Finalise l'avis. Irréversible pour l'évaluateur.

        Un avis rendu ne se retouche plus : c'est ce qui donne un sens à la
        confidentialité. Si l'on pouvait revenir sur son avis après avoir lu
        celui des autres, l'indépendance ne serait qu'une formalité.
        """
        for evaluation in self:
            if evaluation.state == 'submitted':
                raise UserError(_("Cet avis a déjà été rendu."))
            evaluation.write({
                'state': 'submitted',
                'date_submitted': fields.Datetime.now(),
            })
        return True

    def write(self, vals):
        """Un avis rendu est figé, sauf pour le personnel du cluster.

        Le contrôle porte sur le modèle et non sur l'écran : un `write()` venant
        du portail, du back-office ou d'une requête forgée passe par ici.
        """
        locked = self.filtered(lambda e: e.state == 'submitted')
        if locked and not self.env.su and set(vals) - {'state'}:
            if not self.env.user._has_group(
                    'opex_innovation.group_comite_evaluation'):
                raise UserError(_(
                    "L'avis de %s a été rendu : il ne peut plus être modifié."
                ) % locked[0].evaluator_id.display_name)
        return super().write(vals)
