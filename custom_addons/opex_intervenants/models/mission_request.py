from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

#: Code de la définition de workflow de la mission, configurée en data XML.
#: C'est le **seul** mot que ce module connaisse de son propre processus : ni
#: les quatorze étapes, ni les trente-deux transitions, ni les conditions
#: n'apparaissent en Python.
MISSION_WORKFLOW_CODE = 'mission_request'

#: Rôle porté par le client sur **son** appel. Sans groupe : il s'attribue
#: dossier par dossier, par une ligne `opex.workflow.instance.actor`.
CLIENT_ROLE = 'opex_intervenants.role_client'

#: Libellé d'attente avant que la séquence ne soit tirée.
NEW_REFERENCE = "Nouveau"


class MissionRequest(models.Model):
    """Un appel à mission — l'objet central du Module 3.

    CE MODÈLE N'A PAS DE CHAMP `state`.

    Son avancement, c'est `workflow_stage_id` — related sur
    `workflow_instance_id.current_stage_id`, piloté par une définition décrite
    en données. Les quatorze étapes, leurs libellés client, les quatre sorties
    de la sélection et les quatre boucles de retour vivent dans
    `data/mission_request_workflow.xml` et nulle part ailleurs.

    Ajouter ici un `state = fields.Selection([...])` « pour aller plus vite »
    ferait de ce module un workflow codé de plus et annulerait la démonstration
    entière des deux modules précédents. Un test l'interdit explicitement.

    **Un seul objet pour la demande ET l'appel.** Le §9 du document UX laisse
    croire que le gestionnaire « crée l'appel à mission » à partir de la
    demande ; ce n'est pas un second enregistrement. Le §1 de la spécification
    (« créer un objet métier unique Mission ») et le premier critère
    d'acceptation du §21 (« sans duplication de mission ») l'interdisent tous
    les deux. Le gestionnaire complète la demande et la publie : c'est une
    transition, pas une copie.
    """

    _name = 'opex.mission.request'
    _description = "Appel à mission"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'opex.workflow.mixin']
    _order = 'create_date desc, id desc'
    _rec_name = 'title'
    _rec_names_search = ['name', 'title']

    # ------------------------------------------------------------
    # Identité — §4 distingue la référence du titre
    # ------------------------------------------------------------

    name = fields.Char(
        string="Référence",
        required=True,
        readonly=True,
        copy=False,
        index=True,
        default=NEW_REFERENCE,
        help="Référence MIS-AAAA-NNNN, tirée d'une séquence à la création.",
    )
    title = fields.Char(
        string="Titre de la mission",
        required=True,
        tracking=True,
        help="Ce que lit un intervenant dans la liste des appels : "
             "« Audit cybersécurité », pas « MIS-2026-001 ».",
    )

    # ------------------------------------------------------------
    # Bloc 1 — Informations générales (§4)
    # ------------------------------------------------------------

    mission_type_id = fields.Many2one(
        'opex.mission.type',
        string="Type de mission",
        required=True,
        ondelete='restrict',
        tracking=True,
    )
    client_id = fields.Many2one(
        'res.partner',
        string="Client",
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
    )
    # `related` et non recopie : le client ne ressaisit pas ce que son contact
    # porte déjà, et une copie divergerait à la première mise à jour du contact.
    client_organisation_id = fields.Many2one(
        related='client_id.parent_id', string="Organisation", readonly=True)
    client_email = fields.Char(related='client_id.email', readonly=True)
    client_phone = fields.Char(related='client_id.phone', readonly=True)

    description = fields.Text(string="Description du besoin", required=True)
    objectifs = fields.Text(string="Objectifs", required=True)
    resultats_attendus = fields.Text(string="Résultats attendus")

    # ------------------------------------------------------------
    # Bloc 2 — Informations opérationnelles (§4, §7 étape 2)
    # ------------------------------------------------------------

    # Vers `opex.innovation.competence`, le référentiel du Module 2, et pas
    # vers un référentiel neuf. La raison est mécanique et vaut d'être relue :
    # voir le commentaire de `mission_referentials.py`.
    skill_ids = fields.Many2many(
        'opex.innovation.competence',
        'mission_request_skill_rel', 'mission_id', 'competence_id',
        string="Compétences recherchées",
        help="Le capital que le Smart Matching interrogera : ce sont ces "
             "compétences-là qui seront comparées à celles des profils experts.",
    )
    domaine_id = fields.Many2one(
        'opex.mission.domain', string="Domaine d'expertise",
        ondelete='restrict', tracking=True)
    niveau_experience = fields.Selection(
        [
            ('junior', "Junior"),
            ('confirme', "Confirmé"),
            ('senior', "Senior"),
            ('expert', "Expert"),
        ],
        string="Niveau d'expérience souhaité",
    )
    annees_experience_min = fields.Integer(string="Expérience minimale (années)")
    certifications_souhaitees = fields.Text(
        string="Certifications souhaitées",
        help="Texte libre à ce stade. L'Extension 3 y substituera le "
             "référentiel de certifications du profil expert.",
    )
    # Nommé `wilaya` comme le champ de `res.partner` que le Module 1 renseigne :
    # c'est lui que comparera le critère « localisation » de l'Extension 4. Un
    # nom différent aurait obligé à écrire une correspondance quelque part.
    wilaya = fields.Char(string="Wilaya")
    localisation = fields.Char(
        string="Lieu d'intervention",
        help="Le lieu tel qu'il s'affiche : site, adresse, ou « à distance ».")
    mode_intervention = fields.Selection(
        [
            ('presentiel', "Présentiel"),
            ('distanciel', "Distanciel"),
            ('hybride', "Hybride"),
        ],
        string="Mode d'intervention",
        default='presentiel',
    )
    # Demandé par la spécification Smart Missions (§5 et le critère 5 % du §11),
    # absent du document UX. Posé maintenant pour que l'Extension 4 ait quelque
    # chose à comparer.
    langues = fields.Char(string="Langues attendues")

    # ------------------------------------------------------------
    # Bloc 3 — Informations temporelles (§4)
    # ------------------------------------------------------------

    date_debut_souhaitee = fields.Date(string="Début souhaité")
    date_fin_souhaitee = fields.Date(string="Fin souhaitée")
    duree_estimee_jours = fields.Integer(
        string="Durée estimée (jours)",
        help="L'unité n'est précisée nulle part dans les documents ; le jour "
             "est retenu, conformément à l'exemple du §11 (« 15 jours »).",
    )
    date_limite_candidature = fields.Date(
        string="Date limite de candidature",
        tracking=True,
        help="Exigée pour publier l'appel, et elle doit encore être à venir.",
    )
    # Calculé, **non stocké**, et c'est ce qui le rend juste.
    #
    # « La date limite est-elle encore ouverte ? » dépend du jour où l'on pose
    # la question. Un champ stocké se figerait au dernier recalcul ; celui-ci
    # est réévalué à chaque lecture, donc à chaque évaluation de la condition
    # de publication.
    #
    # Il existe parce que `safe_eval` n'expose pas `datetime` : `_BUILTINS`
    # (`odoo/tools/safe_eval.py`) ne contient aucune date. Une règle de
    # transition ne peut donc pas comparer à aujourd'hui, et c'est au modèle de
    # lui livrer le fait déjà calculé.
    date_limite_is_open = fields.Boolean(
        string="Date limite encore ouverte",
        compute='_compute_date_limite_is_open',
        help="Fait dérivé, pas un état : lu par la condition de la transition "
             "« Publier l'appel ».",
    )

    # ------------------------------------------------------------
    # Bloc 4 — Informations financières (§4)
    # ------------------------------------------------------------

    currency_id = fields.Many2one(
        'res.currency', string="Devise",
        default=lambda self: self.env.company.currency_id)
    budget_estimatif = fields.Monetary(
        string="Budget estimatif", currency_field='currency_id')
    type_remuneration = fields.Selection(
        [
            ('tjm', "Taux journalier moyen"),
            ('forfait', "Forfait"),
            ('horaire', "Taux horaire"),
            ('autre', "Autre"),
        ],
        string="Type de rémunération",
    )
    conditions_financieres = fields.Text(string="Conditions financières")

    # ------------------------------------------------------------
    # Sourcing — §8
    # ------------------------------------------------------------

    sourcing_mode = fields.Selection(
        [
            ('matching', "Matching ciblé"),
            ('portail', "Appel ouvert sur le portail"),
            ('hybride', "Hybride — les deux canaux"),
        ],
        string="Mode de sourcing",
        default='hybride',
        tracking=True,
        help="Le mode hybride n'est pas un troisième moteur : il active les "
             "deux canaux d'alimentation du même pool de candidats (§8).",
    )

    # ------------------------------------------------------------
    # Confidentialité — §14
    # ------------------------------------------------------------

    # C'est ici qu'un champ d'état fantôme s'introduirait.
    #
    # `is_published` est **calculé depuis l'étape courante** et jamais écrit à
    # la main. Il ne peut donc pas diverger du workflow, et il reste stocké pour
    # que le catalogue public de l'Extension 12 puisse le mettre dans un domaine
    # indexable. Un booléen qu'on écrirait soi-même serait un second état, en
    # concurrence silencieuse avec le premier.
    _PUBLIC_STAGE_CODES = ('sourcing', 'open', 'selection')

    is_published = fields.Boolean(
        string="Publié",
        compute='_compute_is_published',
        store=True,
        readonly=True,
        help="Projection de l'étape courante, jamais écrite à la main.",
    )
    public_fields_only = fields.Boolean(
        string="Vue publique restreinte",
        default=True,
        help="La publication utilise une vue dédiée de la mission, pas l'objet "
             "interne complet (§14). Client, budget et pièces sensibles "
             "peuvent rester masqués.",
    )
    nda_required = fields.Boolean(
        string="NDA requis",
        help="Un accord de confidentialité conditionne l'accès aux documents "
             "détaillés (§14).",
    )

    # ------------------------------------------------------------
    # Documents — §4
    # ------------------------------------------------------------

    # `document_ids` / `document_type` : ce sont les **conventions que le
    # moteur reconnaît** (`workflow_instance.py:211`). Une condition de
    # transition peut donc s'écrire `has_document('cahier_charges')` sans une
    # ligne de Python. Renommer l'un des deux casserait silencieusement toute
    # règle qui s'en sert.
    document_ids = fields.One2many(
        'opex.mission.document', 'mission_id', string="Documents")
    document_count = fields.Integer(
        string="Nombre de documents", compute='_compute_document_count')

    # ------------------------------------------------------------
    # Les candidatures — des compteurs, pas des états
    # ------------------------------------------------------------

    application_ids = fields.One2many(
        'opex.mission.application', 'mission_id', string="Candidatures")

    #: Étapes où la candidature n'a pas encore été déposée. Une invitation
    #: n'est pas une candidature reçue.
    _PENDING_APPLICATION_CODES = ('invited', 'viewed', 'interested')

    application_count = fields.Integer(
        string="Liens candidat", compute='_compute_application_counts',
        help="Toutes les candidatures rattachées, invitations comprises.")
    received_application_count = fields.Integer(
        string="Candidatures reçues", compute='_compute_application_counts',
        help="Celles réellement déposées — les « candidatures reçues » du §15.")
    shortlisted_count = fields.Integer(
        string="En short-list", compute='_compute_application_counts')

    # Le compteur stocké a sa **propre** méthode de calcul, et ce n'est pas un
    # découpage cosmétique.
    #
    # Le registre refuse de charger un modèle dont une même méthode calcule des
    # champs stockés et non stockés (`registry.py:543`, « inconsistent 'store'
    # for computed fields »). La raison est concrète : lire un compteur
    # d'affichage déclencherait alors une **écriture** du compteur stocké, à un
    # moment quelconque et sous l'identité de n'importe quel lecteur.
    #
    # Découvert au premier chargement du module ; l'avertissement nomme
    # exactement le défaut.

    # **Stocké**, et c'est le seul des quatre à l'être.
    #
    # C'est le garde-fou de la règle 4 du §39, lu par la condition de la
    # transition « Attribuer la mission ». Il est stocké parce qu'il sera
    # filtré et agrégé (tableaux de bord de l'Extension 11), les trois autres
    # ne servent qu'à l'affichage.
    #
    # **C'est un compteur, pas un état.** C'est l'unique point de contact
    # entre les deux machines, et il va dans un seul sens : la mission compte
    # ses candidatures retenues, aucune candidature ne lit l'étape de la
    # mission pour décider de la sienne. La ligne de partage est celle du
    # CLAUDE.md du moteur à propos de `roadmap.phase` — une case sans acteur,
    # sans condition, sans historique et sans chemin de refus n'est pas un
    # processus.
    selected_application_count = fields.Integer(
        string="Candidatures retenues",
        compute='_compute_selected_application_count',
        store=True,
        readonly=True,
    )

    # `related` non stocké : lu par la condition de « Attribuer la mission »
    # pour reconnaître l'exception de la règle 4.
    type_multi_intervenants = fields.Boolean(
        related='mission_type_id.multi_intervenants',
        string="Plusieurs intervenants autorisés",
        readonly=True,
    )

    # ------------------------------------------------------------
    # Calculs
    # ------------------------------------------------------------

    @api.depends('name', 'title')
    def _compute_display_name(self):
        """« MIS-2026-0001 — Audit cybersécurité » : l'en-tête exact du §40."""
        for mission in self:
            if mission.name and mission.name != NEW_REFERENCE:
                mission.display_name = "%s — %s" % (mission.name, mission.title or '')
            else:
                mission.display_name = mission.title or NEW_REFERENCE

    @api.depends('document_ids')
    def _compute_document_count(self):
        for mission in self:
            mission.document_count = len(mission.document_ids)

    def _compute_date_limite_is_open(self):
        today = fields.Date.context_today(self)
        for mission in self:
            mission.date_limite_is_open = bool(
                mission.date_limite_candidature
                and mission.date_limite_candidature >= today
            )

    @api.depends('workflow_stage_id')
    def _compute_is_published(self):
        for mission in self:
            # `sudo()` sur la seule lecture du **code d'étape** : c'est de la
            # configuration moteur, un client portail n'y a pas accès et n'en a
            # pas besoin — ce qui le concerne, c'est le résultat.
            code = mission.workflow_stage_id.sudo().code
            mission.is_published = code in self._PUBLIC_STAGE_CODES

    def _application_stage_codes(self):
        """Les codes d'étape des candidatures, **avec leurs répétitions**.

        Une compréhension, jamais `mapped('workflow_stage_id.code')` :
        `mapped()` sur un Many2one déduplique, et deux candidatures arrêtées à
        la même étape n'en feraient qu'une. C'est le piège du §7 du CLAUDE.md,
        et ici il fausserait directement le garde-fou de la règle 4 — deux
        candidatures retenues seraient comptées pour une, et l'attribution
        passerait.

        `sudo()` sur la lecture : un client doit pouvoir compter les
        candidatures reçues sur son appel sans avoir le droit de les lire.
        """
        self.ensure_one()
        return [
            application.workflow_stage_id.code
            for application in self.sudo().application_ids
        ]

    @api.depends('application_ids.workflow_stage_id')
    def _compute_application_counts(self):
        """Les trois compteurs d'affichage — non stockés."""
        for mission in self:
            codes = mission._application_stage_codes()
            mission.application_count = len(codes)
            mission.received_application_count = sum(
                1 for code in codes
                if code not in self._PENDING_APPLICATION_CODES
            )
            mission.shortlisted_count = codes.count('shortlisted')

    @api.depends('application_ids.workflow_stage_id')
    def _compute_selected_application_count(self):
        """Le garde-fou de la règle 4 — stocké, donc calculé à part."""
        for mission in self:
            mission.selected_application_count = \
                mission._application_stage_codes().count('selected')

    # ------------------------------------------------------------
    # Cohérence des dates
    # ------------------------------------------------------------

    @api.constrains('date_debut_souhaitee', 'date_fin_souhaitee',
                    'date_limite_candidature')
    def _check_dates(self):
        """Cohérence entre les trois dates, et rien de plus.

        On ne vérifie **pas** ici que la date limite est à venir. Une
        contrainte se rejoue à chaque écriture : elle rendrait toute mission
        ancienne impossible à modifier, y compris pour corriger autre chose.
        « Encore ouverte » est un fait qui dépend du jour ; il est porté par
        `date_limite_is_open` et lu au moment où il compte — la publication.
        """
        for mission in self:
            if (mission.date_debut_souhaitee and mission.date_fin_souhaitee
                    and mission.date_fin_souhaitee < mission.date_debut_souhaitee):
                raise ValidationError(_(
                    "La fin souhaitée (%(fin)s) précède le début souhaité "
                    "(%(debut)s)."
                ) % {
                    'fin': mission.date_fin_souhaitee,
                    'debut': mission.date_debut_souhaitee,
                })
            if (mission.date_limite_candidature and mission.date_debut_souhaitee
                    and mission.date_limite_candidature > mission.date_debut_souhaitee):
                raise ValidationError(_(
                    "La date limite de candidature (%(limite)s) est postérieure "
                    "au début souhaité de la mission (%(debut)s) : les "
                    "candidats seraient retenus après le démarrage."
                ) % {
                    'limite': mission.date_limite_candidature,
                    'debut': mission.date_debut_souhaitee,
                })

    # ------------------------------------------------------------
    # Création
    # ------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """Référence tirée, workflow démarré, client rendu acteur de son appel.

        Le verrou sur `client_id` est celui du Module 1 et du Module 2 : la
        valeur est **réécrite côté serveur** pour un utilisateur portail, quelle
        que soit celle reçue du navigateur. Ne pas afficher le champ ne protège
        de rien — une requête forgée n'a jamais vu le formulaire.
        """
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == NEW_REFERENCE:
                # `sudo()` : `ir.sequence` n'est pas lisible par un compte
                # portail, et tirer un numéro n'est pas une donnée de
                # l'utilisateur mais de la comptabilité du module.
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code(
                    'opex.mission.request') or NEW_REFERENCE

        if self.env.user._is_portal():
            client_id = self.env.user.partner_id.id
            for vals in vals_list:
                vals['client_id'] = client_id

        missions = super().create(vals_list)
        for mission in missions:
            mission.start_workflow(MISSION_WORKFLOW_CODE)
            mission._grant_client_actor()
            if mission.client_id:
                mission.sudo().message_subscribe(
                    partner_ids=mission.client_id.ids)
        return missions

    def _grant_client_actor(self):
        """Donne au client le rôle `client` sur **son** appel.

        POURQUOI PAS `initiator_role_id`

        Le moteur sait poser cet acteur tout seul, si la définition déclare un
        `initiator_role_id`. Mais il le pose sur **`instance.initiator_id`**,
        c'est-à-dire sur l'utilisateur qui exécute le `create()` — le moteur le
        documente lui-même comme une limite (`workflow_definition.py:89-97`).

        C'est le bon titulaire quand le client remplit sa propre demande au
        portail. Ce n'est **pas** lui quand le secrétariat ouvre un appel pour
        le compte d'un client (§9) : le secrétariat recevrait le rôle `client`
        en accès `full` sur ce dossier.

        On résout donc l'acteur depuis `client_id`, jamais depuis l'utilisateur
        courant. `opex_innovation` a tranché pareil, pour la même raison :
        `project_workflow.xml` ne renseigne pas `initiator_role_id` et
        `InnovationProject.create()` pose l'acteur à la main
        (`innovation_project.py:259-268`).

        Silencieuse quand le contact n'a pas de compte : un client saisi en
        back-office n'a rien à voir au portail, et lui inventer un acteur
        n'ouvrirait de droits à personne.
        """
        self.ensure_one()
        role = self.env.ref(CLIENT_ROLE, raise_if_not_found=False)
        user = self.client_id.sudo().user_ids[:1]
        if role and user and self.workflow_instance_id:
            self.workflow_instance_id.add_actor(role, user, 'full')
        return True

    # ------------------------------------------------------------
    # §6 — Le tableau de bord du client
    # ------------------------------------------------------------
    #
    # Les quatre indicateurs du §6, exprimés en **codes d'étape**. Ils vivent
    # ici et non dans le controller pour deux raisons : ils se testent sans
    # HTTP, et les filtres de l'écran « mes demandes » se servent des mêmes
    # listes — un compteur qui annonce un nombre que l'écran ne contient pas
    # est pire qu'absent.

    #: « Appels en cours » — la demande est devenue un appel public.
    OPEN_CALL_STAGES = ('sourcing', 'open', 'selection')
    #: « Missions en cours » — un intervenant est retenu, la mission tourne.
    RUNNING_MISSION_STAGES = ('awarded', 'contracting', 'in_progress',
                              'delivered', 'on_hold')
    #: « Missions terminées » — service fait, puis clôture.
    DONE_MISSION_STAGES = ('accepted', 'closed')

    @api.model
    def client_dashboard(self, partner):
        """Les quatre indicateurs du §6, pour ce client.

        Recalculés à chaque affichage, jamais stockés : un agrégat mémorisé se
        décorrélerait du réel à la première transition, et un tableau de bord
        faux est pire qu'absent. C'est le parti déjà retenu sur le tableau de
        bord membre du Module 1.

        `sudo()` **après** avoir borné le domaine au contact : le client doit
        pouvoir compter ses propres dossiers sans que les `ir.rule` du moteur
        aient à lui ouvrir quoi que ce soit de plus.
        """
        missions = self.sudo().search([('client_id', '=', partner.id)])
        codes = [mission.workflow_stage_id.code for mission in missions]
        return {
            'demandes': len(codes),
            'appels': sum(1 for c in codes if c in self.OPEN_CALL_STAGES),
            'en_cours': sum(1 for c in codes if c in self.RUNNING_MISSION_STAGES),
            'terminees': sum(1 for c in codes if c in self.DONE_MISSION_STAGES),
        }

    # ------------------------------------------------------------
    # §8 — Ce que le client doit lire de son propre dossier
    # ------------------------------------------------------------

    def is_first_draft(self):
        """Brouillon jamais soumis — à distinguer d'un dossier renvoyé.

        Les deux sont à l'étape `draft`, et c'est voulu : la boucle du
        Schéma 3 ramène le dossier là où le client a le droit d'écrire, sans
        créer une seconde étape qui dirait la même chose.

        Ils ne se distinguent donc pas par l'étape mais par **l'historique** :
        un dossier déjà passé en qualification n'est plus une saisie en cours.
        Sans cette distinction, « Créer une demande » reprendrait le dossier
        qu'un contrôleur vient de renvoyer, au lieu d'en ouvrir un nouveau.
        """
        self.ensure_one()
        instance = self.workflow_instance_id.sudo()
        if not instance:
            return True
        return not any(
            line.to_stage_id.code == 'qualified'
            for line in instance.history_ids
        )

    def complement_reason(self):
        """Le motif du dernier retour au client — §8.

        > « Si le dossier est incomplet, le client reçoit une notification lui
        >   indiquant les éléments à compléter. »

        Lu dans le **journal d'audit du moteur**, pas recopié dans un champ. Un
        champ serait écrasé au second retour, et c'est précisément l'historique
        des demandes successives qu'il faudrait alors reconstituer. Même parti
        que `opex.innovation.deliverable._archive_current_version()`.

        Construit en compréhension, jamais par `mapped()` : un dossier renvoyé
        deux fois repasse par la même étape, et `mapped()` sur un Many2one
        dédupliquerait le second passage — on afficherait le premier motif,
        déjà traité.
        """
        self.ensure_one()
        instance = self.workflow_instance_id.sudo()
        if not instance:
            return False
        retours = [
            line.comment
            for line in instance.history_ids.sorted('id')
            if line.transition_id.code == 'mission_request_complement'
        ]
        return retours[-1] if retours else False

    def history_entries(self):
        """L'historique du dossier, préparé **par le modèle**.

        Des **dictionnaires**, jamais le recordset. C'est le modèle qui
        décide ce que le client a le droit de lire, pas le gabarit : passer
        `history_ids` à la page donnerait accès à l'instance, à ses acteurs, et
        de fil en aiguille au dossier entier. Motif repris du Module 1 et du
        Module 2 — `opex.mission.request` n'hérite pas de `portal.mixin`, donc
        le chatter natif ne s'affiche pas au portail.

        Le client lit le **libellé utilisateur** de l'étape, jamais son code.
        """
        self.ensure_one()
        instance = self.workflow_instance_id.sudo()
        if not instance:
            return []
        return [
            {
                'date': line.date,
                'body': line.to_stage_id.user_label or line.to_stage_id.name or '',
                'comment': line.comment or '',
            }
            for line in instance.history_ids.sorted('id')
        ]

    # ------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------

    def action_view_applications(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Candidatures — %s") % self.display_name,
            'res_model': 'opex.mission.application',
            'view_mode': 'list,form',
            'domain': [('mission_id', '=', self.id)],
            'context': {'default_mission_id': self.id},
        }

    def action_view_application_pool(self):
        """Le pool du §10, filtré sur cet appel — Kanban d'abord.

        Distinct de `action_view_applications()` : celui-ci ouvre la liste pour
        consulter, celui-là ouvre l'écran de travail du responsable.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Pool — %s") % self.display_name,
            'res_model': 'opex.mission.application',
            'view_mode': 'kanban,list,form',
            'domain': [('mission_id', '=', self.id)],
            'context': {'default_mission_id': self.id},
        }

    def action_view_documents(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Documents — %s") % self.display_name,
            'res_model': 'opex.mission.document',
            'view_mode': 'list,form',
            'domain': [('mission_id', '=', self.id)],
            'context': {'default_mission_id': self.id},
        }


class MissionDocument(models.Model):
    """Une pièce jointe à l'appel — §4.

    `document_type` porte le nom que le moteur attend
    (`workflow_instance.py:212`) : une condition de transition peut donc exiger
    `has_document('cahier_charges')` sans qu'une ligne de Python soit écrite ici
    ni là-bas.
    """

    _name = 'opex.mission.document'
    _description = "Document d'un appel à mission"
    _order = 'mission_id, document_type, id'

    mission_id = fields.Many2one(
        'opex.mission.request',
        string="Appel à mission",
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(string="Intitulé", required=True)
    document_type = fields.Selection(
        [
            ('cahier_charges', "Cahier des charges"),
            ('technique', "Document technique"),
            ('complementaire', "Document complémentaire"),
            ('autre', "Autre"),
        ],
        string="Type de document",
        required=True,
        default='complementaire',
    )
    file = fields.Binary(string="Fichier", attachment=True)
    filename = fields.Char(string="Nom du fichier")
    description = fields.Text(string="Description")
    # §14 — « Les informations sensibles sont classées par niveau de
    # visibilité. » La vue publique de l'Extension 5 ne servira que celles-ci.
    is_public = fields.Boolean(
        string="Visible dans l'appel public",
        help="Décoché, le document n'est servi qu'aux acteurs autorisés du "
             "dossier — et à eux seuls, y compris dans le HTML rendu.",
    )

    @api.depends('name', 'document_type')
    def _compute_display_name(self):
        labels = dict(self._fields['document_type'].selection)
        for document in self:
            document.display_name = "[%s] %s" % (
                labels.get(document.document_type, ''), document.name or '')
