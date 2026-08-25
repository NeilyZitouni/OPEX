import html
import re

from lxml import html as lxml_html

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

CSRF_TOKEN = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')
CSRF_SESSION = re.compile(r'csrf_token:\s*"([^"]+)"')

#: Tous les codes d'états techniques du workflow. Aucun ne doit atteindre un
#: écran d'acteur, quel qu'il soit (section 16).
CODES_ETATS = (
    'depot_express', 'pre_analyse', 'dossier_progressif', 'quality_gate',
    'quality_complement', 'etude_decision', 'accompagnement', 'reevaluation',
    'matching_financier', 'mise_en_relation', 'decision_financeur',
)


class InterfacesCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.crowdfunding.project']
        cls.Relation = cls.env['opex.crowdfunding.relation']
        cls.Mission = cls.env['opex.crowdfunding.mission']
        cls.Queue = cls.env['opex.crowdfunding.work.queue']

        cls.porteur = new_test_user(
            cls.env, login='cf11_porteur', password='cf11_porteur',
            groups='base.group_portal', name="Rachid Belkacem")
        cls.ceo = new_test_user(
            cls.env, login='cf11_ceo', password='cf11_ceo',
            groups='base.group_user,opex_crowdfunding.group_ceo')
        cls.qualite = new_test_user(
            cls.env, login='cf11_qualite',
            groups='base.group_user,opex_crowdfunding.group_quality_control')
        cls.investisseur = new_test_user(
            cls.env, login='cf11_investisseur', password='cf11_investisseur',
            groups='base.group_portal', name="Fonds Industrie DZ")
        cls.investisseur.partner_id.write({
            'cf_is_financial_actor': True, 'cf_actor_type': 'fonds'})
        cls.expert = new_test_user(
            cls.env, login='cf11_expert', password='cf11_expert',
            groups='base.group_portal', name="Nadia Cherif")
        cls.expert.partner_id.write({
            'cf_is_expert': True, 'cf_expertise_secteur': 'industrie'})

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
            'besoin_financier': 8000000.0,
            'state': state,
        }
        donnees.update(valeurs)
        return self.Project.create(donnees)

    def _relation(self, projet=None, niveau='limited'):
        projet = projet or self._projet(state='mise_en_relation')
        relation = self.Relation.create({
            'project_id': projet.id,
            'partner_id': self.investisseur.partner_id.id,
        })
        if niveau != 'teaser':
            relation.action_exprimer_interet()
            relation.with_user(self.porteur).sudo().action_autoriser_partage()
        return relation

    def _mission(self):
        projet = self._projet()
        projet.with_user(self.ceo).action_route_maturation()
        accompagnement = projet._accompagnement_en_cours()
        return self.Mission.create({
            'accompagnement_id': accompagnement.id,
            'expert_id': self.expert.partner_id.id,
            'objectif': "Business Model & Go-to-Market",
            'date_fin': fields.Date.today(),
        })


@tagged('post_install', '-at_install')
class TestExtension11Notifications(InterfacesCommon):
    """`mt_note` pour l'interne, `mt_comment` pour ce que le porteur doit
    recevoir — le bug déjà payé sur le Module 1."""

    def _subtypes(self, projet, extrait):
        note = self.env.ref('mail.mt_note')
        comment = self.env.ref('mail.mt_comment')
        messages = projet.message_ids.filtered(lambda m: extrait in (m.body or ''))
        self.assertTrue(messages, "Aucun message ne contient « %s »." % extrait)
        return messages[0].subtype_id, note, comment

    def test_les_decisions_qui_concernent_le_porteur_partent_par_email(self):
        cas = [
            ('go', "Pré-analyse : GO"),
            ('orientation', "orientation vers un accompagnement"),
        ]
        for issue, extrait in cas:
            projet = self._projet(state='pre_analyse')
            projet._current_prequalification()
            getattr(projet.with_user(self.ceo), 'action_%s' % issue)()
            subtype, _note, comment = self._subtypes(projet, extrait)
            self.assertEqual(subtype, comment,
                             "L'issue « %s » ne part pas au porteur." % issue)

    def test_les_routes_de_l_etude_partent_par_email(self):
        projet = self._projet()
        projet.with_user(self.ceo).action_route_investment_ready()
        subtype, _note, comment = self._subtypes(projet, "route A")
        self.assertEqual(subtype, comment)

        projet = self._projet()
        projet.with_user(self.ceo).action_route_maturation()
        subtype, _note, comment = self._subtypes(projet, "route B")
        self.assertEqual(subtype, comment)

    def test_le_refus_annonce_la_decision_sans_livrer_le_motif(self):
        """Le porteur reçoit la décision ; le motif reste au dossier
        d'instruction. C'est un choix, et il est réversible d'une ligne."""
        projet = self._projet(motif_rejet="Marché déjà couvert par deux adhérents.")
        projet.with_user(self.ceo).action_route_rejected()

        subtype, _note, comment = self._subtypes(projet, "n'a pas été retenu")
        self.assertEqual(subtype, comment)
        interne, note, _comment = self._subtypes(projet, "Marché déjà couvert")
        self.assertEqual(interne, note)

    def test_les_echanges_internes_restent_internes(self):
        """Une alerte qualité partie en `mt_comment` arriverait dans la boîte
        du porteur."""
        projet = self._projet(state='quality_gate')
        control = projet._open_quality_control()
        control.write({
            'completude': True, 'justificatifs': True, 'conformite_criteres': True,
            'coherence': False, 'qualite_informations': True,
            'anomalies': "Incohérence sur le chiffre d'affaires.",
            'avis': 'alerte',
        })
        projet.with_user(self.qualite).action_quality_alerte()

        subtype, note, _comment = self._subtypes(projet, "Anomalies signalées")
        self.assertEqual(subtype, note)

    def test_aucun_canal_sms(self):
        """Décision reprise du Module 1 : portail et email, pas de SMS.

        Le dossier de tests est exclu du balayage : il contient les chaînes
        qu'il recherche, et sans cette exclusion l'assertion se trouverait
        elle-même — un rouge permanent qui n'apprend rien.
        """
        import os
        trouve = []
        for racine, _dossiers, fichiers in os.walk(
                os.path.join(os.path.dirname(__file__), '..')):
            if '__pycache__' in racine or os.path.basename(racine) == 'tests':
                continue
            for fichier in fichiers:
                if not fichier.endswith(('.py', '.xml')):
                    continue
                chemin_complet = os.path.join(racine, fichier)
                with open(chemin_complet, encoding='utf-8') as flux:
                    contenu = flux.read()
                if '_message_sms' in contenu or 'sms.sms' in contenu:
                    trouve.append(fichier)
        self.assertFalse(trouve, "Canal SMS trouvé dans : %s" % trouve)


@tagged('post_install', '-at_install')
class TestExtension11WorkQueue(InterfacesCommon):
    """La Smart Work Queue du comité (section 16)."""

    def test_chaque_compteur_compte_ce_que_son_bouton_ouvre(self):
        """Un compteur qui ne mène pas à ce qu'il a compté est pire qu'inutile.

        On compare, pour les six files, le compteur et le nombre de lignes que
        renvoie le domaine du bouton correspondant.
        """
        # Sans données, les six compteurs valent zéro et le test passerait même
        # si un bouton ouvrait tout autre chose. On garnit donc chaque file.
        self._projet(state='depot_express')
        self._projet(state='pre_analyse')
        self._projet(state='matching_financier')
        self._projet(state='etude_decision')
        anomalie = self._projet(state='quality_gate')
        anomalie._open_quality_control().write(
            {'avis': 'alerte', 'anomalies': "Incohérence."})
        self._projet(state='quality_gate')
        self._relation(niveau='teaser').action_exprimer_interet()
        mission = self._mission()
        mission.accompagnement_id.write({'state': 'actif'})
        mission.write({'state': 'acceptee',
                       'date_fin': fields.Date.to_date('2020-01-01')})

        queue = self.Queue.with_user(self.ceo).create({})
        #: Le champ compteur, et le bouton censé ouvrir ce qu'il a compté. On
        #: passe par l'action — donc par ce que l'utilisateur verra vraiment —
        #: et non par le domaine interne, sans quoi le test comparerait une
        #: méthode à elle-même.
        files = (
            ('prequalifications', 'action_open_prequalifications'),
            ('controles_anomalie', 'action_open_controles_anomalie'),
            ('decisions_ceo', 'action_open_decisions_ceo'),
            ('matchings_a_valider', 'action_open_matchings_a_valider'),
            ('investisseurs_en_attente', 'action_open_investisseurs_en_attente'),
            ('accompagnements_en_retard', 'action_open_accompagnements_en_retard'),
        )
        for champ, bouton in files:
            action = getattr(queue, bouton)()
            attendu = self.env[action['res_model']].with_user(self.ceo).search_count(
                action['domain'])
            self.assertEqual(
                queue[champ], attendu,
                "Le compteur « %s » annonce %s dossiers et son bouton en ouvre %s."
                % (champ, queue[champ], attendu))

    def test_les_preanalyses_en_attente_sont_comptees(self):
        avant = self.Queue.with_user(self.ceo).create({}).prequalifications
        self._projet(state='depot_express')
        self._projet(state='pre_analyse')
        apres = self.Queue.with_user(self.ceo).create({}).prequalifications
        self.assertEqual(apres, avant + 2)

    def test_un_controle_en_anomalie_remonte_dans_la_file(self):
        avant = self.Queue.with_user(self.ceo).create({}).controles_anomalie
        projet = self._projet(state='quality_gate')
        control = projet._open_quality_control()
        control.write({'avis': 'alerte', 'anomalies': "Incohérence."})
        apres = self.Queue.with_user(self.ceo).create({}).controles_anomalie
        self.assertEqual(apres, avant + 1)

    def test_un_investisseur_qui_attend_une_autorisation_remonte(self):
        avant = self.Queue.with_user(self.ceo).create({}).investisseurs_en_attente
        self._relation(niveau='teaser').action_exprimer_interet()
        apres = self.Queue.with_user(self.ceo).create({}).investisseurs_en_attente
        self.assertEqual(apres, avant + 1)

    def test_un_investisseur_deja_autorise_ne_remonte_plus(self):
        relation = self._relation()  # intérêt exprimé puis partage autorisé
        queue = self.Queue.with_user(self.ceo).create({})
        en_attente = self.env['opex.crowdfunding.relation'].search(
            queue._domaine_investisseurs_en_attente())
        self.assertNotIn(relation, en_attente)

    def test_une_mission_en_retard_remonte(self):
        avant = self.Queue.with_user(self.ceo).create({}).accompagnements_en_retard
        mission = self._mission()
        mission.accompagnement_id.write({'state': 'actif'})
        mission.write({'state': 'acceptee',
                       'date_fin': fields.Date.to_date('2020-01-01')})
        apres = self.Queue.with_user(self.ceo).create({}).accompagnements_en_retard
        self.assertEqual(apres, avant + 1)

    def test_le_bouton_ouvre_bien_une_liste_filtree(self):
        queue = self.Queue.with_user(self.ceo).create({})
        action = queue.action_open_decisions_ceo()
        self.assertEqual(action['res_model'], 'opex.crowdfunding.project')
        self.assertEqual(action['domain'], [('state', '=', 'etude_decision')])

    @mute_logger('odoo.addons.base.models.ir_model')
    def test_la_file_est_reservee_au_comite(self):
        with self.assertRaises(AccessError):
            self.Queue.with_user(self.qualite).create({}).prequalifications


@tagged('post_install', '-at_install')
class TestExtension11Interfaces(HttpCase, InterfacesCommon):
    """Les quatre écrans, vérifiés avec un compte de chaque acteur."""

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

    def _comme_une_transaction_anterieure(self, enregistrement):
        """Fait comme si l'enregistrement venait d'une requête précédente.

        Odoo **désactive** le suivi des champs pour un enregistrement créé
        dans la transaction courante : créer puis modifier au même endroit ne
        laisse aucune trace, et l'historique paraît vide sans que rien ne soit
        cassé. En production, le dépôt du porteur et les décisions du comité
        sont dans des requêtes distinctes — ce que cette méthode reproduit.
        """
        self.env.cr.precommit.run()
        self.env.cr.precommit.data.pop(
            'mail.tracking.%s' % enregistrement._name, None)

    def _assert_aucun_code_etat(self, page, url):
        """Aucun code d'état dans la page — hors adresses des liens.

        Les `href` et `action` sont retirés avant la recherche : une route
        nommée `/accompagnement/demander` n'expose pas l'état `accompagnement`
        au porteur, elle nomme un écran. Tout le reste de la page est examiné,
        y compris ce qui serait masqué en CSS — c'est là qu'une fuite se
        cacherait.
        """
        document = lxml_html.fromstring(page.text)
        for element in document.xpath('//*[@href or @action]'):
            element.attrib.pop('href', None)
            element.attrib.pop('action', None)
        contenu = html.unescape(
            lxml_html.tostring(document, encoding='unicode'))
        for code in CODES_ETATS:
            self.assertNotIn(code, contenu,
                             "Le code « %s » est exposé sur %s." % (code, url))

    # ------------------------------------------------------------------
    # 1. Le porteur
    # ------------------------------------------------------------------
    def test_ecran_porteur_progression_et_prochaine_action(self):
        projet = self._projet(state='quality_gate')
        self.authenticate('cf11_porteur', 'cf11_porteur')
        url = '/my/projects/%s' % projet.id
        page = self.url_open(url)
        texte = self._texte(page)

        for jalon in ("Demande reçue", "Projet présélectionné", "Dossier complété",
                      "Étude", "Mise en relation"):
            self.assertIn(jalon, texte)
        self.assertIn("Votre prochaine action", texte)
        self.assertIn("Votre dossier est en cours de vérification", texte)
        self._assert_aucun_code_etat(page, url)

    def test_ecran_porteur_historique(self):
        """L'audit trail, côté porteur : qui, quand, quoi."""
        projet = self._projet(state='pre_analyse')
        projet._current_prequalification()
        self._comme_une_transaction_anterieure(projet)
        projet.with_user(self.ceo).action_go()
        # Les messages de suivi sont générés au précommit (`_track_finalize`),
        # pas au flush : une transaction de test ne commite jamais.
        self.env.cr.precommit.run()

        self.authenticate('cf11_porteur', 'cf11_porteur')
        url = '/my/projects/%s/historique' % projet.id
        page = self.url_open(url)
        texte = self._texte(page)

        self.assertIn("Pré-analyse", texte)
        self.assertIn("Dossier à compléter", texte)
        self.assertIn(self.ceo.name, texte)
        self._assert_aucun_code_etat(page, url)

    @mute_logger('odoo.addons.base.models.ir_rule', 'odoo.addons.base.models.ir_model')
    def test_l_historique_du_porteur_ne_montre_pas_les_notes_internes(self):
        projet = self._projet(motif_rejet="Marché déjà couvert par deux adhérents.")
        projet.with_user(self.ceo).action_route_rejected()

        self.authenticate('cf11_porteur', 'cf11_porteur')
        page = self.url_open('/my/projects/%s/historique' % projet.id)
        contenu = html.unescape(page.text)
        self.assertIn("n'a pas été retenu", self._texte(page))
        self.assertNotIn("Marché déjà couvert", contenu,
                         "Une note interne a fuité dans l'historique du porteur.")

    # ------------------------------------------------------------------
    # 2. L'investisseur
    # ------------------------------------------------------------------
    def test_ecran_investisseur_n_projets_et_scores(self):
        relation = self._relation()
        self.env['opex.crowdfunding.matching.candidate'].create({
            'project_id': relation.project_id.id,
            'partner_id': self.investisseur.partner_id.id,
            'state': 'proposed',
            'score': 92.0,
            'detail': "Score de démonstration.",
        })

        self.authenticate('cf11_investisseur', 'cf11_investisseur')
        url = '/my/opportunities'
        page = self.url_open(url)
        texte = self._texte(page)

        self.assertIn("correspond", texte)
        self.assertIn("à vos critères", texte)
        self.assertIn("92 %", texte)
        self.assertIn("Découvrir", texte)
        self._assert_aucun_code_etat(page, url)

    def test_l_investisseur_ne_voit_pas_les_dossiers_des_autres(self):
        self._relation()
        autre = new_test_user(
            self.env, login='cf11_autre_inv', password='cf11_autre_inv',
            groups='base.group_portal', name="Capital Oran")

        self.authenticate('cf11_autre_inv', 'cf11_autre_inv')
        texte = self._texte(self.url_open('/my/opportunities'))
        self.assertIn("Aucun dossier ne vous est soumis", texte)

    # ------------------------------------------------------------------
    # 3. L'expert
    # ------------------------------------------------------------------
    def test_ecran_expert_mission_proposee_et_deux_boutons(self):
        mission = self._mission()
        self.authenticate('cf11_expert', 'cf11_expert')
        url = '/my/missions'
        page = self.url_open(url)
        texte = self._texte(page)

        self.assertIn("Nouvelle mission proposée", texte)
        self.assertIn("Supervision d'atelier", texte)
        self.assertIn("Business Model & Go-to-Market", texte)
        self.assertIn("Accepter", texte)
        self.assertIn("Décliner", texte)
        self._assert_aucun_code_etat(page, url)

    def test_l_expert_accepte_depuis_son_ecran(self):
        mission = self._mission()
        self.authenticate('cf11_expert', 'cf11_expert')

        self.url_open('/my/missions/%s/reponse' % mission.id, data={
            'reponse': 'accepter', 'csrf_token': self._jeton('/my/missions')})

        mission.invalidate_recordset()
        self.assertEqual(mission.state, 'acceptee')
        texte = self._texte(self.url_open('/my/missions'))
        self.assertNotIn("Nouvelle mission proposée", texte)

    def test_l_expert_decline_depuis_son_ecran(self):
        mission = self._mission()
        self.authenticate('cf11_expert', 'cf11_expert')

        self.url_open('/my/missions/%s/reponse' % mission.id, data={
            'reponse': 'decliner', 'csrf_token': self._jeton('/my/missions')})

        mission.invalidate_recordset()
        self.assertEqual(mission.state, 'declinee')

    def test_l_expert_ne_voit_ni_le_dossier_ni_les_missions_des_autres(self):
        """« Accès au périmètre de sa mission » (section 3)."""
        mission = self._mission()
        projet = mission.project_id
        projet.write({'business_model': "Abonnement mensuel par atelier."})

        self.authenticate('cf11_expert', 'cf11_expert')
        page = self.url_open('/my/missions')
        contenu = html.unescape(page.text)
        self.assertNotIn("Abonnement mensuel", contenu,
                         "Le dossier du porteur a fuité à l'expert.")

        autre_expert = new_test_user(
            self.env, login='cf11_autre_expert', password='cf11_autre_expert',
            groups='base.group_portal', name="Karim Slimani")
        self.authenticate('cf11_autre_expert', 'cf11_autre_expert')
        texte = self._texte(self.url_open('/my/missions'))
        self.assertIn("Aucune mission", texte)

    def test_un_expert_ne_repond_pas_pour_un_autre(self):
        mission = self._mission()
        new_test_user(
            self.env, login='cf11_intrus', password='cf11_intrus',
            groups='base.group_portal', name="Intrus")

        self.authenticate('cf11_intrus', 'cf11_intrus')
        self.url_open('/my/missions/%s/reponse' % mission.id, data={
            'reponse': 'accepter', 'csrf_token': self._jeton('/my/missions')})

        mission.invalidate_recordset()
        self.assertEqual(mission.state, 'proposee')

    @mute_logger('odoo.addons.base.models.ir_rule', 'odoo.addons.base.models.ir_model')
    def test_la_regle_ferme_la_lecture_des_missions_d_autrui(self):
        mission = self._mission()
        with self.assertRaises(AccessError):
            mission.with_user(self.investisseur).read(['objectif'])

    # ------------------------------------------------------------------
    # 4. Les tuiles du portail
    # ------------------------------------------------------------------
    def test_les_tuiles_sont_visibles_pour_chaque_acteur(self):
        """Même piège `d-none` que la tuile « Mes projets » : sans
        `config_card`, la carte reste masquée tant que le compteur est nul."""
        cas = (
            ('cf11_porteur', 'cf11_porteur', '/my/projects'),
            ('cf11_investisseur', 'cf11_investisseur', '/my/opportunities'),
            ('cf11_expert', 'cf11_expert', '/my/missions'),
        )
        for login, motdepasse, url in cas:
            self.authenticate(login, motdepasse)
            page = self.url_open('/my')
            document = lxml_html.fromstring(page.text)
            cartes = document.xpath(
                "//div[contains(@class, 'o_portal_index_card')][.//a[@href='%s']]" % url)
            self.assertTrue(cartes, "Tuile absente pour %s." % url)
            self.assertNotIn('d-none', cartes[0].get('class', ''),
                             "Tuile masquée pour %s." % url)
