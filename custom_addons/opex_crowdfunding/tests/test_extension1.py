from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

#: Les dix-sept états du workflow, dans l'ordre. Cette liste est le contrat passé
#: avec le module générique : les mêmes codes y sont configurés en base. Si
#: elle change d'un côté sans changer de l'autre, la comparaison finale perd
#: son point de repère — d'où un test qui la fige.
ETATS_ATTENDUS = [
    'draft',
    'depot_express',
    'pre_analyse',
    'clarification',
    'dossier_progressif',
    'quality_gate',
    'quality_complement',
    'etude_decision',
    'accompagnement',
    'reevaluation',
    'demo_day',
    'matching_financier',
    'mise_en_relation',
    'decision_financeur',
    'closing',
    'closed',
    'rejected',
]

#: Les informations minimales de la section 5 — et rien d'autre.
DEPOT_EXPRESS_COMPLET = {
    'porteur_type': 'startup',
    'probleme': "Les PME industrielles algériennes n'ont pas d'outil de suivi de production.",
    'solution': "Une application de supervision d'atelier, installable en une journée.",
    'secteur': 'industrie',
    'maturite': 'mvp',
    'besoin_type': 'investisseur',
}


@tagged('post_install', '-at_install')
class TestExtension1(TransactionCase):
    """Extension 1 — socle du dossier et dépôt express (section 5)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env['opex.crowdfunding.project']
        cls.porteur = cls.env['res.partner'].create({'name': "SmartFactory DZ"})

        cls.ceo = new_test_user(
            cls.env, login='cf_ceo',
            groups='base.group_user,opex_crowdfunding.group_ceo')
        cls.qualite = new_test_user(
            cls.env, login='cf_qualite',
            groups='base.group_user,opex_crowdfunding.group_quality_control')
        cls.interne = new_test_user(
            cls.env, login='cf_interne', groups='base.group_user')

    def _projet(self, **valeurs):
        """Un dossier au strict minimum ORM : un porteur et un titre."""
        donnees = {'partner_id': self.porteur.id, 'name': "Supervision d'atelier"}
        donnees.update(valeurs)
        return self.Project.create(donnees)

    # ------------------------------------------------------------------
    # Progressive commitment
    # ------------------------------------------------------------------
    def test_creation_partielle_possible(self):
        """Un dossier incomplet doit pouvoir exister : c'est le brouillon.

        Le portail (Extension 2) crée l'enregistrement dès la première étape du
        formulaire et le complète ensuite par `write()` partiels. Si un champ
        du dépôt devenait obligatoire au niveau de l'ORM, ce parcours
        casserait — ce test le verrait.
        """
        projet = self._projet()
        self.assertEqual(projet.state, 'draft')
        self.assertFalse(projet.besoin_type)

    def test_depot_express_ne_demande_que_le_minimum(self):
        """Les six informations de la section 5 suffisent à présenter un projet.

        Garde-fou du *progressive commitment* : si une extension ultérieure
        rend une information du dossier complet (business model, traction,
        valorisation…) obligatoire dès le dépôt, ce test passe au rouge. Le
        dossier complet se demande après le GO, pas avant.
        """
        projet = self._projet(**DEPOT_EXPRESS_COMPLET)
        projet.action_submit()
        self.assertEqual(projet.state, 'depot_express')

    def test_montant_et_pitch_restent_facultatifs(self):
        """« Montant indicatif si financement demandé », « document facultatif »."""
        projet = self._projet(**DEPOT_EXPRESS_COMPLET)
        self.assertFalse(projet.montant_indicatif)
        self.assertFalse(projet.pitch_document)
        projet.action_submit()
        self.assertEqual(projet.state, 'depot_express')

    # ------------------------------------------------------------------
    # La transition
    # ------------------------------------------------------------------
    def test_submit_incomplet_refuse_et_nomme_les_manques(self):
        projet = self._projet(**dict(DEPOT_EXPRESS_COMPLET, solution=False, secteur=False))
        with self.assertRaises(UserError) as capture:
            projet.action_submit()
        message = capture.exception.args[0]
        self.assertIn("Solution proposée", message)
        self.assertIn("Secteur", message)
        # Un refus qui laisserait le dossier avancer serait pire que pas de
        # contrôle du tout.
        self.assertEqual(projet.state, 'draft')

    def test_submit_deux_fois_refuse(self):
        projet = self._projet(**DEPOT_EXPRESS_COMPLET)
        projet.action_submit()
        with self.assertRaises(UserError):
            projet.action_submit()
        self.assertEqual(projet.state, 'depot_express')

    def test_submit_laisse_une_trace(self):
        """L'audit trail commence au dépôt, et reste interne (`mt_note`)."""
        projet = self._projet(**DEPOT_EXPRESS_COMPLET)
        avant = projet.message_ids
        projet.action_submit()
        depot = (projet.message_ids - avant).filtered(
            lambda message: "SmartFactory DZ" in (message.body or ""))
        self.assertTrue(depot, "Le dépôt n'a laissé aucune trace lisible.")
        self.assertEqual(depot.subtype_id, self.env.ref('mail.mt_note'))

    # ------------------------------------------------------------------
    # Le vocabulaire commun aux deux modules
    # ------------------------------------------------------------------
    def test_les_etats_du_workflow(self):
        codes = [code for code, _libelle in self.Project._fields['state'].selection]
        self.assertEqual(codes, ETATS_ATTENDUS)

    def test_champs_du_benchmark(self):
        """`score` et `ceo_approval` : les deux champs sur lesquels s'appuiera
        l'étape Demo Day de la section 18, des deux côtés de la comparaison."""
        champs = self.Project._fields
        self.assertEqual(champs['score'].type, 'integer')
        self.assertEqual(champs['ceo_approval'].type, 'boolean')

    def test_etat_lisible_par_un_humain(self):
        """Section 16 : le porteur ne voit jamais un code d'état."""
        projet = self._projet(**DEPOT_EXPRESS_COMPLET)
        self.assertEqual(projet._state_label(), "Brouillon")
        projet.action_submit()
        self.assertEqual(projet._state_label(), "Demande déposée")

    # ------------------------------------------------------------------
    # Les quatre acteurs
    # ------------------------------------------------------------------
    def test_les_quatre_groupes_existent(self):
        for xmlid in ('group_ceo', 'group_quality_control',
                      'group_expert', 'group_financial_actor'):
            self.assertTrue(self.env.ref('opex_crowdfunding.%s' % xmlid))

    def test_expert_et_acteur_financier_ne_sont_pas_internes(self):
        """Un investisseur qui devient utilisateur interne, c'est une licence
        payée par erreur et un accès bien trop large."""
        interne = self.env.ref('base.group_user')
        for xmlid in ('group_expert', 'group_financial_actor'):
            groupe = self.env.ref('opex_crowdfunding.%s' % xmlid)
            self.assertNotIn(interne, groupe.implied_ids)

    def test_ceo_gere_les_dossiers(self):
        projet = self.Project.with_user(self.ceo).create({
            'partner_id': self.porteur.id, 'name': "Dossier créé par le CEO",
        })
        projet.write({'secteur': 'sante'})
        self.assertEqual(projet.secteur, 'sante')

    @mute_logger('odoo.addons.base.models.ir_model')
    def test_controle_qualite_lit_mais_ne_cree_pas(self):
        projet = self._projet(**DEPOT_EXPRESS_COMPLET)
        self.assertEqual(projet.with_user(self.qualite).name, projet.name)
        with self.assertRaises(AccessError):
            self.Project.with_user(self.qualite).create({
                'partner_id': self.porteur.id, 'name': "Dossier créé par la qualité",
            })

    @mute_logger('odoo.addons.base.models.ir_model')
    def test_un_interne_sans_role_ne_voit_rien(self):
        """Être utilisateur du portail interne ne donne aucun droit sur les
        dossiers : « être enregistré ne donne pas accès » (section 3)."""
        projet = self._projet(**DEPOT_EXPRESS_COMPLET)
        with self.assertRaises(AccessError):
            projet.with_user(self.interne).read(['name'])
