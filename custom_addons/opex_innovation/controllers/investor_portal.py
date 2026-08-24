from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal

from ..models.final_evaluation import CRITERIA
from .matching_portal import MatchingCandidatePortal


class InvestorOpportunityPortal(MatchingCandidatePortal):
    """Section 26 — l'espace investisseur.

    « L'investisseur ne voit pas tous les projets. Il voit uniquement les
    projets proposés, avec les informations autorisées. »

    Étend le contrôleur de la section 20 plutôt que d'ouvrir un second espace :
    l'expert et l'investisseur reçoivent des propositions par le même
    mécanisme, seule la liste d'informations diffère — et cette différence est
    portée par `_matching_teaser()`, côté modèle, pas par deux contrôleurs
    parallèles qui divergeraient.
    """

    def _my_proposals(self):
        """⚠ Renforcement du filtre de l'Extension 15.

        La version précédente ne consultait que la table des candidats :
        `partner_id` de l'utilisateur, et `state = 'accepted'`. Cela marche
        tant que les deux sources restent d'accord — mais elles peuvent
        diverger.

        `propose_to_candidate()` crée une ligne `instance.actor` en même temps
        que la proposition. Si cet acteur est ensuite **révoqué** — le cluster
        retire un investisseur du dossier — la ligne de candidature, elle,
        reste à `accepted`. L'accès aurait donc survécu à sa révocation : le
        dossier restait visible à quelqu'un à qui on venait de le fermer.

        La vérité de la visibilité est `instance.actor`, et une seule fonction
        la tranche : `instance._has_access()`. C'est elle qu'on interroge ici,
        en second filtre, sur **chaque** proposition.
        """
        proposals = super()._my_proposals()
        user = request.env.user
        return proposals.filtered(
            lambda c: c.instance_id and c.instance_id._has_access(user))

    def _my_proposal(self, candidate_id):
        """Une proposition précise, ou rien.

        Passe par `_my_proposals()` : le contrôle d'accès reste une seule
        fonction, réutilisée par toutes les routes de l'espace. Une route qui
        referait sa propre requête finirait par oublier un filtre.
        """
        return self._my_proposals().filtered(
            lambda c: c.id == candidate_id)[:1]

    @http.route(['/my/innovation/opportunity/<int:candidate_id>'],
                type='http', auth='user', website=True)
    def portal_opportunity_detail(self, candidate_id, **kw):
        """Bouton [Voir le projet] de la section 26.

        ⚠ Le contrôle est **serveur**, avant tout rendu. Un gabarit qui
        masquerait le contenu à l'affichage laisserait la page se construire
        avec les données dedans : il suffit de lire la source. Ici, un
        investisseur à qui le projet n'est pas proposé est renvoyé avant même
        que le dictionnaire ne soit assemblé.
        """
        candidate = self._my_proposal(candidate_id)
        if not candidate:
            return request.redirect('/my/innovation/opportunities')

        detail = request.env['opex.innovation.project'].sudo()._matching_detail(
            candidate)
        return request.render('opex_innovation.portal_opportunity_detail', {
            'candidate': candidate,
            'd': detail,
            'page_name': 'innovation_opportunities',
        })


class FinalEvaluationPortal(CustomerPortal):
    """Section 29 — l'évaluation finale, côté porteur et côté cluster."""

    def _evaluable_project(self, project_id):
        """Le projet **si** l'utilisateur a le droit de l'évaluer.

        Une seule question, un seul appel : `can_evaluate_finally()` répond à
        la fois « qui » et « à quel titre ». Le gabarit s'en sert pour le
        bouton, la route pour le contrôle — même fonction, pas deux réponses
        possibles.
        """
        project = request.env['opex.innovation.project'].sudo().browse(
            project_id).exists()
        if not project:
            return project.browse(), False
        side = project.can_evaluate_finally(request.env.user)
        return (project, side) if side else (project.browse(), False)

    @http.route(['/my/innovation/<int:project_id>/evaluation-finale'],
                type='http', auth='user', website=True,
                methods=['GET', 'POST'])
    def portal_final_evaluation(self, project_id, **post):
        project, side = self._evaluable_project(project_id)
        if not project:
            return request.redirect('/my/innovation')

        error = None
        if request.httprequest.method == 'POST':
            try:
                # ⚠ `side` n'est pas lu dans `post`. Il est déduit de
                # l'identité, côté serveur. Un champ caché dans le formulaire
                # permettrait à un porteur de déposer l'avis du cluster sur
                # l'accompagnement qu'il a lui-même reçu.
                project.submit_final_evaluation(
                    notes=post,
                    commentaire=post.get('commentaire'),
                    user=request.env.user,
                )
                return request.redirect('/my/innovation/%s' % project.id)
            except UserError as exception:
                error = exception.args[0]

        # La grille est décrite une fois, côté modèle. Recopier les quatre
        # libellés dans le gabarit les ferait diverger au premier ajustement,
        # et la note enregistrée ne correspondrait plus à la question posée.
        return request.render('opex_innovation.portal_final_evaluation', {
            'project': project,
            'side': side,
            'criteria': list(CRITERIA.items()),
            'mine': project.visible_final_evaluations(request.env.user),
            'error': error,
            'page_name': 'innovation_project',
        })
