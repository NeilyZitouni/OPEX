from odoo.exceptions import AccessError, UserError
from odoo.tests.common import tagged

from .common import MissionCase

ACCEPTANCE_CODE = 'mission_service_acceptance'


@tagged('post_install', '-at_install')
class TestServiceAcceptance(MissionCase):
    """Extension 9 — service fait, règle 6 du §39, facturation et paiement."""

    # ------------------------------------------------------------
    # Fabriques
    # ------------------------------------------------------------

    def _delivered_mission(self, **overrides):
        """Une mission arrivée à « Livrables remis », constat ouvert.

        C'est le point de départ du §27 : les livrables sont remis, la
        validation finale n'a pas commencé.
        """
        mission = self._new_mission(**overrides)
        self._open_the_call(mission)
        self._select_the_application(self._new_application(mission))
        self._do(mission, 'mission_close_applications', self.manager)
        self._do(mission, 'mission_award', self.decideur,
                 comment="Candidature retenue par le comité.")
        self._validate_the_contract(mission)
        self._do(mission, 'mission_start', self.manager)
        self._do(mission, 'mission_deliver', self.manager)
        return mission

    def _closed_mission(self, **overrides):
        """Une mission clôturée, donc facturée."""
        mission = self._delivered_mission(**overrides)
        self._run_service_acceptance_cycle(mission)
        self._do(mission, 'mission_accept_service', self.manager)
        self._do(mission, 'mission_close', self.secretariat,
                 comment="Mission clôturée par le test.")
        mission.invalidate_recordset()
        return mission

    #
    # LA RÈGLE QUI GOUVERNE TOUT LE RESTE
    #

    def test_the_acceptance_has_no_state_field(self):
        """Quatrième définition du module, et la même règle qu'aux trois autres.

        On vérifie aussi `resultat` : le §28 dit « Le système enregistre :
        Date de validation, Validateur, Commentaire, **Résultat** », et c'est
        exactement le nom sous lequel un état reviendrait ici. Le résultat
        d'un constat, c'est l'étape qu'il a atteinte.
        """
        fields_ = self.env['opex.service.acceptance']._fields
        for suspect in ('state', 'etat', 'statut', 'status', 'stage_id',
                        'resultat', 'avancement', 'phase'):
            self.assertNotIn(
                suspect, fields_,
                "Le constat porte « %s » : son avancement doit être "
                "`workflow_stage_id`, et rien d'autre." % suspect)
        self.assertIn('workflow_instance_id', fields_)

    def test_the_acceptance_workflow_matches_the_schema_11(self):
        """§27, §28 — deux validations, une contestation, une boucle."""
        definition = self.Definition._get_for_code(ACCEPTANCE_CODE)
        self.assertEqual(definition.state, 'published')
        self.assertEqual(definition.model_name, 'opex.service.acceptance')

        self.assertEqual(
            set(definition.stage_ids.mapped('code')),
            {'draft', 'cluster_validated', 'disputed', 'accepted'})

        transitions = set(definition.transition_ids.mapped('code'))
        self.assertIn('service_validate_cluster', transitions)
        self.assertIn('service_validate_client', transitions)
        # La contestation et sa reprise comptent deux transitions à elles
        # seules : c'est cette boucle qui fait du cycle un graphe et non une
        # séquence — et c'est elle qui interdit de marquer `disputed` finale.
        self.assertIn('service_dispute', transitions)
        self.assertIn('service_rework', transitions)

    def test_only_the_success_stage_is_final(self):
        """La règle 14 du CLAUDE.md, née à l'Extension 7, vérifiée ici.

        `do_transition()` pose `state = 'done'` en atteignant **n'importe
        quelle** étape `is_end`. Marquer la contestation comme finale
        clôturerait l'instance, et « Reprendre après contestation »
        deviendrait infranchissable : le client qui conteste fermerait la
        mission définitivement.

        `_check_graph()` ne dit rien de tout cela — deux étapes finales sont
        un graphe parfaitement valide. Ce test est le seul garde-fou.
        """
        definition = self.Definition._get_for_code(ACCEPTANCE_CODE)
        finals = definition.stage_ids.filtered('is_end')
        self.assertEqual(
            [stage.code for stage in finals], ['accepted'],
            "Le constat a plus d'une étape finale : une contestation "
            "clôturerait l'instance et fermerait la mission.")

    def test_the_invoicing_has_no_workflow_of_its_own(self):
        """Le Schéma 12 n'est pas une cinquième définition, et c'est voulu.

            Mission validée → Facturation → Facture générée → En attente de
            paiement → Payée

        Ces quatre cases sont celles de `sale.order` et d'`account.move`, qu
        'Odoo tient déjà. Une définition parallèle serait un second récit de la
        même histoire, et elle se désynchroniserait au premier paiement
        enregistré depuis l'écran de banque.

        Ce test **verrouille le critère**, pas la commodité : le jour où
        quelqu'un publie une définition sur `sale.order`, la conversation a
        lieu.
        """
        definitions = self.Definition.sudo().search(
            [('model_name', 'in', ('sale.order', 'account.move'))])
        self.assertFalse(
            definitions,
            "Une définition de workflow pilote %s : la facturation est celle "
            "d'Odoo, ce module la lit et ne la double pas."
            % definitions.mapped('model_name'))

    #
    # §27 — LE CONSTAT S'OUVRE TOUT SEUL
    #

    def test_the_acceptance_opens_when_the_deliverables_are_submitted(self):
        """Une action configurée sur `mtr_deliver`, pas un `create()` caché."""
        mission = self._delivered_mission()
        acceptance = mission.sudo().acceptance_ids

        self.assertEqual(len(acceptance), 1)
        self.assertEqual(self._stage(acceptance), 'draft')
        self.assertTrue(acceptance.name.startswith('SF-'))
        # Le montant vient de l'affectation, pas d'une saisie.
        self.assertEqual(
            acceptance.montant_a_facturer,
            sum(mission.sudo().assignment_ids.mapped('montant_total')))
        self.assertTrue(acceptance.montant_a_facturer > 0)

    def test_the_acceptance_is_created_once_across_the_correction_loop(self):
        """§25 — la boucle de correction repasse par « Soumettre les livrables ».

        Sans idempotence, chaque retour produirait un constat de plus, et la
        contrainte SQL le dirait brutalement au second tour.
        """
        mission = self._delivered_mission()
        first = mission.sudo().acceptance_ids

        self._do(mission, 'mission_request_corrections', self.manager,
                 comment="Le rapport est incomplet.")
        self.assertEqual(self._stage(mission), 'in_progress')
        self._do(mission, 'mission_deliver', self.manager)

        mission.invalidate_recordset()
        self.assertEqual(mission.sudo().acceptance_ids, first)

    def test_the_expert_who_delivers_does_not_become_the_client(self):
        """`initiator_role_id` vide, pour la troisième fois du module.

        Le constat est créé par le déclencheur de « Soumettre les livrables »,
        donc sous l'identité du responsable. Si la définition renseignait
        `initiator_role_id`, c'est **lui** qui recevrait le rôle `client` en
        accès `full` — et validerait la prestation à la place du client.
        """
        mission = self._delivered_mission()
        acceptance = mission.sudo().acceptance_ids
        definition = self.Definition._get_for_code(ACCEPTANCE_CODE)
        self.assertFalse(definition.initiator_role_id)

        client_actors = acceptance.workflow_instance_id.actor_ids.filtered(
            lambda actor: actor.role_id.code == 'client')
        self.assertEqual(
            client_actors.mapped('user_id'), self.client_user,
            "Le rôle `client` sur le constat n'est pas porté par le client.")

    #
    # §28 — LES QUATRE POINTS DE LA VALIDATION FINALE
    #

    def test_the_four_points_of_the_section_28_gate_the_cluster_validation(self):
        """Quatre cases à cocher que rien ne lirait seraient un aide-mémoire."""
        mission = self._delivered_mission()
        acceptance = mission.sudo().acceptance_ids

        with self.assertRaises(UserError) as refus:
            self._do(acceptance, 'service_validate_cluster', self.manager)
        self.assertIn("quatre points", str(refus.exception))
        self.assertEqual(self._stage(acceptance), 'draft')

        # Trois sur quatre ne suffisent pas : la condition est un « et ».
        acceptance.write({
            'objectifs_atteints': True,
            'livrables_complets': True,
            'corrections_effectuees': True,
        })
        with self.assertRaises(UserError):
            self._do(acceptance, 'service_validate_cluster', self.manager)

        acceptance.write({'conforme_contrat': True})
        self._do(acceptance, 'service_validate_cluster', self.manager)
        self.assertEqual(self._stage(acceptance), 'cluster_validated')

    def test_the_client_pronounces_the_final_validation(self):
        """§27 — « Le client ou le responsable habilité valide la réalisation. »"""
        mission = self._delivered_mission()
        acceptance = self._run_service_acceptance_cycle(mission)

        self.assertEqual(self._stage(acceptance), 'accepted')
        self.assertTrue(acceptance.is_accepted)
        mission.invalidate_recordset()
        self.assertTrue(mission.sudo().service_fait_valide)

    def test_the_service_acceptance_gates_the_mission_validation(self):
        """Sans le constat, « Valider le service fait » serait décoratif.

        Le §27 confie la validation finale au client. Si la transition de la
        mission passait sans lui, le constat ne servirait à rien et le
        responsable clôturerait seul.
        """
        mission = self._delivered_mission()

        with self.assertRaises(UserError) as refus:
            self._do(mission, 'mission_accept_service', self.manager)
        self.assertIn("constat de service fait", str(refus.exception))
        self.assertEqual(self._stage(mission), 'delivered')

        # L'assertion positive, sans laquelle la précédente ne vaut rien.
        self._run_service_acceptance_cycle(mission)
        self._do(mission, 'mission_accept_service', self.manager)
        self.assertEqual(self._stage(mission), 'accepted')

    #
    # LA CONTESTATION, ET CE QU'ELLE APPREND
    #

    def test_a_dispute_does_not_close_the_acceptance(self):
        """La démonstration de la règle 14, par le parcours et non par la config.

        `disputed` n'est pas `is_end`, donc l'instance reste `running` et la
        reprise est possible. Le test précédent lit la configuration ;
        celui-ci fait cliquer — une étape marquée finale ferait échouer les
        deux, et le message dirait `'done' != 'running'`.
        """
        mission = self._delivered_mission()
        acceptance = mission.sudo().acceptance_ids
        acceptance.write({
            'objectifs_atteints': True, 'livrables_complets': True,
            'corrections_effectuees': True, 'conforme_contrat': True,
        })
        self._do(acceptance, 'service_validate_cluster', self.manager)

        self._do(acceptance, 'service_dispute', self.client_user,
                 comment="Le rapport ne couvre pas le périmètre convenu.")
        self.assertEqual(self._stage(acceptance), 'disputed')
        self.assertEqual(
            acceptance.workflow_instance_id.state, 'running',
            "Le constat est clos après une contestation : `disputed` a été "
            "marquée `is_end` et le client vient de fermer la mission.")
        self.assertFalse(acceptance.is_accepted)

        # Et la mission, elle, ne peut pas avancer.
        mission.invalidate_recordset()
        self.assertFalse(mission.sudo().service_fait_valide)
        with self.assertRaises(UserError):
            self._do(mission, 'mission_accept_service', self.manager)

        # La reprise existe et ramène le constat au cluster.
        self._do(acceptance, 'service_rework', self.manager,
                 comment="Périmètre revu avec l'intervenant.")
        self.assertEqual(self._stage(acceptance), 'draft')

    def test_the_validation_facts_come_from_the_journal_and_show_the_last(self):
        """La leçon de l'Extension 8, appliquée aux validations du §28.

        Un constat contesté puis revalidé passe **deux fois** par la
        validation du cluster. Un champ écrit au premier passage afficherait
        une date périmée ; relus dans le journal, les six champs disent la
        dernière.

        Le dernier passage est retrouvé par une compréhension, jamais par
        `mapped()` : `mapped()` sur un Many2one déduplique, et le second
        passage y deviendrait invisible — sans que rien ne le signale, puisqu'il
        resterait une date à afficher.
        """
        mission = self._delivered_mission()
        acceptance = mission.sudo().acceptance_ids
        acceptance.write({
            'objectifs_atteints': True, 'livrables_complets': True,
            'corrections_effectuees': True, 'conforme_contrat': True,
        })

        self._do(acceptance, 'service_validate_cluster', self.manager,
                 comment="Premier contrôle.")
        first_validation = acceptance.date_validation_cluster
        self.assertTrue(first_validation)
        self.assertEqual(acceptance.validateur_cluster_id, self.manager)

        self._do(acceptance, 'service_dispute', self.client_user,
                 comment="Le livrable 2 manque.")
        self._do(acceptance, 'service_rework', self.manager,
                 comment="Livrable 2 ajouté.")
        self._do(acceptance, 'service_validate_cluster', self.manager,
                 comment="Second contrôle.")

        acceptance.invalidate_recordset()
        self.assertEqual(
            acceptance.commentaire_cluster, "Second contrôle.",
            "Le constat affiche le premier contrôle : les validations ont été "
            "recopiées au lieu d'être relues dans le journal.")

        # Le passage par la même étape compte **deux fois**. C'est
        # exactement ce que `mapped()` effacerait.
        entries = acceptance.validation_entries()
        cluster_entries = [entry for entry in entries
                           if entry['commentaire'] in
                           ("Premier contrôle.", "Second contrôle.")]
        self.assertEqual(len(cluster_entries), 2)

        # Et la contestation figure dans la même trace — la règle 9 du §39
        # demande de conserver les tours qui ont échoué, pas seulement le bon.
        self.assertIn(
            "Le livrable 2 manque.",
            [entry['commentaire'] for entry in entries])

    def test_no_field_stores_a_validation(self):
        """Le corollaire du test précédent, côté modèle.

        Un champ **calculé** ne peut pas être écrit : c'est ce qui garantit
        qu'aucune seconde vérité n'apparaîtra. Sans cette assertion, quelqu'un
        pourrait poser un `store=True` et la régression passerait au vert —
        les valeurs seraient justes le jour où on les écrit.
        """
        fields_ = self.env['opex.service.acceptance']._fields
        for name in ('date_validation_cluster', 'validateur_cluster_id',
                     'commentaire_cluster', 'date_validation_client',
                     'validateur_client_id', 'commentaire_client'):
            field = fields_[name]
            self.assertTrue(
                field.compute and not field.store,
                "« %s » est écrit ou stocké : le §28 se relit dans le journal "
                "du moteur, il ne s'y recopie pas." % name)

    #
    # §29 — LA FACTURATION
    #

    def test_the_closing_creates_and_confirms_the_sale_order(self):
        """« Facturer et clôturer » facture — l'Extension 1 l'avait annoncé."""
        self._require_backend('sale.order', "Facturation du §29")
        mission = self._closed_mission()
        acceptance = mission.sudo().acceptance_ids
        order = acceptance._sale_order()

        self.assertTrue(
            order,
            "Aucune commande de vente : le déclencheur de « Facturer et "
            "clôturer » n'a pas tourné, ou la comptabilité l'a refusée.")
        self.assertEqual(order.state, 'sale')
        self.assertEqual(order.partner_id, self.client_user.partner_id)

        # Les six informations que le §29 demande de reprendre.
        line = order.order_line[:1]
        self.assertEqual(order.client_order_ref, mission.name)
        self.assertIn(mission.name, line.name)
        self.assertIn(self.intervenant.partner_id.name, line.name)
        self.assertEqual(line.price_unit, acceptance.montant_a_facturer)

    def test_the_closing_generates_the_invoice(self):
        """Schéma 12 — « Facture générée », puis « En attente de paiement »."""
        self._require_backend('sale.order', "Facturation du §29")
        mission = self._closed_mission()
        invoices = mission.sudo().acceptance_ids._sale_order().invoice_ids

        self.assertEqual(len(invoices), 1)
        self.assertTrue(mission.sudo().facture_generee)
        self.assertFalse(mission.sudo().facture_payee)
        self.assertEqual(
            mission.sudo().facturation_label, "En attente de paiement")

    def test_the_invoicing_does_not_run_twice(self):
        """Idempotence — un second passage ne produit pas une seconde facture.

        La transition ne se rejoue pas dans le graphe, mais le déclencheur
        n'en sait rien : c'est lui qui doit se garder, comme celui de la
        sélection à l'Extension 7.
        """
        self._require_backend('sale.order', "Facturation du §29")
        mission = self._closed_mission()
        acceptance = mission.sudo().acceptance_ids
        order = acceptance._sale_order()

        mission.sudo()._trigger_invoicing()
        mission.invalidate_recordset()
        self.assertEqual(acceptance._sale_order(), order)
        self.assertEqual(len(order.invoice_ids), 1)

    def test_the_payment_completes_the_invoicing(self):
        """Schéma 12 — « Payée », lue dans `account.move`, jamais décidée ici.

        Le paiement est enregistré par le chemin normal d'Odoo — l'assistant
        de règlement —, pas en écrivant `payment_state` à la main. C'est tout
        l'argument de l'extension : cet état ne nous appartient pas, et un test
        qui le forcerait ne prouverait rien sur ce que le module lit.
        """
        self._require_backend('sale.order', "Suivi du paiement du Schéma 12")
        mission = self._closed_mission()
        invoice = mission.sudo().acceptance_ids._sale_order().invoice_ids
        invoice.action_post()

        wizard = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids).create({})
        wizard.action_create_payments()

        mission.invalidate_recordset()
        self.assertTrue(
            mission.sudo().facture_payee,
            "Le règlement est enregistré et la mission l'ignore : "
            "`payment_state` n'est pas lu correctement.")
        self.assertEqual(mission.sudo().facturation_label, "Payée")
        self.assertEqual(mission.sudo().montant_restant_du, 0.0)

    #
    # §40 — LA BARRE, QUATRE JALONS PLUS LOIN
    #

    def test_the_invoicing_milestone_is_reached_at_closing(self):
        mission = self._closed_mission()
        bar = {step['code']: step['etat'] for step in
               mission.sudo().mission_progress_bar()}

        self.assertEqual(bar['mission'], 'fait')
        self.assertEqual(bar['validation'], 'fait')
        self.assertEqual(bar['facturation'], 'en_cours')
        self.assertEqual(bar['evaluation'], 'a_venir')

    def test_the_payment_completes_the_invoicing_milestone(self):
        """Le seul jalon de la barre que l'étape du workflow ne suffit pas à
        décrire — et c'est la démonstration de pourquoi la facturation n'a pas
        de définition : `payment_state` change **sans qu'une transition soit
        franchie**.
        """
        self._require_backend('sale.order', "Jalon Facturation du §40")
        mission = self._closed_mission()
        invoice = mission.sudo().acceptance_ids._sale_order().invoice_ids
        invoice.action_post()
        wizard = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids).create({})
        wizard.action_create_payments()
        mission.invalidate_recordset()

        # L'étape de la mission n'a pas bougé d'un pouce…
        self.assertEqual(self._stage(mission), 'closed')
        # …et pourtant le jalon est achevé.
        bar = {step['code']: step['etat'] for step in
               mission.sudo().mission_progress_bar()}
        self.assertEqual(bar['facturation'], 'fait')

    #
    # ÉTANCHÉITÉ
    #

    def test_an_outsider_cannot_read_an_acceptance(self):
        """On **lit un champ** et on attend une `AccessError`.

        `exists()` n'applique aucune `ir.rule` — il ne fait qu'un `SELECT id`.
        Une assertion d'étanchéité qui l'utiliserait passerait au vert en ne
        prouvant que l'existence de la ligne en base. Règle 7 du CLAUDE.md.
        """
        mission = self._delivered_mission()
        acceptance = mission.sudo().acceptance_ids

        # Assertion positive d'abord : le client concerné, lui, la lit.
        self.assertTrue(
            acceptance.with_user(self.client_user).montant_a_facturer >= 0)

        with self.assertRaises(AccessError):
            acceptance.with_user(self.other_client).montant_a_facturer

    def test_the_client_cannot_tick_the_cluster_checklist(self):
        """Les quatre points du §28 sont ceux du cluster, pas du client.

        Le client prononce la validation finale ; il ne coche pas lui-même les
        cases qui la conditionnent. L'ACL et l'`ir.rule` le tiennent tous les
        deux en lecture seule.
        """
        mission = self._delivered_mission()
        acceptance = mission.sudo().acceptance_ids

        with self.assertRaises(AccessError):
            acceptance.with_user(self.client_user).write(
                {'objectifs_atteints': True})
