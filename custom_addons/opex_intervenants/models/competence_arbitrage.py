"""La file d'arbitrage des compétences non rapprochées - §8.

Un libellé qu'aucune des deux étapes n'a su rattacher au référentiel n'est ni
perdu ni écrit quelque part en attendant : il atterrit ici, et un gestionnaire
tranche.

    « Une compétence non rapprochée part en file "à arbitrer" pour le
      gestionnaire, qui décide de l'ajouter au catalogue. C'est comme ça que la
      taxonomie s'enrichit, et jamais par une écriture automatique. »

LE FLUX D'ENRICHISSEMENT, DECIDE PLUTOT QUE DECOUVERT

L'arbitrage écrit dans `opex.innovation.competence`, c'est-à-dire dans le
référentiel du Module 2. C'est voulu - le référentiel doit rester unique, et
deux catalogues seraient la dette D1 en pire - mais un module qui écrit dans
le référentiel d'un autre est le genre de flux qu'on découvre six mois plus
tard en se demandant d'où viennent ces lignes. Trois garde-fous, donc :

- il passe par **une méthode nommée** de ce modèle, `action_add_to_catalogue`,
  et jamais par un `create()` dispersé. Un test lit le source du module et
  refuse tout autre point d'écriture ;
- il **journalise** qui a ajouté quoi et depuis quel dossier. La ligne
  d'arbitrage conserve la trace après la décision : elle est à la fois la file
  et le journal, et c'est ce qui évite un second récit de la même histoire ;
- il est **réservé au gestionnaire**. L'extraction ne peut pas enrichir le
  catalogue, même indirectement : elle ne fait que déposer dans la file.

POURQUOI `decision` N'EST PAS UN WORKFLOW

À arbitrer → rattachée / ajoutée / écartée. Trois issues, un seul acteur, un
seul moment, aucun chemin de retour, aucune condition, aucune notification.
C'est la ligne de partage que le CLAUDE.md du moteur pose pour
`roadmap.phase`, et que l'Extension 8 a appliquée à l'incident du §26.

Le champ s'appelle `decision` parce que c'en est une : quelqu'un a tranché.
`test_the_arbitration_is_a_decision_not_a_process` verrouille le critère - une
quatrième issue, un chemin de refus, et la conversation a lieu.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

DECISION_SELECTION = [
    ('pending', "À arbitrer"),
    ('linked', "Rattachée à une compétence existante"),
    ('added', "Ajoutée au catalogue"),
    ('discarded', "Écartée"),
]


class CompetenceArbitrage(models.Model):
    """Un libellé en attente d'arbitrage, puis la trace de sa décision."""

    _name = 'opex.competence.arbitrage'
    _description = "Compétence à arbitrer"
    _order = 'decision, create_date desc, id desc'

    name = fields.Char(
        string="Libellé lu", required=True, index=True,
        help="Tel qu'il figure dans le document. Jamais normalisé ici : "
             "c'est ce texte que le gestionnaire doit lire pour décider.")
    normalised = fields.Char(
        string="Forme normalisée", compute='_compute_normalised',
        store=True, index=True, readonly=True)

    profile_id = fields.Many2one(
        'opex.innovation.expert.profile',
        string="Profil d'origine",
        ondelete='cascade',
        index=True,
        help="Le dossier depuis lequel ce libellé a été lu. C'est la moitié "
             "du « depuis quel CV » que la traçabilité demande.")
    partner_id = fields.Many2one(
        related='profile_id.partner_id', string="Intervenant",
        store=True, readonly=True)
    source_document = fields.Char(
        string="Document d'origine",
        help="Le nom du fichier analysé. L'autre moitié du « depuis quel "
             "CV » : un profil peut avoir déposé plusieurs CV.")

    niveau_lu = fields.Char(string="Niveau lu")
    annees_lues = fields.Integer(string="Années lues")

    # --- Ce que l'IA a proposé, s'il y a eu un appel ------------------------
    suggestion_id = fields.Many2one(
        'opex.innovation.competence',
        string="Rapprochement proposé",
        ondelete='set null',
        help="Proposé par l'IA à l'étape 2. Une proposition, pas une "
             "décision : c'est le gestionnaire qui tranche.")
    suggestion_confiance = fields.Integer(
        string="Confiance de la proposition (%)",
        help="Rendue par l'IA avec sa proposition. Une confiance basse n'est "
             "pas une erreur : c'est l'information qui permet de trier.")
    suggestion_motif = fields.Text(string="Justification de l'IA")

    # --- La décision -------------------------------------------------------
    decision = fields.Selection(
        DECISION_SELECTION,
        string="Décision",
        default='pending',
        required=True,
        index=True,
        # Pas de `tracking` : ce modèle n'hérite pas de `mail.thread`, et
        # Odoo signale le paramètre comme inconnu. La traçabilité est portée
        # par les trois champs `decided_*`, qui disent qui a décidé quoi et
        # quand - c'est ce que la journalisation demandait, et un chatter
        # n'aurait rien ajouté.
        help="Trois issues, un seul acteur, aucun retour en arrière. C'est "
             "une décision, pas un processus - voir la docstring du modèle.",
    )
    competence_id = fields.Many2one(
        'opex.innovation.competence',
        string="Compétence retenue",
        ondelete='set null',
        readonly=True,
        help="Celle à laquelle le libellé a été rattaché, ou celle qui a été "
             "créée au catalogue.")

    decided_by = fields.Many2one(
        'res.users', string="Arbitré par", readonly=True)
    decided_on = fields.Datetime(string="Arbitré le", readonly=True)
    decision_note = fields.Text(string="Note d'arbitrage")

    #: Le même libellé lu sur deux CV différents ne fait qu'une ligne à
    #: arbitrer : c'est la même question, et la poser deux fois ferait deux
    #: réponses possiblement différentes.
    #:
    #: Un **index unique partiel**, et non une contrainte de table. La
    #: contrainte ne porte que sur les lignes en attente : une fois tranchées,
    #: elles restent en base comme journal, et le même libellé doit pouvoir y
    #: figurer plusieurs fois - une fois par décision.
    #:
    #: `models.Constraint` ne sait pas exprimer un `WHERE` : une contrainte de
    #: table est totale par nature. `EXCLUDE ... WHERE` le pourrait, mais
    #: demanderait l'extension `btree_gist` pour un simple `=`. L'index
    #: partiel est la forme native de ce besoin.
    _pending_uniq = models.UniqueIndex(
        "(normalised) WHERE decision = 'pending'",
        "Ce libellé est déjà en file d'arbitrage.",
    )

    @api.depends('name')
    def _compute_normalised(self):
        Synonyme = self.env['opex.competence.synonyme']
        for line in self:
            line.normalised = Synonyme._normalise(line.name)

    @api.depends('name', 'decision')
    def _compute_display_name(self):
        labels = dict(DECISION_SELECTION)
        for line in self:
            line.display_name = "%s (%s)" % (
                line.name or '', labels.get(line.decision, ''))

    # ------------------------------------------------------------
    # L'entrée en file
    # ------------------------------------------------------------

    @api.model
    def enqueue(self, label, profile=None, document=None, skill=None,
                suggestion=None):
        """Dépose un libellé en file, ou rend la ligne qui l'attend déjà.

        Idempotent sur la forme normalisée : un même libellé lu sur trois CV
        ne pose qu'une question. La ligne existante est enrichie du profil le
        plus récent seulement si elle n'en avait pas - on ne réécrit pas
        l'origine d'une question déjà posée.

        `sudo()` : le dépôt en file est un effet de l'extraction, qui peut
        tourner sous l'identité d'un gestionnaire comme d'un secrétariat. Ce
        que cela ouvre est borné à ce modèle, et **déposer n'est pas
        décider** - `action_add_to_catalogue` reste réservé au gestionnaire.
        """
        Synonyme = self.env['opex.competence.synonyme']
        key = Synonyme._normalise(label)
        if not key:
            return self.browse()

        existing = self.sudo().search(
            [('normalised', '=', key), ('decision', '=', 'pending')], limit=1)
        if existing:
            if profile and not existing.profile_id:
                existing.profile_id = profile.id
            return existing

        values = {
            'name': (label or '').strip(),
            'profile_id': profile.id if profile else False,
            'source_document': document or False,
            'niveau_lu': (skill or {}).get('niveau') or False,
            'annees_lues': (skill or {}).get('annees') or 0,
        }
        if suggestion:
            values.update({
                'suggestion_id': suggestion.get('competence_id') or False,
                'suggestion_confiance': suggestion.get('confiance') or 0,
                'suggestion_motif': suggestion.get('motif') or False,
            })
        return self.sudo().create(values)

    # ------------------------------------------------------------
    # Les trois issues
    # ------------------------------------------------------------

    def action_link(self, competence=None):
        """Rattache le libellé à une compétence existante, et crée le synonyme.

        C'est l'issue la plus fréquente et la plus utile : elle enseigne. Le
        synonyme créé fait que le même libellé sera reconnu à l'étape 1 la
        prochaine fois, sans appel IA et sans arbitrage. La file se vide
        d'elle-même à mesure qu'on s'en sert.
        """
        self.ensure_one()
        self._check_manager()
        competence = competence or self.suggestion_id
        if not competence:
            raise UserError(_(
                "Choisissez la compétence à laquelle rattacher « %s », ou "
                "ajoutez-la au catalogue.") % self.name)

        self._ensure_synonyme(competence)
        self.sudo().write({
            'decision': 'linked',
            'competence_id': competence.id,
            'decided_by': self.env.user.id,
            'decided_on': fields.Datetime.now(),
        })
        return True

    family_id = fields.Many2one(
        'opex.skill.family',
        string="Famille de rangement",
        help="Où classer la compétence si elle est ajoutée au catalogue. "
             "Renseignée avant de cliquer « Ajouter au catalogue » : une "
             "compétence créée sans famille part dans la file « À classer », "
             "et cette file-là, personne ne la vide.",
    )

    def action_add_to_catalogue(self, domaine=None, family=None):
        """Crée la compétence au référentiel du Module 2, et l'y rattache.

        **Le seul point d'écriture du module dans
        `opex.innovation.competence`.** Un test lit le source et refuse tout
        autre `create()` sur ce modèle : le flux doit rester nommé, pour qu'on
        sache dans six mois d'où viennent ces lignes.

        Le référentiel reste unique, et c'est la raison d'être de ce flux :
        deux catalogues seraient la dette D1 en pire - le matching comparerait
        des ensembles qui ne se croisent que par coïncidence de libellé.

        Ce qui est journalisé, et où : la ligne d'arbitrage conserve qui a
        décidé, quand, depuis quel profil et quel document. Elle ne disparaît
        pas après la décision - c'est elle, le journal.
        """
        self.ensure_one()
        self._check_manager()
        if self.competence_id:
            return self.competence_id

        # La famille du §8, prise de l'argument ou de la ligne d'arbitrage.
        # Elle porte son domaine, et c'est celui-là qui alimente le `Char`
        # hérité du Module 2 : sans cette recopie, l'écran du Module 2
        # afficherait une compétence sans domaine et quelqu'un le remplirait
        # en texte libre - ce que la hiérarchie existe pour éviter.
        famille = family or self.family_id
        competence = self.env['opex.innovation.competence'].sudo().create({
            'name': (self.name or '').strip(),
            'family_id': famille.id if famille else False,
            'domaine': (famille.domain_id.name if famille
                        else domaine or False),
        })
        # Le libellé d'origine devient synonyme de la compétence créée. Sans
        # cela, une variante d'écriture repartirait en arbitrage alors que la
        # question vient d'être tranchée.
        self._ensure_synonyme(competence)

        self.sudo().write({
            'decision': 'added',
            'competence_id': competence.id,
            'decided_by': self.env.user.id,
            'decided_on': fields.Datetime.now(),
        })
        return competence

    def action_discard(self):
        """Écarte le libellé : ce n'est pas une compétence.

        Un CV contient des intitulés de poste, des noms d'outils, des mentions
        de diplôme. Les écarter est une réponse à part entière, et elle se
        garde : le même libellé reviendra d'un autre CV, et la trace évite de
        rejuger.
        """
        self.ensure_one()
        self._check_manager()
        self.sudo().write({
            'decision': 'discarded',
            'decided_by': self.env.user.id,
            'decided_on': fields.Datetime.now(),
        })
        return True

    # ------------------------------------------------------------
    # Garde-fous
    # ------------------------------------------------------------

    def _check_manager(self):
        """Arbitrer est réservé au gestionnaire.

        Le contrôle est ici et pas seulement sur l'écran : une action de
        modèle s'appelle aussi par script, par import et par requête forgée.
        `_is_missions_staff()` est LA fonction d'accès du module - la même que
        celle des routes et des `t-if` des tuiles.
        """
        if not self.env.user._is_missions_staff():
            raise UserError(_(
                "L'arbitrage des compétences est réservé au personnel des "
                "missions : c'est lui qui tient le référentiel."))
        return True

    def _ensure_synonyme(self, competence):
        """Crée le synonyme s'il n'existe pas déjà.

        Silencieux si le libellé normalisé est déjà pris : la contrainte
        d'unicité lèverait, et un arbitrage ne doit pas échouer parce que
        quelqu'un a saisi le synonyme à la main entre-temps.
        """
        self.ensure_one()
        Synonyme = self.env['opex.competence.synonyme'].sudo()
        key = Synonyme._normalise(self.name)
        if not key or Synonyme.search_count([('normalised', '=', key)]):
            return Synonyme.browse()
        # Un libellé identique au nom de la compétence n'a pas besoin de
        # synonyme : l'étape 1 le reconnaît déjà sur le référentiel.
        if key == Synonyme._normalise(competence.name):
            return Synonyme.browse()
        return Synonyme.create({
            'competence_id': competence.id,
            'name': (self.name or '').strip(),
            'origine': 'arbitrage',
        })
