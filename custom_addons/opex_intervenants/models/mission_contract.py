from odoo import _, api, fields, models

#: Référence de pièce contractuelle, séquence semée en data.
CONTRACT_SEQUENCE = 'opex.mission.contract'
NEW_REFERENCE = "Nouveau"


class MissionContract(models.Model):
    """Une pièce contractuelle : contrat, NDA ou ordre de mission — §18, §19.

    **Aucun champ `state`.** Le cycle de validation du §19 est le
    sous-workflow `mission_contract`, qui tourne sur la **mission** — pas sur
    cette pièce. La raison n'est pas doctrinale, elle est mécanique :

    `rule_mission_contract_validated` est écrite `subworkflow_done(
    'mission_contract')`, et `_subworkflow_done()` cherche une instance par
    `res_model` / `res_id` (`workflow_instance.py:305`). Une définition posée
    sur `opex.mission.contract` ne serait jamais vue par l'instance de la
    mission, et la règle 5 du §39 serait fausse pour toujours — sans que rien
    ne le signale, puisque le helper est tolérant et renvoie `False`.

    Ce que porte la pièce, ce sont donc des **faits** — elle existe, elle est
    signée des deux côtés — jamais une position dans un processus. La
    différence se voit à ceci : un fait est constaté, un état est décidé.

    §19 « Chaque version doit pouvoir être tracée » : une révision ne réécrit
    pas la pièce, elle en crée une nouvelle avec `version + 1`. Les
    précédentes restent lisibles, et c'est `current_version` qui distingue la
    pièce en vigueur.
    """

    _name = 'opex.mission.contract'
    _description = "Pièce contractuelle d'une mission"
    _inherit = ['mail.thread']
    _order = 'assignment_id, contract_type, version desc, id desc'

    name = fields.Char(
        string="Référence",
        required=True,
        copy=False,
        readonly=True,
        default=NEW_REFERENCE,
        index=True,
    )
    assignment_id = fields.Many2one(
        'opex.mission.assignment',
        string="Affectation",
        required=True,
        ondelete='cascade',
        index=True,
    )
    mission_id = fields.Many2one(
        related='assignment_id.mission_id',
        string="Appel à mission",
        store=True,
        readonly=True,
        index=True,
    )
    partner_id = fields.Many2one(
        related='assignment_id.partner_id',
        string="Intervenant",
        store=True,
        readonly=True,
    )
    client_id = fields.Many2one(
        related='mission_id.client_id', string="Client", readonly=True)

    contract_type = fields.Selection(
        [
            ('contrat', "Contrat de prestation"),
            ('nda', "Accord de confidentialité (NDA)"),
            ('ordre_mission', "Ordre de mission"),
        ],
        string="Nature de la pièce",
        required=True,
        default='contrat',
        index=True,
    )
    version = fields.Integer(string="Version", default=1, required=True)
    current_version = fields.Boolean(
        string="Version en vigueur",
        default=True,
        help="Décochée lorsqu'une révision produit une version plus récente. "
             "La pièce reste lisible : le §19 exige que chaque version soit "
             "traçable.",
    )

    # --- Le contenu repris du §18 -------------------------------------------
    date_debut = fields.Date(string="Début de la mission")
    date_fin = fields.Date(string="Fin de la mission")
    duree_jours = fields.Integer(string="Durée (jours)")
    currency_id = fields.Many2one(
        related='assignment_id.currency_id', readonly=True)
    montant = fields.Monetary(string="Montant", currency_field='currency_id')
    objet = fields.Text(string="Objet de la mission")
    livrables = fields.Text(string="Livrables attendus")
    conditions = fields.Text(string="Conditions particulières")
    modalites_validation = fields.Text(string="Modalités de validation")

    # --- Signature ----------------------------------------------------------
    #
    # Confirmation horodatée et nominative, comme sur les deux modules
    # précédents. La signature cryptographique est hors périmètre, déclarée
    # comme telle, et le modèle n'y ferme aucune porte : trois champs de plus
    # et le mécanisme change sans que le workflow bouge.
    signature_client = fields.Boolean(string="Signé par le client")
    signature_client_nom = fields.Char(string="Signataire client")
    signature_client_date = fields.Datetime(string="Date de signature client")
    signature_intervenant = fields.Boolean(string="Signé par l'intervenant")
    signature_intervenant_nom = fields.Char(string="Signataire intervenant")
    signature_intervenant_date = fields.Datetime(
        string="Date de signature intervenant")

    is_signed = fields.Boolean(
        string="Signé des deux côtés",
        compute='_compute_is_signed',
        help="Un fait constaté sur la pièce, pas une étape : l'étape est celle "
             "du sous-workflow de contractualisation, sur la mission.",
    )

    document = fields.Binary(string="Pièce signée", attachment=True)
    document_filename = fields.Char(string="Nom du fichier")
    active = fields.Boolean(string="Actif", default=True)

    # ------------------------------------------------------------
    # Calculs
    # ------------------------------------------------------------

    @api.depends('signature_client', 'signature_intervenant')
    def _compute_is_signed(self):
        for contract in self:
            contract.is_signed = bool(
                contract.signature_client and contract.signature_intervenant)

    @api.depends('name', 'contract_type', 'version')
    def _compute_display_name(self):
        labels = dict(self._fields['contract_type'].selection)
        for contract in self:
            contract.display_name = "%s — %s (v%s)" % (
                contract.name or NEW_REFERENCE,
                labels.get(contract.contract_type, ''),
                contract.version,
            )

    # ------------------------------------------------------------
    # Création
    # ------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', NEW_REFERENCE) == NEW_REFERENCE:
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code(
                    CONTRACT_SEQUENCE) or NEW_REFERENCE
        return super().create(vals_list)

    # ------------------------------------------------------------
    # Signature depuis le back-office
    # ------------------------------------------------------------
    #
    # Deux boutons, et **aucune transition déclenchée depuis ici**. Signer est
    # un fait à consigner ; ce qu'on en tire est l'affaire du workflow, dont la
    # transition « Signature recueillie » porte la condition qui lit ces
    # champs. Enchaîner automatiquement ferait décider le modèle à la place du
    # responsable, et rendrait la transition inutile.

    def action_sign_client(self):
        self.ensure_one()
        self.write({
            'signature_client': True,
            'signature_client_nom': self.env.user.display_name,
            'signature_client_date': fields.Datetime.now(),
        })
        self.message_post(body=_(
            "Signature du client enregistrée : %s.") % self.env.user.display_name)
        return True

    def action_sign_intervenant(self):
        self.ensure_one()
        self.write({
            'signature_intervenant': True,
            'signature_intervenant_nom': self.env.user.display_name,
            'signature_intervenant_date': fields.Datetime.now(),
        })
        self.message_post(body=_(
            "Signature de l'intervenant enregistrée : %s."
        ) % self.env.user.display_name)
        return True

    # ------------------------------------------------------------
    # Aperçu
    # ------------------------------------------------------------

    def action_preview_html(self):
        """Ouvre le rendu HTML du rapport, sans passer par wkhtmltopdf.

        `wkhtmltopdf` n'est pas installé sur le poste de développement :
        `ir_actions_report.py:868` lève « Unable to find Wkhtmltopdf » dès
        qu'on demande le PDF. Les deux rapports restent déclarés en `qweb-pdf`
        — c'est leur forme juste, et ils produiront un PDF le jour où le
        binaire sera là. En attendant, la route native `/report/html/...`
        rend exactement le même gabarit et ne demande rien.

        Même catégorie que le SMTP absent : une limite de poste, pas un défaut
        du module.
        """
        self.ensure_one()
        report = (
            'opex_intervenants.report_mission_contract_document'
            if self.contract_type != 'ordre_mission'
            else 'opex_intervenants.report_mission_order_document'
        )
        return {
            'type': 'ir.actions.act_url',
            'url': '/report/html/%s/%s' % (report, self.id),
            'target': 'new',
        }
