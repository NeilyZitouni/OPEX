from odoo import models


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
