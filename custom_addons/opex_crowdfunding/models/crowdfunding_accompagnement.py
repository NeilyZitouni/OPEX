from odoo import _, api, fields, models
from odoo.exceptions import UserError


class OpexCrowdfundingAccompagnement(models.Model):
    """Le sous-processus d'accompagnement CEO (sections 11 et 12).

    Un sous-workflow complet, avec ses propres états :

        demande → diagnostic → proposition → contrepartie → acceptation
        → missions → jalons → livrables → service fait → évaluation

    Il naît de trois façons — recommandation du comité, demande d'un acteur
    financier, demande directe du porteur — et l'origine reste inscrite : on
    ne traite pas de la même manière un accompagnement qu'on a proposé et un
    accompagnement qu'on nous a demandé.
    """

    _name = 'opex.crowdfunding.accompagnement'
    _description = "Accompagnement CEO"
    _order = 'id desc'
    _rec_name = 'project_id'

    project_id = fields.Many2one(
        'opex.crowdfunding.project', string="Projet",
        required=True, ondelete='cascade', index=True,
    )

    #: Les trois déclencheurs de la section 11, jamais confondus.
    origine = fields.Selection([
        ('ceo_recommandation', "Recommandation du comité CEO"),
        ('acteur_financier',   "Demande d'un acteur financier"),
        ('porteur',            "Demande du porteur"),
    ], string="Origine", required=True, readonly=True)
    requested_by_partner_id = fields.Many2one(
        'res.partner', string="Demandé par",
        help="L'acteur financier à l'origine de la demande, le cas échéant.",
    )

    state = fields.Selection([
        ('demande',      "Demande enregistrée"),
        ('diagnostic',   "Diagnostic en cours"),
        ('propose',      "Proposition soumise au porteur"),
        ('actif',        "Accompagnement actif"),
        ('service_fait', "Service fait"),
        ('evalue',       "Évalué et clos"),
        ('refuse',       "Proposition refusée"),
    # Pas de `tracking` : ce modèle n'hérite pas de `mail.thread`. Le suivi se
    # fait dans le fil du projet, qui reste le seul point d'audit du dossier.
    ], string="État", default='demande', required=True)

    demande = fields.Text(string="Demande du porteur")
    diagnostic = fields.Text(string="Diagnostic")
    proposition = fields.Text(string="Proposition d'accompagnement")

    # ------------------------------------------------------------------
    # La contrepartie — section 12
    # ------------------------------------------------------------------
    # Le type vient du référentiel, jamais d'un Selection en dur : « le
    # workflow ne doit pas coder en dur le modèle économique ».
    compensation_type_id = fields.Many2one(
        'opex.crowdfunding.compensation.type', string="Contrepartie",
        ondelete='restrict',
    )
    compensation_detail = fields.Text(
        string="Détail de la contrepartie",
        help="Montant, pourcentage, durée — ce que le type seul ne dit pas.")
    conditions = fields.Text(string="Conditions")

    convention_acceptee = fields.Boolean(
        string="Convention acceptée",
        help="Précondition de la transition « proposé → actif » (section 12).")
    date_acceptation = fields.Datetime(string="Date d'acceptation", readonly=True)

    mission_ids = fields.One2many(
        'opex.crowdfunding.mission', 'accompagnement_id', string="Missions")
    evaluation_ids = fields.One2many(
        'opex.crowdfunding.evaluation', 'accompagnement_id', string="Évaluations")

    #: Experts dont le domaine correspond au secteur du projet. Le document
    #: dit que le choix « peut provenir du Smart Matching Engine » — ici, une
    #: suggestion par secteur, sans scoring : le moteur pondéré de la section
    #: 10 vise les acteurs financiers, pas les experts.
    expert_suggestion_ids = fields.Many2many(
        'res.partner', string="Experts suggérés",
        compute='_compute_expert_suggestion_ids',
        relation='opex_cf_accompagnement_expert_rel',
        column1='accompagnement_id', column2='partner_id',
    )

    @api.depends('project_id.secteur')
    def _compute_expert_suggestion_ids(self):
        for accompagnement in self:
            accompagnement.expert_suggestion_ids = self.env['res.partner'].search([
                ('cf_is_expert', '=', True),
                ('cf_expertise_secteur', '=', accompagnement.project_id.secteur),
            ])

    # ------------------------------------------------------------------
    # Le sous-workflow
    # ------------------------------------------------------------------
    def action_start_diagnostic(self):
        """demande → diagnostic."""
        self.project_id._ensure_ceo()
        for accompagnement in self:
            accompagnement._ensure_state('demande')
            accompagnement.state = 'diagnostic'
            accompagnement.project_id.message_post(
                body=_("Accompagnement : diagnostic engagé."),
                subtype_xmlid='mail.mt_note')
        return True

    def action_propose(self):
        """diagnostic → proposition soumise au porteur.

        Une proposition sans contrepartie n'en est pas une : le porteur doit
        savoir ce qu'on lui demande en échange avant d'accepter quoi que ce
        soit.
        """
        self.project_id._ensure_ceo()
        for accompagnement in self:
            accompagnement._ensure_state('diagnostic')
            if not (accompagnement.diagnostic or '').strip():
                raise UserError(_(
                    "Renseignez le diagnostic avant de proposer un accompagnement."))
            if not (accompagnement.proposition or '').strip():
                raise UserError(_(
                    "Décrivez la proposition d'accompagnement avant de la soumettre."))
            if not accompagnement.compensation_type_id:
                raise UserError(_(
                    "Choisissez une contrepartie : le porteur doit savoir à quoi "
                    "il s'engage avant d'accepter."))
            accompagnement.state = 'propose'
            # Le porteur doit recevoir cette proposition, pas la découvrir en
            # visitant le portail — d'où `mt_comment`.
            accompagnement.project_id.message_post(
                body=_("Une proposition d'accompagnement vous est soumise. "
                       "Contrepartie envisagée : %s.",
                       accompagnement.compensation_type_id.name),
                subtype_xmlid='mail.mt_comment')
        return True

    def action_accept_convention(self):
        """proposition → actif. Précondition : convention acceptée.

        C'est la transition que la section 12 conditionne explicitement à
        `Convention acceptée = TRUE`. Le drapeau est posé par le porteur —
        depuis son portail — et cette méthode ne fait que le constater.
        """
        for accompagnement in self:
            accompagnement._ensure_state('propose')
            if not accompagnement.convention_acceptee:
                raise UserError(_(
                    "L'accompagnement ne devient actif qu'une fois la convention "
                    "acceptée par le porteur."))
            accompagnement.state = 'actif'
            accompagnement.date_acceptation = fields.Datetime.now()
            accompagnement.project_id.message_post(
                body=_("Convention acceptée : l'accompagnement est actif."),
                subtype_xmlid='mail.mt_note')
        return True

    def action_refuse_convention(self):
        """proposition → refusée. Le porteur reste libre de dire non."""
        for accompagnement in self:
            accompagnement._ensure_state('propose')
            accompagnement.state = 'refuse'
            accompagnement.project_id.message_post(
                body=_("Le porteur a refusé la proposition d'accompagnement."),
                subtype_xmlid='mail.mt_note')
        return True

    def action_service_fait(self):
        """actif → service fait.

        « Service fait » a un sens précis : toutes les missions sont terminées
        et tous les livrables attendus ont été validés. Sans ce contrôle, la
        formule ne voudrait rien dire.
        """
        self.project_id._ensure_ceo()
        for accompagnement in self:
            accompagnement._ensure_state('actif')
            if not accompagnement.mission_ids:
                raise UserError(_(
                    "Aucune mission n'a été confiée : il n'y a pas de service à "
                    "constater."))
            en_cours = accompagnement.mission_ids.filtered(
                lambda m: m.state not in ('terminee', 'declinee'))
            if en_cours:
                raise UserError(_(
                    "%s mission(s) ne sont pas terminées.", len(en_cours)))
            livrables = accompagnement.mission_ids.livrable_ids
            non_valides = livrables.filtered(lambda l: l.state != 'valide')
            if non_valides:
                raise UserError(_(
                    "%s livrable(s) ne sont pas validés.", len(non_valides)))
            accompagnement.state = 'service_fait'
            accompagnement.project_id.message_post(
                body=_("Accompagnement : service fait constaté."),
                subtype_xmlid='mail.mt_note')
        return True

    def action_evaluate(self):
        """service fait → évalué. Dernière étape du sous-processus."""
        self.project_id._ensure_ceo()
        for accompagnement in self:
            accompagnement._ensure_state('service_fait')
            if not accompagnement.evaluation_ids:
                raise UserError(_(
                    "Saisissez au moins une évaluation avant de clore "
                    "l'accompagnement."))
            accompagnement.state = 'evalue'
            accompagnement.project_id.message_post(
                body=_("Accompagnement évalué et clos."),
                subtype_xmlid='mail.mt_note')
        return True

    # ------------------------------------------------------------------
    def _ensure_state(self, attendu):
        self.ensure_one()
        if self.state != attendu:
            raise UserError(_(
                "Cet accompagnement est à l'état « %s » : l'action demandée ne "
                "s'y applique pas.",
                dict(self._fields['state']._description_selection(self.env))[self.state]))

    def _state_label(self):
        """Libellé lisible — le porteur ne voit jamais un code."""
        self.ensure_one()
        return dict(self._fields['state']._description_selection(self.env))[self.state]
