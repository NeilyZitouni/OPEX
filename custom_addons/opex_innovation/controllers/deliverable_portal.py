import base64

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal


class DeliverablePortal(CustomerPortal):
    """Sections 23 et 24 — le porteur dépose, l'expert valide.

    **Le contrôle d'accès est une seule fonction**, `_deliverable()`, appelée
    par les trois routes. Elle interroge `instance._has_access()`, qui est la
    seule fonction de visibilité du moteur. Une route qui referait sa propre
    requête finirait par oublier une condition — et c'est celle-là qui recevrait
    la requête forgée.
    """

    def _deliverable(self, deliverable_id):
        """Le livrable **si** l'utilisateur y a accès, sinon un recordset vide.

        Deux titres possibles, et un seul contrôle : le porteur du projet, ou
        un acteur désigné sur ce livrable. Être expert du cluster ne suffit
        pas ; c'est la ligne d'acteur qui donne accès à celui-ci.
        """
        deliverable = request.env['opex.innovation.deliverable'].sudo().browse(
            deliverable_id).exists()
        if not deliverable:
            return deliverable

        user = request.env.user
        est_porteur = deliverable.partner_id == user.partner_id
        instance = deliverable.workflow_instance_id
        est_acteur = bool(instance and instance._has_access(user))
        return deliverable if (est_porteur or est_acteur) else deliverable.browse()

    @http.route(['/my/innovation/deliverable/<int:deliverable_id>'],
                type='http', auth='user', website=True)
    def portal_deliverable(self, deliverable_id, **kw):
        deliverable = self._deliverable(deliverable_id)
        if not deliverable:
            return request.redirect('/my/innovation')

        instance = deliverable.workflow_instance_id
        return request.render('opex_innovation.portal_deliverable', {
            'deliverable': deliverable,
            # Les boutons viennent du moteur : celui qui n'a pas le droit de
            # franchir une transition ne la voit pas proposée.
            'options': instance.transition_options() if instance else [],
            'corrections': deliverable.correction_history(),
            'error': kw.get('error'),
            'page_name': 'innovation_deliverable',
        })

    @http.route(['/my/innovation/deliverable/<int:deliverable_id>/upload'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_deliverable_upload(self, deliverable_id, **post):
        """Dépôt initial, ou nouvelle version après correction — section 23.

        Les deux cas passent par ici, et c'est le **modèle** qui les distingue :
        `submit_new_version()` si le livrable revient d'une correction, un dépôt
        simple sinon. Le contrôleur ne rejoue pas cette décision.
        """
        deliverable = self._deliverable(deliverable_id)
        if not deliverable or deliverable.partner_id != request.env.user.partner_id:
            return request.redirect('/my/innovation')

        upload = request.httprequest.files.get('file')
        contenu = base64.b64encode(upload.read()) if upload else False
        nom = upload.filename if upload else False

        url = '/my/innovation/deliverable/%s' % deliverable.id
        try:
            if deliverable.workflow_stage_id.code == 'correction_requested':
                deliverable.submit_new_version(
                    file=contenu, filename=nom, user=request.env.user)
            else:
                if contenu:
                    deliverable.sudo().write(
                        {'file': contenu, 'filename': nom})
                transition = deliverable._transition('deliverable_submit')
                deliverable.workflow_do_transition(transition)
        except UserError as exception:
            return request.redirect('%s?error=%s' % (url, exception.args[0]))
        return request.redirect(url)

    @http.route(['/my/innovation/deliverable/<int:deliverable_id>/decide'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_deliverable_decide(self, deliverable_id, **post):
        """Valider ou Demander une correction — section 24.

        Le contrôleur ne vérifie **pas** que l'utilisateur est expert : c'est
        `_check_transition_allowed()` du moteur qui tranche, et lui seul. Un
        second contrôle ici finirait par dire autre chose que celui-là.
        """
        deliverable = self._deliverable(deliverable_id)
        if not deliverable:
            return request.redirect('/my/innovation')

        code = post.get('transition_code')
        url = '/my/innovation/deliverable/%s' % deliverable.id
        if code not in ('deliverable_validate', 'deliverable_request_correction'):
            return request.redirect(url)

        try:
            deliverable.workflow_do_transition(
                deliverable._transition(code),
                comment=(post.get('comment') or '').strip())
        except UserError as exception:
            return request.redirect('%s?error=%s' % (url, exception.args[0]))
        return request.redirect(url)
