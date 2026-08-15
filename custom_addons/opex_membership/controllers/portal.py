import base64
from urllib.parse import quote

from odoo import _, fields, http
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

    # Champs saisis à chaque écran de saisie libre. Une seule table : elle
    # décide à la fois ce que l'écran affiche et ce que le `write()` accepte,
    # de sorte qu'un champ ajouté au gabarit sans l'être ici est simplement
    # ignoré côté serveur.
    _STEP_FIELDS = {
        'organisation': (
            'nom_legal', 'nom_commercial', 'forme_juridique', 'nif', 'rc',
            'adresse', 'wilaya', 'commune', 'site_web', 'email_pro', 'telephone',
        ),
        'activite': ('secteur_activite', 'activite_principale', 'description_activite'),
        'representant': (
            'representant_nom', 'representant_prenom', 'representant_fonction',
            'representant_email', 'representant_telephone',
        ),
        'complement': (
            'presentation', 'motivation', 'domaines_expertise', 'partenariats_existants',
        ),
    }

    # Enchaînement des sept écrans (sections 5 à 14). L'ordre vit ici seul :
    # « écran suivant » et « écran précédent » s'en déduisent.
    _PARCOURS_STEPS = (
        ('category', '/my/membership/new'),
        ('organisation', '/my/membership/new/organisation'),
        ('activite', '/my/membership/new/activite'),
        ('representant', '/my/membership/new/representant'),
        ('complement', '/my/membership/new/complement'),
        ('documents', '/my/membership/new/documents'),
        ('recap', '/my/membership/new/recap'),
    )

    def _step_url(self, step):
        return dict(self._PARCOURS_STEPS)[step]

    def _next_step(self, step):
        keys = [key for key, _url in self._PARCOURS_STEPS]
        return keys[min(keys.index(step) + 1, len(keys) - 1)]

    def _current_draft(self):
        """Brouillon en cours du candidat connecté, ou recordset vide.

        Retrouvé par une recherche sur `partner_id`, jamais par un
        identifiant reçu du client : le parcours n'expose aucun id de dossier
        dans ses URL, il n'y a donc rien à forger. La restriction à `draft`
        garantit qu'un dossier déjà soumis ne peut plus être réécrit par ces
        écrans, même en rejouant une URL d'étape.
        """
        return request.env['opex.membership.file'].sudo().search([
            ('partner_id', '=', request.env.user.partner_id.id),
            ('state', '=', 'draft'),
        ], order='id desc', limit=1)

    def _parcours_values(self, membership_file, step, **extra):
        values = self._prepare_portal_layout_values()
        values.update({
            'membership_file': membership_file,
            'steps': self._PARCOURS_STEPS,
            'step': step,
            'step_index': [key for key, _url in self._PARCOURS_STEPS].index(step),
            'step_url': self._step_url,
            'page_name': 'membership_new',
        })
        values.update(extra)
        return values

    def _render_step(self, step, membership_file, **extra):
        return request.render(
            'opex_membership.portal_membership_step_%s' % step,
            self._parcours_values(membership_file, step, **extra))

    def _require_draft(self):
        """Brouillon en cours, ou renvoi au premier écran s'il n'y en a pas."""
        membership_file = self._current_draft()
        if not membership_file:
            return None, request.redirect('/my/membership/new')
        return membership_file, None

    def _save_step(self, membership_file, step, post):
        """Écrit la part du dossier saisie à cet écran, puis avance l'étape.

        Écriture partielle : seuls les champs de l'écran courant sont touchés,
        ce qui rend chaque validation indépendante — quitter en cours de route
        ne perd que ce qui n'a pas encore été envoyé.
        """
        # Les écrans « pièces » et « récapitulatif » n'ont pas de champ de
        # saisie libre : ils n'en font pas moins avancer le parcours, d'où le
        # défaut à vide plutôt qu'une entrée factice dans la table.
        values = {
            field: (post.get(field) or '').strip()
            for field in self._STEP_FIELDS.get(step, ())
            if isinstance(post.get(field), str)
        }
        # L'étape n'est jamais reculée : un candidat qui revient corriger un
        # écran précédent ne doit pas perdre sa progression.
        keys = [key for key, _url in self._PARCOURS_STEPS]
        reached = self._next_step(step)
        if keys.index(reached) > keys.index(membership_file.parcours_step):
            values['parcours_step'] = reached
        membership_file.write(values)

    # ------------------------------------------------------------
    # Écran 1 — catégorie puis sous-catégorie
    # ------------------------------------------------------------

    @http.route(
        ['/my/membership/new'],
        type='http', auth='user', website=True, methods=['GET', 'POST'],
    )
    def portal_membership_new(self, **post):
        """Choix de la catégorie, puis de la sous-catégorie (section 6).

        Deux temps, pas un menu déroulant unique : la catégorie se choisit
        d'abord, et l'écran ne propose ensuite que les sous-catégories qui en
        dépendent. Le passage de l'une à l'autre se fait par un paramètre
        d'URL, ce qui laisse le candidat revenir en arrière.
        """
        MembershipFile = request.env['opex.membership.file']
        if not MembershipFile.has_access('create'):
            return request.redirect('/my')

        Category = request.env['opex.membership.category']
        categories = Category.sudo().search([('subcategory_ids', '!=', False)])
        draft = self._current_draft()

        if request.httprequest.method == 'POST':
            subcategory = self._selected_subcategory(post.get('subcategory_id'))
            if not subcategory:
                return self._render_step(
                    'category', draft, categories=categories, category=None,
                    draft=draft,
                    error=_("Veuillez choisir une sous-catégorie d'adhésion."))
            if draft:
                draft.subcategory_id = subcategory.id
                membership_file = draft
            else:
                # `partner_id` et `state` sont volontairement absents : le
                # `create()` du modèle les impose côté serveur.
                membership_file = MembershipFile.create(
                    {'subcategory_id': subcategory.id})
            if membership_file.parcours_step == 'category':
                membership_file.sudo().parcours_step = 'organisation'
            return request.redirect(self._step_url('organisation'))

        # Deuxième temps : les sous-catégories d'une catégorie choisie.
        category = None
        raw_category = (post.get('category') or '').strip()
        if raw_category.isdigit():
            category = categories.filtered(lambda c: c.id == int(raw_category))[:1]

        return self._render_step(
            'category', draft, categories=categories, category=category,
            draft=draft, error=None)

    def _selected_subcategory(self, raw_value):
        """Sous-catégorie choisie, validée contre la base."""
        raw_value = (raw_value or '').strip()
        if not raw_value.isdigit():
            return request.env['opex.membership.subcategory']
        return request.env['opex.membership.subcategory'].sudo().search(
            [('id', '=', int(raw_value))], limit=1)

    # ------------------------------------------------------------
    # Écrans 2 à 5 — sections A à D
    # ------------------------------------------------------------

    @http.route(
        ['/my/membership/new/organisation'],
        type='http', auth='user', website=True, methods=['GET', 'POST'],
    )
    def portal_membership_step_organisation(self, **post):
        membership_file, redirect = self._require_draft()
        if redirect:
            return redirect
        if request.httprequest.method == 'POST':
            if not (post.get('nom_legal') or '').strip():
                return self._render_step(
                    'organisation', membership_file,
                    error=_("Le nom légal de l'organisation est obligatoire."))
            self._save_step(membership_file, 'organisation', post)
            self._update_candidate_profile(post)
            return request.redirect(self._step_url('activite'))
        return self._render_step('organisation', membership_file)

    @http.route(
        ['/my/membership/new/activite'],
        type='http', auth='user', website=True, methods=['GET', 'POST'],
    )
    def portal_membership_step_activite(self, **post):
        membership_file, redirect = self._require_draft()
        if redirect:
            return redirect

        certifications = request.env['opex.certification'].sudo().search([])
        if request.httprequest.method == 'POST':
            self._save_step(membership_file, 'activite', post)
            self._save_activity_extras(membership_file, post, certifications)
            self._update_candidate_profile(post)
            return request.redirect(self._step_url('representant'))
        return self._render_step(
            'activite', membership_file, certifications=certifications)

    def _save_activity_extras(self, membership_file, post, certifications):
        """Champs de la section B qui ne sont pas du texte libre.

        Les certifications cochées sont recoupées avec celles qui existent
        réellement : un identifiant inventé côté navigateur est écarté au lieu
        d'être écrit.
        """
        values = {}
        salaries = (post.get('nombre_salaries') or '').strip()
        if salaries:
            values['nombre_salaries'] = int(salaries) if salaries.isdigit() else 0
        chiffre = (post.get('chiffre_affaires') or '').replace(',', '.').replace(' ', '')
        if chiffre:
            try:
                values['chiffre_affaires'] = float(chiffre)
            except ValueError:
                values['chiffre_affaires'] = 0.0
        raw_ids = request.httprequest.form.getlist('certification_ids')
        selected = certifications.filtered(lambda c: str(c.id) in raw_ids)
        values['certification_ids'] = [fields.Command.set(selected.ids)]
        membership_file.write(values)

    @http.route(
        ['/my/membership/new/representant'],
        type='http', auth='user', website=True, methods=['GET', 'POST'],
    )
    def portal_membership_step_representant(self, **post):
        membership_file, redirect = self._require_draft()
        if redirect:
            return redirect
        if request.httprequest.method == 'POST':
            self._save_step(membership_file, 'representant', post)
            return request.redirect(self._step_url('complement'))
        return self._render_step('representant', membership_file)

    @http.route(
        ['/my/membership/new/complement'],
        type='http', auth='user', website=True, methods=['GET', 'POST'],
    )
    def portal_membership_step_complement(self, **post):
        membership_file, redirect = self._require_draft()
        if redirect:
            return redirect
        if request.httprequest.method == 'POST':
            self._save_step(membership_file, 'complement', post)
            return request.redirect(self._step_url('documents'))
        return self._render_step('complement', membership_file)

    # ------------------------------------------------------------
    # Écran 6 — pièces du dossier
    # ------------------------------------------------------------

    @http.route(
        ['/my/membership/new/documents'],
        type='http', auth='user', website=True, methods=['GET', 'POST'],
    )
    def portal_membership_step_documents(self, **post):
        membership_file, redirect = self._require_draft()
        if redirect:
            return redirect
        if request.httprequest.method == 'POST':
            self._save_parcours_documents(membership_file)
            self._save_step(membership_file, 'documents', post)
            return request.redirect(self._step_url('recap'))
        return self._render_step(
            'documents', membership_file, document_slots=self._DOCUMENT_SLOTS)

    def _save_parcours_documents(self, membership_file):
        """Enregistre les pièces déposées, une par type.

        Redéposer une pièce du même type remplace la précédente au lieu d'en
        empiler une seconde : le candidat qui se trompe de fichier corrige
        simplement son erreur.
        """
        Document = request.env['opex.membership.document']
        for document_type, _label, _required in self._DOCUMENT_SLOTS:
            upload = request.httprequest.files.get('document_%s' % document_type)
            if not upload or not upload.filename:
                continue
            values = {
                'name': upload.filename,
                'filename': upload.filename,
                'file': base64.b64encode(upload.read()),
            }
            existing = Document.search([
                ('membership_file_id', '=', membership_file.id),
                ('document_type', '=', document_type),
            ], limit=1)
            if existing:
                existing.write(values)
            else:
                Document.create(dict(
                    values, membership_file_id=membership_file.id,
                    document_type=document_type))

    # ------------------------------------------------------------
    # Écran 7 — récapitulatif et dépôt
    # ------------------------------------------------------------

    @http.route(
        ['/my/membership/new/recap'],
        type='http', auth='user', website=True, methods=['GET', 'POST'],
    )
    def portal_membership_step_recap(self, **post):
        """Récapitulatif, certification sur l'honneur, puis dépôt (sections 13-14)."""
        membership_file, redirect = self._require_draft()
        if redirect:
            return redirect

        if request.httprequest.method == 'POST':
            if not post.get('certifie'):
                return self._render_step(
                    'recap', membership_file,
                    error=_("Cochez la case de certification avant de déposer "
                            "votre dossier."))
            # `action_submit()` vérifie lui-même les pièces obligatoires : la
            # règle reste dans le modèle, cet écran ne la rejoue pas.
            return self._apply_candidate_action(
                membership_file, membership_file.action_submit)
        return self._render_step('recap', membership_file)

    def _update_candidate_profile(self, post):
        """Complète le contact du candidat avec ce qu'il a saisi au dépôt."""
        partner_values = {
            field: post[field].strip()
            for field in self._CANDIDATE_PARTNER_FIELDS
            if isinstance(post.get(field), str) and post[field].strip()
        }
        if partner_values:
            request.env.user.partner_id.sudo().write(partner_values)

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
