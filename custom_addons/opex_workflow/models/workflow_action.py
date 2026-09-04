import logging
from datetime import timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class WorkflowAction(models.Model):
    """Ce qu'un workflow *fait* au passage d'une transition.

    Les paramètres sont portés par des champs distincts plutôt que par un blob
    JSON : un champ typé se remplit dans un formulaire, un JSON se remplit dans
    un éditeur de texte. Le configurateur doit rester utilisable par quelqu'un
    qui ne lit pas de Python.

    **Le dispatch se fait par `getattr`, jamais par une chaîne de if/elif.**
    Ajouter un type d'action doit être l'ajout d'une méthode `_execute_<type>`
    et d'une valeur dans la `Selection` — rien d'autre. Une chaîne de
    conditions ferait de chaque nouveau type une modification du cœur du
    moteur, et c'est précisément ce que le moteur existe pour éviter.
    """

    _name = 'opex.workflow.action'
    _description = "Action de workflow"
    _order = 'sequence, id'

    name = fields.Char(string="Nom", required=True, translate=True)
    code = fields.Char(string="Code", required=True, index=True)
    sequence = fields.Integer(
        string="Séquence",
        default=10,
        help="Ordre d'exécution lorsqu'une transition porte plusieurs actions.",
    )
    action_type = fields.Selection(
        [
            ('notify', "Notifier des acteurs"),
            ('set_field', "Écrire une valeur sur l'enregistrement"),
            ('create_task', "Créer une tâche"),
            ('send_email', "Envoyer un email"),
            ('launch_subworkflow', "Démarrer un sous-workflow"),
            ('run_matching', "Lancer le Smart Matching"),
        ],
        string="Type d'action",
        required=True,
        default='notify',
    )
    description = fields.Text(string="Description")
    active = fields.Boolean(string="Actif", default=True)

    # --- Paramètres, selon le type ------------------------------------------
    target_role_ids = fields.Many2many(
        'opex.workflow.role',
        'workflow_action_target_role_rel', 'action_id', 'role_id',
        string="Rôles destinataires",
        help="Utilisé par « Notifier » et « Créer une tâche ».",
    )
    field_id = fields.Many2one(
        'ir.model.fields',
        string="Champ à écrire",
        ondelete='cascade',
        help="Utilisé par « Écrire une valeur ».",
    )
    value_expression = fields.Text(
        string="Valeur (expression)",
        help="Évaluée comme une condition, avec le même contexte "
             "(record, instance, user, stage, field, has_document).",
    )
    body = fields.Html(
        string="Message",
        translate=True,
        help="Corps du message posté par « Notifier ».",
    )
    # Le moteur ne sait pas qui est « interne » et qui est « le porteur » : il
    # ne connaît pas le métier. Le choix est donc explicite, et son défaut est
    # le côté sûr. Bug déjà payé sur le module précédent : des messages de
    # coordination interne partaient par email chez le candidat.
    notify_subtype = fields.Selection(
        [
            ('note', "Note interne — pas d'email au porteur"),
            ('comment', "Message au porteur — envoyé par email"),
        ],
        string="Nature du message",
        default='note',
        required=True,
        help="« Note interne » pour toute coordination entre membres du "
             "personnel. « Message au porteur » uniquement pour ce que "
             "l'intéressé doit réellement recevoir dans sa boîte.",
    )
    template_id = fields.Many2one(
        'mail.template',
        string="Modèle d'email",
        ondelete='set null',
        help="Utilisé par « Envoyer un email ».",
    )
    sub_definition_id = fields.Many2one(
        'opex.workflow.definition',
        string="Workflow à démarrer",
        ondelete='set null',
        help="Utilisé par « Démarrer un sous-workflow ».",
    )
    matching_candidate_type = fields.Selection(
        [
            ('expert', "Expert"),
            ('mentor', "Mentor"),
            ('investisseur', "Investisseur"),
            ('sponsor', "Sponsor"),
        ],
        string="Type de candidat recherché",
        default='expert',
        required=True,
        help="Utilisé par « Lancer le Smart Matching ».",
    )
    matching_limit = fields.Integer(
        string="Nombre de propositions",
        default=10,
        help="Combien de candidats proposer, les mieux classés d'abord.",
    )
    matching_min_score = fields.Float(
        string="Score minimum",
        digits=(5, 2),
        help="En deçà, le candidat n'est pas proposé. Zéro propose tout le "
             "monde, classé par score.",
    )
    matching_domain = fields.Char(
        string="Vivier de candidats",
        help="Domaine Odoo restreignant les contacts examinés. Vide, le "
             "matching parcourt toutes les personnes physiques.\n\n"
             "Exemple : [('is_expert', '=', True)]\n\n"
             "Sans ce champ, chercher un expert et chercher un investisseur "
             "reviendraient à parcourir le même vivier — et à proposer les "
             "mêmes contacts dans les deux catégories.",
    )
    deadline_days = fields.Integer(
        string="Échéance (jours)",
        help="Utilisé par « Créer une tâche » : délai accordé à partir du "
             "passage de la transition.",
    )

    _code_uniq = models.Constraint(
        'unique(code)',
        "Le code d'une action doit être unique.",
    )

    # ------------------------------------------------------------
    # Exécution — dispatch par getattr
    # ------------------------------------------------------------

    def execute(self, instance, transition=None):
        """Exécute cette action sur cette instance.

        Ne capture rien : les erreurs remontent à l'appelant, qui les isole
        dans un savepoint et les journalise. Une action ne décide pas seule de
        ce qu'il advient de son échec.
        """
        self.ensure_one()
        method = getattr(self, '_execute_%s' % self.action_type, None)
        if method is None:
            raise UserError(_(
                "Le type d'action « %(type)s » n'a pas d'implémentation. "
                "Ajoutez une méthode _execute_%(type)s sur "
                "opex.workflow.action."
            ) % {'type': self.action_type})
        return method(instance, transition)

    def _target_partners(self, instance):
        """Destinataires d'une notification : les porteurs des rôles visés.

        Deux sources, comme pour les droits de transition :

        - les **acteurs** de ce dossier portant l'un des rôles visés — c'est le
          cas normal, et le seul qui respecte le principe « l'expert de ce
          dossier-là » ;
        - les membres du **groupe Odoo** adossé au rôle, quand il y en a un —
          sans quoi une notification au Secrétariat n'atteindrait personne tant
          qu'aucune ligne d'acteur n'a été créée.

        `all_user_ids` et non `user_ids` : ceux qui détiennent le groupe par
        implication comptent aussi.
        """
        self.ensure_one()
        roles = self.target_role_ids
        if not roles:
            return self.env['res.partner'].browse()

        # Délègue à l'instance : les relances de SLA (Extension 8) résolvent
        # les mêmes destinataires, et deux versions de cette règle
        # divergeraient au premier ajustement.
        return instance._partners_for_roles(roles)

    # ------------------------------------------------------------
    # Les types
    # ------------------------------------------------------------

    def _execute_notify(self, instance, transition=None):
        """Poste un message sur l'objet métier.

        Le sous-type est **`mail.mt_note` par défaut**. Un message interne
        posté en `mt_comment` sur un enregistrement que le porteur suit lui
        part par email — bug déjà rencontré et corrigé sur le module précédent.
        """
        self.ensure_one()
        record = instance._get_record()
        if not record:
            raise UserError(_(
                "L'enregistrement piloté n'existe plus : impossible d'y poster "
                "un message."))
        if not hasattr(record, 'message_post'):
            raise UserError(_(
                "Le modèle « %s » n'hérite pas de mail.thread : il ne peut pas "
                "recevoir de message. Retirez cette action ou faites hériter le "
                "modèle."
            ) % record._name)

        partners = self._target_partners(instance)
        subtype = 'mail.mt_note' if self.notify_subtype == 'note' else 'mail.mt_comment'
        record.sudo().message_post(
            body=self.body or self.name,
            partner_ids=partners.ids,
            subtype_xmlid=subtype,
        )
        return _("%(count)s destinataire(s), %(kind)s") % {
            'count': len(partners),
            'kind': dict(self._fields['notify_subtype'].selection)[self.notify_subtype],
        }

    def _execute_set_field(self, instance, transition=None):
        """Écrit une valeur calculée sur l'objet métier."""
        self.ensure_one()
        if not self.field_id:
            raise UserError(_(
                "L'action « %s » doit désigner le champ à écrire.") % self.name)
        if not self.value_expression:
            raise UserError(_(
                "L'action « %s » doit porter une expression de valeur.") % self.name)

        record = instance._get_record()
        if not record:
            raise UserError(_("L'enregistrement piloté n'existe plus."))
        # Le champ doit appartenir au modèle piloté : sans ce contrôle, une
        # configuration erronée écrirait sur un modèle sans rapport.
        if self.field_id.model != record._name:
            raise UserError(_(
                "Le champ « %(field)s » appartient au modèle « %(owner)s », "
                "pas à « %(piloted)s »."
            ) % {
                'field': self.field_id.name,
                'owner': self.field_id.model,
                'piloted': record._name,
            })

        value = instance._evaluate_expression(self.value_expression)
        record.sudo().write({self.field_id.name: value})
        return _("%(field)s = %(value)s") % {
            'field': self.field_id.name, 'value': value}

    def _execute_create_task(self, instance, transition=None):
        """Crée une tâche dans la work queue du rôle visé."""
        self.ensure_one()
        role = self.target_role_ids[:1]
        deadline = False
        if self.deadline_days:
            # `timedelta` plutôt qu'un helper Odoo : `fields.Date.add` n'existe
            # plus en 19, et la bibliothèque standard ne bougera pas.
            deadline = fields.Date.context_today(self) + timedelta(
                days=self.deadline_days)

        # Assignation nominative seulement si le rôle n'est porté que par une
        # personne sur ce dossier. À plusieurs, la tâche reste ouverte au
        # premier qui s'en saisit plutôt que d'être attribuée arbitrairement.
        candidates = instance.sudo().actor_ids.filtered(
            lambda a: a.role_id in self.target_role_ids and a.access_level != 'none'
        ).user_id
        task = self.env['opex.workflow.task'].sudo().create({
            'instance_id': instance.id,
            'stage_id': instance.current_stage_id.id or False,
            'name': self.name,
            'role_id': role.id or False,
            'user_id': candidates.id if len(candidates) == 1 else False,
            'deadline': deadline,
        })
        return _("Tâche #%s créée") % task.id

    def _execute_send_email(self, instance, transition=None):
        """Envoie un email via un `mail.template`."""
        self.ensure_one()
        if not self.template_id:
            raise UserError(_(
                "L'action « %s » doit désigner un modèle d'email.") % self.name)
        record = instance._get_record()
        if not record:
            raise UserError(_("L'enregistrement piloté n'existe plus."))
        if self.template_id.model != record._name:
            raise UserError(_(
                "Le modèle d'email « %(template)s » s'applique à "
                "« %(owner)s », pas à « %(piloted)s »."
            ) % {
                'template': self.template_id.name,
                'owner': self.template_id.model,
                'piloted': record._name,
            })
        self.template_id.sudo().send_mail(record.id, force_send=False)
        return _("Email « %s » mis en file") % self.template_id.name

    # --- Types déclarés, implémentation à venir ------------------------------
    #
    # Ils lèvent plutôt que de ne rien faire : une action silencieusement
    # inopérante se découvre en démonstration, une action qui lève se découvre
    # au premier essai et laisse une trace dans l'historique.

    def _execute_launch_subworkflow(self, instance, transition=None):
        """Démarre un second processus sur le même enregistrement."""
        self.ensure_one()
        if not self.sub_definition_id:
            raise UserError(_(
                "L'action « %s » doit désigner le workflow à démarrer."
            ) % self.name)
        child = instance.start_subworkflow(self.sub_definition_id.code)
        return _("Sous-workflow « %(name)s » démarré (dossier #%(id)s)") % {
            'name': self.sub_definition_id.name, 'id': child.id}

    def _execute_run_matching(self, instance, transition=None):
        """Lance le Smart Matching et **s'arrête là**.

        L'action produit des propositions, jamais une décision. Elle n'écrit
        rien sur l'objet métier et ne déclenche aucune transition : c'est le
        responsable qui, ensuite, retient ou écarte, puis fait avancer le
        dossier s'il le juge bon. Une action qui enchaînerait automatiquement
        sur la base d'un score contredirait les deux documents sources.
        """
        self.ensure_one()
        partners = None
        if self.matching_domain:
            # Domaine évalué comme une règle : même `safe_eval`, même
            # tolérance. Un domaine fautif ne doit pas faire échouer une
            # transition — il vide le vivier, et l'échec est journalisé.
            domain = safe_eval(self.matching_domain, {})
            partners = self.env['res.partner'].sudo().search(domain)

        candidates = instance.run_matching(
            candidate_type=self.matching_candidate_type,
            partners=partners,
            limit=self.matching_limit or 10,
            min_score=self.matching_min_score,
        )
        return _("%(count)s candidat(s) proposé(s) (%(kind)s)") % {
            'count': len(candidates),
            'kind': dict(
                self._fields['matching_candidate_type'].selection
            )[self.matching_candidate_type],
        }
