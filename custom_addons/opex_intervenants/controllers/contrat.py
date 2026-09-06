from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal


class MissionContractPortal(CustomerPortal):
    """§19 — le client et l'intervenant confirment le contrat au portail.

    CE QUE CET ÉCRAN EST, ET CE QU'IL N'EST PAS

    Une **confirmation horodatée**, pas une signature cryptographique : c'est
    l'arbitrage de l'Extension 7, et le hors-périmètre du module le dit
    depuis l'origine. Les champs du modèle le disaient déjà —
    `signature_client_nom` et `signature_client_date` sont ce que quelqu'un
    consigne, pas une empreinte.

    ⚠ **AUCUNE TRANSITION N'EST FRANCHIE ICI.**

    `contract_sign` — « Signatures recueillies » — reste ouverte au
    responsable et au secrétariat, et cet écran ne la propose pas. Les deux
    confirmations rendent seulement sa condition vraie : `contract_signed`
    lit `contract_fully_signed`, qui lit les deux champs. C'est la structure
    que le modèle portait déjà, et il n'y avait pas à rouvrir les rôles de la
    transition pour brancher le portail dessus.

    La seule transition offerte ici est **« Signature refusée »** — la seule
    du sous-workflow que le moteur ouvre au `client` et à l'`intervenant`, et
    qui n'avait aucun écran. Sans elle, une partie en désaccord n'avait
    aucune façon de le dire.

    POURQUOI UNE ROUTE DÉDIÉE PLUTÔT QUE DEUX POINTS D'ACCROCHE

    Le diagnostic laissait le choix : accrocher la signature à
    `/my/missions/<id>` pour le client et à `/my/missions/candidature/<id>`
    pour l'intervenant. Une fois le rebond muet corrigé, les deux parties
    atteignent une page qui les concerne — mais ce sont **deux** pages, et le
    contrat est **un** objet. Deux accroches auraient dupliqué la logique de
    confirmation, et c'est toujours la seconde copie qui dérive.

    Routes → `/my/missions/contrats` et `/my/missions/contrat/<id>`.
    """

    #: Les deux gestes, et le seul code de transition offert. Table fermée,
    #: la même pour les boutons et pour le POST.
    _INTERVENANTS_CONTRACT_CONFIRM = ('confirmer',)
    _INTERVENANTS_CONTRACT_TRANSITIONS = ('contract_sign_refused',)

    # ------------------------------------------------------------
    # Le périmètre
    # ------------------------------------------------------------

    def _intervenants_contract_own(self):
        """Les pièces en vigueur des missions où ce contact est partie.

        Les **deux** côtés, dans un seul domaine : `client_id` pour le client,
        `partner_id` pour l'intervenant. C'est ce qui permet à une route
        unique de servir les deux, et l'écran distingue ensuite qui confirme
        quoi — `_intervenants_contract_side()`.

        Bornée à `current_version` : une révision crée une pièce neuve, et
        proposer de confirmer une version périmée serait recueillir un accord
        sur un texte qui n'est plus celui du dossier (§19).
        """
        partner = request.env.user.partner_id
        return request.env['opex.mission.contract'].sudo().search([
            ('current_version', '=', True),
            ('active', '=', True),
            '|', ('client_id', '=', partner.id),
                 ('partner_id', '=', partner.id),
        ], order='mission_id, contract_type')

    def _intervenants_contract_one(self, contract_id):
        return self._intervenants_contract_own().filtered(
            lambda k: k.id == contract_id)[:1]

    def _intervenants_contract_side(self, contract):
        """De quel côté du contrat se trouve la session : 'client', 'intervenant'.

        Un seul endroit répond à cette question, et le modèle la repose pour
        son propre compte dans `_check_signer()`. Ce n'est pas une seconde
        vérité : celle-ci décide de ce que la page affiche, celle-là garde
        l'écriture. L'écran sans le modèle serait contournable ; le modèle
        sans l'écran proposerait à chacun le bouton de l'autre.
        """
        partner = request.env.user.partner_id
        if contract.sudo().client_id == partner:
            return 'client'
        if contract.sudo().partner_id == partner:
            return 'intervenant'
        return False

    def _intervenants_contract_actions(self, contract):
        """« Signature refusée », si le moteur l'ouvre à cet utilisateur."""
        instance = contract.sudo().mission_id._contract_instance()
        if not instance:
            return []
        options = instance.transition_options(user=request.env.user)
        return [
            option for option in options
            if option['transition'].code
            in self._INTERVENANTS_CONTRACT_TRANSITIONS
        ]

    # ------------------------------------------------------------
    # Les deux écrans
    # ------------------------------------------------------------

    @http.route(['/my/missions/contrats'], type='http', auth='user',
                website=True)
    def portal_intervenants_contrats(self, **kw):
        contrats = self._intervenants_contract_own()
        return request.render('opex_intervenants.portal_my_contracts', {
            'contrats': [
                dict(k.portal_signature_state(),
                     mission=k.sudo().mission_id.title,
                     cote=self._intervenants_contract_side(k))
                for k in contrats
            ],
            'page_name': 'intervenants_contrat',
        })

    @http.route(['/my/missions/contrat/<int:contract_id>'], type='http',
                auth='user', website=True, methods=['GET', 'POST'])
    def portal_intervenants_contrat(self, contract_id, **post):
        contract = self._intervenants_contract_one(contract_id)
        cote = self._intervenants_contract_side(contract) if contract else False
        if not contract or not cote:
            return request.render(
                'opex_intervenants.mission_access_refused', {
                    'refus': _(
                        "Cette pièce contractuelle n'existe pas, ou vous "
                        "n'êtes pas partie au contrat qu'elle porte."),
                    'page_name': 'intervenants_contrat',
                })

        error = None
        if request.httprequest.method == 'POST':
            error = self._intervenants_contract_post(contract, cote, post)
            if error is None:
                return request.redirect(
                    '/my/missions/contrat/%s' % contract.id)

        return request.render('opex_intervenants.portal_contract_form', {
            'contrat': contract.portal_signature_state(),
            'mission_titre': contract.sudo().mission_id.title,
            'etape_contrat': contract.sudo().mission_id.contract_stage_label,
            'cote': cote,
            'actions': self._intervenants_contract_actions(contract),
            'error': error,
            'page_name': 'intervenants_contrat',
        })

    def _intervenants_contract_post(self, contract, cote, post):
        """Confirmer, ou refuser de signer. `None` = succès."""
        code = (post.get('action') or '').strip()

        if code in self._INTERVENANTS_CONTRACT_CONFIRM:
            try:
                contract.action_portal_confirm(cote)
            except UserError as refus:
                return str(refus)
            return None

        if code in self._INTERVENANTS_CONTRACT_TRANSITIONS:
            instance = contract.sudo().mission_id._contract_instance()
            transition = instance.available_transitions(
                user=request.env.user).filtered(lambda t: t.code == code)[:1]
            if not transition:
                return _("Cette action n'est pas disponible : soit le contrat "
                         "a changé d'étape, soit votre rôle ne l'autorise pas.")
            try:
                instance.with_user(request.env.user).sudo().do_transition(
                    transition, comment=(post.get('comment') or '').strip())
            except UserError as refus:
                return str(refus)
            return None

        return _("Action inconnue sur une pièce contractuelle.")
