from odoo import fields, models


class OpexCrowdfundingCriteria(models.Model):
    """Critère de validation préliminaire de la pré-analyse (section 6).

    Le document dit « selon des critères configurables » : ils vivent donc en
    base et non dans le code. C'est, avec la contrepartie de l'accompagnement,
    l'un des rares endroits où la spécification impose du paramétrable jusque
    dans l'implémentation texto — à relever tel quel dans le document de
    comparaison plutôt qu'à masquer.

    Ce qui reste codé en dur ici, en revanche, c'est ce qu'on *fait* du
    résultat : quatre issues, quatre méthodes.
    """

    _name = 'opex.crowdfunding.criteria'
    _description = "Critère de pré-analyse"
    _order = 'sequence, id'

    name = fields.Char(string="Critère", required=True, translate=True)
    description = fields.Char(string="Précision", translate=True)
    sequence = fields.Integer(string="Séquence", default=10)
    active = fields.Boolean(string="Actif", default=True)
