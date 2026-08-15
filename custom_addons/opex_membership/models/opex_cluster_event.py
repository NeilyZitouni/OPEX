from odoo import api, fields, models


class OpexClusterEvent(models.Model):
    _name = 'opex.cluster.event'
    _description = 'Événement du cluster'
    _order = 'date_debut desc'

    name = fields.Char(string="Titre", required=True)
    date_debut = fields.Datetime(string="Date de début", required=True)
    date_fin = fields.Datetime(string="Date de fin")
    lieu = fields.Char(string="Lieu")
    type = fields.Selection(
        [
            ('training', 'Formation'),
            ('general_assembly', 'Assemblée générale'),
            ('forum', 'Forum'),
            ('meeting', 'Réunion'),
        ],
        string="Type",
        required=True,
    )
    partner_ids = fields.Many2many(
        'res.partner', 'event_partner_rel', 'event_id', 'partner_id',
        string="Participants",
    )
    registration_ids = fields.One2many(
        'opex.cluster.event.registration', 'event_id', string="Inscriptions")
    calendar_event_id = fields.Many2one(
        'calendar.event',
        string="Événement agenda",
        readonly=True,
        copy=False,
        # Supprimer l'entrée d'agenda ne doit pas emporter l'événement métier :
        # le lien se dénoue, et une prochaine modification en recréera une.
        ondelete='set null',
    )

    # Champs dont la modification doit se répercuter sur l'agenda. Volontairement
    # sans `calendar_event_id` : c'est ce qui empêche l'écriture du lien, faite
    # juste après la création de l'entrée, de relancer la synchronisation.
    _SYNCED_FIELDS = ('name', 'date_debut', 'date_fin', 'lieu', 'partner_ids')

    def action_register(self, partner):
        """Enregistre la participation d'un membre à cet événement.

        Pas de limite de places sur un événement du cluster — c'est propre aux
        formations. L'inscription reste idempotente.
        """
        self.ensure_one()
        return self.env['opex.cluster.event.registration']._register_participant(
            partner, event=self)

    def _calendar_event_values(self):
        """Projection de l'événement métier vers l'agenda natif.

        `stop` est obligatoire côté `calendar.event` et ne peut pas précéder
        `start` : une date de fin absente devient donc la date de début, plutôt
        que de faire échouer la synchronisation sur une contrainte.
        """
        self.ensure_one()
        return {
            'name': self.name,
            'start': self.date_debut,
            'stop': self.date_fin or self.date_debut,
            'location': self.lieu or False,
            'partner_ids': [fields.Command.set(self.partner_ids.ids)],
        }

    def _sync_calendar_event(self):
        """Crée ou met à jour l'entrée d'agenda liée à chaque événement.

        Un seul `calendar.event` par événement du cluster : quand le lien
        existe déjà, on écrit dedans au lieu d'en créer un second — c'est ce
        qui évite les doublons quand une date est corrigée.

        `no_mail_to_attendees` : cette entrée est un miroir destiné à
        l'affichage dans l'agenda, pas une convocation. Les participants ont
        déjà été inscrits côté cluster ; leur envoyer en plus une invitation
        Odoo à chaque modification serait une surprise désagréable. Le noyau
        Odoo utilise la même clé pour ses événements générés.
        """
        CalendarEvent = self.env['calendar.event'].sudo().with_context(
            no_mail_to_attendees=True, mail_create_nolog=True)
        for rec in self:
            if not rec.date_debut:
                continue
            values = rec._calendar_event_values()
            if rec.calendar_event_id:
                CalendarEvent.browse(rec.calendar_event_id.id).write(values)
            else:
                rec.calendar_event_id = CalendarEvent.create(values).id

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_calendar_event()
        return records

    def write(self, vals):
        res = super().write(vals)
        if any(field in vals for field in self._SYNCED_FIELDS):
            self._sync_calendar_event()
        return res

    def unlink(self):
        """L'entrée d'agenda disparaît avec l'événement qu'elle reflétait.

        Sans cela, l'agenda garderait des réunions fantômes que plus rien ne
        permet de rattacher à un événement du cluster.
        """
        calendar_events = self.calendar_event_id.sudo()
        res = super().unlink()
        calendar_events.unlink()
        return res
