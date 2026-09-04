"""L'accueil unique du portail et les indicateurs globaux - §48, US-20.

Noms de méthodes préfixés, comme partout dans ce module : deux modules qui
héritent du même arbre de controller et nomment une méthode pareil, Odoo n'en
garde qu'une, sans erreur.

`http.Controller` et non `CustomerPortal` : ces pages ne sont l'espace
personnel de personne. L'accueil est public, les indicateurs sont l'outil du
cluster.
"""

from odoo import http
from odoo.http import request


class PortalIntegrationPublic(http.Controller):
    """L'accueil qui relie les trois domaines, et le catalogue filtré."""

    @http.route(['/opex'], type='http', auth='public', website=True,
                sitemap=True)
    def portal_intervenants_home(self, **kw):
        """§48 - « Un espace unique ».

        La page ne rend que des dictionnaires à clés fermées : trois entrées de
        domaine et des volumes. Aucun enregistrement des trois modules ne la
        traverse, ce qui rend impossible la publication accidentelle d'un nom
        de membre ou d'un intitulé de projet.
        """
        Integration = request.env['opex.portal.integration'].sudo()
        return request.render('opex_intervenants.portal_opex_home', {
            'domaines': Integration.portal_domains(),
            'indicateurs': Integration.global_indicators(),
            'page_name': 'opex_home',
        })

class PortalIntegrationStaff(http.Controller):
    """Les indicateurs globaux de l'US-20, pour le cluster."""

    def _kpi_staff_user(self):
        """Le contrôle d'accès du staff Missions, et lui seul.

        `res.users._is_missions_staff()` est LA fonction : les routes et les
        `t-if` des tuiles posent la même question. Deux listes de groupes
        finiraient par diverger.
        """
        user = request.env.user
        return user if user._is_missions_staff() else False

    @http.route(['/staff/kpi'], type='http', auth='user', website=True)
    def staff_intervenants_kpi(self, **kw):
        """US-20 - le tableau de bord KPI global.

        Il agrège les trois modules et affiche, à côté, la liste de contrôle
        du §21. Celle-ci n'est pas un texte : elle est calculée à l'affichage,
        et un critère qui cesserait d'être tenu le dirait à l'écran.
        """
        if not self._kpi_staff_user():
            return request.redirect('/my')

        Integration = request.env['opex.portal.integration'].sudo()
        return request.render('opex_intervenants.staff_global_kpi', {
            'indicateurs': Integration.global_indicators(),
            'checklist': Integration.acceptance_checklist(),
            'page_name': 'intervenants_kpi',
        })
