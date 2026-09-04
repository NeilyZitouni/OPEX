from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, new_test_user

MISSION_CODE = 'mission_request'
APPLICATION_CODE = 'mission_application'


class MissionCase(TransactionCase):
    """Socle commun aux deux suites : les cinq acteurs et deux fabriques.

    Les cinq rôles du module y sont représentés par de vrais comptes, avec de
    vrais groupes. C'est la seule façon de vérifier les `allowed_role_ids` : un
    test qui déroule tout en administrateur prouve que le graphe est connexe et
    rien de plus.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Mission = cls.env['opex.mission.request']
        cls.Application = cls.env['opex.mission.application']
        cls.Definition = cls.env['opex.workflow.definition']
        cls.Stage = cls.env['opex.workflow.stage']
        cls.Transition = cls.env['opex.workflow.transition']

        cls.mission_definition = cls.Definition._get_for_code(MISSION_CODE)
        cls.application_definition = cls.Definition._get_for_code(APPLICATION_CODE)

        # Les acteurs
        #
        # Client et intervenant sont des comptes **portail** : ils ne portent
        # leurs rôles que par une ligne `instance.actor`, posée à la création
        # depuis `client_id` / `partner_id`. Les trois autres tiennent les leurs
        # d'un groupe.
        cls.client_user = new_test_user(
            cls.env, login='mis_client', groups='base.group_portal')
        cls.other_client = new_test_user(
            cls.env, login='mis_client_2', groups='base.group_portal')
        cls.intervenant = new_test_user(
            cls.env, login='mis_expert', groups='base.group_portal')
        cls.other_intervenant = new_test_user(
            cls.env, login='mis_expert_2', groups='base.group_portal')
        cls.secretariat = new_test_user(
            cls.env, login='mis_secr',
            groups='base.group_user,opex_membership.group_secretariat')
        cls.manager = new_test_user(
            cls.env, login='mis_manager',
            groups='base.group_user,opex_intervenants.group_mission_manager')
        cls.decideur = new_test_user(
            cls.env, login='mis_decideur',
            groups='base.group_user,opex_intervenants.group_mission_committee')

        cls.mission_type = cls.env.ref('opex_intervenants.mission_type_audit')
        cls.mission_type_multi = cls.env.ref(
            'opex_intervenants.mission_type_formation')
        cls.domaine = cls.env.ref('opex_intervenants.mission_domain_cybersecurite')
        cls.competence = cls.env['opex.innovation.competence'].create({
            'name': "Sécurité des systèmes d'information",
            'code': 'test_ssi',
        })

    # ------------------------------------------------------------
    # Fabriques
    # ------------------------------------------------------------

    def _mission_values(self, **overrides):
        """Un dossier complet, prêt à franchir « Soumettre ma demande ».

        Les dates sont relatives à aujourd'hui : la condition de publication
        exige une date limite **encore ouverte**, et un test qui figerait une
        date se mettrait à échouer tout seul le jour où elle serait passée.
        """
        today = fields.Date.context_today(self.Mission)
        values = {
            'title': "Audit cybersécurité",
            'mission_type_id': self.mission_type.id,
            'client_id': self.client_user.partner_id.id,
            'description': "Le client souhaite un audit de son SI.",
            'objectifs': "Identifier les vulnérabilités et les hiérarchiser.",
            'domaine_id': self.domaine.id,
            'skill_ids': [(6, 0, self.competence.ids)],
            'date_limite_candidature': today + timedelta(days=30),
            'date_debut_souhaitee': today + timedelta(days=45),
            'date_fin_souhaitee': today + timedelta(days=60),
            'duree_estimee_jours': 15,
            'sourcing_mode': 'hybride',
        }
        values.update(overrides)
        return values

    def _new_mission(self, user=None, **overrides):
        """Crée un appel. Sans `user`, la création est faite en interne."""
        model = self.Mission
        if user is not None:
            model = model.with_user(user)
        return model.create(self._mission_values(**overrides))

    def _new_application(self, mission, partner=None, user=None, **overrides):
        """Crée une candidature sur cet appel."""
        values = {
            'mission_id': mission.id,
            'partner_id': (partner or self.intervenant.partner_id).id,
        }
        values.update(overrides)
        model = self.Application
        if user is not None:
            model = model.with_user(user)
        return model.create(values)

    def _fill_lean_form(self, application, user=None):
        """Remplit la candidature Lean — les seules données propres à la mission."""
        values = {
            'disponibilite': 'oui',
            'delai_propose_jours': 10,
            'tarif_propose': 25000.0,
            'type_tarif': 'tjm',
            'motivation': "Quinze ans d'audit SI en environnement industriel.",
            'methodologie': "Revue documentaire, entretiens, tests techniques.",
            'consentement': True,
        }
        record = application.with_user(user) if user is not None else application
        record.write(values)
        return application

    # ------------------------------------------------------------
    # Franchir une transition
    # ------------------------------------------------------------

    def _transition(self, definition, code):
        """La transition de **cette** définition portant ce code.

        Bornée à la définition, jamais cherchée par son seul code. Un test du
        moteur n'est jamais seul en base : `opex_innovation` publie sept
        définitions, et un `search([('code', '=', ...)])` non borné finirait par
        en ramener deux le jour où un autre module choisira le même mot.
        """
        transition = definition.sudo().transition_ids.filtered(
            lambda t: t.code == code)
        self.assertEqual(
            len(transition), 1,
            "Transition « %s » introuvable ou ambiguë dans « %s »."
            % (code, definition.code))
        return transition

    def _do(self, record, code, user, comment=False):
        """Fait franchir une transition à `record` sous l'identité de `user`.

        `.with_user(user).sudo()`, dans cet ordre, et c'est le motif de
        production — celui de `opex_innovation/controllers/staff_portal.py`.

        `sudo()` lève les `ir.rule` de **lecture** sur l'instance : un
        responsable tient son rôle d'un groupe et n'est acteur d'aucun dossier,
        donc `rule_instance_internal` lui masquerait l'instance qu'il a le droit
        de faire avancer. Le contrôle du **droit d'agir**, lui, n'est pas levé :
        `sudo()` ne change pas `env.user`, et `_check_transition_allowed()`
        juge toujours les rôles de l'utilisateur réel. Un client qui tente une
        transition de responsable se voit toujours refuser.
        """
        transition = self._transition(record.workflow_definition_id, code)
        record.with_user(user).sudo().workflow_do_transition(
            transition, comment=comment)
        record.invalidate_recordset()
        return record

    def _stage(self, record):
        """Le code de l'étape courante, lu sans droit particulier."""
        return record.sudo().workflow_stage_id.code

    def _visited(self, record):
        """Les étapes traversées, **dans l'ordre et avec les répétitions**.

        Une compréhension, jamais `mapped('to_stage_id.code')` : `mapped()`
        sur un Many2one déduplique, et une boucle qui repasse deux fois par la
        même étape y devient invisible. C'est le piège du §7 du CLAUDE.md, et
        c'est exactement ce que les tests de boucle doivent mesurer.
        """
        instance = record.sudo().workflow_instance_id
        return [
            line.to_stage_id.code
            for line in instance.history_ids.sorted('id')
        ]

    # ------------------------------------------------------------
    # Parcours complets, réutilisés par les deux suites
    # ------------------------------------------------------------

    #: Du brouillon à l'ouverture des candidatures.
    def _open_the_call(self, mission):
        self._do(mission, 'mission_submit', self.client_user)
        self._do(mission, 'mission_start_sourcing', self.manager)
        self._do(mission, 'mission_open_applications', self.manager)
        return mission

    #: D'une candidature créée à une candidature déposée.
    def _apply(self, application, user=None):
        user = user or self.intervenant
        self._do(application, 'application_view', user)
        self._do(application, 'application_express_interest', user)
        self._fill_lean_form(application)
        self._do(application, 'application_apply', user)
        return application

    #: D'une candidature créée à une candidature retenue.
    def _select_the_application(self, application, user=None):
        self._apply(application, user=user)
        self._do(application, 'application_screen', self.manager)
        self._do(application, 'application_shortlist', self.manager)
        self._do(application, 'application_select', self.decideur,
                 comment="Meilleur rapport expérience / tarif.")
        return application

    # ------------------------------------------------------------
    # Le sous-workflow de contractualisation — Extension 7
    # ------------------------------------------------------------
    #
    # Ces trois helpers vivent ici et non dans `test_contracting.py` parce que
    # le parcours nominal de la mission en dépend désormais : depuis que la
    # règle 5 du §39 est rattachée à « Démarrer la mission », aucune mission ne
    # va jusqu'au bout sans un contrat validé.

    def _contract_instance(self, mission):
        """L'instance du sous-workflow du contrat, sur la mission elle-même."""
        return mission.sudo()._contract_instance()

    def _do_contract(self, mission, code, user, comment=False):
        """Franchir une transition du **sous-workflow**, pas de la mission.

        `_do()` passe par `record.workflow_definition_id`, c'est-à-dire par
        l'instance principale. La contractualisation est une seconde instance
        sur le même enregistrement : confondre les deux ferait échouer le test
        sur une transition introuvable plutôt que sur ce qu'il mesure.
        """
        instance = self._contract_instance(mission)
        self.assertTrue(
            instance,
            "La contractualisation n'est pas lancée sur « %s »."
            % mission.display_name)
        transition = self._transition(instance.definition_id, code)
        instance.with_user(user).sudo().do_transition(
            transition, comment=comment)
        mission.invalidate_recordset()
        return instance

    def _validate_the_contract(self, mission):
        """« Mission attribuée » → « Contrat validé », en passant par le §19.

        C'est « Lancer la contractualisation » qui démarre le sous-workflow,
        par une action configurée sur la transition. Quand celle-ci a déjà été
        franchie, appeler `_run_contract_cycle()` directement.
        """
        self._do(mission, 'mission_start_contracting', self.secretariat)
        return self._run_contract_cycle(mission)

    def _run_contract_cycle(self, mission):
        """Le cycle du §19 seul, sur un sous-workflow déjà lancé."""
        self._do_contract(mission, 'contract_submit_review', self.secretariat)
        self._do_contract(mission, 'contract_send_to_sign', self.manager)

        contract = mission.sudo().contract_id
        contract.action_sign_client()
        contract.action_sign_intervenant()
        mission.invalidate_recordset()

        self._do_contract(mission, 'contract_sign', self.manager)
        self._do_contract(mission, 'contract_validate', self.decideur)
        return mission

    # ------------------------------------------------------------
    # Le constat de service fait — Extension 9
    # ------------------------------------------------------------
    #
    # Ce helper vit ici pour la même raison que les trois précédents : le
    # parcours nominal de la mission en dépend désormais. « Valider le service
    # fait » porte depuis l'Extension 9 la règle 6 du §39 **et** la condition
    # que le constat du §28 ait été prononcé — aucune mission n'atteint plus
    # `accepted` sans que le cluster puis le client se soient exprimés.

    def _run_service_acceptance_cycle(self, mission, user=None):
        """Le cycle du §28 sur le constat ouvert par « Soumettre les livrables ».

        Le constat n'est pas créé par le test : il l'est par une action
        `set_field` configurée sur `mtr_deliver`. L'assertion ci-dessous n'est
        donc pas de la précaution — c'est elle qui vérifie que le déclencheur a
        bien tourné, et elle rougirait si l'action était détachée.

        `_do()` et non `_do_contract()` : le constat est un enregistrement à
        lui, avec sa propre instance. La contractualisation, elle, est un
        **sous-workflow sur la mission**, et c'est ce qui obligeait à un helper
        séparé là-bas.
        """
        acceptance = mission.sudo().acceptance_ids[:1]
        self.assertTrue(
            acceptance,
            "Aucun constat de service fait sur « %s » : le déclencheur de "
            "« Soumettre les livrables » n'a pas tourné."
            % mission.display_name)

        # Les quatre points du §28, que la condition de « Valider (cluster) »
        # exige. Les cocher est le geste du responsable ; le test le fait
        # explicitement plutôt que par un défaut, sans quoi la condition ne
        # serait jamais éprouvée.
        acceptance.sudo().write({
            'objectifs_atteints': True,
            'livrables_complets': True,
            'corrections_effectuees': True,
            'conforme_contrat': True,
        })

        self._do(acceptance, 'service_validate_cluster', self.manager)
        self._do(acceptance, 'service_validate_client',
                 user or self.client_user)
        mission.invalidate_recordset()
        return acceptance

    # ------------------------------------------------------------
    # Modules optionnels — `sale` et `project`
    # ------------------------------------------------------------
    #
    # Ces deux modules ne sont pas déclarés au manifeste : l'instance de
    # déploiement ne les a pas, et les exiger rendait `opex_intervenants`
    # non installable. Voir `models/optional_backends.py`.
    #
    # Les tests qui portent sur la facturation (§29) et sur le projet
    # d'exécution (§13) ne sont **pas supprimés** : ils décrivent ce que le
    # module fait quand les modules sont là, et ce jour reviendra. Ils
    # s'annoncent absents plutôt que de rougir, et se remettent à tourner
    # d'eux-mêmes le jour de l'installation — sans qu'on ait à se souvenir de
    # les décommenter, ce dont personne ne se souvient jamais.
    #
    # C'est la différence entre neutraliser et supprimer : un `skipTest` est
    # visible dans la sortie de la suite, un test effacé ne l'est pas.

    def _require_backend(self, model_name, feature):
        """Annonce le test comme non joué si le modèle n'est pas au registre.

        `feature` nomme la fonctionnalité, pas le modèle : la sortie de la
        suite doit dire ce qui n'a pas été vérifié, pas quel identifiant
        technique manquait.
        """
        if self.env.get(model_name) is None:
            self.skipTest(
                "%s : le modèle « %s » n'est pas au registre sur cette "
                "instance. Le test reprendra dès que le module sera "
                "installé." % (feature, model_name))
