from odoo import _, api, fields, models
from odoo.exceptions import UserError


class RemediationPoint(models.Model):
    """Un point précis à corriger — référentiel semé en données.

    « Le cluster ne doit pas simplement dire *Améliorez votre projet*. Il doit
    préciser ce qui doit être corrigé. » Un référentiel plutôt qu'un texte
    libre : le porteur reçoit une liste de choses à faire, pas un paragraphe à
    interpréter — et le cluster peut mesurer ce qui revient le plus souvent.
    """

    _name = 'opex.innovation.remediation.point'
    _description = "Point de remédiation"
    _order = 'sequence, id'

    name = fields.Char(string="Point", required=True, translate=True)
    code = fields.Char(string="Code", required=True, index=True)
    sequence = fields.Integer(string="Séquence", default=10)
    description = fields.Text(
        string="Ce qui est attendu",
        translate=True,
        help="Affiché au porteur sous le point. C'est ici qu'on explique ce "
             "qu'on attend concrètement.",
    )
    active = fields.Boolean(string="Actif", default=True)

    _code_uniq = models.Constraint(
        'unique(code)', "Le code d'un point de remédiation doit être unique.")


class Remediation(models.Model):
    """Demande de remédiation adressée au porteur — section 18.

    ⚠ **Une remédiation sans point ne peut pas être envoyée.** C'est la
    contrainte qui donne son sens à toute l'extension : sans elle, le comité
    retomberait dans le « améliorez votre projet » que la spécification
    proscrit explicitement.
    """

    _name = 'opex.innovation.remediation'
    _description = "Demande de remédiation"
    _order = 'project_id, date_demande desc, id desc'

    project_id = fields.Many2one(
        'opex.innovation.project',
        string="Projet",
        required=True,
        ondelete='cascade',
        index=True,
    )
    point_ids = fields.Many2many(
        'opex.innovation.remediation.point',
        'remediation_point_rel', 'remediation_id', 'point_id',
        string="Points à corriger",
        required=True,
        help="Ce que le porteur doit reprendre. Au moins un point est exigé : "
             "une demande sans point ne dit rien de ce qu'il faut faire.",
    )
    commentaire_comite = fields.Text(
        string="Commentaire du comité",
        help="Précisions du comité, en complément des points cochés.",
    )
    date_demande = fields.Datetime(
        string="Demandée le", default=fields.Datetime.now, readonly=True)
    date_resolved = fields.Datetime(string="Traitée le", readonly=True)
    resolved = fields.Boolean(string="Traitée", readonly=True)

    #: Version du dossier au moment de la demande. C'est elle qui rend
    #: l'historique des versions lisible : « la remédiation n°2 portait sur la
    #: version 2 du dossier ».
    version = fields.Integer(string="Version du dossier", readonly=True)

    reponse_porteur = fields.Text(
        string="Réponse du porteur",
        help="Ce que le porteur a répondu aux remarques, saisi depuis son "
             "espace au moment de resoumettre.",
    )

    @api.constrains('point_ids')
    def _check_points(self):
        """⚠ La contrainte centrale de la section 18.

        Au niveau du modèle et non du formulaire : une demande créée depuis le
        back-office, depuis le portail ou par une requête forgée passe par la
        même règle.
        """
        for remediation in self:
            if not remediation.point_ids:
                raise UserError(_(
                    "Précisez au moins un point à corriger. Le cluster ne dit "
                    "pas « améliorez votre projet » : il indique quoi reprendre."
                ))

    @api.model_create_multi
    def create(self, vals_list):
        """⚠ Le contrôle est **rappelé explicitement** à la création.

        Piège Odoo : `@api.constrains` sur un Many2many ne se déclenche que si
        le champ figure dans les valeurs écrites. Créer une remédiation **sans
        mentionner `point_ids` du tout** — précisément le cas que la contrainte
        existe pour interdire — passait donc sans être vérifié.

        `required=True` sur le champ n'y change rien : il n'y a pas de
        contrainte NOT NULL possible sur une table de liaison.
        """
        remediations = super().create(vals_list)
        remediations._check_points()
        return remediations

    @api.depends('project_id', 'date_demande')
    def _compute_display_name(self):
        for remediation in self:
            remediation.display_name = _(
                "Remédiation — %(projet)s (v%(version)s)") % {
                'projet': remediation.project_id.name or '',
                'version': remediation.version or 1,
            }

    def action_resolve(self):
        for remediation in self:
            remediation.write({
                'resolved': True,
                'date_resolved': fields.Datetime.now(),
            })
        return True


class ProjectVersion(models.Model):
    """Instantané du dossier à une resoumission — section 18.

    « Le système doit conserver l'historique des versions. »

    Une copie figée plutôt qu'un lien vers le projet vivant : c'est justement
    parce que le projet change qu'on garde la trace de ce qu'il était. Un
    Many2one vers le projet montrerait toujours sa dernière version, ce qui
    n'apprendrait rien.

    Ce n'est pas un `opex.workflow.definition.version` : le moteur versionne les
    **processus**, ce modèle versionne un **dossier**. Les deux sont
    indépendants.
    """

    _name = 'opex.innovation.project.version'
    _description = "Version d'un dossier de projet"
    _order = 'project_id, version desc'

    project_id = fields.Many2one(
        'opex.innovation.project',
        string="Projet",
        required=True,
        ondelete='cascade',
        index=True,
    )
    version = fields.Integer(string="Version", required=True)
    date_snapshot = fields.Datetime(
        string="Figée le", default=fields.Datetime.now, readonly=True)
    remediation_id = fields.Many2one(
        'opex.innovation.remediation',
        string="Remédiation traitée",
        ondelete='set null',
        help="Demande à laquelle cette version répond.",
    )

    #: Le dossier tel qu'il était. Champs figés, jamais related : un `related`
    #: suivrait le projet et effacerait précisément ce qu'on cherche à garder.
    name = fields.Char(string="Nom du projet", readonly=True)
    resume = fields.Text(string="Résumé", readonly=True)
    probleme = fields.Text(string="Problème", readonly=True)
    solution = fields.Text(string="Solution", readonly=True)
    marche_cible = fields.Text(string="Marché cible", readonly=True)
    besoin_marche = fields.Text(string="Besoin du marché", readonly=True)
    concurrence = fields.Text(string="Concurrence", readonly=True)
    proposition_valeur = fields.Text(
        string="Proposition de valeur", readonly=True)
    modele_economique = fields.Char(string="Modèle économique", readonly=True)
    maturite = fields.Char(string="Maturité", readonly=True)
    score = fields.Integer(string="Score à la resoumission", readonly=True)
    document_summary = fields.Text(
        string="Pièces jointes",
        readonly=True,
        help="Liste des pièces au moment du figeage. Les fichiers eux-mêmes ne "
             "sont pas dupliqués — ce serait multiplier le stockage sans "
             "apporter d'information sur ce qui a changé.",
    )
    reponse_porteur = fields.Text(string="Réponse du porteur", readonly=True)

    @api.depends('project_id', 'version')
    def _compute_display_name(self):
        for snapshot in self:
            snapshot.display_name = _("%(projet)s — version %(version)s") % {
                'projet': snapshot.project_id.name or '',
                'version': snapshot.version,
            }

    def write(self, vals):
        """Une version figée ne se retouche pas.

        Même raisonnement que le journal d'audit du moteur : une archive
        modifiable ne prouve rien de ce que le dossier contenait.
        """
        if not self.env.su:
            raise UserError(_(
                "Une version archivée du dossier ne peut pas être modifiée."))
        return super().write(vals)
