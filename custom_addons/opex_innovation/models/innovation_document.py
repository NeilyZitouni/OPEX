from odoo import fields, models


class InnovationProfileDocument(models.Model):
    """Justificatif joint à une demande de profil.

    Un modèle plutôt qu'un `Many2many('ir.attachment')` : une pièce n'est pas
    qu'un fichier, elle a un *type*, et c'est ce type qui permet au contrôleur
    de dire « il manque le CV » plutôt que de compter des fichiers. Même
    raisonnement que sur les pièces du dossier d'adhésion du Module 1.

    Le champ est nommé `document_type` et la collection `document_ids` : ce sont
    les conventions que `has_document()` du moteur reconnaît par défaut. Une
    condition de workflow peut donc s'écrire `has_document('cv')` sans une
    ligne de Python.
    """

    _name = 'opex.innovation.profile.document'
    _description = "Justificatif de profil"
    _order = 'document_type, id'

    name = fields.Char(string="Libellé", required=True)
    document_type = fields.Selection(
        [
            ('cv', "CV"),
            ('diplome', "Diplôme"),
            ('certification', "Certification"),
            ('attestation', "Attestation"),
            ('portfolio', "Portfolio"),
            ('reference', "Référence professionnelle"),
            ('autre', "Autre justificatif"),
        ],
        string="Type",
        required=True,
        default='autre',
    )
    file = fields.Binary(string="Fichier", attachment=True, required=True)
    filename = fields.Char(string="Nom du fichier")

    expert_profile_id = fields.Many2one(
        'opex.innovation.expert.profile',
        string="Profil expert",
        ondelete='cascade',
        index=True,
    )
    investor_profile_id = fields.Many2one(
        'opex.innovation.investor.profile',
        string="Profil investisseur",
        ondelete='cascade',
        index=True,
    )
