from urllib.parse import quote

from odoo import http
from odoo.exceptions import UserError
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

        ⚠ **La vérification serveur est faite ici, avant toute création.**

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
        return request.render('opex_innovation.portal_profile_detail', {
            'profile': profile,
            'profile_type': profile_type,
            # La progression et la prochaine action sont rendues par le
            # gabarit générique du moteur : le métier n'écrit pas sa propre
            # version de « où en est mon dossier ».
            'instance': profile.workflow_instance_id,
            'page_name': 'innovation_profiles',
        })
