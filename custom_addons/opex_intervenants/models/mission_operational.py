"""Le déclenchement opérationnel du §13 — et la ligne qu'il ne franchit pas.

    « Le passage d'une candidature à SELECTED déclenche, **selon
      configuration** : notification, collecte de pièces, NDA, génération du
      contrat, ordre de mission, création du projet/tâches, calendrier et
      accès documentaire. » — §13 de Smart Missions

POURQUOI CE FICHIER N'EST PAS « DU PYTHON MÉTIER QUI PILOTE LE WORKFLOW »

Le moteur offre six types d'actions ; aucun ne crée un `project.project`.
Trois issues, une seule acceptable :

- **ajouter un type d'action au moteur** : il faudrait qu'il connaisse la
  notion de projet d'exécution, donc du métier. C'est ce que le moteur existe
  pour éviter, et le test d'acceptation d'`opex_workflow` exige zéro octet
  modifié ;
- **appeler ces effets depuis `do_transition()`** ou depuis un `write()`
  surchargé : la décision « quelle transition déclenche quoi » retournerait
  dans le code, et il faudrait la chercher à quinze endroits ;
- **passer par `set_field`**, le type d'action qui écrit une valeur évaluée
  sur l'enregistrement piloté. C'est celle-ci.

La configuration écrit `operational_trigger = 'selection'`, l'inverse du champ
dispatche par `getattr(self, '_trigger_%s' % code)` — le calque exact du
`_execute_<action_type>` du moteur (`workflow_action.py:159`). Ajouter un
effet, c'est ajouter une méthode et une valeur de `Selection`, comme là-bas.

La ligne de partage tient en une phrase : **la configuration décide quelle
transition déclenche quoi ; le Python n'implémente que l'effet.** Elle est
déjà celle du moteur — `_execute_notify` est du Python lui aussi. Ce qui
serait fautif, c'est qu'une *décision* de workflow vive dans une méthode ; il
n'y en a aucune ici. Aucun `_trigger_*` ne lit une étape, n'en écrit une, ni
n'appelle `do_transition()`.

Trois tests le gardent : les actions sont bien rattachées aux transitions, le
champ est bien un déclencheur sans mémoire, et aucun `_trigger_*` ne
déclenche de transition.
"""

import logging

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .optional_backends import PROJECT, PROJECT_TASK

_logger = logging.getLogger(__name__)

INTERVENANT_ROLE = 'opex_intervenants.role_intervenant'
CONTRACT_WORKFLOW_CODE = 'mission_contract'


class MissionApplicationOperational(models.Model):
    """Ce que la sélection d'une candidature met en route — §13, §17, §18."""

    _inherit = 'opex.mission.application'

    assignment_id = fields.Many2one(
        'opex.mission.assignment',
        string="Affectation",
        compute='_compute_assignment_id',
        help="Créée par le déclencheur de « Retenir cette candidature ».",
    )

    # Un déclencheur, pas un état. Non stocké, remis à faux par son propre
    # calcul : il ne garde aucune mémoire de ce qui a été déclenché. Le
    # `Selection` n'existe que pour rendre les valeurs légales lisibles dans le
    # configurateur — celui qui règle l'action choisit dans une liste.
    operational_trigger = fields.Selection(
        [('selection', "Sélection de l'intervenant")],
        string="Déclencheur opérationnel",
        compute='_compute_operational_trigger',
        inverse='_inverse_operational_trigger',
        readonly=False,
        store=False,
        help="Écrit par une action `set_field` configurée sur une transition. "
             "N'est jamais saisi à la main et ne conserve aucune valeur.",
    )

    @api.depends('mission_id')
    def _compute_assignment_id(self):
        Assignment = self.env['opex.mission.assignment'].sudo()
        for application in self:
            application.assignment_id = Assignment.search(
                [('application_id', '=', application.id)], limit=1)

    def _compute_operational_trigger(self):
        for application in self:
            application.operational_trigger = False

    def _inverse_operational_trigger(self):
        for application in self:
            code = application.operational_trigger
            if not code:
                continue
            getattr(application.sudo(), '_trigger_%s' % code)()

    # ------------------------------------------------------------
    # Les effets
    # ------------------------------------------------------------

    def _trigger_selection(self):
        """Tout ce que le §13 attache au passage à SELECTED.

        Idempotent de bout en bout : rejouer la transition — ce qui arrive
        quand une candidature revient en short-list puis est retenue de
        nouveau — ne produit ni seconde affectation ni contrat en double.
        """
        self.ensure_one()
        assignment = self._ensure_assignment()
        self._grant_intervenant_actor_on_mission()
        self._ensure_contract_documents(assignment)
        self._notify_candidates_still_open()
        return assignment

    def _ensure_assignment(self):
        """L'affectation de l'intervenant retenu — §15.

        Les conditions sont **recopiées** depuis la candidature : ce sont
        celles qui ont été acceptées. La candidature reste modifiable dans le
        back-office ; le contrat, lui, doit refléter ce qui a été convenu.
        """
        self.ensure_one()
        Assignment = self.env['opex.mission.assignment'].sudo()
        existing = Assignment.search(
            [('application_id', '=', self.id)], limit=1)
        if existing:
            return existing

        mission = self.mission_id.sudo()
        return Assignment.create({
            'mission_id': mission.id,
            'application_id': self.id,
            'partner_id': self.partner_id.id,
            'expert_profile_id': self.expert_profile_id.id or False,
            'date_debut': mission.date_debut_souhaitee or False,
            'date_fin': mission.date_fin_souhaitee or False,
            'duree_jours': mission.duree_estimee_jours or 0,
            'type_tarif': self.type_tarif or False,
            'tarif': self.tarif_propose or 0.0,
            'currency_id': mission.currency_id.id or False,
        })

    def _grant_intervenant_actor_on_mission(self):
        """Le manque déclaré à l'Extension 1, refermé ici.

        Les transitions « Démarrer la mission » et « Soumettre les livrables »
        sont ouvertes au rôle `intervenant` depuis l'Extension 1, mais
        personne ne portait ce rôle **sur l'instance de la mission** :
        l'intervenant était acteur de sa *candidature*, ce qui est une autre
        instance. Le responsable franchissait donc ces transitions à sa place.

        L'accès est `limited` et non `full` : le retenu doit voir le dossier
        de la mission et pouvoir la faire avancer, pas en disposer. `full`
        reste ce que la candidature lui donne — c'est la sienne.

        `test_the_retained_expert_is_not_yet_actor_of_the_mission` de
        l'Extension 1 rougit à cause de cette méthode. C'est exactement ce
        qu'on lui demandait : signaler que l'état du module a changé plutôt
        que laisser une affirmation périmée passer au vert.
        """
        self.ensure_one()
        role = self.env.ref(INTERVENANT_ROLE, raise_if_not_found=False)
        instance = self.mission_id.sudo().workflow_instance_id
        user = self.partner_id.sudo().user_ids[:1]
        if role and instance and user:
            instance.add_actor(role, user, 'limited')
        return True

    def _ensure_contract_documents(self, assignment):
        """§18 — le contrat et l'ordre de mission, générés depuis un modèle.

        Le NDA n'est produit que si l'appel l'exige (`nda_required`, posé à
        l'Extension 1) : une pièce vide que personne ne signera encombre le
        dossier et fait douter des autres.
        """
        self.ensure_one()
        Contract = self.env['opex.mission.contract'].sudo()
        mission = self.mission_id.sudo()

        wanted = ['contrat', 'ordre_mission']
        if mission.nda_required:
            wanted.append('nda')

        created = Contract.browse()
        for contract_type in wanted:
            if Contract.search_count([
                ('assignment_id', '=', assignment.id),
                ('contract_type', '=', contract_type),
            ]):
                continue
            created |= Contract.create(
                self._contract_values(assignment, contract_type))
        return created

    def _contract_values(self, assignment, contract_type):
        """Le contenu du §18 : client, intervenant, mission, dates, montant…"""
        self.ensure_one()
        mission = self.mission_id.sudo()
        return {
            'assignment_id': assignment.id,
            'contract_type': contract_type,
            'version': 1,
            'date_debut': assignment.date_debut,
            'date_fin': assignment.date_fin,
            'duree_jours': assignment.duree_jours,
            'montant': assignment.montant_total,
            'objet': mission.description or '',
            'livrables': mission.resultats_attendus or mission.objectifs or '',
            'conditions': mission.conditions_financieres or '',
            'modalites_validation': _(
                "Les livrables sont validés par le cluster puis par le client. "
                "Le service fait conditionne la facturation."),
        }

    def _notify_candidates_still_open(self):
        """Les autres candidats sont **signalés**, jamais écartés d'office.

        Le §17 dit « Les autres candidats passent à Non retenu ». Appliqué
        littéralement, il casserait une transition que l'Extension 1 a posée
        parce que le §2.4 l'exige : `mission_back_to_selection`, « L'intervenant
        s'est désisté ».

        `rejected` est `is_end` — irréversible par construction. Rejeter
        automatiquement tous les autres, c'est revenir en `selection` après un
        désistement avec zéro candidat récupérable, donc rouvrir l'appel. Le
        chemin de retour disparaîtrait au moment précis où il sert.

        Les candidatures encore ouvertes sont donc listées au responsable, qui
        les écarte quand le contrat est signé. L'humain décide, y compris de
        ne pas décider tout de suite.
        """
        self.ensure_one()
        mission = self.mission_id.sudo()
        pending = mission.application_ids.filtered(
            lambda a: a.id != self.id
            and a.workflow_stage_id.code not in (
                'selected', 'rejected', 'withdrawn', 'declined')
        )
        if not pending:
            return False
        mission.message_post(
            # `Markup` sur le gabarit, et **pas** sur les noms : l'opérateur
            # `%` d'un `Markup` échappe ce qu'il substitue. Un intervenant
            # nommé « Durand & Fils » s'affiche correctement, et un nom
            # contenant du HTML ne s'exécute pas. `names` est déjà du balisage,
            # il est donc construit en `Markup` lui aussi.
            body=Markup(_(
                "<p>%(count)s candidature(s) restent ouvertes sur cet appel "
                "alors qu'un intervenant vient d'être retenu :</p>"
                "<ul>%(names)s</ul>"
                "<p>Elles ne sont pas écartées automatiquement : le chemin de "
                "retour « L'intervenant s'est désisté » a besoin d'elles. "
                "Écartez-les une fois le contrat signé.</p>"
            )) % {
                'count': len(pending),
                'names': Markup("").join(
                    Markup("<li>%s</li>") % application.partner_id.display_name
                    for application in pending),
            },
            subtype_xmlid='mail.mt_note',
        )
        return True


class MissionRequestOperational(models.Model):
    """Les faits contractuels de la mission, et le démarrage de l'exécution.

    Les champs ajoutés ici sont des **faits**, jamais un avancement : le
    contrat existe-t-il, est-il signé des deux côtés. La position dans le
    processus de contractualisation est l'étape du sous-workflow
    `mission_contract`, et rien d'autre ne la porte.

    La différence n'est pas rhétorique : un fait est constaté par lecture des
    données, un état est décidé par une transition. Ces trois champs se
    recalculent ; aucun ne se pose.
    """

    _inherit = 'opex.mission.request'

    assignment_ids = fields.One2many(
        'opex.mission.assignment', 'mission_id', string="Affectations")
    assignment_id = fields.Many2one(
        'opex.mission.assignment',
        string="Affectation en cours",
        compute='_compute_contract_facts',
    )
    contract_id = fields.Many2one(
        'opex.mission.contract',
        string="Contrat en vigueur",
        compute='_compute_contract_facts',
    )
    contract_ready = fields.Boolean(
        string="Contrat prêt",
        compute='_compute_contract_facts',
        help="Un contrat en vigueur existe, avec ses dates et son montant. "
             "Lu par la condition « Envoyer à la signature ».",
    )
    contract_fully_signed = fields.Boolean(
        string="Contrat signé des deux côtés",
        compute='_compute_contract_facts',
        help="Lu par la condition « Signatures recueillies ».",
    )
    contract_stage_label = fields.Char(
        string="Contractualisation",
        compute='_compute_contract_facts',
        help="L'étape du sous-workflow du contrat, telle que l'utilisateur la "
             "lit. Vide tant que la contractualisation n'est pas lancée.",
    )

    operational_trigger = fields.Selection(
        [
            ('contracting', "Ouverture de la contractualisation"),
            ('execution', "Démarrage de l'exécution"),
        ],
        string="Déclencheur opérationnel",
        compute='_compute_operational_trigger',
        inverse='_inverse_operational_trigger',
        readonly=False,
        store=False,
        help="Écrit par une action `set_field` configurée sur une transition.",
    )

    # ------------------------------------------------------------
    # Les faits
    # ------------------------------------------------------------
    #
    # Une seule méthode, cinq champs, **tous non stockés**. Le registre
    # refuse qu'une même méthode produise du stocké et du non stocké
    # (`registry.py:543`) — la règle 9 du CLAUDE.md, payée au premier
    # chargement du module. Ici il n'y a pas de mélange : aucun de ces cinq
    # champs n'est stocké, et aucun ne doit l'être. `contract_fully_signed`
    # figé par un `store=True` continuerait d'affirmer qu'un contrat est signé
    # après qu'une révision l'a remplacé.

    @api.depends(
        'assignment_ids.active',
        'assignment_ids.contract_ids.current_version',
        'assignment_ids.contract_ids.signature_client',
        'assignment_ids.contract_ids.signature_intervenant',
        'assignment_ids.contract_ids.montant',
    )
    def _compute_contract_facts(self):
        for mission in self:
            assignment = mission.sudo().assignment_ids.filtered('active')[:1]
            contract = assignment.contract_ids.filtered(
                lambda c: c.contract_type == 'contrat' and c.current_version
            )[:1]

            mission.assignment_id = assignment
            mission.contract_id = contract
            mission.contract_ready = bool(
                contract and contract.date_debut and contract.montant)
            mission.contract_fully_signed = bool(contract and contract.is_signed)
            mission.contract_stage_label = \
                mission._contract_instance().current_stage_id.user_label or ''

    def _contract_instance(self):
        """L'instance du sous-workflow de contractualisation, s'il tourne.

        Cherchée par `res_model` / `res_id` et non par `parent_instance_id` :
        c'est exactement ce que fait `_subworkflow_done()`
        (`workflow_instance.py:305`), et deux façons de désigner la même
        instance finiraient par ne plus désigner la même.
        """
        self.ensure_one()
        return self.env['opex.workflow.instance'].sudo().search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('definition_id.code', '=', CONTRACT_WORKFLOW_CODE),
        ], order='id desc', limit=1)

    # ------------------------------------------------------------
    # Le déclencheur
    # ------------------------------------------------------------

    def _compute_operational_trigger(self):
        for mission in self:
            mission.operational_trigger = False

    def _inverse_operational_trigger(self):
        for mission in self:
            code = mission.operational_trigger
            if not code:
                continue
            getattr(mission.sudo(), '_trigger_%s' % code)()

    #: Les rôles qu'un sous-workflow de contractualisation doit connaître.
    #: Le secrétariat, le responsable et le décideur tiennent les leurs d'un
    #: groupe et n'ont pas besoin d'une ligne d'acteur ; le client et
    #: l'intervenant, comptes portail, n'existent que par elle.
    _CONTRACT_ACTOR_ROLES = ('client', 'intervenant')

    def _trigger_contracting(self):
        """Reporte client et intervenant sur l'instance du sous-workflow.

        **`start_subworkflow()` ne recopie aucun acteur.** `_start_for()`
        crée une instance neuve (`workflow_instance.py:1261`) et n'hérite rien
        du parent — ce qui est juste : un sous-processus n'a pas
        nécessairement les mêmes intervenants que le processus qui l'ouvre.

        Sans ce report, la conséquence serait double et silencieuse :

        - « Signature refusée » est ouverte au client et à l'intervenant, qui
          ne porteraient aucun rôle sur cette instance-là — le bouton
          n'apparaîtrait jamais ;
        - « Informer que le contrat est validé » vise les mêmes rôles, et
          `_partners_for_roles()` résout les acteurs **de l'instance visée**
          (`workflow_instance.py:895`). La notification ne serait envoyée à
          personne, sans erreur ni trace.

        Rien n'est inventé ici : les acteurs sont recopiés depuis l'instance
        principale, avec leur niveau d'accès. Les trois rôles internes tiennent
        les leurs d'un groupe et n'ont besoin d'aucune ligne.
        """
        self.ensure_one()
        target = self._contract_instance()
        source = self.sudo().workflow_instance_id
        if not target or not source:
            return False
        for actor in source.sudo().actor_ids:
            if actor.role_id.code in self._CONTRACT_ACTOR_ROLES \
                    and actor.user_id and actor.access_level != 'none':
                target.add_actor(actor.role_id, actor.user_id,
                                 actor.access_level)
        return True

    def _trigger_execution(self):
        """§13 — création du projet, des tâches et de leurs échéances.

        Déclenché par « Démarrer la mission », donc **après** la condition de
        la règle 5 : un projet n'est jamais créé pour une mission dont le
        contrat n'est pas validé. Placé sur « Retenir cette candidature »
        comme le §13 le laisserait croire, il aurait produit un projet
        orphelin à chaque contractualisation échouée — et le §13 dit « selon
        configuration », ce qui est précisément l'arbitrage qu'il nous laisse.
        """
        self.ensure_one()
        assignment = self.sudo().assignment_ids.filtered('active')[:1]
        if not assignment:
            _logger.info(
                "opex_intervenants: mission %s démarrée sans affectation ; "
                "aucun projet d'exécution créé.", self.id)
            return False

        # REBRANCHEMENT `project` — le garde-fou d'installation.
        #
        # Même parti qu'à la facturation, et pour la même raison : la
        # transition « Démarrer la mission » doit **aboutir**. La mission
        # démarre, les livrables de l'Extension 8 s'ouvrent normalement — ils
        # ne dépendent pas de `project` —, et ce qui manque est le miroir de
        # l'exécution dans l'outil de gestion de projet d'Odoo.
        #
        # C'est la perte la plus visible à l'écran et la moins grave au fond :
        # le suivi d'exécution du §21 vit dans `opex.mission.deliverable` et
        # dans les points d'avancement, pas dans `project.task`.
        Backend = self.env['opex.optional.backend']
        if not Backend._backend_available(PROJECT):
            _logger.info(
                "opex_intervenants: mission %s démarrée sans projet "
                "d'exécution ; le module Projet n'est pas installé.", self.id)
            self.sudo().message_post(
                # `Markup` : `message_post()` **échappe** un body `str`, et
                # les balises s'affichent alors telles quelles dans le fil -
                # `&lt;p&gt;` sous les yeux du lecteur. Mesuré sur cette base.
                #
                # Le défaut était présent sur les trois notes du module qui
                # portent du balisage ; les trois sont corrigées. Les deux
                # notes de signature de `mission_contract.py` restent en `str`,
                # et c'est juste : elles ne contiennent aucune balise, et
                # l'échappement y protège un nom d'intervenant.
                body=Markup(_(
                    "<p>La mission a démarré. <strong>Aucun projet "
                    "d'exécution n'a été créé</strong> : le module %(module)s "
                    "n'est pas installé sur cette instance.</p>"
                    "<p>Le suivi se fait dans l'onglet <em>Exécution</em> de "
                    "la mission — livrables, points d'avancement et "
                    "incidents —, qui ne dépend pas de ce module.</p>"
                )) % {'module': Backend._backend_missing_note(PROJECT)},
                subtype_xmlid='mail.mt_note',
            )
            return False

        existing = assignment._project()
        if existing:
            return existing

        project = self.env[PROJECT].sudo().create({
            'name': self.display_name,
            'partner_id': self.client_id.id or False,
        })
        assignment.write({
            'project_ref': project.id,
            'project_name': project.display_name,
        })
        self._create_execution_tasks(assignment, project)
        return project

    def _create_execution_tasks(self, assignment, project):
        """Les jalons d'exécution, tirés de ce que le client a écrit.

        Les tâches intermédiaires viennent de `resultats_attendus`, ligne à
        ligne. C'est provisoire et assumé : l'Extension 8 posera
        `opex.mission.deliverable`, et c'est de là qu'elles viendront. Les
        déduire aujourd'hui d'un champ libre vaut mieux que d'inventer trois
        tâches génériques — au moins ce qui s'affiche vient du dossier.

        Le « calendrier » du §13 est porté par `date_deadline` : les tâches
        datées apparaissent dans la vue calendrier native du projet. Un vrai
        `calendar.event` demanderait une dépendance de plus au manifeste, pour
        redire ce que le projet dit déjà.
        """
        # Atteignable seulement quand `project` est installé : `_trigger_execution()`
        # s'arrête avant. Conservée telle qu'elle sera rebranchée.
        self.ensure_one()
        Task = self.env[PROJECT_TASK].sudo()
        user = assignment.partner_id.sudo().user_ids[:1]
        assignee = [fields.Command.set(user.ids)] if user else False

        lines = [
            line.strip()
            for line in (self.resultats_attendus or '').splitlines()
            if line.strip()
        ]

        plan = [(_("Cadrage et lancement de la mission"), assignment.date_debut)]
        plan += [(line, assignment.date_fin) for line in lines]
        plan.append((_("Remise des livrables"), assignment.date_fin))

        tasks = Task.browse()
        for sequence, (name, deadline) in enumerate(plan, start=1):
            values = {
                'name': name[:250],
                'project_id': project.id,
                'sequence': sequence * 10,
                'partner_id': self.client_id.id or False,
            }
            if deadline:
                values['date_deadline'] = fields.Datetime.to_datetime(deadline)
            if assignee:
                values['user_ids'] = assignee
            tasks |= Task.create(values)
        return tasks

    # ------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------

    def action_open_contract_workflow(self):
        """Ouvre le wizard de transition du **sous-workflow** du contrat.

        Le mixin ne connaît que `workflow_instance_id`, l'instance principale.
        Le bouton « Action » de la fiche fait donc avancer la *mission* ; la
        contractualisation a le sien, sur la même page, et il est nommé pour
        qu'on ne les confonde pas.
        """
        self.ensure_one()
        instance = self._contract_instance()
        if not instance:
            raise UserError(_(
                "La contractualisation n'est pas lancée sur cet appel. Elle "
                "démarre avec « Lancer la contractualisation », depuis "
                "l'étape « Mission attribuée »."))
        return instance.action_open_transition_wizard()

    def action_view_assignments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Affectations"),
            'res_model': 'opex.mission.assignment',
            'view_mode': 'list,form',
            'domain': [('mission_id', '=', self.id)],
            'context': {'default_mission_id': self.id},
        }
