import base64

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal

from .uploads import read_upload


class MissionApplicationPortal(CustomerPortal):
    """§9 et §13 — la candidature Lean.

    CE FORMULAIRE NE REDEMANDE RIEN DE PERMANENT

    « Pour un expert référencé, la candidature ne redemande **jamais** les
    informations permanentes déjà connues (identité, CV, compétences,
    certifications, historique). Seules les données propres à la mission sont
    demandées. » (§9)

    Six champs, et pas un de plus : disponibilité, délai de mobilisation,
    proposition financière, approche, pièces propres à la mission, acceptation
    des conditions. C'est le troisième critère d'acceptation du §21.

    Le §13 du document UX liste par ailleurs « CV, portfolio, références,
    certifications » parmi les pièces. Elles ne sont **pas** redemandées ici :
    elles vivent sur le profil, et l'écran les affiche en lecture — « voici ce
    que nous savons déjà de vous ». Les redemander serait précisément la
    ressaisie que le §9 interdit.

    Noms préfixés `portal_intervenants_*` / `_intervenants_*` : cette classe est
    une feuille de plus dans l'arbre `CustomerPortal`, aux côtés de
    `MissionRequestPortal` et `ExpertCapitalPortal`.
    """

    #: Les seuls champs que le portail écrit sur une candidature. **Liste
    #: fermée** : `score`, `score_detail`, `source`, `partner_id` n'y sont pas
    #: et ne peuvent donc pas venir du navigateur.
    _INTERVENANTS_LEAN_FIELDS = (
        'disponibilite_commentaire', 'motivation', 'methodologie')

    #: Les pièces **propres à la mission**. CV, portfolio, références et
    #: certifications sont volontairement absents : ils sont sur le profil.
    _INTERVENANTS_APPLICATION_DOCUMENTS = (
        ('proposition_technique', "Proposition technique"),
        ('proposition_financiere', "Proposition financière"),
        ('autre', "Autre pièce"),
    )

    # Les contrôles de dépôt vivent dans `uploads.py`, en constantes de
    # **module** : déclarés sur cette classe, ils entraient en collision avec
    # ceux de `MissionRequestPortal`, feuille du même arbre `CustomerPortal`.
    # Voir l'en-tête de `uploads.py`.

    #
    # Résolution — toujours côté serveur
    #

    def _intervenants_own_applications(self):
        """Les candidatures du contact connecté.

        Aucun identifiant reçu du navigateur n'est utilisé directement : il est
        cherché **dans** cet ensemble.
        """
        return request.env['opex.mission.application'].sudo().search(
            [('partner_id', '=', request.env.user.partner_id.id)],
            order='create_date desc')

    def _intervenants_own_application(self, application_id):
        return self._intervenants_own_applications().filtered(
            lambda a: a.id == application_id)[:1]

    def _intervenants_application_editable(self, application):
        """`interested` est la seule étape où le candidat écrit.

        La même question que l'`ir.rule` de l'Extension 1, posée une fois. Une
        fois la candidature déposée, il ne la réécrit plus sous le responsable :
        la version examinée doit être celle qui a été lue.
        """
        return bool(application) \
            and application.workflow_stage_id.sudo().code == 'interested'

    #: Ce que l'étape atteinte veut dire pour le candidat. Les étapes absentes
    #: de cette table sont celles où le dossier suit son cours.
    _INTERVENANTS_APPLICATION_OUTCOME = {
        'selected': 'retenue',
        'rejected': 'ecartee',
        'withdrawn': 'retiree',
        'declined': 'declinee',
    }

    def _intervenants_application_outcome(self, application):
        """« en_cours », ou l'issue atteinte. Jamais un code d'étape brut."""
        code = application.workflow_stage_id.sudo().code
        return self._INTERVENANTS_APPLICATION_OUTCOME.get(code, 'en_cours')

    def _intervenants_application_values(self, application, **extra):
        """Ce que l'écran doit savoir — **et ce qu'il montre sans le demander**.

        `profil` alimente le bloc « ce que nous savons déjà » : compétences,
        expériences, certifications, disponibilités du profil. Le candidat les
        **lit**, il ne les ressaisit pas.
        """
        mission = application.mission_id.sudo()
        profile = application.partner_id.sudo().opex_mission_profile()
        values = self._prepare_portal_layout_values()
        values.update({
            'application': application,
            # La mission passe par sa **vue publique**, pas en recordset :
            # un candidat n'a pas plus de droits sur l'appel ici qu'au
            # catalogue.
            'mission': mission.public_detail(),
            'profil': profile,
            'capital': profile.capital_summary() if profile else {},
            'types_pieces': self._INTERVENANTS_APPLICATION_DOCUMENTS,
            # Le dénouement, pour que le titre de la page dise ce qui s'est
            # réellement passé.
            #
            # Le gabarit affichait « Votre candidature est déposée » sur
            # **toutes** les étapes non modifiables — donc aussi à un candidat
            # écarté, qui lisait « votre candidature est déposée … vous ne
            # pouvez plus la modifier : la version examinée par le cluster
            # doit être celle qu'il a lue » alors que le cluster avait déjà
            # tranché. Mesuré en session sur une candidature rejetée.
            #
            # Le code d'étape est lu ici, sous `sudo()` : c'est de la
            # configuration moteur, à laquelle un compte portail n'a pas accès
            # et n'a pas à en avoir. Ce qui le concerne, c'est le résultat.
            'denouement': self._intervenants_application_outcome(application),
            # `modifiable`, et surtout **pas** `editable`.
            #
            # `editable` est une variable **réservée du rendu website** :
            # `website/models/ir_http.py:399` la pose dans le contexte —
            # `has_group('website.group_website_designer')` — pour dire si
            # l'éditeur de site est actif. Elle vaut donc `False` pour tout
            # compte portail et **écrase** celle du controller.
            #
            # Symptôme : le formulaire de candidature ne s'affichait jamais,
            # la page rendait « votre candidature est déposée » alors que
            # l'étape était bien `interested`. Aucune erreur, aucun
            # avertissement — la valeur était simplement remplacée.
            'modifiable': self._intervenants_application_editable(application),
            'page_name': 'intervenants_candidature',
        })
        values.update(extra)
        return values

    #
    # Mes candidatures
    #

    @http.route(['/my/missions/candidatures'], type='http', auth='user',
                website=True)
    def portal_intervenants_candidatures(self, **kw):
        """§14 — « L'intervenant peut consulter uniquement l'état de sa propre
        candidature. »"""
        return request.render('opex_intervenants.portal_my_candidatures', {
            'applications': self._intervenants_own_applications(),
            'page_name': 'intervenants_candidature',
        })

    #
    # §9 — Le formulaire Lean
    #

    @http.route(['/my/missions/candidature/<int:application_id>'], type='http',
                auth='user', website=True, methods=['GET', 'POST'])
    def portal_intervenants_candidature(self, application_id, **post):
        """Saisir, puis envoyer.

        L'envoi passe par `workflow_do_transition()`, donc par l'unique
        contrôle d'accès du moteur et par la condition configurée à
        l'Extension 1 — disponibilité, délai, tarif, motivation, consentement.
        Ce controller ne décide pas que la candidature peut partir : il le
        demande, et rend le refus lisible.
        """
        application = self._intervenants_own_application(application_id)
        if not application:
            return request.redirect('/my/missions/candidatures')

        error = None
        if request.httprequest.method == 'POST':
            if not self._intervenants_application_editable(application):
                return request.redirect(
                    '/my/missions/candidature/%s' % application.id)

            action = post.get('action')
            if action == 'add_document':
                error = self._intervenants_add_application_document(
                    application, post)
                if not error:
                    return request.redirect(
                        '/my/missions/candidature/%s' % application.id)
            elif action == 'remove_document':
                raw = (post.get('document_id') or '')
                application.document_ids.filtered(
                    lambda d: str(d.id) == raw).sudo().unlink()
                return request.redirect(
                    '/my/missions/candidature/%s' % application.id)
            else:
                self._intervenants_save_lean(application, post)
                if action == 'submit':
                    error = self._intervenants_submit(application)
                    if not error:
                        return request.redirect(
                            '/my/missions/candidature/%s' % application.id)
                else:
                    return request.redirect(
                        '/my/missions/candidature/%s' % application.id)

        return request.render(
            'opex_intervenants.portal_candidature',
            self._intervenants_application_values(application, error=error))

    def _intervenants_save_lean(self, application, post):
        """Les six données propres à la mission, et elles seules."""
        values = {
            name: (post.get(name) or '').strip()
            for name in self._INTERVENANTS_LEAN_FIELDS
            if isinstance(post.get(name), str)
        }
        values['disponibilite'] = post.get('disponibilite') or False
        values['type_tarif'] = post.get('type_tarif') or False
        values['consentement'] = bool(post.get('consentement'))

        for champ, cle in (('delai_propose_jours', 'delai_propose_jours'),):
            raw = (post.get(cle) or '').strip()
            values[champ] = int(raw) if raw.isdigit() else 0

        raw = (post.get('tarif_propose') or '')
        cleaned = raw.replace(' ', '').replace(' ', '').replace(',', '.')
        try:
            values['tarif_propose'] = float(cleaned) if cleaned.strip() else 0.0
        except ValueError:
            values['tarif_propose'] = 0.0

        application.sudo().write(values)

    def _intervenants_submit(self, application):
        """Franchit `application_apply`, ou rend le motif du refus."""
        transition = application.workflow_instance_id.sudo()\
            .available_transitions(user=request.env.user)\
            .filtered(lambda t: t.code == 'application_apply')[:1]
        if not transition:
            return _("L'envoi n'est pas ouvert sur cette candidature.")
        try:
            application.workflow_do_transition(transition)
        except UserError as blocked:
            return str(blocked)
        return None

    def _intervenants_add_application_document(self, application, post):
        """Une pièce **propre à la mission**.

        Le type est cherché dans la liste fermée : le candidat ne dépose pas un
        « CV » ici, il est déjà sur son profil.
        """
        types = dict(self._INTERVENANTS_APPLICATION_DOCUMENTS)
        document_type = post.get('document_type') or 'autre'
        name = (post.get('name') or '').strip()
        upload = request.httprequest.files.get('file')

        if document_type not in types:
            return _("Type de pièce inconnu.")
        if not name:
            return _("Donnez un libellé à la pièce.")

        content, erreur = read_upload(upload)
        if erreur:
            return erreur

        request.env['opex.mission.application.document'].sudo().create({
            'application_id': application.id,
            'name': name,
            'document_type': document_type,
            'filename': upload.filename,
            'file': base64.b64encode(content),
        })
        return None

    #
    # Retirer sa candidature
    #

    @http.route(['/my/missions/candidature/<int:application_id>/retirer'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_intervenants_candidature_retirer(self, application_id, **post):
        """La transition est cherchée **dans** celles que le moteur propose.

        Le controller ne décide pas que la candidature peut être retirée : selon
        l'étape, `withdraw` existe ou non, et c'est la configuration qui le dit.
        """
        application = self._intervenants_own_application(application_id)
        if not application:
            return request.redirect('/my/missions/candidatures')
        transition = application.workflow_instance_id.sudo()\
            .available_transitions(user=request.env.user)\
            .filtered(lambda t: t.code.startswith('application_withdraw'))[:1]
        if transition:
            try:
                application.workflow_do_transition(transition)
            except UserError:
                pass
        return request.redirect(
            '/my/missions/candidature/%s' % application.id)

    #
    # Le contrat de `/my/counters`
    #

    def _prepare_home_portal_values(self, counters):
        """Troisième compteur du module, troisième clé **neuve**.

        `intervenants_mission_count` compte les demandes d'un client,
        `intervenants_expertise_count` le capital d'un expert, celui-ci ses
        candidatures. Trois tuiles, trois domaines : `querySelector()` ne
        renvoie que le premier nœud, deux tuiles partageant une clé
        laisseraient la seconde masquée.
        """
        values = super()._prepare_home_portal_values(counters)
        if 'intervenants_candidature_count' in counters:
            Application = request.env['opex.mission.application']
            values['intervenants_candidature_count'] = (
                Application.search_count(
                    [('partner_id', '=', request.env.user.partner_id.id)])
                if Application.has_access('read') else 0
            )
        return values
