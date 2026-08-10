from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import pager as portal_pager


class OpexStaff(http.Controller):
    """Espace de traitement web du Secrétariat, du COPIL et de l'Admin.

    Façade web du back-office, pas un remplacement : aucune règle de transition
    n'est réécrite ici. Le controller décide *qui* peut agir et *quand*, mais le
    passage d'état reste l'affaire du modèle (`action_validate_secretariat`,
    `action_validate_copil`).

    `auth='user'` garantit seulement qu'un utilisateur est connecté — un
    candidat portail l'est aussi. Le contrôle de groupe est donc refait
    explicitement à l'entrée de chaque route.

    Rien n'est fait en `sudo()` : le staff agit sous sa propre identité, donc
    les ACL du module s'appliquent et le suivi `mail.thread` attribue chaque
    validation à son auteur réel.
    """

    _files_per_page = 20

    # ------------------------------------------------------------
    # Rôles
    # ------------------------------------------------------------

    def _is_staff(self):
        user = request.env.user
        return (user.has_group('opex_membership.group_secretariat')
                or user.has_group('opex_membership.group_copil')
                or user.has_group('base.group_system'))

    def _staff_domain(self):
        """Dossiers listés selon le rôle : chacun ne voit que sa file d'attente.

        Un utilisateur cumulant Secrétariat et COPIL voit l'union des deux.
        """
        user = request.env.user
        if user.has_group('base.group_system'):
            return []
        states = []
        if user.has_group('opex_membership.group_secretariat'):
            states.append('control')
        if user.has_group('opex_membership.group_copil'):
            states += ['committee', 'validated']
        return [('state', 'in', states)]

    def _allowed_transition(self, membership_file):
        """Seule transition que cet utilisateur peut déclencher sur ce dossier.

        Le couple rôle × état du dossier détermine entièrement la méthode
        appelée : le formulaire n'envoie que l'identifiant du dossier, aucune
        donnée cliente ne peut donc détourner le workflow vers une autre
        transition. Renvoie `None` quand il n'y a rien à faire — un Secrétariat
        qui ouvre l'URL d'un dossier déjà en comité n'obtient aucun bouton.
        """
        user = request.env.user
        is_admin = user.has_group('base.group_system')
        if membership_file.state == 'control' and (
            is_admin or user.has_group('opex_membership.group_secretariat')
        ):
            return {
                'method': 'action_validate_secretariat',
                'label': "Valider le contrôle et transmettre au comité",
            }
        if membership_file.state == 'committee' and (
            is_admin or user.has_group('opex_membership.group_copil')
        ):
            return {
                'method': 'action_validate_copil',
                'label': "Valider en COPIL et émettre la cotisation",
            }
        return None

    def _payable_subscription(self, membership_file):
        """Cotisation encaissable depuis cette page, sinon recordset vide.

        Uniquement sur un dossier Validé COPIL dont une cotisation attend son
        règlement : ailleurs, il n'y a ni bouton ni action possible.
        """
        if membership_file.state != 'validated':
            return request.env['opex.subscription']
        return membership_file.subscription_ids.filtered(
            lambda subscription: subscription.state == 'waiting'
        )[:1]

    def _get_membership_file(self, file_id):
        """Dossier accessible en lecture à l'utilisateur courant, sinon `None`."""
        membership_file = request.env['opex.membership.file'].browse(file_id).exists()
        if not membership_file or not membership_file.has_access('read'):
            return None
        return membership_file

    # ------------------------------------------------------------
    # Liste des dossiers à traiter
    # ------------------------------------------------------------

    @http.route(
        ['/staff/membership', '/staff/membership/page/<int:page>'],
        type='http', auth='user', website=True, sitemap=False,
    )
    def staff_membership_files(self, page=1, **kw):
        if not self._is_staff():
            return request.redirect('/my')

        MembershipFile = request.env['opex.membership.file']
        domain = self._staff_domain()
        pager_values = portal_pager(
            url='/staff/membership',
            total=MembershipFile.search_count(domain),
            page=page,
            step=self._files_per_page,
        )
        membership_files = MembershipFile.search(
            domain, limit=self._files_per_page, offset=pager_values['offset'],
        )

        values = {
            'membership_files': membership_files,
            'pager': pager_values,
            'page_name': 'staff_membership',
        }
        return request.render('opex_membership.staff_membership_files', values)

    # ------------------------------------------------------------
    # Détail d'un dossier
    # ------------------------------------------------------------

    def _staff_file_values(self, membership_file, error=None):
        return {
            'membership_file': membership_file,
            'transition': self._allowed_transition(membership_file),
            'payable_subscription': self._payable_subscription(membership_file),
            'error': error,
            'page_name': 'staff_membership',
        }

    def _apply_staff_action(self, membership_file, action):
        """Déclenche une action du modèle et réaffiche la page si elle refuse.

        Le point de sauvegarde annule proprement ce que l'action a pu écrire
        avant de lever (le dossier incomplet, la cotisation déjà soldée), pour
        que la page de détail se réaffiche sur une transaction saine. Le message
        remonté est celui du modèle : aucune règle métier n'est réinterprétée
        ici.
        """
        try:
            with request.env.cr.savepoint():
                action()
        except UserError as error:
            return request.render(
                'opex_membership.staff_membership_file_page',
                self._staff_file_values(membership_file, error=error.args[0]),
            )
        return request.redirect('/staff/membership/%s' % membership_file.id)

    @http.route(
        ['/staff/membership/<int:file_id>'],
        type='http', auth='user', website=True, sitemap=False,
    )
    def staff_membership_file_page(self, file_id, **kw):
        if not self._is_staff():
            return request.redirect('/my')

        membership_file = self._get_membership_file(file_id)
        if not membership_file:
            return request.redirect('/staff/membership')

        return request.render(
            'opex_membership.staff_membership_file_page',
            self._staff_file_values(membership_file),
        )

    # ------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------

    @http.route(
        ['/staff/membership/<int:file_id>/validate'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def staff_membership_file_validate(self, file_id, **post):
        if not self._is_staff():
            return request.redirect('/my')

        membership_file = self._get_membership_file(file_id)
        if not membership_file:
            return request.redirect('/staff/membership')

        transition = self._allowed_transition(membership_file)
        if not transition:
            return request.redirect('/staff/membership/%s' % file_id)

        return self._apply_staff_action(
            membership_file, getattr(membership_file, transition['method'])
        )

    # ------------------------------------------------------------
    # Encaissement de la cotisation
    # ------------------------------------------------------------

    @http.route(
        ['/staff/membership/<int:file_id>/register_payment'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def staff_membership_file_register_payment(self, file_id, **post):
        """Enregistre le règlement de la cotisation d'un dossier Validé COPIL.

        Le montant n'est pas demandé au formulaire : `action_register_payment()`
        solde par défaut le reste dû, et c'est le modèle — pas ce controller —
        qui décide du passage à Payée et de l'activation de l'adhésion qui suit.
        """
        if not self._is_staff():
            return request.redirect('/my')

        membership_file = self._get_membership_file(file_id)
        if not membership_file:
            return request.redirect('/staff/membership')

        subscription = self._payable_subscription(membership_file)
        if not subscription:
            return request.redirect('/staff/membership/%s' % file_id)

        return self._apply_staff_action(
            membership_file, subscription.action_register_payment
        )
