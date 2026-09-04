from odoo import fields, models


class ResPartner(models.Model):
    """Le profil d'acteur financier, côté référentiel (sections 2.E et 10).

    Tous les champs sont préfixés `cf_`. Ce n'est pas de la coquetterie : le
    module Membership étend lui aussi `res.partner` (`secteur_activite`,
    `wilaya`, `presentation`…) et les deux modules peuvent être installés dans
    la même base. Une collision de nom sur `res.partner` est silencieuse au
    chargement et fatale au runtime — c'est la règle transversale n°1.
    """

    _inherit = 'res.partner'

    cf_is_financial_actor = fields.Boolean(
        string="Acteur financier (Smart Crowdfunding)",
        help="Rend ce contact éligible au matching financier. « Être "
             "enregistré comme investisseur ne donne pas automatiquement "
             "accès à tous les projets » (section 3) : ce drapeau ne donne "
             "aucun droit de lecture.",
    )
    cf_actor_type = fields.Selection([
        ('investisseur',          "Investisseur / actionnaire"),
        ('fonds',                 "Fonds d'investissement"),
        ('programme_public',      "Programme public de financement"),
        ('sponsor',               "Sponsor"),
        ('banque',                "Banque ou institution financière"),
        ('partenaire_strategique', "Partenaire stratégique"),
    ], string="Type d'acteur financier")

    # ------------------------------------------------------------------
    # Ce sur quoi les dix critères pondérés s'appuient
    # ------------------------------------------------------------------
    cf_secteur = fields.Selection(
        selection=lambda self: self.env[
            'opex.crowdfunding.project']._fields['secteur'].selection,
        string="Secteur de prédilection",
    )
    cf_tous_secteurs = fields.Boolean(
        string="Intervient dans tous les secteurs",
        help="Un acteur généraliste marque moins qu'un spécialiste du secteur "
             "du projet, mais plus qu'un acteur d'un autre secteur.",
    )
    cf_ticket_min = fields.Monetary(
        string="Ticket minimum", currency_field='cf_currency_id')
    cf_ticket_max = fields.Monetary(
        string="Ticket maximum", currency_field='cf_currency_id')
    cf_currency_id = fields.Many2one(
        'res.currency', string="Devise du ticket",
        default=lambda self: self.env.company.currency_id.id,
    )
    cf_stade_min = fields.Selection(
        selection=lambda self: self.env[
            'opex.crowdfunding.project']._fields['maturite'].selection,
        string="Stade minimum financé",
    )
    cf_appetence_risque = fields.Selection([
        ('faible', "Faible"),
        ('moyenne', "Moyenne"),
        ('elevee', "Élevée"),
    ], string="Appétence au risque")
    cf_localisation = fields.Char(
        string="Zone d'intervention",
        help="Comparée à la ville du porteur. Laissée vide, elle ne pénalise "
             "pas l'acteur : le critère devient neutre.",
    )
    cf_porteur_type_prefere = fields.Selection(
        selection=lambda self: self.env[
            'opex.crowdfunding.project']._fields['porteur_type'].selection,
        string="Type de porteur préféré",
    )
    cf_recherche_impact = fields.Boolean(string="Recherche des projets à impact")
    cf_interet_technologie = fields.Boolean(string="Recherche des projets technologiques")

    # ------------------------------------------------------------------
    # Cloche de notification du portail
    # ------------------------------------------------------------------

    def _opex_owned_record_ids(self):
        """Ajoute les dossiers Smart Crowdfunding au périmètre de la cloche.

        `opex_membership` sert une cloche portail qui lit les `mail.message`
        déjà posés sur les enregistrements d'un contact — les comptes portail
        ne supportent pas la cloche native d'Odoo, interdite en base par
        `CHECK (notification_type = 'email' OR NOT share)`. Ce module poste
        bien ses messages, mais son modèle n'était pas dans le périmètre : rien
        n'arrivait jusqu'à la cloche.

        **INACTIVE EN L'ÉTAT — ne pas la croire sur parole.** Mesuré le
        28/08 : le MRO de `res.partner` est
        `opex_innovation → opex_membership → opex_crowdfunding`, et la méthode
        d'`opex_membership` est l'implémentation d'origine : elle renvoie un
        dictionnaire littéral **sans relayer `super()`**. La chaîne s'arrête
        donc chez elle, et ce code n'est jamais atteint.

        L'ordre du MRO suit l'ordre de chargement, lui-même issu du graphe de
        dépendances : `opex_crowdfunding` ne dépendant de rien, il est chargé
        en premier, donc placé en dernier dans le MRO. Le rendre effectif
        demande de le charger **après** `opex_membership`, c'est-à-dire
        d'ajouter cette dépendance au manifeste — ce que ce module refuse
        explicitement (« Pas `opex_membership` (indépendance) »).

        Le code est conservé parce qu'il est correct et devient actif le jour
        où cette dépendance est acceptée. **Arbitrage à rendre** : accepter la
        dépendance, ou assumer que les dossiers Smart Crowdfunding n'entrent
        pas dans la cloche du portail.

        `getattr` plutôt qu'un `super()` direct : sans `opex_membership`
        installé, la méthode parente n'existe pas et un appel direct lèverait
        un `AttributeError` sur un module qui doit rester installable seul.

        Ne donne accès à rien : le filtrage des messages reste celui du
        Module 1, `_get_search_domain_share()`, qui écarte les `mt_note`. Les
        29 `message_post()` internes de ce module n'entreront donc jamais dans
        la cloche d'un porteur, quoi qu'il arrive ici.
        """
        self.ensure_one()
        parent = getattr(super(), '_opex_owned_record_ids', None)
        owned = parent() if parent else {}

        # Seul le projet porte des messages : les modèles satellites
        # (relation, accompagnement, closing) postent tous sur
        # `relation.project_id` / le projet, jamais sur eux-mêmes.
        owned['opex.crowdfunding.project'] = self.env[
            'opex.crowdfunding.project'].sudo().search(
                [('partner_id', '=', self.id)]).ids
        return owned

    def _opex_notification_url(self, message):
        """Lien vers le dossier concerné. Même contrat que la méthode ci-dessus."""
        self.ensure_one()
        if message.model == 'opex.crowdfunding.project':
            return '/my/crowdfunding/%s' % message.res_id
        parent = getattr(super(), '_opex_notification_url', None)
        return parent(message) if parent else '/my'

    # ------------------------------------------------------------------
    # L'expert mandaté par le comité (sections 2.D et 11)
    # ------------------------------------------------------------------
    cf_is_expert = fields.Boolean(
        string="Expert (Smart Crowdfunding)",
        help="Peut être mandaté pour une mission d'accompagnement. Comme pour "
             "l'acteur financier, ce drapeau ne donne aucun droit de lecture "
             "sur les dossiers.",
    )
    cf_expertise = fields.Text(
        string="Domaines d'expertise",
        help="Diagnostic, due diligence, business model, go-to-market…")
    cf_expertise_secteur = fields.Selection(
        selection=lambda self: self.env[
            'opex.crowdfunding.project']._fields['secteur'].selection,
        string="Secteur d'expertise",
    )
