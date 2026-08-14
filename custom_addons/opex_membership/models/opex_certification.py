from odoo import fields, models


class OpexCertification(models.Model):
    """Certification détenue par une organisation (ISO 9001, ISO 14001...).

    Modèle volontairement minimal : la certification n'est qu'un libellé
    réutilisable, que la section B du formulaire coche sur un dossier et que
    l'annuaire utilisera comme critère de recherche (Extension 14).
    """

    _name = 'opex.certification'
    _description = "Certification"
    _order = 'name'

    name = fields.Char(string="Nom", required=True)

    # Syntaxe Odoo 19 : `_sql_constraints` a disparu au profit de
    # `models.Constraint`, comme le montre `decimal.precision` dans `base`.
    _name_uniq = models.Constraint(
        'unique (name)',
        "Cette certification existe déjà.",
    )
