from odoo import fields, models


class OpexClusterVote(models.Model):
    """Vote en assemblée générale — **stub, hors périmètre actuel**.

    ⚠️ Ce modèle ne fait rien d'autre que porter une question et ses options.
    Il n'y a **volontairement** :

    - aucun bulletin (personne n'enregistre de choix) ;
    - aucun dépouillement, aucun décompte, aucun résultat ;
    - aucune notion de quorum, de majorité, d'ouverture ou de clôture ;
    - aucune route portail permettant de voter.

    La section 40 du document de référence marque elle-même les votes comme une
    **évolution** prévue, pas une fonctionnalité du POC. Le modèle existe pour
    que la structure de données soit posée et que l'écran d'assemblée puisse
    montrer les questions soumises — rien de plus.

    Toute implémentation ultérieure devra traiter, au minimum : qui a le droit
    de voter, l'unicité du bulletin, l'anonymat éventuel, et l'horodatage
    d'ouverture/fermeture. Ne pas déduire de ce stub qu'un vote est utilisable
    en l'état.
    """

    _name = 'opex.cluster.vote'
    _description = "Vote en assemblée (stub, non implémenté)"
    _order = 'assembly_id, id'

    question = fields.Char(string="Question", required=True)
    assembly_id = fields.Many2one(
        'opex.cluster.assembly', string="Assemblée", ondelete='cascade', index=True)
    option_ids = fields.One2many(
        'opex.cluster.vote.option', 'vote_id', string="Options")


class OpexClusterVoteOption(models.Model):
    """Option proposée à un vote — support du stub, sans comptage associé."""

    _name = 'opex.cluster.vote.option'
    _description = "Option de vote (stub, non implémenté)"
    _order = 'vote_id, sequence, id'

    name = fields.Char(string="Option", required=True)
    sequence = fields.Integer(string="Séquence", default=10)
    vote_id = fields.Many2one(
        'opex.cluster.vote', string="Vote", required=True,
        ondelete='cascade', index=True)
