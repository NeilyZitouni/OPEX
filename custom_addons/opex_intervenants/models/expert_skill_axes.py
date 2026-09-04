"""Les trois axes d'une compétence qualifiée - §9.

    « Le niveau déclaré par l'expert ne doit pas constituer à lui seul la
      vérité. »

Trois axes, et non un champ enrichi, parce qu'ils répondent à trois questions
différentes :

- `niveau`   - ce que vaut l'expert. Métier. Posé à l'Extension 3.
- `source`   - d'où vient l'information. CV, déclaration, saisie OPEX, mission
               réellement réalisée.
- `confiance` - ce que l'information vaut. Proposée par l'IA, confirmée par
               l'expert, vérifiée par OPEX.

Les confondre rendrait impossible de distinguer « junior, extrait avec
certitude » de « expert, extrait avec doute » - et c'est précisément le second
cas que le Smart Quality Control du §12 doit remonter.

POURQUOI `confiance` N'EST PAS UN WORKFLOW

Proposé par l'IA -> confirmé par l'expert -> vérifié par OPEX est une
progression, et la question mérite d'être posée. La réponse est celle que le
CLAUDE.md du moteur pose pour `roadmap.phase`, et que l'Extension 8 a déjà
appliquée à l'incident du §26 : trois positions, aucun chemin de refus, aucune
condition, aucune notification, aucun historique à conserver. C'est un
compteur, pas un processus.

Le critère est écrit ici plutôt que découvert en soutenance, et
`test_the_confidence_is_a_counter_not_a_process` le verrouille : une quatrième
position, un chemin de refus, et la conversation a lieu.
"""

from odoo import api, fields, models

#: D'où vient l'information. Le §9 en donne quatre.
SOURCE_SELECTION = [
    ('cv', "CV analysé"),
    ('expert', "Déclaré par l'expert"),
    ('opex', "Saisi par OPEX"),
    ('mission', "Mission réalisée"),
]

#: Ce que l'information vaut. Du plus faible au plus fort, et cet ordre est
#: celui du `_order` du modèle : une ligne vérifiée passe devant une ligne
#: proposée.
CONFIANCE_SELECTION = [
    ('ia', "Proposé par l'IA"),
    ('expert', "Confirmé par l'expert"),
    ('opex', "Vérifié par OPEX"),
]

#: Le seul niveau de confiance qui n'engage personne. Nommé une fois, lu par
#: `is_confirmed` et par les tests - deux définitions du « non confirmé »
#: finiraient par diverger, et c'est le matching qui en paierait le prix.
UNCONFIRMED = 'ia'


class ExpertSkillAxes(models.Model):
    """Les deux axes que l'Extension 3 n'avait pas."""

    _inherit = 'opex.expert.skill'

    # Défauts choisis pour les lignes **existantes**, pas pour les nouvelles.
    #
    # À l'ajout d'une colonne, Odoo applique le défaut du champ à toutes les
    # lignes déjà en base. Or celles-ci ont été saisies par l'expert depuis
    # son espace portail à l'Extension 3 : `expert` / `expert` est exact pour
    # elles, et c'est le seul choix qui n'invente rien.
    #
    # Un défaut à `ia` aurait discrédité d'un coup tout le capital déjà
    # déclaré, et l'aurait retiré du matching par la même occasion.
    source = fields.Selection(
        SOURCE_SELECTION,
        string="Source",
        required=True,
        default='expert',
        help="D'où vient cette ligne. Une compétence lue dans un CV et une "
             "compétence prouvée par une mission réalisée ne se valent pas.",
    )
    confiance = fields.Selection(
        CONFIANCE_SELECTION,
        string="Confiance",
        required=True,
        default='expert',
        help="Ce que vaut l'information, indépendamment du niveau. Une "
             "compétence proposée par l'IA reste une proposition tant que "
             "personne ne l'a confirmée.",
    )

    is_confirmed = fields.Boolean(
        string="Confirmée",
        compute='_compute_is_confirmed',
        store=True,
        index=True,
        help="Quelqu'un s'est prononcé sur cette ligne. C'est ce champ que "
             "lit le Smart Matching : une proposition non confirmée ne fait "
             "matcher personne.",
    )

    # ------------------------------------------------------------
    # Les deux attributs du §8 qui manquaient
    # ------------------------------------------------------------
    #
    # Le tableau du §8 en compte sept : compétence canonique, niveau, années,
    # **dernière pratique**, source, **preuve**, confiance. Les cinq autres
    # étaient là depuis l'Extension 3 et l'IA-1.

    derniere_pratique = fields.Date(
        string="Dernière pratique",
        help="Quand cette compétence a été exercée pour la dernière fois. "
             "Un niveau Expert pratiqué il y a huit ans n'est pas un niveau "
             "Expert aujourd'hui, et le matching doit pouvoir le voir.",
    )

    #: Colonne réelle, donc filtrable et groupable sans méthode de recherche.
    #: Un calcul « années écoulées depuis » aurait été plus lisible à l'écran
    #: et **non cherchable** (règle 16) : la vue `search` qui le filtrerait
    #: empêcherait le module de charger. On expose la date ; l'ancienneté se
    #: lit par un filtre de date, que la vue fournit.
    fraicheur = fields.Selection(
        [
            ('recente', "Pratiquée récemment (< 2 ans)"),
            ('ancienne', "Pratique ancienne (2 à 5 ans)"),
            ('dormante', "Dormante (> 5 ans)"),
            ('inconnue', "Non renseignée"),
        ],
        string="Fraîcheur",
        compute='_compute_fraicheur',
        help="Lecture de « dernière pratique ». Non stockée : elle dépend de "
             "la date du jour, et un stockage la figerait au dernier calcul - "
             "une compétence deviendrait dormante le jour où quelqu'un ouvre "
             "sa fiche.",
    )

    # --- La preuve --------------------------------------------------------
    #
    # « Preuve » est **un** attribut du §8, qui répond à une question :
    # qu'est-ce qui appuie cette déclaration ? Il est réalisé par les deux
    # sortes de pièces que le profil porte déjà, plutôt que par un champ libre
    # de plus - l'expert a saisi ses expériences et ses certifications à
    # l'Extension 3, il n'a pas à les redécrire ici.
    #
    # C'est ce qui rend le §9 opérant. « Un niveau 4 auto-déclaré et un
    # niveau 4 confirmé par trois expériences et une certification ne valent
    # pas la même chose » : sans pièces rattachées, cette phrase n'est qu'une
    # intention. Avec elles, elle se compte.
    preuve_experience_ids = fields.Many2many(
        'opex.expert.experience',
        'opex_skill_experience_rel', 'skill_id', 'experience_id',
        string="Missions qui l'attestent",
        domain="[('profile_id', '=', profile_id)]",
    )
    preuve_certification_ids = fields.Many2many(
        'opex.expert.certification',
        'opex_skill_certification_rel', 'skill_id', 'certification_id',
        string="Certifications qui l'attestent",
        domain="[('profile_id', '=', profile_id)]",
    )
    #: La troisième sorte de preuve, et celle qui ferme la chaîne du CV.
    #:
    #: Une compétence promue depuis un CV a pour preuve **le passage exact du
    #: document**. Sans lui, `source='cv'` dirait d'où vient l'information
    #: sans permettre de la vérifier - et le §24 demande précisément qu'une
    #: donnée validée reste traçable jusqu'à sa source.
    preuve_citation = fields.Text(
        string="Passage du CV",
        help="Le texte exact d'où vient cette compétence. On rouvre le "
             "document et on lit : c'est ce qui rend la promotion "
             "vérifiable des mois plus tard.",
    )
    preuve_cv_id = fields.Many2one(
        'opex.expert.cv.source',
        string="CV d'origine",
        ondelete='set null',
        help="Le document, sa version et sa date. La citation seule serait "
             "invérifiable si l'on ne savait pas dans quel CV la chercher.",
    )
    preuve_count = fields.Integer(
        string="Pièces à l'appui",
        compute='_compute_preuve_count',
        help="Le nombre de pièces rattachées. Zéro n'est pas une faute : "
             "c'est une déclaration sans preuve, et c'est une information.",
    )

    # Trois méthodes de calcul et non une seule : `is_confirmed` est **stocké**
    # et les trois autres ne le sont pas. Le registre refuse qu'une même
    # méthode produise les deux (règle 9) - lire un compteur d'affichage
    # déclencherait l'écriture du champ stocké, à un moment quelconque et sous
    # l'identité de n'importe quel lecteur.

    @api.depends('derniere_pratique')
    def _compute_fraicheur(self):
        today = fields.Date.context_today(self)
        for skill in self:
            if not skill.derniere_pratique:
                skill.fraicheur = 'inconnue'
                continue
            jours = (today - skill.derniere_pratique).days
            if jours < 2 * 365:
                skill.fraicheur = 'recente'
            elif jours <= 5 * 365:
                skill.fraicheur = 'ancienne'
            else:
                skill.fraicheur = 'dormante'

    @api.depends('preuve_experience_ids', 'preuve_certification_ids',
                 'preuve_citation')
    def _compute_preuve_count(self):
        for skill in self:
            skill.preuve_count = (len(skill.preuve_experience_ids)
                                  + len(skill.preuve_certification_ids)
                                  + (1 if skill.preuve_citation else 0))

    @api.depends('confiance')
    def _compute_is_confirmed(self):
        """Stocké, et donc seul dans sa méthode.

        Le registre refuse qu'une même méthode produise du stocké et du non
        stocké (règle 9). Stocké parce que le matching le filtre et qu'une
        `ir.rule` ou un domaine a besoin d'une colonne.
        """
        for skill in self:
            skill.is_confirmed = skill.confiance != UNCONFIRMED

    def action_confirm(self):
        """L'expert reprend à son compte une ligne proposée par l'IA.

        Le geste humain que le §9 exige, et le seul qui fasse entrer une
        compétence dans le matching. Il ne touche ni au niveau ni à la
        source : ce qui change, c'est ce que l'information vaut, pas ce
        qu'elle dit ni d'où elle vient.
        """
        for skill in self:
            if skill.confiance == UNCONFIRMED:
                skill.confiance = 'expert'
        return True

    def action_verify(self):
        """OPEX vérifie une ligne - le niveau de confiance le plus haut."""
        for skill in self:
            skill.confiance = 'opex'
        return True
