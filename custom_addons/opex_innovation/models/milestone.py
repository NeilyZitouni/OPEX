from odoo import api, fields, models


class InnovationMilestone(models.Model):
    """Section 35 — les jalons que le porteur lit, pas les étapes qu'il traverse.

    > « Son portail ne doit pas lui montrer toute la complexité interne. »

    Le workflow d'un projet compte **quinze** étapes. La carte de la section 35
    en montre **sept**. Ce modèle porte la correspondance entre les deux.

    ⚠ C'est une **donnée**, pas une table en dur dans un gabarit. Trois raisons,
    dans l'ordre d'importance :

    1. Ajouter une étape technique — le Demo Day du critère d'acceptation, par
       exemple — ne doit pas obliger à rouvrir un fichier Python pour décider
       sous quel jalon elle se range. On la coche dans le jalon voulu.
    2. Le regroupement dépend du processus. Smart Crowdfunding a ses propres
       étapes et aurait ses propres jalons ; `definition_id` le permet sans
       qu'une ligne de code ne distingue les deux.
    3. Le libellé lu par le porteur est du texte métier. Il se corrige sans
       livraison.

    Le moteur, lui, ignore tout de ces jalons — c'est du vocabulaire métier, et
    il n'a rien à en savoir. `progress_steps()` continue de renvoyer les quinze
    étapes ; ce modèle en fait sept pour un seul public.
    """

    _name = 'opex.innovation.milestone'
    _description = "Jalon lisible par le porteur"
    _order = 'definition_id, sequence, id'

    definition_id = fields.Many2one(
        'opex.workflow.definition',
        string="Workflow",
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(
        string="Libellé",
        required=True,
        translate=True,
        help="Ce que le porteur lit. Jamais un code technique.",
    )
    code = fields.Char(string="Code", required=True, index=True)
    sequence = fields.Integer(string="Séquence", default=10)

    stage_ids = fields.Many2many(
        'opex.workflow.stage',
        'opex_milestone_stage_rel', 'milestone_id', 'stage_id',
        string="Étapes couvertes",
        help="Les étapes techniques que ce jalon résume. Une étape non "
             "rattachée n'apparaît nulle part sur la carte du porteur — ce qui "
             "est le comportement voulu pour les étapes purement internes.",
    )
    message = fields.Char(
        string="Phrase d'état",
        translate=True,
        help="Affichée sur la carte quand le dossier est à ce jalon. "
             "Exemple : « Votre projet est actuellement évalué. »",
    )

    _code_uniq = models.Constraint(
        'unique(definition_id, code)',
        "Deux jalons du même workflow ne peuvent pas porter le même code.",
    )

    @api.depends('name', 'definition_id.name')
    def _compute_display_name(self):
        for milestone in self:
            milestone.display_name = "%s / %s" % (
                milestone.definition_id.name or '', milestone.name or '')


class ProjectMilestones(models.Model):
    """La carte « MON PROJET » de la section 35."""

    _inherit = 'opex.innovation.project'

    def milestones(self):
        """Les sept jalons, chacun franchi, en cours ou à venir.

        Trois règles, dans cet ordre :

        - le jalon qui contient l'étape courante est **en cours** ;
        - tout jalon qui le précède est **franchi**, même si le dossier n'a
          traversé aucune de ses étapes. C'est délibéré : le comité peut
          évaluer directement sans passer par les experts, et afficher
          « Évaluation » comme à venir à un porteur déjà accepté serait
          incompréhensible. Le porteur lit une progression, pas un journal —
          l'historique exact reste consultable en dessous ;
        - un jalon dont une étape figure dans l'historique est franchi lui
          aussi, ce qui rattrape les retours en arrière.

        ⚠ Un dossier clos ou refusé n'a plus de jalon « en cours ». Sans cette
        dernière règle, un projet refusé afficherait « Décision » comme étape
        en cours pour toujours.
        """
        self.ensure_one()
        instance = self.workflow_instance_id
        if not instance:
            return []

        Milestone = self.env['opex.innovation.milestone'].sudo()
        milestones = Milestone.search(
            [('definition_id', '=', instance.definition_id.id)])
        if not milestones:
            return []

        # ⚠ Les étapes visitées se lisent en compréhension sur l'historique.
        # Ici l'ensemble suffit — on ne compte pas les passages, on demande
        # seulement s'il y en a eu un.
        visited = {
            line.to_stage_id.id
            for line in instance.sudo().history_ids if line.to_stage_id
        }
        current_stage = instance.current_stage_id
        current = milestones.filtered(
            lambda m: current_stage in m.stage_ids)[:1]

        # ⚠ L'étape courante peut n'appartenir à **aucun** jalon : c'est le cas
        # des allers-retours internes (`complement_requested`, `remediation`,
        # `resubmitted`), volontairement absents de la carte.
        #
        # Sans ce rattrapage, la carte se dérèglerait au pire moment : le jalon
        # « Contrôle terminé », qui était en cours, passerait à franchi parce
        # que son étape figure dans l'historique, et **plus aucun jalon ne
        # serait en cours**. Le porteur à qui l'on vient de demander un
        # complément verrait une carte qui n'indique plus où il en est.
        #
        # On reste donc sur le dernier jalon atteint. Le porteur voit
        # « Contrôle terminé en cours » et l'alerte « Action requise » juste
        # au-dessus : sa carte ne bouge pas, l'action lui est demandée ailleurs.
        if not current:
            atteints = milestones.filtered(
                lambda m: set(m.stage_ids.ids) & visited)
            current = atteints.sorted('sequence')[-1:] if atteints else current

        closed = instance.state != 'running'
        steps = []
        for milestone in milestones:
            if milestone == current:
                state = 'done' if closed else 'current'
            elif current and milestone.sequence < current.sequence:
                state = 'done'
            elif set(milestone.stage_ids.ids) & visited:
                state = 'done'
            else:
                state = 'upcoming'
            steps.append({
                'code': milestone.code,
                'label': milestone.name,
                'state': state,
            })
        return steps

    def milestone_message(self, user=None):
        """La ligne « Dernière action » de la carte.

        La phrase configurée sur le jalon courant, si elle existe. Sinon, celle
        que le moteur sait produire — `next_action_label()` dit à l'utilisateur
        ce qu'on attend de lui plutôt que dans quel état est la machine.

        ⚠ `user` est résolu immédiatement : `_()` devine la langue en
        inspectant les variables locales de l'appelant et fait `int()` sur un
        nom `user`. Un `user=None` laissé tel quel fait planter la traduction.
        """
        self.ensure_one()
        user = user or self.env.user
        instance = self.workflow_instance_id
        if not instance:
            return ""

        if instance.state == 'running':
            # ⚠ Ce qu'on attend de l'utilisateur passe **avant** l'état du
            # dossier. Section 16 : « ne pas demander à l'utilisateur de
            # piloter le workflow, le workflow doit guider l'utilisateur. »
            #
            # Un porteur dont le dossier est incomplet doit lire « il vous
            # manque le résumé », pas « votre projet a bien été enregistré ».
            # Le moteur sait déjà produire cette phrase, y compris le motif du
            # blocage : on ne la réécrit pas ici.
            options = instance.transition_options(user=user)
            if any(option['available'] for option in options):
                return instance.next_action_label(user=user)

            Milestone = self.env['opex.innovation.milestone'].sudo()
            current = Milestone.search([
                ('definition_id', '=', instance.definition_id.id),
                ('stage_ids', 'in', instance.current_stage_id.ids),
            ], limit=1)
            if current.message:
                return current.message
        return instance.next_action_label(user=user)
