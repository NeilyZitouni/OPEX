import re

from lxml import html as lxml_html

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

CSRF_TOKEN = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')

#: Un questionnaire complet par besoin. Trois jeux de données pour trois
#: branches : c'est déjà, côté tests, le coût du branchement.
DOSSIERS = {
    'investisseur': {
        'business_model': "Abonnement mensuel par atelier équipé.",
        'marche': "1 200 PME industrielles en Algérie.",
        'traction': "Quatre ateliers pilotes, 18 mois de recul.",
        'equipe': "Deux ingénieurs, un commercial.",
        'besoin_financier': "8 000 000",
        'utilisation_fonds': "Recrutement de deux développeurs et commercialisation.",
        'previsions_financieres': "Rentabilité attendue en 2028.",
    },
    'sponsor': {
        'sponsor_objectif': "Financer le salon annuel de l'industrie 4.0.",
        'sponsor_public_cible': "400 dirigeants de PME industrielles.",
        'sponsor_visibilite': "Logo sur les supports, prise de parole en ouverture.",
        'sponsor_retombees': "Notoriété auprès de la filière.",
        'sponsor_budget': "1 500 000",
        'sponsor_calendrier': "Édition de mars 2027.",
    },
    'financement_public': {
        'public_dispositif': "Appel à projets ANVREDET 2027.",
        'public_eligibilite': "Startup labellisée, moins de huit ans.",
        'public_montant': "5 000 000",
        'public_plan_financement': "30 % d'apport propre, 70 % de subvention.",
        'public_impact': "Douze emplois directs sur trois ans.",
        'public_conformite': "Registre de commerce et label à jour.",
        'public_calendrier': "Démarrage au premier trimestre 2027.",
    },
}

#: Le champ laissé vide pour vérifier que chaque branche contrôle bien le sien.
CHAMP_TEMOIN = {
    'investisseur': ('business_model', "Business model"),
    'sponsor': ('sponsor_objectif', "Objet du sponsoring"),
    'financement_public': ('public_dispositif', "Dispositif public visé"),
}


class DossierCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.crowdfunding.project']
        cls.porteur = new_test_user(
            cls.env, login='cf4_porteur', password='cf4_porteur',
            groups='base.group_portal', name="Rachid Belkacem")
        cls.ceo = new_test_user(
            cls.env, login='cf4_ceo',
            groups='base.group_user,opex_crowdfunding.group_ceo')

    def _projet(self, besoin_type, state='dossier_progressif', **valeurs):
        donnees = {
            'partner_id': self.porteur.partner_id.id,
            'name': "Supervision d'atelier",
            'porteur_type': 'startup',
            'probleme': "Pas d'outil de suivi de production.",
            'solution': "Une application de supervision d'atelier.",
            'secteur': 'industrie',
            'maturite': 'mvp',
            'besoin_type': besoin_type,
            'state': state,
        }
        donnees.update(valeurs)
        return self.Project.create(donnees)

    def _valeurs_modele(self, besoin_type):
        """Le questionnaire, converti pour une écriture directe en base."""
        valeurs = {}
        for nom, brut in DOSSIERS[besoin_type].items():
            if self.Project._fields[nom].type == 'monetary':
                valeurs[nom] = float(brut.replace(' ', ''))
            else:
                valeurs[nom] = brut
        return valeurs


@tagged('post_install', '-at_install')
class TestExtension4Dossier(DossierCommon):
    """Extension 4 — le dossier progressif et ses trois branches (section 7)."""

    def test_le_dossier_n_est_demande_qu_apres_un_go(self):
        """« Uniquement après un GO » : avant, la transition n'existe pas."""
        for state in ('draft', 'depot_express', 'pre_analyse', 'clarification'):
            projet = self._projet('investisseur', state=state)
            projet.write(self._valeurs_modele('investisseur'))
            with self.assertRaises(UserError, msg="Dossier accepté en %s." % state):
                projet.action_submit_dossier()

    def test_les_trois_branches_partent_au_controle_qualite(self):
        for besoin_type in DOSSIERS:
            projet = self._projet(besoin_type)
            projet.write(self._valeurs_modele(besoin_type))
            projet.action_submit_dossier()
            self.assertEqual(
                projet.state, 'quality_gate',
                "La branche %s n'a pas atteint le Quality Gate." % besoin_type)

    def test_chaque_branche_controle_ses_propres_champs(self):
        """Le cœur du branchement : un champ manquant chez l'un n'est pas
        réclamé chez l'autre."""
        for besoin_type, (champ, libelle) in CHAMP_TEMOIN.items():
            projet = self._projet(besoin_type)
            valeurs = self._valeurs_modele(besoin_type)
            valeurs.pop(champ)
            projet.write(valeurs)

            with self.assertRaises(UserError) as capture:
                projet.action_submit_dossier()
            self.assertIn(libelle, capture.exception.args[0])
            self.assertEqual(projet.state, 'dossier_progressif')

    def test_un_questionnaire_ne_reclame_pas_les_champs_d_un_autre(self):
        """Un dossier sponsor complet part, même sans business model.

        Sans ce test, une liste de champs obligatoires commune aux trois
        branches passerait inaperçue : elle ne casserait que le jour où un
        sponsor se verrait réclamer sa valorisation.
        """
        projet = self._projet('sponsor')
        projet.write(self._valeurs_modele('sponsor'))
        self.assertFalse(projet.business_model)
        self.assertFalse(projet.public_dispositif)
        projet.action_submit_dossier()
        self.assertEqual(projet.state, 'quality_gate')

    def test_les_champs_facultatifs_le_restent(self):
        """Valorisation « éventuelle », documents facultatifs (section 7)."""
        projet = self._projet('investisseur')
        projet.write(self._valeurs_modele('investisseur'))
        self.assertFalse(projet.valorisation)
        self.assertFalse(projet.pitch_deck)
        projet.action_submit_dossier()
        self.assertEqual(projet.state, 'quality_gate')

    def test_les_trois_questionnaires_sont_bien_distincts(self):
        """Trois besoins, trois jeux de champs : aucun recouvrement.

        Deux branches qui partageraient un champ obligatoire, ce serait le
        début du questionnaire unique que la section 7 refuse.
        """
        table = self.Project._CHAMPS_DOSSIER
        self.assertEqual(set(table), {'investisseur', 'sponsor', 'financement_public'})
        for besoin_type, champs in table.items():
            autres = {
                champ
                for autre, liste in table.items() if autre != besoin_type
                for champ in liste
            }
            self.assertFalse(
                set(champs) & autres,
                "Les questionnaires %s et les autres partagent un champ." % besoin_type)
            for champ in champs:
                self.assertIn(champ, self.Project._fields,
                              "%s n'existe pas sur le modèle." % champ)

    def test_un_besoin_sans_questionnaire_est_refuse_bruyamment(self):
        """Garde-fou pour le jour où un quatrième besoin sera ajouté au
        Selection sans son questionnaire : sans ce refus, ces dossiers-là
        fileraient au contrôle qualité sans la moindre vérification."""
        projet = self._projet('investisseur')
        projet.besoin_type = False
        with self.assertRaises(UserError):
            projet.action_submit_dossier()
        self.assertEqual(projet.state, 'dossier_progressif')


@tagged('post_install', '-at_install')
class TestExtension4Portail(HttpCase, DossierCommon):
    """Le porteur remplit son questionnaire, et seulement le sien."""

    def _connexion(self):
        self.authenticate('cf4_porteur', 'cf4_porteur')

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

    def test_le_suivi_propose_le_bouton_completer(self):
        projet = self._projet('investisseur')
        self._connexion()
        page = self.url_open('/my/projects/%s' % projet.id)
        texte = self._texte(page)

        self.assertIn("Compléter mon dossier", texte)
        self.assertIn('/my/projects/%s/dossier' % projet.id, page.text)

    def test_chaque_besoin_voit_son_questionnaire_et_pas_les_autres(self):
        """La condition `t-if` sur `besoin_type`, vérifiée à l'écran."""
        attendu = {
            'investisseur': "Business model",
            'sponsor': "Objet du sponsoring",
            'financement_public': "Dispositif public visé",
        }
        self._connexion()
        for besoin_type, libelle in attendu.items():
            projet = self._projet(besoin_type)
            texte = self._texte(self.url_open('/my/projects/%s/dossier' % projet.id))
            self.assertIn(libelle, texte)
            for autre, libelle_autre in attendu.items():
                if autre != besoin_type:
                    self.assertNotIn(
                        libelle_autre, texte,
                        "Le questionnaire %s montre un champ de %s." % (besoin_type, autre))

    def test_parcours_complet_investisseur(self):
        projet = self._projet('investisseur')
        self._connexion()
        reponse = self._poster('/my/projects/%s/dossier' % projet.id,
                               DOSSIERS['investisseur'])

        projet.invalidate_recordset()
        self.assertEqual(projet.state, 'quality_gate')
        self.assertEqual(projet.business_model, DOSSIERS['investisseur']['business_model'])
        self.assertEqual(projet.besoin_financier, 8000000.0)
        self.assertTrue(reponse.url.endswith('/my/projects/%s' % projet.id))

    def test_enregistrer_et_revenir_plus_tard(self):
        projet = self._projet('sponsor')
        self._connexion()
        partiel = dict(DOSSIERS['sponsor'])
        partiel.pop('sponsor_calendrier')

        self._poster('/my/projects/%s/dossier' % projet.id,
                     dict(partiel, enregistrer='1'))

        projet.invalidate_recordset()
        self.assertEqual(projet.state, 'dossier_progressif')
        self.assertEqual(projet.sponsor_objectif, DOSSIERS['sponsor']['sponsor_objectif'])
        # Et le porteur retrouve sa saisie en revenant sur l'écran.
        texte = self._texte(self.url_open('/my/projects/%s/dossier' % projet.id))
        self.assertIn(DOSSIERS['sponsor']['sponsor_objectif'], texte)

    def test_envoi_incomplet_dit_ce_qui_manque_et_conserve_la_saisie(self):
        projet = self._projet('financement_public')
        self._connexion()
        partiel = dict(DOSSIERS['financement_public'])
        partiel.pop('public_impact')

        reponse = self._poster('/my/projects/%s/dossier' % projet.id, partiel)

        projet.invalidate_recordset()
        self.assertEqual(projet.state, 'dossier_progressif')
        texte = self._texte(reponse)
        self.assertIn("Impact socio-économique", texte)
        self.assertIn(DOSSIERS['financement_public']['public_dispositif'], texte)

    def test_le_document_du_questionnaire_ne_s_efface_pas_tout_seul(self):
        projet = self._projet('investisseur')
        self._connexion()
        url = '/my/projects/%s/dossier' % projet.id

        page = self.url_open(url)
        jeton = CSRF_TOKEN.search(page.text).group(1)
        self.url_open(
            url,
            data=dict(DOSSIERS['investisseur'], enregistrer='1', csrf_token=jeton),
            files={'pitch_deck': ('deck.pdf', b'%PDF-1.4 deck', 'application/pdf')})
        projet.invalidate_recordset()
        self.assertEqual(projet.pitch_deck_filename, 'deck.pdf')

        self._poster(url, dict(DOSSIERS['investisseur'], enregistrer='1'))
        projet.invalidate_recordset()
        self.assertEqual(projet.pitch_deck_filename, 'deck.pdf')

    def test_l_ecran_est_ferme_hors_du_bon_etat(self):
        projet = self._projet('investisseur', state='quality_gate')
        self._connexion()
        page = self.url_open('/my/projects/%s/dossier' % projet.id)
        self.assertTrue(page.url.endswith('/my/projects/%s' % projet.id))
        self.assertNotIn("Business model", self._texte(page))

    def test_un_porteur_ne_remplit_pas_le_dossier_d_un_autre(self):
        autre = new_test_user(
            self.env, login='cf4_autre', password='cf4_autre',
            groups='base.group_portal', name="Amina Haddad")
        projet = self._projet('investisseur')
        projet.partner_id = autre.partner_id

        self._connexion()
        page = self.url_open('/my/projects/%s/dossier' % projet.id)
        self.assertTrue(page.url.endswith('/my/projects'))

    def test_aucun_code_d_etat_sur_l_ecran_du_dossier(self):
        projet = self._projet('investisseur')
        self._connexion()
        texte = self._texte(self.url_open('/my/projects/%s/dossier' % projet.id))
        for code in ('dossier_progressif', 'quality_gate', 'investisseur'):
            self.assertNotIn(code, texte)


@tagged('post_install', '-at_install')
class TestExtension4Securite(DossierCommon):

    @mute_logger('odoo.addons.base.models.ir_rule', 'odoo.addons.base.models.ir_model')
    def test_le_porteur_ecrit_son_dossier_mais_pas_apres_l_envoi(self):
        """La règle d'enregistrement suit le parcours : le porteur a la main
        en `dossier_progressif`, plus après."""
        projet = self._projet('investisseur')
        projet.with_user(self.porteur).write({'business_model': "Abonnement."})
        self.assertEqual(projet.business_model, "Abonnement.")

        projet.write({'state': 'quality_gate'})
        with self.assertRaises(AccessError):
            projet.with_user(self.porteur).write({'business_model': "Réécriture."})
