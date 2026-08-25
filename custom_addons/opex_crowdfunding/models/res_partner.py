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
