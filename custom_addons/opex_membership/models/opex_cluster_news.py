from odoo import fields, models


class OpexClusterNews(models.Model):
    """Actualité du cluster (section 34 de la spécification UX)."""

    _name = 'opex.cluster.news'
    _description = "Actualité du cluster"
    _order = 'publish_date desc, id desc'

    title = fields.Char(string="Titre", required=True)
    image = fields.Image(string="Image", max_width=1920, max_height=1920)
    content = fields.Html(string="Contenu")
    category = fields.Char(
        string="Catégorie",
        help="Libellé libre : la spécification n'arrête pas de liste fermée.",
    )
    # Une actualité datée du futur n'est pas encore publiée : c'est ce que le
    # portail utilise pour ne pas dévoiler une annonce en préparation.
    publish_date = fields.Date(
        string="Date de publication", default=fields.Date.context_today, required=True)
    attachment_ids = fields.Many2many('ir.attachment', string="Pièces jointes")

    def _portal_domain(self):
        """Actualités visibles par un membre : celles déjà publiées."""
        return [('publish_date', '<=', fields.Date.context_today(self))]
