from odoo import _, api, fields, models
from odoo.exceptions import UserError

#: Les quatre critères de la section 29, notés sur 5. Table plutôt que quatre
#: champs recopiés dans chaque calcul : ajouter un critère est une ligne, et la
#: moyenne n'a pas à être retouchée.
CRITERIA = {
    'note_pertinence': "Pertinence de l'accompagnement",
    'note_mentorat': "Qualité du mentorat",
    'note_resultats': "Résultats obtenus",
    'note_delais': "Respect des délais",
}


class FinalEvaluation(models.Model):
    """Section 29 — l'évaluation finale, des deux côtés.

    « Le porteur peut évaluer l'accompagnement. Et le cluster peut également
    évaluer : pertinence de l'accompagnement, qualité du mentorat, résultats,
    respect des délais. »

    Les deux côtés répondent à la **même grille**, et c'est délibéré : deux
    grilles différentes auraient donné deux notes incomparables, alors que tout
    l'intérêt d'interroger les deux parties est de pouvoir les mettre en regard.
    L'écart entre les deux est le renseignement, pas les notes prises isolément.

    Ce modèle porte un champ `state`, contrairement au projet. Ce n'est pas
    une entorse : `state` décrit ici l'état d'un **formulaire** — brouillon ou
    remis — pas l'avancement d'un dossier dans un processus. La règle interdit
    de décrire un parcours métier autrement que par le moteur ; elle
    n'interdit pas à un formulaire d'avoir un bouton « Envoyer ». C'est déjà le
    choix fait pour `opex.innovation.evaluation` à l'Extension 13.
    """

    _name = 'opex.innovation.final.evaluation'
    _description = "Évaluation finale d'un accompagnement"
    _order = 'date_submitted desc, id desc'

    project_id = fields.Many2one(
        'opex.innovation.project',
        string="Projet",
        required=True,
        ondelete='cascade',
        index=True,
    )
    author_id = fields.Many2one(
        'res.partner',
        string="Auteur",
        required=True,
        ondelete='restrict',
        index=True,
    )
    author_side = fields.Selection(
        [
            ('porteur', "Porteur du projet"),
            ('cluster', "Cluster"),
        ],
        string="Répond en tant que",
        required=True,
        index=True,
    )

    note_pertinence = fields.Integer(string=CRITERIA['note_pertinence'])
    note_mentorat = fields.Integer(string=CRITERIA['note_mentorat'])
    note_resultats = fields.Integer(string=CRITERIA['note_resultats'])
    note_delais = fields.Integer(string=CRITERIA['note_delais'])

    note_globale = fields.Float(
        string="Note globale",
        compute='_compute_note_globale',
        store=True,
        digits=(3, 2),
        help="Moyenne des quatre critères, sur 5.",
    )
    commentaire = fields.Text(string="Commentaire")

    state = fields.Selection(
        [
            ('draft', "Brouillon"),
            ('submitted', "Remise"),
        ],
        string="État du formulaire",
        default='draft',
        required=True,
        index=True,
    )
    date_submitted = fields.Datetime(string="Remise le", readonly=True)

    _author_uniq = models.Constraint(
        'unique(project_id, author_id, author_side)',
        "Cette personne a déjà évalué ce projet à ce titre.",
    )

    @api.depends(*CRITERIA)
    def _compute_note_globale(self):
        for record in self:
            notes = [record[name] for name in CRITERIA]
            record.note_globale = sum(notes) / len(notes) if notes else 0.0

    @api.constrains(*CRITERIA)
    def _check_notes(self):
        for record in self:
            for name, label in CRITERIA.items():
                if not 0 <= record[name] <= 5:
                    raise UserError(_(
                        "« %(critere)s » se note de 0 à 5. Valeur reçue : "
                        "%(valeur)s."
                    ) % {'critere': label, 'valeur': record[name]})

    @api.depends('project_id.name', 'author_side')
    def _compute_display_name(self):
        sides = dict(self._fields['author_side'].selection)
        for record in self:
            record.display_name = "%s — %s" % (
                record.project_id.name or '',
                sides.get(record.author_side, ''))

    def write(self, vals):
        """Une évaluation remise ne se retouche plus.

        Sans cette barrière, l'écart entre l'avis du porteur et celui du
        cluster — le seul renseignement que cette section produise — pourrait
        être ajusté après lecture de l'autre.
        """
        locked = self.filtered(lambda r: r.state == 'submitted')
        if locked and not self.env.su and set(vals) - {'state'}:
            raise UserError(_(
                "Une évaluation déjà remise ne peut plus être modifiée."))
        return super().write(vals)

    def action_submit(self):
        self.ensure_one()
        if self.state == 'submitted':
            raise UserError(_("Cette évaluation a déjà été remise."))
        self.write({
            'state': 'submitted',
            'date_submitted': fields.Datetime.now(),
        })
        return True


class ProjectFinalEvaluation(models.Model):
    """L'évaluation finale vue depuis le projet."""

    _inherit = 'opex.innovation.project'

    final_evaluation_ids = fields.One2many(
        'opex.innovation.final.evaluation', 'project_id',
        string="Évaluations finales")

    def can_evaluate_finally(self, user=None):
        """Qui peut ouvrir le formulaire de la section 29, et à quel titre.

        Renvoie `'porteur'`, `'cluster'` ou `False`. Une seule fonction pour la
        route et pour le gabarit : un `t-if` qui dirait autre chose que le
        contrôle serveur produirait un bouton menant à une erreur.
        """
        self.ensure_one()
        user = user or self.env.user
        instance = self.workflow_instance_id
        # Le bilan ferme le dossier ; l'évaluation vient après lui.
        if not instance or instance.state != 'done':
            return False
        if user.partner_id == self.partner_id:
            return 'porteur'
        if self._is_committee(user) or user.sudo()._has_group(
                'opex_innovation.group_innovation_manager'):
            return 'cluster'
        return False

    def visible_final_evaluations(self, user=None):
        """Ce que cet utilisateur a le droit de lire.

        Le porteur voit la sienne. Le cluster voit tout — c'est lui qui exploite
        l'écart. Un porteur ne lit pas l'avis que le cluster porte sur
        l'accompagnement qu'il a reçu : ce n'est pas la même conversation.
        """
        self.ensure_one()
        user = user or self.env.user
        evaluations = self.sudo().final_evaluation_ids
        if self._is_committee(user) or user.sudo()._has_group(
                'opex_innovation.group_innovation_manager'):
            return evaluations
        return evaluations.filtered(
            lambda e: e.author_id == user.partner_id)

    def submit_final_evaluation(self, notes, commentaire=False, user=None):
        """Enregistre et remet l'évaluation, après contrôle du droit.

        Le côté (`porteur` / `cluster`) n'est **jamais** pris dans le
        formulaire : il est déduit de l'identité par `can_evaluate_finally()`.
        Un champ caché dans la page serait modifiable par qui sait ouvrir les
        outils de développement, et un porteur pourrait déposer l'avis du
        cluster sur son propre accompagnement.
        """
        self.ensure_one()
        user = user or self.env.user
        side = self.can_evaluate_finally(user)
        if not side:
            raise UserError(_(
                "Vous ne pouvez pas évaluer l'accompagnement de « %s »."
            ) % self.display_name)

        values = {name: int(notes.get(name) or 0) for name in CRITERIA}
        Evaluation = self.env['opex.innovation.final.evaluation'].sudo()
        existing = Evaluation.search([
            ('project_id', '=', self.id),
            ('author_id', '=', user.partner_id.id),
            ('author_side', '=', side),
        ], limit=1)
        if existing and existing.state == 'submitted':
            raise UserError(_("Vous avez déjà évalué cet accompagnement."))

        values['commentaire'] = commentaire or False
        if existing:
            existing.write(values)
            evaluation = existing
        else:
            values.update({
                'project_id': self.id,
                'author_id': user.partner_id.id,
                'author_side': side,
            })
            evaluation = Evaluation.create(values)

        evaluation.action_submit()
        return evaluation
