from odoo import _, api, fields, models
from odoo.exceptions import UserError


class WorkflowHistory(models.Model):
    """Le journal d'audit : qui a fait quoi, quand, et pourquoi c'était permis.

    ⚠ **Lecture seule pour tout le monde, administrateur compris.** `write()` et
    `unlink()` lèvent une `UserError` explicite, sans exception de groupe et
    sans échappatoire par `sudo()`. Un journal d'audit modifiable ne vaut rien :
    sa seule valeur est la garantie que personne n'a pu le retoucher après
    coup — y compris celui qui avait les droits pour le faire.

    Les lignes sont créées exclusivement par `opex.workflow.instance`, jamais à
    la main.
    """

    _name = 'opex.workflow.history'
    _description = "Historique de workflow"
    _order = 'date desc, id desc'

    instance_id = fields.Many2one(
        'opex.workflow.instance',
        string="Instance",
        required=True,
        ondelete='cascade',
        index=True,
    )
    from_stage_id = fields.Many2one(
        'opex.workflow.stage',
        string="Étape de départ",
        ondelete='restrict',
        help="Vide sur la première ligne : l'entrée dans le processus.",
    )
    to_stage_id = fields.Many2one(
        'opex.workflow.stage',
        string="Étape d'arrivée",
        ondelete='restrict',
    )
    transition_id = fields.Many2one(
        'opex.workflow.transition',
        string="Transition",
        ondelete='restrict',
        help="Vide pour les événements qui ne passent pas par une transition : "
             "démarrage, annulation.",
    )
    user_id = fields.Many2one('res.users', string="Auteur", required=True)
    date = fields.Datetime(
        string="Date", required=True, default=fields.Datetime.now)
    comment = fields.Text(string="Commentaire")
    conditions_note = fields.Text(
        string="Conditions au moment du passage",
        help="Résultat de chaque condition évaluée lors de la transition. "
             "C'est ce qui permet, six mois plus tard, de savoir pourquoi le "
             "dossier est passé alors que la règle semble aujourd'hui l'interdire.",
    )
    forced = fields.Boolean(
        string="Transition forcée",
        help="Vrai lorsqu'un gestionnaire a déclenché une transition dont il ne "
             "portait pas le rôle. Champ à part et non mention dans un texte "
             "libre : un contournement de rôle doit être filtrable, pas "
             "retrouvable à la recherche de sous-chaîne.",
    )

    @api.depends('from_stage_id', 'to_stage_id', 'transition_id')
    def _compute_display_name(self):
        for entry in self:
            if entry.from_stage_id:
                entry.display_name = "%s → %s" % (
                    entry.from_stage_id.name, entry.to_stage_id.name)
            else:
                entry.display_name = _("Entrée : %s") % (entry.to_stage_id.name or '')

    def _immutable_error(self):
        """Méthode et non constante de classe : un `_()` évalué à l'import
        fige la traduction dans la langue du serveur au démarrage."""
        return UserError(_(
            "L'historique d'un workflow est un journal d'audit : il ne peut être "
            "ni modifié ni supprimé, par personne — administrateur compris. Pour "
            "corriger une erreur de parcours, faites avancer le dossier par une "
            "transition, qui laissera sa propre trace."
        ))

    def write(self, vals):
        raise self._immutable_error()

    def unlink(self):
        raise self._immutable_error()
