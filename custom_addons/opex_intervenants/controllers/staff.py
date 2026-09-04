from urllib.parse import quote

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request


class MissionStaffPortal(http.Controller):
    """L'écran du responsable — §6 et §16.

    UN CONTRÔLE D'ACCÈS = UNE SEULE FONCTION

    Toutes les routes passent par `res.users._is_missions_staff()`, et elle
    seule. Elle vit sur le modèle et non ici, pour la raison qui a coûté du
    temps sur le Module 2 : un gabarit ne peut pas appeler un helper de
    controller, et le `t-if` d'une tuile doit poser exactement la même question
    que la route qu'elle ouvre.

    Hérite de `http.Controller` et **non** de `CustomerPortal` : ces écrans
    ne sont pas l'espace personnel d'un client, et rien ici n'a besoin de
    `_prepare_portal_layout_values()`. On reste donc hors de l'arbre fusionné —
    une classe de moins où un nom peut entrer en collision. C'est le parti
    d'`InnovationStaffPortal`, repris tel quel.

    Les noms sont malgré tout préfixés `staff_intervenants_*` : `staff_matching`
    et `staff_matching_decide` existent déjà dans `opex_innovation`, et rien ne
    garantit qu'un futur controller ne rejoindra pas le même arbre.
    """

    #: Les cinq actions du §6, et rien d'autre. Table plutôt que cinq `if` :
    #: ajouter une action est une ligne, et une action inconnue ne fait rien
    #: plutôt que de tomber dans un `else` silencieux.
    _INTERVENANTS_CANDIDATE_ACTIONS = {
        'invite': 'action_invite_to_mission',
        'shortlist': 'action_accept',
        'reject': 'action_reject',
        'reset': 'action_reset',
    }

    #
    # Le périmètre
    #

    def _intervenants_staff_user(self):
        """L'utilisateur connecté s'il est habilité, sinon un recordset vide.

        Renvoie plutôt que de lever : une route qui lève affiche une page
        d'erreur technique ; une route qui redirige garde l'utilisateur dans
        son espace. Le refus est total dans les deux cas.
        """
        user = request.env.user
        return user if user._is_missions_staff() \
            else request.env['res.users'].browse()

    def _intervenants_staff_missions(self):
        """Les appels que **ce** membre du personnel doit voir.

        `sudo()` **après** le contrôle d'habilitation : les `ir.rule` du moteur
        accordent la visibilité par ligne d'acteur, or le personnel tient son
        rôle d'un groupe et n'est acteur d'aucun dossier. Sans cela, sa file de
        travail serait vide — c'est exactement ce qui bloquait les demandes de
        profil du Module 2.

        L'ordre compte : on vérifie **puis** on lit en `sudo()`. L'inverse
        donnerait tous les dossiers à tout le monde.
        """
        if not self._intervenants_staff_user():
            return request.env['opex.mission.request'].browse()
        return request.env['opex.mission.request'].sudo().search(
            [('workflow_state', '=', 'running')], order='create_date desc')

    def _intervenants_staff_mission(self, mission_id):
        """Un appel précis, borné au périmètre du personnel connecté.

        Résolu **dans** la file plutôt que par un `browse()` direct : un
        identifiant deviné ne donne rien de plus que la liste n'en montrait.
        """
        return self._intervenants_staff_missions().filtered(
            lambda m: m.id == mission_id)[:1]

    def _intervenants_staff_back(self, mission, message=None):
        url = '/staff/missions/%s/matching' % mission.id
        if message:
            url += '?error=%s' % quote(str(message))
        return request.redirect(url)

    #
    # La file de travail
    #

    @http.route(['/staff/missions'], type='http', auth='user', website=True)
    def staff_intervenants_missions(self, **kw):
        if not self._intervenants_staff_user():
            return request.redirect('/my')
        return request.render('opex_intervenants.staff_missions', {
            'missions': self._intervenants_staff_missions(),
            'page_name': 'staff_missions',
        })

    #
    # §6 — L'écran de matching
    #

    @http.route(['/staff/missions/<int:mission_id>/matching'], type='http',
                auth='user', website=True)
    def staff_intervenants_matching(self, mission_id, **kw):
        """Les propositions, leur score, et de quoi décider.

        Cinq actions, celles du §6 : Inviter · Écarter · Mettre en short-list ·
        Consulter le profil · Voir l'explication du score.

        Rien ici ne décide à la place du responsable. Aucune transition n'est
        franchie, aucun score n'en déclenche une. « L'IA recommande. Elle ne
        doit pas automatiquement décider seule. »
        """
        if not self._intervenants_staff_user():
            return request.redirect('/my')
        mission = self._intervenants_staff_mission(mission_id)
        if not mission:
            return request.redirect('/staff/missions')

        candidats = mission.matching_candidate_ids.sorted(
            lambda c: (-c.score, c.partner_id.display_name))
        return request.render('opex_intervenants.staff_matching', {
            'mission': mission,
            'candidats': candidats,
            # Les critères appliqués sont affichés **avant** la liste : un
            # score ne se lit pas sans savoir sur quoi il porte.
            'criteres': mission.matching_criteria(),
            'error': kw.get('error'),
            'page_name': 'staff_missions',
        })

    @http.route(['/staff/missions/<int:mission_id>/matching/run'], type='http',
                auth='user', website=True, methods=['POST'])
    def staff_intervenants_matching_run(self, mission_id, **post):
        """Lance le matching. **Geste humain, jamais automatique.**

        Le §19 prévoit « lancement automatique du matching si activé » ; ce
        déclenchement conditionnel viendra avec les actions de transition de
        l'Extension 11. Ici, c'est un bouton — et c'est déjà ce que demande le
        §6, qui décrit un responsable qui consulte et arbitre.
        """
        if not self._intervenants_staff_user():
            return request.redirect('/my')
        mission = self._intervenants_staff_mission(mission_id)
        if not mission:
            return request.redirect('/staff/missions')
        try:
            mission.run_smart_matching()
        except UserError as refus:
            return self._intervenants_staff_back(mission, refus)
        return self._intervenants_staff_back(mission)

    @http.route(['/staff/missions/<int:mission_id>/matching/<int:candidate_id>'
                 '/<string:decision>'],
                type='http', auth='user', website=True, methods=['POST'])
    def staff_intervenants_matching_decide(self, mission_id, candidate_id,
                                           decision, **post):
        """Les quatre décisions du responsable sur une proposition.

        Le candidat est résolu **dans** les propositions de cet appel, jamais
        par un `browse()` sur l'identifiant reçu : une valeur forgée ne désigne
        rien.

        Aucune de ces décisions ne fait avancer l'appel. « Inviter » crée une
        candidature — qui naît sur **sa propre** machine à états — et la mission
        reste où elle est. C'est l'indépendance des deux workflows, vérifiée
        depuis l'Extension 1.
        """
        if not self._intervenants_staff_user():
            return request.redirect('/my')
        mission = self._intervenants_staff_mission(mission_id)
        if not mission:
            return request.redirect('/staff/missions')

        methode = self._INTERVENANTS_CANDIDATE_ACTIONS.get(decision)
        if not methode:
            return self._intervenants_staff_back(
                mission, _("Action inconnue."))

        candidat = mission.matching_candidate_ids.filtered(
            lambda c: c.id == candidate_id)[:1]
        if not candidat:
            return self._intervenants_staff_back(
                mission, _("Cette proposition n'existe plus."))

        try:
            getattr(candidat.sudo(), methode)()
        except UserError as refus:
            return self._intervenants_staff_back(mission, refus)
        return self._intervenants_staff_back(mission)

    #
    # §10 — LE POOL UNIQUE ET LA COMPARAISON
    #

    #: Les transitions que le responsable franchit depuis l'écran de
    #: comparaison. **Des codes de transition**, pas des méthodes : c'est le
    #: moteur qui décide si elles sont ouvertes, avec quel rôle et sous quelle
    #: condition. Une action inconnue ne fait rien plutôt que de tomber dans un
    #: `else` silencieux.
    _INTERVENANTS_POOL_TRANSITIONS = (
        'application_screen', 'application_shortlist', 'application_select',
        'application_back_to_screened',
        'application_reject_applied', 'application_reject_screened',
        'application_reject_shortlisted',
    )

    @http.route(['/staff/missions/<int:mission_id>/pool'], type='http',
                auth='user', website=True)
    def staff_intervenants_pool(self, mission_id, **kw):
        """L'écran de comparaison du §10.

        **Le deuxième critère d'acceptation du §21 se lit ici** : « une
        candidature issue du matching et une candidature Web sont comparables
        dans le même écran ». Elles le sont parce qu'elles sortent du même
        modèle avec la même forme — `comparison_row()` produit les mêmes clés
        pour les quatre origines, et `source` n'est qu'une colonne de plus.

        Des **dictionnaires**, jamais les recordsets : le responsable compare
        des candidats, il n'a pas à recevoir le profil complet de chacun.
        """
        if not self._intervenants_staff_user():
            return request.redirect('/my')
        mission = self._intervenants_staff_mission(mission_id)
        if not mission:
            return request.redirect('/staff/missions')

        applications = mission.sudo().application_ids.sorted(
            lambda a: (-a.score, a.partner_id.display_name))
        colonnes = {}
        for application in applications:
            colonnes.setdefault(application.pool_column, []).append(
                application.comparison_row())

        from odoo.addons.opex_intervenants.models.mission_application_pool \
            import POOL_COLUMNS
        return request.render('opex_intervenants.staff_pool', {
            'mission': mission,
            'colonnes': POOL_COLUMNS,
            'par_colonne': colonnes,
            'lignes': [a.comparison_row() for a in applications],
            # Ce que le responsable peut faire sur chaque candidature vient du
            # **moteur**, pas d'une liste écrite ici : le jour où le processus
            # change, cet écran suit.
            'actions': {
                a.id: a.workflow_instance_id.sudo().transition_options(
                    user=request.env.user)
                for a in applications
            },
            'error': kw.get('error'),
            'page_name': 'staff_missions',
        })

    @http.route(['/staff/missions/<int:mission_id>/pool/<int:application_id>'
                 '/<string:code>'],
                type='http', auth='user', website=True, methods=['POST'])
    def staff_intervenants_pool_transition(self, mission_id, application_id,
                                           code, **post):
        """Fait avancer **une candidature**, jamais l'appel.

        C'est ici que la séparation des deux machines se voit à l'écran :
        qualifier, short-lister ou écarter un candidat ne déplace pas l'appel
        d'un millimètre. L'appel avance par ses propres transitions, quand le
        décideur attribue.

        Aucun droit n'est rejugé : la transition est cherchée **dans** celles
        que le moteur propose à cet utilisateur, puis franchie par
        `workflow_do_transition()`, qui repasse par
        `_check_transition_allowed()`. Le motif obligatoire est exigé par la
        configuration, pas par ce controller.
        """
        if not self._intervenants_staff_user():
            return request.redirect('/my')
        mission = self._intervenants_staff_mission(mission_id)
        if not mission:
            return request.redirect('/staff/missions')
        if code not in self._INTERVENANTS_POOL_TRANSITIONS:
            return self._intervenants_pool_back(
                mission, _("Action inconnue sur une candidature."))

        application = mission.sudo().application_ids.filtered(
            lambda a: a.id == application_id)[:1]
        if not application:
            return self._intervenants_pool_back(
                mission, _("Cette candidature n'existe plus."))

        transition = application.workflow_instance_id.sudo()\
            .available_transitions(user=request.env.user)\
            .filtered(lambda t: t.code == code)[:1]
        if not transition:
            return self._intervenants_pool_back(mission, _(
                "Cette action n'est plus disponible sur cette candidature."))

        try:
            application.workflow_do_transition(
                transition, comment=(post.get('comment') or '').strip())
        except UserError as refus:
            return self._intervenants_pool_back(mission, refus)
        return self._intervenants_pool_back(mission)

    def _intervenants_pool_back(self, mission, message=None):
        url = '/staff/missions/%s/pool' % mission.id
        if message:
            url += '?error=%s' % quote(str(message))
        return request.redirect(url)

    #
    # « Consulter le profil » — la cinquième action du §6
    #

    @http.route(['/staff/missions/<int:mission_id>/matching/<int:candidate_id>'
                 '/profil'],
                type='http', auth='user', website=True)
    def staff_intervenants_candidate_profile(self, mission_id, candidate_id,
                                             **kw):
        """Le capital de l'intervenant, tel que le matching l'a lu.

        On sert **ce que le matching a comparé**, pas la fiche complète du
        contact. Le responsable doit pouvoir vérifier un score, pas parcourir
        les données personnelles d'un expert qui ne l'a pas encore rencontré.
        """
        if not self._intervenants_staff_user():
            return request.redirect('/my')
        mission = self._intervenants_staff_mission(mission_id)
        if not mission:
            return request.redirect('/staff/missions')
        candidat = mission.matching_candidate_ids.filtered(
            lambda c: c.id == candidate_id)[:1]
        if not candidat:
            return self._intervenants_staff_back(mission)

        profile = candidat.partner_id.sudo().expert_profile_id
        return request.render('opex_intervenants.staff_candidate_profile', {
            'mission': mission,
            'candidat': candidat,
            'profile': profile,
            'summary': profile.capital_summary() if profile else {},
            'page_name': 'staff_missions',
        })
