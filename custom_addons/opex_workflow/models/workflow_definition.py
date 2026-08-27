from odoo import _, api, fields, models
from odoo.exceptions import UserError


class WorkflowDefinition(models.Model):
    """Un processus métier décrit sous forme de données.

    C'est l'objet que manipule le configurateur, et le seul écran que verra
    quelqu'un chargé d'ajouter une étape à un workflow existant. Tout ce qui
    suit — étapes, transitions, conditions — lui est rattaché.
    """

    _name = 'opex.workflow.definition'
    _description = "Définition de workflow"
    _inherit = ['mail.thread']
    _order = 'name, version desc'

    name = fields.Char(string="Nom", required=True, translate=True, tracking=True)
    code = fields.Char(
        string="Code",
        required=True,
        index=True,
        tracking=True,
        help="Identifiant technique du processus, stable d'une version à "
             "l'autre. C'est lui que le module métier passe à start_workflow(). "
             "Exemple : innovation_project, smart_crowdfunding.",
    )
    description = fields.Text(string="Description")
    model_id = fields.Many2one(
        'ir.model',
        string="Modèle piloté",
        required=True,
        # `cascade` et non `restrict` : Odoo 19 interdit `restrict` vers les
        # modèles du registre (`odoo/orm/fields.py:IR_MODELS`) et refuse de
        # charger le module. Le comportement obtenu est de toute façon le bon :
        # si le module qui définit le modèle piloté est désinstallé, les
        # définitions qui l'orchestraient n'ont plus d'objet.
        ondelete='cascade',
        domain="[('transient', '=', False)]",
        help="Le modèle métier dont les enregistrements suivront ce processus. "
             "N'importe quel modèle Odoo convient, y compris natif.",
    )
    # Stocké et indexé : c'est par ce champ qu'on retrouve la définition
    # applicable à un enregistrement, et par lui qu'on vérifie qu'une instance
    # ne démarre pas sur le mauvais modèle.
    model_name = fields.Char(
        string="Modèle technique",
        related='model_id.model',
        store=True,
        index=True,
    )
    version = fields.Integer(
        string="Version",
        default=1,
        required=True,
        readonly=True,
        copy=False,
    )
    state = fields.Selection(
        [
            ('draft', "Brouillon"),
            ('published', "Publié"),
            ('archived', "Archivé"),
        ],
        string="État",
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )
    active = fields.Boolean(string="Actif", default=True)

    # ⚠ Le champ qui ferme un trou de sécurité par configuration.
    #
    # Un rôle sans `group_id` — Porteur en tête — n'est porté par personne en
    # permanence : il s'attribue dossier par dossier, par une ligne
    # `instance.actor`. Tant que cette ligne relevait du module métier, chaque
    # `create()` devait penser à la poser, et l'oubli ne se voyait nulle part :
    # ni erreur au chargement, ni erreur au runtime — seulement un déposant qui
    # ne peut pas soumettre son propre dossier, et une transition qui
    # n'apparaît jamais. Les demandes de profil Expert et Investisseur l'ont
    # oublié pendant toute l'Extension 9, et leurs tests étaient au vert parce
    # qu'ils posaient l'acteur eux-mêmes.
    #
    # Le rattachement descend donc dans le moteur : la définition déclare le
    # rôle que porte celui qui démarre l'instance, et `_start_for()` le pose.
    # Un module métier ne peut plus l'oublier — il n'a plus rien à écrire.
    #
    # ⚠ Ce rôle va à l'**initiateur** (`instance.initiator_id`), c'est-à-dire à
    # l'utilisateur qui exécute la création. C'est le bon titulaire quand le
    # déposant remplit son propre dossier — les demandes de profil, le dépôt
    # d'un projet au portail. Ce n'est **pas** le bon quand le dossier est
    # ouvert par un tiers pour le compte d'un autre : le suivi
    # d'industrialisation est ouvert par le CEO et le porteur est celui du
    # projet, pas lui. Ces cas-là continuent d'appeler `add_actor()`
    # explicitement, et c'est volontaire : y poser l'initiateur donnerait un
    # accès `full` au dossier à la personne qui l'a ouvert.
    initiator_role_id = fields.Many2one(
        'opex.workflow.role',
        string="Rôle de l'initiateur",
        ondelete='restrict',
        help="Rôle attribué automatiquement, sur chaque nouvelle instance, à "
             "l'utilisateur qui la démarre — avec un accès complet au dossier. "
             "À renseigner lorsque celui qui ouvre le dossier est aussi celui "
             "qui le porte (Porteur, dans la plupart des processus de dépôt). "
             "À laisser vide lorsque le dossier est ouvert par un tiers pour "
             "le compte d'un autre : le module métier désigne alors lui-même "
             "les acteurs.",
    )

    # `copy=False` : `action_new_version()` recopie étapes et transitions
    # lui-même, parce qu'une copie naïve laisserait les transitions de la
    # nouvelle version pointer vers les étapes de l'ancienne.
    stage_ids = fields.One2many(
        'opex.workflow.stage', 'definition_id', string="Étapes", copy=False)
    transition_ids = fields.One2many(
        'opex.workflow.transition', 'definition_id',
        string="Transitions", copy=False)
    instance_ids = fields.One2many(
        'opex.workflow.instance', 'definition_id', string="Instances")

    # Libellés distincts de ceux des One2many correspondants : deux champs du
    # même modèle portant la même étiquette déclenchent un avertissement au
    # chargement et rendent les deux indiscernables dans les filtres.
    stage_count = fields.Integer(
        string="Nombre d'étapes", compute='_compute_counts')
    transition_count = fields.Integer(
        string="Nombre de transitions", compute='_compute_counts')
    instance_count = fields.Integer(
        string="Nombre d'instances", compute='_compute_counts')

    # L'unicité porte sur (code, version) et non sur `code` seul : sans cela,
    # `action_new_version()` ne pourrait pas créer la v2 d'un processus, qui
    # porte par construction le même code.
    _code_version_uniq = models.Constraint(
        'unique(code, version)',
        "Une définition de workflow existe déjà avec ce code et cette version.",
    )

    def _compute_counts(self):
        for definition in self:
            definition.stage_count = len(definition.stage_ids)
            definition.transition_count = len(definition.transition_ids)
            definition.instance_count = len(definition.instance_ids)

    @api.depends('name', 'version')
    def _compute_display_name(self):
        for definition in self:
            definition.display_name = "%s (v%s)" % (definition.name, definition.version)

    # ------------------------------------------------------------
    # Résolution d'une définition applicable
    # ------------------------------------------------------------

    @api.model
    def _get_for_code(self, code):
        """Définition publiée la plus récente portant ce code.

        Point d'entrée unique du démarrage d'une instance. La recherche est
        restreinte aux définitions **publiées** : un brouillon en cours de
        rédaction ne doit jamais capturer un enregistrement métier, et une
        version archivée ne doit plus en accueillir de nouveau — les instances
        qu'elle porte déjà, elles, continuent de tourner sous elle.
        """
        definition = self.search(
            [('code', '=', code), ('state', '=', 'published')],
            order='version desc', limit=1,
        )
        if not definition:
            raise UserError(_(
                "Aucun workflow publié ne porte le code « %s ». Vérifiez que la "
                "définition existe et qu'elle a bien été publiée."
            ) % code)
        return definition

    def _start_stage(self):
        """L'étape de départ, garantie unique par `_check_graph()`."""
        self.ensure_one()
        return self.stage_ids.filtered('is_start')[:1]

    # ------------------------------------------------------------
    # Validation du graphe
    # ------------------------------------------------------------

    @staticmethod
    def _stage_names(stages):
        return ", ".join("« %s »" % stage.name for stage in stages)

    def _check_graph(self):
        """Refuse un graphe incohérent, en nommant les étapes fautives.

        Les erreurs sont **toutes** collectées avant d'être levées : un
        designer qui corrige son graphe une erreur à la fois republie cinq fois
        pour rien. Et chaque message nomme les étapes concernées — « graphe
        invalide » n'aide personne à corriger sans lire le code.
        """
        self.ensure_one()
        errors = []
        stages = self.stage_ids

        if not stages:
            raise UserError(_(
                "Le workflow « %s » ne contient aucune étape."
            ) % self.name)

        # 1. Exactement une étape de départ.
        starts = stages.filtered('is_start')
        if not starts:
            errors.append(_(
                "Aucune étape n'est marquée « Étape de départ ». Cochez la case "
                "sur l'étape par laquelle le processus commence."
            ))
        elif len(starts) > 1:
            errors.append(_(
                "Plusieurs étapes sont marquées « Étape de départ » : %s. "
                "Il ne peut y en avoir qu'une."
            ) % self._stage_names(starts))

        # 2. Au moins une étape terminale.
        ends = stages.filtered('is_end')
        if not ends:
            errors.append(_(
                "Aucune étape n'est marquée « Étape finale ». Le processus ne "
                "pourrait jamais se clôturer."
            ))

        # 3. Toute transition relie deux étapes de cette définition.
        #    Vérifié avant le parcours du graphe : une transition sortant de la
        #    définition fausserait l'atteignabilité et pourrait faire traverser
        #    le graphe d'un autre workflow.
        foreign = self.transition_ids.filtered(
            lambda t: (t.source_stage_id and t.source_stage_id.definition_id != self)
            or (t.target_stage_id and t.target_stage_id.definition_id != self)
        )
        if foreign:
            errors.append(_(
                "Ces transitions relient des étapes n'appartenant pas à ce "
                "workflow : %s. Une transition ne peut relier que deux étapes "
                "de la même définition."
            ) % ", ".join("« %s »" % t.name for t in foreign))

        local = self.transition_ids - foreign

        if len(starts) == 1 and not foreign:
            # 4. Aucune étape inatteignable depuis le départ.
            outgoing = {}
            for transition in local:
                outgoing.setdefault(transition.source_stage_id.id, []).append(
                    transition.target_stage_id.id)

            reachable = {starts.id}
            frontier = [starts.id]
            while frontier:
                current = frontier.pop()
                for target in outgoing.get(current, ()):
                    if target not in reachable:
                        reachable.add(target)
                        frontier.append(target)

            orphans = stages.filtered(lambda s: s.id not in reachable)
            if orphans:
                errors.append(_(
                    "Ces étapes ne sont atteignables depuis aucune transition "
                    "partant du départ : %s. Ajoutez une transition qui y mène, "
                    "ou supprimez-les."
                ) % self._stage_names(orphans))

            # 5. Aucun cul-de-sac.
            #    Contrôle absent de la spécification, ajouté délibérément : il
            #    attrape exactement l'oubli que produit l'insertion d'une étape
            #    entre deux étapes existantes — on crée la nouvelle étape et la
            #    transition qui y mène, on oublie celle qui en repart.
            dead_ends = stages.filtered(
                lambda s: not s.is_end and not outgoing.get(s.id))
            if dead_ends:
                errors.append(_(
                    "Ces étapes n'ont aucune transition sortante et ne sont pas "
                    "marquées « Étape finale » : %s. Un dossier qui y entre ne "
                    "pourrait plus en sortir."
                ) % self._stage_names(dead_ends))

        if errors:
            raise UserError(
                _("Le workflow « %s » ne peut pas être validé :\n\n") % self.name
                + "\n\n".join("• %s" % error for error in errors)
            )
        return True

    def action_check_graph(self):
        """Bouton « Valider le graphe » : contrôle sans changer d'état."""
        self.ensure_one()
        self._check_graph()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _("Graphe valide"),
                'message': _(
                    "Le workflow « %(name)s » est cohérent : %(stages)s étapes, "
                    "%(transitions)s transitions."
                ) % {
                    'name': self.name,
                    'stages': len(self.stage_ids),
                    'transitions': len(self.transition_ids),
                },
                'sticky': False,
            },
        }

    # ------------------------------------------------------------
    # Cycle de vie
    # ------------------------------------------------------------

    def action_publish(self):
        """Rend la définition utilisable par `start_workflow()`."""
        for definition in self:
            definition._check_graph()
            definition.state = 'published'
        return True

    def action_back_to_draft(self):
        for definition in self:
            if definition.instance_ids:
                raise UserError(_(
                    "Le workflow « %(name)s » porte %(count)s instance(s) en "
                    "cours : il ne peut pas repasser en brouillon. Créez plutôt "
                    "une nouvelle version."
                ) % {'name': definition.name, 'count': len(definition.instance_ids)})
            definition.state = 'draft'
        return True

    def action_new_version(self):
        """Duplique la définition en version + 1 et archive l'ancienne.

        Les instances en cours **restent rattachées à la version sous laquelle
        elles ont démarré** : c'est ce qui rend l'audit trail honnête six mois
        plus tard, quand on relit pourquoi un dossier est passé par une étape
        qui n'existe plus.

        La copie est faite à la main plutôt que par `copy()` : les One2many sont
        en `copy=False`, sinon les transitions dupliquées pointeraient vers les
        étapes de l'ancienne version. On recopie donc les étapes, on garde la
        correspondance ancienne → nouvelle, et on recâble les transitions
        dessus.
        """
        self.ensure_one()
        new_definition = self.copy({
            'name': self.name,
            'code': self.code,
            'version': self.version + 1,
            'state': 'draft',
            'active': True,
        })

        stage_map = {}
        for stage in self.stage_ids:
            stage_map[stage.id] = stage.copy({'definition_id': new_definition.id}).id

        for transition in self.transition_ids:
            transition.copy({
                'definition_id': new_definition.id,
                'source_stage_id': stage_map.get(transition.source_stage_id.id),
                'target_stage_id': stage_map.get(transition.target_stage_id.id),
            })

        self.write({'state': 'archived', 'active': False})

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': new_definition.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_instances(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Instances de %s") % self.name,
            'res_model': 'opex.workflow.instance',
            'view_mode': 'list,form',
            'domain': [('definition_id', '=', self.id)],
            'context': {'default_definition_id': self.id},
        }
