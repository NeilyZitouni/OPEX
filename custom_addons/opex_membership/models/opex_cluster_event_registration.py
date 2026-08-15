from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class OpexClusterEventRegistration(models.Model):
    """Inscription d'un membre à un événement ou à une formation du cluster.

    Le nom du modèle est celui fixé par la spécification (`event.registration`),
    mais il sert aussi aux formations : s'inscrire à une formation et participer
    à un événement sont la même chose du point de vue des données — un membre,
    une activité, un état. Un second modèle jumeau n'apporterait qu'une table de
    plus à tenir synchronisée.

    `event_id` et `training_id` sont donc exclusifs : exactement l'un des deux
    est renseigné, ce que garantit la contrainte ci-dessous.
    """

    _name = 'opex.cluster.event.registration'
    _description = "Inscription à une activité du cluster"
    _order = 'date_inscription desc, id desc'

    partner_id = fields.Many2one(
        'res.partner', string="Participant", required=True, ondelete='cascade', index=True)
    event_id = fields.Many2one(
        'opex.cluster.event', string="Événement", ondelete='cascade', index=True)
    training_id = fields.Many2one(
        'opex.cluster.training', string="Formation", ondelete='cascade', index=True)
    state = fields.Selection(
        [
            ('registered', 'Inscrit'),
            ('attended', 'Présent'),
        ],
        string="État",
        default='registered',
        required=True,
    )
    date_inscription = fields.Datetime(
        string="Inscrit le", default=fields.Datetime.now, readonly=True)

    # PostgreSQL autorise plusieurs NULL dans un index unique : la contrainte
    # sur l'événement n'entrave donc pas les inscriptions aux formations, et
    # réciproquement. C'est ce qui empêche, jusque dans la base, qu'un membre
    # soit inscrit deux fois à la même activité.
    _partner_event_uniq = models.Constraint(
        'unique (partner_id, event_id)',
        "Ce participant est déjà inscrit à cet événement.",
    )
    _partner_training_uniq = models.Constraint(
        'unique (partner_id, training_id)',
        "Ce participant est déjà inscrit à cette formation.",
    )

    # `partner_id` figure dans la liste bien qu'il ne soit pas testé : Odoo ne
    # déclenche une contrainte que pour les champs *présents dans les valeurs*
    # de création. Sans lui, une création ne mentionnant ni événement ni
    # formation échappait entièrement à la vérification — or c'est précisément
    # le cas qu'elle doit rattraper. `partner_id` étant obligatoire, il est
    # toujours fourni, et la contrainte s'exécute donc systématiquement.
    @api.constrains('partner_id', 'event_id', 'training_id')
    def _check_single_activity(self):
        for record in self:
            if bool(record.event_id) == bool(record.training_id):
                raise ValidationError(_(
                    "Une inscription porte soit sur un événement, soit sur une "
                    "formation — jamais sur les deux ni sur aucun des deux."
                ))

    @api.depends('partner_id', 'event_id', 'training_id')
    def _compute_display_name(self):
        for record in self:
            activity = record.event_id.name or record.training_id.name or ''
            record.display_name = '%s — %s' % (record.partner_id.name, activity)

    @api.model
    def _existing_registration(self, partner, event=None, training=None):
        """Inscription déjà enregistrée pour ce couple participant / activité."""
        domain = [('partner_id', '=', partner.id)]
        domain.append(('event_id', '=', event.id if event else False))
        domain.append(('training_id', '=', training.id if training else False))
        return self.search(domain, limit=1)

    @api.model
    def _register_participant(self, partner, event=None, training=None):
        """Crée l'inscription, ou renvoie celle qui existe déjà.

        Idempotent volontairement : cliquer deux fois sur « Participer » ne doit
        ni échouer ni produire un doublon.

        Surtout pas nommée `_register` : `BaseModel._register` est un attribut
        booléen d'Odoo (visibilité au registre). Une méthode de ce nom ne
        remplace pas l'attribut, elle est masquée par lui — l'appel se solde
        alors par « 'bool' object is not callable ».
        """
        existing = self._existing_registration(partner, event=event, training=training)
        if existing:
            return existing
        return self.create({
            'partner_id': partner.id,
            'event_id': event.id if event else False,
            'training_id': training.id if training else False,
        })
