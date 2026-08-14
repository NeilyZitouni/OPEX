from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class OpexMembershipFile(models.Model):
    _name = 'opex.membership.file'
    _description = "Dossier d'adhésion"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_depot desc'

    # Séquence exacte de la section 15 de la spécification UX. Les sorties
    # négatives sont des états à part entière, reconnaissables par `is_rejected()`
    # plutôt qu'énumérées une à une dans chaque vue.
    STATE_SEQUENCE = (
        'draft',
        'control',
        'correction_requested',
        'committee',
        'copil_pending',
        'copil_validated',
        'payment_pending',
        'payment_verification',
        'signature_pending',
        'signature_verification',
        'active',
    )
    REJECTED_STATES = ('rejected_control', 'rejected_committee', 'rejected_copil')

    partner_id = fields.Many2one(
        'res.partner',
        string="Membre",
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    subcategory_id = fields.Many2one(
        'opex.membership.subcategory',
        string="Sous-catégorie demandée",
        tracking=True,
        help="Sous-catégorie d'adhésion souhaitée ; détermine le montant de la "
             "cotisation. À défaut, celle du contact est utilisée.",
    )
    category_id = fields.Many2one(
        'opex.membership.category',
        string="Catégorie demandée",
        related='subcategory_id.category_id',
        store=True,
    )
    date_depot = fields.Datetime(string="Date de dépôt", default=fields.Datetime.now)
    document_ids = fields.One2many(
        'opex.membership.document', 'membership_file_id', string="Pièces du dossier"
    )
    correction_ids = fields.One2many(
        'opex.membership.correction', 'file_id', string="Demandes de correction"
    )
    subscription_ids = fields.One2many(
        'opex.subscription', 'membership_file_id', string="Cotisations"
    )
    signature_date = fields.Date(string="Date de signature de la charte")

    # --- Avis du Comité d'admission (acteur 4 de la spécification) ----------
    avis_comite = fields.Selection(
        [
            ('favorable', 'Favorable'),
            ('defavorable', 'Défavorable'),
            ('complement', 'Demande de complément'),
        ],
        string="Avis du comité d'admission",
        tracking=True,
        help="Avis motivé rendu par le Comité d'admission, que le COPIL consulte "
             "avant de décider.",
    )
    commentaire_comite = fields.Text(string="Commentaire du comité")

    # --- Section A : informations de l'organisation -------------------------
    nom_legal = fields.Char(string="Nom légal")
    nom_commercial = fields.Char(string="Nom commercial")
    forme_juridique = fields.Char(string="Forme juridique")
    nif = fields.Char(string="NIF")
    rc = fields.Char(string="RC")
    adresse = fields.Char(string="Adresse")
    wilaya = fields.Char(string="Wilaya")
    commune = fields.Char(string="Commune")
    site_web = fields.Char(string="Site web")
    email_pro = fields.Char(string="Email professionnel")
    telephone = fields.Char(string="Téléphone")

    # --- Section B : activité ----------------------------------------------
    secteur_activite = fields.Char(string="Secteur d'activité")
    activite_principale = fields.Char(string="Activité principale")
    description_activite = fields.Text(string="Description de l'activité")
    nombre_salaries = fields.Integer(string="Nombre de salariés")
    currency_id = fields.Many2one(
        'res.currency',
        string="Devise",
        default=lambda self: self.env.company.currency_id,
    )
    chiffre_affaires = fields.Monetary(
        string="Chiffre d'affaires", currency_field='currency_id'
    )
    certification_ids = fields.Many2many('opex.certification', string="Certifications")

    # --- Section C : représentant de l'organisation -------------------------
    representant_nom = fields.Char(string="Nom du représentant")
    representant_prenom = fields.Char(string="Prénom du représentant")
    representant_fonction = fields.Char(string="Fonction")
    representant_email = fields.Char(string="Email du représentant")
    representant_telephone = fields.Char(string="Téléphone du représentant")

    # --- Section D : informations complémentaires ---------------------------
    presentation = fields.Text(string="Présentation de l'organisation")
    motivation = fields.Text(string="Pourquoi rejoindre le GIC OPEX Group ?")
    domaines_expertise = fields.Text(string="Domaines d'expertise")
    partenariats_existants = fields.Text(string="Partenariats existants")

    state = fields.Selection(
        [
            ('draft', 'Brouillon'),
            ('control', 'En contrôle'),
            ('correction_requested', 'Correction demandée'),
            ('committee', "Comité d'admission"),
            ('copil_pending', 'Validation COPIL'),
            ('copil_validated', 'Validé COPIL'),
            ('payment_pending', 'Paiement en attente'),
            ('payment_verification', 'Paiement à vérifier'),
            ('signature_pending', 'Signature en attente'),
            ('signature_verification', 'Signature à vérifier'),
            ('active', 'Actif'),
            ('rejected_control', 'Refusé au contrôle'),
            ('rejected_committee', 'Refusé par le comité'),
            ('rejected_copil', 'Refusé par le COPIL'),
        ],
        string="État",
        default='draft',
        required=True,
        tracking=True,
    )

    def _state_label(self):
        self.ensure_one()
        return dict(self._fields['state'].selection).get(self.state)

    def is_rejected(self):
        """Le dossier est-il sorti du parcours par un refus ?

        Utilitaire volontairement unique : les vues testent `is_rejected()`
        plutôt que d'énumérer les trois états terminaux, qui deviendraient
        autant d'endroits à corriger si un quatrième apparaissait.
        """
        self.ensure_one()
        return self.state in self.REJECTED_STATES

    # ------------------------------------------------------------
    # Complétude du dossier
    # ------------------------------------------------------------

    def _missing_required_documents(self):
        """Libellés des pièces obligatoires encore absentes du dossier."""
        self.ensure_one()
        Document = self.env['opex.membership.document']
        present = set(self.document_ids.mapped('document_type'))
        return [
            label for document_type, label in Document._required_type_labels().items()
            if document_type not in present
        ]

    def _check_documents_complete(self):
        self.ensure_one()
        missing = self._missing_required_documents()
        if missing:
            raise UserError(_(
                "Le dossier de %(candidat)s est incomplet : il manque %(pieces)s. "
                "Ces pièces sont obligatoires pour poursuivre l'instruction."
            ) % {
                'candidat': self.partner_id.name,
                'pieces': ', '.join(missing),
            })

    def _ensure_state(self, expected, action_label):
        """Refuse une transition demandée depuis un état qui ne la permet pas."""
        self.ensure_one()
        if self.state not in expected:
            raise UserError(_(
                "%(action)s est impossible sur ce dossier : il est actuellement "
                "à l'état « %(etat)s »."
            ) % {'action': action_label, 'etat': self._state_label()})

    @api.model_create_multi
    def create(self, vals_list):
        """Un candidat portail ne dépose de dossier qu'en son propre nom.

        Le formulaire de `/my/membership/new` est rempli côté navigateur : ni
        `partner_id` ni `state` ne peuvent en venir. Les réécrire ici, plutôt que
        de se contenter de ne pas les afficher, ferme la porte à une requête
        forgée qui créerait un dossier au nom d'un autre contact — ou déjà validé.
        """
        if self.env.user._is_portal():
            partner_id = self.env.user.partner_id.id
            for vals in vals_list:
                vals['partner_id'] = partner_id
                vals['state'] = 'draft'
        return super().create(vals_list)

    # ------------------------------------------------------------
    # Dépôt et contrôle du Secrétariat
    # ------------------------------------------------------------

    def action_submit(self):
        """soumettreDossier : Brouillon -> En contrôle.

        Le dépôt est le moment où les pièces obligatoires sont exigées : c'est
        ce que le candidat certifie à l'écran de récapitulatif (section 13).
        """
        for rec in self:
            rec._ensure_state(('draft',), _("Le dépôt du dossier"))
            rec._check_documents_complete()
            rec.state = 'control'

    def action_request_correction(self, motif, commentaire=False, document=None):
        """Renvoie le dossier au candidat pour correction.

        Deux acteurs l'empruntent : le Secrétariat depuis le contrôle, et le
        Comité d'admission quand il rend un avis « Demande de complément ».
        C'est la même action métier vue de deux étapes, d'où un seul point
        d'entrée plutôt qu'une méthode par acteur.

        Trace *quelle* pièce pose problème et *pourquoi* : le candidat doit
        pouvoir agir sans deviner. Le parcours complet côté candidat (ré-upload
        puis re-soumission) relève de l'Extension 11.
        """
        self.ensure_one()
        self._ensure_state(('control', 'committee'), _("La demande de correction"))
        if not motif:
            raise UserError(_("Le motif de la correction est obligatoire."))
        correction = self.env['opex.membership.correction'].create({
            'file_id': self.id,
            'document_id': document.id if document else False,
            'motif': motif,
            'commentaire': commentaire or False,
        })
        self.state = 'correction_requested'
        return correction

    def action_resubmit(self):
        """Le candidat renvoie son dossier corrigé : Correction demandée -> En contrôle."""
        for rec in self:
            rec._ensure_state(('correction_requested',), _("La re-soumission du dossier"))
            rec._check_documents_complete()
            rec.correction_ids.filtered(lambda c: not c.resolved).resolved = True
            rec.state = 'control'

    def action_validate_secretariat(self):
        """validerParSecretariat : En contrôle -> Comité d'admission.

        L'avis précédent est effacé à l'entrée : un dossier qui revient au
        comité après un complément doit être réexaminé, et un avis périmé
        affiché au COPIL lui ferait valider sur une décision qui n'a plus
        cours. L'historique reste lisible dans le chatter, `avis_comite` étant
        un champ suivi.
        """
        for rec in self:
            rec._ensure_state(('control',), _("La validation par le Secrétariat"))
            rec._check_documents_complete()
            rec.write({
                'state': 'committee',
                'avis_comite': False,
                'commentaire_comite': False,
            })

    def action_reject_control(self):
        """Sortie négative du contrôle (section 15)."""
        for rec in self:
            rec._ensure_state(('control',), _("Le refus au contrôle"))
            rec.state = 'rejected_control'

    # ------------------------------------------------------------
    # Comité d'admission et COPIL
    # ------------------------------------------------------------

    def action_record_avis_comite(self):
        """Enregistre l'avis du Comité d'admission et oriente le dossier.

        L'avis est lu sur l'enregistrement, pas reçu en paramètre : le
        formulaire (back-office comme page staff) l'écrit d'abord, cette
        méthode ne fait qu'appliquer la conséquence. Une donnée cliente ne peut
        donc pas décider seule d'une transition — c'est l'état du dossier qui
        commande, comme partout ailleurs dans ce workflow.

        Les trois issues de la section 21 : favorable transmet au COPIL,
        défavorable met fin au parcours, complément renvoie au candidat.
        """
        for rec in self:
            rec._ensure_state(('committee',), _("L'enregistrement de l'avis du comité"))
            if not rec.avis_comite:
                raise UserError(_(
                    "Choisissez un avis (favorable, défavorable ou demande de "
                    "complément) avant de l'enregistrer."
                ))
            if rec.avis_comite == 'favorable':
                rec.action_send_to_copil()
            elif rec.avis_comite == 'defavorable':
                rec.action_reject_committee()
            else:
                # Le commentaire devient le contenu de la demande de
                # correction : sans lui, le candidat reçoit un dossier à
                # compléter sans savoir ce qu'on attend de lui.
                if not (rec.commentaire_comite or '').strip():
                    raise UserError(_(
                        "Précisez dans le commentaire le complément attendu : "
                        "c'est ce texte que le candidat recevra."
                    ))
                rec.action_request_correction(
                    motif=_("Complément demandé par le Comité d'admission"),
                    commentaire=rec.commentaire_comite,
                )

    def action_send_to_copil(self):
        """Comité d'admission -> Validation COPIL, sur avis favorable."""
        for rec in self:
            rec._ensure_state(('committee',), _("La transmission au COPIL"))
            rec.state = 'copil_pending'

    def action_reject_committee(self):
        for rec in self:
            rec._ensure_state(('committee',), _("Le refus par le comité"))
            rec.state = 'rejected_committee'

    def action_validate_copil(self):
        """validerParCOPIL : Validation COPIL -> Validé COPIL -> Paiement en attente.

        La cotisation est émise dans la foulée : la spécification (section 22)
        enchaîne directement « Adhésion validée » et « Étape suivante :
        Paiement de la cotisation », sans action intermédiaire.
        """
        for rec in self:
            rec._ensure_state(('copil_pending',), _("La validation par le COPIL"))
            rec.state = 'copil_validated'
            rec.action_create_subscription()
            rec.state = 'payment_pending'

    def action_reject_copil(self):
        for rec in self:
            rec._ensure_state(('copil_pending',), _("Le refus par le COPIL"))
            rec.state = 'rejected_copil'

    # ------------------------------------------------------------
    # Cotisation
    # ------------------------------------------------------------

    def _get_subcategory(self):
        """Sous-catégorie facturée : celle demandée sur le dossier, sinon celle du contact."""
        self.ensure_one()
        return self.subcategory_id or self.partner_id.subcategory_id

    def action_create_subscription(self):
        """Émet la cotisation via la facturation native Odoo (sale.order).

        L'encaissement effectif fera passer le dossier à la signature de la
        charte (cf. `action_confirm_payment`), pas directement à l'activation :
        la Partie V exige les deux conditions.
        """
        self.ensure_one()
        partner = self.partner_id
        subcategory = self._get_subcategory()
        if not subcategory:
            raise UserError(_(
                "Impossible de générer la cotisation : %s n'a pas de "
                "sous-catégorie d'adhésion définie (avec un montant de "
                "cotisation associé)."
            ) % partner.name)

        product = subcategory._get_cotisation_product()
        order = self.env['sale.order'].sudo().create({
            'partner_id': partner.id,
            'order_line': [fields.Command.create({
                'product_id': product.id,
                'product_uom_qty': 1,
            })],
        })

        today = fields.Date.context_today(self)
        subscription = self.env['opex.subscription'].create({
            'partner_id': partner.id,
            'membership_file_id': self.id,
            'sale_order_id': order.id,
            'currency_id': subcategory.currency_id.id,
            'montant': product.list_price,
            'date_emission': today,
            'date_echeance': today + timedelta(days=30),
        })
        order.action_confirm()
        return subscription

    def _pending_subscription(self):
        """Cotisation en attente de règlement sur ce dossier, sinon vide."""
        self.ensure_one()
        return self.subscription_ids.filtered(lambda s: s.state == 'waiting')[:1]

    def action_submit_payment_proof(self, reference, date_paiement, montant,
                                    justificatif, filename=False):
        """Voie B : le candidat déclare un paiement effectué hors du portail.

        Rien n'est soldé à ce stade — la preuve part « à vérifier » et le
        dossier attend le contrôle du Secrétariat. C'est la différence avec la
        voie A, où l'encaissement est constaté par Odoo lui-même.
        """
        self.ensure_one()
        self._ensure_state(('payment_pending',), _("Le dépôt d'une preuve de paiement"))
        subscription = self._pending_subscription()
        if not subscription:
            raise UserError(_(
                "Aucune cotisation n'attend de règlement sur ce dossier."
            ))
        if not justificatif:
            raise UserError(_("Le justificatif de paiement est obligatoire."))
        if not montant or montant <= 0:
            raise UserError(_("Le montant du paiement doit être positif."))

        # `sudo(False)` : le dossier est manipulé en `sudo()` par le portail,
        # mais la preuve, elle, doit être créée sous l'identité réelle du
        # candidat — c'est ce qui laisse la règle d'enregistrement vérifier
        # qu'elle porte bien sur sa propre cotisation. Le contrôle du
        # controller et celui de la base disent alors la même chose.
        payment = self.env['opex.payment'].sudo(False).create({
            'subscription_id': subscription.id,
            'montant': montant,
            'date_paiement': date_paiement or fields.Datetime.now(),
            'reference_transaction': reference or False,
            'mode_paiement': 'transfer',
            'justificatif': justificatif,
            'justificatif_filename': filename or False,
            'state': 'to_verify',
        })
        self.state = 'payment_verification'
        return payment

    def action_reject_payment(self):
        """La preuve déposée est rejetée : le dossier redevient à payer.

        Le candidat peut alors en déposer une nouvelle ; le motif du rejet est
        porté par le paiement rejeté, pas par le dossier.
        """
        for rec in self:
            rec._ensure_state(('payment_verification',), _("Le rejet du paiement"))
            rec.state = 'payment_pending'

    def action_confirm_payment(self):
        """Paiement encaissé -> Signature en attente.

        Appelé automatiquement quand la cotisation liée passe à Payée. L'état
        `payment_verification` (preuve de paiement déposée par le candidat et
        contrôlée par le Secrétariat) est desservi par l'Extension 12 ; il est
        déjà accepté ici pour que les deux voies convergent au même endroit.
        """
        for rec in self:
            rec._ensure_state(
                ('payment_pending', 'payment_verification'),
                _("La confirmation du paiement"),
            )
            rec.state = 'signature_pending'

    # ------------------------------------------------------------
    # Signature de la charte et activation
    # ------------------------------------------------------------

    def action_sign_charte(self):
        """Signature de la charte -> activation de l'adhésion.

        **Raccourci assumé, à remplacer en Extension 13.** La séquence complète
        passe par `signature_verification` : le candidat dépose sa signature
        (voie digitale ou charte signée, section 25), puis le Secrétariat la
        contrôle avant l'activation. Ce stub enregistre la signature horodatée
        et active directement, ce qui suffit à jouer le parcours de bout en
        bout tant que les deux voies n'existent pas.
        """
        for rec in self:
            rec._ensure_state(('signature_pending',), _("La signature de la charte"))
            rec.signature_date = fields.Date.context_today(rec)
            rec._activate_membership()

    def _activate_membership(self):
        """Dernière étape du parcours : le candidat devient membre actif.

        Paiement confirmé *et* charte signée sont acquis à ce stade — la
        Partie V de la spécification exige les deux.
        """
        for rec in self:
            rec.state = 'active'
            partner_values = {'is_member': True, 'is_published_directory': True}
            # La sous-catégorie du membre est celle que son dossier a fait
            # accepter ; ne rien écrire si le dossier n'en portait pas, pour ne
            # pas effacer celle que le contact avait déjà.
            subcategory = rec._get_subcategory()
            if subcategory:
                partner_values['subcategory_id'] = subcategory.id
            rec.partner_id.write(partner_values)
