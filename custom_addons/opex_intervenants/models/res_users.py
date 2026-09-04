from odoo import models


class ResUsers(models.Model):
    _inherit = 'res.users'

    #: Les rôles qui instruisent les appels à mission. La liste vit **ici** et
    #: nulle part ailleurs : un gabarit ne peut pas appeler un helper de
    #: controller, et le `t-if` d'une tuile portail doit poser exactement la
    #: même question que la route qu'elle ouvre. Deux listes finiraient par
    #: diverger — la tuile visible pour un rôle que la route refuse, ou
    #: l'inverse.
    OPEX_MISSIONS_STAFF_GROUPS = (
        'opex_intervenants.group_mission_manager',
        'opex_intervenants.group_mission_committee',
        'opex_membership.group_secretariat',
    )

    def _is_missions_staff(self):
        """Cet utilisateur instruit-il les appels à mission ?

        **LA** fonction de contrôle d'accès du staff Missions — règle
        transversale 2 du CLAUDE.md, qui la nomme d'ailleurs exactement ainsi.
        Toutes les routes `/staff/missions/*` l'appellent, et elle seule.

        Les helpers d'appartenance — « cet appel est-il dans mon périmètre ? »
        — sont autre chose et peuvent être plusieurs.

        `sudo()` sur la seule lecture des groupes : un compte portail n'a pas le
        droit de lire `res.groups`, et la question se pose aussi pour lui. La
        réponse est « non ».
        """
        self.ensure_one()
        return any(self.sudo()._has_group(group)
                   for group in self.OPEX_MISSIONS_STAFF_GROUPS)
