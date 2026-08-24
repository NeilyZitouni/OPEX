from odoo import _, api, fields, models
from odoo.exceptions import UserError


class RoadmapTemplate(models.Model):
    """Les phases de la roadmap — référentiel semé, pas une liste en dur.

    Section 22 : Validation, Produit, Marché, Industrialisation.

    ⚠ **Configurables, et c'est explicitement demandé.** Le même raisonnement
    que pour les points de remédiation de l'Extension 14 : un cluster qui veut
    une cinquième phase — « Certification », « Export » — l'ajoute au
    référentiel, sans développement. Les quatre phases du document sont un
    contenu par défaut, pas une structure.

    Modèle distinct de `opex.innovation.roadmap.phase` : celui-ci est le modèle
    (au sens de gabarit), celle-là est l'exemplaire attaché à un
    accompagnement. Confondre les deux obligerait à un `accompagnement_id`
    facultatif, et un enregistrement sans accompagnement serait tantôt un
    gabarit, tantôt une phase orpheline.
    """

    _name = 'opex.innovation.roadmap.template'
    _description = "Phase type de roadmap"
    _order = 'sequence, id'

    name = fields.Char(string="Phase", required=True, translate=True)
    code = fields.Char(string="Code", required=True, index=True)
    sequence = fields.Integer(string="Séquence", default=10)
    description = fields.Text(
        string="Ce que la phase recouvre",
        translate=True,
        help="Affiché au porteur sous le nom de la phase.",
    )
    active = fields.Boolean(string="Actif", default=True)

    _code_uniq = models.Constraint(
        'unique(code)', "Le code d'une phase type doit être unique.")


class RoadmapPhase(models.Model):
    """Une phase de la roadmap d'un accompagnement — section 22.

    ⚠ **Cette phase porte un champ `state`, et le livrable non.** Ce n'est pas
    une incohérence, c'est la ligne de partage.

    Une phase est une case à trois positions : à faire, en cours, faite. Elle
    n'a ni acteur désigné, ni condition d'entrée, ni notification, ni chemin de
    refus, ni historique à conserver. Lui donner une instance de workflow —
    donc une définition, des transitions, des rôles, un journal d'audit — serait
    de la cérémonie pour un compteur d'avancement.

    Un livrable, lui, a un valideur, un chemin de rejet, des versions
    successives et des notifications à chaque passage. C'est un processus, et
    c'est le moteur qui le porte.

    La règle « pas de champ `state` » vise l'avancement d'un dossier dans un
    processus métier. Elle ne proscrit pas les marqueurs simples — le même
    arbitrage a été rendu pour `opex.innovation.evaluation` à l'Extension 13 et
    pour `opex.innovation.final.evaluation` à l'Extension 17.
    """

    _name = 'opex.innovation.roadmap.phase'
    _description = "Phase de roadmap"
    _order = 'accompagnement_id, sequence, id'

    accompagnement_id = fields.Many2one(
        'opex.innovation.accompagnement',
        string="Accompagnement",
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(string="Phase", required=True, translate=True)
    code = fields.Char(string="Code", index=True)
    sequence = fields.Integer(string="Séquence", default=10)
    description = fields.Text(string="Ce que la phase recouvre")

    state = fields.Selection(
        [
            ('todo', "À faire"),
            ('in_progress', "En cours"),
            ('done', "Terminée"),
        ],
        string="Avancement",
        default='todo',
        required=True,
        index=True,
    )

    @api.depends('name', 'accompagnement_id.display_name')
    def _compute_display_name(self):
        for phase in self:
            phase.display_name = phase.name or ''

    def action_start(self):
        self.write({'state': 'in_progress'})
        return True

    def action_done(self):
        self.write({'state': 'done'})
        return True

    def action_reset(self):
        self.write({'state': 'todo'})
        return True


class Accompagnement(models.Model):
    """Section 21 — l'espace dédié au projet accompagné.

    « Après confirmation : Projet accepté → Expert/Mentor sélectionné →
    Accompagnement. On crée un espace dédié au projet. »

    C'est ici — et nulle part ailleurs — qu'on crée le `project.project` lié et
    qu'on renseigne `project_id` sur le projet d'innovation. Le champ existait
    depuis l'Extension 10, délibérément vide : brancher la gestion de projet
    native d'Odoo n'a de sens qu'une fois l'accompagnement réellement engagé.
    Un `project.project` créé au dépôt aurait produit un projet vide pour chaque
    candidature, y compris celles qui n'aboutissent pas.
    """

    _name = 'opex.innovation.accompagnement'
    _description = "Accompagnement d'un projet d'innovation"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_debut desc, id desc'

    project_id = fields.Many2one(
        'opex.innovation.project',
        string="Projet",
        required=True,
        ondelete='cascade',
        index=True,
    )
    partner_id = fields.Many2one(
        related='project_id.partner_id', string="Porteur", store=True)
    name = fields.Char(
        string="Intitulé", compute='_compute_name', store=True)

    # Section 21 : « Expert : Ahmed X, Mentor : Y ». Deux rôles distincts, deux
    # champs — le document les nomme séparément et ils ne recouvrent pas la même
    # mission (expertise technique / accompagnement humain).
    expert_id = fields.Many2one(
        'res.partner', string="Expert", ondelete='set null', tracking=True)
    mentor_id = fields.Many2one(
        'res.partner', string="Mentor", ondelete='set null', tracking=True)

    date_debut = fields.Date(
        string="Début", default=fields.Date.context_today, required=True)
    date_fin = fields.Date(string="Fin prévue", tracking=True)
    objectifs = fields.Text(
        string="Objectifs",
        help="Ce que l'accompagnement doit avoir produit à son terme.",
    )

    phase_ids = fields.One2many(
        'opex.innovation.roadmap.phase', 'accompagnement_id',
        string="Roadmap")
    deliverable_ids = fields.One2many(
        'opex.innovation.deliverable', 'accompagnement_id',
        string="Livrables")

    progression = fields.Float(
        string="Progression",
        compute='_compute_progression',
        store=True,
        digits=(5, 2),
        help="Part de la roadmap et des livrables achevés, en pourcentage.",
    )

    task_project_id = fields.Many2one(
        'project.project',
        string="Espace de travail",
        ondelete='set null',
        copy=False,
        help="Le projet Odoo natif créé pour cet accompagnement. Section 21 : "
             "« on crée un espace dédié au projet ».",
    )

    active = fields.Boolean(string="Actif", default=True)

    _project_uniq = models.Constraint(
        'unique(project_id)',
        "Ce projet a déjà un accompagnement en cours.",
    )

    @api.depends('project_id.name')
    def _compute_name(self):
        for record in self:
            record.name = _("Accompagnement — %s") % (
                record.project_id.name or '')

    @api.depends('phase_ids.state',
                 'deliverable_ids.workflow_stage_id')
    def _compute_progression(self):
        """Section 21 : « Progression 80 % ».

        Phases terminées et livrables validés comptent pour un, le reste pour
        zéro. Une pondération plus fine — poids par phase, part des livrables —
        serait défendable, mais elle demanderait au cluster de régler des poids
        qu'il n'a pas. Un ratio que chacun peut recalculer de tête vaut mieux
        qu'un chiffre juste que personne ne sait expliquer.
        """
        for record in self:
            phases = record.phase_ids
            livrables = record.deliverable_ids
            total = len(phases) + len(livrables)
            if not total:
                record.progression = 0.0
                continue
            faits = len(phases.filtered(lambda p: p.state == 'done'))
            faits += len(livrables.filtered(
                lambda d: d.workflow_stage_id.code == 'validated'))
            record.progression = faits / total * 100.0

    # ------------------------------------------------------------
    # Ouverture
    # ------------------------------------------------------------

    @api.model
    def open_for(self, project, expert=None, mentor=None):
        """Ouvre l'accompagnement d'un projet, avec sa roadmap.

        Refuse si le projet n'y est pas encore. Le contrôle porte sur
        `workflow_stage_id`, jamais sur un champ métier : c'est le workflow qui
        dit où en est le dossier.
        """
        project.ensure_one()
        existing = self.search([('project_id', '=', project.id)], limit=1)
        if existing:
            return existing

        if project.workflow_stage_id.code not in ('matching', 'accompagnement'):
            raise UserError(_(
                "« %(projet)s » est à l'étape « %(etape)s ». "
                "L'accompagnement s'ouvre à partir du matching."
            ) % {
                'projet': project.display_name,
                'etape': project.workflow_stage_label or _("inconnue"),
            })

        return self.create({
            'project_id': project.id,
            'expert_id': expert.id if expert else False,
            'mentor_id': mentor.id if mentor else False,
        })

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record._seed_roadmap()
            record._create_workspace()
        return records

    def _seed_roadmap(self):
        """Recopie le référentiel de phases dans cet accompagnement.

        ⚠ Une **copie**, pas une référence. Modifier le référentiel plus tard ne
        doit pas réécrire la roadmap d'un accompagnement déjà en cours : le
        porteur verrait ses phases changer de nom sous ses yeux. Le référentiel
        décide de ce qu'on propose au démarrage, pas de ce qui a été convenu.
        """
        self.ensure_one()
        if self.phase_ids:
            return
        Template = self.env['opex.innovation.roadmap.template'].sudo()
        Phase = self.env['opex.innovation.roadmap.phase'].sudo()
        for template in Template.search([]):
            Phase.create({
                'accompagnement_id': self.id,
                'name': template.name,
                'code': template.code,
                'sequence': template.sequence,
                'description': template.description,
            })

    def _create_workspace(self):
        """Section 21 — « on crée un espace dédié au projet ».

        C'est le seul endroit du module qui crée un `project.project`, et le
        seul qui renseigne `project_id` sur le projet d'innovation. En `sudo()` :
        la création de l'espace est de la comptabilité interne, pas une donnée
        que l'utilisateur saisit — et le porteur n'a aucun droit sur
        `project.project`.
        """
        self.ensure_one()
        if self.task_project_id:
            return
        workspace = self.env['project.project'].sudo().create({
            'name': self.project_id.name or self.name,
            'partner_id': self.project_id.partner_id.id,
        })
        self.sudo().task_project_id = workspace.id
        # Le lien retour, resté vide depuis l'Extension 10 en attendant ce
        # moment précis.
        self.project_id.sudo().project_id = workspace.id

    def action_open_workspace(self):
        self.ensure_one()
        if not self.task_project_id:
            raise UserError(_("Aucun espace de travail n'est rattaché."))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'project.project',
            'res_id': self.task_project_id.id,
            'view_mode': 'form',
            'target': 'current',
        }


class ProjectAccompagnement(models.Model):
    """L'accompagnement vu depuis le projet."""

    _inherit = 'opex.innovation.project'

    accompagnement_id = fields.Many2one(
        'opex.innovation.accompagnement',
        string="Accompagnement",
        compute='_compute_accompagnement_id',
    )

    def _compute_accompagnement_id(self):
        Accompagnement = self.env['opex.innovation.accompagnement'].sudo()
        for project in self:
            project.accompagnement_id = Accompagnement.search(
                [('project_id', '=', project.id)], limit=1)
