from odoo import http
from odoo.http import request


class OpexClusterPage(http.Controller):
    """Page de présentation publique du cluster (landing page).

    Route publique en lecture seule : les compteurs affichés sont calculés en
    `sudo()` — un visiteur anonyme ne peut pas lire `res.partner` — mais seuls
    des agrégats sortent d'ici, jamais un enregistrement.

    La page n'est pas montée sur `/` : l'accueil du site se règle depuis
    Site Web → Configuration → Réglages → URL de la page d'accueil, pour ne pas
    entrer en conflit avec les pages installées par le module `website`.
    """

    @http.route(['/cluster'], type='http', auth='public', website=True, sitemap=True)
    def opex_cluster_page(self, **kw):
        values = {
            'member_count': request.env['res.partner'].sudo().search_count(
                [('is_member', '=', True)]
            ),
            'category_count': request.env['opex.membership.category'].sudo().search_count([]),
        }
        return request.render('opex_membership.website_cluster_homepage', values)
