from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestExtension12DemoDay(TransactionCase):
    """L'étape Demo Day demandée à la section 18.

    « Ajoutez une étape Demo Day entre Accompagnement et Matching
    Investisseurs. Elle nécessite l'accord du CEO, une présentation Pitch Deck
    et une note ≥ 70/100. »
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.crowdfunding.project']
        cls.porteur = new_test_user(
            cls.env, login='cf12_porteur', groups='base.group_portal')
        cls.ceo = new_test_user(
            cls.env, login='cf12_ceo',
            groups='base.group_user,opex_crowdfunding.group_ceo')
        cls.qualite = new_test_user(
            cls.env, login='cf12_qualite',
            groups='base.group_user,opex_crowdfunding.group_quality_control')

    def _projet(self, state='demo_day', **valeurs):
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

    def _projet_pret(self, **valeurs):
        """Un projet au Demo Day qui remplit les trois conditions."""
        donnees = {
            'ceo_approval': True,
            'pitch_deck': b'JVBERi0xLjQgcGl0Y2g=',
            'pitch_deck_filename': "pitch.pdf",
            'score': 75,
        }
        donnees.update(valeurs)
        return self._projet(**donnees)

    # ------------------------------------------------------------------
    # L'étape s'insère au bon endroit
    # ------------------------------------------------------------------
    def test_le_demo_day_s_intercale_entre_accompagnement_et_matching(self):
        projet = self._projet(state='reevaluation')
        projet.with_user(self.ceo).action_retour_matching()
        self.assertEqual(projet.state, 'demo_day',
                         "La réévaluation mène toujours directement au matching.")

    def test_le_parcours_complet_traverse_le_demo_day(self):
        projet = self._projet(state='etude_decision')
        projet.with_user(self.ceo).action_route_maturation()
        accompagnement = projet._accompagnement_en_cours()
        accompagnement.with_user(self.ceo).action_start_diagnostic()
        accompagnement.write({
            'diagnostic': "À consolider.", 'proposition': "Deux mois.",
            'compensation_type_id': self.env.ref(
                'opex_crowdfunding.compensation_forfait').id,
        })
        accompagnement.with_user(self.ceo).action_propose()
        accompagnement.convention_acceptee = True
        accompagnement.action_accept_convention()

        mission = self.env['opex.crowdfunding.mission'].create({
            'accompagnement_id': accompagnement.id,
            'expert_id': self.env['res.partner'].create({
                'name': "Expert", 'cf_is_expert': True}).id,
            'objectif': "Go-to-market.",
        })
        livrable = self.env['opex.crowdfunding.livrable'].create({
            'mission_id': mission.id, 'name': "Plan"})
        mission.action_accept()
        livrable.action_remettre()
        livrable.with_user(self.ceo).action_valider()
        mission.action_terminate()
        accompagnement.with_user(self.ceo).action_service_fait()

        projet.with_user(self.ceo).action_reevaluation()
        projet.with_user(self.ceo).action_retour_matching()
        self.assertEqual(projet.state, 'demo_day')

        projet.write({'ceo_approval': True, 'score': 82,
                      'pitch_deck': b'JVBERi0xLjQgcGl0Y2g='})
        projet.with_user(self.ceo).action_valider_demo_day()
        self.assertEqual(projet.state, 'matching_financier')

    # ------------------------------------------------------------------
    # Les trois conditions
    # ------------------------------------------------------------------
    def test_les_trois_conditions_sont_exigees(self):
        projet = self._projet_pret()
        projet.with_user(self.ceo).action_valider_demo_day()
        self.assertEqual(projet.state, 'matching_financier')

    def test_sans_accord_du_ceo(self):
        projet = self._projet_pret(ceo_approval=False)
        with self.assertRaises(UserError) as capture:
            projet.with_user(self.ceo).action_valider_demo_day()
        self.assertIn("accord du comité CEO", capture.exception.args[0])
        self.assertEqual(projet.state, 'demo_day')

    def test_sans_pitch_deck(self):
        projet = self._projet_pret(pitch_deck=False, pitch_deck_filename=False)
        with self.assertRaises(UserError) as capture:
            projet.with_user(self.ceo).action_valider_demo_day()
        self.assertIn("Pitch Deck", capture.exception.args[0])

    def test_avec_une_note_insuffisante(self):
        projet = self._projet_pret(score=69)
        with self.assertRaises(UserError) as capture:
            projet.with_user(self.ceo).action_valider_demo_day()
        message = capture.exception.args[0]
        self.assertIn("70/100", message)
        self.assertIn("69", message)

    def test_la_note_de_soixante_dix_passe(self):
        """« ≥ 70 » : soixante-dix est dedans, pas dehors."""
        projet = self._projet_pret(score=70)
        projet.with_user(self.ceo).action_valider_demo_day()
        self.assertEqual(projet.state, 'matching_financier')

    def test_le_refus_nomme_toutes_les_conditions_manquantes(self):
        """Un refus qui dirait « conditions non remplies » ferait recommencer
        à l'aveugle."""
        projet = self._projet(ceo_approval=False, score=10)
        with self.assertRaises(UserError) as capture:
            projet.with_user(self.ceo).action_valider_demo_day()
        message = capture.exception.args[0]
        self.assertIn("accord du comité CEO", message)
        self.assertIn("Pitch Deck", message)
        self.assertIn("70/100", message)

    # ------------------------------------------------------------------
    # Garde-fous
    # ------------------------------------------------------------------
    def test_le_demo_day_ne_se_valide_qu_au_demo_day(self):
        for state in ('accompagnement', 'reevaluation', 'matching_financier'):
            projet = self._projet_pret(state=state)
            with self.assertRaises(UserError, msg="Validé depuis %s." % state):
                projet.with_user(self.ceo).action_valider_demo_day()

    @mute_logger('odoo.addons.base.models.ir_model')
    def test_seul_le_comite_valide_le_demo_day(self):
        projet = self._projet_pret()
        with self.assertRaises(AccessError):
            projet.with_user(self.qualite).action_valider_demo_day()

    def test_le_demo_day_est_dans_le_pipeline(self):
        projet = self._projet()
        self.assertTrue(projet.in_pipeline)

    def test_le_porteur_sait_ou_en_est_son_projet(self):
        """Le nouvel état doit dire quelque chose au porteur, comme les autres."""
        projet = self._projet()
        action = projet._portal_next_action()
        self.assertIn("Demo Day", action['message'])
        statuts = [jalon['status'] for jalon in projet._portal_progress()]
        self.assertEqual(statuts, ['done', 'done', 'done', 'done', 'current', 'todo'])
