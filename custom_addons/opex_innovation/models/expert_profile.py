from odoo import _, api, fields, models
from odoo.exceptions import UserError

#: Code de la définition de workflow commune aux deux profils, configurée en
#: data XML. C'est la seule chose que le métier connaît du processus : ni les
#: étapes, ni les transitions, ni les conditions n'apparaissent en Python.
PROFILE_WORKFLOW_CODE = 'profile_request'


class ExpertProfile(models.Model):
    """Demande de profil Expert — Modification 4 du PDF.

    ⚠ **Aucun champ `state`.** L'avancement de la demande, c'est
    `workflow_stage_id`, piloté par une définition configurée en données. C'est
    la démonstration entière du projet : la première personne qui ajoute ici un
    `state = fields.Selection(...)` « juste pour aller plus vite » l'annule.
    """

    _name = 'opex.innovation.expert.profile'
    _description = "Profil Expert"
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

    # --- Modification 4 : le formulaire ------------------------------------
    domaine_expertise = fields.Char(string="Domaine d'expertise", tracking=True)
    specialites = fields.Text(string="Spécialités")
    fonction = fields.Char(string="Fonction")
    annees_experience = fields.Integer(string="Années d'expérience")
    competence_ids = fields.Many2many(
        'opex.innovation.competence',
        'expert_profile_competence_rel', 'profile_id', 'competence_id',
        string="Compétences",
    )
    experiences_pro = fields.Text(string="Expériences professionnelles")
    projets_realises = fields.Text(string="Projets réalisés")
    experiences_conseil = fields.Text(string="Expériences de conseil")
    experience_mentoring = fields.Text(string="Expérience de mentoring")
    description_expertise = fields.Text(string="Description de l'expertise")

    document_ids = fields.One2many(
        'opex.innovation.profile.document', 'expert_profile_id',
        string="Justificatifs",
        help="CV, diplômes, certifications, attestations, portfolio, "
             "références professionnelles.",
    )

    # Motif du dernier retour du contrôleur, alimenté par le commentaire de la
    # transition. Le porteur doit savoir *quoi* corriger, pas seulement que
    # quelque chose ne va pas.
    motif_complement = fields.Text(string="Complément demandé", readonly=True)

    # ⚠ Ce n'est **pas** un champ d'état, malgré les apparences.
    #
    # C'est le point de contact entre le workflow et le métier : l'action
    # `set_field` de la transition « Valider » l'écrit, et le `write()`
    # ci-dessous en tire la conséquence sur le contact. Le workflow ne sait
    # donc rien de `res.partner`, et le métier ne sait rien du processus.
    #
    # L'avancement de la demande reste `workflow_stage_id` et lui seul.
    profile_activated = fields.Boolean(
        string="Profil activé", readonly=True, copy=False)

    _partner_uniq = models.Constraint(
        'unique(partner_id)',
        "Ce membre a déjà une demande de profil Expert.",
    )

    @api.depends('partner_id')
    def _compute_display_name(self):
        for profile in self:
            profile.display_name = _("Profil Expert — %s") % (
                profile.partner_id.display_name or '')

    @api.model_create_multi
    def create(self, vals_list):
        """Un membre ne dépose une demande qu'en son propre nom.

        Même verrou que sur `opex.membership.file` du Module 1 : le formulaire
        est rempli côté navigateur, `partner_id` ne peut pas en venir. Le
        réécrire ici, plutôt que se contenter de ne pas l'afficher, ferme la
        porte à une requête forgée qui créerait une demande au nom d'un autre.
        """
        if self.env.user._is_portal():
            partner_id = self.env.user.partner_id.id
            for vals in vals_list:
                vals['partner_id'] = partner_id
        profiles = super().create(vals_list)
        for profile in profiles:
            profile.start_workflow(PROFILE_WORKFLOW_CODE)
            if profile.partner_id:
                profile.sudo().message_subscribe(
                    partner_ids=profile.partner_id.ids)
        return profiles

    def write(self, vals):
        """Propage l'activation décidée par le workflow vers le contact.

        Le workflow écrit un booléen sur l'objet qu'il pilote — c'est tout ce
        qu'une action `set_field` sait faire, et c'est suffisant. La
        conséquence métier, elle, appartient au métier.
        """
        result = super().write(vals)
        if vals.get('profile_activated'):
            self.action_activate_profile()
        return result

    def action_activate_profile(self):
        """Active le profil sur le contact — appelée par le workflow.

        C'est l'action `set_field` de la transition « Valider » qui la
        déclenche, pas un `if` dans le code métier. Le jour où le processus
        change, la configuration change ; cette méthode ne bouge pas.
        """
        for profile in self:
            profile.partner_id.sudo().write({
                'is_expert': True,
                'expert_profile_id': profile.id,
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
