from odoo import api, fields, models


class WorkflowStage(models.Model):
    """Une étape du processus.

    Deux noms, et ce n'est pas une redondance : `name` est le nom système, que
    lit le personnel du back-office (« Contrôle administratif ») ; `user_label`
    est ce que lit l'utilisateur final sur le portail (« Contrôle en cours »).
    Le workflow système peut être complexe, ce que l'utilisateur lit ne doit pas
    l'être.
    """

    _name = 'opex.workflow.stage'
    _description = "Étape de workflow"
    _order = 'definition_id, sequence, id'

    definition_id = fields.Many2one(
        'opex.workflow.definition',
        string="Workflow",
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(
        string="Nom",
        required=True,
        translate=True,
        help="Nom système de l'étape, affiché en back-office.",
    )
    user_label = fields.Char(
        string="Libellé utilisateur",
        translate=True,
        help="Ce que lit l'utilisateur final sur son portail. Écrivez « Contrôle "
             "en cours », jamais « under_review ». Laissé vide, le portail "
             "n'affichera rien pour cette étape.",
    )
    code = fields.Char(
        string="Code",
        required=True,
        index=True,
        help="Identifiant technique de l'étape, unique au sein du workflow.",
    )
    sequence = fields.Integer(
        string="Séquence",
        default=10,
        help="Ordre d'affichage. Ne détermine pas l'enchaînement du processus : "
             "ce sont les transitions qui le font.",
    )
    description = fields.Text(string="Description")

    is_start = fields.Boolean(
        string="Étape de départ",
        help="L'étape par laquelle tout nouvel enregistrement entre dans le "
             "processus. Il ne peut y en avoir qu'une.",
    )
    is_end = fields.Boolean(
        string="Étape finale",
        help="Atteindre cette étape clôture l'instance. Il peut y en avoir "
             "plusieurs : une clôture réussie et un refus sont deux fins.",
    )

    actor_role_ids = fields.Many2many(
        'opex.workflow.role',
        'workflow_stage_role_rel', 'stage_id', 'role_id',
        string="Rôles concernés",
        help="Qui travaille pendant cette étape. Informatif ici ; c'est la "
             "transition qui porte le droit de faire avancer le dossier.",
    )
    sla_days = fields.Integer(
        string="Délai attendu (jours)",
        help="Durée au-delà de laquelle un dossier resté à cette étape est en "
             "retard. Exploité par les relances (Extension 8).",
    )

    # Le champ annoncé en Extension 1 et différé jusqu'ici : il pointe vers
    # `opex.workflow.form`, qui n'existait pas alors. Un Many2one vers un modèle
    # absent du registre fait échouer le chargement du module — c'est pour ça
    # qu'il attendait son modèle.
    form_id = fields.Many2one(
        'opex.workflow.form',
        string="Formulaire",
        ondelete='set null',
        domain="[('definition_id', '=', definition_id)]",
        help="Écran de saisie présenté au porteur pendant cette étape. "
             "Laissé vide, l'étape ne demande rien.",
    )

    transition_out_ids = fields.One2many(
        'opex.workflow.transition', 'source_stage_id', string="Transitions sortantes")
    transition_in_ids = fields.One2many(
        'opex.workflow.transition', 'target_stage_id', string="Transitions entrantes")

    _code_uniq = models.Constraint(
        'unique(definition_id, code)',
        "Deux étapes du même workflow ne peuvent pas porter le même code.",
    )

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for stage in self:
            stage.display_name = "[%s] %s" % (stage.code, stage.name)
