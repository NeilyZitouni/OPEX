from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    """Les profils métier du portail, portés par le référentiel unique.

    Le PDF titre cette partie « Modifications à apporter au Module 1 ». On ne
    les implémente **pas** dans `opex_membership` : ce module est gelé avant sa
    présentation à l'encadrant. On étend `res.partner` depuis ici.

    L'exigence réelle du PDF — « le Module 1 devient la source des profils
    métier, le Module 2 ne recrée pas ces utilisateurs » — est respectée : il
    n'y a toujours qu'un seul `res.partner`, aucune duplication. Seul le module
    qui déclare les champs change, et c'est invisible du métier.

    **Trois booléens indépendants, jamais une Selection.** Un même compte
    peut être Membre + Expert + Investisseur — c'est la Modification 2, écrite
    noir sur blanc. Une Selection exclusive obligerait à choisir, et c'est
    précisément ce que le portail refuse.
    """

    _inherit = 'res.partner'

    is_expert = fields.Boolean(
        string="Est expert",
        help="Profil Expert actif. Cumulable avec les autres profils.",
    )
    is_investor = fields.Boolean(
        string="Est investisseur",
        help="Profil Investisseur actif. Cumulable avec les autres profils.",
    )
    expert_profile_id = fields.Many2one(
        'opex.innovation.expert.profile',
        string="Profil expert",
        ondelete='set null',
    )
    investor_profile_id = fields.Many2one(
        'opex.innovation.investor.profile',
        string="Profil investisseur",
        ondelete='set null',
    )

    # Toutes les demandes, y compris celles qui n'ont pas abouti : le portail
    # doit pouvoir dire « votre demande est en cours » et pas seulement
    # « vous n'êtes pas expert ».
    expert_request_ids = fields.One2many(
        'opex.innovation.expert.profile', 'partner_id',
        string="Demandes de profil expert")
    investor_request_ids = fields.One2many(
        'opex.innovation.investor.profile', 'partner_id',
        string="Demandes de profil investisseur")

    # ------------------------------------------------------------
    # Champs cibles du Smart Matching (section 19)
    # ------------------------------------------------------------
    #
    # Le moteur compare une valeur du dossier à un **champ de `res.partner`**.
    # Les données utiles vivent sur les profils ; ces `related` les exposent là
    # où le matching sait les lire, sans les dupliquer.
    #
    # **Non stockés**, et c'était une erreur de vouloir les stocker.
    #
    # Un `Many2many` à la fois `related` et `store=True` exige un nom de table
    # de liaison qu'Odoo ne sait pas déduire : le registre refuse de se charger
    # (`AttributeError: 'NoneType' object has no attribute 'isidentifier'`).
    #
    # Et le stockage n'apporterait rien : le matching filtre le vivier sur des
    # champs réels (`is_expert`, `is_investor`) puis lit ces valeurs **en
    # Python**, candidat par candidat. Un `related` non stocké ne coûte donc
    # qu'une traversée de relation, pas une requête supplémentaire.

    expert_competence_ids = fields.Many2many(
        'opex.innovation.competence',
        related='expert_profile_id.competence_ids',
        string="Compétences de l'expert",
    )
    expert_domaine = fields.Char(
        related='expert_profile_id.domaine_expertise',
        string="Domaine d'expertise",
    )
    investor_secteur_ids = fields.Many2many(
        'opex.innovation.competence',
        related='investor_profile_id.secteur_ids',
        string="Secteurs de l'investisseur",
    )
    investor_maturite = fields.Selection(
        related='investor_profile_id.stade_maturite_recherche',
        string="Maturité recherchée",
    )
    investor_zone = fields.Char(
        related='investor_profile_id.zone_geographique',
        string="Zone d'investissement",
    )
    investor_montant_max = fields.Monetary(
        related='investor_profile_id.montant_max',
        string="Ticket maximum",
        currency_field='investor_currency_id',
    )
    investor_currency_id = fields.Many2one(
        related='investor_profile_id.currency_id',
        string="Devise de l'investisseur",
    )

    # ------------------------------------------------------------
    # Activation automatique après validation de l'adhésion
    # ------------------------------------------------------------

    #: Catégorie d'adhésion → profil ouvert automatiquement (Modification 1).
    #: Table plutôt que deux `if` : ajouter une correspondance est une ligne,
    #: et la règle se lit d'un coup d'œil.
    _PROFILE_BY_CATEGORY = {
        'opex_membership.category_partenaires_sponsors': 'is_investor',
        'opex_membership.category_experts_consultants': 'is_expert',
    }

    def _opex_auto_profile_fields(self):
        """Profils que la catégorie d'adhésion de ce contact ouvre d'office."""
        self.ensure_one()
        category = self.membership_category_id
        if not category:
            return []
        fields_to_set = []
        for xmlid, field_name in self._PROFILE_BY_CATEGORY.items():
            expected = self.env.ref(xmlid, raise_if_not_found=False)
            if expected and category == expected:
                fields_to_set.append(field_name)
        return fields_to_set

    def _opex_sync_auto_profiles(self):
        """Ouvre les profils dus à la catégorie, pour les membres actifs.

        **N'active jamais rien à l'envers.** Un profil obtenu ne se retire
        pas parce qu'une catégorie a changé : la Modification 1 parle
        d'activation automatique, pas de révocation automatique. Retirer un
        profil est une décision, elle se prend à la main.

        Branché sur `create()` et `write()` plutôt que dans
        `_activate_membership()` du Module 1 : ce dernier est gelé. L'effet
        obtenu est le même — il écrit `is_member` sur le contact, et c'est
        cette écriture qu'on observe.
        """
        for partner in self:
            if not partner.is_member:
                continue
            values = {
                field_name: True
                for field_name in partner._opex_auto_profile_fields()
                if not partner[field_name]
            }
            if values:
                super(ResPartner, partner.sudo()).write(values)

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        partners._opex_sync_auto_profiles()
        return partners

    def write(self, vals):
        result = super().write(vals)
        # Seules ces deux écritures peuvent ouvrir un profil : devenir membre,
        # ou changer de catégorie en l'étant déjà. Se déclencher sur tout
        # `write()` ferait tourner la synchronisation à chaque frappe.
        if {'is_member', 'subcategory_id'} & set(vals):
            self._opex_sync_auto_profiles()
        return result

    # ------------------------------------------------------------
    # Éligibilité aux demandes de profil
    # ------------------------------------------------------------

    def _opex_pending_request(self, model_name):
        """Demande de profil en cours pour ce contact, sinon recordset vide."""
        self.ensure_one()
        return self.env[model_name].sudo().search([
            ('partner_id', '=', self.id),
            ('workflow_state', '=', 'running'),
        ], limit=1)

    def opex_can_request_expert(self):
        """Le bouton « Devenir Expert » doit-il être proposé ?

        Trois refus possibles : ne pas être membre actif, l'être déjà, ou avoir
        une demande en cours. La méthode répond aux trois, et c'est **la même**
        qui sert au gabarit et à la route — un `t-if` qui dirait autre chose
        que le contrôle serveur produirait un bouton menant à une erreur.
        """
        self.ensure_one()
        if not self.is_member or self.is_expert:
            return False
        return not self._opex_pending_request('opex.innovation.expert.profile')

    def opex_can_request_investor(self):
        self.ensure_one()
        if not self.is_member or self.is_investor:
            return False
        return not self._opex_pending_request('opex.innovation.investor.profile')

    def opex_check_can_request(self, profile_type):
        """Vérification **serveur** avant création, avec un message lisible.

        Le `t-if` du gabarit masque le bouton ; il n'empêche rien. Une
        requête forgée sur la route de création n'a jamais vu le gabarit. Le
        bug symétrique est déjà arrivé sur le Module 1 — « Devenir membre »
        resté visible pour un membre actif — et c'est le contrôle serveur qui
        manquait, pas le `t-if`.
        """
        self.ensure_one()
        if profile_type == 'expert':
            allowed, already, label = (
                self.opex_can_request_expert(), self.is_expert, _("Expert"))
        else:
            allowed, already, label = (
                self.opex_can_request_investor(), self.is_investor,
                _("Investisseur"))

        if allowed:
            return True
        if not self.is_member:
            raise UserError(_(
                "Votre adhésion doit être validée avant de demander un profil "
                "%s.") % label)
        if already:
            raise UserError(_(
                "Vous disposez déjà du profil %s.") % label)
        raise UserError(_(
            "Une demande de profil %s est déjà en cours d'examen.") % label)

    # ------------------------------------------------------------
    # Cloche de notification du portail — extension du Module 1
    # ------------------------------------------------------------

    def _opex_owned_record_ids(self):
        """Ajoute les enregistrements Innovation au périmètre de la cloche.

        **On n'écrit pas un second système de notification.** Le Module 1 en
        a un complet : il lit les `mail.message` déjà posés sur les
        enregistrements du contact, en écarte les notes internes par
        `_get_search_domain_share()`, et compare leur date à
        `notification_last_seen`. Tout cela fonctionne déjà pour les dossiers
        d'adhésion.

        Le seul manque était le **périmètre** : `_opex_owned_record_ids()` ne
        connaissait que `opex.membership.file` et `opex.subscription`. Les
        actions `notify` du moteur postaient donc correctement, avec les bons
        sous-types et les bons destinataires — et aucune n'atteignait la
        cloche, faute d'être sur un modèle déclaré ici.

        Surcharge **coopérative** : elle commence par `super()`, donc les
        dossiers d'adhésion restent visibles. C'est la ligne de partage de la
        règle transversale 1 bis — une méthode qui relaie `super()` s'exécute
        en chaîne, celle qui ne le fait pas efface la précédente.

        Ne donne accès à rien. Cette table décide de ce que le contact voit
        dans sa cloche ; la visibilité réelle des messages reste tranchée par
        `_get_search_domain_share()` en amont, qui exclut les `mt_note`. Un
        message de coordination interne n'y entrera jamais, même si son
        enregistrement est listé ici.
        """
        self.ensure_one()
        owned = super()._opex_owned_record_ids()

        Project = self.env['opex.innovation.project'].sudo()
        projects = Project.search([('partner_id', '=', self.id)])

        owned.update({
            'opex.innovation.project': projects.ids,
            'opex.innovation.expert.profile':
                self.env['opex.innovation.expert.profile'].sudo().search(
                    [('partner_id', '=', self.id)]).ids,
            'opex.innovation.investor.profile':
                self.env['opex.innovation.investor.profile'].sudo().search(
                    [('partner_id', '=', self.id)]).ids,
            # `partner_id` est un `related` **stocké** depuis l'accompagnement :
            # on interroge donc le livrable directement, sans traverser.
            'opex.innovation.deliverable':
                self.env['opex.innovation.deliverable'].sudo().search(
                    [('partner_id', '=', self.id)]).ids,
            'opex.innovation.industrialisation':
                self.env['opex.innovation.industrialisation'].sudo().search(
                    [('project_id.partner_id', '=', self.id)]).ids,
        })
        return owned

    def _opex_notification_url(self, message):
        """Lien vers l'écran portail qui porte le message.

        Une notification qu'on ne peut pas ouvrir n'aide personne : chaque
        modèle ajouté au périmètre ci-dessus doit avoir sa destination ici.
        Les demandes de profil n'ont pas d'identifiant dans leur URL — le
        controller les résout depuis `partner_id` —, d'où le lien par type.

        Le suivi d'industrialisation n'a pas d'écran portail dédié : on renvoie
        vers le projet, seul endroit où le porteur le voit aujourd'hui. Même
        parti que le Module 1 pour les cotisations.
        """
        self.ensure_one()
        if message.model == 'opex.innovation.project':
            return '/my/innovation/%s' % message.res_id
        if message.model == 'opex.innovation.expert.profile':
            return '/my/innovation/profiles/expert'
        if message.model == 'opex.innovation.investor.profile':
            return '/my/innovation/profiles/investor'
        if message.model == 'opex.innovation.deliverable':
            return '/my/innovation/deliverable/%s' % message.res_id
        if message.model == 'opex.innovation.industrialisation':
            industrialisation = self.env[
                'opex.innovation.industrialisation'].sudo().browse(message.res_id)
            if industrialisation.project_id:
                return '/my/innovation/%s' % industrialisation.project_id.id
        return super()._opex_notification_url(message)
