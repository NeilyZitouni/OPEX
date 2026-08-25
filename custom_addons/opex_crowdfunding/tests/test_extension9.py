import html
import re

from lxml import html as lxml_html

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

CSRF_TOKEN = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')
#: Le jeton de session, présent dans l'en-tête de toute page du portail —
#: utile quand la page ne porte pas de formulaire.
CSRF_SESSION = re.compile(r'csrf_token:\s*"([^"]+)"')

#: Ce qu'un teaser anonymisé ne doit jamais contenir — cherché dans le HTML
#: brut, pas dans le texte visible : « présent dans le HTML » suffirait ici à
#: violer la confidentialité.
SECRETS = {
    'titre': "Supervision d'atelier",
    'probleme': "Les PME industrielles n'ont pas d'outil de suivi",
    'solution': "Une application de supervision installable en une journée",
    'business_model': "Abonnement mensuel par atelier",
    'porteur': "Rachid Belkacem",
    'montant_exact': "8000000",
}


class RelationCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.crowdfunding.project']
        cls.Relation = cls.env['opex.crowdfunding.relation']

        cls.porteur = new_test_user(
            cls.env, login='cf9_porteur', password='cf9_porteur',
            groups='base.group_portal', name=SECRETS['porteur'])
        cls.ceo = new_test_user(
            cls.env, login='cf9_ceo',
            groups='base.group_user,opex_crowdfunding.group_ceo')
        # L'acteur financier est un utilisateur portail : « être enregistré
        # comme investisseur ne donne pas automatiquement accès » (section 3).
        cls.investisseur = new_test_user(
            cls.env, login='cf9_investisseur', password='cf9_investisseur',
            groups='base.group_portal', name="Fonds Industrie DZ")
        cls.investisseur.partner_id.write({
            'cf_is_financial_actor': True, 'cf_actor_type': 'fonds'})
        cls.autre_investisseur = new_test_user(
            cls.env, login='cf9_autre', password='cf9_autre',
            groups='base.group_portal', name="Capital Oran")

    def _projet(self, state='mise_en_relation', **valeurs):
        donnees = {
            'partner_id': self.porteur.partner_id.id,
            'name': SECRETS['titre'],
            'porteur_type': 'startup',
            'probleme': SECRETS['probleme'] + " de production.",
            'solution': SECRETS['solution'] + ".",
            'secteur': 'industrie',
            'maturite': 'mvp',
            'besoin_type': 'investisseur',
            'besoin_financier': 8000000.0,
            'business_model': SECRETS['business_model'] + " équipé.",
            'marche': "1 200 PME industrielles.",
            'traction': "Quatre ateliers pilotes.",
            'equipe': "Deux ingénieurs, un commercial.",
            'utilisation_fonds': "Recrutement et commercialisation.",
            'previsions_financieres': "Rentabilité attendue en 2028.",
            'state': state,
        }
        donnees.update(valeurs)
        return self.Project.create(donnees)

    def _relation(self, projet=None, partner=None):
        return self.Relation.create({
            'project_id': (projet or self._projet()).id,
            'partner_id': (partner or self.investisseur.partner_id).id,
        })


@tagged('post_install', '-at_install')
class TestExtension9Relation(RelationCommon):
    """Extension 9 — la mise en relation contrôlée (section 13)."""

    def test_le_matching_valide_ouvre_un_teaser_pas_un_dossier(self):
        """« Le matching ne signifie pas automatiquement partage du dossier. »"""
        projet = self._projet(state='matching_financier')
        candidat = self.env['opex.crowdfunding.matching.candidate'].create({
            'project_id': projet.id,
            'partner_id': self.investisseur.partner_id.id,
            'state': 'proposed',
        })
        candidat.with_user(self.ceo).action_validate()
        projet.with_user(self.ceo).action_validate_matching()

        relation = projet.relation_ids
        self.assertEqual(len(relation), 1)
        self.assertEqual(relation.partner_id, self.investisseur.partner_id)
        self.assertEqual(relation.niveau_acces, 'teaser')

    def test_l_interet_n_ouvre_rien(self):
        """Le cœur de la section 13 : dire « ça m'intéresse » ne donne aucun
        droit supplémentaire. La suite appartient au porteur."""
        relation = self._relation()
        relation.action_exprimer_interet()

        self.assertTrue(relation.interet_exprime)
        self.assertEqual(relation.niveau_acces, 'teaser',
                         "L'expression d'intérêt a ouvert le dossier toute seule.")

    def test_l_autorisation_du_porteur_ouvre_le_dossier_limite(self):
        """`with_user(porteur).sudo()` reproduit exactement le contrôleur.

        Le portail n'a aucun droit d'écriture sur la relation — c'est voulu
        (voir `test_un_acteur_ne_peut_pas_s_autoriser_lui_meme_par_ecriture`).
        Le geste passe donc par le contrôleur, qui a vérifié l'appartenance du
        dossier avant d'appeler la méthode en `sudo()`. L'utilisateur reste le
        porteur : c'est bien lui que `autorise_par_id` enregistre.
        """
        relation = self._relation()
        with self.assertRaises(UserError, msg="Autorisation sans intérêt exprimé."):
            relation.with_user(self.porteur).sudo().action_autoriser_partage()

        relation.action_exprimer_interet()
        relation.with_user(self.porteur).sudo().action_autoriser_partage()

        self.assertEqual(relation.niveau_acces, 'limited')
        self.assertEqual(relation.autorise_par_id, self.porteur)
        self.assertTrue(relation.date_autorisation)

    def test_le_dossier_detaille_attend_le_nda_quand_il_est_requis(self):
        relation = self._relation()
        relation.action_exprimer_interet()
        relation.with_user(self.porteur).sudo().action_autoriser_partage()
        relation.nda_requis = True

        with self.assertRaises(UserError):
            relation.with_user(self.ceo).action_ouvrir_dossier_complet()
        self.assertEqual(relation.niveau_acces, 'limited')

        relation.with_user(self.ceo).action_signer_nda()
        relation.with_user(self.ceo).action_ouvrir_dossier_complet()
        self.assertEqual(relation.niveau_acces, 'full')

    def test_sans_nda_requis_le_dossier_s_ouvre_directement(self):
        """« NDA si nécessaire » : quand il ne l'est pas, il ne bloque pas."""
        relation = self._relation()
        relation.action_exprimer_interet()
        relation.with_user(self.porteur).sudo().action_autoriser_partage()
        relation.with_user(self.ceo).action_ouvrir_dossier_complet()
        self.assertEqual(relation.niveau_acces, 'full')

    def test_aucun_cran_ne_se_saute(self):
        relation = self._relation()
        with self.assertRaises(UserError, msg="Dossier détaillé ouvert depuis le teaser."):
            relation.with_user(self.ceo).action_ouvrir_dossier_complet()
        self.assertEqual(relation.niveau_acces, 'teaser')

    @mute_logger('odoo.addons.base.models.ir_model')
    def test_seul_le_comite_ouvre_le_dossier_detaille(self):
        relation = self._relation()
        relation.action_exprimer_interet()
        relation.with_user(self.porteur).sudo().action_autoriser_partage()
        with self.assertRaises(AccessError):
            relation.with_user(self.investisseur).action_ouvrir_dossier_complet()

    def test_un_acteur_ne_peut_pas_s_autoriser_lui_meme_par_ecriture(self):
        """Le portail n'a aucun droit d'écriture sur la relation.

        Avec `perm_write` à 1, une requête forgée poserait
        `niveau_acces = 'full'` et se servirait elle-même.
        """
        relation = self._relation()
        with self.assertRaises(AccessError):
            relation.with_user(self.investisseur).write({'niveau_acces': 'full'})

    # ------------------------------------------------------------------
    # La fonction unique de contrôle d'accès
    # ------------------------------------------------------------------
    def test_le_payload_du_teaser_ne_contient_aucune_donnee_reservee(self):
        """Le contrôle est côté serveur : les données réservées ne sont même
        pas calculées, encore moins passées au gabarit."""
        relation = self._relation()
        gabarit, valeurs = relation._portal_payload()

        self.assertEqual(gabarit, 'opex_crowdfunding.portal_relation_teaser')
        for interdit in ('titre', 'probleme', 'solution', 'montant', 'porteur',
                         'dossier'):
            self.assertNotIn(interdit, valeurs,
                             "La clé « %s » est passée au gabarit du teaser." % interdit)
        # Et le gabarit ne reçoit ni la relation ni le projet : avec
        # l'enregistrement en main, tout le filtrage serait contournable.
        for cle, valeur in valeurs.items():
            self.assertFalse(
                hasattr(valeur, '_name') and valeur._name == 'opex.crowdfunding.project',
                "Le projet lui-même est passé au gabarit via « %s »." % cle)

    def test_le_payload_limite_ouvre_le_projet_mais_pas_le_porteur(self):
        relation = self._relation()
        relation.action_exprimer_interet()
        relation.with_user(self.porteur).sudo().action_autoriser_partage()
        gabarit, valeurs = relation._portal_payload()

        self.assertEqual(gabarit, 'opex_crowdfunding.portal_relation_limited')
        self.assertIn('titre', valeurs)
        self.assertIn('probleme', valeurs)
        for interdit in ('porteur', 'dossier'):
            self.assertNotIn(interdit, valeurs)

    def test_le_payload_complet_ouvre_tout(self):
        relation = self._relation()
        relation.action_exprimer_interet()
        relation.with_user(self.porteur).sudo().action_autoriser_partage()
        relation.with_user(self.ceo).action_ouvrir_dossier_complet()
        gabarit, valeurs = relation._portal_payload()

        self.assertEqual(gabarit, 'opex_crowdfunding.portal_relation_full')
        self.assertEqual(valeurs['porteur'], SECRETS['porteur'])
        libelles = [ligne[0] for ligne in valeurs['dossier']]
        self.assertIn("Business model", libelles)

    def test_le_teaser_ne_donne_qu_une_fourchette(self):
        relation = self._relation()
        _gabarit, valeurs = relation._portal_payload()
        self.assertIn("millions", valeurs['fourchette'])
        self.assertNotIn("8000000", valeurs['fourchette'])
        self.assertNotIn("8 000 000", valeurs['fourchette'])

    def test_la_reference_ne_dit_rien_du_projet(self):
        projet = self._projet()
        reference = projet._portal_reference()
        self.assertTrue(reference.startswith("PRJ-"))
        self.assertNotIn(SECRETS['titre'], reference)
        self.assertNotIn(SECRETS['porteur'], reference)


@tagged('post_install', '-at_install')
class TestExtension9Confidentialite(HttpCase, RelationCommon):
    """Ce qui part réellement sur le fil, octet par octet."""

    def _texte(self, page):
        document = lxml_html.fromstring(page.text)
        for element in document.xpath('//script | //style'):
            element.getparent().remove(element)
        return ' '.join(document.text_content().split())

    def _jeton(self, page_url):
        """Le jeton CSRF, pris sur la page qui porte le formulaire.

        Les routes d'action sont en POST seul : les interroger en GET ne rend
        aucun formulaire, donc aucun jeton.
        """
        page = self.url_open(page_url)
        jeton = CSRF_TOKEN.search(page.text) or CSRF_SESSION.search(page.text)
        self.assertTrue(jeton, "Pas de jeton CSRF sur %s." % page_url)
        return jeton.group(1)

    def _poster(self, url, donnees=None, jeton_depuis=None):
        jeton = self._jeton(jeton_depuis or url)
        return self.url_open(url, data=dict(donnees or {}, csrf_token=jeton))

    def _assert_aucun_secret(self, page, url, autorises=()):
        """Aucune donnée réservée dans le HTML — ni masquée, ni en attribut.

        ⚠️ Le HTML est **déséchappé** avant la recherche, et ce détail décide
        de tout : QWeb rend « Supervision d'atelier » en
        « Supervision d&#39;atelier ». Chercher la chaîne brute dans la réponse
        ne la trouve jamais — l'assertion passerait au vert quoi qu'il arrive,
        y compris sur une fuite réelle. C'est le piège n°6 du dossier, à
        l'endroit du module où il coûterait le plus cher.

        On cherche dans la réponse entière, pas dans le texte visible : une
        donnée en `d-none` ou dans un attribut est tout aussi divulguée.
        """
        contenu = html.unescape(page.text)
        for cle, secret in SECRETS.items():
            if cle in autorises:
                continue
            self.assertNotIn(
                secret, contenu,
                "« %s » est présent dans le HTML de %s." % (cle, url))

    def test_le_teaser_ne_livre_rien_dans_son_html(self):
        """Le test central de l'extension.

        On ne cherche pas dans le texte visible mais dans la réponse brute :
        une donnée masquée en CSS serait tout aussi divulguée.
        """
        relation = self._relation()
        self.authenticate('cf9_investisseur', 'cf9_investisseur')
        url = '/my/opportunities/%s' % relation.id
        page = self.url_open(url)

        self.assertEqual(page.status_code, 200)
        texte = self._texte(page)
        self.assertIn("Teaser anonymisé", texte)
        self.assertIn("Industrie & manufacturing", texte)
        self._assert_aucun_secret(page, url)

    def test_l_url_directe_ne_donne_pas_le_dossier_complet(self):
        """Un acteur au teaser tape l'URL de la fiche : il obtient le teaser.

        Il n'existe pas d'URL « dossier complet » à deviner — c'est le niveau
        d'accès enregistré qui décide du gabarit, pas le chemin demandé.
        """
        relation = self._relation()
        self.authenticate('cf9_investisseur', 'cf9_investisseur')

        for suffixe in ('', '?niveau=full', '?niveau_acces=full', '#full'):
            url = '/my/opportunities/%s%s' % (relation.id, suffixe)
            page = self.url_open(url)
            self.assertIn("Teaser anonymisé", self._texte(page))
            self._assert_aucun_secret(page, url)

    def test_la_liste_des_opportunites_reste_au_teaser(self):
        relation = self._relation()
        self.authenticate('cf9_investisseur', 'cf9_investisseur')
        page = self.url_open('/my/opportunities')

        self.assertIn(relation.project_id._portal_reference(), self._texte(page))
        self._assert_aucun_secret(page, '/my/opportunities')

    def test_l_acteur_exprime_son_interet_sans_rien_gagner(self):
        relation = self._relation()
        self.authenticate('cf9_investisseur', 'cf9_investisseur')
        url = '/my/opportunities/%s' % relation.id

        reponse = self._poster(url + '/interet', jeton_depuis=url)
        relation.invalidate_recordset()
        self.assertTrue(relation.interet_exprime)
        self.assertEqual(relation.niveau_acces, 'teaser')
        self._assert_aucun_secret(reponse, url)

    def test_apres_autorisation_le_dossier_limite_s_ouvre_sans_le_porteur(self):
        relation = self._relation()
        relation.action_exprimer_interet()
        relation.with_user(self.porteur).sudo().action_autoriser_partage()

        self.authenticate('cf9_investisseur', 'cf9_investisseur')
        url = '/my/opportunities/%s' % relation.id
        page = self.url_open(url)
        texte = self._texte(page)

        self.assertIn(SECRETS['titre'], texte)
        self.assertIn("accès limité", texte)
        # L'identité du porteur et le dossier financier restent fermés.
        self._assert_aucun_secret(page, url, autorises=('titre', 'probleme', 'solution'))

    def test_le_dossier_detaille_nomme_enfin_le_porteur(self):
        relation = self._relation()
        relation.action_exprimer_interet()
        relation.with_user(self.porteur).sudo().action_autoriser_partage()
        relation.with_user(self.ceo).action_ouvrir_dossier_complet()

        self.authenticate('cf9_investisseur', 'cf9_investisseur')
        texte = self._texte(
            self.url_open('/my/opportunities/%s' % relation.id))
        self.assertIn(SECRETS['porteur'], texte)
        self.assertIn(SECRETS['business_model'], texte)

    def test_un_acteur_n_atteint_pas_la_relation_d_un_autre(self):
        relation = self._relation()
        relation.action_exprimer_interet()
        relation.with_user(self.porteur).sudo().action_autoriser_partage()
        relation.with_user(self.ceo).action_ouvrir_dossier_complet()

        self.authenticate('cf9_autre', 'cf9_autre')
        url = '/my/opportunities/%s' % relation.id
        page = self.url_open(url)
        self.assertTrue(page.url.endswith('/my/opportunities'))
        self._assert_aucun_secret(page, url)

    def test_un_acteur_forge_l_url_d_autorisation_du_porteur(self):
        """La route d'autorisation appartient au porteur, pas à l'acteur."""
        relation = self._relation()
        relation.action_exprimer_interet()
        projet = relation.project_id

        self.authenticate('cf9_investisseur', 'cf9_investisseur')
        # Jeton CSRF valide, pris sur sa propre page : ce n'est pas le jeton
        # qui doit l'arrêter, c'est le contrôle d'appartenance du dossier.
        self.url_open(
            '/my/projects/%s/relations/%s/autoriser' % (projet.id, relation.id),
            data={'csrf_token': self._jeton('/my/opportunities')})

        relation.invalidate_recordset()
        self.assertEqual(relation.niveau_acces, 'teaser',
                         "Un acteur s'est autorisé lui-même par URL forgée.")

    def test_le_porteur_voit_qui_s_interesse_et_autorise(self):
        relation = self._relation()
        relation.action_exprimer_interet()
        projet = relation.project_id

        self.authenticate('cf9_porteur', 'cf9_porteur')
        url = '/my/projects/%s/relations' % projet.id
        texte = self._texte(self.url_open(url))
        self.assertIn("Fonds Industrie DZ", texte)
        self.assertIn("résumé anonymisé", texte)

        self._poster('/my/projects/%s/relations/%s/autoriser' % (projet.id, relation.id),
                     jeton_depuis=url)
        relation.invalidate_recordset()
        self.assertEqual(relation.niveau_acces, 'limited')

    @mute_logger('odoo.addons.base.models.ir_rule', 'odoo.addons.base.models.ir_model')
    def test_la_regle_ferme_la_lecture_directe_des_relations_d_autrui(self):
        relation = self._relation()
        with self.assertRaises(AccessError):
            relation.with_user(self.autre_investisseur).read(['project_id'])
