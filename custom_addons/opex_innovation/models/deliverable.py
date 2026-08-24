from odoo import _, api, fields, models
from odoo.exceptions import UserError

DELIVERABLE_WORKFLOW_CODE = 'innovation_deliverable'


class DeliverableVersion(models.Model):
    """Une version figée d'un livrable — section 24.

    > « Si correction : Livrable → Correction demandée → Nouvelle version →
    >   Validation. **L'historique est conservé.** »

    Même raisonnement que les versions de dossier de l'Extension 14 et que le
    bilan de clôture de l'Extension 17 : une archive modifiable ne prouve rien
    de ce que le livrable contenait au moment où l'expert l'a refusé.

    Le motif de la correction est stocké **sur la version refusée**, pas sur le
    livrable. Sur le livrable, il serait écrasé au refus suivant, et on perdrait
    la raison du premier — c'est-à-dire justement ce que l'historique doit
    montrer.
    """

    _name = 'opex.innovation.deliverable.version'
    _description = "Version d'un livrable"
    _order = 'deliverable_id, version desc, id desc'

    deliverable_id = fields.Many2one(
        'opex.innovation.deliverable',
        string="Livrable",
        required=True,
        ondelete='cascade',
        index=True,
        readonly=True,
    )
    version = fields.Integer(string="Version", required=True, readonly=True)
    file = fields.Binary(string="Fichier", attachment=True, readonly=True)
    filename = fields.Char(string="Nom du fichier", readonly=True)
    date = fields.Datetime(
        string="Déposée le", default=fields.Datetime.now, readonly=True)
    author_id = fields.Many2one(
        'res.partner', string="Déposée par", readonly=True,
        ondelete='set null')
    motif_correction = fields.Text(
        string="Motif de la correction demandée",
        readonly=True,
        help="Ce que l'expert a reproché à cette version-là.",
    )

    @api.depends('deliverable_id.name', 'version')
    def _compute_display_name(self):
        for record in self:
            record.display_name = "%s — v%s" % (
                record.deliverable_id.name or '', record.version)

    def write(self, vals):
        if not self.env.su:
            raise UserError(_(
                "Une version archivée d'un livrable ne peut pas être "
                "modifiée : c'est ce qui donne sa valeur à l'historique."))
        return super().write(vals)


class Deliverable(models.Model):
    """Sections 23 et 24 — un livrable, et son cycle de vie.

    ⚠ **Aucun champ `state` ici.** Le cycle de vie d'un livrable est un petit
    processus — quatre étapes, un chemin de refus, un valideur désigné, des
    notifications à chaque passage — et c'est le moteur qui le porte, comme
    pour le projet et pour l'industrialisation.

    C'est la **quatrième instance** du moteur, sur un quatrième modèle :
    demande de profil, projet d'innovation, Smart Crowdfunding,
    industrialisation, et maintenant livrable. Aucune ligne de Python n'a été
    ajoutée à `opex_workflow` pour aucune des cinq.

    Le gain concret : « demander une seconde validation par le mentor avant
    l'expert » s'obtient au configurateur, en insérant une étape — exactement
    l'exercice du Demo Day.
    """

    _name = 'opex.innovation.deliverable'
    _description = "Livrable d'accompagnement"
    _inherit = ['mail.thread', 'opex.workflow.mixin']
    _order = 'accompagnement_id, deadline, id'

    accompagnement_id = fields.Many2one(
        'opex.innovation.accompagnement',
        string="Accompagnement",
        required=True,
        ondelete='cascade',
        index=True,
    )
    project_id = fields.Many2one(
        related='accompagnement_id.project_id', string="Projet", store=True)
    partner_id = fields.Many2one(
        related='accompagnement_id.partner_id', string="Porteur", store=True)

    name = fields.Char(string="Livrable", required=True, tracking=True)
    description = fields.Text(string="Ce qui est attendu")
    deadline = fields.Date(string="Échéance", tracking=True)
    en_retard = fields.Boolean(string="En retard", compute='_compute_en_retard')

    file = fields.Binary(string="Fichier", attachment=True)
    filename = fields.Char(string="Nom du fichier")
    version = fields.Integer(
        string="Version",
        default=1,
        readonly=True,
        help="Incrémentée à chaque nouveau dépôt après une correction "
             "demandée. Les versions précédentes restent consultables.",
    )
    history_ids = fields.One2many(
        'opex.innovation.deliverable.version', 'deliverable_id',
        string="Versions précédentes")

    @api.depends('deadline', 'workflow_stage_id')
    def _compute_en_retard(self):
        today = fields.Date.context_today(self)
        for record in self:
            record.en_retard = bool(
                record.deadline
                and record.deadline < today
                and record.workflow_stage_id.code != 'validated'
            )

    # ------------------------------------------------------------
    # Démarrage
    # ------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record.start_workflow(DELIVERABLE_WORKFLOW_CODE)
            record._grant_actors()
        return records

    def _grant_actors(self):
        """Le porteur dépose, l'expert valide — chacun acteur de ce livrable-ci.

        ⚠ Sur **ce** livrable, pas sur tous. C'est le principe de visibilité des
        documents sources : être expert du cluster ne donne accès à rien ; c'est
        la ligne d'acteur qui donne accès à celui-là.
        """
        self.ensure_one()
        instance = self.workflow_instance_id
        if not instance:
            return

        porteur_role = self.env.ref('opex_workflow.role_porteur',
                                    raise_if_not_found=False)
        expert_role = self.env.ref('opex_workflow.role_expert',
                                   raise_if_not_found=False)

        porteur = self.accompagnement_id.project_id.partner_id.user_ids[:1]
        if porteur_role and porteur:
            instance.add_actor(porteur_role, porteur, 'full')

        # Expert et mentor portent tous deux le rôle qui valide : la section 24
        # dit « l'expert/mentor reçoit une notification », sans les distinguer.
        for partner in (self.accompagnement_id.expert_id
                        | self.accompagnement_id.mentor_id):
            user = partner.user_ids[:1]
            if expert_role and user:
                instance.add_actor(expert_role, user, 'limited')

    # ------------------------------------------------------------
    # Section 24 — la nouvelle version après une correction
    # ------------------------------------------------------------

    def submit_new_version(self, file=False, filename=False, user=None):
        """Archive la version refusée, dépose la nouvelle, franchit l'étape.

        ⚠ L'ordre compte. On fige **avant** d'écrire : après, le champ `file`
        porte déjà le nouveau contenu et la version archivée serait un double
        de la version courante. L'historique existerait, et ne contiendrait
        rien d'utile.

        La transition, elle, passe par le moteur comme les autres. Ce que fait
        cette méthode, c'est ce que le moteur ne sait pas faire : recopier un
        fichier dans une archive. Elle ne décide pas du droit de passer — c'est
        `_check_transition_allowed()` qui tranche, et lui seul.
        """
        self.ensure_one()
        user = user or self.env.user

        if self.workflow_stage_id.code != 'correction_requested':
            raise UserError(_(
                "Une nouvelle version ne se dépose qu'après une demande de "
                "correction. « %(livrable)s » est à l'étape « %(etape)s »."
            ) % {
                'livrable': self.display_name,
                'etape': self.workflow_stage_label or _("inconnue"),
            })

        self._archive_current_version()

        values = {'version': self.version + 1}
        if file:
            values.update({'file': file, 'filename': filename or self.filename})
        self.sudo().write(values)

        transition = self._transition('deliverable_resubmit')
        return self.with_user(user).workflow_do_transition(transition)

    def _archive_current_version(self):
        """Fige la version courante, avec le motif du refus qui l'a visée.

        Le motif se lit dans le **journal d'audit du moteur** : c'est le
        commentaire obligatoire de la transition « Demander une correction ».
        Le recopier sur le livrable au moment du refus aurait été plus simple à
        lire, et faux dès le second refus — il aurait écrasé le premier.
        """
        self.ensure_one()
        instance = self.workflow_instance_id
        motif = False
        if instance:
            refus = [
                line for line in instance.sudo().history_ids.sorted('id')
                if line.to_stage_id.code == 'correction_requested'
            ]
            motif = refus[-1].comment if refus else False

        return self.env['opex.innovation.deliverable.version'].sudo().create({
            'deliverable_id': self.id,
            'version': self.version,
            'file': self.file,
            'filename': self.filename,
            'author_id': self.partner_id.id,
            'motif_correction': motif,
        })

    def _transition(self, code):
        transition = self.workflow_definition_id.transition_ids.filtered(
            lambda t: t.code == code)
        if not transition:
            raise UserError(_(
                "La transition « %s » n'est pas configurée sur le workflow des "
                "livrables.") % code)
        return transition

    # ------------------------------------------------------------
    # Ce que l'expert doit lire
    # ------------------------------------------------------------

    def correction_history(self):
        """Les corrections demandées, dans l'ordre, avec leur motif.

        ⚠ Construit en compréhension sur l'historique, jamais avec `mapped()` :
        un livrable refusé deux fois repasse par la même étape, et `mapped()`
        sur un Many2one dédoublonne — le second refus disparaîtrait du
        résultat.
        """
        self.ensure_one()
        instance = self.workflow_instance_id
        if not instance:
            return []
        return [
            {
                'date': line.date,
                'auteur': line.user_id.partner_id.display_name or '',
                'motif': line.comment or '',
            }
            for line in instance.sudo().history_ids.sorted('id')
            if line.to_stage_id.code == 'correction_requested'
        ]
