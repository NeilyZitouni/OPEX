from odoo import fields, models


class MissionType(models.Model):
    """Un type d'intervention — Audit, Conseil, Formation, Coaching…

    Un modèle et non un `Selection` figé : le cluster ajoutera des types sans
    migration, et surtout `multi_intervenants` doit se régler **par type**, ce
    qu'une valeur de `Selection` ne saurait pas porter.
    """

    _name = 'opex.mission.type'
    _description = "Type de mission"
    _order = 'sequence, name, id'

    name = fields.Char(string="Nom", required=True, translate=True)
    code = fields.Char(
        string="Code",
        required=True,
        index=True,
        help="Identifiant technique, stable. C'est lui que citent les "
             "configurations et les tests, jamais le libellé.",
    )
    sequence = fields.Integer(string="Séquence", default=10)
    description = fields.Text(string="Description")
    active = fields.Boolean(string="Actif", default=True)

    # L'exception explicite de la règle 4 du §39 :
    #
    #   « Une mission ne peut avoir qu'un intervenant sélectionné […] sauf si le
    #     modèle de mission autorise explicitement plusieurs intervenants. »
    #
    # Sans ce champ, la condition de la transition « Attribuer la mission » est
    # un `== 1` en dur et l'exception du document n'est pas implémentable. Avec
    # lui, elle est une case à cocher sur le référentiel — donc une décision de
    # paramétrage, pas de développement.
    multi_intervenants = fields.Boolean(
        string="Plusieurs intervenants autorisés",
        help="Coché, ce type de mission accepte plusieurs candidatures "
             "retenues. Décoché — le cas normal —, la transition "
             "« Attribuer la mission » exige exactement une candidature "
             "retenue (règle 4 du §39).",
    )

    _code_uniq = models.Constraint(
        'unique(code)',
        "Deux types de mission ne peuvent pas porter le même code.",
    )


class MissionDomain(models.Model):
    """Un domaine d'expertise — cybersécurité, qualité, finance…

    Distinct des **compétences** : le domaine situe la mission, les compétences
    disent ce qu'il faut savoir faire. Le matching de l'Extension 4 compare le
    domaine au `expert_domaine` du profil et les compétences à
    `expert_competence_ids` — deux critères, deux poids.
    """

    _name = 'opex.mission.domain'
    _description = "Domaine d'expertise"
    _order = 'sequence, name, id'

    name = fields.Char(string="Nom", required=True, translate=True)
    code = fields.Char(string="Code", required=True, index=True)
    sequence = fields.Integer(string="Séquence", default=10)
    description = fields.Text(string="Description")
    active = fields.Boolean(string="Actif", default=True)

    _code_uniq = models.Constraint(
        'unique(code)',
        "Deux domaines ne peuvent pas porter le même code.",
    )


#
# IL N'Y A PAS DE TROISIÈME RÉFÉRENTIEL ICI, ET C'EST DÉLIBÉRÉ
#
#
# Les compétences recherchées d'une mission pointent vers
# `opex.innovation.competence`, le référentiel du Module 2. On n'en crée pas un
# second, et ce n'est pas une économie de fichier — c'est une condition de
# fonctionnement du matching.
#
# Le moteur compare une valeur du dossier à un **champ de `res.partner`**
# (`_score_candidate`, `opex_workflow/models/workflow_instance.py:1077`), et
# `res.partner.expert_competence_ids` — `related` de
# `expert_profile_id.competence_ids` — pointe déjà vers ce référentiel-là.
#
# Avec un référentiel propre au Module 3, les deux ensembles ne se croiseraient
# que par coïncidence de libellé : `_as_set()` normalise en minuscules et
# compare des chaînes. « Cybersécurité » ici et « Cybersécurité » là-bas
# tomberaient juste, jusqu'au premier renommage d'un côté. Le critère
# « Compétences 30 % » deviendrait alors faux **sans que rien ne le signale** —
# exactement le mode de défaillance décrit au §6c du CLAUDE.md du moteur, et
# déjà payé une fois.


class ExpertCompetence(models.Model):
    """Le référentiel de compétences du Module 2, ouvert aux missions.

    Aucun champ ajouté : ce modèle n'est présent ici que pour porter le
    commentaire ci-dessus au bon endroit, et pour que `_inherit` documente la
    dépendance dans le registre. La qualification par niveau et par années
    (`opex.expert.skill`) viendra à l'Extension 3, **sur ce référentiel**.
    """

    _inherit = 'opex.innovation.competence'

    mission_request_ids = fields.Many2many(
        'opex.mission.request',
        # Les trois noms doivent être **exactement** ceux déclarés côté
        # mission, colonnes inversées. Une paire de Many2many réciproques qui
        # divergent d'un nom de colonne produit deux tables distinctes : les
        # deux champs marchent, et aucun ne voit ce que l'autre écrit.
        'mission_request_skill_rel', 'competence_id', 'mission_id',
        string="Appels à mission",
        help="Les appels qui recherchent cette compétence. Miroir du champ "
             "`skill_ids` de la mission — de quoi mesurer, plus tard, ce que le "
             "cluster demande le plus.",
    )
