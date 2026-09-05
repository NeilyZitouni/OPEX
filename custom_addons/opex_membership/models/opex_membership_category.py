from odoo import fields, models


class OpexMembershipCategory(models.Model):
    """Catégorie d'adhésion (section 3 de la spécification UX).

    La catégorie ne porte plus de barème : depuis l'introduction des
    sous-catégories, c'est `opex.membership.subcategory` qui définit le montant
    de la cotisation et le critère d'éligibilité. La catégorie n'est plus que le
    premier niveau de choix du candidat.
    """

    _name = 'opex.membership.category'
    _description = "Catégorie d'adhésion"
    _order = 'sequence, name'

    name = fields.Char(
        string="Nom",
        required=True,
        help="Membres adhérents, Membres associés, Partenaires/Sponsors, Experts/Consultants.",
    )
    sequence = fields.Integer(string="Séquence", default=10)

    #: Une catégorie retirée du parcours **sans être supprimée**.
    #:
    #: La suppression n'est pas une option : une catégorie de test a servi à
    #: quatre adhésions actives, et la supprimer les orphelinerait. Odoo
    #: exclut d'office les enregistrements archivés de `search()`, ce qui les
    #: fait disparaître du parcours de dépôt sans toucher aux dossiers qui les
    #: référencent — ils continuent de l'afficher.
    active = fields.Boolean(
        string="Actif", default=True,
        help="Décochez pour retirer cette entrée du parcours de dépôt sans "
             "perdre les dossiers qui l'utilisent déjà.")

    subcategory_ids = fields.One2many(
        'opex.membership.subcategory', 'category_id', string="Sous-catégories"
    )
    subcategory_count = fields.Integer(
        string="Nombre de sous-catégories", compute='_compute_subcategory_count'
    )
    droits_acces = fields.Text(string="Droits d'accès")

    def _compute_subcategory_count(self):
        counts = dict(self.env['opex.membership.subcategory']._read_group(
            [('category_id', 'in', self.ids)],
            groupby=['category_id'],
            aggregates=['__count'],
        ))
        for record in self:
            record.subcategory_count = counts.get(record, 0)
