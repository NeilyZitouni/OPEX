"""La certification d'un expert, rattachée au référentiel — et ses trois axes.

CE QUI CHANGE, ET POURQUOI C'EST LA MOITIÉ DE D1

`opex.expert.certification` portait un `name` en **texte libre**. C'est ce
texte que `res.partner.expert_certification_names` agrégeait, et que le
critère éliminatoire comparait par inclusion de chaînes. D'où les trois
défaillances mesurées : « ISO 27001 » passait pour « ISO 27001 Lead Auditor »,
« ISO27001 » ne croisait plus rien, et exiger deux normes revenait à n'en
exiger au plus qu'une.

`certification_id` rattache la ligne au référentiel. Le `name` **reste**, et
ce n'est pas une hésitation :

- il porte la saisie libre pendant la transition, et le portail expert
  continue de fonctionner sur des données existantes ;
- il garde la trace de ce que l'expert a **écrit**, quand le rapprochement a
  choisi autre chose. C'est ce qui permet de contester un rapprochement.

Une ligne sans `certification_id` est visible comme telle — filtre « Non
rapprochées » — et **n'entre pas dans le critère éliminatoire**. C'est une
file de travail, pas une erreur ; mais c'est une file qu'il faut vider, sinon
les certifications déclarées avant cette extension ne comptent plus.

LES TROIS AXES DU §9, ICI AUSSI

Une certification lue dans un CV et une certification dont le justificatif a
été vérifié par OPEX ne valent pas la même chose. Le §9 vaut pour elles comme
pour les compétences, et la promotion pose les trois : `source='cv'`,
`confiance='expert'`, et la citation du CV en preuve.
"""

from odoo import api, fields, models

from .expert_skill_axes import (CONFIANCE_SELECTION, SOURCE_SELECTION,
                                UNCONFIRMED)


class ExpertCertificationAxes(models.Model):
    """Le rattachement au référentiel, et les axes du §9."""

    _inherit = 'opex.expert.certification'

    certification_id = fields.Many2one(
        'opex.certification',
        string="Certification du référentiel",
        ondelete='restrict',
        index=True,
        domain="[('porte', 'in', ['personne', 'les_deux'])]",
        help="Le référentiel partagé avec le Module 1. C'est lui que le "
             "critère éliminatoire compare — jamais l'intitulé libre.",
    )

    # Défauts choisis pour les lignes **existantes**, pas pour les nouvelles.
    # Elles ont été saisies par l'expert depuis son portail à l'Extension 3 :
    # `expert` / `expert` est exact pour elles. Un défaut à `ia` aurait
    # discrédité d'un coup tout le capital déjà déclaré.
    source = fields.Selection(
        SOURCE_SELECTION,
        string="Source",
        required=True,
        default='expert',
        help="D'où vient cette ligne.",
    )
    confiance = fields.Selection(
        CONFIANCE_SELECTION,
        string="Confiance",
        required=True,
        default='expert',
        help="Ce que vaut l'information, indépendamment de sa validité "
             "calendaire. Une certification lue dans un CV et une "
             "certification dont le justificatif a été vérifié ne se valent "
             "pas.",
    )
    is_confirmed = fields.Boolean(
        string="Confirmée",
        compute='_compute_certification_is_confirmed',
        store=True,
        index=True,
        help="Quelqu'un s'est prononcé. C'est ce champ, croisé avec la "
             "validité calendaire, que le critère éliminatoire lit.",
    )

    preuve_citation = fields.Text(
        string="Passage du CV",
        help="Le texte exact d'où vient cette certification. Sans lui, "
             "`source = CV analysé` dirait la provenance sans permettre de la "
             "vérifier.",
    )
    preuve_cv_id = fields.Many2one(
        'opex.expert.cv.source',
        string="CV d'origine",
        ondelete='set null',
    )

    #: Ce que lit le matching : rapprochée, confirmée **et** encore valable.
    #: Les trois, et pas deux : une certification expirée ne prouve plus rien,
    #: une certification non confirmée n'engage personne, et une certification
    #: non rapprochée n'est comparable à rien.
    #: **Non stocké, et ce n'est pas un oubli.** `is_valid` compare la date
    #: d'expiration à *aujourd'hui* : il n'a aucune dépendance déclarable, et
    #: rien ne se déclenche le jour où une certification expire.
    #:
    #: Stocker `is_eligible` le figerait à sa dernière écriture — une
    #: certification périmée continuerait de compter dans le vivier jusqu'à ce
    #: que quelqu'un rouvre sa fiche. Sur un critère éliminatoire, cela veut
    #: dire admettre un candidat qui n'est plus qualifié : exactement le genre
    #: de défaut que D1 existe pour fermer.
    #:
    #: Le coût est un calcul par candidat évalué. C'est le bon échange.
    #: Règle 16 du CLAUDE.md, prise du côté où elle interdit de stocker.
    is_eligible = fields.Boolean(
        string="Comptée par le matching",
        compute='_compute_is_eligible',
        search='_search_is_eligible',
    )

    # Deux méthodes de calcul, et cette fois la règle 9 l'impose :
    # `is_confirmed` est **stocké** et `is_eligible` ne l'est pas. Le registre
    # refuse qu'une même méthode produise les deux - lire un indicateur
    # d'affichage déclencherait l'écriture du champ stocké, à un moment
    # quelconque et sous l'identité de n'importe quel lecteur.

    @api.depends('date_expiration')
    def _compute_is_valid(self):
        """Redéclare la dépendance qui manquait à l'Extension 3.

        `is_valid` y est calculé sans `@api.depends` : Odoo ne l'invalide donc
        **jamais** à l'écriture, et une date d'expiration modifiée laissait le
        champ à sa valeur en cache. Le calcul lui-même est juste ; c'est son
        invalidation qui manquait.

        Sans cette ligne, `is_eligible` — qui lit `is_valid` — héritait de la
        valeur périmée, et une certification expirée continuait de qualifier
        son porteur jusqu'à la fin de la transaction. Mesuré au shell :
        `is_valid: True` sur une date d'expiration mise à hier.

        La méthode parente est appelée telle quelle : on ajoute la
        dépendance, on ne réécrit pas la règle. Une seconde définition de « en
        cours de validité » divergerait au premier ajustement.

        ⚠ Ce que cette dépendance ne peut pas porter : le passage du temps. Le
        jour où une certification expire, rien ne se déclenche — c'est
        précisément pourquoi `is_eligible` et la cible de matching ne sont pas
        stockés.
        """
        return super()._compute_is_valid()

    @api.depends('confiance')
    def _compute_certification_is_confirmed(self):
        for certification in self:
            certification.is_confirmed = certification.confiance != UNCONFIRMED

    @api.depends('certification_id', 'is_confirmed', 'date_expiration')
    def _compute_is_eligible(self):
        for certification in self:
            certification.is_eligible = bool(
                certification.certification_id
                and certification.is_confirmed
                and certification.is_valid)

    @api.model
    def _search_is_eligible(self, operator, value):
        """Traduit l'éligibilité en domaine sur des colonnes réelles.

        Sans elle, le filtre « Comptées par le matching » de la vue `search`
        rend la vue invalide et **le module ne charge plus** :

            Unsearchable field "is_eligible" in path "is_eligible" in domain
            of <filter name="comptees">

        Mesuré. Le message est excellent — il nomme le champ et le filtre —,
        et la règle 16 du CLAUDE.md donne la bonne issue : donner sa méthode
        de recherche au champ plutôt que recopier la logique dans le domaine
        du filtre. Deux définitions du même prédicat divergeraient au premier
        ajustement, sans que rien ne le signale.

        DEUX PIÈGES, LES DEUX MESURÉS

        1. **Odoo 19 normalise les booléens.** `('is_eligible', '=', True)`
           arrive ici en `operator='in'`, `value=OrderedSet([True])` — jamais
           en `'='`. Une implémentation qui ne teste que `'='` et `'!='` ne se
           déclenche pour aucun des deux cas et rend le mauvais domaine.

        2. **`'!'` est unaire.** `['!'] + domaine` ne nie que le **premier**
           terme, pas l'ensemble : `['!', A, B, C]` vaut `(NON A) ET B ET C`.
           La négation s'écrit donc en toutes lettres, par une chaîne de `'|'`.

        Les deux ensemble donnaient un résultat qui ressemblait à une réponse :
        la recherche rendait « Texte libre » là où le calcul rendait « CISA ».
        Pas une erreur, pas un ensemble vide — **l'autre** ensemble.

        ⚠ Corollaire de la règle 16 :
        `test_the_eligibility_search_matches_its_computation` compare les deux
        implémentations sur les quatre cas qui font varier le prédicat. Rien
        dans Odoo ne garantit qu'elles répondent la même chose.
        """
        today = fields.Date.context_today(self)

        eligible = [
            ('certification_id', '!=', False),
            ('is_confirmed', '=', True),
            '|',
            ('date_expiration', '=', False),
            ('date_expiration', '>=', today),
        ]
        # La négation, écrite et non dérivée : non rapprochée OU non
        # confirmée OU expirée.
        non_eligible = [
            '|', ('certification_id', '=', False),
            '|', ('is_confirmed', '=', False),
            '&', ('date_expiration', '!=', False),
            ('date_expiration', '<', today),
        ]

        valeurs = value if isinstance(
            value, (list, tuple, set, frozenset)) else [value]
        cherche_vrai = any(bool(v) for v in valeurs)
        positif = cherche_vrai == (operator in ('=', '==', 'in'))
        return eligible if positif else non_eligible

    def action_confirm(self):
        """Le geste humain : la ligne compte désormais dans le vivier."""
        for certification in self:
            if certification.is_confirmed:
                continue
            certification.sudo().confiance = 'expert'
        return True

    def action_verify(self):
        """OPEX a vu le justificatif.

        Le cran au-dessus de « confirmé par l'expert », et le seul qui engage
        le cluster. Réservé au personnel des missions.
        """
        for certification in self:
            certification.sudo().confiance = 'opex'
        return True
