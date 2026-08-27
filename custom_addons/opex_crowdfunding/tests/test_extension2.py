import re

from lxml import html as lxml_html

from odoo.exceptions import AccessError
from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

CSRF_TOKEN = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')

#: Le libellé que le document interdit — section 5. On le cherche à l'écran,
#: pas dans le code : c'est à l'écran qu'il ferait des dégâts.
CTA_INTERDIT = "Constituer mon dossier"

ECRAN_PROJET = {
    'name': "Supervision d'atelier",
    'porteur_type': 'startup',
    'probleme': "Les PME industrielles n'ont pas d'outil de suivi de production.",
    'solution': "Une application de supervision installable en une journée.",
}
ECRAN_BESOIN = {
    'secteur': 'industrie',
    'maturite': 'mvp',
    'besoin_type': 'investisseur',
    'montant_indicatif': "2 500 000,50",
}


@tagged('post_install', '-at_install')
class TestExtension2Portail(HttpCase):
    """Extension 2 — le parcours du porteur, tel qu'il le voit vraiment."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.crowdfunding.project']
        cls.porteur = new_test_user(
            cls.env, login='cf_porteur', password='cf_porteur',
            groups='base.group_portal', name="Rachid Belkacem")
        cls.autre = new_test_user(
            cls.env, login='cf_autre', password='cf_autre',
            groups='base.group_portal', name="Amina Haddad")

    def _connexion(self):
        self.authenticate('cf_porteur', 'cf_porteur')

    def _csrf(self, url):
        page = self.url_open(url)
        self.assertEqual(page.status_code, 200)
        trouve = CSRF_TOKEN.search(page.text)
        self.assertTrue(trouve, "Le formulaire de %s n'a pas de jeton CSRF." % url)
        return trouve.group(1)

    def _poster(self, url, donnees):
        payload = dict(donnees, csrf_token=self._csrf(url))
        return self.url_open(url, data=payload)

    def _mes_projets(self):
        return self.Project.search([('partner_id', '=', self.porteur.partner_id.id)])

    def _texte(self, page):
        """Le texte réellement rendu, espaces normalisés.

        Chercher une phrase dans le HTML brut échoue sur les apostrophes
        échappées (`&#39;`) et sur les coupures de ligne du gabarit. Ce sont
        des artefacts de gabarit, pas ce que lit le porteur : on compare donc
        au texte rendu, ce qui rapproche l'assertion de « visible à l'écran ».
        """
        document = lxml_html.fromstring(page.text)
        for element in document.xpath('//script | //style'):
            element.getparent().remove(element)
        return ' '.join(document.text_content().split())

    # ------------------------------------------------------------------
    # L'entrée dans le dispositif
    # ------------------------------------------------------------------
    def test_la_tuile_est_visible_meme_avec_zero_projet(self):
        """Le piège du portail : `d-none` sur une tuile sans compteur.

        `portal_docs_entry` masque la tuile et le script ne la réaffiche que si
        le compteur revient strictement positif. Un porteur qui n'a encore
        aucun projet — celui qu'on attend — ne verrait donc jamais l'entrée qui
        lui permet d'en déposer un. Présente dans le HTML ne suffit pas : on
        vérifie ici que la carte ne porte pas `d-none`.
        """
        self._connexion()
        self.assertFalse(self._mes_projets(), "Le porteur ne doit avoir aucun projet.")

        page = self.url_open('/my')
        self.assertEqual(page.status_code, 200)
        document = lxml_html.fromstring(page.text)
        cartes = document.xpath(
            "//div[contains(@class, 'o_portal_index_card')][.//a[@href='/my/crowdfunding']]")
        self.assertTrue(cartes, "La tuile « Mes projets » est absente de l'accueil du portail.")
        self.assertNotIn(
            'd-none', cartes[0].get('class', ''),
            "La tuile « Mes projets » est rendue masquée : un porteur sans "
            "projet n'a aucun moyen d'en présenter un.")

    def test_liste_vide_propose_le_bon_appel_a_l_action(self):
        self._connexion()
        page = self.url_open('/my/crowdfunding')
        self.assertEqual(page.status_code, 200)
        self.assertIn("Présenter mon projet", self._texte(page))
        self.assertNotIn(CTA_INTERDIT, page.text)

    def test_le_cta_interdit_n_apparait_sur_aucun_ecran(self):
        """Section 5 : le libellé conditionne le taux de dépôt."""
        self._connexion()
        self._poster('/my/crowdfunding/new', ECRAN_PROJET)
        projet = self._mes_projets()
        for url in ('/my/crowdfunding', '/my/crowdfunding/new', '/my/crowdfunding/new/besoin',
                    '/my/crowdfunding/%s' % projet.id):
            page = self.url_open(url)
            self.assertNotIn(CTA_INTERDIT, page.text, "Libellé interdit sur %s." % url)

    # ------------------------------------------------------------------
    # Le brouillon auto-sauvegardé
    # ------------------------------------------------------------------
    def test_le_projet_est_cree_des_la_premiere_saisie(self):
        self._connexion()
        reponse = self._poster('/my/crowdfunding/new', ECRAN_PROJET)
        self.assertEqual(reponse.status_code, 200)
        self.assertTrue(reponse.url.endswith('/my/crowdfunding/new/besoin'))

        projet = self._mes_projets()
        self.assertEqual(len(projet), 1)
        self.assertEqual(projet.state, 'draft')
        self.assertEqual(projet.name, ECRAN_PROJET['name'])
        self.assertEqual(projet.probleme, ECRAN_PROJET['probleme'])

    def test_sans_titre_rien_n_est_cree_et_la_saisie_est_rendue(self):
        """Un brouillon sans titre serait introuvable dans « Mes projets »."""
        self._connexion()
        reponse = self._poster('/my/crowdfunding/new', dict(ECRAN_PROJET, name=""))
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(self._mes_projets(), "Un projet sans titre a été créé.")
        # La saisie déjà faite est réaffichée : personne ne retape sa
        # présentation parce qu'il a oublié le titre.
        self.assertIn(ECRAN_PROJET['probleme'], self._texte(reponse))

    def test_ecriture_partielle_le_second_ecran_ne_perd_pas_le_premier(self):
        self._connexion()
        self._poster('/my/crowdfunding/new', ECRAN_PROJET)
        self._poster('/my/crowdfunding/new/besoin', dict(ECRAN_BESOIN, enregistrer='1'))

        projet = self._mes_projets()
        self.assertEqual(projet.probleme, ECRAN_PROJET['probleme'])
        self.assertEqual(projet.secteur, 'industrie')
        self.assertEqual(projet.besoin_type, 'investisseur')
        self.assertEqual(projet.montant_indicatif, 2500000.50)
        self.assertEqual(projet.state, 'draft', "« Continuer plus tard » ne dépose pas le projet.")

    def test_le_pitch_est_facultatif_et_ne_s_efface_pas_tout_seul(self):
        """« Document/pitch facultatif » (section 5).

        Le troisième temps est le vrai piège : un second passage sur l'écran
        n'envoie pas de fichier, et effacerait le document déjà déposé si le
        contrôleur écrivait le champ sans regarder.
        """
        self._connexion()
        self._poster('/my/crowdfunding/new', ECRAN_PROJET)
        url = '/my/crowdfunding/new/besoin'

        self._poster(url, dict(ECRAN_BESOIN, enregistrer='1'))
        self.assertFalse(self._mes_projets().pitch_document)

        self.url_open(
            url,
            data=dict(ECRAN_BESOIN, enregistrer='1', csrf_token=self._csrf(url)),
            files={'pitch_document': ('pitch.pdf', b'%PDF-1.4 pitch', 'application/pdf')})
        self.assertEqual(self._mes_projets().pitch_filename, 'pitch.pdf')

        # Un navigateur qui repasse sur l'écran sans choisir de fichier envoie
        # bien une part, mais vide : c'est ce cas-là qu'il faut simuler, pas
        # l'absence totale de part.
        self.url_open(
            url,
            data=dict(ECRAN_BESOIN, enregistrer='1', csrf_token=self._csrf(url)),
            files={'pitch_document': ('', b'')})
        self.assertEqual(self._mes_projets().pitch_filename, 'pitch.pdf')

    def test_message_de_reprise_quand_le_porteur_revient(self):
        self._connexion()
        self._poster('/my/crowdfunding/new', ECRAN_PROJET)

        page = self.url_open('/my/crowdfunding/new')
        self.assertIn("Votre saisie a été conservée", self._texte(page))
        self.assertIn(ECRAN_PROJET['name'], self._texte(page))

        # La liste aussi propose de reprendre plutôt que de recommencer.
        liste = self.url_open('/my/crowdfunding')
        self.assertIn("Reprendre", self._texte(liste))

    def test_une_seule_presentation_en_cours_a_la_fois(self):
        """Repasser par l'écran 1 reprend le brouillon, il ne le duplique pas."""
        self._connexion()
        self._poster('/my/crowdfunding/new', ECRAN_PROJET)
        self._poster('/my/crowdfunding/new', dict(ECRAN_PROJET, name="Titre corrigé"))

        projets = self._mes_projets()
        self.assertEqual(len(projets), 1)
        self.assertEqual(projets.name, "Titre corrigé")

    # ------------------------------------------------------------------
    # Le dépôt
    # ------------------------------------------------------------------
    def test_parcours_complet_depuis_le_portail(self):
        self._connexion()
        self._poster('/my/crowdfunding/new', ECRAN_PROJET)
        reponse = self._poster('/my/crowdfunding/new/besoin', ECRAN_BESOIN)

        projet = self._mes_projets()
        self.assertEqual(projet.state, 'depot_express')
        self.assertTrue(reponse.url.endswith('/my/crowdfunding/%s' % projet.id))
        self.assertIn("Votre prochaine action", self._texte(reponse))

    def test_depot_incomplet_dit_ce_qui_manque_sans_page_d_erreur(self):
        self._connexion()
        self._poster('/my/crowdfunding/new', ECRAN_PROJET)
        reponse = self._poster(
            '/my/crowdfunding/new/besoin', dict(ECRAN_BESOIN, besoin_type=""))

        self.assertEqual(reponse.status_code, 200)
        self.assertIn("Besoin recherché", self._texte(reponse))
        self.assertEqual(self._mes_projets().state, 'draft')

    # ------------------------------------------------------------------
    # La vue « Mon projet » — section 16
    # ------------------------------------------------------------------
    def test_la_page_de_suivi_montre_les_jalons_et_la_prochaine_action(self):
        self._connexion()
        self._poster('/my/crowdfunding/new', ECRAN_PROJET)
        self._poster('/my/crowdfunding/new/besoin', ECRAN_BESOIN)
        projet = self._mes_projets()

        page = self.url_open('/my/crowdfunding/%s' % projet.id)
        self.assertEqual(page.status_code, 200)
        texte = self._texte(page)
        for jalon in ("Demande reçue", "Projet présélectionné", "Dossier complété",
                      "Étude", "Mise en relation"):
            self.assertIn(jalon, texte)
        self.assertIn("Votre prochaine action", texte)
        self.assertIn("Le comité CEO va l'examiner", texte)

    def test_aucun_code_d_etat_technique_a_l_ecran(self):
        """Section 16 : le porteur ne pilote pas le workflow, il est guidé."""
        self._connexion()
        self._poster('/my/crowdfunding/new', ECRAN_PROJET)
        self._poster('/my/crowdfunding/new/besoin', ECRAN_BESOIN)
        projet = self._mes_projets()

        for url in ('/my/crowdfunding', '/my/crowdfunding/%s' % projet.id):
            page = self.url_open(url)
            for code in ('depot_express', 'quality_gate', 'etude_decision',
                         'matching_financier'):
                self.assertNotIn(code, page.text, "Code d'état « %s » visible sur %s." % (code, url))

    # ------------------------------------------------------------------
    # Cloisonnement
    # ------------------------------------------------------------------
    def test_un_porteur_n_atteint_pas_le_projet_d_un_autre(self):
        projet_autre = self.Project.create({
            'partner_id': self.autre.partner_id.id,
            'name': "Projet confidentiel d'Amina",
        })
        self._connexion()
        page = self.url_open('/my/crowdfunding/%s' % projet_autre.id)
        self.assertTrue(page.url.endswith('/my/crowdfunding'))
        # Sur le texte rendu : dans le HTML brut, l'apostrophe est échappée et
        # la recherche ne trouverait jamais rien — un vert sans valeur.
        texte = self._texte(page)
        self.assertNotIn("Projet confidentiel", texte)
        self.assertIn("Présenter mon projet", texte)

    def test_un_porteur_ne_reprend_pas_le_brouillon_d_un_autre(self):
        self.Project.create({
            'partner_id': self.autre.partner_id.id,
            'name': "Brouillon d'Amina",
        })
        self._connexion()
        texte = self._texte(self.url_open('/my/crowdfunding/new'))
        self.assertNotIn("Brouillon", texte)
        self.assertNotIn("Votre saisie a été conservée", texte)


@tagged('post_install', '-at_install')
class TestExtension2Securite(TransactionCase):
    """Ce que la base garantit, indépendamment de ce que font les écrans."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.crowdfunding.project']
        cls.porteur = new_test_user(
            cls.env, login='cf_sec_porteur', groups='base.group_portal')
        cls.autre = new_test_user(
            cls.env, login='cf_sec_autre', groups='base.group_portal')

    def test_create_force_le_porteur_et_le_brouillon(self):
        """Une requête forgée ne dépose pas un projet au nom d'un autre."""
        projet = self.Project.with_user(self.porteur).create({
            'name': "Tentative",
            'partner_id': self.autre.partner_id.id,   # ignoré
            'state': 'closing',                       # ignoré
        })
        self.assertEqual(projet.partner_id, self.porteur.partner_id)
        self.assertEqual(projet.state, 'draft')

    def test_le_ceo_reste_libre_de_saisir_pour_un_tiers(self):
        """La surcharge ne vise que le portail : elle ne bride pas le backend."""
        ceo = new_test_user(
            self.env, login='cf_sec_ceo',
            groups='base.group_user,opex_crowdfunding.group_ceo')
        projet = self.Project.with_user(ceo).create({
            'name': "Dossier saisi au bureau",
            'partner_id': self.autre.partner_id.id,
        })
        self.assertEqual(projet.partner_id, self.autre.partner_id)

    @mute_logger('odoo.addons.base.models.ir_rule', 'odoo.addons.base.models.ir_model')
    def test_la_regle_interdit_de_lire_le_projet_d_un_autre(self):
        projet = self.Project.create({
            'partner_id': self.autre.partner_id.id, 'name': "Projet d'un autre",
        })
        with self.assertRaises(AccessError):
            projet.with_user(self.porteur).read(['name'])

    @mute_logger('odoo.addons.base.models.ir_rule', 'odoo.addons.base.models.ir_model')
    def test_la_regle_ferme_l_ecriture_une_fois_le_projet_depose(self):
        projet = self.Project.with_user(self.porteur).create({'name': "Mon projet"})
        # Tant qu'il est brouillon, le porteur corrige sa présentation.
        projet.with_user(self.porteur).write({'probleme': "Un problème."})
        projet.write({'state': 'depot_express'})
        with self.assertRaises(AccessError):
            projet.with_user(self.porteur).write({'probleme': "Réécriture après dépôt."})

    # ------------------------------------------------------------------
    # Les tables de traduction de la section 16
    # ------------------------------------------------------------------
    def test_chaque_etat_dit_au_porteur_ce_qui_l_attend(self):
        """Un état sans consigne afficherait une page muette à quelqu'un qui
        attend qu'on lui dise quoi faire."""
        codes = [code for code, _libelle in self.Project._fields['state'].selection]
        for code in codes:
            self.assertIn(code, self.Project._PORTAL_NEXT_ACTIONS)

    def test_chaque_etat_est_rattache_a_un_jalon_sauf_la_sortie(self):
        couverts = {
            code
            for _label, etats in self.Project._PORTAL_MILESTONES
            for code in etats
        }
        codes = {code for code, _libelle in self.Project._fields['state'].selection}
        # `rejected` est volontairement hors parcours : un dossier non retenu
        # n'est pas « en retard » sur une étape, il en est sorti.
        self.assertEqual(codes - couverts, {'rejected'})

    def test_la_progression_avance_avec_le_dossier(self):
        projet = self.Project.create({'partner_id': self.porteur.partner_id.id,
                                      'name': "Progression"})
        statuts = [jalon['status'] for jalon in projet._portal_progress()]
        self.assertEqual(statuts, ['current', 'todo', 'todo', 'todo', 'todo', 'todo'])

        projet.write({'state': 'quality_gate'})
        statuts = [jalon['status'] for jalon in projet._portal_progress()]
        self.assertEqual(statuts, ['done', 'done', 'current', 'todo', 'todo', 'todo'])

        projet.write({'state': 'rejected'})
        statuts = [jalon['status'] for jalon in projet._portal_progress()]
        self.assertEqual(statuts, ['todo'] * 6)

    def test_le_bouton_n_existe_que_quand_le_porteur_a_la_main(self):
        """Un bouton mort vaut moins que pas de bouton."""
        projet = self.Project.create({'partner_id': self.porteur.partner_id.id,
                                      'name': "Prochaine action"})
        action = projet._portal_next_action()
        self.assertEqual(action['url'], '/my/crowdfunding/new')

        projet.write({'state': 'etude_decision'})
        action = projet._portal_next_action()
        self.assertFalse(action['url'])
        self.assertTrue(action['message'])
