from odoo import _, api, fields, models
from odoo.exceptions import UserError

DELIVERABLE_WORKFLOW_CODE = 'mission_deliverable'
#: Seuls les deux rôles **portail** ont besoin d'une ligne d'acteur : le
#: responsable et le secrétariat tiennent les leurs d'un groupe Odoo
#: (`role.group_id`), que `_user_roles()` lit directement
#: (`workflow_instance.py:427`).
INTERVENANT_ROLE = 'opex_intervenants.role_intervenant'
CLIENT_ROLE = 'opex_intervenants.role_client'


class MissionDeliverableVersion(models.Model):
    """Une version figée d'un livrable — §25.

    > « L'historique des versions doit être conservé. »

    **Le motif du refus est porté par la version, jamais par le livrable.**

    C'est la leçon d'`opex_innovation`, reprise telle quelle. Sur le livrable,
    un champ `motif_correction` serait écrasé au refus suivant : on garderait
    la raison du dernier refus et on perdrait celle du premier — c'est-à-dire
    exactement ce que l'historique doit montrer. Un intervenant à qui l'on
    reproche deux choses différentes en deux tours ne lirait plus que la
    seconde, et l'on ne saurait plus si la première a été corrigée.

    Et il n'est pas **recopié au moment du refus** : il est relu dans le
    journal d'audit du moteur au moment d'archiver
    (`_archive_current_version()`). Le journal est immuable, donc la source
    est fiable ; un champ recopié au refus serait une seconde vérité, qui
    dériverait de la première.
    """

    _name = 'opex.mission.deliverable.version'
    _description = "Version d'un livrable de mission"
    _order = 'deliverable_id, version desc, id desc'

    deliverable_id = fields.Many2one(
        'opex.mission.deliverable',
        string="Livrable",
        required=True,
        ondelete='cascade',
        index=True,
        readonly=True,
    )
    version = fields.Integer(string="Version", required=True, readonly=True)
    file = fields.Binary(string="Fichier", attachment=True, readonly=True)
    filename = fields.Char(string="Nom du fichier", readonly=True)
    date = fields.Datetime(
        string="Déposée le", default=fields.Datetime.now, readonly=True)
    author_id = fields.Many2one(
        'res.partner', string="Déposée par", readonly=True,
        ondelete='set null')
    motif_correction = fields.Text(
        string="Motif de la correction demandée",
        readonly=True,
        help="Ce qui a été reproché à cette version-là, et à elle seule.",
    )

    @api.depends('deliverable_id.name', 'version')
    def _compute_display_name(self):
        for record in self:
            record.display_name = "%s — v%s" % (
                record.deliverable_id.name or '', record.version)

    def write(self, vals):
        """Une archive modifiable ne prouve rien.

        Même verrou que sur `opex.workflow.history` : sans lui, l'historique
        des versions dirait ce qu'on veut bien qu'il dise, et le §25 n'aurait
        plus de portée. `sudo()` reste ouvert — c'est par là que passe
        l'archivage lui-même.
        """
        if not self.env.su:
            raise UserError(_(
                "Une version archivée d'un livrable ne peut pas être "
                "modifiée : c'est ce qui donne sa valeur à l'historique "
                "(§25)."))
        return super().write(vals)


class MissionDeliverable(models.Model):
    """Un livrable de mission — §22, §24, §25.

    ```python
    _inherit = ['mail.thread', 'opex.workflow.mixin']
    ```

    **Aucun champ `state`.** Le cycle de vie d'un livrable est lui-même un
    petit workflow, configuré dans `data/mission_deliverable_workflow.xml`.
    C'est la troisième définition du module, et la neuvième du projet — la
    démonstration que le moteur porte aussi les petits processus, pas
    seulement les gros.

    **Cinq étapes, et non quatre comme le livrable d'`opex_innovation`.**
    Le Schéma 9 du §23 intercale « En cours » entre « À faire » et
    « Soumise », et c'est le `Module3_OPEX_Intervenants.md` qui fait foi sur
    l'UX. La distinction n'est pas cosmétique : sans elle, « pas commencé » et
    « commencé, pas rendu » se confondent, et le §43 ne peut plus signaler un
    livrable en retard sur ce qui a réellement démarré.

    **Les jalons du §22 ne sont pas un modèle séparé.** « Une mission peut
    être divisée en plusieurs étapes ; chaque étape peut avoir une date, un
    responsable, un statut, un livrable. » Un objet de plus qui porterait un
    statut dérivé de celui de ses livrables serait un second récit de la même
    histoire — et c'est toujours le second qui se désynchronise. Le jalon est
    donc un **libellé de regroupement** (`jalon`) porté par le livrable, et le
    « statut de l'étape » se lit sur les livrables qui la composent.
    """

    _name = 'opex.mission.deliverable'
    _description = "Livrable d'une mission"
    _inherit = ['mail.thread', 'opex.workflow.mixin']
    _order = 'mission_id, sequence, deadline, id'

    mission_id = fields.Many2one(
        'opex.mission.request',
        string="Mission",
        required=True,
        ondelete='cascade',
        index=True,
    )
    assignment_id = fields.Many2one(
        'opex.mission.assignment',
        string="Affectation",
        ondelete='set null',
        help="L'intervenant qui doit produire ce livrable.",
    )
    partner_id = fields.Many2one(
        related='assignment_id.partner_id',
        string="Intervenant",
        store=True,
        readonly=True,
        index=True,
    )

    name = fields.Char(string="Livrable", required=True, tracking=True)
    description = fields.Text(string="Ce qui est attendu")
    deliverable_type = fields.Selection(
        [
            ('rapport', "Rapport"),
            ('document', "Document de travail"),
            ('presentation', "Présentation"),
            ('formation', "Support de formation"),
            ('procedure', "Procédure"),
            ('outil', "Outil ou modèle"),
            ('autre', "Autre"),
        ],
        string="Type",
        default='rapport',
    )

    #: §22 — le plan de mission. Un libellé, pas un modèle : voir la docstring.
    jalon = fields.Char(
        string="Jalon",
        help="L'étape du plan de mission à laquelle ce livrable se rattache "
             "(§22). Plusieurs livrables peuvent partager le même jalon.",
    )
    sequence = fields.Integer(string="Ordre", default=10)

    #: §28 — « les livrables sont complets ». C'est ce booléen que lisent les
    #: deux compteurs de la mission, donc les règles 5 et 6 du §39.
    is_required = fields.Boolean(
        string="Obligatoire",
        default=True,
        help="Un livrable obligatoire bloque la soumission de la mission tant "
             "qu'il n'est pas déposé, et sa clôture tant qu'il n'est pas "
             "validé (règle 6 du §39).",
    )
    criteres_acceptation = fields.Text(
        string="Critères d'acceptation",
        help="§22 — ce sur quoi le validateur se prononcera. Écrits avant le "
             "dépôt, ils évitent le « ce n'est pas ce que j'attendais » qui "
             "n'a pas de réponse.",
    )

    deadline = fields.Date(string="Échéance", tracking=True)
    #: `search=` et non `store=True`.
    #:
    #: Un champ calculé non stocké n'est pas cherchable : le filtre « En
    #: retard » de la vue `search` faisait échouer le **chargement du module**
    #: (« Unsearchable field "en_retard" »). Deux issues, une seule bonne :
    #: recopier la logique dans le domaine du filtre — deux définitions du
    #: retard, qui divergeraient au premier ajustement — ou donner sa méthode
    #: de recherche au champ. Le stockage, lui, est exclu : `en_retard` dépend
    #: de la date du jour et se figerait au dernier recalcul.
    en_retard = fields.Boolean(
        string="En retard",
        compute='_compute_execution_facts',
        search='_search_en_retard',
    )
    is_submitted = fields.Boolean(
        string="Déposé", compute='_compute_execution_facts')
    is_validated = fields.Boolean(
        string="Validé", compute='_compute_execution_facts')

    file = fields.Binary(string="Fichier", attachment=True)
    filename = fields.Char(string="Nom du fichier")
    version = fields.Integer(
        string="Version", default=1, readonly=True,
        help="Incrémentée à chaque nouvelle soumission après correction.")
    version_ids = fields.One2many(
        'opex.mission.deliverable.version', 'deliverable_id',
        string="Versions précédentes", readonly=True)
    version_count = fields.Integer(
        string="Versions archivées", compute='_compute_version_count')

    # ------------------------------------------------------------
    # Calculs
    # ------------------------------------------------------------
    #
    # Les trois faits d'exécution partagent une méthode, et **aucun n'est
    # stocké**. Le registre refuse qu'une même méthode produise du stocké et du
    # non stocké (`registry.py:543`, règle 9 du CLAUDE.md). `en_retard`
    # dépendant de la date du jour, le stocker le figerait au dernier recalcul :
    # un livrable deviendrait en retard le jour où quelqu'un ouvre sa fiche.

    @api.depends('deadline', 'workflow_stage_id')
    def _compute_execution_facts(self):
        today = fields.Date.context_today(self)
        for deliverable in self:
            code = deliverable.workflow_stage_id.sudo().code
            deliverable.is_submitted = code in self._SUBMITTED_CODES
            deliverable.is_validated = code == 'validated'
            deliverable.en_retard = bool(
                deliverable.deadline
                and deliverable.deadline < today
                and code not in self._SUBMITTED_CODES
            )

    #: Les étapes où le livrable est entre les mains du valideur : il n'est
    #: plus « en retard » du fait de l'intervenant. Nommées une fois, lues par
    #: le calcul **et** par la recherche — c'est ce qui garantit que les deux
    #: répondent la même chose.
    _SUBMITTED_CODES = ('submitted', 'validated')

    def _search_en_retard(self, operator, value):
        """Traduit « en retard » en domaine sur des colonnes réelles.

        La même définition que `_compute_execution_facts`, exprimée en
        domaine : échéance dépassée **et** livrable pas encore soumis.

        `context_today` et non `fields.Date.today()` : le retard se juge dans
        le fuseau de l'utilisateur, comme le calcul le fait déjà.
        """
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise UserError(_(
                "« En retard » ne se compare qu'à Vrai ou Faux."))
        late = (operator == '=') == value

        today = fields.Date.context_today(self)
        domain = [
            ('deadline', '<', today),
            ('workflow_stage_id.code', 'not in', list(self._SUBMITTED_CODES)),
        ]
        if late:
            return domain
        return ['!'] + domain

    @api.depends('version_ids')
    def _compute_version_count(self):
        for deliverable in self:
            deliverable.version_count = len(deliverable.version_ids)

    @api.depends('name', 'version')
    def _compute_display_name(self):
        for deliverable in self:
            deliverable.display_name = "%s — v%s" % (
                deliverable.name or '', deliverable.version)

    # ------------------------------------------------------------
    # Création
    # ------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        deliverables = super().create(vals_list)
        for deliverable in deliverables:
            deliverable._link_assignment()
            deliverable.start_workflow(DELIVERABLE_WORKFLOW_CODE)
            deliverable._grant_actors()
        return deliverables

    def _link_assignment(self):
        """Rattache l'affectation en cours de la mission, si elle existe.

        Silencieux quand il n'y en a pas : un responsable peut préparer les
        livrables attendus **avant** qu'un intervenant soit retenu — c'est même
        ce que le §22 décrit, le plan de mission se dessinant à la création de
        l'appel.
        """
        self.ensure_one()
        if self.assignment_id:
            return False
        assignment = self.mission_id.sudo().assignment_ids.filtered('active')[:1]
        if assignment:
            self.sudo().assignment_id = assignment.id
        return bool(assignment)

    def _grant_actors(self):
        """Qui agit sur ce livrable : l'intervenant, le responsable, le client.

        Les acteurs sont posés depuis `partner_id` et depuis les acteurs de
        la **mission**, jamais depuis l'utilisateur courant. C'est le même
        motif qu'aux Extensions 1 et 7 : un responsable qui prépare le plan de
        mission créerait sinon des livrables dont il serait l'intervenant.

        Le client est acteur en `limited` : le §21 dit qu'il suit les
        livrables, et le §28 qu'il participe à la validation finale. Il n'a
        aucune transition ouverte ici — voir la définition.
        """
        self.ensure_one()
        instance = self.sudo().workflow_instance_id
        if not instance:
            return False

        roles = {
            code: self.env.ref(xmlid, raise_if_not_found=False)
            for code, xmlid in (
                ('intervenant', INTERVENANT_ROLE),
                ('client', CLIENT_ROLE),
            )
        }

        intervenant = self.partner_id.sudo().user_ids[:1]
        if roles['intervenant'] and intervenant:
            instance.add_actor(roles['intervenant'], intervenant, 'full')

        client = self.mission_id.sudo().client_id.user_ids[:1]
        if roles['client'] and client:
            instance.add_actor(roles['client'], client, 'limited')
        return True

    # ------------------------------------------------------------
    # §25 — la nouvelle version après une correction
    # ------------------------------------------------------------

    def submit_new_version(self, file=False, filename=False, user=None):
        """Archive la version refusée, dépose la nouvelle, franchit l'étape.

        **L'ordre compte, et c'est tout l'intérêt de la méthode.** On fige
        *avant* d'écrire : après, `file` porte déjà le nouveau contenu et
        l'archive serait un double de la version courante. L'historique
        existerait, et ne contiendrait rien d'utile — le pire des deux mondes,
        parce qu'on le croirait bon.

        La transition, elle, passe par le moteur comme les autres. Ce que fait
        cette méthode, c'est ce que le moteur ne sait pas faire : recopier un
        fichier dans une archive. Elle ne décide pas du droit de passer —
        `_check_transition_allowed()` tranche, et lui seul.
        """
        self.ensure_one()
        user = user or self.env.user

        if self.sudo().workflow_stage_id.code != 'correction_requested':
            raise UserError(_(
                "Une nouvelle version ne se dépose qu'après une demande de "
                "correction. « %(livrable)s » est à l'étape « %(etape)s »."
            ) % {
                'livrable': self.display_name,
                'etape': self.workflow_stage_label or _("inconnue"),
            })

        self._archive_current_version()

        values = {'version': self.version + 1}
        if file:
            values.update({'file': file, 'filename': filename or self.filename})
        self.sudo().write(values)

        return self.with_user(user).sudo().workflow_do_transition(
            self._deliverable_transition('deliverable_resubmit'))

    def _archive_current_version(self):
        """Fige la version courante, avec le motif du refus qui l'a visée.

        Le motif se lit dans le **journal d'audit du moteur** : c'est le
        commentaire obligatoire de « Demander une correction ». Le recopier sur
        le livrable au moment du refus aurait été plus simple à lire, et faux
        dès le second refus — il aurait écrasé le premier.

        Le dernier refus est retrouvé par une **compréhension** sur
        l'historique trié, jamais par `mapped()` : un livrable refusé deux fois
        repasse par la même étape, et `mapped()` sur un Many2one dédoublonne —
        le second refus disparaîtrait, et l'archive porterait le motif du
        premier.
        """
        self.ensure_one()
        instance = self.sudo().workflow_instance_id
        motif = False
        if instance:
            refus = [
                line for line in instance.history_ids.sorted('id')
                if line.to_stage_id.code == 'correction_requested'
            ]
            motif = refus[-1].comment if refus else False

        return self.env['opex.mission.deliverable.version'].sudo().create({
            'deliverable_id': self.id,
            'version': self.version,
            'file': self.file,
            'filename': self.filename,
            'author_id': self.partner_id.id or False,
            'motif_correction': motif,
        })

    def _deliverable_transition(self, code):
        transition = self.sudo().workflow_definition_id.transition_ids.filtered(
            lambda t: t.code == code)
        if not transition:
            raise UserError(_(
                "La transition « %s » n'est pas configurée sur le workflow "
                "des livrables.") % code)
        return transition

    # ------------------------------------------------------------
    # Ce que l'intervenant et le responsable doivent lire
    # ------------------------------------------------------------

    def correction_history(self):
        """Les corrections demandées, dans l'ordre, avec leur motif.

        Compréhension, jamais `mapped()` — même raison qu'au-dessus, et
        c'est ici qu'elle se voit : deux refus successifs sur le même livrable
        n'en feraient qu'un, et l'écran affirmerait qu'on n'a rien reproché
        deux fois.
        """
        self.ensure_one()
        instance = self.sudo().workflow_instance_id
        if not instance:
            return []
        return [
            {
                'date': line.date,
                'auteur': line.user_id.partner_id.display_name or '',
                'motif': line.comment or '',
            }
            for line in instance.history_ids.sorted('id')
            if line.to_stage_id.code == 'correction_requested'
        ]

    def action_view_versions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Versions de « %s »") % self.name,
            'res_model': 'opex.mission.deliverable.version',
            'view_mode': 'list,form',
            'domain': [('deliverable_id', '=', self.id)],
        }
