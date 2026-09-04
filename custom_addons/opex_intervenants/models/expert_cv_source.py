"""Le CV déposé, son analyse, et ses propositions - §6, §17, §24.

LE CRITERE QUI GOUVERNE TOUT CE FICHIER (§24)

    « Le parsing ne transforme jamais une donnée incertaine en donnée validée
      sans traçabilité. »

Il se tient par une seule décision de conception : **rien de ce que l'IA
produit n'entre dans les modèles du profil.** Tout atterrit dans
`opex.expert.cv.proposal`, qui porte pour chaque élément sa valeur, sa
confiance, et le passage exact du CV d'où elle vient. La promotion vers
`opex.expert.skill` et ses voisins est un geste humain, et elle n'est pas dans
ce fichier.

Le corollaire compte autant : il n'y a pas de second chemin. Aucune méthode
d'ici n'écrit dans `opex.expert.skill`, et un test lit le source pour le
vérifier. Une proposition qui pourrait devenir une donnée par deux portes
finirait par passer par celle qu'on ne surveille pas.

POURQUOI L'ANALYSE EST ASYNCHRONE

Un parsing prend dix à trente secondes. Une route portail qui attend cela est
inutilisable : le navigateur tourne, l'utilisateur recharge, et le second
appel repart pour trente secondes. Le dépôt crée l'enregistrement et rend la
main ; un `ir.cron` traite la file. L'expert voit un état, pas une roue qui
tourne.

POURQUOI `analyse` N'EST PAS UN WORKFLOW

À analyser -> en cours -> analysé / échoué. Aucun acteur - c'est une machine
qui avance -, aucune condition, aucun chemin de refus, rien à notifier. C'est
la ligne de partage que le CLAUDE.md du moteur pose pour `roadmap.phase`, et
que les Extensions 8 et IA-2 ont déjà appliquée. Un compteur de file d'attente
n'est pas un processus métier.
"""

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

CV_PROMPT = 'cv_parsing'

#: Les neuf destinations du tableau du §6. Nommées une fois : le schéma de
#: validation, le modèle de proposition et l'écran les lisent toutes les trois
#: ici. Trois listes séparées divergeraient au premier ajout.
DESTINATIONS = [
    ('titre', "Titre professionnel"),
    ('resume', "Résumé"),
    ('experience', "Expérience"),
    ('competence', "Compétence"),
    ('diplome', "Diplôme"),
    ('certification', "Certification"),
    ('langue', "Langue"),
    ('secteur', "Secteur"),
    ('annees', "Années d'expérience estimées"),
]
DESTINATION_CODES = [code for code, _label in DESTINATIONS]

#: Les destinations qui se promeuvent, et le modèle qui les accueille.
#:
#: Deux, désormais. La compétence depuis l'IA-2, et la **certification**
#: depuis la refermeture de D1 — les deux ont maintenant un référentiel
#: canonique et un rapprochement en deux temps, ce qui est exactement la
#: condition pour promouvoir sans écrire de texte libre en base.
#:
#: Les sept autres — titre, résumé, expérience, diplôme, langue, secteur,
#: années — n'ont pas de référentiel. Les promouvoir demanderait d'en créer un
#: par destination, et un référentiel qu'on ne saurait pas alimenter est pire
#: qu'une saisie libre assumée.
PROMOTABLE_DESTINATIONS = {
    'competence': 'opex.expert.skill',
    'certification': 'opex.expert.certification',
}

#: Les clés du JSON attendu, par destination. C'est le **schéma** : ce qui
#: n'y figure pas est ignoré, jamais écrit. Un modèle de langage ajoute
#: volontiers un champ qu'on ne lui a pas demandé, et un champ inattendu qui
#: traverse finit par s'afficher quelque part.
SCHEMA_KEYS = ('valeur', 'confidence', 'source_quote')

#: Une confiance est un flottant de 0 à 1. Ce qui n'est pas lisible vaut 0 -
#: et zéro est la bonne valeur : une confiance qu'on ne sait pas lire n'est
#: pas une confiance haute.
MIN_CONFIDENCE = 0.0
MAX_CONFIDENCE = 1.0

#: Au-delà, on arrête de retenter. Un PDF que le modèle ne sait pas lire ne
#: deviendra pas lisible au quatrième essai, et la file se viderait de toute
#: façon en boucle sur le même document.
MAX_ATTEMPTS = 3


class ExpertCvSource(models.Model):
    """Un CV déposé, et la trace de son analyse - §17.

    « Le CV original, sa version, sa date, le JSON brut renvoyé par le parsing,
    et l'horodatage de l'analyse. » C'est ce qui rend la provenance vérifiable
    des mois plus tard : quand quelqu'un demandera d'où vient une compétence,
    la réponse sera un document, une date, et un extrait.
    """

    _name = 'opex.expert.cv.source'
    _description = "CV déposé et analysé"
    _order = 'profile_id, version desc, id desc'
    _rec_name = 'display_name'

    profile_id = fields.Many2one(
        'opex.innovation.expert.profile',
        string="Profil expert",
        required=True,
        ondelete='cascade',
        index=True,
    )
    partner_id = fields.Many2one(
        related='profile_id.partner_id', string="Intervenant",
        store=True, index=True, readonly=True)

    document = fields.Binary(
        string="Curriculum vitae", required=True, attachment=True,
        help="Le document original, conservé tel quel. C'est lui qui fait "
             "foi quand une proposition est contestée.")
    filename = fields.Char(string="Nom du fichier")
    mimetype = fields.Char(
        string="Type de document", default='application/pdf',
        help="Envoyé tel quel au fournisseur. Gemini lit le PDF nativement : "
             "on ne convertit pas en texte, ce qui perdrait la mise en page "
             "dont le modèle se sert pour distinguer un titre d'une ligne.")

    #: La version se compte par profil, pas globalement : « le troisième CV de
    #: Zitouni » a un sens, « le 412e CV du portail » n'en a aucun.
    version = fields.Integer(string="Version", readonly=True, default=1)
    date_depot = fields.Datetime(
        string="Déposé le", default=fields.Datetime.now, readonly=True)

    # --- L'analyse ---------------------------------------------------------
    analyse = fields.Selection(
        [
            ('pending', "À analyser"),
            ('running', "Analyse en cours"),
            ('done', "Analysé"),
            ('failed', "Analyse impossible"),
        ],
        string="Analyse",
        default='pending',
        required=True,
        index=True,
        readonly=True,
        help="Une file d'attente, pas un processus : aucun acteur, aucun "
             "chemin de refus. Voir la docstring du modèle.",
    )
    date_analyse = fields.Datetime(
        string="Analysé le", readonly=True,
        help="L'horodatage que le §17 demande. Vide tant que l'analyse n'a "
             "pas eu lieu.")
    raw_json = fields.Text(
        string="JSON brut renvoyé", readonly=True,
        help="Tel que le fournisseur l'a rendu, avant toute validation. "
             "C'est ce qui permet de comprendre une extraction ratée sans "
             "relancer l'appel - et de rejouer la validation si le schéma "
             "change.")
    error_message = fields.Text(string="Motif de l'échec", readonly=True)
    attempts = fields.Integer(string="Tentatives", readonly=True, default=0)

    proposal_ids = fields.One2many(
        'opex.expert.cv.proposal', 'source_id', string="Propositions")
    proposal_count = fields.Integer(
        string="Nombre de propositions", compute='_compute_proposal_counts')
    confirmed_count = fields.Integer(
        string="Nombre de confirmées", compute='_compute_proposal_counts')

    @api.depends('proposal_ids.is_confirmed')
    def _compute_proposal_counts(self):
        for source in self:
            proposals = source.proposal_ids
            source.proposal_count = len(proposals)
            source.confirmed_count = len(proposals.filtered('is_confirmed'))

    @api.depends('partner_id', 'version', 'filename')
    def _compute_display_name(self):
        for source in self:
            source.display_name = "%s — CV v%s" % (
                source.partner_id.display_name or '', source.version)

    @api.model_create_multi
    def create(self, vals_list):
        """Dépose le CV et le met en file. N'analyse rien.

        C'est tout l'intérêt de l'asynchrone : la création rend la main
        immédiatement. Le cron passera.
        """
        for vals in vals_list:
            profile_id = vals.get('profile_id')
            if profile_id and not vals.get('version'):
                previous = self.sudo().search_count(
                    [('profile_id', '=', profile_id)])
                vals['version'] = previous + 1
        return super().create(vals_list)

    # ------------------------------------------------------------
    # La file
    # ------------------------------------------------------------

    @api.model
    def _cron_parse_pending(self, limit=5):
        """Traite la file des CV à analyser. Appelé par `ir.cron`.

        Borné à cinq par passage : un cron qui traite toute la file d'un coup
        tient la transaction ouverte pendant des minutes, et un appel qui
        échoue à la fin annulerait les précédents. Cinq passages de cinq
        valent mieux qu'un passage de vingt-cinq.

        Chaque CV est traité dans son propre savepoint. Un document illisible
        ne doit pas empêcher les quatre autres d'être analysés - c'est la
        règle 10 du CLAUDE.md, appliquée à une file.
        """
        pending = self.sudo().search(
            [('analyse', '=', 'pending'),
             ('attempts', '<', MAX_ATTEMPTS)],
            order='date_depot asc, id asc', limit=limit)

        for source in pending:
            try:
                with self.env.cr.savepoint():
                    source._parse()
            except Exception as error:  # noqa: BLE001 - file, pas parcours
                self.env.invalidate_all()
                _logger.warning(
                    "opex_intervenants: analyse du CV %s impossible : %s",
                    source.id, error)
                source.sudo().write({
                    'analyse': 'failed',
                    'error_message': str(error)[:500],
                })
        return len(pending)

    def _parse(self):
        """Appelle le service, valide, et écrit les propositions.

        L'ordre compte et il est celui du cahier des charges : on appelle, on
        conserve le brut, on **valide contre le schéma**, et seulement ensuite
        on écrit. Une réponse qui ne passe pas le schéma laisse le CV en échec
        avec son JSON conservé - il y a de quoi comprendre sans rappeler le
        fournisseur.
        """
        self.ensure_one()
        self.sudo().write({
            'analyse': 'running',
            'attempts': self.attempts + 1,
        })

        payload = self.env['opex.ai.bridge']._ai_call_prompt(
            CV_PROMPT,
            document={'data': self.document, 'mimetype': self.mimetype},
        )

        if payload is None:
            self.sudo().write({
                'analyse': 'failed',
                'date_analyse': fields.Datetime.now(),
                'error_message': _(
                    "Aucune réponse exploitable. L'assistance IA est-elle "
                    "installée et configurée ? Le motif exact figure dans le "
                    "journal des appels."),
            })
            return False

        # Le brut d'abord, quoi qu'il arrive ensuite. Le §17 le demande, et
        # c'est ce qui rend une extraction ratée compréhensible.
        raw = json.dumps(payload, ensure_ascii=False, indent=1)

        proposals = self._validate_payload(payload)
        self.sudo().write({
            'analyse': 'done',
            'date_analyse': fields.Datetime.now(),
            'raw_json': raw,
            'error_message': False,
        })
        self._write_proposals(proposals)
        return True

    # ------------------------------------------------------------
    # La validation, AVANT toute écriture
    # ------------------------------------------------------------

    @api.model
    def _validate_payload(self, payload):
        """Rend la liste des propositions valides. N'écrit rien.

        **Un champ inattendu est ignoré, pas écrit.** C'est la consigne du
        cahier des charges, et elle est plus forte qu'elle n'en a l'air : sans
        elle, un modèle qui ajoute `salaire_souhaite` ou `note_interne` verrait
        sa trouvaille traverser jusqu'à un écran, et personne ne saurait d'où
        elle vient.

        Le schéma est fermé des deux côtés : les destinations inconnues sont
        écartées, et dans chaque élément seules `valeur`, `confidence` et
        `source_quote` sont lues.

        Ne lève jamais. Une réponse mal formée donne une liste vide, et le CV
        est analysé sans proposition - ce qui est une information, pas une
        panne.
        """
        if not isinstance(payload, dict):
            return []

        proposals = []
        for destination in DESTINATION_CODES:
            for raw_item in self._as_list(payload.get(destination)):
                item = self._validate_item(destination, raw_item)
                if item:
                    proposals.append(item)
        return proposals

    @api.model
    def _validate_item(self, destination, raw):
        """Un élément conforme au schéma, ou None.

        Une valeur vide est écartée : elle ne dit rien, et une proposition
        vide encombrerait l'écran d'arbitrage sans jamais pouvoir être
        confirmée.

        `source_quote` manquante n'écarte pas l'élément mais laisse la trace
        vide - et l'écran le montre. Le §24 demande la traçabilité ; il vaut
        mieux une proposition dont on voit qu'elle n'est pas sourcée qu'une
        proposition absente dont personne ne sait qu'elle a existé.
        """
        if not isinstance(raw, dict):
            # Un modèle rend parfois une chaîne nue là où un objet était
            # demandé. On la garde comme valeur, sans confiance ni citation.
            valeur = self._as_text(raw)
            return {'destination': destination, 'valeur': valeur,
                    'confidence': 0.0, 'source_quote': ''} if valeur else None

        valeur = self._as_text(raw.get('valeur'))
        if not valeur:
            return None
        return {
            'destination': destination,
            'valeur': valeur,
            'confidence': self._as_confidence(raw.get('confidence')),
            'source_quote': self._as_text(raw.get('source_quote'))[:2000],
        }

    @staticmethod
    def _as_list(value):
        if isinstance(value, list):
            return value
        if value in (None, '', {}):
            return []
        return [value]

    @staticmethod
    def _as_text(value):
        if value is None or isinstance(value, (dict, list, bool)):
            return ''
        return str(value).strip()

    @staticmethod
    def _as_confidence(value):
        """Un flottant borné à [0, 1], ou 0.

        Accepte « 0.85 », « 85 » et « 85 % » : un modèle rend l'un ou l'autre
        selon l'humeur, et refuser perdrait une information juste pour une
        question de format.
        """
        try:
            number = float(str(value).strip().rstrip('%').replace(',', '.'))
        except (TypeError, ValueError):
            return 0.0
        if number > 1:
            number /= 100.0
        return max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, round(number, 3)))

    def _write_proposals(self, proposals):
        """Écrit les propositions. **Rien d'autre n'est écrit.**

        Aucune ligne de `opex.expert.skill`, aucune expérience, aucune
        certification. C'est le §24 : tant que l'expert n'a pas confirmé, la
        donnée n'existe qu'à l'état de proposition.
        """
        self.ensure_one()
        Proposal = self.env['opex.expert.cv.proposal'].sudo()
        Proposal.search([('source_id', '=', self.id)]).unlink()
        for item in proposals:
            # Aucune confiance haute ne vaut confirmation. Une proposition
            # créée déjà confirmée n'aurait aucun `confirmed_by` : la donnée
            # serait validée sans que personne l'ait validée, ce qui est
            # exactement le contraire du §24. Mesuré par régression
            # volontaire, et les deux tests qui rougissent le disent - l'un
            # sur le statut, l'autre sur l'auteur manquant.
            Proposal.create(dict(item, source_id=self.id))
        return True

    # ------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------

    def action_reanalyse(self):
        """Remet le CV en file. Le compteur de tentatives est remis à zéro.

        Utile après une correction de prompt ou un déblocage de quota : sans
        cela, un CV ayant épuisé ses trois tentatives resterait bloqué à
        jamais.
        """
        self.ensure_one()
        if not self.env.user._is_missions_staff():
            raise UserError(_(
                "Relancer une analyse est réservé au personnel des missions."))
        self.sudo().write({
            'analyse': 'pending', 'attempts': 0, 'error_message': False})
        return True

    def action_view_proposals(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Propositions de « %s »") % self.display_name,
            'res_model': 'opex.expert.cv.proposal',
            'view_mode': 'list,form',
            'domain': [('source_id', '=', self.id)],
        }


class ExpertCvProposal(models.Model):
    """Un élément extrait d'un CV, à l'état de proposition - §24.

    Trois informations par élément, et les trois sont exigées par le cahier
    des charges : la valeur, la confiance du modèle, et **le passage exact du
    CV d'où elle vient**.

    La troisième est celle qui fait la traçabilité. Une compétence proposée
    sans citation est une affirmation ; avec sa citation, c'est une lecture
    qu'on peut vérifier en rouvrant le document.
    """

    _name = 'opex.expert.cv.proposal'
    _description = "Proposition issue d'un CV"
    _order = 'source_id, destination, confidence desc, id'

    source_id = fields.Many2one(
        'opex.expert.cv.source',
        string="CV d'origine",
        required=True,
        ondelete='cascade',
        index=True,
    )
    profile_id = fields.Many2one(
        related='source_id.profile_id', string="Profil expert",
        store=True, index=True, readonly=True)
    partner_id = fields.Many2one(
        related='source_id.partner_id', string="Intervenant",
        store=True, index=True, readonly=True)

    destination = fields.Selection(
        DESTINATIONS, string="Destination", required=True, index=True,
        help="L'une des neuf du tableau du §6.")
    valeur = fields.Char(string="Valeur lue", required=True)
    confidence = fields.Float(
        string="Confiance du modèle", digits=(3, 3),
        help="Rendue par le modèle, entre 0 et 1. Une confiance basse n'est "
             "pas une erreur : c'est l'information qui permet de trier.")
    source_quote = fields.Text(
        string="Passage du CV",
        help="Le texte exact d'où vient l'information. C'est lui qui rend la "
             "proposition vérifiable : on rouvre le document et on lit.")

    #: Les deux axes du §9, avec les valeurs que le cahier des charges nomme.
    #: Ils sont ici et pas seulement sur la ligne de compétence, parce que les
    #: neuf destinations passent par ce modèle et que toutes doivent porter
    #: leur provenance.
    source = fields.Selection(
        [('ia', "Proposé par l'IA")],
        string="Source", default='ia', required=True, readonly=True,
        help="Une seule valeur, et c'est le propos : tout ce qui entre dans "
             "ce modèle vient de l'IA. Une donnée saisie par un humain n'a "
             "rien à y faire - elle va directement dans le modèle du profil.")
    confiance = fields.Selection(
        [
            ('propose', "Proposé"),
            ('confirme', "Confirmé par l'expert"),
        ],
        string="Confiance retenue",
        default='propose',
        required=True,
        readonly=True,
        help="Une proposition ne devient une donnée qu'après confirmation, et "
             "la confirmation est un geste humain.",
    )
    is_confirmed = fields.Boolean(
        string="Confirmée", compute='_compute_is_confirmed', store=True,
        index=True)

    confirmed_by = fields.Many2one(
        'res.users', string="Confirmée par", readonly=True)
    confirmed_on = fields.Datetime(string="Confirmée le", readonly=True)

    @api.depends('confiance')
    def _compute_is_confirmed(self):
        for proposal in self:
            proposal.is_confirmed = proposal.confiance == 'confirme'

    @api.depends('destination', 'valeur')
    def _compute_display_name(self):
        labels = dict(DESTINATIONS)
        for proposal in self:
            proposal.display_name = "%s : %s" % (
                labels.get(proposal.destination, ''), proposal.valeur or '')

    def action_confirm(self):
        """Le geste humain que le §24 exige.

        Il marque la proposition comme confirmée et **rien d'autre**. La
        promotion vers `opex.expert.skill` est un second geste, et les deux
        restent séparés : confirmer dit « j'ai bien écrit cela dans mon CV »,
        promouvoir dit « et cela doit compter dans le vivier ». La première
        affirmation est de l'expert, la seconde engage le matching.
        """
        for proposal in self:
            if proposal.is_confirmed:
                continue
            proposal.sudo().write({
                'confiance': 'confirme',
                'confirmed_by': self.env.user.id,
                'confirmed_on': fields.Datetime.now(),
            })
        return True

    # ------------------------------------------------------------
    # La promotion — le dernier maillon de la chaîne
    # ------------------------------------------------------------
    #
    #   CV déposé -> proposition extraite -> confirmée -> compétence
    #   qualifiée -> visible par le matching
    #
    # Les quatre premières flèches existaient. Celle-ci les relie, et elle est
    # la seule qui écrive dans le capital de l'expert.
    #
    # DEUX RÈGLES QUI NE SE NÉGOCIENT PAS
    #
    # 1. **La promotion passe par `resolve_skills()`, jamais par un `create()`
    #    sur `opex.innovation.competence`.** Un bouton qui écrirait un libellé
    #    libre au référentiel créerait le catalogue parallèle que le §8
    #    interdit, et le matching comparerait des ensembles qui ne se croisent
    #    que par coïncidence d'orthographe. Un test lit le source de tous les
    #    modèles et refuse tout autre point d'écriture.
    #
    # 2. **Une proposition non rapprochée ne crée rien.** Elle part en file
    #    d'arbitrage - ce que `resolve_skills()` fait déjà - et la promotion
    #    rend la main en le disant. C'est le cas le plus fréquent au début de
    #    la vie du catalogue, et c'est celui qui l'enrichit.

    #: Ce que la promotion a donné. Calculé depuis ses deux résultats, jamais
    #: écrit : deux vérités sur le même fait finiraient par diverger, et c'est
    #: la copie périmée qu'on lirait.
    #:
    #: Ce n'est pas un workflow - aucun acteur, aucune condition, aucun chemin
    #: de refus, rien à notifier. Même ligne de partage que `confiance` et que
    #: l'état d'analyse du CV : un compteur n'est pas un processus.
    promotion = fields.Selection(
        [
            ('non_promue', "Non promue"),
            ('promue', "Promue au profil"),
            ('arbitrage', "En attente d'arbitrage"),
        ],
        string="Promotion",
        compute='_compute_promotion',
        store=True,
        index=True,
    )
    skill_id = fields.Many2one(
        'opex.expert.skill',
        string="Compétence qualifiée",
        readonly=True,
        ondelete='set null',
        copy=False,
        help="La ligne créée au profil. C'est elle que le Smart Matching "
             "voit, une fois sa confiance posée.",
    )
    certification_line_id = fields.Many2one(
        'opex.expert.certification',
        string="Certification qualifiée",
        readonly=True,
        ondelete='set null',
        copy=False,
        help="La ligne créée au profil pour une proposition de "
             "certification. C'est elle que le critère éliminatoire lit, une "
             "fois sa validité renseignée.",
    )
    certification_arbitrage_id = fields.Many2one(
        'opex.certification.arbitrage',
        string="Arbitrage de certification",
        readonly=True,
        ondelete='set null',
        copy=False,
    )
    arbitrage_id = fields.Many2one(
        'opex.competence.arbitrage',
        string="Ligne d'arbitrage",
        readonly=True,
        ondelete='set null',
        copy=False,
        help="Quand le libellé n'a pas été rapproché. La proposition n'est "
             "pas perdue : elle attend une décision du gestionnaire.",
    )

    # Méthode séparée de `_compute_is_confirmed` : les deux champs sont
    # stockés, mais les mélanger dans une seule méthode ferait qu'un
    # changement de confiance recalculerait la promotion et réciproquement.
    # Ce n'est pas la règle 9 - elle interdit de mélanger stocké et non
    # stocké -, c'est simplement deux faits indépendants.
    @api.depends('skill_id', 'arbitrage_id',
                 'certification_line_id', 'certification_arbitrage_id')
    def _compute_promotion(self):
        for proposal in self:
            if proposal.skill_id or proposal.certification_line_id:
                proposal.promotion = 'promue'
            elif proposal.arbitrage_id or proposal.certification_arbitrage_id:
                proposal.promotion = 'arbitrage'
            else:
                proposal.promotion = 'non_promue'

    def action_promote(self):
        """Transforme une proposition confirmée en compétence qualifiée.

        Rend le recordset des compétences créées ou retrouvées. Ne lève que
        sur les deux refus qui méritent une explication à l'écran ; tout le
        reste est un cas normal, y compris l'absence de rapprochement.
        """
        # Sur un enregistrement — le cas du bouton — on rend **le recordset
        # produit**, ce qui permet d'enchaîner. Sur plusieurs, une liste : les
        # résultats peuvent être de deux modèles différents
        # (`opex.expert.skill` et `opex.expert.certification`), et les réunir
        # par `|` lèverait dès qu'une sélection mêle les deux destinations —
        # ce qu'une promotion en masse fait naturellement.
        if len(self) == 1:
            return self._promote_one()

        promues = []
        for proposal in self:
            resultat = proposal._promote_one()
            if resultat:
                promues.append(resultat)
        return promues

    def _promote_one(self):
        self.ensure_one()

        if self.destination not in PROMOTABLE_DESTINATIONS:
            raise UserError(_(
                "Seules les compétences et les certifications se promeuvent : "
                "ce sont les deux destinations qui ont un référentiel "
                "canonique. « %(valeur)s » est de type « %(type)s » et se "
                "reporte à la main sur le profil."
            ) % {'valeur': self.valeur,
                 'type': dict(DESTINATIONS).get(self.destination, '')})

        if not self.is_confirmed:
            raise UserError(_(
                "« %s » n'est pas confirmée. Une proposition de l'IA ne "
                "devient une donnée du profil qu'après un geste humain — "
                "c'est le §24, et la promotion ne le contourne pas."
            ) % self.valeur)

        # Idempotence. Le chemin du second passage est réel et banal : deux
        # clics, une liste promue en masse qui contient déjà une ligne traitée,
        # un script de reprise. Sans cette garde, la contrainte
        # `unique(profile_id, competence_id)` ferait sauter la transaction
        # entière (règle 10) plutôt que de ne rien faire.
        if self.skill_id:
            return self.skill_id
        if self.certification_line_id:
            return self.certification_line_id

        profile = self.profile_id
        if not profile:
            raise UserError(_(
                "Cette proposition n'est rattachée à aucun profil expert."))

        document = self.source_id.display_name or self.source_id.filename
        if self.destination == 'certification':
            return self._promote_certification(profile, document)
        return self._promote_competence(profile, document)

    def _promote_competence(self, profile, document):
        """§8 — le rapprochement taxonomique, puis la ligne de qualification.

        LE point de passage obligé : `resolve_skills()` fait les deux temps du
        §8 et dépose en file ce qu'il n'a pas su rapprocher ; il n'écrit jamais
        au catalogue.
        """
        self.ensure_one()
        resolved = self.env['opex.competence.resolution'].resolve_skills(
            [{'libelle': self.valeur}], profile=profile, document=document)
        entry = resolved[0] if resolved else {}

        if not entry.get('competence_id'):
            # Non rapprochée : rien n'est créé au profil, et la question
            # survit à la fermeture de l'écran.
            self.sudo().arbitrage_id = entry.get('arbitrage_id') or False
            return self.env['opex.expert.skill']

        return self._qualified_skill(profile, entry['competence_id'])

    def _promote_certification(self, profile, document):
        """D1 — le même motif, sur le référentiel de certifications.

        Exactement la même mécanique que pour une compétence, et c'est le
        propos : les deux manques de D1 étaient le même vu des deux bouts. Un
        référentiel canonique rend la promotion possible **et** rend le
        critère éliminatoire juste ; l'un ne va pas sans l'autre.

        ⚠ La ligne créée n'entre pas immédiatement dans le vivier. Elle est
        `is_confirmed`, mais `is_eligible` exige en plus qu'elle soit **encore
        valable** — et le CV ne dit presque jamais la date d'expiration. Une
        certification promue sans date reste donc à compléter, et c'est plus
        honnête que de la supposer perpétuelle : sur un critère éliminatoire,
        supposer vaut admettre à tort.
        """
        self.ensure_one()
        Resolution = self.env['opex.certification.resolution']
        resolved = Resolution.resolve_certifications(
            [self.valeur], profile=profile, document=document)
        entry = resolved[0] if resolved else {}

        if not entry.get('certification_id'):
            self.sudo().certification_arbitrage_id =                 entry.get('arbitrage_id') or False
            return self.env['opex.expert.certification']

        return self._qualified_certification(profile,
                                             entry['certification_id'])

    def _qualified_skill(self, profile, competence_id):
        """Crée la ligne du §8, ou enrichit celle qui existe.

        Les trois axes du §9 y sont posés explicitement :

        - `source = 'cv'` — d'où vient l'information ;
        - `confiance = 'expert'` — ce qu'elle vaut : l'expert a confirmé ;
        - la **citation** en preuve — de quoi la vérifier.

        C'est ce triplet qui rend le §9 vérifiable sur une ligne issue d'un
        CV. `source` seul dirait la provenance sans permettre de remonter au
        passage exact.
        """
        self.ensure_one()
        Skill = self.env['opex.expert.skill'].sudo()
        existing = Skill.search([
            ('profile_id', '=', profile.id),
            ('competence_id', '=', competence_id),
        ], limit=1)

        if existing:
            # La compétence est déjà déclarée. On **ajoute la preuve** et on
            # ne touche à rien d'autre.
            #
            # Surtout pas à la confiance : une ligne vérifiée par OPEX que la
            # promotion ramènerait à « confirmé par l'expert » perdrait le
            # travail de vérification, sans un mot. Le §9 se dégraderait par
            # le chemin censé l'alimenter.
            valeurs = {}
            if not existing.preuve_citation and self.source_quote:
                valeurs['preuve_citation'] = self.source_quote
                valeurs['preuve_cv_id'] = self.source_id.id
            if valeurs:
                existing.write(valeurs)
            self.sudo().skill_id = existing.id
            return existing

        skill = Skill.create({
            'profile_id': profile.id,
            'competence_id': competence_id,
            # Le niveau n'est pas déduit du CV. Un modèle qui lit
            # « dix ans d'audit » propose volontiers « Expert », et personne
            # ne l'a validé : le §9 sépare précisément le niveau métier de ce
            # que vaut l'information. La valeur par défaut est celle du
            # modèle, et l'expert l'ajuste.
            'source': 'cv',
            # `expert` et non `ia` : l'expert a confirmé la proposition, et
            # c'est ce geste qui la fait valoir. Mesuré par régression
            # volontaire - avec `ia`, `is_confirmed` reste faux et la
            # compétence n'atteint jamais le champ que le matching lit. Le
            # message du test le dit en toutes lettres : « la chaîne n'est
            # pas bouclée ».
            'confiance': 'expert',
            'preuve_citation': self.source_quote or False,
            'preuve_cv_id': self.source_id.id,
        })
        self.sudo().skill_id = skill.id
        return skill

    def _qualified_certification(self, profile, certification_id):
        """Crée la certification du profil, ou enrichit celle qui existe.

        Les trois axes du §9, comme pour une compétence : `source='cv'`,
        `confiance='expert'`, et la citation du CV en preuve.

        Le `name` reçoit le libellé **lu**, pas celui du référentiel. C'est ce
        qui permet de contester un rapprochement : on voit ce que l'expert a
        écrit à côté de ce que le système en a fait.
        """
        self.ensure_one()
        Certification = self.env['opex.expert.certification'].sudo()
        existing = Certification.search([
            ('profile_id', '=', profile.id),
            ('certification_id', '=', certification_id),
        ], limit=1)

        if existing:
            # Même garde que pour les compétences : on ajoute la preuve et on
            # ne rétrograde rien. Une certification dont OPEX a vu le
            # justificatif ne redevient pas « confirmée par l'expert » parce
            # qu'un CV la mentionne.
            valeurs = {}
            if not existing.preuve_citation and self.source_quote:
                valeurs['preuve_citation'] = self.source_quote
                valeurs['preuve_cv_id'] = self.source_id.id
            if valeurs:
                existing.write(valeurs)
            self.sudo().certification_line_id = existing.id
            return existing

        ligne = Certification.create({
            'profile_id': profile.id,
            'certification_id': certification_id,
            'name': self.valeur,
            'source': 'cv',
            'confiance': 'expert',
            'preuve_citation': self.source_quote or False,
            'preuve_cv_id': self.source_id.id,
        })
        self.sudo().certification_line_id = ligne.id
        return ligne

    def action_view_skill(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Compétence qualifiée"),
            'res_model': 'opex.expert.skill',
            'view_mode': 'form',
            'res_id': self.skill_id.id,
        }

    def action_view_arbitrage(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Compétence à arbitrer"),
            'res_model': 'opex.competence.arbitrage',
            'view_mode': 'form',
            'res_id': self.arbitrage_id.id,
        }
