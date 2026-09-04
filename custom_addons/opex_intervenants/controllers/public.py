import base64
from urllib.parse import quote

from odoo import _, fields, http
from odoo.exceptions import UserError
from odoo.http import content_disposition, request


class MissionPublicPortal(http.Controller):
    """§7 — la rubrique « Opportunités / Missions OPEX ».

    AUCUN RECORDSET NE SORT D'ICI

    Toutes les routes passent au gabarit un **dictionnaire** produit par
    `public_card()` / `public_detail()`. Le visiteur anonyme n'a aucun droit sur
    `opex.mission.request` — il ne doit pas en avoir — et ce n'est pas le
    contrôle d'accès qui protège la page, c'est la liste fermée de clés.

    Passer le recordset « parce que c'est plus pratique » suffirait à publier le
    budget d'un appel le jour où quelqu'un ajoute un `t-out` : rien dans le code
    ne l'en empêcherait, et aucun test ne le verrait.

    `http.Controller` et non `CustomerPortal` : ces pages ne sont l'espace
    personnel de personne. Une classe de moins dans l'arbre fusionné, donc un
    nom de moins qui peut entrer en collision.
    """

    #: Champs du mini-profil que le candidat externe remplit. **Liste fermée** :
    #: tout ajout ici donne le droit d'écrire ce champ depuis le navigateur.
    #: `partner_id` n'y est évidemment pas — le `create()` du Module 2 le
    #: réécrit côté serveur pour un compte portail.
    _INTERVENANTS_MINI_PROFILE_FIELDS = (
        'domaine_expertise', 'specialites', 'fonction',
        'description_expertise',
    )

    #
    # La rubrique
    #

    def _intervenants_catalogue_filters(self, kw):
        """Nettoie les quatre filtres du §48 reçus de la requête.

        Le controller nettoie, le modèle filtre. Les deux identifiants sont
        convertis en entier ou abandonnés : une valeur qui n'est pas un entier
        est ignorée plutôt que passée au domaine, et une requête forgée ne
        choisit donc pas son propre critère. Même parti que l'annuaire du
        Module 1.

        Les dates sont **validées ici**, et pas seulement passées telles
        quelles. Une chaîne qui n'est pas une date atteint sinon le domaine,
        et PostgreSQL refuse la comparaison : `/missions?date_min=zz` rendait
        un **500** sur une page publique, ouverte à tout visiteur. Défaut
        trouvé par le test qui envoie une requête volontairement mal formée.

        Une valeur illisible neutralise donc son filtre. C'est la même
        asymétrie prudente que partout ailleurs : sur une page publique, ne pas
        filtrer vaut mieux que ne pas répondre.
        """
        def as_id(value):
            try:
                return int(value)
            except (TypeError, ValueError):
                return False

        def as_date(value):
            value = (value or '').strip()
            if not value:
                return ''
            try:
                fields.Date.from_string(value)
            except (TypeError, ValueError):
                return ''
            return value

        return {
            'domaine': as_id(kw.get('domaine')),
            'type': as_id(kw.get('type')),
            'localisation': (kw.get('localisation') or '').strip(),
            'date_min': as_date(kw.get('date_min')),
            'date_max': as_date(kw.get('date_max')),
        }

    @http.route(['/missions'], type='http', auth='public', website=True,
                sitemap=True)
    def portal_intervenants_public_missions(self, **kw):
        """Le catalogue des appels ouverts, filtré — §7, §48.

        Les filtres ont été ajoutés à l'Extension 12, à l'endroit annoncé.
        La route n'est pas redéfinie ailleurs : deux `@http.route` sur la même
        URL dans deux classes, et c'est la dernière chargée qui gagne — sans
        erreur, et sans qu'on sache laquelle.

        Les valeurs saisies sont **réaffichées** au gabarit pour que le
        formulaire reste rempli après filtrage. Un filtre qui s'oublie
        lui-même donne l'impression que rien ne s'est passé.
        """
        Mission = request.env['opex.mission.request']
        filters = self._intervenants_catalogue_filters(kw)
        return request.render('opex_intervenants.public_missions', {
            'missions': Mission.public_catalogue(filters=filters),
            'options': Mission.public_filter_options(),
            'filters': filters,
            'page_name': 'public_missions',
        })

    @http.route(['/missions/<int:mission_id>'], type='http', auth='public',
                website=True, sitemap=False)
    def portal_intervenants_public_mission(self, mission_id, **kw):
        """La fiche publique — §12 du Module 3, filtrée par le §14.

        L'appel est résolu **dans le catalogue**, pas par un `browse()` :
        un identifiant d'appel encore en brouillon, annulé ou déjà en sélection
        ne donne rien. Sans cela, il suffirait d'incrémenter un nombre dans
        l'URL pour lire un appel non publié.
        """
        mission = self._intervenants_public_mission(mission_id)
        if not mission:
            return request.redirect('/missions')

        partner = request.env.user.partner_id
        peut_candidater = False
        motif = None
        if not request.env.user._is_public():
            try:
                partner.opex_check_can_apply(mission)
                peut_candidater = True
            except UserError as refus:
                motif = str(refus)

        return request.render('opex_intervenants.public_mission_detail', {
            'mission': mission.public_detail(),
            'connecte': not request.env.user._is_public(),
            'peut_candidater': peut_candidater,
            # Le motif du refus, qu'il vienne du contrôle ci-dessus ou d'une
            # redirection : un bouton absent sans explication laisse le
            # candidat chercher ce qu'il a mal fait.
            'motif': motif or kw.get('error'),
            'page_name': 'public_missions',
        })

    def _intervenants_public_mission(self, mission_id):
        """Un appel **publié**, ou un recordset vide.

        `sudo()` assumé : la page est publique. Ce qui borne l'accès, c'est le
        domaine sur l'étape — pas les droits du visiteur, qui n'en a aucun.
        """
        Mission = request.env['opex.mission.request'].sudo()
        return Mission.search([
            ('id', '=', mission_id),
            ('workflow_stage_id.code', 'in', Mission.PUBLIC_STAGES),
        ], limit=1)

    #
    # Les pièces publiables
    #

    @http.route(['/missions/<int:mission_id>/document/<int:document_id>'],
                type='http', auth='public')
    def portal_intervenants_public_document(self, mission_id, document_id,
                                            **kw):
        """Sert une pièce **publiable** de cet appel.

        Le contrôle est refait ici et pas seulement à l'affichage : la liste
        des pièces vient d'un dictionnaire, mais l'URL, elle, se forge à la
        main.
        """
        mission = self._intervenants_public_mission(mission_id)
        if not mission:
            return request.redirect('/missions')
        document = mission.public_document(document_id)
        if not document or not document.file:
            return request.redirect('/missions/%s' % mission.id)

        contenu = base64.b64decode(document.file)
        return request.make_response(contenu, headers=[
            # `octet-stream` et pièce jointe : on ne rend pas dans la page un
            # fichier déposé par un tiers. Un HTML ou un SVG servi en ligne
            # s'exécuterait dans la session du visiteur.
            ('Content-Type', 'application/octet-stream'),
            ('Content-Length', str(len(contenu))),
            ('Content-Disposition', content_disposition(
                document.filename or document.name)),
        ])

    #
    # CTA « Je suis intéressé » — la règle 1 se vérifie ICI
    #

    @http.route(['/missions/<int:mission_id>/interesse'], type='http',
                auth='user', website=True, methods=['GET', 'POST'])
    def portal_intervenants_interesse(self, mission_id, **post):
        """Le CTA principal du §7.

        **`auth='user'`** : un visiteur anonyme est renvoyé vers la connexion
        par Odoo lui-même, avec retour sur cette URL. On ne réimplémente pas un
        parcours d'inscription.

        **La règle 1 du §39 est vérifiée ici, sur la requête**, et pas
        seulement par l'affichage du bouton. `opex_check_can_apply()` est la
        même fonction que celle qu'interroge le `t-if` : un bouton visible là
        où la route refuse, ou l'inverse, seraient deux bugs symétriques — le
        second est déjà arrivé sur le Module 1.

        En GET, la page explique ce qui manque et propose le mini-profil. En
        POST, elle crée la candidature.
        """
        mission = self._intervenants_public_mission(mission_id)
        if not mission:
            return request.redirect('/missions')

        partner = request.env.user.partner_id
        try:
            partner.opex_check_can_apply(mission)
        except UserError as refus:
            # Le motif décide de l'écran : sans profil, on propose de le créer ;
            # candidature existante, on y renvoie ; appel fermé, on le dit.
            existante = self._intervenants_existing_application(mission, partner)
            if existante:
                return request.redirect(
                    '/my/missions/candidature/%s' % existante.id)
            if not partner.opex_mission_profile():
                return request.render(
                    'opex_intervenants.public_mission_no_profile', {
                        'mission': mission.public_detail(),
                        'motif': str(refus),
                        'page_name': 'public_missions',
                    })
            return request.redirect(
                '/missions/%s?error=%s' % (mission.id, quote(str(refus))))

        if request.httprequest.method != 'POST':
            return request.redirect('/missions/%s' % mission.id)

        application = self._intervenants_create_application(mission, partner)
        if isinstance(application, str):
            return request.redirect(
                '/missions/%s?error=%s' % (mission.id, quote(application)))
        return request.redirect(
            '/my/missions/candidature/%s' % application.id)

    def _intervenants_existing_application(self, mission, partner):
        return request.env['opex.mission.application'].sudo().search([
            ('mission_id', '=', mission.id),
            ('partner_id', '=', partner.id),
        ], limit=1)

    def _intervenants_create_application(self, mission, partner):
        """Crée la candidature et l'amène là où le candidat doit écrire.

        Les trois premières étapes du §12.2 sont franchies dans la même
        requête, et c'est fidèle : `invited` est l'instant de création, le
        candidat **a** consulté la fiche pour arriver ici, et cliquer « Je suis
        intéressé » **est** la déclaration d'intérêt. `source = 'portail'` lève
        l'ambiguïté sur l'origine.

        Savepoint : la contrainte `unique(mission_id, partner_id)` ne se
        déclenche qu'au `flush` et **empoisonne la transaction** — le rendu de
        la page d'erreur recevrait « current transaction is aborted » et le
        candidat un 500. Leçon de l'Extension 3.
        """
        Application = request.env['opex.mission.application'].sudo()
        try:
            with request.env.cr.savepoint():
                application = Application.create({
                    'mission_id': mission.id,
                    'partner_id': partner.id,
                    'source': 'portail',
                })
                application.flush_recordset()
        except UserError as refus:
            request.env.invalidate_all()
            return str(refus)
        except Exception:  # noqa: BLE001 — contrainte SQL, message lisible
            request.env.invalidate_all()
            return _(
                "Vous avez déjà une candidature sur cet appel : un intervenant "
                "ne peut pas candidater deux fois au même appel.")

        for code in ('application_view', 'application_express_interest'):
            transition = application.workflow_definition_id.sudo()\
                .transition_ids.filtered(lambda t: t.code == code)
            application.with_user(request.env.user).sudo()\
                .workflow_do_transition(transition)
        return application

    #
    # §7 — Le candidat externe et son mini-profil
    #

    @http.route(['/missions/<int:mission_id>/mini-profil'], type='http',
                auth='user', website=True, methods=['GET', 'POST'])
    def portal_intervenants_mini_profile(self, mission_id, **post):
        """« Un candidat externe crée un mini-profil » — §7.

        Un **vrai** profil expert du Module 2, pas un objet parallèle. Il
        naît en brouillon, suit son propre workflow de qualification, et
        « s'il est qualifié, son profil peut intégrer le référentiel experts
        OPEX » — sans que rien n'ait à être recopié.

        Quatre champs, pas quinze : c'est un **mini**-profil. Le reste se
        complète depuis l'espace expertise une fois le profil ouvert.
        """
        mission = self._intervenants_public_mission(mission_id)
        if not mission:
            return request.redirect('/missions')

        partner = request.env.user.partner_id
        if partner.opex_mission_profile():
            return request.redirect('/missions/%s/interesse' % mission.id)

        error = None
        if request.httprequest.method == 'POST':
            domaine = (post.get('domaine_expertise') or '').strip()
            if not domaine:
                error = _("Indiquez votre domaine d'expertise.")
            else:
                values = {
                    name: (post.get(name) or '').strip()
                    for name in self._INTERVENANTS_MINI_PROFILE_FIELDS
                    if isinstance(post.get(name), str)
                }
                # `partner_id` volontairement absent : le `create()` du
                # Module 2 l'impose côté serveur pour un compte portail.
                request.env['opex.innovation.expert.profile'].create(values)
                return request.redirect(
                    '/missions/%s/interesse' % mission.id)

        return request.render('opex_intervenants.public_mini_profile', {
            'mission': mission.public_detail(),
            'error': error,
            'page_name': 'public_missions',
        })
