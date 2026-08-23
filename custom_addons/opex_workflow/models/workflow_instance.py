import logging

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

    actor_ids = fields.One2many(
        'opex.workflow.instance.actor', 'instance_id', string="Acteurs")
    # ⚠ One2many **filtré**, et c'est indispensable, pas cosmétique.
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
        }

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
                notes.append("⚠ %s — erreur d'évaluation : %s" % (rule.name, error))
                blocking.append(rule.message)
            elif passed:
                notes.append("✓ %s" % rule.name)
            else:
                notes.append("✗ %s" % rule.name)
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

        ⚠ **Elle ne filtre pas sur les conditions.** Une transition dont une
        condition échoue reste dans la liste : elle sera présentée désactivée,
        accompagnée du message de la règle qui bloque. Une transition qui
        disparaît sans explication laisse l'utilisateur bloqué sans savoir
        pourquoi — et sans savoir ce qu'il doit faire pour la débloquer.
        """
        self.ensure_one()
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

        self.sudo().current_stage_id = target.id

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

        ⚠ **Une action qui échoue ne rollback pas la transition.** Un serveur
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
                notes.append("✓ %s%s" % (
                    action.name, " — %s" % detail if detail else ''))
            except Exception as error:  # noqa: BLE001 — isolation volontaire
                failures += 1
                self.env.invalidate_all()
                _logger.exception(
                    "opex_workflow: l'action « %s » (%s) a échoué sur "
                    "l'instance %s ; la transition est conservée.",
                    action.name, action.code, self.id,
                )
                notes.append("✗ %s — %s" % (action.name, error))

        if failures:
            self.env['opex.workflow.history'].sudo().create({
                'instance_id': self.id,
                'from_stage_id': self.current_stage_id.id or False,
                'to_stage_id': self.current_stage_id.id or False,
                'transition_id': transition.id,
                'user_id': self.env.user.id,
                'comment': _(
                    "%(failed)s action(s) sur %(total)s ont échoué. La "
                    "transition a bien eu lieu."
                ) % {'failed': failures, 'total': len(notes)},
                'conditions_note': "\n".join(notes),
            })
        return failures, "\n".join(notes)

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
