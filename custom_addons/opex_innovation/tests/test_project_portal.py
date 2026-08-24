import re

from odoo.tests.common import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestProjectPortal(HttpCase):
    """Extension 11 — le parcours de dépôt en cinq écrans.

    Les routes sont exercées par de vraies requêtes HTTP, sous un vrai compte
    portail. Un test qui appellerait les méthodes du controller directement
    sauterait l'authentification, les `ir.rule` et le rendu — c'est-à-dire tout
    ce qui casse en production.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.member = new_test_user(
            cls.env, login='pp_member', password='pp_member',
            groups='base.group_portal')
        cls.member.partner_id.sudo().write({'is_member': True})

        cls.outsider = new_test_user(
            cls.env, login='pp_outsider', password='pp_outsider',
            groups='base.group_portal')
        cls.outsider.partner_id.sudo().write({'is_member': True})

        cls.Project = cls.env['opex.innovation.project']

    def _login(self, login='pp_member'):
        self.authenticate(login, login)

    def _csrf(self):
        """Jeton CSRF extrait d'une page réellement rendue.

        `ir.http._get_csrf_token()` n'existe pas : le jeton est lié à la
        session HTTP, pas au registre. Odoo l'écrit dans le script d'amorçage
        de chaque page ; on le lit là où le navigateur le lirait.
        """
        page = self.url_open('/my').text
        match = re.search(r'csrf_token: "([^"]+)"', page)
        self.assertTrue(match, "Jeton CSRF introuvable dans la page")
        return match.group(1)

    @staticmethod
    def _flat(text):
        """Le HTML rendu, espaces normalisés.

        Une phrase du gabarit est coupée par les retours à la ligne et
        l'indentation de la source : « ne seront plus
     modifiables ».
        Chercher la phrase telle qu'on la lit à l'écran demande donc d'aplatir
        les blancs — sinon le test échoue sur une question de mise en forme et
        non de contenu.
        """
        return " ".join(text.split())

    def _post(self, url, data=None):
        payload = {'csrf_token': self._csrf()}
        payload.update(data or {})
        return self.url_open(url, data=payload)

    def _project_of(self, user):
        return self.Project.sudo().search(
            [('partner_id', '=', user.partner_id.id)], order='id desc', limit=1)

    # ------------------------------------------------------------
    # Section 4 — Mes projets
    # ------------------------------------------------------------

    def test_my_projects_shows_the_section_35_card(self):
        """⚠ Réécrit à l'Extension 19.

        Cette page listait les projets dans un tableau à cinq colonnes
        (« Projet, Catégorie, État, Dernière mise à jour, Action »). La
        section 35 ne décrit pas un tableau : elle décrit une **carte** qui
        répond à la seule question que le porteur se pose — où en est mon
        projet, et qu'attend-on de moi ?

        Le test suit le changement d'interface au lieu de le contraindre : ce
        qu'il garde, c'est la règle d'or, pas la mise en page.
        """
        self._login()
        self._post('/my/innovation/new', {'name': "Smart Factory"})
        response = self.url_open('/my/innovation')
        self.assertEqual(response.status_code, 200)
        body = response.text

        self.assertIn("Smart Factory", body)
        # Les sept jalons de la section 35.
        for jalon in ("Déposé", "Contrôle terminé", "Évaluation", "Décision",
                      "Accompagnement", "Financement", "Industrialisation"):
            self.assertIn(jalon, body)
        self.assertIn("Consulter mon projet", body)

    def test_my_projects_shows_the_user_label_not_the_stage_code(self):
        """Section 35 : le porteur ne lit jamais un code technique."""
        self._login()
        self._post('/my/innovation/new', {'name': "Smart Factory"})

        body = self.url_open('/my/innovation').text
        # Positive d'abord : la carte est bien rendue.
        self.assertIn("Smart Factory", body)
        self.assertIn("Compléter mon dossier", body)
        # Et aucun code d'étape n'y figure.
        self.assertNotIn(">draft<", body)
        self.assertNotIn("complement_requested", body)

    def test_a_non_member_cannot_start_a_project(self):
        visitor = new_test_user(
            self.env, login='pp_visitor', password='pp_visitor',
            groups='base.group_portal')
        self.authenticate('pp_visitor', 'pp_visitor')
        body = self.url_open('/my/innovation/new').text
        self.assertIn("adhésion", body.lower())
        self.assertFalse(self._project_of(visitor))

    # ------------------------------------------------------------
    # Le brouillon automatique
    # ------------------------------------------------------------

    def test_the_project_is_created_on_the_first_screen(self):
        self._login()
        self.assertFalse(self._project_of(self.member))

        self._post('/my/innovation/new', {
            'name': "Smart Factory",
            'resume': "Une usine pilotée par l'IA.",
            'secteur': 'industrie',
        })

        project = self._project_of(self.member)
        self.assertTrue(project)
        self.assertEqual(project.name, "Smart Factory")
        self.assertEqual(project.workflow_stage_id.code, 'draft')

    def test_each_screen_writes_only_its_own_fields(self):
        """Écriture partielle : quitter en cours de route ne perd que ce qui
        n'a pas encore été envoyé."""
        self._login()
        self._post('/my/innovation/new', {
            'name': "Smart Factory", 'resume': "Résumé initial."})
        project = self._project_of(self.member)

        self._post('/my/innovation/%s/marche' % project.id, {
            'marche_cible': "Industriels algériens",
            'modele_economique': 'abonnement',
        })
        project.invalidate_recordset()

        self.assertEqual(project.marche_cible, "Industriels algériens")
        # L'écran 2 n'a pas touché aux champs de l'écran 1.
        self.assertEqual(project.resume, "Résumé initial.")

    def test_returning_shows_a_resume_message(self):
        self._login()
        self._post('/my/innovation/new', {'name': "Projet interrompu"})
        body = self.url_open('/my/innovation').text
        self.assertIn("en cours de saisie", body)
        self.assertIn("Projet interrompu", body)

    def test_a_second_visit_reuses_the_draft_instead_of_duplicating(self):
        self._login()
        self._post('/my/innovation/new', {'name': "Premier"})
        self._post('/my/innovation/new', {'name': "Renommé"})

        projects = self.Project.sudo().search(
            [('partner_id', '=', self.member.partner_id.id)])
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects.name, "Renommé")

    def test_name_is_required_on_the_first_screen(self):
        self._login()
        response = self._post('/my/innovation/new', {'name': "   "})
        self.assertIn("obligatoire", response.text)
        self.assertFalse(self._project_of(self.member))

    # ------------------------------------------------------------
    # Les écrans intermédiaires
    # ------------------------------------------------------------

    def _draft(self):
        self._login()
        self._post('/my/innovation/new', {
            'name': "Smart Factory",
            'resume': "Une usine pilotée par l'IA.",
            'probleme': "Arrêts imprévus.",
            'solution': "Maintenance prédictive.",
            'secteur': 'industrie',
            'maturite': 'mvp',
        })
        return self._project_of(self.member)

    def test_team_members_can_be_added_and_removed(self):
        project = self._draft()
        self._post('/my/innovation/%s/equipe' % project.id, {
            'action': 'add',
            'member_name': "Amine",
            'member_fonction': "CTO",
        })
        project.invalidate_recordset()
        self.assertEqual(len(project.team_member_ids), 1)

        member = project.team_member_ids
        self._post('/my/innovation/%s/equipe' % project.id, {
            'action': 'remove', 'member_id': str(member.id)})
        project.invalidate_recordset()
        self.assertFalse(project.team_member_ids)

    def test_needs_screen_saves_the_financing_block(self):
        project = self._draft()
        self._post('/my/innovation/%s/besoins' % project.id, {
            'besoin_financement': '1',
            'montant_recherche': '500000',
            'type_financement': "Levée de fonds",
        })
        project.invalidate_recordset()
        self.assertTrue(project.besoin_financement)
        self.assertEqual(project.montant_recherche, 500000)

    def test_unticked_financing_is_saved_as_false(self):
        project = self._draft()
        project.sudo().besoin_financement = True
        self._post('/my/innovation/%s/besoins' % project.id, {})
        project.invalidate_recordset()
        self.assertFalse(project.besoin_financement)

    def test_document_controls_are_reported_as_page_errors(self):
        """Les contrôles du modèle remontent en message, pas en erreur 500."""
        project = self._draft()
        response = self._post('/my/innovation/%s/documents' % project.id, {
            'action': 'add', 'document_type': 'business_plan', 'name': "BP"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("fichier", response.text.lower())

    # ------------------------------------------------------------
    # Section 11 — Récapitulatif et soumission
    # ------------------------------------------------------------

    def test_recap_warns_before_submission(self):
        project = self._draft()
        body = self._flat(self.url_open('/my/innovation/%s/recap' % project.id).text)
        self.assertIn("ne seront plus modifiables", body)

    def test_submission_requires_the_confirmation_checkbox(self):
        project = self._draft()
        response = self._post('/my/innovation/%s/recap' % project.id, {})
        self.assertIn("case de confirmation", response.text)
        project.invalidate_recordset()
        self.assertEqual(project.workflow_stage_id.code, 'draft')

    def test_confirmed_submission_moves_the_project(self):
        project = self._draft()
        self._post('/my/innovation/%s/recap' % project.id, {'confirm': '1'})
        project.invalidate_recordset()
        self.assertEqual(project.workflow_stage_id.code, 'submitted')

    def test_a_blocked_condition_is_shown_on_the_recap_page(self):
        """Le refus du moteur est rendu lisible, pas avalé."""
        self._login()
        self._post('/my/innovation/new', {'name': "Dossier vide"})
        project = self._project_of(self.member)

        response = self._post(
            '/my/innovation/%s/recap' % project.id, {'confirm': '1'})
        self.assertIn("Complétez", response.text)
        project.invalidate_recordset()
        self.assertEqual(project.workflow_stage_id.code, 'draft')

    # ------------------------------------------------------------
    # Sécurité
    # ------------------------------------------------------------

    def test_a_forged_partner_id_is_ignored(self):
        """`create()` impose `partner_id`, quelle que soit la valeur envoyée."""
        self._login()
        self._post('/my/innovation/new', {
            'name': "Tentative",
            'partner_id': str(self.outsider.partner_id.id),
        })
        project = self._project_of(self.member)
        self.assertEqual(project.partner_id, self.member.partner_id)

    def test_another_project_cannot_be_reached_by_its_id(self):
        project = self._draft()

        self.authenticate('pp_outsider', 'pp_outsider')
        response = self.url_open(
            '/my/innovation/%s/marche' % project.id, allow_redirects=False)
        # Redirigé vers la liste : l'identifiant n'a rien désigné.
        self.assertIn(response.status_code, (302, 303))

    def test_another_project_cannot_be_written_by_its_id(self):
        project = self._draft()
        original = project.marche_cible

        self.authenticate('pp_outsider', 'pp_outsider')
        self._post('/my/innovation/%s/marche' % project.id,
                   {'marche_cible': "Injecté"})

        project.invalidate_recordset()
        self.assertEqual(project.marche_cible, original)

    def test_a_submitted_project_can_no_longer_be_edited_by_the_screens(self):
        project = self._draft()
        self._post('/my/innovation/%s/recap' % project.id, {'confirm': '1'})
        project.invalidate_recordset()
        self.assertEqual(project.workflow_stage_id.code, 'submitted')

        response = self.url_open(
            '/my/innovation/%s/marche' % project.id, allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))

    def test_only_whitelisted_fields_can_be_written(self):
        """Une clé hors liste blanche n'écrit rien, même si le champ existe."""
        project = self._draft()
        self._post('/my/innovation/%s/marche' % project.id, {
            'marche_cible': "Industriels",
            'ceo_approval': '1',
            'score': '100',
        })
        project.invalidate_recordset()
        self.assertEqual(project.marche_cible, "Industriels")
        self.assertFalse(project.ceo_approval)
        self.assertEqual(project.score, 0)
