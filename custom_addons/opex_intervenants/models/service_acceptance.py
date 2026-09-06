"""Le constat de service fait — §27, §28, et la règle 6 du §39.

    « Le client ou le responsable habilité valide la réalisation. »  — §27
    « La validation finale confirme que : les objectifs ont été atteints, les
      livrables sont complets, les corrections ont été effectuées, la
      prestation correspond au contrat. »  — §28

QUATRIÈME DÉFINITION DU MODULE, DIXIÈME DU PROJET

`opex.service.acceptance` porte le mixin et **aucun champ `state`**. Son
avancement — Constat à établir → Validé par le cluster → Service fait — est
`workflow_instance_id.current_stage_id`, comme partout ailleurs.

**Le « Résultat » du §28 n'est pas un champ.** Le document dit « Le système
enregistre : Date de validation, Validateur, Commentaire, Résultat ». Les trois
premiers sont dans le journal d'audit du moteur, qui les écrit de toute façon ;
le quatrième **est l'étape atteinte**. Un `Selection` « résultat » à côté de
l'étape serait un second récit de la même décision, et c'est toujours le second
qui se désynchronise.

C'est la leçon de l'Extension 8 appliquée une seconde fois : le motif du refus
d'un livrable est relu dans le journal plutôt que recopié, et les quatre
validations du §28 le sont aussi. Les six champs de validation de ce modèle
sont **calculés depuis l'historique**, jamais écrits.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .optional_backends import SALE_ORDER

ACCEPTANCE_WORKFLOW_CODE = 'mission_service_acceptance'
INTERVENANT_ROLE = 'opex_intervenants.role_intervenant'
CLIENT_ROLE = 'opex_intervenants.role_client'

#: Non traduit, et volontairement : la valeur sert de sentinelle dans
#: `create()`. Traduite, elle ne se comparerait plus à elle-même d'une langue à
#: l'autre et la séquence cesserait de s'appliquer sans le dire. Même motif
#: qu'`opex.mission.incident` à l'Extension 8.
NEW_REFERENCE = "Nouveau"

#: Les étapes dont l'atteinte vaut validation, par partie. Nommées une fois et
#: lues par le calcul des six champs de validation : deux listes qui
#: divergeraient donneraient deux dates de validation différentes pour le même
#: événement.
CLUSTER_VALIDATION_STAGE = 'cluster_validated'
CLIENT_VALIDATION_STAGE = 'accepted'
DISPUTE_STAGE = 'disputed'


class ServiceAcceptance(models.Model):
    """Le constat de service fait d'une mission — §28.

    Un constat par mission, et non par affectation. Le §28 valide **la
    prestation** — « la prestation correspond au contrat » —, pas le travail de
    chaque intervenant pris séparément ; et la facturation qui en découle part
    au client, une fois. Sur un type de mission à plusieurs intervenants
    (l'exception de la règle 4), le montant à facturer additionne les
    affectations actives.
    """

    _name = 'opex.service.acceptance'
    _description = "Constat de service fait"
    _inherit = ['mail.thread', 'opex.workflow.mixin']
    _order = 'mission_id, id desc'

    name = fields.Char(
        string="Référence", required=True, copy=False, readonly=True,
        default=NEW_REFERENCE, index=True)

    mission_id = fields.Many2one(
        'opex.mission.request',
        string="Mission",
        required=True,
        ondelete='cascade',
        index=True,
    )
    client_id = fields.Many2one(
        related='mission_id.client_id', string="Client", readonly=True)
    assignment_ids = fields.Many2many(
        'opex.mission.assignment',
        'service_acceptance_assignment_rel', 'acceptance_id', 'assignment_id',
        string="Affectations concernées",
        readonly=True,
    )

    #: Une contrainte SQL, pas seulement l'idempotence de `_ensure_acceptance()`.
    #:
    #: Le constat est recréé à chaque passage par « Soumettre les livrables » —
    #: et la boucle de correction du §25 y repasse. Le déclencheur vérifie qu'il
    #: en existe déjà un ; la contrainte tient le cas que le déclencheur ne voit
    #: pas, celui de l'import et du script. Même raisonnement qu'à l'Extension 7
    #: sur `unique(application_id)`.
    _mission_uniq = models.Constraint(
        'unique(mission_id)',
        "Cette mission a déjà un constat de service fait.",
    )

    # ------------------------------------------------------------
    # §28 — les quatre points de la validation finale
    # ------------------------------------------------------------
    #
    # Ces quatre booléens ne sont pas décoratifs : ils sont la **condition**
    # de « Valider (cluster) », par `rule_service_checklist`. Une case à cocher
    # que rien ne lit serait un aide-mémoire ; celles-ci ferment la transition.

    objectifs_atteints = fields.Boolean(
        string="Les objectifs ont été atteints", tracking=True)
    livrables_complets = fields.Boolean(
        string="Les livrables sont complets", tracking=True)
    corrections_effectuees = fields.Boolean(
        string="Les corrections ont été effectuées", tracking=True)
    conforme_contrat = fields.Boolean(
        string="La prestation correspond au contrat", tracking=True)

    observations = fields.Text(
        string="Observations du cluster",
        help="Ce que le contrôle a relevé, au-delà des quatre points du §28.",
    )

    # ------------------------------------------------------------
    # Ce qui sera facturé — §29
    # ------------------------------------------------------------

    currency_id = fields.Many2one(
        'res.currency',
        string="Devise",
        default=lambda self: self.env.company.currency_id,
    )
    montant_a_facturer = fields.Monetary(
        string="Montant à facturer",
        currency_field='currency_id',
        tracking=True,
        help="Repris des affectations à la création du constat, et modifiable "
             "par le cluster tant que le constat n'est pas validé.",
    )

    # --- REBRANCHEMENT `sale` ---------------------------------------------
    #
    # Ce champ était :
    #
    #     sale_order_id = fields.Many2one(
    #         'sale.order', string="Commande de facturation",
    #         readonly=True, ondelete='set null', copy=False)
    #
    # `sale` n'étant pas installé, une `Many2one` vers `sale.order` empêche le
    # registre de démarrer : Odoo ne peut pas résoudre le comodèle, et le
    # module entier devient non installable.
    #
    # La paire ci-dessous conserve **les deux faits** qu'on peut conserver
    # sans le module : l'identifiant et le libellé de la commande. Le jour où
    # `sale` revient, la `Many2one` est rétablie et `sale_order_ref` donne
    # directement les ids à reprendre — aucune donnée n'est perdue, la
    # migration est un `UPDATE` d'une ligne.
    #
    # Aujourd'hui ces deux champs restent vides : rien ne les écrit, puisque
    # `_trigger_invoicing()` s'arrête avant.
    sale_order_ref = fields.Integer(
        string="Commande de facturation (id)",
        readonly=True,
        copy=False,
        help="L'identifiant de la commande de vente émise à la clôture. "
             "Vide tant que le module Ventes n'est pas installé.",
    )
    sale_order_name = fields.Char(
        string="Commande de facturation",
        readonly=True,
        copy=False,
        help="La référence de la commande, conservée en clair pour rester "
             "lisible même sans le module Ventes.",
    )

    #: Ce qui décide de l'affichage des blocs de facturation. Un `t-if` ou un
    #: `invisible` a besoin d'une valeur du dossier, pas d'un appel Python :
    #: c'est ce champ. Non stocké — la réponse dépend des modules installés,
    #: et un `store=True` la figerait au dernier recalcul, c'est-à-dire au
    #: jour d'avant l'installation de `sale`.
    sale_disponible = fields.Boolean(
        string="Facturation disponible",
        compute='_compute_sale_disponible',
        help="Faux tant que le module Ventes n'est pas installé. Les écrans "
             "de facturation s'effacent au lieu d'afficher des champs vides.",
    )

    def _compute_sale_disponible(self):
        available = self.env['opex.optional.backend']._backend_available(
            SALE_ORDER)
        for acceptance in self:
            acceptance.sale_disponible = available

    # ------------------------------------------------------------
    # §28 — « Date de validation, Validateur, Commentaire »
    # ------------------------------------------------------------
    #
    # **Six champs calculés, aucun écrit.** Ils sont relus dans le journal
    # d'audit du moteur, qui les consigne de toute façon — `do_transition()`
    # écrit l'auteur, la date et le commentaire sur chaque ligne d'historique.
    #
    # Les recopier au moment de la transition aurait produit une seconde
    # vérité, et elle aurait dérivé : le constat contesté puis revalidé passe
    # **deux fois** par la validation du cluster, et c'est la seconde qui
    # compte. Un champ écrit au premier passage affirmerait une date périmée
    # sans que rien ne le signale.
    #
    # Aucun n'est stocké — la règle 9 est donc respectée sans effort : une
    # seule méthode, six champs, tous non stockés.

    date_validation_cluster = fields.Datetime(
        string="Validé par le cluster le", compute='_compute_validation_facts')
    validateur_cluster_id = fields.Many2one(
        'res.users', string="Validateur cluster",
        compute='_compute_validation_facts')
    commentaire_cluster = fields.Text(
        string="Commentaire du cluster", compute='_compute_validation_facts')

    date_validation_client = fields.Datetime(
        string="Validé par le client le", compute='_compute_validation_facts')
    validateur_client_id = fields.Many2one(
        'res.users', string="Validateur client",
        compute='_compute_validation_facts')
    commentaire_client = fields.Text(
        string="Commentaire du client", compute='_compute_validation_facts')

    is_accepted = fields.Boolean(
        string="Service fait",
        compute='_compute_validation_facts',
        help="Le constat a atteint son étape finale. C'est ce fait que lit la "
             "condition de « Valider le service fait » sur la mission.",
    )

    # ------------------------------------------------------------
    # La règle 6, exposée là où la condition sait la lire
    # ------------------------------------------------------------
    #
    # `related` non stocké, et c'est ce qui permet à **la même règle** de
    # garder deux transitions.
    #
    # `rule_mission_deliverables_validated` évalue
    # `field('deliverable_unvalidated_count', 1) == 0`, et `field()` lit
    # l'enregistrement piloté par l'instance — ici le constat, là-bas la
    # mission. Sans ce related, la règle serait « fermée » sur le constat par
    # son défaut de repli et « Valider (cluster) » serait infranchissable, sans
    # message utile.
    #
    # Une seconde règle écrite pour le constat aurait été l'autre issue, et la
    # mauvaise : deux définitions du même prédicat divergent au premier
    # ajustement, exactement comme le filtre « En retard » de la règle 16.
    deliverable_unvalidated_count = fields.Integer(
        related='mission_id.deliverable_unvalidated_count',
        string="Livrables obligatoires non validés",
        readonly=True,
    )

    # ------------------------------------------------------------
    # Calculs
    # ------------------------------------------------------------

    @api.depends('workflow_instance_id.history_ids',
                 'workflow_instance_id.current_stage_id')
    def _compute_validation_facts(self):
        """Les validations du §28, relues dans le journal du moteur.

        **Le dernier passage, pas le premier.** Un constat contesté puis
        revalidé repasse par `cluster_validated`, et c'est la seconde date qui
        est la bonne.

        Une compréhension, jamais `mapped()` : `mapped()` sur un Many2one
        déduplique, et les deux passages par la même étape n'en feraient qu'un
        — le défaut serait invisible puisqu'il resterait une date à afficher.
        """
        for acceptance in self:
            entries = acceptance._history_lines()
            cluster = acceptance._last_entry_to(entries, CLUSTER_VALIDATION_STAGE)
            client = acceptance._last_entry_to(entries, CLIENT_VALIDATION_STAGE)

            acceptance.date_validation_cluster = cluster.date if cluster else False
            acceptance.validateur_cluster_id = cluster.user_id if cluster else False
            acceptance.commentaire_cluster = (
                cluster.comment if cluster else False) or False

            acceptance.date_validation_client = client.date if client else False
            acceptance.validateur_client_id = client.user_id if client else False
            acceptance.commentaire_client = (
                client.comment if client else False) or False

            acceptance.is_accepted = (
                acceptance.sudo().workflow_stage_id.code
                == CLIENT_VALIDATION_STAGE)

    def _history_lines(self):
        """L'historique de l'instance, trié, ou rien s'il n'y en a pas."""
        self.ensure_one()
        instance = self.sudo().workflow_instance_id
        return instance.history_ids.sorted('id') if instance else []

    @staticmethod
    def _last_entry_to(entries, stage_code):
        """La **dernière** ligne d'historique menant à cette étape."""
        matching = [line for line in entries
                    if line.to_stage_id.code == stage_code]
        return matching[-1] if matching else None

    @api.depends('name', 'mission_id')
    def _compute_display_name(self):
        for acceptance in self:
            acceptance.display_name = "%s — %s" % (
                acceptance.name or '', acceptance.mission_id.name or '')

    # ------------------------------------------------------------
    # Création
    # ------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', NEW_REFERENCE) == NEW_REFERENCE:
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code(
                    'opex.service.acceptance') or NEW_REFERENCE
        acceptances = super().create(vals_list)
        for acceptance in acceptances:
            acceptance.start_workflow(ACCEPTANCE_WORKFLOW_CODE)
            acceptance._grant_actors()
        return acceptances

    def _grant_actors(self):
        """Le client valide, l'intervenant suit — §27, §28.

        Les acteurs viennent de la **mission**, jamais de l'utilisateur
        courant. C'est le déclencheur de « Soumettre les livrables » qui crée
        le constat : sans cette précaution, le responsable qui franchit cette
        transition deviendrait le client de son propre constat, et validerait
        des deux côtés.

        Le client est en `full` : c'est lui qui prononce la validation finale
        du §28. L'intervenant est en `limited` — il doit voir où en est le
        constat qui conditionne son paiement, il ne le valide pas.
        """
        self.ensure_one()
        instance = self.sudo().workflow_instance_id
        if not instance:
            return False

        roles = {
            code: self.env.ref(xmlid, raise_if_not_found=False)
            for code, xmlid in (('client', CLIENT_ROLE),
                                ('intervenant', INTERVENANT_ROLE))
        }

        client = self.mission_id.sudo().client_id.user_ids[:1]
        if roles['client'] and client:
            instance.add_actor(roles['client'], client, 'full')

        for assignment in self.sudo().assignment_ids:
            user = assignment.partner_id.sudo().user_ids[:1]
            if roles['intervenant'] and user:
                instance.add_actor(roles['intervenant'], user, 'limited')
        return True

    # ------------------------------------------------------------
    # Ce que les écrans lisent
    # ------------------------------------------------------------

    def validation_entries(self):
        """Les validations et les contestations, dans l'ordre, avec leur motif.

        Le pendant de `correction_history()` de l'Extension 8 : la trace
        complète du §28, y compris les tours qui ont échoué. Un constat validé
        du premier coup et un constat validé après une contestation ne se
        lisent pas de la même façon, et c'est précisément ce que la règle 9
        du §39 demande de conserver.
        """
        self.ensure_one()
        watched = (CLUSTER_VALIDATION_STAGE, CLIENT_VALIDATION_STAGE,
                   DISPUTE_STAGE)
        return [
            {
                'date': line.date,
                'etape': line.to_stage_id.user_label or line.to_stage_id.name,
                'auteur': line.user_id.partner_id.display_name or '',
                'commentaire': line.comment or '',
            }
            for line in self._history_lines()
            if line.to_stage_id.code in watched
        ]

    # ------------------------------------------------------------
    # Navigation vers la facturation — REBRANCHEMENT `sale`
    # ------------------------------------------------------------
    #
    # Les deux méthodes sont conservées **en entier** : ce sont elles qu'il
    # faudra rebrancher, et les réécrire de mémoire coûterait plus que de les
    # lire. Elles commencent désormais par résoudre le modèle, et rendent
    # False s'il est absent.
    #
    # Rendre False plutôt que lever : ces méthodes sont appelées par des
    # boutons, et les boutons sont masqués par `sale_disponible`. Si l'un
    # d'eux réapparaissait — vue héritée, action ajoutée —, il ne ferait rien
    # au lieu de rendre un 500.

    def _sale_order(self):
        """La commande de vente, ou None si `sale` n'est pas installé."""
        self.ensure_one()
        return self.env['opex.optional.backend']._backend_record(
            SALE_ORDER, self.sale_order_ref)

    def action_view_sale_order(self):
        self.ensure_one()
        order = self._sale_order()
        if order is None:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _("Commande de facturation"),
            'res_model': SALE_ORDER,
            'view_mode': 'form',
            'res_id': order.id,
        }

    def action_view_invoices(self):
        self.ensure_one()
        order = self._sale_order()
        if order is None:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _("Factures"),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', order.invoice_ids.ids)],
        }

    # ------------------------------------------------------------
    # §27 et §28 — le client prononce, depuis le portail
    # ------------------------------------------------------------
    #
    # POURQUOI CES DEUX MÉTHODES EXISTENT
    #
    # Le moteur ouvrait déjà `service_validate_client` et `service_dispute`
    # au rôle `client`, mais le portail est en **lecture seule** sur ce
    # modèle (`rwcu=1000`) : franchir la transition demande d'écrire
    # l'instance, donc un `sudo()`. Or un `sudo()` posé dans un controller
    # remplace l'`ir.rule` par la confiance qu'on accorde à ce fichier.
    #
    # Le contrôle vit donc **ici**, sur le modèle, exactement comme
    # `_check_manager()` de `competence_arbitrage.py:307` : ces méthodes
    # s'appellent aussi par script, par import et par requête forgée, et un
    # écran n'est pas une garde.
    #
    # ⚠ Elles ne rejugent pas le rôle ni l'étape — c'est le travail du
    # moteur, et le refaire ici en ferait une seconde vérité. Elles
    # répondent à la seule question que le moteur ne pose pas : **cette
    # session est-elle le client de ce constat ?**

    def _check_client(self):
        """Le prononcé du §28 appartient au client, et à lui seul.

        L'intervenant est acteur du constat en `limited` — il voit où en est
        ce qui conditionne son paiement. Le laisser valider lui ferait
        prononcer la réception de sa propre prestation.

        Le personnel des missions n'a pas besoin de passer par ici : il a
        `service_validate_client` par son rôle et son propre écran. Cette
        garde protège le chemin **portail**, qui est le seul à devoir
        `sudo()`.
        """
        self.ensure_one()
        if self.sudo().mission_id.client_id != self.env.user.partner_id:
            raise UserError(_(
                "Le constat de service fait est prononcé par le client de la "
                "mission. Votre compte n'est pas celui du client de ce "
                "dossier."))
        return True

    def _portal_do(self, code, comment=None):
        """Franchit une transition du constat pour le compte du client.

        Le `sudo()` est **encadré** : le contrôle d'appelant a eu lieu juste
        avant, et la transition est cherchée dans celles que le moteur ouvre
        à **cet utilisateur** — pas à `sudo()`. Résoudre la transition en
        `sudo()` ferait franchir au client des transitions réservées au
        responsable, ce que ni le rôle ni l'écran ne montreraient.
        """
        self.ensure_one()
        self._check_client()
        transition = self.workflow_instance_id.sudo()\
            .available_transitions(user=self.env.user)\
            .filtered(lambda t: t.code == code)[:1]
        if not transition:
            raise UserError(_(
                "Cette action n'est pas disponible : soit le constat a changé "
                "d'étape, soit votre rôle ne l'autorise pas."))
        # ⚠ L'ORDRE DES DEUX APPELS COMPTE, et il a été mesuré.
        #
        # `with_user()` **après** `sudo()` remet `env.su` à False :
        # `record.sudo().with_user(u).env.su` vaut `False`, alors que
        # `record.with_user(u).sudo().env.su` vaut `True`. Écrit dans le
        # mauvais ordre, le `sudo()` ne fait rien — et le code continue de
        # fonctionner, parce que la transition écrit l'**instance** et non le
        # constat. Il tomberait le jour où une action configurée sur cette
        # transition écrirait le constat lui-même, c'est-à-dire longtemps
        # après qu'on ait oublié pourquoi.
        #
        # `sudo()` ne change pas `env.user` : le journal du moteur porte bien
        # le client comme auteur, ce qui est vérifié — la ligne d'historique
        # de « Service fait contesté » nomme le compte du client.
        return self.sudo().workflow_do_transition(
            transition, comment=comment or '')

    def action_portal_validate(self):
        """« Je valide le service fait » — §28, second passage."""
        return self._portal_do('service_validate_client')

    def action_portal_dispute(self, comment=None):
        """« Je conteste » — le motif est exigé par la configuration.

        `requires_comment` est porté par la transition, et c'est
        `do_transition()` qui refuse un commentaire vide
        (`workflow_instance.py:722`). On transmet, on ne redouble pas.
        """
        return self._portal_do('service_dispute', comment=comment)
