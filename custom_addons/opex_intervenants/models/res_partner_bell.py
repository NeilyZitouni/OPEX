"""La cloche du portail voit enfin les missions - §34.

On n'écrit pas un second système de notification. Le Module 1 en a un complet :
il lit les `mail.message` posés sur les enregistrements du contact, écarte les
notes internes par `_get_search_domain_share()`, ajoute ce qui lui a été
adressé nommément, et compare les dates à `notification_last_seen`.

Le seul manque était le périmètre. Les actions `notify` des cinq définitions de
ce module postaient correctement, avec les bons sous-types et les bons
destinataires, et aucune n'atteignait la cloche : leurs modèles n'étaient
déclarés nulle part. C'est exactement le constat qu'`opex_innovation` avait
fait avant nous, et la correction est la même.

Surcharge coopérative : `super()` d'abord, toujours. Une méthode qui ne relaie
pas efface celle des trois modules précédents, sans erreur et sans trace - les
dossiers d'adhésion et les projets d'innovation disparaîtraient de la cloche du
jour où ce module serait installé.
"""

from odoo import models


class ResPartnerBell(models.Model):
    _inherit = 'res.partner'

    def _opex_owned_record_ids(self):
        """Ajoute les enregistrements Missions au périmètre de la cloche.

        Les deux côtés du dossier y figurent, et pas par le même chemin : le
        client par `client_id`, l'intervenant par `partner_id`. Un contact peut
        être les deux, sur des dossiers différents ; les deux recherches se
        cumulent sans se recouvrir.

        Cette table décide de ce que le contact voit dans sa cloche, elle ne
        donne accès à rien. La visibilité réelle reste tranchée en amont par
        `_get_search_domain_share()`, qui écarte les `mt_note` : un message de
        coordination interne n'entrera jamais ici, même sur un dossier listé.
        """
        self.ensure_one()
        owned = super()._opex_owned_record_ids()

        Mission = self.env['opex.mission.request'].sudo()
        missions = Mission.search([('client_id', '=', self.id)])

        # Les missions où le contact intervient : il n'en est pas le client, et
        # il doit pourtant recevoir ce qui s'y passe.
        assignments = self.env['opex.mission.assignment'].sudo().search(
            [('partner_id', '=', self.id)])
        missions |= assignments.mission_id

        owned.update({
            'opex.mission.request': missions.ids,
            'opex.mission.application':
                self.env['opex.mission.application'].sudo().search(
                    [('partner_id', '=', self.id)]).ids,
            'opex.mission.deliverable':
                self.env['opex.mission.deliverable'].sudo().search(
                    ['|', ('partner_id', '=', self.id),
                     ('mission_id.client_id', '=', self.id)]).ids,
            'opex.mission.contract':
                self.env['opex.mission.contract'].sudo().search(
                    ['|', ('partner_id', '=', self.id),
                     ('mission_id.client_id', '=', self.id)]).ids,
            'opex.service.acceptance':
                self.env['opex.service.acceptance'].sudo().search(
                    ['|', ('mission_id.client_id', '=', self.id),
                     ('assignment_ids.partner_id', '=', self.id)]).ids,
            'opex.mission.evaluation':
                self.env['opex.mission.evaluation'].sudo().search(
                    ['|', ('partner_id', '=', self.id),
                     ('mission_id.client_id', '=', self.id)]).ids,
        })
        return owned

    def _opex_notification_url(self, message):
        """Où mène la notification.

        Une notification qu'on ne peut pas ouvrir n'aide personne : chaque
        modèle ajouté au périmètre ci-dessus a sa destination ici.

        Les objets satellites - livrable, contrat, constat, évaluation -
        renvoient vers la mission qui les porte. Ils n'ont pas d'écran portail
        à eux, et le §40 veut de toute façon que tout se lise depuis la fiche
        de la mission. Même parti que le Module 1 pour les cotisations et que
        le Module 2 pour l'industrialisation.

        `super()` en dernier, jamais en premier : la chaîne s'arrête au premier
        module qui reconnaît le modèle, et celui-ci ne reconnaît que les siens.
        """
        self.ensure_one()
        if message.model == 'opex.mission.request':
            return '/my/missions/%s' % message.res_id

        if message.model == 'opex.mission.application':
            return self._application_notification_url(message)

        satellites = {
            'opex.mission.deliverable': 'mission_id',
            'opex.mission.contract': 'mission_id',
            'opex.service.acceptance': 'mission_id',
            'opex.mission.evaluation': 'mission_id',
        }
        if message.model in satellites:
            record = self.env[message.model].sudo().browse(message.res_id)
            mission = record[satellites[message.model]] if record.exists() \
                else False
            if mission:
                return '/my/missions/%s' % mission.id
        return super()._opex_notification_url(message)

    def _application_notification_url(self, message):
        """La candidature ne mène pas au même écran selon qui la lit.

        Défaut trouvé au navigateur, et invisible autrement : le §34 fait
        prévenir le client qu'une candidature a été déposée sur son appel. Le
        message est bien posté sur la candidature, et le lien envoyait donc
        tout le monde vers `/my/candidatures/<id>` - un écran que l'`ir.rule`
        du portail réserve au candidat. Le client cliquait et tombait sur un
        404.

        Le cas est propre à cette extension : jusqu'ici, un message ne
        parvenait qu'au propriétaire de l'enregistrement, et l'URL pouvait
        s'en déduire. La cloche montre désormais aussi ce qui est adressé
        nommément sur le dossier d'un autre - c'est ce qui la rend utile, et
        c'est ce qui oblige à résoudre le lien pour le **lecteur**.

        Le candidat va à sa candidature ; toute autre personne va à la mission,
        qu'elle a le droit de lire si le message la concerne.
        """
        self.ensure_one()
        application = self.env['opex.mission.application'].sudo().browse(
            message.res_id)
        if not application.exists():
            return '/my'
        if application.partner_id == self:
            return '/my/candidatures/%s' % application.id
        return '/my/missions/%s' % application.mission_id.id
