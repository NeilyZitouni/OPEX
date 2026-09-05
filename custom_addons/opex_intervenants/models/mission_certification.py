"""L'exigence de certification d'un appel — canonique, et conjonctive.

Le pendant, côté mission, de `res.partner.expert_certification_ref_ids`.

POURQUOI `certifications_souhaitees` RESTE

Le champ texte est conservé et reste affiché au portail client. Il porte ce
que le client **demande en toutes lettres** — « idéalement un auditeur ayant
déjà travaillé en environnement bancaire » —, ce qu'aucun référentiel ne
saura jamais exprimer. Il continue de nourrir un critère pondéré ; ce qu'il
ne fait plus, c'est décider qui entre dans le vivier.

L'EXIGENCE EST CONJONCTIVE, ET C'EST LE TROISIÈME DÉFAUT DE D1

    « Exiger deux certifications revient à n'en exiger au plus qu'une. »

Le mode `intersect` du moteur teste un **recoupement** : `bool(source &
target)`. Sur un critère pondéré c'est exactement ce qu'on veut — un candidat
qui a une des deux normes mérite ses points. Sur un critère **éliminatoire**,
c'est faux : exiger ISO 27001 **et** ISO 9001 doit vouloir dire les deux.

Le moteur n'a pas de mode conjonctif et n'en aura pas — ce serait lui
apprendre une nuance métier. La conjonction est donc portée par un champ de
**configuration** sur le critère, `is_conjonctif`, et l'élimination le lit.
La comparaison, elle, reste celle du moteur : `_compare()` est appelé une
fois par certification exigée, jamais réécrit.
"""

from odoo import _, api, fields, models

#: La famille du critère éliminatoire de certification. Nommée une fois : le
#: modèle et les tests y lisent tous les deux.
CERTIFICATION_FAMILY = 'certification'


class MissionRequestCertification(models.Model):
    """Ce que l'appel exige, en références du référentiel."""

    _inherit = 'opex.mission.request'

    certification_ids = fields.Many2many(
        'opex.certification',
        'opex_mission_certification_rel', 'mission_id', 'certification_id',
        string="Certifications exigées",
        domain="[('porte', 'in', ['personne', 'les_deux'])]",
        help="Chacune est obligatoire : un candidat qui n'en détient qu'une "
             "partie est écarté du vivier, pas mal noté. Laisser vide "
             "n'exige rien.",
    )
    certification_count = fields.Integer(
        string="Nombre de certifications exigées",
        compute='_compute_certification_count',
    )

    @api.depends('certification_ids')
    def _compute_certification_count(self):
        for mission in self:
            mission.certification_count = len(mission.certification_ids)

    # ------------------------------------------------------------
    # « Ce qu'on ne sait pas encore » — la note du §11
    # ------------------------------------------------------------

    def _matching_unresolved_declarations(self, criterion, partner):
        """Les certifications que ce candidat déclare sans qu'elles soient
        rapprochées — et qui partent en arbitrage.

            « Une certification non rapprochée n'est pas une non-conformité,
              c'est une file d'arbitrage : elle n'admet pas le candidat, elle
              nomme ce qu'on ne sait pas encore. »

        Deux effets, et les deux comptent :

        1. le **motif** d'exclusion change — « à arbitrer » plutôt que « il
           manque ». Un responsable qui lit la liste des écartés sait alors
           s'il regarde une réponse ou une question ;
        2. la ligne **part en file**, au lieu d'être passée sous silence. Sans
           cela, la même question se reposerait à chaque appel, sur chaque
           candidat, sans que personne ne la voie jamais.

        ⚠ Le candidat reste **écarté**. Une certification non rapprochée n'est
        comparable à rien ; l'admettre ferait franchir le critère éliminatoire
        à un intitulé libre, c'est-à-dire rouvrirait la dette D1 par la porte
        de derrière.

        Bornée aux critères de la famille `certification` : ce module ne sait
        dire « je ne sais pas encore » que sur ce qu'il a un référentiel pour
        juger.
        """
        if criterion.family != CERTIFICATION_FAMILY:
            return super()._matching_unresolved_declarations(
                criterion, partner)

        profile = partner.sudo().expert_profile_id
        if not profile:
            return []

        # Non rapprochées **et** encore valables : une certification périmée
        # ne pose aucune question, elle a sa réponse.
        en_attente = profile.expert_certification_ids.filtered(
            lambda c: not c.certification_id and c.is_valid and c.name)
        if not en_attente:
            return []

        Arbitrage = self.env['opex.certification.arbitrage']
        libelles = []
        for ligne in en_attente:
            libelles.append(ligne.name)
            # Idempotent sur la forme normalisée : le même intitulé lu sur
            # trois profils ne pose qu'une question.
            Arbitrage.enqueue(
                ligne.name,
                profile=profile,
                document=_("Matching sur %s") % (self.display_name or ''),
            )
        return libelles


class MatchingCriteriaConjunction(models.Model):
    """La conjonction, portée par la configuration et non par du Python.

    Même parti qu'à l'Extension 4 pour `is_eliminatoire` : le moteur ne
    connaît pas la notion, le module l'ajoute au critère, et c'est
    l'orchestration du module qui en tire les conséquences. Le scoring et la
    comparaison restent ceux du moteur.
    """

    _inherit = 'opex.matching.criteria'

    is_conjonctif = fields.Boolean(
        string="Toutes les valeurs sont exigées",
        help="Sur un critère éliminatoire, exige que le candidat satisfasse "
             "**chacune** des valeurs attendues et non une seule. C'est la "
             "différence entre « exiger ISO 27001 et ISO 9001 » et « exiger "
             "l'une des deux ». Sans effet sur un critère pondéré, où un "
             "recoupement partiel mérite légitimement ses points.",
    )
