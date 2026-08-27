import re

from lxml import html as lxml_html

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

CSRF_TOKEN = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')

#: Les neuf contreparties citées par la section 12.
CONTREPARTIES = (
    "Forfait", "Commission au succès", "Success fee", "Participation",
    "Abonnement", "Prestation d'accompagnement", "Sponsoring",
    "Gratuité dans le cadre d'un programme", "Autre convention",
)


class AccompagnementCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.crowdfunding.project']
        cls.Accompagnement = cls.env['opex.crowdfunding.accompagnement']
        cls.Mission = cls.env['opex.crowdfunding.mission']
        cls.Compensation = cls.env['opex.crowdfunding.compensation.type']

        cls.porteur = new_test_user(
            cls.env, login='cf8_porteur', password='cf8_porteur',
            groups='base.group_portal', name="Rachid Belkacem")
        cls.ceo = new_test_user(
            cls.env, login='cf8_ceo',
            groups='base.group_user,opex_crowdfunding.group_ceo')
        cls.qualite = new_test_user(
            cls.env, login='cf8_qualite',
            groups='base.group_user,opex_crowdfunding.group_quality_control')

        cls.expert = cls.env['res.partner'].create({
            'name': "Nadia Cherif",
            'cf_is_expert': True,
            'cf_expertise': "Business model, go-to-market",
            'cf_expertise_secteur': 'industrie',
        })
        cls.forfait = cls.env.ref('opex_crowdfunding.compensation_forfait')

    def _projet(self, state='etude_decision', **valeurs):
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
        return self.Project.create(donnees)

    def _accompagnement_actif(self, projet=None):
        """Un accompagnement mené jusqu'à l'état actif, convention acceptée."""
        projet = projet or self._projet()
        projet.with_user(self.ceo).action_route_maturation()
        accompagnement = projet._accompagnement_en_cours()
        accompagnement.with_user(self.ceo).action_start_diagnostic()
        accompagnement.write({
            'diagnostic': "Business model à consolider avant toute levée.",
            'proposition': "Deux mois d'accompagnement sur le go-to-market.",
            'compensation_type_id': self.forfait.id,
            'compensation_detail': "150 000 DA, payables à mi-parcours.",
        })
        accompagnement.with_user(self.ceo).action_propose()
        accompagnement.convention_acceptee = True
        accompagnement.action_accept_convention()
        return accompagnement

    def _mission_terminee(self, accompagnement):
        mission = self.Mission.create({
            'accompagnement_id': accompagnement.id,
            'expert_id': self.expert.id,
            'objectif': "Refonte du go-to-market.",
        })
        self.env['opex.crowdfunding.jalon'].create({
            'mission_id': mission.id,
            'name': "Atelier de cadrage",
            'date_prevue': fields.Date.today(),
            'state': 'atteint',
        })
        livrable = self.env['opex.crowdfunding.livrable'].create({
            'mission_id': mission.id,
            'name': "Plan de commercialisation",
        })
        mission.action_accept()
        livrable.action_remettre()
        livrable.with_user(self.ceo).action_valider()
        mission.action_terminate()
        return mission


@tagged('post_install', '-at_install')
class TestExtension8Declencheurs(AccompagnementCommon):
    """Les trois déclencheurs de la section 11, tous les trois."""

    def test_declencheur_1_recommandation_du_comite(self):
        """Route B de l'étude : le sous-processus s'ouvre séance tenante."""
        projet = self._projet()
        projet.with_user(self.ceo).action_route_maturation()

        accompagnement = projet._accompagnement_en_cours()
        self.assertTrue(accompagnement)
        self.assertEqual(accompagnement.origine, 'ceo_recommandation')
        self.assertEqual(accompagnement.state, 'demande')
        # Ici, et seulement ici, le dossier bascule dans l'étape accompagnement.
        self.assertEqual(projet.state, 'accompagnement')

    def test_declencheur_2_condition_d_un_acteur_financier(self):
        projet = self._projet(state='mise_en_relation')
        projet.with_user(self.ceo).action_accompagnement_demande_financeur()

        accompagnement = projet._accompagnement_en_cours()
        self.assertEqual(accompagnement.origine, 'acteur_financier')
        # Le dossier ne quitte pas son étape : le sous-workflow tourne à côté.
        self.assertEqual(projet.state, 'mise_en_relation')

    def test_declencheur_2_ne_s_invoque_pas_avant_la_mise_en_relation(self):
        for state in ('depot_express', 'pre_analyse', 'quality_gate', 'etude_decision'):
            projet = self._projet(state=state)
            with self.assertRaises(UserError, msg="Accepté depuis %s." % state):
                projet.with_user(self.ceo).action_accompagnement_demande_financeur()

    def test_declencheur_3_demande_du_porteur_a_tout_moment_autorise(self):
        """« À tout moment autorisé du parcours » — et le dossier ne bouge pas.

        Un porteur qui demande de l'aide pendant que son dossier est au
        contrôle qualité ne doit pas sortir du contrôle qualité.
        """
        for state in ('depot_express', 'quality_gate', 'etude_decision',
                      'mise_en_relation'):
            projet = self._projet(state=state)
            projet.action_accompagnement_demande_porteur(demande="J'ai besoin d'aide.")
            accompagnement = projet._accompagnement_en_cours()
            self.assertEqual(accompagnement.origine, 'porteur')
            self.assertEqual(accompagnement.demande, "J'ai besoin d'aide.")
            self.assertEqual(projet.state, state,
                             "La demande du porteur a dérouté le dossier.")

    def test_declencheur_3_refuse_avant_le_depot_et_apres_la_sortie(self):
        for state in ('draft', 'rejected', 'closed', 'accompagnement', 'reevaluation'):
            projet = self._projet(state=state)
            with self.assertRaises(UserError, msg="Accepté depuis %s." % state):
                projet.action_accompagnement_demande_porteur()

    def test_un_seul_accompagnement_a_la_fois(self):
        projet = self._projet(state='quality_gate')
        projet.action_accompagnement_demande_porteur()
        with self.assertRaises(UserError):
            projet.action_accompagnement_demande_porteur()

    def test_un_accompagnement_clos_laisse_la_place_a_un_autre(self):
        projet = self._projet(state='quality_gate')
        projet.action_accompagnement_demande_porteur()
        projet._accompagnement_en_cours().state = 'refuse'
        projet.action_accompagnement_demande_porteur()
        self.assertEqual(len(projet.accompagnement_ids), 2)

    def test_les_trois_origines_sont_distinctes_et_conservees(self):
        """L'origine reste inscrite : on ne traite pas de la même façon un
        accompagnement qu'on a proposé et un qu'on nous a demandé."""
        origines = [code for code, _l in self.Accompagnement._fields['origine'].selection]
        self.assertEqual(
            origines, ['ceo_recommandation', 'acteur_financier', 'porteur'])


@tagged('post_install', '-at_install')
class TestExtension8SousProcessus(AccompagnementCommon):
    """demande → diagnostic → proposition → contrepartie → acceptation →
    missions → jalons → livrables → service fait → évaluation."""

    def test_la_proposition_exige_diagnostic_proposition_et_contrepartie(self):
        projet = self._projet()
        projet.with_user(self.ceo).action_route_maturation()
        accompagnement = projet._accompagnement_en_cours()
        accompagnement.with_user(self.ceo).action_start_diagnostic()

        with self.assertRaises(UserError):
            accompagnement.with_user(self.ceo).action_propose()

        accompagnement.diagnostic = "Business model à consolider."
        with self.assertRaises(UserError):
            accompagnement.with_user(self.ceo).action_propose()

        accompagnement.proposition = "Deux mois sur le go-to-market."
        with self.assertRaises(UserError, msg="Proposition acceptée sans contrepartie."):
            accompagnement.with_user(self.ceo).action_propose()

        accompagnement.compensation_type_id = self.forfait
        accompagnement.with_user(self.ceo).action_propose()
        self.assertEqual(accompagnement.state, 'propose')

    def test_la_convention_acceptee_conditionne_l_activation(self):
        """Section 12, mot pour mot : « Accompagnement proposé →
        Accompagnement actif » a pour précondition « Convention acceptée =
        TRUE »."""
        projet = self._projet()
        projet.with_user(self.ceo).action_route_maturation()
        accompagnement = projet._accompagnement_en_cours()
        accompagnement.with_user(self.ceo).action_start_diagnostic()
        accompagnement.write({
            'diagnostic': "Diagnostic.",
            'proposition': "Proposition.",
            'compensation_type_id': self.forfait.id,
        })
        accompagnement.with_user(self.ceo).action_propose()

        self.assertFalse(accompagnement.convention_acceptee)
        with self.assertRaises(UserError):
            accompagnement.action_accept_convention()
        self.assertEqual(accompagnement.state, 'propose')

        accompagnement.convention_acceptee = True
        accompagnement.action_accept_convention()
        self.assertEqual(accompagnement.state, 'actif')
        self.assertTrue(accompagnement.date_acceptation)

    def test_le_porteur_peut_refuser_la_proposition(self):
        accompagnement = self._accompagnement_actif()
        # On rejoue une proposition sur un second projet pour la refuser.
        projet = self._projet()
        projet.with_user(self.ceo).action_route_maturation()
        seconde = projet._accompagnement_en_cours()
        seconde.with_user(self.ceo).action_start_diagnostic()
        seconde.write({'diagnostic': "D.", 'proposition': "P.",
                       'compensation_type_id': self.forfait.id})
        seconde.with_user(self.ceo).action_propose()
        seconde.action_refuse_convention()

        self.assertEqual(seconde.state, 'refuse')
        self.assertEqual(accompagnement.state, 'actif')

    def test_le_service_fait_exige_missions_terminees_et_livrables_valides(self):
        accompagnement = self._accompagnement_actif()

        with self.assertRaises(UserError, msg="Service fait sans mission."):
            accompagnement.with_user(self.ceo).action_service_fait()

        mission = self.Mission.create({
            'accompagnement_id': accompagnement.id,
            'expert_id': self.expert.id,
            'objectif': "Refonte du go-to-market.",
        })
        with self.assertRaises(UserError, msg="Service fait avec une mission en cours."):
            accompagnement.with_user(self.ceo).action_service_fait()

        livrable = self.env['opex.crowdfunding.livrable'].create({
            'mission_id': mission.id, 'name': "Plan de commercialisation"})
        mission.action_accept()
        with self.assertRaises(UserError, msg="Mission terminée sans livrable validé."):
            mission.action_terminate()

        livrable.action_remettre()
        livrable.with_user(self.ceo).action_valider()
        mission.action_terminate()
        accompagnement.with_user(self.ceo).action_service_fait()
        self.assertEqual(accompagnement.state, 'service_fait')

    def test_la_cloture_exige_une_evaluation(self):
        accompagnement = self._accompagnement_actif()
        self._mission_terminee(accompagnement)
        accompagnement.with_user(self.ceo).action_service_fait()

        with self.assertRaises(UserError):
            accompagnement.with_user(self.ceo).action_evaluate()

        self.env['opex.crowdfunding.evaluation'].create({
            'accompagnement_id': accompagnement.id,
            'note': 4,
            'commentaire': "Accompagnement utile, jalons tenus.",
        })
        accompagnement.with_user(self.ceo).action_evaluate()
        self.assertEqual(accompagnement.state, 'evalue')

    def test_l_expert_accepte_ou_decline(self):
        """Les deux boutons de la section 16, côté expert."""
        accompagnement = self._accompagnement_actif()
        mission = self.Mission.create({
            'accompagnement_id': accompagnement.id,
            'expert_id': self.expert.id,
            'objectif': "Diagnostic technique.",
        })
        self.assertEqual(mission.state, 'proposee')
        mission.action_decline()
        self.assertEqual(mission.state, 'declinee')
        with self.assertRaises(UserError):
            mission.action_accept()

    def test_un_livrable_refuse_dit_pourquoi(self):
        accompagnement = self._accompagnement_actif()
        mission = self.Mission.create({
            'accompagnement_id': accompagnement.id,
            'expert_id': self.expert.id,
            'objectif': "Diagnostic technique.",
        })
        livrable = self.env['opex.crowdfunding.livrable'].create({
            'mission_id': mission.id, 'name': "Note de cadrage"})
        livrable.action_remettre()

        with self.assertRaises(UserError):
            livrable.with_user(self.ceo).action_refuser()
        livrable.commentaire = "Le chiffrage manque."
        livrable.with_user(self.ceo).action_refuser()
        self.assertEqual(livrable.state, 'refuse')

    def test_les_experts_du_secteur_sont_suggeres(self):
        accompagnement = self._accompagnement_actif()
        self.assertIn(self.expert, accompagnement.expert_suggestion_ids)

        autre_secteur = self.env['res.partner'].create({
            'name': "Expert santé", 'cf_is_expert': True,
            'cf_expertise_secteur': 'sante'})
        accompagnement.invalidate_recordset()
        self.assertNotIn(autre_secteur, accompagnement.expert_suggestion_ids)

    @mute_logger('odoo.addons.base.models.ir_model')
    def test_seul_le_comite_conduit_le_sous_processus(self):
        projet = self._projet()
        projet.with_user(self.ceo).action_route_maturation()
        accompagnement = projet._accompagnement_en_cours()
        with self.assertRaises(AccessError):
            accompagnement.with_user(self.qualite).action_start_diagnostic()


@tagged('post_install', '-at_install')
class TestExtension8Contrepartie(AccompagnementCommon):
    """Section 12 — « Le workflow ne doit pas coder en dur le modèle économique. »"""

    def test_les_neuf_contreparties_sont_semees(self):
        semees = set(self.Compensation.search([]).mapped('name'))
        for libelle in CONTREPARTIES:
            self.assertIn(libelle, semees)

    def test_la_contrepartie_est_un_referentiel_pas_un_selection(self):
        """Le test structurel qui garde la zone paramétrable.

        Si quelqu'un remplace un jour ce Many2one par un Selection « c'est
        plus simple », il aura codé en dur le modèle économique — exactement
        ce que la section 12 interdit. Ce test le dit tout de suite.
        """
        champ = self.Accompagnement._fields['compensation_type_id']
        self.assertEqual(champ.type, 'many2one')
        self.assertEqual(champ.comodel_name, 'opex.crowdfunding.compensation.type')

    def test_une_contrepartie_s_ajoute_sans_developpeur(self):
        """Un modèle économique inventé demain, sans redéploiement."""
        royalties = self.Compensation.with_user(self.ceo).create({
            'name': "Royalties sur chiffre d'affaires",
            'description': "3 % du CA pendant cinq ans.",
        })
        projet = self._projet()
        projet.with_user(self.ceo).action_route_maturation()
        accompagnement = projet._accompagnement_en_cours()
        accompagnement.with_user(self.ceo).action_start_diagnostic()
        accompagnement.write({
            'diagnostic': "D.", 'proposition': "P.",
            'compensation_type_id': royalties.id,
        })
        accompagnement.with_user(self.ceo).action_propose()
        self.assertEqual(accompagnement.compensation_type_id, royalties)

    def test_la_contrepartie_de_l_expert_vient_du_meme_referentiel(self):
        champ = self.Mission._fields['contrepartie_type_id']
        self.assertEqual(champ.comodel_name, 'opex.crowdfunding.compensation.type')


@tagged('post_install', '-at_install')
class TestExtension8Boucle(AccompagnementCommon):
    """La boucle de réévaluation — ce qui distingue ce processus d'une séquence."""

    def test_la_reevaluation_suit_un_accompagnement_abouti(self):
        accompagnement = self._accompagnement_actif()
        projet = accompagnement.project_id

        with self.assertRaises(UserError, msg="Réévaluation avant le service fait."):
            projet.with_user(self.ceo).action_reevaluation()

        self._mission_terminee(accompagnement)
        accompagnement.with_user(self.ceo).action_service_fait()
        projet.with_user(self.ceo).action_reevaluation()
        self.assertEqual(projet.state, 'reevaluation')

    def test_la_boucle_complete_ramene_au_matching(self):
        """Étude → route B → accompagnement → service fait → réévaluation →
        Demo Day → matching financier. Le dossier revient là d'où il aurait pu
        partir directement, mais mûri.

        Le Demo Day (section 18) s'est intercalé sur ce chemin : la boucle
        existe toujours, elle compte une étape de plus.
        """
        projet = self._projet()
        projet.with_user(self.ceo).action_route_maturation()
        self.assertEqual(projet.state, 'accompagnement')

        accompagnement = projet._accompagnement_en_cours()
        accompagnement.with_user(self.ceo).action_start_diagnostic()
        accompagnement.write({
            'diagnostic': "Business model à consolider.",
            'proposition': "Deux mois d'accompagnement.",
            'compensation_type_id': self.forfait.id,
        })
        accompagnement.with_user(self.ceo).action_propose()
        accompagnement.convention_acceptee = True
        accompagnement.action_accept_convention()
        self._mission_terminee(accompagnement)
        accompagnement.with_user(self.ceo).action_service_fait()

        projet.with_user(self.ceo).action_reevaluation()
        projet.with_user(self.ceo).action_retour_matching()
        self.assertEqual(projet.state, 'demo_day')

        projet.write({'ceo_approval': True, 'score': 80,
                      'pitch_deck': b'JVBERi0xLjQgcGl0Y2g='})
        projet.with_user(self.ceo).action_valider_demo_day()

        self.assertEqual(projet.state, 'matching_financier')
        self.assertTrue(projet.in_pipeline)

    def test_la_reevaluation_ne_part_pas_de_n_importe_ou(self):
        for state in ('etude_decision', 'quality_gate', 'matching_financier'):
            projet = self._projet(state=state)
            with self.assertRaises(UserError, msg="Réévaluation depuis %s." % state):
                projet.with_user(self.ceo).action_reevaluation()

    def test_le_retour_au_matching_ne_part_que_de_la_reevaluation(self):
        projet = self._projet(state='accompagnement')
        with self.assertRaises(UserError):
            projet.with_user(self.ceo).action_retour_matching()

    @mute_logger('odoo.addons.base.models.ir_model')
    def test_seul_le_comite_referme_la_boucle(self):
        projet = self._projet(state='reevaluation')
        with self.assertRaises(AccessError):
            projet.with_user(self.qualite).action_retour_matching()


@tagged('post_install', '-at_install')
class TestExtension8Portail(HttpCase, AccompagnementCommon):
    """Le porteur demande, lit la proposition, accepte ou refuse."""

    def _connexion(self):
        self.authenticate('cf8_porteur', 'cf8_porteur')

    def _texte(self, page):
        document = lxml_html.fromstring(page.text)
        for element in document.xpath('//script | //style'):
            element.getparent().remove(element)
        return ' '.join(document.text_content().split())

    def _poster(self, url, donnees=None):
        page = self.url_open(url)
        jeton = CSRF_TOKEN.search(page.text)
        self.assertTrue(jeton, "Pas de jeton CSRF sur %s." % url)
        return self.url_open(url, data=dict(donnees or {}, csrf_token=jeton.group(1)))

    def test_le_porteur_demande_un_accompagnement(self):
        projet = self._projet(state='quality_gate')
        self._connexion()

        texte = self._texte(self.url_open('/my/crowdfunding/%s' % projet.id))
        self.assertIn("Être accompagné par CEO", texte)

        self._poster('/my/crowdfunding/%s/accompagnement/demander' % projet.id,
                     {'demande': "Je cale sur mon business model."})

        projet.invalidate_recordset()
        accompagnement = projet._accompagnement_en_cours()
        self.assertEqual(accompagnement.origine, 'porteur')
        self.assertEqual(accompagnement.demande, "Je cale sur mon business model.")
        self.assertEqual(projet.state, 'quality_gate')

    def test_le_bouton_disparait_quand_la_demande_n_a_pas_de_sens(self):
        projet = self._projet(state='draft')
        self._connexion()
        texte = self._texte(self.url_open('/my/crowdfunding/%s' % projet.id))
        self.assertNotIn("Être accompagné par CEO", texte)

    def test_le_porteur_lit_la_proposition_et_sa_contrepartie(self):
        projet = self._projet()
        projet.with_user(self.ceo).action_route_maturation()
        accompagnement = projet._accompagnement_en_cours()
        accompagnement.with_user(self.ceo).action_start_diagnostic()
        accompagnement.write({
            'diagnostic': "Diagnostic interne réservé au comité.",
            'proposition': "Deux mois d'accompagnement sur le go-to-market.",
            'compensation_type_id': self.forfait.id,
            'compensation_detail': "150 000 DA, payables à mi-parcours.",
        })
        accompagnement.with_user(self.ceo).action_propose()

        self._connexion()
        texte = self._texte(
            self.url_open('/my/crowdfunding/%s/accompagnement' % projet.id))
        self.assertIn("Deux mois d'accompagnement", texte)
        self.assertIn("Forfait", texte)
        self.assertIn("150 000 DA", texte)
        # Le diagnostic est un document de travail du comité.
        self.assertNotIn("Diagnostic interne", texte)

    def test_le_porteur_accepte_la_convention(self):
        projet = self._projet()
        projet.with_user(self.ceo).action_route_maturation()
        accompagnement = projet._accompagnement_en_cours()
        accompagnement.with_user(self.ceo).action_start_diagnostic()
        accompagnement.write({'diagnostic': "D.", 'proposition': "P.",
                              'compensation_type_id': self.forfait.id})
        accompagnement.with_user(self.ceo).action_propose()

        self._connexion()
        self._poster('/my/crowdfunding/%s/accompagnement' % projet.id)

        accompagnement.invalidate_recordset()
        self.assertTrue(accompagnement.convention_acceptee)
        self.assertEqual(accompagnement.state, 'actif')

    def test_le_porteur_refuse_la_convention(self):
        projet = self._projet()
        projet.with_user(self.ceo).action_route_maturation()
        accompagnement = projet._accompagnement_en_cours()
        accompagnement.with_user(self.ceo).action_start_diagnostic()
        accompagnement.write({'diagnostic': "D.", 'proposition': "P.",
                              'compensation_type_id': self.forfait.id})
        accompagnement.with_user(self.ceo).action_propose()

        self._connexion()
        self._poster('/my/crowdfunding/%s/accompagnement' % projet.id, {'refuser': '1'})

        accompagnement.invalidate_recordset()
        self.assertEqual(accompagnement.state, 'refuse')
        self.assertFalse(accompagnement.convention_acceptee)

    @mute_logger('odoo.addons.base.models.ir_rule', 'odoo.addons.base.models.ir_model')
    def test_un_porteur_ne_voit_pas_l_accompagnement_d_un_autre(self):
        autre = new_test_user(
            self.env, login='cf8_autre', password='cf8_autre',
            groups='base.group_portal', name="Amina Haddad")
        projet = self._projet(state='quality_gate', partner_id=autre.partner_id.id)
        projet.action_accompagnement_demande_porteur(demande="Demande d'Amina.")
        accompagnement = projet._accompagnement_en_cours()

        self._connexion()
        page = self.url_open('/my/crowdfunding/%s/accompagnement' % projet.id)
        self.assertTrue(page.url.endswith('/my/crowdfunding'))
        with self.assertRaises(AccessError):
            accompagnement.with_user(self.porteur).read(['diagnostic'])
