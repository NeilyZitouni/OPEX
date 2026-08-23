from odoo import fields, models

# Documentation affichée sous le champ `expression`. C'est la seule aide dont
# disposera la personne qui configure une condition sans lire de Python : elle
# est donc exhaustive sur le contexte disponible, et donne des exemples
# copiables tels quels.
EXPRESSION_HELP = """Expression Python évaluée en lecture seule (safe_eval).

Objets disponibles :
  record    l'enregistrement métier piloté (le projet, le dossier…)
  instance  l'instance de workflow en cours
  stage     l'étape courante
  user      l'utilisateur qui tente la transition
  field(nom)          valeur d'un champ de l'enregistrement, False s'il n'existe pas
  has_document(type)  True si l'enregistrement porte un document de ce type

Exemples :
  record.ceo_approval == True
  has_document('pitch_deck')
  field('score') >= 70
  field('score') >= 70 and has_document('business_plan')

Une expression qui échoue est considérée comme FAUSSE : la transition est
bloquée et le message ci-dessous est affiché. Elle ne casse jamais la page."""


class WorkflowRule(models.Model):
    """Une condition nommée, réutilisable par plusieurs transitions.

    Le couple (expression, message) est indissociable : une condition qui
    bloque sans expliquer pourquoi laisse l'utilisateur devant un bouton mort.
    `message` est donc requis au même titre que `expression`.

    Aucune évaluation ici : le moteur d'évaluation vit sur
    `opex.workflow.instance` (Extension 2), parce qu'évaluer demande un
    enregistrement métier et une étape courante, que la règle seule ne connaît
    pas.
    """

    _name = 'opex.workflow.rule'
    _description = "Règle de workflow (condition)"
    _order = 'name'

    name = fields.Char(string="Nom", required=True, translate=True)
    code = fields.Char(string="Code", required=True, index=True)
    expression = fields.Text(
        string="Expression",
        required=True,
        help=EXPRESSION_HELP,
    )
    message = fields.Char(
        string="Message si la condition bloque",
        required=True,
        translate=True,
        help="Texte affiché à l'utilisateur quand cette condition empêche la "
             "transition. Rédigez-le pour un lecteur : « Le pitch deck n'a pas "
             "encore été déposé », pas « has_document failed ».",
    )
    description = fields.Text(string="Description")
    active = fields.Boolean(string="Actif", default=True)

    _code_uniq = models.Constraint(
        'unique(code)',
        "Le code d'une règle doit être unique.",
    )
