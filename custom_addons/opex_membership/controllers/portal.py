import base64

from odoo import _, http
from odoo.exceptions import AccessError, MissingError
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

    @http.route(['/my/membership/<int:file_id>'], type='http', auth='user', website=True)
    def portal_membership_file_page(self, file_id, **kw):
        try:
            membership_file_sudo = self._document_check_access('opex.membership.file', file_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        values = self._prepare_portal_layout_values()
        values.update({
            'membership_file': membership_file_sudo,
            'page_name': 'membership',
        })
        return request.render('opex_membership.portal_membership_file_page', values)

    @http.route(
        ['/my/membership/<int:file_id>/submit'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_membership_file_submit(self, file_id, **post):
        """Soumission du dossier par le candidat (Brouillon -> En contrôle).

        Sans cette route, un dossier déposé au portail resterait en Brouillon et
        ne remonterait jamais au Secrétariat.

        La transition s'exécute en `sudo()` pour que le suivi `mail.thread` du
        changement d'état ne bute pas sur les droits du groupe portail. Le
        propriétaire du dossier est donc réaffirmé explicitement juste avant,
        au même titre que `create()` réécrit `partner_id` : ce qui protège la
        route ne doit pas dépendre du seul filtrage amont.
        """
        try:
            membership_file_sudo = self._document_check_access('opex.membership.file', file_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        if membership_file_sudo.partner_id != request.env.user.partner_id:
            return request.redirect('/my')
        if membership_file_sudo.state == 'draft':
            membership_file_sudo.action_submit()
        return request.redirect('/my/membership/%s' % file_id)
