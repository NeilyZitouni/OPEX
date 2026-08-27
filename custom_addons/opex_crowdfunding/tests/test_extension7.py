from lxml import html as lxml_html

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

#: Les dix critères de la section 10, dans l'ordre du document.
CRITERES = (
    "Type de financement", "Secteur", "Ticket d'investissement",
    "Stade du projet", "Localisation", "Appétence au risque",
    "Type de porteur", "Impact", "Technologie", "Historique",
)


class MatchingCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.crowdfunding.project']
        cls.Candidate = cls.env['opex.crowdfunding.matching.candidate']
        cls.Partner = cls.env['res.partner']

        cls.porteur = new_test_user(
            cls.env, login='cf7_porteur', password='cf7_porteur',
            groups='base.group_portal', name="Rachid Belkacem")
        cls.porteur.partner_id.city = "Alger"
        cls.ceo = new_test_user(
            cls.env, login='cf7_ceo',
            groups='base.group_user,opex_crowdfunding.group_ceo')
        cls.qualite = new_test_user(
            cls.env, login='cf7_qualite',
            groups='base.group_user,opex_crowdfunding.group_quality_control')

        # L'acteur taillé pour le projet de référence : même secteur, ticket
        # englobant, stade atteint, même ville, risque assorti.
        cls.acteur_ideal = cls.Partner.create({
            'name': "Fonds Industrie DZ",
            'city': "Alger",
            'cf_is_financial_actor': True,
            'cf_actor_type': 'fonds',
            'cf_secteur': 'industrie',
            'cf_ticket_min': 5000000.0,
            'cf_ticket_max': 20000000.0,
            'cf_stade_min': 'prototype',
            'cf_appetence_risque': 'moyenne',
            'cf_localisation': "Alger",
            'cf_porteur_type_prefere': 'startup',
            'cf_interet_technologie': False,
            'cf_recherche_impact': False,
        })
        # L'acteur à contre-emploi : mauvais besoin, mauvais secteur, ticket
        # hors de portée, zone différente.
        cls.acteur_inadapte = cls.Partner.create({
            'name': "Mécénat Culturel",
            'city': "Oran",
            'cf_is_financial_actor': True,
            'cf_actor_type': 'sponsor',
            'cf_secteur': 'services',
            'cf_ticket_min': 50000.0,
            'cf_ticket_max': 200000.0,
            'cf_stade_min': 'croissance',
            'cf_appetence_risque': 'faible',
            'cf_localisation': "Oran",
            'cf_porteur_type_prefere': 'association',
        })

    def _projet(self, state='matching_financier', **valeurs):
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

    def _candidat(self, projet, partner):
        return projet.matching_candidate_ids.filtered(
            lambda c: c.partner_id == partner)


@tagged('post_install', '-at_install')
class TestExtension7Matching(MatchingCommon):
    """Extension 7 — le Smart Matching financier (section 10)."""

    # ------------------------------------------------------------------
    # La recommandation
    # ------------------------------------------------------------------
    def test_le_matching_propose_les_acteurs_du_referentiel(self):
        projet = self._projet()
        projet.with_user(self.ceo).action_run_matching()

        proposes = projet.matching_candidate_ids
        self.assertIn(self.acteur_ideal, proposes.partner_id)
        self.assertIn(self.acteur_inadapte, proposes.partner_id)
        self.assertEqual(set(proposes.mapped('state')), {'proposed'})

    def test_un_contact_qui_n_est_pas_acteur_financier_n_est_pas_propose(self):
        quidam = self.Partner.create({'name': "Contact quelconque"})
        projet = self._projet()
        projet.with_user(self.ceo).action_run_matching()
        self.assertNotIn(quidam, projet.matching_candidate_ids.partner_id)

    def test_la_liste_est_triee_par_score_decroissant(self):
        projet = self._projet()
        projet.with_user(self.ceo).action_run_matching()

        scores = projet.matching_candidate_ids.mapped('score')
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(projet.matching_candidate_ids[0].partner_id, self.acteur_ideal)

    def test_l_acteur_adapte_marque_plus_que_l_inadapte(self):
        projet = self._projet()
        projet.with_user(self.ceo).action_run_matching()

        ideal = self._candidat(projet, self.acteur_ideal)
        inadapte = self._candidat(projet, self.acteur_inadapte)
        self.assertGreater(ideal.score, inadapte.score)
        self.assertGreater(ideal.score, 70.0)
        self.assertLess(inadapte.score, 40.0)

    def test_relancer_le_matching_ne_duplique_pas_les_candidats(self):
        projet = self._projet()
        projet.with_user(self.ceo).action_run_matching()
        nombre = len(projet.matching_candidate_ids)
        projet.with_user(self.ceo).action_run_matching()
        self.assertEqual(len(projet.matching_candidate_ids), nombre)

    def test_une_exclusion_survit_a_une_relance(self):
        """Un acteur écarté par le comité le reste, quel que soit son score."""
        projet = self._projet()
        projet.with_user(self.ceo).action_run_matching()
        ideal = self._candidat(projet, self.acteur_ideal)
        score_avant = ideal.score
        ideal.with_user(self.ceo).action_exclude()

        projet.with_user(self.ceo).action_run_matching()
        self.assertEqual(ideal.state, 'excluded')
        self.assertEqual(ideal.score, score_avant, "Le score d'un exclu a été recalculé.")

    # ------------------------------------------------------------------
    # « Le matching est une recommandation »
    # ------------------------------------------------------------------
    def test_aucun_score_ne_fait_avancer_le_dossier(self):
        """Le point central de la section 10.

        Même un candidat au score maximal ne déplace rien : seule une décision
        explicite du comité fait passer le dossier en mise en relation.
        """
        projet = self._projet()
        projet.with_user(self.ceo).action_run_matching()
        parfait = self._candidat(projet, self.acteur_ideal)
        parfait.score = 100.0
        parfait.with_user(self.ceo).action_validate()

        self.assertEqual(projet.state, 'matching_financier',
                         "Un score a fait avancer le dossier tout seul.")

    def test_seule_la_validation_du_comite_met_en_relation(self):
        projet = self._projet()
        projet.with_user(self.ceo).action_run_matching()
        self._candidat(projet, self.acteur_ideal).with_user(self.ceo).action_validate()
        projet.with_user(self.ceo).action_validate_matching()
        self.assertEqual(projet.state, 'mise_en_relation')

    def test_pas_de_mise_en_relation_sans_acteur_retenu(self):
        projet = self._projet()
        projet.with_user(self.ceo).action_run_matching()
        with self.assertRaises(UserError):
            projet.with_user(self.ceo).action_validate_matching()
        self.assertEqual(projet.state, 'matching_financier')

    def test_un_acteur_exclu_ne_compte_pas_comme_retenu(self):
        projet = self._projet()
        projet.with_user(self.ceo).action_run_matching()
        projet.matching_candidate_ids.with_user(self.ceo).action_exclude()
        with self.assertRaises(UserError):
            projet.with_user(self.ceo).action_validate_matching()

    # ------------------------------------------------------------------
    # L'explication du score
    # ------------------------------------------------------------------
    def test_le_detail_expose_les_dix_criteres_et_leur_contribution(self):
        """« Un score de 91 % sans explication n'est pas défendable. »"""
        projet = self._projet()
        projet.with_user(self.ceo).action_run_matching()
        detail = self._candidat(projet, self.acteur_ideal).detail

        for libelle in CRITERES:
            self.assertIn(libelle, detail, "Le critère « %s » n'est pas expliqué." % libelle)
        self.assertIn("TOTAL", detail)
        # Chaque ligne dit d'où vient sa contribution, pas seulement combien.
        self.assertIn("secteur de prédilection de l'acteur", detail)
        self.assertIn("le besoin tombe dans la fourchette de l'acteur", detail)

    def test_les_contributions_du_detail_font_le_score(self):
        """Le détail n'est pas un texte décoratif : il redonne le total.

        Sans ce test, une explication pourrait dériver du calcul sans que
        personne ne s'en aperçoive — et c'est précisément le reproche qu'un
        jury ferait à un score inexpliqué.
        """
        projet = self._projet()
        projet.with_user(self.ceo).action_run_matching()
        candidat = self._candidat(projet, self.acteur_ideal)

        somme = 0.0
        for ligne in candidat.detail.splitlines():
            if ligne.startswith("TOTAL"):
                continue
            contribution = ligne.split(':')[1].split('/')[0]
            somme += float(contribution.strip().replace(',', '.'))
        self.assertAlmostEqual(somme, candidat.score, places=1)

    def test_un_candidat_valide_sans_explication_est_refuse(self):
        projet = self._projet()
        candidat = self.Candidate.create({
            'project_id': projet.id,
            'partner_id': self.acteur_ideal.id,
            'state': 'proposed',
        })
        with self.assertRaises(ValidationError):
            candidat.write({'state': 'validated', 'detail': "  "})

    def test_le_total_ne_depasse_jamais_cent(self):
        """Les dix poids somment à 100 : un critère mal pondéré se verrait."""
        projet = self._projet()
        projet.with_user(self.ceo).action_run_matching()
        for candidat in projet.matching_candidate_ids:
            self.assertLessEqual(candidat.score, 100.0)
            self.assertGreaterEqual(candidat.score, 0.0)

    def test_un_champ_vide_neutralise_son_critere_sans_penaliser(self):
        """« Un champ laissé vide ne pénalise pas l'acteur. »"""
        muet = self.Partner.create({
            'name': "Investisseur discret",
            'cf_is_financial_actor': True,
            'cf_actor_type': 'investisseur',
        })
        projet = self._projet()
        projet.with_user(self.ceo).action_run_matching()
        candidat = self._candidat(projet, muet)

        self.assertIn("critère neutralisé", candidat.detail)
        self.assertGreater(candidat.score, 30.0,
                           "Un profil incomplet est traité comme un mauvais profil.")

    # ------------------------------------------------------------------
    # Valider / Modifier / Exclure / Ajouter
    # ------------------------------------------------------------------
    def test_le_comite_ajoute_un_acteur_absent_de_la_recommandation(self):
        """Un acteur ajouté à la main est marqué comme tel, et scoré quand même."""
        projet = self._projet()
        hors_referentiel = self.Partner.create({
            'name': "Banque régionale",
            'cf_actor_type': 'banque',
            'cf_secteur': 'industrie',
        })
        candidat = self.Candidate.with_user(self.ceo).create({
            'project_id': projet.id,
            'partner_id': hors_referentiel.id,
            'candidate_type': 'banque',
        })
        self.assertEqual(candidat.state, 'added_manually')

        candidat.action_reevaluate()
        self.assertTrue(candidat.detail)
        candidat.action_validate()
        self.assertEqual(candidat.state, 'validated')

    def test_le_meme_acteur_ne_figure_pas_deux_fois(self):
        projet = self._projet()
        self.Candidate.create({
            'project_id': projet.id, 'partner_id': self.acteur_ideal.id})
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.Candidate.create({
                    'project_id': projet.id, 'partner_id': self.acteur_ideal.id})

    def test_valider_un_candidat_jamais_evalue_l_evalue_d_abord(self):
        projet = self._projet()
        candidat = self.Candidate.create({
            'project_id': projet.id, 'partner_id': self.acteur_ideal.id})
        candidat.with_user(self.ceo).action_validate()
        self.assertEqual(candidat.state, 'validated')
        self.assertIn("TOTAL", candidat.detail)

    # ------------------------------------------------------------------
    # Qui a le droit
    # ------------------------------------------------------------------
    @mute_logger('odoo.addons.base.models.ir_model')
    def test_seul_le_comite_ceo_pilote_le_matching(self):
        projet = self._projet()
        with self.assertRaises(AccessError):
            projet.with_user(self.qualite).action_run_matching()
        with self.assertRaises(AccessError):
            projet.with_user(self.qualite).action_validate_matching()

    def test_le_matching_ne_tourne_qu_a_son_etape(self):
        for state in ('etude_decision', 'quality_gate', 'mise_en_relation'):
            projet = self._projet(state=state)
            with self.assertRaises(UserError, msg="Matching lancé depuis %s." % state):
                projet.with_user(self.ceo).action_run_matching()


@tagged('post_install', '-at_install')
class TestExtension7Confidentialite(HttpCase, MatchingCommon):
    """Le porteur ne voit pas qui on lui cherche — c'est la section 13 qui
    ouvrira la mise en relation, pas le matching."""

    def _texte(self, page):
        document = lxml_html.fromstring(page.text)
        for element in document.xpath('//script | //style'):
            element.getparent().remove(element)
        return ' '.join(document.text_content().split())

    def test_le_porteur_ne_voit_pas_la_liste_des_acteurs(self):
        projet = self._projet()
        projet.with_user(self.ceo).action_run_matching()

        self.authenticate('cf7_porteur', 'cf7_porteur')
        page = self.url_open('/my/crowdfunding/%s' % projet.id)
        texte = self._texte(page)
        self.assertIn("Nous recherchons les acteurs financiers", texte)
        for nom in ("Fonds Industrie DZ", "Mécénat Culturel"):
            self.assertNotIn(nom, page.text,
                             "Le nom d'un acteur pressenti a fuité au porteur.")

    @mute_logger('odoo.addons.base.models.ir_rule', 'odoo.addons.base.models.ir_model')
    def test_le_porteur_n_a_aucun_droit_sur_les_candidatures(self):
        projet = self._projet()
        projet.with_user(self.ceo).action_run_matching()
        candidat = projet.matching_candidate_ids[0]
        with self.assertRaises(AccessError):
            candidat.with_user(self.porteur).read(['partner_id', 'score'])
