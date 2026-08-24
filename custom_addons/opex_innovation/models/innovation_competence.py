from odoo import fields, models


class InnovationCompetence(models.Model):
    """Référentiel de compétences, partagé par les profils et les projets.

    Un modèle plutôt qu'un champ texte libre : c'est ce qui rend le Matching IA
    possible. Deux personnes qui écrivent « IA » et « intelligence
    artificielle » dans une zone de texte ne se croiseront jamais ; deux
    personnes rattachées au même enregistrement, si.
    """

    _name = 'opex.innovation.competence'
    _description = "Compétence"
    _order = 'domaine, name'

    name = fields.Char(string="Compétence", required=True, translate=True)
    code = fields.Char(string="Code", index=True)
    domaine = fields.Char(string="Domaine", translate=True)
    niveau = fields.Selection(
        [
            ('debutant', "Débutant"),
            ('intermediaire', "Intermédiaire"),
            ('confirme', "Confirmé"),
            ('expert', "Expert"),
        ],
        string="Niveau attendu",
    )
    description = fields.Text(string="Description")
    active = fields.Boolean(string="Actif", default=True)
