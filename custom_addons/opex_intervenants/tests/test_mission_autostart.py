from datetime import timedelta

from odoo import fields
from odoo.tests.common import tagged

from .common import MissionCase


@tagged('post_install', '-at_install')
class TestMissionAutoStart(MissionCase):
    """Le démarrage à échéance — le cron ne peut rien qu'un humain ne pouvait.

    Les quatre tests ci-dessous cernent la même frontière sous quatre angles :
    le cron choisit **le moment**, jamais le droit ni la condition.
    """

    def _mission_in_contracting(self, validate_contract=True):
        """Une mission arrêtée à `contracting`, contrat validé ou non.

        Le helper vit ici et non dans `common.py` : il n'a qu'un usage, et un
        helper partagé se met à porter les besoins de tous ses appelants.

        ⚠ `_validate_the_contract()` franchit « Lancer la contractualisation »
        **et** déroule le cycle du §19. Avec `validate_contract=False` on
        s'arrête après le lancement : le contrat existe, il est en
        préparation, et la règle 5 du §39 est donc fausse — c'est exactement
        l'état de la mission que le cron ne doit pas démarrer.
        """
        mission = self._new_mission()
        self._open_the_call(mission)
        self._select_the_application(self._new_application(mission))
        self._do(mission, 'mission_close_applications', self.manager)
        self._do(mission, 'mission_award', self.decideur,
                 comment="Candidature retenue par le comité.")
        if validate_contract:
            self._validate_the_contract(mission)
        else:
            self._do(mission, 'mission_start_contracting', self.secretariat)
        mission.invalidate_recordset()
        return mission

    # ------------------------------------------------------------

    def test_the_cron_is_declared_and_daily(self):
        """La configuration est la référence, l'écran n'en est que la vue."""
        cron = self.env.ref('opex_intervenants.cron_mission_autostart')
        self.assertEqual(cron.state, 'code')
        self.assertIn('_cron_start_due_missions', cron.code)
        self.assertEqual(cron.interval_type, 'days')
        self.assertEqual(cron.interval_number, 1)
        self.assertEqual(cron.model_id.model, 'opex.mission.request')

    def test_a_mission_before_its_start_date_is_not_started(self):
        """Le cron regarde la date du **contrat**, pas le souhait de l'appel."""
        mission = self._mission_in_contracting()
        contrat = mission.sudo().contract_id
        contrat.write({'date_debut': fields.Date.context_today(mission)
                       + timedelta(days=30)})
        avant = mission.sudo().workflow_stage_id.code

        resultat = self.env['opex.mission.request']\
            .with_user(self.manager)._cron_start_due_missions()

        self.assertEqual(mission.sudo().workflow_stage_id.code, avant,
                         "Une mission dont la date n'est pas atteinte a "
                         "pourtant démarré.")
        self.assertGreaterEqual(resultat['pas_encore_a_echeance'], 1)

    def test_a_mission_whose_contract_is_not_validated_never_starts(self):
        """La règle 5 du §39 n'est pas réécrite : elle est **demandée**.

        C'est le test qui compte. Sans lui, le cron pourrait démarrer une
        mission dont le contrat vient d'être refusé — exactement ce que la
        règle 14 des règles transversales décrit, un cran plus loin.
        """
        mission = self._mission_in_contracting(validate_contract=False)
        contrat = mission.sudo().contract_id
        contrat.write({'date_debut': fields.Date.context_today(mission)
                       - timedelta(days=1)})

        self.env['opex.mission.request']\
            .with_user(self.manager)._cron_start_due_missions()

        self.assertEqual(
            mission.sudo().workflow_stage_id.code, 'contracting',
            "La mission a démarré alors que son contrat n'est pas validé : "
            "le cron a court-circuité la règle 5 du §39.")

    def test_a_due_mission_with_a_validated_contract_starts(self):
        mission = self._mission_in_contracting()
        contrat = mission.sudo().contract_id
        contrat.write({'date_debut': fields.Date.context_today(mission)})

        resultat = self.env['opex.mission.request']\
            .with_user(self.manager)._cron_start_due_missions()

        self.assertEqual(mission.sudo().workflow_stage_id.code, 'in_progress')
        self.assertGreaterEqual(resultat['demarrees'], 1)

    def test_a_second_pass_does_nothing(self):
        """Idempotent par le graphe, pas par un drapeau.

        La mission franchie quitte `contracting`, donc sort du domaine. Le
        second passage ne la voit plus — et c'est ce qu'on vérifie, plutôt
        qu'un champ « déjà traité » qu'il faudrait penser à remettre à zéro.
        """
        mission = self._mission_in_contracting()
        mission.sudo().contract_id.write(
            {'date_debut': fields.Date.context_today(mission)})
        Mission = self.env['opex.mission.request'].with_user(self.manager)

        Mission._cron_start_due_missions()
        etape = mission.sudo().workflow_stage_id.code
        historique = len(mission.sudo().workflow_instance_id.history_ids)

        Mission._cron_start_due_missions()

        self.assertEqual(mission.sudo().workflow_stage_id.code, etape)
        self.assertEqual(
            len(mission.sudo().workflow_instance_id.history_ids), historique,
            "Le second passage a produit une ligne d'historique : le cron "
            "n'est pas idempotent.")

    def test_the_cron_starts_under_the_identity_it_really_has(self):
        """LE TEST QUI MANQUAIT, ET SON ABSENCE A COÛTÉ LE DÉFAUT.

        Les autres tests appellent la méthode `with_user(self.manager)` —
        une identité que le cron n'a pas. Or un `ir.cron` sans `user_id`
        s'exécute en `__system__` (uid 1), qui ne tient aucun rôle du module :
        `available_transitions()` renvoyait une liste vide, et le cron
        n'aurait jamais rien démarré en production.

        Celui-ci part donc de l'identité **réelle**, sans `with_user`.
        """
        mission = self._mission_in_contracting()
        mission.sudo().contract_id.write(
            {'date_debut': fields.Date.context_today(mission)})

        systeme = self.env['res.users'].sudo().browse(1)
        self.assertFalse(
            mission.sudo().workflow_instance_id.available_transitions(
                user=systeme).filtered(lambda t: t.code == 'mission_start'),
            "Le super-utilisateur tient un rôle du module : ce test ne mesure "
            "plus le cas qu'il prétend mesurer.")

        resultat = self.env['opex.mission.request'].with_user(systeme)\
            ._cron_start_due_missions()

        self.assertEqual(
            mission.sudo().workflow_stage_id.code, 'in_progress',
            "Le cron n'a rien démarré sous son identité réelle : il tourne "
            "tous les jours pour rien.")
        self.assertGreaterEqual(resultat['demarrees'], 1)

    def test_the_journal_names_an_actor_and_says_it_was_automatic(self):
        """Le journal ne doit pas laisser croire que quelqu'un a cliqué."""
        mission = self._mission_in_contracting()
        mission.sudo().contract_id.write(
            {'date_debut': fields.Date.context_today(mission)})

        self.env['opex.mission.request'].with_user(
            self.env['res.users'].sudo().browse(1))._cron_start_due_missions()

        ligne = mission.sudo().workflow_instance_id.history_ids.filtered(
            lambda h: h.transition_id.code == 'mission_start')[:1]
        self.assertTrue(ligne, "Aucune ligne d'historique pour le démarrage.")
        self.assertIn("automatique", (ligne.comment or '').lower())
        self.assertTrue(
            ligne.user_id,
            "La ligne ne nomme personne : le journal ne dit pas qui porte "
            "cette mission.")

    def test_the_cron_never_forces_a_transition(self):
        """Le source, docstrings retirées : aucun forçage, aucune écriture directe.

        Le pendant de `test_the_triggers_never_advance_a_workflow` de
        l'Extension 7, retourné : ici `do_transition` est **attendu**, mais
        tout ce qui contournerait le moteur est interdit.
        """
        import inspect
        import re

        from ..models import mission_autostart

        forbidden = ('current_stage_id =', "write({'workflow_",
                     '_is_workflow_manager', 'sudo().su')
        examined = 0
        for klass in vars(mission_autostart).values():
            if not inspect.isclass(klass) \
                    or klass.__module__ != mission_autostart.__name__:
                continue
            for name, attribute in vars(klass).items():
                if not inspect.isfunction(attribute):
                    continue
                examined += 1
                source = inspect.getsource(attribute)
                source = re.sub(r'("""|\'\'\')(?:.|\n)*?\1', '', source)
                body = re.sub(r'#[^\n]*', '', source)
                for word in forbidden:
                    self.assertNotIn(
                        word, body,
                        "`%s.%s` contient « %s » : le cron contourne le "
                        "moteur au lieu de lui demander." % (
                            klass.__name__, name, word))
        self.assertGreaterEqual(
            examined, 3,
            "Seules %s méthodes examinées : la boucle ne trouve plus le code "
            "qu'elle garde." % examined)
