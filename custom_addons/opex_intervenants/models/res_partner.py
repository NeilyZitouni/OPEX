from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    """Les champs que le Smart Matching lira sur le candidat.

    POURQUOI CES CHAMPS SONT ICI ET PAS SUR LE PROFIL

    Contrainte du moteur, pas choix de conception :
    `opex.workflow.instance._score_candidate()` compare une valeur du dossier à
    `partner.sudo()[criterion.target_field]`
    (`opex_workflow/models/workflow_instance.py:1077`). Le champ cible est donc
    **toujours** un champ de `res.partner` — jamais du profil.

    Le capital vit sur le profil ; ces champs l'exposent là où le moteur sait le
    lire, sans le dupliquer. C'est exactement le motif d'`opex_innovation`, qui
    expose déjà `expert_competence_ids` et `expert_domaine` pour la même raison.

    **Aucun n'est stocké.** Trois raisons, dans cet ordre d'importance :

    1. **Ils seraient faux.** `is_valid` d'une certification et `is_current`
       d'une disponibilité dépendent du **jour où l'on regarde** : rien ne
       déclenche de recalcul quand une échéance passe. Un
       `expert_disponible` stocké resterait vrai après la fin de la période, et
       le matching proposerait des experts indisponibles.
    2. Le stockage n'apporterait rien : le matching filtre d'abord le vivier sur
       des champs réels (`is_expert`), puis lit ces valeurs **en Python**,
       candidat par candidat. Un calcul non stocké ne coûte qu'une traversée de
       relation.
    3. Prudence sur les Many2many. Le CLAUDE.md rapporte qu'un `Many2many` à la
       fois `related` **et** `store=True` empêche le registre de démarrer
       (`AttributeError: 'NoneType' object has no attribute 'isidentifier'`) :
       une chaîne `related` ne permet pas de déduire le nom de la table de
       liaison.

       **Vérifié ici, et la nuance compte** : avec `compute` — et non
       `related` — `store=True` **charge sans erreur**, le comodèle étant
       déclaré explicitement. Le crash est propre au couple `related`+`store`.
       Ce sont donc les raisons 1 et 2 qui justifient l'absence de stockage,
       pas la troisième.

    Corollaire à connaître : on ne peut pas `search()` sur ces champs. Le
    moteur ne le fait pas — il restreint le vivier par `matching_domain` puis
    lit. C'est la même limite que côté Module 2.
    """

    _inherit = 'res.partner'

    # ------------------------------------------------------------
    # Compétences — critère « Compétences 30 % » du §11
    # ------------------------------------------------------------

    expert_skill_competence_ids = fields.Many2many(
        'opex.innovation.competence',
        string="Compétences qualifiées",
        compute='_compute_expert_capital',
        help="Les compétences déclarées **avec un niveau**, issues des lignes "
             "de qualification. À distinguer de `expert_competence_ids`, hérité "
             "du Module 2, qui ne porte pas de niveau.",
    )

    # ------------------------------------------------------------
    # Expérience — critères « Expérience 20 % » et « Secteur 15 % »
    # ------------------------------------------------------------

    expert_experience_domaine_ids = fields.Many2many(
        'opex.mission.domain',
        string="Domaines pratiqués",
        compute='_compute_expert_capital',
        help="Les domaines des missions déjà réalisées. C'est ce qui distingue "
             "un consultant qui a fait dix audits d'un consultant qui a fait "
             "dix formations — un compteur d'années les confondrait.",
    )
    expert_mission_type_ids = fields.Many2many(
        'opex.mission.type',
        string="Types de mission pratiqués",
        compute='_compute_expert_capital',
        help="Le « missions similaires » du §6.",
    )
    expert_seniorite = fields.Selection(
        [
            ('junior', "Junior"),
            ('confirme', "Confirmé"),
            ('senior', "Senior"),
            ('expert', "Expert"),
        ],
        string="Séniorité atteinte",
        compute='_compute_expert_capital',
        help="La plus haute séniorité exercée sur une expérience déclarée. "
             "Mêmes valeurs que `niveau_experience` d'un appel à mission : "
             "deux vocabulaires différents ne se croiseraient jamais.",
    )

    # ------------------------------------------------------------
    # Disponibilité — critère « Disponibilité 10 % »
    # ------------------------------------------------------------

    expert_disponible = fields.Boolean(
        string="Disponible actuellement", compute='_compute_expert_capital')
    expert_taux_disponibilite = fields.Integer(
        string="Taux de disponibilité (%)", compute='_compute_expert_capital')

    # ------------------------------------------------------------
    # Réputation — critère « Réputation OPEX 10 % »
    # ------------------------------------------------------------

    expert_reputation = fields.Float(
        string="Réputation (sur 5)",
        digits=(2, 1),
        compute='_compute_expert_capital',
        help="Vaut 0 tant qu'aucune mission n'a été évaluée. L'Extension 10 "
             "alimente ce capital ; l'Extension 4 le lit.",
    )
    expert_certification_names = fields.Char(
        string="Certifications valides",
        compute='_compute_expert_capital',
        help="Les intitulés des certifications encore valables, en clair. "
             "Le moteur normalise les chaînes avant de comparer, ce qui rend "
             "ce champ exploitable par un critère « contient ».",
    )

    # ------------------------------------------------------------
    # Budget et langue — critères « Budget 10 % » et « Localisation / langue 5 % »
    # ------------------------------------------------------------

    expert_tjm = fields.Monetary(
        string="TJM indicatif",
        currency_field='expert_currency_id',
        compute='_compute_expert_capital',
        help="Comparé au **budget journalier** de la mission, pas à son budget "
             "total : le critère de l'Extension 4 divise `budget_estimatif` "
             "par `duree_estimee_jours` avant de comparer.",
    )
    expert_currency_id = fields.Many2one(
        'res.currency', string="Devise du TJM",
        compute='_compute_expert_capital')
    expert_langues = fields.Char(
        string="Langues de travail", compute='_compute_expert_capital')

    #: Une **seule** méthode de calcul pour tous ces champs, et c'est
    #: possible parce qu'aucun n'est stocké. Le registre n'interdit que le
    #: mélange stocké / non stocké. Une seule traversée du profil sert les huit.
    @api.depends(
        'expert_profile_id',
        'expert_profile_id.expert_skill_ids.competence_id',
        # Sans cette dépendance, confirmer une compétence ne rendrait pas
        # l'expert matchable avant le prochain recalcul - c'est-à-dire à un
        # moment quelconque, et invisible.
        'expert_profile_id.expert_skill_ids.is_confirmed',
        'expert_profile_id.expert_experience_ids.domaine_id',
        'expert_profile_id.expert_experience_ids.mission_type_id',
        'expert_profile_id.expert_experience_ids.seniorite',
        'expert_profile_id.expert_availability_ids',
        'expert_profile_id.expert_certification_ids',
        'expert_profile_id.reputation_score',
        'expert_profile_id.tjm_indicatif',
        'expert_profile_id.langues',
    )
    def _compute_expert_capital(self):
        """Expose le capital du profil là où le moteur sait le lire.

        `sudo()` sur la lecture du profil : le matching s'exécute sous
        l'identité du responsable qui l'a déclenché, et celui-ci n'a aucune
        raison d'avoir le droit de lire le profil de chaque candidat du vivier.
        Le moteur lit d'ailleurs déjà `partner.sudo()[target_field]` de son
        côté ; on ne s'en remet pas à lui pour autant.
        """
        #: Du plus faible au plus fort — pour prendre le maximum, pas le dernier
        #: rencontré. Un `max()` sur les chaînes trierait par ordre
        #: alphabétique et ferait de « junior » le sommet de la hiérarchie.
        rangs = {'junior': 1, 'confirme': 2, 'senior': 3, 'expert': 4}

        for partner in self:
            profile = partner.expert_profile_id.sudo()
            if not profile:
                partner.expert_skill_competence_ids = [(5, 0, 0)]
                partner.expert_experience_domaine_ids = [(5, 0, 0)]
                partner.expert_mission_type_ids = [(5, 0, 0)]
                partner.expert_seniorite = False
                partner.expert_disponible = False
                partner.expert_taux_disponibilite = 0
                partner.expert_reputation = 0.0
                partner.expert_certification_names = False
                partner.expert_tjm = 0.0
                partner.expert_currency_id = False
                partner.expert_langues = False
                continue

            experiences = profile.expert_experience_ids
            # **Les lignes confirmées, et elles seules** - posé à l'IA-1.
            #
            # Sans ce filtre, une compétence proposée par l'IA à la lecture
            # d'un CV ferait matcher l'expert dès l'extraction, avant que
            # quiconque se soit prononcé. Le §9 dit l'inverse : « le niveau
            # déclaré par l'expert ne doit pas constituer à lui seul la
            # vérité », et une proposition de machine vaut encore moins.
            #
            # Le défaut aurait été silencieux et flatteur : plus de
            # compétences, donc de meilleurs scores, donc des experts proposés
            # sur des compétences que personne n'a validées.
            partner.expert_skill_competence_ids = [
                (6, 0, profile.expert_skill_ids
                 .filtered('is_confirmed').competence_id.ids)]
            partner.expert_experience_domaine_ids = [
                (6, 0, experiences.domaine_id.ids)]
            partner.expert_mission_type_ids = [
                (6, 0, experiences.mission_type_id.ids)]

            atteintes = [
                rangs[value] for value in experiences.mapped('seniorite')
                if value in rangs
            ]
            partner.expert_seniorite = next(
                (code for code, rang in rangs.items()
                 if rang == max(atteintes)), False) if atteintes else False

            courante = profile.expert_availability_ids.filtered('is_current')[:1]
            partner.expert_disponible = bool(courante)
            partner.expert_taux_disponibilite = courante.taux if courante else 0

            partner.expert_reputation = profile.reputation_score
            valides = profile.expert_certification_ids.filtered('is_valid')
            partner.expert_certification_names = ", ".join(
                valides.mapped('name')) or False
            partner.expert_tjm = profile.tjm_indicatif
            partner.expert_currency_id = profile.currency_id
            partner.expert_langues = profile.langues

    #
    # RÈGLE 1 DU §39 — **LA** fonction, et il n'y en a qu'une
    #

    def opex_mission_profile(self):
        """Le profil Expert de ce contact, activé **ou en cours d'instruction**.

        Plus large que `expert_profile_id`, et c'est délibéré.

        `expert_profile_id` n'est renseigné qu'à l'**activation** du profil par
        le Module 2. S'y tenir interdirait de candidater au « candidat externe »
        du §7 — celui qui « crée un mini-profil puis fournit les informations
        nécessaires à la candidature. S'il est qualifié, son profil **peut**
        intégrer le référentiel experts OPEX ». Le mot « peut » dit bien que
        l'intégration vient **après** la candidature, pas avant.

        La règle 1 dit « le statut/profil Expert **requis** » : ce qui est
        requis pour candidater, c'est d'avoir un dossier d'expert ouvert — pas
        d'être déjà référencé. Les deux niveaux existent donc :

        - **candidater** → un profil, quel que soit son avancement (ici) ;
        - **maintenir son capital** (`/my/missions/expertise`, Extension 3) →
          un profil **activé**, parce qu'on n'entretient un référencement
          qu'une fois référencé.
        """
        self.ensure_one()
        if self.expert_profile_id:
            return self.expert_profile_id
        return self.env['opex.innovation.expert.profile'].sudo().search(
            [('partner_id', '=', self.id)], order='id desc', limit=1)

    def opex_can_apply_to_mission(self, mission):
        """Ce contact peut-il candidater à cet appel ? — règle 1 et règle 3.

        **LA** fonction, appelée par la route POST **et** par le `t-if` du
        bouton. Le `t-if` masque, il n'empêche rien : une requête forgée n'a
        jamais vu le gabarit. Et un bouton affiché là où la route refuse est le
        bug symétrique, déjà rencontré sur le Module 1 avec « Devenir membre ».

        Renvoie un booléen ; `opex_check_can_apply()` en donne la raison.
        """
        self.ensure_one()
        try:
            self.opex_check_can_apply(mission)
        except UserError:
            return False
        return True

    def opex_check_can_apply(self, mission):
        """La même question, avec le motif du refus.

        Quatre refus possibles, et ils appellent des gestes différents : ouvrir
        un profil, attendre, revenir sur sa candidature, ou renoncer. Une page
        d'erreur muette n'aiderait personne.

        L'ordre compte : on dit d'abord ce qui dépend du candidat, ensuite ce
        qui dépend de l'appel.
        """
        self.ensure_one()
        if not self.opex_mission_profile():
            raise UserError(_(
                "Pour candidater, vous devez disposer d'un profil Expert. "
                "Créez-le en quelques champs : il sera instruit par le cluster "
                "en même temps que votre candidature."))

        # Règle 3 du §39, contrôlée **avant** la contrainte SQL. Celle-ci
        # existe depuis l'Extension 1 et fait autorité ; mais une violation de
        # contrainte empoisonne la transaction et rend un 500 au lieu d'un
        # message. On répond ici, l'écran reste lisible, et la base garde le
        # dernier mot.
        existante = self.env['opex.mission.application'].sudo().search([
            ('mission_id', '=', mission.id),
            ('partner_id', '=', self.id),
        ], limit=1)
        if existante:
            raise UserError(_(
                "Vous avez déjà une candidature sur cet appel — elle est à "
                "l'étape « %s ». Un intervenant ne peut pas candidater deux "
                "fois au même appel."
            ) % (existante.workflow_stage_id.sudo().user_label or ''))

        if not mission.sudo().is_open_for_applications():
            raise UserError(_(
                "Les candidatures ne sont pas ouvertes sur cet appel, ou la "
                "date limite est passée."))
        return True
