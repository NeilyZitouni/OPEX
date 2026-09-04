"""Le référentiel de certifications — la dette D1, refermée par les deux bouts.

CE QUE D1 REPROCHAIT

Le critère éliminatoire de certification comparait **du texte libre** des deux
côtés : `opex.mission.request.certifications_souhaitees` contre
`res.partner.expert_certification_names`, en mode `contains`. Trois
défaillances mesurées :

1. **trop permissif** — « ISO 27001 » satisfaisait « ISO 27001 Lead Auditor »,
   parce que `contains` teste l'inclusion dans les deux sens ;
2. **trop restrictif** — « ISO27001 » sans espace ne croisait plus rien, et un
   candidat qualifié disparaissait du vivier pour une faute de frappe ;
3. **cumul impossible** — `_as_set()` sur une chaîne ne la découpe pas :
   exiger « ISO 27001, ISO 9001 » produisait **un seul jeton**, et n'exiger au
   plus qu'une des deux.

Sur un critère éliminatoire, ces trois-là ne dégradent pas un classement :
elles font disparaître un candidat, ou en laissent entrer un qui n'aurait pas
dû.

POURQUOI CE FICHIER N'INTRODUIT PAS UN SECOND RÉFÉRENTIEL

`opex.certification` existe déjà, dans le Module 1, semé de six normes. En
créer un second ici serait **exactement l'erreur que D1 documente** — deux
ensembles qui ne se croisent que par coïncidence de libellé. Il est donc
étendu par `_inherit` : pas une ligne du Module 1 ne change.

LA NUANCE QUE LE CLAUDE.MD LAISSAIT OUVERTE, ET COMMENT ELLE EST TRANCHÉE

    « `opex.certification` porte aujourd'hui des certifications
      d'organisation (« l'entreprise est ISO 9001 ») et le §B du Module 1 s'en
      sert ainsi. Ici il s'agit de certifications de personne (« Karim est
      Lead Auditor »). Le modèle peut porter les deux ; mais les mélanger dans
      une même liste déroulante mérite un accord. »

Le champ `porte` tranche sans rien mélanger : **un référentiel, deux vues**.
L'annuaire du Module 1 continue de proposer les certifications
d'organisation, le profil expert propose celles de personne, et une norme qui
vaut des deux côtés est déclarée telle une fois.

Le défaut est `organisation` — jamais `personne`. À l'ajout d'une colonne,
Odoo applique le défaut à toutes les lignes déjà en base : les six normes
semées par le Module 1 sont des certifications d'organisation, et les
requalifier d'office aurait changé le sens de données existantes sans que
personne le demande.
"""

import unicodedata

from odoo import _, api, fields, models

#: Les trois portées. Une certification peut valoir des deux côtés — ISO 27001
#: certifie une organisation, et un auditeur se certifie sur la même norme.
PORTEE_SELECTION = [
    ('organisation', "Organisation"),
    ('personne', "Personne"),
    ('les_deux', "Organisation et personne"),
]

#: Les portées qu'un profil expert peut déclarer. Nommées une fois : le
#: domaine de la relation, la résolution et l'écran y lisent tous les trois.
PORTEES_PERSONNE = ('personne', 'les_deux')

#: L'origine d'un synonyme, sur le même motif que ceux de compétences.
ORIGINE_SELECTION = [
    ('socle', "Livré avec le catalogue"),
    ('manuel', "Saisi par OPEX"),
    ('arbitrage', "Issu d'un arbitrage"),
]


class OpexCertificationCatalog(models.Model):
    """Le référentiel du Module 1, rangé et enrichi de ses synonymes."""

    _inherit = 'opex.certification'

    code = fields.Char(
        string="Code",
        index=True,
        help="Stable et court. C'est lui que le prompt de rapprochement "
             "présente au modèle, jamais l'identifiant technique.",
    )
    porte = fields.Selection(
        PORTEE_SELECTION,
        string="Porte sur",
        default='organisation',
        required=True,
        index=True,
        help="Une certification d'organisation atteste l'entreprise ; une "
             "certification de personne atteste l'intervenant. Le même "
             "référentiel porte les deux, et chaque écran ne propose que ce "
             "qui le concerne.",
    )
    organisme = fields.Char(
        string="Organisme certificateur",
        help="Qui délivre. Deux certifications de même intitulé délivrées par "
             "deux organismes ne valent pas la même chose.")
    active = fields.Boolean(string="Actif", default=True)

    synonyme_ids = fields.One2many(
        'opex.certification.synonyme', 'certification_id', string="Synonymes")
    synonyme_count = fields.Integer(
        string="Nombre de synonymes", compute='_compute_synonyme_count')

    @api.depends('synonyme_ids')
    def _compute_synonyme_count(self):
        for certification in self:
            certification.synonyme_count = len(certification.synonyme_ids)

    def action_view_synonymes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Synonymes de « %s »") % self.name,
            'res_model': 'opex.certification.synonyme',
            'view_mode': 'list,form',
            'domain': [('certification_id', '=', self.id)],
            'context': {'default_certification_id': self.id},
        }


class OpexCertificationSynonyme(models.Model):
    """Une écriture connue d'une certification du référentiel.

    Même motif que `opex.competence.synonyme` de l'IA-2, et pour la même
    raison : c'est l'étape 1 du rapprochement, gratuite et déterministe, qui
    traite la majorité des libellés d'un CV. Sans elle, tout part en
    arbitrage et la file cesse d'être regardée.

    Les sigles sont ceux qu'un CV écrit réellement — « ISO27001 » collé,
    « LA 27001 », « CISA », « PMP ».
    """

    _name = 'opex.certification.synonyme'
    _description = "Synonyme de certification"
    _order = 'certification_id, name'

    certification_id = fields.Many2one(
        'opex.certification',
        string="Certification du référentiel",
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(
        string="Libellé", required=True,
        help="Tel qu'on le rencontre dans un CV.")
    normalised = fields.Char(
        string="Forme normalisée",
        compute='_compute_normalised',
        store=True,
        index=True,
        readonly=True,
    )
    origine = fields.Selection(
        ORIGINE_SELECTION,
        string="Origine",
        default='manuel',
        required=True,
    )

    #: Un même libellé ne peut pas désigner deux certifications : la
    #: résolution renverrait l'une ou l'autre selon l'ordre d'insertion, et le
    #: **critère éliminatoire** deviendrait non déterministe. C'est plus grave
    #: ici que sur une compétence : un candidat serait écarté ou admis selon
    #: le hasard d'un index.
    _normalised_uniq = models.Constraint(
        'unique(normalised)',
        "Ce libellé est déjà rattaché à une certification du référentiel.",
    )

    @api.depends('name')
    def _compute_normalised(self):
        for synonyme in self:
            synonyme.normalised = self._normalise(synonyme.name)

    @api.depends('name', 'certification_id')
    def _compute_display_name(self):
        for synonyme in self:
            synonyme.display_name = "%s → %s" % (
                synonyme.name or '', synonyme.certification_id.name or '')

    # ------------------------------------------------------------
    # La normalisation — la même que celle des compétences
    # ------------------------------------------------------------

    @api.model
    def _normalise(self, label):
        """La forme comparable d'un libellé.

        Identique à celle des compétences, y compris dans ce qu'elle refuse de
        faire : **elle ne retire pas les espaces.** « ISO 27001 » et
        « ISO27001 » restent deux clés distinctes, et c'est un synonyme qui
        les réunit.

        Tout coller les ferait correspondre — ce qu'on veut — mais ferait
        aussi correspondre « iso 27001 » et « iso27 001 », donc n'importe
        quelle suite de caractères avec n'importe quelle autre à un espace
        près. Sur un critère qui décide qui entre dans le vivier, une
        correspondance approximative est pire qu'une absence : elle se trompe
        en silence.
        """
        if not label:
            return ''
        decomposed = unicodedata.normalize('NFKD', str(label))
        stripped = decomposed.encode('ascii', 'ignore').decode('ascii')
        return ' '.join(
            ''.join(c if c.isalnum() else ' ' for c in stripped.lower()).split())

    @api.model
    def resolve_label(self, label, porte_personne=True):
        """La certification désignée par ce libellé, ou un recordset vide.

        Deux temps, dans cet ordre :

        1. le **référentiel** lui-même, sur sa forme normalisée ;
        2. la table des **synonymes**.

        Aucun appel réseau, aucune approximation.

        ⚠ **Une correspondance ambiguë refuse de choisir.** Si deux
        certifications du catalogue se normalisent pareil, rendre l'une ou
        l'autre serait non déterministe — et sur un critère éliminatoire, cela
        veut dire qu'un candidat serait admis ou écarté selon l'ordre de
        recherche. C'est le défaut trouvé à l'IA-2 sur les compétences ; il
        est plus grave ici, et il se traite pareil : on rend vide, et le
        libellé part en arbitrage où quelqu'un voit les deux entrées.
        """
        Certification = self.env['opex.certification'].sudo()
        key = self._normalise(label)
        if not key:
            return Certification.browse()

        domain = [('active', '=', True)]
        if porte_personne:
            domain.append(('porte', 'in', PORTEES_PERSONNE))

        exactes = Certification.search(domain).filtered(
            lambda c: self._normalise(c.name) == key)
        if len(exactes) > 1:
            return Certification.browse()
        if exactes:
            return exactes

        synonymes = self.sudo().search([('normalised', '=', key)])
        candidates = synonymes.certification_id.filtered(
            lambda c: c.active and (
                not porte_personne or c.porte in PORTEES_PERSONNE))
        if len(candidates) != 1:
            return Certification.browse()
        return candidates

    @api.model
    def catalogue_for_prompt(self, limit=200):
        """Le catalogue présenté au modèle, pour l'étape 2.

        Codes et libellés seulement : le modèle doit rendre **un code du
        catalogue**, et on le vérifie ensuite contre lui. Un modèle invente
        volontiers un code plausible.
        """
        Certification = self.env['opex.certification'].sudo()
        entries = Certification.search(
            [('active', '=', True), ('porte', 'in', PORTEES_PERSONNE)],
            limit=limit)
        return [
            {'code': c.code or str(c.id), 'libelle': c.name}
            for c in entries
        ]
