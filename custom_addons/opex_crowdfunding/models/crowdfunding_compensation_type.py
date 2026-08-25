from odoo import fields, models


class OpexCrowdfundingCompensationType(models.Model):
    """La contrepartie du CEO pour un accompagnement (section 12).

    ⚠️ Le document est catégorique : « Le workflow ne doit pas coder en dur le
    modèle économique. La contrepartie doit être configurable. »

    C'est, avec les critères de pré-analyse, l'une des deux zones où la
    spécification impose du paramétrable **jusque dans l'implémentation
    texto**. Un `Selection` en dur ici serait plus court à écrire et
    contredirait le document : ajouter « paiement différé » ou « royalties »
    ne doit pas demander de développeur.

    À relever tel quel dans le document de comparaison : le module texto n'est
    pas intégralement en dur, et le dire renforce la comparaison au lieu de
    l'affaiblir.
    """

    _name = 'opex.crowdfunding.compensation.type'
    _description = "Type de contrepartie CEO"
    _order = 'sequence, id'

    name = fields.Char(string="Contrepartie", required=True, translate=True)
    description = fields.Char(string="Précision", translate=True)
    sequence = fields.Integer(string="Séquence", default=10)
    active = fields.Boolean(string="Actif", default=True)
