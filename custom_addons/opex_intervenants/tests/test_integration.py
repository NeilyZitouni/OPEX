from datetime import timedelta

from odoo import fields
from odoo.tests.common import HttpCase, new_test_user, tagged

from .common import MissionCase


@tagged('post_install', '-at_install')
class TestIntegration(MissionCase):
    """Extension 12 - catalogue filtré, accueil unique, indicateurs globaux."""

    def _integration(self):
        return self.env['opex.portal.integration'].sudo()

    def _published_call(self, **overrides):
        """Un appel publié, donc présent au catalogue public."""
        mission = self._new_mission(**overrides)
        self._open_the_call(mission)
        mission.sudo().is_published = True
        return mission

    #
    # §48 - le catalogue et ses filtres
    #

    def test_the_catalogue_lists_the_open_calls(self):
        """L'assertion positive dont dépendent tous les tests de filtre.

        Sans elle, un filtre qui ne renverrait jamais rien passerait pour un
        filtre qui fonctionne.
        """
        mission = self._published_call()
        references = [card['reference']
                      for card in self.Mission.public_catalogue()]
        self.assertIn(mission.name, references)

    def test_each_filter_narrows_the_catalogue(self):
        """Les quatre filtres du §48, un par un.

        Chacun est éprouvé dans les deux sens : la valeur qui retient l'appel,
        et une valeur voisine qui l'écarte. Un filtre testé seulement sur le
        cas qui passe ne prouve pas qu'il filtre.
        """
        today = fields.Date.context_today(self.Mission)
        mission = self._published_call(
            localisation="Alger",
            date_debut_souhaitee=today + timedelta(days=45),
            date_fin_souhaitee=today + timedelta(days=70),
        )
        other_domain = self.env['opex.mission.domain'].sudo().create(
            {'name': "Domaine sans appel", 'code': 'ig_vide'})

        def references(**filters):
            return [card['reference']
                    for card in self.Mission.public_catalogue(filters=filters)]

        # Domaine
        self.assertIn(mission.name, references(domaine=self.domaine.id))
        self.assertNotIn(mission.name, references(domaine=other_domain.id))

        # Type
        self.assertIn(mission.name, references(type=self.mission_type.id))
        self.assertNotIn(
            mission.name, references(type=self.mission_type_multi.id))

        # Localisation, cherchée dans `localisation` et `wilaya`
        self.assertIn(mission.name, references(localisation="alg"))
        self.assertNotIn(mission.name, references(localisation="Tamanrasset"))

        # Dates : elles encadrent le démarrage souhaité
        self.assertIn(
            mission.name,
            references(date_min=str(today), date_max=str(today + timedelta(days=60))))
        self.assertNotIn(
            mission.name, references(date_min=str(today + timedelta(days=90))))

    def test_a_forged_filter_value_is_ignored_not_passed_to_the_domain(self):
        """Une valeur qui n'est pas un identifiant ne choisit pas son domaine.

        Le nettoyage est dans le controller ; ce test passe par lui, sinon il
        ne prouverait rien sur ce qui arrive vraiment du réseau.
        """
        from odoo.addons.opex_intervenants.controllers.public import (
            MissionPublicPortal,
        )
        cleaned = MissionPublicPortal()._intervenants_catalogue_filters({
            'domaine': "1 OR 1=1",
            'type': None,
            'localisation': "  Alger  ",
        })
        self.assertFalse(cleaned['domaine'])
        self.assertFalse(cleaned['type'])
        self.assertEqual(cleaned['localisation'], "Alger")

    def test_the_filter_options_are_bounded_to_the_open_calls(self):
        """Proposer un critère sur lequel rien n'est ouvert donne une liste
        vide et laisse croire à une panne."""
        self.env['opex.mission.domain'].sudo().create(
            {'name': "Domaine jamais utilisé", 'code': 'ig_jamais'})
        mission = self._published_call()

        options = self.Mission.public_filter_options()
        noms = [domaine['nom'] for domaine in options['domaines']]
        self.assertIn(self.domaine.name, noms)
        self.assertNotIn("Domaine jamais utilisé", noms)
        self.assertTrue(mission)

    def test_the_filtered_catalogue_still_hides_the_reserved_data(self):
        """Le filtrage ne rouvre pas ce que le §14 ferme.

        Régression possible et discrète : un filtre ajouté au domaine pourrait
        tenter de porter le champ filtré dans la vignette. Les clés restent
        celles de `public_card()`.
        """
        self._published_call(localisation="Alger")
        cards = self.Mission.public_catalogue(filters={'localisation': "Alger"})
        self.assertTrue(cards)
        for card in cards:
            for reserved in ('client', 'client_id', 'budget',
                             'budget_estimatif', 'conditions_financieres'):
                self.assertNotIn(
                    reserved, card,
                    "« %s » sort dans le catalogue public." % reserved)

    #
    # §48 - l'accueil unique
    #

    def test_the_home_links_the_three_domains_and_not_the_fourth(self):
        """Annuaire, innovation, missions. Pas de crowdfunding.

        `opex_crowdfunding` est isolé par construction, et rien ne doit le
        référencer - c'est la moitié texto de l'expérience de comparaison.
        """
        domaines = self._integration().portal_domains()
        self.assertEqual(
            [domaine['code'] for domaine in domaines],
            ['annuaire', 'innovation', 'missions'])
        self.assertEqual(
            [domaine['url'] for domaine in domaines],
            ['/opex/directory', '/my/innovation', '/missions'])
        for domaine in domaines:
            self.assertNotIn('crowdfunding', domaine['url'])

    def test_the_home_hands_no_recordset_to_the_template(self):
        """La page est publique : elle ne reçoit que des clés fermées."""
        for domaine in self._integration().portal_domains():
            self.assertEqual(
                set(domaine),
                {'code', 'titre', 'texte', 'url', 'public',
                 'compteur', 'compteur_libelle'})

    #
    # US-20 - les indicateurs globaux
    #

    def test_the_global_indicators_aggregate_the_three_modules(self):
        mission = self._published_call()
        indicators = self._integration().global_indicators()

        self.assertEqual(
            set(indicators),
            {'membres', 'projets_en_cours', 'projets_total',
             'missions_en_cours', 'missions_total', 'appels_ouverts',
             'taux_reussite'})
        self.assertGreaterEqual(indicators['appels_ouverts'], 1)
        self.assertGreaterEqual(indicators['missions_total'], 1)
        self.assertTrue(mission)

    def test_the_success_rate_ignores_the_missions_still_running(self):
        """Le dénominateur est ce qui a abouti, pas ce qui existe.

        Les compter toutes ferait chuter le taux à chaque appel publié, ce qui
        dirait le contraire de la vérité.
        """
        rate = self._integration()._success_rate
        self.assertEqual(rate(['accepted', 'closed', 'cancelled']), 67)
        # Deux missions en route ne changent rien au taux.
        self.assertEqual(
            rate(['accepted', 'closed', 'cancelled', 'open', 'in_progress']),
            67)

    def test_the_success_rate_is_zero_when_nothing_has_concluded(self):
        """Zéro, et non cent.

        Un cluster qui n'a terminé aucune mission n'a pas un taux de réussite
        parfait : il n'en a pas. C'est la division par zéro, tranchée dans le
        bon sens.
        """
        self.assertEqual(self._integration()._success_rate([]), 0)
        self.assertEqual(
            self._integration()._success_rate(['open', 'in_progress']), 0)

    #
    # §21 - la liste de contrôle, mesurée
    #

    def test_the_nine_acceptance_criteria_are_met(self):
        """Les neuf critères du §21, vérifiés à l'exécution.

        Cette liste n'est pas une déclaration : chaque entrée est calculée
        depuis la configuration et les données. Un critère qui cesserait
        d'être tenu ferait rougir ce test, et le tableau `/staff/kpi`
        l'afficherait en rouge.
        """
        checklist = self._integration().acceptance_checklist()
        self.assertEqual(
            len(checklist), 9,
            "Le §21 en compte neuf ; la liste en porte %s." % len(checklist))

        non_tenus = [item['critere'] for item in checklist if not item['fait']]
        self.assertFalse(
            non_tenus,
            "Critères d'acceptation non tenus : %s" % non_tenus)

        # Chaque entrée porte sa preuve : un critère coché sans preuve serait
        # une affirmation, ce que ce tableau existe précisément pour éviter.
        for item in checklist:
            self.assertTrue(item['preuve'].strip())

    def test_the_two_state_machines_are_still_independent(self):
        """Le critère du §21 qui gouverne tout le module, mesuré sur un dossier.

        Une mission en sélection porte simultanément des candidatures à des
        étapes différentes. Le test le montre plutôt que de le lire dans la
        configuration - les deux tests se tiennent.
        """
        mission = self._new_mission()
        self._open_the_call(mission)

        retenue = self._new_application(mission)
        ecartee = self._new_application(
            mission, partner=self.other_intervenant.partner_id)

        self._apply(retenue)
        self._apply(ecartee, user=self.other_intervenant)
        self._do(ecartee, 'application_reject_applied', self.manager,
                 comment="Profil hors périmètre.")
        self._do(retenue, 'application_screen', self.manager)

        self._do(mission, 'mission_close_applications', self.manager)

        self.assertEqual(self._stage(mission), 'selection')
        self.assertEqual(self._stage(retenue), 'screened')
        self.assertEqual(self._stage(ecartee), 'rejected')


@tagged('post_install', '-at_install')
class TestIntegrationHttp(HttpCase):
    """Les trois écrans de l'intégration, par de vraies requêtes."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.visitor = new_test_user(
            cls.env, login='ig_portal', password='ig_portal',
            groups='base.group_portal')
        cls.manager = new_test_user(
            cls.env, login='ig_manager', password='ig_manager',
            groups='base.group_user,opex_intervenants.group_mission_manager')

    def test_the_home_is_public(self):
        """§48 - l'accueil ne demande pas de compte.

        Sans authentification : c'est la porte d'entrée du portail, et une
        porte qui demande une clé n'en est pas une.

        Aucune apostrophe dans les assertions portant sur une valeur
        **dynamique**. Les trois titres viennent du modèle et passent par
        `t-out`, qui échappe : « Projets d'innovation » devient
        « Projets d&#39;innovation » dans le HTML rendu. Ce test a rougi
        là-dessus, et c'est le piège de la règle 7 - il aurait aussi bien pu
        passer sur du texte statique et masquer que la valeur dynamique ne
        s'affiche pas.
        """
        response = self.url_open('/opex')
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn("Annuaire des membres", body)
        self.assertIn("Appels à missions", body)
        # Les trois domaines sont là : on vérifie l'innovation par son lien,
        # qui ne contient pas d'apostrophe.
        self.assertIn('href="/my/innovation"', body)
        self.assertIn('href="/opex/directory"', body)
        self.assertIn('href="/missions"', body)
        # Texte **statique** du gabarit : celui-ci n'est pas réécrit.
        self.assertIn("Taux de réussite", body)

    def test_the_catalogue_renders_its_filters(self):
        response = self.url_open('/missions')
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn("Domaine d'expertise", body)
        self.assertIn("Type de mission", body)
        self.assertIn("Localisation", body)
        self.assertIn("Démarrage entre", body)

    def test_the_catalogue_survives_a_forged_filter(self):
        """Une page publique ne tombe pas sur une valeur mal formée."""
        response = self.url_open('/missions?domaine=abc&type=%27&date_min=zz')
        self.assertEqual(response.status_code, 200)

    def test_the_global_kpi_is_closed_to_the_portal(self):
        self.authenticate('ig_portal', 'ig_portal')
        response = self.url_open('/staff/kpi')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            "indicateurs globaux", response.text,
            "Un compte portail atteint le tableau de bord du cluster.")

    def test_the_global_kpi_renders_for_the_staff(self):
        self.authenticate('ig_manager', 'ig_manager')
        response = self.url_open('/staff/kpi')
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn("indicateurs globaux", body)
        self.assertIn("Critères d'acceptation", body)
        # Les neuf critères sont rendus, et tenus.
        self.assertIn("Tenu", body)
        self.assertNotIn("Non tenu", body)
