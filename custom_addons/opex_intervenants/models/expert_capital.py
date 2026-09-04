from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

#: Échelle de niveau, partagée par les compétences de l'expert et par les
#: exigences d'une mission. Une seule échelle, sinon le matching de
#: l'Extension 4 comparerait « confirmé » à « intermédiaire » sans savoir
#: lequel est au-dessus.
NIVEAU_SELECTION = [
    ('debutant', "Débutant"),
    ('intermediaire', "Intermédiaire"),
    ('confirme', "Confirmé"),
    ('expert', "Expert"),
]

#: Séniorité d'une expérience. Reprend **exactement** les valeurs de
#: `opex.mission.request.niveau_experience` : le critère « Expérience 20 % »
#: compare l'une à l'autre, et deux vocabulaires différents ne se croiseraient
#: jamais.
SENIORITE_SELECTION = [
    ('junior', "Junior"),
    ('confirme', "Confirmé"),
    ('senior', "Senior"),
    ('expert', "Expert"),
]


class ExpertSkill(models.Model):
    """Une compétence de l'expert, qualifiée — §15 et §16.

    **Ce n'est pas un référentiel de compétences.** Le référentiel est
    `opex.innovation.competence`, celui du Module 2, et il n'y en a qu'un. Ce
    modèle est la **ligne de qualification** qui relie un profil à une
    compétence en disant à quel niveau et depuis combien d'années.

    Le profil expert porte déjà un `competence_ids` (Many2many nu, hérité du
    Module 2). Il reste : il dit *quelles* compétences, ces lignes disent
    *combien*. Le matching de l'Extension 4 lira les lignes, plus riches.
    """

    _name = 'opex.expert.skill'
    _description = "Compétence qualifiée d'un intervenant"
    _order = 'profile_id, niveau desc, annees desc, id'

    profile_id = fields.Many2one(
        'opex.innovation.expert.profile',
        string="Profil expert",
        required=True,
        ondelete='cascade',
        index=True,
    )
    # `related` **stocké** : c'est par lui que les `ir.rule` du portail bornent
    # ces lignes au contact connecté, et une `ir.rule` a besoin d'une colonne.
    # Un Many2one related stocké ne pose aucun problème — c'est le **Many2many**
    # à la fois `related` et `store=True` qui empêche le registre de démarrer.
    partner_id = fields.Many2one(
        related='profile_id.partner_id', string="Intervenant",
        store=True, index=True, readonly=True)

    competence_id = fields.Many2one(
        'opex.innovation.competence',
        string="Compétence",
        required=True,
        ondelete='restrict',
        index=True,
        help="Le référentiel partagé avec le Module 2. C'est lui que le Smart "
             "Matching compare aux compétences recherchées par une mission.",
    )
    niveau = fields.Selection(
        NIVEAU_SELECTION, string="Niveau", required=True, default='confirme')
    annees = fields.Integer(
        string="Années de pratique",
        help="Sur cette compétence précise, pas sur l'ensemble du parcours.")

    _skill_uniq = models.Constraint(
        'unique(profile_id, competence_id)',
        "Cette compétence est déjà déclarée sur ce profil : modifiez la ligne "
        "existante plutôt que d'en ajouter une seconde.",
    )
    _annees_positive = models.Constraint(
        'CHECK(annees >= 0)',
        "Le nombre d'années de pratique ne peut pas être négatif.",
    )

    @api.depends('competence_id', 'niveau')
    def _compute_display_name(self):
        labels = dict(NIVEAU_SELECTION)
        for skill in self:
            skill.display_name = "%s — %s" % (
                skill.competence_id.name or '',
                labels.get(skill.niveau, ''))


class ExpertExperience(models.Model):
    """Une mission déjà réalisée — le « missions similaires » du §6.

    Trois choses que le matching y lira : le **type** de mission, le
    **domaine**, et la **séniorité** exercée. C'est ce qui permet de distinguer
    un consultant qui a fait dix audits d'un consultant qui a fait dix
    formations, là où un simple compteur d'années les confondrait.
    """

    _name = 'opex.expert.experience'
    _description = "Expérience d'un intervenant"
    _order = 'profile_id, date_debut desc, id desc'

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

    name = fields.Char(string="Intitulé de la mission", required=True)
    organisation = fields.Char(
        string="Organisation",
        help="Le client de cette mission. Laissez vide si la référence est "
             "confidentielle.")
    mission_type_id = fields.Many2one(
        'opex.mission.type', string="Type de mission", ondelete='restrict',
        help="Le même référentiel que celui des appels : c'est ce qui rend "
             "« missions similaires » calculable.")
    domaine_id = fields.Many2one(
        'opex.mission.domain', string="Domaine", ondelete='restrict',
        help="Alimente le critère « Expérience secteur » du §11.")
    seniorite = fields.Selection(
        SENIORITE_SELECTION, string="Séniorité exercée")

    date_debut = fields.Date(string="Début")
    date_fin = fields.Date(string="Fin")
    duree_jours = fields.Integer(string="Durée (jours)")
    description = fields.Text(string="Description")

    _duree_positive = models.Constraint(
        'CHECK(duree_jours >= 0)',
        "La durée d'une expérience ne peut pas être négative.",
    )

    @api.constrains('date_debut', 'date_fin')
    def _check_dates(self):
        for experience in self:
            if (experience.date_debut and experience.date_fin
                    and experience.date_fin < experience.date_debut):
                raise ValidationError(_(
                    "« %(nom)s » : la date de fin (%(fin)s) précède la date de "
                    "début (%(debut)s)."
                ) % {
                    'nom': experience.name,
                    'fin': experience.date_fin,
                    'debut': experience.date_debut,
                })

    @api.depends('name', 'organisation')
    def _compute_display_name(self):
        for experience in self:
            experience.display_name = " — ".join(
                part for part in (experience.name, experience.organisation)
                if part)


class ExpertCertification(models.Model):
    """Une certification — §6 : « critères obligatoires ou préférentiels ».

    La **validité** est calculée, non stockée. « Cette certification est-elle
    encore valable ? » dépend du jour où l'on pose la question : un champ
    stocké se figerait au dernier recalcul et l'Extension 4 sélectionnerait des
    experts sur des certifications périmées. Même raisonnement que
    `date_limite_is_open` sur l'appel à mission.
    """

    _name = 'opex.expert.certification'
    _description = "Certification d'un intervenant"
    _order = 'profile_id, date_obtention desc, id desc'

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

    name = fields.Char(string="Intitulé", required=True)
    organisme = fields.Char(string="Organisme émetteur")
    reference = fields.Char(string="Référence / numéro")
    date_obtention = fields.Date(string="Date d'obtention")
    date_expiration = fields.Date(
        string="Valable jusqu'au",
        help="Laissez vide pour une certification sans échéance.")

    # Facultatif, et c'est un arbitrage explicite du 30/08.
    #
    # Une certification déclarative n'est pas une certification prouvée, et le
    # MVP l'accepte : exiger le justificatif bloquerait la saisie du capital
    # avant même que le matching ait servi une fois. Le champ existe **dès
    # maintenant** parce que le rétro-remplir sur des données déjà saisies
    # coûte plus cher que de le poser aujourd'hui.
    justificatif = fields.Binary(
        string="Justificatif", attachment=True,
        help="Copie du certificat. Facultatif au MVP ; le cluster peut "
             "l'exiger plus tard sans migration de données.")
    justificatif_filename = fields.Char(string="Nom du fichier")
    is_valid = fields.Boolean(
        string="En cours de validité", compute='_compute_is_valid',
        help="Fait dérivé, recalculé à chaque lecture — jamais stocké.")

    @api.constrains('date_obtention', 'date_expiration')
    def _check_dates(self):
        for certification in self:
            if (certification.date_obtention and certification.date_expiration
                    and certification.date_expiration
                    < certification.date_obtention):
                raise ValidationError(_(
                    "« %s » : la date d'expiration précède la date "
                    "d'obtention."
                ) % certification.name)

    def _compute_is_valid(self):
        today = fields.Date.context_today(self)
        for certification in self:
            certification.is_valid = (
                not certification.date_expiration
                or certification.date_expiration >= today
            )

    @api.depends('name', 'organisme')
    def _compute_display_name(self):
        for certification in self:
            certification.display_name = " — ".join(
                part for part in (certification.name, certification.organisme)
                if part)


class ExpertAvailability(models.Model):
    """Une période de disponibilité — le critère « Disponibilité 10 % » du §11.

    Une période et un taux, pas un simple booléen : le §9 demande une
    disponibilité « Oui / Non / **Partielle** », et un expert à 40 % n'est ni
    disponible ni indisponible.
    """

    _name = 'opex.expert.availability'
    _description = "Disponibilité d'un intervenant"
    _order = 'profile_id, date_debut, id'

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

    date_debut = fields.Date(string="Disponible à partir du", required=True)
    date_fin = fields.Date(string="Jusqu'au", required=True)
    taux = fields.Integer(
        string="Taux de disponibilité (%)",
        default=100,
        help="100 % pour une disponibilité pleine, 50 % pour un mi-temps.")
    note = fields.Char(string="Précision")

    is_current = fields.Boolean(
        string="Période en cours", compute='_compute_is_current',
        help="Fait dérivé, recalculé à chaque lecture — jamais stocké.")

    _taux_range = models.Constraint(
        'CHECK(taux >= 0 AND taux <= 100)',
        "Le taux de disponibilité s'exprime entre 0 et 100 %.",
    )

    @api.constrains('date_debut', 'date_fin')
    def _check_dates(self):
        for availability in self:
            if availability.date_fin < availability.date_debut:
                raise ValidationError(_(
                    "La fin de la période de disponibilité (%(fin)s) précède "
                    "son début (%(debut)s)."
                ) % {
                    'fin': availability.date_fin,
                    'debut': availability.date_debut,
                })

    def _compute_is_current(self):
        today = fields.Date.context_today(self)
        for availability in self:
            availability.is_current = (
                availability.date_debut <= today <= availability.date_fin
                if availability.date_debut and availability.date_fin
                else False
            )

    @api.depends('date_debut', 'date_fin', 'taux')
    def _compute_display_name(self):
        for availability in self:
            availability.display_name = "%s → %s (%s %%)" % (
                availability.date_debut or '?',
                availability.date_fin or '?',
                availability.taux)


class ExpertRating(models.Model):
    """Une note portée sur un intervenant — la brique de la réputation.

    CE MODÈLE EST CRÉÉ VIDE, ET C'EST VOULU.

    Aucun écran ne crée de ligne ici, ni au portail ni au back-office. Les
    notes viendront des **évaluations de l'Extension 10** — celle du client
    (§30) et celle du cluster (§31) —, à la clôture d'une mission.

    Il existe dès maintenant pour une seule raison : le critère « Réputation
    OPEX 10 % » du §11 doit avoir quelque chose à lire à l'Extension 4. Sans
    lui, il faudrait ou bien retarder le matching, ou bien lui inventer une
    source qu'on remplacerait ensuite.

    `reputation_score` du profil vaut donc **0** tant qu'aucune évaluation n'a
    eu lieu, et l'écran le dit plutôt que d'afficher une note inventée.
    """

    _name = 'opex.expert.rating'
    _description = "Évaluation d'un intervenant"
    _order = 'profile_id, date desc, id desc'

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

    mission_id = fields.Many2one(
        'opex.mission.request',
        string="Mission évaluée",
        ondelete='set null',
        help="La mission au titre de laquelle la note a été portée. "
             "Renseignée par l'Extension 10.",
    )
    source = fields.Selection(
        [
            ('client', "Évaluation du client (§30)"),
            ('cluster', "Évaluation du cluster (§31)"),
        ],
        string="Origine",
        required=True,
        default='client',
        help="Les deux évaluations du Module 3 sont indépendantes et se "
             "cumulent dans la réputation.",
    )
    note = fields.Float(
        string="Note sur 5", digits=(2, 1),
        help="§30 et §31 notent chaque critère sur 5 ; c'est la moyenne de la "
             "grille qui arrive ici.")
    respect_delais = fields.Boolean(
        string="Délais respectés",
        help="Alimente le « Respect des délais » du §32.")
    date = fields.Datetime(
        string="Portée le", default=fields.Datetime.now, readonly=True)
    commentaire = fields.Text(string="Commentaire")

    _note_range = models.Constraint(
        'CHECK(note >= 0 AND note <= 5)',
        "Une note s'exprime entre 0 et 5.",
    )
