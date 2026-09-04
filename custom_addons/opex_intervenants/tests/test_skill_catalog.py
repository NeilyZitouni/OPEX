"""IA-2 : la taxonomie du §8 et les sept attributs du tableau.

Le rapprochement en deux temps est éprouvé dans `test_competence_taxonomy.py`.
Ce fichier-ci porte ce que l'extension ajoute : la hiérarchie, le socle semé,
et les deux attributs de `expert.skill` qui manquaient.
"""

import re
import unicodedata
from datetime import date, timedelta
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import MissionCase

NON_WORD = re.compile(r"[^a-z0-9]+")


def normalise(label):
    """La normalisation du module, recopiée volontairement.

    Recopiée et non importée : ce test doit rougir si `_normalise()` change
    de comportement sans qu'on l'ait voulu. Un test qui appelle la fonction
    qu'il vérifie ne vérifie que sa cohérence avec elle-même.
    """
    s = unicodedata.normalize('NFKD', (label or '').strip().lower())
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return NON_WORD.sub(' ', s).strip()


@tagged('post_install', '-at_install')
class TestSkillCatalog(MissionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Domain = cls.env['opex.skill.domain']
        cls.Family = cls.env['opex.skill.family']
        cls.Competence = cls.env['opex.innovation.competence']
        cls.Synonyme = cls.env['opex.competence.synonyme']
        cls.Arbitrage = cls.env['opex.competence.arbitrage']
        cls.Resolution = cls.env['opex.competence.resolution']
        cls.Skill = cls.env['opex.expert.skill']
        cls.Bridge = cls.env['opex.ai.bridge']

    def _profile(self):
        partner = self.intervenant.partner_id
        Profile = self.env['opex.innovation.expert.profile'].sudo()
        profile = Profile.search([('partner_id', '=', partner.id)], limit=1)
        if not profile:
            profile = Profile.create({'partner_id': partner.id})
        partner.sudo().expert_profile_id = profile.id
        return profile

    #
    # §8 — LA HIÉRARCHIE
    #

    def test_the_taxonomy_has_its_three_levels(self):
        """Domaine, famille, compétence — et la compétence est celle du
        Module 2.

        C'est le point d'architecture de l'extension. Un modèle de compétences
        propre au Module 3 aurait été plus simple à écrire et aurait rendu le
        Smart Matching faux : il lit
        `res.partner.expert_skill_competence_ids`, qui pointe sur le
        référentiel du Module 2.
        """
        famille = self.env.ref('opex_intervenants.skill_family_si_securite')
        self.assertEqual(famille._name, 'opex.skill.family')
        self.assertEqual(famille.domain_id._name, 'opex.skill.domain')
        self.assertEqual(
            famille.competence_ids._name, 'opex.innovation.competence',
            "Les compétences d'une famille ne sont pas celles du Module 2 : "
            "un second référentiel rendrait le matching faux en silence.")

    def test_no_parallel_competence_model_was_created(self):
        """La garde d'architecture.

        `skill.catalog` comme modèle de compétences à part aurait été la
        lecture littérale du périmètre. C'est celle que la dette D1 interdit,
        et que l'arbitrage de l'auteur a tranchée : « le référentiel doit
        rester unique ».
        """
        for interdit in ('opex.skill.catalog', 'opex.skill.competence',
                         'opex.competence'):
            self.assertIsNone(
                self.env.get(interdit),
                "« %s » existe : un second catalogue de compétences ne "
                "croiserait le premier que par coïncidence de libellé."
                % interdit)

    def test_a_competence_without_a_family_is_a_queue_not_an_error(self):
        """`family_id` n'est pas requis, et c'est délibéré.

        Le référentiel contient des lignes créées avant cette extension. Les
        rendre invalides d'un coup aurait bloqué l'écran de compétences du
        Module 2 sur des données existantes.
        """
        orpheline = self.Competence.sudo().create(
            {'name': "Compétence sans rangement pour le test"})
        self.assertFalse(orpheline.family_id)
        self.assertFalse(orpheline.skill_domain_id)
        a_classer = self.Competence.sudo().search_count(
            [('family_id', '=', False)])
        self.assertGreaterEqual(a_classer, 1)

    #
    # LE SOCLE SEMÉ
    #

    def test_the_seeded_catalogue_covers_the_cluster(self):
        """Un catalogue vide enverrait tout en arbitrage dès le premier CV.

        Les bornes sont larges à dessein : le test garde l'existence d'un
        socle, pas un inventaire exact qu'un ajout ferait rougir pour rien.
        """
        self.assertGreaterEqual(self.Domain.search_count([]), 5)
        self.assertGreaterEqual(self.Family.search_count([]), 12)
        self.assertGreaterEqual(
            self.Competence.search_count([('family_id', '!=', False)]), 40)
        self.assertGreaterEqual(
            self.Synonyme.search_count([('origine', '=', 'socle')]), 40)

    def test_every_seeded_family_belongs_to_a_domain(self):
        orphelines = self.Family.search([('domain_id', '=', False)])
        self.assertFalse(
            orphelines.mapped('name'),
            "Une famille sans domaine casse la hiérarchie du §8.")

    def test_the_seeded_catalogue_has_no_normalisation_collision(self):
        """Le défaut mesuré à l'IA-2, transformé en garde.

        Deux libellés qui se normalisent pareil rendent le rapprochement
        ambigu : `resolve_label()` refuse alors de choisir et envoie en
        arbitrage un libellé que le catalogue contient pourtant. Le socle ne
        doit pas en introduire.
        """
        vus = {}
        for competence in self.Competence.search([('family_id', '!=', False)]):
            vus.setdefault(normalise(competence.name), []).append(
                competence.name)
        for synonyme in self.Synonyme.search([('origine', '=', 'socle')]):
            vus.setdefault(normalise(synonyme.name), []).append(synonyme.name)

        collisions = {k: v for k, v in vus.items() if len(v) > 1}
        self.assertFalse(
            collisions,
            "Le socle contient des libellés qui se normalisent pareil : %s"
            % collisions)

    def test_a_seeded_synonym_resolves_without_calling_the_ai(self):
        """L'étape 1 sur le socle livré — c'est ce qui rend la file tenable.

        « RGPD » est ce qu'un CV écrit ; « Protection des données
        personnelles » est ce que le catalogue porte. Sans le synonyme, le
        libellé partirait en arbitrage alors que la réponse est connue.
        """
        attendue = self.env.ref(
            'opex_intervenants.skill_comp_protection_donnees')

        with patch.object(type(self.Bridge), '_ai_call_prompt') as called:
            resolved = self.Resolution.resolve_skills(
                [{'libelle': "RGPD", 'niveau': 'expert'}])

        called.assert_not_called()
        self.assertEqual(resolved[0]['competence_id'], attendue.id)
        self.assertEqual(resolved[0]['matched_on'], 'synonyme')
        self.assertFalse(resolved[0]['arbitrage_id'])

    def test_an_acronym_without_a_space_still_resolves(self):
        """« ISO27001 » et « ISO 27001 » sont deux clés distinctes.

        La normalisation ne colle pas les espaces — sinon « audit si » et
        « auditsi » correspondraient, donc n'importe quelle suite de mots avec
        n'importe quelle autre. Ce sont donc **deux synonymes** du socle, et
        c'est voulu : un synonyme manquant envoie en arbitrage, une
        correspondance approximative se trompe en silence.
        """
        attendue = self.env.ref('opex_intervenants.skill_comp_iso27001')
        for ecriture in ("ISO 27001", "ISO27001", "iso 27001"):
            with patch.object(type(self.Bridge), '_ai_call_prompt') as called:
                resolved = self.Resolution.resolve_skills(
                    [{'libelle': ecriture}])
            called.assert_not_called()
            self.assertEqual(
                resolved[0]['competence_id'], attendue.id,
                "« %s » n'est pas rapproché." % ecriture)

    def test_an_unknown_label_goes_to_arbitration(self):
        """Une compétence non rapprochée n'est pas jetée.

        C'est comme cela que la taxonomie s'enrichit : le libellé attend un
        gestionnaire au lieu de disparaître.
        """
        libelle = "Pilotage de drones agricoles en zone aride"
        with patch.object(type(self.Bridge), '_ai_call_prompt',
                          return_value=None):
            resolved = self.Resolution.resolve_skills([{'libelle': libelle}])

        self.assertFalse(resolved[0]['competence_id'])
        self.assertTrue(
            resolved[0]['arbitrage_id'],
            "Le libellé inconnu a été perdu au lieu de partir en arbitrage.")
        ligne = self.Arbitrage.sudo().browse(resolved[0]['arbitrage_id'])
        self.assertEqual(ligne.decision, 'pending')

    #
    # L'IA PROPOSE, ELLE N'ÉCRIT PAS
    #

    def test_the_ai_never_writes_in_the_catalogue(self):
        """La garde qui empêche la taxonomie de diverger.

        Une IA qui enrichit le catalogue le fait diverger en trois mois, et le
        matching devient faux sans que rien ne le signale. La proposition la
        plus assurée reste une proposition.
        """
        avant = self.Competence.sudo().search_count([])
        suggestion = self.env.ref('opex_intervenants.skill_comp_audit_si')

        with patch.object(type(self.Bridge), '_ai_call_prompt',
                          # `confiance` et non `confidence` : c'est la clé
                          # que `_suggest()` lit. Écrite en anglais, elle vaut
                          # zéro, et ce test passait alors sans jamais
                          # exercer sa garde - mesuré par régression
                          # volontaire.
                          return_value={'code': suggestion.code,
                                        'confiance': 0.99,
                                        'motif': "Très proche."}):
            resolved = self.Resolution.resolve_skills(
                [{'libelle': "Revue technique des SI bancaires"}])

        self.assertEqual(
            self.Competence.sudo().search_count([]), avant,
            "Le service IA a créé une compétence au catalogue.")
        # Elle est proposée, et elle attend quand même un humain.
        self.assertTrue(resolved[0]['arbitrage_id'])
        ligne = self.Arbitrage.sudo().browse(resolved[0]['arbitrage_id'])
        self.assertEqual(ligne.decision, 'pending')
        self.assertEqual(ligne.suggestion_id, suggestion)
        self.assertGreaterEqual(
            ligne.suggestion_confiance, 90,
            "La confiance de l'IA n'a pas été lue : le test ne mesure alors "
            "que le chemin sans suggestion.")

    def test_enriching_the_catalogue_is_reserved_to_the_manager(self):
        """Décision humaine, et humaine habilitée."""
        ligne = self.Arbitrage.sudo().create({'name': "Libellé à arbitrer"})
        # `UserError` et non `AccessError` : le contrôle est celui du
        # modèle, `_is_missions_staff()`, la même fonction que les routes et
        # les `t-if` des tuiles. Un seul contrôle d'accès, règle 2.
        with self.assertRaises(UserError):
            ligne.with_user(self.intervenant).action_add_to_catalogue()

    def test_the_manager_files_the_new_competence_in_a_family(self):
        """Une compétence ajoutée sans famille part dans « À classer », et
        cette file-là, personne ne la vide."""
        famille = self.env.ref('opex_intervenants.skill_family_si_securite')
        ligne = self.Arbitrage.sudo().create({
            'name': "Sécurité des systèmes industriels",
            'family_id': famille.id,
        })
        competence = ligne.with_user(self.manager).action_add_to_catalogue()

        self.assertEqual(competence.family_id, famille)
        self.assertEqual(competence.skill_domain_id, famille.domain_id)
        # Le `Char` du Module 2 suit, sans quoi son écran afficherait une
        # compétence sans domaine et quelqu'un le remplirait à la main.
        self.assertEqual(competence.domaine, famille.domain_id.name)

    #
    # §8 — LES SEPT ATTRIBUTS
    #

    def test_a_qualified_skill_carries_the_seven_attributes(self):
        champs = self.Skill._fields
        attendus = {
            'competence_id': "compétence canonique",
            'niveau': "niveau",
            'annees': "années",
            'derniere_pratique': "dernière pratique",
            'source': "source",
            'preuve_count': "preuve",
            'confiance': "confiance",
        }
        for nom, libelle in attendus.items():
            self.assertIn(
                nom, champs,
                "L'attribut « %s » du tableau du §8 n'a pas de champ." % libelle)

    def test_the_evidence_is_what_makes_section_9_operative(self):
        """« Un niveau 4 auto-déclaré et un niveau 4 confirmé par trois
        expériences et une certification ne valent pas la même chose. »

        Sans pièces rattachées, cette phrase reste une intention. Avec elles,
        elle se compte — et deux lignes de même niveau se distinguent.
        """
        profile = self._profile()
        competence = self.env.ref('opex_intervenants.skill_comp_audit_si')
        autre = self.env.ref('opex_intervenants.skill_comp_iso27001')

        experience = self.env['opex.expert.experience'].sudo().create({
            'profile_id': profile.id, 'name': "Audit SI d'une banque"})
        certification = self.env['opex.expert.certification'].sudo().create({
            'profile_id': profile.id, 'name': "Lead Auditor ISO 27001"})

        prouve = self.Skill.sudo().create({
            'profile_id': profile.id,
            'competence_id': competence.id,
            'niveau': 'expert',
            'preuve_experience_ids': [(6, 0, experience.ids)],
            'preuve_certification_ids': [(6, 0, certification.ids)],
        })
        declare = self.Skill.sudo().create({
            'profile_id': profile.id,
            'competence_id': autre.id,
            'niveau': 'expert',
        })

        self.assertEqual(prouve.niveau, declare.niveau)
        self.assertEqual(prouve.preuve_count, 2)
        self.assertEqual(
            declare.preuve_count, 0,
            "Zéro pièce n'est pas une faute : c'est ce qui distingue les "
            "deux lignes, et le §9 en dépend.")

    def test_the_freshness_reads_the_last_practice(self):
        """Un niveau Expert pratiqué il y a huit ans n'est pas un niveau
        Expert aujourd'hui."""
        profile = self._profile()
        competence = self.env.ref('opex_intervenants.skill_comp_audit_si')
        skill = self.Skill.sudo().create({
            'profile_id': profile.id,
            'competence_id': competence.id,
            'niveau': 'expert',
        })
        self.assertEqual(skill.fraicheur, 'inconnue')

        aujourdhui = date.today()
        for jours, attendu in ((30, 'recente'), (3 * 365, 'ancienne'),
                               (8 * 365, 'dormante')):
            skill.derniere_pratique = aujourdhui - timedelta(days=jours)
            skill.invalidate_recordset(['fraicheur'])
            self.assertEqual(
                skill.fraicheur, attendu,
                "Une pratique vieille de %s jours devrait être « %s »."
                % (jours, attendu))

    def test_the_freshness_is_not_stored(self):
        """Elle dépend de la date du jour.

        Stockée, elle se figerait au dernier recalcul : une compétence
        deviendrait dormante le jour où quelqu'un ouvre sa fiche, pas le jour
        où elle le devient.
        """
        champ = self.Skill._fields['fraicheur']
        self.assertTrue(champ.compute)
        self.assertFalse(
            champ.store,
            "`fraicheur` est stockée : elle mentira jusqu'au prochain calcul.")

    #
    # §9 — LES DEUX AXES RESTENT DEUX
    #

    def test_level_and_confidence_stay_independent(self):
        """Le point subtil du §9, et le seul qui se vérifie par l'absurde.

        On fait varier l'un et on vérifie que l'autre ne bouge pas — dans les
        deux sens. Un champ unique passerait le premier sens et pas le second.
        """
        profile = self._profile()
        competence = self.env.ref('opex_intervenants.skill_comp_audit_si')
        skill = self.Skill.sudo().create({
            'profile_id': profile.id,
            'competence_id': competence.id,
            'niveau': 'debutant',
            'source': 'cv',
            'confiance': 'ia',
        })

        skill.niveau = 'expert'
        self.assertEqual(
            skill.confiance, 'ia',
            "Monter le niveau a changé la confiance : les deux axes sont "
            "fusionnés.")
        self.assertFalse(skill.is_confirmed)

        skill.confiance = 'opex'
        self.assertEqual(
            skill.niveau, 'expert',
            "Confirmer la ligne a changé le niveau métier.")
        self.assertEqual(skill.source, 'cv')
        self.assertTrue(skill.is_confirmed)

    def test_an_expert_level_proposed_by_the_ai_does_not_reach_the_matching(self):
        """Les deux axes se rencontrent là où ça compte.

        Niveau 4 et confiance « proposé » : le matching ne doit pas le voir.
        C'est le filtre `is_confirmed` posé à l'IA-1, et c'est ce qui donne
        au §9 sa conséquence pratique.
        """
        profile = self._profile()
        partner = profile.partner_id
        competence = self.env.ref('opex_intervenants.skill_comp_audit_si')
        skill = self.Skill.sudo().create({
            'profile_id': profile.id,
            'competence_id': competence.id,
            'niveau': 'expert',
            'source': 'cv',
            'confiance': 'ia',
        })

        self.assertNotIn(
            competence, partner.sudo().expert_skill_competence_ids,
            "Un niveau Expert jamais confirmé fait matcher l'intervenant.")
        skill.confiance = 'expert'
        self.assertIn(competence, partner.sudo().expert_skill_competence_ids)
