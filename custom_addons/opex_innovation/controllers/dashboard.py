from odoo import fields, http
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal

from .project_portal import InnovationProjectPortal
from .staff_portal import InnovationStaffPortal


class InnovationPortalCounters(CustomerPortal):
    """⚠ Les compteurs qui **rendent les tuiles visibles**.

    Piège déjà payé sur le Module 1, et retrouvé intact ici sur les quatre
    tuiles du Module 2 : `portal.portal_docs_entry` ajoute `d-none` à toute
    entrée qui ne fournit ni `placeholder_count` non nul, ni `config_card`.

        <t t-set="force_show" t-value="placeholder_count and
            request.session.get('portal_counters', {}).get(placeholder_count)
            and not show_count"/>
        <div t-att-class="'o_portal_index_card ' +
            ('' if force_show or config_card else 'd-none ') + ...">

    Une tuile qui ne déclare qu'un titre, une URL et un texte est donc rendue
    dans le HTML — et **jamais affichée**. Un test qui vérifie
    `'Mes projets' in response.text` passe au vert sur une page où l'utilisateur
    ne voit rien. C'est le mode de défaillance le plus coûteux du portail, parce
    qu'il ne laisse aucune trace : ni erreur, ni test rouge.

    Le remplissage se fait en deux temps : la page pose des marqueurs, puis un
    appel `/my/counters` en arrière-plan renseigne
    `request.session['portal_counters']`, ce qui démasque les tuiles utiles.
    C'est `_prepare_home_portal_values()` qui répond à cet appel.
    """

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id

        if 'innovation_project_count' in counters:
            Project = request.env['opex.innovation.project']
            values['innovation_project_count'] = (
                Project.search_count([('partner_id', '=', partner.id)])
                if Project.has_access('read') else 0
            )

        if 'innovation_opportunity_count' in counters:
            Candidate = request.env['opex.matching.candidate'].sudo()
            proposals = Candidate.search([
                ('partner_id', '=', partner.id),
                ('state', '=', 'accepted'),
            ])
            # Même second filtre que l'espace investisseur : la visibilité se
            # tranche sur `instance.actor`, pas sur la table des candidats.
            values['innovation_opportunity_count'] = len(proposals.filtered(
                lambda c: c.instance_id
                and c.instance_id._has_access(request.env.user)))

        if 'innovation_evaluation_count' in counters:
            Evaluation = request.env['opex.innovation.evaluation'].sudo()
            values['innovation_evaluation_count'] = Evaluation.search_count([
                ('evaluator_id', '=', partner.id),
                ('state', '!=', 'submitted'),
            ])

        return values


class InnovationHolderDashboard(InnovationProjectPortal):
    """Section 35 — le tableau de bord du porteur.

    Étend la route existante plutôt que d'en ouvrir une seconde : le cahier des
    charges dit « dashboard porteur sur `/my/innovation` », et c'est déjà
    l'adresse de la liste des projets. Deux pages auraient obligé le porteur à
    choisir laquelle regarder.
    """

    @http.route(['/my/innovation'], type='http', auth='user', website=True)
    def portal_my_projects(self, **kw):
        response = super().portal_my_projects(**kw)
        # `qcontext` plutôt qu'un second `render()` : on enrichit la page que le
        # contrôleur parent a préparée, on ne la reconstruit pas. Recopier son
        # corps ici ferait diverger les deux au premier changement.
        if getattr(response, 'qcontext', None) is None:
            return response

        projects = response.qcontext.get(
            'projects', request.env['opex.innovation.project'].browse())
        response.qcontext.update({
            'cards': [self._project_card(project) for project in projects],
            'dashboard': self._holder_summary(projects),
        })
        return response

    def _project_card(self, project):
        """La carte « MON PROJET », préparée par le contrôleur.

        ⚠ Le projet **est** passé au gabarit ici, contrairement aux vignettes
        de l'espace investisseur — et c'est légitime : c'est son propre
        dossier, il en est le porteur. La liste fermée protège d'un tiers, pas
        de soi-même.

        Ce qui est préparé, ce sont les jalons et la phrase d'état, parce que
        les calculer dans le gabarit y ferait entrer la logique de progression.
        """
        actions = []
        instance = project.workflow_instance_id
        if instance and instance.state == 'running':
            actions = [
                option for option in instance.transition_options()
                if option['available']
            ]
        return {
            'project': project,
            'milestones': project.milestones(),
            'message': project.milestone_message(),
            'actions': actions,
        }

    def _holder_summary(self, projects):
        """Les trois chiffres en tête de page."""
        running = projects.filtered(
            lambda p: p.workflow_state == 'running')
        return {
            'total': len(projects),
            'en_cours': len(running),
            'action_requise': len(running.filtered(
                lambda p: p.workflow_stage_id.code in (
                    'draft', 'complement_requested', 'remediation'))),
        }


class InnovationExpertDashboard(CustomerPortal):
    """« Dashboard expert : mes missions, mes livrables »."""

    @http.route(['/my/innovation/missions'], type='http', auth='user',
                website=True)
    def portal_missions(self, **kw):
        partner = request.env.user.partner_id
        Candidate = request.env['opex.matching.candidate'].sudo()

        proposals = Candidate.search([
            ('partner_id', '=', partner.id),
            ('candidate_type', 'in', ('expert', 'mentor')),
            ('state', '=', 'accepted'),
        ], order='score desc')
        # ⚠ Le filtre de visibilité est le même partout : `instance.actor`,
        # tranché par la seule fonction du moteur qui en décide. Une route qui
        # referait sa propre requête finirait par oublier une condition.
        proposals = proposals.filtered(
            lambda c: c.instance_id
            and c.instance_id._has_access(request.env.user))

        Evaluation = request.env['opex.innovation.evaluation'].sudo()
        evaluations = Evaluation.search([('evaluator_id', '=', partner.id)])

        # ✅ « Mes livrables » — couture refermée par l'Extension 16.
        #
        # ⚠ Le filtre passe par `instance.actor`, comme partout : être expert du
        # cluster ne donne accès à aucun livrable ; c'est la désignation sur
        # CE livrable-là qui ouvre la porte. `_has_access()` est la seule
        # fonction qui en décide.
        Deliverable = request.env['opex.innovation.deliverable'].sudo()
        livrables = Deliverable.search([
            ('workflow_stage_id.code', 'in', ('submitted', 'correction_requested')),
        ]).filtered(
            lambda d: d.workflow_instance_id
            and d.workflow_instance_id._has_access(request.env.user))

        Project = request.env['opex.innovation.project'].sudo()
        return request.render('opex_innovation.portal_missions', {
            'missions': [Project._matching_teaser(c) for c in proposals],
            'a_rendre': evaluations.filtered(lambda e: e.state != 'submitted'),
            'rendues': evaluations.filtered(lambda e: e.state == 'submitted'),
            'a_verifier': livrables.filtered(
                lambda d: d.workflow_stage_id.code == 'submitted'),
            'en_correction': livrables.filtered(
                lambda d: d.workflow_stage_id.code == 'correction_requested'),
            'page_name': 'innovation_missions',
        })


class InnovationStaffDashboard(InnovationStaffPortal):
    """« Dashboard gestionnaire : projets par étape, délais, alertes ».

    Hérite du contrôleur staff pour réutiliser `_staff_user()` et
    `_staff_projects()` : le contrôle d'accès reste une seule fonction, et le
    périmètre affiché est exactement celui de la file de travail. Un tableau de
    bord qui compterait plus large que ce que l'utilisateur peut ouvrir serait
    une fuite par les chiffres.
    """

    @http.route(['/staff/innovation/dashboard'], type='http', auth='user',
                website=True)
    def staff_dashboard(self, **kw):
        if not self._staff_user():
            return request.redirect('/my')

        projects = self._staff_projects()
        instances = projects.mapped('workflow_instance_id')
        now = fields.Datetime.now()

        return request.render('opex_innovation.staff_dashboard', {
            'projects': projects,
            'par_etape': self._by_stage(projects),
            'delais': self._delays(instances, now),
            'alertes': self._alerts(projects, instances, now),
            'page_name': 'staff_dashboard',
        })

    def _by_stage(self, projects):
        """Projets par étape, dans l'ordre du workflow.

        ⚠ `mapped()` sert ici à obtenir la **liste des étapes distinctes** —
        c'est exactement ce qu'il fait, et c'est ce qu'on veut. Le comptage,
        lui, se fait à part : `len(projects.mapped('workflow_stage_id'))`
        aurait donné le nombre d'étapes occupées, pas le nombre de projets.
        Les deux questions se ressemblent et n'ont pas la même réponse.
        """
        stages = projects.mapped('workflow_stage_id').sorted('sequence')

        counts = {}
        for project in projects:
            stage = project.workflow_stage_id
            if stage:
                counts[stage.id] = counts.get(stage.id, 0) + 1

        return [
            {
                'stage': stage,
                'label': stage.name,
                'code': stage.code,
                'count': counts.get(stage.id, 0),
            }
            for stage in stages
        ]

    def _delays(self, instances, now):
        """Le temps passé à l'étape courante, et l'échéance quand il y en a une."""
        rows = []
        for instance in instances.sorted(
                lambda i: i.sla_deadline or fields.Datetime.now()):
            if not instance.date_stage_start:
                continue
            rows.append({
                'instance': instance,
                'jours': (now - instance.date_stage_start).days,
                'echeance': instance.sla_deadline,
                'en_retard': instance.is_late,
            })
        return rows

    def _alerts(self, projects, instances, now):
        """Ce qui demande une intervention, du plus urgent au moins urgent.

        Trois familles, et aucune n'est un compteur : chaque alerte pointe un
        dossier précis. Un tableau de bord qui dirait « 3 anomalies » sans dire
        lesquelles obligerait à les chercher à la main.
        """
        alertes = []

        for instance in instances.filtered('is_late'):
            record = instance._get_record()
            alertes.append({
                'niveau': 'danger',
                'titre': "Délai dépassé",
                'detail': "%s — à l'étape « %s » depuis %s jours." % (
                    record.display_name if record else '',
                    instance.current_stage_id.name,
                    (now - instance.date_stage_start).days
                    if instance.date_stage_start else '?'),
                'url': '/staff/innovation/%s' % (record.id if record else ''),
            })

        # Un projet évalué mais dont aucun avis n'est rendu : le comité ne peut
        # pas décider, et rien ne le signale ailleurs.
        for project in projects.filtered(
                lambda p: p.workflow_stage_id.code == 'evaluation'):
            rendues = project.evaluation_ids.filtered(
                lambda e: e.state == 'submitted')
            if not rendues:
                alertes.append({
                    'niveau': 'warning',
                    'titre': "Évaluation sans avis rendu",
                    'detail': "%s — %s évaluateur(s) désigné(s), aucun avis "
                              "finalisé." % (project.display_name,
                                             len(project.evaluation_ids)),
                    'url': '/staff/innovation/%s' % project.id,
                })

        # Un projet accepté qui cherche un financement sans qu'aucun acteur
        # financier n'ait été proposé.
        for project in projects.filtered(
                lambda p: p.besoin_financement
                and p.workflow_stage_id.code in ('matching', 'financement')):
            candidats = request.env['opex.matching.candidate'].sudo().search_count([
                ('instance_id', '=', project.workflow_instance_id.id),
                ('candidate_type', 'in', ('investisseur', 'sponsor')),
            ])
            if not candidats:
                alertes.append({
                    'niveau': 'info',
                    'titre': "Financement sans candidat",
                    'detail': "%s — aucun acteur financier proposé." %
                              project.display_name,
                    'url': '/staff/innovation/%s/matching' % project.id,
                })

        return alertes
