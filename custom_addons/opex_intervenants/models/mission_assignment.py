from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .optional_backends import PROJECT


class MissionAssignment(models.Model):
    """L'affectation de l'intervenant retenu — §15 de Smart Missions.

    **Aucun champ `state`, et ce n'est pas par symétrie décorative.**

    Une affectation n'a pas d'avancement propre : elle naît quand une
    candidature est retenue et vaut jusqu'à la clôture de la mission. Son
    « où en est-on » se lit sur les deux processus qui l'encadrent —
    l'étape de la mission pour l'exécution, l'étape du sous-workflow
    `mission_contract` pour la contractualisation. Lui donner un état
    ferait un troisième récit de la même histoire, et c'est toujours le
    troisième qui se désynchronise.

    C'est la ligne de partage posée par le CLAUDE.md du moteur à propos de
    `roadmap.phase` : un objet sans acteur, sans condition, sans chemin de
    refus et sans historique n'est pas un processus.
    """

    _name = 'opex.mission.assignment'
    _description = "Affectation d'un intervenant à une mission"
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'

    mission_id = fields.Many2one(
        'opex.mission.request',
        string="Appel à mission",
        required=True,
        ondelete='cascade',
        index=True,
    )
    application_id = fields.Many2one(
        'opex.mission.application',
        string="Candidature retenue",
        required=True,
        ondelete='cascade',
        index=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string="Intervenant",
        required=True,
        index=True,
    )
    expert_profile_id = fields.Many2one(
        'opex.innovation.expert.profile',
        string="Profil expert",
        readonly=True,
    )
    source = fields.Selection(
        related='application_id.source',
        string="Canal d'origine",
        readonly=True,
        help="§21 : les deux canaux du §8 restent distinguables jusqu'au bout.",
    )

    # --- Conditions retenues, recopiées de la candidature -------------------
    #
    # Recopiées et non `related` : ce sont les conditions **au moment de
    # l'attribution**. La candidature reste modifiable après coup dans le
    # back-office ; le contrat, lui, doit refléter ce qui a été accepté.
    date_debut = fields.Date(string="Début prévu")
    date_fin = fields.Date(string="Fin prévue")
    duree_jours = fields.Integer(string="Durée retenue (jours)")
    type_tarif = fields.Selection(
        [('tjm', "Taux journalier"), ('forfait', "Forfait global")],
        string="Type de tarif",
    )
    currency_id = fields.Many2one(
        'res.currency',
        string="Devise",
        default=lambda self: self.env.company.currency_id,
    )
    tarif = fields.Monetary(string="Tarif retenu", currency_field='currency_id')
    montant_total = fields.Monetary(
        string="Montant total",
        compute='_compute_montant_total',
        currency_field='currency_id',
        help="Forfait : le tarif tel quel. Taux journalier : tarif × durée.",
    )

    # --- Exécution — posée par le déclencheur de « Démarrer la mission » ----
    #
    # REBRANCHEMENT `project` — ce champ était :
    #
    #     project_id = fields.Many2one(
    #         'project.project', string="Projet d'exécution",
    #         readonly=True, ondelete='set null')
    #
    # `project` n'étant pas installé, la `Many2one` empêchait le registre de
    # démarrer. Même parti que pour `sale.order` sur le constat de service
    # fait : la paire id + libellé conserve ce qui peut l'être, et la
    # relation se rétablit sans migration de données.
    #
    # Attention : la perte de `ondelete='set null'` est réelle et il faut la connaître :
    # un projet supprimé côté Odoo laissera ici un id qui ne pointe plus sur
    # rien. `_backend_record()` applique `exists()` pour cette raison — il
    # rend un recordset vide plutôt qu'un enregistrement fantôme.
    project_ref = fields.Integer(
        string="Projet d'exécution (id)",
        readonly=True,
        copy=False,
        help="L'identifiant du projet créé au démarrage de la mission. Vide "
             "tant que le module Projet n'est pas installé.",
    )
    project_name = fields.Char(
        string="Projet d'exécution",
        readonly=True,
        copy=False,
    )
    project_disponible = fields.Boolean(
        string="Projet disponible",
        compute='_compute_project_disponible',
    )
    task_count = fields.Integer(
        string="Nombre de tâches", compute='_compute_task_count')

    contract_ids = fields.One2many(
        'opex.mission.contract', 'assignment_id', string="Pièces contractuelles")
    contract_count = fields.Integer(
        string="Nombre de pièces", compute='_compute_contract_count')

    nda_required = fields.Boolean(
        related='mission_id.nda_required', string="NDA exigé", readonly=True)
    active = fields.Boolean(string="Actif", default=True)

    # ------------------------------------------------------------
    # Règle 4 du §39 — au niveau de la contrainte, pas de la convention
    # ------------------------------------------------------------
    #
    # « Une mission ne peut avoir qu'un intervenant sélectionné, sauf si le
    #   modèle de mission autorise explicitement plusieurs intervenants. »
    #
    # Elle est tenue à **trois** niveaux, et les trois disent la même chose à
    # trois publics différents :
    #
    # 1. `rule_application_single_selection`, condition de la transition
    #    « Retenir cette candidature » (Extension 1). C'est l'**explication** :
    #    le décideur lit pourquoi le bouton refuse, avant d'avoir cliqué.
    # 2. la contrainte SQL ci-dessous : une même candidature ne produit jamais
    #    deux affectations, quel qu'en soit le chemin — import, script, requête
    #    forgée.
    # 3. `_check_single_assignment()` : le compte par mission, confronté à
    #    `multi_intervenants`. Une contrainte Python ne se contourne que par du
    #    SQL brut ; l'exception étant portée par une **autre table**
    #    (`opex.mission.type`), un index partiel ne pouvait pas l'exprimer.
    #
    # Le premier niveau seul serait une convention : il ne protège que le
    # chemin qui passe par la transition.
    _application_uniq = models.Constraint(
        'unique(application_id)',
        "Cette candidature a déjà produit une affectation.",
    )

    @api.constrains('mission_id', 'active')
    def _check_single_assignment(self):
        """Une seule affectation active par mission — sauf exception du type."""
        for assignment in self:
            mission = assignment.mission_id.sudo()
            if not assignment.active or mission.type_multi_intervenants:
                continue
            others = self.sudo().search_count([
                ('mission_id', '=', mission.id),
                ('active', '=', True),
                ('id', '!=', assignment.id),
            ])
            if others:
                raise ValidationError(_(
                    "L'appel « %(mission)s » a déjà un intervenant affecté, et "
                    "le type de mission « %(type)s » n'en autorise qu'un "
                    "(règle 4 du §39). Retirez l'affectation existante, ou "
                    "cochez « Plusieurs intervenants » sur le type de mission."
                ) % {
                    'mission': mission.display_name,
                    'type': mission.mission_type_id.name or '—',
                })

    # ------------------------------------------------------------
    # Calculs
    # ------------------------------------------------------------

    @api.depends('partner_id', 'mission_id')
    def _compute_display_name(self):
        for assignment in self:
            assignment.display_name = "%s — %s" % (
                assignment.mission_id.name or '',
                assignment.partner_id.display_name or '',
            )

    @api.depends('tarif', 'type_tarif', 'duree_jours')
    def _compute_montant_total(self):
        for assignment in self:
            if assignment.type_tarif == 'tjm':
                assignment.montant_total = \
                    assignment.tarif * (assignment.duree_jours or 0)
            else:
                assignment.montant_total = assignment.tarif

    def _compute_project_disponible(self):
        available = self.env['opex.optional.backend']._backend_available(
            PROJECT)
        for assignment in self:
            assignment.project_disponible = available

    def _project(self):
        """Le projet d'exécution, ou None si `project` n'est pas installé."""
        self.ensure_one()
        return self.env['opex.optional.backend']._backend_record(
            PROJECT, self.project_ref)

    # REBRANCHEMENT `project` — la dépendance était `@api.depends(
    # 'project_id.task_ids')`. Elle rendait le compteur vivant : une tâche
    # ajoutée au projet le mettait à jour tout seul. Sans `project` il n'y a
    # aucune tâche à compter, mais **le jour du rebranchement cette ligne est
    # à remettre**, sans quoi le compteur resterait figé à sa valeur du
    # dernier calcul et le bouton statistique mentirait.
    @api.depends('project_ref')
    def _compute_task_count(self):
        for assignment in self:
            project = assignment._project()
            assignment.task_count = len(project.task_ids) if project else 0

    @api.depends('contract_ids')
    def _compute_contract_count(self):
        for assignment in self:
            assignment.contract_count = len(assignment.contract_ids)

    # ------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------

    def action_view_contracts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Pièces contractuelles"),
            'res_model': 'opex.mission.contract',
            'view_mode': 'list,form',
            'domain': [('assignment_id', '=', self.id)],
            'context': {'default_assignment_id': self.id},
        }

    def action_view_project(self):
        """REBRANCHEMENT `project` — conservée en entier.

        Rend False quand le module est absent : le bouton qui l'appelle est
        masqué par `project_disponible`, mais une action qui ne fait rien
        vaut mieux qu'un 500 si le bouton reparaissait par une vue héritée.
        """
        self.ensure_one()
        project = self._project()
        if project is None:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _("Projet d'exécution"),
            'res_model': PROJECT,
            'view_mode': 'form',
            'res_id': project.id,
        }
