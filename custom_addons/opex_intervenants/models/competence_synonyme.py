"""La table de correspondance vers le référentiel du Module 2 - §8.

    « Les compétences ne doivent pas être de simples tags libres. »

Un modèle séparé plutôt qu'un champ `synonymes` sur
`opex.innovation.competence` : le Module 2 reste gelé. C'est moins naturel -
un synonyme est une propriété de la compétence, pas un objet - et c'est
assumé, parce que rouvrir un module présenté coûte plus que cette indirection.

Conséquence à connaître : `competence_id` est en `ondelete='cascade'`. Si le
Module 2 supprime une compétence, ses synonymes partent avec elle plutôt que
de pointer dans le vide. C'est la seule dépendance que ce modèle crée, et elle
va dans le bon sens - le Module 3 connaît le Module 2, jamais l'inverse.

POURQUOI LA NORMALISATION EST ICI ET PAS AILLEURS

Elle est ce qui décide si deux libellés désignent la même chose. La dette D1
montre le coût de s'être fié à une comparaison approximative sur un critère
qui décide de qui entre dans le vivier : « ISO 27001 » y passe un critère
exigeant « ISO 27001 Lead Auditor », et « ISO27001 » n'y croise plus rien.

La réponse retenue n'est pas une comparaison plus intelligente, c'est une
**clé normalisée exacte plus une table de synonymes**. Une correspondance
approximative se trompe silencieusement ; un synonyme absent se voit, parce
que le libellé part en file d'arbitrage.
"""

import logging
import re
import unicodedata

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

#: Ce qui sépare deux mots. Tout le reste - ponctuation, tirets, deux-points -
#: disparaît : « ISO 27001:2022 » et « ISO 27001 : 2022 » sont le même
#: libellé écrit par deux personnes différentes.
NON_WORD = re.compile(r"[^a-z0-9]+")


class CompetenceSynonyme(models.Model):
    """Un libellé alternatif désignant une compétence du référentiel."""

    _name = 'opex.competence.synonyme'
    _description = "Synonyme de compétence"
    _order = 'competence_id, name'

    competence_id = fields.Many2one(
        'opex.innovation.competence',
        string="Compétence du référentiel",
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(
        string="Libellé alternatif", required=True,
        help="Tel qu'on le rencontre dans un CV. La casse, les accents et la "
             "ponctuation n'ont pas d'importance : c'est la forme normalisée "
             "qui sert à la comparaison.")

    #: La forme sur laquelle porte la comparaison. Stockée parce qu'une
    #: recherche a besoin d'une colonne, et calculée parce qu'un humain ne
    #: doit jamais avoir à la saisir.
    normalised = fields.Char(
        string="Forme normalisée", compute='_compute_normalised',
        store=True, index=True, readonly=True)

    origine = fields.Selection(
        [
            ('socle', "Livré avec le catalogue"),
            ('manuel', "Saisi par OPEX"),
            ('arbitrage', "Issu d'un arbitrage"),
        ],
        string="Origine",
        default='manuel',
        required=True,
        help="Un synonyme né d'un arbitrage porte la trace de la décision qui "
             "l'a créé ; celle-ci reste consultable dans la file. Un synonyme "
             "du socle est livré par le module et réécrit à chaque mise à "
             "jour - ce n'est pas là qu'il faut corriger une erreur.",
    )

    #: Un même libellé ne peut pas désigner deux compétences : la résolution
    #: renverrait l'une ou l'autre selon l'ordre d'insertion, et le matching
    #: deviendrait non déterministe.
    _normalised_uniq = models.Constraint(
        'unique(normalised)',
        "Ce libellé est déjà rattaché à une compétence du référentiel.",
    )

    @api.depends('name')
    def _compute_normalised(self):
        for synonyme in self:
            synonyme.normalised = self._normalise(synonyme.name)

    @api.depends('name', 'competence_id')
    def _compute_display_name(self):
        for synonyme in self:
            synonyme.display_name = "%s → %s" % (
                synonyme.name or '', synonyme.competence_id.name or '')

    # ------------------------------------------------------------
    # La normalisation
    # ------------------------------------------------------------

    @api.model
    def _normalise(self, label):
        """La forme comparable d'un libellé.

        Minuscules, accents retirés, ponctuation réduite à un séparateur.
        « Audit des Systèmes d'Information » et « audit des systemes
        d'information » donnent la même clé.

        Ce qu'elle ne fait **pas**, et c'est délibéré : elle ne retire pas les
        espaces. « ISO 27001 » et « ISO27001 » restent deux clés distinctes,
        et c'est un synonyme qui les réunit - pas une règle de comparaison.

        La tentation serait de tout coller pour les faire correspondre. Elle
        ferait aussi correspondre « audit SI » et « auditsi », donc n'importe
        quelle suite de mots avec n'importe quelle autre à un espace près. Une
        correspondance approximative se trompe en silence ; un synonyme
        manquant envoie le libellé en arbitrage, où quelqu'un le voit.
        """
        if not label:
            return ''
        # NFKD sépare la lettre de son accent ; l'encodage ASCII avec `ignore`
        # laisse tomber les accents restés seuls.
        decomposed = unicodedata.normalize('NFKD', str(label))
        stripped = decomposed.encode('ascii', 'ignore').decode('ascii')
        return NON_WORD.sub(' ', stripped.lower()).strip()

    # ------------------------------------------------------------
    # Étape 1 - la correspondance, sans appel IA
    # ------------------------------------------------------------

    @api.model
    def resolve_label(self, label):
        """Rend la compétence désignée par ce libellé, ou un recordset vide.

        **Première étape des deux, et elle ne coûte rien.** Le rapprochement
        se fait contre le référentiel puis contre la table de synonymes, par
        clé normalisée exacte. Aucun appel à l'IA : la majorité des libellés
        d'un CV sont des intitulés courants, déjà au catalogue, et les payer
        au fournisseur serait absurde.

        C'est aussi ce qui rend l'IA-2 utilisable sans clé configurée. Un
        cluster qui n'active pas l'assistance IA garde le rapprochement exact
        et la file d'arbitrage - la règle 1 du service, vue depuis le métier.
        """
        Competence = self.env['opex.innovation.competence'].sudo()
        empty = Competence.browse()

        key = self._normalise(label)
        if not key:
            return empty

        # Le référentiel d'abord : un libellé du catalogue n'a pas besoin d'un
        # synonyme pour être reconnu.
        matches = Competence.search([]).filtered(
            lambda c: self._normalise(c.name) == key)

        # **Une correspondance ambiguë n'en est pas une.**
        #
        # Trouvé en conditions réelles : le catalogue contenait « Audit des
        # systemes d'information » et « Audit des systèmes d'information » -
        # deux entrées que la normalisation rend identiques. La boucle
        # d'origine renvoyait la première rencontrée, donc l'une ou l'autre
        # selon l'ordre de recherche.
        #
        # L'expert aurait été qualifié sur une des deux au hasard, et le
        # matching aurait comparé à celle que la mission avait choisie. Deux
        # fois sur trois, personne ne se croise - sans qu'aucune erreur ne
        # soit levée. C'est exactement le motif de la dette D1.
        #
        # `opex.innovation.competence` n'a pas de contrainte d'unicité et le
        # Module 2 est gelé : on ne peut pas empêcher le doublon, seulement
        # refuser de choisir à la place d'un humain. Le libellé part en
        # arbitrage, où le gestionnaire voit les deux entrées et nettoie son
        # catalogue.
        if len(matches) > 1:
            _logger.warning(
                "opex_intervenants: « %s » correspond à %s entrées du "
                "catalogue (%s). Rapprochement automatique refusé : le "
                "référentiel a des doublons à nettoyer.",
                label, len(matches), ", ".join(matches.mapped('name')))
            return empty
        if matches:
            return matches

        synonyme = self.sudo().search([('normalised', '=', key)], limit=1)
        return synonyme.competence_id

    @api.model
    def catalogue_for_prompt(self, limit=200):
        """Le catalogue, sous la forme que le prompt de rapprochement attend.

        Borné : un référentiel de plusieurs milliers d'entrées ferait un
        prompt coûteux et moins précis. Le jour où le catalogue dépasse cette
        borne, il faudra présélectionner par domaine plutôt que d'augmenter la
        limite - c'est écrit ici pour que ce soit décidé et non découvert.
        """
        competences = self.env['opex.innovation.competence'].sudo().search(
            [('active', '=', True)], limit=limit)
        return [
            {'code': competence.code or str(competence.id),
             'nom': competence.name,
             'domaine': competence.domaine or ''}
            for competence in competences
        ]

    def action_open_competence(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Compétence"),
            'res_model': 'opex.innovation.competence',
            'view_mode': 'form',
            'res_id': self.competence_id.id,
        }
