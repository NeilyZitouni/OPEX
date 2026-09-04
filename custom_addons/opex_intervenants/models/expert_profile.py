from odoo import api, fields, models


class ExpertProfile(models.Model):
    """Le profil expert du Module 2, enrichi du capital que le matching lira.

    ON N'EN CRÉE PAS UN SECOND — ON ÉTEND CELUI QUI EXISTE.

    `opex.innovation.expert.profile` porte déjà le profil validé d'un membre :
    domaine d'expertise, spécialités, fonction, années d'expérience,
    compétences, parcours, justificatifs — et son propre workflow de demande.
    La spécification est explicite : « Un expert référencé ne ressaisit pas son
    profil permanent pour candidater. » Un second modèle obligerait exactement à
    cela.

    Ce fichier n'ajoute donc que des **relations** et deux agrégats. Il ne
    touche à aucun champ existant, ne modifie aucun comportement du Module 2, et
    `opex_innovation` reste installable et présentable sans celui-ci.

    Écart assumé et signalé, identique à celui d'`opex_innovation` vis-à-vis du
    Module 1 : la spécification range ces objets sous un `expert.profile`
    générique ; ici ils se rattachent au profil existant, qui est le même.
    """

    _inherit = 'opex.innovation.expert.profile'

    # ------------------------------------------------------------
    # Le capital — §16 : skills / experiences / certifications /
    #              availability / ratings
    # ------------------------------------------------------------

    expert_skill_ids = fields.One2many(
        'opex.expert.skill', 'profile_id', string="Compétences qualifiées")
    expert_experience_ids = fields.One2many(
        'opex.expert.experience', 'profile_id', string="Expériences")
    expert_certification_ids = fields.One2many(
        'opex.expert.certification', 'profile_id', string="Certifications")
    expert_availability_ids = fields.One2many(
        'opex.expert.availability', 'profile_id', string="Disponibilités")
    expert_rating_ids = fields.One2many(
        'opex.expert.rating', 'profile_id', string="Évaluations reçues")

    # ------------------------------------------------------------
    # Les deux données que le matching réclamait — arbitrage du 30/08
    # ------------------------------------------------------------

    currency_id = fields.Many2one(
        'res.currency', string="Devise",
        default=lambda self: self.env.company.currency_id)
    tjm_indicatif = fields.Monetary(
        string="TJM indicatif",
        currency_field='currency_id',
        help="Tarif journalier moyen, à titre indicatif. Le critère "
             "« Budget 10 % » du §11 en a besoin **avant** qu'une candidature "
             "existe : le matching tourne en amont. Le tarif ferme, lui, est "
             "porté par la candidature (`tarif_propose`).",
    )
    langues = fields.Char(
        string="Langues de travail",
        help="En face du champ `langues` d'un appel à mission. Deux champs "
             "texte : le moteur normalise en minuscules avant de comparer, "
             "donc « Français » croise « français » — mais pas « FR ». Un "
             "référentiel des deux côtés serait plus robuste ; c'est un écart "
             "assumé du MVP.",
    )

    # ------------------------------------------------------------
    # Les agrégats
    # ------------------------------------------------------------
    #
    # **Deux méthodes de calcul, et ce n'est pas un découpage cosmétique.**
    #
    # Le registre refuse de charger un modèle dont une même méthode produit des
    # champs stockés et non stockés (`registry.py:543`) : lire un compteur
    # d'affichage déclencherait une **écriture** de la réputation, à un moment
    # quelconque et sous l'identité de n'importe quel lecteur. Leçon payée à
    # l'Extension 1, appliquée d'emblée ici.

    reputation_score = fields.Float(
        string="Réputation (sur 5)",
        digits=(2, 1),
        compute='_compute_reputation_score',
        store=True,
        readonly=True,
        help="Moyenne des évaluations reçues, client et cluster confondues. "
             "Vaut 0 tant qu'aucune mission n'a été évaluée — l'Extension 10 "
             "alimente ce capital.",
    )
    # Libellés **distincts** de ceux des One2many correspondants.
    #
    # Deux champs du même modèle portant la même étiquette déclenchent un
    # avertissement au chargement — « Two fields (skill_count, competence_ids)
    # […] have the same label » — et rendent les deux indiscernables dans les
    # filtres et les regroupements : l'utilisateur voit deux fois « Compétences »
    # sans savoir lequel compte et lequel liste. Le CLAUDE.md du moteur porte
    # déjà la leçon pour `opex.workflow.definition` ; elle vaut ici, et
    # `competence_ids` appartient au Module 2, qu'on ne renomme pas.
    rating_count = fields.Integer(
        string="Nombre d'évaluations", compute='_compute_capital_counts')
    skill_count = fields.Integer(
        string="Nombre de compétences", compute='_compute_capital_counts')
    experience_count = fields.Integer(
        string="Nombre d'expériences", compute='_compute_capital_counts')
    certification_count = fields.Integer(
        string="Nombre de certifications", compute='_compute_capital_counts')
    valid_certification_count = fields.Integer(
        string="Certifications valides", compute='_compute_capital_counts')
    is_available_now = fields.Boolean(
        string="Disponible actuellement", compute='_compute_capital_counts')
    current_availability_rate = fields.Integer(
        string="Taux de disponibilité (%)", compute='_compute_capital_counts')

    @api.depends('expert_rating_ids.note')
    def _compute_reputation_score(self):
        """Le seul agrégat **stocké** : il sera filtré et trié.

        Zéro quand il n'y a aucune évaluation, et c'est la bonne valeur — pas
        une note par défaut qui ferait passer un expert jamais évalué pour un
        expert moyen.
        """
        for profile in self:
            notes = profile.expert_rating_ids.mapped('note')
            profile.reputation_score = (
                round(sum(notes) / len(notes), 1) if notes else 0.0)

    @api.depends('expert_skill_ids', 'expert_experience_ids',
                 'expert_certification_ids', 'expert_availability_ids',
                 'expert_rating_ids')
    def _compute_capital_counts(self):
        """Les compteurs d'affichage — **non stockés**.

        `valid_certification_count` et les deux champs de disponibilité
        dépendent du jour où l'on regarde : les stocker les figerait au dernier
        recalcul, et le matching sélectionnerait des experts sur des données
        périmées.
        """
        for profile in self:
            profile.skill_count = len(profile.expert_skill_ids)
            profile.experience_count = len(profile.expert_experience_ids)
            profile.certification_count = len(profile.expert_certification_ids)
            profile.rating_count = len(profile.expert_rating_ids)
            profile.valid_certification_count = len(
                profile.expert_certification_ids.filtered('is_valid'))
            courante = profile.expert_availability_ids.filtered('is_current')[:1]
            profile.is_available_now = bool(courante)
            profile.current_availability_rate = courante.taux if courante else 0

    # ------------------------------------------------------------
    # Ce que le matching lira — préparé ici, consommé à l'Extension 4
    # ------------------------------------------------------------

    def capital_summary(self):
        """Synthèse du capital, pour l'écran de l'expert et le back-office.

        Un dictionnaire calculé à la demande plutôt qu'un modèle de plus : ce
        sont des chiffres dérivés, ils n'ont pas à être stockés une seconde
        fois. Motif repris de `qualification_summary()` du Module 2.
        """
        self.ensure_one()
        return {
            'competences': self.skill_count,
            'experiences': self.experience_count,
            'certifications': self.certification_count,
            'certifications_valides': self.valid_certification_count,
            'disponible': self.is_available_now,
            'taux': self.current_availability_rate,
            'reputation': self.reputation_score,
            'evaluations': self.rating_count,
        }
