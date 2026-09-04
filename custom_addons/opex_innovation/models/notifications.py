from odoo import api, models


class ProjectNotifications(models.Model):
    """Section 30 — les déclencheurs qui ne sont pas des transitions.

    Onze des quatorze notifications sont des actions `notify` portées par une
    transition : elles ne demandent aucune ligne de Python, et c'est le cas
    normal. Trois ne le sont pas, parce que l'événement qui les déclenche n'est
    pas un passage d'étape :

    - 9. « Expert intéressé » : la réponse d'un candidat à une proposition. Le
      dossier ne bouge pas — « l'IA recommande, elle ne décide pas », et une
      réponse de candidat n'engage rien.
    - 13. « Évolution du financement » : l'écriture d'un montant.
    - 10. 11. 12. : les trois livrables, qui attendent l'Extension 16.

    Pour celles-là, le Python dit **quand**, jamais **quoi ni à qui**. Le
    message, le sous-type et les destinataires restent dans
    `data/notifications.xml`, avec les onze autres. La règle de la section 30
    est tenue : pour savoir pourquoi un message part, on lit un seul fichier.
    """

    _inherit = 'opex.innovation.project'

    def notify_event(self, action_code):
        """Déclenche une notification **configurée**, hors transition.

        Ne construit aucun message. Elle nomme une action et laisse le moteur
        faire — le même `_execute_notify` que pour les transitions, donc les
        mêmes règles de sous-type et la même résolution des destinataires par
        `instance.actor`.

        Le moteur le permettait déjà : `execute(instance, transition=None)`
        porte cette valeur par défaut depuis l'Extension 4, et `_execute_notify`
        n'utilise pas son argument `transition`. Aucune ligne n'a été ajoutée à
        `opex_workflow` pour cette extension.

        Silencieuse si l'action ou l'instance manquent : une notification est un
        effet de bord, elle ne doit pas faire échouer l'opération qui l'a
        déclenchée. C'est le même parti que la règle de l'Extension 4 — une
        action qui échoue est journalisée, elle n'annule pas la transition.
        """
        self.ensure_one()
        instance = self.workflow_instance_id
        if not instance:
            return False
        action = self.env['opex.workflow.action'].sudo().search(
            [('code', '=', action_code)], limit=1)
        if not action:
            return False
        return action.execute(instance)

    # ------------------------------------------------------------
    # 13. Évolution du financement
    # ------------------------------------------------------------

    def write(self, vals):
        """Prévient le porteur quand le montant obtenu change réellement.

        Sur le **changement de valeur**, pas sur la présence de la clé. Un
        écran qui renvoie tous ses champs à chaque enregistrement écrit
        `financement_obtenu` même sans y toucher : notifier sur la clé enverrait
        un courriel au porteur à chaque sauvegarde du dossier par le cluster.

        Les anciennes valeurs sont relevées **avant** `super()` : après, le
        champ porte déjà la nouvelle.
        """
        if 'financement_obtenu' not in vals:
            return super().write(vals)

        avant = {project.id: project.financement_obtenu for project in self}
        result = super().write(vals)
        for project in self:
            if project.financement_obtenu != avant.get(project.id):
                project.notify_event('innovation_notify_evolution_financement')
        return result

    # ------------------------------------------------------------
    # Section 31 — Historique / traçabilité
    # ------------------------------------------------------------

    def history_entries(self, user=None):
        """L'historique du dossier, préparé **par le modèle**.

        Section 31 : « Chaque projet doit avoir un historique : date / heure,
        événement. » Il n'y a rien à recoder — `opex.workflow.history` est le
        journal d'audit du moteur depuis l'Extension 2, immuable, y compris
        pour l'administrateur.

        Reste à l'afficher. `opex.innovation.project` n'hérite pas de
        `portal.mixin`, donc le chatter natif ne s'affiche pas au portail :
        même situation que sur le Module 1, et même réponse — un bloc QWeb en
        lecture seule, alimenté par une liste de dictionnaires.

        **Des dictionnaires, pas le recordset**, et c'est le point du motif
        repris au Module 1 : c'est le modèle qui décide ce que chaque public a
        le droit de lire, pas le gabarit. Passer `history_ids` à la page
        donnerait accès à l'instance, à ses acteurs et, de fil en aiguille, au
        dossier entier.

        Le porteur lit le **libellé utilisateur** de l'étape, jamais son code
        technique : « Évaluation en cours », pas `evaluation`.
        """
        self.ensure_one()
        instance = self.workflow_instance_id
        if not instance:
            return []

        user = user or self.env.user
        interne = self._is_committee(user) or user.sudo()._has_group(
            'opex_innovation.group_innovation_manager')

        entries = []
        for line in instance.sudo().history_ids.sorted('id'):
            stage = line.to_stage_id
            entries.append({
                'date': line.date,
                'body': stage.user_label or stage.name or '',
                'code': stage.code if interne else '',
                'author': line.user_id.partner_id.display_name or '',
                'comment': line.comment or '',
            })
        return entries

    # ------------------------------------------------------------
    # L'inventaire, pour la recette et pour les tests
    # ------------------------------------------------------------

    #: Les quatorze codes de la section 30, dans l'ordre du document. Écrits
    #: ici plutôt que déduits de la base : un inventaire qui se relit lui-même
    #: ne vérifie rien.
    NOTIFICATION_CODES = [
        'innovation_notify_projet_soumis',
        'innovation_notify_complement_demande',
        'innovation_notify_projet_qualifie',
        'innovation_notify_projet_evalue',
        'innovation_notify_decision_comite',
        'innovation_notify_remediation_demandee',
        'innovation_notify_projet_accepte',
        'innovation_notify_matching_propose',
        'innovation_notify_expert_interesse',
        'innovation_notify_nouveau_livrable',
        'innovation_notify_livrable_valide',
        'innovation_notify_correction_demandee',
        'innovation_notify_evolution_financement',
        'innovation_notify_projet_cloture',
    ]

    @api.model
    def notification_inventory(self):
        """Où en est chacune des quatorze notifications.

        Sert à la recette autant qu'aux tests : elle dit lesquelles sont
        rattachées à une transition, lesquelles sont déclenchées depuis le code,
        et lesquelles n'ont encore rien derrière elles.
        """
        Action = self.env['opex.workflow.action'].sudo()
        Transition = self.env['opex.workflow.transition'].sudo()

        # Déclenchées par `notify_event()` plutôt que par une transition, et
        # pourquoi. Table plutôt que trois `if` disséminés.
        hors_transition = {
            'innovation_notify_expert_interesse':
                "Réponse d'un candidat — le dossier ne change pas d'étape.",
            'innovation_notify_evolution_financement':
                "Écriture d'un montant — ce n'est pas un passage d'étape.",
        }

        inventaire = []
        for code in self.NOTIFICATION_CODES:
            action = Action.search([('code', '=', code)], limit=1)
            transitions = Transition.search([('action_ids', 'in', action.ids)]) \
                if action else Transition.browse()
            inventaire.append({
                'code': code,
                'exists': bool(action),
                'name': action.name if action else '',
                'subtype': action.notify_subtype if action else '',
                'roles': action.target_role_ids.mapped('name') if action else [],
                'transitions': transitions.mapped('code'),
                'hors_transition': hors_transition.get(code, ''),
                'orpheline': bool(action) and not transitions
                             and code not in hors_transition,
            })
        return inventaire
