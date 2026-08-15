from odoo import http
from odoo.http import request

from odoo.addons.portal.controllers.portal import pager as portal_pager


class OpexDirectory(http.Controller):
    """Annuaire public des membres du cluster (US-16).

    Route publique et strictement en lecture : les `res.partner` sont lus en
    `sudo()` — un visiteur anonyme n'a aucun droit sur ce modèle — mais deux
    garde-fous encadrent cette élévation de droits :

    - le domaine impose `is_published_directory`, donc seuls les membres qui ont
      demandé leur publication apparaissent ;
    - les enregistrements ne sont jamais passés tels quels au template, mais
      convertis par `get_public_profile()`, qui fige la liste des champs
      exposables (un contact publié garde ainsi son email et son téléphone
      privés).
    """

    _members_per_page = 12

    def _published_members_domain(self):
        return [('is_member', '=', True), ('is_published_directory', '=', True)]

    def _directory_domain(self, search):
        domain = self._published_members_domain()
        if search['q']:
            domain.append(('name', 'ilike', search['q']))
        # Égalité stricte sur les deux filtres : leurs valeurs proviennent des
        # listes déroulantes construites par `_directory_filter_values()`.
        if search['secteur']:
            domain.append(('secteur_activite', '=', search['secteur']))
        if search['wilaya']:
            domain.append(('wilaya', '=', search['wilaya']))
        # L'expertise est un texte libre saisi par le membre : une liste
        # déroulante de paragraphes entiers n'aurait aucun sens, on cherche
        # donc dedans. La certification, elle, est un vrai modèle à valeurs
        # discrètes : elle reste un menu déroulant, filtré sur l'identifiant.
        if search['expertise']:
            domain.append(('domaines_expertise', 'ilike', search['expertise']))
        if search['certification']:
            domain.append(('certification_ids', 'in', [int(search['certification'])]))
        return domain

    def _directory_certifications(self):
        """Certifications réellement détenues par au moins un membre publié.

        Comme pour les secteurs et les wilayas : ne pas proposer un filtre qui
        ne ramènerait aucun résultat.
        """
        members = request.env['res.partner'].sudo().search(
            self._published_members_domain())
        return members.certification_ids.sorted('name')

    def _directory_filter_values(self, field):
        """Valeurs distinctes proposées dans un filtre, prises sur les seuls
        membres publiés — un secteur qui ne ramènerait aucun résultat n'a pas à
        être proposé."""
        groups = request.env['res.partner'].sudo()._read_group(
            self._published_members_domain() + [(field, '!=', False)],
            groupby=[field],
        )
        return sorted(group[0] for group in groups)

    @http.route(
        ['/opex/directory', '/opex/directory/page/<int:page>'],
        type='http', auth='public', website=True, sitemap=True,
    )
    def opex_directory(self, page=1, secteur=None, wilaya=None, q=None,
                       expertise=None, certification=None, **kw):
        certification = (certification or '').strip()
        search = {
            'q': (q or '').strip(),
            'secteur': (secteur or '').strip(),
            'wilaya': (wilaya or '').strip(),
            'expertise': (expertise or '').strip(),
            # Vient d'une liste déroulante : tout ce qui n'est pas un
            # identifiant est ignoré plutôt que passé au domaine.
            'certification': certification if certification.isdigit() else '',
        }
        Partner = request.env['res.partner'].sudo()
        domain = self._directory_domain(search)
        member_count = Partner.search_count(domain)

        pager_values = portal_pager(
            url='/opex/directory',
            total=member_count,
            page=page,
            step=self._members_per_page,
            url_args={key: value for key, value in search.items() if value},
        )
        members = Partner.search(
            domain,
            order='name',
            limit=self._members_per_page,
            offset=pager_values['offset'],
        )

        values = {
            'members': [member.get_public_profile() for member in members],
            'search': search,
            'secteurs': self._directory_filter_values('secteur_activite'),
            'wilayas': self._directory_filter_values('wilaya'),
            'certifications': self._directory_certifications(),
            'pager': pager_values,
            'member_count': member_count,
        }
        return request.render('opex_membership.directory_page', values)

    @http.route(
        ['/opex/directory/<int:partner_id>'],
        type='http', auth='public', website=True, sitemap=True,
    )
    def opex_directory_profile(self, partner_id, **kw):
        """Profil public d'un membre (section 28 de la spécification UX).

        Le membre est cherché *avec* les conditions de visibilité de la liste,
        pas simplement lu puis testé : un contact non publié et un identifiant
        qui n'existe pas produisent alors rigoureusement la même réponse, une
        404. Rien ne permet à un visiteur de deviner qu'un contact existe mais
        se cache.

        Les données affichées sont celles de `get_public_profile()` — la même
        méthode que la liste, donc les mêmes champs et rien de plus.
        """
        member = request.env['res.partner'].sudo().search(
            self._published_members_domain() + [('id', '=', partner_id)], limit=1)
        if not member:
            return request.not_found()
        return request.render('opex_membership.directory_profile_page', {
            'member': member.get_public_profile(),
        })
