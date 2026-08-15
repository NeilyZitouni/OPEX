from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_amount, html2plaintext


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
    signature_mode = fields.Selection(
        [
            ('digital', 'Signature électronique'),
            ('document', 'Charte signée déposée'),
        ],
        string="Mode de signature",
        help="Voie empruntée par le candidat pour signer la charte d'adhésion.",
    )
    charte_document = fields.Binary(string="Charte signée", attachment=True)
    charte_document_filename = fields.Char(string="Nom de la charte signée")
    charte_motif_rejet = fields.Char(string="Motif du rejet de la signature")

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

    # ------------------------------------------------------------
    # Notifications (section 43 de la spécification UX)
    # ------------------------------------------------------------

    _NOTIFY_GROUPS = {
        'secretariat': 'opex_membership.group_secretariat',
        'comite': 'opex_membership.group_comite',
        'copil': 'opex_membership.group_copil',
    }

    def _candidate_label(self):
        """Nom sous lequel le dossier est désigné au personnel interne."""
        self.ensure_one()
        return self.nom_legal or self.partner_id.name

    def _format_montant(self, subscription):
        return format_amount(self.env, subscription.montant, subscription.currency_id)

    def _notify_candidate(self, body):
        """Adresse un message au candidat sur son dossier.

        Deux règles tiennent ici :

        - le texte est rédigé pour un lecteur, jamais dérivé de `state` — un
          candidat ne doit pas lire « payment_verification » (section 47) ;
        - l'envoi passe par `sudo()` parce que l'auteur de la transition n'est
          pas toujours le propriétaire du dossier (le Secrétariat écrit au
          candidat), mais l'auteur du message reste l'utilisateur réel :
          `sudo()` élève les droits, pas l'identité.
        """
        for rec in self:
            rec.sudo().message_post(
                body=body,
                partner_ids=rec.partner_id.ids,
                subtype_xmlid='mail.mt_comment',
            )

    def _notify_staff(self, group_key, body):
        """Prévient les membres d'un rôle interne qu'un dossier les attend.

        Les destinataires sont les utilisateurs du groupe — `all_user_ids`
        plutôt que `user_ids`, pour ne pas oublier ceux qui le détiennent par
        implication. Ils sont notifiés sans devenir abonnés : suivre chaque
        dossier à vie transformerait la boîte du Secrétariat en journal.

        **Note interne (`mt_note`), pas commentaire.** Le candidat est abonné à
        son dossier : avec `mt_comment`, tout message de coordination interne
        (« il attend votre contrôle », l'avis du Comité) lui serait notifié et
        s'afficherait dans son historique. `mt_note` porte un sous-type
        `internal`, qu'Odoo exclut des destinataires et des vues portail —
        les destinataires explicites, eux, sont notifiés normalement.
        """
        group = self.env.ref(self._NOTIFY_GROUPS[group_key], raise_if_not_found=False)
        partners = group.sudo().all_user_ids.partner_id if group else self.env['res.partner']
        for rec in self:
            rec.sudo().message_post(
                body=body,
                partner_ids=partners.ids,
                subtype_xmlid='mail.mt_note',
            )

    def _history_entries(self, internal=False):
        """Fil chronologique du dossier — date, auteur, action (section 44).

        Rendu en lecture seule plutôt qu'avec le chatter portail natif : le
        dossier n'hérite pas de `portal.mixin` (pas de jeton d'accès), et la
        section 44 décrit un journal de traçabilité, pas un espace de
        discussion où le candidat pourrait écrire.

        `internal=False` reprend la définition d'Odoo lui-même de ce qu'un
        utilisateur portail a le droit de voir (`_get_search_domain_share`),
        plutôt que d'en réécrire une variante qui divergerait au premier
        changement de version : les notes internes du personnel restent au
        personnel.

        La création n'a pas de message dédié — l'abonnement du candidat est le
        seul effet de `create()` — mais elle ouvre le fil : elle est reconstruite
        depuis `create_date`, ce qui évite d'inventer un message pour un
        événement que l'enregistrement date déjà.
        """
        self.ensure_one()
        record = self.sudo()
        entries = [{
            'date': record.create_date,
            'author': record.create_uid.name,
            'body': _("Dossier créé"),
        }]

        messages = record.message_ids
        if not internal:
            messages = messages.filtered_domain(
                self.env['mail.message']._get_search_domain_share()
            )
        for message in messages.sorted('id'):
            # Les messages de suivi purs (changement de champ tracé) n'ont pas
            # de corps : les afficher donnerait des lignes vides, alors que
            # chaque transition a déjà son message rédigé.
            if not html2plaintext(message.body or '').strip():
                continue
            entries.append({
                'date': message.date,
                'author': message.author_id.name or message.email_from or _("Système"),
                'body': message.body,
            })
        return entries

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
        records = super().create(vals_list)
        # Un seul abonnement, à la création : le candidat suit son dossier pour
        # toute sa vie. Le refaire à chaque transition dupliquerait l'abonné et
        # ferait repartir des notifications déjà envoyées.
        for record in records:
            if record.partner_id:
                record.sudo().message_subscribe(partner_ids=record.partner_id.ids)
        return records

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
            rec._notify_candidate(_(
                "Votre dossier d'adhésion a bien été transmis au Secrétariat du "
                "GIC OPEX Group. Vous recevrez une notification dès qu'il aura "
                "été examiné."
            ))
            rec._notify_staff('secretariat', _(
                "Nouveau dossier d'adhésion déposé par %s : il attend votre contrôle."
            ) % rec._candidate_label())

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
        document_label = _(" concernant « %s »") % document.name if document else ''
        self._notify_candidate(_(
            "Votre dossier nécessite une correction%(document)s : %(motif)s"
            "%(commentaire)s Connectez-vous à votre espace pour le mettre à jour, "
            "puis renvoyez-le au Secrétariat."
        ) % {
            'document': document_label,
            'motif': motif,
            'commentaire': ' %s' % commentaire if commentaire else '',
        })
        return correction

    def action_resubmit(self):
        """Le candidat renvoie son dossier corrigé : Correction demandée -> En contrôle."""
        for rec in self:
            rec._ensure_state(('correction_requested',), _("La re-soumission du dossier"))
            rec._check_documents_complete()
            rec.correction_ids.filtered(lambda c: not c.resolved).resolved = True
            rec.state = 'control'
            rec._notify_staff('secretariat', _(
                "Le dossier de %s a été corrigé et renvoyé : il attend un nouveau "
                "contrôle."
            ) % rec._candidate_label())

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
            # Un dossier déjà passé par une correction revient devant le Comité :
            # c'est la « nouvelle demande de décision » de la section 43, pas un
            # premier examen.
            already_seen = bool(rec.correction_ids)
            rec.write({
                'state': 'committee',
                'avis_comite': False,
                'commentaire_comite': False,
            })
            if already_seen:
                rec._notify_staff('comite', _(
                    "Le dossier de %s, complété à la suite d'une demande de "
                    "correction, revient devant le Comité d'admission pour décision."
                ) % rec._candidate_label())
            else:
                rec._notify_staff('comite', _(
                    "Le dossier de %s a été validé par le Secrétariat : il attend "
                    "l'examen du Comité d'admission."
                ) % rec._candidate_label())

    def action_reject_control(self):
        """Sortie négative du contrôle (section 15)."""
        for rec in self:
            rec._ensure_state(('control',), _("Le refus au contrôle"))
            rec.state = 'rejected_control'
            rec._notify_candidate(rec._rejection_message())

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

    def _rejection_message(self):
        """Un refus s'annonce sans jargon et sans laisser le candidat sans interlocuteur."""
        self.ensure_one()
        return _(
            "Après examen, votre demande d'adhésion au GIC OPEX Group n'a pas été "
            "retenue. Le Secrétariat reste à votre disposition pour vous en "
            "préciser les motifs."
        )

    def action_send_to_copil(self):
        """Comité d'admission -> Validation COPIL, sur avis favorable."""
        for rec in self:
            rec._ensure_state(('committee',), _("La transmission au COPIL"))
            rec.state = 'copil_pending'
            rec._notify_staff('copil', _(
                "Le Comité d'admission a rendu un avis favorable sur le dossier "
                "de %s : il est prêt pour votre validation."
            ) % rec._candidate_label())

    def action_reject_committee(self):
        for rec in self:
            rec._ensure_state(('committee',), _("Le refus par le comité"))
            rec.state = 'rejected_committee'
            rec._notify_candidate(rec._rejection_message())

    def action_validate_copil(self):
        """validerParCOPIL : Validation COPIL -> Validé COPIL -> Paiement en attente.

        La cotisation est émise dans la foulée : la spécification (section 22)
        enchaîne directement « Adhésion validée » et « Étape suivante :
        Paiement de la cotisation », sans action intermédiaire.
        """
        for rec in self:
            rec._ensure_state(('copil_pending',), _("La validation par le COPIL"))
            rec.state = 'copil_validated'
            subscription = rec.action_create_subscription()
            rec.state = 'payment_pending'
            rec._notify_candidate(_(
                "Bonne nouvelle : votre demande d'adhésion au GIC OPEX Group a "
                "été acceptée."
            ))
            rec._notify_candidate(_(
                "Étape suivante : le règlement de votre cotisation de %(montant)s"
                "%(echeance)s. Depuis votre espace, vous pouvez payer en ligne ou "
                "envoyer une preuve de paiement si vous avez déjà réglé."
            ) % {
                'montant': rec._format_montant(subscription),
                'echeance': _(", à régler avant le %s") % subscription.date_echeance
                            if subscription.date_echeance else '',
            })

    def action_reject_copil(self):
        for rec in self:
            rec._ensure_state(('copil_pending',), _("Le refus par le COPIL"))
            rec.state = 'rejected_copil'
            rec._notify_candidate(rec._rejection_message())

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
        self._notify_staff('secretariat', _(
            "%(candidat)s a déposé une preuve de paiement de %(montant)s pour sa "
            "cotisation : elle attend votre vérification."
        ) % {
            'candidat': self._candidate_label(),
            'montant': format_amount(self.env, montant, subscription.currency_id),
        })
        return payment

    def action_reject_payment(self, motif=False):
        """La preuve déposée est rejetée : le dossier redevient à payer.

        Le candidat peut alors en déposer une nouvelle ; le motif du rejet est
        porté par le paiement rejeté, pas par le dossier, mais il est repris
        dans la notification — sinon le candidat devrait aller le chercher.
        """
        for rec in self:
            rec._ensure_state(('payment_verification',), _("Le rejet du paiement"))
            rec.state = 'payment_pending'
            rec._notify_candidate(_(
                "Votre preuve de paiement n'a pas pu être acceptée%(motif)s. "
                "Vous pouvez en déposer une nouvelle depuis votre espace, ou "
                "régler votre cotisation en ligne."
            ) % {'motif': _(" : %s") % motif if motif else ''})

    def action_renew(self):
        """Renouvellement de l'adhésion pour la période suivante (section 32).

        Le membre actif ne recommence pas son adhésion : ni contrôle du
        Secrétariat, ni Comité, ni COPIL, ni signature. Le dossier reste
        `active` d'un bout à l'autre — seule une nouvelle cotisation est émise,
        par la méthode qui émet déjà celle de l'adhésion initiale. L'historique
        des périodes précédentes est conservé, puisque rien n'est écrasé.
        """
        self.ensure_one()
        if self.state != 'active':
            raise UserError(_(
                "Seule une adhésion active peut être renouvelée. Ce dossier est "
                "actuellement à l'état « %s »."
            ) % self._state_label())
        pending = self._pending_subscription()
        if pending:
            raise UserError(_(
                "Une cotisation est déjà en attente de règlement pour %s : "
                "réglez-la avant d'en émettre une nouvelle."
            ) % self.partner_id.name)

        subscription = self.action_create_subscription()
        self._notify_candidate(_(
            "Votre adhésion au GIC OPEX Group est renouvelée pour la période "
            "suivante. La cotisation de %(montant)s est à régler avant le "
            "%(echeance)s depuis votre espace membre."
        ) % {
            'montant': self._format_montant(subscription),
            'echeance': subscription.date_echeance,
        })
        return subscription

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
            rec._notify_candidate(_(
                "Votre paiement a bien été confirmé. Merci."
            ))
            rec._notify_candidate(_(
                "Il ne reste qu'une étape : signer la charte d'adhésion. Depuis "
                "votre espace, vous pouvez la signer en ligne ou la télécharger, "
                "la signer et la déposer."
            ))

    # ------------------------------------------------------------
    # Signature de la charte et activation
    # ------------------------------------------------------------

    def action_sign_charte_digital(self):
        """Voie A : le candidat signe électroniquement la charte.

        **Simplification assumée pour le POC.** Il ne s'agit pas d'une
        signature cryptographique : aucun certificat n'est émis, aucun condensat
        du document n'est scellé, rien ne prouverait l'intégrité de la charte
        devant un tiers. On enregistre une *confirmation horodatée* — qui a
        cliqué, quand — ce qui suffit à dérouler le processus métier et à le
        démontrer, mais ne vaut pas signature électronique au sens légal. Une
        vraie intégration (Odoo Sign, prestataire externe) remplacerait cette
        méthode sans toucher au reste du parcours : seul le mode change, les
        transitions restent les mêmes.
        """
        for rec in self:
            rec._ensure_state(('signature_pending',), _("La signature de la charte"))
            rec.write({
                'signature_mode': 'digital',
                'signature_date': fields.Date.context_today(rec),
                'charte_motif_rejet': False,
                'state': 'signature_verification',
            })
            rec._notify_staff('secretariat', _(
                "%s a signé la charte d'adhésion en ligne : la signature attend "
                "votre vérification."
            ) % rec._candidate_label())

    def action_submit_charte_document(self, charte_document, filename=False):
        """Voie B : le candidat dépose la charte qu'il a signée à la main."""
        self.ensure_one()
        self._ensure_state(('signature_pending',), _("Le dépôt de la charte signée"))
        if not charte_document:
            raise UserError(_("La charte signée est obligatoire pour cette voie."))
        self.write({
            'signature_mode': 'document',
            'signature_date': fields.Date.context_today(self),
            'charte_document': charte_document,
            'charte_document_filename': filename or False,
            'charte_motif_rejet': False,
            'state': 'signature_verification',
        })
        self._notify_staff('secretariat', _(
            "%s a déposé sa charte d'adhésion signée : elle attend votre "
            "vérification."
        ) % self._candidate_label())

    def action_confirm_signature(self):
        """Le Secrétariat valide la signature : l'adhésion s'active.

        Dernier des deux verrous de la Partie V. Le paiement est structurellement
        acquis à ce stade — on ne parvient à la signature qu'après lui — mais la
        condition est vérifiée explicitement plutôt que supposée : c'est le seul
        endroit où l'adhésion devient effective, et un état forcé à la main dans
        le back-office ne doit pas suffire à contourner l'encaissement.
        """
        for rec in self:
            rec._ensure_state(
                ('signature_verification',), _("La confirmation de la signature"))
            unpaid = rec.subscription_ids.filtered(lambda s: s.state != 'paid')
            if unpaid or not rec.subscription_ids:
                raise UserError(_(
                    "L'adhésion de %s ne peut pas être activée : sa cotisation "
                    "n'est pas soldée. Le paiement et la signature doivent être "
                    "confirmés tous les deux."
                ) % rec.partner_id.name)
            rec._activate_membership()

    def action_reject_signature(self, motif):
        """La signature déposée est refusée : le candidat doit recommencer.

        La signature elle-même est effacée, pas seulement l'état : laisser une
        date et un mode derrière soi ferait croire, sur la page du candidat
        comme dans le back-office, qu'une charte valide est déjà en place.
        """
        self.ensure_one()
        self._ensure_state(('signature_verification',), _("Le rejet de la signature"))
        if not (motif or '').strip():
            raise UserError(_(
                "Indiquez le motif du rejet : c'est ce texte que le candidat "
                "recevra pour redéposer sa charte."
            ))
        self.write({
            'state': 'signature_pending',
            'signature_mode': False,
            'signature_date': False,
            'charte_document': False,
            'charte_document_filename': False,
            'charte_motif_rejet': motif.strip(),
        })
        self._notify_candidate(_(
            "Votre charte signée n'a pas pu être acceptée : %s. Merci de la "
            "signer à nouveau depuis votre espace."
        ) % motif.strip())

    # Informations du dossier reprises sur le contact à l'activation, pour que
    # l'annuaire public puisse les chercher et les afficher. Clé = champ du
    # dossier, valeur = champ du contact ; `site_web` alimente le `website`
    # natif de `res.partner` plutôt qu'un doublon.
    _PUBLIC_PROFILE_FIELDS = {
        'presentation': 'presentation',
        'site_web': 'website',
        'domaines_expertise': 'domaines_expertise',
    }

    def _public_profile_values(self):
        """Instantané publiable du dossier, au format `res.partner.write()`.

        Même logique que `subcategory_id` : le dossier est la candidature, le
        contact est le membre. On recopie à l'activation plutôt que de lier des
        champs calculés — un membre peut déposer d'autres dossiers plus tard
        sans que son profil public change dans son dos.

        Un champ vide n'est pas recopié : il effacerait ce que le contact
        portait déjà.
        """
        self.ensure_one()
        values = {
            partner_field: self[file_field]
            for file_field, partner_field in self._PUBLIC_PROFILE_FIELDS.items()
            if self[file_field]
        }
        if self.certification_ids:
            values['certification_ids'] = [fields.Command.set(self.certification_ids.ids)]
        return values

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
            partner_values.update(rec._public_profile_values())
            rec.partner_id.write(partner_values)
            rec._notify_candidate(_(
                "Félicitations ! Votre adhésion au GIC OPEX Group est maintenant "
                "active. Vous pouvez accéder à votre espace membre et votre "
                "organisation apparaît désormais dans l'annuaire du cluster."
            ))
