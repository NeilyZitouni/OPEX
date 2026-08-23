from odoo import _, fields, models
from odoo.exceptions import UserError


class WorkflowMixin(models.AbstractModel):
    """Rend un modèle métier pilotable par un workflow.

    Côté module métier, c'est une ligne :

        _inherit = ['mail.thread', 'opex.workflow.mixin']

    ⚠ **Tous les champs sont préfixés `workflow_`, sans exception.** Un modèle
    hôte a presque toujours déjà un `state`, souvent un `stage_id` (c'est le cas
    de `project.project`), parfois un `sequence`. Une collision de nom sur un
    mixin ne se voit pas au chargement : elle écrase silencieusement le champ de
    l'hôte et échoue au runtime, sur un écran que personne ne regardait.

    Le mixin est délibérément **mince** : il n'expose que des champs de confort
    et délègue toute la logique à `opex.workflow.instance`. Le moteur tourne sur
    `res_model` / `res_id` et n'exige donc pas ce mixin — il pilote aussi bien un
    modèle natif Odoo qui ne l'a jamais hérité. Le mixin rend l'usage agréable,
    il ne le rend pas possible.
    """

    _name = 'opex.workflow.mixin'
    _description = "Objet piloté par un workflow"

    workflow_instance_id = fields.Many2one(
        'opex.workflow.instance',
        string="Instance de workflow",
        readonly=True,
        copy=False,
        ondelete='set null',
    )
    workflow_stage_id = fields.Many2one(
        'opex.workflow.stage',
        string="Étape",
        related='workflow_instance_id.current_stage_id',
        store=True,
        readonly=True,
    )
    workflow_stage_label = fields.Char(
        string="Étape (utilisateur)",
        related='workflow_stage_id.user_label',
        readonly=True,
    )
    workflow_definition_id = fields.Many2one(
        'opex.workflow.definition',
        string="Workflow",
        related='workflow_instance_id.definition_id',
        readonly=True,
    )
    workflow_state = fields.Selection(
        string="État du workflow",
        related='workflow_instance_id.state',
        readonly=True,
    )

    def start_workflow(self, definition_code, actor_values=None):
        """Fait entrer l'enregistrement dans le processus nommé par ce code.

        Le démarrage est idempotent au sens strict : il refuse plutôt qu'il ne
        remplace. Redémarrer un workflow sur un dossier déjà engagé
        détacherait son historique sans le supprimer — on aurait un journal
        d'audit orphelin et un dossier qui semble n'être jamais passé nulle part.
        """
        self.ensure_one()
        if self.workflow_instance_id:
            raise UserError(_(
                "« %(record)s » suit déjà le workflow « %(workflow)s ». "
                "Un enregistrement ne peut pas être engagé deux fois."
            ) % {
                'record': self.display_name,
                'workflow': self.workflow_instance_id.definition_id.name,
            })
        instance = self.env['opex.workflow.instance']._start_for(
            self, definition_code, actor_values=actor_values)
        self.workflow_instance_id = instance.id
        return instance

    def workflow_available_transitions(self, user=None):
        """Raccourci vers les transitions possibles sur cet enregistrement."""
        self.ensure_one()
        if not self.workflow_instance_id:
            return self.env['opex.workflow.transition'].browse()
        return self.workflow_instance_id.available_transitions(user=user)

    def workflow_transition_options(self, user=None):
        """Les mêmes, avec l'état de chaque transition (disponible / bloquée)."""
        self.ensure_one()
        if not self.workflow_instance_id:
            return []
        return self.workflow_instance_id.transition_options(user=user)

    def workflow_do_transition(self, transition, comment=False):
        """Déclenche une transition sur cet enregistrement.

        Passe par `opex.workflow.instance.do_transition()`, donc par l'unique
        fonction de contrôle d'accès. Il n'y a pas de vérification de droits
        ici : en ajouter une créerait un second endroit où le droit de
        transition se décide.
        """
        self.ensure_one()
        if not self.workflow_instance_id:
            raise UserError(_(
                "« %s » n'est engagé dans aucun workflow."
            ) % self.display_name)
        return self.workflow_instance_id.do_transition(transition, comment=comment)

    def action_workflow_transition(self):
        """Bouton « Action » : ouvre le wizard des transitions possibles.

        Un bouton unique, et non N boutons générés : leur nombre et leur
        libellé dépendent de la donnée, ce qu'une vue XML ne sait pas exprimer.

        Le wizard est refusé plutôt qu'ouvert vide quand il n'y a rien à
        proposer. Une fenêtre avec une liste déroulante sans option laisse
        l'utilisateur chercher ce qu'il a mal fait ; un message lui dit
        pourquoi.
        """
        self.ensure_one()
        if not self.workflow_instance_id:
            raise UserError(_(
                "« %s » n'est engagé dans aucun workflow."
            ) % self.display_name)
        return self.workflow_instance_id.action_open_transition_wizard()

    # ------------------------------------------------------------
    # Extrait de vue à reprendre dans le module métier
    # ------------------------------------------------------------
    #
    # Le mixin fournit les champs, pas les vues : c'est le module métier qui
    # possède le formulaire de son modèle. Le bloc à y coller :
    #
    #   <header>
    #       <button name="action_workflow_transition" type="object"
    #               string="Action" class="btn-primary"
    #               invisible="workflow_state != 'running'"/>
    #       <field name="workflow_definition_id" invisible="1"/>
    #       <field name="workflow_stage_id" widget="statusbar"
    #              options="{'clickable': false}"
    #              domain="[('definition_id', '=', workflow_definition_id)]"/>
    #   </header>
    #
    # `workflow_definition_id` doit être présent dans la vue, même invisible :
    # sans lui, le `domain` du statusbar ne peut pas être évalué et la barre
    # affiche les étapes de *tous* les workflows.
