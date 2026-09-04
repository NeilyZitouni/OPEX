from odoo import fields, models


class WorkflowInstanceActor(models.Model):
    """Qui a un rôle sur **ce** dossier-là.

    C'est la pièce qui distingue « être expert sur le portail » de « être
    l'expert de ce projet » : le premier est un profil du vivier, le second est
    une ligne ici. Un rôle porté par un groupe Odoo vaut pour tous les dossiers ;
    un rôle porté par une ligne d'acteur ne vaut que pour celui-ci.

    Extension 2 : **modèle seul.** Les `ir.rule` qui s'appuient dessus pour
    restreindre la visibilité des instances, de l'historique et des tâches sont
    l'Extension 5. Le modèle est posé maintenant parce que
    `_check_transition_allowed()` en a besoin dès l'exécution : sans lui, seuls
    les rôles adossés à un groupe permanent existeraient.
    """

    _name = 'opex.workflow.instance.actor'
    _description = "Acteur d'une instance de workflow"
    _order = 'instance_id, role_id'

    instance_id = fields.Many2one(
        'opex.workflow.instance',
        string="Instance",
        required=True,
        ondelete='cascade',
        index=True,
    )
    role_id = fields.Many2one(
        'opex.workflow.role',
        string="Rôle",
        required=True,
        ondelete='restrict',
        index=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string="Utilisateur",
        ondelete='cascade',
        index=True,
    )
    access_level = fields.Selection(
        [
            ('none', "Aucun"),
            ('limited', "Limité"),
            ('full', "Complet"),
        ],
        string="Niveau d'accès",
        default='limited',
        required=True,
        index=True,
        help="« Limité » donne accès aux informations autorisées pour ce rôle, "
             "« Complet » au dossier entier. « Aucun » conserve la trace de la "
             "désignation tout en retirant l'accès : le rôle ne compte alors "
             "plus pour les transitions.",
    )
    date_granted = fields.Datetime(
        string="Accordé le",
        default=fields.Datetime.now,
        readonly=True,
        help="Quand cet accès a été ouvert. Avec `granted_by_id`, c'est ce qui "
             "permet de répondre six mois plus tard à « qui a donné accès à ce "
             "dossier, et quand ».",
    )
    granted_by_id = fields.Many2one(
        'res.users',
        string="Accordé par",
        default=lambda self: self.env.user,
        readonly=True,
        ondelete='set null',
    )

    _actor_uniq = models.Constraint(
        'unique(instance_id, role_id, user_id)',
        "Cet utilisateur porte déjà ce rôle sur ce dossier.",
    )
