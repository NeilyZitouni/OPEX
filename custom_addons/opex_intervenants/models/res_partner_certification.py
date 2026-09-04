"""La cible de matching des certifications — canonique, plus du texte.

POURQUOI UN CHAMP DE PLUS PLUTÔT QU'UNE MODIFICATION DE L'ANCIEN

`expert_certification_names` reste, et reste alimenté. Trois raisons, dans
l'ordre où elles comptent :

1. **Le Module 1 ne le lit pas, mais le portail et les écrans, si.** Le
   supprimer casserait ce qui l'affiche, pour un gain nul.
2. Il porte ce que l'expert a **écrit**, y compris les lignes que personne n'a
   encore rapprochées. C'est ce qui permet au gestionnaire de voir ce qui
   reste à ranger.
3. Un critère de matching **pondéré** peut légitimement continuer de s'en
   servir : sur un critère qui note, une correspondance approximative coûte
   des points, elle ne fait disparaître personne.

Ce que D1 interdit, c'est de comparer du texte sur un critère **éliminatoire**.
`expert_certification_ref_ids` est là pour celui-là, et il porte des
identifiants du référentiel : deux ensembles issus de la même table se
croisent par construction, jamais par coïncidence d'orthographe.

⚠ **Ce champ n'est pas stocké**, et c'est une correction mesurée. L'éligibilité
d'une certification dépend de sa date d'expiration comparée à *aujourd'hui* :
aucune dépendance ne se déclenche le jour où elle expire. Un stockage figerait
la valeur à son dernier recalcul, et une certification périmée continuerait de
qualifier son porteur jusqu'à ce que quelqu'un rouvre sa fiche.

Sur un critère qui décide de l'éligibilité, c'est admettre un candidat qui
n'est plus qualifié — le symptôme exact que D1 documente, obtenu par un autre
chemin. Règle 16, prise du côté où elle interdit de stocker.

Le prix est un calcul par candidat évalué. Il est payé volontiers.
"""

from odoo import api, fields, models


class ResPartnerCertification(models.Model):
    """Ce que le critère éliminatoire compare, du côté du candidat."""

    _inherit = 'res.partner'

    expert_certification_ref_ids = fields.Many2many(
        'opex.certification',
        'opex_partner_certification_ref_rel', 'partner_id', 'certification_id',
        string="Certifications canoniques",
        compute='_compute_expert_certification_refs',
        help="Les certifications du référentiel que cet intervenant détient : "
             "rapprochées, confirmées et encore valables. C'est ce champ que "
             "le critère éliminatoire compare, jamais les intitulés libres.",
    )
    expert_certification_ref_count = fields.Integer(
        string="Nombre de certifications canoniques",
        compute='_compute_expert_certification_ref_count',
    )

    # Deux méthodes, parce que l'un est stocké et l'autre non : le registre
    # refuse qu'une même méthode produise les deux (règle 9). Lire le compteur
    # d'affichage déclencherait sinon une écriture du champ stocké, à un
    # moment quelconque et sous l'identité de n'importe quel lecteur.

    # Les dépendances portent sur des champs **réels**, pas sur `is_eligible`
    # qui n'est pas stocké. Elles servent l'invalidation du cache : confirmer
    # une certification ou la rapprocher change le vivier immédiatement. Ce
    # qu'aucune dépendance ne peut porter, c'est le passage du temps - d'où
    # l'absence de stockage.
    @api.depends(
        'expert_profile_id',
        'expert_profile_id.expert_certification_ids',
        'expert_profile_id.expert_certification_ids.certification_id',
        'expert_profile_id.expert_certification_ids.confiance',
        'expert_profile_id.expert_certification_ids.date_expiration',
    )
    def _compute_expert_certification_refs(self):
        for partner in self:
            profile = partner.expert_profile_id
            if not profile:
                partner.expert_certification_ref_ids = [(5, 0, 0)]
                continue
            eligibles = profile.sudo().expert_certification_ids.filtered(
                'is_eligible')
            partner.expert_certification_ref_ids = [
                (6, 0, eligibles.certification_id.ids)]

    @api.depends('expert_certification_ref_ids')
    def _compute_expert_certification_ref_count(self):
        for partner in self:
            partner.expert_certification_ref_count = len(
                partner.expert_certification_ref_ids)
