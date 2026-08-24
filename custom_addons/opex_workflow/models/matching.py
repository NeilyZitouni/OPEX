import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MatchingCriteria(models.Model):
    """Un critère pondéré de rapprochement entre un dossier et des candidats.

    Le rapprochement se fait toujours de la même façon : on lit une valeur
    **sur le dossier** (`source_expression`), on la compare à une valeur **sur
    le candidat** (`target_field`), et la correspondance rapporte `weight`.

    Aucun apprentissage automatique. « IA » veut dire ici *scoring explicable* :
    chaque point du score se rattache à un critère nommé, et l'explication se
    lit en français. Un modèle statistique donnerait peut-être un meilleur
    classement, mais un score qu'on ne sait pas justifier n'est pas défendable —
    ce serait un défaut, pas une qualité.
    """

    _name = 'opex.matching.criteria'
    _description = "Critère de matching"
    _order = 'definition_id, sequence, id'

    definition_id = fields.Many2one(
        'opex.workflow.definition',
        string="Workflow",
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(string="Nom", required=True, translate=True)
    code = fields.Char(string="Code", required=True, index=True)
    sequence = fields.Integer(string="Séquence", default=10)
    criteria_type = fields.Selection(
        [
            ('secteur', "Secteur"),
            ('competence', "Compétence"),
            ('localisation', "Localisation"),
            ('maturite', "Niveau de maturité"),
            ('montant', "Montant / ticket"),
            ('technologie', "Technologie"),
            ('disponibilite', "Disponibilité"),
            ('autre', "Autre"),
        ],
        string="Type",
        default='autre',
        required=True,
        help="Purement descriptif : sert à regrouper et à lire les résultats. "
             "Le calcul, lui, ne dépend que de l'expression et du champ cible.",
    )
    weight = fields.Float(
        string="Poids",
        default=1.0,
        required=True,
        help="Contribution de ce critère quand il correspond. Les poids sont "
             "normalisés : seul leur rapport compte, pas leur échelle.",
    )
    source_expression = fields.Text(
        string="Valeur attendue (côté dossier)",
        required=True,
        help="Expression évaluée sur le dossier, avec le même contexte que les "
             "règles de transition : record, instance, user, stage, "
             "field('nom'), has_document('type').\n\n"
             "Exemple : field('secteur')\n"
             "Exemple : field('besoin_competence_ids').mapped('name')\n\n"
             "Une expression en erreur neutralise le critère : il ne rapporte "
             "rien et le dit dans l'explication, plutôt que de fausser le score.",
    )
    target_field = fields.Char(
        string="Champ comparé (côté candidat)",
        required=True,
        help="Nom d'un champ de res.partner porté par le candidat. "
             "Exemple : secteur_activite, wilaya.",
    )
    match_mode = fields.Selection(
        [
            ('equal', "Égalité"),
            ('contains', "Contient (texte)"),
            ('intersect', "Intersection (listes)"),
            ('gte', "Candidat ≥ dossier"),
            ('lte', "Candidat ≤ dossier"),
        ],
        string="Mode de comparaison",
        default='equal',
        required=True,
    )
    active = fields.Boolean(string="Actif", default=True)

    _code_uniq = models.Constraint(
        'unique(definition_id, code)',
        "Deux critères du même workflow ne peuvent pas porter le même code.",
    )

    # ------------------------------------------------------------
    # Comparaison
    # ------------------------------------------------------------

    @staticmethod
    def _as_set(value):
        """Ramène une valeur à un ensemble comparable.

        Les champs métier sont hétérogènes : un secteur est une chaîne, des
        compétences un recordset, des tags une liste. Les comparer suppose de
        les mettre au même format une bonne fois, ici, plutôt que d'écrire un
        cas par type dans chaque mode.
        """
        if isinstance(value, models.BaseModel):
            items = value.mapped('display_name')
        elif value in (False, None, ''):
            return set()
        elif isinstance(value, (list, tuple, set)):
            items = list(value)
        else:
            items = [value]
        # Normalisation **identique pour toutes les sources**. Sans elle, un
        # recordset dont le libellé est « IA » ne croiserait jamais une liste
        # écrite `['ia', 'iot']` dans la configuration : le critère resterait
        # muet et le score serait faux sans que rien ne le signale.
        return {
            str(item).strip().lower()
            for item in items
            if item not in (False, None, '')
        }

    def _compare(self, source_value, target_value):
        """Le critère est-il satisfait ? Renvoie (booléen, explication)."""
        self.ensure_one()
        source = self._as_set(source_value)
        target = self._as_set(target_value)

        if not source:
            return False, _("aucune attente exprimée sur le dossier")
        if not target:
            return False, _("le candidat ne renseigne pas ce champ")

        if self.match_mode == 'equal':
            ok = source == target
        elif self.match_mode == 'contains':
            ok = any(s in t or t in s for s in source for t in target)
        elif self.match_mode == 'intersect':
            ok = bool(source & target)
        elif self.match_mode in ('gte', 'lte'):
            try:
                left = float(next(iter(target)))
                right = float(next(iter(source)))
            except (TypeError, ValueError):
                return False, _("valeurs non numériques, comparaison impossible")
            ok = left >= right if self.match_mode == 'gte' else left <= right
        else:
            return False, _("mode de comparaison inconnu")

        detail = "%s ↔ %s" % (
            ", ".join(sorted(source)) or '∅',
            ", ".join(sorted(target)) or '∅',
        )
        return ok, detail


class MatchingCandidate(models.Model):
    """Un candidat proposé sur un dossier, avec son score et son explication.

    ⚠ **Une recommandation, jamais une décision.** Aucun état de ce modèle ne
    déclenche de transition, et rien dans le moteur ne lit un score pour
    décider. Les deux documents sources le disent noir sur blanc : « L'IA
    recommande. Elle ne doit pas automatiquement décider seule. » Le
    responsable Valide / Modifie / Exclut / Ajoute.
    """

    _name = 'opex.matching.candidate'
    _description = "Candidat proposé par le matching"
    _order = 'instance_id, score desc, id'

    instance_id = fields.Many2one(
        'opex.workflow.instance',
        string="Dossier",
        required=True,
        ondelete='cascade',
        index=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string="Candidat",
        required=True,
        ondelete='cascade',
        index=True,
    )
    candidate_type = fields.Selection(
        [
            ('expert', "Expert"),
            ('mentor', "Mentor"),
            ('investisseur', "Investisseur"),
            ('sponsor', "Sponsor"),
        ],
        string="Type",
        required=True,
        default='expert',
        index=True,
    )
    score = fields.Float(
        string="Score",
        digits=(5, 2),
        help="Pourcentage de correspondance : somme des poids satisfaits "
             "rapportée à la somme des poids applicables.",
    )
    # Requis au niveau du modèle, pas seulement par convention : un score sans
    # explication n'est pas défendable devant un jury, et une contrainte qui
    # n'est pas dans le schéma finit par être contournée.
    detail = fields.Text(
        string="Explication du score",
        required=True,
        help="Contribution de chaque critère. C'est ce qui distingue un score "
             "explicable d'un score opaque.",
    )
    state = fields.Selection(
        [
            ('proposed', "Proposé"),
            ('accepted', "Retenu"),
            ('rejected', "Écarté"),
            ('excluded', "Exclu"),
        ],
        string="État",
        default='proposed',
        required=True,
        index=True,
    )
    added_manually = fields.Boolean(
        string="Ajouté à la main",
        help="Vrai quand le responsable a ajouté ce candidat lui-même, hors "
             "proposition du moteur. Le distinguer permet de mesurer, plus "
             "tard, la pertinence réelle des recommandations.",
    )
    # ⚠ Distinct de `state`, et ce n'est pas une redondance.
    #
    # `state` porte la décision du **responsable** — retenir ou écarter la
    # proposition. `candidate_response` porte celle du **candidat** — être
    # disponible ou non. Les deux sont indépendantes : un candidat retenu peut
    # décliner, et c'est une information en soi.
    candidate_response = fields.Selection(
        [
            ('pending', "Sans réponse"),
            ('interested', "Intéressé"),
            ('declined', "Non disponible"),
        ],
        string="Réponse du candidat",
        default='pending',
        required=True,
        index=True,
    )
    date_response = fields.Datetime(string="Répondu le", readonly=True)

    decided_by_id = fields.Many2one(
        'res.users', string="Décidé par", readonly=True, ondelete='set null')
    decision_date = fields.Datetime(string="Décidé le", readonly=True)

    _candidate_uniq = models.Constraint(
        'unique(instance_id, partner_id, candidate_type)',
        "Ce candidat est déjà proposé sur ce dossier pour ce rôle.",
    )

    @api.depends('partner_id', 'score')
    def _compute_display_name(self):
        for candidate in self:
            candidate.display_name = "%s — %.0f %%" % (
                candidate.partner_id.display_name or '', candidate.score)

    def _decide(self, state):
        self.write({
            'state': state,
            'decided_by_id': self.env.user.id,
            'decision_date': fields.Datetime.now(),
        })
        return True

    # Quatre décisions humaines, quatre méthodes. Aucune ne déclenche de
    # transition : le responsable décide de la suite séparément, en connaissance
    # de cause.
    def action_accept(self):
        return self._decide('accepted')

    def action_reject(self):
        return self._decide('rejected')

    def action_exclude(self):
        return self._decide('excluded')

    def action_reset(self):
        return self._decide('proposed')

    # ------------------------------------------------------------
    # La réponse du candidat
    # ------------------------------------------------------------

    def _respond(self, response):
        """Enregistre la réponse du candidat.

        ⚠ Ne déclenche aucune transition, comme le reste du matching. Un
        candidat qui se déclare intéressé n'engage pas le dossier : c'est le
        responsable qui décide de la suite.
        """
        self.write({
            'candidate_response': response,
            'date_response': fields.Datetime.now(),
        })
        return True

    def action_interested(self):
        return self._respond('interested')

    def action_declined(self):
        return self._respond('declined')


class MatchingRelation(models.Model):
    """La mise en relation contrôlée : le match ne donne pas le dossier.

    Séquence des documents sources : match → teaser → intérêt → autorisation →
    NDA si nécessaire → dossier détaillé. Ce modèle porte l'**autorisation**,
    c'est-à-dire le moment où quelqu'un décide, nommément, d'ouvrir tel niveau
    d'information à tel candidat.

    Il ne remplace pas `opex.workflow.instance.actor` : l'acteur donne accès au
    dossier dans le moteur, la relation trace la négociation d'accès côté
    métier — qui a autorisé, quand, et si un NDA a été signé. Créer la relation
    peut ouvrir la ligne d'acteur correspondante, jamais l'inverse.
    """

    _name = 'opex.matching.relation'
    _description = "Mise en relation contrôlée"
    _order = 'instance_id, date desc, id'

    instance_id = fields.Many2one(
        'opex.workflow.instance',
        string="Dossier",
        required=True,
        ondelete='cascade',
        index=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string="Contact",
        required=True,
        ondelete='cascade',
        index=True,
    )
    candidate_id = fields.Many2one(
        'opex.matching.candidate',
        string="Candidature d'origine",
        ondelete='set null',
    )
    access_level = fields.Selection(
        [
            ('teaser', "Teaser anonymisé"),
            ('limited', "Informations autorisées"),
            ('full', "Dossier détaillé"),
        ],
        string="Niveau d'accès",
        default='teaser',
        required=True,
        help="Le principe du minimum nécessaire appliqué à l'information : on "
             "n'ouvre le niveau suivant qu'une fois l'intérêt exprimé et "
             "l'autorisation donnée.",
    )
    authorized_by_id = fields.Many2one(
        'res.users',
        string="Autorisé par",
        default=lambda self: self.env.user,
        readonly=True,
        ondelete='set null',
    )
    nda_signed = fields.Boolean(
        string="NDA signé",
        help="Confirmation horodatée, pas signature cryptographique — "
             "simplification assumée du POC, identique à celle du Module 1.",
    )
    nda_date = fields.Datetime(string="NDA signé le", readonly=True)
    date = fields.Datetime(
        string="Date", default=fields.Datetime.now, readonly=True)
    note = fields.Text(string="Note")

    _relation_uniq = models.Constraint(
        'unique(instance_id, partner_id)',
        "Une relation existe déjà entre ce dossier et ce contact.",
    )

    def action_sign_nda(self):
        for relation in self:
            relation.write({
                'nda_signed': True,
                'nda_date': fields.Datetime.now(),
            })
        return True

    def action_grant_workflow_access(self, role):
        """Ouvre l'accès moteur correspondant au niveau négocié.

        Passe par `instance.add_actor()` — l'unique porte de l'Extension 5 —
        plutôt que de créer la ligne d'acteur ici. Le niveau `teaser` n'ouvre
        rien : un teaser se lit sans accéder au dossier.
        """
        self.ensure_one()
        if self.access_level == 'teaser':
            raise UserError(_(
                "Un teaser ne donne pas accès au dossier. Relevez d'abord le "
                "niveau d'accès de cette relation."))
        user = self.partner_id.user_ids[:1]
        if not user:
            raise UserError(_(
                "%s n'a pas de compte utilisateur : impossible de lui ouvrir "
                "l'accès au dossier."
            ) % self.partner_id.display_name)
        return self.instance_id.add_actor(role, user, self.access_level)
