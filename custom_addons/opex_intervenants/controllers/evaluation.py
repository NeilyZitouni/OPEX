from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal


class MissionEvaluationPortal(CustomerPortal):
    """§30 et §33 — le client rend sa grille depuis le portail.

    L'ÉCRAN QUI MANQUAIT, ET CE QUI L'AVAIT LAISSÉ MANQUER

    Le moteur ouvrait déjà `evaluation_submit` et `evaluation_resume` au rôle
    `client`, l'`ir.rule` bornait déjà l'écriture à l'auteur tant que la
    grille n'est pas rendue, et le portail avait déjà le droit d'écrire sur
    `opex.mission.evaluation`. Tout était en place **sauf la route** :
    l'Extension 10 l'avait déclarée comme limite, propriétaire « Extensions 11
    et 12 », et ni l'une ni l'autre ne l'a refermée.

    Relevé de collisions avant d'écrire ce fichier — `CustomerPortal` est
    l'arbre commun de sept classes des quatre modules. `_own_evaluations`,
    `_evaluation_editable` et `portal_my_evaluations` n'y sont pas repris :
    tout est préfixé `_intervenants_evaluation_*` /
    `portal_intervenants_evaluation_*`. Seul `_prepare_home_portal_values`
    garderait son nom, et il n'est pas surchargé ici — la tuile d'accueil
    appartient à `MissionRequestPortal`, et deux tuiles partageant une clé
    laisseraient la seconde masquée.

    Routes → `/my/missions/evaluations` et `/my/missions/evaluation/<id>`,
    dans l'espace de noms du module (règle 1).
    """

    #: Les deux transitions que cet écran propose, et rien d'autre. Liste
    #: fermée, la même pour les boutons et pour le POST — règle 2, et le
    #: motif du §27 bis : deux listes feraient apparaître un bouton que le
    #: POST refuse.
    _INTERVENANTS_EVALUATION_TRANSITIONS = ('evaluation_submit',
                                            'evaluation_resume')

    # ------------------------------------------------------------
    # Le périmètre — toujours côté serveur
    # ------------------------------------------------------------

    def _intervenants_evaluation_own(self):
        """Les grilles que **ce** contact doit remplir.

        Deux bornes, et les deux comptent :

        - `client_id`, parce qu'une évaluation appartient à celui qui la rend ;
        - `evaluateur = 'client'`, parce que la grille du cluster juge aussi
          le respect des procédures internes. `_grant_actors()` le dit déjà
          côté acteurs ; le redire ici n'est pas une seconde vérité mais la
          même, posée à l'endroit qui décide de la page.

        L'intervenant est acteur de ses évaluations **en lecture** — ce sont
        ses notes. Il n'entre pas dans cet écran : on n'évalue pas soi-même.
        """
        return request.env['opex.mission.evaluation'].sudo().search(
            [('client_id', '=', request.env.user.partner_id.id),
             ('evaluateur', '=', 'client')],
            order='create_date desc')

    def _intervenants_evaluation_one(self, evaluation_id):
        return self._intervenants_evaluation_own().filtered(
            lambda e: e.id == evaluation_id)[:1]

    def _intervenants_evaluation_editable(self, evaluation):
        """`pending` est la seule étape où le client écrit.

        Une fois rendue, la grille ne se réécrit plus sous le responsable :
        la version examinée doit être celle qui a été lue. C'est le parti de
        la candidature (`interested`) et du dossier d'adhésion, repris tel
        quel — et c'est exactement ce que dit l'`ir.rule` « modifiable par son
        auteur tant qu'elle n'est pas rendue ».
        """
        return bool(evaluation) \
            and evaluation.sudo().workflow_stage_id.code == 'pending'

    def _intervenants_evaluation_actions(self, evaluation):
        """Ce que le moteur ouvre à cet utilisateur, filtré par la liste."""
        options = evaluation.workflow_instance_id.sudo().transition_options(
            user=request.env.user)
        return [
            option for option in options
            if option['transition'].code
            in self._INTERVENANTS_EVALUATION_TRANSITIONS
        ]

    def _intervenants_evaluation_values(self, evaluation, error=None):
        return {
            'evaluation': evaluation,
            'grille': evaluation.evaluation_grid(),
            'actions': self._intervenants_evaluation_actions(evaluation),
            'modifiable': self._intervenants_evaluation_editable(evaluation),
            'error': error,
            'page_name': 'intervenants_evaluation',
        }

    # ------------------------------------------------------------
    # Les deux écrans
    # ------------------------------------------------------------

    @http.route(['/my/missions/evaluations'], type='http', auth='user',
                website=True)
    def portal_intervenants_evaluations(self, **kw):
        return request.render('opex_intervenants.portal_my_evaluations', {
            'evaluations': self._intervenants_evaluation_own(),
            'page_name': 'intervenants_evaluation',
        })

    @http.route(['/my/missions/evaluation/<int:evaluation_id>'], type='http',
                auth='user', website=True, methods=['GET', 'POST'])
    def portal_intervenants_evaluation(self, evaluation_id, **post):
        """Noter, puis rendre.

        Les six critères viennent d'`_criteria_fields()` par
        `evaluation_grid()` : l'écran ne connaît **aucun nom de champ**. Les
        dix notes du modèle couvrent deux grilles dont seules six s'appliquent
        ici, et une liste réécrite dans ce controller aurait fait la moyenne
        sur les dix — c'est la régression volontaire de l'Extension 10, avec
        son `3.0 != 5.0`.

        Le passage à « rendue » n'est pas décidé ici : il est demandé au
        moteur, qui porte les deux conditions du §39 — la mission doit être
        validée (règle 7) et la grille complète. Ce controller rend le refus
        lisible, il ne le devance pas.
        """
        evaluation = self._intervenants_evaluation_one(evaluation_id)
        if not evaluation:
            return self._intervenants_evaluation_refused()

        error = None
        if request.httprequest.method == 'POST':
            error = self._intervenants_evaluation_post(evaluation, post)
            if error is None:
                return request.redirect(
                    '/my/missions/evaluation/%s' % evaluation.id)

        return request.render(
            'opex_intervenants.portal_evaluation_form',
            self._intervenants_evaluation_values(evaluation, error=error))

    def _intervenants_evaluation_post(self, evaluation, post):
        """Enregistre, puis franchit si on le lui demande. `None` = succès.

        L'écriture passe par l'identité de l'utilisateur, **sans `sudo()`** :
        le portail a le droit d'écrire sur ce modèle et l'`ir.rule` borne à
        l'auteur et à l'étape. Un `sudo()` ici remplacerait cette garde par
        la confiance qu'on accorde à ce fichier.
        """
        code = (post.get('action') or '').strip()
        if code not in self._INTERVENANTS_EVALUATION_TRANSITIONS \
                and code != 'save':
            return _("Action inconnue sur une évaluation.")

        if code in ('save', 'evaluation_submit'):
            if not self._intervenants_evaluation_editable(evaluation):
                return _("Cette grille n'est plus modifiable : elle a déjà "
                         "été rendue.")
            try:
                evaluation.write(self._intervenants_evaluation_scores(
                    evaluation, post))
            except (UserError, ValueError) as refus:
                return str(refus)
            if code == 'save':
                return None

        transition = evaluation.workflow_instance_id.sudo()\
            .available_transitions(user=request.env.user)\
            .filtered(lambda t: t.code == code)[:1]
        if not transition:
            return _("Cette action n'est pas disponible : soit la grille a "
                     "changé d'étape, soit votre rôle ne l'autorise pas.")
        try:
            evaluation.workflow_do_transition(transition)
        except UserError as refus:
            return str(refus)
        return None

    def _intervenants_evaluation_scores(self, evaluation, post):
        """Les six notes reçues, bornées avant d'atteindre l'ORM.

        Une valeur illisible vaut **0**, c'est-à-dire « pas encore noté », et
        non une erreur serveur : c'est la même asymétrie prudente que les
        dates du catalogue public (E12). Zéro laisse simplement la grille
        incomplète, et la condition du moteur refusera de la rendre.

        Les noms de champs acceptés sont ceux d'`_criteria_fields()` : un
        `note_procedures` glissé dans le POST — critère de la grille cluster —
        n'est pas écrit, parce qu'il n'est pas dans la liste applicable.
        """
        values = {}
        for name in evaluation._criteria_fields():
            raw = (post.get(name) or '').strip()
            try:
                score = int(raw)
            except ValueError:
                score = 0
            values[name] = score if 0 <= score <= 5 else 0
        values['commentaire'] = (post.get('commentaire') or '').strip()
        return values

    def _intervenants_evaluation_refused(self):
        """Règle 25 : un refus rend une page, il ne rebondit pas.

        Un seul message, que la grille n'existe pas, qu'elle appartienne à
        quelqu'un d'autre ou qu'elle soit celle du cluster — règle 3.
        """
        return request.render('opex_intervenants.mission_access_refused', {
            'refus': _(
                "Cette évaluation n'existe pas, ou elle n'est pas à remplir "
                "depuis ce compte. Seul le client d'une mission rend la "
                "grille qui la concerne."),
            'page_name': 'intervenants_evaluation',
        })
