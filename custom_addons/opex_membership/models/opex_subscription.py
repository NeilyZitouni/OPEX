from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_amount


class OpexSubscription(models.Model):
    _name = 'opex.subscription'
    _description = 'Cotisation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_echeance desc'

    partner_id = fields.Many2one(
        'res.partner',
        string="Membre",
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string="Devise",
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    montant = fields.Monetary(string="Montant", required=True)
    date_emission = fields.Date(string="Date d'émission", default=fields.Date.context_today)
    date_echeance = fields.Date(string="Date d'échéance")
    state = fields.Selection(
        [
            ('waiting', 'En attente'),
            ('paid', 'Payée'),
            ('late', 'En retard'),
            ('cancelled', 'Annulée'),
        ],
        string="État",
        default='waiting',
        required=True,
        tracking=True,
    )
    payment_ids = fields.One2many('opex.payment', 'subscription_id', string="Paiements")
    date_relance_echeance = fields.Date(
        string="Relance avant échéance envoyée le",
        readonly=True,
        help="Empêche le cron de renvoyer chaque jour la même relance "
             "pré-échéance ; le rappel de retard, lui, ne part qu'une fois "
             "puisque la cotisation change alors d'état.",
    )
    membership_file_id = fields.Many2one(
        'opex.membership.file',
        string="Dossier d'adhésion",
        readonly=True,
        ondelete='set null',
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string="Devis/Commande de cotisation",
        readonly=True,
    )

    def write(self, vals):
        res = super().write(vals)
        if vals.get('state') == 'paid':
            self._trigger_membership_activation()
        return res

    # États d'un dossier qu'une cotisation soldée fait avancer vers la signature
    # de la charte. Le règlement ne suffit plus à activer l'adhésion : depuis
    # l'alignement sur la spécification UX (Partie V), l'activation exige aussi
    # la charte signée.
    _PAYABLE_FILE_STATES = ('payment_pending', 'payment_verification')

    def _trigger_membership_activation(self):
        """Une cotisation soldée fait passer le dossier à la signature de la charte.

        Vaut quelle que soit l'origine du paiement : facture Odoo réglée
        (sale.order) ou paiement hors Odoo saisi via opex.payment.
        """
        for rec in self:
            membership_file = rec.membership_file_id
            if not membership_file:
                membership_file = self.env['opex.membership.file'].search([
                    ('partner_id', '=', rec.partner_id.id),
                    ('state', 'in', self._PAYABLE_FILE_STATES),
                ], limit=1)
            membership_file.filtered(
                lambda f: f.state in self._PAYABLE_FILE_STATES
            ).action_confirm_payment()

    @api.model
    def _dashboard_counts(self):
        """Cotisations par état, comptées en direct (section 42)."""
        counts = dict(self._read_group([], ['state'], ['__count']))
        labels = dict(self._fields['state'].selection)
        return [
            {'state': state, 'label': label, 'count': counts.get(state, 0)}
            for state, label in labels.items()
        ]

    def _state_label(self):
        self.ensure_one()
        return dict(self._fields['state'].selection).get(self.state)

    # Nombre de jours avant l'échéance où part la première relance. Réglable
    # sans toucher au code, comme le « X jours » de la spécification.
    _REMINDER_DAYS_PARAM = 'opex_membership.relance_jours_avant'
    _REMINDER_DAYS_DEFAULT = 15

    @api.model
    def _reminder_days_before(self):
        raw = self.env['ir.config_parameter'].sudo().get_param(
            self._REMINDER_DAYS_PARAM, self._REMINDER_DAYS_DEFAULT)
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return self._REMINDER_DAYS_DEFAULT

    @api.model
    def _cron_process_reminders(self):
        """Relances automatiques des cotisations (section 30).

        Deux passes distinctes, et une seule notification par situation :

        - avant l'échéance, un rappel au membre ; `date_relance_echeance` sert
          de garde, sans quoi le cron répéterait le même message chaque jour de
          la fenêtre ;
        - après l'échéance, la cotisation passe En retard *puis* la relance
          existante part telle quelle. Aucune garde n'est nécessaire ici : le
          changement d'état sort la cotisation du domaine, elle ne sera pas
          reprise au passage suivant.

        `action_generate_reminder()` n'est pas modifiée — elle exige déjà
        l'état En retard, ce que cette méthode lui garantit avant de l'appeler.
        """
        today = fields.Date.context_today(self)
        horizon = today + timedelta(days=self._reminder_days_before())

        upcoming = self.search([
            ('state', '=', 'waiting'),
            ('date_echeance', '!=', False),
            ('date_echeance', '>=', today),
            ('date_echeance', '<=', horizon),
            ('date_relance_echeance', '=', False),
        ])
        upcoming.action_notify_upcoming_due()

        overdue = self.search([
            ('state', '=', 'waiting'),
            ('date_echeance', '!=', False),
            ('date_echeance', '<', today),
        ])
        if overdue:
            overdue.write({'state': 'late'})
            overdue.action_generate_reminder()

        return {'relances_echeance': len(upcoming), 'passees_en_retard': len(overdue)}

    def action_notify_upcoming_due(self):
        """Rappel amont : la cotisation arrive à échéance, elle n'est pas en retard.

        Message distinct de `action_generate_reminder()` — annoncer un retard
        qui n'existe pas encore serait faux, et pousserait le membre à croire
        qu'il a manqué quelque chose.
        """
        for rec in self:
            rec.sudo().message_post(
                body=_(
                    "Votre cotisation de %(montant)s arrive à échéance le "
                    "%(echeance)s. Vous pouvez la régulariser dès maintenant "
                    "depuis votre espace membre."
                ) % {
                    'montant': format_amount(self.env, rec.montant, rec.currency_id),
                    'echeance': rec.date_echeance,
                },
                partner_ids=rec.partner_id.ids,
                subtype_xmlid='mail.mt_comment',
            )
            rec.sudo().date_relance_echeance = fields.Date.context_today(rec)

    def _portal_status(self):
        """État lisible par le membre (section 29), jamais le code interne."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        if self.state == 'paid':
            return {'icon': '', 'label': _("Payée"), 'css': 'text-bg-success'}
        if self.state == 'cancelled':
            return {'icon': '—', 'label': _("Annulée"), 'css': 'text-bg-secondary'}
        if self.state == 'late':
            return {'icon': '', 'label': _("En retard"), 'css': 'text-bg-danger'}
        if self.date_echeance and self.date_echeance > today:
            return {'icon': '', 'label': _("À venir"), 'css': 'text-bg-info'}
        return {'icon': '', 'label': _("À renouveler"), 'css': 'text-bg-warning'}

    def _portal_year(self):
        """Année de rattachement de la cotisation, pour l'historique annuel."""
        self.ensure_one()
        reference = self.date_echeance or self.date_emission
        return reference.year if reference else False

    def action_generate_reminder(self):
        """genererRelances : envoie une relance si la cotisation est En retard.

        Deux destinataires, deux textes : le membre reçoit une relance qui lui
        dit quoi faire, le Secrétariat un signalement de retard (section 43).
        Le message précédent décrivait l'envoi au lieu d'être l'envoi — il ne
        partait à personne.
        """
        secretariat = self.env.ref(
            'opex_membership.group_secretariat', raise_if_not_found=False)
        staff_partners = (
            secretariat.sudo().all_user_ids.partner_id
            if secretariat else self.env['res.partner']
        )
        for rec in self:
            if rec.state != 'late':
                raise UserError(_(
                    "Une relance ne peut être envoyée que pour une cotisation "
                    "En retard. La cotisation de %s est actuellement à l'état « %s »."
                ) % (rec.partner_id.name, rec._state_label()))
            montant = format_amount(self.env, rec.montant, rec.currency_id)
            rec.sudo().message_post(
                body=_(
                    "Votre cotisation de %(montant)s est en retard (échéance : "
                    "%(echeance)s). Merci de la régulariser depuis votre espace "
                    "membre."
                ) % {'montant': montant, 'echeance': rec.date_echeance},
                partner_ids=rec.partner_id.ids,
                subtype_xmlid='mail.mt_comment',
            )
            rec.sudo().message_post(
                body=_(
                    "La cotisation de %(membre)s (%(montant)s, échéance "
                    "%(echeance)s) est en retard : une relance vient de lui être "
                    "envoyée."
                ) % {
                    'membre': rec.partner_id.name,
                    'montant': montant,
                    'echeance': rec.date_echeance,
                },
                partner_ids=staff_partners.ids,
                # Note interne : le suivi du retard regarde le Secrétariat, pas
                # le membre, qui a déjà reçu sa relance juste au-dessus.
                subtype_xmlid='mail.mt_note',
            )

    def _amount_paid(self):
        """Total réellement encaissé : seuls les paiements confirmés comptent.

        Une preuve déposée par le candidat est « à vérifier » tant que le
        Secrétariat ne l'a pas contrôlée ; la compter ici solderait la
        cotisation sur la seule déclaration du candidat.
        """
        self.ensure_one()
        return sum(
            self.payment_ids.filtered(lambda p: p.state == 'paid').mapped('montant')
        )

    def _reconcile_payments(self):
        """Solde la cotisation dès que les paiements confirmés la couvrent."""
        for rec in self:
            if rec.state in ('paid', 'cancelled'):
                continue
            if rec._amount_paid() >= rec.montant:
                rec.state = 'paid'

    def action_register_payment(self, montant=None, mode_paiement='transfer',
                                 reference_transaction=False, date_paiement=None):
        """enregistrerPaiement : crée un opex.payment lié, passe l'état à Payée si le montant couvre la cotisation."""
        for rec in self:
            if rec.state == 'cancelled':
                raise UserError(_(
                    "Impossible d'enregistrer un paiement : la cotisation de "
                    "%s est annulée."
                ) % rec.partner_id.name)
            if rec.state == 'paid':
                raise UserError(_(
                    "La cotisation de %s est déjà soldée."
                ) % rec.partner_id.name)
            amount = montant if montant is not None else (rec.montant - rec._amount_paid())
            if amount <= 0:
                raise UserError(_("Le montant du paiement doit être positif."))
            self.env['opex.payment'].create({
                'subscription_id': rec.id,
                'montant': amount,
                'date_paiement': date_paiement or fields.Datetime.now(),
                'reference_transaction': reference_transaction,
                'mode_paiement': mode_paiement,
                # Saisie par le Secrétariat : l'encaissement est constaté, pas
                # déclaré — il n'y a rien à vérifier ensuite.
                'state': 'paid',
            })
            rec._reconcile_payments()
