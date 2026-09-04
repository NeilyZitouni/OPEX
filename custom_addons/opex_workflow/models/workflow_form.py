import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class WorkflowForm(models.Model):
    """Un écran de saisie décrit en données, pas en template.

    C'est le « dossier progressif » des documents sources : on ne demande au
    porteur que ce dont on a besoin **à cette étape-là**, et le questionnaire
    dépend de ce qu'il a déjà répondu. Un projet cherchant un investisseur ne
    voit pas les mêmes champs qu'un projet cherchant un sponsor.

    Sans ce modèle, la seule façon d'obtenir ce résultat serait un template par
    combinaison — c'est-à-dire du code à écrire pour chaque nouveau type de
    besoin. Ici, c'est une ligne de configuration.
    """

    _name = 'opex.workflow.form'
    _description = "Formulaire dynamique de workflow"
    _order = 'definition_id, sequence, id'

    name = fields.Char(string="Nom", required=True, translate=True)
    code = fields.Char(string="Code", required=True, index=True)
    definition_id = fields.Many2one(
        'opex.workflow.definition',
        string="Workflow",
        required=True,
        ondelete='cascade',
        index=True,
    )
    stage_id = fields.Many2one(
        'opex.workflow.stage',
        string="Étape",
        ondelete='cascade',
        index=True,
        domain="[('definition_id', '=', definition_id)]",
        help="Étape à laquelle ce formulaire est présenté. Plusieurs "
             "formulaires peuvent viser la même étape : c'est leur "
             "« condition d'affichage » qui décide lequel s'applique.",
    )
    sequence = fields.Integer(string="Séquence", default=10)
    description = fields.Text(string="Description")
    intro = fields.Html(
        string="Texte d'introduction",
        translate=True,
        help="Affiché en haut de la page, avant les champs. Sert à expliquer "
             "au porteur ce qu'on attend de lui à cette étape.",
    )
    field_ids = fields.One2many(
        'opex.workflow.form.field', 'form_id', string="Champs")
    active = fields.Boolean(string="Actif", default=True)

    _code_uniq = models.Constraint(
        'unique(definition_id, code)',
        "Deux formulaires du même workflow ne peuvent pas porter le même code.",
    )

    @api.depends('name', 'stage_id')
    def _compute_display_name(self):
        for form in self:
            form.display_name = "%s%s" % (
                form.name,
                " — %s" % form.stage_id.name if form.stage_id else '',
            )

    # ------------------------------------------------------------
    # Ce qui est réellement présenté
    # ------------------------------------------------------------

    def visible_field_lines(self, instance):
        """Les champs à rendre, **calculés côté serveur**.

        C'est le pivot de sécurité de toute l'extension. Un champ dont la
        condition de visibilité est fausse ne doit pas être rendu du tout —
        pas rendu puis masqué en CSS. « Présent dans le HTML » suffirait à
        divulguer une information réservée, et un masquage client se retire
        avec l'inspecteur du navigateur.

        C'est aussi cette liste qui borne l'enregistrement : `save()` n'écrit
        que ce qu'elle contient. Un POST forgé nommant un champ invisible
        n'écrit rien.
        """
        self.ensure_one()
        return self.field_ids.filtered(
            lambda line: line._is_visible(instance)).sorted('sequence')

    def required_field_lines(self, instance):
        """Parmi les champs visibles, ceux qui doivent être renseignés.

        Un champ invisible n'est jamais requis : exiger la saisie d'un champ
        qu'on ne montre pas enferme l'utilisateur dans un formulaire
        insoumettable.
        """
        self.ensure_one()
        return self.visible_field_lines(instance).filtered(
            lambda line: line._is_required(instance))

    def render_values(self, instance):
        """Données prêtes à rendre : une entrée par champ visible."""
        self.ensure_one()
        record = instance._get_record()
        values = []
        for line in self.visible_field_lines(instance):
            values.append(line._render_value(instance, record))
        return values

    # ------------------------------------------------------------
    # Validation et enregistrement
    # ------------------------------------------------------------

    def validate(self, instance, posted):
        """Messages d'erreur pour les champs requis non renseignés."""
        self.ensure_one()
        errors = []
        for line in self.required_field_lines(instance):
            raw = posted.get(line.input_name)
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                errors.append(_("« %s » est obligatoire.") % line.label)
        return errors

    def save(self, instance, posted, partial=True):
        """Écrit sur l'objet métier les champs de ce formulaire.

        `partial=True` est le **brouillon automatique** : on enregistre ce qui
        a été saisi sans exiger que tout le soit. C'est ce qui permet au
        porteur de quitter la page et de revenir sans rien perdre. La
        vérification des champs requis se fait au moment de valider l'étape,
        pas à chaque frappe.

        Seuls les champs **visibles** sont écrits, et ils sont relus depuis
        la configuration, jamais depuis les clés du POST. Un formulaire forgé
        qui nommerait un champ non exposé n'écrit rien.
        """
        self.ensure_one()
        record = instance._get_record()
        if not record:
            return False

        if not partial:
            errors = self.validate(instance, posted)
            if errors:
                return errors

        values = {}
        for line in self.visible_field_lines(instance):
            if line.input_name not in posted:
                continue
            if line.readonly:
                continue
            values[line.field_name] = line._convert(posted.get(line.input_name))

        if values:
            record.sudo().write(values)
        return []

    @api.model
    def form_for_stage(self, instance):
        """Le formulaire applicable à l'étape courante d'une instance.

        Renvoie le premier par séquence : plusieurs formulaires peuvent viser
        la même étape, l'ordre tranche. Un moteur qui en renverrait plusieurs
        obligerait chaque appelant à choisir, et ils choisiraient
        différemment.
        """
        stage = instance.current_stage_id
        if not stage:
            return self.browse()
        return self.sudo().search([
            ('definition_id', '=', instance.definition_id.id),
            ('stage_id', '=', stage.id),
        ], order='sequence, id', limit=1)


class WorkflowFormField(models.Model):
    """Un champ présenté dans un formulaire dynamique.

    Il ne duplique pas la donnée : il pointe vers un champ réel du modèle
    métier (`ir.model.fields`). Le formulaire décide seulement de sa
    présentation et de ses conditions.
    """

    _name = 'opex.workflow.form.field'
    _description = "Champ d'un formulaire dynamique"
    _order = 'form_id, sequence, id'

    form_id = fields.Many2one(
        'opex.workflow.form',
        string="Formulaire",
        required=True,
        ondelete='cascade',
        index=True,
    )
    field_id = fields.Many2one(
        'ir.model.fields',
        string="Champ",
        required=True,
        ondelete='cascade',
        index=True,
    )
    field_name = fields.Char(related='field_id.name', store=True)
    ttype = fields.Selection(related='field_id.ttype')
    sequence = fields.Integer(string="Séquence", default=10)

    label_override = fields.Char(
        string="Libellé affiché",
        translate=True,
        help="Remplace le libellé technique du champ. « Quel problème votre "
             "projet cherche-t-il à résoudre ? » plutôt que « Problème ».",
    )
    help_text = fields.Text(
        string="Aide",
        translate=True,
        help="Texte d'accompagnement affiché sous le champ.",
    )
    placeholder = fields.Char(string="Texte indicatif", translate=True)
    readonly = fields.Boolean(
        string="Lecture seule",
        help="Affiché mais non modifiable. Sert aux informations reprises du "
             "profil, que le porteur ne doit pas ressaisir.",
    )

    required_expression = fields.Text(
        string="Condition d'obligation",
        help="Expression évaluée comme une règle de workflow. Vraie, le champ "
             "devient obligatoire. Vide, le champ reste facultatif.\n\n"
             "Exemple : field('besoin_financement') == True\n\n"
             "Une expression en erreur est considérée FAUSSE : le champ reste "
             "facultatif plutôt que de rendre le formulaire insoumettable.",
    )
    visible_expression = fields.Text(
        string="Condition d'affichage",
        help="Expression évaluée comme une règle de workflow. Vraie, le champ "
             "est présenté. Vide, le champ est toujours présenté.\n\n"
             "Une expression en erreur est considérée FAUSSE : le champ n'est "
             "pas rendu. Le côté sûr — un champ affiché par erreur peut "
             "divulguer, un champ absent ne fait que manquer.",
    )
    widget_hint = fields.Selection(
        [
            ('auto', "Automatique"),
            ('text', "Ligne de texte"),
            ('textarea', "Zone de texte"),
            ('number', "Nombre"),
            ('date', "Date"),
            ('checkbox', "Case à cocher"),
            ('selection', "Liste de choix"),
        ],
        string="Présentation",
        default='auto',
        required=True,
        help="« Automatique » déduit la présentation du type du champ.",
    )

    label = fields.Char(string="Libellé", compute='_compute_label')
    input_name = fields.Char(string="Nom HTML", compute='_compute_input_name')

    _field_uniq = models.Constraint(
        'unique(form_id, field_id)',
        "Ce champ figure déjà dans ce formulaire.",
    )

    @api.depends('label_override', 'field_id')
    def _compute_label(self):
        for line in self:
            line.label = line.label_override or line.field_id.field_description

    @api.depends('field_name')
    def _compute_input_name(self):
        # Préfixé pour ne jamais collerà un nom de paramètre du framework
        # (`csrf_token`, `action`…) qui transiterait par le même POST.
        for line in self:
            line.input_name = 'wf_%s' % (line.field_name or '')

    @api.depends('label', 'form_id')
    def _compute_display_name(self):
        for line in self:
            line.display_name = line.label or line.field_name or ''

    # ------------------------------------------------------------
    # Conditions
    # ------------------------------------------------------------

    def _is_visible(self, instance):
        self.ensure_one()
        if not self.visible_expression:
            return True
        return instance._evaluate_flag(
            self.visible_expression,
            label=_("condition d'affichage de « %s »") % self.label,
        )

    def _is_required(self, instance):
        self.ensure_one()
        if not self.required_expression:
            return False
        return instance._evaluate_flag(
            self.required_expression,
            label=_("condition d'obligation de « %s »") % self.label,
        )

    # ------------------------------------------------------------
    # Rendu et conversion
    # ------------------------------------------------------------

    _WIDGET_BY_TTYPE = {
        'text': 'textarea',
        'html': 'textarea',
        'integer': 'number',
        'float': 'number',
        'monetary': 'number',
        'boolean': 'checkbox',
        'date': 'date',
        'datetime': 'date',
        'selection': 'selection',
    }

    def _widget(self):
        self.ensure_one()
        if self.widget_hint != 'auto':
            return self.widget_hint
        return self._WIDGET_BY_TTYPE.get(self.ttype, 'text')

    def _selection_options(self, record):
        """Choix d'un champ Selection, lus sur le modèle réel."""
        self.ensure_one()
        if self.ttype != 'selection' or not record:
            return []
        field = record._fields.get(self.field_name)
        if not field:
            return []
        try:
            return field._description_selection(record.env)
        except Exception:  # noqa: BLE001
            _logger.warning(
                "opex_workflow: choix illisibles pour %s.%s",
                record._name, self.field_name, exc_info=True)
            return []

    def _render_value(self, instance, record):
        self.ensure_one()
        value = False
        if record and self.field_name in record._fields:
            value = record.sudo()[self.field_name]
            if self.ttype == 'many2one':
                value = value.id or False
        return {
            'line': self,
            'name': self.input_name,
            'label': self.label,
            'help': self.help_text,
            'placeholder': self.placeholder,
            'required': self._is_required(instance),
            'readonly': self.readonly,
            'widget': self._widget(),
            'ttype': self.ttype,
            'value': value,
            'options': self._selection_options(record),
        }

    def _convert(self, raw):
        """Traduit une valeur de formulaire HTML vers le type du champ.

        Tolérante : une saisie inconvertible devient vide plutôt que de faire
        échouer l'enregistrement. Le brouillon automatique doit accepter un
        champ à moitié rempli — c'est sa raison d'être.
        """
        self.ensure_one()
        if self.ttype == 'boolean':
            return bool(raw) and str(raw).lower() not in ('0', 'false', 'off')
        if raw is None:
            return False
        raw = raw.strip() if isinstance(raw, str) else raw
        if raw == '':
            return False
        if self.ttype == 'integer':
            try:
                return int(raw)
            except (TypeError, ValueError):
                return 0
        if self.ttype in ('float', 'monetary'):
            try:
                return float(str(raw).replace(',', '.'))
            except (TypeError, ValueError):
                return 0.0
        if self.ttype == 'many2one':
            try:
                return int(raw)
            except (TypeError, ValueError):
                return False
        return raw
