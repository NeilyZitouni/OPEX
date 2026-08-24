from odoo import _, http
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal

from .staff_portal import InnovationStaffPortal


class MatchingStaffPortal(InnovationStaffPortal):
    """Écran du responsable OPEX — section 19.

    Hérite du controller staff pour réutiliser `_staff_user()` : le contrôle
    d'accès reste une seule fonction, conformément à la règle transversale.
    """

    @http.route(['/staff/innovation/<int:project_id>/matching'], type='http',
                auth='user', website=True)
    def staff_matching(self, project_id, **kw):
        if not self._staff_user():
            return request.redirect('/my')
        project = self._staff_project(project_id)
        if not project:
            return request.redirect('/staff/innovation')

        Candidate = request.env['opex.matching.candidate'].sudo()
        candidates = Candidate.search(
            [('instance_id', '=', project.workflow_instance_id.id)],
            order='score desc')

        # Trois listes, dans l'ordre de la section 19.
        by_type = {
            key: candidates.filtered(lambda c: c.candidate_type == key)
            for key in ('expert', 'mentor', 'investisseur')
        }
        return request.render('opex_innovation.staff_matching', {
            'project': project,
            'by_type': by_type,
            'labels': dict(
                Candidate._fields['candidate_type'].selection),
            'error': kw.get('error'),
            'page_name': 'staff_innovation',
        })

    @http.route(['/staff/innovation/<int:project_id>/matching/decide'],
                type='http', auth='user', website=True, methods=['POST'])
    def staff_matching_decide(self, project_id, **post):
        """Accepter / Modifier / Ignorer — la décision humaine.

        ⚠ Aucune de ces décisions ne fait avancer le dossier. Retenir un
        candidat lui ouvre l'accès à ce qui le concerne, rien de plus : la
        suite du processus se déclenche par une transition, séparément et
        volontairement.
        """
        if not self._staff_user():
            return request.redirect('/my')
        project = self._staff_project(project_id)
        if not project:
            return request.redirect('/staff/innovation')

        raw = (post.get('candidate_id') or '').strip()
        candidate = request.env['opex.matching.candidate'].sudo().search([
            ('instance_id', '=', project.workflow_instance_id.id),
            ('id', '=', int(raw) if raw.isdigit() else 0),
        ], limit=1)
        if not candidate:
            return request.redirect(
                '/staff/innovation/%s/matching' % project.id)

        decision = post.get('decision')
        if decision == 'accept':
            candidate.action_accept()
            # Section 20 : c'est ici que le candidat est **proposé**, donc ici
            # qu'on lui ouvre l'accès — et au niveau `limited`, pas au dossier
            # entier.
            project.propose_to_candidate(candidate)
        elif decision == 'reject':
            candidate.action_reject()
        elif decision == 'exclude':
            candidate.action_exclude()
        elif decision == 'reset':
            candidate.action_reset()

        return request.redirect('/staff/innovation/%s/matching' % project.id)


class MatchingCandidatePortal(CustomerPortal):
    """Espace du candidat proposé — section 20."""

    def _my_proposals(self):
        """Propositions faites à l'utilisateur connecté.

        Résolues depuis `partner_id`. Restreintes aux candidatures **retenues**
        par le responsable : une proposition écartée n'a jamais existé du point
        de vue du candidat.
        """
        return request.env['opex.matching.candidate'].sudo().search([
            ('partner_id', '=', request.env.user.partner_id.id),
            ('state', '=', 'accepted'),
        ], order='score desc')

    @http.route(['/my/innovation/opportunities'], type='http', auth='user',
                website=True)
    def portal_opportunities(self, **kw):
        proposals = self._my_proposals()
        return request.render('opex_innovation.portal_opportunities', {
            'proposals': [
                request.env['opex.innovation.project']
                .sudo()._matching_teaser(proposal)
                for proposal in proposals
            ],
            'page_name': 'innovation_opportunities',
        })

    @http.route(['/my/innovation/opportunities/<int:candidate_id>/respond'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_respond(self, candidate_id, **post):
        """[Je suis intéressé] / [Je ne suis pas disponible].

        La réponse du candidat ne déclenche rien non plus : elle informe le
        responsable, qui décide de la suite.
        """
        candidate = self._my_proposals().filtered(
            lambda c: c.id == candidate_id)[:1]
        if not candidate:
            return request.redirect('/my/innovation/opportunities')

        if post.get('response') == 'interested':
            candidate.action_interested()
            # ⑨ « Expert intéressé » — section 30.
            #
            # ⚠ Déclenché ici et non par une transition, parce qu'il n'y en a
            # pas : la réponse d'un candidat ne fait pas avancer le dossier.
            # « L'IA recommande, elle ne décide pas seule », et un candidat qui
            # se déclare disponible n'engage rien non plus.
            #
            # Le Python dit **quand**. Le message, le sous-type et les
            # destinataires restent dans `data/notifications.xml`.
            project = candidate.instance_id._get_record()
            if project and project._name == 'opex.innovation.project':
                project.sudo().notify_event(
                    'innovation_notify_expert_interesse')
        elif post.get('response') == 'declined':
            candidate.action_declined()
        return request.redirect('/my/innovation/opportunities')
