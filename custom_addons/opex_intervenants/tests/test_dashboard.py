import os
import re

from odoo.exceptions import AccessError
from odoo.tests.common import HttpCase, new_test_user, tagged

from .common import MissionCase


@tagged('post_install', '-at_install')
class TestDashboard(MissionCase):
    """Extension 11 - les quatre espaces, la priorisation, les notifications."""

    def _closed_mission(self, **overrides):
        mission = self._new_mission(**overrides)
        self._open_the_call(mission)
        self._select_the_application(self._new_application(mission))
        self._do(mission, 'mission_close_applications', self.manager)
        self._do(mission, 'mission_award', self.decideur, comment="Retenue.")
        self._validate_the_contract(mission)
        self._do(mission, 'mission_start', self.manager)
        self._do(mission, 'mission_deliver', self.manager)
        self._run_service_acceptance_cycle(mission)
        self._do(mission, 'mission_accept_service', self.manager)
        self._do(mission, 'mission_close', self.secretariat, comment="Clôturée.")
        mission.invalidate_recordset()
        return mission

    def _dashboard(self):
        return self.env['opex.mission.dashboard'].sudo()

    def _assert_route_resolves(self, url, endpoint, **arguments):
        """L'URL est-elle servie par une règle, et par laquelle ?

        Écrit après un 404 qu'aucun test ne voyait. Les assertions d'alors
        comparaient la valeur rendue à une chaîne construite par le même `%` :

            self.assertEqual(url, '/my/candidatures/%s' % application.id)

        Les deux côtés étaient faux de la même façon, donc l'égalité tenait.
        L'URL ne correspondait à **aucune** route — l'espace de noms du module
        est `/my/missions/*` — et le candidat qui cliquait sur sa propre
        notification de cloche tombait sur une page introuvable.

        Confronter l'URL au routing map est la seule forme qui ne peut pas
        être fausse des deux côtés : la carte est construite par les
        `@http.route`, pas par le test.
        """
        from werkzeug.exceptions import NotFound

        adaptateur = self.env['ir.http'].routing_map().bind('localhost')
        try:
            trouve, valeurs = adaptateur.match(url, method='GET')
        except NotFound:
            raise AssertionError(
                "« %s » ne correspond à aucune route : l'écran renverra un "
                "404. Comparer cette chaîne à une autre chaîne ne l'aurait "
                "pas dit." % url)
        nom = getattr(getattr(trouve, 'func', trouve), '__name__', str(trouve))
        self.assertEqual(
            nom, endpoint,
            "« %s » est servie par `%s`, pas par `%s` : l'utilisateur "
            "n'atterrit pas sur l'écran attendu." % (url, nom, endpoint))
        for cle, attendu in arguments.items():
            self.assertEqual(
                valeurs.get(cle), attendu,
                "« %s » désigne %s=%s au lieu de %s : le lien mène au dossier "
                "de quelqu'un d'autre." % (url, cle, valeurs.get(cle), attendu))

    #
    # Les quatre espaces du §18
    #

    def test_the_manager_queue_has_the_seven_indicators_of_the_section_42(self):
        """Le tableau du §42, dans son ordre."""
        self._new_mission()
        queue = self._dashboard().manager_queue()
        self.assertEqual(
            list(queue['indicateurs']),
            ['demandes_a_traiter', 'appels_actifs', 'candidatures',
             'missions_en_cours', 'livrables_a_valider', 'contrats_en_attente',
             'missions_a_cloturer'])
        self.assertEqual(list(queue['priorites']),
                         ['urgent', 'a_traiter', 'termine'])

    def test_the_intervenant_space_has_the_five_indicators_of_the_section_41(self):
        space = self._dashboard().intervenant_space(self.intervenant.partner_id)
        self.assertEqual(
            list(space['indicateurs']),
            ['appels_pertinents', 'candidatures_en_cours', 'missions_en_cours',
             'missions_terminees', 'note_moyenne'])

    def test_each_space_is_bounded_to_its_own_records(self):
        """« Chacun voit ce qui le concerne, jamais le graphe complet. »

        La démonstration se fait sur deux dossiers appartenant à deux
        personnes différentes. Sans bornage, les compteurs du second
        apparaîtraient dans l'espace du premier.
        """
        mine = self._new_mission()
        self._open_the_call(mine)

        # Le second dossier appartient à un autre client, et c'est lui qui le
        # soumet : `_open_the_call()` passe toujours par `client_user`, et
        # l'acteur `client` de cette instance-là est quelqu'un d'autre.
        other = self._new_mission(client_id=self.other_client.partner_id.id)
        self._do(other, 'mission_submit', self.other_client)
        self._do(other, 'mission_start_sourcing', self.manager)
        self._do(other, 'mission_open_applications', self.manager)

        client_space = self._dashboard().client_space(
            self.client_user.partner_id)
        self.assertEqual(client_space['indicateurs']['demandes'], 1)

        # Assertion positive de l'autre côté : le second dossier existe bien,
        # et il compte pour son propre client. Sans elle, un compteur cassé
        # renvoyant zéro partout ferait passer le test.
        other_space = self._dashboard().client_space(
            self.other_client.partner_id)
        self.assertEqual(other_space['indicateurs']['demandes'], 1)

        # Le responsable, lui, voit les deux.
        queue = self._dashboard().manager_queue()
        self.assertGreaterEqual(queue['indicateurs']['appels_actifs'], 2)

    def test_the_candidate_space_carries_a_status_and_no_priority_queue(self):
        """§18 - le candidat externe a un suivi, pas une file de travail.

        Les urgences d'un dossier appartiennent à ceux qui l'instruisent. Lui
        en montrer serait lui donner à lire l'organisation interne du cluster.
        """
        mission = self._new_mission()
        self._open_the_call(mission)
        application = self._apply(self._new_application(mission))

        space = self._dashboard().candidate_space(self.intervenant.partner_id)
        self.assertEqual(space['indicateurs']['candidatures'], 1)
        self.assertEqual(space['indicateurs']['en_cours'], 1)
        self.assertNotIn('priorites', space)
        # La file « suivi » porte un lien cliquable : il doit mener quelque
        # part, et au bon dossier. Résolu contre le routing map, pas comparé
        # à une chaîne que ce test construirait lui-même.
        self._assert_route_resolves(
            space['suivi'][0]['url'],
            'portal_intervenants_candidature',
            application_id=application.id)

    def test_no_space_hands_a_recordset_to_the_template(self):
        """Règle 12 - la donnée réservée se filtre au modèle.

        Une file qui porterait l'enregistrement laisserait un gabarit afficher
        n'importe lequel de ses champs, budget et client compris. Les entrées
        sont donc des dictionnaires à clés fermées, et ce test le verrouille.
        """
        self._closed_mission()
        for board in (self._dashboard().manager_queue()['priorites'],
                      self._dashboard().client_space(
                          self.client_user.partner_id)['priorites']):
            entries = [e for bucket in board.values() for e in bucket]
            self.assertTrue(entries, "Aucune entrée à vérifier.")
            for entry in entries:
                self.assertEqual(
                    set(entry), {'libelle', 'reference', 'titre', 'url'},
                    "Une entrée de file porte autre chose que ses quatre clés.")

    #
    # §43 - la priorisation
    #

    def test_a_late_deliverable_is_urgent(self):
        from datetime import timedelta

        from odoo import fields as odoo_fields

        mission = self._new_mission()
        self._open_the_call(mission)
        self._select_the_application(self._new_application(mission))
        self._do(mission, 'mission_close_applications', self.manager)
        self._do(mission, 'mission_award', self.decideur, comment="Retenue.")
        self._validate_the_contract(mission)
        self._do(mission, 'mission_start', self.manager)

        self.env['opex.mission.deliverable'].create({
            'mission_id': mission.id,
            'name': "Rapport en retard",
            'deadline': odoo_fields.Date.context_today(self.Mission)
            - timedelta(days=3),
        })

        queue = self._dashboard().manager_queue()
        libelles = [item['libelle'] for item in queue['priorites']['urgent']]
        self.assertTrue(
            any("Livrable en retard" in libelle for libelle in libelles),
            "Un livrable dont l'échéance est passée n'est pas signalé urgent.")

    def test_a_deposited_application_is_to_be_processed(self):
        mission = self._new_mission()
        self._open_the_call(mission)
        self._apply(self._new_application(mission))

        queue = self._dashboard().manager_queue()
        libelles = [item['libelle'] for item in queue['priorites']['a_traiter']]
        self.assertTrue(
            any("Nouvelle candidature" in libelle for libelle in libelles))

    def test_a_new_application_is_not_a_task_for_the_client(self):
        """Le §43 est la file de celui qui instruit, pas de celui qui attend.

        Le client n'a rien à faire d'une candidature déposée : c'est le cluster
        qui la qualifie. L'y ranger lui donnerait une tâche qu'il ne peut pas
        exécuter.
        """
        mission = self._new_mission()
        self._open_the_call(mission)
        self._apply(self._new_application(mission))

        space = self._dashboard().client_space(self.client_user.partner_id)
        libelles = [item['libelle'] for item in space['priorites']['a_traiter']]
        self.assertFalse(
            any("Nouvelle candidature" in libelle for libelle in libelles))

    def test_a_closed_mission_lands_in_the_done_column(self):
        mission = self._closed_mission()
        space = self._dashboard().client_space(self.client_user.partner_id)
        libelles = [item['libelle'] for item in space['priorites']['termine']]
        self.assertIn("Contrat signé", libelles)
        self.assertTrue(mission)

    #
    # §34 - les trois listes de notifications
    #

    #: Les actions ajoutées par cette extension, et la transition qui les
    #: porte. Écrit ici plutôt que déduit de la configuration : un test qui
    #: se relit lui-même ne vérifie rien.
    EXPECTED_NOTIFICATIONS = [
        ('mission_notify_request_received', 'mission_submit'),
        ('mission_notify_staff_new_request', 'mission_submit'),
        ('mission_notify_qualified', 'mission_start_sourcing'),
        ('mission_notify_decision_due', 'mission_close_applications'),
        ('application_notify_applicant', 'application_apply'),
        ('application_notify_client', 'application_apply'),
        ('application_notify_staff', 'application_apply'),
        ('application_notify_shortlisted', 'application_shortlist'),
        ('application_notify_rejected', 'application_reject_applied'),
        ('application_notify_rejected', 'application_reject_screened'),
        ('application_notify_rejected', 'application_reject_shortlisted'),
        ('contract_notify_available', 'contract_send_to_sign'),
        ('deliverable_notify_client', 'deliverable_submit'),
        ('mission_notify_accepted', 'mission_accept_service'),
        ('mission_notify_to_close', 'mission_accept_service'),
        ('mission_notify_evaluation_due', 'mission_close'),
    ]

    def test_the_section_34_notifications_are_attached_to_transitions(self):
        """Aucune n'est un `message_post()` : toutes sont configurées."""
        Transition = self.env['opex.workflow.transition'].sudo()
        for action_code, transition_code in self.EXPECTED_NOTIFICATIONS:
            transitions = Transition.search(
                [('code', '=', transition_code)])
            self.assertTrue(
                transitions,
                "Transition « %s » introuvable." % transition_code)
            codes = {action.code
                     for transition in transitions
                     for action in transition.action_ids}
            self.assertIn(
                action_code, codes,
                "« %s » n'est plus rattachée à « %s »."
                % (action_code, transition_code))

    def test_no_business_method_posts_a_notification_by_hand(self):
        """Le §34 passe par la configuration, pas par du Python dispersé.

        On examine le **code** et non la prose : les docstrings et les
        commentaires parlent de notifications, et un test qui interdit un mot
        interdit aussi qu'on en parle. Leçon de l'Extension 7, règle 15.

        Les `message_post()` légitimes restants sont des comptes rendus posés
        sur le dossier - la facturation émise, les candidatures restées
        ouvertes -, pas des notifications à un rôle. Ils sont nommés ici, un
        par un : en ajouter un demande de passer par cette liste.
        """
        allowed = {
            'mission_contract.py',
            'mission_invoicing.py',
            'mission_operational.py',
            # IA-3 : l'avis de contrôle qualité. C'est un **compte rendu posé
            # sur le dossier**, pas une notification à un rôle — il n'a pas
            # de destinataire, il documente un passage du contrôle.
            #
            # Et il ne PEUT pas être une action `notify` : celles-ci se
            # déclenchent sur une transition, or tout l'objet du §12 est que
            # le contrôle ne franchit aucune transition. Une notification
            # configurée supposerait exactement la décision automatique que
            # l'extension existe pour interdire.
            'expert_qualification_review.py',
        }
        models_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'models')

        examined = 0
        for name in sorted(os.listdir(models_dir)):
            if not name.endswith('.py') or name in allowed:
                continue
            with open(os.path.join(models_dir, name), encoding='utf-8') as f:
                source = f.read()
            source = re.sub(r'("""|\'\'\')(?:.|\n)*?\1', '', source)
            source = re.sub(r'#[^\n]*', '', source)
            examined += 1
            self.assertNotIn(
                'message_post', source,
                "« %s » poste un message à la main : le §34 se règle par des "
                "actions `notify` sur les transitions." % name)

        self.assertGreaterEqual(
            examined, 10,
            "La boucle n'examine presque rien : le chemin des modèles est "
            "probablement faux, et ce test passerait au vert sans rien lire.")

    def test_the_client_is_notified_when_an_application_arrives(self):
        """§34, liste client - « candidature reçue ».

        La notification ne part que parce que le client est acteur de la
        candidature : `_partners_for_roles()` résout les acteurs de l'instance
        visée, et un rôle sans porteur ne notifie personne.
        """
        mission = self._new_mission()
        self._open_the_call(mission)
        application = self._apply(self._new_application(mission))

        messages = self.env['mail.message'].sudo().search([
            ('model', '=', 'opex.mission.application'),
            ('res_id', '=', application.id),
        ])
        addressed = messages.filtered(
            lambda m: self.client_user.partner_id in m.partner_ids)
        self.assertTrue(
            addressed,
            "Le client n'est destinataire d'aucun message sur la candidature "
            "déposée sur son propre appel.")

    def test_the_message_meant_for_the_client_is_a_note(self):
        """Un `mt_comment` part aussi aux followers.

        L'intervenant est follower de sa candidature. En `comment`, le message
        destiné au client lui partirait par email - un message qui ne le
        concerne pas, sur un dossier qui est le sien. Il est donc posté en
        note, et la cloche du portail le montre quand même au client :
        `_execute_notify()` passe toujours `partner_ids`, que la seconde source
        de la cloche lit.
        """
        note_subtype = self.env.ref('mail.mt_note')
        action = self.env['opex.workflow.action'].sudo().search(
            [('code', '=', 'application_notify_client')], limit=1)
        self.assertEqual(action.notify_subtype, 'note')

        mission = self._new_mission()
        self._open_the_call(mission)
        application = self._apply(self._new_application(mission))

        message = self.env['mail.message'].sudo().search([
            ('model', '=', 'opex.mission.application'),
            ('res_id', '=', application.id),
            ('partner_ids', 'in', self.client_user.partner_id.ids),
        ], limit=1)
        self.assertEqual(message.subtype_id, note_subtype)

    def test_the_applicant_is_notified_by_comment(self):
        """Ce que l'intéressé doit recevoir part en `comment`."""
        action = self.env['opex.workflow.action'].sudo().search(
            [('code', '=', 'application_notify_applicant')], limit=1)
        self.assertEqual(action.notify_subtype, 'comment')

    def test_the_client_actor_on_an_application_opens_no_transition(self):
        """Le client est acteur pour être notifié, pas pour agir.

        Aucune transition du workflow de la candidature n'est ouverte au rôle
        `client`. Ce test verrouille le critère : le jour où quelqu'un en
        ouvre une, la conversation a lieu.
        """
        role = self.env.ref('opex_intervenants.role_client')
        transitions = self.application_definition.sudo().transition_ids.filtered(
            lambda t: role in t.allowed_role_ids)
        self.assertFalse(
            transitions.mapped('code'),
            "Le rôle `client` a gagné une transition sur la candidature.")

    def test_the_client_still_cannot_read_the_application(self):
        """Acteur d'instance n'est pas droit de lecture.

        L'`ir.rule` borne les candidatures au portail à `partner_id =
        user.partner_id`. Un acteur ne la lève pas - et c'est ce que le §14
        demande.

        On lit un champ et on attend une AccessError : `exists()` n'applique
        aucune `ir.rule`.
        """
        mission = self._new_mission()
        self._open_the_call(mission)
        application = self._apply(self._new_application(mission))

        # Assertion positive : le candidat, lui, lit sa candidature.
        self.assertTrue(
            application.with_user(self.intervenant).workflow_stage_id)

        with self.assertRaises(AccessError):
            application.with_user(self.client_user).motivation

    #
    # La cloche du portail
    #

    def test_the_bell_scope_stays_cooperative(self):
        """`super()` d'abord, sinon les trois modules précédents disparaissent.

        Une surcharge qui ne relaie pas efface la précédente, sans erreur et
        sans trace. Le symptôme serait muet : les dossiers d'adhésion et les
        projets d'innovation quitteraient la cloche le jour de l'installation
        de ce module.
        """
        owned = self.client_user.partner_id.sudo()._opex_owned_record_ids()
        for model in ('opex.membership.file', 'opex.subscription',
                      'opex.innovation.project'):
            self.assertIn(
                model, owned,
                "« %s » a quitté le périmètre de la cloche : la surcharge de "
                "ce module n'appelle plus `super()`." % model)
        for model in ('opex.mission.request', 'opex.mission.application',
                      'opex.mission.deliverable', 'opex.mission.contract',
                      'opex.service.acceptance', 'opex.mission.evaluation'):
            self.assertIn(model, owned)

    def test_the_bell_sees_the_missions_of_both_sides(self):
        """Le client par `client_id`, l'intervenant par son affectation."""
        mission = self._closed_mission()

        client_owned = self.client_user.partner_id.sudo()._opex_owned_record_ids()
        self.assertIn(mission.id, client_owned['opex.mission.request'])

        expert_owned = self.intervenant.partner_id.sudo()._opex_owned_record_ids()
        self.assertIn(
            mission.id, expert_owned['opex.mission.request'],
            "L'intervenant ne voit pas dans sa cloche la mission qu'il exécute.")

    def test_every_model_of_the_scope_has_a_notification_url(self):
        """Une notification qu'on ne peut pas ouvrir n'aide personne.

        Chaque modèle ajouté au périmètre doit avoir sa destination. Le test
        se construit depuis le périmètre lui-même : ajouter un modèle sans son
        URL le fait rougir.
        """
        mission = self._closed_mission()
        partner = self.client_user.partner_id.sudo()
        owned = partner._opex_owned_record_ids()

        Message = self.env['mail.message'].sudo()
        for model in ('opex.mission.request', 'opex.mission.application',
                      'opex.mission.deliverable', 'opex.mission.contract',
                      'opex.service.acceptance', 'opex.mission.evaluation'):
            record_ids = owned.get(model)
            if not record_ids:
                continue
            message = Message.new({'model': model, 'res_id': record_ids[0]})
            url = partner._opex_notification_url(message)
            self.assertTrue(
                url.startswith('/my/'),
                "« %s » renvoie vers « %s », qui n'est pas un écran portail."
                % (model, url))
        self.assertTrue(mission)

    def test_an_application_notification_leads_where_the_reader_can_go(self):
        """Défaut trouvé au navigateur, et invisible aux tests d'alors.

        Le §34 fait prévenir le client qu'une candidature a été déposée sur son
        appel. Le message est posté sur la candidature, et le lien envoyait
        tout le monde vers `/my/candidatures/<id>` - un écran que l'`ir.rule`
        réserve au candidat. Le client cliquait, et tombait sur un 404.

        Le test précédent ne pouvait pas le voir : il vérifiait que l'URL
        commence par `/my/`, ce qui restait vrai. Celui-ci vérifie que le
        lecteur peut y aller.

        ⚠ Et il ne le vérifiait toujours pas. Écrit pour la branche client, il
        assertait les deux branches par comparaison de chaînes — donc il a
        figé l'URL fautive de la branche **candidat**, qui ne correspondait à
        aucune route. Les deux côtés de l'égalité étaient faux de la même
        façon. Les deux résolvent désormais contre le routing map.
        """
        mission = self._new_mission()
        self._open_the_call(mission)
        application = self._apply(self._new_application(mission))

        message = self.env['mail.message'].sudo().new({
            'model': 'opex.mission.application',
            'res_id': application.id,
        })

        # Le candidat va à sa candidature — et cette route existe.
        self._assert_route_resolves(
            self.intervenant.partner_id.sudo()._opex_notification_url(message),
            'portal_intervenants_candidature',
            application_id=application.id)

        # Le client va à sa mission, pas au dossier du candidat.
        self._assert_route_resolves(
            self.client_user.partner_id.sudo()._opex_notification_url(message),
            'portal_intervenants_mission_detail',
            mission_id=mission.id)

    #
    # Le contrat de /my/counters
    #

    def test_every_counter_key_has_exactly_one_tile(self):
        """Les deux moitiés du contrat, vérifiées ensemble.

        Un compteur renvoyé sans nœud DOM correspondant fait lever
        `portal_home_counters.js`, ce qui rejette le `Promise.all` et tue tout
        le JavaScript de l'accueil - pour tous les utilisateurs, pas seulement
        pour la tuile fautive. Et deux tuiles partageant une clé laisseraient
        la seconde masquée : `querySelector()` ne renvoie que le premier nœud.

        Le test lit les deux sources - les clés que les controllers renvoient,
        les `placeholder_count` que les gabarits posent - et exige une
        bijection.
        """
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        declared = []
        views_dir = os.path.join(root, 'views')
        for name in sorted(os.listdir(views_dir)):
            if not name.endswith('.xml'):
                continue
            with open(os.path.join(views_dir, name), encoding='utf-8') as f:
                content = f.read()
            declared += re.findall(
                r"""t-set="placeholder_count"\s+t-value="'([^']+)'""", content)

        served = []
        controllers_dir = os.path.join(root, 'controllers')
        for name in sorted(os.listdir(controllers_dir)):
            if not name.endswith('.py'):
                continue
            with open(os.path.join(controllers_dir, name), encoding='utf-8') as f:
                source = f.read()
            source = re.sub(r'("""|\'\'\')(?:.|\n)*?\1', '', source)
            served += re.findall(r"""if '([a-z_]+_count)' in counters""", source)

        self.assertGreaterEqual(
            len(declared), 4,
            "Aucun `placeholder_count` trouvé : le chemin des vues est "
            "probablement faux, et ce test passerait au vert sans rien lire.")
        self.assertEqual(
            sorted(declared), sorted(set(declared)),
            "Deux tuiles partagent un `placeholder_count` : la seconde "
            "restera masquée.")
        self.assertEqual(
            sorted(set(declared)), sorted(set(served)),
            "Les clés servies par les controllers et celles posées par les "
            "gabarits ne se correspondent plus.")


@tagged('post_install', '-at_install')
class TestDashboardHttp(HttpCase):
    """Les deux écrans neufs, par de vraies requêtes HTTP.

    Ce que ces tests ne prouvent pas : `url_open()` lit le HTML rendu par le
    serveur. Il passerait au vert pendant qu'une exception JavaScript vide la
    page dans un vrai navigateur. Le démasquage des tuiles de `/my` se vérifie
    à l'écran, console ouverte - c'est une partie du protocole manuel.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.expert = new_test_user(
            cls.env, login='db_expert', password='db_expert',
            groups='base.group_portal')
        cls.manager = new_test_user(
            cls.env, login='db_manager', password='db_manager',
            groups='base.group_user,opex_intervenants.group_mission_manager')

    def test_the_intervenant_space_renders(self):
        self.authenticate('db_expert', 'db_expert')
        response = self.url_open('/my/intervenant')
        self.assertEqual(response.status_code, 200)
        body = response.text
        # Assertion positive d'abord : la page est bien celle qu'on croit.
        self.assertIn("Mon espace intervenant", body)
        self.assertIn("Appels pertinents", body)

    def test_the_work_queue_is_closed_to_the_portal(self):
        """Le contrôle vit dans la route, pas dans l'affichage de la tuile."""
        self.authenticate('db_expert', 'db_expert')
        response = self.url_open('/staff/queue')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            "Smart Work Queue", response.text,
            "Un compte portail atteint la file de travail du cluster.")

    def test_the_work_queue_renders_for_the_staff(self):
        self.authenticate('db_manager', 'db_manager')
        response = self.url_open('/staff/queue')
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn("Smart Work Queue", body)
        self.assertIn("Demandes à traiter", body)
        self.assertIn("Contrats en attente", body)

    def test_the_counters_route_answers_without_breaking(self):
        """`/my/counters` renvoie exactement les clés demandées.

        Une clé de plus, et le JavaScript de l'accueil tombe pour tout le
        monde. Le test demande les quatre clés du module et vérifie qu'il n'en
        revient pas une cinquième.
        """
        self.authenticate('db_expert', 'db_expert')
        asked = [
            'intervenants_mission_count',
            'intervenants_candidature_count',
            'intervenants_expertise_count',
            'intervenants_espace_count',
        ]
        response = self.url_open(
            '/my/counters',
            data='{"jsonrpc":"2.0","method":"call","params":{"counters":%s}}'
                 % str(asked).replace("'", '"'),
            headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 200)
        payload = response.json().get('result', {})
        self.assertEqual(
            sorted(payload), sorted(asked),
            "`/my/counters` renvoie autre chose que ce qui lui est demandé.")
