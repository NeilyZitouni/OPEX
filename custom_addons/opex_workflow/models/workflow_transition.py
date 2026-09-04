from odoo import api, fields, models


class WorkflowTransition(models.Model):
    """Un passage possible d'une étape à une autre.

    **Plusieurs transitions partent d'une même étape.** C'est ce qui produit
    le GO / À clarifier / NO GO / Orientation d'une pré-analyse et le
    Accepté / Ajourné / Refusé d'un comité. Aucune contrainte d'unicité ne porte
    sur `source_stage_id` : supposer qu'une étape n'a qu'une sortie
    transformerait le moteur en séquence linéaire.

    `name` n'est pas décoratif : c'est **le libellé du bouton** que verra
    l'utilisateur. « Valider », « Demander un complément », « Ajourner ».
    """

    _name = 'opex.workflow.transition'
    _description = "Transition de workflow"
    _order = 'definition_id, sequence, id'

    definition_id = fields.Many2one(
        'opex.workflow.definition',
        string="Workflow",
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(
        string="Libellé du bouton",
        required=True,
        translate=True,
        help="Ce que lit l'utilisateur sur le bouton d'action : « Valider », "
             "« Demander un complément », « Ajourner ».",
    )
    code = fields.Char(string="Code", required=True, index=True)
    sequence = fields.Integer(
        string="Séquence",
        default=10,
        help="Ordre de présentation des actions possibles à l'utilisateur.",
    )

    source_stage_id = fields.Many2one(
        'opex.workflow.stage',
        string="Étape de départ",
        required=True,
        ondelete='cascade',
        index=True,
        domain="[('definition_id', '=', definition_id)]",
    )
    # `restrict` et non `cascade` : supprimer une étape encore ciblée par une
    # transition doit échouer bruyamment. En cascade, le graphe perdrait
    # silencieusement un chemin, et l'erreur ne se verrait qu'au moment où un
    # dossier réel se retrouve bloqué.
    target_stage_id = fields.Many2one(
        'opex.workflow.stage',
        string="Étape d'arrivée",
        required=True,
        ondelete='restrict',
        index=True,
        domain="[('definition_id', '=', definition_id)]",
    )

    allowed_role_ids = fields.Many2many(
        'opex.workflow.role',
        'workflow_transition_role_rel', 'transition_id', 'role_id',
        string="Rôles autorisés",
        help="Qui peut déclencher cette transition. Laissé vide, elle est "
             "ouverte à tout utilisateur ayant accès au dossier.",
    )
    condition_ids = fields.Many2many(
        'opex.workflow.rule',
        'workflow_transition_rule_rel', 'transition_id', 'rule_id',
        string="Conditions",
        help="Toutes doivent être vraies pour que la transition soit "
             "déclenchable. Une condition fausse n'efface pas le bouton : elle "
             "le désactive et affiche son message.",
    )
    action_ids = fields.Many2many(
        'opex.workflow.action',
        'workflow_transition_action_rel', 'transition_id', 'action_id',
        string="Actions",
        help="Exécutées après le changement d'étape (Extension 4).",
    )
    requires_comment = fields.Boolean(
        string="Commentaire obligatoire",
        help="Impose une justification écrite. À cocher sur les refus, les "
             "ajournements et les demandes de complément : sans motif, "
             "l'utilisateur reçoit une décision qu'il ne peut pas corriger.",
    )
    description = fields.Text(string="Description")
    active = fields.Boolean(string="Actif", default=True)

    _code_uniq = models.Constraint(
        'unique(definition_id, code)',
        "Deux transitions du même workflow ne peuvent pas porter le même code.",
    )

    @api.depends('name', 'source_stage_id', 'target_stage_id')
    def _compute_display_name(self):
        for transition in self:
            transition.display_name = "%s : %s → %s" % (
                transition.name,
                transition.source_stage_id.name or '?',
                transition.target_stage_id.name or '?',
            )
