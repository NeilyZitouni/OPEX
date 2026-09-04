import base64
from urllib.parse import quote

from odoo import _, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal


class InnovationProfilePortal(CustomerPortal):
    """Espace membre : demander un profil Expert ou Investisseur."""

    #: Champs que le formulaire de demande peut renseigner. Liste fermée : tout
    #: ajout ici donne au membre le droit d'écrire ce champ. Les champs qui
    #: décident (partner_id, l'avancement) n'y sont pas et ne peuvent donc pas
    #: venir du navigateur.
    _EXPERT_FIELDS = (
        'domaine_expertise', 'specialites', 'fonction', 'experiences_pro',
        'projets_realises', 'experiences_conseil', 'experience_mentoring',
        'description_expertise',
    )
    _INVESTOR_FIELDS = (
        'type_investisseur', 'domaines_investissement',
        'types_projets_recherches', 'stade_maturite_recherche',
        'zone_geographique', 'experience_investissement', 'preferences',
        'presentation',
    )

    _PROFILE_MODELS = {
        'expert': 'opex.innovation.expert.profile',
        'investor': 'opex.innovation.investor.profile',
    }

    def _partner(self):
        return request.env.user.partner_id

    def _own_profile(self, profile_type):
        """Demande du membre connecté, résolue **côté serveur**.

        Aucun identifiant ne vient de l'URL : la demande est retrouvée depuis
        `partner_id`. Il n'y a donc rien à forger. C'est le pattern du parcours
        d'adhésion du Module 1, repris tel quel.
        """
        model = self._PROFILE_MODELS[profile_type]
        return request.env[model].sudo().search(
            [('partner_id', '=', self._partner().id)], order='id desc', limit=1)

    # ------------------------------------------------------------
    # Espace personnel
    # ------------------------------------------------------------

    @http.route(['/my/innovation/profiles'], type='http', auth='user',
                website=True)
    def portal_profiles(self, **kw):
        partner = self._partner()
        return request.render('opex_innovation.portal_my_profiles', {
            'partner': partner,
            'expert_profile': self._own_profile('expert'),
            'investor_profile': self._own_profile('investor'),
            'can_request_expert': partner.opex_can_request_expert(),
            'can_request_investor': partner.opex_can_request_investor(),
            'error': kw.get('error'),
            'page_name': 'innovation_profiles',
        })

    # ------------------------------------------------------------
    # Création — « Devenir Expert » / « Devenir Investisseur »
    # ------------------------------------------------------------

    @http.route(['/my/innovation/profiles/new/<string:profile_type>'],
                type='http', auth='user', website=True,
                methods=['GET', 'POST'])
    def portal_profile_new(self, profile_type, **post):
        """Dépose une demande de profil.

        **La vérification serveur est faite ici, avant toute création.**

        Le `t-if` du gabarit masque le bouton ; il n'empêche rien. Une requête
        forgée sur cette route n'a jamais vu le gabarit. Le bug symétrique est
        déjà arrivé sur le Module 1 — « Devenir membre » resté visible pour un
        membre actif — et ce qui manquait n'était pas le `t-if`.
        """
        if profile_type not in self._PROFILE_MODELS:
            return request.redirect('/my/innovation/profiles')

        partner = self._partner()
        try:
            partner.opex_check_can_request(profile_type)
        except UserError as error:
            # Le motif du refus est rendu au membre : « vous avez déjà ce
            # profil » et « votre adhésion n'est pas validée » appellent des
            # gestes différents, une page d'erreur muette n'aiderait personne.
            return request.redirect(
                '/my/innovation/profiles?error=%s' % quote(str(error)))

        model = self._PROFILE_MODELS[profile_type]
        allowed = (self._EXPERT_FIELDS if profile_type == 'expert'
                   else self._INVESTOR_FIELDS)

        if request.httprequest.method == 'POST':
            values = {
                name: (post.get(name) or '').strip()
                for name in allowed
                if isinstance(post.get(name), str)
            }
            # `partner_id` volontairement absent : le `create()` du modèle
            # l'impose côté serveur pour un utilisateur portail.
            profile = request.env[model].create(values)
            return request.redirect('/my/innovation/profiles')

        return request.render('opex_innovation.portal_profile_form', {
            'profile_type': profile_type,
            'page_name': 'innovation_profiles',
        })

    # ------------------------------------------------------------
    # Suivi de la demande
    # ------------------------------------------------------------

    @http.route(['/my/innovation/profiles/<string:profile_type>'],
                type='http', auth='user', website=True)
    def portal_profile_detail(self, profile_type, **kw):
        if profile_type not in self._PROFILE_MODELS:
            return request.redirect('/my/innovation/profiles')
        profile = self._own_profile(profile_type)
        if not profile:
            return request.redirect('/my/innovation/profiles')
        return request.render(
            'opex_innovation.portal_profile_detail',
            self._innovation_profile_values(profile, profile_type,
                                            error=kw.get('error')))

    def _innovation_profile_values(self, profile, profile_type, error=None):
        """Ce que l'écran de suivi doit savoir pour être utilisable.

        Les transitions sont demandées **au moteur**, sous l'identité du
        visiteur, et rendues **toutes** — y compris celles qu'une condition
        bloque. `transition_options()` porte pour chacune sa disponibilité et,
        si elle est bloquée, la raison rédigée par la règle. Une transition
        qu'on retirerait de la liste laisserait le porteur devant un écran
        muet, sans savoir ce qu'on attend de lui : c'est la note
        d'`available_transitions()` dans le moteur, et c'est aussi ce que
        demande la section 16 du document source.
        """
        instance = profile.workflow_instance_id
        return {
            'profile': profile,
            'profile_type': profile_type,
            # La progression et la prochaine action sont rendues par le
            # gabarit générique du moteur : le métier n'écrit pas sa propre
            # version de « où en est mon dossier ».
            'instance': instance,
            'transition_options': instance.transition_options(
                user=request.env.user) if instance else [],
            # Le référentiel des types vient du modèle, il n'est pas recopié :
            # un type ajouté au modèle apparaît ici sans toucher au controller
            # ni au gabarit.
            'document_types': request.env[
                'opex.innovation.profile.document'
            ]._fields['document_type'].selection,
            # Le dépôt de pièces n'a de sens que tant que le membre est
            # attendu. Le critère est l'étape courante — la même que celle des
            # `ir.rule` d'écriture —, jamais un champ d'état du métier.
            'can_upload': bool(
                instance and instance.current_stage_id.code in (
                    'draft', 'complement_requested')),
            'error': error,
            'page_name': 'innovation_profiles',
        }

    def _innovation_profile_redirect(self, profile_type, error=None):
        """Retour à l'écran de suivi, avec son motif d'échec s'il y en a un.

        POST puis redirection puis GET : un rechargement de page ne rejoue pas
        la transition ni le dépôt.
        """
        url = '/my/innovation/profiles/%s' % profile_type
        if error:
            url += '?error=%s' % quote(str(error))
        return request.redirect(url)

    # ------------------------------------------------------------
    # Dépôt des justificatifs
    # ------------------------------------------------------------

    @http.route(['/my/innovation/profiles/<string:profile_type>/document'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_innovation_profile_document(self, profile_type, **post):
        """Joint une pièce à sa propre demande.

        Nom de méthode préfixé du module, conformément à la règle
        transversale 1 bis : `_generate_routing_rules()` fusionne toutes les
        classes filles de `CustomerPortal` en une seule, et deux modules qui
        définiraient `portal_profile_document` n'en garderaient qu'un — sans
        erreur, ni au chargement ni au runtime.

        La pièce est créée **sous l'identité du membre**, pas en `sudo()` :
        c'est l'`ir.rule` du justificatif qui garantit qu'il ne l'accroche
        qu'à un profil qui est le sien. Un `sudo()` ici supprimerait ce
        contrôle au lieu de le satisfaire.
        """
        if profile_type not in self._PROFILE_MODELS:
            return request.redirect('/my/innovation/profiles')
        profile = self._own_profile(profile_type)
        if not profile:
            return request.redirect('/my/innovation/profiles')

        upload = request.httprequest.files.get('file')
        content = upload.read() if upload else b''
        if not content:
            return self._innovation_profile_redirect(
                profile_type,
                _("Choisissez un fichier avant de valider : le dépôt était "
                  "vide."))

        document_type = post.get('document_type') or 'autre'
        Document = request.env['opex.innovation.profile.document']
        if document_type not in dict(
                Document._fields['document_type'].selection):
            return self._innovation_profile_redirect(
                profile_type, _("Type de justificatif inconnu."))

        link_field = ('expert_profile_id' if profile_type == 'expert'
                      else 'investor_profile_id')
        try:
            Document.create({
                # Le libellé saisi prime, le nom du fichier sert de repli :
                # une pièce sans libellé n'est identifiable nulle part.
                'name': (post.get('name') or '').strip() or upload.filename,
                'document_type': document_type,
                'file': base64.b64encode(content),
                'filename': upload.filename,
                link_field: profile.id,
            })
        except (AccessError, UserError) as refus:
            return self._innovation_profile_redirect(profile_type, refus)
        return self._innovation_profile_redirect(profile_type)

    # ------------------------------------------------------------
    # Franchissement d'une transition
    # ------------------------------------------------------------

    @http.route(['/my/innovation/profiles/<string:profile_type>/transition'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_innovation_profile_transition(self, profile_type, **post):
        """Franchit une transition, **sans juger si elle est permise**.

        Aucun contrôle de droit ici, et c'est délibéré (règle transversale
        2). `workflow_do_transition()` mène à
        `opex.workflow.instance._check_transition_allowed()`, l'unique juge :
        appartenance de la transition au workflow, cohérence de l'étape de
        départ, état du dossier, rôles. Un identifiant forgé n'a donc rien à
        gagner — la transition d'un autre workflow, ou d'une étape où le
        dossier n'est pas, est refusée par le moteur. Refaire ici une
        vérification « par prudence » créerait un second contrôle d'accès,
        qui finirait par diverger du premier.

        L'appel se fait sous l'identité du membre (`with_user`) et non en
        `sudo()` : c'est `self.env.user` que le moteur interroge pour établir
        les rôles. `do_transition()` passe lui-même ses écritures en `sudo()`,
        le membre n'a donc besoin d'aucun droit d'écriture sur l'instance.
        """
        if profile_type not in self._PROFILE_MODELS:
            return request.redirect('/my/innovation/profiles')
        profile = self._own_profile(profile_type)
        if not profile:
            return request.redirect('/my/innovation/profiles')

        raw = (post.get('transition_id') or '').strip()
        if not raw.isdigit():
            return self._innovation_profile_redirect(
                profile_type, _("Aucune action sélectionnée."))

        transition = request.env['opex.workflow.transition'].sudo().browse(
            int(raw)).exists()
        if not transition:
            return self._innovation_profile_redirect(
                profile_type, _("Cette action n'existe plus."))

        try:
            profile.with_user(request.env.user).workflow_do_transition(
                transition, comment=post.get('comment'))
            # Le motif est soldé : il a été traité, il n'a plus à s'afficher en
            # évidence. Sans cela l'encart « Complément demandé » suit le
            # dossier jusqu'à sa clôture et donne à lire, sur une demande
            # validée, une exigence à laquelle le membre a déjà répondu.
            if transition.code == 'resubmit':
                profile.sudo().motif_complement = False
        except (AccessError, UserError) as refus:
            # Le motif est rendu au membre. Une action refusée sans explication
            # le laisse devant un écran qui n'a pas bougé, sans rien à faire.
            return self._innovation_profile_redirect(profile_type, refus)
        return self._innovation_profile_redirect(profile_type)
