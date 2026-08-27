import html
import re

from lxml import html as lxml_html

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

CSRF_TOKEN = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')
CSRF_SESSION = re.compile(r'csrf_token:\s*"([^"]+)"')

#: Les cinq actions de la section 14, dans l'ordre du document.
DECISIONS = (
    'action_decision_interesse',
    'action_decision_informations',
    'action_decision_accompagnement',
    'action_decision_rendez_vous',
    'action_decision_non_interesse',
)

#: Les sept natures d'opération de la section 15.
TYPES_OPERATION = (
    'investissement', 'partenariat', 'financement_public',
    'sponsoring', 'pret', 'convention', 'autre',
)


class ClosingCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.crowdfunding.project']
        cls.Relation = cls.env['opex.crowdfunding.relation']
        cls.Closing = cls.env['opex.crowdfunding.closing']

        cls.porteur = new_test_user(
            cls.env, login='cf10_porteur', password='cf10_porteur',
            groups='base.group_portal', name="Rachid Belkacem")
        cls.ceo = new_test_user(
            cls.env, login='cf10_ceo',
            groups='base.group_user,opex_crowdfunding.group_ceo')
        cls.investisseur = new_test_user(
            cls.env, login='cf10_investisseur', password='cf10_investisseur',
            groups='base.group_portal', name="Fonds Industrie DZ")
        cls.investisseur.partner_id.write({
            'cf_is_financial_actor': True, 'cf_actor_type': 'fonds'})

    def _projet(self, state='mise_en_relation', **valeurs):
        donnees = {
            'partner_id': self.porteur.partner_id.id,
            'name': "Supervision d'atelier",
            'porteur_type': 'startup',
            'probleme': "Pas d'outil de suivi de production.",
            'solution': "Une application de supervision d'atelier.",
            'secteur': 'industrie',
            'maturite': 'mvp',
            'besoin_type': 'investisseur',
            'besoin_financier': 8000000.0,
            'state': state,
        }
        donnees.update(valeurs)
        return self.Project.create(donnees)

    def _relation(self, projet=None, niveau='limited'):
        """Une relation à laquelle le dossier a déjà été ouvert."""
        projet = projet or self._projet()
        relation = self.Relation.create({
            'project_id': projet.id,
            'partner_id': self.investisseur.partner_id.id,
        })
        if niveau != 'teaser':
            relation.action_exprimer_interet()
            relation.with_user(self.porteur).sudo().action_autoriser_partage()
        if niveau == 'full':
            relation.with_user(self.ceo).action_ouvrir_dossier_complet()
        return relation

    def _closing_pret_a_clore(self, type_operation='investissement'):
        """Un dossier mené jusqu'au closing, pièces validées et signé."""
        relation = self._relation()
        relation.action_decision_interesse()
        projet = relation.project_id
        projet.with_user(self.ceo).action_start_closing(
            type_operation=type_operation)

        closing = projet._current_closing()
        closing.with_user(self.ceo).action_preparer_dossier()
        for document in closing.document_ids:
            document.fichier = b'ZmljaGllcg=='
            document.with_user(self.ceo).action_valider()
        exigences = closing._exigences()
        if exigences['versements']:
            self.env['opex.crowdfunding.versement'].create({
                'closing_id': closing.id,
                'name': "Première tranche",
                'montant': 4000000.0,
                'date_prevue': fields.Date.today(),
            })
        if exigences['reporting']:
            closing.reporting = "Un point d'avancement trimestriel."
        closing.with_user(self.ceo).action_confirmer_signature()
        return closing


@tagged('post_install', '-at_install')
class TestExtension10Decision(ClosingCommon):
    """Les cinq actions de l'acteur financier (section 14)."""

    def test_cinq_methodes_une_par_bouton(self):
        for nom in DECISIONS:
            self.assertTrue(
                callable(getattr(type(self.Relation), nom, None)),
                "%s n'existe pas." % nom)

    def test_interesse_fait_avancer_le_dossier(self):
        relation = self._relation()
        relation.action_decision_interesse()

        self.assertEqual(relation.decision, 'interesse')
        self.assertTrue(relation.date_decision)
        self.assertEqual(relation.project_id.state, 'decision_financeur')

    def test_besoin_d_informations_ne_fait_pas_avancer_le_dossier(self):
        """Une question n'est ni un oui ni un non."""
        relation = self._relation()
        relation.action_decision_informations(
            message="Quelle est la part de récurrent dans le chiffre d'affaires ?")

        self.assertEqual(relation.decision, 'informations')
        self.assertIn("part de récurrent", relation.message_financeur)
        self.assertEqual(relation.project_id.state, 'mise_en_relation')

    def test_une_question_vide_est_refusee(self):
        relation = self._relation()
        with self.assertRaises(UserError):
            relation.action_decision_informations(message="   ")

    def test_demander_un_accompagnement_declenche_le_sous_processus(self):
        """Le déclencheur n°2 de la section 11, atteint depuis la section 14."""
        relation = self._relation()
        relation.action_decision_accompagnement()

        accompagnement = relation.project_id._accompagnement_en_cours()
        self.assertTrue(accompagnement)
        self.assertEqual(accompagnement.origine, 'acteur_financier')
        self.assertEqual(accompagnement.requested_by_partner_id,
                         self.investisseur.partner_id)
        # Le sous-processus tourne à côté : le dossier ne bouge pas.
        self.assertEqual(relation.project_id.state, 'mise_en_relation')

    def test_proposer_un_rendez_vous(self):
        relation = self._relation()
        relation.action_decision_rendez_vous(
            date_rendez_vous="2027-03-15 10:00:00",
            message="Une heure pour parler industrialisation.")

        self.assertEqual(relation.decision, 'rendez_vous')
        self.assertTrue(relation.date_rendez_vous)
        self.assertEqual(relation.project_id.state, 'mise_en_relation')

    def test_non_interesse_n_ecarte_pas_le_projet(self):
        """Un refus sort l'acteur, pas le dossier."""
        relation = self._relation()
        relation.action_decision_non_interesse()

        self.assertEqual(relation.decision, 'non_interesse')
        self.assertEqual(relation.project_id.state, 'mise_en_relation')
        self.assertTrue(relation.project_id.in_pipeline)

    def test_aucune_decision_avant_l_ouverture_du_dossier(self):
        """Au teaser, l'acteur n'a rien lu qui permette de se prononcer."""
        relation = self._relation(niveau='teaser')
        for nom in DECISIONS:
            with self.assertRaises(UserError, msg="%s acceptée au teaser." % nom):
                getattr(relation, nom)()


@tagged('post_install', '-at_install')
class TestExtension10Closing(ClosingCommon):
    """Closing et suivi post-financement (section 15)."""

    def test_les_sept_natures_d_operation(self):
        codes = [code for code, _l in self.Closing._fields['type_operation'].selection]
        self.assertEqual(codes, list(TYPES_OPERATION))

    def test_le_closing_suit_la_decision_du_financeur(self):
        projet = self._projet()
        with self.assertRaises(UserError):
            projet.with_user(self.ceo).action_start_closing(
                type_operation='investissement')

        relation = self._relation(projet=projet)
        relation.action_decision_interesse()
        projet.with_user(self.ceo).action_start_closing(
            type_operation='investissement')

        self.assertEqual(projet.state, 'closing')
        closing = projet._current_closing()
        self.assertEqual(closing.type_operation, 'investissement')
        self.assertEqual(closing.partner_id, self.investisseur.partner_id)

    def test_une_operation_sans_nature_n_existe_pas(self):
        relation = self._relation()
        relation.action_decision_interesse()
        with self.assertRaises(UserError):
            relation.project_id.with_user(self.ceo).action_start_closing()

    def test_la_nature_de_l_operation_commande_les_pieces(self):
        """Le branchement de la section 15, vérifié sur trois natures."""
        attendus = {
            'pret': "Contrat de prêt",
            'sponsoring': "Convention de sponsoring",
            'investissement': "Pacte d'associés",
        }
        for type_operation, document in attendus.items():
            relation = self._relation()
            relation.action_decision_interesse()
            projet = relation.project_id
            projet.with_user(self.ceo).action_start_closing(
                type_operation=type_operation)
            closing = projet._current_closing()
            closing.with_user(self.ceo).action_preparer_dossier()
            self.assertIn(document, closing.document_ids.mapped('name'))

    def test_preparer_le_dossier_ne_duplique_pas_les_pieces(self):
        closing = self._closing_pret_a_clore()
        nombre = len(closing.document_ids)
        closing.with_user(self.ceo).action_preparer_dossier()
        self.assertEqual(len(closing.document_ids), nombre)

    def test_un_document_sans_fichier_ne_se_valide_pas(self):
        relation = self._relation()
        relation.action_decision_interesse()
        projet = relation.project_id
        projet.with_user(self.ceo).action_start_closing(type_operation='pret')
        closing = projet._current_closing()
        closing.with_user(self.ceo).action_preparer_dossier()

        with self.assertRaises(UserError):
            closing.document_ids[0].with_user(self.ceo).action_valider()

    def test_la_signature_attend_les_pieces(self):
        relation = self._relation()
        relation.action_decision_interesse()
        projet = relation.project_id
        projet.with_user(self.ceo).action_start_closing(type_operation='pret')
        closing = projet._current_closing()
        closing.with_user(self.ceo).action_preparer_dossier()

        with self.assertRaises(UserError) as capture:
            closing.with_user(self.ceo).action_confirmer_signature()
        self.assertIn("Contrat de prêt", capture.exception.args[0])

    def test_la_cloture_exige_signature_versements_et_reporting(self):
        relation = self._relation()
        relation.action_decision_interesse()
        projet = relation.project_id
        projet.with_user(self.ceo).action_start_closing(
            type_operation='investissement')
        closing = projet._current_closing()
        closing.with_user(self.ceo).action_preparer_dossier()

        with self.assertRaises(UserError, msg="Clôture avec des pièces non validées."):
            projet.with_user(self.ceo).action_close()

        for document in closing.document_ids:
            document.fichier = b'ZmljaGllcg=='
            document.with_user(self.ceo).action_valider()
        with self.assertRaises(UserError, msg="Clôture sans signature."):
            projet.with_user(self.ceo).action_close()

        closing.with_user(self.ceo).action_confirmer_signature()
        with self.assertRaises(UserError, msg="Clôture sans échéancier."):
            projet.with_user(self.ceo).action_close()

        self.env['opex.crowdfunding.versement'].create({
            'closing_id': closing.id, 'name': "Tranche unique",
            'montant': 8000000.0, 'date_prevue': fields.Date.today(),
        })
        with self.assertRaises(UserError, msg="Clôture sans reporting."):
            projet.with_user(self.ceo).action_close()

        closing.reporting = "Reporting trimestriel."
        projet.with_user(self.ceo).action_close()
        self.assertEqual(projet.state, 'closed')

    def test_une_nature_sans_exigence_se_clot_sans_echeancier(self):
        """« Autre » n'impose ni versement ni reporting — et c'est voulu."""
        closing = self._closing_pret_a_clore(type_operation='autre')
        self.assertFalse(closing.versement_ids)
        closing.project_id.with_user(self.ceo).action_close()
        self.assertEqual(closing.project_id.state, 'closed')

    def test_le_versement_se_constate(self):
        closing = self._closing_pret_a_clore()
        versement = closing.versement_ids[0]
        self.assertEqual(versement.state, 'prevu')
        versement.with_user(self.ceo).action_constater_versement()
        self.assertEqual(versement.state, 'verse')
        self.assertTrue(versement.date_versement)

    def test_le_projet_clos_reste_hors_pipeline(self):
        closing = self._closing_pret_a_clore()
        projet = closing.project_id
        projet.with_user(self.ceo).action_close()
        self.assertFalse(projet.in_pipeline)

    @mute_logger('odoo.addons.base.models.ir_model')
    def test_seul_le_comite_clot_le_financement(self):
        closing = self._closing_pret_a_clore()
        with self.assertRaises(AccessError):
            closing.project_id.with_user(self.investisseur).action_close()


@tagged('post_install', '-at_install')
class TestExtension10Portail(HttpCase, ClosingCommon):
    """L'acteur financier décide sans jamais voir le workflow ; le porteur
    suit son financement."""

    def _texte(self, page):
        document = lxml_html.fromstring(page.text)
        for element in document.xpath('//script | //style'):
            element.getparent().remove(element)
        return ' '.join(document.text_content().split())

    def _jeton(self, page_url):
        page = self.url_open(page_url)
        jeton = CSRF_TOKEN.search(page.text) or CSRF_SESSION.search(page.text)
        self.assertTrue(jeton, "Pas de jeton CSRF sur %s." % page_url)
        return jeton.group(1)

    def test_les_cinq_boutons_sont_a_l_ecran_sans_aucun_etat_technique(self):
        """« Il ne doit pas avoir à comprendre le workflow interne CEO. »"""
        relation = self._relation()
        self.authenticate('cf10_investisseur', 'cf10_investisseur')
        page = self.url_open('/my/crowdfunding/opportunities/%s' % relation.id)
        texte = self._texte(page)

        for libelle in ("Intéressé", "Besoin d'informations",
                        "Demander un accompagnement CEO",
                        "Proposer un rendez-vous", "Non intéressé"):
            self.assertIn(libelle, texte, "Bouton manquant : %s." % libelle)

        contenu = html.unescape(page.text)
        for code in ('mise_en_relation', 'decision_financeur', 'matching_financier',
                     'quality_gate', 'etude_decision', 'closing'):
            self.assertNotIn(code, contenu,
                             "Le code d'état « %s » est exposé à l'acteur." % code)

    def test_les_boutons_n_apparaissent_pas_au_teaser(self):
        relation = self._relation(niveau='teaser')
        self.authenticate('cf10_investisseur', 'cf10_investisseur')
        texte = self._texte(self.url_open('/my/crowdfunding/opportunities/%s' % relation.id))
        self.assertNotIn("Non intéressé", texte)

    def test_l_acteur_se_declare_interesse_depuis_son_ecran(self):
        relation = self._relation()
        url = '/my/crowdfunding/opportunities/%s' % relation.id
        self.authenticate('cf10_investisseur', 'cf10_investisseur')

        self.url_open(url + '/decision', data={
            'choix': 'interesse', 'csrf_token': self._jeton(url)})

        relation.invalidate_recordset()
        self.assertEqual(relation.decision, 'interesse')
        self.assertEqual(relation.project_id.state, 'decision_financeur')
        self.assertIn("Votre réponse a été transmise", self._texte(self.url_open(url)))

    def test_l_acteur_demande_un_accompagnement_depuis_son_ecran(self):
        relation = self._relation()
        url = '/my/crowdfunding/opportunities/%s' % relation.id
        self.authenticate('cf10_investisseur', 'cf10_investisseur')

        self.url_open(url + '/decision', data={
            'choix': 'accompagnement', 'csrf_token': self._jeton(url)})

        relation.invalidate_recordset()
        self.assertEqual(relation.decision, 'accompagnement')
        self.assertTrue(relation.project_id._accompagnement_en_cours())

    def test_un_choix_inconnu_ne_fait_rien(self):
        relation = self._relation()
        url = '/my/crowdfunding/opportunities/%s' % relation.id
        self.authenticate('cf10_investisseur', 'cf10_investisseur')

        self.url_open(url + '/decision', data={
            'choix': 'ouvrir_le_dossier_complet', 'csrf_token': self._jeton(url)})

        relation.invalidate_recordset()
        self.assertFalse(relation.decision)
        self.assertEqual(relation.niveau_acces, 'limited')

    def test_un_acteur_ne_decide_pas_pour_un_autre(self):
        relation = self._relation()
        autre = new_test_user(
            self.env, login='cf10_autre', password='cf10_autre',
            groups='base.group_portal', name="Capital Oran")
        self.authenticate('cf10_autre', 'cf10_autre')

        self.url_open('/my/crowdfunding/opportunities/%s/decision' % relation.id, data={
            'choix': 'interesse', 'csrf_token': self._jeton('/my/crowdfunding/opportunities')})

        relation.invalidate_recordset()
        self.assertFalse(relation.decision)

    def test_le_porteur_suit_son_financement(self):
        """« Le dossier devient un projet suivi plutôt qu'une candidature. »"""
        closing = self._closing_pret_a_clore()
        closing.write({
            'engagements_porteur': "Fournir les états financiers annuels.",
            'reporting': "Un point d'avancement trimestriel.",
        })
        self.env['opex.crowdfunding.suivi'].create({
            'closing_id': closing.id,
            'name': "Premier comité de suivi",
            'commentaire': "Déploiement conforme au calendrier.",
        })
        projet = closing.project_id
        projet.with_user(self.ceo).action_close()

        self.authenticate('cf10_porteur', 'cf10_porteur')
        texte = self._texte(self.url_open('/my/crowdfunding/%s' % projet.id))
        self.assertIn("Voir mon financement", texte)

        texte = self._texte(self.url_open('/my/crowdfunding/%s/financement' % projet.id))
        self.assertIn("Investissement", texte)
        self.assertIn("Première tranche", texte)
        self.assertIn("états financiers annuels", texte)
        self.assertIn("point d'avancement trimestriel", texte)
        self.assertIn("Premier comité de suivi", texte)

    @mute_logger('odoo.addons.base.models.ir_rule', 'odoo.addons.base.models.ir_model')
    def test_un_porteur_ne_voit_pas_le_financement_d_un_autre(self):
        closing = self._closing_pret_a_clore()
        autre = new_test_user(
            self.env, login='cf10_autre_porteur', password='cf10_autre_porteur',
            groups='base.group_portal', name="Amina Haddad")

        self.authenticate('cf10_autre_porteur', 'cf10_autre_porteur')
        page = self.url_open('/my/crowdfunding/%s/financement' % closing.project_id.id)
        self.assertTrue(page.url.endswith('/my/crowdfunding'))
        with self.assertRaises(AccessError):
            closing.with_user(autre).read(['montant'])
