"""Le module tourne sans `sale` ni `project`.

`opex_intervenants` ne les déclare plus au manifeste : l'instance de
déploiement ne les a pas. Ces tests vérifient que leur absence **éteint deux
fonctionnalités** et n'en casse aucune autre.

POURQUOI ILS SIMULENT L'ABSENCE PLUTÔT QUE DE L'ATTENDRE

Sur le poste de développement, `sale` et `project` sont installés — ils sont
amenés par `opex_membership` et `opex_innovation`. Un test qui se contenterait
de constater l'état de la base ne vérifierait donc rien ici, et rougirait
ailleurs. Il faut simuler.

La simulation porte sur `_backend_available()` et `_backend_record()`, c'est-
à-dire sur **le seul point par lequel le module accède à ces modèles**. C'est
ce qui rend la simulation fidèle : s'il existait un second chemin, ces tests
resteraient verts et le module casserait à l'installation. D'où le test de
source qui suit, qui interdit précisément ce second chemin.
"""

import re
from pathlib import Path
from unittest.mock import patch

from odoo.tests.common import tagged

from odoo.addons.opex_intervenants.models.optional_backends import (
    PROJECT, PROJECT_TASK, SALE_ORDER)

from .common import MissionCase

#: Les fichiers qui ont le droit de nommer ces modèles : le pont lui-même,
#: et les deux méthodes qui portent le code de la fonctionnalité et que le
#: garde-fou d'installation protège en amont.
ALLOWED = {
    'optional_backends.py',
    'mission_invoicing.py',
    'mission_operational.py',
    'service_acceptance.py',
    'mission_assignment.py',
}


def strip_prose(source):
    """Retire docstrings et commentaires — règle 15 du CLAUDE.md.

    Un test qui inspecte du source examine du **code**, pas de la prose. Sans
    cela, il rougirait sur les commentaires « REBRANCHEMENT » qui expliquent
    justement ce qu'il vérifie — et la correction de moindre effort serait de
    supprimer l'explication.
    """
    source = re.sub(r'("""|\'\'\')(?:.|\n)*?\1', '', source)
    return re.sub(r'#[^\n]*', '', source)


@tagged('post_install', '-at_install')
class TestOptionalBackends(MissionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Backend = cls.env['opex.optional.backend']

    # ------------------------------------------------------------
    # Fabriques
    # ------------------------------------------------------------
    #
    # Recopiées des deux classes qui les portent plutôt qu'importées : les
    # remonter dans `common.py` aurait touché deux fichiers d'extensions
    # livrées pour le confort d'un troisième. Elles s'arrêtent d'ailleurs plus
    # tôt — aucune ne va jusqu'à la clôture, puisque c'est précisément la
    # clôture qu'on éteint.

    def _awarded_mission(self, **overrides):
        mission = self._new_mission(**overrides)
        self._open_the_call(mission)
        self._select_the_application(self._new_application(mission))
        self._do(mission, 'mission_close_applications', self.manager)
        self._do(mission, 'mission_award', self.decideur,
                 comment="Candidature retenue par le comité.")
        return mission

    def _delivered_mission(self, **overrides):
        mission = self._awarded_mission(**overrides)
        self._validate_the_contract(mission)
        self._do(mission, 'mission_start', self.manager)
        self._do(mission, 'mission_deliver', self.manager)
        return mission

    def _accepted_mission(self, **overrides):
        mission = self._delivered_mission(**overrides)
        self._run_service_acceptance_cycle(mission)
        self._do(mission, 'mission_accept_service', self.manager)
        return mission

    def _assert_renders_as_html(self, body):
        """La note doit s'afficher, pas montrer ses balises.

        `message_post()` **échappe** un body `str` : les balises ressortent
        en `&lt;p&gt;` et le lecteur voit du code. Il faut un `Markup`.
        Mesuré sur cette base, et corrigé sur les quatre notes du module qui
        portaient du balisage.

        Ce test garde la correction. Sans lui, un `Markup` retiré par
        distraction ne se verrait qu'à l'écran, et seulement si quelqu'un
        ouvre le bon dossier.
        """
        self.assertNotIn(
            "&lt;", body,
            "La note affiche ses balises au lieu de les rendre : le body est "
            "passé en `str` là où `message_post()` attend un `Markup`.")
        self.assertIn("<strong>", body)

    def _without(self, *models):
        """Le registre vu comme si ces modèles n'existaient pas."""
        absent = set(models)
        real_available = type(self.Backend)._backend_available
        real_record = type(self.Backend)._backend_record

        def available(self_, model_name):
            if model_name in absent:
                return False
            return real_available(self_, model_name)

        def record(self_, model_name, record_id):
            if model_name in absent:
                return None
            return real_record(self_, model_name, record_id)

        return (
            patch.object(type(self.Backend), '_backend_available', available),
            patch.object(type(self.Backend), '_backend_record', record),
        )

    #
    # Le manifeste
    #

    def test_the_manifest_declares_neither_sale_nor_project(self):
        """La garde qui empêche la dépendance de revenir par distraction.

        Elle reviendrait sans bruit : `depends` est une liste, et y ajouter un
        nom pour faire marcher un écran est le geste le plus naturel du monde.
        Le module redeviendrait alors non installable sur l'instance cible, et
        on ne s'en apercevrait qu'au déploiement suivant.
        """
        module = self.env['ir.module.module'].sudo().search(
            [('name', '=', 'opex_intervenants')], limit=1)
        declared = {
            dependency.name for dependency in module.dependencies_id}

        for forbidden in ('sale', 'project', 'opex_ai_core'):
            self.assertNotIn(
                forbidden, declared,
                "« %s » est redevenu une dépendance déclarée. Le module ne "
                "s'installera plus sur une instance qui ne l'a pas ; il doit "
                "passer par `opex.optional.backend`." % forbidden)

    def test_no_model_reaches_these_models_outside_the_bridge(self):
        """Un seul chemin d'accès, sinon la garde ne garde rien.

        Sans cette discipline, on découvrirait les endroits non protégés un
        par un, en production — et les tests de dégradation ci-dessous
        resteraient verts pendant ce temps, puisqu'ils ne simulent l'absence
        qu'au niveau du pont.
        """
        directory = Path(__file__).resolve().parent.parent / 'models'
        examined = 0

        for path in sorted(directory.glob('*.py')):
            if path.name in ALLOWED:
                continue
            examined += 1
            code = strip_prose(path.read_text(encoding='utf-8'))
            for model in (SALE_ORDER, PROJECT, PROJECT_TASK):
                self.assertNotIn(
                    "'%s'" % model, code,
                    "%s nomme « %s » hors du pont. Tout accès à un modèle "
                    "optionnel passe par `opex.optional.backend`."
                    % (path.name, model))

        # Une boucle qui ne trouve plus rien à examiner passe au vert.
        self.assertGreaterEqual(examined, 15)

    #
    # Sans `sale` — la facturation du §29
    #

    def test_a_mission_closes_without_sale_and_says_so(self):
        """La clôture aboutit ; la facturation ne se fait pas ; le dossier
        le dit.

        C'est l'arbitrage central de tout ce travail. Une mission qu'on ne
        pourrait plus clôturer parce que la comptabilité manque serait
        bloquée pour une raison qui ne la regarde pas.
        """
        mission = self._accepted_mission()

        available, record = self._without(SALE_ORDER)
        with available, record:
            before = len(mission.sudo().message_ids)
            result = mission.sudo()._trigger_invoicing()

        self.assertFalse(
            result,
            "Le déclencheur a rendu une commande alors que `sale` est absent.")

        messages = mission.sudo().message_ids[:len(mission.message_ids) - before]
        body = " ".join(messages.mapped('body'))
        self.assertIn(
            "Ventes", body,
            "La note ne nomme pas le module manquant : le gestionnaire ne "
            "saura pas quoi demander.")
        self.assertIn(
            "clôturée", body,
            "La note ne dit pas que la mission est clôturée — c'est pourtant "
            "ce qui distingue une fonctionnalité éteinte d'une panne.")
        self._assert_renders_as_html(body)

    def test_the_acceptance_records_no_order_without_sale(self):
        mission = self._accepted_mission()
        acceptance = mission.sudo().acceptance_ids

        available, record = self._without(SALE_ORDER)
        with available, record:
            mission.sudo()._trigger_invoicing()

        self.assertFalse(acceptance.sale_order_ref)
        self.assertFalse(acceptance.sale_order_name)

    def test_the_label_separates_unavailable_from_not_invoiced(self):
        """« Non facturée » et « indisponible » ne disent pas la même chose.

        La première décrit une mission qu'on n'a pas encore facturée, la
        seconde un portail qui ne sait pas facturer. Les confondre ferait
        chercher une commande manquante là où c'est le module qui l'est, et
        ce sont deux enquêtes différentes.
        """
        Mission = self.env['opex.mission.request']
        self.assertEqual(
            Mission._invoicing_label(False, None, None, False),
            "Facturation indisponible (module Ventes absent)")
        self.assertEqual(
            Mission._invoicing_label(True, None, None, False),
            "Non facturée")

    def test_the_invoicing_facts_stay_readable_without_sale(self):
        """Les huit champs du Schéma 12 se lisent toujours.

        Ils ne lèvent pas et ne mentent pas : aucune facture, aucun montant.
        C'est ce qui permet aux tableaux de bord du §42 et à la barre du §40
        de continuer à tourner sans savoir que la facturation est éteinte.
        """
        mission = self._delivered_mission()

        available, record = self._without(SALE_ORDER)
        with available, record:
            mission.invalidate_recordset()
            self.assertFalse(mission.sudo().facture_generee)
            self.assertFalse(mission.sudo().facture_payee)
            self.assertEqual(mission.sudo().montant_facture, 0.0)
            self.assertEqual(mission.sudo().montant_restant_du, 0.0)
            self.assertFalse(mission.sudo().facturation_disponible)

    #
    # Sans `project` — le projet d'exécution du §13
    #

    def test_a_mission_starts_without_project_and_says_so(self):
        mission = self._awarded_mission()
        self._validate_the_contract(mission)

        available, record = self._without(PROJECT, PROJECT_TASK)
        with available, record:
            before = len(mission.sudo().message_ids)
            self._do(mission, 'mission_start', self.manager)

        # La mission a bien démarré : c'est le point.
        self.assertEqual(self._stage(mission), 'in_progress')
        self.assertFalse(mission.sudo().assignment_id.project_ref)

        messages = mission.sudo().message_ids[:len(mission.message_ids) - before]
        body = " ".join(messages.mapped('body'))
        self.assertIn("Projet", body)
        self.assertIn(
            "Exécution", body,
            "La note ne dit pas où se fait le suivi à la place.")
        self._assert_renders_as_html(body)

    def test_the_execution_tracking_does_not_depend_on_project(self):
        """Ce qui compte du §21 ne passe pas par `project.task`.

        Les livrables, les points d'avancement et les incidents vivent dans
        nos propres modèles. C'est ce qui rend la perte supportable, et c'est
        la seule raison pour laquelle elle est supportable.
        """
        mission = self._awarded_mission()
        self._validate_the_contract(mission)

        available, record = self._without(PROJECT, PROJECT_TASK)
        with available, record:
            self._do(mission, 'mission_start', self.manager)
            deliverable = self.env['opex.mission.deliverable'].sudo().create({
                'mission_id': mission.id,
                'name': "Rapport d'audit",
                'is_required': True,
            })

        self.assertTrue(deliverable.workflow_instance_id)
        self.assertEqual(mission.sudo().assignment_id.task_count, 0)

    def test_the_progress_bar_survives_both_absences(self):
        """La barre du §40 est le point de rencontre des deux modules.

        Son jalon Facturation lit `facture_payee`, et la mission entière est
        décrite par ses étapes. Si quelque chose devait casser en silence,
        c'est là.
        """
        mission = self._delivered_mission()

        available, record = self._without(SALE_ORDER, PROJECT, PROJECT_TASK)
        with available, record:
            mission.invalidate_recordset()
            bar = mission.sudo().mission_progress_bar()

        self.assertEqual(len(bar), 8)
        self.assertTrue(all(step.get('etat') for step in bar))
