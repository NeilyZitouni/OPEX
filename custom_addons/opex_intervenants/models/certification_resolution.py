"""Rapprocher un libellé de certification, et arbitrer ce qui reste.

Le motif est celui de l'IA-2 pour les compétences, et il est repris **parce
que c'est le même problème** : un libellé lu dans un CV, un référentiel
canonique, et l'écart entre les deux.

Deux temps :

1. **correspondance exacte ou par synonyme**, sans appel IA. Gratuite,
   instantanée, déterministe — la majorité des cas ;
2. **proposition de l'IA avec sa confiance**, seulement pour ce que l'étape 1
   n'a pas su rattacher. Le code rendu est vérifié contre le catalogue.

Et une seule sortie pour le reste : la **file d'arbitrage**. Une certification
non rapprochée n'est pas jetée, et elle n'entre pas au profil non plus.

⚠ **L'IA ne crée jamais une certification au référentiel.** Sur un critère
éliminatoire, un référentiel qui s'enrichit tout seul est pire qu'un
référentiel incomplet : il se met à contenir des variantes proches, et
`resolve_label()` cesse alors de savoir laquelle choisir. L'ajout passe par
`action_add_to_catalogue()`, réservé au gestionnaire et journalisé.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

MATCHING_PROMPT = 'certification_matching'


class CertificationResolution(models.AbstractModel):
    """Le rapprochement en deux temps. N'écrit aucun profil."""

    _name = 'opex.certification.resolution'
    _description = "Rapprochement d'une certification vers le référentiel"

    @api.model
    def resolve_certifications(self, labels, profile=None, document=None,
                               use_ai=True):
        """Rapproche une liste de libellés. Rend une liste d'entrées.

        Chaque entrée porte :

        - `libelle` : ce qui a été lu ;
        - `certification_id` : l'identifiant du référentiel, ou False ;
        - `matched_on` : `referentiel`, `synonyme`, `ia`, ou False ;
        - `confiance_rapprochement` : 100 à l'étape 1, la valeur de l'IA à
          l'étape 2, 0 sinon ;
        - `arbitrage_id` : la ligne de file, quand il y en a une.

        La seule écriture est la file d'arbitrage : une question posée doit
        survivre à la fermeture de l'écran.
        """
        Synonyme = self.env['opex.certification.synonyme']
        resolved = []

        for label in labels or []:
            libelle = (label or '').strip() if isinstance(label, str) else (
                (label or {}).get('libelle'))
            if not libelle:
                continue

            entry = {
                'libelle': libelle,
                'certification_id': False,
                'matched_on': False,
                'confiance_rapprochement': 0,
                'arbitrage_id': False,
            }

            # Étape 1 — gratuite.
            certification = Synonyme.resolve_label(libelle)
            if certification:
                entry.update({
                    'certification_id': certification.id,
                    'matched_on': self._matched_on(certification, libelle),
                    'confiance_rapprochement': 100,
                })
                resolved.append(entry)
                continue

            # Étape 2 — payante, et seulement si elle est activée.
            suggestion = self._suggest(libelle) if use_ai else None
            if suggestion and suggestion.get('certification_id'):
                entry.update({
                    'certification_id': suggestion['certification_id'],
                    'matched_on': 'ia',
                    'confiance_rapprochement': suggestion.get('confiance', 0),
                })

            # Rapprochée ou non, une certification que l'étape 1 n'a pas
            # reconnue passe par la file. Aucune confiance ne dispense de ce
            # passage : le référentiel décide qui entre dans le vivier, et il
            # ne s'enrichit que par une décision humaine.
            arbitrage = self.env['opex.certification.arbitrage'].enqueue(
                libelle, profile=profile, document=document,
                suggestion=suggestion)
            entry['arbitrage_id'] = arbitrage.id if arbitrage else False
            resolved.append(entry)

        return resolved

    @api.model
    def _matched_on(self, certification, libelle):
        Synonyme = self.env['opex.certification.synonyme']
        if Synonyme._normalise(certification.name) == \
                Synonyme._normalise(libelle):
            return 'referentiel'
        return 'synonyme'

    @api.model
    def _suggest(self, libelle):
        """Demande un rapprochement à l'IA. Rend None si rien d'exploitable.

        Ne lève jamais et n'écrit rien. Une clé absente, un quota, une réponse
        illisible — le libellé part simplement en arbitrage sans suggestion,
        ce qui est l'état où il serait sans IA du tout.

        Le code rendu est **vérifié contre le catalogue**. L'accepter sur
        parole rattacherait une certification à un identifiant qui n'existe
        pas, ou pire à un qui existe et ne correspond pas — et sur un critère
        éliminatoire, cela se traduit par un candidat admis à tort.
        """
        import json

        Synonyme = self.env['opex.certification.synonyme']
        catalogue = Synonyme.catalogue_for_prompt()
        if not catalogue:
            return None

        payload = self.env['opex.ai.bridge']._ai_call_prompt(
            MATCHING_PROMPT,
            values={
                'libelle': libelle,
                'catalogue': json.dumps(catalogue, ensure_ascii=False,
                                        indent=1),
            },
        )
        if not payload:
            return None

        code = str(payload.get('code') or '').strip()
        confiance = self._as_percent(payload.get('confiance'))
        motif = str(payload.get('motif') or '').strip()

        certification = self._certification_for_code(code) if code else None
        if code and not certification:
            _logger.info(
                "opex_intervenants: rapprochement ignoré, code « %s » absent "
                "du catalogue de certifications pour « %s ».", code, libelle)

        return {
            'certification_id': certification.id if certification else False,
            'confiance': confiance,
            'motif': motif,
        }

    @api.model
    def _certification_for_code(self, code):
        Certification = self.env['opex.certification'].sudo()
        found = Certification.search([('code', '=', code)], limit=1)
        if found:
            return found
        if str(code).isdigit():
            return Certification.browse(int(code)).exists()
        return None

    @staticmethod
    def _as_percent(value):
        """Un entier de 0 à 100, ou 0.

        « 0.85 », « 85 % » et « élevée » : les deux premiers se rattrapent, le
        troisième vaut zéro — une confiance qu'on ne sait pas lire n'est pas
        une confiance haute.
        """
        try:
            number = float(str(value).strip().rstrip('%').replace(',', '.'))
        except (TypeError, ValueError):
            return 0
        if number <= 1:
            number *= 100
        return int(max(0, min(100, round(number))))


class CertificationArbitrage(models.Model):
    """La file des certifications à arbitrer — et son journal.

    La ligne ne disparaît pas après la décision : c'est elle qui dit qui a
    ajouté quoi au référentiel, quand, depuis quel profil et quel document.
    Sur un référentiel qui décide de l'éligibilité, savoir d'où vient chaque
    entrée n'est pas un luxe.
    """

    _name = 'opex.certification.arbitrage'
    _description = "Certification à arbitrer"
    _order = 'decision, create_date desc, id desc'

    name = fields.Char(string="Libellé lu", required=True, index=True)
    normalised = fields.Char(
        string="Forme normalisée",
        compute='_compute_normalised',
        store=True,
        index=True,
        readonly=True,
    )
    profile_id = fields.Many2one(
        'opex.innovation.expert.profile',
        string="Profil d'origine",
        ondelete='set null',
        index=True,
    )
    partner_id = fields.Many2one(
        related='profile_id.partner_id', string="Intervenant",
        store=True, readonly=True)
    source_document = fields.Char(string="Document d'origine")

    suggestion_id = fields.Many2one(
        'opex.certification',
        string="Rapprochement proposé",
        ondelete='set null',
        help="Proposé par l'IA, jamais appliqué : une proposition à 99 % "
             "reste une proposition.",
    )
    suggestion_confiance = fields.Integer(string="Confiance de l'IA")
    suggestion_motif = fields.Text(string="Justification de l'IA")

    decision = fields.Selection(
        [
            ('pending', "En attente"),
            ('linked', "Rattachée"),
            ('added', "Ajoutée au référentiel"),
            ('discarded', "Écartée"),
        ],
        string="Décision",
        default='pending',
        required=True,
        index=True,
    )
    certification_id = fields.Many2one(
        'opex.certification',
        string="Certification retenue",
        ondelete='set null',
        readonly=True,
    )
    decided_by = fields.Many2one('res.users', string="Arbitré par",
                                 readonly=True)
    decided_on = fields.Datetime(string="Arbitré le", readonly=True)
    decision_note = fields.Text(string="Note d'arbitrage")

    #: Une seule question en attente par libellé. Le même intitulé lu sur
    #: trois CV ne se pose qu'une fois.
    _pending_uniq = models.UniqueIndex(
        "(normalised) WHERE decision = 'pending'",
        "Ce libellé attend déjà un arbitrage.",
    )

    @api.depends('name')
    def _compute_normalised(self):
        Synonyme = self.env['opex.certification.synonyme']
        for ligne in self:
            ligne.normalised = Synonyme._normalise(ligne.name)

    @api.depends('name', 'decision')
    def _compute_display_name(self):
        libelles = dict(self._fields['decision'].selection)
        for ligne in self:
            ligne.display_name = "%s (%s)" % (
                ligne.name or '', libelles.get(ligne.decision, ''))

    @api.model
    def enqueue(self, label, profile=None, document=None, suggestion=None):
        """Dépose un libellé en file, ou rend la ligne qui l'attend déjà.

        `sudo()` : le dépôt est un effet de l'extraction, qui tourne sous des
        identités variées. Ce que cela ouvre est borné à ce modèle, et
        **déposer n'est pas décider** — les trois issues restent réservées au
        gestionnaire.
        """
        Synonyme = self.env['opex.certification.synonyme']
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
        }
        if suggestion:
            values.update({
                'suggestion_id': suggestion.get('certification_id') or False,
                'suggestion_confiance': suggestion.get('confiance') or 0,
                'suggestion_motif': suggestion.get('motif') or False,
            })
        return self.sudo().create(values)

    # ------------------------------------------------------------
    # Les trois issues
    # ------------------------------------------------------------

    def action_link(self, certification=None):
        """Rattache le libellé à une certification existante."""
        self.ensure_one()
        self._check_manager()
        cible = certification or self.suggestion_id
        if not cible:
            raise UserError(_(
                "Choisissez la certification à laquelle rattacher « %s », ou "
                "ajoutez-la au référentiel." % self.name))

        self._ensure_synonyme(cible)
        self.sudo().write({
            'decision': 'linked',
            'certification_id': cible.id,
            'decided_by': self.env.user.id,
            'decided_on': fields.Datetime.now(),
        })
        return cible

    def action_add_to_catalogue(self, porte='personne', organisme=None):
        """Crée la certification au référentiel du Module 1, et l'y rattache.

        **Le seul point d'écriture du module dans `opex.certification`.** Un
        test lit le source et refuse tout autre `create()` sur ce modèle : le
        flux doit rester nommé, pour qu'on sache dans six mois d'où viennent
        ces lignes.

        Le référentiel reste unique — c'est toute la leçon de D1. Un second
        catalogue rendrait le critère éliminatoire faux sans que rien ne le
        signale.
        """
        self.ensure_one()
        self._check_manager()
        if self.certification_id:
            return self.certification_id

        certification = self.env['opex.certification'].sudo().create({
            'name': (self.name or '').strip(),
            'porte': porte,
            'organisme': organisme or False,
        })
        # Le libellé d'origine devient synonyme : sans cela, une variante
        # d'écriture repartirait en arbitrage alors que la question vient
        # d'être tranchée.
        self._ensure_synonyme(certification)

        self.sudo().write({
            'decision': 'added',
            'certification_id': certification.id,
            'decided_by': self.env.user.id,
            'decided_on': fields.Datetime.now(),
        })
        return certification

    def action_discard(self):
        """Écarte le libellé : ce n'est pas une certification.

        Un CV mentionne des formations suivies, des outils maîtrisés, des
        adhésions. Les écarter est une réponse à part entière, et elle se
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

    def _check_manager(self):
        """Arbitrer est réservé au gestionnaire.

        Dans le **modèle** et pas seulement sur l'écran : ce modèle s'appelle
        aussi par script, par import et par requête forgée.
        `_is_missions_staff()` est LA fonction d'accès du module — la même que
        celle des routes et des `t-if` des tuiles.
        """
        if not self.env.user._is_missions_staff():
            raise UserError(_(
                "Arbitrer une certification est réservé au personnel des "
                "missions. Le référentiel décide de l'éligibilité aux appels ; "
                "il ne s'enrichit pas par le portail."))

    def _ensure_synonyme(self, certification):
        """Le libellé d'origine devient une écriture connue de la cible."""
        self.ensure_one()
        Synonyme = self.env['opex.certification.synonyme'].sudo()
        key = Synonyme._normalise(self.name)
        if not key or Synonyme.search_count([('normalised', '=', key)]):
            return False
        return Synonyme.create({
            'certification_id': certification.id,
            'name': (self.name or '').strip(),
            'origine': 'arbitrage',
        })
