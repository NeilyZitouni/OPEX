"""IA-3 : le contrôle qualité assisté — §11 et §12.

Le test qui gouverne le fichier est
`test_an_ai_advice_never_activates_a_profile` : l'agent prépare, un humain
tranche. Tous les autres décrivent ce que le contrôle sait faire ; celui-là
décrit ce qu'il ne doit **jamais** faire.
"""

import re
from datetime import date, timedelta
from unittest.mock import patch

from odoo.tests.common import tagged

from .common import MissionCase

QUALIFICATION_CODE = 'expert_qualification'


@tagged('post_install', '-at_install')
class TestQualificationReview(MissionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Review = cls.env['opex.expert.qualification.review']
        cls.Anomaly = cls.env['opex.expert.qualification.anomaly']
        cls.Profile = cls.env['opex.innovation.expert.profile']
        cls.Bridge = cls.env['opex.ai.bridge']
        cls.Definition = cls.env['opex.workflow.definition']
        cls.cisa = cls.env.ref('opex_intervenants.cert_cisa')

    # ------------------------------------------------------------
    # Fabriques
    # ------------------------------------------------------------

    def _profile(self, nom="Intervenant contrôlé", **overrides):
        partner = self.env['res.partner'].sudo().create(dict({
            'name': nom,
            'email': "%s@example.dz" % re.sub(r'\W+', '.', nom.lower()),
            'phone': "+213 555 %s" % (abs(hash(nom)) % 900000 + 100000),
        }, **overrides.pop('partner', {})))
        values = {
            'partner_id': partner.id,
            'domaine_expertise': "Audit des systèmes d'information",
            'fonction': "Consultant senior",
            'annees_experience': 12,
            'description_expertise': "Quinze audits SI en environnement bancaire.",
        }
        values.update(overrides)
        profile = self.Profile.sudo().create(values)
        partner.sudo().expert_profile_id = profile.id
        return profile

    def _complete_profile(self, **overrides):
        """Un profil complet : rien de **bloquant** ne doit s'y déclencher.

        Complet ne veut pas dire sans anomalie : il n'a aucune pièce jointe,
        et `_check_conformite()` le signale en `warning`. La distinction a
        compté — une première régression volontaire conditionnée à
        « aucune anomalie » ne s'est jamais déclenchée sur ce profil, et le
        test de garde est resté vert sans rien prouver.
        """
        profile = self._profile(**overrides)
        self.env['opex.expert.skill'].sudo().create({
            'profile_id': profile.id,
            'competence_id': self.competence.id,
            'niveau': 'expert',
            'source': 'expert', 'confiance': 'expert',
        })
        self.env['opex.expert.experience'].sudo().create({
            'profile_id': profile.id,
            'name': "Audit SI d'une banque",
            'date_debut': date(2018, 1, 1),
            'date_fin': date(2021, 12, 31),
        })
        self.env['opex.expert.certification'].sudo().create({
            'profile_id': profile.id,
            'certification_id': self.cisa.id,
            'name': "CISA",
            'source': 'expert', 'confiance': 'expert',
            'date_expiration': date.today() + timedelta(days=365),
        })
        self.env['opex.expert.availability'].sudo().create({
            'profile_id': profile.id,
            'date_debut': date.today() - timedelta(days=1),
            'date_fin': date.today() + timedelta(days=90),
            'taux': 100,
        })
        return profile

    def _review(self, profile):
        return self.Review.sudo().create({'profile_id': profile.id})

    def _run_without_ai(self, review):
        """Le contrôle, IA explicitement absente."""
        with patch.object(type(self.Bridge), '_ai_available',
                          return_value=False):
            review.action_run()
        return review

    def _anomalies(self, review, control=None):
        anomalies = review.anomaly_ids
        if control:
            anomalies = anomalies.filtered(lambda a: a.control == control)
        return anomalies

    #
    # LE TEST QUI GOUVERNE — §12
    #

    def test_an_ai_advice_never_activates_a_profile(self):
        """« La décision d'activation reste gouvernée par les règles OPEX. »

        Un avis, même sans la moindre anomalie, ne fait avancer le dossier
        d'aucune étape. C'est ce qui sépare un agent qui prépare d'un agent
        qui décide.

        L'assertion positive vient d'abord : le contrôle a bien tourné et a
        bien produit un avis. Sans elle, un contrôle qui planterait
        silencieusement passerait ce test.
        """
        profile = self._complete_profile(nom="Profil sain")
        review = self._review(profile)
        etape_avant = review.workflow_stage_id

        with patch.object(type(self.Bridge), '_ai_available',
                          return_value=True), \
                patch.object(type(self.Bridge), '_ai_call_prompt',
                             return_value={'anomalies': []}):
            review.action_run()

        # Le contrôle a tourné.
        self.assertTrue(review.date_controle)
        self.assertTrue(review.recommandation)
        self.assertTrue(review.ia_sollicitee)

        # …et il n'a rien décidé.
        self.assertEqual(
            review.workflow_stage_id, etape_avant,
            "Le contrôle a fait avancer le dossier : l'agent décide au lieu "
            "de préparer, ce que le §12 interdit.")
        self.assertNotEqual(review.workflow_stage_id.code, 'active')
        self.assertNotEqual(review.workflow_stage_id.code, 'qualified')

    def test_no_transition_condition_reads_what_the_control_produces(self):
        """La garde de configuration, et elle est plus forte que la précédente.

        Le test ci-dessus vérifie qu'un passage du contrôle ne déclenche rien.
        Celui-ci vérifie qu'**aucune condition ne pourrait** le faire : une
        règle qui lirait `blocking_count` rendrait l'activation dépendante
        d'un avis, sans qu'aucun appel à `do_transition()` soit écrit nulle
        part.

        C'est la forme que prendrait le défaut si quelqu'un voulait « gagner
        du temps » : pas du Python, une condition.
        """
        definition = self.Definition.sudo()._get_for_code(QUALIFICATION_CODE)
        self.assertTrue(definition, "La définition du §11 est absente.")

        produits = ('anomaly_count', 'blocking_count', 'recommandation',
                    'ia_sollicitee', 'date_controle')
        examinees = 0
        for transition in definition.transition_ids:
            for condition in transition.condition_ids:
                examinees += 1
                expression = "%s %s" % (
                    condition.expression or '', condition.name or '')
                for champ in produits:
                    self.assertNotIn(
                        champ, expression,
                        "La transition « %s » conditionne son franchissement "
                        "à « %s », produit par le contrôle : l'activation "
                        "dépendrait d'un avis." % (transition.name, champ))
        # Une boucle qui n'examine rien passe au vert. Ici il n'y a
        # légitimement aucune condition, et c'est cela qu'on affirme.
        self.assertEqual(
            examinees, 0,
            "Des conditions sont apparues sur le workflow de qualification : "
            "vérifier une par une qu'aucune ne lit un avis.")

    def test_the_control_never_calls_do_transition(self):
        """Le pendant côté source. Règle 15 : on examine du code, pas de la
        prose — le fichier explique en toutes lettres qu'il n'appelle pas
        `do_transition()`, et un test naïf rougirait sur sa propre
        documentation.
        """
        import os
        chemin = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'models', 'expert_qualification_review.py')
        with open(chemin, encoding='utf-8') as fichier:
            source = fichier.read()
        source = re.sub(r'("""|\'\'\')(?:.|\n)*?\1', '', source)
        source = re.sub(r'#[^\n]*', '', source)

        self.assertNotIn(
            'do_transition', source,
            "Le contrôle qualité fait avancer un workflow.")
        self.assertIn(
            'def action_run', source,
            "Le source examiné n'est pas celui du contrôle : ce test ne "
            "vérifie rien.")

    #
    # LES CONTRÔLES DÉTERMINISTES — sans le moindre appel
    #

    def test_the_deterministic_checks_find_an_inconsistent_date(self):
        """Une date incohérente se voit sans appeler personne.

        Deux cas, et ils n'arrivent pas par le même chemin :

        - **début dans le futur** : personne ne l'interdit, il s'atteint
          normalement ;
        - **fin avant début** : `opex.expert.experience._check_dates()`
          (Extension 3) le refuse déjà par une contrainte. Le cas n'arrive
          donc **jamais par l'écran** — mais une contrainte Python ne
          s'applique qu'à l'ORM, et un import le laisse passer.

        Le second est donc éprouvé **en écrivant en base**, faute de quoi ce
        test ne mesurerait rien : il vérifierait une garde par un chemin qui
        ne peut pas l'atteindre. Règle 20.
        """
        profile = self._complete_profile(nom="Dates incoherentes")
        self.env['opex.expert.experience'].sudo().create({
            'profile_id': profile.id,
            'name': "Mission qui commence demain",
            'date_debut': date.today() + timedelta(days=30),
        })
        importee = self.env['opex.expert.experience'].sudo().create({
            'profile_id': profile.id,
            'name': "Mission a l'envers (importee)",
            'date_debut': date(2021, 1, 1),
            'date_fin': date(2022, 6, 1),
        })
        # Le chemin réel du défaut : une donnée qui n'est pas passée par
        # l'ORM. La contrainte de l'Extension 3 ne s'y applique pas.
        self.env.cr.execute(
            "UPDATE opex_expert_experience SET date_fin = %s WHERE id = %s",
            (date(2020, 1, 1), importee.id))
        importee.invalidate_recordset()

        review = self._review(profile)
        with patch.object(type(self.Bridge), '_ai_call_prompt') as appelee:
            self._run_without_ai(review)

        appelee.assert_not_called()
        coherence = self._anomalies(review, 'coherence')
        self.assertTrue(
            coherence, "Aucune incohérence de date détectée.")
        self.assertTrue(all(a.origin == 'deterministe' for a in coherence))

        libelles = " ".join(coherence.mapped('name'))
        self.assertIn("commence demain", libelles)
        self.assertIn("importee", libelles)
        self.assertTrue(
            coherence.filtered(lambda a: a.severity == 'blocking'),
            "Une fin antérieure au début n'est pas signalée comme bloquante.")

    def test_the_deterministic_checks_find_an_expired_certification(self):
        profile = self._complete_profile(nom="Certif expiree")
        self.env['opex.expert.certification'].sudo().create({
            'profile_id': profile.id,
            'certification_id': self.cisa.id,
            'name': "CISA périmée",
            'source': 'expert', 'confiance': 'expert',
            'date_expiration': date.today() - timedelta(days=30),
        })
        review = self._review(profile)

        with patch.object(type(self.Bridge), '_ai_call_prompt') as appelee:
            self._run_without_ai(review)

        appelee.assert_not_called()
        certifications = self._anomalies(review, 'certifications')
        self.assertTrue(certifications)
        self.assertIn("expirée", " ".join(certifications.mapped('name')))
        self.assertTrue(all(a.origin == 'deterministe'
                            for a in certifications))

    def test_an_unmatched_certification_is_reported_as_a_question(self):
        """La note du §11, reprise ici : une certification non rapprochée
        n'est pas une non-conformité, c'est quelque chose qu'on ne sait pas
        encore."""
        profile = self._complete_profile(nom="Certif libre")
        self.env['opex.expert.certification'].sudo().create({
            'profile_id': profile.id,
            'name': "Habilitation maison non referencee",
            'source': 'expert', 'confiance': 'expert',
            'date_expiration': date.today() + timedelta(days=200),
        })
        review = self._review(profile)
        self._run_without_ai(review)

        libelles = " ".join(
            self._anomalies(review, 'certifications').mapped('name'))
        self.assertIn("non rapprochée", libelles)

    def test_a_probable_duplicate_is_detected_before_creation(self):
        """§16 — deux fiches pour une même personne dispersent sa réputation.

        La détection est **déterministe et bornée** : email exact ou téléphone
        réduit à ses chiffres. Aucune approximation de nom — une fausse alerte
        sur un doublon coûte plus cher qu'une alerte manquée, puisqu'elle fait
        fusionner deux personnes.
        """
        premier = self._complete_profile(nom="Karim Original")
        double = self.env['res.partner'].sudo().create({
            'name': "K. Original (doublon)",
            'email': premier.partner_id.email,
        })
        profile_double = self.Profile.sudo().create({
            'partner_id': double.id,
            'domaine_expertise': "Audit",
            'fonction': "Consultant",
            'annees_experience': 5,
            'description_expertise': "x",
        })
        double.sudo().expert_profile_id = profile_double.id

        review = self._review(profile_double)
        self._run_without_ai(review)

        identite = self._anomalies(review, 'identite')
        self.assertTrue(
            identite.filtered(lambda a: "Doublon" in a.name),
            "Le doublon par email n'est pas détecté.")
        self.assertEqual(
            identite.filtered(lambda a: "Doublon" in a.name)[0].severity,
            'blocking')

    def test_a_short_phone_number_raises_no_duplicate(self):
        """Moins de huit chiffres n'identifie personne.

        Sans cette borne, un poste interne ou un indicatif seul ferait
        remonter tout l'annuaire comme doublon probable — et un contrôleur
        qui reçoit trois fausses alertes cesse de lire les vraies.
        """
        profile = self._complete_profile(
            nom="Poste interne", partner={'phone': "4021", 'email': False})
        doublons = self.Review._probable_duplicates(profile.partner_id)
        self.assertFalse(doublons.filtered(
            lambda p: p.phone == "4021" and p != profile.partner_id))

    def test_the_seven_controls_of_the_table_are_all_covered(self):
        """Les sept du §11 existent, et chacun peut produire une anomalie."""
        from odoo.addons.opex_intervenants.models.expert_qualification_review \
            import CONTROLS
        codes = {code for code, _label in CONTROLS}
        self.assertEqual(codes, {
            'identite', 'completude', 'coherence', 'competences',
            'certifications', 'references', 'conformite'})
        for code in codes:
            self.assertTrue(
                hasattr(self.Review, '_check_%s' % code)
                or code == 'coherence',
                "Le contrôle « %s » n'a pas de méthode." % code)

    def test_an_empty_profile_triggers_several_controls(self):
        """Le cas le plus fréquent : un profil à peine commencé."""
        partner = self.env['res.partner'].sudo().create({'name': "Profil vide"})
        profile = self.Profile.sudo().create({'partner_id': partner.id})
        partner.sudo().expert_profile_id = profile.id
        review = self._review(profile)
        self._run_without_ai(review)

        touches = set(review.anomaly_ids.mapped('control'))
        for attendu in ('identite', 'completude', 'competences', 'references'):
            self.assertIn(
                attendu, touches,
                "Le contrôle « %s » n'a rien relevé sur un profil vide."
                % attendu)
        self.assertTrue(review.blocking_count)

    #
    # SANS CLÉ — LA MOITIÉ QUI VÉRIFIE RESTE
    #

    def test_the_deterministic_checks_run_without_any_api_key(self):
        """La règle 1 du service, portée au métier.

        Sans assistance, le contrôle perd les jugements et **garde les
        vérifications**. C'est ce qui rend le module livrable à un cluster qui
        n'active pas l'IA.
        """
        profile = self._complete_profile(nom="Sans cle")
        self.env['opex.expert.experience'].sudo().create({
            'profile_id': profile.id, 'name': "Commence demain",
            'date_debut': date.today() + timedelta(days=30),
        })
        review = self._review(profile)
        self._run_without_ai(review)

        self.assertTrue(review.date_controle)
        self.assertFalse(review.ia_sollicitee)
        self.assertTrue(
            review.ia_indisponible_motif,
            "L'avis ne dit pas pourquoi l'IA n'a pas été sollicitée.")
        self.assertTrue(
            self._anomalies(review, 'coherence'),
            "Les contrôles déterministes n'ont pas tourné sans clé.")
        self.assertTrue(all(a.origin == 'deterministe'
                            for a in review.anomaly_ids))

    def test_an_unusable_ai_answer_is_not_fatal(self):
        profile = self._complete_profile(nom="IA muette")
        review = self._review(profile)

        with patch.object(type(self.Bridge), '_ai_available',
                          return_value=True), \
                patch.object(type(self.Bridge), '_ai_call_prompt',
                             return_value=None):
            review.action_run()

        self.assertTrue(review.date_controle)
        self.assertFalse(review.ia_sollicitee)
        self.assertTrue(review.ia_indisponible_motif)

    #
    # L'IA PROPOSE, ELLE NE BLOQUE PAS
    #

    def test_an_ai_anomaly_can_never_be_blocking(self):
        """Un jugement de modèle ne bloque pas un dossier.

        `blocking` est ce que lit un contrôleur pressé. Laisser l'IA le poser
        reviendrait à lui faire prendre une décision d'activation, ce que le
        §12 interdit — sans qu'aucune ligne de code ne l'écrive.
        """
        profile = self._complete_profile(nom="IA severe")
        review = self._review(profile)

        with patch.object(type(self.Bridge), '_ai_available',
                          return_value=True), \
                patch.object(type(self.Bridge), '_ai_call_prompt',
                             return_value={'anomalies': [{
                                 'controle': 'coherence',
                                 'gravite': 'blocking',
                                 'libelle': "Parcours incoherent",
                                 'justification': "20 ans declares, 3 couverts",
                             }]}):
            review.action_run()

        ia = review.anomaly_ids.filtered(lambda a: a.origin == 'ia')
        self.assertTrue(ia, "L'anomalie de l'IA n'a pas été enregistrée.")
        self.assertEqual(
            ia[0].severity, 'warning',
            "Une anomalie d'IA est bloquante : le modèle décide.")
        self.assertEqual(review.blocking_count, 0)

    def test_the_ai_cannot_invent_a_control(self):
        """Le schéma est fermé : le modèle ne décide pas de la liste des sept.

        Et il ne peut instruire que les trois qui relèvent du jugement — un
        modèle qui prétendrait vérifier une identité rendrait un avis moins
        fiable que le `if` qui le fait déjà.
        """
        profile = self._complete_profile(nom="IA inventive")
        review = self._review(profile)

        with patch.object(type(self.Bridge), '_ai_available',
                          return_value=True), \
                patch.object(type(self.Bridge), '_ai_call_prompt',
                             return_value={'anomalies': [
                                 {'controle': 'solvabilite',
                                  'gravite': 'warning', 'libelle': "Inventé"},
                                 {'controle': 'identite',
                                  'gravite': 'warning',
                                  'libelle': "Hors de son domaine"},
                                 {'controle': 'coherence',
                                  'gravite': 'warning',
                                  'libelle': "Legitime"},
                             ]}):
            review.action_run()

        ia = review.anomaly_ids.filtered(lambda a: a.origin == 'ia')
        self.assertEqual(ia.mapped('name'), ["Legitime"])

    #
    # L'AVIS
    #

    def test_the_advice_is_posted_as_an_internal_note(self):
        """`mail.mt_note` et jamais `mt_comment`.

        Un `mt_comment` partirait par email aux followers, dont l'intervenant
        — qui recevrait la liste des anomalies relevées sur son dossier avant
        que quiconque l'ait instruit.
        """
        note = self.env.ref('mail.mt_note')
        profile = self._complete_profile(nom="Avis poste")
        review = self._review(profile)
        self._run_without_ai(review)

        messages = self.env['mail.message'].sudo().search([
            ('model', '=', 'opex.expert.qualification.review'),
            ('res_id', '=', review.id),
        ])
        avis = messages.filtered(
            lambda m: "contrôle qualité" in (m.body or '').lower())
        self.assertTrue(avis, "Aucun avis posté sur le dossier.")
        self.assertEqual(avis[0].subtype_id, note)
        self.assertNotIn(
            "&lt;", avis[0].body,
            "L'avis affiche ses balises : le body est passé en `str` là où "
            "`message_post()` attend un `Markup`.")

    def test_the_recommendation_never_decides(self):
        """Le vocabulaire est délibéré : « suggère de », jamais « activer »."""
        profile = self._complete_profile(nom="Recommandation")
        review = self._review(profile)
        self._run_without_ai(review)

        texte = (review.recommandation or '').lower()
        self.assertIn("décision reste au contrôleur", texte)
        for verbe in ("à activer", "activer le profil", "refuser le profil"):
            self.assertNotIn(
                verbe, texte,
                "La recommandation est écrite comme une décision.")

    def test_running_twice_replaces_the_advice(self):
        """Chaque passage remplace le précédent.

        Accumuler ferait grossir l'avis à chaque relance et rendrait
        impossible de savoir ce qui vaut aujourd'hui. Le chemin du second
        passage est banal : on relance après correction.
        """
        profile = self._complete_profile(nom="Deux passages")
        experience = self.env['opex.expert.experience'].sudo().create({
            'profile_id': profile.id, 'name': "Commence demain",
            'date_debut': date.today() + timedelta(days=30),
        })
        review = self._review(profile)
        self._run_without_ai(review)
        premier = review.anomaly_count
        self.assertTrue(premier)

        experience.sudo().date_debut = date(2020, 1, 1)
        self._run_without_ai(review)
        self.assertLess(
            review.anomaly_count, premier,
            "L'avis s'accumule au lieu d'être remplacé.")

    #
    # LE §11 — LA MACHINE À ÉTATS
    #

    def test_the_review_has_no_state_field(self):
        """Douzième définition du projet, même règle qu'aux onze autres."""
        for interdit in ('state', 'etat', 'statut', 'status', 'stage_id'):
            self.assertNotIn(
                interdit, self.Review._fields,
                "« %s » décrit l'avancement : c'est le workflow qui le fait."
                % interdit)
        self.assertTrue(self.Review._fields.get('workflow_stage_id'))

    def test_the_state_machine_has_the_ten_positions_of_section_11(self):
        definition = self.Definition.sudo()._get_for_code(QUALIFICATION_CODE)
        self.assertEqual(
            set(definition.stage_ids.mapped('code')),
            {'registered', 'profile_draft', 'submitted', 'quality_check',
             'to_complete', 'qualified', 'active', 'suspended', 'rejected',
             'archived'})

    def test_active_is_not_a_final_stage(self):
        """Un intervenant actif reste dans le processus.

        `do_transition()` pose `state = 'done'` en atteignant une étape
        `is_end` (règle 14), et `_check_transition_allowed()` refuse alors
        tout. Une qualification close en `active` ne pourrait plus être
        suspendue ni archivée — ce que la vie d'un vivier demande.
        """
        definition = self.Definition.sudo()._get_for_code(QUALIFICATION_CODE)
        finales = definition.stage_ids.filtered('is_end').mapped('code')
        self.assertEqual(set(finales), {'rejected', 'archived'})

    def test_the_module_two_profile_workflow_is_untouched(self):
        """La garde qui protège un module gelé.

        La définition du §11 n'étend pas `profile_request` : `test_profiles.py`
        du Module 2 y verrouille six étapes et six transitions, et les faire
        rougir depuis ici serait inacceptable.
        """
        module_deux = self.Definition.sudo()._get_for_code('profile_request')
        self.assertTrue(module_deux)
        self.assertEqual(len(module_deux.stage_ids), 6)
        self.assertEqual(len(module_deux.transition_ids), 6)

    #
    # LE CONTRÔLEUR N'EST PAS SUPPOSÉ HUMAIN
    #

    def test_nothing_assumes_the_controller_is_a_person(self):
        """« Seul le type d'acteur change. »

        Le remplacement du contrôleur humain par un agent autonome ne doit
        demander aucune modification du workflow métier. Deux conditions :
        les transitions passent par un **rôle**, et le module ne teste jamais
        l'utilisateur courant pour décider du contrôle.
        """
        definition = self.Definition.sudo()._get_for_code(QUALIFICATION_CODE)
        controle = self.env.ref(
            'opex_intervenants.role_qualification_control')
        portees = definition.transition_ids.filtered(
            lambda t: controle in t.allowed_role_ids)
        self.assertTrue(
            portees, "Aucune transition n'est tenue par le rôle de contrôle.")

        # Aucune transition n'est réservée à un groupe d'utilisateurs : c'est
        # le rôle qui décide, et un rôle se porte aussi bien par un agent.
        import os
        chemin = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'models', 'expert_qualification_review.py')
        with open(chemin, encoding='utf-8') as fichier:
            source = fichier.read()
        source = re.sub(r'("""|\'\'\')(?:.|\n)*?\1', '', source)
        source = re.sub(r'#[^\n]*', '', source)
        for suppose_humain in ('has_group', '_is_missions_staff',
                               'env.user.partner_id'):
            self.assertNotIn(
                suppose_humain, source,
                "Le contrôle suppose un contrôleur humain (« %s ») : le "
                "remplacer par un agent demanderait de modifier ce module."
                % suppose_humain)

    #
    # LA FILE DU §20
    #

    def test_the_work_queue_is_a_closed_dictionary(self):
        profile = self._complete_profile(nom="File")
        review = self._review(profile)
        file_attente = self.Review.work_queue()

        self.assertEqual(
            set(file_attente), {'a_controler', 'bloquants', 'a_verifier'})
        self.assertIn(
            review.id, [item['id'] for item in file_attente['a_controler']],
            "Un dossier jamais contrôlé n'est pas dans la file.")

        self._run_without_ai(review)
        file_attente = self.Review.work_queue()
        self.assertNotIn(
            review.id, [item['id'] for item in file_attente['a_controler']])
        for colonne in file_attente.values():
            for item in colonne:
                self.assertEqual(
                    set(item),
                    {'id', 'intervenant', 'etape', 'anomalies', 'bloquantes',
                     'controle_le'})
