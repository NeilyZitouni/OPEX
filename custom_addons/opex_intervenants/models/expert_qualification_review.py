"""Le contrôle qualité assisté — les sept contrôles du §11, l'avis du §12.

LE PRINCIPE QUI GOUVERNE TOUT CE FICHIER (§12)

    « La décision d'activation reste gouvernée par les règles OPEX. »

L'agent **prépare** le contrôle ; un humain tranche. Aucune transition ne se
déclenche sur la foi d'un avis, et il n'existe aucune condition de workflow qui
lise un champ produit ici. Un test lit le source des règles pour s'en assurer.

Ce que cela veut dire concrètement : `action_run()` écrit un avis et le poste
sur le dossier. Elle n'appelle jamais `do_transition()`, et l'avis n'est pas un
état — c'est un **document de travail** qui alimente la file du §20.

L'ORDRE DES DEUX MOITIÉS N'EST PAS UNE PRÉFÉRENCE

Les contrôles **déterministes** tournent d'abord, tous, sans exception. Ils
sont fiables, gratuits et instantanés : un champ manquant est manquant, une
date d'expiration passée est passée, deux profils partageant un email sont un
doublon probable. Aucun modèle de langage ne fait cela mieux, et beaucoup le
font moins bien.

L'IA ne vient **qu'ensuite**, et seulement pour ce que le déterministe ne sait
pas faire : une contradiction de fond entre un CV et un profil déclaré, une
compétence annoncée que le parcours ne justifie pas, une clarification à
demander. Ce sont des jugements, pas des vérifications.

Conséquence directe, et c'est la règle 1 du service portée au métier : **sans
clé, le contrôle qualité fonctionne.** Il perd la moitié qui juge, il garde
celle qui vérifie. Un test le mesure.

POURQUOI LA MACHINE À ÉTATS DU §11 EST PORTÉE PAR CE MODÈLE

    REGISTERED → PROFILE_DRAFT → SUBMITTED → QUALITY_CHECK → QUALIFIED
    → ACTIVE, branches TO_COMPLETE · SUSPENDED · REJECTED · ARCHIVED

Elle n'est pas posée sur `opex.innovation.expert.profile`, et ce n'est pas un
choix de confort. Deux raisons, mesurées :

1. **le mixin n'admet qu'une instance.** `workflow_instance_id` est un
   `Many2one` et `start_workflow()` refuse plutôt qu'il ne remplace. Le profil
   est déjà piloté par `profile_request` (Module 2) ;
2. **étendre la définition du Module 2 ferait rougir un module gelé.**
   `test_profiles.py` y verrouille `len(stage_ids) == 6` et
   `len(transition_ids) == 6`.

Le dossier de qualification est donc l'objet qui porte ce cycle — et c'est
cohérent : ACTIVE, SUSPENDED et ARCHIVED décrivent la vie de l'expert **après**
la demande, ce dont `profile_request` n'a aucune notion. Les deux ne se
recouvrent que sur la partie instruction, et la table de correspondance est
dans `data/expert_qualification_workflow.xml`.

⚠ **Aucun champ `state`.** Douzième définition du projet.

CE QUI NE SUPPOSE PAS QUE LE CONTRÔLEUR EST HUMAIN

Le rôle qui tient les transitions de contrôle s'appelle `qualification_control`.
Rien dans ce fichier ne teste `env.user`, ne lit un groupe, ni ne suppose une
personne. Remplacer le contrôleur par un agent autonome demande de changer le
**porteur du rôle** sur l'instance — pas une ligne de ce module, pas une
transition, pas une condition.
"""

import logging
import re

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

QUALIFICATION_WORKFLOW_CODE = 'expert_qualification'
QUALITY_PROMPT = 'qualification_review'

#: Les sept contrôles du tableau du §11, dans l'ordre où ils se lisent.
#: Nommés une fois : le modèle de ligne, l'écran et les tests y lisent tous.
CONTROLS = [
    ('identite', "Identité"),
    ('completude', "Complétude du profil"),
    ('coherence', "Cohérence CV / profil"),
    ('competences', "Compétences clés"),
    ('certifications', "Certifications requises"),
    ('references', "Références"),
    ('conformite', "Conformité"),
]
CONTROL_CODES = [code for code, _label in CONTROLS]

#: La gravité d'une anomalie. Trois niveaux et pas quatre : au-delà, personne
#: ne sait plus ce qui distingue le troisième du quatrième, et tout devient
#: « moyen ».
SEVERITIES = [
    ('info', "Information"),
    ('warning', "À vérifier"),
    ('blocking', "Bloquant"),
]

#: D'où vient l'anomalie. C'est ce qui permet de lire un avis : une anomalie
#: déterministe est un **fait**, une anomalie d'IA est un **jugement**. Les
#: présenter pareil ferait traiter les deux pareil.
ORIGINS = [
    ('deterministe', "Contrôle déterministe"),
    ('ia', "Assistance IA"),
]

#: Les contrôles que l'IA peut instruire. Les quatre autres sont entièrement
#: déterministes : l'identité, la complétude, les certifications et la
#: conformité se vérifient, elles ne se jugent pas.
AI_CONTROLS = ('coherence', 'competences', 'references')

#: Le seuil de complétude attendu, en nombre de champs renseignés sur les
#: champs attendus. Exprimé ici plutôt qu'en dur dans la méthode : c'est un
#: réglage, et il se discute.
COMPLETENESS_FIELDS = (
    'domaine_expertise', 'fonction', 'annees_experience',
    'description_expertise',
)


class ExpertQualificationReview(models.Model):
    """Le dossier de qualification d'un expert — §11 et §12.

    Il porte la machine à états du §11 et l'avis structuré du contrôle
    qualité. **Aucun champ `state`** : l'avancement est
    `workflow_instance_id.current_stage_id`.
    """

    _name = 'opex.expert.qualification.review'
    _description = "Dossier de qualification d'un intervenant"
    _inherit = ['mail.thread', 'opex.workflow.mixin']
    _order = 'create_date desc, id desc'
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

    anomaly_ids = fields.One2many(
        'opex.expert.qualification.anomaly', 'review_id',
        string="Anomalies détectées")
    #: Stockés tous les deux, et c'est légitime ici : ils sont des fonctions
    #: pures de données stockées — le nombre d'anomalies et leur gravité. Rien
    #: n'y dépend de la date du jour, donc rien ne se fige (règle 16 prise du
    #: côté où elle autorise).
    #:
    #: Le stockage est nécessaire : la file du §20 filtre et groupe dessus, et
    #: une vue `search` refuse un champ calculé non stocké — le module ne
    #: chargerait plus. Mesuré : « Unsearchable field "blocking_count" ».
    anomaly_count = fields.Integer(
        string="Nombre d'anomalies", compute='_compute_anomaly_counts',
        store=True)
    blocking_count = fields.Integer(
        string="Anomalies bloquantes", compute='_compute_anomaly_counts',
        store=True)

    date_controle = fields.Datetime(
        string="Dernier contrôle", readonly=True,
        help="Le contrôle se rejoue autant de fois qu'on veut : il ne décide "
             "rien, il constate. Chaque passage remplace l'avis précédent.")
    ia_sollicitee = fields.Boolean(
        string="Assistance IA sollicitée", readonly=True,
        help="Faux quand le module d'assistance n'est pas installé ou n'a pas "
             "de clé. Les contrôles déterministes ont tourné quand même.")
    ia_indisponible_motif = fields.Char(
        string="Pourquoi l'IA n'a pas été sollicitée", readonly=True)

    recommandation = fields.Text(
        string="Recommandation",
        readonly=True,
        help="Ce que l'avis suggère. **Une suggestion**, jamais une décision : "
             "la transition reste au porteur du rôle de contrôle.",
    )

    _profile_uniq = models.Constraint(
        'unique(profile_id)',
        "Ce profil a déjà un dossier de qualification : rejouez le contrôle "
        "sur le dossier existant plutôt que d'en ouvrir un second.",
    )

    @api.depends('anomaly_ids', 'anomaly_ids.severity')
    def _compute_anomaly_counts(self):
        for review in self:
            anomalies = review.anomaly_ids
            review.anomaly_count = len(anomalies)
            review.blocking_count = len(
                anomalies.filtered(lambda a: a.severity == 'blocking'))

    @api.depends('partner_id')
    def _compute_display_name(self):
        for review in self:
            review.display_name = _("Qualification — %s") % (
                review.partner_id.display_name or '')

    @api.model_create_multi
    def create(self, vals_list):
        """Ouvre le dossier et l'engage dans le processus du §11.

        L'acteur est posé depuis `partner_id`, jamais depuis l'utilisateur qui
        crée : c'est l'arbitrage de l'Extension 1 sur `initiator_role_id`, et
        il vaut ici pour la même raison — le dossier est souvent ouvert par le
        secrétariat pour le compte de quelqu'un d'autre.
        """
        reviews = super().create(vals_list)
        for review in reviews:
            review._start_qualification()
        return reviews

    def _start_qualification(self):
        self.ensure_one()
        if self.workflow_instance_id:
            return False
        definition = self.env['opex.workflow.definition'].sudo()._get_for_code(
            QUALIFICATION_WORKFLOW_CODE)
        if not definition:
            _logger.info(
                "opex_intervenants: définition « %s » absente ; le dossier %s "
                "reste hors processus.", QUALIFICATION_WORKFLOW_CODE, self.id)
            return False
        self.sudo().start_workflow(QUALIFICATION_WORKFLOW_CODE)
        return True

    # ------------------------------------------------------------
    # LE CONTRÔLE — déterministe d'abord, IA ensuite
    # ------------------------------------------------------------

    def action_run(self):
        """Rejoue le contrôle et produit l'avis. **Ne décide rien.**

        Rejouable autant de fois qu'on veut : chaque passage remplace l'avis
        précédent. C'est ce qui distingue un avis d'un état — un état se
        franchit une fois, un avis se reprend quand le dossier bouge.
        """
        for review in self:
            review._run_once()
        return True

    def _run_once(self):
        self.ensure_one()
        profile = self.profile_id.sudo()

        # 1. Le déterministe, toujours, en entier.
        anomalies = self._deterministic_checks(profile)

        # 2. L'IA, seulement ensuite, et seulement si elle est là.
        anomalies_ia, sollicitee, motif = self._ai_checks(profile)
        anomalies += anomalies_ia

        self._replace_anomalies(anomalies)
        self.sudo().write({
            'date_controle': fields.Datetime.now(),
            'ia_sollicitee': sollicitee,
            'ia_indisponible_motif': motif or False,
            'recommandation': self._recommendation(anomalies),
        })
        self._post_advice()
        return True

    # --- Les contrôles déterministes --------------------------------------
    #
    # Chacun rend une liste de dicts. Ils ne lèvent jamais et n'écrivent rien :
    # ce sont des lectures. Un contrôle qui planterait ferait perdre les six
    # autres, et l'avis serait vide sans qu'on sache pourquoi.

    def _deterministic_checks(self, profile):
        """Les contrôles fiables, gratuits et instantanés.

        Ils couvrent en entier quatre des sept contrôles du §11 — identité,
        complétude, certifications, conformité — et la moitié vérifiable des
        trois autres.
        """
        self.ensure_one()
        anomalies = []
        anomalies += self._check_identite(profile)
        anomalies += self._check_completude(profile)
        anomalies += self._check_coherence_dates(profile)
        anomalies += self._check_competences(profile)
        anomalies += self._check_certifications(profile)
        anomalies += self._check_references(profile)
        anomalies += self._check_conformite(profile)
        return anomalies

    def _anomaly(self, control, severity, label, detail=False,
                 origin='deterministe'):
        return {
            'control': control,
            'severity': severity,
            'name': label,
            'detail': detail or False,
            'origin': origin,
        }

    def _check_identite(self, profile):
        """§11 — identité, et le doublon probable du §16.

        Le doublon se cherche sur l'email et le téléphone **normalisés**. Deux
        profils qui partagent un email sont le même intervenant dans la quasi-
        totalité des cas ; les laisser coexister casse la réputation, qui se
        calcule par partenaire.
        """
        anomalies = []
        partner = profile.partner_id
        if not partner:
            return [self._anomaly(
                'identite', 'blocking', _("Aucun contact rattaché au profil"))]

        if not (partner.email or '').strip():
            anomalies.append(self._anomaly(
                'identite', 'blocking', _("Adresse email absente"),
                _("Sans email, ni la cloche ni les notifications du §34 "
                  "n'atteignent l'intervenant.")))
        if not self._phone_numbers(partner):
            anomalies.append(self._anomaly(
                'identite', 'warning', _("Aucun numéro de téléphone")))

        for doublon in self._probable_duplicates(partner):
            anomalies.append(self._anomaly(
                'identite', 'blocking',
                _("Doublon probable : %s") % doublon.display_name,
                _("Même email ou même téléphone. Deux fiches pour une même "
                  "personne dispersent sa réputation et son historique.")))
        return anomalies

    @staticmethod
    def _phone_numbers(partner):
        """Les numéros du contact, sans supposer quels champs existent.

        `mobile` n'est pas présent sur `res.partner` dans toutes les versions
        - il ne l'est pas sur celle-ci, et le supposer faisait échouer treize
        tests sur un `AttributeError`. On lit ce qui est là.
        """
        return [
            partner[nom] for nom in ('phone', 'mobile')
            if nom in partner._fields and partner[nom]
        ]

    @api.model
    def _probable_duplicates(self, partner):
        """Les contacts qui sont probablement la même personne — §16.

        Déterministe et bornée : email exact normalisé, ou téléphone réduit à
        ses chiffres. Aucune approximation de nom — « Mohamed Amine » et
        « M. Amine » se ressemblent trop pour qu'un rapprochement
        automatique soit défendable, et une fausse alerte sur un doublon coûte
        plus cher qu'une alerte manquée : elle fait fusionner deux personnes.
        """
        Partner = self.env['res.partner'].sudo()
        domaines = []
        email = (partner.email or '').strip().lower()
        if email:
            domaines.append([('email', '=ilike', email)])
        for numero in self._phone_numbers(partner):
            chiffres = re.sub(r'\D', '', numero or '')
            # Moins de huit chiffres n'identifie personne : un poste interne,
            # un indicatif seul. Chercher dessus produirait du bruit.
            if len(chiffres) >= 8:
                domaines.append([('phone', 'like', chiffres[-8:])])
        if not domaines:
            return Partner.browse()

        domaine = domaines[0]
        for suivant in domaines[1:]:
            domaine = ['|'] + domaine + suivant
        return Partner.search(domaine + [('id', '!=', partner.id)], limit=5)

    def _check_completude(self, profile):
        """§11 — complétude. Un champ manquant est manquant."""
        manquants = [
            profile._fields[nom].string
            for nom in COMPLETENESS_FIELDS
            if nom in profile._fields and not profile[nom]
        ]
        if not manquants:
            return []
        return [self._anomaly(
            'completude', 'warning' if len(manquants) < 3 else 'blocking',
            _("%s champ(s) du profil non renseigné(s)") % len(manquants),
            ", ".join(manquants))]

    def _check_coherence_dates(self, profile):
        """§11 — cohérence, moitié vérifiable.

        Les dates se contrôlent, elles ne se jugent pas. Ce que le
        déterministe ne sait pas faire — une contradiction de **fond** entre
        le CV et le profil — est laissé à l'IA.

        ⚠ **Le cas « fin avant début » n'arrive pas par l'écran.**
        `opex.expert.experience._check_dates()` (Extension 3) le refuse déjà
        par une contrainte. Le garder ici n'est pas une redondance décorative :
        c'est le seul filet pour des données arrivées **par un autre chemin** —
        import, reprise, migration, requête forgée. Une contrainte Python ne
        s'applique qu'à l'ORM.

        C'est la règle 20 prise à l'endroit : avant d'écrire une garde, se
        demander par quel chemin le cas arriverait. Celui-ci en a un, il n'est
        simplement pas celui de l'écran — et le test qui l'éprouve passe donc
        par du SQL, faute de quoi il ne mesurerait rien.

        Le cas « début dans le futur », lui, n'est contraint par personne et
        s'atteint normalement.
        """
        anomalies = []
        for experience in profile.expert_experience_ids:
            debut, fin = experience.date_debut, experience.date_fin
            if debut and fin and fin < debut:
                anomalies.append(self._anomaly(
                    'coherence', 'blocking',
                    _("Expérience « %s » : fin antérieure au début")
                    % experience.name,
                    _("Du %(fin)s au %(debut)s.")
                    % {'fin': fin, 'debut': debut}))
            if debut and debut > fields.Date.context_today(self):
                anomalies.append(self._anomaly(
                    'coherence', 'warning',
                    _("Expérience « %s » : début dans le futur")
                    % experience.name))

        annees = profile.annees_experience or 0
        if annees and annees > 60:
            anomalies.append(self._anomaly(
                'coherence', 'warning',
                _("Années d'expérience invraisemblables : %s") % annees))
        return anomalies

    def _check_competences(self, profile):
        """§11 — compétences clés, moitié vérifiable.

        On vérifie qu'il y en a et qu'elles sont confirmées. Savoir si une
        compétence annoncée est **justifiée par le parcours** est un jugement,
        et c'est l'IA qui l'instruit.
        """
        anomalies = []
        skills = profile.expert_skill_ids
        if not skills:
            return [self._anomaly(
                'competences', 'blocking',
                _("Aucune compétence qualifiée"),
                _("Sans compétence confirmée, le Smart Matching ne propose "
                  "jamais cet intervenant."))]

        non_confirmees = skills.filtered(lambda s: not s.is_confirmed)
        if non_confirmees:
            anomalies.append(self._anomaly(
                'competences', 'warning',
                _("%s compétence(s) proposée(s) et non confirmée(s)")
                % len(non_confirmees),
                ", ".join(non_confirmees.mapped('competence_id.name'))))
        return anomalies

    def _check_certifications(self, profile):
        """§11 — certifications requises.

        Entièrement déterministe, et c'est la dette D1 qui le permet : le
        référentiel canonique rend le contrôle exact. Deux anomalies
        distinctes, et la distinction est celle de la note du §11 —

        - **expirée** : une réponse. La certification ne prouve plus rien ;
        - **non rapprochée** : une question. On ne sait pas encore ce qu'elle
          vaut, et elle part en file d'arbitrage.
        """
        anomalies = []
        aujourd_hui = fields.Date.context_today(self)
        for certification in profile.expert_certification_ids:
            if certification.date_expiration \
                    and certification.date_expiration < aujourd_hui:
                anomalies.append(self._anomaly(
                    'certifications', 'warning',
                    _("Certification expirée : %s") % certification.name,
                    _("Expirée le %s.") % certification.date_expiration))
            elif not certification.certification_id:
                anomalies.append(self._anomaly(
                    'certifications', 'warning',
                    _("Certification non rapprochée : %s")
                    % certification.name,
                    _("Elle n'est comparable à rien tant qu'elle n'est pas "
                      "rattachée au référentiel, et ne compte donc pour aucun "
                      "appel. À arbitrer.")))
        return anomalies

    def _check_references(self, profile):
        """§11 — références, moitié vérifiable."""
        if not profile.expert_experience_ids:
            return [self._anomaly(
                'references', 'warning',
                _("Aucune expérience renseignée"),
                _("Le critère « Expérience 20 % » du §6 n'a rien à lire."))]
        return []

    def _check_conformite(self, profile):
        """§11 — conformité. Ce qui doit être là pour instruire un dossier."""
        anomalies = []
        if not profile.document_ids:
            anomalies.append(self._anomaly(
                'conformite', 'warning',
                _("Aucune pièce jointe au dossier")))
        if not profile.expert_availability_ids:
            anomalies.append(self._anomaly(
                'conformite', 'info',
                _("Aucune disponibilité déclarée"),
                _("Le critère « Disponibilité 10 % » comptera zéro.")))
        return anomalies

    # --- L'assistance IA, ensuite et seulement ensuite --------------------

    def _ai_checks(self, profile):
        """Ce que le déterministe ne sait pas faire.

        Rend `(anomalies, sollicitee, motif)`. Ne lève jamais : une IA absente,
        sans clé ou en panne rend un avis **incomplet**, jamais un avis
        manquant. Les contrôles déterministes ont déjà tourné.
        """
        self.ensure_one()
        Bridge = self.env['opex.ai.bridge']
        if not Bridge._ai_available():
            return [], False, _(
                "Assistance IA non installée ou non configurée. Les contrôles "
                "déterministes ont tourné ; les jugements de fond n'ont pas "
                "été instruits.")

        payload = Bridge._ai_call_prompt(
            QUALITY_PROMPT, values=self._ai_values(profile))
        if not payload:
            return [], False, _(
                "L'assistance IA n'a rien rendu d'exploitable. Le motif exact "
                "figure dans le journal des appels.")

        return self._validate_ai_payload(payload), True, False

    def _ai_values(self, profile):
        """Ce qu'on envoie au modèle. Fermé, et volontairement pauvre.

        Ni email, ni téléphone, ni pièce jointe : le jugement demandé porte
        sur la **cohérence d'un parcours**, pas sur l'identité de quelqu'un.
        Envoyer plus serait envoyer des données personnelles à un tiers pour
        une question qui ne les demande pas.
        """
        return {
            'profil_declare': "\n".join(filter(None, [
                _("Domaine : %s") % (profile.domaine_expertise or '—'),
                _("Fonction : %s") % (profile.fonction or '—'),
                _("Années d'expérience déclarées : %s")
                % (profile.annees_experience or 0),
                _("Description : %s") % (profile.description_expertise or '—'),
            ])),
            'competences': ", ".join(
                profile.expert_skill_ids.mapped('competence_id.name')) or '—',
            'experiences': "\n".join(
                "- %s (%s → %s)" % (e.name, e.date_debut or '?',
                                    e.date_fin or "en cours")
                for e in profile.expert_experience_ids) or '—',
            'certifications': ", ".join(
                profile.expert_certification_ids.mapped('name')) or '—',
        }

    @api.model
    def _validate_ai_payload(self, payload):
        """Valide la réponse contre un schéma fermé. **Ne lève jamais.**

        Un champ inattendu est ignoré, pas écrit — même règle qu'à l'IA-1, et
        pour la même raison : sans elle, une trouvaille du modèle traverserait
        jusqu'à un écran et personne ne saurait d'où elle vient.

        Un contrôle inconnu est écarté : le modèle ne décide pas de la liste
        des sept.
        """
        anomalies = []
        if not isinstance(payload, dict):
            return anomalies

        for brut in payload.get('anomalies') or []:
            if not isinstance(brut, dict):
                continue
            control = str(brut.get('controle') or '').strip()
            if control not in AI_CONTROLS:
                continue
            libelle = str(brut.get('libelle') or '').strip()
            if not libelle:
                continue
            severite = str(brut.get('gravite') or '').strip()
            if severite not in dict(SEVERITIES):
                severite = 'warning'
            # ⚠ Une anomalie d'IA ne peut pas être bloquante.
            #
            # Ce n'est pas de la prudence décorative : `blocking` est ce que
            # lira un humain pressé, et l'agent ne décide pas. Un jugement de
            # modèle qui bloquerait un dossier serait une décision
            # d'activation prise par l'IA — exactement ce que le §12 interdit.
            if severite == 'blocking':
                severite = 'warning'
            anomalies.append(self._anomaly(
                control, severite, libelle,
                str(brut.get('justification') or '').strip() or False,
                origin='ia'))
        return anomalies

    # --- L'avis ------------------------------------------------------------

    def _replace_anomalies(self, anomalies):
        """Chaque passage remplace l'avis précédent.

        Accumuler ferait grossir l'avis à chaque relance et rendrait
        impossible de savoir ce qui vaut aujourd'hui.
        """
        self.ensure_one()
        Anomaly = self.env['opex.expert.qualification.anomaly'].sudo()
        Anomaly.search([('review_id', '=', self.id)]).unlink()
        for anomalie in anomalies:
            Anomaly.create(dict(anomalie, review_id=self.id))
        return True

    def _recommendation(self, anomalies):
        """Ce que l'avis **suggère**. Jamais ce qu'il décide.

        Le vocabulaire est délibéré : « suggère de », jamais « refuser » ni
        « activer ». Un avis qui écrirait « profil à activer » serait lu comme
        une décision par le premier lecteur pressé, et la nuance du §12 se
        perdrait au premier dossier traité vite.
        """
        bloquants = [a for a in anomalies if a['severity'] == 'blocking']
        a_verifier = [a for a in anomalies if a['severity'] == 'warning']

        if bloquants:
            return _(
                "%(n)s anomalie(s) bloquante(s) relevée(s). L'avis suggère de "
                "demander un complément avant de poursuivre l'instruction. "
                "La décision reste au contrôleur."
            ) % {'n': len(bloquants)}
        if a_verifier:
            return _(
                "Aucune anomalie bloquante. %(n)s point(s) à vérifier avant "
                "qualification. La décision reste au contrôleur."
            ) % {'n': len(a_verifier)}
        return _(
            "Aucune anomalie détectée par les contrôles automatiques. Cela ne "
            "vaut pas qualification : la décision reste au contrôleur.")

    def _post_advice(self):
        """Poste l'avis sur le dossier, en **note interne**.

        `mail.mt_note` et jamais `mt_comment` : c'est de la coordination
        interne. Un `mt_comment` partirait par email aux followers, dont
        l'intervenant — qui recevrait la liste des anomalies relevées sur son
        propre dossier avant que quiconque l'ait instruit.

        `Markup` : `message_post()` échappe un body `str`, et les balises
        s'afficheraient telles quelles.
        """
        self.ensure_one()
        lignes = []
        libelles_controles = dict(CONTROLS)
        libelles_gravite = dict(SEVERITIES)
        for anomalie in self.anomaly_ids:
            lignes.append(Markup(
                "<li><strong>%s</strong> — %s <em>(%s, %s)</em></li>"
            ) % (libelles_controles.get(anomalie.control, ''),
                 anomalie.name,
                 libelles_gravite.get(anomalie.severity, ''),
                 dict(ORIGINS).get(anomalie.origin, '')))

        corps = Markup(_(
            "<p><strong>Avis de contrôle qualité</strong> — %(date)s</p>"
        )) % {'date': fields.Datetime.to_string(self.date_controle)}
        if lignes:
            corps += Markup("<ul>%s</ul>") % Markup("").join(lignes)
        else:
            corps += Markup(_("<p>Aucune anomalie relevée.</p>"))
        corps += Markup("<p><em>%s</em></p>") % (self.recommandation or '')
        if not self.ia_sollicitee and self.ia_indisponible_motif:
            corps += Markup("<p class='text-muted'>%s</p>") % \
                self.ia_indisponible_motif

        self.sudo().message_post(body=corps, subtype_xmlid='mail.mt_note')
        return True

    # ------------------------------------------------------------
    # La file du §20
    # ------------------------------------------------------------

    @api.model
    def work_queue(self):
        """Les dossiers de qualification qui attendent un contrôleur.

        Dictionnaire à clés fermées, comme les quatre espaces de l'Extension
        11. Aucune donnée réservée n'y entre, et le périmètre est borné par le
        modèle, pas par le gabarit.
        """
        reviews = self.sudo().search([])
        en_attente = reviews.filtered(lambda r: not r.date_controle)
        avec_bloquants = reviews.filtered(lambda r: r.blocking_count)
        a_verifier = reviews.filtered(
            lambda r: r.date_controle and not r.blocking_count
            and r.anomaly_count)
        return {
            'a_controler': [r._queue_item() for r in en_attente],
            'bloquants': [r._queue_item() for r in avec_bloquants],
            'a_verifier': [r._queue_item() for r in a_verifier],
        }

    def _queue_item(self):
        self.ensure_one()
        return {
            'id': self.id,
            'intervenant': self.partner_id.display_name or '',
            'etape': self.workflow_stage_id.user_label
            or self.workflow_stage_id.name or '',
            'anomalies': self.anomaly_count,
            'bloquantes': self.blocking_count,
            'controle_le': self.date_controle or False,
        }

    def action_view_profile(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Profil expert"),
            'res_model': 'opex.innovation.expert.profile',
            'view_mode': 'form',
            'res_id': self.profile_id.id,
        }


class ExpertQualificationAnomaly(models.Model):
    """Une anomalie relevée par le contrôle — un constat, jamais une décision.

    `origin` est le champ qui rend l'avis lisible : une anomalie déterministe
    est un **fait** (une date est passée, un champ est vide), une anomalie
    d'IA est un **jugement**. Les afficher sans les distinguer ferait traiter
    les deux avec la même confiance.
    """

    _name = 'opex.expert.qualification.anomaly'
    _description = "Anomalie relevée par le contrôle qualité"
    _order = 'review_id, severity desc, control, id'

    review_id = fields.Many2one(
        'opex.expert.qualification.review',
        string="Dossier de qualification",
        required=True,
        ondelete='cascade',
        index=True,
    )
    partner_id = fields.Many2one(
        related='review_id.partner_id', string="Intervenant",
        store=True, index=True, readonly=True)

    control = fields.Selection(
        CONTROLS, string="Contrôle", required=True, index=True,
        help="L'un des sept du tableau du §11.")
    severity = fields.Selection(
        SEVERITIES, string="Gravité", required=True, default='warning',
        index=True)
    origin = fields.Selection(
        ORIGINS, string="Origine", required=True, default='deterministe',
        index=True,
        help="Déterministe : un fait vérifié. IA : un jugement proposé.")
    name = fields.Char(string="Anomalie", required=True)
    detail = fields.Text(string="Détail")

    @api.depends('control', 'name')
    def _compute_display_name(self):
        libelles = dict(CONTROLS)
        for anomalie in self:
            anomalie.display_name = "%s — %s" % (
                libelles.get(anomalie.control, ''), anomalie.name or '')
