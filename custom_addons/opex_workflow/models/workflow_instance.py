import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class WorkflowInstance(models.Model):
    """Un enregistrement métier en train de parcourir un workflow.

    Le couple `res_model` / `res_id` plutôt qu'un Many2one : c'est ce qui rend
    le moteur utilisable sur **n'importe quel** modèle, y compris natif Odoo,
    sans que le moteur ait à déclarer une relation vers chaque modèle métier
    qu'il pilotera un jour.
    """

    _name = 'opex.workflow.instance'
    _description = "Instance de workflow"
    _order = 'date_start desc, id desc'

    definition_id = fields.Many2one(
        'opex.workflow.definition',
        string="Workflow",
        required=True,
        ondelete='restrict',
        index=True,
    )
    res_model = fields.Char(
        string="Modèle", required=True, index=True, readonly=True)
    res_id = fields.Integer(
        string="Identifiant", required=True, index=True, readonly=True)
    resource_ref = fields.Reference(
        selection='_selection_resource_model',
        string="Enregistrement",
        compute='_compute_resource_ref',
        help="Lien de navigation vers l'objet métier piloté.",
    )

    current_stage_id = fields.Many2one(
        'opex.workflow.stage',
        string="Étape courante",
        ondelete='restrict',
        index=True,
        readonly=True,
    )
    current_stage_label = fields.Char(
        string="Étape (utilisateur)",
        related='current_stage_id.user_label',
    )
    state = fields.Selection(
        [
            ('running', "En cours"),
            ('done', "Terminée"),
            ('cancelled', "Annulée"),
        ],
        string="État",
        default='running',
        required=True,
        readonly=True,
        index=True,
    )
    initiator_id = fields.Many2one(
        'res.users',
        string="Initiateur",
        default=lambda self: self.env.user,
        readonly=True,
    )
    date_start = fields.Datetime(
        string="Démarrée le", default=fields.Datetime.now, readonly=True)
    date_end = fields.Datetime(string="Terminée le", readonly=True)

    # ------------------------------------------------------------
    # Sous-workflows (Extension 8)
    # ------------------------------------------------------------
    parent_instance_id = fields.Many2one(
        'opex.workflow.instance',
        string="Dossier parent",
        ondelete='set null',
        index=True,
        readonly=True,
        help="Renseigné quand cette instance a été démarrée comme "
             "sous-workflow. Sans ce lien, un enregistrement portant plusieurs "
             "sous-processus ne dirait pas lequel a déclenché lequel.",
    )
    child_instance_ids = fields.One2many(
        'opex.workflow.instance', 'parent_instance_id',
        string="Sous-workflows")

    # ------------------------------------------------------------
    # SLA (Extension 8)
    # ------------------------------------------------------------
    date_stage_start = fields.Datetime(
        string="Sur cette étape depuis",
        default=fields.Datetime.now,
        readonly=True,
        help="Horodatage de l'entrée dans l'étape courante. Stocké plutôt que "
             "déduit de l'historique : le calcul des retards s'exécute sur "
             "toute la base, il doit tenir dans une requête.",
    )
    sla_deadline = fields.Datetime(
        string="Échéance",
        compute='_compute_sla_deadline',
        store=True,
        help="Date au-delà de laquelle le dossier est en retard sur son étape.",
    )
    # Écrit par le cron, pas calculé : « en retard » dépend de l'heure qu'il
    # est. Un champ calculé stocké se figerait au dernier recalcul et un champ
    # calculé non stocké ne serait pas filtrable. C'est le cron qui fait foi,
    # comme le demande la spécification.
    is_late = fields.Boolean(string="En retard", readonly=True, index=True)
    sla_notified_stage_id = fields.Many2one(
        'opex.workflow.stage',
        string="Retard déjà signalé pour",
        readonly=True,
        ondelete='set null',
        help="Étape pour laquelle l'alerte a déjà été envoyée. Évite de "
             "renotifier à chaque passage du cron : une alerte répétée toutes "
             "les heures cesse d'être lue.",
    )

    actor_ids = fields.One2many(
        'opex.workflow.instance.actor', 'instance_id', string="Acteurs")
    # One2many **filtré**, et c'est indispensable, pas cosmétique.
    #
    # Une `ir.rule` écrite `['&', ('actor_ids.user_id','=',user.id),
    # ('actor_ids.access_level','!=','none')]` serait fausse : Odoo produit
    # deux sous-requêtes indépendantes, et les deux conditions pourraient être
    # satisfaites par **deux lignes différentes**. Un utilisateur révoqué
    # garderait donc l'accès dès qu'un autre acteur du dossier, lui, l'a.
    #
    # En portant le filtre sur le champ, la traversée `active_actor_ids.user_id`
    # ne voit que les lignes réellement actives : les deux conditions portent
    # forcément sur la même ligne.
    active_actor_ids = fields.One2many(
        'opex.workflow.instance.actor', 'instance_id',
        domain=[('access_level', '!=', 'none')],
        string="Acteurs ayant accès",
    )
    history_ids = fields.One2many(
        'opex.workflow.history', 'instance_id', string="Historique")

    @api.depends('date_stage_start', 'current_stage_id.sla_days', 'state')
    def _compute_sla_deadline(self):
        for instance in self:
            days = instance.current_stage_id.sla_days
            if instance.state == 'running' and days and instance.date_stage_start:
                instance.sla_deadline = instance.date_stage_start + timedelta(days=days)
            else:
                instance.sla_deadline = False

    @api.model
    def _selection_resource_model(self):
        models_ = self.env['ir.model'].sudo().search([('transient', '=', False)])
        return [(model.model, model.name) for model in models_]

    @api.depends('res_model', 'res_id')
    def _compute_resource_ref(self):
        for instance in self:
            if instance.res_model and instance.res_id:
                instance.resource_ref = '%s,%s' % (instance.res_model, instance.res_id)
            else:
                instance.resource_ref = False

    @api.depends('definition_id', 'current_stage_id', 'res_model', 'res_id')
    def _compute_display_name(self):
        for instance in self:
            record = instance._get_record()
            # `sudo()` sur la seule lecture du libellé : sans lui, la liste des
            # instances lèverait une AccessError chez tout utilisateur n'ayant
            # pas le droit de lire l'objet métier — alors qu'il a le droit de
            # voir passer le dossier.
            label = record.sudo().display_name if record else '%s#%s' % (
                instance.res_model, instance.res_id)
            instance.display_name = "%s — %s" % (
                label, instance.current_stage_id.name or _("non démarrée"))

    # ------------------------------------------------------------
    # L'enregistrement piloté
    # ------------------------------------------------------------

    def _get_record(self):
        """L'enregistrement métier, ou un recordset vide s'il n'existe plus.

        Recordset vide plutôt que `None` : `.exists()` renvoie déjà le bon
        modèle vide quand l'enregistrement a été supprimé, et une expression de
        condition qui lit `record.montant` dessus reçoit `False` au lieu de
        lever. Un dossier supprimé bloque donc les transitions conditionnelles
        au lieu de faire tomber la page.

        Seul le cas d'un modèle absent du registre (module désinstallé) n'a pas
        de recordset naturel à renvoyer ; il est traité comme « pas
        d'enregistrement ».
        """
        self.ensure_one()
        if not self.res_model or self.res_model not in self.env:
            return self.browse()
        return self.env[self.res_model].browse(self.res_id).exists()

    # ------------------------------------------------------------
    # Helpers exposés aux expressions de conditions
    # ------------------------------------------------------------

    # Conventions de nommage attendues sur le modèle hôte pour `has_document()`.
    # Ce sont des noms structurels, pas du vocabulaire métier : le moteur ne
    # sait toujours pas ce qu'est un « pitch deck », il sait seulement qu'un
    # enregistrement peut porter une collection de documents typés. Un modèle
    # hôte qui range ses documents autrement surcharge `_workflow_has_document`.
    _DOCUMENT_FIELD = 'document_ids'
    _DOCUMENT_TYPE_FIELD = 'document_type'

    def _has_document(self, document_type):
        """`has_document('pitch_deck')` — l'enregistrement porte-t-il ce document ?

        Générique par construction : le type est un **paramètre**, jamais un nom
        de méthode. Un `has_pitch_deck()` obligerait à écrire du Python dans le
        moteur pour chaque nouveau type de pièce — c'est-à-dire exactement ce
        que le test d'acceptation interdit.

        Tolérant à tout : modèle sans documents, champ absent, enregistrement
        supprimé. Renvoie False plutôt que de lever.
        """
        self.ensure_one()
        record = self._get_record()
        if not record:
            return False
        record = record.sudo()

        # Le modèle hôte peut définir sa propre notion de document.
        if hasattr(record, '_workflow_has_document'):
            try:
                return bool(record._workflow_has_document(document_type))
            except Exception:
                _logger.warning(
                    "opex_workflow: _workflow_has_document a échoué sur %s#%s",
                    self.res_model, self.res_id, exc_info=True)
                return False

        field_name = getattr(record, '_workflow_document_field', self._DOCUMENT_FIELD)
        type_field = getattr(
            record, '_workflow_document_type_field', self._DOCUMENT_TYPE_FIELD)
        if field_name not in record._fields:
            return False
        documents = record[field_name]
        if type_field not in documents._fields:
            return bool(documents)
        return bool(documents.filtered(lambda d: d[type_field] == document_type))

    def _field(self, name, default=False):
        """`field('score')` — valeur d'un champ, tolérante à son absence.

        Un workflow configuré peut nommer un champ que le modèle piloté n'a pas
        (encore). Renvoyer `default` plutôt que lever permet à la même règle de
        servir sur deux modèles différents, dont l'un seulement porte le champ.
        """
        self.ensure_one()
        record = self._get_record()
        if not record or name not in record._fields:
            return default
        return record.sudo()[name]

    def _evaluation_context(self):
        """Namespace offert aux expressions de conditions.

        Reconstruit à chaque appel : `safe_eval` **mute** le dictionnaire qu'on
        lui passe (il y réinjecte les variables créées pendant l'évaluation).
        Un contexte partagé entre deux règles verrait donc la seconde hériter
        des variables de la première.

        `record` est en `sudo()` : le droit de déclencher une transition est
        tranché par `_check_transition_allowed()`, pas par la capacité de
        l'utilisateur à lire tel ou tel champ. Sans cela, un contrôleur qui n'a
        pas accès au montant verrait toutes ses conditions financières échouer
        silencieusement.
        """
        self.ensure_one()
        record = self._get_record()
        return {
            'record': record.sudo() if record else record,
            'instance': self,
            'user': self.env.user,
            'stage': self.current_stage_id,
            'has_document': self._has_document,
            'field': self._field,
            'subworkflow_done': self._subworkflow_done,
        }

    def _subworkflow_done(self, definition_code):
        """`subworkflow_done('accompagnement')` — ce sous-processus est-il fini ?

        Cherche sur le **même enregistrement métier**, pas seulement parmi les
        enfants directs : un sous-workflow lancé par une autre branche du
        processus compte tout autant. C'est ce qui rend un même sous-processus
        réutilisable d'un workflow à l'autre — l'accompagnement se déroule une
        fois, et les deux processus qui l'attendent le voient terminé.

        Tolérant : un code inconnu renvoie False plutôt que de lever, comme
        tous les helpers de condition.
        """
        self.ensure_one()
        if not self.res_model or not self.res_id:
            return False
        return bool(self.sudo().search_count([
            ('res_model', '=', self.res_model),
            ('res_id', '=', self.res_id),
            ('definition_id.code', '=', definition_code),
            ('state', '=', 'done'),
        ]))

    def _evaluate_expression(self, expression):
        """Évalue une expression et renvoie sa **valeur brute**.

        Distincte de `_evaluate_rule()`, qui ramène tout à un booléen : une
        action `set_field` a besoin de la valeur, pas de sa vérité. Ne capture
        rien — l'appelant décide de ce qu'il advient d'un échec, et il ne décide
        pas la même chose selon qu'il s'agit d'une condition (fausse) ou d'une
        action (journalisée).
        """
        self.ensure_one()
        return safe_eval(expression, self._evaluation_context())

    def _evaluate_flag(self, expression, default=False, label=None):
        """Évalue une expression en booléen, **sans jamais lever**.

        Même contexte et même tolérance que `_evaluate_rule()`, pour une
        expression nue plutôt qu'une règle nommée : c'est ce dont ont besoin
        les conditions d'affichage et d'obligation des formulaires dynamiques.

        `default` est renvoyé en cas d'erreur. Il vaut False partout, et les
        conséquences sont volontairement asymétriques :

        - condition d'affichage en erreur → champ **non rendu**. Un champ
          affiché par erreur peut divulguer ; un champ absent ne fait que
          manquer.
        - condition d'obligation en erreur → champ **facultatif**. Rendre un
          champ obligatoire sur une faute de frappe rendrait le formulaire
          insoumettable pour tout le monde.
        """
        self.ensure_one()
        if not expression:
            return default
        try:
            return bool(safe_eval(expression, self._evaluation_context()))
        except Exception as error:  # noqa: BLE001 — tolérance volontaire
            _logger.warning(
                "opex_workflow: %s a échoué sur l'instance %s : %s",
                label or _("une expression"), self.id, error,
            )
            return default

    def _evaluate_rule(self, rule):
        """Évalue une règle. Renvoie (résultat booléen, erreur ou False).

        Trois exigences, non négociables :

        1. `safe_eval` uniquement, jamais `eval()` — une expression est saisie
           depuis l'interface, elle doit être traitée comme une donnée hostile.
        2. Une expression qui lève **ne casse jamais la page** : on capture, on
           journalise, et la condition est considérée **fausse**. Un moteur
           configurable dont une faute de frappe blanchit l'écran est
           inutilisable.
        3. L'échec reste lisible : l'appelant reçoit l'erreur pour la consigner
           dans l'historique, et l'utilisateur voit le message de la règle.
        """
        self.ensure_one()
        try:
            result = safe_eval(rule.expression, self._evaluation_context())
            return bool(result), False
        except Exception as error:  # noqa: BLE001 — capture volontairement large
            _logger.warning(
                "opex_workflow: la règle « %s » (%s) a échoué sur l'instance %s : %s",
                rule.name, rule.code, self.id, error,
            )
            return False, str(error)

    def _evaluate_conditions(self, transition):
        """Évalue toutes les conditions d'une transition.

        Renvoie (ok, messages bloquants, note d'audit). Les conditions sont en
        **ET** : toutes doivent être vraies. Un OU s'écrit dans l'expression
        elle-même (`a or b`) plutôt que par un arbre booléen en base — plus
        simple à configurer, et suffisant pour tous les cas des documents
        sources.

        Toutes les règles sont évaluées, même après un premier échec : un
        utilisateur qui corrige une condition à la fois pour découvrir la
        suivante perd un aller-retour à chaque fois.
        """
        self.ensure_one()
        blocking = []
        notes = []
        for rule in transition.sudo().condition_ids:
            passed, error = self._evaluate_rule(rule)
            if error:
                notes.append("%s — erreur d'évaluation : %s" % (rule.name, error))
                blocking.append(rule.message)
            elif passed:
                notes.append("%s" % rule.name)
            else:
                notes.append("%s" % rule.name)
                blocking.append(rule.message)
        return (not blocking), blocking, "\n".join(notes)

    # ------------------------------------------------------------
    # Contrôle d'accès — LE point unique
    # ------------------------------------------------------------

    def _user_roles(self, user):
        """Rôles portés par cet utilisateur sur **cette** instance.

        Deux sources, cumulées :

        - le rôle est adossé à un groupe Odoo permanent (`role.group_id`) et
          l'utilisateur appartient à ce groupe ;
        - une ligne `instance.actor` le désigne pour ce dossier précis.

        C'est la seconde qui porte le principe de visibilité des documents
        sources : être enregistré comme investisseur ne donne pas accès à tous
        les projets, c'est la ligne d'acteur qui donne accès à celui-ci.
        """
        self.ensure_one()
        Role = self.env['opex.workflow.role']
        roles = Role.browse()

        group_ids = set(user.sudo().all_group_ids.ids)
        if group_ids:
            roles |= Role.sudo().search([('group_id', 'in', list(group_ids))])

        actor_roles = self.sudo().actor_ids.filtered(
            lambda a: a.user_id == user and a.access_level != 'none'
        ).role_id
        return roles | actor_roles

    # Hiérarchie des niveaux d'accès. Comparer des rangs plutôt que des chaînes
    # évite le `if level == 'full' or level == 'limited'` qui se recopie et
    # finit par diverger d'un appelant à l'autre.
    _ACCESS_RANK = {'none': 0, 'limited': 1, 'full': 2}

    def _has_access(self, user=None, level='limited'):
        """**LA** fonction de visibilité — « cet utilisateur voit-il ce dossier ? »

        Traduit la règle des documents sources :

            Identité + rôle + relation au dossier + étape → droits d'accès

        Les trois premiers termes sont ici : l'identité est `user`, le rôle et
        la relation au dossier sont la ligne `instance.actor`. Le quatrième —
        l'étape — n'entre pas dans la *visibilité* mais dans le *droit d'agir*,
        qui est tranché par `_check_transition_allowed()`. Les deux questions
        sont distinctes : voir un dossier n'est pas pouvoir le faire avancer.

        Être enregistré comme investisseur ne donne accès à aucun projet ; c'est
        la ligne d'acteur qui donne accès à **celui-ci**.

        Comme `_check_transition_allowed()` pour les transitions, c'est le seul
        endroit où la question se tranche. Les `ir.rule` en sont la traduction
        déclarative pour la base ; tout code Python qui a besoin de la réponse
        appelle cette méthode et n'en réécrit pas une variante.
        """
        self.ensure_one()
        user = user or self.env.user
        required = self._ACCESS_RANK.get(level, 1)

        # Le personnel du workflow voit tout : c'est le sens même des deux
        # groupes, et c'est ce qui permet à un gestionnaire de débloquer un
        # dossier dont il n'est pas acteur.
        if self._is_workflow_manager(user) or user.sudo()._has_group(
                'opex_workflow.group_workflow_designer'):
            return True

        levels = self.sudo().actor_ids.filtered(
            lambda a: a.user_id == user).mapped('access_level')
        granted = max((self._ACCESS_RANK.get(value, 0) for value in levels),
                      default=0)
        return granted >= required

    # ------------------------------------------------------------
    # Gestion des acteurs
    # ------------------------------------------------------------

    def add_actor(self, role, user, access_level='limited'):
        """Donne à `user` le rôle `role` sur **ce** dossier.

        Idempotent par relèvement : rappeler la méthode sur un acteur existant
        met à jour son niveau plutôt que de créer un doublon — la contrainte
        d'unicité l'interdirait de toute façon, et échouer sur une
        ré-attribution serait une mauvaise surprise au milieu d'un processus.
        """
        self.ensure_one()
        Actor = self.env['opex.workflow.instance.actor'].sudo()
        existing = Actor.search([
            ('instance_id', '=', self.id),
            ('role_id', '=', role.id),
            ('user_id', '=', user.id),
        ], limit=1)
        if existing:
            existing.access_level = access_level
            return existing
        return Actor.create({
            'instance_id': self.id,
            'role_id': role.id,
            'user_id': user.id,
            'access_level': access_level,
        })

    def _grant_initiator_role(self):
        """Donne à l'initiateur le rôle déclaré par la définition.

        Appelée par `_start_for()`, donc sur **tout** démarrage d'instance, y
        compris un sous-workflow. Sans effet si la définition ne déclare aucun
        rôle d'initiateur — c'est le cas des processus dont le titulaire n'est
        pas celui qui ouvre le dossier.

        Silencieuse sur l'utilisateur public : un enregistrement créé par un
        visiteur non connecté n'a pas d'acteur à désigner, et lui en donner un
        ouvrirait le dossier à tous les visiteurs, qui partagent ce compte.
        """
        self.ensure_one()
        role = self.definition_id.sudo().initiator_role_id
        user = self.initiator_id
        if not role or not user or user.sudo()._is_public():
            return False
        # `full` : l'initiateur est le titulaire du dossier qu'il vient
        # d'ouvrir. Un accès `limited` l'empêcherait de relire ce qu'il a
        # déposé dès que les `ir.rule` du moteur s'appliquent.
        return self.add_actor(role, user, 'full')

    @api.model
    def _backfill_missing_initiator_actors(self, definition_codes=None):
        """Pose l'acteur initiateur sur les instances nées sans lui.

        Un correctif qui ne vaudrait que pour l'avenir laisserait derrière lui
        les dossiers déjà ouverts : leur déposant resterait incapable de
        franchir la moindre transition, sans que rien ne le signale. Appelée
        depuis les fichiers de données du module métier, hors bloc `noupdate`.

        Ne touche qu'aux instances **en cours** : rejouer l'histoire d'un
        dossier clos rouvrirait un accès que sa clôture avait fermé. Idempotent
        — `add_actor()` l'est déjà, et une instance qui a son acteur n'est même
        pas relue.
        """
        domain = [
            ('state', '=', 'running'),
            ('definition_id.initiator_role_id', '!=', False),
        ]
        if definition_codes:
            domain.append(('definition_id.code', 'in', definition_codes))

        repaired = 0
        for instance in self.sudo().search(domain):
            role = instance.definition_id.initiator_role_id
            if instance.actor_ids.filtered(lambda a: a.role_id == role):
                continue
            # Instance orpheline — son enregistrement métier a été supprimé
            # sans elle. Lui poser un acteur ne rendrait service à personne et
            # laisserait des lignes d'accès pointant vers un dossier disparu.
            if not instance._get_record():
                continue
            if instance._grant_initiator_role():
                repaired += 1
        if repaired:
            _logger.info(
                "opex_workflow: acteur initiateur posé sur %s instance(s) "
                "qui en étaient dépourvues.", repaired)
        return repaired

    def remove_actor(self, role, user, keep_trace=True):
        """Retire l'accès de `user` au titre de `role`.

        `keep_trace=True` par défaut : la ligne passe à « Aucun » au lieu d'être
        supprimée. L'accès est bien coupé — les `ir.rule` traversent
        `active_actor_ids`, qui exclut ce niveau — mais on garde la trace qu'il
        a existé, avec qui l'avait ouvert et quand. Un accès qui disparaît sans
        laisser d'empreinte n'est pas auditable.
        """
        self.ensure_one()
        actors = self.sudo().actor_ids.filtered(
            lambda a: a.role_id == role and a.user_id == user)
        if not actors:
            return False
        if keep_trace:
            actors.access_level = 'none'
        else:
            actors.unlink()
        return True

    def _is_workflow_manager(self, user):
        """Un gestionnaire peut forcer une transition ; c'est tracé comme tel."""
        return user.sudo()._has_group('opex_workflow.group_workflow_manager')

    def _check_transition_allowed(self, transition, user=None, raise_exception=False):
        """**LA** fonction de contrôle d'accès aux transitions.

        Il n'en existe aucune autre, nulle part. Le back-office, le wizard, le
        portail et les tests passent tous par ici. Une vérification dupliquée
        finit par en oublier une occurrence — et c'est celle-là qui reçoit la
        requête forgée.

        Elle ne juge **que** le droit : appartenance de la transition au
        workflow, cohérence de l'étape de départ, état de l'instance, rôles.
        Les conditions métier sont évaluées séparément, parce qu'elles ne sont
        pas un refus d'accès : une transition bloquée par une condition reste
        visible et redeviendra possible quand le dossier avancera.
        """
        self.ensure_one()
        user = user or self.env.user
        error = None

        if self.state != 'running':
            error = _(
                "Ce dossier n'est plus en cours (%s) : aucune transition n'est "
                "possible."
            ) % dict(self._fields['state'].selection)[self.state]
        elif transition.definition_id != self.definition_id:
            error = _(
                "La transition « %s » appartient à un autre workflow."
            ) % transition.name
        elif transition.source_stage_id != self.current_stage_id:
            error = _(
                "La transition « %(transition)s » part de l'étape "
                "« %(source)s », or ce dossier est à l'étape « %(current)s »."
            ) % {
                'transition': transition.name,
                'source': transition.source_stage_id.name,
                'current': self.current_stage_id.name or _("aucune"),
            }
        elif transition.allowed_role_ids:
            if not (transition.allowed_role_ids & self._user_roles(user)) \
                    and not self._is_workflow_manager(user):
                error = _(
                    "L'action « %(transition)s » est réservée au(x) rôle(s) : "
                    "%(roles)s."
                ) % {
                    'transition': transition.name,
                    'roles': ", ".join(transition.allowed_role_ids.mapped('name')),
                }

        if error and raise_exception:
            raise UserError(error)
        return not error

    # ------------------------------------------------------------
    # Ce que l'utilisateur peut faire
    # ------------------------------------------------------------

    def available_transitions(self, user=None):
        """Transitions partant de l'étape courante que les rôles autorisent.

        **Elle ne filtre pas sur les conditions.** Une transition dont une
        condition échoue reste dans la liste : elle sera présentée désactivée,
        accompagnée du message de la règle qui bloque. Une transition qui
        disparaît sans explication laisse l'utilisateur bloqué sans savoir
        pourquoi — et sans savoir ce qu'il doit faire pour la débloquer.
        """
        self.ensure_one()
        # Résolu ici plutôt que laissé à None : voir la note de
        # `next_action_label()` sur la détection de langue par `_()`. Toute
        # méthode portant un local nommé `user` doit lui donner une vraie
        # valeur avant d'appeler quoi que ce soit de traduit.
        user = user or self.env.user
        if self.state != 'running' or not self.current_stage_id:
            return self.env['opex.workflow.transition'].browse()
        # `sudo()` sur la **configuration** : étapes, transitions et règles sont
        # du paramétrage moteur, pas des données de l'utilisateur. Un porteur
        # portail n'a aucun droit de lecture dessus, et n'en a pas besoin — ce
        # qui le concerne, c'est le résultat. Les droits sur le *dossier*, eux,
        # restent tranchés par `_check_transition_allowed()`.
        candidates = self.definition_id.sudo().transition_ids.filtered(
            lambda t: t.source_stage_id == self.current_stage_id and t.active)
        return candidates.filtered(
            lambda t: self._check_transition_allowed(t, user=user))

    def transition_options(self, user=None):
        """`available_transitions()` enrichie de l'état de chaque transition.

        Forme consommée par l'interface (Extension 3) : chaque entrée porte la
        transition, sa disponibilité réelle et, si elle est bloquée, la raison
        rédigée. Séparée d'`available_transitions()` pour que cette dernière
        garde le type qu'annonce son nom — un recordset de transitions.
        """
        self.ensure_one()
        user = user or self.env.user
        options = []
        for transition in self.available_transitions(user=user):
            ok, blocking, _notes = self._evaluate_conditions(transition)
            options.append({
                'transition': transition,
                'available': ok,
                'blocking_messages': blocking,
                'reason': " ".join(blocking) if blocking else False,
            })
        return options

    # ------------------------------------------------------------
    # L'exécution
    # ------------------------------------------------------------

    def do_transition(self, transition, comment=False):
        """Fait avancer le dossier d'une étape.

        Ordre imposé : contrôle d'accès → évaluation des conditions → écriture
        de l'étape → écriture de l'historique → clôture si l'étape cible est
        finale. (L'exécution des actions s'insère entre l'historique et la
        clôture — Extension 4.)

        Les écritures passent en `sudo()` : l'autorisation a déjà été tranchée
        par `_check_transition_allowed()`, et c'est le seul juge. Faire aussi
        dépendre le passage des droits CRUD sur `opex.workflow.instance`
        créerait un second contrôle d'accès, à un autre endroit, disant autre
        chose — exactement ce que la règle d'unicité du contrôle interdit.
        """
        self.ensure_one()
        if isinstance(transition, int):
            transition = self.env['opex.workflow.transition'].browse(transition)
        transition.ensure_one()

        self._check_transition_allowed(transition, raise_exception=True)

        comment = (comment or '').strip()
        if transition.requires_comment and not comment:
            raise UserError(_(
                "L'action « %s » exige un motif écrit. Il sera transmis à "
                "l'intéressé et conservé dans l'historique du dossier."
            ) % transition.name)

        ok, blocking, notes = self._evaluate_conditions(transition)
        if not ok:
            raise UserError(_(
                "L'action « %(transition)s » n'est pas possible pour le "
                "moment :\n\n%(raisons)s"
            ) % {
                'transition': transition.name,
                'raisons': "\n".join("• %s" % message for message in blocking),
            })

        from_stage = self.current_stage_id
        target = transition.target_stage_id
        forced = bool(
            transition.allowed_role_ids
            and not (transition.allowed_role_ids & self._user_roles(self.env.user))
        )

        # `date_stage_start` repart à chaque étape : le SLA se compte depuis
        # l'entrée dans l'étape courante, pas depuis l'ouverture du dossier.
        # `sla_notified_stage_id` est effacé pour que la nouvelle étape puisse
        # alerter à son tour.
        self.sudo().write({
            'current_stage_id': target.id,
            'date_stage_start': fields.Datetime.now(),
            'is_late': False,
            'sla_notified_stage_id': False,
        })

        self.env['opex.workflow.history'].sudo().create({
            'instance_id': self.id,
            'from_stage_id': from_stage.id or False,
            'to_stage_id': target.id,
            'transition_id': transition.id,
            'user_id': self.env.user.id,
            'comment': comment or False,
            'conditions_note': notes or False,
            'forced': forced,
        })

        self._execute_actions(transition)

        if target.is_end:
            self.sudo().write({
                'state': 'done',
                'date_end': fields.Datetime.now(),
            })
        return True

    def _execute_actions(self, transition):
        """Exécute les actions d'une transition, chacune isolée des autres.

        **Une action qui échoue ne rollback pas la transition.** Un serveur
        mail en panne ne doit pas bloquer un processus métier : le dossier a
        avancé, c'est un fait métier acquis, et l'échec de la notification est
        un incident technique séparé.

        Techniquement, c'est ce que fait le savepoint : sans lui, une exception
        remonterait jusqu'au rollback de toute la transaction — donc du
        changement d'étape et de la ligne d'historique. Chaque action a le sien,
        pour qu'un échec n'emporte pas non plus les actions déjà exécutées.

        `invalidate_all()` après un échec : le rollback au savepoint défait les
        écritures en base mais pas le cache de l'ORM, qui contiendrait alors des
        valeurs jamais écrites.

        Les échecs sont journalisés dans une **ligne d'historique
        supplémentaire** plutôt qu'ajoutés à celle de la transition : cette
        dernière est déjà écrite et l'historique est immuable. C'est aussi plus
        juste — l'échec d'une action est un événement distinct, avec son propre
        horodatage.
        """
        self.ensure_one()
        notes = []
        failures = 0

        for action in transition.sudo().action_ids.filtered('active').sorted('sequence'):
            try:
                with self.env.cr.savepoint():
                    detail = action.execute(self, transition)
                notes.append("%s%s" % (
                    action.name, " — %s" % detail if detail else ''))
            except Exception as error:  # noqa: BLE001 — isolation volontaire
                failures += 1
                self.env.invalidate_all()
                _logger.exception(
                    "opex_workflow: l'action « %s » (%s) a échoué sur "
                    "l'instance %s ; la transition est conservée.",
                    action.name, action.code, self.id,
                )
                notes.append("%s — %s" % (action.name, error))

        if failures:
            # `sudo()` sur la **lecture** aussi, pas seulement sur l'écriture.
            #
            # Un utilisateur peut légitimement franchir une transition sans
            # avoir le droit de *lire* l'instance : il tient son rôle d'un
            # groupe, alors que les `ir.rule` accordent la lecture par ligne
            # d'acteur. Lire `current_stage_id` sous son identité pour
            # journaliser un échec d'action lève alors une AccessError — et
            # fait échouer une transition qui, elle, avait parfaitement abouti.
            instance = self.sudo()
            self.env['opex.workflow.history'].sudo().create({
                'instance_id': instance.id,
                'from_stage_id': instance.current_stage_id.id or False,
                'to_stage_id': instance.current_stage_id.id or False,
                'transition_id': transition.id,
                'user_id': self.env.user.id,
                'comment': _(
                    "%(failed)s action(s) sur %(total)s ont échoué. La "
                    "transition a bien eu lieu."
                ) % {'failed': failures, 'total': len(notes)},
                'conditions_note': "\n".join(notes),
            })
        return failures, "\n".join(notes)

    # ------------------------------------------------------------
    # Sous-workflows
    # ------------------------------------------------------------

    def start_subworkflow(self, definition_code):
        """Démarre un second processus sur le **même** enregistrement métier.

        C'est ce qui rend un sous-processus réutilisable : l'accompagnement se
        décrit une fois et se déclenche depuis n'importe quel workflow, sans
        être recopié dans chacun.

        Le sous-workflow est une instance à part entière — son propre
        historique, ses propres acteurs, sa propre étape courante. Il ne touche
        pas à l'instance parente : celle-ci n'avance que par ses propres
        transitions, et attend le cas échéant via `subworkflow_done()`.
        """
        self.ensure_one()
        record = self._get_record()
        if not record:
            raise UserError(_(
                "L'enregistrement piloté n'existe plus : impossible d'y "
                "démarrer un sous-workflow."))

        existing = self.sudo().search([
            ('res_model', '=', self.res_model),
            ('res_id', '=', self.res_id),
            ('definition_id.code', '=', definition_code),
            ('state', '=', 'running'),
        ], limit=1)
        if existing:
            raise UserError(_(
                "Un sous-workflow « %s » est déjà en cours sur ce dossier."
            ) % definition_code)

        child = self._start_for(record, definition_code)
        child.sudo().parent_instance_id = self.id
        return child

    # ------------------------------------------------------------
    # SLA et relances
    # ------------------------------------------------------------

    def _partners_for_roles(self, roles):
        """Destinataires portant l'un de ces rôles sur ce dossier.

        Un seul endroit pour cette résolution : les actions de notification et
        les relances de SLA s'en servent toutes les deux, et deux versions
        divergeraient au premier ajustement.
        """
        self.ensure_one()
        if not roles:
            return self.env['res.partner'].browse()
        partners = self.sudo().actor_ids.filtered(
            lambda a: a.role_id in roles and a.access_level != 'none'
        ).user_id.partner_id
        groups = roles.sudo().group_id
        if groups:
            partners |= groups.sudo().all_user_ids.partner_id
        return partners

    def _notify_sla_breach(self):
        """Prévient le rôle attendu qu'un dossier traîne sur son étape.

        `mail.mt_note` : c'est une relance interne, destinée à celui qui doit
        agir. Le porteur n'a pas à recevoir un email parce que le secrétariat
        est en retard.
        """
        self.ensure_one()
        record = self._get_record()
        if not record or not hasattr(record, 'message_post'):
            return False
        partners = self._partners_for_roles(self.current_stage_id.actor_role_ids)
        record.sudo().message_post(
            body=_(
                "Ce dossier est à l'étape « %(stage)s » depuis plus de "
                "%(days)s jour(s) et dépasse le délai attendu."
            ) % {
                'stage': self.current_stage_id.name,
                'days': self.current_stage_id.sla_days,
            },
            partner_ids=partners.ids,
            subtype_xmlid='mail.mt_note',
        )
        return True

    @api.model
    def _cron_check_sla(self):
        """Marque les dossiers en retard et relance le rôle attendu.

        Deux écritures distinctes, et c'est délibéré : `is_late` marque **tous**
        les dossiers dépassés à chaque passage, alors que la notification ne
        part qu'une fois par étape. Un compteur « 3 accompagnements en retard »
        doit rester exact en permanence ; une alerte répétée toutes les heures,
        elle, cesse d'être lue.
        """
        now = fields.Datetime.now()
        late = self.sudo().search([
            ('state', '=', 'running'),
            ('sla_deadline', '!=', False),
            ('sla_deadline', '<', now),
        ])
        on_time = self.sudo().search([
            ('state', '=', 'running'),
            ('is_late', '=', True),
            '|', ('sla_deadline', '=', False), ('sla_deadline', '>=', now),
        ])

        on_time.write({'is_late': False})
        if late:
            late.write({'is_late': True})

        notified = 0
        for instance in late:
            if instance.sla_notified_stage_id == instance.current_stage_id:
                continue
            try:
                with self.env.cr.savepoint():
                    instance._notify_sla_breach()
                instance.sla_notified_stage_id = instance.current_stage_id.id
                notified += 1
            except Exception:  # noqa: BLE001 — une relance ratée n'arrête pas le cron
                self.env.invalidate_all()
                _logger.exception(
                    "opex_workflow: relance SLA impossible sur l'instance %s",
                    instance.id)

        _logger.info(
            "opex_workflow: SLA — %s dossier(s) en retard, %s relance(s) envoyée(s)",
            len(late), notified)
        return True

    # ------------------------------------------------------------
    # Progression, pour le portail générique
    # ------------------------------------------------------------

    def progress_steps(self):
        """La progression telle que l'utilisateur final doit la lire.

        Renvoie une entrée par étape, avec son **libellé utilisateur** et son
        état : franchie, en cours, à venir. Jamais de code technique — le
        workflow système peut être complexe, ce que l'utilisateur lit ne doit
        pas l'être.

        « Franchie » se lit dans l'historique et non dans la séquence : le
        processus est un graphe, pas une file. Un dossier passé par la boucle
        de remédiation a franchi des étapes qu'un autre n'aura jamais vues, et
        déduire l'avancement d'un numéro d'ordre mentirait sur les deux.
        """
        self.ensure_one()
        visited = set(self.sudo().history_ids.mapped('to_stage_id').ids)
        steps = []
        for stage in self.definition_id.sudo().stage_ids.sorted('sequence'):
            if stage == self.current_stage_id:
                state = 'current'
            elif stage.id in visited:
                state = 'done'
            else:
                state = 'upcoming'
            steps.append({
                'stage': stage,
                'label': stage.user_label or stage.name,
                'state': state,
            })
        return steps

    def next_action_label(self, user=None):
        """Ce que l'utilisateur doit faire ensuite, en une phrase.

        Le principe des documents sources : « ne pas demander à l'utilisateur
        de piloter le workflow, le workflow doit guider l'utilisateur ». On lui
        dit donc ce qu'on attend de lui, pas dans quel état est la machine.
        """
        self.ensure_one()
        # Résolu immédiatement, et ce n'est pas de la coquetterie.
        #
        # `_()` devine la langue en inspectant les **variables locales de
        # l'appelant** : `odoo/tools/translate.py` y cherche un nom `user` et
        # fait `int()` dessus. Un paramètre `user=None` laissé tel quel fait
        # donc planter la traduction — `TypeError: int() argument must be ...
        # not 'NoneType'` — dans une méthode qui n'a rien à voir avec les
        # langues. Le piège vaut pour toute méthode ayant un local `user` et
        # appelant `_()`.
        user = user or self.env.user

        if self.state == 'done':
            return _("Ce dossier est clôturé.")
        if self.state == 'cancelled':
            return _("Ce dossier a été annulé.")

        options = self.transition_options(user=user)
        available = [option for option in options if option['available']]
        if available:
            return _("Votre prochaine action : %s") % ", ".join(
                option['transition'].name for option in available)
        if options:
            return _("En attente : %s") % options[0]['reason']
        return _(
            "Votre dossier est en cours de traitement. Aucune action ne vous "
            "est demandée pour le moment.")

    # ------------------------------------------------------------
    # Smart Matching — scoring pondéré explicable
    # ------------------------------------------------------------

    def _score_candidate(self, partner, criteria):
        """Score d'un candidat sur ce dossier. Renvoie (score, explication).

        Somme des poids satisfaits rapportée à la somme des poids
        **applicables**, en pourcentage. Un critère qu'on n'a pas pu évaluer —
        expression fautive, champ absent — est retiré des deux sommes plutôt
        que compté comme un échec : le pénaliser ferait chuter tous les
        candidats de la même façon et rendrait le classement dépendant d'une
        faute de configuration.

        L'explication est construite ligne à ligne en même temps que le calcul.
        Elle n'est pas un commentaire ajouté après coup : c'est la trace de ce
        qui a effectivement été comparé.
        """
        self.ensure_one()
        lines = []
        earned = 0.0
        applicable = 0.0

        for criterion in criteria:
            try:
                source_value = self._evaluate_expression(criterion.source_expression)
            except Exception as error:  # noqa: BLE001 — critère neutralisé
                _logger.warning(
                    "opex_workflow: critère « %s » illisible sur l'instance %s : %s",
                    criterion.name, self.id, error)
                lines.append("· %s — non évalué (%s)" % (criterion.name, error))
                continue

            target_value = False
            if criterion.target_field in partner._fields:
                target_value = partner.sudo()[criterion.target_field]
            elif criterion.target_field:
                lines.append("· %s — le champ « %s » n'existe pas sur le candidat"
                             % (criterion.name, criterion.target_field))
                continue

            ok, detail = criterion._compare(source_value, target_value)
            applicable += criterion.weight
            if ok:
                earned += criterion.weight
                lines.append("%s (poids %g) — %s" % (
                    criterion.name, criterion.weight, detail))
            else:
                lines.append("%s (poids %g) — %s" % (
                    criterion.name, criterion.weight, detail))

        score = (earned / applicable * 100.0) if applicable else 0.0
        header = _("Score %(score).0f %% — %(earned)g point(s) sur %(total)g") % {
            'score': score, 'earned': earned, 'total': applicable,
        }
        return score, "\n".join([header, ""] + lines)

    def run_matching(self, candidate_type='expert', partners=None, limit=10,
                     min_score=0.0):
        """Propose des candidats scorés sur ce dossier.

        **Ne déclenche aucune transition et n'écrit rien sur l'objet
        métier.** Elle produit une liste de propositions, rien de plus. C'est
        écrit dans les deux documents sources : l'IA recommande, elle ne décide
        pas. Le responsable Valide / Modifie / Exclut / Ajoute ensuite, et
        déclenche lui-même la suite du processus s'il y a lieu.

        Les candidats déjà décidés (retenus, écartés, exclus) ne sont pas
        recalculés : relancer le matching ne doit pas effacer un arbitrage
        humain.
        """
        self.ensure_one()
        Candidate = self.env['opex.matching.candidate'].sudo()
        criteria = self.env['opex.matching.criteria'].sudo().search([
            ('definition_id', '=', self.definition_id.id),
            ('active', '=', True),
        ])
        if not criteria:
            raise UserError(_(
                "Aucun critère de matching n'est configuré sur le workflow "
                "« %s »."
            ) % self.definition_id.name)

        if partners is None:
            partners = self.env['res.partner'].sudo().search(
                [('is_company', '=', False)])

        decided = Candidate.search([
            ('instance_id', '=', self.id),
            ('candidate_type', '=', candidate_type),
            ('state', '!=', 'proposed'),
        ])
        untouchable = set(decided.mapped('partner_id').ids)

        # Les propositions non arbitrées sont remplacées : le dossier a pu
        # évoluer depuis, et laisser d'anciens scores à côté des nouveaux
        # rendrait la liste illisible.
        Candidate.search([
            ('instance_id', '=', self.id),
            ('candidate_type', '=', candidate_type),
            ('state', '=', 'proposed'),
        ]).unlink()

        scored = []
        for partner in partners:
            if partner.id in untouchable:
                continue
            score, detail = self._score_candidate(partner, criteria)
            if score >= min_score:
                scored.append((score, detail, partner))

        scored.sort(key=lambda item: item[0], reverse=True)
        created = Candidate.browse()
        for score, detail, partner in scored[:limit]:
            created |= Candidate.create({
                'instance_id': self.id,
                'partner_id': partner.id,
                'candidate_type': candidate_type,
                'score': score,
                'detail': detail,
            })
        return created

    def action_view_candidates(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Candidats proposés"),
            'res_model': 'opex.matching.candidate',
            'view_mode': 'list,form',
            'domain': [('instance_id', '=', self.id)],
            'context': {'default_instance_id': self.id},
        }

    def action_open_transition_wizard(self):
        """Ouvre le wizard des transitions possibles sur ce dossier.

        Vit ici plutôt que sur le mixin pour la même raison que le reste du
        moteur : une instance existe sans que son modèle hôte hérite du mixin.
        Le back-office des instances peut donc ouvrir le wizard sur n'importe
        quel dossier, y compris ceux portés par un modèle natif.
        """
        self.ensure_one()
        if self.state != 'running':
            raise UserError(_(
                "Ce dossier n'est plus en cours : aucune action n'est possible."))
        if not self.available_transitions():
            raise UserError(_(
                "Aucune action ne vous est ouverte depuis l'étape "
                "« %(stage)s ». Soit ce dossier attend l'intervention d'un "
                "autre acteur, soit cette étape n'a pas de suite configurée."
            ) % {'stage': self.current_stage_id.name or _("courante")})
        return {
            'type': 'ir.actions.act_window',
            'name': _("Faire avancer le dossier"),
            'res_model': 'opex.workflow.transition.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_instance_id': self.id},
        }

    def action_cancel(self):
        """Sort le dossier du processus sans lui faire atteindre une fin.

        L'annulation est tracée comme le reste : sans ligne d'historique, un
        dossier disparu du circuit serait indistinguable d'un dossier jamais
        démarré.
        """
        for instance in self:
            if instance.state != 'running':
                raise UserError(_(
                    "Seule une instance en cours peut être annulée."))
            instance.sudo().write({
                'state': 'cancelled',
                'date_end': fields.Datetime.now(),
            })
            self.env['opex.workflow.history'].sudo().create({
                'instance_id': instance.id,
                'from_stage_id': instance.current_stage_id.id or False,
                'to_stage_id': instance.current_stage_id.id or False,
                'user_id': self.env.user.id,
                'comment': _("Instance annulée."),
            })
        return True

    # ------------------------------------------------------------
    # Démarrage
    # ------------------------------------------------------------

    @api.model
    def _start_for(self, record, definition_code, actor_values=None):
        """Démarre une instance sur `record`, et renvoie l'instance.

        La logique vit ici plutôt que sur le mixin pour deux raisons : elle
        n'exige rien du modèle hôte (le moteur tourne sur `res_model`/`res_id`,
        pas sur un mixin), et elle reste donc testable sur un modèle natif —
        ce qui vaut démonstration de généricité autant que test.
        """
        record.ensure_one()
        definition = self.env['opex.workflow.definition']._get_for_code(definition_code)

        if definition.model_name != record._name:
            raise UserError(_(
                "Le workflow « %(workflow)s » pilote des enregistrements "
                "« %(attendu)s », pas « %(recu)s »."
            ) % {
                'workflow': definition.name,
                'attendu': definition.model_name,
                'recu': record._name,
            })

        start_stage = definition._start_stage()
        if not start_stage:
            raise UserError(_(
                "Le workflow « %s » n'a pas d'étape de départ. Validez son "
                "graphe avant de l'utiliser."
            ) % definition.name)

        instance = self.sudo().create({
            'definition_id': definition.id,
            'res_model': record._name,
            'res_id': record.id,
            'current_stage_id': start_stage.id,
            'initiator_id': self.env.user.id,
            'actor_ids': [
                fields.Command.create(values) for values in (actor_values or [])
            ],
        })

        # L'initiateur devient acteur de son dossier, si la définition le
        # demande. C'est ici, et nulle part ailleurs : `_start_for()` est le
        # seul chemin par lequel une instance naît — `start_workflow()` du
        # mixin et `start_subworkflow()` y passent tous les deux. Un module
        # métier n'a donc rien à écrire, et surtout rien à oublier.
        #
        # Le rôle est posé **avant** l'historique pour que le journal d'un
        # dossier soit déjà lisible par son porteur à la ligne 1 : les
        # `ir.rule` de l'historique traversent `active_actor_ids`.
        instance._grant_initiator_role()

        # Première ligne d'historique : sans elle, le journal d'un dossier
        # commence à sa deuxième étape et l'entrée dans le processus n'est
        # datée nulle part.
        self.env['opex.workflow.history'].sudo().create({
            'instance_id': instance.id,
            'from_stage_id': False,
            'to_stage_id': start_stage.id,
            'user_id': self.env.user.id,
            'comment': _("Workflow démarré."),
        })
        return instance
