from odoo import _, api, fields, models

#: Code de la **seconde** définition de workflow, configurée en data XML.
#: Séparée de celle de la mission, sur un modèle distinct : « l'avancement
#: global de la mission ne doit pas être confondu avec le parcours individuel
#: de chaque candidat » (§12.2 de la spécification Smart Missions).
APPLICATION_WORKFLOW_CODE = 'mission_application'

#: Rôle porté par l'intervenant sur **sa** candidature. Sans groupe : il
#: s'attribue candidature par candidature.
INTERVENANT_ROLE = 'opex_intervenants.role_intervenant'


class MissionApplication(models.Model):
    """Une candidature — le pool unique du §10.

    CE MODÈLE N'A PAS DE CHAMP `state` NON PLUS.

    Il porte sa **propre** définition de workflow, distincte de celle de la
    mission : dix étapes, vingt transitions, décrites dans
    `data/mission_application_workflow.xml`.

    Les deux machines tournent en parallèle sur des objets liés, et ne se
    dérivent jamais l'une de l'autre. Une mission en `selection` porte
    simultanément des candidatures en `shortlisted`, en `rejected` et en
    `applied` — faire avancer l'une ne fait bouger ni la mission ni les autres.

    **Toutes les candidatures convergent ici, quelle que soit leur origine**
    (§10). Le champ `source` les distingue, et rien d'autre : c'est ce qui rend
    comparables « dans le même écran » une candidature issue du matching et une
    candidature Web — le deuxième critère d'acceptation du §21.

    **Les trois premières étapes ne sont pas une candidature déposée.**
    `invited`, `viewed` et `interested` sont le parcours d'invitation du §12.2 :
    un lien entre un expert et un appel, pas encore un dossier. Les compteurs
    de la mission les excluent, et les `ir.rule` des internes aussi.
    """

    _name = 'opex.mission.application'
    _description = "Candidature à un appel à mission"
    _inherit = ['mail.thread', 'opex.workflow.mixin']
    _order = 'mission_id, score desc, id'
    _rec_name = 'partner_id'

    # ------------------------------------------------------------
    # Le lien — règle 2 du §39 : 1 appel + 1 intervenant
    # ------------------------------------------------------------

    mission_id = fields.Many2one(
        'opex.mission.request',
        string="Appel à mission",
        required=True,
        ondelete='cascade',
        index=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string="Intervenant",
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
    )
    # **Le profil du Module 2, pas un nouveau.** « Un expert référencé ne
    # ressaisit pas son profil permanent pour candidater » : identité, CV,
    # compétences et certifications vivent là-bas et n'ont pas à être recopiées
    # ici. C'est le troisième critère d'acceptation du §21.
    expert_profile_id = fields.Many2one(
        'opex.innovation.expert.profile',
        string="Profil expert",
        ondelete='set null',
        help="Rattaché automatiquement à la création quand le contact en a un.",
    )

    source = fields.Selection(
        [
            ('matching', "Smart Matching"),
            ('portail', "Portail Web"),
            ('invitation', "Invitation directe"),
            ('manuel', "Ajout manuel"),
        ],
        string="Origine",
        required=True,
        default='portail',
        index=True,
        tracking=True,
        help="§10 : toutes les candidatures convergent dans le même objet, "
             "quelle que soit leur origine. Ce champ les distingue, et rien "
             "d'autre — surtout pas un second modèle ni une seconde machine à "
             "états.",
    )
    # Le pont invitation → candidature. Vide pour une candidature portail.
    matching_candidate_id = fields.Many2one(
        'opex.matching.candidate',
        string="Proposition d'origine",
        ondelete='set null',
        help="La ligne du Smart Matching qui a conduit à cette invitation. "
             "Elle porte le score et son explication au moment où le "
             "responsable a décidé d'inviter.",
    )

    # ------------------------------------------------------------
    # La candidature Lean — §13 du Module 3, §9 de Smart Missions
    # ------------------------------------------------------------
    #
    # Seules les données **propres à la mission** sont demandées. Tout ce qui
    # est permanent se lit sur le profil.

    motivation = fields.Text(string="Motivation")
    methodologie = fields.Text(string="Méthodologie proposée")
    disponibilite = fields.Selection(
        [
            ('oui', "Disponible"),
            ('partielle', "Partiellement disponible"),
            ('non', "Non disponible"),
        ],
        string="Disponibilité",
        tracking=True,
        help="Obligatoire au dépôt (§9 de la spécification).",
    )
    disponibilite_commentaire = fields.Char(string="Précision sur la disponibilité")
    delai_propose_jours = fields.Integer(string="Délai de mobilisation (jours)")
    type_tarif = fields.Selection(
        [
            ('tjm', "Taux journalier moyen"),
            ('forfait', "Forfait"),
            ('montant', "Montant global"),
        ],
        string="Type de proposition financière",
    )
    currency_id = fields.Many2one(
        related='mission_id.currency_id', string="Devise", readonly=True)
    tarif_propose = fields.Monetary(
        string="Tarif proposé", currency_field='currency_id')
    consentement = fields.Boolean(
        string="Conditions acceptées",
        help="Consentements, confidentialité et règles de candidature (§9).",
    )

    # ------------------------------------------------------------
    # Le score — écrit par l'Extension 4, jamais calculé ici
    # ------------------------------------------------------------

    score = fields.Float(
        string="Score",
        digits=(5, 2),
        readonly=True,
        tracking=True,
        help="Renseigné par le Smart Matching à la qualification. Ce module "
             "n'écrit aucune ligne de scoring : le moteur le fait "
             "(Extension 4).",
    )
    # Un score sans explication n'est pas défendable devant un jury, et c'est
    # le quatrième critère d'acceptation du §21. Le moteur rend `detail`
    # obligatoire sur `opex.matching.candidate` (`matching.py:211`) ; on recopie
    # ici l'explication au moment de la qualification pour qu'elle survive à un
    # recalcul du matching.
    score_detail = fields.Text(
        string="Explication du score",
        readonly=True,
        help="Critères positifs, manquants et pénalisants, tels qu'ils ont été "
             "évalués au moment de la qualification.",
    )

    document_ids = fields.One2many(
        'opex.mission.application.document', 'application_id',
        string="Pièces jointes")
    document_count = fields.Integer(
        string="Nombre de pièces", compute='_compute_document_count')

    # ------------------------------------------------------------
    # Ce que la règle 4 a besoin de lire — sur la mission, en lecture seule
    # ------------------------------------------------------------
    #
    # `related` non stockés, et lus **uniquement** par la condition de la
    # transition « Retenir cette candidature ». Ce n'est pas dériver l'état de
    # la candidature de celui de la mission : c'est compter, sur la mission,
    # combien de candidatures sont déjà retenues. Aucune étape de l'une ne
    # détermine une étape de l'autre.
    #
    # Une expression `safe_eval` qui traverserait
    # `record.mission_id.application_ids.filtered(...)` aurait fait la même
    # chose, en moins lisible et en dépendant de ce que `safe_eval` autorise.

    mission_selected_count = fields.Integer(
        related='mission_id.selected_application_count',
        string="Candidatures déjà retenues sur cet appel",
        readonly=True,
    )
    mission_allows_multi = fields.Boolean(
        related='mission_id.type_multi_intervenants',
        string="Appel à plusieurs intervenants",
        readonly=True,
    )

    # ------------------------------------------------------------
    # Règle 3 du §39 — au niveau SQL, pas seulement applicatif
    # ------------------------------------------------------------
    #
    # « Un intervenant peut avoir plusieurs candidatures, mais il ne peut pas
    #   déposer deux fois la même candidature pour le même appel. »
    #
    # Une contrainte applicative se contourne par un import, par un script, par
    # une requête forgée. Celle-ci ne se contourne pas.
    #
    # Conséquence, et c'est pour elle que `declined` est **réversible** :
    # avec le §12.2, `declined` est atteignable dès `invited`. Un expert qui
    # décline une invitation ciblée doit pouvoir revenir quand l'appel est
    # publié au portail — et il ne peut pas créer une seconde candidature. Le
    # chemin de retour est donc une transition, `reconsider : declined →
    # viewed`, et non une seconde ligne en base.
    _mission_partner_uniq = models.Constraint(
        'unique(mission_id, partner_id)',
        "Cet intervenant a déjà une candidature sur cet appel : "
        "un intervenant ne peut pas candidater deux fois au même appel "
        "(règle 3 du §39).",
    )

    # ------------------------------------------------------------
    # Calculs
    # ------------------------------------------------------------

    @api.depends('partner_id', 'mission_id')
    def _compute_display_name(self):
        for application in self:
            application.display_name = "%s — %s" % (
                application.partner_id.display_name or '',
                application.mission_id.name or '',
            )

    @api.depends('document_ids')
    def _compute_document_count(self):
        for application in self:
            application.document_count = len(application.document_ids)

    # ------------------------------------------------------------
    # Création
    # ------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """Profil rattaché, workflow démarré, intervenant rendu acteur.

        Le verrou sur `partner_id` est celui des deux modules précédents : pour
        un compte portail, la valeur est réécrite côté serveur quelle que soit
        celle reçue. C'est ce qui empêche une requête forgée de candidater au
        nom d'un autre.
        """
        if self.env.user._is_portal():
            partner_id = self.env.user.partner_id.id
            for vals in vals_list:
                vals['partner_id'] = partner_id

        applications = super().create(vals_list)
        for application in applications:
            application._link_expert_profile()
            application.start_workflow(APPLICATION_WORKFLOW_CODE)
            application._grant_intervenant_actor()
            if application.partner_id:
                application.sudo().message_subscribe(
                    partner_ids=application.partner_id.ids)
        return applications

    def _link_expert_profile(self):
        """Rattache le profil expert du contact, s'il en a un.

        Le premier geste de la candidature Lean : ce qui est permanent est déjà
        connu, on le relie au lieu de le redemander. Silencieux si le contact
        n'a pas de profil — le candidat externe du §7 s'en créera un à
        l'Extension 5, et sa candidature existe entre-temps.
        """
        self.ensure_one()
        if self.expert_profile_id or not self.partner_id:
            return False
        profile = self.partner_id.sudo().expert_profile_id
        if profile:
            self.sudo().expert_profile_id = profile.id
        return bool(profile)

    def _grant_intervenant_actor(self):
        """Donne à l'intervenant le rôle `intervenant` sur **sa** candidature.

        POURQUOI PAS `initiator_role_id` — le cas le plus net des deux

        `_grant_initiator_role()` attribue le rôle à l'utilisateur qui exécute
        le `create()` (`workflow_definition.py:89-97`). Or sur le canal
        matching, c'est le **responsable** qui crée la candidature en invitant
        un expert : il recevrait le rôle `intervenant` en accès **`full`** sur
        cette candidature — celle d'un autre.

        L'acteur est donc résolu depuis `partner_id`, jamais depuis
        l'utilisateur courant. Les deux canaux du §8 passent par le même
        chemin, et le responsable garde ses droits de son groupe, pas d'une
        ligne d'acteur usurpée.

        Un test le vérifie dans les deux sens : l'intervenant est acteur, le
        créateur ne l'est pas.
        """
        self.ensure_one()
        role = self.env.ref(INTERVENANT_ROLE, raise_if_not_found=False)
        user = self.partner_id.sudo().user_ids[:1]
        if role and user and self.workflow_instance_id:
            self.workflow_instance_id.add_actor(role, user, 'full')
        return True

    # ------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------

    def action_view_documents(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Pièces — %s") % self.display_name,
            'res_model': 'opex.mission.application.document',
            'view_mode': 'list,form',
            'domain': [('application_id', '=', self.id)],
            'context': {'default_application_id': self.id},
        }


class MissionApplicationDocument(models.Model):
    """Une pièce jointe à la candidature — §13.

    Mêmes noms de champs que côté mission (`document_ids` / `document_type`) :
    une condition de transition peut exiger `has_document('cv')` sur la
    candidature exactement comme `has_document('cahier_charges')` sur l'appel,
    et le moteur n'a rien appris de nouveau pour cela.
    """

    _name = 'opex.mission.application.document'
    _description = "Pièce jointe d'une candidature"
    _order = 'application_id, document_type, id'

    application_id = fields.Many2one(
        'opex.mission.application',
        string="Candidature",
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(string="Intitulé", required=True)
    document_type = fields.Selection(
        [
            ('cv', "CV"),
            ('portfolio', "Portfolio"),
            ('references', "Références"),
            ('proposition_technique', "Proposition technique"),
            ('proposition_financiere', "Proposition financière"),
            ('certification', "Certification"),
            ('autre', "Autre"),
        ],
        string="Type de pièce",
        required=True,
        default='autre',
    )
    file = fields.Binary(string="Fichier", attachment=True)
    filename = fields.Char(string="Nom du fichier")
    description = fields.Text(string="Description")

    @api.depends('name', 'document_type')
    def _compute_display_name(self):
        labels = dict(self._fields['document_type'].selection)
        for document in self:
            document.display_name = "[%s] %s" % (
                labels.get(document.document_type, ''), document.name or '')
