"""La promotion — le dernier maillon, et la preuve que la chaîne est bouclée.

    CV déposé -> proposition extraite -> confirmée par l'expert
              -> compétence qualifiée -> visible par le matching

Les quatre premières flèches sont éprouvées ailleurs — `test_cv_parsing.py`
pour l'extraction, `test_skill_catalog.py` pour le rapprochement. Ce fichier
porte la dernière, et surtout **le test qui relie les deux bouts** :
`test_the_promoted_skill_reaches_the_matching`.
"""

from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import MissionCase


def element(valeur, quote="extrait du CV", confidence=0.9):
    return {'valeur': valeur, 'confidence': confidence,
            'source_quote': quote}


@tagged('post_install', '-at_install')
class TestCvPromotion(MissionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Source = cls.env['opex.expert.cv.source']
        cls.Proposal = cls.env['opex.expert.cv.proposal']
        cls.Skill = cls.env['opex.expert.skill']
        cls.Arbitrage = cls.env['opex.competence.arbitrage']
        cls.Bridge = cls.env['opex.ai.bridge']
        # Deux compétences du socle semé, et leurs synonymes : le
        # rapprochement doit se faire à l'étape 1, sans appel.
        cls.rgpd = cls.env.ref(
            'opex_intervenants.skill_comp_protection_donnees')
        cls.iso27001 = cls.env.ref('opex_intervenants.skill_comp_iso27001')

    def _profile(self):
        partner = self.intervenant.partner_id
        Profile = self.env['opex.innovation.expert.profile'].sudo()
        profile = Profile.search([('partner_id', '=', partner.id)], limit=1)
        if not profile:
            profile = Profile.create({'partner_id': partner.id})
        partner.sudo().expert_profile_id = profile.id
        return profile

    def _analysed_cv(self, payload, profile=None):
        """Un CV déposé, analysé, avec ses propositions."""
        profile = profile or self._profile()
        source = self.Source.sudo().create({
            'profile_id': profile.id,
            'document': b'ZmF1eC1jdg==',
            'filename': 'cv.pdf',
        })
        with patch.object(type(self.Bridge), '_ai_call_prompt',
                          return_value=payload):
            source._parse()
        return source

    def _confirmed_proposal(self, libelle, quote="extrait du CV",
                            profile=None):
        source = self._analysed_cv(
            {'competence': [element(libelle, quote)]}, profile=profile)
        proposal = source.proposal_ids.filtered(
            lambda p: p.destination == 'competence')
        self.assertTrue(proposal, "Aucune proposition de compétence extraite.")
        proposal.with_user(self.manager).action_confirm()
        return proposal

    #
    # LE TEST QUI PROUVE QUE LA CHAÎNE EST BOUCLÉE
    #

    def test_the_promoted_skill_reaches_the_matching(self):
        """De bout en bout, et jusqu'au champ que le Smart Matching lit.

        C'est le seul test qui prouve quelque chose sur la chaîne entière.
        Les autres vérifient un maillon ; celui-ci vérifie qu'ils sont
        attachés.

        L'assertion négative d'abord est nécessaire : sans elle, un champ qui
        contiendrait déjà la compétence pour une autre raison ferait passer le
        test sans que la promotion y soit pour quelque chose.
        """
        profile = self._profile()
        partner = profile.partner_id

        self.assertNotIn(
            self.rgpd, partner.sudo().expert_skill_competence_ids,
            "La compétence est déjà dans le vivier avant toute promotion : "
            "ce test ne mesurerait rien.")

        proposal = self._confirmed_proposal(
            "RGPD", quote="Mise en conformité RGPD de trois filiales")
        skill = proposal.with_user(self.manager).action_promote()

        self.assertTrue(skill, "La promotion n'a produit aucune compétence.")
        self.assertEqual(skill.competence_id, self.rgpd)

        # LE point. Pas d'invalidation manuelle : le champ de matching dépend
        # de `is_confirmed`, et la dépendance fait partie de ce qu'on vérifie.
        self.assertIn(
            self.rgpd, partner.sudo().expert_skill_competence_ids,
            "La compétence promue n'atteint pas le champ que le Smart "
            "Matching interroge : la chaîne n'est pas bouclée.")

    #
    # LES TROIS AXES DU §9, POSÉS PAR LA PROMOTION
    #

    def test_the_promoted_skill_carries_the_three_axes(self):
        """`source='cv'`, `confiance='expert'`, et la citation en preuve.

        C'est ce triplet qui rend le §9 vérifiable sur une ligne issue d'un
        CV. `source` seul dirait la provenance sans permettre de remonter au
        passage exact.
        """
        citation = "Pilotage de la mise en conformité RGPD, 2021-2023"
        proposal = self._confirmed_proposal("RGPD", quote=citation)
        skill = proposal.with_user(self.manager).action_promote()

        self.assertEqual(skill.source, 'cv')
        self.assertEqual(skill.confiance, 'expert')
        self.assertEqual(skill.preuve_citation, citation)
        self.assertEqual(skill.preuve_cv_id, proposal.source_id)
        self.assertTrue(skill.is_confirmed)
        self.assertGreaterEqual(
            skill.preuve_count, 1,
            "La citation ne compte pas comme preuve : le §9 n'est alors pas "
            "vérifiable sur une compétence issue d'un CV.")

    def test_the_promotion_does_not_invent_a_level(self):
        """Le niveau reste celui du modèle, et l'expert l'ajuste.

        Un modèle qui lit « dix ans d'audit » propose volontiers « Expert ».
        Personne ne l'a validé, et le §9 sépare précisément le niveau métier
        de ce que vaut l'information. Déduire le niveau du CV les
        refusionnerait par la porte de derrière.
        """
        proposal = self._confirmed_proposal("RGPD")
        skill = proposal.with_user(self.manager).action_promote()
        self.assertEqual(
            skill.niveau, self.Skill._fields['niveau'].default(self.Skill),
            "La promotion a posé un niveau que personne n'a validé.")

    def test_the_proposal_keeps_the_link_to_what_it_produced(self):
        proposal = self._confirmed_proposal("RGPD")
        skill = proposal.with_user(self.manager).action_promote()

        self.assertEqual(proposal.skill_id, skill)
        self.assertEqual(proposal.promotion, 'promue')
        self.assertFalse(proposal.arbitrage_id)

    #
    # LA PROMOTION PASSE PAR LE RAPPROCHEMENT, JAMAIS À CÔTÉ
    #

    def test_a_synonym_is_promoted_without_calling_the_ai(self):
        """L'étape 1 du §8 fait le travail, et elle est gratuite.

        « RGPD » n'est pas un libellé du catalogue : c'est un synonyme de
        « Protection des données personnelles ». La promotion doit le
        rapprocher sans appel — sinon chaque compétence promue coûterait un
        appel au fournisseur.
        """
        proposal = self._confirmed_proposal("RGPD")
        with patch.object(type(self.Bridge), '_ai_call_prompt') as called:
            skill = proposal.with_user(self.manager).action_promote()

        called.assert_not_called()
        self.assertEqual(skill.competence_id, self.rgpd)

    def test_an_unmatched_proposal_creates_nothing_and_goes_to_arbitration(self):
        """La seconde règle de vigilance, et le cas le plus fréquent au début.

        Rien au profil, rien au catalogue, et la question survit à la
        fermeture de l'écran.
        """
        profile = self._profile()
        skills_avant = self.Skill.sudo().search_count(
            [('profile_id', '=', profile.id)])
        catalogue_avant = self.env['opex.innovation.competence'].sudo(
            ).search_count([])

        proposal = self._confirmed_proposal(
            "Pilotage de drones agricoles en zone aride")
        with patch.object(type(self.Bridge), '_ai_call_prompt',
                          return_value=None):
            resultat = proposal.with_user(self.manager).action_promote()

        self.assertFalse(resultat, "Une compétence a été créée sans rapprochement.")
        self.assertEqual(
            self.Skill.sudo().search_count([('profile_id', '=', profile.id)]),
            skills_avant,
            "Le profil a gagné une ligne pour un libellé non rapproché.")
        self.assertEqual(
            self.env['opex.innovation.competence'].sudo().search_count([]),
            catalogue_avant,
            "La promotion a écrit dans le catalogue : elle doit passer par "
            "`resolve_skills()`, qui ne l'écrit jamais.")

        self.assertEqual(proposal.promotion, 'arbitrage')
        self.assertTrue(proposal.arbitrage_id)
        self.assertEqual(proposal.arbitrage_id.decision, 'pending')

    def test_the_arbitration_line_carries_the_profile_and_the_document(self):
        """La question posée doit dire de qui et d'où elle vient."""
        profile = self._profile()
        proposal = self._confirmed_proposal("Pilotage de drones agricoles")
        with patch.object(type(self.Bridge), '_ai_call_prompt',
                          return_value=None):
            proposal.with_user(self.manager).action_promote()

        ligne = proposal.arbitrage_id
        self.assertEqual(ligne.profile_id, profile)
        self.assertTrue(
            ligne.source_document,
            "La ligne d'arbitrage ne dit pas de quel document elle vient.")

    #
    # LES DEUX REFUS
    #

    def test_an_unconfirmed_proposal_cannot_be_promoted(self):
        """Le §24 ne se contourne pas par la promotion.

        Une donnée incertaine ne devient pas validée sans traçabilité, et
        promouvoir sans confirmer serait exactement cela : la ligne entrerait
        au vivier sans que personne se soit prononcé.
        """
        source = self._analysed_cv({'competence': [element("RGPD")]})
        proposal = source.proposal_ids.filtered(
            lambda p: p.destination == 'competence')
        self.assertFalse(proposal.is_confirmed)

        with self.assertRaises(UserError):
            proposal.with_user(self.manager).action_promote()

    def test_only_competences_are_promotable(self):
        """Les huit autres destinations n'ont pas de modèle qui les attende.

        Promouvoir un diplôme ou une certification demanderait un référentiel
        par destination — c'est la dette D1 pour les certifications, et ce
        n'est pas ici. Le refus est explicite plutôt que silencieux.
        """
        source = self._analysed_cv({
            'competence': [element("RGPD")],
            'langue': [element("Français")],
        })
        langue = source.proposal_ids.filtered(
            lambda p: p.destination == 'langue')
        langue.with_user(self.manager).action_confirm()

        with self.assertRaises(UserError):
            langue.with_user(self.manager).action_promote()

    #
    # IDEMPOTENCE — et le chemin réel du second passage
    #

    def test_promoting_twice_produces_one_skill(self):
        """Deux clics, une liste promue en masse, un script de reprise.

        Le chemin du second passage est banal, contrairement à celui de
        l'Extension 10 où l'étape finale du graphe l'interdisait. La garde
        est donc atteignable, et ce test l'atteint — en appelant deux fois.

        Sans elle, `unique(profile_id, competence_id)` ferait sauter la
        transaction entière plutôt que de ne rien faire (règle 10).
        """
        profile = self._profile()
        proposal = self._confirmed_proposal("RGPD")

        premier = proposal.with_user(self.manager).action_promote()
        second = proposal.with_user(self.manager).action_promote()

        self.assertEqual(premier, second)
        self.assertEqual(
            self.Skill.sudo().search_count([
                ('profile_id', '=', profile.id),
                ('competence_id', '=', self.rgpd.id),
            ]), 1)

    def test_promoting_onto_an_existing_skill_adds_the_proof(self):
        """La compétence est déjà déclarée : on ajoute la preuve.

        C'est le cas d'un expert qui avait saisi sa compétence à la main, puis
        dépose un CV qui la mentionne. La citation enrichit ce qui existe.
        """
        profile = self._profile()
        existante = self.Skill.sudo().create({
            'profile_id': profile.id,
            'competence_id': self.rgpd.id,
            'niveau': 'expert',
            'source': 'expert',
            'confiance': 'expert',
        })
        self.assertFalse(existante.preuve_citation)

        citation = "Référent RGPD du groupe depuis 2020"
        proposal = self._confirmed_proposal("RGPD", quote=citation)
        skill = proposal.with_user(self.manager).action_promote()

        self.assertEqual(skill, existante)
        self.assertEqual(skill.preuve_citation, citation)
        self.assertEqual(skill.niveau, 'expert')

    def test_a_promotion_never_downgrades_a_verified_skill(self):
        """La garde qui protège le travail de vérification.

        Une ligne vérifiée par OPEX que la promotion ramènerait à « confirmé
        par l'expert » perdrait ce travail **sans un mot**, et le §9 se
        dégraderait par le chemin censé l'alimenter.

        C'est le défaut le plus discret de cette extension : il ne casse rien,
        il abaisse une qualité.
        """
        profile = self._profile()
        verifiee = self.Skill.sudo().create({
            'profile_id': profile.id,
            'competence_id': self.rgpd.id,
            'niveau': 'expert',
            'source': 'mission',
            'confiance': 'opex',
        })

        proposal = self._confirmed_proposal("RGPD")
        proposal.with_user(self.manager).action_promote()
        verifiee.invalidate_recordset()

        self.assertEqual(
            verifiee.confiance, 'opex',
            "La promotion a rétrogradé une compétence vérifiée par OPEX.")
        self.assertEqual(
            verifiee.source, 'mission',
            "La promotion a réécrit la source d'une ligne existante.")

    #
    # LE POINT D'ÉCRITURE RESTE UNIQUE
    #

    def test_the_promotion_writes_no_competence_in_the_catalogue(self):
        """Sous trois angles, dont un qui vaut pour tous les libellés.

        Le troisième est celui qui compte : même quand le rapprochement
        réussit, le catalogue ne bouge pas. C'est ce qui distingue « promouvoir
        vers une compétence connue » de « créer la compétence au passage ».
        """
        Competence = self.env['opex.innovation.competence'].sudo()
        avant = Competence.search_count([])

        for libelle in ("RGPD", "ISO27001", "Libellé totalement inconnu ici"):
            proposal = self._confirmed_proposal(libelle)
            with patch.object(type(self.Bridge), '_ai_call_prompt',
                              return_value=None):
                proposal.with_user(self.manager).action_promote()

        self.assertEqual(
            Competence.search_count([]), avant,
            "La promotion a enrichi le catalogue. Seul "
            "`action_add_to_catalogue()`, réservé au gestionnaire et "
            "journalisé, en a le droit.")
