"""Ce qu'il a fallu poser pour que les notifications du §34 atteignent quelqu'un.

Une action `notify` résout ses destinataires par `_partners_for_roles()`, qui
lit les acteurs de l'instance visée et écarte ceux dont l'accès vaut `none`
(`workflow_instance.py:895`). Un rôle sans porteur sur le dossier ne notifie
donc personne - sans erreur, sans trace, et sans qu'aucun test de configuration
ne le signale.

Le §34 demande que le client soit prévenu qu'une candidature a été déposée sur
son appel. La candidature n'avait qu'un acteur, l'intervenant. La notification
serait partie dans le vide.
"""

from odoo import api, models

CLIENT_ROLE = 'opex_intervenants.role_client'


class MissionApplicationNotification(models.Model):
    """Le client devient acteur des candidatures déposées sur ses appels."""

    _inherit = 'opex.mission.application'

    @api.model_create_multi
    def create(self, vals_list):
        applications = super().create(vals_list)
        for application in applications:
            application._grant_client_actor()
        return applications

    def _grant_client_actor(self):
        """Rend le client acteur de la candidature, en lecture.

        Ce que cela ouvre, et ce que cela n'ouvre pas.

        Cela ouvre les notifications : le client est désormais un destinataire
        résoluble pour le rôle `client` sur cette instance, ce que le §34
        exige et ce que le §18 confirme - « short-list autorisée » suppose
        qu'il sache qu'il y a des candidatures.

        Cela n'ouvre aucune action : aucune transition du workflow de la
        candidature n'est ouverte au rôle `client`. Vérifié, et un test le
        maintient - le jour où quelqu'un en ouvre une, la conversation a lieu.

        Cela n'ouvre pas non plus la lecture de l'enregistrement. L'`ir.rule`
        du portail borne les candidatures à `partner_id = user.partner_id`, et
        un acteur d'instance ne la lève pas. Le client reçoit la notification,
        il n'ouvre pas le dossier du candidat - ce que le §14 demande.

        L'accès est `limited` et non `full` : `none` serait plus juste sur le
        papier, mais `_partners_for_roles()` écarte précisément ce niveau, et
        la notification ne partirait pas.
        """
        self.ensure_one()
        role = self.env.ref(CLIENT_ROLE, raise_if_not_found=False)
        instance = self.sudo().workflow_instance_id
        client = self.mission_id.sudo().client_id.user_ids[:1]
        if role and instance and client:
            instance.add_actor(role, client, 'limited')
        return True
