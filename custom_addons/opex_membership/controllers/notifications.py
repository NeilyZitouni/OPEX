from odoo import http
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal


class MembershipNotifications(CustomerPortal):
    """Cloche de notification du portail candidat.

    Odoo interdit en base le type de notification « inbox » pour un compte
    portail (`CHECK (notification_type = 'email' OR NOT share)`) : le systray
    natif ne peut donc jamais s'afficher pour un candidat. Plutôt que de forcer
    le mécanisme natif, ces routes lisent directement les `mail.message` déjà
    créés par les `message_post()` du workflow — ils existent indépendamment du
    canal par lequel ils ont été notifiés.

    Toute la résolution de propriété vit dans `res.partner`
    (`_opex_notification_*`) : le controller ne reçoit aucun identifiant du
    client et n'a donc rien à filtrer lui-même.
    """

    _notifications_per_page = 30

    @http.route(['/my/notifications'], type='http', auth='user', website=True, sitemap=False)
    def portal_notifications(self, **kw):
        """Liste des notifications du candidat, la plus récente en tête.

        La consultation marque les notifications comme vues — c'est le
        comportement attendu d'une cloche. Le calcul du « nouveau » est fait
        *avant* la mise à jour, pour que la page affiche encore ce qui vient
        d'être lu ; c'est le rechargement suivant qui montrera la liste apaisée.
        """
        partner = request.env.user.partner_id
        entries = partner._opex_notification_entries(limit=self._notifications_per_page)

        values = self._prepare_portal_layout_values()
        values.update({
            'notification_entries': entries,
            'page_name': 'notifications',
        })
        partner._opex_mark_notifications_seen()
        return request.render('opex_membership.portal_notifications', values)

    @http.route(
        ['/my/notifications/mark_seen'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_notifications_mark_seen(self, **post):
        """Marque explicitement les notifications comme lues.

        Le changement d'état passe par un POST, comme il se doit ; la route
        sert au bouton « Tout marquer comme lu » et reste appelable seule.
        """
        request.env.user.partner_id._opex_mark_notifications_seen()
        return request.redirect(post.get('redirect') or '/my/notifications')
