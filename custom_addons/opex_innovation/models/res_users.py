import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    # Rôles qui instruisent les dossiers d'innovation. La liste vivait dans
    # `InnovationStaffPortal._STAFF_GROUPS`, où seul un controller pouvait la
    # lire : la tuile d'accueil du portail, elle, est un gabarit. Remontée ici
    # pour qu'il n'existe toujours qu'**un** endroit où se pose la question
    # « cet utilisateur est-il habilité à instruire ? » (règle transversale 2)
    # — `_staff_user()` l'appelle désormais au lieu de refaire le test.
    OPEX_INNOVATION_STAFF_GROUPS = (
        'opex_membership.group_secretariat',
        'opex_innovation.group_innovation_manager',
        'opex_innovation.group_comite_evaluation',
    )

    def _is_innovation_staff(self):
        """Cet utilisateur instruit-il les projets d'innovation ?

        `sudo()` sur la lecture des groupes seulement : un porteur portail n'a
        pas le droit de lire `res.groups`, et la question se pose aussi pour
        lui — la réponse est « non ».
        """
        self.ensure_one()
        return any(self.sudo()._has_group(group)
                   for group in self.OPEX_INNOVATION_STAFF_GROUPS)

    @api.model
    def _opex_innovation_enable_inbox(self):
        """Fait basculer le personnel d'innovation sur la cloche native d'Odoo.

        Le portail a une cloche maison (`opex_membership`) parce qu'Odoo
        **interdit en base** le type « inbox » à un compte partagé :
        `CHECK (notification_type = 'email' OR NOT share)`. Cette contrainte ne
        vise que les comptes portail. Le personnel, lui, est interne : la
        cloche native fonctionne pour lui, et c'est elle qu'on réutilise plutôt
        que d'étendre la cloche maison à un second public.

        Sans ce réglage, un compte interne reste en `email` — le défaut d'Odoo
        pour un utilisateur créé par un administrateur. Ses `mail.notification`
        partent alors par courriel et **rien ne s'affiche dans le systray** :
        le personnel ne voit passer aucune des notes qui lui sont adressées.

        `share = False` en garde dure. Écrire `inbox` sur un compte portail
        violerait la contrainte et ferait échouer la mise à jour du module.

        Ne touche que les comptes **déjà en `email`** : un compte qu'un
        administrateur aurait délibérément remis en `email` est réécrit au
        prochain `-u`. C'est le prix d'un réglage porté par les données ; il
        est assumé, et c'est pour cela que la méthode journalise ce qu'elle
        change.

        Appelée par un `<function>` hors bloc `noupdate`, donc rejouée à chaque
        mise à jour : un membre du personnel ajouté après l'installation est
        réglé au déploiement suivant.
        """
        internes = self.sudo().search([
            ('share', '=', False),
            ('notification_type', '=', 'email'),
        ])
        concernes = internes.filtered(lambda u: u._is_innovation_staff())
        if concernes:
            concernes.write({'notification_type': 'inbox'})
            _logger.info(
                "opex_innovation: cloche native activée pour %s compte(s) : %s",
                len(concernes), ", ".join(concernes.mapped('login')))
        return len(concernes)
