from odoo import _, api, fields, models
from odoo.exceptions import UserError


class WorkflowTransitionWizard(models.TransientModel):
    """Le « que puis-je faire ? » du moteur.

    Un bouton unique **« Action »** ouvre ce wizard, plutôt que N boutons
    générés dynamiquement dans la vue. La raison est structurelle : le nombre et
    le libellé des transitions dépendent de la **donnée** (l'étape courante, les
    rôles de l'utilisateur), or une vue XML est statique. Générer des boutons
    variables demanderait un composant OWL — une journée et demie de
    développement sur quatre, et un point de fragilité en démonstration.

    Le statusbar donne le « où j'en suis », ce wizard donne le « que puis-je
    faire ». Ensemble, ça couvre le besoin sans une ligne de JavaScript.

    ⚠ **Aucun contrôle d'accès ici.** Le wizard construit sa liste avec
    `available_transitions()` et confirme avec `do_transition()`, qui appelle
    `_check_transition_allowed()`. Ajouter une vérification dans ce fichier
    créerait un second endroit où le droit de transition se décide — et c'est
    toujours le second qu'on oublie de mettre à jour.
    """

    _name = 'opex.workflow.transition.wizard'
    _description = "Faire avancer le dossier"

    instance_id = fields.Many2one(
        'opex.workflow.instance',
        string="Instance",
        required=True,
        readonly=True,
    )
    current_stage_id = fields.Many2one(
        'opex.workflow.stage',
        string="Étape courante",
        related='instance_id.current_stage_id',
        readonly=True,
    )
    # Selection et non Many2one : c'est le seul type de champ dont le *libellé*
    # peut être calculé à la volée, ce qui permet d'afficher « Valider » et
    # « Refuser — bloqué : le pitch deck manque » dans la même liste. Un
    # Many2one afficherait le nom de la transition et rien d'autre.
    transition_id = fields.Selection(
        selection='_selection_transitions',
        string="Action",
        required=True,
    )
    comment = fields.Text(
        string="Commentaire",
        help="Transmis à l'intéressé et conservé dans l'historique du dossier.",
    )
    requires_comment = fields.Boolean(compute='_compute_transition_state')
    is_blocked = fields.Boolean(compute='_compute_transition_state')
    blocking_reason = fields.Text(compute='_compute_transition_state')

    # ------------------------------------------------------------
    # Les options proposées
    # ------------------------------------------------------------

    def _instance_from_context(self):
        """L'instance concernée, lue dans le contexte.

        Une méthode de `selection` est appelée sur le modèle, pas sur
        l'enregistrement : `self` n'a pas encore d'`instance_id`. Le contexte
        est donc le seul endroit où trouver le dossier, et c'est pour cela que
        `action_workflow_transition()` y place `default_instance_id`.
        """
        instance_id = self.env.context.get('default_instance_id')
        if not instance_id:
            return self.env['opex.workflow.instance'].browse()
        return self.env['opex.workflow.instance'].browse(instance_id).exists()

    @api.model
    def _selection_transitions(self):
        """Les transitions proposées, chacune avec son état.

        ⚠ Les transitions **bloquées par une condition sont présentes**, avec
        le motif dans leur libellé. Les retirer laisserait l'utilisateur devant
        une liste amputée sans savoir ce qui manque ni quoi faire pour le
        débloquer. C'est le même principe que `available_transitions()`, dont
        cette méthode n'est que l'habillage.
        """
        instance = self._instance_from_context()
        if not instance:
            return []
        options = []
        for option in instance.transition_options():
            transition = option['transition']
            label = transition.name
            if not option['available']:
                label = _("%(name)s — indisponible : %(reason)s") % {
                    'name': transition.name,
                    'reason': option['reason'],
                }
            options.append((str(transition.id), label))
        return options

    def _selected_transition(self):
        """La transition choisie, **cherchée parmi celles qui sont proposées**.

        L'identifiant vient du client : il n'est jamais utilisé pour naviguer
        directement. Il est résolu *dans* l'ensemble des transitions autorisées,
        calculé côté serveur. Une valeur forgée ne désigne donc rien.
        """
        self.ensure_one()
        if not self.transition_id:
            return self.env['opex.workflow.transition'].browse()
        allowed = self.instance_id.available_transitions()
        return allowed.filtered(lambda t: str(t.id) == self.transition_id)[:1]

    @api.depends('transition_id', 'instance_id')
    def _compute_transition_state(self):
        for wizard in self:
            transition = wizard._selected_transition()
            wizard.requires_comment = transition.requires_comment
            if not transition:
                wizard.is_blocked = False
                wizard.blocking_reason = False
                continue
            ok, blocking, _notes = wizard.instance_id._evaluate_conditions(transition)
            wizard.is_blocked = not ok
            wizard.blocking_reason = "\n".join(
                "• %s" % message for message in blocking) if blocking else False

    # ------------------------------------------------------------
    # Confirmation
    # ------------------------------------------------------------

    def action_confirm(self):
        """Déclenche la transition choisie.

        Ne réimplémente ni le contrôle d'accès, ni l'évaluation des conditions,
        ni l'exigence de commentaire : `do_transition()` fait les trois, et
        lève un message rédigé si l'un échoue. Le wizard ne fait que traduire
        un choix d'écran en appel de méthode.
        """
        self.ensure_one()
        transition = self._selected_transition()
        if not transition:
            raise UserError(_(
                "Cette action n'est plus disponible sur ce dossier. Fermez "
                "cette fenêtre et rouvrez-la pour voir les actions à jour."
            ))
        self.instance_id.do_transition(transition, comment=self.comment)
        return {'type': 'ir.actions.act_window_close'}
