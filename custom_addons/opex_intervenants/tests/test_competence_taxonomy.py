"""IA-2 : le rapprochement en deux temps du §8, et le flux d'enrichissement."""

import os
import re
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import tagged
from odoo.tools import mute_logger

from .common import MissionCase


@tagged('post_install', '-at_install')
class TestCompetenceTaxonomy(MissionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Competence = cls.env['opex.innovation.competence']
        cls.Synonyme = cls.env['opex.competence.synonyme']
        cls.Arbitrage = cls.env['opex.competence.arbitrage']
        cls.Resolution = cls.env['opex.competence.resolution']
        # Le **pont**, pas le service : `opex_ai_core` n'est pas une
        # dépendance déclarée, et `self.env['opex.ai.service']` lèverait un
        # `KeyError` à la construction de la classe sur une base qui ne l'a
        # pas installé - c'est-à-dire l'instance de déploiement.
        #
        # Patcher le pont est aussi plus fidèle : c'est par lui que le module
        # appelle, et lui seul. Un test qui patche le service vérifie le
        # chemin d'un autre module que celui qu'il teste.
        cls.Bridge = cls.env['opex.ai.bridge']

        # Un libellé qui n'existe nulle part ailleurs.
        #
        # Le premier jet de ces tests utilisait « Audit des systèmes
        # d'information », et deux d'entre eux ont rougi : le jeu de
        # démonstration portait déjà « Audit des systemes d'information »,
        # sans accents, que la normalisation rend identique. La résolution
        # renvoyait l'une ou l'autre selon l'ordre de recherche.
        #
        # Le défaut était réel et il a été corrigé - une correspondance
        # ambiguë part désormais en arbitrage. Le test, lui, ne doit pas
        # dépendre de ce que contient le catalogue : un test du moteur n'est
        # jamais seul en base.
        cls.audit = cls.Competence.sudo().create({
            'name': "Cryptographie appliquée aux paiements",
            'code': 'tax_audit',
        })

    def _profile(self):
        partner = self.intervenant.partner_id
        Profile = self.env['opex.innovation.expert.profile'].sudo()
        profile = Profile.search([('partner_id', '=', partner.id)], limit=1)
        if not profile:
            profile = Profile.create({'partner_id': partner.id})
        partner.sudo().expert_profile_id = profile.id
        return profile

    #
    # La normalisation
    #

    def test_the_normalised_form_ignores_case_accents_and_punctuation(self):
        """Ce qui décide si deux libellés désignent la même chose."""
        key = self.Synonyme._normalise("Audit des Systèmes d'Information")
        self.assertEqual(key, "audit des systemes d information")
        self.assertEqual(
            self.Synonyme._normalise("  AUDIT   DES  SYSTEMES D'INFORMATION "),
            key)
        self.assertEqual(self.Synonyme._normalise("ISO 27001 : 2022"),
                         self.Synonyme._normalise("iso 27001:2022"))

    def test_the_normalisation_does_not_collapse_spaces_away(self):
        """La tentation qu'il fallait refuser.

        Tout coller ferait correspondre « ISO27001 » et « ISO 27001 » — ce
        qu'on veut — mais aussi « audit si » et « auditsi », donc n'importe
        quelle suite de mots avec n'importe quelle autre à un espace près.

        Une correspondance approximative se trompe en silence. C'est la
        dette D1, et la réponse est un synonyme explicite, pas une règle plus
        permissive.
        """
        self.assertNotEqual(
            self.Synonyme._normalise("ISO27001"),
            self.Synonyme._normalise("ISO 27001"))

    #
    # Étape 1 - la correspondance, sans appel IA
    #

    def test_the_first_step_matches_the_referential_without_calling_the_ai(self):
        """La majorité des libellés d'un CV sont déjà au catalogue.

        Les payer au fournisseur serait absurde. Le test vérifie les deux
        choses : que la correspondance se fait, et qu'aucun appel n'est parti.
        """
        with patch.object(type(self.Bridge), '_ai_call_prompt') as called:
            resolved = self.Resolution.resolve_skills([
                {'libelle': "cryptographie appliquee aux paiements",
                 'niveau': 'expert', 'annees': 10}])

        called.assert_not_called()
        self.assertEqual(resolved[0]['competence_id'], self.audit.id)
        self.assertEqual(resolved[0]['matched_on'], 'referentiel')
        self.assertEqual(resolved[0]['confiance_rapprochement'], 100)
        self.assertFalse(resolved[0]['arbitrage_id'])

    def test_a_synonym_matches_without_calling_the_ai_either(self):
        """C'est la réponse à la dette D1 : une table explicite.

        Le libellé est volontairement absurde. Il l'était moins avant que le
        socle du §8 ne soit semé : « Audit SI » y figure désormais, et la
        contrainte d'unicité sur la forme normalisée faisait échouer la
        création du fixture. Règle 7 du CLAUDE.md — un test ne suppose jamais
        qu'il est seul en base, et il choisit ses libellés en conséquence.
        """
        self.Synonyme.sudo().create({
            'competence_id': self.audit.id, 'name': "Zeta Audit Fixture"})

        with patch.object(type(self.Bridge), '_ai_call_prompt') as called:
            resolved = self.Resolution.resolve_skills(
                [{'libelle': "ZETA  AUDIT FIXTURE", 'niveau': 'expert'}])

        called.assert_not_called()
        self.assertEqual(resolved[0]['competence_id'], self.audit.id)
        self.assertEqual(resolved[0]['matched_on'], 'synonyme')

    def test_the_module_still_resolves_without_any_ai_key(self):
        """Le second effet de l'étape 1, et le plus important.

        Un cluster qui n'active pas l'assistance IA garde le rapprochement
        exact et la file d'arbitrage. C'est la règle 1 du service — une panne
        ne bloque aucun parcours — vue depuis le métier.
        """
        with patch.object(type(self.Bridge), '_ai_call_prompt',
                          return_value=None):
            resolved = self.Resolution.resolve_skills([
                {'libelle': "Cryptographie appliquée aux paiements"},
                {'libelle': "Compétence inconnue au catalogue"},
            ])

        self.assertEqual(resolved[0]['competence_id'], self.audit.id)
        self.assertFalse(resolved[1]['competence_id'])
        self.assertTrue(
            resolved[1]['arbitrage_id'],
            "Sans IA, un libellé inconnu doit quand même partir en file.")

    def test_an_ambiguous_catalogue_refuses_to_choose(self):
        """Trouvé en conditions réelles, pendant l'écriture de ces tests.

        Le catalogue contenait « Audit des systemes d'information » et
        « Audit des systèmes d'information » — deux entrées que la
        normalisation rend identiques. La résolution renvoyait la première
        rencontrée, donc l'une ou l'autre selon l'ordre de recherche.

        L'expert aurait été qualifié sur une des deux au hasard, et le
        matching aurait comparé à celle que la mission avait choisie. Deux
        fois sur trois, personne ne se croise — sans qu'aucune erreur ne soit
        levée. C'est le motif exact de la dette D1.

        `opex.innovation.competence` n'a pas de contrainte d'unicité et le
        Module 2 est gelé : on ne peut pas empêcher le doublon, seulement
        refuser de choisir à la place d'un humain.
        """
        self.Competence.sudo().create({'name': "Cryptographie appliquee "
                                               "aux paiements"})

        with mute_logger(
                'odoo.addons.opex_intervenants.models.competence_synonyme'), \
                patch.object(type(self.Bridge), '_ai_call_prompt',
                             return_value=None):
            resolved = self.Resolution.resolve_skills(
                [{'libelle': "Cryptographie appliquée aux paiements"}])

        self.assertFalse(
            resolved[0]['competence_id'],
            "Le rapprochement a choisi entre deux entrées identiques du "
            "catalogue au lieu de laisser un humain trancher.")
        self.assertTrue(
            resolved[0]['arbitrage_id'],
            "Une correspondance ambiguë doit partir en arbitrage, où le "
            "gestionnaire voit les deux entrées et nettoie son catalogue.")

    def test_two_synonyms_cannot_designate_two_competences(self):
        """La résolution deviendrait non déterministe.

        Elle renverrait l'une ou l'autre selon l'ordre d'insertion, et le
        matching avec elle.
        """
        autre = self.Competence.sudo().create(
            {'name': "Autre compétence", 'code': 'tax_autre'})
        # Libellé propre au test : le socle du §8 occupe désormais « Audit
        # SI », et la contrainte que ce test éprouve se serait déclenchée sur
        # le fixture au lieu de l'assertion.
        self.Synonyme.sudo().create(
            {'competence_id': self.audit.id, 'name': "Zeta Doublon Fixture"})

        with mute_logger('odoo.sql_db'), self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.Synonyme.sudo().create({
                    'competence_id': autre.id,
                    'name': "zeta doublon fixture"}).flush_recordset()

    #
    # Étape 2 - la proposition de l'IA
    #

    def test_the_second_step_proposes_with_a_confidence(self):
        resolved = self._resolve_with_ai(
            "Contrôle des SI", {'code': 'tax_audit', 'confiance': 85,
                                'motif': "Même domaine."})

        self.assertEqual(resolved[0]['competence_id'], self.audit.id)
        self.assertEqual(resolved[0]['matched_on'], 'ia')
        self.assertEqual(resolved[0]['confiance_rapprochement'], 85)

    def test_an_ai_proposal_still_goes_through_the_arbitration_queue(self):
        """L'IA propose, l'humain décide — et le §8 ne laisse pas d'autre porte.

        Une proposition à 95 % reste une proposition : elle n'écrit rien au
        référentiel et ne rejoint pas le profil sans qu'un gestionnaire la
        valide.
        """
        resolved = self._resolve_with_ai(
            "Contrôle des SI", {'code': 'tax_audit', 'confiance': 95})

        self.assertTrue(
            resolved[0]['arbitrage_id'],
            "Une proposition de l'IA contourne la file d'arbitrage.")
        ligne = self.Arbitrage.sudo().browse(resolved[0]['arbitrage_id'])
        self.assertEqual(ligne.decision, 'pending')
        self.assertEqual(ligne.suggestion_id, self.audit)

    def test_a_code_the_model_invented_is_refused(self):
        """Un modèle invente volontiers un code plausible.

        L'accepter sur parole rattacherait la compétence à un identifiant qui
        n'existe pas — ou pire, à un qui existe et ne correspond pas.
        """
        resolved = self._resolve_with_ai(
            "Chose inconnue", {'code': 'code_invente', 'confiance': 90})

        self.assertFalse(resolved[0]['competence_id'])
        self.assertTrue(resolved[0]['arbitrage_id'])

    def test_an_unreadable_confidence_is_worth_zero(self):
        """Une confiance qu'on ne sait pas lire n'est pas une confiance haute."""
        as_percent = self.Resolution._as_percent
        self.assertEqual(as_percent(85), 85)
        self.assertEqual(as_percent("85 %"), 85)
        self.assertEqual(as_percent("0.85"), 85)
        self.assertEqual(as_percent("élevée"), 0)
        self.assertEqual(as_percent(None), 0)
        self.assertEqual(as_percent(250), 100)

    def _resolve_with_ai(self, libelle, payload):
        with patch.object(type(self.Bridge), '_ai_call_prompt',
                          return_value=payload):
            return self.Resolution.resolve_skills([{'libelle': libelle}])

    #
    # La file d'arbitrage
    #

    def test_the_same_label_asks_the_question_only_once(self):
        """Le même libellé lu sur trois CV ne pose qu'une question.

        La poser trois fois ferait trois réponses possiblement différentes.
        """
        profile = self._profile()
        with patch.object(type(self.Bridge), '_ai_call_prompt',
                          return_value=None):
            self.Resolution.resolve_skills(
                [{'libelle': "Compétence rare"}], profile=profile)
            self.Resolution.resolve_skills(
                [{'libelle': "compétence  RARE"}], profile=profile)

        lignes = self.Arbitrage.sudo().search([
            ('normalised', '=', self.Synonyme._normalise("Compétence rare"))])
        self.assertEqual(len(lignes), 1)

    def test_the_queue_records_where_the_label_came_from(self):
        """« Il journalise qui a ajouté quelle compétence et depuis quel CV. »

        La moitié « depuis quel CV » est ici ; la moitié « qui » arrive avec
        la décision.
        """
        profile = self._profile()
        with patch.object(type(self.Bridge), '_ai_call_prompt',
                          return_value=None):
            resolved = self.Resolution.resolve_skills(
                [{'libelle': "Compétence traçable", 'niveau': 'expert',
                  'annees': 7}],
                profile=profile, document="cv_zitouni.pdf")

        ligne = self.Arbitrage.sudo().browse(resolved[0]['arbitrage_id'])
        self.assertEqual(ligne.profile_id, profile)
        self.assertEqual(ligne.partner_id, self.intervenant.partner_id)
        self.assertEqual(ligne.source_document, "cv_zitouni.pdf")
        self.assertEqual(ligne.niveau_lu, 'expert')
        self.assertEqual(ligne.annees_lues, 7)

    def test_the_arbitration_is_a_decision_not_a_process(self):
        """Trois issues, un acteur, un moment, aucun retour.

        C'est la ligne de partage que le CLAUDE.md du moteur pose pour
        `roadmap.phase`. Ce test verrouille le critère : une quatrième issue,
        un chemin de refus, et la conversation a lieu.
        """
        self.assertNotIn(
            'workflow_instance_id', self.Arbitrage._fields,
            "L'arbitrage a reçu un workflow : mettez à jour ce test et le "
            "CLAUDE.md, la décision a changé.")
        self.assertEqual(
            [value for value, _l
             in self.Arbitrage._fields['decision'].selection],
            ['pending', 'linked', 'added', 'discarded'])

    #
    # L'enrichissement du catalogue - le flux décidé
    #

    def test_linking_creates_the_synonym_so_the_queue_empties_itself(self):
        """L'issue la plus utile : elle enseigne.

        Le synonyme créé fait que le même libellé sera reconnu à l'étape 1 la
        prochaine fois, sans appel IA et sans arbitrage.
        """
        ligne = self.Arbitrage.sudo().enqueue("Contrôle des SI")
        ligne.with_user(self.manager).action_link(self.audit)

        self.assertEqual(ligne.decision, 'linked')
        self.assertEqual(ligne.competence_id, self.audit)
        self.assertEqual(ligne.decided_by, self.manager)
        self.assertTrue(ligne.decided_on)

        # La question ne se reposera plus : l'étape 1 la reconnaît.
        with patch.object(type(self.Bridge), '_ai_call_prompt') as called:
            resolved = self.Resolution.resolve_skills(
                [{'libelle': "contrôle des si"}])
        called.assert_not_called()
        self.assertEqual(resolved[0]['competence_id'], self.audit.id)

    def test_adding_to_the_catalogue_enriches_the_module_2_referential(self):
        """Le référentiel reste unique — deux catalogues seraient D1 en pire.

        Le test vérifie que la compétence est bien créée dans
        `opex.innovation.competence`, celui du Module 2, et pas dans un
        catalogue parallèle du Module 3.
        """
        before = self.Competence.sudo().search_count([])
        ligne = self.Arbitrage.sudo().enqueue("Continuité d'activité")

        competence = ligne.with_user(self.manager).action_add_to_catalogue(
            domaine="Cybersécurité")

        self.assertEqual(competence._name, 'opex.innovation.competence')
        self.assertEqual(self.Competence.sudo().search_count([]), before + 1)
        self.assertEqual(competence.name, "Continuité d'activité")
        self.assertEqual(competence.domaine, "Cybersécurité")

        self.assertEqual(ligne.decision, 'added')
        self.assertEqual(ligne.competence_id, competence)
        self.assertEqual(ligne.decided_by, self.manager)

    def test_the_arbitration_is_reserved_to_the_manager(self):
        """Le contrôle est dans le modèle, pas seulement sur l'écran.

        Une action de modèle s'appelle aussi par script, par import et par
        requête forgée. `_is_missions_staff()` est LA fonction d'accès du
        module — la même que celle des routes.
        """
        ligne = self.Arbitrage.sudo().enqueue("Compétence protégée")

        for user in (self.client_user, self.intervenant):
            with self.assertRaises(UserError):
                ligne.with_user(user).action_add_to_catalogue()
            with self.assertRaises(UserError):
                ligne.with_user(user).action_link(self.audit)

        # Assertion positive : le gestionnaire, lui, peut.
        ligne.with_user(self.manager).action_discard()
        self.assertEqual(ligne.decision, 'discarded')

    def test_the_extraction_never_enriches_the_catalogue(self):
        """« Il est réservé au gestionnaire, pas ouvert à l'extraction. »

        C'est la garantie que le §8 demande : la taxonomie ne s'enrichit
        jamais par une écriture automatique. Le test fait tourner une
        extraction entière sur un libellé inconnu et compte le catalogue.
        """
        before = self.Competence.sudo().search_count([])

        resolved = self._resolve_with_ai(
            "Libellé jamais vu", {'code': '', 'confiance': 0,
                                  'motif': "Aucune correspondance."})

        self.assertEqual(
            self.Competence.sudo().search_count([]), before,
            "L'extraction a enrichi le catalogue : seul l'arbitrage le peut.")
        self.assertTrue(resolved[0]['arbitrage_id'])

    def test_the_catalogue_has_a_single_write_point_in_the_module(self):
        """Le flux doit rester nommé, pour qu'on sache d'où viennent ces lignes.

        Test de garde sur le source, docstrings et commentaires retirés : le
        seul `create()` sur `opex.innovation.competence` est celui de
        `action_add_to_catalogue`. Un `create()` dispersé ailleurs ferait
        exactement le flux qu'on découvre six mois plus tard.

        L'assertion positive qui va avec : la boucle doit avoir lu des
        fichiers.
        """
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        models_dir = os.path.join(root, 'models')
        pattern = re.compile(
            r"\[\s*['\"]opex\.innovation\.competence['\"]\s*\][^\n]*\.create")

        examined = 0
        for name in sorted(os.listdir(models_dir)):
            if not name.endswith('.py'):
                continue
            with open(os.path.join(models_dir, name), encoding='utf-8') as f:
                source = f.read()
            source = re.sub(r'("""|\'\'\')(?:.|\n)*?\1', '', source)
            source = re.sub(r'#[^\n]*', '', source)
            examined += 1

            if name == 'competence_arbitrage.py':
                self.assertTrue(
                    pattern.search(source),
                    "Le point d'écriture nommé a disparu de "
                    "`competence_arbitrage.py`.")
                continue
            self.assertIsNone(
                pattern.search(source),
                "« %s » écrit dans le référentiel du Module 2 : ce flux "
                "passe par `action_add_to_catalogue`, et par lui seul."
                % name)

        self.assertGreaterEqual(examined, 20)

    def test_an_added_competence_does_not_join_the_profile_by_itself(self):
        """Enrichir le catalogue n'est pas qualifier un expert.

        Deux gestes distincts : le premier dit qu'une compétence existe, le
        second qu'une personne la possède. Les confondre ferait qu'arbitrer
        une file qualifierait des dizaines de profils d'un coup.
        """
        profile = self._profile()
        Skill = self.env['opex.expert.skill'].sudo()
        before = Skill.search_count([('profile_id', '=', profile.id)])

        with patch.object(type(self.Bridge), '_ai_call_prompt',
                          return_value=None):
            self.Resolution.resolve_skills(
                [{'libelle': "Compétence à ajouter"}], profile=profile)

        ligne = self.Arbitrage.sudo().search(
            [('name', '=', "Compétence à ajouter")], limit=1)
        ligne.with_user(self.manager).action_add_to_catalogue()

        self.assertEqual(
            Skill.search_count([('profile_id', '=', profile.id)]), before,
            "L'arbitrage a qualifié le profil : enrichir le catalogue et "
            "qualifier un expert sont deux gestes distincts.")
