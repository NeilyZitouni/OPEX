import base64
from urllib.parse import quote

from odoo import _, http
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.portal.controllers.portal import pager as portal_pager


class MembershipCustomerPortal(CustomerPortal):
    """Espace candidat : dépôt et suivi d'un dossier d'adhésion depuis le portail.

    Le candidat s'inscrit par le flux natif `/web/signup` et arrive dans
    `base.group_portal` ; il n'a donc jamais besoin qu'un membre du Secrétariat
    crée son dossier à sa place.
    """

    # Champs du profil candidat que le formulaire de dépôt peut renseigner sur
    # `res.partner`. Liste fermée : elle est appliquée en `sudo()`, tout ajout
    # ici donne au candidat le droit d'écrire ce champ sur son contact.
    _CANDIDATE_PARTNER_FIELDS = ('secteur_activite', 'wilaya')

    # Champs du dossier que le formulaire de dépôt renseigne directement.
    # Le parcours en sept écrans des sections A à E (Extension 10) remplacera
    # cette page unique ; d'ici là, elle couvre l'essentiel de la section A et
    # les identifiants dont le Secrétariat a besoin pour instruire.
    _CANDIDATE_FILE_FIELDS = (
        'nom_legal', 'nom_commercial', 'forme_juridique', 'nif', 'rc',
        'adresse', 'wilaya', 'commune', 'site_web', 'email_pro', 'telephone',
        'secteur_activite', 'activite_principale',
        'representant_nom', 'representant_prenom', 'representant_fonction',
        'representant_email', 'representant_telephone',
        'motivation',
    )

    # Pièces proposées à l'écran de dépôt, dans l'ordre de la section E : les
    # deux obligatoires d'abord, les complémentaires ensuite.
    _DOCUMENT_SLOTS = (
        ('registre_commerce', "Registre de commerce", True),
        ('statuts', "Statuts de l'organisation", True),
        ('presentation_entreprise', "Présentation de l'entreprise", False),
        ('certification', "Certifications", False),
        ('autre', "Autre document", False),
    )

    def _membership_file_domain(self):
        """Filtre applicatif ; la règle d'enregistrement le garantit côté base."""
        return [('partner_id', '=', request.env.user.partner_id.id)]

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'membership_file_count' in counters:
            MembershipFile = request.env['opex.membership.file']
            values['membership_file_count'] = (
                MembershipFile.search_count(self._membership_file_domain())
                if MembershipFile.has_access('read') else 0
            )
        if 'subscription_count' in counters:
            Subscription = request.env['opex.subscription']
            values['subscription_count'] = (
                Subscription.search_count(
                    [('partner_id', '=', request.env.user.partner_id.id)])
                if Subscription.has_access('read') else 0
            )
        return values

    # ------------------------------------------------------------
    # Liste des dossiers
    # ------------------------------------------------------------

    def _membership_searchbar_sortings(self):
        return {
            'date': {'label': _("Date de dépôt"), 'order': 'date_depot desc'},
            'state': {'label': _("État"), 'order': 'state'},
        }

    @http.route(
        ['/my/membership', '/my/membership/page/<int:page>'],
        type='http', auth='user', website=True,
    )
    def portal_my_membership_files(self, page=1, sortby=None, **kw):
        MembershipFile = request.env['opex.membership.file']
        if not MembershipFile.has_access('read'):
            return request.redirect('/my')

        searchbar_sortings = self._membership_searchbar_sortings()
        if sortby not in searchbar_sortings:
            sortby = 'date'

        domain = self._membership_file_domain()
        pager_values = portal_pager(
            url='/my/membership',
            total=MembershipFile.search_count(domain),
            page=page,
            step=self._items_per_page,
            url_args={'sortby': sortby},
        )
        membership_files = MembershipFile.search(
            domain,
            order=searchbar_sortings[sortby]['order'],
            limit=self._items_per_page,
            offset=pager_values['offset'],
        )

        values = self._prepare_portal_layout_values()
        values.update({
            # `sudo()` pour l'affichage seul : les dossiers ont déjà été
            # sélectionnés sous l'identité du candidat, donc filtrés par la
            # règle d'enregistrement.
            'membership_files': membership_files.sudo(),
            'page_name': 'membership',
            'pager': pager_values,
            'default_url': '/my/membership',
            'sortby': sortby,
            'searchbar_sortings': searchbar_sortings,
        })
        return request.render('opex_membership.portal_my_membership_files', values)

    # ------------------------------------------------------------
    # Cotisations du membre (historique, reçu, renouvellement)
    # ------------------------------------------------------------

    def _own_subscriptions(self):
        """Cotisations du membre connecté, résolues côté serveur.

        Aucun identifiant ne vient du client : la liste est construite depuis
        `partner_id`, comme la cloche de l'Extension 20. Un identifiant reçu en
        URL n'est jamais lu directement, il est recherché *dans* cet ensemble.
        """
        return request.env['opex.subscription'].sudo().search(
            [('partner_id', '=', request.env.user.partner_id.id)],
            order='date_echeance desc, id desc',
        )

    def _own_subscription(self, subscription_id):
        """Cotisation appartenant au membre connecté, sinon recordset vide."""
        return self._own_subscriptions().filtered(
            lambda s: s.id == subscription_id)[:1]

    def _renewable_membership_file(self):
        """Dossier actif du membre pouvant porter un renouvellement, sinon vide.

        Le renouvellement se rattache au dossier qui a fait de ce contact un
        membre : c'est lui qui porte la sous-catégorie, donc le barème.
        """
        return request.env['opex.membership.file'].sudo().search([
            ('partner_id', '=', request.env.user.partner_id.id),
            ('state', '=', 'active'),
        ], order='id desc', limit=1)

    @http.route(['/my/subscriptions'], type='http', auth='user', website=True)
    def portal_my_subscriptions(self, **kw):
        """Historique année par année des cotisations (section 29)."""
        subscriptions = self._own_subscriptions()

        # Regroupement par année, la plus récente en tête : c'est la lecture
        # qu'attend la spécification (2026 payée, 2027 à renouveler…).
        years = {}
        for subscription in subscriptions:
            years.setdefault(subscription._portal_year(), []).append(subscription)

        membership_file = self._renewable_membership_file()
        values = self._prepare_portal_layout_values()
        values.update({
            'subscription_years': sorted(
                years.items(), key=lambda item: item[0] or 0, reverse=True),
            'membership_file': membership_file,
            'can_renew': bool(membership_file) and not membership_file._pending_subscription(),
            'error': kw.get('error'),
            'page_name': 'subscriptions',
        })
        return request.render('opex_membership.portal_my_subscriptions', values)

    @http.route(
        ['/my/subscriptions/<int:subscription_id>/receipt'],
        type='http', auth='user', website=True, sitemap=False,
    )
    def portal_subscription_receipt(self, subscription_id, **kw):
        """Reçu d'une cotisation réglée (section 31).

        Page imprimable plutôt que PDF généré, comme la charte de l'Extension
        13 : le POC n'embarque pas wkhtmltopdf. Le navigateur suffit à en tirer
        un PDF, et brancher un vrai rapport ne toucherait que cette route.
        """
        subscription = self._own_subscription(subscription_id)
        if not subscription or subscription.state != 'paid':
            return request.redirect('/my/subscriptions')
        return request.render('opex_membership.portal_subscription_receipt', {
            'subscription': subscription,
            'page_name': 'subscriptions',
        })

    @http.route(
        ['/my/subscriptions/renew'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_subscription_renew(self, **post):
        """Renouvellement demandé par le membre lui-même.

        Le dossier concerné n'est pas reçu du formulaire : il est retrouvé
        depuis le contact connecté. Les règles (adhésion active, pas de
        cotisation déjà en attente) restent dans `action_renew()`.
        """
        membership_file = self._renewable_membership_file()
        if not membership_file:
            return request.redirect('/my/subscriptions')
        try:
            with request.env.cr.savepoint():
                membership_file.action_renew()
        except UserError as error:
            return request.redirect(
                '/my/subscriptions?error=%s' % quote(error.args[0]))
        return request.redirect('/my/subscriptions')

    # ------------------------------------------------------------
    # Dépôt d'un dossier
    # ------------------------------------------------------------

    @http.route(
        ['/my/membership/new'],
        type='http', auth='user', website=True, methods=['GET', 'POST'],
    )
    def portal_membership_file_new(self, **post):
        MembershipFile = request.env['opex.membership.file']
        if not MembershipFile.has_access('create'):
            return request.redirect('/my')

        values = self._prepare_portal_layout_values()
        values.update({
            'page_name': 'membership_new',
            'categories': request.env['opex.membership.category'].search(
                [('subcategory_ids', '!=', False)]
            ),
            'document_slots': self._DOCUMENT_SLOTS,
            'partner': request.env.user.partner_id,
            'form': {},
            'errors': {},
        })

        if request.httprequest.method == 'POST':
            values['form'] = {
                key: value for key, value in post.items()
                if isinstance(value, str) and key != 'csrf_token'
            }
            values['errors'] = self._validate_membership_form(post)
            if not values['errors']:
                # `partner_id` et `state` sont volontairement absents : le
                # `create()` du modèle les impose côté serveur.
                file_values = {'subcategory_id': int(post['subcategory_id'])}
                file_values.update({
                    field: post[field].strip()
                    for field in self._CANDIDATE_FILE_FIELDS
                    if isinstance(post.get(field), str) and post[field].strip()
                })
                membership_file = MembershipFile.create(file_values)
                self._update_candidate_profile(post)
                self._attach_membership_documents(membership_file)
                return request.redirect('/my/membership/%s' % membership_file.id)

        return request.render('opex_membership.portal_membership_file_new', values)

    def _validate_membership_form(self, post):
        errors = {}
        subcategory_id = post.get('subcategory_id')
        if not subcategory_id or not subcategory_id.isdigit():
            errors['subcategory_id'] = _("Veuillez choisir une sous-catégorie d'adhésion.")
        elif not request.env['opex.membership.subcategory'].browse(
            int(subcategory_id)
        ).exists():
            errors['subcategory_id'] = _("Cette sous-catégorie d'adhésion n'existe pas.")
        if not (post.get('nom_legal') or '').strip():
            errors['nom_legal'] = _("Le nom légal de l'organisation est obligatoire.")
        return errors

    def _update_candidate_profile(self, post):
        """Complète le contact du candidat avec ce qu'il a saisi au dépôt."""
        partner_values = {
            field: post[field].strip()
            for field in self._CANDIDATE_PARTNER_FIELDS
            if isinstance(post.get(field), str) and post[field].strip()
        }
        if partner_values:
            request.env.user.partner_id.sudo().write(partner_values)

    def _attach_membership_documents(self, membership_file):
        """Crée une pièce de dossier par fichier téléversé, typée selon son champ.

        Le type n'est jamais déduit du nom du fichier : il vient du champ du
        formulaire dans lequel le candidat a déposé la pièce. C'est lui qui
        décide ensuite si le dossier est complet — un `Registre.pdf` déposé dans
        « Autre document » reste une pièce complémentaire.
        """
        Document = request.env['opex.membership.document']
        values = []
        for document_type, label, _is_required in self._DOCUMENT_SLOTS:
            for upload in request.httprequest.files.getlist('document_%s' % document_type):
                if not upload.filename:
                    continue
                values.append({
                    'name': upload.filename,
                    'filename': upload.filename,
                    'membership_file_id': membership_file.id,
                    'document_type': document_type,
                    'file': base64.b64encode(upload.read()),
                })
        if values:
            Document.create(values)

    # ------------------------------------------------------------
    # Détail d'un dossier
    # ------------------------------------------------------------

    def _readable_membership_file(self, file_id):
        """Dossier lisible par l'utilisateur courant, en `sudo()`, ou `None`.

        S'en remet au contrôle d'accès standard du portail, qui gère aussi les
        liens partagés par jeton : la consultation n'est pas réservée au seul
        propriétaire.
        """
        try:
            return self._document_check_access('opex.membership.file', file_id)
        except (AccessError, MissingError):
            return None

    def _own_membership_file(self, file_id):
        """Dossier appartenant au candidat connecté, en `sudo()`, ou `None`.

        Réservé aux routes qui *écrivent*. Le propriétaire y est réaffirmé
        explicitement, au même titre que `create()` réécrit `partner_id` : ce
        qui protège une route ne doit pas dépendre du seul filtrage amont.
        Lire un dossier et le modifier ne demandent pas le même niveau de
        preuve, d'où deux helpers distincts.
        """
        membership_file_sudo = self._readable_membership_file(file_id)
        if not membership_file_sudo:
            return None
        if membership_file_sudo.partner_id != request.env.user.partner_id:
            return None
        return membership_file_sudo

    def _render_membership_file_page(self, membership_file, error=None):
        """Page de détail du dossier, éventuellement porteuse d'un message d'erreur."""
        subscription = membership_file._pending_subscription()
        values = self._prepare_portal_layout_values()
        values.update({
            'membership_file': membership_file,
            'pending_subscription': subscription,
            # Voie A : la page de commande native d'Odoo porte déjà le bouton
            # « Payer maintenant » dès qu'un fournisseur de paiement est
            # configuré. Rien à réimplémenter, juste à y conduire le candidat.
            'online_payment_url': (
                subscription.sale_order_id.get_portal_url()
                if subscription.sale_order_id else False
            ),
            # Preuve refusée : le candidat doit lire pourquoi avant d'en
            # redéposer une.
            'rejected_payment': membership_file.subscription_ids.payment_ids.filtered(
                lambda p: p.state == 'rejected'
            )[:1],
            'payment_to_verify': membership_file.subscription_ids.payment_ids.filtered(
                lambda p: p.state == 'to_verify'
            )[:1],
            # Pièces obligatoires encore absentes, présentées comme des champs
            # de dépôt : le candidat en correction doit pouvoir les ajouter
            # sans repasser par un formulaire de création.
            'missing_slots': [
                slot for slot in self._DOCUMENT_SLOTS
                if slot[2] and slot[0] not in membership_file.document_ids.mapped('document_type')
            ],
            # Fil chronologique sans les notes internes du personnel : c'est le
            # modèle qui applique la règle de visibilité, pas le gabarit.
            'history_entries': membership_file._history_entries(internal=False),
            'error': error,
            'page_name': 'membership',
        })
        return request.render('opex_membership.portal_membership_file_page', values)

    @http.route(['/my/membership/<int:file_id>'], type='http', auth='user', website=True)
    def portal_membership_file_page(self, file_id, **kw):
        membership_file_sudo = self._readable_membership_file(file_id)
        if not membership_file_sudo:
            return request.redirect('/my')
        return self._render_membership_file_page(membership_file_sudo)

    def _apply_candidate_action(self, membership_file, action):
        """Déclenche une action du modèle et réaffiche la page si elle refuse.

        Sans cela, un dossier auquel il manque une pièce obligatoire renverrait
        au candidat une page d'erreur Odoo brute au lieu de lui dire ce qui
        manque — exactement l'inverse de la règle d'or de la section 47.
        """
        try:
            with request.env.cr.savepoint():
                action()
        except UserError as error:
            return self._render_membership_file_page(
                membership_file, error=error.args[0])
        return request.redirect('/my/membership/%s' % membership_file.id)

    @http.route(
        ['/my/membership/<int:file_id>/submit'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_membership_file_submit(self, file_id, **post):
        """Soumission du dossier par le candidat (Brouillon -> En contrôle).

        Sans cette route, un dossier déposé au portail resterait en Brouillon et
        ne remonterait jamais au Secrétariat.

        La transition s'exécute en `sudo()` pour que le suivi `mail.thread` du
        changement d'état ne bute pas sur les droits du groupe portail.
        """
        membership_file_sudo = self._own_membership_file(file_id)
        if not membership_file_sudo:
            return request.redirect('/my')
        if membership_file_sudo.state != 'draft':
            return request.redirect('/my/membership/%s' % file_id)
        return self._apply_candidate_action(
            membership_file_sudo, membership_file_sudo.action_submit)

    # ------------------------------------------------------------
    # Réponse à une demande de correction
    # ------------------------------------------------------------

    @http.route(
        ['/my/membership/<int:file_id>/documents'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_membership_file_documents(self, file_id, **post):
        """Remplace la pièce visée par une correction, ou ajoute une pièce manquante.

        Les pièces sont écrites sous l'identité du candidat, pas en `sudo()` :
        la règle d'enregistrement du module vérifie alors elle-même qu'elles
        lui appartiennent *et* que son dossier est encore modifiable. Le
        contrôle du controller et celui de la base disent la même chose, et
        c'est voulu — si l'un se trompe, l'autre tient.
        """
        membership_file_sudo = self._own_membership_file(file_id)
        if not membership_file_sudo:
            return request.redirect('/my')
        if membership_file_sudo.state not in ('draft', 'correction_requested'):
            return request.redirect('/my/membership/%s' % file_id)

        try:
            with request.env.cr.savepoint():
                self._replace_membership_documents(membership_file_sudo)
                self._add_missing_membership_documents(membership_file_sudo)
        except AccessError:
            return self._render_membership_file_page(
                membership_file_sudo,
                error="Vous ne pouvez plus modifier les pièces de ce dossier.",
            )
        return request.redirect('/my/membership/%s' % file_id)

    def _replace_membership_documents(self, membership_file):
        """Écrase le contenu des pièces que le candidat re-téléverse.

        La pièce est retrouvée parmi celles du dossier : un identifiant forgé
        ne désigne rien et le fichier est ignoré, plutôt que d'aller écraser la
        pièce d'un autre candidat.
        """
        Document = request.env['opex.membership.document']
        for key in request.httprequest.files.keys():
            if not key.startswith('replace_'):
                continue
            upload = request.httprequest.files[key]
            if not upload.filename:
                continue
            document = Document.search([
                ('id', '=', int(key[len('replace_'):])),
                ('membership_file_id', '=', membership_file.id),
            ], limit=1) if key[len('replace_'):].isdigit() else Document
            if document:
                document.write({
                    'name': upload.filename,
                    'filename': upload.filename,
                    'file': base64.b64encode(upload.read()),
                })

    def _add_missing_membership_documents(self, membership_file):
        """Ajoute les pièces obligatoires que le dossier n'a pas encore."""
        Document = request.env['opex.membership.document']
        present = membership_file.document_ids.mapped('document_type')
        values = []
        for document_type, _label, is_required in self._DOCUMENT_SLOTS:
            if not is_required or document_type in present:
                continue
            for upload in request.httprequest.files.getlist('document_%s' % document_type):
                if not upload.filename:
                    continue
                values.append({
                    'name': upload.filename,
                    'filename': upload.filename,
                    'membership_file_id': membership_file.id,
                    'document_type': document_type,
                    'file': base64.b64encode(upload.read()),
                })
        if values:
            Document.create(values)

    # ------------------------------------------------------------
    # Paiement de la cotisation (voie B — preuve de paiement)
    # ------------------------------------------------------------

    @http.route(
        ['/my/membership/<int:file_id>/payment_proof'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_membership_payment_proof(self, file_id, **post):
        """Dépôt d'une preuve de paiement par le candidat (section 24, option B).

        Le paiement est créé sous l'identité du candidat : la règle
        d'enregistrement vérifie alors elle-même qu'il porte sur *sa* cotisation,
        et `create()` impose l'état « à vérifier ». Le montant saisi n'engage
        donc rien tant que le Secrétariat n'a pas contrôlé le justificatif.
        """
        membership_file_sudo = self._own_membership_file(file_id)
        if not membership_file_sudo:
            return request.redirect('/my')
        if membership_file_sudo.state != 'payment_pending':
            return request.redirect('/my/membership/%s' % file_id)

        upload = request.httprequest.files.get('justificatif')
        if not upload or not upload.filename:
            return self._render_membership_file_page(
                membership_file_sudo,
                error="Le justificatif de paiement est obligatoire.",
            )

        montant, error = self._parse_payment_amount(post.get('montant'))
        if error:
            return self._render_membership_file_page(membership_file_sudo, error=error)

        proof = {
            'reference': (post.get('reference_paiement') or '').strip(),
            'date_paiement': (post.get('date_paiement') or '').strip() or False,
            'montant': montant,
            'justificatif': base64.b64encode(upload.read()),
            'filename': upload.filename,
        }
        try:
            return self._apply_candidate_action(
                membership_file_sudo,
                lambda: membership_file_sudo.action_submit_payment_proof(**proof),
            )
        except AccessError:
            return self._render_membership_file_page(
                membership_file_sudo,
                error="Vous ne pouvez pas déposer de preuve sur cette cotisation.",
            )

    def _parse_payment_amount(self, raw):
        """Montant déclaré, ou message d'erreur lisible.

        La saisie vient d'un champ libre : une virgule décimale et les espaces
        des montants en dinars sont acceptés plutôt que renvoyés au candidat
        comme une erreur de format.
        """
        cleaned = (raw or '').replace(',', '.').replace(' ', '').replace(' ', '')
        if not cleaned:
            return 0.0, "Indiquez le montant que vous avez payé."
        try:
            montant = float(cleaned)
        except ValueError:
            return 0.0, "Le montant doit être un nombre, par exemple 50000."
        if montant <= 0:
            return 0.0, "Le montant du paiement doit être positif."
        return montant, None

    # ------------------------------------------------------------
    # Signature de la charte (voies A et B)
    # ------------------------------------------------------------

    @http.route(
        ['/my/membership/<int:file_id>/charte'],
        type='http', auth='user', website=True,
    )
    def portal_membership_charte(self, file_id, **kw):
        """La charte d'adhésion, à lire (voie A) ou à imprimer et signer (voie B).

        **Simplification assumée pour le POC** : la charte est un gabarit QWeb
        statique, pas un PDF généré. Le candidat la consulte à l'écran et,
        pour la voie document, l'imprime depuis son navigateur. Brancher un
        vrai rapport PDF (ou servir un document fourni par l'Administrateur)
        ne changerait que cette route — les deux voies de signature et leur
        vérification restent identiques.
        """
        membership_file_sudo = self._readable_membership_file(file_id)
        if not membership_file_sudo:
            return request.redirect('/my')
        return request.render('opex_membership.portal_charte_adhesion', {
            'membership_file': membership_file_sudo,
            'page_name': 'membership',
        })

    @http.route(
        ['/my/membership/<int:file_id>/sign'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_membership_sign(self, file_id, **post):
        """Voie A : signature électronique par confirmation horodatée.

        La case de certification est exigée côté serveur, pas seulement dans
        le navigateur : c'est le seul consentement que le POC enregistre.
        """
        membership_file_sudo = self._own_membership_file(file_id)
        if not membership_file_sudo:
            return request.redirect('/my')
        if membership_file_sudo.state != 'signature_pending':
            return request.redirect('/my/membership/%s' % file_id)
        if not post.get('certifie'):
            return self._render_membership_file_page(
                membership_file_sudo,
                error="Cochez la case de certification avant de signer la charte.",
            )
        return self._apply_candidate_action(
            membership_file_sudo, membership_file_sudo.action_sign_charte_digital)

    @http.route(
        ['/my/membership/<int:file_id>/charte_document'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_membership_charte_document(self, file_id, **post):
        """Voie B : dépôt de la charte signée à la main.

        L'écriture passe par le dossier en `sudo()` — `charte_document` est un
        champ du dossier, que la règle d'enregistrement du portail ne laisse
        modifier qu'en Brouillon. L'appartenance et l'état sont donc réaffirmés
        ici, comme pour la soumission et la re-soumission.
        """
        membership_file_sudo = self._own_membership_file(file_id)
        if not membership_file_sudo:
            return request.redirect('/my')
        if membership_file_sudo.state != 'signature_pending':
            return request.redirect('/my/membership/%s' % file_id)

        upload = request.httprequest.files.get('charte_document')
        if not upload or not upload.filename:
            return self._render_membership_file_page(
                membership_file_sudo,
                error="Joignez la charte signée avant de l'envoyer.",
            )
        return self._apply_candidate_action(
            membership_file_sudo,
            lambda: membership_file_sudo.action_submit_charte_document(
                base64.b64encode(upload.read()), upload.filename),
        )

    @http.route(
        ['/my/membership/<int:file_id>/resubmit'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_membership_file_resubmit(self, file_id, **post):
        """Re-soumission après correction (Correction demandée -> En contrôle).

        C'est `action_resubmit()` qui marque les corrections traitées et
        revérifie les pièces obligatoires : le controller ne rejoue aucune de
        ces règles.
        """
        membership_file_sudo = self._own_membership_file(file_id)
        if not membership_file_sudo:
            return request.redirect('/my')
        if membership_file_sudo.state != 'correction_requested':
            return request.redirect('/my/membership/%s' % file_id)
        return self._apply_candidate_action(
            membership_file_sudo, membership_file_sudo.action_resubmit)
