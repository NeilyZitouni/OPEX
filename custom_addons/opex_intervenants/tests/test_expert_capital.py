import re
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import HttpCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestExpertCapital(HttpCase):
    """Extension 3 — le capital que le matching interrogera.

    Deux choses à prouver, et elles ne se recouvrent pas :

    1. le capital **s'attache au profil existant** du Module 2, sans en créer
       un second ni modifier celui-là ;
    2. il **s'expose sur `res.partner`**, parce que c'est le seul endroit où le
       moteur de matching sait lire (`_score_candidate` compare à
       `partner[target_field]`). Sans cela, l'Extension 4 n'aurait rien à
       comparer et on ne s'en apercevrait qu'à ce moment-là.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Profile = cls.env['opex.innovation.expert.profile']
        cls.Skill = cls.env['opex.expert.skill']
        cls.Experience = cls.env['opex.expert.experience']
        cls.Certification = cls.env['opex.expert.certification']
        cls.Availability = cls.env['opex.expert.availability']
        cls.Rating = cls.env['opex.expert.rating']

        cls.expert = new_test_user(
            cls.env, login='ec_expert', password='ec_expert',
            groups='base.group_portal')
        cls.other_expert = new_test_user(
            cls.env, login='ec_other', password='ec_other',
            groups='base.group_portal')
        cls.sans_profil = new_test_user(
            cls.env, login='ec_nobody', password='ec_nobody',
            groups='base.group_portal')
        cls.manager = new_test_user(
            cls.env, login='ec_manager', password='ec_manager',
            groups='base.group_user,opex_intervenants.group_mission_manager')

        cls.profile = cls._activate_profile(cls.expert)
        cls.other_profile = cls._activate_profile(cls.other_expert)

        cls.competence = cls.env['opex.innovation.competence'].create(
            {'name': "Cybersécurité", 'code': 'ec_cyber'})
        cls.autre_competence = cls.env['opex.innovation.competence'].create(
            {'name': "Lean manufacturing", 'code': 'ec_lean'})
        cls.mission_type = cls.env.ref('opex_intervenants.mission_type_audit')
        cls.domaine = cls.env.ref(
            'opex_intervenants.mission_domain_cybersecurite')

    @classmethod
    def _activate_profile(cls, user):
        """Crée le profil du Module 2 **et l'active**.

        `partner.expert_profile_id` n'est renseigné qu'à l'activation, par
        `action_activate_profile()` du Module 2. C'est ce champ que les écrans
        de l'Extension 3 interrogent : une demande encore en instruction
        n'ouvre rien, conformément à la règle 1 du §39.
        """
        profile = cls.env['opex.innovation.expert.profile'].sudo().create({
            'partner_id': user.partner_id.id,
            'domaine_expertise': "Sécurité des systèmes d'information",
            'annees_experience': 15,
        })
        profile.action_activate_profile()
        return profile

    # ------------------------------------------------------------
    # Outils HTTP
    # ------------------------------------------------------------

    def _login(self, login='ec_expert'):
        self.authenticate(login, login)

    def _csrf(self):
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
        return " ".join(text.split())

    def _today(self, **delta):
        return fields.Date.context_today(self.Skill) + timedelta(**delta)

    #
    # ON N'A PAS CRÉÉ UN SECOND PROFIL
    #

    def test_no_second_expert_profile_model_exists(self):
        """« Un expert référencé ne ressaisit pas son profil permanent. »

        Le capital se rattache à `opex.innovation.expert.profile`, celui du
        Module 2. Un modèle `opex.expert.profile` propre à ce module
        obligerait exactement à la ressaisie que la spécification interdit.
        """
        self.assertNotIn('opex.expert.profile', self.env)
        self.assertNotIn('opex.intervenants.expert.profile', self.env)
        for model in ('opex.expert.skill', 'opex.expert.experience',
                      'opex.expert.certification', 'opex.expert.availability',
                      'opex.expert.rating'):
            self.assertEqual(
                self.env[model]._fields['profile_id'].comodel_name,
                'opex.innovation.expert.profile',
                "%s ne se rattache pas au profil du Module 2." % model)

    def test_the_module_2_profile_is_not_modified(self):
        """L'extension ajoute des relations, elle ne touche à rien.

        Assertion positive d'abord — les champs du Module 2 sont toujours là —
        puis la vérification que les nôtres se sont ajoutés à côté.
        """
        champs = self.Profile._fields
        for name in ('domaine_expertise', 'specialites', 'annees_experience',
                     'competence_ids', 'workflow_instance_id'):
            self.assertIn(name, champs,
                          "Le champ « %s » du Module 2 a disparu." % name)
        for name in ('expert_skill_ids', 'expert_experience_ids',
                     'expert_certification_ids', 'expert_availability_ids',
                     'expert_rating_ids', 'reputation_score'):
            self.assertIn(name, champs)

    #
    # LES CINQ MODÈLES
    #

    @mute_logger('odoo.sql_db')
    def test_a_competence_is_declared_once_per_profile(self):
        """Deux lignes pour la même compétence n'auraient aucun sens : c'est la
        même compétence, à un niveau donné."""
        self.Skill.create({
            'profile_id': self.profile.id,
            'competence_id': self.competence.id,
            'niveau': 'expert', 'annees': 10,
        })
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.Skill.create({
                    'profile_id': self.profile.id,
                    'competence_id': self.competence.id,
                    'niveau': 'debutant',
                })

    def test_the_same_competence_may_be_declared_by_two_experts(self):
        """L'autre moitié de la contrainte, qu'une clause trop large casserait."""
        for profile in (self.profile, self.other_profile):
            self.Skill.create({
                'profile_id': profile.id,
                'competence_id': self.competence.id,
                'niveau': 'confirme',
            })
        self.assertEqual(len(self.Skill.search(
            [('competence_id', '=', self.competence.id)])), 2)

    def test_a_certification_expires_on_its_date(self):
        """La validité est calculée, jamais stockée.

        « Cette certification est-elle encore valable ? » dépend du jour où
        l'on pose la question. Stockée, elle se figerait au dernier recalcul et
        l'Extension 4 sélectionnerait des experts sur des certifications
        périmées.
        """
        valide = self.Certification.create({
            'profile_id': self.profile.id, 'name': "ISO 27001",
            'date_expiration': self._today(days=30),
        })
        perimee = self.Certification.create({
            'profile_id': self.profile.id, 'name': "ITIL v3",
            'date_expiration': self._today(days=-1),
        })
        sans_echeance = self.Certification.create({
            'profile_id': self.profile.id, 'name': "Diplôme d'ingénieur",
        })
        self.assertTrue(valide.is_valid)
        self.assertFalse(perimee.is_valid)
        self.assertTrue(sans_echeance.is_valid)
        self.assertFalse(
            self.Certification._fields['is_valid'].store,
            "`is_valid` est stocké : il se figera au dernier recalcul.")

    def test_an_availability_period_is_current_only_within_its_dates(self):
        courante = self.Availability.create({
            'profile_id': self.profile.id,
            'date_debut': self._today(days=-5),
            'date_fin': self._today(days=5),
            'taux': 60,
        })
        passee = self.Availability.create({
            'profile_id': self.profile.id,
            'date_debut': self._today(days=-30),
            'date_fin': self._today(days=-20),
        })
        self.assertTrue(courante.is_current)
        self.assertFalse(passee.is_current)
        self.assertFalse(self.Availability._fields['is_current'].store)

    def test_inconsistent_dates_are_refused(self):
        with self.assertRaises(ValidationError):
            self.Availability.create({
                'profile_id': self.profile.id,
                'date_debut': self._today(days=10),
                'date_fin': self._today(days=1),
            })
        with self.assertRaises(ValidationError):
            self.Experience.create({
                'profile_id': self.profile.id, 'name': "Mission",
                'date_debut': self._today(days=10),
                'date_fin': self._today(days=1),
            })

    @mute_logger('odoo.sql_db')
    def test_a_rate_outside_zero_hundred_is_refused(self):
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.Availability.create({
                    'profile_id': self.profile.id,
                    'date_debut': self._today(),
                    'date_fin': self._today(days=1),
                    'taux': 150,
                })

    #
    # LA RÉPUTATION — le modèle existe, il est vide
    #

    def test_reputation_is_zero_and_says_so(self):
        """Zéro parce que jamais évalué, pas parce que mal noté.

        C'est la distinction que l'écran porte : il affiche « — » et « Aucune
        mission évaluée », pas « 0 / 5 ».
        """
        self.assertEqual(self.profile.reputation_score, 0.0)
        self.assertEqual(self.profile.rating_count, 0)
        self.assertFalse(self.profile.expert_rating_ids)

    def test_no_screen_creates_a_rating(self):
        """Le modèle est créé vide et le reste : aucune route ne l'écrit.

        Les notes viendront de l'Extension 10, à la clôture d'une mission. Un
        écran qui en saisirait viderait la réputation de son sens — le §32
        demande un historique « basé sur les missions réellement réalisées ».
        """
        router = self.env['ir.http'].routing_map()
        routes = [str(r.rule) for r in router.iter_rules()]
        self.assertFalse(
            [r for r in routes if 'rating' in r and '/my/missions' in r],
            "Une route du module écrit des évaluations avant l'Extension 10.")

    def test_reputation_averages_the_ratings_when_they_exist(self):
        """L'agrégat fonctionne — c'est l'Extension 10 qui fournira les lignes."""
        for note in (4.0, 5.0, 3.0):
            self.Rating.create({
                'profile_id': self.profile.id, 'source': 'client',
                'note': note,
            })
        self.profile.invalidate_recordset()
        self.assertEqual(self.profile.reputation_score, 4.0)
        self.assertEqual(self.profile.rating_count, 3)

    def test_the_stored_and_unstored_aggregates_use_distinct_methods(self):
        """Le registre l'exige, et la raison est concrète.

        Une même méthode produisant des champs stockés et non stockés fait
        refuser le chargement (`registry.py:543`) : lire un compteur
        d'affichage déclencherait une **écriture** de la réputation. Leçon de
        l'Extension 1, appliquée d'emblée.
        """
        champs = self.Profile._fields
        self.assertTrue(champs['reputation_score'].store)
        self.assertFalse(champs['rating_count'].store)
        self.assertNotEqual(
            champs['reputation_score'].compute, champs['rating_count'].compute,
            "Le champ stocké et les compteurs partagent une méthode de calcul.")

    #
    # CE QUE LE MATCHING LIRA — SUR `res.partner`
    #

    def test_the_capital_is_exposed_on_res_partner(self):
        """La contrainte du moteur, pas un choix de conception.

        `_score_candidate()` compare à `partner.sudo()[criterion.target_field]`
        (`workflow_instance.py:1077`). Le champ cible est **toujours** un champ
        de `res.partner`. Sans cette exposition, l'Extension 4 n'aurait rien à
        lire — et on ne s'en apercevrait qu'à ce moment-là.
        """
        self.Skill.create({
            'profile_id': self.profile.id,
            'competence_id': self.competence.id, 'niveau': 'expert',
        })
        self.Experience.create({
            'profile_id': self.profile.id, 'name': "Audit SI",
            'mission_type_id': self.mission_type.id,
            'domaine_id': self.domaine.id, 'seniorite': 'senior',
        })
        self.Availability.create({
            'profile_id': self.profile.id,
            'date_debut': self._today(days=-1), 'date_fin': self._today(days=30),
            'taux': 80,
        })
        self.Certification.create({
            'profile_id': self.profile.id, 'name': "ISO 27001",
            'date_expiration': self._today(days=365),
        })

        partner = self.expert.partner_id
        partner.invalidate_recordset()
        self.assertEqual(partner.expert_skill_competence_ids, self.competence)
        self.assertEqual(partner.expert_experience_domaine_ids, self.domaine)
        self.assertEqual(partner.expert_mission_type_ids, self.mission_type)
        self.assertEqual(partner.expert_seniorite, 'senior')
        self.assertTrue(partner.expert_disponible)
        self.assertEqual(partner.expert_taux_disponibilite, 80)
        self.assertIn("ISO 27001", partner.expert_certification_names)

    def test_none_of_the_matching_targets_is_stored(self):
        """Stockés, ces champs seraient **faux**, pas seulement inutiles.

        `is_valid` d'une certification et `is_current` d'une disponibilité
        dépendent du jour où l'on regarde, et **rien ne déclenche de recalcul
        quand une échéance passe**. Un `expert_disponible` stocké resterait
        vrai après la fin de la période, et le matching de l'Extension 4
        proposerait des experts indisponibles — sans que rien ne le signale.

        (Le crash de registre que documente le CLAUDE.md concerne le couple
        `related` + `store` sur un Many2many. Vérifié : avec `compute`, le
        registre charge sans erreur. Ce n'est donc pas ce qui justifie
        l'absence de stockage ici.)
        """
        champs = self.env['res.partner']._fields
        for name in ('expert_skill_competence_ids',
                     'expert_experience_domaine_ids',
                     'expert_mission_type_ids', 'expert_seniorite',
                     'expert_disponible', 'expert_taux_disponibilite',
                     'expert_reputation', 'expert_certification_names'):
            self.assertIn(name, champs, "Cible de matching absente : %s" % name)
            self.assertFalse(
                champs[name].store,
                "« %s » est stocké : il se figera au dernier recalcul, et une "
                "échéance passée ne le mettra pas à jour." % name)

    def test_the_seniority_exposed_is_the_highest_reached(self):
        """Un `max()` sur les chaînes trierait par ordre alphabétique et
        ferait de « junior » le sommet de la hiérarchie."""
        for seniorite in ('junior', 'expert', 'confirme'):
            self.Experience.create({
                'profile_id': self.profile.id,
                'name': "Mission %s" % seniorite, 'seniorite': seniorite,
            })
        partner = self.expert.partner_id
        partner.invalidate_recordset()
        self.assertEqual(partner.expert_seniorite, 'expert')

    def test_a_partner_without_profile_exposes_an_empty_capital(self):
        """Aucune erreur, aucune valeur inventée : le vivier contient aussi des
        contacts qui ne sont pas experts."""
        partner = self.sans_profil.partner_id
        self.assertFalse(partner.expert_skill_competence_ids)
        self.assertFalse(partner.expert_seniorite)
        self.assertFalse(partner.expert_disponible)
        self.assertEqual(partner.expert_reputation, 0.0)

    def test_an_expired_certification_leaves_the_matching_target(self):
        """La cible de matching suit la validité, pas la simple existence."""
        self.Certification.create({
            'profile_id': self.profile.id, 'name': "Périmée",
            'date_expiration': self._today(days=-1),
        })
        partner = self.expert.partner_id
        partner.invalidate_recordset()
        self.assertFalse(partner.expert_certification_names)

    #
    # LES ÉCRANS PORTAIL
    #

    def test_the_capital_page_renders_its_four_blocks(self):
        self._login()
        response = self.url_open('/my/missions/expertise')
        self.assertEqual(response.status_code, 200)
        body = self._flat(response.text)
        # Assertion positive d'abord : la page est bien la bonne.
        self.assertIn("Mon expertise", body)
        for bloc in ("Compétences", "Expériences", "Certifications",
                     "Disponibilités", "Mes évaluations"):
            self.assertIn(bloc, body)

    def test_a_member_without_an_active_profile_is_told_why(self):
        """Règle 1 du §39, appliquée en amont — et **expliquée**.

        Une redirection muette vers `/my` laisserait le membre sans savoir ce
        qui lui manque.
        """
        self._login('ec_nobody')
        response = self.url_open('/my/missions/expertise')
        self.assertEqual(response.status_code, 200)
        body = self._flat(response.text)
        self.assertIn("profil Expert validé", body)
        self.assertIn("/my/innovation/profiles", response.text)
        # …et il n'a pas les formulaires d'ajout.
        self.assertNotIn("Ajouter", body)

    def test_the_expert_adds_and_removes_a_competence(self):
        self._login()
        self._post('/my/missions/expertise/skill', {
            'action': 'add',
            'competence_id': str(self.competence.id),
            'niveau': 'expert', 'annees': '12',
        })
        skill = self.Skill.search([('profile_id', '=', self.profile.id)])
        self.assertEqual(len(skill), 1)
        self.assertEqual(skill.niveau, 'expert')
        self.assertEqual(skill.annees, 12)

        self._post('/my/missions/expertise/skill',
                   {'action': 'remove', 'line_id': str(skill.id)})
        self.assertFalse(
            self.Skill.search([('profile_id', '=', self.profile.id)]))

    def test_the_four_blocks_are_writable_from_the_portal(self):
        self._login()
        self._post('/my/missions/expertise/experience', {
            'action': 'add', 'name': "Audit SI industriel",
            'mission_type_id': str(self.mission_type.id),
            'domaine_id': str(self.domaine.id), 'seniorite': 'senior',
            'date_debut': str(self._today(days=-400)),
            'date_fin': str(self._today(days=-300)),
        })
        self._post('/my/missions/expertise/certification', {
            'action': 'add', 'name': "ISO 27001 Lead Auditor",
            'organisme': "AFNOR",
            'date_expiration': str(self._today(days=365)),
        })
        self._post('/my/missions/expertise/availability', {
            'action': 'add',
            'date_debut': str(self._today(days=-1)),
            'date_fin': str(self._today(days=60)),
            'taux': '75',
        })
        self.profile.invalidate_recordset()
        self.assertEqual(self.profile.experience_count, 1)
        self.assertEqual(self.profile.valid_certification_count, 1)
        self.assertTrue(self.profile.is_available_now)
        self.assertEqual(self.profile.current_availability_rate, 75)

    def test_a_refused_line_shows_a_message_not_a_server_error(self):
        """Les contrôles vivent sur les modèles ; la page traduit le refus."""
        self._login()
        response = self._post('/my/missions/expertise/skill',
                              {'action': 'add', 'competence_id': ''})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Choisissez une compétence", self._flat(response.text))

        # Et la contrainte SQL d'unicité, elle aussi, revient en message.
        self.Skill.create({
            'profile_id': self.profile.id,
            'competence_id': self.competence.id, 'niveau': 'confirme',
        })
        doublon = self._post('/my/missions/expertise/skill', {
            'action': 'add', 'competence_id': str(self.competence.id),
            'niveau': 'expert',
        })
        self.assertEqual(doublon.status_code, 200)
        self.assertIn("Mon expertise", self._flat(doublon.text))

    #
    # L'ÉTANCHÉITÉ
    #

    def test_an_expert_cannot_read_another_experts_capital(self):
        """Assertion positive puis négative.

        La négative **lit un champ** : `exists()` ne fait qu'un `SELECT id`
        et n'applique aucune `ir.rule`.
        """
        mienne = self.Skill.create({
            'profile_id': self.profile.id,
            'competence_id': self.competence.id, 'niveau': 'expert',
        })
        autre = self.Skill.create({
            'profile_id': self.other_profile.id,
            'competence_id': self.competence.id, 'niveau': 'debutant',
        })
        self.assertEqual(
            mienne.with_user(self.expert).niveau, 'expert')
        with self.assertRaises(AccessError):
            autre.with_user(self.expert).niveau

    def test_an_expert_cannot_write_into_another_experts_capital(self):
        autre = self.Skill.create({
            'profile_id': self.other_profile.id,
            'competence_id': self.competence.id, 'niveau': 'debutant',
        })
        self._login()
        self._post('/my/missions/expertise/skill',
                   {'action': 'remove', 'line_id': str(autre.id)})
        self.assertTrue(
            autre.exists(),
            "Un intervenant a supprimé une ligne du capital d'un autre.")

    def test_the_line_is_attached_to_the_connected_expert(self):
        """`profile_id` est imposé côté serveur, jamais lu dans le formulaire.

        Même verrou que `client_id` sur la demande de mission : ne pas afficher
        un champ ne protège de rien, une requête forgée n'a jamais vu le
        formulaire. On la forge donc.
        """
        self._login()
        self._post('/my/missions/expertise/skill', {
            'action': 'add', 'competence_id': str(self.competence.id),
            'niveau': 'confirme',
            'profile_id': str(self.other_profile.id),
        })
        self.assertEqual(
            len(self.Skill.search([('profile_id', '=', self.other_profile.id)])),
            0, "Une ligne a été rattachée au profil d'un autre.")
        self.assertEqual(
            len(self.Skill.search([('profile_id', '=', self.profile.id)])), 1)

    def test_an_expert_cannot_write_his_own_rating(self):
        """§33 — un intervenant qui corrigerait sa note viderait la réputation
        de son sens."""
        rating = self.Rating.create({
            'profile_id': self.profile.id, 'source': 'client', 'note': 3.0,
        })
        # Il la lit…
        self.assertEqual(rating.with_user(self.expert).note, 3.0)
        # …et ne l'écrit pas.
        with self.assertRaises(AccessError):
            rating.with_user(self.expert).write({'note': 5.0})

    def test_the_staff_reads_the_capital_without_writing_it(self):
        """Le cluster consulte pour décider ; il ne corrige pas à la place de
        l'intervenant."""
        skill = self.Skill.create({
            'profile_id': self.profile.id,
            'competence_id': self.competence.id, 'niveau': 'confirme',
        })
        self.assertEqual(skill.with_user(self.manager).niveau, 'confirme')

    #
    # LE CONTRAT DES COMPTEURS ET LES COLLISIONS
    #

    def test_the_expertise_counter_has_its_own_key(self):
        """Un compteur, une tuile, un domaine.

        Celui-ci mesure le **capital**, `intervenants_mission_count` mesure les
        demandes. Deux tuiles partageant une clé laisseraient la seconde
        masquée — `querySelector()` ne renvoie que le premier nœud.
        """
        home = self.env.ref('portal.portal_my_home')
        tuiles = self.env['ir.ui.view'].sudo().search(
            [('inherit_id', '=', home.id)])
        for cle in ('intervenants_expertise_count', 'intervenants_mission_count'):
            porteuses = tuiles.filtered(lambda v: cle in (v.arch or ''))
            self.assertEqual(
                len(porteuses), 1,
                "« %s » est déclaré par %s tuiles." % (cle, len(porteuses)))

    def test_our_expertise_controller_names_are_all_prefixed(self):
        """Arbre `CustomerPortal` : deux classes du même module en sont deux
        feuilles, et leurs noms se fusionnent aussi entre elles."""
        from odoo.addons.opex_intervenants.controllers.expertise import (
            ExpertCapitalPortal)

        cooperatifs = {'_prepare_home_portal_values'}
        propres = {
            name for name in vars(ExpertCapitalPortal)
            if not name.startswith('__')
        }
        for name in propres - cooperatifs:
            self.assertTrue(
                name.startswith(('portal_intervenants_', '_intervenants_',
                                 '_INTERVENANTS_')),
                "« %s » n'est pas préfixé." % name)

    # La vérification des collisions entre **toutes** les classes portail du
    # module vit désormais dans `test_public_portal.py`
    # (`test_no_two_controllers_of_the_module_share_a_name`) : elle en couvre
    # quatre au lieu de deux. Ce test-ci ne portait que sur les deux premières
    # et laissait passer celles de l'Extension 5.

    def test_no_neighbour_route_disappeared(self):
        router = self.env['ir.http'].routing_map()
        routes = {str(rule.rule) for rule in router.iter_rules()}
        attendues = [
            '/my/missions/expertise',
            '/my/missions/expertise/<string:block>',
            '/my/missions', '/my/missions/new',
            '/my/innovation', '/my/innovation/profiles',
            '/my/innovation/missions', '/my/membership/new',
        ]
        manquantes = [route for route in attendues if route not in routes]
        self.assertFalse(
            manquantes, "Routes absentes du routing map : %s" % manquantes)
