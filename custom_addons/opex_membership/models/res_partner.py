from odoo import fields, models
from odoo.tools import html2plaintext


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_member = fields.Boolean(string="Est membre du cluster")
    subcategory_id = fields.Many2one(
        'opex.membership.subcategory',
        string="Sous-catégorie de membre",
        ondelete='restrict',
    )
    # Surtout pas `category_id` ici : sur `res.partner`, ce nom est déjà celui
    # des étiquettes natives (Many2many vers `res.partner.category`). La
    # catégorie d'adhésion se lit via `subcategory_id.category_id`.
    membership_category_id = fields.Many2one(
        'opex.membership.category',
        string="Catégorie d'adhésion",
        related='subcategory_id.category_id',
        store=True,
    )
    secteur_activite = fields.Char(string="Secteur d'activité")
    wilaya = fields.Char(string="Wilaya")
    # Informations publiables, recopiées depuis le dossier au moment de
    # l'activation (cf. `opex.membership.file._activate_membership`). Le
    # dossier est la candidature, le contact est le membre : l'annuaire
    # interroge le contact, jamais les dossiers.
    # Pas de champ « site web » ici : `res.partner.website` existe déjà en
    # natif, c'est lui qu'on renseigne.
    presentation = fields.Text(string="Présentation publique")
    domaines_expertise = fields.Text(string="Domaines d'expertise")
    certification_ids = fields.Many2many('opex.certification', string="Certifications")
    date_adhesion = fields.Date(string="Date d'adhésion")
    membership_file_ids = fields.One2many(
        'opex.membership.file', 'partner_id', string="Dossiers d'adhésion"
    )
    subscription_ids = fields.One2many(
        'opex.subscription', 'partner_id', string="Cotisations"
    )
    is_published_directory = fields.Boolean(string="Publié dans l'annuaire public")
    event_ids = fields.Many2many(
        'opex.cluster.event', 'event_partner_rel', 'partner_id', 'event_id',
        string="Événements",
    )

    notification_last_seen = fields.Datetime(
        string="Notifications consultées le",
        help="Horodatage de la dernière consultation de la cloche par ce contact ; "
             "tout message postérieur est compté comme non lu.",
    )

    # ------------------------------------------------------------
    # Cloche de notification du portail candidat
    # ------------------------------------------------------------

    def _opex_owned_record_ids(self):
        """Enregistrements de ce contact susceptibles de porter des notifications.

        Résolus par une recherche serveur sur `partner_id`, jamais depuis un
        paramètre de requête : c'est cette table qui fait autorité pour décider
        quels messages ce contact a le droit de voir.
        """
        self.ensure_one()
        return {
            'opex.membership.file': self.env['opex.membership.file'].sudo().search(
                [('partner_id', '=', self.id)]).ids,
            'opex.subscription': self.env['opex.subscription'].sudo().search(
                [('partner_id', '=', self.id)]).ids,
        }

    def _opex_notification_messages(self):
        """Messages visibles par ce contact sur ses propres enregistrements.

        La règle de visibilité est *exactement* celle de l'historique du dossier
        (`opex.membership.file._history_entries`) : le même
        `mail.message._get_search_domain_share()` d'Odoo, qui écarte les notes
        internes. Les deux vues ne doivent jamais diverger — une note qu'on
        vient d'apprendre à masquer dans l'historique ne doit pas réapparaître
        dans la cloche. D'où l'appel commun plutôt qu'un filtre réécrit ici.
        """
        self.ensure_one()
        Message = self.env['mail.message'].sudo()
        owned = self._opex_owned_record_ids()

        messages = Message.browse()
        for model, record_ids in owned.items():
            if record_ids:
                messages |= Message.search(
                    [('model', '=', model), ('res_id', 'in', record_ids)])

        messages = messages.filtered_domain(Message._get_search_domain_share())

        # Deuxième passage d'appartenance, sur la donnée déjà chargée : le
        # domaine de recherche a beau être construit ici, on ne s'y fie pas
        # seul. Un message dont le couple (modèle, id) n'est pas dans la table
        # des enregistrements du contact est écarté, quoi qu'il arrive en amont.
        allowed = {
            (model, record_id)
            for model, record_ids in owned.items()
            for record_id in record_ids
        }
        messages = messages.filtered(lambda m: (m.model, m.res_id) in allowed)

        # Les messages de suivi purs n'ont pas de corps : ils encombreraient la
        # liste sans rien dire, comme dans l'historique.
        messages = messages.filtered(lambda m: html2plaintext(m.body or '').strip())
        return messages.sorted(lambda m: (m.date, m.id), reverse=True)

    def _opex_notification_url(self, message):
        """Lien vers l'enregistrement concerné par le message.

        Une cotisation n'a pas encore de page portail dédiée (Extension 15) :
        on renvoie vers le dossier qui l'a émise, seul écran où le candidat la
        voit aujourd'hui.
        """
        self.ensure_one()
        if message.model == 'opex.membership.file':
            return '/my/membership/%s' % message.res_id
        if message.model == 'opex.subscription':
            subscription = self.env['opex.subscription'].sudo().browse(message.res_id)
            if subscription.membership_file_id:
                return '/my/membership/%s' % subscription.membership_file_id.id
        return '/my'

    def _opex_notification_entries(self, limit=None):
        """Notifications prêtes à afficher : message, lien, caractère non lu."""
        self.ensure_one()
        last_seen = self.sudo().notification_last_seen
        entries = []
        for message in self._opex_notification_messages():
            entries.append({
                'message': message,
                'url': self._opex_notification_url(message),
                'is_new': bool(message.date and (not last_seen or message.date > last_seen)),
            })
            if limit and len(entries) >= limit:
                break
        return entries

    def _opex_notification_count(self):
        """Nombre de messages postés depuis la dernière consultation.

        Appelé au rendu de chaque page du portail : pas de temps réel, le
        compteur se rafraîchit au chargement, ce qui suffit à la spécification.
        """
        self.ensure_one()
        last_seen = self.sudo().notification_last_seen
        if not last_seen:
            return len(self._opex_notification_messages())
        return len(self._opex_notification_messages().filtered(
            lambda m: m.date and m.date > last_seen))

    def _opex_mark_notifications_seen(self):
        self.ensure_one()
        self.sudo().notification_last_seen = fields.Datetime.now()

    def get_public_profile(self):
        """Champs exposables dans l'annuaire public des membres.

        Source unique de vérité de ce qui est public : la liste de l'annuaire
        comme la page de profil dédiée passent par ici. Ajouter une clé ici
        l'expose sur les deux ; en définir une seconde liste ailleurs ferait
        diverger les deux écrans au premier oubli.

        Email et téléphone restent volontairement absents : un membre publié
        accepte de figurer à l'annuaire, pas de voir ses coordonnées directes
        exposées à un visiteur anonyme.
        """
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'secteur_activite': self.secteur_activite,
            'wilaya': self.wilaya,
            'subcategory_id': self.subcategory_id.display_name if self.subcategory_id else False,
            'presentation': self.presentation,
            'website': self.website,
            'domaines_expertise': self.domaines_expertise,
            # Converties en libellés : un recordset passé à un gabarit public
            # donnerait accès à tout le modèle depuis la vue.
            'certifications': self.certification_ids.mapped('name'),
        }
