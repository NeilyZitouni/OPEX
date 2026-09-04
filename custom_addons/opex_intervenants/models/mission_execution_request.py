"""La mission vue depuis son exécution — §21, §40.

Deux choses ici, et une seule est nouvelle :

- les **compteurs de livrables**, qui donnent enfin leur champ aux deux règles
  différées de l'Extension 1 ;
- la **barre de progression du §40**, qui est une projection d'affichage de
  l'étape courante — le même parti que `pool_column` à l'Extension 6, et pour
  la même raison : le §40 demande huit jalons lisibles, pas quatorze étapes.
"""

from odoo import _, api, fields, models

#: La barre du §40, à la lettre :
#:
#:     Demande [x] Appel [x] Sélection [x] Contrat [x] Mission [>]
#:     Validation [ ] Facturation [ ] Évaluation [ ]
#:
#: Chaque jalon regroupe les étapes du graphe qui le composent. Les deux
#: derniers n'en ont pas ou en partagent une : ils se lisent sur des objets
#: extérieurs au graphe de la mission — la facture et les grilles
#: d'évaluation. Voir les deux méthodes d'affinage plus bas.
#:
#: **Deux jalons ont changé de bornes à l'Extension 9**, et le test qui
#: l'annonçait a rougi comme prévu.
#:
#: `validation` couvrait `accepted` **et** `closed`, et `facturation` n'avait
#: aucune étape. C'était juste tant que la facturation n'existait pas ; ça ne
#: l'est plus. `mission_close` s'appelle « Facturer et clôturer » depuis
#: l'Extension 1 et émet désormais la commande de vente : une mission `closed`
#: est une mission **facturée**, pas une mission en cours de validation. La
#: barre le dit.
PROGRESS_MILESTONES = [
    ('demande', "Demande", ('draft',)),
    ('appel', "Appel", ('qualified', 'sourcing', 'open')),
    ('selection', "Sélection", ('selection',)),
    ('contrat', "Contrat", ('awarded', 'contracting')),
    ('mission', "Mission", ('in_progress', 'delivered')),
    ('validation', "Validation", ('accepted',)),
    ('facturation', "Facturation", ('closed',)),
    ('evaluation', "Évaluation", ()),
]

#: Le jalon que le paiement achève. La position dans le graphe dit que la
#: facturation est **engagée** ; seul le règlement dit qu'elle est finie, et
#: cette information-là ne vient pas du workflow de la mission mais
#: d'`account.move`. Voir `_refine_invoicing_milestone()`.
INVOICING_MILESTONE = 'facturation'

#: Le jalon que les évaluations achèvent, sur le même principe. L'Extension 10
#: lui a donné son objet : une mission clôturée ouvre ses grilles, et le jalon
#: s'achève quand elles sont toutes validées. Comme pour la facturation, cela
#: se produit sans qu'une transition de la mission soit franchie.
EVALUATION_MILESTONE = 'evaluation'

#: Les étapes de branche ne figurent sur aucun jalon : une mission suspendue,
#: annulée ou infructueuse n'est pas « quelque part » sur la ligne du §40, elle
#: en est sortie. La barre le dit au lieu de mentir sur une position.
OFF_TRACK_STAGES = ('on_hold', 'cancelled', 'unsuccessful')


class MissionRequestExecution(models.Model):
    """§21 et §40 — le suivi d'exécution et la fiche de mission."""

    _inherit = 'opex.mission.request'

    deliverable_ids = fields.One2many(
        'opex.mission.deliverable', 'mission_id', string="Livrables")
    progress_report_ids = fields.One2many(
        'opex.mission.progress.report', 'mission_id',
        string="Points d'avancement")
    incident_ids = fields.One2many(
        'opex.mission.incident', 'mission_id', string="Incidents")

    # ------------------------------------------------------------
    # Les compteurs que lisent les règles 5 et 6 du §39
    # ------------------------------------------------------------
    #
    # **Stockés, et donc calculés par leur propre méthode.** Le registre
    # refuse qu'une même méthode produise du stocké et du non stocké
    # (`registry.py:543`) — la règle 9, payée au premier chargement du module.
    # Les compteurs d'affichage plus bas ont la leur.
    #
    # Ils sont stockés parce qu'ils seront filtrés et agrégés par les tableaux
    # de bord du §42 (« Livrables à valider : 5 »), et parce qu'une condition
    # de transition les lit à chaque évaluation.
    #
    # Ils comptent les livrables **obligatoires**, et eux seuls. Le §39 dit
    # « les livrables obligatoires », pas « tous les livrables » : un document
    # de confort déposé en plus ne doit pas bloquer une mission.

    deliverable_pending_count = fields.Integer(
        string="Livrables obligatoires non déposés",
        compute='_compute_deliverable_gates',
        store=True,
        readonly=True,
        help="Lu par la condition de « Soumettre les livrables ».",
    )
    deliverable_unvalidated_count = fields.Integer(
        string="Livrables obligatoires non validés",
        compute='_compute_deliverable_gates',
        store=True,
        readonly=True,
        help="Lu par la règle 6 du §39, que l'Extension 9 rattachera à "
             "« Valider le service fait ».",
    )

    deliverable_count = fields.Integer(
        string="Nombre de livrables", compute='_compute_execution_counters')
    deliverable_late_count = fields.Integer(
        string="Livrables en retard", compute='_compute_execution_counters')
    deliverable_to_validate_count = fields.Integer(
        string="Livrables à valider", compute='_compute_execution_counters')
    incident_open_count = fields.Integer(
        string="Incidents ouverts", compute='_compute_execution_counters')
    temps_passe_total = fields.Float(
        string="Temps passé (jours)", digits=(6, 2),
        compute='_compute_execution_counters')
    #: `avancement_declare`, et non `avancement` tout court.
    #:
    #: Le test de l'Extension 1 refuse tout champ dont le nom pourrait être
    #: celui d'un état déguisé, et il a rougi sur `avancement`. Il avait raison
    #: de le signaler : le nom, seul, ne dit pas s'il s'agit d'une position
    #: dans le processus ou d'un pourcentage tapé par quelqu'un.
    #:
    #: C'est un pourcentage tapé par quelqu'un — l'intervenant, dans son point
    #: d'avancement du §21. Le suffixe le dit, et il n'y a plus à se poser la
    #: question en relisant le modèle.
    avancement_declare = fields.Integer(
        string="Avancement déclaré (%)",
        compute='_compute_execution_counters',
        help="Celui du dernier point d'avancement rédigé par l'intervenant. "
             "C'est une donnée déclarative, pas une position dans le "
             "processus : celle-là est portée par l'étape du workflow.")

    @api.depends('deliverable_ids.is_required',
                 'deliverable_ids.workflow_stage_id')
    def _compute_deliverable_gates(self):
        """Les deux compteurs stockés — ceux qui commandent des transitions."""
        for mission in self:
            codes = mission._required_deliverable_stage_codes()
            mission.deliverable_pending_count = sum(
                1 for code in codes if code not in ('submitted', 'validated'))
            mission.deliverable_unvalidated_count = sum(
                1 for code in codes if code != 'validated')

    def _required_deliverable_stage_codes(self):
        """Les codes d'étape des livrables obligatoires, **avec répétitions**.

        Une compréhension, jamais `mapped('workflow_stage_id.code')` :
        `mapped()` sur un Many2one déduplique, et trois livrables arrêtés à la
        même étape n'en feraient qu'un. Ici, le défaut serait direct — la
        condition de « Soumettre les livrables » compterait 1 là où il en
        manque 3, et la mission passerait.

        `sudo()` : un client doit pouvoir voir où en sont les livrables de sa
        mission sans avoir le droit de les lire un par un.
        """
        self.ensure_one()
        return [
            deliverable.workflow_stage_id.code
            for deliverable in self.sudo().deliverable_ids
            if deliverable.is_required
        ]

    @api.depends('deliverable_ids.workflow_stage_id',
                 'deliverable_ids.deadline',
                 'incident_ids.is_open',
                 'progress_report_ids.avancement',
                 'progress_report_ids.temps_passe_jours')
    def _compute_execution_counters(self):
        """Les compteurs d'affichage — non stockés, méthode distincte."""
        for mission in self:
            deliverables = mission.sudo().deliverable_ids
            reports = mission.sudo().progress_report_ids

            mission.deliverable_count = len(deliverables)
            mission.deliverable_late_count = sum(
                1 for d in deliverables if d.en_retard)
            mission.deliverable_to_validate_count = sum(
                1 for d in deliverables
                if d.workflow_stage_id.code == 'submitted')
            mission.incident_open_count = sum(
                1 for incident in mission.sudo().incident_ids
                if incident.is_open)
            mission.temps_passe_total = sum(
                report.temps_passe_jours for report in reports)
            # Le dernier point déclaré, pas une moyenne : l'avancement n'est
            # pas une grandeur qu'on additionne.
            latest = reports.sorted(key=lambda r: (r.date, r.id), reverse=True)
            mission.avancement_declare = latest[0].avancement if latest else 0

    # ------------------------------------------------------------
    # §40 — la barre de progression de la fiche de mission
    # ------------------------------------------------------------

    def mission_progress_bar(self):
        """Les huit jalons du §40, avec leur état d'affichage.

        > Demande [x] Appel [x] Sélection [x] Contrat [x] Mission [>]
        > Validation [ ] Facturation [ ] Évaluation [ ]

        Les marqueurs sont ceux de cette docstring, pas ceux du modèle : la
        méthode renvoie `fait`, `en_cours` ou `a_venir`, et c'est le gabarit
        qui choisit comment les dessiner.

        **Une méthode, pas un champ stocké.** C'est une projection
        d'affichage de `workflow_stage_id`, comme `pool_column` à l'Extension 6
        — à ceci près que celui-là devait être groupable dans un Kanban, ce qui
        justifiait son stockage. Ici, rien ne filtre ni n'agrège sur la barre :
        la stocker n'ajouterait qu'une valeur à resynchroniser.

        Retourne une liste de dictionnaires `{code, libelle, etat}`, où `etat`
        vaut `fait`, `en_cours` ou `a_venir`. Le gabarit choisit les symboles ;
        le modèle ne connaît pas ni .

        Les deux derniers jalons ne se lisent pas sur l'étape : Facturation
        s'achève au règlement de la facture, Évaluation à la validation des
        grilles. Ni l'un ni l'autre ne correspond à une transition de la
        mission, et c'est exactement pourquoi ni la facturation ni les
        évaluations ne sont pilotées par le graphe de la mission.
        """
        self.ensure_one()
        code = self.sudo().workflow_stage_id.code
        off_track = code in OFF_TRACK_STAGES

        # Le jalon courant : le premier dont les étapes contiennent celle-ci.
        current = next(
            (index for index, (_c, _l, stages) in enumerate(PROGRESS_MILESTONES)
             if code in stages),
            None,
        )

        steps = []
        for index, (milestone, label, _stages) in enumerate(PROGRESS_MILESTONES):
            if current is None:
                # Étape de branche, ou étape inconnue : aucun jalon n'est
                # « en cours ». On ne devine pas une position sur une ligne
                # dont la mission est sortie.
                etat = 'a_venir'
            elif index < current:
                etat = 'fait'
            elif index == current:
                etat = 'en_cours'
            else:
                etat = 'a_venir'
            steps.append({
                'code': milestone,
                'libelle': label,
                'etat': etat,
            })

        if off_track:
            # Signalé plutôt que masqué : une mission suspendue dont la barre
            # afficherait « Mission » ferait croire qu'elle avance.
            for step in steps:
                if step['etat'] == 'en_cours':
                    step['etat'] = 'a_venir'
            return steps

        self._refine_invoicing_milestone(steps)
        self._refine_evaluation_milestone(steps)
        return steps

    def _refine_evaluation_milestone(self, steps):
        """Les évaluations achèvent le dernier jalon - §30, §31, §40.

        Même mécanique que pour la facturation, et pour la même raison : les
        grilles sont validées une par une, sur leur propre workflow, pendant
        que la mission reste `closed`. Aucune transition de la mission ne
        marque ce moment.

        Le jalon n'est jamais `en_cours` : `closed` est déjà pris par la
        facturation, et un jalon ne peut pas être le courant de deux endroits
        à la fois. Il passe de `a_venir` à `fait`, ce qui suffit - le §40
        n'affiche que trois symboles.
        """
        self.ensure_one()
        if not self.evaluations_validees:
            return steps
        for step in steps:
            if step['code'] == EVALUATION_MILESTONE:
                step['etat'] = 'fait'
        return steps

    def _refine_invoicing_milestone(self, steps):
        """Le paiement achève le jalon Facturation — §29, Schéma 12.

        **Le seul endroit de la barre où l'étape du workflow ne suffit
        pas.** Les sept autres jalons se déduisent entièrement de
        `workflow_stage_id` ; celui-ci a deux moments que le graphe de la
        mission ne distingue pas, parce qu'ils ne lui appartiennent pas :

        - la commande est émise et la facture générée — `en_cours` ;
        - la facture est réglée — `fait`.

        Le second fait vit dans `account.move.payment_state`, et il change
        quand un comptable enregistre un paiement, c'est-à-dire **sans qu'une
        seule transition soit franchie**. Aucune configuration de workflow ne
        pouvait le porter ; c'est bien ce qui a justifié de ne pas donner de
        définition à la facturation (voir `models/mission_invoicing.py`).

        La mission clôturée sans facture — le savepoint du §29 a rendu la main
        — reste `en_cours` sur ce jalon. C'est exact : il reste quelque chose à
        faire, et la note du dossier dit quoi.
        """
        self.ensure_one()
        if not self.facture_payee:
            return steps
        for step in steps:
            if step['code'] == INVOICING_MILESTONE and step['etat'] == 'en_cours':
                step['etat'] = 'fait'
        return steps

    def mission_progress_label(self):
        """L'en-tête du §40 : « Statut : En cours ».

        Le libellé utilisateur de l'étape, jamais son code — c'est
        `stage.user_label` qui le porte depuis l'Extension 1.
        """
        self.ensure_one()
        return self.sudo().workflow_stage_id.user_label or ''

    # ------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------

    def action_view_deliverables(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Livrables"),
            'res_model': 'opex.mission.deliverable',
            'view_mode': 'list,form',
            'domain': [('mission_id', '=', self.id)],
            'context': {'default_mission_id': self.id},
        }

    def action_view_incidents(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Incidents"),
            'res_model': 'opex.mission.incident',
            'view_mode': 'list,form',
            'domain': [('mission_id', '=', self.id)],
            'context': {'default_mission_id': self.id},
        }
