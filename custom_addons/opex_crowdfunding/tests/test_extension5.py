import re

from lxml import html as lxml_html

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

CSRF_TOKEN = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')

#: Un dossier investisseur complet — de quoi franchir l'Extension 4.
DOSSIER_INVESTISSEUR = {
    'business_model': "Abonnement mensuel par atelier équipé.",
    'marche': "1 200 PME industrielles en Algérie.",
    'traction': "Quatre ateliers pilotes.",
    'equipe': "Deux ingénieurs, un commercial.",
    'besoin_financier': 8000000.0,
    'utilisation_fonds': "Recrutement et commercialisation.",
    'previsions_financieres': "Rentabilité attendue en 2028.",
}

#: Les six vérifications toutes au vert.
CONTROLE_CONFORME = {
    'completude': True,
    'coherence': True,
    'qualite_informations': True,
    'conformite_criteres': True,
    'justificatifs': True,
}


class QualityCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.crowdfunding.project']
        cls.Control = cls.env['opex.crowdfunding.quality.control']
        cls.porteur = new_test_user(
            cls.env, login='cf5_porteur', password='cf5_porteur',
            groups='base.group_portal', name="Rachid Belkacem")
        cls.ceo = new_test_user(
            cls.env, login='cf5_ceo',
            groups='base.group_user,opex_crowdfunding.group_ceo')
        cls.qualite = new_test_user(
            cls.env, login='cf5_qualite',
            groups='base.group_user,opex_crowdfunding.group_quality_control')
        # Second contrôleur : sert à prouver qu'aucune transition ne dépend de
        # l'identité de celui qui a rempli la fiche.
        cls.qualite_bis = new_test_user(
            cls.env, login='cf5_qualite_bis',
            groups='base.group_user,opex_crowdfunding.group_quality_control')

    def _projet(self, state='quality_gate', **valeurs):
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
        donnees.update(DOSSIER_INVESTISSEUR)
        donnees.update(valeurs)
        projet = self.Project.create(donnees)
        if state == 'quality_gate':
            projet._open_quality_control()
        return projet

    def _controler(self, projet, avis, **valeurs):
        """Remplit la fiche de contrôle en cours et retient un avis."""
        control = projet._current_quality_control()
        control.write(dict(CONTROLE_CONFORME, avis=avis, **valeurs))
        return control

    def _message(self, projet, extrait):
        """Le message du fil qui contient `extrait`.

        On ne prend pas « le dernier message » : le suivi de `state` en poste
        un de son côté, et l'ordre des deux n'est pas garanti.
        """
        trouves = projet.message_ids.filtered(lambda m: extrait in (m.body or ''))
        self.assertTrue(trouves, "Aucun message ne contient « %s »." % extrait)
        return trouves[0]


@tagged('post_install', '-at_install')
class TestExtension5QualityGate(QualityCommon):
    """Extension 5 — le Quality Gate : quatre avis, trois sorties (section 8)."""

    # ------------------------------------------------------------------
    # L'arrivée au contrôle
    # ------------------------------------------------------------------
    def test_le_dossier_envoye_ouvre_une_fiche_de_controle(self):
        projet = self._projet(state='dossier_progressif')
        projet.action_submit_dossier()
        self.assertEqual(projet.state, 'quality_gate')
        self.assertEqual(len(projet.quality_control_ids), 1)
        self.assertFalse(projet.quality_control_ids.avis)
        self.assertFalse(projet.quality_control_ids.date)

    # ------------------------------------------------------------------
    # Les quatre avis, les trois sorties
    # ------------------------------------------------------------------
    def test_conforme_transmet_au_comite(self):
        projet = self._projet()
        self._controler(projet, 'ok')
        projet.with_user(self.qualite).action_quality_ok()

        self.assertEqual(projet.state, 'etude_decision')
        control = projet.quality_control_ids
        self.assertEqual(control.controlled_by_id, self.qualite)
        self.assertTrue(control.date)

    def test_a_completer_rend_la_main_au_porteur(self):
        projet = self._projet()
        self._controler(projet, 'a_completer', completude=False,
                        anomalies="Il manque les prévisions financières.")
        projet.with_user(self.qualite).action_quality_complement()
        self.assertEqual(projet.state, 'quality_complement')

    def test_alerte_previent_le_comite_sans_deplacer_le_dossier(self):
        projet = self._projet()
        self._controler(projet, 'alerte', coherence=False,
                        anomalies="Le chiffre d'affaires annoncé contredit le pitch.")
        projet.with_user(self.qualite).action_quality_alerte()

        self.assertEqual(projet.state, 'quality_gate',
                         "Une alerte ne doit pas faire bouger le dossier.")
        message = self._message(projet, "Anomalies signalées au comité CEO")
        self.assertIn(self.ceo.partner_id, message.partner_ids)

    def test_non_conforme_emprunte_la_meme_sortie_que_l_alerte(self):
        """Quatre avis, trois branches. Le contrôle qualité signale au comité,
        il n'écarte jamais un projet lui-même : « la décision métier finale
        reste portée par le workflow et les acteurs autorisés »."""
        projet = self._projet()
        self._controler(projet, 'non_conforme', conformite_criteres=False,
                        anomalies="Hors des critères du dispositif.")
        projet.with_user(self.qualite).action_quality_alerte()

        self.assertEqual(projet.state, 'quality_gate')
        self.assertNotEqual(projet.state, 'rejected')

    def test_les_quatre_avis_existent(self):
        codes = [code for code, _libelle in self.Control._fields['avis'].selection]
        self.assertEqual(codes, ['ok', 'a_completer', 'alerte', 'non_conforme'])

    # ------------------------------------------------------------------
    # Cohérence entre l'avis retenu et la sortie empruntée
    # ------------------------------------------------------------------
    def test_on_ne_transmet_pas_un_dossier_juge_non_conforme(self):
        projet = self._projet()
        self._controler(projet, 'non_conforme', conformite_criteres=False,
                        anomalies="Hors critères.")
        with self.assertRaises(UserError):
            projet.with_user(self.qualite).action_quality_ok()
        self.assertEqual(projet.state, 'quality_gate')

    def test_une_sortie_sans_avis_est_refusee(self):
        projet = self._projet()
        for methode in ('action_quality_ok', 'action_quality_complement',
                        'action_quality_alerte'):
            with self.assertRaises(UserError, msg="%s a été acceptée sans avis." % methode):
                getattr(projet.with_user(self.qualite), methode)()

    def test_un_avis_defavorable_sans_anomalie_est_refuse(self):
        """On ne renvoie pas un dossier au porteur sans lui dire quoi corriger."""
        projet = self._projet()
        self._controler(projet, 'a_completer', completude=False)
        with self.assertRaises(UserError):
            projet.with_user(self.qualite).action_quality_complement()
        self.assertEqual(projet.state, 'quality_gate')

    def test_le_quality_gate_ne_s_ouvre_pas_ailleurs(self):
        projet = self._projet(state='etude_decision')
        with self.assertRaises(UserError):
            projet.with_user(self.qualite).action_quality_ok()

    # ------------------------------------------------------------------
    # La contrainte « remplaçable par un agent IA »
    # ------------------------------------------------------------------
    def test_aucune_transition_ne_depend_de_qui_a_rempli_la_fiche(self):
        """Le contrôleur qui remplit et celui qui conclut peuvent différer.

        C'est la forme testable de « seul le type d'acteur exécutant
        l'activité change » : demain, la fiche sera remplie par un agent et
        conclue par lui-même ou par un humain, sans que rien ne change ici.
        """
        projet = self._projet()
        control = projet._current_quality_control()
        control.with_user(self.qualite).write(dict(CONTROLE_CONFORME, avis='ok'))

        projet.with_user(self.qualite_bis).action_quality_ok()
        self.assertEqual(projet.state, 'etude_decision')
        self.assertEqual(control.controlled_by_id, self.qualite_bis)

    def test_la_logique_de_controle_ne_connait_pas_le_workflow(self):
        """`_avis_suggere()` juge des données, rien d'autre.

        Elle est appelable sur une fiche sans projet en base : si elle
        commençait à lire l'état du dossier, ce test la trahirait — et le
        remplacement par un agent deviendrait un chantier.
        """
        cas = [
            (dict(CONTROLE_CONFORME), 'ok'),
            (dict(CONTROLE_CONFORME, completude=False), 'a_completer'),
            (dict(CONTROLE_CONFORME, justificatifs=False), 'a_completer'),
            (dict(CONTROLE_CONFORME, conformite_criteres=False), 'non_conforme'),
            (dict(CONTROLE_CONFORME, coherence=False), 'alerte'),
            (dict(CONTROLE_CONFORME, qualite_informations=False), 'alerte'),
            (dict(CONTROLE_CONFORME, anomalies="Un doute sur les chiffres."), 'alerte'),
        ]
        fiche = self.Control.new({'project_id': self._projet().id})
        for valeurs, attendu in cas:
            fiche.update(valeurs)
            self.assertEqual(
                fiche._avis_suggere(), attendu,
                "Vérifications %s → avis attendu %s." % (valeurs, attendu))
            self.assertEqual(fiche.avis_suggere, attendu)

    def test_l_avis_suggere_n_impose_rien(self):
        """Le contrôleur reste libre : la suggestion n'écrase pas son avis."""
        projet = self._projet()
        control = self._controler(projet, 'alerte', anomalies="Doute sur la traction.")
        self.assertEqual(control.avis_suggere, 'alerte')
        control.avis = 'ok'
        projet.with_user(self.qualite).action_quality_ok()
        self.assertEqual(projet.state, 'etude_decision')

    # ------------------------------------------------------------------
    # Le retour du porteur
    # ------------------------------------------------------------------
    def test_le_dossier_corrige_revient_avec_une_fiche_neuve(self):
        projet = self._projet()
        self._controler(projet, 'a_completer', completude=False,
                        anomalies="Prévisions financières absentes.")
        projet.with_user(self.qualite).action_quality_complement()

        projet.action_submit_complement()
        self.assertEqual(projet.state, 'quality_gate')
        self.assertEqual(len(projet.quality_control_ids), 2)
        self.assertFalse(projet._current_quality_control().avis)

    def test_un_dossier_incomplet_ne_revient_pas_au_controle(self):
        projet = self._projet()
        self._controler(projet, 'a_completer', completude=False, anomalies="Manque.")
        projet.with_user(self.qualite).action_quality_complement()
        projet.business_model = False

        with self.assertRaises(UserError):
            projet.action_submit_complement()
        self.assertEqual(projet.state, 'quality_complement')

    def test_un_second_controle_peut_debloquer_apres_une_alerte(self):
        """La sortie d'une alerte, c'est un nouveau contrôle — pas une impasse."""
        projet = self._projet()
        self._controler(projet, 'alerte', coherence=False, anomalies="Incohérence.")
        projet.with_user(self.qualite).action_quality_alerte()

        second = projet._current_quality_control()
        self.assertEqual(len(projet.quality_control_ids), 2,
                         "Le second contrôle doit être une fiche neuve.")
        second.write(dict(CONTROLE_CONFORME, avis='ok'))
        projet.with_user(self.qualite).action_quality_ok()
        self.assertEqual(projet.state, 'etude_decision')

    # ------------------------------------------------------------------
    # Qui a le droit
    # ------------------------------------------------------------------
    @mute_logger('odoo.addons.base.models.ir_model')
    def test_le_comite_ceo_ne_rend_pas_l_avis_qualite(self):
        """Séparation des rôles : le CEO lit le contrôle, il ne le rend pas."""
        projet = self._projet()
        self._controler(projet, 'ok')
        with self.assertRaises(AccessError):
            projet.with_user(self.ceo).action_quality_ok()
        self.assertEqual(projet.state, 'quality_gate')

    @mute_logger('odoo.addons.base.models.ir_model')
    def test_le_comite_ceo_lit_mais_ne_modifie_pas_la_fiche(self):
        projet = self._projet()
        control = self._controler(projet, 'ok')
        self.assertEqual(control.with_user(self.ceo).avis, 'ok')
        with self.assertRaises(AccessError):
            control.with_user(self.ceo).write({'avis': 'non_conforme'})

    # ------------------------------------------------------------------
    # Le piège des sous-types de message
    # ------------------------------------------------------------------
    def test_seul_le_retour_au_porteur_sort_par_email(self):
        """`mt_comment` pour ce que le porteur doit recevoir, `mt_note` sinon.

        Une alerte interne partie en `mt_comment` arriverait dans la boîte du
        porteur — exactement le bug déjà payé sur le Module 1.
        """
        note = self.env.ref('mail.mt_note')
        comment = self.env.ref('mail.mt_comment')

        conforme = self._projet()
        self._controler(conforme, 'ok')
        conforme.with_user(self.qualite).action_quality_ok()
        self.assertEqual(
            self._message(conforme, "transmis au comité CEO").subtype_id, note)

        alerte = self._projet()
        self._controler(alerte, 'alerte', coherence=False, anomalies="Incohérence.")
        alerte.with_user(self.qualite).action_quality_alerte()
        self.assertEqual(
            self._message(alerte, "Anomalies signalées").subtype_id, note)

        complement = self._projet()
        self._controler(complement, 'a_completer', completude=False,
                        anomalies="Pièces manquantes.")
        complement.with_user(self.qualite).action_quality_complement()
        self.assertEqual(
            self._message(complement, "Des compléments sont demandés").subtype_id,
            comment)


@tagged('post_install', '-at_install')
class TestExtension5Portail(HttpCase, QualityCommon):
    """Ce que le porteur voit d'un contrôle qualité : la demande, pas l'avis."""

    def _connexion(self):
        self.authenticate('cf5_porteur', 'cf5_porteur')

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

    def _projet_en_complement(self):
        projet = self._projet()
        self._controler(
            projet, 'a_completer', completude=False,
            anomalies="Le plan de trésorerie 2027 est absent du dossier.")
        projet.with_user(self.qualite).action_quality_complement()
        return projet

    def test_le_porteur_lit_ce_qu_on_lui_demande(self):
        projet = self._projet_en_complement()
        self._connexion()
        texte = self._texte(self.url_open('/my/crowdfunding/%s' % projet.id))

        self.assertIn("Compléments demandés", texte)
        self.assertIn("plan de trésorerie 2027", texte)
        self.assertIn("Compléter mon dossier", texte)

    def test_le_porteur_ne_lit_ni_l_avis_ni_le_controleur(self):
        """Les anomalies lui sont adressées ; le reste de la fiche, non."""
        projet = self._projet_en_complement()
        self._connexion()
        for url in ('/my/crowdfunding/%s' % projet.id,
                    '/my/crowdfunding/%s/dossier' % projet.id):
            page = self.url_open(url)
            texte = self._texte(page)
            self.assertNotIn("À compléter", texte)
            self.assertNotIn(self.qualite.name, texte)
            for code in ('a_completer', 'non_conforme', 'quality_gate',
                         'quality_complement'):
                self.assertNotIn(code, page.text,
                                 "Fuite de « %s » sur %s." % (code, url))

    def test_le_porteur_corrige_et_renvoie(self):
        projet = self._projet_en_complement()
        self._connexion()
        reponse = self._poster('/my/crowdfunding/%s/dossier' % projet.id, {
            'business_model': "Abonnement mensuel, révisé.",
            'marche': DOSSIER_INVESTISSEUR['marche'],
            'traction': DOSSIER_INVESTISSEUR['traction'],
            'equipe': DOSSIER_INVESTISSEUR['equipe'],
            'besoin_financier': "8 000 000",
            'utilisation_fonds': DOSSIER_INVESTISSEUR['utilisation_fonds'],
            'previsions_financieres': "Plan de trésorerie 2027 joint.",
        })

        projet.invalidate_recordset()
        self.assertEqual(projet.state, 'quality_gate')
        self.assertEqual(projet.business_model, "Abonnement mensuel, révisé.")
        self.assertEqual(len(projet.quality_control_ids), 2)
        self.assertIn("Votre dossier est en cours de vérification", self._texte(reponse))

    def test_le_porteur_peut_enregistrer_sa_correction_sans_la_renvoyer(self):
        projet = self._projet_en_complement()
        self._connexion()
        self._poster('/my/crowdfunding/%s/dossier' % projet.id, {
            'business_model': "Brouillon de correction.",
            'enregistrer': '1',
        })

        projet.invalidate_recordset()
        self.assertEqual(projet.state, 'quality_complement')
        self.assertEqual(projet.business_model, "Brouillon de correction.")
