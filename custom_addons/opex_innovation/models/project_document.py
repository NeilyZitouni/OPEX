import base64

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class InnovationDocument(models.Model):
    """Pièce jointe d'un projet — section 9.

    « Le système doit contrôler : extension, taille, fichier vide, doublons
    éventuels. » Les quatre contrôles sont ici, en `@api.constrains` : au
    niveau du modèle et non du formulaire, pour qu'un dépôt par le portail, par
    le back-office ou par une requête forgée passe par les mêmes règles.
    """

    _name = 'opex.innovation.document'
    _description = "Pièce jointe d'un projet d'innovation"
    _order = 'project_id, document_type, version desc, id'

    #: Extensions acceptées par type. Une table plutôt que des `if` : ajouter
    #: un type est une ligne, et la règle se lit d'un coup d'œil.
    ALLOWED_EXTENSIONS = {
        'business_plan': ('pdf', 'doc', 'docx'),
        'pitch_deck': ('pdf', 'ppt', 'pptx'),
        'mvp': ('pdf', 'ppt', 'pptx', 'zip', 'png', 'jpg', 'jpeg'),
        'video': ('mp4', 'mov', 'avi', 'mkv'),
        'prototype': ('pdf', 'zip', 'png', 'jpg', 'jpeg'),
        'etude_marche': ('pdf', 'doc', 'docx', 'xls', 'xlsx'),
        'previsions_financieres': ('pdf', 'xls', 'xlsx', 'csv'),
        'brevet': ('pdf',),
        'poc': ('pdf', 'zip', 'ppt', 'pptx'),
        'presentation_technique': ('pdf', 'ppt', 'pptx', 'doc', 'docx'),
        'autre': (),  # tuple vide = aucune restriction
    }

    #: 25 Mo. Au-delà, la pièce n'est pas refusée par principe mais parce
    #: qu'elle ne traversera pas correctement le portail.
    MAX_SIZE_BYTES = 25 * 1024 * 1024

    #: Types dont un seul exemplaire a un sens. Le pitch deck se remplace, il
    #: ne s'accumule pas — sauf en versions successives, que `version` porte.
    UNIQUE_TYPES = ('business_plan', 'pitch_deck', 'video')

    project_id = fields.Many2one(
        'opex.innovation.project',
        string="Projet",
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(string="Libellé", required=True)
    document_type = fields.Selection(
        [
            ('business_plan', "Business Plan"),
            ('pitch_deck', "Pitch Deck"),
            ('mvp', "Présentation du MVP"),
            ('video', "Vidéo de démonstration"),
            ('prototype', "Prototype"),
            ('etude_marche', "Étude de marché"),
            ('previsions_financieres', "Prévisions financières"),
            ('brevet', "Brevet"),
            ('poc', "Preuve de concept"),
            ('presentation_technique', "Présentation technique"),
            ('autre', "Autre document"),
        ],
        string="Type de pièce",
        required=True,
        default='autre',
        index=True,
    )
    file = fields.Binary(string="Fichier", attachment=True)
    filename = fields.Char(string="Nom du fichier")
    url = fields.Char(
        string="Lien",
        help="Alternative au fichier pour la vidéo de démonstration : le PDF "
             "prévoit « Ajouter un lien » aussi bien qu'« Ajouter une vidéo ».",
    )
    version = fields.Integer(string="Version", default=1)
    description = fields.Text(string="Description")

    @api.depends('name', 'document_type')
    def _compute_display_name(self):
        labels = dict(self._fields['document_type'].selection)
        for document in self:
            document.display_name = "%s — %s" % (
                labels.get(document.document_type, ''), document.name or '')

    # ------------------------------------------------------------
    # Les quatre contrôles de la section 9
    # ------------------------------------------------------------

    def _extension(self):
        self.ensure_one()
        if not self.filename or '.' not in self.filename:
            return ''
        return self.filename.rsplit('.', 1)[-1].lower()

    @api.constrains('file', 'url', 'filename', 'document_type')
    def _check_document(self):
        for document in self:
            document._check_has_content()
            document._check_not_empty()
            document._check_extension()
            document._check_size()

    def _check_has_content(self):
        """Une pièce sans fichier **ni** lien ne prouve rien.

        Deux messages et non un : au niveau d'un champ Binary, un fichier vide
        arrive indistinctement d'un fichier absent — les deux valent `False`.
        La présence d'un nom de fichier tranche : l'utilisateur a bien déposé
        quelque chose, et lui dire « aucun fichier » l'enverrait chercher un
        problème qui n'est pas le sien.
        """
        self.ensure_one()
        if self.file or self.url:
            return
        if self.filename:
            raise UserError(_(
                "Le fichier « %(file)s » déposé pour la pièce « %(name)s » est "
                "vide."
            ) % {'file': self.filename, 'name': self.name})
        raise UserError(_(
            "La pièce « %s » n'a ni fichier ni lien. Déposez un fichier ou "
            "indiquez un lien."
        ) % self.name)

    def _check_not_empty(self):
        """Fichier vide : le cas que le navigateur laisse passer sans rien dire."""
        self.ensure_one()
        if not self.file:
            return
        try:
            size = len(base64.b64decode(self.file))
        except Exception:  # noqa: BLE001 — donnée illisible = donnée refusée
            raise UserError(_(
                "Le fichier de la pièce « %s » est illisible.") % self.name)
        if size == 0:
            raise UserError(_(
                "Le fichier de la pièce « %s » est vide.") % self.name)

    def _check_extension(self):
        self.ensure_one()
        allowed = self.ALLOWED_EXTENSIONS.get(self.document_type, ())
        if not allowed or not self.file:
            return
        extension = self._extension()
        if extension and extension not in allowed:
            raise UserError(_(
                "La pièce « %(name)s » est un fichier .%(ext)s. Les formats "
                "acceptés pour ce type sont : %(allowed)s."
            ) % {
                'name': self.name,
                'ext': extension,
                'allowed': ", ".join(".%s" % ext for ext in allowed),
            })

    def _check_size(self):
        self.ensure_one()
        if not self.file:
            return
        size = len(base64.b64decode(self.file))
        if size > self.MAX_SIZE_BYTES:
            raise UserError(_(
                "La pièce « %(name)s » pèse %(size).1f Mo. La limite est de "
                "%(max)s Mo."
            ) % {
                'name': self.name,
                'size': size / (1024 * 1024),
                'max': self.MAX_SIZE_BYTES // (1024 * 1024),
            })

    @api.constrains('project_id', 'document_type', 'version')
    def _check_no_duplicate(self):
        """Doublons : un second business plan à la même version est une erreur.

        Contrôle Python et non contrainte SQL : `version` doit pouvoir
        s'incrémenter — une nouvelle version du pitch deck est légitime, un
        second pitch deck de version 1 ne l'est pas.
        """
        labels = dict(self._fields['document_type'].selection)
        for document in self:
            if document.document_type not in self.UNIQUE_TYPES:
                continue
            duplicate = self.search_count([
                ('id', '!=', document.id),
                ('project_id', '=', document.project_id.id),
                ('document_type', '=', document.document_type),
                ('version', '=', document.version),
            ])
            if duplicate:
                raise UserError(_(
                    "Une pièce « %(type)s » en version %(version)s existe déjà "
                    "sur ce projet. Incrémentez la version ou remplacez la "
                    "pièce existante."
                ) % {
                    'type': labels.get(document.document_type, ''),
                    'version': document.version,
                })
