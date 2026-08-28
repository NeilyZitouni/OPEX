import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    # Rôles qui *instruisent* les dossiers : ceux du back-office. Définis une
    # seule fois — la tuile d'accueil du portail et tout écran de traitement à
    # venir s'appuient dessus, et deux listes séparées finiraient par diverger,
    # un rôle ajouté d'un côté et oublié de l'autre (règle transversale 2).
    #
    # L'Expert et l'Acteur financier n'y figurent pas : ils *participent* au
    # dossier depuis le portail — leur mission, leurs opportunités — ils ne
    # l'instruisent pas. Leur appartenance à un dossier se vérifie
    # enregistrement par enregistrement (`_crowdfunding_mission_de_l_expert()`,
    # `_crowdfunding_relation_du_partenaire()`), ce qui est une autre question
    # que celle-ci.
    OPEX_CROWDFUNDING_STAFF_GROUPS = (
        'opex_crowdfunding.group_ceo',
        'opex_crowdfunding.group_quality_control',
    )

    def _is_crowdfunding_staff(self):
        """Cet utilisateur instruit-il les dossiers Smart Crowdfunding ?

        `sudo()` sur la lecture des groupes seulement : un utilisateur portail
        n'a pas le droit de lire `res.groups`, et la question se pose aussi
        pour lui — la réponse est simplement « non ».
        """
        self.ensure_one()
        return any(self.sudo()._has_group(group)
                   for group in self.OPEX_CROWDFUNDING_STAFF_GROUPS)

    @api.model
    def _opex_crowdfunding_enable_inbox(self):
        """Active la cloche native d'Odoo pour le personnel de ce module.

        Un compte interne créé par un administrateur est en
        `notification_type = 'email'` : ses notifications partent par courriel
        et **le systray reste vide**. Les 29 `message_post()` internes de ce
        module n'atteignaient donc personne à l'écran.

        La cloche native suffit ici : la contrainte
        `CHECK (notification_type = 'email' OR NOT share)` d'Odoo ne vise que
        les comptes partagés. D'où la garde `share = False`, sans laquelle un
        compte portail ferait échouer la mise à jour du module.

        ⚠ Méthode propre à ce module, malgré son air de doublon avec celle
        d'`opex_innovation`. La règle d'isolation interdit à ce module
        d'importer quoi que ce soit des autres, et les deux ne parlent pas des
        mêmes groupes. Deux listes de rôles distinctes, deux méthodes.
        """
        internes = self.sudo().search([
            ('share', '=', False),
            ('notification_type', '=', 'email'),
        ])
        concernes = internes.filtered(lambda u: u._is_crowdfunding_staff())
        if concernes:
            concernes.write({'notification_type': 'inbox'})
            _logger.info(
                "opex_crowdfunding: cloche native activée pour %s compte(s) : %s",
                len(concernes), ", ".join(concernes.mapped('login')))
        return len(concernes)

    # `_crowdfunding_staff_url()` a été retiré le 27/08. Il aiguillait la tuile
    # d'accueil vers l'action back-office adaptée au rôle — Smart Work Queue
    # pour le Comité CEO, liste des projets pour le Contrôle Qualité, la
    # première n'étant ouverte qu'au premier. L'espace de traitement est
    # désormais une page du site, `/staff/crowdfunding`, dont la file se filtre
    # elle-même par rôle : une seule destination suffit, et la démonstration ne
    # quitte plus le site.
