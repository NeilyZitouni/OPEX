from odoo import _, api, fields, models
from odoo.exceptions import UserError

#: Code de la définition de workflow du projet, configurée en data XML. C'est
#: le **seul** mot que ce module connaît de son propre processus.
PROJECT_WORKFLOW_CODE = 'innovation_project'

#: Rôle porté par un évaluateur désigné sur un projet (section 15).
EVALUATOR_ROLE = 'opex_innovation.role_evaluateur'


class InnovationProject(models.Model):
    """Un projet d'innovation déposé par un membre du cluster.

    ═══════════════════════════════════════════════════════════════════════
    ⚠ CE MODÈLE N'A PAS DE CHAMP `state`.
    ═══════════════════════════════════════════════════════════════════════

    Son avancement, c'est `workflow_stage_id` — related sur
    `workflow_instance_id.current_stage_id`, piloté par une définition décrite
    en données. Les quinze étapes du parcours, leurs libellés, les trois sorties
    du comité et les deux boucles de retour vivent dans
    `data/project_workflow.xml` et nulle part ailleurs.

    Ajouter ici un `state = fields.Selection([...])` « pour aller plus vite »
    ferait de ce module un workflow codé de plus, et annulerait la démonstration
    entière du travail. Un test l'interdit explicitement.

    ⚠ **N'hérite pas de `project.project`**, malgré le Product Backlog.
    `project.project` apporte son propre `stage_id`, ses tâches et ses vues
    Kanban, en collision frontale avec nos étapes — c'est exactement la
    collision de nommage qui échoue au runtime plutôt qu'au chargement. Le lien
    se fait par `project_id`, alimenté au démarrage de l'accompagnement quand le
    dossier devient un vrai projet à piloter.
    """

    _name = 'opex.innovation.project'
    _description = "Projet d'innovation"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'opex.workflow.mixin']
    _order = 'create_date desc'

    # ------------------------------------------------------------
    # Section 5 — Le porteur, repris du profil sans ressaisie
    # ------------------------------------------------------------

    partner_id = fields.Many2one(
        'res.partner',
        string="Porteur",
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
    )
    # `related` et non recopie : « le porteur ne doit pas ressaisir
    # inutilement les informations déjà présentes dans son profil ». Une copie
    # divergerait dès la première mise à jour du contact.
    organisation_id = fields.Many2one(
        related='partner_id.parent_id', string="Organisation", readonly=True)
    email = fields.Char(related='partner_id.email', readonly=True)
    telephone = fields.Char(related='partner_id.phone', readonly=True)
    wilaya = fields.Char(related='partner_id.wilaya', readonly=True)
    secteur_porteur = fields.Char(
        related='partner_id.secteur_activite', readonly=True)

    # ------------------------------------------------------------
    # Section 5 — Le projet
    # ------------------------------------------------------------

    name = fields.Char(string="Nom du projet", required=True, tracking=True)
    resume = fields.Text(string="Résumé du projet")
    probleme = fields.Text(
        string="Problème identifié",
        help="Quel problème votre projet cherche-t-il à résoudre ?")
    solution = fields.Text(
        string="Solution proposée",
        help="Comment votre solution répond-elle à ce problème ?")
    secteur = fields.Selection(
        [
            ('industrie', "Industrie"),
            ('energie', "Énergie"),
            ('numerique', "Numérique"),
            ('agriculture', "Agriculture"),
            ('sante', "Santé"),
            ('environnement', "Environnement"),
            ('transport', "Transport"),
            ('autre', "Autre"),
        ],
        string="Secteur",
        tracking=True,
    )
    maturite = fields.Selection(
        [
            ('idee', "Idée"),
            ('prototype', "Prototype"),
            ('mvp', "MVP"),
            ('produit', "Produit développé"),
            ('premiers_clients', "Premiers clients"),
            ('commercialisation', "Commercialisation"),
            ('industrialisation', "Industrialisation"),
        ],
        string="Niveau de maturité",
        tracking=True,
    )

    # ------------------------------------------------------------
    # Section 6 — Marché et modèle économique
    # ------------------------------------------------------------

    marche_cible = fields.Text(string="Marché cible", help="Qui sont vos clients ?")
    besoin_marche = fields.Text(
        string="Besoin du marché", help="Quel besoin avez-vous identifié ?")
    concurrence = fields.Text(
        string="Concurrence", help="Qui sont vos principaux concurrents ?")
    proposition_valeur = fields.Text(
        string="Proposition de valeur",
        help="Pourquoi votre solution est-elle différente ?")
    modele_economique = fields.Selection(
        [
            ('vente', "Vente"),
            ('abonnement', "Abonnement"),
            ('licence', "Licence"),
            ('commission', "Commission"),
            ('marketplace', "Marketplace"),
            ('autre', "Autre"),
        ],
        string="Modèle économique",
    )
    potentiel_commercial = fields.Selection(
        [
            ('local', "Marché local"),
            ('national', "Marché national"),
            ('international', "Marché international"),
        ],
        string="Potentiel commercial",
    )

    # ------------------------------------------------------------
    # Section 7 — Équipe
    # ------------------------------------------------------------

    team_member_ids = fields.One2many(
        'opex.innovation.team.member', 'project_id', string="Équipe")

    # ------------------------------------------------------------
    # Section 8 — Besoins (la plus importante pour le matching)
    # ------------------------------------------------------------

    besoin_competence_ids = fields.Many2many(
        'opex.innovation.competence',
        'project_besoin_competence_rel', 'project_id', 'competence_id',
        string="Besoins en compétences",
    )
    besoin_accompagnement_ids = fields.Many2many(
        'opex.innovation.competence',
        'project_besoin_accompagnement_rel', 'project_id', 'competence_id',
        string="Besoins d'accompagnement",
    )
    besoin_financement = fields.Boolean(string="Besoin de financement")
    currency_id = fields.Many2one(
        'res.currency', string="Devise",
        default=lambda self: self.env.company.currency_id)
    montant_recherche = fields.Monetary(
        string="Montant recherché", currency_field='currency_id')
    type_financement = fields.Char(string="Type de financement")
    utilisation_prevue = fields.Text(string="Utilisation prévue")

    # ------------------------------------------------------------
    # Section 9 — Pièces jointes
    # ------------------------------------------------------------

    # Nommés `document_ids` / `document_type` : ce sont les conventions que
    # `has_document()` du moteur reconnaît. Une condition de transition peut
    # donc s'écrire `has_document('pitch_deck')` sans une ligne de Python.
    document_ids = fields.One2many(
        'opex.innovation.document', 'project_id', string="Pièces jointes")
    document_count = fields.Integer(
        string="Pièces", compute='_compute_document_count')

    # ------------------------------------------------------------
    # Les deux champs convenus avec l'implémentation « texto »
    # ------------------------------------------------------------

    evaluation_ids = fields.One2many(
        'opex.innovation.evaluation', 'project_id', string="Évaluations")
    score = fields.Integer(
        string="Score",
        compute='_compute_score',
        store=True,
        tracking=True,
        help="Moyenne des évaluations soumises, sur 100. Nom convenu avec "
             "l'implémentation « texto » : c'est lui que lit la condition "
             "field('score') >= 70 du test d'acceptation.",
    )
    ceo_approval = fields.Boolean(
        string="Accord CEO",
        tracking=True,
        help="Nom convenu avec l'implémentation « texto ». Lu par les "
             "conditions de transition, jamais par du code métier.",
    )

    # ------------------------------------------------------------
    # Lien optionnel vers la gestion de projet native
    # ------------------------------------------------------------

    # Motif du dernier retour au porteur — complément demandé ou remédiation.
    # Recopié depuis le commentaire de la transition pour que le porteur le
    # lise en évidence sur son écran, sans avoir à parcourir l'historique.
    # L'historique reste la source de vérité ; ceci en est le raccourci.
    motif_complement = fields.Text(string="Correction demandée", readonly=True)

    project_id = fields.Many2one(
        'project.project',
        string="Projet de suivi",
        ondelete='set null',
        copy=False,
        help="Créé au démarrage de l'accompagnement (Extension 16), quand le "
             "dossier devient un vrai projet à piloter. Optionnel : le "
             "parcours d'innovation n'en dépend pas.",
    )

    @api.depends('document_ids')
    def _compute_document_count(self):
        for project in self:
            project.document_count = len(project.document_ids)

    @api.depends('evaluation_ids.score_total', 'evaluation_ids.state')
    def _compute_score(self):
        """Moyenne des évaluations **soumises**.

        Les évaluations en cours ne comptent pas : un avis à moitié rempli
        ferait chuter la moyenne et pourrait bloquer une transition
        conditionnée au score, sans que personne comprenne pourquoi.
        """
        for project in self:
            submitted = project.evaluation_ids.filtered(
                lambda e: e.state == 'submitted')
            project.score = round(
                sum(submitted.mapped('score_total')) / len(submitted)
            ) if submitted else 0

    # ------------------------------------------------------------
    # Création
    # ------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """Le porteur ne dépose que pour lui-même, et le workflow démarre.

        Même verrou que sur `opex.membership.file` du Module 1 : `partner_id`
        est réécrit côté serveur pour un utilisateur portail, quelle que soit la
        valeur reçue du navigateur.
        """
        if self.env.user._is_portal():
            partner_id = self.env.user.partner_id.id
            for vals in vals_list:
                vals['partner_id'] = partner_id

        projects = super().create(vals_list)
        porteur_role = self.env.ref(
            'opex_workflow.role_porteur', raise_if_not_found=False)
        for project in projects:
            project.start_workflow(PROJECT_WORKFLOW_CODE)
            # Le déposant devient acteur de son dossier : sans cette ligne, les
            # ir.rule du moteur lui refuseraient l'accès à son propre projet.
            user = project.partner_id.user_ids[:1]
            if porteur_role and user:
                project.workflow_instance_id.add_actor(
                    porteur_role, user, 'full')
            if project.partner_id:
                project.sudo().message_subscribe(
                    partner_ids=project.partner_id.ids)
        return projects

    # ------------------------------------------------------------
    # Section 20 — Notification de matching, à information limitée
    # ------------------------------------------------------------

    def propose_to_candidate(self, candidate):
        """Ouvre au candidat retenu l'accès à ce qui le concerne.

        ⚠ `access_level = 'limited'`, jamais `full`. « Il voit Projet, Secteur,
        Résumé, Besoin, Rôle proposé, Durée estimée — **mais seulement les
        informations auxquelles il a droit**. »

        Appelée par la décision du responsable, pas par le matching : c'est le
        geste humain qui déclenche la proposition. Un score ne notifie personne.
        """
        self.ensure_one()
        role_by_type = {
            'expert': 'opex_workflow.role_expert',
            'mentor': 'opex_workflow.role_expert',
            'investisseur': 'opex_workflow.role_investisseur',
            'sponsor': 'opex_workflow.role_investisseur',
        }
        role = self.env.ref(
            role_by_type.get(candidate.candidate_type, 'opex_workflow.role_expert'),
            raise_if_not_found=False)
        user = candidate.partner_id.user_ids[:1]
        if role and user and self.workflow_instance_id:
            self.workflow_instance_id.add_actor(role, user, 'limited')

        # Le message de la section 20, adressé à l'intéressé — donc en
        # `mt_comment` : c'est ce qu'il doit réellement recevoir.
        self.sudo().message_post(
            body=_("Une opportunité d'accompagnement vous a été proposée."),
            partner_ids=candidate.partner_id.ids,
            subtype_xmlid='mail.mt_comment',
        )
        return True

    @api.model
    def _matching_teaser(self, candidate):
        """Ce que le candidat voit — **une liste fermée**, pas le dossier.

        ⚠ Un dictionnaire et non le recordset du projet. Passer le projet au
        gabarit lui donnerait accès à tous ses champs : budget, évaluations,
        historique, coordonnées du porteur. La liste ci-dessous est exactement
        celle de la section 20, et rien d'autre ne peut être rendu par
        inadvertance.
        """
        project = candidate.instance_id._get_record()
        if not project or project._name != 'opex.innovation.project':
            return {'candidate': candidate}

        project = project.sudo()
        labels = dict(project._fields['secteur'].selection)
        besoins = ", ".join(
            project.besoin_accompagnement_ids.mapped('name')
        ) or ", ".join(project.besoin_competence_ids.mapped('name'))
        role_labels = dict(
            candidate._fields['candidate_type'].selection)

        return {
            'candidate': candidate,
            'projet': project.name,
            'secteur': labels.get(project.secteur, ''),
            'resume': project.resume or '',
            'besoin': besoins or _("Non précisé"),
            'role': role_labels.get(candidate.candidate_type, ''),
            'duree': _("À convenir avec le cluster"),
            'score': candidate.score,
        }

    # ------------------------------------------------------------
    # Section 18 — Remédiation et historique des versions
    # ------------------------------------------------------------

    remediation_ids = fields.One2many(
        'opex.innovation.remediation', 'project_id', string="Remédiations")
    version_ids = fields.One2many(
        'opex.innovation.project.version', 'project_id',
        string="Versions du dossier")
    current_version = fields.Integer(
        string="Version courante",
        default=1,
        readonly=True,
        help="Incrémentée à chaque resoumission. La version précédente reste "
             "consultable dans l'onglet Versions.",
    )
    pending_remediation_id = fields.Many2one(
        'opex.innovation.remediation',
        string="Remédiation en cours",
        compute='_compute_pending_remediation',
    )

    @api.depends('remediation_ids.resolved')
    def _compute_pending_remediation(self):
        for project in self:
            project.pending_remediation_id = project.remediation_ids.filtered(
                lambda r: not r.resolved)[:1]

    def request_remediation(self, point_ids, commentaire=False):
        """Enregistre ce que le comité demande de corriger.

        Appelée au moment d'ajourner. La contrainte « au moins un point » vit
        sur le modèle : cette méthode n'a pas besoin de la répéter, et ne doit
        pas — deux formulations de la même règle finiraient par diverger.
        """
        self.ensure_one()
        return self.env['opex.innovation.remediation'].sudo().create({
            'project_id': self.id,
            'point_ids': [fields.Command.set(list(point_ids))],
            'commentaire_comite': commentaire or False,
            'version': self.current_version,
        })

    def snapshot_version(self, remediation=None, reponse=False):
        """Fige le dossier tel qu'il est, puis passe à la version suivante.

        Appelée à la resoumission. L'ordre compte : on archive **l'état
        d'avant**, puis on incrémente. Archiver après incrémentation
        enregistrerait la version suivante sous le numéro de la précédente.
        """
        self.ensure_one()
        labels = dict(self._fields['maturite'].selection)
        documents = "\n".join(
            "- %s : %s" % (
                dict(document._fields['document_type'].selection).get(
                    document.document_type, ''),
                document.name,
            )
            for document in self.document_ids
        )

        snapshot = self.env['opex.innovation.project.version'].sudo().create({
            'project_id': self.id,
            'version': self.current_version,
            'remediation_id': remediation.id if remediation else False,
            'name': self.name,
            'resume': self.resume,
            'probleme': self.probleme,
            'solution': self.solution,
            'marche_cible': self.marche_cible,
            'besoin_marche': self.besoin_marche,
            'concurrence': self.concurrence,
            'proposition_valeur': self.proposition_valeur,
            'modele_economique': self.modele_economique,
            'maturite': labels.get(self.maturite, ''),
            'score': self.score,
            'document_summary': documents or _("Aucune pièce jointe."),
            'reponse_porteur': reponse or False,
        })
        self.sudo().current_version = self.current_version + 1

        if remediation:
            remediation.sudo().write({'reponse_porteur': reponse or False})
            remediation.sudo().action_resolve()
        return snapshot

    # ------------------------------------------------------------
    # Section 15 — Désignation des évaluateurs
    # ------------------------------------------------------------

    def designate_evaluator(self, partner):
        """Fait de ce contact un évaluateur **de ce projet-là**.

        ⚠ Deux choses en une, et elles sont indissociables :

        1. une ligne `opex.innovation.evaluation` — l'avis à rendre ;
        2. une ligne `opex.workflow.instance.actor` portant le rôle
           `evaluateur` — l'accès au dossier.

        Sans la seconde, l'évaluateur ne verrait même pas le projet sur lequel
        on lui demande un avis. C'est exactement le principe des droits
        dynamiques : être expert du vivier n'ouvre aucun dossier, c'est la
        désignation qui ouvre celui-ci.
        """
        self.ensure_one()
        if not partner:
            raise UserError(_("Choisissez un évaluateur à solliciter."))

        Evaluation = self.env['opex.innovation.evaluation'].sudo()
        existing = Evaluation.search([
            ('project_id', '=', self.id),
            ('evaluator_id', '=', partner.id),
        ], limit=1)
        if existing:
            raise UserError(_(
                "%s est déjà sollicité sur ce projet.") % partner.display_name)

        evaluation = Evaluation.create({
            'project_id': self.id,
            'evaluator_id': partner.id,
        })

        role = self.env.ref(EVALUATOR_ROLE, raise_if_not_found=False)
        user = partner.user_ids[:1]
        if role and user and self.workflow_instance_id:
            # `limited` et non `full` : l'évaluateur accède au périmètre de sa
            # mission, pas au dossier entier (section 32).
            self.workflow_instance_id.add_actor(role, user, 'limited')
        return evaluation

    def revoke_evaluator(self, partner):
        """Retire la sollicitation, et l'accès avec elle.

        L'avis déjà rendu est conservé : il a existé, il reste dans le dossier.
        Seul l'accès est coupé.
        """
        self.ensure_one()
        role = self.env.ref(EVALUATOR_ROLE, raise_if_not_found=False)
        user = partner.user_ids[:1]
        if role and user and self.workflow_instance_id:
            self.workflow_instance_id.remove_actor(role, user)

        pending = self.evaluation_ids.filtered(
            lambda e: e.evaluator_id == partner and e.state != 'submitted')
        pending.sudo().unlink()
        return True

    # ------------------------------------------------------------
    # ⚠ Confidentialité des avis — schéma 7
    # ------------------------------------------------------------

    def _is_committee(self, user):
        """Le comité et le personnel du cluster voient tous les avis.

        C'est leur métier : « le Comité d'évaluation peut consulter les avis
        des évaluateurs lorsqu'ils existent ». La confidentialité protège les
        évaluateurs les uns des autres, pas le comité de son dossier.
        """
        return (
            user.sudo()._has_group('opex_innovation.group_comite_evaluation')
            or user.sudo()._has_group('opex_innovation.group_innovation_manager')
        )

    def visible_evaluations(self, user=None):
        """**LA** fonction de visibilité des avis.

        « Chaque évaluateur travaille indépendamment. Il ne peut pas consulter
        les avis ou les scores des autres évaluateurs **avant la finalisation
        de son propre avis**. »

        Une seule fonction, appelée par la page de l'évaluateur, par celle du
        comité et par les tests. Un second filtre écrit ailleurs finirait par
        diverger — et ici, diverger signifie divulguer.

        ⚠ Cette fonction est **plus stricte que l'`ir.rule`** posée sur le
        modèle, et c'est délibéré. La règle de base autorise la lecture de tout
        avis déjà rendu ; la formulation de la section 15 exige en plus que
        l'évaluateur ait finalisé le sien. La règle est le plancher de la base,
        cette fonction est ce qu'appliquent les écrans.
        """
        self.ensure_one()
        user = user or self.env.user
        evaluations = self.sudo().evaluation_ids

        if self._is_committee(user):
            return evaluations

        mine = evaluations.filtered(
            lambda e: e.evaluator_id == user.partner_id)
        if not mine:
            return evaluations.browse()
        if mine.state != 'submitted':
            # Tant qu'il n'a pas rendu, il ne voit que le sien.
            return mine
        return mine | evaluations.filtered(lambda e: e.state == 'submitted')

    # ------------------------------------------------------------
    # Synthèse de qualification (section 14) — une vue, pas un modèle
    # ------------------------------------------------------------

    def qualification_summary(self):
        """Fiche synthétique du dossier qualifié.

        Un dictionnaire calculé à la demande plutôt qu'un modèle de plus : la
        section 14 décrit un **écran**, pas une entité. Un modèle stocké
        divergerait du projet dès la première modification.
        """
        self.ensure_one()
        selections = {
            name: dict(self._fields[name].selection)
            for name in ('secteur', 'maturite', 'potentiel_commercial')
        }
        return [
            (_("Secteur"), selections['secteur'].get(self.secteur, '')),
            (_("Maturité"), selections['maturite'].get(self.maturite, '')),
            (_("Potentiel marché"),
             selections['potentiel_commercial'].get(self.potentiel_commercial, '')),
            (_("Besoin financement"), _("Oui") if self.besoin_financement else _("Non")),
            (_("Besoin expertise"),
             ", ".join(self.besoin_competence_ids.mapped('name')) or _("Aucun")),
        ]

    def action_view_documents(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Pièces de %s") % self.name,
            'res_model': 'opex.innovation.document',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }


class InnovationTeamMember(models.Model):
    """Un membre de l'équipe projet — section 7.

    « Cela permettra ensuite au système de mieux comprendre les besoins du
    projet » : c'est pour le matching que ces lignes existent, pas pour
    l'affichage.
    """

    _name = 'opex.innovation.team.member'
    _description = "Membre de l'équipe projet"
    _order = 'project_id, sequence, id'

    project_id = fields.Many2one(
        'opex.innovation.project',
        string="Projet",
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string="Séquence", default=10)
    name = fields.Char(string="Nom", required=True)
    fonction = fields.Char(string="Fonction")
    competence = fields.Char(string="Compétence")
    experience = fields.Text(string="Expérience")
