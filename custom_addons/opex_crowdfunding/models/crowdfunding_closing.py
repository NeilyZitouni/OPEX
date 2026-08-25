from odoo import _, fields, models
from odoo.exceptions import UserError

#: Ce que chaque nature d'opération exige avant d'être close (section 15).
#: Codé en dur : ajouter une huitième nature demande un développeur, une
#: entrée ici, une valeur dans le Selection et un redéploiement. C'est le
#: même branchement que celui du dossier progressif, et il se mesure pareil.
EXIGENCES_PAR_TYPE = {
    'investissement': {
        'documents': ("Convention d'investissement", "Pacte d'associés"),
        'versements': True,
        'reporting': True,
    },
    'partenariat': {
        'documents': ("Convention de partenariat",),
        'versements': False,
        'reporting': True,
    },
    'financement_public': {
        'documents': ("Convention de financement", "Attestation d'éligibilité"),
        'versements': True,
        'reporting': True,
    },
    'sponsoring': {
        'documents': ("Convention de sponsoring",),
        'versements': True,
        'reporting': False,
    },
    'pret': {
        'documents': ("Contrat de prêt", "Échéancier de remboursement"),
        'versements': True,
        'reporting': True,
    },
    'convention': {
        'documents': ("Convention",),
        'versements': False,
        'reporting': True,
    },
    'autre': {
        'documents': (),
        'versements': False,
        'reporting': False,
    },
}


class OpexCrowdfundingClosing(models.Model):
    """L'opération de financement et son suivi (section 15).

    « Le dossier devient alors un projet suivi plutôt qu'une simple
    candidature. » C'est ce modèle qui opère ce changement de nature : après
    lui, le projet a une convention, un échéancier, des engagements et un
    journal de suivi.
    """

    _name = 'opex.crowdfunding.closing'
    _description = "Closing et suivi d'un financement"
    _order = 'id desc'
    _rec_name = 'project_id'

    project_id = fields.Many2one(
        'opex.crowdfunding.project', string="Projet",
        required=True, ondelete='cascade', index=True,
    )
    partner_id = fields.Many2one(
        'res.partner', string="Acteur financier", ondelete='restrict',
        help="Celui avec qui l'opération se conclut.")

    type_operation = fields.Selection([
        ('investissement',     "Investissement"),
        ('partenariat',        "Partenariat"),
        ('financement_public', "Financement public"),
        ('sponsoring',         "Sponsoring"),
        ('pret',               "Prêt"),
        ('convention',         "Convention"),
        ('autre',              "Autre"),
    ], string="Nature de l'opération", required=True)

    montant = fields.Monetary(string="Montant de l'opération",
                              currency_field='currency_id')
    currency_id = fields.Many2one(
        related='project_id.currency_id', string="Devise", readonly=True)

    document_ids = fields.One2many(
        'opex.crowdfunding.closing.document', 'closing_id', string="Documents")
    versement_ids = fields.One2many(
        'opex.crowdfunding.versement', 'closing_id', string="Versements")
    suivi_ids = fields.One2many(
        'opex.crowdfunding.suivi', 'closing_id', string="Suivi post-financement")

    # Signature : confirmation horodatée, pas de cryptographie — hors périmètre
    # assumé, comme sur le Module 1.
    signature_confirmee = fields.Boolean(string="Signature confirmée", readonly=True)
    date_signature = fields.Datetime(string="Date de signature", readonly=True)

    engagements_porteur = fields.Text(string="Engagements du porteur")
    reporting = fields.Text(
        string="Obligations de reporting",
        help="Périodicité et contenu attendu après le financement.")

    # ------------------------------------------------------------------
    def _exigences(self):
        """Ce que la nature de l'opération impose — le branchement, en un point."""
        self.ensure_one()
        return EXIGENCES_PAR_TYPE.get(self.type_operation, EXIGENCES_PAR_TYPE['autre'])

    def action_preparer_dossier(self):
        """Crée les documents attendus par la nature de l'opération.

        Le comité n'a pas à se souvenir qu'un prêt demande un échéancier : la
        nature choisie le dit, et les lignes manquantes apparaissent.
        """
        self.project_id._ensure_ceo()
        Document = self.env['opex.crowdfunding.closing.document']
        for closing in self:
            attendus = closing._exigences()['documents']
            existants = set(closing.document_ids.mapped('name'))
            Document.create([
                {'closing_id': closing.id, 'name': libelle}
                for libelle in attendus if libelle not in existants
            ])
        return True

    def action_confirmer_signature(self):
        """Signature de l'opération : confirmation datée.

        Tous les documents exigés doivent être validés — on ne signe pas une
        opération dont les pièces ne sont pas en règle.
        """
        self.project_id._ensure_ceo()
        for closing in self:
            if closing.signature_confirmee:
                raise UserError(_("Cette opération est déjà signée."))
            manquants = closing._documents_manquants()
            if manquants:
                raise UserError(_(
                    "Ces documents ne sont pas validés :\n%s",
                    "\n".join("— %s" % libelle for libelle in manquants)))
            closing.signature_confirmee = True
            closing.date_signature = fields.Datetime.now()
            closing.project_id.message_post(
                body=_("Opération signée : %s.",
                       closing._label_type_operation()),
                subtype_xmlid='mail.mt_note')
        return True

    def _documents_manquants(self):
        """Libellés des documents exigés qui ne sont pas validés."""
        self.ensure_one()
        valides = set(
            self.document_ids.filtered(lambda d: d.valide).mapped('name'))
        return [libelle for libelle in self._exigences()['documents']
                if libelle not in valides]

    def _label_type_operation(self):
        self.ensure_one()
        return dict(
            self._fields['type_operation']._description_selection(self.env)
        )[self.type_operation]

    def _portal_suivi(self):
        """Ce que le porteur voit de son financement, une fois celui-ci conclu."""
        self.ensure_one()
        return {
            'operation': self._label_type_operation(),
            'montant': self.montant,
            'devise': self.currency_id,
            'signature_confirmee': self.signature_confirmee,
            'date_signature': self.date_signature,
            'engagements': self.engagements_porteur or '',
            'reporting': self.reporting or '',
            'versements': [
                {
                    'libelle': versement.name,
                    'montant': versement.montant,
                    'date_prevue': versement.date_prevue,
                    'etat': versement._label_state(),
                    'verse': versement.state == 'verse',
                }
                for versement in self.versement_ids
            ],
            'suivi': [
                {
                    'date': entree.date,
                    'libelle': entree.name,
                    'commentaire': entree.commentaire or '',
                }
                for entree in self.suivi_ids
            ],
        }
