import inspect
import re

from lxml import html as lxml_html

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

CSRF_TOKEN = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')

#: Les quatre issues du bloc « RÉSULTAT » de l'étape 2 de l'infographie.
ISSUES = ('action_go', 'action_clarify', 'action_no_go', 'action_orientation')


class CrowdfundingCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.crowdfunding.project']
        cls.Criteria = cls.env['opex.crowdfunding.criteria']
        cls.porteur = new_test_user(
            cls.env, login='cf3_porteur', password='cf3_porteur',
            groups='base.group_portal', name="Rachid Belkacem")
        cls.ceo = new_test_user(
            cls.env, login='cf3_ceo',
            groups='base.group_user,opex_crowdfunding.group_ceo')
        cls.qualite = new_test_user(
            cls.env, login='cf3_qualite',
            groups='base.group_user,opex_crowdfunding.group_quality_control')

    def _projet(self, state='pre_analyse', **valeurs):
        """Un dossier déposé, posé directement à l'état voulu."""
        donnees = {
            'partner_id': self.porteur.partner_id.id,
            'name': "Supervision d'atelier",
            'porteur_type': 'startup',
            'probleme': "Pas d'outil de suivi de production.",
            'solution': "Une application de supervision d'atelier.",
            'secteur': 'industrie',
            'maturite': 'mvp',
            'besoin_type': 'investisseur',
            'state': state,
        }
        donnees.update(valeurs)
        projet = self.Project.create(donnees)
        if state == 'pre_analyse':
            projet._current_prequalification()
        return projet


@tagged('post_install', '-at_install')
class TestExtension3PreAnalyse(CrowdfundingCommon):
    """Extension 3 — la pré-analyse et ses quatre issues (section 6)."""

    # ------------------------------------------------------------------
    # Les critères : paramétrables, comme le demande le document
    # ------------------------------------------------------------------
    def test_les_sept_criteres_sont_semes(self):
        attendus = {
            "Adéquation avec les domaines CEO",
            "Potentiel",
            "Caractère innovant",
            "Faisabilité apparente",
            "Maturité minimale",
            "Besoin identifiable",
            "Crédibilité du porteur",
        }
        semes = set(self.Criteria.search([]).mapped('name'))
        self.assertTrue(attendus <= semes, "Critères manquants : %s" % (attendus - semes))

    def test_un_critere_s_ajoute_sans_developpeur(self):
        """« Selon des critères configurables » : ils vivent en base.

        C'est l'une des deux zones où la spécification impose du paramétrable
        jusque dans le module texto — à relever tel quel dans le document de
        comparaison.
        """
        critere = self.Criteria.with_user(self.ceo).create({'name': "Impact territorial"})
        projet = self._projet()
        projet._current_prequalification().criteria_ids = critere
        self.assertIn(critere, projet.prequalification_ids.criteria_ids)

    # ------------------------------------------------------------------
    # L'entrée en pré-analyse
    # ------------------------------------------------------------------
    def test_ouverture_de_la_pre_analyse(self):
        projet = self._projet(state='depot_express')
        projet.with_user(self.ceo).action_start_pre_analyse()
        self.assertEqual(projet.state, 'pre_analyse')
        self.assertEqual(len(projet.prequalification_ids), 1)
        self.assertFalse(projet.prequalification_ids.resultat)

    def test_on_n_ouvre_pas_une_pre_analyse_sur_un_brouillon(self):
        projet = self._projet(state='draft')
        with self.assertRaises(UserError):
            projet.with_user(self.ceo).action_start_pre_analyse()
        self.assertEqual(projet.state, 'draft')

    # ------------------------------------------------------------------
    # Les quatre issues
    # ------------------------------------------------------------------
    def test_quatre_methodes_distinctes_sans_parametre_d_issue(self):
        """La manière texto, vérifiée par un test.

        Une `action_prequalify(resultat)` ferait disparaître le coût d'une
        cinquième issue — exactement ce que le benchmark final doit mesurer.
        Ce test rend le raccourci impossible à prendre par distraction.
        """
        for nom in ISSUES:
            # La fonction non liée, prise sur la classe : sur un recordset,
            # `self` serait déjà consommé et la signature paraîtrait vide.
            methode = getattr(type(self.Project), nom, None)
            self.assertTrue(callable(methode), "%s n'existe pas." % nom)
            self.assertEqual(
                list(inspect.signature(methode).parameters), ['self'],
                "%s prend un paramètre : l'issue est devenue configurable." % nom)

    def test_go(self):
        projet = self._projet()
        projet.with_user(self.ceo).action_go()
        self.assertEqual(projet.state, 'dossier_progressif')
        prequalification = projet.prequalification_ids
        self.assertEqual(prequalification.resultat, 'go')
        self.assertEqual(prequalification.evaluated_by_id, self.ceo)
        self.assertTrue(prequalification.date)

    def test_clarify_pose_les_questions_au_porteur(self):
        projet = self._projet()
        self.env['opex.crowdfunding.clarification'].create([
            {'project_id': projet.id, 'question': "Quel est votre chiffre d'affaires ?"},
            {'project_id': projet.id, 'question': "Combien d'associés ?"},
        ])
        projet.with_user(self.ceo).action_clarify()

        self.assertEqual(projet.state, 'clarification')
        self.assertEqual(set(projet.clarification_ids.mapped('state')), {'asked'})
        self.assertEqual(projet.prequalification_ids.resultat, 'clarify')

    def test_clarify_sans_question_est_refuse(self):
        """« Poser 1..N questions ciblées » : zéro n'est pas dans 1..N."""
        projet = self._projet()
        with self.assertRaises(UserError):
            projet.with_user(self.ceo).action_clarify()
        self.assertEqual(projet.state, 'pre_analyse')

    def test_no_go_exige_un_motif(self):
        projet = self._projet()
        with self.assertRaises(UserError):
            projet.with_user(self.ceo).action_no_go()
        self.assertEqual(projet.state, 'pre_analyse')

        projet.motif_rejet = "Hors des domaines d'intervention du comité."
        projet.with_user(self.ceo).action_no_go()
        self.assertEqual(projet.state, 'rejected')
        self.assertEqual(projet.prequalification_ids.resultat, 'no_go')

    def test_no_go_refuse_un_motif_vide(self):
        """Trois espaces ne sont pas une décision motivée."""
        projet = self._projet(motif_rejet="   ")
        with self.assertRaises(UserError):
            projet.with_user(self.ceo).action_no_go()

    def test_orientation_n_est_pas_un_refus(self):
        """« Un projet intéressant mais insuffisamment mature reste dans le
        pipeline » — il part en accompagnement, pas à la corbeille."""
        projet = self._projet()
        projet.with_user(self.ceo).action_orientation()
        self.assertEqual(projet.state, 'accompagnement')
        self.assertNotEqual(projet.state, 'rejected')
        self.assertEqual(projet.prequalification_ids.resultat, 'orientation')

    def test_une_issue_ne_se_prend_qu_en_pre_analyse(self):
        projet = self._projet(state='depot_express')
        for nom in ISSUES:
            with self.assertRaises(UserError, msg="%s a été acceptée hors pré-analyse." % nom):
                getattr(projet.with_user(self.ceo), nom)()

    @mute_logger('odoo.addons.base.models.ir_model')
    def test_seul_le_comite_ceo_decide(self):
        """Les boutons sont filtrés par groupe dans la vue ; l'appel direct,
        lui, doit être refusé aussi."""
        projet = self._projet()
        with self.assertRaises(AccessError):
            projet.with_user(self.qualite).action_go()
        self.assertEqual(projet.state, 'pre_analyse')

    # ------------------------------------------------------------------
    # La boucle de clarification
    # ------------------------------------------------------------------
    def test_le_dossier_revient_en_pre_analyse_avec_une_nouvelle_fiche(self):
        projet = self._projet()
        self.env['opex.crowdfunding.clarification'].create(
            {'project_id': projet.id, 'question': "Quel chiffre d'affaires ?"})
        projet.with_user(self.ceo).action_clarify()

        projet.clarification_ids.write({'reponse': "1,2 MDA en 2025.", 'state': 'answered'})
        projet.action_clarifications_answered()

        self.assertEqual(projet.state, 'pre_analyse')
        # Deux fiches : la lecture d'avant les questions, et celle d'après.
        # L'historique des deux décisions reste lisible côté comité.
        self.assertEqual(len(projet.prequalification_ids), 2)
        self.assertFalse(projet._current_prequalification().resultat)

    def test_un_questionnaire_incomplet_ne_repart_pas_au_comite(self):
        projet = self._projet()
        self.env['opex.crowdfunding.clarification'].create([
            {'project_id': projet.id, 'question': "Première question ?"},
            {'project_id': projet.id, 'question': "Deuxième question ?"},
        ])
        projet.with_user(self.ceo).action_clarify()
        projet.clarification_ids[0].write({'reponse': "Réponse.", 'state': 'answered'})

        with self.assertRaises(UserError):
            projet.action_clarifications_answered()
        self.assertEqual(projet.state, 'clarification')

    @mute_logger('odoo.addons.base.models.ir_rule', 'odoo.addons.base.models.ir_model')
    def test_la_regle_cache_au_porteur_les_questions_en_preparation(self):
        """Le portail rend en `sudo()` : la règle est le second verrou."""
        projet = self._projet()
        brouillon = self.env['opex.crowdfunding.clarification'].create({
            'project_id': projet.id, 'question': "Brouillon interne du comité",
        })
        with self.assertRaises(AccessError):
            brouillon.with_user(self.porteur).read(['question'])

    def test_on_ne_repond_pas_a_un_dossier_qui_n_attend_rien(self):
        projet = self._projet()
        with self.assertRaises(UserError):
            projet.action_clarifications_answered()


@tagged('post_install', '-at_install')
class TestExtension3Portail(HttpCase, CrowdfundingCommon):
    """Le porteur répond depuis son portail, sans jamais voir le workflow."""

    def _connexion(self):
        self.authenticate('cf3_porteur', 'cf3_porteur')

    def _texte(self, page):
        document = lxml_html.fromstring(page.text)
        for element in document.xpath('//script | //style'):
            element.getparent().remove(element)
        return ' '.join(document.text_content().split())

    def _poster(self, url, donnees):
        page = self.url_open(url)
        jeton = CSRF_TOKEN.search(page.text)
        self.assertTrue(jeton, "Pas de jeton CSRF sur %s." % url)
        return self.url_open(url, data=dict(donnees, csrf_token=jeton.group(1)))

    def _projet_en_clarification(self, questions):
        projet = self._projet()
        self.env['opex.crowdfunding.clarification'].create([
            {'project_id': projet.id, 'question': question} for question in questions
        ])
        projet.with_user(self.ceo).action_clarify()
        return projet

    def test_le_suivi_propose_le_bouton_repondre(self):
        projet = self._projet_en_clarification(["Quel chiffre d'affaires ?"])
        self._connexion()
        page = self.url_open('/my/projects/%s' % projet.id)
        texte = self._texte(page)

        self.assertIn("Votre prochaine action", texte)
        self.assertIn("Répondre aux questions", texte)
        self.assertIn('/my/projects/%s/clarifications' % projet.id, page.text)

    def test_le_porteur_repond_et_le_dossier_repart(self):
        projet = self._projet_en_clarification(
            ["Quel chiffre d'affaires ?", "Combien d'associés ?"])
        self._connexion()

        reponse = self._poster('/my/projects/%s/clarifications' % projet.id, {
            'reponse_%s' % projet.clarification_ids[0].id: "1,2 MDA en 2025.",
            'reponse_%s' % projet.clarification_ids[1].id: "Trois associés.",
        })

        self.assertTrue(reponse.url.endswith('/my/projects/%s' % projet.id))
        projet.invalidate_recordset()
        self.assertEqual(projet.state, 'pre_analyse')
        self.assertEqual(set(projet.clarification_ids.mapped('state')), {'answered'})
        # Le porteur retrouve ses réponses sur le suivi de son projet.
        self.assertIn("1,2 MDA en 2025.", self._texte(reponse))

    def test_une_reponse_partielle_est_conservee(self):
        """Progressive commitment : ce qui est saisi n'est jamais perdu."""
        projet = self._projet_en_clarification(
            ["Quel chiffre d'affaires ?", "Combien d'associés ?"])
        self._connexion()
        premiere, seconde = projet.clarification_ids

        reponse = self._poster('/my/projects/%s/clarifications' % projet.id, {
            'reponse_%s' % premiere.id: "1,2 MDA en 2025.",
        })

        projet.invalidate_recordset()
        self.assertEqual(projet.state, 'clarification', "Le dossier est reparti trop tôt.")
        self.assertEqual(premiere.state, 'answered')
        self.assertEqual(seconde.state, 'asked')
        texte = self._texte(reponse)
        self.assertIn("1,2 MDA en 2025.", texte)
        self.assertIn("Répondez à toutes les questions", texte)

    def test_une_question_en_preparation_reste_invisible(self):
        """Une question que le comité rédige encore n'est pas une question posée.

        « Présent dans le HTML » suffirait ici à la montrer au porteur.
        """
        projet = self._projet_en_clarification(["Question envoyée ?"])
        self.env['opex.crowdfunding.clarification'].create({
            'project_id': projet.id,
            'question': "Brouillon interne du comité",
        })
        self._connexion()

        for url in ('/my/projects/%s' % projet.id,
                    '/my/projects/%s/clarifications' % projet.id):
            page = self.url_open(url)
            self.assertIn("Question envoyée ?", self._texte(page))
            self.assertNotIn("Brouillon interne", page.text,
                             "Une question en préparation a fuité sur %s." % url)

    def test_un_porteur_ne_repond_pas_aux_questions_d_un_autre(self):
        autre = new_test_user(
            self.env, login='cf3_autre', password='cf3_autre',
            groups='base.group_portal', name="Amina Haddad")
        projet = self._projet_en_clarification(["Question réservée ?"])
        projet.partner_id = autre.partner_id

        self._connexion()
        page = self.url_open('/my/projects/%s/clarifications' % projet.id)
        self.assertTrue(page.url.endswith('/my/projects'))
        self.assertNotIn("Question réservée", self._texte(page))

    def test_aucun_code_d_etat_sur_l_ecran_de_reponse(self):
        projet = self._projet_en_clarification(["Quel chiffre d'affaires ?"])
        self._connexion()
        page = self.url_open('/my/projects/%s/clarifications' % projet.id)
        for code in ('pre_analyse', 'clarification', 'dossier_progressif'):
            self.assertNotIn(code, self._texte(page))
