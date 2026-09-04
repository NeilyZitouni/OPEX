"""La taxonomie canonique du §8 — domaine, famille, compétence.

POURQUOI IL N'Y A PAS DE MODÈLE `opex.skill.catalog`

Le périmètre demande « la taxonomie canonique — domaine, famille, compétence,
avec ses synonymes ». Trois des quatre existent déjà, et le quatrième — la
compétence — existe **dans un autre module** : `opex.innovation.competence`,
le référentiel du Module 2.

Créer ici un second modèle de compétences canoniques aurait produit exactement
ce que le §8 interdit et ce que la dette D1 documente : deux catalogues qui ne
se croisent que par coïncidence de libellé. Le Smart Matching lit
`res.partner.expert_skill_competence_ids`, qui pointe sur le référentiel du
Module 2 ; un catalogue parallèle aurait rendu le matching faux **sans que rien
ne le signale**, ce qui est mot pour mot le risque que l'arbitrage de l'auteur
demandait d'éviter :

    « L'arbitrage enrichit le catalogue du Module 2, parce que le référentiel
      doit rester unique — deux catalogues seraient la dette D1 en pire. »

Ce fichier apporte donc **ce qui manquait** — les deux niveaux supérieurs de la
hiérarchie — et les greffe sur le référentiel existant par `_inherit`. Le
Module 2 n'est pas rouvert : pas une ligne de ses fichiers ne change. C'est le
même procédé que l'Extension 3 a utilisé pour le profil expert.

Le résultat est bien la taxonomie que le §8 décrit :

    opex.skill.domain  ->  opex.skill.family  ->  opex.innovation.competence
                                                    + opex.competence.synonyme

POURQUOI `domaine` NE SUFFISAIT PAS

`opex.innovation.competence` porte déjà un champ `domaine`. C'est un `Char`
libre — le motif exact de la dette D1. « Systèmes d'information », « Systemes
d'information » et « SI » y sont trois domaines différents, et rien ne le
signale. Le champ est conservé pour ne pas casser le Module 2 ; il devient
**alimenté** par la hiérarchie plutôt que saisi, ce qui le rend cohérent sans
le supprimer.
"""

from odoo import _, api, fields, models


class SkillDomain(models.Model):
    """Le premier niveau de la taxonomie — un grand secteur d'expertise.

    Volontairement peu nombreux : une dizaine, pas cent. Un domaine sert à
    **orienter** — le gestionnaire qui arbitre un libellé inconnu cherche
    d'abord « c'est de l'audit ou de la formation ? ». S'il y a soixante
    domaines, il ne cherche plus, il crée un doublon.
    """

    _name = 'opex.skill.domain'
    _description = "Domaine de compétence"
    _order = 'sequence, name'

    name = fields.Char(string="Domaine", required=True, translate=True)
    code = fields.Char(
        string="Code", required=True,
        help="Stable et court. C'est lui que le prompt de rapprochement "
             "présente au modèle, pas l'identifiant technique.")
    sequence = fields.Integer(string="Séquence", default=10)
    description = fields.Text(string="Description")
    active = fields.Boolean(string="Actif", default=True)

    family_ids = fields.One2many(
        'opex.skill.family', 'domain_id', string="Familles")
    family_count = fields.Integer(
        string="Nombre de familles", compute='_compute_counts')
    competence_count = fields.Integer(
        string="Nombre de compétences", compute='_compute_counts')

    _code_uniq = models.Constraint(
        'unique(code)', "Ce code de domaine est déjà utilisé.")

    @api.depends('family_ids', 'family_ids.competence_ids')
    def _compute_counts(self):
        for domain in self:
            families = domain.family_ids
            domain.family_count = len(families)
            domain.competence_count = len(families.competence_ids)

    def action_view_competences(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Compétences — %s") % self.name,
            'res_model': 'opex.innovation.competence',
            'view_mode': 'list,form',
            'domain': [('family_id.domain_id', '=', self.id)],
            'context': {'search_default_group_family': 1},
        }


class SkillFamily(models.Model):
    """Le second niveau — un regroupement de compétences voisines.

    C'est le niveau qui travaille vraiment. Deux compétences d'une même
    famille sont des candidates naturelles à la synonymie, et c'est là que le
    gestionnaire voit un doublon : « Audit SI » et « Audit des systèmes
    d'information » côte à côte dans la même famille se remarquent, dispersées
    dans un catalogue de six cents lignes, non.
    """

    _name = 'opex.skill.family'
    _description = "Famille de compétences"
    _order = 'domain_id, sequence, name'

    name = fields.Char(string="Famille", required=True, translate=True)
    code = fields.Char(string="Code", required=True)
    domain_id = fields.Many2one(
        'opex.skill.domain',
        string="Domaine",
        required=True,
        ondelete='restrict',
        index=True,
    )
    sequence = fields.Integer(string="Séquence", default=10)
    description = fields.Text(string="Description")
    active = fields.Boolean(string="Actif", default=True)

    competence_ids = fields.One2many(
        'opex.innovation.competence', 'family_id', string="Compétences")
    competence_count = fields.Integer(
        string="Nombre de compétences", compute='_compute_competence_count')

    _code_uniq = models.Constraint(
        'unique(code)', "Ce code de famille est déjà utilisé.")

    @api.depends('competence_ids')
    def _compute_competence_count(self):
        for family in self:
            family.competence_count = len(family.competence_ids)

    @api.depends('name', 'domain_id')
    def _compute_display_name(self):
        for family in self:
            family.display_name = "%s / %s" % (
                family.domain_id.name or '', family.name or '')


class InnovationCompetenceTaxonomy(models.Model):
    """Le troisième niveau, rattaché à sa famille.

    `_inherit` et non `_name` : c'est **le** référentiel du portail, celui que
    le Smart Matching interroge. On lui ajoute son rangement ; on ne le
    duplique pas.

    `family_id` n'est pas requis, et c'est délibéré. Le référentiel contient
    déjà des lignes créées avant cette extension — par l'arbitrage, ou à la
    main dans le Module 2. Les rendre invalides d'un coup aurait bloqué
    l'écran de compétences du Module 2 sur des données existantes. Une
    compétence sans famille est **visible comme telle** dans le filtre « À
    classer » ; c'est une file de rangement, pas une erreur.
    """

    _inherit = 'opex.innovation.competence'

    family_id = fields.Many2one(
        'opex.skill.family',
        string="Famille",
        ondelete='restrict',
        index=True,
        help="Le rangement du §8. Une compétence sans famille apparaît dans "
             "le filtre « À classer » du catalogue.",
    )
    skill_domain_id = fields.Many2one(
        'opex.skill.domain',
        # Pas « Domaine » tout court : le Module 2 a déjà un champ texte de ce
        # libellé sur ce modèle, et deux champs homonymes déclenchent un
        # avertissement au chargement — puis une confusion à l'écran, où l'on
        # ne sait plus lequel fait foi.
        string="Domaine (taxonomie)",
        related='family_id.domain_id',
        store=True,
        index=True,
        readonly=True,
        help="Déduit de la famille. Le champ texte `domaine` du Module 2 est "
             "conservé pour ne rien casser, mais c'est celui-ci qui fait foi.",
    )
    synonyme_ids = fields.One2many(
        'opex.competence.synonyme', 'competence_id', string="Synonymes")
    synonyme_count = fields.Integer(
        string="Nombre de synonymes", compute='_compute_synonyme_count')

    @api.depends('synonyme_ids')
    def _compute_synonyme_count(self):
        for competence in self:
            competence.synonyme_count = len(competence.synonyme_ids)

    @api.onchange('family_id')
    def _onchange_family_id(self):
        """Recopie le libellé du domaine dans le `Char` hérité du Module 2.

        Le Module 2 affiche `domaine` sur ses propres écrans et ne connaît pas
        la hiérarchie. Sans cette recopie, un utilisateur du Module 2 verrait
        une compétence sans domaine alors qu'elle en a un — et la remplirait à
        la main, en texte libre, ce que cette extension existe pour éviter.
        """
        for competence in self:
            if competence.family_id:
                competence.domaine = competence.family_id.domain_id.name

    def action_view_synonymes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Synonymes de « %s »") % self.name,
            'res_model': 'opex.competence.synonyme',
            'view_mode': 'list,form',
            'domain': [('competence_id', '=', self.id)],
            'context': {'default_competence_id': self.id},
        }
