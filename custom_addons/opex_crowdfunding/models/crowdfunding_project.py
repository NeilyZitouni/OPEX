from odoo import _, fields, models
from odoo.exceptions import UserError


class OpexCrowdfundingProject(models.Model):
    """Le dossier Smart Crowdfunding, du dépôt express au closing.

    C'est ici que le workflow est codé en dur — un `Selection` d'états et, au
    fil des extensions, une méthode Python par transition. C'est assumé : le
    module générique construit le même processus par configuration, et la
    comparaison des deux est le livrable du stage.
    """

    _name = 'opex.crowdfunding.project'
    _description = "Projet Smart Crowdfunding"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    # ------------------------------------------------------------------
    # Le workflow
    # ------------------------------------------------------------------
    # Les codes sont identiques à ceux configurés dans le module générique :
    # c'est ce qui rendra la comparaison finale possible sans ambiguïté.
    # Les seize valeurs couvrent les dix étapes du document ; les extensions
    # suivantes ajoutent les méthodes de transition, pas des états.
    state = fields.Selection([
        ('draft',              "Brouillon"),
        ('depot_express',      "Demande déposée"),
        ('pre_analyse',        "Pré-analyse"),
        ('clarification',      "Clarification demandée"),
        ('dossier_progressif', "Dossier à compléter"),
        ('quality_gate',       "Contrôle qualité"),
        ('quality_complement', "Complément demandé"),
        ('etude_decision',     "Étude CEO"),
        ('accompagnement',     "Accompagnement CEO"),
        ('reevaluation',       "Réévaluation"),
        ('matching_financier', "Matching financier"),
        ('mise_en_relation',   "Mise en relation"),
        ('decision_financeur', "Décision de l'acteur financier"),
        ('closing',            "Closing"),
        ('closed',             "Clôturé"),
        ('rejected',           "Non retenu"),
    ], string="État", default='draft', required=True, tracking=True, index=True)

    # ------------------------------------------------------------------
    # Dépôt Express — section 5 du document
    # ------------------------------------------------------------------
    # Progressive commitment : on ne demande que le minimum nécessaire pour
    # décider de l'étape suivante. Les champs du dossier complet (business
    # model, marché, traction, valorisation…) n'ont rien à faire ici — ils
    # arrivent à l'Extension 4, et uniquement après un GO.
    #
    # Seuls `partner_id` et `name` sont obligatoires au niveau de l'ORM : le
    # portail (Extension 2) crée le brouillon dès la première étape du
    # formulaire puis le complète par `write()` partiels. Les autres
    # informations minimales sont exigées à la soumission, par
    # `action_submit()`, et non à la création.
    partner_id = fields.Many2one(
        'res.partner', string="Porteur", required=True, tracking=True,
        index=True, ondelete='restrict',
    )
    porteur_type = fields.Selection([
        ('physique',     "Personne physique"),
        ('startup',      "Startup"),
        ('entreprise',   "Entreprise"),
        ('groupe',       "Groupe"),
        ('association',  "Association"),
        ('autre_morale', "Autre personne morale"),
    ], string="Type de porteur", tracking=True)

    name = fields.Char(string="Titre du projet", required=True, tracking=True)
    probleme = fields.Text(string="Problème / opportunité")
    solution = fields.Text(string="Solution proposée")

    # Référentiels codés en dur, à l'inverse du module générique : ajouter un
    # secteur ou un palier de maturité demande ici une modification du code et
    # une mise à jour du module. C'est une des mesures du document de
    # comparaison.
    secteur = fields.Selection([
        ('agroalimentaire', "Agroalimentaire"),
        ('industrie',       "Industrie & manufacturing"),
        ('energie',         "Énergie & renouvelables"),
        ('numerique',       "Numérique & TIC"),
        ('sante',           "Santé"),
        ('transport',       "Transport & logistique"),
        ('btp',             "BTP & construction"),
        ('environnement',   "Environnement & économie circulaire"),
        ('services',        "Services"),
        ('formation',       "Éducation & formation"),
        ('autre',           "Autre"),
    ], string="Secteur", tracking=True)
    maturite = fields.Selection([
        ('idee',            "Idée"),
        ('prototype',       "Prototype"),
        ('mvp',             "MVP / produit minimum"),
        ('premiers_client', "Premiers clients"),
        ('croissance',      "Croissance"),
    ], string="Maturité actuelle", tracking=True)

    # Le besoin recherché commande le questionnaire du dossier progressif
    # (Extension 4, section 7 du document) : investisseur, sponsor et
    # financement public y reçoivent trois formulaires différents. Les trois
    # valeurs ci-dessous sont donc exactement les trois branches à venir —
    # ajouter un quatrième besoin obligera à toucher ce Selection, le modèle,
    # un template et une condition d'affichage. Ce coût-là sera mesuré, pas
    # estimé.
    besoin_type = fields.Selection([
        ('investisseur',      "Investisseur / actionnaire"),
        ('sponsor',           "Sponsor / mécène"),
        ('financement_public', "Financement public"),
    ], string="Besoin recherché", tracking=True)
    montant_indicatif = fields.Monetary(
        string="Montant indicatif", currency_field='currency_id',
        help="Facultatif au dépôt : une fourchette suffit à orienter la pré-analyse.",
    )
    currency_id = fields.Many2one(
        'res.currency', string="Devise",
        default=lambda self: self.env.company.currency_id.id,
    )

    pitch_document = fields.Binary(string="Document / pitch (facultatif)", attachment=True)
    pitch_filename = fields.Char(string="Nom du fichier")

    # ------------------------------------------------------------------
    # Les deux champs du benchmark
    # ------------------------------------------------------------------
    # Portent les mêmes noms que dans le module générique : le test final
    # (section 18 — l'étape Demo Day exige l'accord du CEO et une note ≥ 70)
    # s'appuie sur eux des deux côtés. Ils sont déclarés dès maintenant pour
    # que le vocabulaire commun soit fixé avant que quiconque n'improvise.
    score = fields.Integer(string="Score", tracking=True, help="Note du dossier, sur 100.")
    ceo_approval = fields.Boolean(string="Accord CEO", tracking=True)

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------
    # Une méthode par transition, nommée d'après l'issue métier et non d'après
    # l'état d'arrivée. Aucune méthode générique `_do_transition(state)` : le
    # coût d'une issue supplémentaire doit rester visible.

    #: Informations minimales exigées à la soumission (section 5).
    _CHAMPS_DEPOT_EXPRESS = (
        'porteur_type', 'probleme', 'solution', 'secteur', 'maturite', 'besoin_type',
    )

    def action_submit(self):
        """Dépôt express : `draft` → `depot_express`."""
        for project in self:
            if project.state != 'draft':
                raise UserError(_(
                    "Ce projet a déjà été déposé : il est à l'état « %s ».",
                    project._state_label(),
                ))
            manquants = project._champs_depot_manquants()
            if manquants:
                raise UserError(_(
                    "Complétez ces informations avant de présenter votre projet :\n%s",
                    "\n".join("— %s" % libelle for libelle in manquants),
                ))
            project.state = 'depot_express'
            project.message_post(
                body=_("Projet présenté par %s.", project.partner_id.display_name),
                subtype_xmlid='mail.mt_note',
            )
        return True

    # ------------------------------------------------------------------
    # Utilitaires
    # ------------------------------------------------------------------
    def _champs_depot_manquants(self):
        """Libellés des informations minimales encore absentes du dossier."""
        self.ensure_one()
        descriptions = self.fields_get(self._CHAMPS_DEPOT_EXPRESS, ['string'])
        return [
            descriptions[nom]['string']
            for nom in self._CHAMPS_DEPOT_EXPRESS
            if not self[nom]
        ]

    def _state_label(self):
        """Libellé lisible de l'état courant.

        Le porteur ne doit jamais voir un code d'état (section 16) : cette
        méthode est le seul endroit qui traduit, et le portail s'en sert.
        """
        self.ensure_one()
        return dict(self._fields['state']._description_selection(self.env))[self.state]
