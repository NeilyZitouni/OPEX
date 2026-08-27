import inspect

from lxml import etree
from lxml import html as lxml_html

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

#: Les trois routes de la section 9.
ROUTES = (
    'action_route_investment_ready',
    'action_route_maturation',
    'action_route_rejected',
)


class EtudeCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.crowdfunding.project']
        cls.porteur = new_test_user(
            cls.env, login='cf6_porteur', password='cf6_porteur',
            groups='base.group_portal', name="Rachid Belkacem")
        cls.ceo = new_test_user(
            cls.env, login='cf6_ceo',
            groups='base.group_user,opex_crowdfunding.group_ceo')
        cls.qualite = new_test_user(
            cls.env, login='cf6_qualite',
            groups='base.group_user,opex_crowdfunding.group_quality_control')

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


@tagged('post_install', '-at_install')
class TestExtension6Etude(EtudeCommon):
    """Extension 6 — l'étude du comité et ses trois routes (section 9)."""

    # ------------------------------------------------------------------
    # Trois routes, trois méthodes, aucun code partagé
    # ------------------------------------------------------------------
    def test_trois_methodes_distinctes_sans_parametre_de_route(self):
        for nom in ROUTES:
            methode = getattr(type(self.Project), nom, None)
            self.assertTrue(callable(methode), "%s n'existe pas." % nom)
            self.assertEqual(
                list(inspect.signature(methode).parameters), ['self'],
                "%s prend un paramètre : la route est devenue configurable." % nom)

    def test_aucune_route_n_en_appelle_une_autre(self):
        """« Les routes B et C ne partagent aucun code. »

        Un jour, quelqu'un trouvera élégant de faire appeler la route C par la
        route B « puisque les deux terminent le dossier ». Elles ne terminent
        pas le même dossier de la même façon, et ce test le rappelle.
        """
        sources = {
            nom: inspect.getsource(getattr(type(self.Project), nom))
            for nom in ROUTES
        }
        for nom, source in sources.items():
            for autre in ROUTES:
                if autre != nom:
                    self.assertNotIn(
                        autre, source,
                        "%s fait référence à %s : les routes se sont mises à "
                        "partager du code." % (nom, autre))

    # ------------------------------------------------------------------
    # Les trois issues
    # ------------------------------------------------------------------
    def test_route_a_lance_la_recherche_de_financement(self):
        projet = self._projet()
        projet.with_user(self.ceo).action_route_investment_ready()
        self.assertEqual(projet.state, 'matching_financier')

    def test_route_b_envoie_en_accompagnement(self):
        projet = self._projet()
        projet.with_user(self.ceo).action_route_maturation()
        self.assertEqual(projet.state, 'accompagnement')

    def test_route_c_exige_un_motif(self):
        projet = self._projet()
        with self.assertRaises(UserError):
            projet.with_user(self.ceo).action_route_rejected()
        self.assertEqual(projet.state, 'etude_decision')

        projet.motif_rejet = "Le marché visé est déjà couvert par deux adhérents."
        projet.with_user(self.ceo).action_route_rejected()
        self.assertEqual(projet.state, 'rejected')

    def test_route_c_refuse_un_motif_vide(self):
        projet = self._projet(motif_rejet="   ")
        with self.assertRaises(UserError):
            projet.with_user(self.ceo).action_route_rejected()

    def test_une_route_ne_se_prend_qu_a_l_etude(self):
        for state in ('quality_gate', 'dossier_progressif', 'matching_financier'):
            projet = self._projet(state=state, motif_rejet="Motif.")
            for nom in ROUTES:
                with self.assertRaises(
                        UserError, msg="%s acceptée depuis %s." % (nom, state)):
                    getattr(projet.with_user(self.ceo), nom)()

    @mute_logger('odoo.addons.base.models.ir_model')
    def test_seul_le_comite_ceo_oriente(self):
        projet = self._projet(motif_rejet="Motif.")
        for nom in ROUTES:
            with self.assertRaises(AccessError, msg="%s ouverte au contrôle qualité." % nom):
                getattr(projet.with_user(self.qualite), nom)()
        self.assertEqual(projet.state, 'etude_decision')

    # ------------------------------------------------------------------
    # Maturation ≠ refus
    # ------------------------------------------------------------------
    def test_la_maturation_reste_dans_le_pipeline(self):
        """Le cœur de la section 9, vérifié des deux côtés à la fois."""
        maturation = self._projet()
        maturation.with_user(self.ceo).action_route_maturation()

        refus = self._projet(motif_rejet="Hors périmètre.")
        refus.with_user(self.ceo).action_route_rejected()

        self.assertTrue(maturation.in_pipeline, "La route B a sorti le projet du pipeline.")
        self.assertFalse(refus.in_pipeline)

    def test_la_maturation_apparait_dans_les_tableaux_de_bord(self):
        """La requête que font les écrans, jouée telle quelle."""
        maturation = self._projet()
        maturation.with_user(self.ceo).action_route_maturation()
        refus = self._projet(motif_rejet="Hors périmètre.")
        refus.with_user(self.ceo).action_route_rejected()

        en_cours = self.Project.search([('in_pipeline', '=', True)])
        self.assertIn(maturation, en_cours)
        self.assertNotIn(refus, en_cours)

    def test_la_maturation_ne_demande_pas_de_motif(self):
        """Exiger un motif pour la route B, ce serait la traiter en refus."""
        projet = self._projet()
        self.assertFalse(projet.motif_rejet)
        projet.with_user(self.ceo).action_route_maturation()
        self.assertEqual(projet.state, 'accompagnement')
        self.assertFalse(projet.motif_rejet)

    def test_le_filtre_en_cours_ne_recopie_pas_la_liste_des_etats(self):
        """Le filtre par défaut de la liste s'appuie sur `in_pipeline`.

        S'il recopiait les états, il finirait par diverger — et c'est la
        maturation qui en ferait les frais.
        """
        vue = self.env.ref('opex_crowdfunding.view_crowdfunding_project_search')
        arch = etree.fromstring(vue.arch.encode('utf-8'))
        filtre = arch.xpath("//filter[@name='filter_en_cours']")
        self.assertTrue(filtre)
        self.assertIn('in_pipeline', filtre[0].get('domain'))
        self.assertNotIn('accompagnement', filtre[0].get('domain'))

    # ------------------------------------------------------------------
    # L'écran d'étude
    # ------------------------------------------------------------------
    def test_le_comite_voit_l_avis_du_quality_gate(self):
        projet = self._projet(state='quality_gate')
        control = projet._open_quality_control()
        control.write({
            'completude': True, 'coherence': True, 'qualite_informations': True,
            'conformite_criteres': True, 'justificatifs': True, 'avis': 'ok',
        })
        projet.with_user(self.qualite).action_quality_ok()

        self.assertEqual(projet.state, 'etude_decision')
        self.assertEqual(projet.avis_qualite, 'ok')

    def test_l_avis_remonte_est_le_dernier_rendu(self):
        # Dossier investisseur complet : le retour du porteur en repasse par
        # `action_submit_complement()`, qui le vérifie.
        projet = self._projet(
            state='quality_gate',
            business_model="Abonnement mensuel par atelier.",
            marche="1 200 PME industrielles.",
            traction="Quatre ateliers pilotes.",
            equipe="Deux ingénieurs, un commercial.",
            besoin_financier=8000000.0,
            utilisation_fonds="Recrutement et commercialisation.",
            previsions_financieres="Rentabilité attendue en 2028.")
        premier = projet._open_quality_control()
        premier.write({'completude': False, 'anomalies': "Pièces manquantes.",
                       'avis': 'a_completer'})
        projet.with_user(self.qualite).action_quality_complement()
        self.assertEqual(projet.avis_qualite, 'a_completer')

        projet.action_submit_complement()
        second = projet._current_quality_control()
        second.write({
            'completude': True, 'coherence': True, 'qualite_informations': True,
            'conformite_criteres': True, 'justificatifs': True, 'avis': 'ok',
        })
        projet.with_user(self.qualite).action_quality_ok()
        self.assertEqual(projet.avis_qualite, 'ok')


@tagged('post_install', '-at_install')
class TestExtension6Portail(HttpCase, EtudeCommon):
    """Ce que le porteur comprend d'une route B — et ce qu'il n'en comprend pas."""

    def _connexion(self):
        self.authenticate('cf6_porteur', 'cf6_porteur')

    def _texte(self, page):
        document = lxml_html.fromstring(page.text)
        for element in document.xpath('//script | //style'):
            element.getparent().remove(element)
        return ' '.join(document.text_content().split())

    def test_un_projet_en_maturation_n_est_pas_annonce_comme_refuse(self):
        projet = self._projet()
        projet.with_user(self.ceo).action_route_maturation()

        self._connexion()
        texte = self._texte(self.url_open('/my/crowdfunding/%s' % projet.id))
        self.assertIn("Un accompagnement est en cours", texte)
        self.assertNotIn("n'a pas été retenu", texte)

    def test_un_projet_en_maturation_est_toujours_dans_son_parcours(self):
        """Côté porteur aussi, la maturation n'est pas une sortie : le jalon
        « Étude » est en cours, pas éteint."""
        maturation = self._projet()
        maturation.with_user(self.ceo).action_route_maturation()
        statuts = [jalon['status'] for jalon in maturation._portal_progress()]
        self.assertEqual(statuts, ['done', 'done', 'done', 'current', 'todo', 'todo'])

        refus = self._projet(motif_rejet="Hors périmètre.")
        refus.with_user(self.ceo).action_route_rejected()
        self.assertEqual(
            [jalon['status'] for jalon in refus._portal_progress()], ['todo'] * 6)

    def test_le_motif_du_refus_n_est_pas_jete_au_visage_du_porteur(self):
        """Le porteur apprend le refus, pas le détail de l'argumentaire
        interne : le document ne prévoit qu'une décision motivée, que le
        comité communique comme il l'entend."""
        projet = self._projet(motif_rejet="Marché déjà couvert par deux adhérents.")
        projet.with_user(self.ceo).action_route_rejected()

        self._connexion()
        texte = self._texte(self.url_open('/my/crowdfunding/%s' % projet.id))
        self.assertIn("n'a pas été retenu", texte)
        self.assertNotIn("Marché déjà couvert", texte)
