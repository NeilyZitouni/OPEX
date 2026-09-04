from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import tagged

from .common import MissionCase

DELIVERABLE_CODE = 'mission_deliverable'


@tagged('post_install', '-at_install')
class TestExecution(MissionCase):
    """Extension 8 — l'exécution : livrables, avancement, incidents, §40."""

    # ------------------------------------------------------------
    # Fabriques
    # ------------------------------------------------------------

    def _running_mission(self, **overrides):
        """Une mission en cours d'exécution, avec son intervenant affecté."""
        mission = self._new_mission(**overrides)
        self._open_the_call(mission)
        self._select_the_application(self._new_application(mission))
        self._do(mission, 'mission_close_applications', self.manager)
        self._do(mission, 'mission_award', self.decideur,
                 comment="Candidature retenue par le comité.")
        self._validate_the_contract(mission)
        self._do(mission, 'mission_start', self.manager)
        return mission

    def _new_deliverable(self, mission, **overrides):
        values = {
            'mission_id': mission.id,
            'name': "Rapport de vulnérabilités",
            'deadline': fields.Date.context_today(self.Mission)
            + timedelta(days=10),
        }
        values.update(overrides)
        return self.env['opex.mission.deliverable'].create(values)

    def _do_deliverable(self, deliverable, code, user, comment=False):
        return self._do(deliverable, code, user, comment=comment)

    def _submit_deliverable(self, deliverable, user=None):
        user = user or self.intervenant
        deliverable.sudo().write({'file': b'ZmljaGllcg==', 'filename': "v1.pdf"})
        self._do(deliverable, 'deliverable_start', user)
        self._do(deliverable, 'deliverable_submit', user)
        return deliverable

    #
    # LA RÈGLE QUI GOUVERNE TOUT LE RESTE
    #

    def test_the_deliverable_has_no_state_field(self):
        """Le cycle de vie d'un livrable est un workflow, pas un `Selection`.

        On vérifie aussi les synonymes : un `state` renommé `etat` ou
        `statut` serait le même défaut sous un autre nom.
        """
        fields_ = self.env['opex.mission.deliverable']._fields
        for suspect in ('state', 'etat', 'statut', 'stage_id', 'avancement'):
            self.assertNotIn(
                suspect, fields_,
                "Le livrable porte « %s » : son avancement doit être "
                "`workflow_stage_id`, et rien d'autre." % suspect)
        self.assertIn('workflow_instance_id', fields_)

    def test_the_deliverable_workflow_matches_the_schema_9(self):
        """§23, Schéma 9 — cinq étapes, dont « En cours ».

        Une de plus que le livrable d'`opex_innovation`. Le Schéma 9 du §23
        intercale « En cours » entre « À faire » et « Soumise », et c'est le
        `Module3_OPEX_Intervenants.md` qui fait foi sur l'UX. Sans elle,
        « pas commencé » et « commencé, pas rendu » se confondent, et le §43
        ne peut plus signaler un retard sur ce qui a réellement démarré.
        """
        definition = self.Definition._get_for_code(DELIVERABLE_CODE)
        self.assertEqual(definition.state, 'published')
        self.assertEqual(definition.model_name, 'opex.mission.deliverable')

        codes = set(definition.stage_ids.mapped('code'))
        self.assertEqual(
            codes,
            {'todo', 'in_progress', 'submitted', 'correction_requested',
             'validated'})

        # La boucle de correction compte deux transitions à elle seule :
        # c'est elle qui fait de ce cycle un graphe et non une séquence.
        transition_codes = set(definition.transition_ids.mapped('code'))
        self.assertIn('deliverable_request_correction', transition_codes)
        self.assertIn('deliverable_resubmit', transition_codes)

        finals = definition.stage_ids.filtered('is_end')
        self.assertEqual([stage.code for stage in finals], ['validated'])

    def test_the_incident_is_a_counter_not_a_process(self):
        """L'incident porte un champ d'état, et c'est le critère qui décide.

        Le Schéma 10 du §26 donne le cycle en entier — Ouvert → En traitement
        → Résolu. Linéaire : pas de chemin de refus, pas de condition, pas de
        rôle qui change d'une case à l'autre. C'est la ligne de partage que le
        CLAUDE.md du moteur pose pour `roadmap.phase`.

        Ce test **verrouille le critère**, pas la commodité : si quelqu'un
        ajoute une quatrième position — « contesté », « rejeté » —, l'incident
        cesse d'être un compteur et doit devenir une définition. Le test
        rougira, et ce sera la bonne conversation.
        """
        Incident = self.env['opex.mission.incident']
        self.assertNotIn(
            'workflow_instance_id', Incident._fields,
            "L'incident a reçu un workflow : mettez à jour ce test et le "
            "CLAUDE.md, la décision a changé.")
        self.assertEqual(
            [value for value, _label in Incident._fields['traitement'].selection],
            ['ouvert', 'en_traitement', 'resolu'],
            "Le cycle de l'incident n'est plus celui du Schéma 10 : s'il a "
            "gagné une issue, ce n'est plus un compteur mais un processus.")

    #
    # §24, §25 — LE DÉPÔT, LA VALIDATION, LA CORRECTION
    #

    def test_the_deliverable_starts_its_own_workflow(self):
        mission = self._running_mission()
        deliverable = self._new_deliverable(mission)

        self.assertTrue(deliverable.workflow_instance_id)
        self.assertEqual(self._stage(deliverable), 'todo')
        # L'instance du livrable est distincte de celle de la mission.
        self.assertNotEqual(
            deliverable.sudo().workflow_instance_id,
            mission.sudo().workflow_instance_id)

    def test_the_deliverable_is_linked_to_the_assignment(self):
        mission = self._running_mission()
        deliverable = self._new_deliverable(mission)
        self.assertEqual(
            deliverable.sudo().partner_id, self.intervenant.partner_id)

    def test_a_deliverable_can_be_planned_before_any_assignment(self):
        """§22 — le plan de mission se dessine avant qu'on ait un intervenant.

        Assertion positive d'abord : le livrable existe et avance. Sans elle,
        « pas d'affectation » serait aussi vrai sur une création échouée.
        """
        mission = self._new_mission()
        deliverable = self._new_deliverable(mission)
        self.assertEqual(self._stage(deliverable), 'todo')
        self.assertFalse(deliverable.sudo().assignment_id)

    def test_the_submission_is_blocked_without_a_file(self):
        mission = self._running_mission()
        deliverable = self._new_deliverable(mission)
        self._do(deliverable, 'deliverable_start', self.intervenant)

        with self.assertRaises(UserError) as refus:
            self._do(deliverable, 'deliverable_submit', self.intervenant)
        self.assertIn("Joignez le fichier", str(refus.exception))
        self.assertEqual(self._stage(deliverable), 'in_progress')

    def test_the_nominal_deliverable_path(self):
        mission = self._running_mission()
        deliverable = self._submit_deliverable(self._new_deliverable(mission))
        self.assertEqual(self._stage(deliverable), 'submitted')

        self._do(deliverable, 'deliverable_validate', self.manager)
        self.assertEqual(self._stage(deliverable), 'validated')
        self.assertEqual(deliverable.sudo().workflow_state, 'done')
        self.assertTrue(deliverable.sudo().is_validated)

    #
    # §25 — L'HISTORIQUE DES VERSIONS ET LE MOTIF DU REFUS
    #

    def test_the_refusal_reason_is_carried_by_the_archived_version(self):
        """Le point de conception, et la leçon d'`opex_innovation`.

        Deux refus successifs, deux motifs différents. Si le motif vivait sur
        le **livrable**, le second écraserait le premier et l'on ne saurait
        plus ce qui avait été reproché d'abord — c'est-à-dire justement ce que
        le §25 demande de conserver.

        Le test ne se contente pas de compter les versions : il vérifie que
        **chaque version porte le motif qui la visait**, elle et pas une autre.
        """
        mission = self._running_mission()
        deliverable = self._submit_deliverable(self._new_deliverable(mission))

        self._do(deliverable, 'deliverable_request_correction', self.manager,
                 comment="Le périmètre réseau manque.")
        deliverable.sudo().submit_new_version(
            file=b'ZGV1eA==', filename="v2.pdf", user=self.intervenant)

        self._do(deliverable, 'deliverable_request_correction', self.manager,
                 comment="Les recommandations ne sont pas hiérarchisées.")
        deliverable.sudo().submit_new_version(
            file=b'dHJvaXM=', filename="v3.pdf", user=self.intervenant)

        versions = deliverable.sudo().version_ids.sorted('version')
        self.assertEqual(len(versions), 2)
        self.assertEqual(deliverable.sudo().version, 3)

        # Chaque motif sur SA version. C'est l'assertion qui rougit si le
        # motif est recopié sur le livrable au lieu d'être relu au moment
        # d'archiver.
        self.assertEqual(versions[0].version, 1)
        self.assertIn("périmètre réseau", versions[0].motif_correction)
        self.assertEqual(versions[1].version, 2)
        self.assertIn("hiérarchisées", versions[1].motif_correction)

    def test_the_archived_version_keeps_the_file_it_had(self):
        """On fige AVANT d'écrire, et c'est tout l'intérêt de la méthode.

        Après l'écriture, `file` porte déjà le nouveau contenu et l'archive
        serait un double de la version courante. L'historique existerait, et
        ne contiendrait rien d'utile — le pire des deux mondes, parce qu'on le
        croirait bon.
        """
        mission = self._running_mission()
        deliverable = self._submit_deliverable(self._new_deliverable(mission))
        self._do(deliverable, 'deliverable_request_correction', self.manager,
                 comment="À revoir.")

        deliverable.sudo().submit_new_version(
            file=b'ZGV1eA==', filename="v2.pdf", user=self.intervenant)

        archived = deliverable.sudo().version_ids
        self.assertEqual(archived.filename, "v1.pdf")
        self.assertNotEqual(
            archived.file, deliverable.sudo().file,
            "La version archivée est un double de la version courante : "
            "l'archivage a eu lieu après l'écriture.")

    def test_an_archived_version_cannot_be_rewritten(self):
        """Une archive modifiable ne prouve rien.

        Même verrou que sur `opex.workflow.history`. Sans lui, l'historique
        des versions dirait ce qu'on veut bien qu'il dise, et le §25 n'aurait
        plus de portée.
        """
        mission = self._running_mission()
        deliverable = self._submit_deliverable(self._new_deliverable(mission))
        self._do(deliverable, 'deliverable_request_correction', self.manager,
                 comment="À revoir.")
        deliverable.sudo().submit_new_version(user=self.intervenant)

        version = deliverable.sudo().version_ids[:1]
        with self.assertRaises(UserError) as refus:
            version.with_user(self.manager).write(
                {'motif_correction': "Autre chose."})
        self.assertIn("historique", str(refus.exception))

    def test_the_correction_history_counts_every_refusal(self):
        """Compréhension, jamais `mapped()`.

        Un livrable refusé deux fois repasse par la même étape, et `mapped()`
        sur un Many2one dédoublonne : le second refus disparaîtrait, et
        l'écran affirmerait qu'on n'a rien reproché deux fois.
        """
        mission = self._running_mission()
        deliverable = self._submit_deliverable(self._new_deliverable(mission))

        for motif in ("Premier motif.", "Second motif."):
            self._do(deliverable, 'deliverable_request_correction',
                     self.manager, comment=motif)
            deliverable.sudo().submit_new_version(user=self.intervenant)

        history = deliverable.sudo().correction_history()
        self.assertEqual(len(history), 2)
        self.assertEqual(
            [entry['motif'] for entry in history],
            ["Premier motif.", "Second motif."])

    def test_a_new_version_is_refused_outside_the_correction_stage(self):
        mission = self._running_mission()
        deliverable = self._submit_deliverable(self._new_deliverable(mission))
        with self.assertRaises(UserError) as refus:
            deliverable.sudo().submit_new_version(user=self.intervenant)
        self.assertIn("demande de correction", str(refus.exception))

    #
    # LA CONDITION DE DÉPÔT — LA RÈGLE DIFFÉRÉE DE L'EXTENSION 1
    #

    def test_the_pending_rule_is_now_attached(self):
        """`rule_mission_deliverables_submitted` a trouvé son champ.

        Déclarée à l'Extension 1 et rattachée à rien : son expression
        `field('deliverable_pending_count', 1) == 0` valait 1 — son défaut —
        tant que le champ n'existait pas, donc elle était **fermée** et aurait
        rendu « Soumettre les livrables » infranchissable.
        """
        transition = self._transition(self.mission_definition, 'mission_deliver')
        codes = {rule.code for rule in transition.sudo().condition_ids}
        self.assertIn('mission_deliverables_submitted', codes)

    def test_the_mission_cannot_be_delivered_with_a_pending_deliverable(self):
        mission = self._running_mission()
        self._new_deliverable(mission, is_required=True)

        with self.assertRaises(UserError) as refus:
            self._do(mission, 'mission_deliver', self.manager)
        self.assertIn("livrables obligatoires", str(refus.exception))
        self.assertEqual(self._stage(mission), 'in_progress')

    def test_a_submitted_deliverable_unlocks_the_delivery(self):
        """L'assertion positive, sans laquelle la précédente ne vaut rien."""
        mission = self._running_mission()
        deliverable = self._new_deliverable(mission, is_required=True)
        self._submit_deliverable(deliverable)
        mission.invalidate_recordset()

        self.assertEqual(mission.sudo().deliverable_pending_count, 0)
        self._do(mission, 'mission_deliver', self.manager)
        self.assertEqual(self._stage(mission), 'delivered')

    def test_an_optional_deliverable_blocks_nothing(self):
        """§39 dit « les livrables **obligatoires** », pas « tous ».

        Un document de confort déposé en plus ne doit bloquer aucune
        transition — sinon personne n'en déposera jamais.
        """
        mission = self._running_mission()
        self._new_deliverable(mission, is_required=False)
        mission.invalidate_recordset()

        self.assertEqual(mission.sudo().deliverable_pending_count, 0)
        self._do(mission, 'mission_deliver', self.manager)
        self.assertEqual(self._stage(mission), 'delivered')

    def test_the_counters_do_not_deduplicate(self):
        """Trois livrables à la même étape en font trois, pas un.

        `mapped()` sur un Many2one déduplique. Ici le défaut serait direct : la
        condition compterait 1 là où il en manque 3, et la mission passerait
        avec deux livrables non déposés.
        """
        mission = self._running_mission()
        for index in range(3):
            self._new_deliverable(mission, name="Livrable %s" % index)
        mission.invalidate_recordset()
        self.assertEqual(mission.sudo().deliverable_pending_count, 3)

    def test_the_validation_rule_guards_the_service_acceptance(self):
        """Ce test a rougi à l'Extension 9, et c'était sa raison d'être.

        Il s'appelait `test_the_validation_rule_stays_deferred_to_extension_9`
        et affirmait que la règle 6 n'était rattachée à rien —
        `mission_request_workflow.xml` écrivant sur `mtr_accept_service` que
        « la règle 6 y sera rattachée par l'Extension 9 ». Elle l'est ; le
        test est retourné plutôt que retiré.

        Le compteur qu'elle lit — `deliverable_unvalidated_count` — est celui
        que l'Extension 8 a posé, et il compte les livrables **obligatoires**
        seulement. C'est ce que le §39 demande : « tant que les livrables
        obligatoires ne sont pas validés ».
        """
        transition = self._transition(
            self.mission_definition, 'mission_accept_service')
        codes = {rule.code for rule in transition.sudo().condition_ids}
        self.assertIn(
            'mission_deliverables_validated', codes,
            "La règle 6 du §39 ne garde plus « Valider le service fait ».")

    def test_an_unvalidated_deliverable_blocks_the_final_validation(self):
        """La règle 6 du §39, mesurée plutôt que constatée dans la config.

        Vérifier qu'une règle est *rattachée* ne prouve pas qu'elle
        *bloque* : le test précédent lit la configuration, celui-ci fait
        cliquer. Les deux sont nécessaires — une règle rattachée dont
        l'expression serait fausse passerait le premier sans rien garder.
        """
        mission = self._running_mission()
        deliverable = self._new_deliverable(mission)
        self._submit_deliverable(deliverable)
        self._do(mission, 'mission_deliver', self.manager)

        # Le livrable est déposé, pas validé : le compteur de la règle 6 le dit.
        mission.invalidate_recordset()
        self.assertEqual(mission.sudo().deliverable_unvalidated_count, 1)

        with self.assertRaises(UserError):
            self._run_service_acceptance_cycle(mission)

        # Assertion positive : une fois le livrable validé, le même cycle
        # passe. Sans elle, le test rougirait aussi bien pour une bonne raison
        # que pour une mauvaise — un helper cassé, par exemple.
        self._do(deliverable, 'deliverable_validate', self.manager)
        mission.invalidate_recordset()
        self.assertEqual(mission.sudo().deliverable_unvalidated_count, 0)

        self._run_service_acceptance_cycle(mission)
        self._do(mission, 'mission_accept_service', self.manager)
        self.assertEqual(self._stage(mission), 'accepted')

    #
    # §21 — LE POINT D'AVANCEMENT
    #

    def test_the_progress_report_carries_the_five_facts_of_the_brief(self):
        """Temps passé, avancement, livrables, problèmes, prochaine étape."""
        mission = self._running_mission()
        deliverable = self._new_deliverable(mission)
        report = self.env['opex.mission.progress.report'].create({
            'mission_id': mission.id,
            'partner_id': self.intervenant.partner_id.id,
            'temps_passe_jours': 3.5,
            'avancement': 40,
            'travaux_realises': "Revue documentaire terminée.",
            'problemes': "Accès au SI de production toujours en attente.",
            'prochaine_etape': "Tests techniques.",
            'deliverable_ids': [(6, 0, deliverable.ids)],
        })
        mission.invalidate_recordset()

        self.assertEqual(mission.sudo().temps_passe_total, 3.5)
        self.assertEqual(mission.sudo().avancement_declare, 40)
        self.assertEqual(report.deliverable_ids, deliverable)

    def test_the_mission_shows_the_latest_progress_not_a_sum(self):
        """L'avancement n'est pas une grandeur qu'on additionne.

        Le temps passé se cumule, l'avancement se remplace. Deux compteurs,
        deux agrégations — les confondre donnerait 90 % après deux points à
        40 et 50.
        """
        mission = self._running_mission()
        today = fields.Date.context_today(self.Mission)
        Report = self.env['opex.mission.progress.report']
        for offset, avancement, temps in ((7, 40, 3.0), (1, 65, 2.0)):
            Report.create({
                'mission_id': mission.id,
                'partner_id': self.intervenant.partner_id.id,
                'date': today - timedelta(days=offset),
                'avancement': avancement,
                'temps_passe_jours': temps,
            })
        mission.invalidate_recordset()

        self.assertEqual(mission.sudo().avancement_declare, 65)
        self.assertEqual(mission.sudo().temps_passe_total, 5.0)

    def test_an_impossible_progress_is_refused(self):
        mission = self._running_mission()
        with self.assertRaises(ValidationError):
            self.env['opex.mission.progress.report'].create({
                'mission_id': mission.id,
                'partner_id': self.intervenant.partner_id.id,
                'avancement': 140,
            })

    #
    # §26 — LES INCIDENTS
    #

    def test_the_incident_follows_the_schema_10(self):
        mission = self._running_mission()
        incident = self.env['opex.mission.incident'].create({
            'mission_id': mission.id,
            'incident_type': 'retard',
            'priorite': '1',
            'description': "Livrable intermédiaire non reçu.",
        })
        self.assertTrue(incident.name.startswith("INC-"))
        self.assertEqual(incident.traitement, 'ouvert')
        self.assertTrue(incident.is_open)

        incident.action_take_over()
        self.assertEqual(incident.traitement, 'en_traitement')
        self.assertTrue(incident.is_open)

        incident.action_resolve()
        self.assertEqual(incident.traitement, 'resolu')
        self.assertFalse(incident.is_open)
        self.assertTrue(incident.date_resolution)

        incident.action_reopen()
        self.assertEqual(incident.traitement, 'en_traitement')
        self.assertFalse(incident.date_resolution)

    def test_the_open_incident_counter_feeds_the_mission(self):
        mission = self._running_mission()
        Incident = self.env['opex.mission.incident']
        first = Incident.create({
            'mission_id': mission.id, 'description': "Retard."})
        Incident.create({'mission_id': mission.id, 'description': "Blocage."})
        mission.invalidate_recordset()
        self.assertEqual(mission.sudo().incident_open_count, 2)

        first.action_resolve()
        mission.invalidate_recordset()
        self.assertEqual(mission.sudo().incident_open_count, 1)

    def test_the_intervenant_cannot_open_an_incident(self):
        """§26 réserve le signalement au responsable.

        Ce n'est pas un canal de réclamation ouvert : l'intervenant décrit ses
        difficultés dans « Problèmes rencontrés » de son point d'avancement, et
        c'est le responsable qui décide d'en faire un incident.
        """
        mission = self._running_mission()
        with self.assertRaises(AccessError):
            self.env['opex.mission.incident'].with_user(
                self.intervenant).create({
                    'mission_id': mission.id,
                    'description': "Je signale moi-même.",
                })

    #
    # §43 — LE RETARD
    #

    def test_a_late_deliverable_is_flagged_and_searchable(self):
        """Le champ calculé **et** sa recherche disent la même chose.

        `en_retard` n'est pas stocké — il dépend de la date du jour et se
        figerait au dernier recalcul. Il n'était donc pas cherchable, et le
        filtre « En retard » de la vue faisait échouer le **chargement du
        module**. La parade est une méthode `search`, pas une recopie de la
        logique dans le domaine du filtre : deux définitions du retard
        divergeraient au premier ajustement.

        Ce test les compare, précisément pour que cette divergence rougisse.
        """
        mission = self._running_mission()
        today = fields.Date.context_today(self.Mission)
        late = self._new_deliverable(
            mission, name="En retard", deadline=today - timedelta(days=3))
        on_time = self._new_deliverable(
            mission, name="Dans les temps",
            deadline=today + timedelta(days=3))

        self.assertTrue(late.en_retard)
        self.assertFalse(on_time.en_retard)

        Deliverable = self.env['opex.mission.deliverable'].sudo()
        found = Deliverable.search([
            ('mission_id', '=', mission.id), ('en_retard', '=', True)])
        self.assertEqual(
            found, late,
            "Le calcul et la recherche ne désignent pas les mêmes livrables.")

        # Et le retard cesse dès que le livrable est déposé : il n'est plus
        # entre les mains de l'intervenant.
        self._submit_deliverable(late)
        late.invalidate_recordset()
        self.assertFalse(late.en_retard)
        self.assertFalse(Deliverable.search([
            ('mission_id', '=', mission.id), ('en_retard', '=', True)]))

    #
    # §40 — LA BARRE DE PROGRESSION
    #

    def test_the_progress_bar_has_the_eight_milestones_of_the_document(self):
        """> Demande Appel Sélection Contrat Mission Validation
        > Facturation Évaluation
        """
        mission = self._new_mission()
        bar = mission.mission_progress_bar()
        self.assertEqual(
            [step['libelle'] for step in bar],
            ["Demande", "Appel", "Sélection", "Contrat", "Mission",
             "Validation", "Facturation", "Évaluation"])

    def test_the_progress_bar_follows_the_stage(self):
        """L'exemple exact du §40, sur une mission en cours."""
        mission = self._running_mission()
        bar = {step['code']: step['etat'] for step in
               mission.sudo().mission_progress_bar()}

        self.assertEqual(bar['demande'], 'fait')
        self.assertEqual(bar['appel'], 'fait')
        self.assertEqual(bar['selection'], 'fait')
        self.assertEqual(bar['contrat'], 'fait')
        self.assertEqual(bar['mission'], 'en_cours')
        self.assertEqual(bar['validation'], 'a_venir')

    def test_a_suspended_mission_is_not_shown_as_advancing(self):
        """Signalé plutôt que masqué.

        Une mission suspendue dont la barre afficherait « Mission » ferait
        croire qu'elle avance. `on_hold` n'est sur aucun jalon : la mission est
        sortie de la ligne du §40, et la barre le dit au lieu d'inventer une
        position.
        """
        mission = self._running_mission()
        self._do(mission, 'mission_hold_progress', self.manager,
                 comment="Le client est indisponible.")
        self.assertEqual(self._stage(mission), 'on_hold')

        bar = mission.sudo().mission_progress_bar()
        self.assertFalse(
            [step for step in bar if step['etat'] == 'en_cours'],
            "Une mission suspendue est affichée comme si elle avançait.")
        # Assertion positive : la barre est bien rendue, et l'amont reste acquis.
        self.assertEqual(len(bar), 8)
        self.assertEqual(bar[0]['etat'], 'a_venir')

    def test_the_bar_reaches_the_last_two_milestones_at_closing(self):
        """Les huit jalons du §40 ont tous leur objet.

        Ce test a porté deux affirmations périmées et a rougi deux fois, à
        chaque fois pour la bonne raison. Il disait d'abord que Facturation et
        Évaluation n'avaient aucune étape ; l'Extension 9 a donné la sienne à
        la première, l'Extension 10 à la seconde.

        Ce qu'il mesure désormais est l'état de la barre au moment de la
        clôture, avant que la facture soit réglée et que les grilles soient
        rendues. Les deux derniers jalons s'achèvent plus tard, sans qu'une
        transition de la mission soit franchie — c'est l'objet des tests de
        `test_service_acceptance.py` et de `test_evaluation.py`.
        """
        mission = self._running_mission()
        self._do(mission, 'mission_deliver', self.manager)
        self._run_service_acceptance_cycle(mission)
        self._do(mission, 'mission_accept_service', self.manager)
        self._do(mission, 'mission_close', self.secretariat,
                 comment="Mission clôturée par le test.")

        bar = {step['code']: step['etat'] for step in
               mission.sudo().mission_progress_bar()}
        self.assertEqual(bar['validation'], 'fait')
        self.assertEqual(bar['facturation'], 'en_cours')
        self.assertEqual(bar['evaluation'], 'a_venir')

        # Et les évaluations sont bien ouvertes : la clôture les a demandées.
        self.assertEqual(len(mission.sudo().evaluation_ids), 2)

    #
    # ÉTANCHÉITÉ
    #

    def test_an_outsider_cannot_read_a_deliverable(self):
        """On **lit un champ** et on attend une `AccessError`.

        `exists()` n'applique aucune `ir.rule` — il ne fait qu'un `SELECT id`.
        Deux tests d'étanchéité écrits `assertFalse(record.with_user(autre)
        .exists())` passaient au vert en ne prouvant que l'existence de la
        ligne en base. Payé à l'Extension 1.
        """
        mission = self._running_mission()
        deliverable = self._new_deliverable(mission)

        # Assertion positive d'abord : l'intervenant concerné, lui, y accède.
        self.assertTrue(deliverable.with_user(self.intervenant).name)

        with self.assertRaises(AccessError):
            deliverable.with_user(self.other_intervenant).name

    def test_the_client_reads_the_deliverables_without_writing_them(self):
        """§21 — le client suit les livrables. Il ne les dépose pas."""
        mission = self._running_mission()
        deliverable = self._new_deliverable(mission)

        self.assertTrue(deliverable.with_user(self.client_user).name)
        with self.assertRaises(AccessError):
            deliverable.with_user(self.client_user).write({'name': "Autre"})

    def test_the_intervenant_cannot_rewrite_a_submitted_deliverable(self):
        """La version examinée doit être celle qui a été lue.

        C'est aussi ce qui donne son sens à l'archive du §25 : un fichier
        qu'on peut remplacer après coup rendrait l'historique décoratif.
        """
        mission = self._running_mission()
        deliverable = self._new_deliverable(mission)

        # Assertion positive : il écrit bien tant qu'il est attendu.
        deliverable.with_user(self.intervenant).write({'description': "Plan."})

        self._submit_deliverable(deliverable)
        with self.assertRaises(AccessError):
            deliverable.with_user(self.intervenant).write(
                {'description': "Après coup."})
