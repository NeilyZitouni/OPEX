from odoo import fields, models


class WorkflowRole(models.Model):
    """Qui intervient dans un workflow, indépendamment de quel workflow.

    Référentiel **global** et non rattaché à une définition : Porteur,
    Secrétariat, Comité, Expert se réutilisent d'un processus à l'autre. C'est
    ce qui permet à une transition d'un second workflow de réutiliser le rôle
    déjà défini pour le premier, sans le redéclarer.

    `group_id` est le pont vers la sécurité Odoo quand le rôle correspond à un
    groupe permanent (le Secrétariat, le CEO). Il reste **vide** pour les rôles
    attribués au cas par cas — l'expert *de ce dossier-là* — qui sont alors
    portés par une ligne `opex.workflow.instance.actor` (Extension 5).
    """

    _name = 'opex.workflow.role'
    _description = "Rôle de workflow"
    _order = 'name'

    name = fields.Char(string="Nom", required=True, translate=True)
    code = fields.Char(
        string="Code",
        required=True,
        index=True,
        help="Identifiant technique, utilisé dans les fichiers de configuration. "
             "Exemple : secretariat, comite, ceo.",
    )
    description = fields.Text(string="Description")
    group_id = fields.Many2one(
        'res.groups',
        string="Groupe Odoo correspondant",
        ondelete='set null',
        help="Groupe de sécurité dont les membres portent ce rôle en permanence. "
             "Laisser vide pour un rôle attribué dossier par dossier : il sera "
             "alors porté par les acteurs de l'instance.",
    )
    active = fields.Boolean(string="Actif", default=True)

    _code_uniq = models.Constraint(
        'unique(code)',
        "Le code d'un rôle doit être unique.",
    )
