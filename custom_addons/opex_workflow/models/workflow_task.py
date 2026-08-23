from odoo import _, api, fields, models
from odoo.exceptions import UserError


class WorkflowTask(models.Model):
    """Ce qu'un acteur a concrètement à traiter.

    C'est la **work queue** : chaque acteur voit ce qui l'attend, jamais le
    graphe complet. Un porteur n'a pas à comprendre le workflow pour savoir
    qu'on attend une pièce de sa part ; un contrôleur n'a pas à parcourir la
    liste des dossiers pour trouver les siens.

    Les tâches ne sont pas créées à la main : elles naissent d'une action
    `create_task` posée sur une transition.
    """

    _name = 'opex.workflow.task'
    _description = "Tâche de workflow"
    _order = 'deadline asc, id desc'

    instance_id = fields.Many2one(
        'opex.workflow.instance',
        string="Dossier",
        required=True,
        ondelete='cascade',
        index=True,
    )
    stage_id = fields.Many2one(
        'opex.workflow.stage',
        string="Étape",
        ondelete='restrict',
        index=True,
        help="Étape à laquelle la tâche a été créée. Sert aux vues agrégées : "
             "« combien de dossiers attendent quoi ».",
    )
    definition_id = fields.Many2one(
        'opex.workflow.definition',
        string="Workflow",
        related='instance_id.definition_id',
        store=True,
    )
    name = fields.Char(string="Intitulé", required=True, translate=True)
    role_id = fields.Many2one(
        'opex.workflow.role',
        string="Rôle attendu",
        ondelete='restrict',
        index=True,
        help="Qui doit traiter cette tâche. Renseigné même quand un "
             "utilisateur précis est assigné : si celui-ci change, le rôle "
             "reste la vérité.",
    )
    user_id = fields.Many2one(
        'res.users',
        string="Assignée à",
        ondelete='set null',
        index=True,
        help="Laissé vide quand le rôle est porté par plusieurs personnes : "
             "la tâche revient alors au premier qui s'en saisit.",
    )
    deadline = fields.Date(string="Échéance")
    state = fields.Selection(
        [
            ('todo', "À faire"),
            ('done', "Faite"),
            ('cancelled', "Annulée"),
        ],
        string="État",
        default='todo',
        required=True,
        index=True,
    )
    date_done = fields.Datetime(string="Terminée le", readonly=True)
    is_late = fields.Boolean(
        string="En retard", compute='_compute_is_late', search='_search_is_late')

    @api.depends('deadline', 'state')
    def _compute_is_late(self):
        today = fields.Date.context_today(self)
        for task in self:
            task.is_late = bool(
                task.state == 'todo' and task.deadline and task.deadline < today)

    def _search_is_late(self, operator, value):
        """Rend « en retard » utilisable en filtre malgré son calcul non stocké.

        Sans cette méthode, le filtre de la vue de recherche serait rejeté :
        un champ calculé non stocké n'est pas interrogeable par défaut.
        """
        today = fields.Date.context_today(self)
        late = [('state', '=', 'todo'), ('deadline', '<', today)]
        if operator not in ('=', '!='):
            raise UserError(_("Filtre non supporté sur « En retard »."))
        positive = (operator == '=') == bool(value)
        if positive:
            return late
        return ['!', '&'] + late

    @api.depends('name', 'instance_id')
    def _compute_display_name(self):
        for task in self:
            task.display_name = "%s — %s" % (
                task.name, task.instance_id.display_name or '')

    def action_done(self):
        for task in self:
            if task.state != 'todo':
                raise UserError(_(
                    "Seule une tâche à faire peut être marquée comme faite."))
            task.write({'state': 'done', 'date_done': fields.Datetime.now()})
        return True

    def action_cancel(self):
        for task in self:
            if task.state == 'done':
                raise UserError(_(
                    "Une tâche déjà faite ne peut pas être annulée."))
            task.state = 'cancelled'
        return True

    def action_open_instance(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'opex.workflow.instance',
            'res_id': self.instance_id.id,
            'view_mode': 'form',
        }
