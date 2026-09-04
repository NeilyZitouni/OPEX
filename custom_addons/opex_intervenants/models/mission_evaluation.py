"""Les deux évaluations de fin de mission et ce qu'elles alimentent.

Le §30 donne la grille du client, le §31 celle du cluster. Les deux portent sur
le même intervenant et la même mission, mais ne jugent pas la même chose et ne
sont pas rendues par les mêmes personnes : ce sont deux enregistrements
distincts du même modèle, que le champ `evaluateur` sépare.

La règle 7 du §39 - le client n'évalue qu'après la validation finale - est une
condition de transition, comme les règles 5 et 6. La règle 8 - une évaluation
validée alimente le profil - est une action configurée sur cette même
transition de validation.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

EVALUATION_WORKFLOW_CODE = 'mission_evaluation'
CLIENT_ROLE = 'opex_intervenants.role_client'
INTERVENANT_ROLE = 'opex_intervenants.role_intervenant'

NEW_REFERENCE = "Nouveau"

# Les six critères du §30 et les six du §31. Deux leur sont communs - le
# respect des délais et la communication -, et ils partagent le même champ :
# une évaluation est de l'un ou l'autre type, jamais des deux, donc rien ne se
# recouvre. Écrits ici plutôt que déduits d'un préfixe, pour que l'ordre du
# document soit celui de l'écran.
CLIENT_CRITERIA = (
    'note_qualite',
    'note_delais',
    'note_expertise',
    'note_communication',
    'note_pertinence',
    'note_satisfaction',
)
CLUSTER_CRITERIA = (
    'note_contrat',
    'note_delais',
    'note_livrables',
    'note_professionnalisme',
    'note_communication',
    'note_procedures',
)

# Une note de 4 ou 5 sur le respect des délais vaut « délai tenu » pour le
# pourcentage du §32. Le seuil est arbitraire et c'est pourquoi il est nommé
# ici : le changer se fait à un endroit, et le test qui le mesure le cite.
DELAY_COMPLIANCE_THRESHOLD = 4

# L'union des deux grilles, dans un ordre stable : `@api.depends` et
# `@api.constrains` reçoivent cette séquence, et un ensemble non ordonné y
# produirait une signature différente à chaque démarrage.
ALL_CRITERIA = tuple(sorted(set(CLIENT_CRITERIA) | set(CLUSTER_CRITERIA)))


class MissionEvaluation(models.Model):
    """Une évaluation de fin de mission, client (§30) ou cluster (§31).

    Aucun champ d'état : le parcours d'une évaluation - à remplir, soumise,
    validée - est celui de son instance de workflow. C'est la cinquième
    définition du module.

    Le modèle porte les dix critères des deux grilles. Seuls six sont
    applicables à un enregistrement donné, selon `evaluateur` ; les autres
    restent à zéro et sont masqués par la vue.
    """

    _name = 'opex.mission.evaluation'
    _description = "Évaluation de fin de mission"
    _inherit = ['mail.thread', 'opex.workflow.mixin']
    _order = 'mission_id, evaluateur, id desc'

    name = fields.Char(
        string="Référence", required=True, copy=False, readonly=True,
        default=NEW_REFERENCE, index=True)

    mission_id = fields.Many2one(
        'opex.mission.request',
        string="Mission",
        required=True,
        ondelete='cascade',
        index=True,
    )
    assignment_id = fields.Many2one(
        'opex.mission.assignment', string="Affectation",
        ondelete='set null')
    partner_id = fields.Many2one(
        'res.partner', string="Intervenant évalué",
        required=True, index=True)
    expert_profile_id = fields.Many2one(
        'opex.innovation.expert.profile',
        string="Profil expert",
        compute='_compute_expert_profile_id',
        store=True,
        readonly=True,
        help="La cible de la règle 8 : c'est ce profil que la validation "
             "alimente.",
    )
    client_id = fields.Many2one(
        related='mission_id.client_id', string="Client", readonly=True)

    evaluateur = fields.Selection(
        [
            ('client', "Client (§30)"),
            ('cluster', "Cluster (§31)"),
        ],
        string="Évaluation rendue par",
        required=True,
        default='client',
    )

    # Grille du client - §30
    note_qualite = fields.Integer(string="Qualité du travail")
    note_expertise = fields.Integer(string="Expertise")
    note_pertinence = fields.Integer(string="Pertinence des recommandations")
    note_satisfaction = fields.Integer(string="Satisfaction générale")

    # Grille du cluster - §31
    note_contrat = fields.Integer(string="Respect du contrat")
    note_livrables = fields.Integer(string="Qualité des livrables")
    note_professionnalisme = fields.Integer(string="Professionnalisme")
    note_procedures = fields.Integer(string="Respect des procédures")

    # Communs aux deux grilles
    note_delais = fields.Integer(string="Respect des délais")
    note_communication = fields.Integer(string="Communication")

    commentaire = fields.Text(string="Commentaire")

    note_globale = fields.Float(
        string="Note globale",
        digits=(2, 1),
        compute='_compute_grille',
        store=True,
        readonly=True,
        help="Moyenne des six critères applicables. Stockée parce que les "
             "écrans de réputation la trient et l'agrègent.",
    )
    grille_complete = fields.Boolean(
        string="Grille complète",
        compute='_compute_grille',
        store=True,
        readonly=True,
        help="Les six critères applicables sont notés. Lu par la condition "
             "de « Soumettre l'évaluation ».",
    )

    # La règle 7 lit ce champ. Il traverse la mission jusqu'au constat de
    # service fait de l'Extension 9 : « la validation finale » du §39, c'est
    # celle du §28, pas la clôture administrative.
    mission_validee = fields.Boolean(
        related='mission_id.service_fait_valide',
        string="Validation finale prononcée",
        readonly=True,
    )

    is_validated = fields.Boolean(
        string="Évaluation validée", compute='_compute_is_validated')

    # §33 - la visibilité contrôlée. Une évaluation validée n'est pas publique
    # d'office : le §33 dit « selon les droits », et c'est le cluster qui
    # décide ce qui sort du dossier.
    is_public = fields.Boolean(
        string="Visible dans l'historique public",
        default=False,
        tracking=True,
        help="Le commentaire et le détail des notes restent confidentiels "
             "quoi qu'il arrive ; cette case n'ouvre que la note globale.",
    )

    rating_id = fields.Many2one(
        'opex.expert.rating',
        string="Note portée au profil",
        readonly=True,
        copy=False,
        ondelete='set null',
        help="Créée par la validation. C'est la règle 8 du §39.",
    )

    # Une évaluation par intervenant, par mission et par évaluateur. Le trio
    # plutôt que le couple : un type de mission à plusieurs intervenants
    # produit une évaluation par personne, et le client les rend séparément.
    _evaluation_uniq = models.Constraint(
        'unique(mission_id, partner_id, evaluateur)',
        "Cet intervenant a déjà une évaluation de ce type sur cette mission.",
    )

    @api.constrains(*ALL_CRITERIA)
    def _check_scores(self):
        """Zéro vaut « pas encore noté » ; au-delà, l'échelle est celle du §30."""
        for evaluation in self:
            for field_name in evaluation._criteria_fields():
                score = evaluation[field_name]
                if not 0 <= score <= 5:
                    raise ValidationError(_(
                        "« %(critere)s » se note de 1 à 5, pas %(valeur)s."
                    ) % {
                        'critere': evaluation._fields[field_name].string,
                        'valeur': score,
                    })

    def _criteria_fields(self):
        """Les six critères applicables à cette évaluation."""
        self.ensure_one()
        return (CLUSTER_CRITERIA if self.evaluateur == 'cluster'
                else CLIENT_CRITERIA)

    @api.depends('evaluateur', *ALL_CRITERIA)
    def _compute_grille(self):
        for evaluation in self:
            scores = [evaluation[name]
                      for name in evaluation._criteria_fields()]
            evaluation.grille_complete = all(score >= 1 for score in scores)
            evaluation.note_globale = (
                round(sum(scores) / len(scores), 1) if scores else 0.0)

    @api.depends('workflow_stage_id')
    def _compute_is_validated(self):
        for evaluation in self:
            evaluation.is_validated = (
                evaluation.sudo().workflow_stage_id.code == 'validated')

    @api.depends('partner_id')
    def _compute_expert_profile_id(self):
        Profile = self.env['opex.innovation.expert.profile'].sudo()
        for evaluation in self:
            evaluation.expert_profile_id = Profile.search(
                [('partner_id', '=', evaluation.partner_id.id)], limit=1)

    @api.depends('name', 'partner_id', 'evaluateur')
    def _compute_display_name(self):
        labels = dict(self._fields['evaluateur'].selection)
        for evaluation in self:
            evaluation.display_name = "%s — %s (%s)" % (
                evaluation.name or '',
                evaluation.partner_id.display_name or '',
                labels.get(evaluation.evaluateur, ''),
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', NEW_REFERENCE) == NEW_REFERENCE:
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code(
                    'opex.mission.evaluation') or NEW_REFERENCE
        evaluations = super().create(vals_list)
        for evaluation in evaluations:
            evaluation.start_workflow(EVALUATION_WORKFLOW_CODE)
            evaluation._grant_actors()
        return evaluations

    def _grant_actors(self):
        """Qui remplit la grille, et qui la lit.

        Le client est acteur des évaluations qu'il rend et de celles-là seules :
        il n'a rien à voir dans la grille opérationnelle du cluster, qui juge
        aussi le respect des procédures internes. L'intervenant est acteur des
        deux, en lecture, parce que ce sont ses notes.

        Les acteurs viennent de la mission, jamais de l'utilisateur courant :
        les évaluations sont créées par le déclencheur de « Facturer et
        clôturer », donc sous l'identité du secrétariat.
        """
        self.ensure_one()
        instance = self.sudo().workflow_instance_id
        if not instance:
            return False

        client_role = self.env.ref(CLIENT_ROLE, raise_if_not_found=False)
        intervenant_role = self.env.ref(
            INTERVENANT_ROLE, raise_if_not_found=False)

        if self.evaluateur == 'client':
            client = self.mission_id.sudo().client_id.user_ids[:1]
            if client_role and client:
                instance.add_actor(client_role, client, 'full')

        expert = self.partner_id.sudo().user_ids[:1]
        if intervenant_role and expert:
            instance.add_actor(intervenant_role, expert, 'limited')
        return True

    # Le déclencheur de la règle 8, sur le même motif qu'aux Extensions 7 et 9 :
    # la configuration décide quelle transition alimente le profil, le Python
    # n'implémente que l'effet.
    operational_trigger = fields.Selection(
        [('reputation', "Report de la note au profil")],
        string="Déclencheur opérationnel",
        compute='_compute_operational_trigger',
        inverse='_inverse_operational_trigger',
        readonly=False,
        store=False,
    )

    def _compute_operational_trigger(self):
        for evaluation in self:
            evaluation.operational_trigger = False

    def _inverse_operational_trigger(self):
        for evaluation in self:
            code = evaluation.operational_trigger
            if not code:
                continue
            getattr(evaluation.sudo(), '_trigger_%s' % code)()

    def _trigger_reputation(self):
        """Règle 8 : une évaluation validée est associée au profil.

        La ligne créée ici est un `opex.expert.rating`, le modèle que
        l'Extension 3 avait posé vide en annonçant que l'Extension 10 le
        remplirait. Rien n'a été ajouté à ce modèle : `reputation_score` se
        recalcule seul, puisqu'il dépend de `expert_rating_ids.note`.

        La garde d'idempotence ne protège pas d'un second passage par la
        transition : `validated` est finale, l'instance se clôt en l'atteignant
        et le moteur n'y ramènera jamais l'évaluation. Elle protège du reste -
        une action rejouée à la main, un script de reprise, une transition
        ajoutée un jour vers cette étape. Une note comptée deux fois ne se
        verrait pas : elle déplacerait la moyenne, sans rien casser.
        """
        self.ensure_one()
        if self.rating_id:
            return self.rating_id

        profile = self.expert_profile_id
        if not profile:
            _logger.info(
                "opex_intervenants: évaluation %s validée sans profil expert "
                "pour %s ; aucune note portée.", self.id, self.partner_id.id)
            return False

        rating = self.env['opex.expert.rating'].sudo().create({
            'profile_id': profile.id,
            'mission_id': self.mission_id.id,
            'source': self.evaluateur,
            'note': self.note_globale,
            'respect_delais': self.note_delais >= DELAY_COMPLIANCE_THRESHOLD,
            'commentaire': self.commentaire or False,
        })
        self.sudo().rating_id = rating.id
        return rating

    def evaluation_grid(self):
        """La grille applicable, prête pour un écran ou un gabarit."""
        self.ensure_one()
        return [
            {
                'champ': name,
                'libelle': self._fields[name].string,
                'note': self[name],
            }
            for name in self._criteria_fields()
        ]


class MissionRequestEvaluation(models.Model):
    """Ce que la clôture d'une mission ouvre du côté des évaluations."""

    _inherit = 'opex.mission.request'

    evaluation_ids = fields.One2many(
        'opex.mission.evaluation', 'mission_id', string="Évaluations")
    evaluation_count = fields.Integer(
        string="Nombre d'évaluations", compute='_compute_evaluation_facts')
    evaluation_pending_count = fields.Integer(
        string="Évaluations à rendre", compute='_compute_evaluation_facts')
    evaluations_validees = fields.Boolean(
        string="Évaluations validées",
        compute='_compute_evaluation_facts',
        help="Toutes les évaluations ouvertes sur la mission ont été validées. "
             "Lu par le jalon Évaluation de la barre du §40.",
    )

    operational_trigger = fields.Selection(
        selection_add=[('evaluation', "Ouverture des évaluations de fin")],
    )

    @api.depends('evaluation_ids.workflow_stage_id')
    def _compute_evaluation_facts(self):
        for mission in self:
            evaluations = mission.sudo().evaluation_ids
            validated = evaluations.filtered('is_validated')
            mission.evaluation_count = len(evaluations)
            mission.evaluation_pending_count = len(evaluations) - len(validated)
            mission.evaluations_validees = bool(evaluations) and not (
                len(evaluations) - len(validated))

    def _trigger_evaluation(self):
        """§30 et §31 : les deux demandes d'évaluation, à la clôture.

        Rattaché à « Facturer et clôturer », comme l'Extension 1 l'avait écrit
        sur cette transition.

        Une paire par intervenant affecté : sur une mission à plusieurs
        intervenants, le client et le cluster se prononcent sur chacun
        séparément. Une note moyennée sur l'équipe ne dirait rien de personne.
        """
        self.ensure_one()
        Evaluation = self.env['opex.mission.evaluation'].sudo()
        created = Evaluation.browse()

        for assignment in self.sudo().assignment_ids.filtered('active'):
            for evaluateur in ('client', 'cluster'):
                if Evaluation.search_count([
                    ('mission_id', '=', self.id),
                    ('partner_id', '=', assignment.partner_id.id),
                    ('evaluateur', '=', evaluateur),
                ]):
                    continue
                created |= Evaluation.create({
                    'mission_id': self.id,
                    'assignment_id': assignment.id,
                    'partner_id': assignment.partner_id.id,
                    'evaluateur': evaluateur,
                })

        if not created:
            _logger.info(
                "opex_intervenants: mission %s clôturée sans affectation "
                "active ; aucune évaluation ouverte.", self.id)
        return created

    def action_view_evaluations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Évaluations"),
            'res_model': 'opex.mission.evaluation',
            'view_mode': 'list,form',
            'domain': [('mission_id', '=', self.id)],
            'context': {'default_mission_id': self.id},
        }
