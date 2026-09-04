from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestApplicationPool(TransactionCase):
    """Extension 6 — le pool unique du §10.

    Deux exigences, et la seconde est celle que le brief demande d'écrire
    explicitement :

    1. **toutes les candidatures convergent dans le même objet**, quelle que
       soit leur origine — deuxième critère d'acceptation du §21 ;
    2. **les deux machines à états sont indépendantes** — une mission en
       `selection` porte simultanément des candidatures à des étapes
       différentes.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Mission = cls.env['opex.mission.request']
        cls.Application = cls.env['opex.mission.application']

        cls.audit = cls.env.ref('opex_intervenants.mission_type_audit')
        cls.domaine = cls.env.ref(
            'opex_intervenants.mission_domain_cybersecurite')
        cls.competence = cls.env['opex.innovation.competence'].create(
            {'name': "Cybersécurité", 'code': 'pool_cyber'})

        cls.client_user = new_test_user(
            cls.env, login='pool_client', groups='base.group_portal')
        cls.manager = new_test_user(
            cls.env, login='pool_manager',
            groups='base.group_user,opex_intervenants.group_mission_manager')
        cls.decideur = new_test_user(
            cls.env, login='pool_decideur',
            groups='base.group_user,opex_intervenants.group_mission_committee')

    # ------------------------------------------------------------
    # Fabriques
    # ------------------------------------------------------------

    @classmethod
    def _today(cls, **delta):
        return fields.Date.context_today(cls.env['opex.mission.request']) \
            + timedelta(**delta)

    def _expert(self, login, competences=None, dispo=True, certifs=None):
        user = new_test_user(
            self.env, login=login, groups='base.group_portal')
        user.partner_id.sudo().write({'wilaya': "Alger"})
        profile = self.env['opex.innovation.expert.profile'].sudo().create({
            'partner_id': user.partner_id.id, 'domaine_expertise': "Sécurité",
            'annees_experience': 10, 'tjm_indicatif': 15000.0,
        })
        profile.action_activate_profile()
        for competence in (competences or []):
            self.env['opex.expert.skill'].sudo().create({
                'profile_id': profile.id, 'competence_id': competence.id,
                'niveau': 'expert', 'annees': 8})
        self.env['opex.expert.experience'].sudo().create({
            'profile_id': profile.id, 'name': "Mission",
            'domaine_id': self.domaine.id, 'seniorite': 'senior'})
        if dispo:
            self.env['opex.expert.availability'].sudo().create({
                'profile_id': profile.id, 'date_debut': self._today(days=-1),
                'date_fin': self._today(days=90), 'taux': 100})
        # D1 : rapprochée au référentiel, sinon elle ne compte pour aucun
        # critère - un intitulé libre n'est comparable à rien.
        Synonyme = self.env['opex.certification.synonyme']
        for intitule in (certifs or []):
            canonique = Synonyme.resolve_label(intitule)
            self.env['opex.expert.certification'].sudo().create({
                'profile_id': profile.id, 'name': intitule,
                'certification_id': canonique.id if canonique else False,
                'source': 'expert', 'confiance': 'expert',
                'date_expiration': self._today(days=365)})
        user.partner_id.invalidate_recordset()
        return user.partner_id

    def _mission(self, **overrides):
        values = {
            'title': "Audit cybersécurité", 'mission_type_id': self.audit.id,
            'client_id': self.client_user.partner_id.id,
            'description': "Audit.", 'objectifs': "Cartographier.",
            'domaine_id': self.domaine.id,
            'skill_ids': [(6, 0, self.competence.ids)],
            'budget_estimatif': 300000.0, 'duree_estimee_jours': 15,
            'date_limite_candidature': self._today(days=30),
        }
        values.update(overrides)
        return self.Mission.create(values)

    def _do(self, record, code, user, comment="Décision du test."):
        transition = record.workflow_definition_id.sudo().transition_ids\
            .filtered(lambda t: t.code == code)
        record.with_user(user).sudo().workflow_do_transition(
            transition, comment=comment)
        record.invalidate_recordset()
        return record

    def _open_the_call(self, mission):
        self._do(mission, 'mission_submit', self.client_user)
        self._do(mission, 'mission_start_sourcing', self.manager)
        self._do(mission, 'mission_open_applications', self.manager)
        return mission

    def _apply(self, mission, partner, source='portail'):
        """Une candidature amenée jusqu'au dépôt, par le moteur."""
        application = self.Application.create({
            'mission_id': mission.id, 'partner_id': partner.id,
            'source': source, 'disponibilite': 'oui',
            'delai_propose_jours': 10, 'tarif_propose': 15000.0,
            'type_tarif': 'tjm', 'motivation': "Motivé.",
            'consentement': True,
        })
        user = partner.user_ids[:1]
        self._do(application, 'application_view', user)
        self._do(application, 'application_express_interest', user)
        self._do(application, 'application_apply', user)
        return application

    #
    # LA CONVERGENCE — deuxième critère d'acceptation du §21
    #

    def test_the_four_origins_land_in_the_same_object(self):
        """« Toutes les candidatures convergent dans un objet unique. »

        Un seul modèle, une seule définition de workflow, un champ `source`.
        Rien d'autre ne les distingue — et c'est ce qui les rend comparables.
        """
        mission = self._open_the_call(self._mission())
        partenaires = {
            source: self._expert('pool_%s' % source,
                                 competences=[self.competence])
            for source in ('matching', 'portail', 'invitation', 'manuel')
        }
        candidatures = self.Application.browse()
        for source, partner in partenaires.items():
            candidatures |= self.Application.create({
                'mission_id': mission.id, 'partner_id': partner.id,
                'source': source})

        self.assertEqual(len(candidatures), 4)
        # Un seul modèle…
        self.assertEqual({a._name for a in candidatures},
                         {'opex.mission.application'})
        # …une seule définition de workflow…
        self.assertEqual(
            len(candidatures.mapped('workflow_definition_id')), 1)
        # …et la même étape de départ pour toutes.
        self.assertEqual(
            {a.workflow_stage_id.code for a in candidatures}, {'invited'})
        # Seule l'origine diffère.
        self.assertEqual(
            {a.source for a in candidatures},
            {'matching', 'portail', 'invitation', 'manuel'})

    def test_the_comparison_row_has_the_same_shape_for_every_origin(self):
        """« Une candidature du matching et une candidature Web sont
        comparables **dans le même écran**. »

        Elles le sont parce qu'elles en sortent avec les **mêmes clés**. Une
        forme différente par origine obligerait l'écran à brancher, et
        n'importe quel ajout ultérieur ferait diverger les deux colonnes.
        """
        mission = self._open_the_call(self._mission())
        du_matching = self._apply(
            mission, self._expert('pool_m', competences=[self.competence]),
            source='matching')
        du_portail = self._apply(
            mission, self._expert('pool_p', competences=[self.competence]),
            source='portail')

        self.assertEqual(
            set(du_matching.comparison_row()),
            set(du_portail.comparison_row()),
            "Les deux origines ne produisent pas les mêmes colonnes.")
        self.assertNotEqual(
            du_matching.comparison_row()['source'],
            du_portail.comparison_row()['source'])

    #
    # L'INDÉPENDANCE DES DEUX MACHINES — le test demandé
    #

    def test_a_mission_in_selection_carries_applications_at_every_stage(self):
        """Le test que le §12.2 réclame, écrit explicitement.

        « La séparation des deux machines à états est obligatoire : l'avancement
        global de la mission ne doit pas être confondu avec le parcours
        individuel de chaque candidat. »

        Une mission en `selection` porte ici **six** candidatures à **six**
        étapes différentes, sur les deux canaux. Aucune n'a déplacé l'appel, et
        l'appel n'en a déplacé aucune.
        """
        mission = self._open_the_call(self._mission())

        # Six candidatures, six parcours
        invitee = self.Application.create({
            'mission_id': mission.id,
            'partner_id': self._expert('pool_a', [self.competence]).id,
            'source': 'matching'})

        interessee = self.Application.create({
            'mission_id': mission.id,
            'partner_id': self._expert('pool_b', [self.competence]).id,
            'source': 'portail'})
        self._do(interessee, 'application_view',
                 interessee.partner_id.user_ids[:1])

        deposee = self._apply(
            mission, self._expert('pool_c', [self.competence]))

        qualifiee = self._apply(
            mission, self._expert('pool_d', [self.competence]))
        self._do(qualifiee, 'application_screen', self.manager)

        short_listee = self._apply(
            mission, self._expert('pool_e', [self.competence]),
            source='matching')
        self._do(short_listee, 'application_screen', self.manager)
        self._do(short_listee, 'application_shortlist', self.manager)

        ecartee = self._apply(
            mission, self._expert('pool_f', [self.competence]))
        self._do(ecartee, 'application_reject_applied', self.manager)

        # L'appel avance de son côté
        self._do(mission, 'mission_close_applications', self.manager)
        self.assertEqual(mission.workflow_stage_id.code, 'selection')

        # Six étapes distinctes, sous une seule mission
        etapes = {
            invitee: 'invited',
            interessee: 'viewed',
            deposee: 'applied',
            qualifiee: 'screened',
            short_listee: 'shortlisted',
            ecartee: 'rejected',
        }
        for application, attendue in etapes.items():
            application.invalidate_recordset()
            self.assertEqual(
                application.workflow_stage_id.code, attendue,
                "La candidature de %s devrait être en « %s »."
                % (application.partner_id.name, attendue))
        self.assertEqual(len(set(etapes.values())), 6)

        # Faire avancer une candidature ne bouge ni l'appel,
        # ni les cinq autres
        self._do(short_listee, 'application_select', self.decideur)
        mission.invalidate_recordset()
        self.assertEqual(
            mission.workflow_stage_id.code, 'selection',
            "L'appel a suivi l'avancement d'une de ses candidatures.")
        for application, attendue in etapes.items():
            if application == short_listee:
                continue
            application.invalidate_recordset()
            self.assertEqual(application.workflow_stage_id.code, attendue)

        # Faire avancer l'appel ne bouge aucune candidature
        self._do(mission, 'mission_award', self.decideur)
        self.assertEqual(mission.workflow_stage_id.code, 'awarded')
        for application, attendue in etapes.items():
            application.invalidate_recordset()
            if application == short_listee:
                self.assertEqual(application.workflow_stage_id.code, 'selected')
            else:
                self.assertEqual(
                    application.workflow_stage_id.code, attendue,
                    "L'attribution de l'appel a modifié une candidature qui "
                    "n'y était pour rien.")

        # Et les instances sont bien distinctes
        instances = {a.workflow_instance_id for a in etapes}
        self.assertEqual(len(instances), 6)
        self.assertNotIn(mission.workflow_instance_id, instances)

    #
    # LES COLONNES DU §10
    #

    def test_the_column_follows_the_stage(self):
        """`pool_column` est une **projection**, pas un second état."""
        mission = self._open_the_call(self._mission())
        application = self._apply(
            mission, self._expert('pool_col', [self.competence]))

        self.assertEqual(application.pool_column, 'nouveaux')
        self._do(application, 'application_screen', self.manager)
        self.assertEqual(application.pool_column, 'qualifies')
        self._do(application, 'application_shortlist', self.manager)
        self.assertEqual(application.pool_column, 'short_list')
        self._do(application, 'application_select', self.decideur)
        self.assertEqual(application.pool_column, 'retenus')

    def test_the_column_is_computed_stored_and_readonly(self):
        """Le champ qu'on nous reprochera en soutenance, et la réponse.

        Calculé depuis l'étape, stocké pour être groupable, **readonly** : il
        ne peut pas diverger du workflow. C'est le parti d'`is_published` sur
        l'appel, repris tel quel.
        """
        champ = self.Application._fields['pool_column']
        self.assertTrue(champ.compute)
        self.assertTrue(champ.store)
        self.assertTrue(champ.readonly)
        # Pas d'assertion sur `champ.depends` : l'attribut n'existe pas sur
        # l'objet `Field` en Odoo 19 (`AttributeError`). La dépendance à
        # l'étape se prouve de toute façon mieux par le comportement —
        # `test_the_column_follows_the_stage` la suit sur quatre transitions.

    def test_the_ten_stages_map_onto_the_columns(self):
        """Aucune étape ne tombe dans un défaut silencieux."""
        from odoo.addons.opex_intervenants.models.mission_application_pool \
            import POOL_COLUMNS, STAGE_TO_COLUMN

        definition = self.env['opex.workflow.definition']._get_for_code(
            'mission_application')
        codes = set(definition.stage_ids.mapped('code'))
        self.assertEqual(
            codes, set(STAGE_TO_COLUMN),
            "Une étape de la définition n'est pas rattachée à une colonne.")
        self.assertTrue(
            set(STAGE_TO_COLUMN.values()) <= {c for c, _l in POOL_COLUMNS})

    def test_every_column_is_shown_even_when_empty(self):
        """Un Kanban dont les colonnes apparaissent au fur et à mesure ne se lit
        pas comme un processus."""
        from odoo.addons.opex_intervenants.models.mission_application_pool \
            import POOL_COLUMNS

        self.assertEqual(
            self.Application._group_expand_pool_column([], []),
            [code for code, _label in POOL_COLUMNS])

    def test_the_kanban_does_not_let_a_card_be_dragged(self):
        """Glisser une carte écrirait `pool_column` et court-circuiterait le
        moteur : ni rôle, ni condition, ni historique.

        C'est le seul endroit du module où l'ergonomie native d'Odoo aurait
        cassé la règle qui gouverne tout le reste.
        """
        vue = self.env.ref('opex_intervenants.view_mission_application_kanban')
        self.assertIn('records_draggable="0"', vue.arch)

    #
    # LES ALERTES D'ÉLIGIBILITÉ — §10
    #

    def test_the_alerts_catch_what_the_matching_never_filtered(self):
        """La raison d'être des alertes.

        Les critères éliminatoires de l'Extension 4 filtrent le **vivier du
        matching**. Un candidat arrivé par le **portail** ne passe par aucun
        vivier : sans ces alertes, il arriverait en short-list sans que rien ne
        signale qu'il n'a pas la certification obligatoire.
        """
        # D1 : l'exigence est une référence du référentiel, plus un texte.
        mission = self._open_the_call(self._mission(
            certifications_souhaitees=False,
            certification_ids=[(6, 0, self.env.ref(
                'opex_membership.certification_iso_27001').ids)]))
        sans_certif = self._expert('pool_nc', [self.competence])
        avec_certif = self._expert(
            'pool_ok', [self.competence], certifs=["ISO 27001"])

        # Le matching l'aurait écarté du vivier…
        self.assertNotIn(sans_certif, [])  # assertion positive de contexte
        proposes = mission.run_smart_matching().partner_id
        self.assertIn(avec_certif, proposes)
        self.assertNotIn(sans_certif, proposes)

        # …mais rien ne l'empêche d'arriver par le portail.
        par_le_portail = self._apply(mission, sans_certif)
        alertes = par_le_portail.eligibility_alerts()
        bloquantes = [a for a in alertes if a['niveau'] == 'danger']
        self.assertTrue(
            bloquantes,
            "Un candidat sans le critère obligatoire arrive dans le pool sans "
            "alerte : les deux canaux ne sont plus comparables.")
        self.assertTrue(par_le_portail.has_blocking_alert)

        # Le candidat conforme, lui, n'a pas d'alerte bloquante.
        conforme = self._apply(mission, avec_certif)
        self.assertFalse(conforme.has_blocking_alert)

    def test_the_alerts_reuse_the_calls_own_criteria(self):
        """Elles ne réécrivent pas la liste des critères éliminatoires.

        Le jour où le cluster en change un, les alertes suivent. Deux listes
        auraient divergé au premier ajustement.
        """
        import inspect

        from odoo.addons.opex_intervenants.models import (
            mission_application_pool)

        source = inspect.getsource(mission_application_pool)
        self.assertIn('_matching_check_eliminatoires', source)
        self.assertIn("matching_criteria()", source)

    def test_an_unavailable_candidate_raises_an_alert(self):
        mission = self._open_the_call(self._mission())
        indisponible = self._expert(
            'pool_indispo', [self.competence], dispo=False)
        application = self._apply(mission, indisponible)
        titres = [a['titre'] for a in application.eligibility_alerts()]
        self.assertTrue(
            any("disponibilité" in t.lower() for t in titres),
            "Aucune alerte sur un candidat sans disponibilité : %s" % titres)

    def test_a_tariff_above_budget_raises_an_alert(self):
        """Même arithmétique que le critère budget de l'E4 : le budget
        **journalier**, pas le total."""
        mission = self._open_the_call(
            self._mission(budget_estimatif=300000.0, duree_estimee_jours=15))
        cher = self._expert('pool_cher', [self.competence])
        application = self._apply(mission, cher)
        application.sudo().write({'tarif_propose': 50000.0,
                                  'type_tarif': 'tjm'})
        application.invalidate_recordset()
        titres = [a['titre'] for a in application.eligibility_alerts()]
        self.assertTrue(any("budget" in t.lower() for t in titres), titres)

    def test_a_clean_candidate_has_no_alert(self):
        """Assertion positive : les alertes discriminent, elles ne crient pas
        sur tout le monde."""
        mission = self._open_the_call(self._mission())
        impeccable = self._expert('pool_clean', [self.competence])
        application = self._apply(mission, impeccable)
        self._do(application, 'application_screen', self.manager)
        application.sudo().score = 88.0
        application.invalidate_recordset()
        self.assertEqual(
            application.eligibility_alerts(), [],
            "Un candidat conforme déclenche des alertes : elles ne "
            "discriminent plus rien.")

    def test_the_alert_counters_use_a_distinct_compute(self):
        """Règle 9 : un `compute` ne mélange pas stocké et non stocké."""
        champs = self.Application._fields
        self.assertTrue(champs['pool_column'].store)
        self.assertFalse(champs['alert_count'].store)
        self.assertNotEqual(
            champs['pool_column'].compute, champs['alert_count'].compute)

    def test_the_comparison_row_returns_a_dictionary(self):
        """Le responsable compare des candidats, il ne reçoit pas les objets."""
        mission = self._open_the_call(self._mission())
        application = self._apply(
            mission, self._expert('pool_dict', [self.competence]))
        ligne = application.comparison_row()
        self.assertIsInstance(ligne, dict)
        for interdit in ('partner_id', 'mission_id', 'workflow_instance_id',
                         'expert_profile_id'):
            self.assertNotIn(interdit, ligne)
