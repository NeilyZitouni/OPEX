"""Les quatre espaces du §18 et la priorisation du §43.

Un modèle abstrait plutôt qu'une table : ce sont des agrégats recalculés à
chaque affichage. Un tableau de bord mémorisé se décorrèle du réel à la
première transition, et un tableau de bord faux est pire qu'absent - c'est
déjà le parti de `client_dashboard()` à l'Extension 2.

Chaque espace renvoie un dictionnaire à clés fermées, construit ici et non
dans le gabarit. Deux raisons, et les deux ont été payées :

- une requête ORM posée en QWeb s'exécute sous l'identité du visiteur et fait
  tomber la page entière en AccessError, pas le bloc fautif (règle 5) ;
- une donnée réservée se filtre au modèle, pas au gabarit (règle 12). Un
  intervenant ne doit jamais recevoir le dictionnaire du responsable, même
  partiellement masqué à l'affichage.

C'est aussi ce que veut le §18 : « chacun voit ce qui le concerne ». Les
quatre méthodes ne partagent pas leur périmètre, elles partagent leur forme.
"""

from odoo import api, fields, models

# §43 - au-delà de ce délai sur l'étape, un contrat en attente passe en urgent.
# Le document dit « Contrat en attente depuis 3 jours ».
CONTRACT_ALERT_DAYS = 3

# §43 - « Mission arrivant à échéance ». Une semaine laisse le temps d'agir ;
# le jour même, l'alerte ne sert plus à rien.
DEADLINE_ALERT_DAYS = 7

# Les trois niveaux du §43. Les libellés vivent ici et non dans le gabarit :
# c'est le modèle qui range un élément dans un niveau, l'écran ne fait que
# choisir la couleur.
URGENT = 'urgent'
A_TRAITER = 'a_traiter'
TERMINE = 'termine'


class MissionDashboard(models.AbstractModel):
    """Les indicateurs et les files d'attente, par acteur."""

    _name = 'opex.mission.dashboard'
    _description = "Tableaux de bord des missions"

    # ------------------------------------------------------------
    # Responsable OPEX - Smart Work Queue (§42, §18)
    # ------------------------------------------------------------

    @api.model
    def manager_queue(self):
        """Les sept indicateurs du §42, plus la file priorisée du §43.

        Appelée derrière `res.users._is_missions_staff()`, jamais autrement :
        c'est la seule méthode des quatre qui ne borne pas son périmètre à un
        contact. Le contrôle d'accès vit dans la route, comme partout ailleurs
        dans ce module.
        """
        Mission = self.env['opex.mission.request'].sudo()
        Application = self.env['opex.mission.application'].sudo()
        Deliverable = self.env['opex.mission.deliverable'].sudo()

        missions = Mission.search([])
        applications = Application.search([])
        deliverables = Deliverable.search([])

        return {
            'indicateurs': {
                'demandes_a_traiter': self._count_stage(missions, ('qualified',)),
                'appels_actifs': self._count_stage(
                    missions, Mission.OPEN_CALL_STAGES),
                'candidatures': len(applications.filtered(
                    lambda a: a.workflow_stage_id.code
                    not in ('selected', 'rejected', 'withdrawn', 'declined'))),
                'missions_en_cours': self._count_stage(
                    missions, ('in_progress', 'delivered')),
                'livrables_a_valider': self._count_stage(
                    deliverables, ('submitted',)),
                'contrats_en_attente': len(self._pending_contracts(missions)),
                'missions_a_cloturer': self._count_stage(missions, ('accepted',)),
            },
            'priorites': self._priority_board(
                missions, applications, deliverables),
        }

    # ------------------------------------------------------------
    # Intervenant (§41)
    # ------------------------------------------------------------

    @api.model
    def intervenant_space(self, partner):
        """Les cinq indicateurs du §41 et les actions rapides.

        « Appels pertinents » se lit au sens strict du §41 : les appels
        ouverts et publiés auxquels cet intervenant n'a pas encore répondu.
        Un appel où il a déjà une candidature n'est plus une opportunité, il
        est déjà dans la colonne d'à côté - l'y compter deux fois gonflerait
        le chiffre que l'expert regarde en premier.
        """
        Mission = self.env['opex.mission.request'].sudo()
        Application = self.env['opex.mission.application'].sudo()

        applications = Application.search([('partner_id', '=', partner.id)])
        assignments = self.env['opex.mission.assignment'].sudo().search(
            [('partner_id', '=', partner.id), ('active', '=', True)])
        missions = assignments.mission_id

        deja_candidat = applications.mission_id.ids
        opportunites = Mission.search([
            ('workflow_stage_id.code', '=', 'open'),
            ('is_published', '=', True),
            ('id', 'not in', deja_candidat),
        ])

        profile = partner.sudo().expert_profile_id

        return {
            'indicateurs': {
                'appels_pertinents': len(opportunites),
                'candidatures_en_cours': len(applications.filtered(
                    lambda a: a.workflow_stage_id.code
                    not in ('rejected', 'withdrawn', 'declined'))),
                'missions_en_cours': self._count_stage(
                    missions, ('in_progress', 'delivered')),
                'missions_terminees': self._count_stage(
                    missions, Mission.DONE_MISSION_STAGES),
                'note_moyenne': profile.reputation_score if profile else 0.0,
            },
            'opportunites': opportunites[:5],
            'priorites': self._priority_board(
                missions, applications,
                self.env['opex.mission.deliverable'].sudo().search(
                    [('partner_id', '=', partner.id)]),
                for_staff=False),
        }

    # ------------------------------------------------------------
    # Client (§6, §18)
    # ------------------------------------------------------------

    @api.model
    def client_space(self, partner):
        """Ce que le client suit : ses demandes, et ce qui l'attend.

        Les quatre indicateurs sont ceux de `client_dashboard()`, posés à
        l'Extension 2 et laissés là où ils sont : les redéfinir ici en ferait
        deux versions du même compte, et c'est toujours la seconde qui dérive.
        """
        Mission = self.env['opex.mission.request'].sudo()
        missions = Mission.search([('client_id', '=', partner.id)])
        applications = self.env['opex.mission.application'].sudo().search(
            [('mission_id', 'in', missions.ids)])
        deliverables = self.env['opex.mission.deliverable'].sudo().search(
            [('mission_id', 'in', missions.ids)])

        return {
            'indicateurs': Mission.client_dashboard(partner),
            'priorites': self._priority_board(
                missions, applications, deliverables, for_staff=False),
        }

    # ------------------------------------------------------------
    # Candidat externe (§18)
    # ------------------------------------------------------------

    @api.model
    def candidate_space(self, partner):
        """« Catalogue public, fiche mission, candidature courte, suivi. »

        Le candidat externe n'a ni mission ni affectation : il a des
        candidatures et leur état. L'espace se réduit donc à un suivi, et
        c'est exactement ce que le §18 lui accorde.

        Il ne reçoit pas de file du §43. Rien de ce qu'il pourrait y lire ne
        lui appartient : les urgences d'un dossier sont celles de ceux qui
        l'instruisent.
        """
        Application = self.env['opex.mission.application'].sudo()
        applications = Application.search([('partner_id', '=', partner.id)])

        return {
            'indicateurs': {
                'candidatures': len(applications),
                'en_cours': len(applications.filtered(
                    lambda a: a.workflow_stage_id.code
                    not in ('selected', 'rejected', 'withdrawn', 'declined'))),
                'retenues': len(applications.filtered(
                    lambda a: a.workflow_stage_id.code == 'selected')),
            },
            'suivi': [
                {
                    'reference': application.display_name,
                    'mission': application.mission_id.title or '',
                    'etape': application.workflow_stage_label or '',
                    # `/my/missions/candidature/<id>` : l'espace de noms du
                    # module est `/my/missions/*` (règle 1). Écrite
                    # `/my/candidatures/<id>`, cette URL ne correspondait à
                    # aucune règle du routing map — 404 mesuré.
                    'url': '/my/missions/candidature/%s' % application.id,
                }
                for application in applications
            ],
        }

    # ------------------------------------------------------------
    # §43 - la priorisation
    # ------------------------------------------------------------

    def _priority_board(self, missions, applications, deliverables,
                        for_staff=True):
        """Les trois niveaux du §43, sur le périmètre reçu.

        Le périmètre est passé par l'appelant et jamais recalculé ici : c'est
        ce qui permet à la même méthode de servir le responsable, qui voit
        tout, et l'intervenant, qui ne voit que ses dossiers. Une méthode qui
        déciderait elle-même de son périmètre finirait par le décider mal pour
        l'un des deux.

        `for_staff` ne masque rien du contenu - il retire les entrées qui
        n'ont de sens que pour celui qui instruit. Une nouvelle candidature
        n'est pas une tâche du client.
        """
        today = fields.Date.context_today(self)
        limite = fields.Date.add(today, days=DEADLINE_ALERT_DAYS)

        urgent = []
        for mission in self._pending_contracts(missions, aged=True):
            urgent.append(self._item(
                mission, "Contrat en attente depuis plus de %s jours"
                % CONTRACT_ALERT_DAYS))
        for deliverable in deliverables.filtered('en_retard'):
            urgent.append(self._item(
                deliverable, "Livrable en retard : %s" % deliverable.name,
                url='/my/missions/%s' % deliverable.mission_id.id))
        for mission in missions.filtered(
                lambda m: m.workflow_stage_id.code in ('in_progress', 'delivered')
                and m.date_fin_souhaitee and m.date_fin_souhaitee <= limite):
            urgent.append(self._item(mission, "Mission arrivant à échéance"))

        a_traiter = []
        if for_staff:
            for application in applications.filtered(
                    lambda a: a.workflow_stage_id.code == 'applied'):
                a_traiter.append(self._item(
                    application,
                    "Nouvelle candidature : %s"
                    % application.partner_id.display_name,
                    url='/staff/missions/%s/pool' % application.mission_id.id))
            for mission in missions.filtered(
                    lambda m: m.workflow_stage_id.code == 'qualified'):
                a_traiter.append(self._item(mission, "Nouvelle demande"))
        for deliverable in deliverables.filtered(
                lambda d: d.workflow_stage_id.code == 'submitted'):
            a_traiter.append(self._item(
                deliverable, "Livrable soumis : %s" % deliverable.name,
                url='/my/missions/%s' % deliverable.mission_id.id))

        termine = []
        for mission in missions.filtered(
                lambda m: m.workflow_stage_id.code == 'accepted'):
            termine.append(self._item(mission, "Mission validée"))
        for mission in missions.filtered('contract_fully_signed'):
            termine.append(self._item(mission, "Contrat signé"))
        for mission in missions.filtered('facture_payee'):
            termine.append(self._item(mission, "Facture payée"))

        return {URGENT: urgent, A_TRAITER: a_traiter, TERMINE: termine}

    def _item(self, record, libelle, url=None):
        """Une entrée de file : ce qu'on lit, et où l'on va.

        Clés fermées, et aucune n'est le recordset lui-même. Un gabarit qui
        recevrait l'enregistrement pourrait en afficher n'importe quel champ,
        y compris ceux que le §14 réserve.
        """
        mission = record if record._name == 'opex.mission.request' \
            else getattr(record, 'mission_id', None)
        return {
            'libelle': libelle,
            'reference': (mission.name if mission else '') or '',
            'titre': (mission.title if mission else '') or '',
            'url': url or ('/my/missions/%s' % mission.id if mission else '/my'),
        }

    # ------------------------------------------------------------
    # Helpers partagés
    # ------------------------------------------------------------

    @staticmethod
    def _count_stage(records, codes):
        """Compte les enregistrements arrêtés sur l'une de ces étapes.

        Une compréhension, jamais `mapped('workflow_stage_id.code')` :
        `mapped()` sur un Many2one déduplique, et trois dossiers arrêtés à la
        même étape n'en feraient qu'un. Sur un tableau de bord, le défaut
        serait invisible - le chiffre serait simplement faux.
        """
        return sum(1 for record in records
                   if record.workflow_stage_id.code in codes)

    def _pending_contracts(self, missions, aged=False):
        """Les missions dont la contractualisation traîne.

        `aged` distingue le compteur du §42 - tout ce qui est en attente - de
        l'alerte du §43, qui ne se déclenche qu'au-delà de trois jours. Deux
        questions voisines, une seule traversée : les séparer en deux méthodes
        aurait fait diverger la définition de « en attente ».
        """
        limite = fields.Datetime.subtract(
            fields.Datetime.now(), days=CONTRACT_ALERT_DAYS)
        pending = missions.filtered(
            lambda m: m.workflow_stage_id.code in ('awarded', 'contracting')
            and not m.contract_fully_signed)
        if not aged:
            return pending
        return pending.filtered(
            lambda m: self._entered_stage_on(m) <= limite
            if self._entered_stage_on(m) else False)

    @staticmethod
    def _entered_stage_on(record):
        """Depuis quand ce dossier est-il arrêté sur son étape ?

        Lu dans le journal du moteur, qui date chaque passage. L'instance ne
        porte que `date_start` et `date_end` : s'en servir ferait dater
        l'attente de l'ouverture du dossier, et une mission ouverte il y a
        trois semaines serait « en attente depuis trois semaines » le jour même
        où elle atteint la contractualisation.

        La dernière ligne, pas la première : c'est le passage le plus récent
        qui dit depuis quand rien ne bouge.
        """
        instance = record.sudo().workflow_instance_id
        lines = instance.history_ids.sorted('id') if instance else None
        return lines[-1].date if lines else False
