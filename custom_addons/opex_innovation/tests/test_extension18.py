import ast
import os
import re

from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged

#: Les onze déclencheurs qui doivent être portés par une transition, avec la
#: transition attendue. Écrits ici plutôt que relus depuis la base : un test qui
#: relit la donnée qu'il vérifie ne vérifie rien.
BOUND = {
    'innovation_notify_projet_soumis': ['submit'],
    'innovation_notify_complement_demande': ['request_complement'],
    'innovation_notify_projet_qualifie': ['qualify'],
    'innovation_notify_projet_evalue': ['evaluate_with_experts',
                                        'evaluate_directly'],
    'innovation_notify_decision_comite': ['reject', 'adjourn'],
    'innovation_notify_remediation_demandee': ['adjourn'],
    'innovation_notify_projet_accepte': ['accept'],
    'innovation_notify_matching_propose': ['start_matching'],
    'innovation_notify_projet_cloture': ['close'],
}

#: ⚠ **Vide depuis l'Extension 16.**
#:
#: Trois notifications — ⑩ Nouveau livrable, ⑪ Livrable validé, ⑫ Correction
#: demandée — étaient configurées et rattachées à rien, faute de transitions
#: auxquelles les accrocher : `opex.innovation.deliverable` n'existait pas.
#:
#: L'Extension 16 les a branchées sur le workflow des livrables, sans en
#: réécrire une seule : mêmes enregistrements, même corps, même sous-type. Il ne
#: doit donc plus rester **aucune** orpheline, et ce jeu vide est ce qui le dit.
#:
#: C'est l'assertion qui a rougi le jour où l'Extension 16 a été faite — elle a
#: signalé que l'état du module avait changé au lieu de laisser une affirmation
#: périmée passer au vert.
AWAITING_EXTENSION_16 = set()

#: Les trois qui l'attendaient, gardées pour vérifier qu'elles sont bien
#: rattachées au workflow des livrables et pas ailleurs.
DELIVERABLE_TRIGGERS = {
    'innovation_notify_nouveau_livrable': [
        'deliverable_submit', 'deliverable_resubmit'],
    'innovation_notify_livrable_valide': ['deliverable_validate'],
    'innovation_notify_correction_demandee': [
        'deliverable_request_correction'],
}

#: Déclenchés depuis le code, faute de transition correspondante.
OFF_TRANSITION = {
    'innovation_notify_expert_interesse',
    'innovation_notify_evolution_financement',
}


class Extension18Case(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.innovation.project']
        cls.Action = cls.env['opex.workflow.action']

        cls.porteur = new_test_user(
            cls.env, login='e18_porteur', password='e18_porteur',
            groups='base.group_portal')
        cls.porteur.partner_id.sudo().write({'is_member': True})
        cls.secretariat = new_test_user(
            cls.env, login='e18_secr', password='e18_secr',
            groups='base.group_user,opex_membership.group_secretariat')
        cls.comite = new_test_user(
            cls.env, login='e18_comite', password='e18_comite',
            groups='base.group_user,opex_innovation.group_comite_evaluation')
        cls.ceo = new_test_user(
            cls.env, login='e18_ceo', password='e18_ceo',
            groups='base.group_user,opex_innovation.group_innovation_manager')
        cls.employe = new_test_user(
            cls.env, login='e18_employe', password='e18_employe',
            groups='base.group_user')

        cls.actors = {
            'porteur': cls.porteur, 'secretariat': cls.secretariat,
            'comite': cls.comite, 'ceo': cls.ceo,
        }

    def _project(self, **values):
        base = {
            'partner_id': self.porteur.partner_id.id,
            'name': "Smart Factory",
            'resume': "Une usine pilotée par l'IA.",
            'probleme': "Arrêts imprévus.",
            'solution': "Maintenance prédictive.",
            'secteur': 'industrie',
            'maturite': 'mvp',
            'besoin_financement': True,
            'montant_recherche': 500000,
        }
        base.update(values)
        return self.Project.sudo().create(base)

    def _do(self, project, code, actor, comment="Décision motivée."):
        transition = project.workflow_definition_id.transition_ids.filtered(
            lambda t: t.code == code)
        self.assertTrue(transition, "Transition « %s » introuvable." % code)
        return project.with_user(self.actors[actor]).workflow_do_transition(
            transition, comment=comment)

    def _action(self, code):
        action = self.Action.sudo().search([('code', '=', code)], limit=1)
        self.assertTrue(action, "Action « %s » introuvable." % code)
        return action


@tagged('post_install', '-at_install')
class TestNotificationInventory(Extension18Case):
    """Section 30 — les quatorze déclencheurs, configurés au même endroit."""

    def test_the_fourteen_triggers_exist(self):
        inventory = self.Project.notification_inventory()
        self.assertEqual(len(inventory), 14)
        missing = [row['code'] for row in inventory if not row['exists']]
        self.assertFalse(missing, "Notifications manquantes : %s"
                         % ", ".join(missing))

    def test_each_transition_bound_trigger_is_actually_attached(self):
        """Une action configurée mais rattachée à rien ne notifie personne.

        C'est le mode de défaillance propre à cette extension : tout est vert,
        la donnée existe, et aucun message ne part jamais.
        """
        inventory = {row['code']: row
                     for row in self.Project.notification_inventory()}
        for code, expected in BOUND.items():
            attached = set(inventory[code]['transitions'])
            for transition_code in expected:
                self.assertIn(
                    transition_code, attached,
                    "« %s » n'est pas branchée sur « %s » (branchée sur : %s)."
                    % (code, transition_code, ", ".join(sorted(attached))
                       or "rien"))

    def test_no_trigger_is_left_orphan(self):
        """⚠ L'inventaire nomme ses trous plutôt que de les taire.

        Trois des quatorze portaient sur `opex.innovation.deliverable` et
        n'étaient rattachées à rien tant que l'Extension 16 n'existait pas.
        Elles le sont depuis. Une orpheline aujourd'hui serait un oubli.
        """
        orphans = {row['code'] for row in self.Project.notification_inventory()
                   if row['orpheline']}
        self.assertEqual(
            orphans, AWAITING_EXTENSION_16,
            "Orphelines inattendues : %s"
            % ", ".join(sorted(orphans - AWAITING_EXTENSION_16)))

    def test_the_deliverable_triggers_are_on_the_deliverable_workflow(self):
        """Les trois ex-orphelines, branchées là où elles doivent l'être.

        Vérifier qu'elles ne sont plus orphelines ne suffit pas : accrochées
        par erreur à une transition du parcours projet, elles ne seraient pas
        orphelines non plus, et partiraient au mauvais moment.
        """
        inventory = {row['code']: row
                     for row in self.Project.notification_inventory()}
        for code, expected in DELIVERABLE_TRIGGERS.items():
            attached = set(inventory[code]['transitions'])
            self.assertTrue(attached, "« %s » n'est branchée nulle part." % code)
            for transition_code in expected:
                self.assertIn(
                    transition_code, attached,
                    "« %s » devrait être sur « %s » (branchée sur : %s)."
                    % (code, transition_code, ", ".join(sorted(attached))))

    def test_the_off_transition_triggers_are_declared_as_such(self):
        inventory = {row['code']: row
                     for row in self.Project.notification_inventory()}
        for code in OFF_TRANSITION:
            self.assertTrue(
                inventory[code]['hors_transition'],
                "« %s » devrait déclarer pourquoi elle n'est pas sur une "
                "transition." % code)
            self.assertFalse(inventory[code]['orpheline'])

    def test_every_trigger_names_its_recipients_by_role(self):
        """Jamais une personne nommée : un rôle, résolu sur `instance.actor`."""
        for code in self.Project.NOTIFICATION_CODES:
            action = self._action(code)
            self.assertTrue(
                action.target_role_ids,
                "« %s » ne vise aucun rôle : elle notifierait les abonnés du "
                "dossier, dont le porteur." % code)

    # ------------------------------------------------------------
    # ⚠ Le sous-type — bug déjà rencontré, verrouillé ici
    # ------------------------------------------------------------

    #: Ce que chaque destinataire doit recevoir. Le porteur et le candidat sont
    #: des externes : ils reçoivent par courriel. Tout le reste est interne.
    EXTERNAL_ROLES = {'Porteur'}

    def test_internal_messages_never_leave_by_email(self):
        """⚠ `mail.mt_note` pour tout ce qui est interne.

        Un message de coordination posté en `mt_comment` sur un enregistrement
        que le porteur suit lui part par courriel. Bug déjà rencontré et corrigé
        sur le Module 1 ; ce test l'empêche de revenir par la configuration
        plutôt que par le code.
        """
        fautes = []
        for code in self.Project.NOTIFICATION_CODES:
            action = self._action(code)
            roles = set(action.target_role_ids.mapped('name'))
            interne = not (roles & self.EXTERNAL_ROLES)
            if interne and action.notify_subtype != 'note':
                fautes.append("%s → %s (rôles : %s)"
                              % (code, action.notify_subtype,
                                 ", ".join(sorted(roles))))
        self.assertFalse(
            fautes,
            "Messages internes envoyés en courriel : %s" % " ; ".join(fautes))

    def test_the_holder_messages_are_the_ones_he_must_receive(self):
        """Le symétrique : ce qui s'adresse au porteur doit bien lui partir."""
        for code in self.Project.NOTIFICATION_CODES:
            action = self._action(code)
            if 'Porteur' in action.target_role_ids.mapped('name'):
                self.assertEqual(
                    action.notify_subtype, 'comment',
                    "« %s » s'adresse au porteur mais reste une note interne."
                    % code)

    def test_no_channel_other_than_portal_and_email(self):
        """« Pas de SMS », décision reprise du Module 1.

        Il n'y a rien à désactiver : les quatorze sont de type `notify`, et le
        moteur ne connaît pas d'autre canal que le message Odoo — portail et
        courriel selon le sous-type.
        """
        for code in self.Project.NOTIFICATION_CODES:
            self.assertEqual(self._action(code).action_type, 'notify')


@tagged('post_install', '-at_install')
class TestNotificationFiring(Extension18Case):
    """Les notifications partent réellement, et au bon moment."""

    def _messages(self, project):
        return project.sudo().message_ids

    def _bodies(self, project):
        return " ".join(self._messages(project).mapped('body') or [])

    def test_submitting_warns_the_secretariat_as_an_internal_note(self):
        project = self._project()
        self._do(project, 'submit', 'porteur')

        bodies = self._bodies(project)
        self.assertIn("contrôle administratif", bodies)

        message = self._messages(project).filtered(
            lambda m: "contrôle administratif" in (m.body or ''))[:1]
        self.assertTrue(message)
        self.assertEqual(message.subtype_id,
                         self.env.ref('mail.mt_note'))

    def test_the_decision_reaches_the_holder_by_email(self):
        project = self._project()
        for code, actor in (('submit', 'porteur'),
                            ('take_in_charge', 'secretariat'),
                            ('qualify', 'secretariat'),
                            ('evaluate_directly', 'comite')):
            self._do(project, code, actor)
        self._do(project, 'accept', 'comite')

        message = self._messages(project).filtered(
            lambda m: "accepté" in (m.body or ''))[:1]
        self.assertTrue(message, "Le porteur n'est pas informé de l'acceptation.")
        self.assertEqual(message.subtype_id,
                         self.env.ref('mail.mt_comment'))
        self.assertIn(self.porteur.partner_id,
                      message.notified_partner_ids | message.partner_ids)

    def test_adjourning_fires_the_two_events_of_the_section(self):
        """⑤ et ⑥ sur la même transition : le moteur les enchaîne."""
        project = self._project()
        for code, actor in (('submit', 'porteur'),
                            ('take_in_charge', 'secretariat'),
                            ('qualify', 'secretariat'),
                            ('evaluate_directly', 'comite')):
            self._do(project, code, actor)
        self._do(project, 'adjourn', 'comite', comment="À retravailler.")

        bodies = self._bodies(project)
        self.assertIn("rendu sa décision", bodies)
        self.assertIn("nécessite des améliorations", bodies)

    # ------------------------------------------------------------
    # ⑬ Évolution du financement
    # ------------------------------------------------------------

    def test_a_real_change_of_amount_warns_the_holder(self):
        project = self._project()
        before = len(self._messages(project))

        project.sudo().write({'financement_obtenu': 300000})
        self.assertGreater(len(self._messages(project)), before)
        self.assertIn("financement de votre projet a évolué",
                      self._bodies(project))

    def test_rewriting_the_same_amount_warns_nobody(self):
        """⚠ Sur le changement de valeur, pas sur la présence de la clé.

        Un écran qui renvoie tous ses champs à chaque enregistrement écrit
        `financement_obtenu` sans y toucher. Notifier sur la clé enverrait un
        courriel au porteur à chaque sauvegarde du dossier par le cluster.
        """
        project = self._project()
        project.sudo().write({'financement_obtenu': 300000})
        after_first = len(self._messages(project))

        project.sudo().write({'financement_obtenu': 300000})
        self.assertEqual(len(self._messages(project)), after_first)

    def test_notify_event_uses_the_configured_action_not_a_literal(self):
        """`notify_event()` ne construit aucun message : elle en nomme un.

        On modifie le corps configuré, et le message posté suit — preuve que le
        texte vient bien de la donnée et non d'une chaîne en Python.
        """
        project = self._project()
        action = self._action('innovation_notify_evolution_financement')
        action.sudo().body = "<p>Formulation changée par configuration.</p>"

        project.notify_event('innovation_notify_evolution_financement')
        self.assertIn("changée par configuration", self._bodies(project))

    def test_an_unknown_action_code_stays_silent(self):
        """Une notification est un effet de bord : elle ne fait pas échouer
        l'opération qui l'a déclenchée."""
        project = self._project()
        self.assertFalse(project.notify_event('innovation_notify_inexistante'))


@tagged('post_install', '-at_install')
class TestNoHardcodedMessages(Extension18Case):
    """⚠ La question posée : reste-t-il des `message_post()` en dur ?

    Ce test répond, et surtout il **fige** la réponse. Sans lui, la règle de la
    section 30 tient tant que quelqu'un y pense ; avec lui, un quinzième
    message écrit en Python fait rougir la suite.
    """

    #: Le seul `message_post()` toléré dans le métier, et sa justification.
    #: Toute autre occurrence fait échouer le test.
    ALLOWED = {
        ('innovation_project.py', 'propose_to_candidate'):
            "Message adressé à **une personne nommée** — le candidat qui vient "
            "d'être retenu. Une action `notify` configurée résout ses "
            "destinataires par rôle : elle notifierait tous les experts déjà "
            "proposés sur le dossier, dont ceux qui ont déjà répondu. Le "
            "moteur ne sait pas encore adresser une notification configurée à "
            "un destinataire passé en argument.",
    }

    def test_the_business_module_posts_no_message_of_its_own(self):
        import odoo.addons.opex_innovation as business
        import inspect

        root = os.path.dirname(inspect.getfile(business))
        found, scanned = [], 0

        for base, _dirs, files in os.walk(root):
            if 'tests' in base.split(os.sep):
                continue
            for filename in sorted(files):
                if not filename.endswith('.py'):
                    continue
                path = os.path.join(base, filename)
                with open(path, encoding='utf-8') as handle:
                    tree = ast.parse(handle.read(), filename=filename)
                scanned += 1

                # Fonction englobante de chaque appel, pour situer la faute.
                for node in ast.walk(tree):
                    if not isinstance(node, (ast.FunctionDef,
                                             ast.AsyncFunctionDef)):
                        continue
                    for inner in ast.walk(node):
                        if (isinstance(inner, ast.Call)
                                and isinstance(inner.func, ast.Attribute)
                                and inner.func.attr in ('message_post',
                                                        'message_notify')):
                            found.append((filename, node.name, inner.lineno))

        # ⚠ Assertion positive d'abord : un `root` erroné donnerait zéro
        # fichier, zéro trouvaille, et un test vert qui ne prouve rien.
        self.assertGreaterEqual(
            scanned, 10, "Le module n'a pas été parcouru (%s fichiers)."
            % scanned)

        unexpected = [
            "%s:%s dans %s()" % (filename, lineno, function)
            for filename, function, lineno in found
            if (filename, function) not in self.ALLOWED
        ]
        self.assertFalse(
            unexpected,
            "`message_post()` en dur hors des cas justifiés : %s"
            % " ; ".join(unexpected))

        # Et le symétrique : si l'exception disparaît un jour, on veut le
        # savoir pour retirer la dérogation plutôt que la laisser périmer.
        still_there = {(f, fn) for f, fn, _ in found}
        stale = set(self.ALLOWED) - still_there
        self.assertFalse(
            stale,
            "Dérogations devenues inutiles, à retirer de ALLOWED : %s"
            % ", ".join("%s/%s" % pair for pair in sorted(stale)))

    def test_the_messages_all_live_in_one_data_file(self):
        """« Il faut chercher à quinze endroits pourquoi un email part. »

        Ce fichier **est** ces quinze endroits, réduits à un.
        """
        import odoo.addons.opex_innovation as business
        import inspect

        path = os.path.join(
            os.path.dirname(inspect.getfile(business)),
            'data', 'notifications.xml')
        self.assertTrue(os.path.exists(path))
        with open(path, encoding='utf-8') as handle:
            content = handle.read()
        for code in self.Project.NOTIFICATION_CODES:
            self.assertIn(code, content)


@tagged('post_install', '-at_install')
class TestTraceability(Extension18Case):
    """Section 31 — l'historique, rien à recoder."""

    def test_the_history_is_the_engine_journal(self):
        """Aucun modèle d'historique métier n'a été créé."""
        self.assertNotIn('opex.innovation.history', self.env)
        self.assertIn('opex.workflow.history', self.env)

    def test_entries_are_dictionaries_never_the_recordset(self):
        """Motif repris du Module 1 : le modèle décide ce qui est lisible."""
        project = self._project()
        self._do(project, 'submit', 'porteur')

        entries = project.history_entries(self.porteur)
        self.assertTrue(entries)
        self.assertIsInstance(entries, list)
        self.assertIsInstance(entries[0], dict)
        self.assertEqual(
            set(entries[0]),
            {'date', 'body', 'code', 'author', 'comment'})

    def test_the_holder_reads_labels_never_technical_codes(self):
        project = self._project()
        self._do(project, 'submit', 'porteur')
        self._do(project, 'take_in_charge', 'secretariat')

        entries = project.history_entries(self.porteur)
        labels = [entry['body'] for entry in entries]
        self.assertTrue(any(labels), "Historique vide.")
        self.assertFalse(
            [entry for entry in entries if entry['code']],
            "Le porteur reçoit des codes techniques d'étape.")

        # Le cluster, lui, y a droit — c'est ce qui rend l'absence
        # significative plutôt qu'accidentelle.
        internal = project.history_entries(self.ceo)
        self.assertTrue([entry for entry in internal if entry['code']])

    def test_the_history_records_every_passage(self):
        """⚠ En compréhension, pas avec `mapped()` : un dossier qui repasse par
        la même étape doit apparaître deux fois."""
        project = self._project()
        for code, actor in (('submit', 'porteur'),
                            ('take_in_charge', 'secretariat'),
                            ('request_complement', 'secretariat'),
                            ('resubmit_after_complement', 'porteur')):
            self._do(project, code, actor)

        bodies = [entry['body'] for entry in project.history_entries(self.ceo)]
        self.assertGreaterEqual(
            len([b for b in bodies if b]), 5,
            "Chaque passage doit laisser sa ligne : %s" % bodies)


@tagged('post_install', '-at_install')
class TestSection32Rights(Extension18Case):
    """Section 32 — le tableau des cinq acteurs."""

    def test_an_ordinary_employee_cannot_read_a_draft(self):
        """Ce qui manquait : aucune `ir.rule` interne n'existait sur le projet.

        Tout utilisateur interne lisait l'intégralité des projets, brouillons
        compris — et pouvait les écrire.
        """
        draft = self._project()
        submitted = self._project(name="Déjà soumis")
        self._do(submitted, 'submit', 'porteur')

        visible = self.Project.with_user(self.employe).search([
            ('id', 'in', (draft | submitted).ids)])

        # Positive d'abord : la règle n'est pas un « tout refuser ».
        self.assertIn(submitted, visible)
        self.assertNotIn(draft, visible)

    def test_an_ordinary_employee_cannot_write_a_project(self):
        from odoo.exceptions import AccessError

        project = self._project()
        self._do(project, 'submit', 'porteur')
        with self.assertRaises(AccessError):
            project.with_user(self.employe).write({'resume': "Réécrit."})

    def test_the_manager_keeps_full_access(self):
        """Règles de groupes différents : elles s'unissent, elles ne se
        retranchent pas. Le gestionnaire retrouve tout par sa propre règle."""
        draft = self._project()
        visible = self.Project.with_user(self.ceo).search([
            ('id', '=', draft.id)])
        self.assertIn(draft, visible)

    def test_the_secretariat_does_not_see_drafts_either(self):
        """Section 32 : le secrétariat voit les « projets soumis ». Un dossier
        en cours de rédaction n'appartient qu'à son porteur."""
        draft = self._project()
        visible = self.Project.with_user(self.secretariat).search([
            ('id', '=', draft.id)])
        self.assertFalse(visible)

    def test_the_holder_still_sees_his_own_draft(self):
        draft = self._project()
        visible = self.Project.with_user(self.porteur).search([
            ('id', '=', draft.id)])
        self.assertIn(draft, visible)


@tagged('post_install', '-at_install')
class TestHistoryOnPortal(HttpCase):
    """Le bloc QWeb de la section 31, rendu pour de bon."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.innovation.project']
        cls.porteur = new_test_user(
            cls.env, login='e18p_porteur', password='e18p_porteur',
            groups='base.group_portal')
        cls.porteur.partner_id.sudo().write({'is_member': True})
        cls.secretariat = new_test_user(
            cls.env, login='e18p_secr', password='e18p_secr',
            groups='base.group_user,opex_membership.group_secretariat')

    def test_the_holder_page_shows_the_history_without_technical_codes(self):
        project = self.Project.sudo().create({
            'partner_id': self.porteur.partner_id.id,
            'name': "Smart Factory",
            'resume': "Une usine pilotée par l'IA.",
            'probleme': "Arrêts imprévus.",
            'solution': "Maintenance prédictive.",
            'secteur': 'industrie',
            'maturite': 'mvp',
        })
        submit = project.workflow_definition_id.transition_ids.filtered(
            lambda t: t.code == 'submit')
        project.with_user(self.porteur).workflow_do_transition(submit)
        take = project.workflow_definition_id.transition_ids.filtered(
            lambda t: t.code == 'take_in_charge')
        project.with_user(self.secretariat).workflow_do_transition(take)

        self.authenticate('e18p_porteur', 'e18p_porteur')
        response = self.url_open('/my/innovation/%s' % project.id)
        self.assertEqual(response.status_code, 200)

        raw = response.text
        flat = re.sub(r'\s+', ' ', raw)

        # Positive d'abord : sans elle, une page 500 passerait au vert.
        self.assertIn("Smart Factory", flat)
        self.assertIn("Historique", flat)
        self.assertIn("Date / heure", flat)
        self.assertIn("Événement", flat)

        # Et les codes techniques n'y sont pas.
        for code in ('under_review', 'workflow_stage_id'):
            self.assertNotIn(code, raw,
                             "Code technique « %s » rendu au porteur." % code)
