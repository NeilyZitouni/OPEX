"""L'accès au dépôt d'un dossier d'adhésion — une seule fonction, un motif.

LE DÉFAUT QUE CES TESTS GARDENT

Un compte interne simple voyait le bouton « Devenir membre », cliquait, et
était renvoyé sur `/my` **sans un mot**. Un rebond silencieux est
indistinguable d'une panne.

La cause était une asymétrie : le bouton testait la règle du dossier engagé,
la route testait *en plus* les droits de création. Deux questions différentes
sous un seul libellé — c'est la règle 2 du projet, contournée.
"""

import glob
import os
import re

from odoo.tests.common import HttpCase, new_test_user, tagged


def strip_prose(source):
    """Retire docstrings et commentaires — règle 15.

    Un test qui inspecte du source examine du **code**, pas de la prose : les
    commentaires de ce module expliquent en toutes lettres pourquoi
    `redirect('/my')` a été abandonné, et un test naïf rougirait dessus.
    """
    source = re.sub(r'("""|\'\'\')(?:.|\n)*?\1', '', source)
    return re.sub(r'#[^\n]*', '', source)


@tagged('post_install', '-at_install')
class TestMembershipDeposit(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.MembershipFile = cls.env['opex.membership.file']

        cls.interne = new_test_user(
            cls.env, login='test_dep_interne', groups='base.group_user',
            name="Interne simple")
        cls.portail = new_test_user(
            cls.env, login='test_dep_portail', groups='base.group_portal',
            name="Candidat portail")
        cls.secretariat = new_test_user(
            cls.env, login='test_dep_secr',
            groups='base.group_user,opex_membership.group_secretariat',
            name="Secretariat")

    def _refusal(self, user):
        return self.MembershipFile.with_user(user).deposit_refusal(
            user.partner_id)

    #
    # LA FONCTION UNIQUE
    #

    def test_an_internal_account_is_refused_with_a_readable_reason(self):
        """Le cœur de la correction.

        Un compte interne n'a pas `create` sur `opex.membership.file` — le
        parcours est fait pour des comptes portail. Ce refus est légitime ; ce
        qui ne l'était pas, c'est qu'il ne se dise pas.

        L'assertion positive d'abord : le compte portail, lui, passe. Sans
        elle, une fonction qui refuserait tout le monde ferait passer ce test.
        """
        self.assertFalse(
            self._refusal(self.portail),
            "Le compte portail est refuse : la fonction refuse tout le monde "
            "et ce test ne prouverait rien.")

        refus = self._refusal(self.interne)
        self.assertTrue(
            refus,
            "Un compte interne obtient le depot alors qu'il n'a pas le droit "
            "de creer un dossier.")
        self.assertIsInstance(
            refus, str,
            "Le refus n'est pas un texte : il ne pourra pas etre affiche, et "
            "l'utilisateur reverra un rebond muet.")
        # Le message doit **orienter**, pas seulement constater.
        for attendu in ("portail", "Secr"):
            self.assertIn(
                attendu, refus,
                "Le motif ne dit pas quoi faire : « %s » attendu." % attendu)

    def test_the_button_and_the_route_ask_the_same_function(self):
        """Règle 2 : un contrôle d'accès est une seule fonction.

        Le test lit le source du contrôleur, docstrings et commentaires
        retirés (règle 15) : ni la route ni le calcul du bouton ne doivent
        refaire le contrôle à leur façon. C'est en le refaisant que les deux
        avaient divergé.
        """
        chemin = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'controllers', 'portal.py')
        with open(chemin, encoding='utf-8') as fichier:
            source = fichier.read()
        source = strip_prose(source)

        self.assertNotIn(
            "has_access('create')", source,
            "Le controleur refait le controle de droits a la main : c'est "
            "exactement l'asymetrie qui a produit le rebond silencieux.")
        self.assertEqual(
            source.count('deposit_refusal'), 2,
            "La fonction d'acces doit etre appelee deux fois — par la route "
            "et par le calcul du bouton — et pas une de plus.")

    def test_a_secretariat_account_may_deposit(self):
        """Le refus porte sur les droits, pas sur le fait d'être interne."""
        self.assertFalse(self._refusal(self.secretariat))

    #
    # LE PARCOURS RÉEL — ce que voit l'utilisateur
    #

    def test_an_internal_account_gets_a_message_not_a_bounce(self):
        """Le symptôme signalé, éprouvé par la route.

        Avant : `redirect('/my')`, page du profil, aucune explication.
        Après : `/my/membership` avec le motif affiché.
        """
        self.authenticate('test_dep_interne', 'test_dep_interne')
        reponse = self.url_open('/my/membership/new', allow_redirects=True)

        self.assertEqual(reponse.status_code, 200)
        corps = reponse.content.decode()

        # Le motif est **rendu**, pas redirige : rediriger vers
        # `/my/membership` perdait le message, cette page rebondissant
        # elle-meme vers `/my` pour qui n'a pas le droit de lire les dossiers.
        # Mesure a l'appui : l'URL finale etait `/my`.
        self.assertIn(
            "compte interne", corps,
            "Le motif du refus n'est pas affiche : le rebond reste muet, et "
            "c'est indistinguable d'une panne.")
        self.assertIn(
            "Secr", corps,
            "Le motif affiche ne dit pas quoi faire.")
        self.assertNotIn(
            "Quelle est votre cat", corps,
            "Le formulaire s'affiche pour un compte sans droit de creation.")

    def test_a_portal_account_reaches_the_form(self):
        """L'assertion positive du parcours : le chemin nominal marche."""
        self.authenticate('test_dep_portail', 'test_dep_portail')
        reponse = self.url_open('/my/membership/new', allow_redirects=True)

        self.assertEqual(reponse.status_code, 200)
        self.assertIn(
            '/my/membership/new', reponse.url,
            "Le candidat portail est detourne du formulaire.")
        self.assertIn("cat", reponse.content.decode().lower())

    def test_the_button_is_hidden_for_an_internal_account(self):
        """Le pendant à l'écran : il ne promet plus ce que le serveur refuse."""
        self.authenticate('test_dep_interne', 'test_dep_interne')
        corps = self.url_open('/my/membership').content.decode()
        self.assertNotIn(
            "poser un dossier d'adh", corps,
            "Le bouton s'affiche pour un compte qui ne peut pas deposer.")

        self.authenticate('test_dep_portail', 'test_dep_portail')
        corps = self.url_open('/my/membership').content.decode()
        self.assertIn(
            "poser un dossier d'adh", corps,
            "Le bouton a disparu pour le candidat portail : la correction a "
            "masque le chemin nominal.")

    def test_the_membership_list_also_explains_its_refusal(self):
        """Le même motif, sur la page voisine.

        `/my/membership` portait le même rebond silencieux
        (`has_access('read')` → `/my`). Il ne produisait pas le symptôme
        signalé, mais c'est lui qui **avalait le message du dépôt** quand
        celui-ci redirigeait ici : le compte refusé au dépôt était exactement
        celui qui ne peut pas lire cette page.

        Deux refus, un seul comportement : la page dit pourquoi.
        """
        self.authenticate('test_dep_interne', 'test_dep_interne')
        reponse = self.url_open('/my/membership', allow_redirects=True)

        self.assertEqual(reponse.status_code, 200)
        corps = reponse.content.decode()
        self.assertIn(
            "compte interne", corps,
            "La liste des dossiers rebondit sans dire pourquoi.")
        self.assertNotIn(
            "My Portal", corps,
            "L'utilisateur est renvoye sur son profil : le rebond muet.")

        # L'assertion positive : le candidat portail voit bien sa liste.
        self.authenticate('test_dep_portail', 'test_dep_portail')
        reponse = self.url_open('/my/membership', allow_redirects=True)
        self.assertIn('/my/membership', reponse.url)
        self.assertNotIn("compte interne", reponse.content.decode())

    #
    # UN DOSSIER INTROUVABLE — UN SEUL MESSAGE, NEUTRE
    #

    def test_an_unreachable_file_says_so_without_revealing_anything(self):
        """Le cas qu'un vrai candidat rencontre.

        Un signet gardé, un lien d'un vieil email, un dossier supprimé. Avant,
        il revenait sur son profil sans savoir si le dossier avait disparu,
        s'il s'était trompé, ou si le portail était cassé.

        ⚠ **Un seul message pour les deux cas.** « N'existe pas » et « ne vous
        appartient pas » sont deux réponses différentes : les distinguer
        dirait à un visiteur que l'objet existe, et lui permettrait d'énumérer
        les dossiers en changeant l'identifiant. Règle 3.
        """
        self.authenticate('test_dep_portail', 'test_dep_portail')

        # (a) un identifiant qui n'existe pas
        inexistant = self.url_open('/my/membership/99999999',
                                   allow_redirects=True)
        # (b) un dossier réel, appartenant à quelqu'un d'autre
        autre = self.env['res.partner'].sudo().create({'name': "Autre candidat"})
        sous_categorie = self.env['opex.membership.subcategory'].sudo().search(
            [], limit=1)
        dossier = self.MembershipFile.sudo().create({
            'partner_id': autre.id,
            'subcategory_id': sous_categorie.id,
        })
        etranger = self.url_open('/my/membership/%s' % dossier.id,
                                 allow_redirects=True)

        for reponse, cas in ((inexistant, "inexistant"), (etranger, "d'autrui")):
            corps = reponse.content.decode()
            self.assertEqual(reponse.status_code, 200)
            # Sans apostrophe : `t-out` echappe, et « n'existe » devient
            # « n&#39;existe » dans le HTML rendu. C'est la regle 7 du
            # CLAUDE.md - une assertion sur une valeur **dynamique** ne
            # contient pas d'apostrophe. Mesure : ce test a rougi dessus alors
            # que la page affichee etait la bonne.
            self.assertIn(
                "ne vous est pas accessible", corps,
                "Dossier %s : le refus ne dit rien, le rebond reste muet."
                % cas)
            self.assertNotIn(
                "My Portal", corps,
                "Dossier %s : l'utilisateur est renvoye sur son profil." % cas)

        # Les deux réponses doivent être **indiscernables** — à ceci près
        # que la page renvoie dans ses métadonnées l'URL demandée. Ce n'est
        # pas une fuite : c'est ce que le visiteur a tapé lui-même. On les
        # neutralise avant de comparer, faute de quoi le test échouerait sur
        # une différence que le visiteur connaît déjà.
        def comparable(html, identifiant):
            html = html.replace('/my/membership/%s' % identifiant, '/ID')
            html = re.sub(r'unique=\w+', '', html)
            html = re.sub(r'csrf_token[^"]*"[^"]*"', '', html)
            return html

        self.assertEqual(
            comparable(inexistant.content.decode(), 99999999),
            comparable(etranger.content.decode(), dossier.id),
            "Les deux refus different : un visiteur peut distinguer un "
            "dossier qui existe d'un dossier qui n'existe pas, et enumerer "
            "les dossiers du portail en changeant l'identifiant.")

        # Et rien du dossier d'autrui ne transparait.
        corps_etranger = etranger.content.decode()
        self.assertNotIn(autre.name, corps_etranger)
        self.assertNotIn(sous_categorie.name, corps_etranger)

    def test_no_silent_bounce_remains_in_the_portal_controller(self):
        """La garde qui empêche le motif de revenir.

        `redirect('/my')` nu est le geste le plus naturel du monde quand on
        ajoute une route : c'est ce qui a produit les deux défauts
        diagnostiqués, puis huit autres du même genre.
        """
        chemin = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'controllers', 'portal.py')
        with open(chemin, encoding='utf-8') as fichier:
            source = fichier.read()
        source = strip_prose(source)

        self.assertNotIn(
            "request.redirect('/my')", source,
            "Un rebond silencieux vers le profil est revenu dans le "
            "controleur du portail : regle 25, un refus affiche son motif.")

    #
    # UN SEUL CHEMIN SOUS UN SEUL LIBELLÉ
    #

    def test_every_entry_point_uses_the_same_url(self):
        """La cause du « parfois ».

        Trois liens pointaient sur `/web/signup?redirect=…` et un quatrième
        sur `/my/membership/new`. Selon l'écran d'où l'on cliquait, on
        obtenait un 404 ou un rebond — sous le même libellé.

        ⚠ La greffe de visibilité du menu filtre sur l'URL **exacte**. Si elle
        cesse de correspondre, l'entrée « Devenir membre » redevient visible
        pour un candidat qui a déjà un dossier engagé — le défaut d'avant.
        """
        racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        fichiers = glob.glob(os.path.join(racine, 'views', '*.xml'))
        fichiers += glob.glob(os.path.join(racine, 'data', '*.xml'))

        examines = 0
        for chemin in fichiers:
            with open(chemin, encoding='utf-8') as fichier:
                contenu = fichier.read()
            examines += 1
            # Les commentaires expliquent pourquoi cette route a ete
            # abandonnee : un test qui interdit un mot interdit aussi qu'on en
            # parle (regle 15).
            sans_commentaires = re.sub(r'<!--(?:.|\n)*?-->', '', contenu)
            self.assertNotIn(
                '/web/signup', sans_commentaires,
                "%s pointe encore sur `/web/signup` : cette route rend un 404 "
                "quand le site est en `b2b`, et le reglage du site prime sur "
                "le parametre systeme." % os.path.basename(chemin))
        self.assertGreaterEqual(examines, 5)

        # La greffe doit suivre l'URL, sinon le masquage cesse en silence.
        chemin = os.path.join(racine, 'views', 'website_menu_templates.xml')
        with open(chemin, encoding='utf-8') as fichier:
            greffe = fichier.read()
        menu = self.env.ref('opex_membership.website_menu_become_member')
        self.assertIn(
            "submenu.url == '%s'" % menu.url, greffe,
            "La greffe de visibilite ne filtre plus sur l'URL de l'entree : "
            "« Devenir membre » restera visible pour un candidat deja engage.")

    def test_the_menu_entry_points_at_the_business_route(self):
        menu = self.env.ref('opex_membership.website_menu_become_member')
        self.assertEqual(menu.url, '/my/membership/new')
