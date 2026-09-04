from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

#: Non traduit, et volontairement : la valeur sert de **sentinelle** dans
#: `create()`. Traduite, elle ne se comparerait plus à elle-même d'une langue à
#: l'autre, et la séquence cesserait de s'appliquer sans que rien ne le dise.
NEW_REFERENCE = "Nouveau"


class MissionProgressReport(models.Model):
    """Le point d'avancement de l'intervenant — §21.

    > « Pendant la mission, le responsable et le client peuvent suivre :
    >   progression, étapes, livrables, échéances, commentaires, documents,
    >   réunions, problèmes éventuels. »

    **Aucun champ d'état, et ici c'est presque une évidence** : un compte
    rendu ne s'avance pas, il est écrit puis il est lu. Ce qui avance, c'est la
    mission ; ce qui progresse, c'est le pourcentage que ce compte rendu
    déclare.

    Un compte rendu **n'est jamais modifié après coup** : au point suivant, on
    en écrit un nouveau. C'est ce qui rend la série lisible — dire « au 12,
    j'étais à 40 % » n'a de sens que si le 12 n'a pas été réécrit le 19.
    """

    _name = 'opex.mission.progress.report'
    _description = "Point d'avancement d'une mission"
    _inherit = ['mail.thread']
    _order = 'mission_id, date desc, id desc'

    mission_id = fields.Many2one(
        'opex.mission.request',
        string="Mission",
        required=True,
        ondelete='cascade',
        index=True,
    )
    assignment_id = fields.Many2one(
        'opex.mission.assignment', string="Affectation", ondelete='set null')
    partner_id = fields.Many2one(
        'res.partner', string="Rédigé par", required=True, index=True,
        default=lambda self: self.env.user.partner_id.id)

    date = fields.Date(
        string="Date du point", required=True,
        default=fields.Date.context_today)
    periode_debut = fields.Date(string="Période couverte — début")
    periode_fin = fields.Date(string="Période couverte — fin")

    #: §21 — « temps passé »
    temps_passe_jours = fields.Float(
        string="Temps passé (jours)",
        digits=(6, 2),
        help="Sur la période couverte par ce point, pas depuis le début.",
    )
    #: §21 — « progression »
    avancement = fields.Integer(
        string="Avancement (%)",
        help="Estimation de l'intervenant à la date du point.",
    )

    travaux_realises = fields.Text(string="Travaux réalisés")
    #: §21 — « problèmes éventuels »
    problemes = fields.Text(
        string="Problèmes rencontrés",
        help="Un problème signalé ici n'ouvre pas d'incident : c'est le "
             "responsable qui décide d'en ouvrir un (§26).",
    )
    #: §21 — « prochaine étape »
    prochaine_etape = fields.Text(string="Prochaine étape")

    deliverable_ids = fields.Many2many(
        'opex.mission.deliverable',
        'mission_report_deliverable_rel', 'report_id', 'deliverable_id',
        string="Livrables concernés",
    )

    @api.depends('mission_id', 'date')
    def _compute_display_name(self):
        for report in self:
            report.display_name = "%s — %s" % (
                report.mission_id.name or '', report.date or '')

    @api.constrains('avancement')
    def _check_avancement(self):
        for report in self:
            if not 0 <= report.avancement <= 100:
                raise ValidationError(_(
                    "L'avancement se déclare entre 0 et 100 %%, pas %s.")
                    % report.avancement)


class MissionIncident(models.Model):
    """Un incident de mission — §26.

    CE MODÈLE PORTE UN CHAMP D'ÉTAT, ET C'EST ASSUMÉ

    Le Schéma 10 du §26 donne le cycle en entier :

        Ouvert → En traitement → Résolu

    Linéaire. Pas de chemin de refus, pas de boucle, pas de condition, pas de
    rôle qui change d'une case à l'autre. C'est **exactement** la ligne de
    partage posée par le CLAUDE.md du moteur à propos de `roadmap.phase` :

    > « Une phase est une case à trois positions, sans acteur, sans condition,
    >   sans notification, sans chemin de refus et sans historique. Lui donner
    >   une instance de workflow serait de la cérémonie pour un compteur
    >   d'avancement. Un livrable, lui, a un valideur, un chemin de rejet, des
    >   versions successives et des notifications à chaque passage — c'est un
    >   processus. »

    Le livrable de ce module est dans la seconde catégorie et a sa définition.
    L'incident est dans la première. Le champ s'appelle `traitement` et non
    `state` — pas pour esquiver la règle, mais parce que `state` est un nom
    pris par l'API interne d'Odoo (règle 1). C'est bien un champ d'état, il est
    nommé comme tel dans son libellé, et le critère qui le rend légitime est
    écrit ci-dessus plutôt que découvert en soutenance.

    Si le cluster demande un jour un circuit de validation d'incident — un
    responsable qui refuse la clôture, un client qui conteste —, il change de
    catégorie et devient une quatrième définition. Rien à réécrire : le modèle
    hérite déjà de `mail.thread`, et le mixin est une ligne.
    """

    _name = 'opex.mission.incident'
    _description = "Incident de mission"
    _inherit = ['mail.thread']
    _order = 'mission_id, priorite desc, date_ouverture desc, id desc'

    name = fields.Char(
        string="Référence", required=True, copy=False, readonly=True,
        default=NEW_REFERENCE, index=True)
    mission_id = fields.Many2one(
        'opex.mission.request',
        string="Mission",
        required=True,
        ondelete='cascade',
        index=True,
    )

    #: Les cinq types du §26, à la lettre.
    incident_type = fields.Selection(
        [
            ('retard', "Retard"),
            ('blocage', "Blocage"),
            ('disponibilite', "Problème de disponibilité"),
            ('livrable', "Problème de livrable"),
            ('contractuel', "Problème contractuel"),
        ],
        string="Type",
        required=True,
        default='retard',
    )
    priorite = fields.Selection(
        [('0', "Basse"), ('1', "Moyenne"), ('2', "Haute")],
        string="Priorité",
        default='1',
        required=True,
    )
    description = fields.Text(string="Description", required=True)

    #: Le Schéma 10, et rien de plus. Voir la docstring de la classe.
    traitement = fields.Selection(
        [
            ('ouvert', "Ouvert"),
            ('en_traitement', "En traitement"),
            ('resolu', "Résolu"),
        ],
        string="État du traitement",
        default='ouvert',
        required=True,
        tracking=True,
    )
    resolution = fields.Text(string="Résolution apportée")

    deliverable_id = fields.Many2one(
        'opex.mission.deliverable', string="Livrable concerné",
        ondelete='set null')
    reporter_id = fields.Many2one(
        'res.partner', string="Signalé par", required=True,
        default=lambda self: self.env.user.partner_id.id)
    assignee_id = fields.Many2one(
        'res.users', string="Pris en charge par", ondelete='set null')
    date_ouverture = fields.Datetime(
        string="Ouvert le", default=fields.Datetime.now, readonly=True)
    date_resolution = fields.Datetime(string="Résolu le", readonly=True)

    is_open = fields.Boolean(
        string="Ouvert", compute='_compute_is_open', store=True, index=True,
        help="Le compteur que lisent les tableaux de bord. Stocké parce qu'il "
             "sera filtré et agrégé.")

    @api.depends('traitement')
    def _compute_is_open(self):
        for incident in self:
            incident.is_open = incident.traitement != 'resolu'

    @api.depends('name', 'incident_type')
    def _compute_display_name(self):
        labels = dict(self._fields['incident_type'].selection)
        for incident in self:
            incident.display_name = "%s — %s" % (
                incident.name or '', labels.get(incident.incident_type, ''))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', NEW_REFERENCE) == NEW_REFERENCE:
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code(
                    'opex.mission.incident') or NEW_REFERENCE
        return super().create(vals_list)

    def action_take_over(self):
        self.ensure_one()
        self.write({
            'traitement': 'en_traitement',
            'assignee_id': self.env.user.id,
        })
        return True

    def action_resolve(self):
        self.ensure_one()
        self.write({
            'traitement': 'resolu',
            'date_resolution': fields.Datetime.now(),
        })
        return True

    def action_reopen(self):
        """Un incident refermé trop vite se rouvre.

        Ce n'est pas un chemin de refus au sens du workflow : personne ne
        conteste une décision, on constate que le problème persiste. Le
        chatter en garde la trace, ce qui suffit ici.
        """
        self.ensure_one()
        self.write({'traitement': 'en_traitement', 'date_resolution': False})
        return True
