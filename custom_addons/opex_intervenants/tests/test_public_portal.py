import re
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestPublicPortal(HttpCase):
    """Extension 5 — l'appel au portail et la candidature Lean.

    Quatre exigences, toutes des critères d'acceptation ou des règles du §39 :

    1. la vue publique est **dédiée** — aucune donnée réservée dans le HTML,
       même masquée ;
    2. la règle 1 est vérifiée **côté serveur sur le POST**, pas seulement par
       l'affichage du bouton ;
    3. la règle 3 rend un **message lisible**, pas une erreur de base ;
    4. la candidature Lean ne redemande **rien** de permanent.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Mission = cls.env['opex.mission.request']
        cls.Application = cls.env['opex.mission.application']
        cls.Profile = cls.env['opex.innovation.expert.profile']

        cls.audit = cls.env.ref('opex_intervenants.mission_type_audit')
        cls.domaine = cls.env.ref(
            'opex_intervenants.mission_domain_cybersecurite')
        cls.competence = cls.env['opex.innovation.competence'].create(
            {'name': "Cybersécurité", 'code': 'pp_cyber'})

        cls.client_user = new_test_user(
            cls.env, login='pp_client', password='pp_client',
            groups='base.group_portal')
        cls.manager = new_test_user(
            cls.env, login='pp_manager', password='pp_manager',
            groups='base.group_user,opex_intervenants.group_mission_manager')

        # Un expert référencé, profil **activé**.
        cls.expert = new_test_user(
            cls.env, login='pp_expert', password='pp_expert',
            groups='base.group_portal')
        cls.expert_profile = cls.Profile.sudo().create({
            'partner_id': cls.expert.partner_id.id,
            'domaine_expertise': "Sécurité", 'annees_experience': 12,
        })
        cls.expert_profile.action_activate_profile()
        cls.env['opex.expert.skill'].sudo().create({
            'profile_id': cls.expert_profile.id,
            'competence_id': cls.competence.id, 'niveau': 'expert',
        })

        # Un candidat externe : compte portail, **aucun** profil.
        cls.externe = new_test_user(
            cls.env, login='pp_externe', password='pp_externe',
            groups='base.group_portal')

    # ------------------------------------------------------------
    # Outils
    # ------------------------------------------------------------

    @classmethod
    def _today(cls, **delta):
        return fields.Date.context_today(cls.env['opex.mission.request']) \
            + timedelta(**delta)

    def _login(self, login):
        self.authenticate(login, login)

    def _csrf(self):
        page = self.url_open('/missions').text
        match = re.search(r'csrf_token: "([^"]+)"', page)
        self.assertTrue(match, "Jeton CSRF introuvable")
        return match.group(1)

    def _post(self, url, data=None):
        payload = {'csrf_token': self._csrf()}
        payload.update(data or {})
        return self.url_open(url, data=payload)

    @staticmethod
    def _flat(text):
        return " ".join(text.split())

    def _mission(self, stage='open', public_fields_only=True, **overrides):
        """Un appel amené jusqu'à l'étape voulue, par le moteur."""
        values = {
            'title': "Audit cybersécurité",
            'mission_type_id': self.audit.id,
            'client_id': self.client_user.partner_id.id,
            'description': "Audit du SI industriel.",
            'objectifs': "Cartographier les vulnérabilités.",
            'domaine_id': self.domaine.id,
            'skill_ids': [(6, 0, self.competence.ids)],
            'budget_estimatif': 300000.0,
            'duree_estimee_jours': 15,
            'public_fields_only': public_fields_only,
            'date_limite_candidature': self._today(days=30),
        }
        values.update(overrides)
        mission = self.Mission.create(values)

        chemin = [('mission_submit', self.client_user),
                  ('mission_start_sourcing', self.manager),
                  ('mission_open_applications', self.manager)]
        for code, user in chemin:
            if code == 'mission_open_applications' and stage == 'sourcing':
                break
            transition = mission.workflow_definition_id.sudo()\
                .transition_ids.filtered(lambda t: t.code == code)
            mission.with_user(user).sudo().workflow_do_transition(transition)
        mission.invalidate_recordset()
        return mission

    #
    # §7 — LA RUBRIQUE PUBLIQUE
    #

    def test_the_catalogue_is_public(self):
        """Un visiteur **anonyme** voit la rubrique.

        `auth='public'` : c'est le point d'entrée de la méthode B du §8 — le
        marché, pas seulement le vivier.
        """
        self._mission()
        response = self.url_open('/missions')
        self.assertEqual(response.status_code, 200)
        body = self._flat(response.text)
        self.assertIn("Opportunités — Missions OPEX", body)
        self.assertIn("Audit cybersécurité", body)

    def test_only_published_calls_appear(self):
        """Un brouillon n'est pas au catalogue, et son URL ne donne rien.

        Assertion positive d'abord — l'appel ouvert est là — puis la négative,
        qui ne vaudrait rien seule.
        """
        ouvert = self._mission()
        brouillon = self.Mission.create({
            'title': "Appel confidentiel non publié",
            'mission_type_id': self.audit.id,
            'client_id': self.client_user.partner_id.id,
            'description': "x", 'objectifs': "y",
        })
        body = self.url_open('/missions').text
        self.assertIn(ouvert.title, body)
        self.assertNotIn("Appel confidentiel non publié", body)

        # …et l'URL directe ne le sert pas non plus.
        direct = self.url_open('/missions/%s' % brouillon.id)
        self.assertNotIn("Appel confidentiel non publié", direct.text)

    #
    # §14 — LA VUE DÉDIÉE : RIEN DE RÉSERVÉ DANS LE HTML
    #

    def test_a_restricted_call_leaks_neither_client_nor_budget(self):
        """Le point de sécurité de cette extension.

        « Ne rends **jamais** dans le HTML une donnée réservée, même masquée en
        CSS. » On vérifie donc la **source de la page**, pas ce qui s'affiche.
        """
        mission = self._mission(public_fields_only=True)
        response = self.url_open('/missions/%s' % mission.id)
        self.assertEqual(response.status_code, 200)
        body = response.text

        # Assertion positive : la page est bien la bonne.
        self.assertIn("Audit cybersécurité", body)
        self.assertIn("Cartographier les vulnérabilités", body)

        # …et elle ne contient ni le client, ni le budget, nulle part.
        self.assertNotIn(
            self.client_user.partner_id.name, body,
            "Le nom du client apparaît dans la source de la page publique.")
        self.assertNotIn(
            "300000", body.replace(" ", ""),
            "Le budget apparaît dans la source de la page publique.")
        # Et la page le **dit**, au lieu de laisser un blanc.
        self.assertIn("ne sont communiqués qu'aux candidats retenus",
                      self._flat(body))

    def test_an_open_call_may_publish_client_and_budget(self):
        """`public_fields_only` décoché : le §12 du document UX est servi.

        Les deux documents se réconcilient par un réglage **par appel**, pas
        par un arbitrage global.
        """
        mission = self._mission(public_fields_only=False)
        body = self.url_open('/missions/%s' % mission.id).text
        self.assertIn(self.client_user.partner_id.name, body)
        self.assertIn("300", body.replace(" ", ""))

    def test_the_public_view_returns_a_closed_dictionary(self):
        """La liste de clés est fermée, et les clés masquées sont **absentes**.

        Pas mises à `False` : un gabarit qui les afficherait lèverait au
        premier rendu. Une erreur bruyante vaut mieux qu'une fuite silencieuse.

        **C'est ce test-ci qui garde vraiment la confidentialité, pas celui
        sur le HTML.** Mesuré par régression volontaire : en retirant le filtre
        `public_fields_only` du dictionnaire, seul ce test rougit — le gabarit
        continuait de masquer client et budget par son propre `t-if`, et la
        page restait propre.

        Les deux sont donc complémentaires et ne se remplacent pas : celui-ci
        vérifie que la donnée **ne sort pas du modèle**, l'autre qu'elle
        n'atteint pas la page. Une fuite au niveau du dictionnaire n'attend
        qu'un `t-out` ajouté un mardi pour devenir visible.
        """
        restreint = self._mission(public_fields_only=True).public_detail()
        ouvert = self._mission(public_fields_only=False).public_detail()

        self.assertNotIn('client', restreint)
        self.assertNotIn('budget', restreint)
        self.assertIn('client', ouvert)
        self.assertIn('budget', ouvert)

        # Aucun champ interne ne s'est glissé dans le dictionnaire.
        for interdit in ('client_id', 'workflow_instance_id',
                         'application_ids', 'matching_candidate_ids',
                         'conditions_financieres', 'sourcing_mode'):
            self.assertNotIn(interdit, restreint)
            self.assertNotIn(interdit, ouvert)

    def test_only_public_documents_are_served(self):
        mission = self._mission()
        prive = self.env['opex.mission.document'].sudo().create({
            'mission_id': mission.id, 'name': "Annexe technique confidentielle",
            'document_type': 'technique', 'is_public': False,
            'filename': 'annexe.pdf', 'file': b'UEs=',
        })
        public = self.env['opex.mission.document'].sudo().create({
            'mission_id': mission.id, 'name': "Cahier des charges",
            'document_type': 'cahier_charges', 'is_public': True,
            'filename': 'cdc.pdf', 'file': b'UEs=',
        })
        body = self.url_open('/missions/%s' % mission.id).text
        self.assertIn("Cahier des charges", body)
        self.assertNotIn("Annexe technique confidentielle", body)

        # …et l'URL forgée de la pièce privée ne la sert pas.
        vole = self.url_open(
            '/missions/%s/document/%s' % (mission.id, prive.id))
        self.assertNotIn(b'UEs=', vole.content)
        # La publique, elle, se télécharge.
        servie = self.url_open(
            '/missions/%s/document/%s' % (mission.id, public.id))
        self.assertEqual(servie.status_code, 200)

    #
    # RÈGLE 1 DU §39 — VÉRIFIÉE SUR LE POST
    #

    def test_applying_without_a_profile_is_refused_server_side(self):
        """La règle 1, éprouvée par une **requête forgée**.

        Le `t-if` masque le bouton ; il n'empêche rien. On poste donc
        directement sur la route, sans jamais avoir vu le gabarit.
        """
        mission = self._mission()
        self._login('pp_externe')
        self._post('/missions/%s/interesse' % mission.id)
        self.assertFalse(
            self.Application.sudo().search([
                ('mission_id', '=', mission.id),
                ('partner_id', '=', self.externe.partner_id.id)]),
            "Une candidature a été créée sans profil Expert.")

    def test_the_button_and_the_route_ask_the_same_question(self):
        """Un bouton visible là où la route refuse, ou l'inverse, sont deux
        bugs symétriques. Une seule fonction répond aux deux."""
        mission = self._mission()
        self.assertFalse(
            self.externe.partner_id.opex_can_apply_to_mission(mission))
        self.assertTrue(
            self.expert.partner_id.opex_can_apply_to_mission(mission))

    def test_a_referenced_expert_may_apply(self):
        """Assertion positive : le verrou refuse, il ne bloque pas tout."""
        mission = self._mission()
        self._login('pp_expert')
        self._post('/missions/%s/interesse' % mission.id)
        application = self.Application.sudo().search([
            ('mission_id', '=', mission.id),
            ('partner_id', '=', self.expert.partner_id.id)])
        self.assertEqual(len(application), 1)
        self.assertEqual(application.source, 'portail')
        # Les trois premières étapes du §12.2 sont franchies dans la requête :
        # il a consulté, il a déclaré son intérêt.
        self.assertEqual(application.workflow_stage_id.code, 'interested')

    def test_applying_to_a_closed_call_is_refused(self):
        """Publier n'est pas ouvrir : le §8 distingue les deux."""
        mission = self._mission(stage='sourcing')
        self.assertFalse(mission.is_open_for_applications())
        self._login('pp_expert')
        self._post('/missions/%s/interesse' % mission.id)
        self.assertFalse(self.Application.sudo().search([
            ('mission_id', '=', mission.id),
            ('partner_id', '=', self.expert.partner_id.id)]))

    def test_applying_after_the_deadline_is_refused(self):
        mission = self._mission()
        mission.sudo().write({
            'date_debut_souhaitee': False, 'date_fin_souhaitee': False,
            'date_limite_candidature': self._today(days=-1),
        })
        self.assertFalse(mission.is_open_for_applications())
        self._login('pp_expert')
        self._post('/missions/%s/interesse' % mission.id)
        self.assertFalse(self.Application.sudo().search([
            ('mission_id', '=', mission.id),
            ('partner_id', '=', self.expert.partner_id.id)]))

    #
    # RÈGLE 3 — UN MESSAGE, PAS UNE ERREUR DE BASE
    #

    def test_a_second_application_gives_a_readable_message(self):
        """La contrainte SQL empoisonne la transaction.

        Sans contrôle applicatif **et** savepoint, le second « Je suis
        intéressé » rendrait un 500 : la violation ne se déclenche qu'au
        `flush`, et tout ce qui suit — y compris le rendu de la page d'erreur —
        reçoit « current transaction is aborted ».
        """
        mission = self._mission()
        self._login('pp_expert')
        self._post('/missions/%s/interesse' % mission.id)

        seconde = self._post('/missions/%s/interesse' % mission.id)
        self.assertEqual(
            seconde.status_code, 200,
            "Le second dépôt rend une erreur serveur au lieu d'un message.")
        self.assertEqual(len(self.Application.sudo().search([
            ('mission_id', '=', mission.id),
            ('partner_id', '=', self.expert.partner_id.id)])), 1)

    def test_the_message_names_the_current_stage(self):
        """« Vous avez déjà une candidature — elle est à l'étape X. »

        Un refus qui ne dit pas où en est le dossier oblige à chercher.
        """
        mission = self._mission()
        self.Application.sudo().create({
            'mission_id': mission.id,
            'partner_id': self.expert.partner_id.id, 'source': 'portail'})
        with self.assertRaises(UserError) as error:
            self.expert.partner_id.opex_check_can_apply(mission)
        self.assertIn("déjà une candidature", str(error.exception))
        self.assertIn("Nouvelle opportunité", str(error.exception))

    #
    # §9 — LA CANDIDATURE LEAN
    #

    def test_the_lean_form_asks_nothing_permanent(self):
        """Le troisième critère d'acceptation du §21.

        « Un expert référencé ne ressaisit pas son profil permanent. »

        Le formulaire demande les six données du §9 — et **aucun** champ
        d'identité, de CV, de compétence ou de certification.
        """
        mission = self._mission()
        self._login('pp_expert')
        self._post('/missions/%s/interesse' % mission.id)
        application = self.Application.sudo().search([
            ('mission_id', '=', mission.id),
            ('partner_id', '=', self.expert.partner_id.id)])

        body = self.url_open(
            '/my/missions/candidature/%s' % application.id).text
        flat = self._flat(body)

        # Les six données propres à la mission sont demandées.
        for demande in ("Disponibilité", "Délai de mobilisation",
                        "Tarif proposé", "Motivation", "Approche proposée",
                        "J'accepte les conditions"):
            self.assertIn(demande, flat, "Le §9 demande « %s »." % demande)

        # …et rien de permanent ne l'est.
        for interdit in ('name="domaine_expertise"', 'name="annees_experience"',
                         'name="competence_id"', 'name="specialites"'):
            self.assertNotIn(
                interdit, body,
                "Le formulaire redemande « %s », que le profil porte déjà."
                % interdit)

    def test_the_lean_form_shows_what_is_already_known(self):
        """La preuve à l'écran que rien n'est redemandé : le capital est
        affiché, en lecture."""
        mission = self._mission()
        self._login('pp_expert')
        self._post('/missions/%s/interesse' % mission.id)
        application = self.Application.sudo().search([
            ('mission_id', '=', mission.id),
            ('partner_id', '=', self.expert.partner_id.id)])
        flat = self._flat(self.url_open(
            '/my/missions/candidature/%s' % application.id).text)
        self.assertIn("Ce que nous savons déjà de vous", flat)
        self.assertIn("Cybersécurité", flat)

    def test_the_document_slots_exclude_the_permanent_pieces(self):
        """CV, portfolio, références et certifications sont sur le profil.

        Les redemander ici serait exactement la ressaisie que le §9 interdit ;
        ne restent que les pièces propres à la mission.
        """
        from odoo.addons.opex_intervenants.controllers.candidature import (
            MissionApplicationPortal)

        types = dict(MissionApplicationPortal._INTERVENANTS_APPLICATION_DOCUMENTS)
        self.assertEqual(
            set(types), {'proposition_technique', 'proposition_financiere',
                         'autre'})
        for permanent in ('cv', 'portfolio', 'references', 'certification'):
            self.assertNotIn(permanent, types)

    def test_submitting_goes_through_the_engine(self):
        """L'envoi est une **transition**, avec sa condition configurée."""
        mission = self._mission()
        self._login('pp_expert')
        self._post('/missions/%s/interesse' % mission.id)
        application = self.Application.sudo().search([
            ('mission_id', '=', mission.id),
            ('partner_id', '=', self.expert.partner_id.id)])

        # Incomplet : la condition de l'Extension 1 refuse, et la page le dit.
        refus = self._post('/my/missions/candidature/%s' % application.id,
                           {'action': 'submit', 'disponibilite': 'oui'})
        self.assertEqual(refus.status_code, 200)
        self.assertIn("Renseignez votre disponibilité", self._flat(refus.text))
        application.invalidate_recordset()
        self.assertEqual(application.workflow_stage_id.code, 'interested')

        # Complet : la candidature part.
        self._post('/my/missions/candidature/%s' % application.id, {
            'action': 'submit', 'disponibilite': 'oui',
            'delai_propose_jours': '10', 'type_tarif': 'tjm',
            'tarif_propose': '25 000,50',
            'motivation': "Quinze ans d'audit SI.",
            'consentement': '1',
        })
        application.invalidate_recordset()
        self.assertEqual(application.workflow_stage_id.code, 'applied')
        self.assertEqual(application.tarif_propose, 25000.50)

    def test_a_deposited_application_is_no_longer_editable(self):
        mission = self._mission()
        self._login('pp_expert')
        self._post('/missions/%s/interesse' % mission.id)
        application = self.Application.sudo().search([
            ('mission_id', '=', mission.id),
            ('partner_id', '=', self.expert.partner_id.id)])
        self._post('/my/missions/candidature/%s' % application.id, {
            'action': 'submit', 'disponibilite': 'oui',
            'delai_propose_jours': '10', 'tarif_propose': '1000',
            'motivation': "x", 'consentement': '1'})

        page = self._flat(self.url_open(
            '/my/missions/candidature/%s' % application.id).text)
        self.assertIn("Votre candidature est déposée", page)

        self._post('/my/missions/candidature/%s' % application.id,
                   {'action': 'save', 'tarif_propose': '1'})
        application.invalidate_recordset()
        self.assertEqual(application.tarif_propose, 1000.0)

    #
    # §7 — LE CANDIDAT EXTERNE
    #

    def test_an_external_candidate_is_told_what_is_missing(self):
        """Une page qui explique, pas une redirection muette."""
        mission = self._mission()
        self._login('pp_externe')
        response = self.url_open('/missions/%s/interesse' % mission.id)
        self.assertEqual(response.status_code, 200)
        flat = self._flat(response.text)
        self.assertIn("profil Expert", flat)
        self.assertIn("Créer mon profil et candidater", flat)

    def test_the_mini_profile_creates_a_real_module_2_profile(self):
        """« S'il est qualifié, son profil **peut** intégrer le référentiel. »

        Donc un vrai `opex.innovation.expert.profile`, avec son workflow de
        qualification — pas un objet parallèle qu'il faudrait recopier ensuite.
        """
        mission = self._mission()
        self._login('pp_externe')
        self._post('/missions/%s/mini-profil' % mission.id, {
            'domaine_expertise': "Comptabilité",
            'fonction': "Consultant",
        })
        profile = self.Profile.sudo().search(
            [('partner_id', '=', self.externe.partner_id.id)])
        self.assertEqual(len(profile), 1)
        self.assertEqual(profile.domaine_expertise, "Comptabilité")
        # Il suit son propre workflow, comme toute demande de profil.
        self.assertTrue(profile.workflow_instance_id)
        self.assertEqual(profile.workflow_stage_id.code, 'draft')

    def test_the_external_candidate_may_then_apply(self):
        """Le mini-profil ouvre la candidature, sans attendre l'activation.

        La règle 1 exige « le profil **requis** » ; le §7 fait entrer le
        candidat externe avant qu'il soit référencé. Les deux se tiennent : le
        cluster instruit profil et candidature ensemble.
        """
        mission = self._mission()
        self._login('pp_externe')
        self._post('/missions/%s/mini-profil' % mission.id,
                   {'domaine_expertise': "Comptabilité"})
        self._post('/missions/%s/interesse' % mission.id)

        application = self.Application.sudo().search([
            ('mission_id', '=', mission.id),
            ('partner_id', '=', self.externe.partner_id.id)])
        self.assertEqual(len(application), 1)
        self.assertEqual(application.workflow_stage_id.code, 'interested')

    def test_the_mini_profile_cannot_be_created_for_another(self):
        """`partner_id` est réécrit côté serveur par le `create()` du Module 2."""
        mission = self._mission()
        self._login('pp_externe')
        self._post('/missions/%s/mini-profil' % mission.id, {
            'domaine_expertise': "Comptabilité",
            'partner_id': str(self.expert.partner_id.id),
        })
        profile = self.Profile.sudo().search(
            [('partner_id', '=', self.externe.partner_id.id)])
        self.assertEqual(len(profile), 1)

    def test_the_capital_screen_still_needs_an_activated_profile(self):
        """Les deux niveaux de la règle 1, et ils diffèrent.

        Candidater demande un profil, **quel que soit son avancement**.
        Entretenir son capital demande un profil **activé** : on n'entretient
        un référencement qu'une fois référencé.
        """
        mission = self._mission()
        self._login('pp_externe')
        self._post('/missions/%s/mini-profil' % mission.id,
                   {'domaine_expertise': "Comptabilité"})

        # Il peut candidater…
        self.assertTrue(
            self.externe.partner_id.opex_can_apply_to_mission(mission))
        # …et pas encore entretenir son capital.
        flat = self._flat(self.url_open('/my/missions/expertise').text)
        self.assertIn("profil Expert validé", flat)

    #
    # ÉTANCHÉITÉ ET COLLISIONS
    #

    def test_a_candidate_cannot_read_another_candidates_application(self):
        mission = self._mission()
        autre = self.Application.sudo().create({
            'mission_id': mission.id,
            'partner_id': self.expert.partner_id.id, 'source': 'portail'})
        self._login('pp_externe')
        page = self.url_open('/my/missions/candidature/%s' % autre.id)
        self.assertNotIn("Ce que nous savons déjà", self._flat(page.text))

    def _controller_classes(self):
        from odoo.addons.opex_intervenants.controllers.candidature import (
            MissionApplicationPortal)
        from odoo.addons.opex_intervenants.controllers.expertise import (
            ExpertCapitalPortal)
        from odoo.addons.opex_intervenants.controllers.portal import (
            MissionRequestPortal)
        from odoo.addons.opex_intervenants.controllers.public import (
            MissionPublicPortal)
        return (MissionRequestPortal, ExpertCapitalPortal,
                MissionApplicationPortal, MissionPublicPortal)

    def test_our_public_controller_names_are_prefixed(self):
        cooperatifs = {'_prepare_home_portal_values'}
        for classe in self._controller_classes():
            noms = {n for n in vars(classe) if not n.startswith('__')}
            for nom in noms - cooperatifs:
                self.assertTrue(
                    nom.startswith(('portal_intervenants_', '_intervenants_',
                                    '_INTERVENANTS_')),
                    "« %s » (%s) n'est pas préfixé."
                    % (nom, classe.__name__))

    def test_no_two_controllers_of_the_module_share_a_name(self):
        """Le piège le plus discret : deux classes **du même module**.

        Elles sont quatre feuilles du même arbre `CustomerPortal`, donc une
        seule classe à l'exécution. Deux constantes homonymes portant la même
        valeur ne cassent rien — et c'est exactement ce qui les rend
        dangereuses : le jour où l'une change, les deux écrans changent, ou
        aucun, selon la MRO. Sans erreur et sans test rouge.

        Trouvé ainsi à l'Extension 5 :
        `_INTERVENANTS_BLOCKED_EXTENSIONS` et `_INTERVENANTS_MAX_UPLOAD`
        étaient déclarés dans deux classes. Ils vivent désormais en constantes
        de module, qui n'appartiennent à personne.
        """
        cooperatifs = {'_prepare_home_portal_values'}
        vus = {}
        for classe in self._controller_classes():
            for nom in vars(classe):
                if nom.startswith('__') or nom in cooperatifs:
                    continue
                vus.setdefault(nom, []).append(classe.__name__)

        collisions = {k: v for k, v in vus.items() if len(v) > 1}
        self.assertFalse(
            collisions,
            "Noms partagés entre les controllers du module : %s" % collisions)

    def test_the_three_counters_have_distinct_keys(self):
        """Trois tuiles, trois domaines. `querySelector()` ne renvoie que le
        premier nœud."""
        home = self.env.ref('portal.portal_my_home')
        tuiles = self.env['ir.ui.view'].sudo().search(
            [('inherit_id', '=', home.id)])
        for cle in ('intervenants_mission_count',
                    'intervenants_expertise_count',
                    'intervenants_candidature_count'):
            porteuses = tuiles.filtered(lambda v: cle in (v.arch or ''))
            self.assertEqual(
                len(porteuses), 1,
                "« %s » est déclaré par %s tuiles." % (cle, len(porteuses)))

    def test_no_neighbour_route_disappeared(self):
        router = self.env['ir.http'].routing_map()
        routes = {str(rule.rule) for rule in router.iter_rules()}
        attendues = [
            '/missions', '/missions/<int:mission_id>',
            '/missions/<int:mission_id>/interesse',
            '/missions/<int:mission_id>/mini-profil',
            '/my/missions/candidatures',
            '/my/missions/candidature/<int:application_id>',
            '/my/missions', '/my/missions/expertise',
            '/my/missions/<int:mission_id>',
            '/staff/missions',
            '/my/innovation', '/my/membership/new', '/opex/directory',
        ]
        manquantes = [route for route in attendues if route not in routes]
        self.assertFalse(
            manquantes, "Routes absentes du routing map : %s" % manquantes)
