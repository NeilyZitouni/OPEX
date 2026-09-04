"""Dette D1 — le référentiel de certifications, et le critère qui écarte.

Deux manques qui étaient le même, vus des deux bouts : le critère éliminatoire
comparait du texte libre, et les certifications extraites d'un CV ne se
promouvaient pas faute de référentiel.

**Le test qui compte** est `test_a_close_but_different_certification_is_rejected` :
un expert déclarant « ISO 27001 » ne doit PAS satisfaire un appel exigeant
« ISO 27001 Lead Auditor ». C'était la première des trois défaillances
mesurées, et c'est celle qui fait entrer quelqu'un qui n'aurait pas dû.
"""

import re
import unicodedata
from datetime import date, timedelta
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import MissionCase


def normalise(label):
    """La normalisation du module, recopiée volontairement.

    Ce test doit rougir si `_normalise()` change de comportement sans qu'on
    l'ait voulu. Un test qui appelle la fonction qu'il vérifie ne vérifie que
    sa cohérence avec elle-même.
    """
    decomposed = unicodedata.normalize('NFKD', str(label or ''))
    stripped = decomposed.encode('ascii', 'ignore').decode('ascii')
    return ' '.join(
        ''.join(c if c.isalnum() else ' ' for c in stripped.lower()).split())


@tagged('post_install', '-at_install')
class TestCertificationD1(MissionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Certification = cls.env['opex.certification']
        cls.Synonyme = cls.env['opex.certification.synonyme']
        cls.Arbitrage = cls.env['opex.certification.arbitrage']
        cls.Resolution = cls.env['opex.certification.resolution']
        cls.ExpertCert = cls.env['opex.expert.certification']
        cls.Bridge = cls.env['opex.ai.bridge']

        cls.iso27001 = cls.env.ref(
            'opex_membership.certification_iso_27001')
        cls.iso9001 = cls.env.ref('opex_membership.certification_iso_9001')
        cls.la27001 = cls.env.ref('opex_intervenants.cert_la_27001')
        cls.cisa = cls.env.ref('opex_intervenants.cert_cisa')
        cls.cissp = cls.env.ref('opex_intervenants.cert_cissp')

    # ------------------------------------------------------------
    # Fabriques
    # ------------------------------------------------------------

    def _profile(self, partner=None):
        partner = partner or self.intervenant.partner_id
        Profile = self.env['opex.innovation.expert.profile'].sudo()
        profile = Profile.search([('partner_id', '=', partner.id)], limit=1)
        if not profile:
            profile = Profile.create({'partner_id': partner.id})
        partner.sudo().expert_profile_id = profile.id
        return profile

    def _hold(self, profile, certification, valide=True):
        """L'expert détient cette certification, rapprochée et confirmée."""
        return self.ExpertCert.sudo().create({
            'profile_id': profile.id,
            'certification_id': certification.id,
            'name': certification.name,
            'source': 'expert',
            'confiance': 'expert',
            'date_expiration': (
                date.today() + timedelta(days=365) if valide
                else date.today() - timedelta(days=30)),
        })

    def _requiring_mission(self, certifications):
        """Un appel d'audit qui exige ces certifications."""
        mission = self._new_mission(
            mission_type_id=self.env.ref(
                'opex_intervenants.mission_type_audit').id)
        mission.sudo().certification_ids = [(6, 0, certifications.ids)]
        return mission

    def _eliminatory(self, mission):
        return mission.sudo().matching_criteria().filtered(
            lambda c: c.is_eliminatoire and c.family == 'certification')

    def _admitted(self, mission, partner):
        """Ce candidat passe-t-il les critères obligatoires ?"""
        instance = mission.sudo().workflow_instance_id
        admis, motifs = mission.sudo()._matching_check_eliminatoires(
            instance, partner, self._eliminatory(mission))
        return admis, motifs

    #
    # LE TEST QUI COMPTE
    #

    def test_a_close_but_different_certification_is_rejected(self):
        """La première défaillance de D1, et la plus grave.

        « ISO 27001 » atteste la connaissance d'une norme. « ISO 27001 Lead
        Auditor » atteste la qualification à conduire un audit de
        certification. Ce sont deux qualifications différentes, et l'ancienne
        comparaison `contains` les confondait :
        `"iso 27001" in "iso 27001 lead auditor"` est vrai.

        Constaté sur le jeu de démonstration de l'E4 : Amina Cherif, sans le
        Lead Auditor, était proposée.

        L'assertion positive vient d'abord — sans elle, un critère qui
        écarterait tout le monde ferait passer ce test sans rien prouver.
        """
        mission = self._requiring_mission(self.la27001)

        # Le vrai Lead Auditor passe.
        qualifie = self.env['res.partner'].sudo().create(
            {'name': "Karim, Lead Auditor"})
        self._hold(self._profile(qualifie), self.la27001)
        qualifie.invalidate_recordset()
        admis, _motifs = self._admitted(mission, qualifie)
        self.assertTrue(
            admis,
            "Le candidat qui détient exactement la certification exigée est "
            "écarté : le critère écarte tout le monde et ne prouve rien.")

        # Celui qui n'a que la norme, non.
        proche = self.env['res.partner'].sudo().create(
            {'name': "Amina, ISO 27001 sans Lead Auditor"})
        self._hold(self._profile(proche), self.iso27001)
        proche.invalidate_recordset()
        admis, motifs = self._admitted(mission, proche)

        self.assertFalse(
            admis,
            "Un expert déclarant « ISO 27001 » satisfait un appel exigeant "
            "« ISO 27001 Lead Auditor ». C'est la dette D1 : le critère "
            "rapproche par hasard au lieu d'écarter.")
        self.assertTrue(motifs, "L'exclusion n'est pas expliquée.")

    def test_the_eliminatory_criterion_compares_references_not_text(self):
        """La garde sur la configuration, et elle était nécessaire.

        Le test précédent vérifie le **comportement**, et il est plus robuste
        qu'on ne le croirait : le référentiel écarte correctement même si l'on
        remet le mode `contains`, parce que les deux libellés canoniques —
        « ISO 27001 — Sécurité de l'information » et « ISO 27001 Lead
        Auditor » — ne s'incluent ni l'un ni l'autre.

        Mesuré par régression volontaire : remettre `contains` n'a fait rougir
        qu'un test sur les trois défaillances. C'est une bonne nouvelle et un
        angle mort — la protection vient du référentiel, pas du mode, et rien
        ne signalait que la configuration avait été ramenée à l'état d'avant.

        Ce test-ci ferme l'angle mort : il vérifie **ce que le critère
        compare**. Un retour au texte libre le fait rougir immédiatement,
        avant même qu'un candidat soit mal classé.
        """
        mission = self._requiring_mission(self.la27001)
        critere = self._eliminatory(mission)
        self.assertTrue(critere, "Le critère éliminatoire a disparu.")

        self.assertIn(
            'certification_ids', critere.source_expression,
            "Le critère interroge autre chose que les certifications "
            "canoniques exigées : c'est la dette D1 telle qu'elle était.")
        self.assertNotIn(
            'certifications_souhaitees', critere.source_expression,
            "Le critère éliminatoire compare de nouveau du texte libre.")
        self.assertEqual(
            critere.target_field, 'expert_certification_ref_ids',
            "Le critère compare les intitulés libres du candidat au lieu de "
            "ses références canoniques.")
        self.assertEqual(
            critere.match_mode, 'intersect',
            "Le mode `contains` teste l'inclusion de chaînes dans les deux "
            "sens - la première défaillance de D1.")
        self.assertTrue(
            critere.is_conjonctif,
            "Sans conjonction, exiger deux certifications revient à n'en "
            "exiger au plus qu'une - la troisième défaillance de D1.")

    #
    # LES DEUX AUTRES DÉFAILLANCES DE D1
    #

    def test_a_spelling_variant_no_longer_excludes_a_qualified_expert(self):
        """La deuxième défaillance : le trop restrictif.

        « ISO27001 » sans espace, ou « ISO 27001:2022 », ne croisait plus
        rien : aucune des deux chaînes ne contenait l'autre, et un candidat
        qualifié disparaissait du vivier pour une faute de frappe.

        Le rapprochement se fait désormais **avant** la comparaison : quelle
        que soit l'écriture, la ligne porte la même référence canonique.
        """
        mission = self._requiring_mission(self.iso27001)
        for ecriture in ("ISO27001", "ISO 27001:2022", "iso 27001"):
            certification = self.Synonyme.resolve_label(ecriture)
            self.assertEqual(
                certification, self.iso27001,
                "« %s » n'est pas rapprochée : un candidat qualifié "
                "disparaîtrait du vivier pour une variante d'écriture."
                % ecriture)

        partner = self.env['res.partner'].sudo().create(
            {'name': "Expert à l'orthographe libre"})
        ligne = self._hold(self._profile(partner), self.iso27001)
        ligne.sudo().name = "ISO27001"        # ce qu'il a écrit
        partner.invalidate_recordset()

        admis, _motifs = self._admitted(mission, partner)
        self.assertTrue(admis)

    def test_requiring_two_certifications_requires_both(self):
        """La troisième défaillance, la moins visible des trois.

        `_as_set()` sur une chaîne ne la découpe pas : exiger « ISO 27001,
        ISO 9001 » produisait **un seul jeton**, qu'un expert n'ayant que la
        première satisfaisait par inclusion. Exiger deux certifications
        revenait à n'en exiger au plus qu'une.

        Deux `Many2many` donnent deux éléments, et `is_conjonctif` exige les
        deux — le mode `intersect` du moteur ne teste qu'un recoupement, ce
        qui est juste pour un critère pondéré et faux pour un éliminatoire.
        """
        mission = self._requiring_mission(self.iso27001 | self.iso9001)

        partiel = self.env['res.partner'].sudo().create(
            {'name': "N'a qu'une des deux"})
        profile = self._profile(partiel)
        self._hold(profile, self.iso27001)
        partiel.invalidate_recordset()

        admis, motifs = self._admitted(mission, partiel)
        self.assertFalse(
            admis,
            "Un candidat n'ayant qu'une des deux certifications exigées est "
            "admis : exiger deux normes revient encore à n'en exiger qu'une.")
        self.assertIn(
            "ISO 9001", " ".join(motifs),
            "Le motif ne nomme pas la certification manquante.")

        # Avec les deux, il passe.
        self._hold(profile, self.iso9001)
        partiel.invalidate_recordset()
        admis, _motifs = self._admitted(mission, partiel)
        self.assertTrue(admis)

    #
    # LE CAS QUI A CAUSÉ LA DETTE : LA CONFIGURATION MUETTE
    #

    def test_a_misspelled_criterion_stops_the_matching_instead_of_the_exclusion(self):
        """« Il ne doit pas cesser d'écarter en silence. »

        `field('nom_mal_orthographie')` **ne lève pas** : le helper du moteur
        est tolérant par conception et rend `False`. Ce `False` traverse
        `_as_set()`, qui rend un ensemble vide, et l'élimination conclut « cet
        appel n'exprime aucune attente » — donc n'écarte personne.

        Une faute de frappe **supprimait le critère**, sans erreur, sans
        avertissement, et le vivier restait plein. Plus plein, même. C'est le
        motif exact du balayage typographique de la règle 21 : le symptôme ne
        ressemble pas à une panne.

        Le matching refuse désormais de tourner. Une liste qui contient des
        candidats qui auraient dû être écartés est pire qu'une absence de
        liste : personne ne la relit.
        """
        mission = self._requiring_mission(self.la27001)
        critere = self._eliminatory(mission)
        self.assertTrue(critere, "Aucun critère éliminatoire à éprouver.")

        # Le comportement du moteur, constaté et non supposé.
        instance = mission.sudo().workflow_instance_id
        self.assertFalse(
            instance._evaluate_expression("field('certification_idz')"),
            "Le helper `field()` lève désormais sur un champ inconnu : ce "
            "test surveille un piège qui n'existe plus, et son garde-fou "
            "peut être reconsidéré.")

        critere.sudo().source_expression = "field('certification_idz')"
        erreurs = mission.sudo()._matching_configuration_errors(critere)
        self.assertTrue(
            erreurs,
            "Une expression qui nomme un champ inexistant n'est pas "
            "signalée : le critère cesserait d'écarter en silence.")
        self.assertIn("certification_idz", " ".join(erreurs))

        with self.assertRaises(UserError):
            mission.sudo().run_smart_matching()

    def test_a_misspelled_target_field_excludes_instead_of_admitting(self):
        """Le pendant, côté candidat.

        Un `target_field` inexistant valait `False`, et `_compare()` répondait
        « le candidat ne renseigne pas ce champ ». Le comportement était donc
        déjà fermé — mais par accident, et sans le dire. Il est désormais
        explicite et motivé.
        """
        mission = self._requiring_mission(self.la27001)
        critere = self._eliminatory(mission)
        critere.sudo().target_field = 'expert_certification_ref_idz'

        partner = self.env['res.partner'].sudo().create({'name': "Qualifié"})
        self._hold(self._profile(partner), self.la27001)
        partner.invalidate_recordset()

        admis, motifs = self._admitted(mission, partner)
        self.assertFalse(admis)
        self.assertIn("n'existe pas", " ".join(motifs))
        self.assertTrue(
            mission.sudo()._matching_configuration_errors(critere),
            "Un champ candidat inexistant n'est pas signalé avant le "
            "lancement.")

    def test_an_empty_requirement_excludes_nobody(self):
        """Le garde-fou d'origine tient toujours.

        Un appel qui n'exige aucune certification ne doit écarter personne —
        le §6 dit « obligatoires ou préférentiels **selon la mission** ». Sans
        cela, `_compare()` répondrait « aucune attente exprimée », donc faux,
        donc éliminé, et la liste serait vide sans que rien ne l'explique.

        Ce cas ressemble au précédent et n'en est pas un : ici l'expression
        est valide et le dossier est vide. Les distinguer est tout l'objet du
        contrôle de configuration.
        """
        mission = self._requiring_mission(self.Certification.browse())
        self.assertFalse(mission.certification_ids)

        partner = self.env['res.partner'].sudo().create({'name': "Sans rien"})
        self._profile(partner)
        admis, _motifs = self._admitted(mission, partner)
        self.assertTrue(
            admis,
            "Un appel qui n'exige aucune certification écarte le vivier "
            "entier.")
        self.assertFalse(mission.sudo()._matching_configuration_errors(
            self._eliminatory(mission)))

    #
    # LE RÉFÉRENTIEL
    #

    def test_the_module_one_referential_is_extended_not_duplicated(self):
        """L'erreur que D1 documente, et qu'on ne refait pas.

        Un second référentiel de certifications ne croiserait le premier que
        par coïncidence de libellé — exactement le défaut qu'on répare.
        """
        for interdit in ('opex.expert.certification.catalog',
                         'opex.mission.certification',
                         'opex.certification.referentiel'):
            self.assertIsNone(
                self.env.get(interdit),
                "« %s » existe : un second référentiel de certifications."
                % interdit)

        # Le champ ajouté vit bien sur le modèle du Module 1.
        self.assertIn('porte', self.Certification._fields)
        self.assertEqual(
            self.iso27001._name, 'opex.certification',
            "La certification exigée ne vient pas du référentiel du Module 1.")

    def test_the_two_scopes_do_not_mix(self):
        """Un référentiel, deux vues.

        Le Module 1 propose les certifications d'organisation, le profil
        expert celles de personne. Une norme qui vaut des deux côtés est
        déclarée telle une fois — c'est ce que `porte` permet, et c'est ce
        qui évitait d'avoir à trancher entre deux modèles.
        """
        personnelles = self.Certification.search(
            [('porte', 'in', ['personne', 'les_deux'])])
        self.assertIn(self.la27001, personnelles)
        self.assertIn(
            self.iso27001, personnelles,
            "ISO 27001 devrait valoir des deux côtés : une entreprise s'y "
            "certifie, et un auditeur aussi.")

        # Une certification purement personnelle ne pollue pas l'annuaire.
        organisationnelles = self.Certification.search(
            [('porte', 'in', ['organisation', 'les_deux'])])
        self.assertNotIn(self.cisa, organisationnelles)

    def test_the_seeded_certifications_have_no_normalisation_collision(self):
        """Deux libellés qui se normalisent pareil rendent le rapprochement
        ambigu — et sur un éliminatoire, un candidat serait admis ou écarté
        selon l'ordre d'un index."""
        vus = {}
        for certification in self.Certification.search([]):
            vus.setdefault(normalise(certification.name), []).append(
                certification.name)
        for synonyme in self.Synonyme.search([('origine', '=', 'socle')]):
            vus.setdefault(normalise(synonyme.name), []).append(synonyme.name)

        collisions = {k: v for k, v in vus.items() if len(v) > 1}
        self.assertFalse(
            collisions, "Libellés ambigus dans le socle : %s" % collisions)

    def test_no_synonym_bridges_two_distinct_qualifications(self):
        """La garde qui protège le test principal.

        Un synonyme reliant « ISO 27001 » au Lead Auditor rendrait
        `test_a_close_but_different_certification_is_rejected` faux, et le
        ferait rougir — mais dans six mois, la correction de moindre effort
        serait d'ajuster le test. Celui-ci dit pourquoi c'est interdit.
        """
        self.assertEqual(
            self.Synonyme.resolve_label("ISO 27001"), self.iso27001)
        self.assertEqual(
            self.Synonyme.resolve_label("ISO 27001 Lead Auditor"),
            self.la27001)
        self.assertNotEqual(
            self.Synonyme.resolve_label("ISO 27001"),
            self.Synonyme.resolve_label("Lead Auditor ISO 27001"),
            "Un synonyme relie la norme et la qualification d'auditeur : ce "
            "sont deux certifications distinctes.")

    def test_an_ambiguous_referential_refuses_to_choose(self):
        """Sur un éliminatoire, choisir au hasard est le pire des résultats."""
        self.Certification.sudo().create(
            {'name': "Certification Ambigue Test", 'porte': 'personne'})
        self.Certification.sudo().create(
            {'name': "Certification  ambiguë  test", 'porte': 'personne'})

        self.assertFalse(
            self.Synonyme.resolve_label("certification ambigue test"),
            "Le référentiel contient deux entrées équivalentes et la "
            "résolution en a choisi une : l'éligibilité deviendrait un "
            "tirage au sort.")

    #
    # LA PROMOTION D'UNE CERTIFICATION
    #

    def _confirmed_certification_proposal(self, libelle, quote="extrait"):
        profile = self._profile()
        source = self.env['opex.expert.cv.source'].sudo().create({
            'profile_id': profile.id,
            'document': b'ZmF1eC1jdg==',
            'filename': 'cv.pdf',
        })
        payload = {'certification': [
            {'valeur': libelle, 'confidence': 0.9, 'source_quote': quote}]}
        with patch.object(type(self.Bridge), '_ai_call_prompt',
                          return_value=payload):
            source._parse()
        proposal = source.proposal_ids.filtered(
            lambda p: p.destination == 'certification')
        self.assertTrue(proposal, "Aucune proposition de certification.")
        proposal.with_user(self.manager).action_confirm()
        return proposal

    def test_a_certification_proposal_is_promoted_through_the_referential(self):
        """Le second manque de D1, refermé sur le motif de la promotion de
        compétence : resolve, puis les trois axes du §9."""
        citation = "Certifié ISO 27001 Lead Auditor depuis 2019"
        proposal = self._confirmed_certification_proposal("LA 27001", citation)

        with patch.object(type(self.Bridge), '_ai_call_prompt') as called:
            ligne = proposal.with_user(self.manager).action_promote()

        called.assert_not_called()
        self.assertEqual(ligne._name, 'opex.expert.certification')
        self.assertEqual(ligne.certification_id, self.la27001)
        self.assertEqual(ligne.source, 'cv')
        self.assertEqual(ligne.confiance, 'expert')
        self.assertEqual(ligne.preuve_citation, citation)
        self.assertEqual(ligne.preuve_cv_id, proposal.source_id)
        self.assertEqual(
            ligne.name, "LA 27001",
            "Le libellé lu n'est pas conservé : on ne pourrait plus contester "
            "un rapprochement.")
        self.assertEqual(proposal.promotion, 'promue')

    def test_an_unknown_certification_creates_nothing_and_goes_to_arbitration(self):
        profile = self._profile()
        avant_lignes = self.ExpertCert.sudo().search_count(
            [('profile_id', '=', profile.id)])
        avant_catalogue = self.Certification.sudo().search_count([])

        proposal = self._confirmed_certification_proposal(
            "Habilitation drone catégorie A3 délivrée en 2024")
        with patch.object(type(self.Bridge), '_ai_call_prompt',
                          return_value=None):
            resultat = proposal.with_user(self.manager).action_promote()

        self.assertFalse(resultat)
        self.assertEqual(
            self.ExpertCert.sudo().search_count(
                [('profile_id', '=', profile.id)]), avant_lignes)
        self.assertEqual(
            self.Certification.sudo().search_count([]), avant_catalogue,
            "La promotion a écrit dans le référentiel : seul "
            "`action_add_to_catalogue()` en a le droit.")
        self.assertEqual(proposal.promotion, 'arbitrage')
        self.assertTrue(proposal.certification_arbitrage_id)

    def test_a_promoted_certification_waits_for_its_validity(self):
        """Le point qui surprend, et qui est le bon comportement.

        Un CV dit rarement la date d'expiration. La ligne est donc créée
        confirmée mais **pas encore comptée** : `is_eligible` exige en plus
        qu'elle soit valable. Supposer une validité perpétuelle sur un critère
        éliminatoire reviendrait à admettre à tort.
        """
        proposal = self._confirmed_certification_proposal("CISA")
        ligne = proposal.with_user(self.manager).action_promote()

        self.assertTrue(ligne.is_confirmed)
        self.assertFalse(
            ligne.date_expiration,
            "Une date d'expiration a été inventée à partir du CV.")

        ligne.sudo().date_expiration = date.today() + timedelta(days=200)
        ligne.invalidate_recordset()
        self.assertTrue(
            ligne.is_eligible,
            "La certification datée ne compte toujours pas pour le matching.")

    def test_the_promoted_certification_reaches_the_matching(self):
        """La chaîne, jusqu'au champ que le critère éliminatoire lit."""
        profile = self._profile()
        partner = profile.partner_id
        self.assertNotIn(self.cisa, partner.sudo().expert_certification_ref_ids)

        proposal = self._confirmed_certification_proposal("CISA")
        ligne = proposal.with_user(self.manager).action_promote()
        ligne.sudo().date_expiration = date.today() + timedelta(days=365)
        partner.invalidate_recordset()

        self.assertIn(
            self.cisa, partner.sudo().expert_certification_ref_ids,
            "La certification promue n'atteint pas le champ que le critère "
            "éliminatoire compare : la chaîne n'est pas bouclée.")

    def test_an_expired_certification_leaves_the_pool(self):
        """Une certification périmée ne prouve plus rien.

        Et elle doit sortir **sans qu'on y touche** : la dépendance de
        recalcul porte sur `is_eligible`, pas sur un passage de cron.
        """
        partner = self.env['res.partner'].sudo().create({'name': "Périmé"})
        profile = self._profile(partner)
        ligne = self._hold(profile, self.cisa)
        partner.invalidate_recordset()
        self.assertIn(self.cisa, partner.sudo().expert_certification_ref_ids)

        ligne.sudo().date_expiration = date.today() - timedelta(days=1)
        partner.invalidate_recordset()
        self.assertNotIn(
            self.cisa, partner.sudo().expert_certification_ref_ids,
            "Une certification expirée compte encore dans le vivier.")

    def test_an_unmatched_line_does_not_count(self):
        """Les lignes saisies avant D1 ne comptent pour aucun critère.

        C'est une conséquence à annoncer, pas un défaut : une certification en
        texte libre n'est comparable à rien. Le filtre « Non rapprochées » est
        la file de travail qui la vide.
        """
        partner = self.env['res.partner'].sudo().create({'name': "Texte libre"})
        profile = self._profile(partner)
        ligne = self.ExpertCert.sudo().create({
            'profile_id': profile.id,
            'name': "ISO 27001 Lead Auditor",
            'date_expiration': date.today() + timedelta(days=365),
        })
        partner.invalidate_recordset()

        self.assertFalse(ligne.certification_id)
        self.assertFalse(ligne.is_eligible)
        self.assertFalse(partner.sudo().expert_certification_ref_ids)

    def test_the_eligibility_search_matches_its_computation(self):
        """Le corollaire de la règle 16 : les deux implémentations d'accord.

        `_compute_is_eligible` et `_search_is_eligible` sont deux écritures du
        même prédicat, et rien dans Odoo ne garantit qu'elles répondent la
        même chose. Une divergence ferait qu'un écran de travail montre des
        lignes que le matching ignore — ou l'inverse, ce qui est pire.
        """
        partner = self.env['res.partner'].sudo().create({'name': "Panachage"})
        profile = self._profile(partner)

        # Les quatre cas qui font varier le prédicat.
        self._hold(profile, self.cisa)                        # éligible
        self._hold(profile, self.la27001, valide=False)       # expirée
        non_rapprochee = self.ExpertCert.sudo().create({
            'profile_id': profile.id, 'name': "Texte libre"})
        non_confirmee = self.ExpertCert.sudo().create({
            'profile_id': profile.id,
            'certification_id': self.cissp.id,
            'name': self.cissp.name,
            'confiance': 'ia',
        })
        self.assertTrue(non_rapprochee and non_confirmee)

        lignes = self.ExpertCert.sudo().search(
            [('profile_id', '=', profile.id)])
        par_calcul = lignes.filtered('is_eligible')
        par_recherche = self.ExpertCert.sudo().search([
            ('profile_id', '=', profile.id), ('is_eligible', '=', True)])

        self.assertEqual(
            set(par_calcul.ids), set(par_recherche.ids),
            "Le calcul et la recherche de l'éligibilité ne s'accordent pas : "
            "un écran montrerait des lignes que le matching ignore.")

        # Et la négation, qui est le second chemin du domaine.
        par_recherche_faux = self.ExpertCert.sudo().search([
            ('profile_id', '=', profile.id), ('is_eligible', '=', False)])
        self.assertEqual(
            set((lignes - par_calcul).ids), set(par_recherche_faux.ids))

    def test_enriching_the_certification_referential_is_reserved(self):
        ligne = self.Arbitrage.sudo().create({'name': "Libellé à arbitrer"})
        with self.assertRaises(UserError):
            ligne.with_user(self.intervenant).action_add_to_catalogue()

    def test_the_referential_has_a_single_write_point(self):
        """Un test de source, sur le modèle de celui des compétences."""
        import os
        directory = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'models')
        autorise = 'certification_resolution.py'
        examines = 0
        for nom in sorted(os.listdir(directory)):
            if not nom.endswith('.py') or nom == autorise:
                continue
            with open(os.path.join(directory, nom), encoding='utf-8') as f:
                source = f.read()
            source = re.sub(r'("""|\'\'\')(?:.|\n)*?\1', '', source)
            source = re.sub(r'#[^\n]*', '', source)
            examines += 1
            self.assertNotIn(
                "['opex.certification'].sudo().create", source,
                "« %s » écrit dans le référentiel de certifications : ce flux "
                "passe par `action_add_to_catalogue`, et par lui seul." % nom)
        self.assertGreaterEqual(examines, 15)
