from odoo import _, api, fields, models
from odoo.exceptions import UserError

INDUSTRIALISATION_WORKFLOW_CODE = 'innovation_industrialisation'


class Industrialisation(models.Model):
    """Section 27 — le suivi de l'industrialisation.

    Le cahier des charges demande de suivre « l'état d'industrialisation ».
    Il n'y a pourtant **aucun champ d'état ici**, et c'est le point.

    Un `industrialisation_etat = fields.Selection([...])` aurait fait l'affaire
    et se serait glissé sous le test qui garde le projet — celui-ci vérifie
    l'absence d'un champ nommé `state`, il n'aurait rien vu passer sous un
    autre nom. Un test vert qui ne prouve rien, exactement le piège qu'on
    s'est promis d'éviter.

    L'état est donc `workflow_stage_id`, piloté par une définition configurée
    en données. Conséquence concrète : ajouter une étape « Certification » entre
    Production pilote et Déploiement se fait au configurateur, comme le Demo
    Day, sans toucher à ce fichier.

    Enregistrement **distinct du projet**, et non des champs de plus sur
    lui. Le projet suit déjà son propre workflow ; deux instances sur le même
    enregistrement lui donneraient deux étapes courantes et un seul champ
    `workflow_stage_id` pour les porter.
    """

    _name = 'opex.innovation.industrialisation'
    _description = "Industrialisation d'un projet"
    _inherit = ['mail.thread', 'opex.workflow.mixin']
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

    date_debut = fields.Date(
        string="Démarrage",
        default=fields.Date.context_today,
        required=True,
    )
    echeance = fields.Date(
        string="Échéance visée",
        tracking=True,
        help="Date à laquelle l'industrialisation doit être achevée.",
    )
    en_retard = fields.Boolean(
        string="En retard", compute='_compute_en_retard')

    partenaire_ids = fields.Many2many(
        'res.partner',
        'opex_industrialisation_partner_rel',
        'industrialisation_id', 'partner_id',
        string="Partenaires",
        help="Industriels, sous-traitants, laboratoires ou institutions "
             "associés à la mise en production.",
    )
    resultats = fields.Text(
        string="Résultats",
        help="Ce qui a effectivement été produit, mesuré, mis en service.",
    )

    # Le financement n'est pas ressaisi ici : il vit sur le projet, et le
    # recopier créerait un second montant à tenir à jour.
    currency_id = fields.Many2one(related='project_id.currency_id')
    financement_obtenu = fields.Monetary(
        related='project_id.financement_obtenu',
        string="Financement obtenu",
        currency_field='currency_id',
    )
    progression_financement = fields.Float(
        related='project_id.progression_financement',
        string="Progression du financement",
    )

    # **Couture refermée par l'Extension 16.**
    #
    # La section 27 liste « livrables » parmi ce que le cluster suit. Jusqu'ici,
    # faute du modèle `opex.innovation.deliverable`, ce champ exposait les
    # **documents** du projet — réel, mais pas équivalent : un document déposé
    # n'est pas un livrable validé par un expert.
    #
    # Il pointe désormais vers les vrais livrables de l'accompagnement. Comme
    # annoncé, rien d'autre de ce modèle n'a bougé.
    #
    # Un `related='project_id.accompagnement_id.deliverable_ids'` aurait été
    # plus court, et Odoo l'a refusé en avertissant : `accompagnement_id` est
    # lui-même calculé et non stocké, donc non cherchable, et le moteur de
    # recalcul ne sait plus quels enregistrements réviser quand un livrable
    # change. Un calcul direct, lui, repose la question à chaque lecture.
    livrable_ids = fields.Many2many(
        'opex.innovation.deliverable',
        string="Livrables",
        compute='_compute_livrable_ids')
    livrable_count = fields.Integer(
        string="Livrables validés", compute='_compute_livrable_ids')

    def _compute_livrable_ids(self):
        """Les livrables du projet, et le compte de ceux qui sont **validés**.

        Un compteur qui inclurait les livrables refusés donnerait au cluster une
        avance qui n'existe pas.
        """
        Deliverable = self.env['opex.innovation.deliverable'].sudo()
        for record in self:
            livrables = Deliverable.search(
                [('project_id', '=', record.project_id.id)])
            record.livrable_ids = livrables
            record.livrable_count = len(livrables.filtered(
                lambda d: d.workflow_stage_id.code == 'validated'))

    @api.depends('project_id.name')
    def _compute_name(self):
        for record in self:
            record.name = _("Industrialisation — %s") % (
                record.project_id.name or '')


    @api.depends('echeance', 'workflow_state')
    def _compute_en_retard(self):
        today = fields.Date.context_today(self)
        for record in self:
            record.en_retard = bool(
                record.echeance
                and record.workflow_state == 'running'
                and record.echeance < today
            )

    _project_uniq = models.Constraint(
        'unique(project_id)',
        "Ce projet a déjà un suivi d'industrialisation.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record.start_workflow(INDUSTRIALISATION_WORKFLOW_CODE)
            # Le porteur et le cluster sont acteurs dès l'ouverture : sans eux,
            # personne ne peut faire avancer le suivi qu'on vient de créer.
            record._grant_initial_actors()
        return records

    def _grant_initial_actors(self):
        self.ensure_one()
        instance = self.workflow_instance_id
        if not instance:
            return
        porteur_role = self.env.ref('opex_workflow.role_porteur',
                                    raise_if_not_found=False)
        porteur_user = self.project_id.partner_id.user_ids[:1]
        if porteur_role and porteur_user:
            instance.add_actor(porteur_role, porteur_user, 'full')

    # ------------------------------------------------------------
    # Ouverture depuis le projet
    # ------------------------------------------------------------

    @api.model
    def open_for(self, project):
        """Ouvre le suivi d'industrialisation d'un projet.

        Refuse si le projet n'est pas parvenu à l'étape qui la justifie. Le
        contrôle porte sur `workflow_stage_id`, jamais sur un champ métier :
        c'est le workflow qui dit où en est le dossier.
        """
        project.ensure_one()
        existing = self.search([('project_id', '=', project.id)], limit=1)
        if existing:
            return existing

        stage = project.workflow_stage_id.code
        if stage not in ('financement', 'industrialisation'):
            raise UserError(_(
                "« %(projet)s » est à l'étape « %(etape)s ». "
                "L'industrialisation s'ouvre à partir du financement."
            ) % {
                'projet': project.display_name,
                'etape': project.workflow_stage_label or _("inconnue"),
            })
        return self.create({'project_id': project.id})
