"""Les espaces du §18 : Smart Work Queue et espace intervenant.

Les deux autres espaces existaient déjà. Le client a son tableau de bord depuis
l'Extension 2 (`/my/missions`), le candidat externe son suivi depuis
l'Extension 5 (`/my/candidatures`). Cette extension leur ajoute la file
priorisée du §43 et laisse leurs routes où elles sont : les dupliquer aurait
fait deux écrans à tenir d'accord.

Noms de méthodes préfixés, comme partout dans ce module. Deux modules qui
héritent du même arbre `CustomerPortal` et nomment une méthode pareil : Odoo
n'en garde qu'une, sans erreur. La leçon a coûté une route disparue au Module 2.
"""

from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


class MissionDashboardPortal(CustomerPortal):
    """L'espace intervenant du §41, et le compteur qui va avec."""

    def _intervenants_dashboard(self):
        return request.env['opex.mission.dashboard'].sudo()

    @http.route(['/my/intervenant'], type='http', auth='user', website=True)
    def portal_intervenants_espace(self, **kw):
        """§41 - les cinq indicateurs et les actions rapides.

        Tout arrive calculé du modèle. Aucun `search()` en QWeb : une requête
        ORM posée dans un gabarit s'exécute sous l'identité du visiteur et fait
        tomber la page entière en AccessError, pas le bloc fautif.
        """
        partner = request.env.user.partner_id
        space = self._intervenants_dashboard().intervenant_space(partner)
        return request.render('opex_intervenants.portal_espace_intervenant', {
            'space': space,
            'page_name': 'intervenants_espace',
        })

    def _prepare_home_portal_values(self, counters):
        """Le quatrième compteur du module, et une clé neuve.

        Les trois règles des extensions précédentes, sans exception :

        1. `super()` en premier - c'est ce qui fait cohabiter les surcharges
           des quatre modules dans la classe fusionnée ;
        2. `if 'x' in counters` - une clé renvoyée sans nœud DOM correspondant
           fait lever `portal_home_counters.js`, ce qui rejette le
           `Promise.all` et tue tout le JavaScript de l'accueil, pour tous les
           utilisateurs ;
        3. une clé qui n'appartient qu'à une tuile - `querySelector()` ne
           renvoie que le premier nœud, deux tuiles partageant une clé
           laisseraient la seconde masquée.

        Relevé fait avant de choisir le nom : les clés déjà prises sont
        `membership_file_count`, `subscription_count`, les quatre
        `innovation_*`, les trois `crowdfunding_*` et les trois
        `intervenants_mission_count`, `intervenants_candidature_count`,
        `intervenants_expertise_count`.

        Celui-ci compte les missions où le contact intervient - ce que la tuile
        annonce et ce que l'écran contient. Ni les demandes qu'il a déposées
        comme client, ni ses candidatures : elles ont déjà les leurs.
        """
        values = super()._prepare_home_portal_values(counters)
        if 'intervenants_espace_count' in counters:
            Assignment = request.env['opex.mission.assignment']
            values['intervenants_espace_count'] = (
                Assignment.search_count([
                    ('partner_id', '=', request.env.user.partner_id.id),
                    ('active', '=', True),
                ])
                if Assignment.has_access('read') else 0
            )
        return values


class MissionWorkQueue(http.Controller):
    """La Smart Work Queue du responsable - §42, §43, §18.

    `http.Controller` et non `CustomerPortal` : cet écran n'est pas l'espace
    personnel d'un contact, c'est l'outil de travail du cluster. Le distinguer
    évite qu'il hérite des hooks du portail - dont `/my/counters`, qui n'a rien
    à voir avec lui.
    """

    def _queue_staff_user(self):
        """Le contrôle d'accès du staff Missions, et lui seul.

        `res.users._is_missions_staff()` est LA fonction, appelée par les
        routes et par les `t-if` des tuiles. Deux listes de groupes finiraient
        par diverger - la tuile visible pour un rôle que la route refuse.

        Renvoie plutôt que de lever : une route qui lève affiche une page
        d'erreur technique, une route qui redirige garde l'utilisateur dans
        son parcours.
        """
        user = request.env.user
        return user if user._is_missions_staff() else False

    @http.route(['/staff/queue'], type='http', auth='user', website=True)
    def staff_intervenants_queue(self, **kw):
        """Les sept indicateurs du §42 et les trois niveaux du §43."""
        if not self._queue_staff_user():
            return request.redirect('/my')

        queue = request.env['opex.mission.dashboard'].sudo().manager_queue()
        return request.render('opex_intervenants.staff_work_queue', {
            'queue': queue,
            'page_name': 'intervenants_queue',
        })
