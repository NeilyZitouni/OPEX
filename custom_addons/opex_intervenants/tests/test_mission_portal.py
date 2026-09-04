import json
import re
from datetime import timedelta

from odoo import fields
from odoo.tests.common import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestMissionPortal(HttpCase):
    """Extension 2 — la demande client, en cinq écrans.

    Les routes sont exercées par de **vraies requêtes HTTP**, sous un vrai
    compte portail. Un test qui appellerait les méthodes du controller
    directement sauterait l'authentification, les `ir.rule` et le rendu —
    c'est-à-dire tout ce qui casse en production.

    Ce que ces tests **ne** prouvent pas : `url_open()` lit le HTML rendu par
    le serveur. Il voit les tuiles, leurs classes et leurs liens, et passe au
    vert pendant qu'une exception JavaScript vide la page dans un vrai
    navigateur. Le démasquage des tuiles de `/my` se vérifie à l'écran,
    console ouverte — c'est le §4 du protocole de test manuel.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Mission = cls.env['opex.mission.request']

        cls.client_user = new_test_user(
            cls.env, login='mp_client', password='mp_client',
            groups='base.group_portal')
        cls.other_client = new_test_user(
            cls.env, login='mp_other', password='mp_other',
            groups='base.group_portal')
        cls.secretariat = new_test_user(
            cls.env, login='mp_secr', password='mp_secr',
            groups='base.group_user,opex_membership.group_secretariat')

        cls.mission_type = cls.env.ref('opex_intervenants.mission_type_audit')
        cls.domaine = cls.env.ref(
            'opex_intervenants.mission_domain_cybersecurite')
        cls.competence = cls.env['opex.innovation.competence'].create({
            'name': "Sécurité des systèmes d'information", 'code': 'mp_ssi'})

    # ------------------------------------------------------------
    # Outils
    # ------------------------------------------------------------

    def _login(self, login='mp_client'):
        self.authenticate(login, login)

    def _csrf(self):
        """Jeton CSRF lu là où le navigateur le lirait.

        Il est lié à la session HTTP, pas au registre : on le prend dans le
        script d'amorçage d'une page réellement rendue.
        """
        page = self.url_open('/my').text
        match = re.search(r'csrf_token: "([^"]+)"', page)
        self.assertTrue(match, "Jeton CSRF introuvable dans la page")
        return match.group(1)

    def _post(self, url, data=None):
        payload = {'csrf_token': self._csrf()}
        payload.update(data or {})
        return self.url_open(url, data=payload)

    @staticmethod
    def _flat(text):
        """Le HTML rendu, blancs normalisés.

        Une phrase du gabarit est coupée par l'indentation de la source :
        la chercher telle qu'on la lit à l'écran demande d'aplatir les blancs,
        sinon le test échoue sur une question de mise en forme.
        """
        return " ".join(text.split())

    def _mission_of(self, user):
        return self.Mission.sudo().search(
            [('client_id', '=', user.partner_id.id)], order='id desc', limit=1)

    def _create_through_screen_one(self, title="Audit cybersécurité"):
        return self._post('/my/missions/new', {
            'title': title,
            'mission_type_id': str(self.mission_type.id),
            'description': "Audit du SI industriel.",
            'objectifs': "Cartographier les vulnérabilités.",
        })

    def _fill_screen_two(self, mission):
        return self._post('/my/missions/%s/profil' % mission.id, {
            'domaine_id': str(self.domaine.id),
            'skill_ids': str(self.competence.id),
            'annees_experience_min': '5',
            'niveau_experience': 'senior',
        })

    #
    # §7 — LES CINQ ÉCRANS
    #

    def test_the_five_screens_are_five_screens(self):
        """« Cinq écrans courts, jamais un formulaire monolithique. »

        Chacun se rend, et chacun ne demande que ce que le §7 lui attribue.
        """
        self._login()
        response = self.url_open('/my/missions/new')
        self.assertEqual(response.status_code, 200)
        body = self._flat(response.text)
        # Assertion positive d'abord : la page est bien rendue.
        self.assertIn("Créer une demande de mission", body)
        self.assertIn("Titre de la mission", body)
        # …et elle ne contient pas les écrans suivants.
        self.assertNotIn("Budget estimatif", body)
        self.assertNotIn("Compétences recherchées", body)

        self._create_through_screen_one()
        mission = self._mission_of(self.client_user)

        ecrans = [
            ('/my/missions/%s/profil', "Compétences recherchées", "Budget estimatif"),
            ('/my/missions/%s/organisation', "Mode d'intervention", "Budget estimatif"),
            ('/my/missions/%s/budget', "Budget estimatif", "Compétences recherchées"),
            ('/my/missions/%s/documents', "Ajouter une pièce", "Budget estimatif"),
        ]
        for url, present, absent in ecrans:
            page = self.url_open(url % mission.id)
            self.assertEqual(page.status_code, 200, url)
            flat = self._flat(page.text)
            self.assertIn(present, flat, url)
            self.assertNotIn(absent, flat, url)

    def test_the_step_bar_shows_five_pills(self):
        """Cinq pastilles, pas six : le récapitulatif n'est pas un écran de
        saisie."""
        self._login()
        self._create_through_screen_one()
        mission = self._mission_of(self.client_user)
        body = self._flat(self.url_open(
            '/my/missions/%s/profil' % mission.id).text)
        for label in ("Informations générales", "Profil recherché",
                      "Organisation", "Budget", "Documents"):
            self.assertIn(label, body)

    #
    # LE BROUILLON AUTO-SAUVEGARDÉ
    #

    def test_the_request_is_created_on_the_first_screen(self):
        """Le brouillon commence dès la validation du premier écran.

        Le client n'a jamais à « tout finir d'un coup ».
        """
        self._login()
        self.assertFalse(self._mission_of(self.client_user))
        self._create_through_screen_one()

        mission = self._mission_of(self.client_user)
        self.assertTrue(mission)
        self.assertEqual(mission.title, "Audit cybersécurité")
        self.assertEqual(mission.workflow_stage_id.code, 'draft')
        self.assertTrue(mission.name.startswith('MIS-'))

    def test_each_screen_writes_only_its_own_fields(self):
        """Écriture partielle : quitter en cours de route ne perd que ce qui
        n'a pas été envoyé."""
        self._login()
        self._create_through_screen_one()
        mission = self._mission_of(self.client_user)

        self._fill_screen_two(mission)
        mission.invalidate_recordset()
        self.assertEqual(mission.domaine_id, self.domaine)
        self.assertEqual(mission.skill_ids, self.competence)
        self.assertEqual(mission.annees_experience_min, 5)
        # L'écran 2 n'a pas touché au budget : il ne le connaît pas.
        self.assertEqual(mission.budget_estimatif, 0.0)

        self._post('/my/missions/%s/budget' % mission.id, {
            'budget_estimatif': '250 000,50',
            'type_remuneration': 'forfait',
            'conditions_financieres': "Paiement à 30 jours.",
        })
        mission.invalidate_recordset()
        # Virgule décimale et espace d'affichage acceptés : un `float()` nu
        # aurait rendu une erreur serveur là où le client attend un formulaire.
        self.assertEqual(mission.budget_estimatif, 250000.50)
        self.assertEqual(mission.type_remuneration, 'forfait')
        # …et le budget n'a pas effacé le profil.
        self.assertEqual(mission.domaine_id, self.domaine)

    def test_a_second_visit_resumes_the_draft(self):
        """La reprise, et son message."""
        self._login()
        self._create_through_screen_one()
        mission = self._mission_of(self.client_user)

        body = self._flat(self.url_open('/my/missions').text)
        self.assertIn("Vous avez une demande en cours de saisie", body)
        self.assertIn("Audit cybersécurité", body)

        # Repasser par l'écran 1 ne crée pas un second dossier.
        self._create_through_screen_one(title="Titre corrigé")
        self.assertEqual(len(self.Mission.sudo().search(
            [('client_id', '=', self.client_user.partner_id.id)])), 1)
        mission.invalidate_recordset()
        self.assertEqual(mission.title, "Titre corrigé")

    def test_the_multi_select_keeps_every_checked_box(self):
        """`getlist()` et non `post.get()`.

        Un formulaire qui coche trois cases du même nom n'en transmet qu'une à
        `post.get()` : le client verrait sa sélection réduite au dernier choix,
        sans qu'aucune erreur ne le signale.
        """
        autre = self.env['opex.innovation.competence'].create(
            {'name': "Réseaux", 'code': 'mp_reseaux'})
        self._login()
        self._create_through_screen_one()
        mission = self._mission_of(self.client_user)

        self._post('/my/missions/%s/profil' % mission.id, {
            'domaine_id': str(self.domaine.id),
            'skill_ids': [str(self.competence.id), str(autre.id)],
        })
        mission.invalidate_recordset()
        self.assertEqual(len(mission.skill_ids), 2)

    #
    # LE VERROU SUR `client_id`
    #

    def test_the_client_cannot_file_on_behalf_of_another(self):
        """Le `create()` réécrit `client_id` côté serveur.

        Ne pas afficher le champ ne protège de rien : une requête forgée n'a
        jamais vu le formulaire. On la forge donc.
        """
        self._login()
        self._post('/my/missions/new', {
            'title': "Demande forgée",
            'mission_type_id': str(self.mission_type.id),
            'description': "x",
            'objectifs': "y",
            'client_id': str(self.other_client.partner_id.id),
        })
        mission = self.Mission.sudo().search([('title', '=', "Demande forgée")])
        self.assertEqual(len(mission), 1)
        self.assertEqual(
            mission.client_id, self.client_user.partner_id,
            "Un compte portail a déposé une demande au nom d'un autre.")

    def test_a_client_cannot_reach_another_clients_request(self):
        """L'`ir.rule` scopée, éprouvée par l'URL.

        Assertion positive d'abord — le propriétaire voit sa demande — puis la
        négative, qui ne vaudrait rien seule : sans elle, une redirection vers
        une page d'erreur passerait aussi.
        """
        self._login()
        self._create_through_screen_one(title="Dossier confidentiel")
        mission = self._mission_of(self.client_user)

        mine = self.url_open('/my/missions/%s' % mission.id)
        self.assertEqual(mine.status_code, 200)
        self.assertIn("Dossier confidentiel", mine.text)

        self._login('mp_other')
        stolen = self.url_open('/my/missions/%s' % mission.id)
        self.assertEqual(stolen.status_code, 200)
        self.assertNotIn(
            "Dossier confidentiel", stolen.text,
            "Le titre d'un dossier d'autrui apparaît dans le HTML rendu.")

    def test_a_client_cannot_write_into_another_clients_request(self):
        self._login()
        self._create_through_screen_one()
        mission = self._mission_of(self.client_user)

        self._login('mp_other')
        self._post('/my/missions/%s/budget' % mission.id,
                   {'budget_estimatif': '999999'})
        mission.invalidate_recordset()
        self.assertEqual(mission.budget_estimatif, 0.0)

    #
    # §8 — LA DEMANDE NE DEVIENT PAS PUBLIQUE
    #

    def test_submission_goes_through_the_engine(self):
        """La soumission est une **transition**, pas un booléen.

        Le controller ne décide pas que la demande peut partir : il le demande
        au moteur, qui applique le rôle et la condition configurés.
        """
        self._login()
        self._create_through_screen_one()
        mission = self._mission_of(self.client_user)
        self._fill_screen_two(mission)

        self._post('/my/missions/%s/recap' % mission.id, {'confirm': '1'})
        mission.invalidate_recordset()
        self.assertEqual(mission.workflow_stage_id.code, 'qualified')

    def test_submission_is_refused_without_confirmation(self):
        self._login()
        self._create_through_screen_one()
        mission = self._mission_of(self.client_user)
        self._fill_screen_two(mission)

        response = self._post('/my/missions/%s/recap' % mission.id, {})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Cochez la case", self._flat(response.text))
        mission.invalidate_recordset()
        self.assertEqual(mission.workflow_stage_id.code, 'draft')

    def test_submission_is_blocked_while_the_file_is_incomplete(self):
        """La condition du moteur, rendue lisible par la page.

        Le client n'a pas rempli l'écran 2 : la règle configurée bloque, et le
        motif s'affiche au lieu d'une erreur serveur.
        """
        self._login()
        self._create_through_screen_one()
        mission = self._mission_of(self.client_user)

        response = self._post(
            '/my/missions/%s/recap' % mission.id, {'confirm': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertIn("au moins une compétence", self._flat(response.text))
        mission.invalidate_recordset()
        self.assertEqual(mission.workflow_stage_id.code, 'draft')

    def test_the_request_does_not_become_public_by_itself(self):
        """§8, le cœur de l'extension.

        Une demande soumise **n'est pas publiée**. `is_published` reste faux,
        et il le reste parce qu'il est calculé depuis l'étape : aucun écran ne
        peut le cocher.
        """
        self._login()
        self._create_through_screen_one()
        mission = self._mission_of(self.client_user)
        self._fill_screen_two(mission)
        self._post('/my/missions/%s/recap' % mission.id, {'confirm': '1'})

        mission.invalidate_recordset()
        self.assertEqual(mission.workflow_stage_id.code, 'qualified')
        self.assertFalse(
            mission.is_published,
            "Une demande soumise par le client est devenue publique sans "
            "qualification du cluster.")

    def test_the_recap_warns_that_publication_is_not_automatic(self):
        """Et le client le lit **avant** de cliquer, pas après."""
        self._login()
        self._create_through_screen_one()
        mission = self._mission_of(self.client_user)
        body = self._flat(self.url_open(
            '/my/missions/%s/recap' % mission.id).text)
        self.assertIn("ne devient pas publique automatiquement", body)

    def test_a_submitted_request_is_no_longer_editable(self):
        """Assertion positive puis négative : éditable avant, plus après."""
        self._login()
        self._create_through_screen_one()
        mission = self._mission_of(self.client_user)
        self._fill_screen_two(mission)

        avant = self.url_open('/my/missions/%s/budget' % mission.id)
        self.assertIn("Budget estimatif", self._flat(avant.text))

        self._post('/my/missions/%s/recap' % mission.id, {'confirm': '1'})
        apres = self.url_open('/my/missions/%s/budget' % mission.id)
        # Redirigé vers la liste : l'écran de saisie n'est plus servi.
        self.assertNotIn("Modalités financières", self._flat(apres.text))

    #
    # LA BOUCLE DU §8 — LE DOSSIER RENVOYÉ
    #

    def test_a_returned_request_shows_its_reason_and_becomes_editable_again(self):
        """Le retour au client, vu du portail.

        Le dossier renvoyé est à l'étape `draft`, comme une saisie en cours,
        mais ce n'est pas la même chose : « Créer une demande » ne doit pas le
        reprendre. C'est `is_first_draft()` qui les sépare, sur l'historique.
        """
        self._login()
        self._create_through_screen_one()
        mission = self._mission_of(self.client_user)
        self._fill_screen_two(mission)
        self._post('/my/missions/%s/recap' % mission.id, {'confirm': '1'})

        # Le secrétariat renvoie le dossier, avec un motif.
        transition = mission.workflow_definition_id.sudo().transition_ids\
            .filtered(lambda t: t.code == 'mission_request_complement')
        mission.with_user(self.secretariat).sudo().workflow_do_transition(
            transition, comment="Le périmètre technique n'est pas décrit.")
        mission.invalidate_recordset()
        self.assertEqual(mission.workflow_stage_id.code, 'draft')

        page = self._flat(self.url_open('/my/missions/%s' % mission.id).text)
        self.assertIn("Le cluster demande un complément", page)
        # Sans apostrophe dans l'extrait cherché : le motif arrive par
        # `t-out`, donc **échappé** — « n'est » devient « n&#39;est ». Le texte
        # statique du gabarit, lui, ne l'est pas. Une assertion sur une valeur
        # dynamique ne doit porter que sur des caractères que QWeb ne réécrit
        # pas, sinon elle échoue sur l'échappement et non sur le contenu.
        self.assertIn("périmètre technique", page)

        # Le client réécrit, ce qui prouve que l'`ir.rule` lui a rendu la main.
        self._post('/my/missions/%s/budget' % mission.id,
                   {'budget_estimatif': '120000'})
        mission.invalidate_recordset()
        self.assertEqual(mission.budget_estimatif, 120000.0)

        # …et « Créer une demande » n'a pas repris ce dossier-là.
        self.assertFalse(mission.is_first_draft())
        liste = self._flat(self.url_open('/my/missions').text)
        self.assertIn("Action requise", liste)
        self.assertNotIn("Vous avez une demande en cours de saisie", liste)

    def test_only_the_last_reason_is_shown(self):
        """Deux retours successifs : c'est le second motif qui s'affiche.

        Le motif est lu dans l'historique en compréhension. Avec `mapped()`,
        le second passage par la même étape serait dédupliqué et on afficherait
        le premier motif — déjà traité.
        """
        self._login()
        self._create_through_screen_one()
        mission = self._mission_of(self.client_user)
        self._fill_screen_two(mission)

        submit = mission.workflow_definition_id.sudo().transition_ids.filtered(
            lambda t: t.code == 'mission_submit')
        complement = mission.workflow_definition_id.sudo().transition_ids\
            .filtered(lambda t: t.code == 'mission_request_complement')

        for motif in ("Premier motif à corriger.", "Second motif à corriger."):
            mission.with_user(self.client_user).sudo()\
                .workflow_do_transition(submit)
            mission.with_user(self.secretariat).sudo()\
                .workflow_do_transition(complement, comment=motif)
            mission.invalidate_recordset()

        self.assertEqual(mission.complement_reason(), "Second motif à corriger.")

    #
    # §6 — LE TABLEAU DE BORD
    #

    def test_the_dashboard_counts_the_four_indicators(self):
        self._login()
        self._create_through_screen_one()
        mission = self._mission_of(self.client_user)
        self._fill_screen_two(mission)

        dashboard = self.Mission.client_dashboard(self.client_user.partner_id)
        self.assertEqual(dashboard['demandes'], 1)
        self.assertEqual(dashboard['appels'], 0)
        self.assertEqual(dashboard['en_cours'], 0)
        self.assertEqual(dashboard['terminees'], 0)

        # Le dossier devient un appel publié : l'indicateur suit l'étape,
        # sans qu'aucun compteur n'ait été écrit nulle part.
        self._post('/my/missions/%s/recap' % mission.id, {'confirm': '1'})
        manager = new_test_user(
            self.env, login='mp_manager', password='mp_manager',
            groups='base.group_user,opex_intervenants.group_mission_manager')
        mission.sudo().write({
            'date_limite_candidature':
                fields.Date.context_today(self.Mission) + timedelta(days=30),
        })
        publish = mission.workflow_definition_id.sudo().transition_ids.filtered(
            lambda t: t.code == 'mission_start_sourcing')
        mission.with_user(manager).sudo().workflow_do_transition(publish)
        mission.invalidate_recordset()

        dashboard = self.Mission.client_dashboard(self.client_user.partner_id)
        self.assertEqual(dashboard['demandes'], 1)
        self.assertEqual(dashboard['appels'], 1)

    def test_the_dashboard_page_renders_the_four_labels(self):
        self._login()
        response = self.url_open('/my/missions')
        self.assertEqual(response.status_code, 200)
        body = self._flat(response.text)
        # Assertion positive : la page est bien la bonne.
        self.assertIn("OPEX Intervenants — mes demandes", body)
        for label in ("Mes demandes", "Appels en cours",
                      "Missions en cours", "Missions terminées"):
            self.assertIn(label, body)
        self.assertIn("Créer une demande de mission", body)

    def test_the_dashboard_only_counts_its_own_client(self):
        self._login()
        self._create_through_screen_one()
        self._login('mp_other')
        dashboard = self.Mission.client_dashboard(self.other_client.partner_id)
        self.assertEqual(dashboard['demandes'], 0)

    #
    # LE CONTRAT DE `/my/counters`
    #

    def _counters(self, demandes):
        """Appelle réellement `/my/counters`, comme le fait le navigateur."""
        response = self.url_open(
            '/my/counters',
            data=json.dumps({'params': {'counters': demandes}}),
            headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 200)
        return response.json().get('result', {})

    def test_the_counter_is_declared_on_both_sides(self):
        """Les deux, ou aucun — éprouvé sur la vraie route.

        Une clé renvoyée sans nœud DOM correspondant fait lever
        `portal_home_counters.js`, ce qui rejette le `Promise.all` et tue
        **tout** le JavaScript de l'accueil, pour tous les utilisateurs.
        """
        self._login()
        self._create_through_screen_one()

        # Côté gabarit : le nœud existe.
        self.assertIn("intervenants_mission_count", self.url_open('/my').text)

        # Côté controller : la clé est servie quand elle est demandée…
        servis = self._counters(['intervenants_mission_count'])
        self.assertEqual(servis.get('intervenants_mission_count'), 1)

        # …et **jamais** quand elle ne l'est pas.
        muets = self._counters(['membership_file_count'])
        self.assertNotIn(
            'intervenants_mission_count', muets,
            "Une clé non demandée est renvoyée : le JavaScript de l'accueil "
            "lèvera sur un nœud DOM introuvable.")

    def test_the_counter_name_is_unique_across_modules(self):
        """Un compteur, une tuile, un domaine.

        `portal_home_counters.js` résout chaque compteur par `querySelector()`,
        qui ne renvoie que le **premier** nœud : deux tuiles partageant une clé
        laisseraient la seconde masquée jusqu'au rechargement suivant.
        """
        home = self.env.ref('portal.portal_my_home')
        tuiles = self.env['ir.ui.view'].sudo().search(
            [('inherit_id', '=', home.id)])
        porteuses = tuiles.filtered(
            lambda v: 'intervenants_mission_count' in (v.arch or ''))
        self.assertEqual(
            len(porteuses), 1,
            "Le compteur est déclaré par %s tuiles : %s"
            % (len(porteuses), porteuses.mapped('key')))

    def test_the_tile_declares_config_card(self):
        """`config_card` : la tuile doit exister pour celui qui n'a rien déposé.

        Sans lui, `portal.portal_docs_entry` la met en `d-none` tant que le
        compteur est nul — elle disparaîtrait exactement pour celui qui en a le
        plus besoin, et il n'aurait aucun chemin vers « Créer une demande ».

        Assertion sur la **source** du gabarit et non sur le HTML rendu :
        `d-none` apparaît dans la page pour d'autres raisons, et un test qui le
        chercherait dans le corps entier mesurerait la tuile du voisin. Que la
        tuile soit réellement **visible** se vérifie dans un navigateur — c'est
        le §4 du protocole de test manuel, et aucune requête HTTP ne le
        remplace.
        """
        tuile = self.env.ref('opex_intervenants.portal_my_home_mission')
        self.assertIn('config_card', tuile.arch)

        self._login('mp_other')
        body = self.url_open('/my').text
        self.assertIn("OPEX Intervenants", body)
        self.assertIn('href="/my/missions"', body)

    #
    # LES COLLISIONS DE L'ARBRE `CustomerPortal`
    #

    def test_no_route_of_the_other_modules_disappeared(self):
        """Le routing map réel, seul juge des collisions.

        `_generate_routing_rules()` fusionne toutes les classes feuilles d'un
        même arbre en une seule : pour un nom donné, il n'existe qu'un
        exemplaire. Une méthode homonyme fait disparaître les URL d'un autre
        module — **sans erreur, ni au chargement ni au runtime**. Aucun test
        unitaire ne l'attrape ; seul le routing map le montre.
        """
        router = self.env['ir.http'].routing_map()
        routes = {str(rule.rule) for rule in router.iter_rules()}

        attendues = [
            # Les miennes.
            '/my/missions', '/my/missions/new',
            '/my/missions/<int:mission_id>',
            '/my/missions/<int:mission_id>/profil',
            '/my/missions/<int:mission_id>/organisation',
            '/my/missions/<int:mission_id>/budget',
            '/my/missions/<int:mission_id>/documents',
            '/my/missions/<int:mission_id>/recap',
            # Celles des voisins, qui doivent avoir survécu.
            '/my/innovation', '/my/innovation/new',
            '/my/innovation/missions',
            '/my/membership/new',
            '/my/notifications',
        ]
        manquantes = [route for route in attendues if route not in routes]
        self.assertFalse(
            manquantes,
            "Routes absentes du routing map : %s" % manquantes)

    def test_our_controller_names_are_all_prefixed(self):
        """Ce que ce module définit sans passer par `super()` est préfixé.

        Le hook natif `_prepare_home_portal_values` garde son nom : il relaie
        `super()` et s'exécute donc en chaîne avec ceux des autres modules.
        C'est la ligne de partage.
        """
        from odoo.addons.opex_intervenants.controllers.portal import (
            MissionRequestPortal)

        cooperatifs = {'_prepare_home_portal_values'}
        propres = {
            name for name in vars(MissionRequestPortal)
            if not name.startswith('__')
        }
        for name in propres - cooperatifs:
            self.assertTrue(
                name.startswith(('portal_intervenants_', '_intervenants_',
                                 '_INTERVENANTS_')),
                "« %s » n'est pas préfixé : il écrasera ou sera écrasé par "
                "l'homonyme d'un autre module de l'arbre CustomerPortal."
                % name)
