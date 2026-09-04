from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal


class EvaluationPortal(CustomerPortal):
    """Espace de l'évaluateur — section 15.

    **Le point de sécurité le plus sensible du module.**

    Aucune de ces pages ne rend l'avis d'un autre évaluateur. Pas masqué en
    CSS, pas dans un bloc replié, pas dans un attribut de données : absent. Ici,
    « présent dans le HTML » suffirait à violer la confidentialité — un
    évaluateur curieux n'a qu'à ouvrir la source de la page.
    """

    #: Champs de la grille que l'évaluateur remplit. Liste fermée : rien
    #: d'autre ne peut être écrit depuis le formulaire, quelle que soit la clé
    #: envoyée.
    _SCORE_FIELDS = (
        'score_innovation', 'score_pertinence', 'score_faisabilite',
        'score_marche', 'score_equipe', 'score_impact',
    )
    _TEXT_FIELDS = (
        'commentaires', 'observations', 'points_forts', 'points_faibles',
        'risques', 'recommandations', 'propositions_amelioration',
    )

    def _text_layout(self, evaluation):
        """Les zones de texte de l'avis, libellés compris.

        Construite ici plutôt qu'en `t-foreach` littéral dans le gabarit : une
        liste Python écrite dans un attribut XML doit survivre à deux couches
        d'échappement, et une apostrophe française y suffit à produire un
        `SyntaxError` au rendu. Les libellés viennent du modèle, qui les porte
        déjà.
        """
        Evaluation = request.env['opex.innovation.evaluation']
        return [
            {
                'name': name,
                'label': Evaluation._fields[name].string,
                'value': evaluation[name] or '',
            }
            for name in self._TEXT_FIELDS
        ]

    def _my_evaluations(self):
        """Les avis demandés à l'utilisateur connecté.

        Résolus depuis `partner_id`, jamais depuis un identifiant d'URL. Il n'y
        a donc rien à forger.
        """
        return request.env['opex.innovation.evaluation'].sudo().search(
            [('evaluator_id', '=', request.env.user.partner_id.id)],
            order='state, id desc')

    def _my_evaluation(self, evaluation_id):
        return self._my_evaluations().filtered(
            lambda e: e.id == evaluation_id)[:1]

    @http.route(['/my/innovation/evaluations'], type='http', auth='user',
                website=True)
    def portal_my_evaluations(self, **kw):
        return request.render('opex_innovation.portal_my_evaluations', {
            'evaluations': self._my_evaluations(),
            'page_name': 'innovation_evaluations',
        })

    @http.route(['/my/innovation/evaluation/<int:evaluation_id>'], type='http',
                auth='user', website=True, methods=['GET', 'POST'])
    def portal_evaluation(self, evaluation_id, **post):
        """La grille d'évaluation.

        Le contexte de rendu ne contient **que** l'avis de l'évaluateur. Le
        projet est passé pour qu'il puisse lire le dossier ; ses
        `evaluation_ids` ne sont jamais parcourus par le gabarit.
        """
        evaluation = self._my_evaluation(evaluation_id)
        if not evaluation:
            return request.redirect('/my/innovation/evaluations')

        error = None
        if request.httprequest.method == 'POST':
            if evaluation.state == 'submitted':
                error = _("Votre avis a déjà été rendu : il n'est plus modifiable.")
            else:
                error = self._save(evaluation, post)
                if not error and post.get('action') == 'submit':
                    try:
                        evaluation.sudo().action_submit()
                        return request.redirect(
                            '/my/innovation/evaluations')
                    except UserError as blocked:
                        error = str(blocked)
                elif not error:
                    return request.redirect(
                        '/my/innovation/evaluation/%s?saved=1' % evaluation.id)

        return request.render('opex_innovation.portal_evaluation_form', {
            'evaluation': evaluation,
            'project': evaluation.project_id,
            'criteria': self._criteria_layout(evaluation),
            'text_fields': self._text_layout(evaluation),
            'error': error,
            # `post` porte aussi bien les paramètres d'URL que ceux du
            # formulaire : la route n'a pas de `**kw` séparé.
            'saved': post.get('saved'),
            'page_name': 'innovation_evaluations',
        })

    def _criteria_layout(self, evaluation):
        """La grille prête à rendre : libellé, maximum, valeur courante.

        Construite depuis `_CRITERIA` du modèle : le barème vit à un seul
        endroit, et le gabarit ne le recopie pas.
        """
        Evaluation = request.env['opex.innovation.evaluation']
        return [
            {
                'name': name,
                'label': Evaluation._fields[name].string,
                'max': maximum,
                'value': evaluation[name],
            }
            for name, maximum in Evaluation._CRITERIA.items()
        ]

    def _save(self, evaluation, post):
        values = {}
        for name in self._SCORE_FIELDS:
            raw = (post.get(name) or '').strip()
            if raw == '':
                continue
            try:
                values[name] = int(raw)
            except ValueError:
                return _("« %s » doit être un nombre entier.") % name
        for name in self._TEXT_FIELDS:
            if isinstance(post.get(name), str):
                values[name] = post[name].strip()

        if evaluation.state == 'requested':
            values['state'] = 'in_progress'
        try:
            evaluation.sudo().write(values)
        except UserError as error:
            return str(error)
        return None
