from odoo import http
from odoo.http import request


class WorkflowFormPortal(http.Controller):
    """Rendu générique d'un formulaire dynamique côté portail.

    Le moteur sert la page ; il ne connaît toujours rien au métier. La route
    ne nomme ni « projet » ni « dossier » : elle prend une instance et un
    formulaire, et rend ce que la configuration décrit.

    ⚠ Aucun contrôle d'accès réécrit ici. La visibilité passe par
    `instance._has_access()`, l'unique fonction de l'Extension 5. Un second
    contrôle, même correct au moment où on l'écrit, finirait par diverger.
    """

    def _instance(self, instance_id, level='limited'):
        """L'instance demandée, si l'utilisateur y a droit — sinon vide.

        L'identifiant vient de l'URL, donc du client : il est résolu en
        `sudo()` puis **soumis au contrôle d'accès**, jamais utilisé
        directement. La distinction compte : lire d'abord sous l'identité de
        l'utilisateur donnerait une AccessError brute là où on veut une page
        d'erreur, et lire en sudo sans contrôler donnerait tous les dossiers à
        tout le monde.
        """
        instance = request.env['opex.workflow.instance'].sudo().browse(
            instance_id).exists()
        if not instance or not instance._has_access(request.env.user, level):
            return request.env['opex.workflow.instance'].browse()
        return instance

    def _form(self, instance, form_id):
        form = request.env['opex.workflow.form'].sudo().browse(form_id).exists()
        if not form or form.definition_id != instance.definition_id:
            return request.env['opex.workflow.form'].browse()
        return form

    @http.route(
        ['/my/workflow/<int:instance_id>/form/<int:form_id>'],
        type='http', auth='user', website=True, methods=['GET', 'POST'],
    )
    def workflow_dynamic_form(self, instance_id, form_id, **post):
        instance = self._instance(instance_id)
        if not instance:
            return request.redirect('/my')
        form = self._form(instance, form_id)
        if not form:
            return request.redirect('/my')

        errors = []
        saved = False

        if request.httprequest.method == 'POST':
            validate = post.get('action') == 'validate'
            result = form.save(instance, post, partial=not validate)
            errors = result or []
            saved = not errors

        # Relu **après** l'enregistrement : une réponse peut rendre visible un
        # champ qui ne l'était pas — c'est tout l'intérêt du dossier
        # progressif. Rendre la liste calculée avant l'écriture afficherait le
        # formulaire d'avant la réponse.
        values = {
            'instance': instance,
            'form': form,
            'fields': form.render_values(instance),
            'stage_label': instance.current_stage_id.user_label
                           or instance.current_stage_id.name,
            'errors': errors,
            'saved': saved,
            'post_url': '/my/workflow/%s/form/%s' % (instance.id, form.id),
        }
        return request.render('opex_workflow.workflow_dynamic_form_page', values)

    @http.route(
        ['/my/workflow/<int:instance_id>/form'],
        type='http', auth='user', website=True,
    )
    def workflow_current_form(self, instance_id, **kw):
        """Raccourci : le formulaire de l'étape où en est le dossier.

        C'est l'URL que porte un lien « Compléter mon dossier » : elle reste
        valable quand le dossier avance, alors qu'un lien vers un formulaire
        précis se périme à la transition suivante.
        """
        instance = self._instance(instance_id)
        if not instance:
            return request.redirect('/my')
        form = instance.current_stage_id.sudo().form_id
        if not form:
            form = request.env['opex.workflow.form'].form_for_stage(instance)
        if not form:
            return request.redirect('/my')
        return request.redirect(
            '/my/workflow/%s/form/%s' % (instance.id, form.id))
