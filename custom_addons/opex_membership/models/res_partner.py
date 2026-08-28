from odoo import _, fields, models
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
    # Entrée « Devenir membre » du menu principal
    # ------------------------------------------------------------

    def opex_can_apply_membership(self):
        """Ce contact a-t-il encore quelque chose à faire de « Devenir membre » ?

        Faux dès qu'**un seul** de ses dossiers est engagé dans le parcours de
        validation. La question se pose sur l'ensemble des dossiers du contact,
        pas sur le dernier créé : un candidat qui en a déjà deux par accident
        doit voir l'entrée disparaître au premier engagé, pas selon l'ordre de
        création.

        Un brouillon ne compte pas : `/my/membership/new` le retrouve et le
        reprend, l'entrée reste donc utile. Un dossier refusé non plus — il
        ferme un parcours, il n'interdit pas d'en ouvrir un autre.

        Ce booléen ne décide que d'un affichage. Ce qui interdit réellement le
        doublon, c'est `opex.membership.file._check_no_engaged_file()`, appelé
        au `create()` — et c'est lui que cette méthode interroge, pour que le
        menu ne puisse pas promettre autre chose que ce que le serveur accepte.
        """
        self.ensure_one()
        return not self.env['opex.membership.file']._engaged_file(self)

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

    def _opex_notification_addressed_messages(self):
        """Messages dont ce contact est **destinataire explicite**.

        Seconde source de la cloche, et la seule qui laisse passer des notes
        internes. Elle existe parce que le portail ne sert pas que des
        porteurs : l'expert, l'évaluateur et l'acteur financier sont des
        comptes **portail**, ils sont notifiés en `mt_note` — c'est correct,
        un `mt_comment` partirait aussi aux followers, dont le porteur — et
        la première source les écarte donc systématiquement. Résultat avant
        ce correctif : des acteurs centraux du parcours étaient notifiés et ne
        voyaient rien nulle part.

        ⚠ **Ce que cette source n'ouvre pas.** Le critère est `partner_ids`,
        c'est-à-dire les destinataires **passés explicitement** à
        `message_post()`. Vérifié sur les données du 28/08 : une note adressée
        au Secrétariat sur le projet d'un porteur porte `partner_ids = [3, 15]`
        — le porteur, pourtant **follower** du projet, n'y figure pas. Les
        followers sont notifiés par un autre chemin et ne sont jamais inscrits
        dans ce champ.

        Autrement dit : on ne voit que ce qui nous a été adressé. Un porteur ne
        gagne l'accès à aucune note de coordination interne, **même sur son
        propre dossier** — c'est la propriété à ne jamais casser, et le test
        d'étanchéité porte dessus.

        Corollaire assumé : un message adressé à quelqu'un sur un
        enregistrement qu'il ne possède pas devient visible dans sa cloche.
        C'est précisément l'effet recherché — l'expert doit apprendre qu'un
        livrable l'attend sur un dossier qui n'est pas le sien.
        """
        self.ensure_one()
        return self.env['mail.message'].sudo().search(
            [('partner_ids', 'in', self.id)])

    def _opex_notification_messages(self):
        """Messages visibles par ce contact : deux sources, réunies.

        1. **Ses propres enregistrements** — filtrés par le
           `mail.message._get_search_domain_share()` d'Odoo, exactement comme
           l'historique du dossier (`opex.membership.file._history_entries`).
           Les notes internes en sont écartées, et les deux vues ne divergent
           pas : une note qu'on apprend à masquer dans l'historique ne
           réapparaît pas dans la cloche.
        2. **Ce qui lui est explicitement adressé** —
           `_opex_notification_addressed_messages()`, notes comprises, y
           compris sur des enregistrements qui ne sont pas les siens.

        ⚠ La règle n'est donc plus *identique* à celle de l'historique, elle la
        **contient**. La différence tient en une phrase : la cloche montre en
        plus ce qui vous a été adressé nommément. Rien d'autre n'a bougé — la
        source 1 conserve son filtre de partage et sa double vérification
        d'appartenance.
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

        # ⚠ L'union vient **après** les filtres de la source 1, jamais avant :
        # les appliquer à la source 2 lui retirerait précisément ce qu'elle
        # apporte — les notes adressées.
        messages |= self._opex_notification_addressed_messages()

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

    # ------------------------------------------------------------
    # Tableau de bord du membre (section 41)
    # ------------------------------------------------------------

    def _opex_member_dashboard(self):
        """Synthèse de l'espace membre, recalculée à chaque affichage.

        Aucun compteur n'est stocké : tout est compté à la demande sur les
        modèles existants. Un agrégat mémorisé se serait décorrélé du réel dès
        la première transition de dossier ou le premier paiement — et un
        tableau de bord faux est pire qu'absent.

        Les actualités du cluster ne sont servies qu'aux membres actifs, par
        cohérence avec la règle d'accès des pages Vie du Cluster : le tableau
        de bord ne doit pas devenir une porte dérobée vers ce contenu.
        """
        self.ensure_one()
        membership_file = self.env['opex.membership.file'].sudo().search(
            [('partner_id', '=', self.id)], order='id desc', limit=1)

        Subscription = self.env['opex.subscription'].sudo()
        # Cotisation « en cours » : celle qui reste à régler, la plus proche de
        # son échéance ; à défaut, la dernière connue, pour afficher « payée ».
        subscription = Subscription.search(
            [('partner_id', '=', self.id), ('state', 'in', ('waiting', 'late'))],
            order='date_echeance asc, id asc', limit=1)
        if not subscription:
            subscription = Subscription.search(
                [('partner_id', '=', self.id)],
                order='date_echeance desc, id desc', limit=1)

        return {
            'membership_file': membership_file,
            'subscription': subscription,
            'document_count': self.env['opex.membership.document'].sudo().search_count(
                [('membership_file_id.partner_id', '=', self.id)]),
            'upcoming_activities': self._opex_upcoming_activities(),
            'latest_news': self._opex_latest_news(),
        }

    def _opex_upcoming_activities(self, limit=5):
        """Événements et formations à venir auxquels ce contact est inscrit.

        Les deux tiennent dans le même modèle d'inscription (décision de la
        première moitié de l'Extension 16) : une seule lecture suffit, il n'y a
        pas deux tables à interroger.
        """
        self.ensure_one()
        now = fields.Datetime.now()
        registrations = self.env['opex.cluster.event.registration'].sudo().search(
            [('partner_id', '=', self.id)])

        activities = []
        for registration in registrations:
            event = registration.event_id
            training = registration.training_id
            if event and event.date_debut and event.date_debut >= now:
                activities.append({
                    'name': event.name, 'date': event.date_debut,
                    'kind': _("Événement"), 'lieu': event.lieu,
                })
            elif training and training.date and training.date >= now:
                activities.append({
                    'name': training.name, 'date': training.date,
                    'kind': _("Formation"), 'lieu': False,
                })
        activities.sort(key=lambda activity: activity['date'])
        return activities[:limit]

    def _opex_latest_news(self, limit=3):
        """Dernières actualités publiées, réservées aux membres actifs."""
        self.ensure_one()
        News = self.env['opex.cluster.news'].sudo()
        if not self.is_member:
            return News.browse()
        return News.search(News._portal_domain(), limit=limit)

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
