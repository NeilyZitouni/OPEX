from odoo import models


class ResUsers(models.Model):
    _inherit = 'res.users'

    # Rôles internes du module. Définis une seule fois : l'espace de traitement
    # (`/staff/...`) et la prévisualisation de la Vie du Cluster s'appuient tous
    # deux dessus, et deux listes séparées finiraient par diverger — un groupe
    # ajouté d'un côté, oublié de l'autre.
    OPEX_STAFF_GROUPS = (
        'opex_membership.group_secretariat',
        'opex_membership.group_comite',
        'opex_membership.group_copil',
        'base.group_system',
    )

    def _is_opex_staff(self):
        """Cet utilisateur fait-il partie du personnel interne du module ?"""
        self.ensure_one()
        return any(self.has_group(group) for group in self.OPEX_STAFF_GROUPS)
