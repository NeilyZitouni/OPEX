"""IA-1 : le parsing d'un CV - §6, §17, §24.

Le service d'IA est simulé. Ce qui est vérifié ici, c'est ce que le module
**fait de** la réponse, pas ce que Gemini répond.
"""

import json
from unittest.mock import patch

from odoo.tests.common import tagged

from .common import MissionCase


def element(valeur, confidence=0.9, quote="extrait du CV"):
    """Un élément conforme au schéma du §6."""
    return {'valeur': valeur, 'confidence': confidence,
            'source_quote': quote}


#: Ce qu'un modèle rend quand tout se passe bien : les neuf destinations.
GOOD_PAYLOAD = {
    'titre': [element("Auditeur des systèmes d'information")],
    'resume': [element("Quinze ans d'audit SI en environnement industriel.")],
    'experience': [element("Responsable audit - ACME", 0.95)],
    'competence': [element("Audit des systèmes d'information", 0.92),
                   element("ISO 27001", 0.7)],
    'diplome': [element("Ingénieur en informatique", 0.88)],
    'certification': [element("Lead Auditor ISO 27001", 0.8)],
    'langue': [element("Français"), element("Anglais", 0.6)],
    'secteur': [element("Industrie", 0.55)],
    'annees': [element("15", 0.75)],
}


@tagged('post_install', '-at_install')
class TestCvParsing(MissionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Source = cls.env['opex.expert.cv.source']
        cls.Proposal = cls.env['opex.expert.cv.proposal']
        cls.Bridge = cls.env['opex.ai.bridge']
        cls.Skill = cls.env['opex.expert.skill']

    def _profile(self):
        partner = self.intervenant.partner_id
        Profile = self.env['opex.innovation.expert.profile'].sudo()
        profile = Profile.search([('partner_id', '=', partner.id)], limit=1)
        if not profile:
            profile = Profile.create({'partner_id': partner.id})
        partner.sudo().expert_profile_id = profile.id
        return profile

    def _deposit(self, **overrides):
        values = {
            'profile_id': self._profile().id,
            'document': b'ZmF1eC1jdg==',
            'filename': 'cv.pdf',
        }
        values.update(overrides)
        return self.Source.sudo().create(values)

    def _parse(self, source, payload):
        with patch.object(type(self.Bridge), '_ai_call_prompt',
                          return_value=payload) as called:
            source._parse()
        return called

    #
    # §6 - le dépôt est asynchrone
    #

    def test_the_deposit_queues_and_analyses_nothing(self):
        """Un parsing prend dix à trente secondes.

        Le dépôt doit rendre la main : c'est toute la raison de l'asynchrone.
        Le test vérifie les deux choses - l'état est « à analyser », et aucun
        appel n'est parti.
        """
        with patch.object(type(self.Bridge), '_ai_call_prompt') as called:
            source = self._deposit()

        called.assert_not_called()
        self.assertEqual(source.analyse, 'pending')
        self.assertFalse(source.date_analyse)
        self.assertFalse(source.proposal_ids)

    def test_the_version_counts_per_profile(self):
        """« Le troisième CV de Zitouni » a un sens ; « le 412e du portail »,
        non."""
        first = self._deposit()
        second = self._deposit()
        self.assertEqual(first.version, 1)
        self.assertEqual(second.version, 2)

    def test_the_cron_processes_the_queue(self):
        source = self._deposit()
        with patch.object(type(self.Bridge), '_ai_call_prompt',
                          return_value=dict(GOOD_PAYLOAD)):
            self.Source._cron_parse_pending()

        source.invalidate_recordset()
        self.assertEqual(source.analyse, 'done')
        self.assertTrue(source.date_analyse)

    def test_the_pdf_goes_out_as_a_document_not_as_text(self):
        """Gemini lit le PDF nativement.

        Extraire le texte nous-mêmes perdrait la mise en page, dont le modèle
        se sert : un titre se distingue d'une ligne de corps par sa position
        et sa taille, pas par ses mots.
        """
        source = self._deposit()
        called = self._parse(source, dict(GOOD_PAYLOAD))

        document = called.call_args.kwargs['document']
        self.assertEqual(document['mimetype'], 'application/pdf')
        self.assertEqual(document['data'], source.document)
        self.assertEqual(called.call_args.args[0], 'cv_parsing')

    #
    # §17 - la provenance vérifiable
    #

    def test_the_raw_json_is_kept(self):
        """« Le JSON brut renvoyé par le parsing. »

        C'est ce qui permet de comprendre une extraction ratée sans relancer
        l'appel, et de rejouer la validation si le schéma change.
        """
        source = self._deposit()
        self._parse(source, dict(GOOD_PAYLOAD))

        self.assertTrue(source.raw_json)
        restored = json.loads(source.raw_json)
        self.assertEqual(restored['titre'][0]['valeur'],
                         "Auditeur des systèmes d'information")

    def test_the_source_keeps_the_document_and_its_dates(self):
        """Les cinq informations du §17, sur un seul enregistrement."""
        source = self._deposit()
        self._parse(source, dict(GOOD_PAYLOAD))

        self.assertTrue(source.document)
        self.assertTrue(source.version)
        self.assertTrue(source.date_depot)
        self.assertTrue(source.raw_json)
        self.assertTrue(source.date_analyse)

    #
    # §6 - les neuf destinations, et le schéma
    #

    def test_the_nine_destinations_of_the_table_are_extracted(self):
        source = self._deposit()
        self._parse(source, dict(GOOD_PAYLOAD))

        destinations = set(source.proposal_ids.mapped('destination'))
        self.assertEqual(
            destinations,
            {'titre', 'resume', 'experience', 'competence', 'diplome',
             'certification', 'langue', 'secteur', 'annees'})

    def test_every_proposal_carries_a_confidence_and_a_quote(self):
        """Les trois informations que le §6 exige par élément."""
        source = self._deposit()
        self._parse(source, dict(GOOD_PAYLOAD))

        for proposal in source.proposal_ids:
            self.assertTrue(proposal.valeur)
            self.assertGreater(proposal.confidence, 0)
            self.assertTrue(
                proposal.source_quote,
                "« %s » n'a pas de passage cité : la traçabilité du §24 "
                "repose dessus." % proposal.valeur)

    def test_an_unexpected_field_is_ignored_not_written(self):
        """« Un champ inattendu est ignoré, pas écrit. »

        Sans cela, un modèle qui ajoute `salaire_souhaite` verrait sa
        trouvaille traverser jusqu'à un écran, et personne ne saurait d'où
        elle vient.
        """
        payload = dict(GOOD_PAYLOAD)
        payload['salaire_souhaite'] = [element("80000 EUR")]
        payload['competence'] = [
            {'valeur': "Audit", 'confidence': 0.9,
             'source_quote': "extrait", 'note_interne': "à revoir"}]

        source = self._deposit()
        self._parse(source, payload)

        self.assertNotIn(
            'salaire_souhaite',
            source.proposal_ids.mapped('destination'),
            "Une destination inconnue du schéma a été écrite.")
        self.assertNotIn('note_interne', self.Proposal._fields)

    def test_the_validation_happens_before_any_write(self):
        """Une réponse mal formée n'écrit rien, et ne lève pas."""
        source = self._deposit()
        for payload in ({}, {'competence': "pas une liste"},
                        {'competence': [None]}, {'titre': [{}]}):
            self._parse(source, payload)
            source.invalidate_recordset()
            self.assertEqual(source.analyse, 'done')

    def test_a_confidence_is_read_in_any_reasonable_form(self):
        """« 0.85 », « 85 » et « 85 % » disent la même chose."""
        as_confidence = self.Source._as_confidence
        self.assertEqual(as_confidence(0.85), 0.85)
        self.assertEqual(as_confidence(85), 0.85)
        self.assertEqual(as_confidence("85 %"), 0.85)
        self.assertEqual(as_confidence("élevée"), 0.0)
        self.assertEqual(as_confidence(None), 0.0)
        # Bornée des deux côtés : un modèle qui rend 150 ne rend pas une
        # confiance supérieure à la certitude.
        self.assertEqual(as_confidence(150), 1.0)
        self.assertEqual(as_confidence(-3), 0.0)

    #
    # §24 - LE CRITERE QUI GOUVERNE TOUT
    #

    def test_the_parsing_never_produces_a_validated_datum(self):
        """« Le parsing ne transforme jamais une donnée incertaine en donnée
        validée sans traçabilité. »

        C'est LE critère d'acceptation. Il est vérifié sous trois angles, et
        les trois sont nécessaires :

        1. toute proposition porte `source='ia'` et `confiance='propose'` ;
        2. aucune n'est confirmée ;
        3. rien n'a été écrit dans les modèles du profil - une proposition
           n'est pas une compétence.

        Le troisième est celui qui compte le plus. Les deux premiers
        décriraient encore un module qui écrirait aussi ailleurs.
        """
        profile = self._profile()
        before_skills = self.Skill.sudo().search_count(
            [('profile_id', '=', profile.id)])

        source = self._deposit()
        self._parse(source, dict(GOOD_PAYLOAD))

        proposals = source.proposal_ids
        self.assertTrue(proposals, "Aucune proposition à vérifier.")

        for proposal in proposals:
            self.assertEqual(proposal.source, 'ia')
            self.assertEqual(proposal.confiance, 'propose')
            self.assertFalse(
                proposal.is_confirmed,
                "« %s » est validée sans qu'un humain l'ait confirmée."
                % proposal.valeur)

        self.assertEqual(
            self.Skill.sudo().search_count([('profile_id', '=', profile.id)]),
            before_skills,
            "Le parsing a écrit dans `opex.expert.skill` : une donnée issue "
            "de l'IA n'existe qu'à l'état de proposition tant que l'expert "
            "n'a pas confirmé.")

    def test_confirming_is_a_human_gesture_and_it_is_traced(self):
        """La confirmation change ce que la donnée vaut, et laisse sa trace."""
        source = self._deposit()
        self._parse(source, dict(GOOD_PAYLOAD))
        proposal = source.proposal_ids[0]

        proposal.with_user(self.manager).action_confirm()
        proposal.invalidate_recordset()

        self.assertEqual(proposal.confiance, 'confirme')
        self.assertTrue(proposal.is_confirmed)
        self.assertEqual(proposal.confirmed_by, self.manager)
        self.assertTrue(proposal.confirmed_on)
        # La valeur et la citation ne bougent pas : ce qui change, c'est ce
        # que l'information vaut, pas ce qu'elle dit.
        self.assertTrue(proposal.source_quote)

    def test_a_proposal_is_never_a_qualified_skill(self):
        """Deux modèles, deux sens, et aucun pont automatique.

        Confirmer une proposition ne crée pas de ligne de compétence : cela
        supposerait un rapprochement taxonomique, et écrire un libellé libre
        dans le référentiel est exactement ce que le §8 interdit.
        """
        profile = self._profile()
        source = self._deposit()
        self._parse(source, dict(GOOD_PAYLOAD))

        before = self.Skill.sudo().search_count(
            [('profile_id', '=', profile.id)])
        for proposal in source.proposal_ids:
            proposal.with_user(self.manager).action_confirm()

        self.assertEqual(
            self.Skill.sudo().search_count([('profile_id', '=', profile.id)]),
            before,
            "Confirmer une proposition a créé une compétence qualifiée sans "
            "rapprochement taxonomique.")

    #
    # Les pannes ne cassent rien
    #

    def test_an_unreadable_pdf_breaks_nothing(self):
        """Le service rend None ; le CV part en échec, avec son motif.

        Rien ne lève, rien n'est écrit, et la file continue.
        """
        source = self._deposit()
        self._parse(source, None)
        source.invalidate_recordset()

        self.assertEqual(source.analyse, 'failed')
        self.assertTrue(source.error_message)
        self.assertFalse(source.proposal_ids)
        self.assertTrue(source.date_analyse)

    def test_a_failure_does_not_stop_the_queue(self):
        """Un document illisible ne doit pas empêcher les autres d'être lus.

        C'est la règle 10 du CLAUDE.md appliquée à une file : chaque CV est
        traité dans son propre savepoint.
        """
        broken = self._deposit(filename='illisible.pdf')
        good = self._deposit(filename='bon.pdf')

        answers = [None, dict(GOOD_PAYLOAD)]
        with patch.object(type(self.Bridge), '_ai_call_prompt',
                          side_effect=answers):
            self.Source._cron_parse_pending()

        broken.invalidate_recordset()
        good.invalidate_recordset()
        self.assertEqual(broken.analyse, 'failed')
        self.assertEqual(good.analyse, 'done')
        self.assertTrue(good.proposal_ids)

    def test_the_queue_gives_up_after_three_attempts(self):
        """Un PDF que le modèle ne sait pas lire ne le deviendra pas.

        Sans cette borne, la file bouclerait sur le même document à chaque
        passage du cron, et chaque tour serait facturé.
        """
        source = self._deposit()
        for _ in range(4):
            source.sudo().analyse = 'pending'
            with patch.object(type(self.Bridge), '_ai_call_prompt',
                              return_value=None):
                self.Source._cron_parse_pending()
            source.invalidate_recordset()

        self.assertEqual(source.attempts, 3)

    def test_the_module_works_without_the_ai_module_installed(self):
        """`opex_ai_core` n'est pas une dépendance déclarée.

        Le pont rend None quand le service n'est pas au registre, et le CV
        part en échec au lieu de lever. Le portail reste livrable sans
        assistance IA.
        """
        source = self._deposit()
        # Un nom de modèle absent du registre : c'est exactement ce que voit
        # le pont quand `opex_ai_core` n'est pas installé.
        with patch('odoo.addons.opex_intervenants.models.ai_bridge.AI_SERVICE',
                   'opex.ai.service.absent'):
            self.assertFalse(self.Bridge._ai_available())
            source._parse()

        source.invalidate_recordset()
        self.assertEqual(source.analyse, 'failed')
        self.assertFalse(source.proposal_ids)
