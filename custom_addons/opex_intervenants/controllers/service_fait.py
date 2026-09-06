from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal


class MissionServicePortal(CustomerPortal):
    """§27 et §28 — le client prononce le service fait depuis le portail.

    LA LIMITE DÉCLARÉE À L'EXTENSION 9, REFERMÉE

    « La validation du client se fait depuis le back-office. […] **C'est le
    canal qui manque, pas la fonction.** » — propriétaire annoncé :
    Extension 11, qui a livré sans le poser.

    `service_dispute` est le point qui compte : elle n'est ouverte **à
    personne d'autre** que le client. Sans écran, un client qui n'est pas
    d'accord n'avait aucun moyen de le dire, et le responsable validait à sa
    place par `service_validate_client` — les deux passages du §28 se
    réduisaient à un seul.

    ⚠ CE CONTROLLER N'ÉCRIT RIEN LUI-MÊME.

    Le portail est en lecture seule sur `opex.service.acceptance` : franchir
    la transition demande un `sudo()`, et un `sudo()` posé ici remplacerait
    l'`ir.rule` par la confiance qu'on accorde à ce fichier. Les deux gestes
    passent donc par `action_portal_validate()` et `action_portal_dispute()`,
    qui portent le contrôle d'appelant **dans le modèle** — précédent
    `_check_manager()` de `competence_arbitrage.py`.

    Routes → `/my/missions/services` et `/my/missions/service/<id>`.
    Noms    → `portal_intervenants_service_*` / `_intervenants_service_*`.
    """

    #: Les deux gestes du client, et la méthode de modèle de chacun. Table
    #: plutôt que deux `if` : une action inconnue ne fait rien plutôt que de
    #: tomber dans un `else` silencieux, et c'est la **même** table qui
    #: filtre les boutons et garde le POST.
    _INTERVENANTS_SERVICE_ACTIONS = {
        'service_validate_client': 'action_portal_validate',
        'service_dispute': 'action_portal_dispute',
    }

    # ------------------------------------------------------------
    # Le périmètre
    # ------------------------------------------------------------

    def _intervenants_service_own(self):
        """Les constats des missions de ce client.

        Borné par `mission_id.client_id`, la même question que pose
        `_check_client()` sur le modèle. Ce n'est pas une seconde vérité : le
        modèle garde l'écriture, ce domaine décide de la page. L'un sans
        l'autre laisserait soit un écran vide, soit une garde contournable.
        """
        return request.env['opex.service.acceptance'].sudo().search(
            [('mission_id.client_id', '=', request.env.user.partner_id.id)],
            order='create_date desc')

    def _intervenants_service_one(self, acceptance_id):
        return self._intervenants_service_own().filtered(
            lambda a: a.id == acceptance_id)[:1]

    def _intervenants_service_actions(self, acceptance):
        options = acceptance.workflow_instance_id.sudo().transition_options(
            user=request.env.user)
        return [
            option for option in options
            if option['transition'].code in self._INTERVENANTS_SERVICE_ACTIONS
        ]

    # ------------------------------------------------------------
    # Les deux écrans
    # ------------------------------------------------------------

    @http.route(['/my/missions/services'], type='http', auth='user',
                website=True)
    def portal_intervenants_services(self, **kw):
        return request.render('opex_intervenants.portal_my_services', {
            'services': self._intervenants_service_own(),
            'page_name': 'intervenants_service',
        })

    @http.route(['/my/missions/service/<int:acceptance_id>'], type='http',
                auth='user', website=True, methods=['GET', 'POST'])
    def portal_intervenants_service(self, acceptance_id, **post):
        """Lire le constat, puis valider ou contester.

        Le client voit **ce que le cluster a coché** — les quatre points du
        §28 — parce que c'est ce sur quoi il se prononce. Il ne peut pas les
        modifier : l'`ir.rule` et les droits l'interdisent déjà, et l'écran
        ne propose pas de champ.
        """
        acceptance = self._intervenants_service_one(acceptance_id)
        if not acceptance:
            return request.render(
                'opex_intervenants.mission_access_refused', {
                    'refus': _(
                        "Ce constat de service fait n'existe pas, ou il ne "
                        "relève pas d'une mission dont vous êtes le client."),
                    'page_name': 'intervenants_service',
                })

        error = None
        if request.httprequest.method == 'POST':
            error = self._intervenants_service_post(acceptance, post)
            if error is None:
                return request.redirect(
                    '/my/missions/service/%s' % acceptance.id)

        return request.render('opex_intervenants.portal_service_form', {
            'service': acceptance,
            'actions': self._intervenants_service_actions(acceptance),
            'validations': acceptance.validation_entries(),
            'error': error,
            'page_name': 'intervenants_service',
        })

    def _intervenants_service_post(self, acceptance, post):
        """Appelle la méthode de modèle. `None` = succès.

        Quatre contrôles se succèdent avant qu'une étape bouge, et aucun ne
        suppose le précédent : le périmètre (constat résolu **dans** la file),
        le code confronté à la table fermée, puis — dans le modèle —
        `_check_client()` et la recherche de la transition parmi celles que le
        moteur ouvre à cet utilisateur. `do_transition()` rejuge ensuite pour
        son propre compte.
        """
        code = (post.get('action') or '').strip()
        methode = self._INTERVENANTS_SERVICE_ACTIONS.get(code)
        if not methode:
            return _("Action inconnue sur un constat de service fait.")

        comment = (post.get('comment') or '').strip()
        try:
            if code == 'service_dispute':
                acceptance.action_portal_dispute(comment=comment)
            else:
                acceptance.action_portal_validate()
        except UserError as refus:
            return str(refus)
        return None
