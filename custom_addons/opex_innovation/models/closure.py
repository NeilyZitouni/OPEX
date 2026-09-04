from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ProjectClosure(models.Model):
    """Section 28 — le bilan de clôture.

    « Le système génère un bilan : date de dépôt, date d'acceptation, durée
    d'accompagnement, experts impliqués, financement obtenu, livrables
    réalisés, résultat final. »

    **Toutes ces valeurs sont figées à la génération.** C'est un bilan, pas
    une vue. Un bilan calculé à l'affichage changerait après coup — le jour où
    un expert est retiré du dossier, où un document est supprimé, où le montant
    est corrigé — et un bilan qui change n'est pas un bilan.

    Les dates et la durée d'accompagnement ne sont **pas** saisies : elles sont
    lues dans l'historique du workflow, qui est le journal d'audit du moteur et
    la seule source qui sache réellement quand le dossier est passé où.
    """

    _name = 'opex.innovation.closure'
    _description = "Bilan de clôture d'un projet"
    _order = 'date_bilan desc, id desc'

    project_id = fields.Many2one(
        'opex.innovation.project',
        string="Projet",
        required=True,
        ondelete='cascade',
        index=True,
        readonly=True,
    )
    project_name = fields.Char(string="Nom du projet", readonly=True)
    date_bilan = fields.Datetime(
        string="Bilan généré le",
        default=fields.Datetime.now,
        readonly=True,
    )
    generated_by_id = fields.Many2one(
        'res.users', string="Généré par", readonly=True, ondelete='set null')

    # ------------------------------------------------------------
    # Les sept lignes du bilan
    # ------------------------------------------------------------

    date_depot = fields.Datetime(string="Date de dépôt", readonly=True)
    date_acceptation = fields.Datetime(
        string="Date d'acceptation", readonly=True)
    duree_accompagnement_jours = fields.Integer(
        string="Durée d'accompagnement (jours)",
        readonly=True,
        help="Temps passé à l'étape Accompagnement, mesuré sur l'historique "
             "du workflow. Nul si le projet n'y est jamais passé.",
    )
    expert_ids = fields.Many2many(
        'res.partner',
        'opex_closure_expert_rel', 'closure_id', 'partner_id',
        string="Experts impliqués",
        readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency', string="Devise", readonly=True)
    financement_obtenu = fields.Monetary(
        string="Financement obtenu",
        currency_field='currency_id',
        readonly=True,
    )
    livrable_count = fields.Integer(
        string="Livrables réalisés", readonly=True)
    resultat_final = fields.Selection(
        [
            ('reussi', "Projet abouti"),
            ('partiel', "Abouti partiellement"),
            ('abandonne', "Non abouti"),
        ],
        string="Résultat final",
        required=True,
        readonly=True,
    )
    synthese = fields.Text(string="Synthèse", readonly=True)

    _project_uniq = models.Constraint(
        'unique(project_id)',
        "Ce projet a déjà un bilan de clôture.",
    )

    @api.depends('project_name', 'date_bilan')
    def _compute_display_name(self):
        for closure in self:
            closure.display_name = _("Bilan — %s") % (closure.project_name or '')

    def write(self, vals):
        """Un bilan figé ne se retouche pas.

        Même raisonnement que les versions de dossier et que le journal du
        moteur : un bilan modifiable ne prouve rien de ce qui s'est passé.
        """
        if not self.env.su:
            raise UserError(_(
                "Un bilan de clôture ne peut pas être modifié. Si les faits "
                "ont changé, supprimez-le et générez-en un nouveau."))
        return super().write(vals)

    # ------------------------------------------------------------
    # La génération
    # ------------------------------------------------------------

    @api.model
    def generate_for(self, project, resultat_final='reussi', synthese=False):
        """Produit le bilan d'un projet, en lisant son historique.

        Refuse deux fois : si le dossier n'est pas clos, et s'il a déjà un
        bilan. Régénérer silencieusement écraserait un document daté.
        """
        project.ensure_one()
        existing = self.search([('project_id', '=', project.id)], limit=1)
        if existing:
            raise UserError(_(
                "« %s » a déjà un bilan de clôture.") % project.display_name)

        instance = project.workflow_instance_id
        if not instance or instance.state != 'done':
            raise UserError(_(
                "Le bilan se génère à la clôture. « %(projet)s » est encore à "
                "l'étape « %(etape)s »."
            ) % {
                'projet': project.display_name,
                'etape': project.workflow_stage_label or _("inconnue"),
            })

        facts = self._read_history(instance)
        return self.create({
            'project_id': project.id,
            'project_name': project.name,
            'generated_by_id': self.env.user.id,
            'date_depot': facts['date_depot'],
            'date_acceptation': facts['date_acceptation'],
            'duree_accompagnement_jours': facts['duree_accompagnement'],
            'expert_ids': [(6, 0, self._experts_of(instance).ids)],
            'currency_id': project.currency_id.id,
            'financement_obtenu': project.financement_obtenu,
            'livrable_count': self._livrables_realises(project),
            'resultat_final': resultat_final,
            'synthese': synthese or False,
        })

    @api.model
    def _livrables_realises(self, project):
        """« Livrables réalisés » — enfin ce que la section 28 demandait.

        Couture refermée. Jusqu'à l'Extension 16, ce chiffre comptait les
        `opex.innovation.document` du projet, faute de modèle de livrable. Un
        document déposé n'est pas un livrable validé par un expert : le bilan
        annonçait donc systématiquement plus que la réalité, et il était figé
        — donc faux pour toujours.

        Il compte maintenant les livrables **validés**, et eux seuls. Un
        livrable déposé mais refusé n'a pas été réalisé.
        """
        Deliverable = self.env['opex.innovation.deliverable'].sudo()
        return Deliverable.search_count([
            ('project_id', '=', project.id),
            ('workflow_stage_id.code', '=', 'validated'),
        ])

    @api.model
    def _read_history(self, instance):
        """Les trois faits datés, lus dans le journal d'audit du moteur.

        L'historique est parcouru **en compréhension**, jamais avec
        `mapped()`. Un projet qui repasse par l'accompagnement après une
        réévaluation y entre deux fois : `mapped('to_stage_id.code')`
        dédoublonnerait, le second séjour disparaîtrait du résultat, et la
        durée d'accompagnement serait sous-évaluée sans que rien ne le signale.
        """
        lines = instance.sudo().history_ids.sorted('id')
        entries = [
            (line.to_stage_id.code, line.date)
            for line in lines if line.to_stage_id
        ]

        date_depot = entries[0][1] if entries else False
        date_acceptation = next(
            (date for code, date in entries if code == 'accepted'), False)

        # Durée d'accompagnement : somme de **tous** les séjours à l'étape,
        # chacun mesuré de l'entrée à la sortie suivante. Le séjour en cours,
        # s'il y en a un, court jusqu'à maintenant.
        duree = 0
        entree = None
        for code, date in entries:
            if code == 'accompagnement':
                entree = entree or date
            elif entree:
                duree += (date - entree).days
                entree = None
        if entree:
            duree += (fields.Datetime.now() - entree).days

        return {
            'date_depot': date_depot,
            'date_acceptation': date_acceptation,
            'duree_accompagnement': duree,
        }

    @api.model
    def _experts_of(self, instance):
        """Experts et mentors ayant réellement été acteurs du dossier.

        Lu sur `instance.actor`, y compris les acteurs retirés : quelqu'un qui
        a accompagné le projet puis a été révoqué a bien été impliqué, et un
        bilan qui l'oublierait serait faux.
        """
        role = self.env.ref('opex_workflow.role_expert',
                            raise_if_not_found=False)
        if not role:
            return self.env['res.partner'].browse()
        actors = instance.sudo().actor_ids.filtered(
            lambda a: a.role_id == role)
        return actors.mapped('user_id.partner_id')


class ProjectClosureLink(models.Model):
    """Le bilan vu depuis le projet."""

    _inherit = 'opex.innovation.project'

    closure_id = fields.Many2one(
        'opex.innovation.closure',
        string="Bilan de clôture",
        compute='_compute_closure_id',
        help="Généré à la clôture du dossier.",
    )
    industrialisation_id = fields.Many2one(
        'opex.innovation.industrialisation',
        string="Industrialisation",
        compute='_compute_industrialisation_id',
    )

    def _compute_closure_id(self):
        Closure = self.env['opex.innovation.closure'].sudo()
        for project in self:
            project.closure_id = Closure.search(
                [('project_id', '=', project.id)], limit=1)

    def _compute_industrialisation_id(self):
        Industrialisation = self.env[
            'opex.innovation.industrialisation'].sudo()
        for project in self:
            project.industrialisation_id = Industrialisation.search(
                [('project_id', '=', project.id)], limit=1)

    def action_generate_closure(self):
        """Bouton « Générer le bilan » du back-office."""
        self.ensure_one()
        closure = self.env['opex.innovation.closure'].generate_for(self)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'opex.innovation.closure',
            'res_id': closure.id,
            'view_mode': 'form',
            'target': 'current',
        }
