from odoo import _, api, fields, models
from odoo.exceptions import UserError

#: Le profil Investisseur suit **le même processus** que le profil Expert, mais
#: sur son propre modèle : le moteur pilote par `res_model`, une définition est
#: donc liée à un modèle. Deux définitions, une seule description du processus —
#: elle vit intégralement dans `data/profile_workflow.xml`.
INVESTOR_WORKFLOW_CODE = 'profile_request_investor'


class InvestorProfile(models.Model):
    """Demande de profil Investisseur — Modification 5 du PDF.

    **Aucun champ `state`**, pour la même raison que le profil Expert.

    Les deux profils partagent **la même définition de workflow**
    (`profile_request`), et c'est un point de démonstration à lui seul : deux
    modèles différents suivent un processus identique sans qu'une ligne de
    Python soit écrite deux fois. Le moteur pilote par `res_model`/`res_id`, il
    ne demande pas que les objets se ressemblent.
    """

    _name = 'opex.innovation.investor.profile'
    _description = "Profil Investisseur"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'opex.workflow.mixin']
    _order = 'create_date desc'
    _rec_name = 'partner_id'

    partner_id = fields.Many2one(
        'res.partner',
        string="Membre",
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
    )

    # --- Modification 5 : le formulaire ------------------------------------
    type_investisseur = fields.Selection(
        [
            ('business_angel', "Business angel"),
            ('fonds', "Fonds d'investissement"),
            ('banque', "Banque"),
            ('institution', "Institution publique"),
            ('entreprise', "Entreprise"),
            ('sponsor', "Sponsor"),
            ('autre', "Autre"),
        ],
        string="Type d'investisseur",
        tracking=True,
    )
    secteur_ids = fields.Many2many(
        'opex.innovation.competence',
        'investor_profile_secteur_rel', 'profile_id', 'competence_id',
        string="Secteurs d'intérêt",
    )
    domaines_investissement = fields.Text(string="Domaines d'investissement")
    types_projets_recherches = fields.Text(string="Types de projets recherchés")
    stade_maturite_recherche = fields.Selection(
        [
            ('idee', "Idée"),
            ('prototype', "Prototype"),
            ('mvp', "MVP"),
            ('produit', "Produit développé"),
            ('premiers_clients', "Premiers clients"),
            ('commercialisation', "Commercialisation"),
            ('industrialisation', "Industrialisation"),
        ],
        string="Stade de maturité recherché",
    )
    zone_geographique = fields.Char(string="Zone géographique")
    currency_id = fields.Many2one(
        'res.currency',
        string="Devise",
        default=lambda self: self.env.company.currency_id,
    )
    montant_min = fields.Monetary(
        string="Ticket minimum", currency_field='currency_id')
    montant_max = fields.Monetary(
        string="Ticket maximum", currency_field='currency_id')
    experience_investissement = fields.Text(string="Expérience d'investissement")
    preferences = fields.Text(string="Préférences")
    presentation = fields.Text(string="Présentation")

    document_ids = fields.One2many(
        'opex.innovation.profile.document', 'investor_profile_id',
        string="Justificatifs")

    motif_complement = fields.Text(string="Complément demandé", readonly=True)
    profile_activated = fields.Boolean(
        string="Profil activé", readonly=True, copy=False,
        help="Écrit par l'action « set_field » de la transition « Valider ». "
             "Ce n'est pas un champ d'état : l'avancement de la demande reste "
             "workflow_stage_id, et lui seul.")

    _partner_uniq = models.Constraint(
        'unique(partner_id)',
        "Ce membre a déjà une demande de profil Investisseur.",
    )

    @api.constrains('montant_min', 'montant_max')
    def _check_montants(self):
        for profile in self:
            if profile.montant_max and profile.montant_min > profile.montant_max:
                raise UserError(_(
                    "Le ticket minimum ne peut pas dépasser le ticket maximum."))

    @api.depends('partner_id')
    def _compute_display_name(self):
        for profile in self:
            profile.display_name = _("Profil Investisseur — %s") % (
                profile.partner_id.display_name or '')

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.user._is_portal():
            partner_id = self.env.user.partner_id.id
            for vals in vals_list:
                vals['partner_id'] = partner_id
        profiles = super().create(vals_list)
        for profile in profiles:
            profile.start_workflow(INVESTOR_WORKFLOW_CODE)
            if profile.partner_id:
                profile.sudo().message_subscribe(
                    partner_ids=profile.partner_id.ids)
        return profiles

    def write(self, vals):
        result = super().write(vals)
        if vals.get('profile_activated'):
            self.action_activate_profile()
        return result

    def action_activate_profile(self):
        for profile in self:
            profile.partner_id.sudo().write({
                'is_investor': True,
                'investor_profile_id': profile.id,
            })
        return True

    def action_record_complement(self, motif):
        self.ensure_one()
        if not (motif or '').strip():
            raise UserError(_(
                "Précisez le complément attendu : c'est ce texte que le "
                "membre recevra."))
        self.motif_complement = motif.strip()
        return True
