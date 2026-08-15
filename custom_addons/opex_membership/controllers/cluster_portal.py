from urllib.parse import quote

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal


class ClusterPortal(CustomerPortal):
    """Vie du Cluster côté membre : actualités, événements, formations.

    Distinct de `controllers/cluster.py`, qui sert la page de présentation
    publique `/cluster` : ici tout est derrière `auth='user'`, et rattaché au
    membre connecté.

    Règle de sécurité commune à toutes les inscriptions : le participant n'est
    jamais lu dans le formulaire, il est toujours pris sur la session
    (`request.env.user.partner_id`). L'identifiant reçu en URL ne sert qu'à
    désigner l'activité, et il est vérifié avant usage.
    """

    _items_per_page = 20

    # ------------------------------------------------------------
    # Accès : réservé aux membres actifs
    # ------------------------------------------------------------

    def _cluster_access_denied(self):
        """Réponse de refus si l'utilisateur n'est pas membre actif, sinon `None`.

        Point de décision unique de toute la Vie du Cluster : les trois listes
        *et* les deux actions d'inscription passent par ici. Rejouer le test à
        chaque endroit finirait par en laisser un derrière — et ce serait
        justement celui qui reçoit une requête forgée.

        Masquer les liens ne suffit donc pas : un candidat qui poste
        directement sur une inscription retombe sur cette même vérification.

        `is_member` n'est vrai qu'après activation de l'adhésion
        (`_activate_membership`) : un candidat en cours de parcours est refusé
        sans qu'on ait à inspecter l'état de son dossier ici.

        Le personnel interne du module passe également, sans être membre :
        Secrétariat, Comité et COPIL doivent pouvoir prévisualiser ce que
        verront les adhérents. Cette exception vit ici, dans la même méthode
        que la règle qu'elle assouplit — une route parallèle réservée au staff
        finirait par diverger de celle des membres.
        """
        user = request.env.user
        if user.partner_id.sudo().is_member or user._is_opex_staff():
            return None
        # Motif passé en drapeau, pas en texte libre : la page d'accueil du
        # portail affiche un message qu'elle contrôle, plutôt que de réafficher
        # une chaîne venue de l'URL.
        return request.redirect('/my?cluster=members_only')

    # ------------------------------------------------------------
    # Actualités
    # ------------------------------------------------------------

    @http.route(['/my/cluster/news'], type='http', auth='user', website=True)
    def portal_cluster_news(self, **kw):
        denied = self._cluster_access_denied()
        if denied:
            return denied

        News = request.env['opex.cluster.news']
        news = News.sudo().search(
            News._portal_domain(), limit=self._items_per_page)

        values = self._prepare_portal_layout_values()
        values.update({
            'news_items': news,
            'page_name': 'cluster_news',
            'cluster_page': 'news',
        })
        return request.render('opex_membership.portal_cluster_news', values)

    # ------------------------------------------------------------
    # Événements
    # ------------------------------------------------------------

    def _registered_activity_ids(self, field):
        """Identifiants des activités auxquelles le membre est déjà inscrit.

        Sert uniquement à l'affichage (bouton « Déjà inscrit ») ; l'inscription
        elle-même reste protégée côté serveur.
        """
        registrations = request.env['opex.cluster.event.registration'].sudo().search(
            [('partner_id', '=', request.env.user.partner_id.id)])
        return set(registrations.mapped(field).ids)

    @http.route(['/my/cluster/events'], type='http', auth='user', website=True)
    def portal_cluster_events(self, **kw):
        denied = self._cluster_access_denied()
        if denied:
            return denied

        events = request.env['opex.cluster.event'].sudo().search(
            [], limit=self._items_per_page)

        values = self._prepare_portal_layout_values()
        values.update({
            'events': events,
            'registered_event_ids': self._registered_activity_ids('event_id'),
            'error': kw.get('error'),
            'page_name': 'cluster_events',
            'cluster_page': 'events',
        })
        return request.render('opex_membership.portal_cluster_events', values)

    @http.route(
        ['/my/cluster/events/<int:event_id>/register'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_cluster_event_register(self, event_id, **post):
        denied = self._cluster_access_denied()
        if denied:
            return denied

        event = request.env['opex.cluster.event'].sudo().browse(event_id).exists()
        if not event:
            return request.redirect('/my/cluster/events')
        return self._register_to(
            event, '/my/cluster/events')

    # ------------------------------------------------------------
    # Formations
    # ------------------------------------------------------------

    @http.route(['/my/cluster/trainings'], type='http', auth='user', website=True)
    def portal_cluster_trainings(self, **kw):
        denied = self._cluster_access_denied()
        if denied:
            return denied

        trainings = request.env['opex.cluster.training'].sudo().search(
            [], limit=self._items_per_page)

        values = self._prepare_portal_layout_values()
        values.update({
            'trainings': trainings,
            'registered_training_ids': self._registered_activity_ids('training_id'),
            'error': kw.get('error'),
            'page_name': 'cluster_trainings',
            'cluster_page': 'trainings',
        })
        return request.render('opex_membership.portal_cluster_trainings', values)

    @http.route(
        ['/my/cluster/trainings/<int:training_id>/register'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_cluster_training_register(self, training_id, **post):
        denied = self._cluster_access_denied()
        if denied:
            return denied

        training = request.env['opex.cluster.training'].sudo().browse(training_id).exists()
        if not training:
            return request.redirect('/my/cluster/trainings')
        return self._register_to(training, '/my/cluster/trainings')

    # ------------------------------------------------------------
    # Documents et groupes
    # ------------------------------------------------------------

    @http.route(['/my/cluster/documents'], type='http', auth='user', website=True)
    def portal_cluster_documents(self, **kw):
        denied = self._cluster_access_denied()
        if denied:
            return denied

        Document = request.env['opex.cluster.document']
        # Le personnel interne prévisualise aussi les pièces de comité ; un
        # membre ne les voit pas. Même notion de « personnel » que le garde-fou
        # d'accès, pas une seconde définition.
        is_staff = request.env.user._is_opex_staff()
        documents = Document.sudo().search(Document._portal_domain(is_staff=is_staff))

        # Regroupement par dossier, dans l'ordre de la sélection : c'est
        # l'arborescence de la section 37, pas une liste plate.
        folders = dict(Document._fields['folder'].selection)
        grouped = []
        for key, label in folders.items():
            in_folder = documents.filtered(lambda d: d.folder == key)
            if in_folder:
                grouped.append((label, in_folder))

        values = self._prepare_portal_layout_values()
        values.update({
            'document_folders': grouped,
            'sees_committee_documents': is_staff,
            'page_name': 'cluster_documents',
            'cluster_page': 'documents',
        })
        return request.render('opex_membership.portal_cluster_documents', values)

    @http.route(['/my/cluster/groups'], type='http', auth='user', website=True)
    def portal_cluster_groups(self, **kw):
        denied = self._cluster_access_denied()
        if denied:
            return denied

        groups = request.env['opex.cluster.group'].sudo().search(
            [], limit=self._items_per_page)

        values = self._prepare_portal_layout_values()
        values.update({
            'groups': groups,
            'my_group_ids': set(groups.filtered(
                lambda g: request.env.user.partner_id in g.member_ids).ids),
            'page_name': 'cluster_groups',
            'cluster_page': 'groups',
        })
        return request.render('opex_membership.portal_cluster_groups', values)

    # ------------------------------------------------------------

    def _register_to(self, activity, redirect_url):
        """Inscrit le membre connecté à l'activité, et rapporte un refus lisible.

        Le participant vient de la session, jamais du formulaire : une requête
        forgée ne peut pas inscrire quelqu'un d'autre. Le refus éventuel (une
        formation complète) est celui du modèle, réaffiché tel quel.
        """
        partner = request.env.user.partner_id
        try:
            with request.env.cr.savepoint():
                activity.action_register(partner)
        except UserError as error:
            return request.redirect('%s?error=%s' % (redirect_url, quote(error.args[0])))
        return request.redirect(redirect_url)
