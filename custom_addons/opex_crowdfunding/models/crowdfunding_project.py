from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


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
        ('demo_day',           "Demo Day"),
        ('matching_financier', "Matching financier"),
        ('mise_en_relation',   "Mise en relation"),
        ('decision_financeur', "Décision de l'acteur financier"),
        ('closing',            "Closing"),
        ('closed',             "Clôturé"),
        ('rejected',           "Non retenu"),
    ], string="État", default='draft', required=True, tracking=True, index=True)

    #: Les états qui font sortir un dossier du pipeline : pas encore entré, ou
    #: sorti. Tout le reste y est — y compris l'accompagnement.
    _ETATS_HORS_PIPELINE = ('draft', 'rejected', 'closed')

    in_pipeline = fields.Boolean(
        string="Dans le pipeline", compute='_compute_in_pipeline',
        store=True, index=True,
        help="Un dossier déposé et non clos. Les tableaux de bord s'appuient "
             "dessus : un projet en maturation y reste, un projet non retenu "
             "en sort.",
    )

    @api.depends('state')
    def _compute_in_pipeline(self):
        """« Un projet intéressant mais insuffisamment mature reste dans le
        pipeline » (section 9).

        Un seul endroit définit ce qu'est « être dans le pipeline », et les
        écrans s'y réfèrent : sans ça, chaque tableau de bord recopierait sa
        propre liste d'états et l'un d'eux finirait par ranger la maturation
        avec les refus.
        """
        for project in self:
            project.in_pipeline = project.state not in self._ETATS_HORS_PIPELINE

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
    # Dossier progressif — section 7
    # ------------------------------------------------------------------
    # Demandé uniquement après un GO, et son contenu dépend du besoin :
    # « Étape → Type de projet → Type de financement → Formulaire dynamique. »
    #
    # En version texto, « formulaire dynamique » veut dire trois groupes de
    # champs, trois gabarits et une condition sur `besoin_type`. Les noms du
    # groupe investisseur sont ceux du document ; les deux autres
    # questionnaires, que le document laisse à déduire, sont préfixés pour
    # qu'on voie d'un coup d'œil à quelle branche appartient chaque champ.

    # Branche 1 — investisseur (liste explicite de la section 7)
    business_model = fields.Text(string="Business model")
    marche = fields.Text(string="Marché")
    traction = fields.Text(string="Traction")
    equipe = fields.Text(string="Équipe")
    besoin_financier = fields.Monetary(
        string="Besoin financier", currency_field='currency_id')
    utilisation_fonds = fields.Text(string="Utilisation des fonds")
    valorisation = fields.Monetary(
        string="Valorisation envisagée", currency_field='currency_id',
        help="Facultative : le document la dit « éventuelle ».")
    previsions_financieres = fields.Text(string="Prévisions financières")
    pitch_deck = fields.Binary(string="Pitch deck", attachment=True)
    pitch_deck_filename = fields.Char(string="Nom du pitch deck")

    # Branche 2 — sponsor : ce qu'un sponsor finance n'est pas une part du
    # capital mais une opération et sa visibilité.
    sponsor_objectif = fields.Text(string="Objet du sponsoring")
    sponsor_public_cible = fields.Text(string="Public touché")
    sponsor_visibilite = fields.Text(string="Visibilité offerte au sponsor")
    sponsor_retombees = fields.Text(string="Retombées attendues")
    sponsor_budget = fields.Monetary(
        string="Budget de l'opération", currency_field='currency_id')
    sponsor_calendrier = fields.Text(string="Calendrier de l'opération")
    sponsor_partenaires = fields.Text(string="Partenaires déjà engagés")
    sponsor_document = fields.Binary(string="Dossier de sponsoring", attachment=True)
    sponsor_document_filename = fields.Char(string="Nom du dossier de sponsoring")

    # Branche 3 — financement public : un dispositif, une éligibilité, un
    # plan de financement et des obligations réglementaires.
    public_dispositif = fields.Text(string="Dispositif public visé")
    public_eligibilite = fields.Text(string="Éligibilité au dispositif")
    public_montant = fields.Monetary(
        string="Montant demandé", currency_field='currency_id')
    public_plan_financement = fields.Text(
        string="Plan de financement",
        help="Apport propre, cofinancements, emprunts déjà obtenus.")
    public_impact = fields.Text(string="Impact socio-économique")
    public_conformite = fields.Text(string="Conformité réglementaire")
    public_calendrier = fields.Text(string="Calendrier d'exécution")
    public_document = fields.Binary(string="Dossier administratif", attachment=True)
    public_document_filename = fields.Char(string="Nom du dossier administratif")

    # ------------------------------------------------------------------
    # Pré-analyse — section 6
    # ------------------------------------------------------------------
    prequalification_ids = fields.One2many(
        'opex.crowdfunding.prequalification', 'project_id', string="Pré-analyses")
    quality_control_ids = fields.One2many(
        'opex.crowdfunding.quality.control', 'project_id', string="Contrôles qualité")
    matching_candidate_ids = fields.One2many(
        'opex.crowdfunding.matching.candidate', 'project_id',
        string="Candidats au financement")
    accompagnement_ids = fields.One2many(
        'opex.crowdfunding.accompagnement', 'project_id', string="Accompagnements")
    relation_ids = fields.One2many(
        'opex.crowdfunding.relation', 'project_id', string="Mises en relation")
    closing_ids = fields.One2many(
        'opex.crowdfunding.closing', 'project_id', string="Closing")

    # Le dernier avis rendu, remonté sur le projet : le comité étudie un
    # dossier, il ne va pas chercher la fiche de contrôle dans un autre écran.
    avis_qualite = fields.Selection(
        selection=lambda self: self.env[
            'opex.crowdfunding.quality.control']._fields['avis'].selection,
        string="Avis du contrôle qualité", compute='_compute_avis_qualite',
    )
    anomalies_qualite = fields.Text(
        string="Anomalies relevées au contrôle", compute='_compute_avis_qualite')

    @api.depends('quality_control_ids.avis', 'quality_control_ids.date')
    def _compute_avis_qualite(self):
        # `sorted('id')[-1]` et pas `[0]` : l'ordre d'un One2many déjà en cache
        # ne suit pas forcément le `_order` du comodèle. S'en remettre à lui,
        # c'est afficher au comité l'avis de l'avant-dernier contrôle un jour
        # sur deux.
        for project in self:
            rendus = project.quality_control_ids.filtered(lambda c: c.date)
            dernier = rendus.sorted('id')[-1] if rendus else False
            project.avis_qualite = dernier.avis if dernier else False
            project.anomalies_qualite = dernier.anomalies if dernier else False
    clarification_ids = fields.One2many(
        'opex.crowdfunding.clarification', 'project_id', string="Clarifications")

    # Le motif d'un refus est exigé à deux endroits du parcours : ici en NO GO
    # (section 6) et en route C de l'étude CEO (section 9). Un seul champ, donc,
    # plutôt qu'un par étape — « un projet non retenu » se motive de la même
    # manière quel que soit le moment où on le décide.
    motif_rejet = fields.Text(string="Motif du refus", tracking=True)

    # ------------------------------------------------------------------
    # Création
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        """Un porteur portail ne présente de projet qu'en son propre nom.

        Le formulaire de `/my/crowdfunding/new` est rempli côté navigateur : ni
        `partner_id` ni `state` ne peuvent en venir. Les réécrire ici, plutôt
        que de se contenter de ne pas les afficher, ferme la porte à une
        requête forgée qui déposerait un projet au nom d'un autre contact — ou
        déjà passé le dépôt express.
        """
        if self.env.user._is_portal():
            partner_id = self.env.user.partner_id.id
            for vals in vals_list:
                vals['partner_id'] = partner_id
                vals['state'] = 'draft'
        projects = super().create(vals_list)
        # Un seul abonnement, à la création : le porteur suit son projet pour
        # toute sa vie. Le refaire à chaque transition dupliquerait l'abonné.
        for project in projects:
            if project.partner_id:
                project.sudo().message_subscribe(partner_ids=project.partner_id.ids)
        return projects

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

    def action_start_pre_analyse(self):
        """Prise en charge par le comité CEO : `depot_express` → `pre_analyse`.

        Le document fait démarrer l'étape 2 sans dire qui l'ouvre : sans cette
        transition, un dossier déposé resterait indéfiniment en « Demande
        déposée » et la pré-analyse n'aurait pas de porte d'entrée. Elle crée
        la fiche de pré-analyse que le comité remplira.
        """
        self._ensure_ceo()
        for project in self:
            if project.state != 'depot_express':
                raise UserError(_(
                    "Seule une demande déposée peut entrer en pré-analyse ; "
                    "celle-ci est à l'état « %s ».", project._state_label()))
            project.state = 'pre_analyse'
            project.prequalification_ids.create({'project_id': project.id})
            project.message_post(
                body=_("Pré-analyse ouverte par %s.", self.env.user.display_name),
                subtype_xmlid='mail.mt_note',
            )
        return True

    # ------------------------------------------------------------------
    # Les quatre issues de la pré-analyse — section 6
    # ------------------------------------------------------------------
    # Quatre méthodes, une par issue. Pas de `action_prequalify(resultat)` :
    # chacune porte ses propres préconditions, son propre état d'arrivée et
    # son propre message. La répétition des quatre lignes qui horodatent la
    # préqualification est délibérée — c'est exactement ce que coûterait une
    # cinquième issue, et c'est ce que le document de comparaison doit
    # pouvoir mesurer sans qu'on l'estime à la louche.

    def action_go(self):
        """GO : le dossier poursuit. → `dossier_progressif`."""
        self._ensure_ceo()
        for project in self:
            project._ensure_pre_analyse()
            prequalification = project._current_prequalification()
            prequalification.resultat = 'go'
            prequalification.evaluated_by_id = self.env.user
            prequalification.date = fields.Datetime.now()
            project.state = 'dossier_progressif'
            project.message_post(
                body=_("Pré-analyse : GO. Le porteur est invité à compléter son dossier."),
                subtype_xmlid='mail.mt_comment',
            )
        return True

    def action_clarify(self):
        """À CLARIFIER : 1..N questions ciblées partent au porteur.

        → `clarification`. Le dossier n'est ni retenu ni écarté : il manque une
        information précise, et c'est tout ce qu'on demande.
        """
        self._ensure_ceo()
        for project in self:
            project._ensure_pre_analyse()
            questions = project.clarification_ids.filtered(lambda c: c.state == 'draft')
            if not questions:
                raise UserError(_(
                    "Posez au moins une question ciblée avant de demander une "
                    "clarification au porteur."))
            prequalification = project._current_prequalification()
            prequalification.resultat = 'clarify'
            prequalification.evaluated_by_id = self.env.user
            prequalification.date = fields.Datetime.now()
            questions.state = 'asked'
            project.state = 'clarification'
            project.message_post(
                body=_("Pré-analyse : %s question(s) de clarification adressée(s) "
                       "au porteur.", len(questions)),
                subtype_xmlid='mail.mt_comment',
            )
        return True

    def action_no_go(self):
        """NO GO : clôture motivée. → `rejected`."""
        self._ensure_ceo()
        for project in self:
            project._ensure_pre_analyse()
            if not (project.motif_rejet or '').strip():
                raise UserError(_(
                    "Un refus se motive : renseignez le motif avant de clôturer "
                    "le dossier."))
            prequalification = project._current_prequalification()
            prequalification.resultat = 'no_go'
            prequalification.evaluated_by_id = self.env.user
            prequalification.date = fields.Datetime.now()
            project.state = 'rejected'
            project.message_post(
                body=_("Pré-analyse : NO GO. Motif : %s", project.motif_rejet),
                subtype_xmlid='mail.mt_note',
            )
            # Deux messages, et c'est délibéré : le motif reste au dossier
            # d'instruction, le porteur reçoit la décision. Si le comité veut
            # lui transmettre le motif, c'est une ligne à changer ici — pas
            # une politique à deviner dans le code.
            project.message_post(
                body=_("Après examen, votre projet n'a pas été retenu."),
                subtype_xmlid='mail.mt_comment',
            )
        return True

    def action_orientation(self):
        """ORIENTATION : maturation conseillée. → `accompagnement`.

        Ce n'est pas un refus déguisé : le projet reste dans le pipeline, il
        est seulement orienté vers un accompagnement avant d'aller plus loin.
        """
        self._ensure_ceo()
        for project in self:
            project._ensure_pre_analyse()
            prequalification = project._current_prequalification()
            prequalification.resultat = 'orientation'
            prequalification.evaluated_by_id = self.env.user
            prequalification.date = fields.Datetime.now()
            project.state = 'accompagnement'
            project.message_post(
                body=_("Pré-analyse : orientation vers un accompagnement CEO "
                       "avant poursuite du parcours."),
                subtype_xmlid='mail.mt_comment',
            )
        return True

    def action_clarifications_answered(self):
        """Le porteur a répondu : `clarification` → `pre_analyse`.

        Déclenchée par le porteur depuis son portail, donc sans contrôle de
        groupe CEO — mais avec la règle métier : on ne renvoie pas au comité un
        questionnaire à moitié rempli.
        """
        for project in self:
            if project.state != 'clarification':
                raise UserError(_(
                    "Ce projet n'attend pas de clarification : il est à l'état "
                    "« %s ».", project._state_label()))
            restantes = project.clarification_ids.filtered(lambda c: c.state == 'asked')
            if restantes:
                raise UserError(_(
                    "Répondez à toutes les questions du comité avant de renvoyer "
                    "votre dossier (%s sans réponse).", len(restantes)))
            project.state = 'pre_analyse'
            # Nouvelle fiche : la seconde lecture du comité est une décision
            # distincte de la première, et l'historique des deux doit rester.
            project.prequalification_ids.create({'project_id': project.id})
            project.message_post(
                body=_("Le porteur a répondu aux questions de clarification."),
                subtype_xmlid='mail.mt_note',
            )
        return True

    # ------------------------------------------------------------------
    # Le dossier complémentaire — section 7
    # ------------------------------------------------------------------
    #: Ce que chaque besoin exige avant que le dossier parte au contrôle
    #: qualité. Les champs facultatifs (valorisation « éventuelle », documents,
    #: partenaires déjà engagés) n'y figurent pas : le progressive commitment
    #: vaut aussi ici, on ne réclame que ce qui sert à décider.
    _CHAMPS_DOSSIER = {
        'investisseur': (
            'business_model', 'marche', 'traction', 'equipe',
            'besoin_financier', 'utilisation_fonds', 'previsions_financieres',
        ),
        'sponsor': (
            'sponsor_objectif', 'sponsor_public_cible', 'sponsor_visibilite',
            'sponsor_retombees', 'sponsor_budget', 'sponsor_calendrier',
        ),
        'financement_public': (
            'public_dispositif', 'public_eligibilite', 'public_montant',
            'public_plan_financement', 'public_impact', 'public_conformite',
            'public_calendrier',
        ),
    }

    def action_submit_dossier(self):
        """Le porteur envoie son dossier complémentaire.

        `dossier_progressif` → `quality_gate`. Déclenchée depuis le portail :
        pas de contrôle de groupe, mais la règle métier — un dossier
        incomplet ne mobilise pas le contrôle qualité.
        """
        for project in self:
            if project.state != 'dossier_progressif':
                raise UserError(_(
                    "Ce projet n'attend pas de dossier complémentaire : il est "
                    "à l'état « %s ».", project._state_label()))
            manquants = project._champs_dossier_manquants()
            if manquants:
                raise UserError(_(
                    "Complétez ces informations avant d'envoyer votre dossier :\n%s",
                    "\n".join("— %s" % libelle for libelle in manquants)))
            project.state = 'quality_gate'
            project._open_quality_control()
            project.message_post(
                body=_("Dossier complémentaire envoyé au contrôle qualité."),
                subtype_xmlid='mail.mt_note',
            )
        return True

    def action_submit_complement(self):
        """Le porteur renvoie son dossier corrigé.

        `quality_complement` → `quality_gate`. Distincte de
        `action_submit_dossier()` : ce n'est pas le même acte métier, le
        dossier ne vient pas d'un GO mais d'une demande de complément, et le
        contrôle qualité le reprend à zéro avec une fiche neuve.
        """
        for project in self:
            if project.state != 'quality_complement':
                raise UserError(_(
                    "Ce projet n'attend pas de complément : il est à l'état "
                    "« %s ».", project._state_label()))
            manquants = project._champs_dossier_manquants()
            if manquants:
                raise UserError(_(
                    "Complétez ces informations avant de renvoyer votre dossier :\n%s",
                    "\n".join("— %s" % libelle for libelle in manquants)))
            project.state = 'quality_gate'
            project._open_quality_control()
            project.message_post(
                body=_("Dossier corrigé renvoyé au contrôle qualité."),
                subtype_xmlid='mail.mt_note',
            )
        return True

    # ------------------------------------------------------------------
    # Quality Gate — section 8
    # ------------------------------------------------------------------
    # Quatre avis, trois sorties. « Alerte » et « Non conforme » remontent
    # toutes deux au comité sans faire bouger le dossier : le contrôle qualité
    # vérifie, il ne décide pas. Chaque méthode exige l'avis qui lui
    # correspond — on ne clôt pas un contrôle en « Conforme » quand la fiche
    # dit « Non conforme ».

    def action_quality_ok(self):
        """Conforme → `etude_decision`.

        Ne regarde jamais *qui* appelle au-delà du groupe : le jour où un
        agent IA tiendra le contrôle qualité, cette méthode ne bougera pas.
        """
        self._ensure_quality_control()
        for project in self:
            control = project._ensure_quality_gate_control('ok')
            control.controlled_by_id = self.env.user
            control.date = fields.Datetime.now()
            project.state = 'etude_decision'
            project.message_post(
                body=_("Contrôle qualité : dossier conforme, transmis au comité CEO."),
                subtype_xmlid='mail.mt_note',
            )
        return True

    def action_quality_complement(self):
        """À compléter → `quality_complement`, la main revient au porteur."""
        self._ensure_quality_control()
        for project in self:
            control = project._ensure_quality_gate_control('a_completer')
            control.controlled_by_id = self.env.user
            control.date = fields.Datetime.now()
            project.state = 'quality_complement'
            # Seul message du module destiné à sortir par email : le porteur
            # doit apprendre qu'on l'attend sans avoir à visiter le portail.
            project.message_post(
                body=_("Des compléments sont demandés sur votre dossier :\n%s",
                       control.anomalies),
                subtype_xmlid='mail.mt_comment',
            )
        return True

    def action_quality_alerte(self):
        """Alerte ou Non conforme → le comité CEO est prévenu, le dossier reste.

        Deux avis, une seule sortie : le contrôle qualité signale, il n'écarte
        pas. Le dossier ne quitte pas le Quality Gate — un nouveau contrôle
        pourra le débloquer, ou le comité décidera.
        """
        self._ensure_quality_control()
        for project in self:
            control = project._ensure_quality_gate_control(('alerte', 'non_conforme'))
            control.controlled_by_id = self.env.user
            control.date = fields.Datetime.now()
            libelle = dict(
                control._fields['avis']._description_selection(self.env))[control.avis]
            project.message_post(
                body=_("Contrôle qualité — %s. Anomalies signalées au comité CEO :\n%s",
                       libelle, control.anomalies),
                partner_ids=project._ceo_partners().ids,
                subtype_xmlid='mail.mt_note',
            )
        return True

    # ------------------------------------------------------------------
    # Étude et décision CEO — section 9
    # ------------------------------------------------------------------
    # Trois routes, trois méthodes, et — c'est le point important — aucun code
    # partagé entre elles. Ni précondition commune extraite dans un utilitaire,
    # ni message construit à deux. Seul `_ensure_ceo()` est commun, parce que
    # la règle transversale n°2 exige qu'un contrôle d'accès ne soit jamais
    # recopié.
    #
    # Cette redondance est le sujet même de la comparaison : dans le module
    # générique, ces trois routes sont trois transitions configurées depuis la
    # même étape. Ici, ce sont trois blocs de code qu'un développeur écrit,
    # relit et maintient séparément.

    def action_route_investment_ready(self):
        """Route A — le projet est mature. → `matching_financier`."""
        self._ensure_ceo()
        for project in self:
            if project.state != 'etude_decision':
                raise UserError(_(
                    "Ce projet n'est pas à l'étude du comité : il est à l'état "
                    "« %s ».", project._state_label()))
            project.state = 'matching_financier'
            project.message_post(
                body=_("Étude CEO — route A : projet Investment Ready, "
                       "recherche d'acteurs financiers engagée."),
                subtype_xmlid='mail.mt_comment',
            )
        return True

    def action_route_maturation(self):
        """Route B — potentiel, mais maturation nécessaire. → `accompagnement`.

        Ce n'est pas un refus. Le dossier reste dans le pipeline
        (`in_pipeline` reste vrai), il repassera par la réévaluation puis par
        le matching financier. Aucune ligne de cette méthode ne ressemble à
        celle de la route C, et c'est voulu : le jour où quelqu'un voudra
        « factoriser les deux sorties du comité », il verra qu'elles n'ont
        rien en commun.
        """
        self._ensure_ceo()
        for project in self:
            if project.state != 'etude_decision':
                raise UserError(_(
                    "Ce projet n'est pas à l'étude du comité : il est à l'état "
                    "« %s ».", project._state_label()))
            project.state = 'accompagnement'
            # Déclencheur 1 de la section 11 : la recommandation du comité
            # ouvre le sous-processus d'accompagnement séance tenante.
            project._open_accompagnement('ceo_recommandation')
            project.message_post(
                body=_("Étude CEO — route B : projet retenu, accompagnement "
                       "recommandé avant la recherche de financement."),
                subtype_xmlid='mail.mt_comment',
            )
        return True

    def action_route_rejected(self):
        """Route C — non retenu, décision motivée. → `rejected`."""
        self._ensure_ceo()
        for project in self:
            if project.state != 'etude_decision':
                raise UserError(_(
                    "Ce projet n'est pas à l'étude du comité : il est à l'état "
                    "« %s ».", project._state_label()))
            if not (project.motif_rejet or '').strip():
                raise UserError(_(
                    "Un refus se motive : renseignez le motif avant de clôturer "
                    "le dossier."))
            project.state = 'rejected'
            project.message_post(
                body=_("Étude CEO — route C : projet non retenu. Motif : %s",
                       project.motif_rejet),
                subtype_xmlid='mail.mt_note',
            )
            # Même partage qu'au NO GO de la pré-analyse : la décision au
            # porteur, le motif au dossier.
            project.message_post(
                body=_("Après étude, votre projet n'a pas été retenu."),
                subtype_xmlid='mail.mt_comment',
            )
        return True

    # ------------------------------------------------------------------
    # Closing et suivi — section 15
    # ------------------------------------------------------------------
    def action_start_closing(self, type_operation=None, partner_id=None):
        """`decision_financeur` → `closing`. L'opération prend une nature.

        C'est la nature choisie qui dira ensuite quels documents sont exigés,
        s'il y a des versements à échelonner et un reporting à tenir.
        """
        self._ensure_ceo()
        for project in self:
            if project.state != 'decision_financeur':
                raise UserError(_(
                    "Le closing suit la décision de l'acteur financier ; ce "
                    "projet est à l'état « %s ».", project._state_label()))
            # Deux chemins mènent ici : le comité a déjà saisi l'opération
            # dans l'onglet Closing, ou la nature arrive en paramètre. Dans
            # les deux cas, une opération sans nature n'existe pas.
            closing = project._current_closing()
            if not closing:
                if not type_operation:
                    raise UserError(_(
                        "Précisez la nature de l'opération avant d'ouvrir le "
                        "closing."))
                interesse = project.relation_ids.filtered(
                    lambda r: r.decision == 'interesse')[:1]
                closing = project.closing_ids.create({
                    'project_id': project.id,
                    'type_operation': type_operation,
                    'partner_id': partner_id or interesse.partner_id.id or False,
                })
            project.state = 'closing'
            type_operation = closing.type_operation
            project.message_post(
                body=_("Closing ouvert : %s.", closing._label_type_operation()),
                subtype_xmlid='mail.mt_note')
        return True

    def action_close(self):
        """`closing` → `closed`. Le dossier devient un projet suivi.

        On ne clôt pas une opération dont les pièces ne sont pas validées, qui
        n'est pas signée, ou dont l'échéancier manque quand sa nature en exige
        un. « Clôturé » doit vouloir dire quelque chose.
        """
        self._ensure_ceo()
        for project in self:
            if project.state != 'closing':
                raise UserError(_(
                    "Ce projet n'est pas en closing : il est à l'état « %s ».",
                    project._state_label()))
            closing = project._current_closing()
            if not closing:
                raise UserError(_("Aucune opération n'est enregistrée."))
            manquants = closing._documents_manquants()
            if manquants:
                raise UserError(_(
                    "Ces documents ne sont pas validés :\n%s",
                    "\n".join("— %s" % libelle for libelle in manquants)))
            if not closing.signature_confirmee:
                raise UserError(_(
                    "L'opération n'est pas signée : la clôture attend la "
                    "signature."))
            exigences = closing._exigences()
            if exigences['versements'] and not closing.versement_ids:
                raise UserError(_(
                    "Cette nature d'opération suppose un échéancier : "
                    "enregistrez au moins un versement."))
            if exigences['reporting'] and not (closing.reporting or '').strip():
                raise UserError(_(
                    "Cette nature d'opération suppose un reporting : précisez "
                    "ce qui est attendu du porteur."))
            project.state = 'closed'
            project.message_post(
                body=_("Financement conclu. Le dossier devient un projet suivi."),
                subtype_xmlid='mail.mt_comment')
        return True

    def _current_closing(self):
        """L'opération de ce projet, s'il y en a une."""
        self.ensure_one()
        return self.closing_ids.sorted('id')[-1:] if self.closing_ids else self.closing_ids

    # ------------------------------------------------------------------
    # Accompagnement CEO — sections 11 et 12
    # ------------------------------------------------------------------
    # Trois déclencheurs, trois méthodes. Ils ne diffèrent pas seulement par
    # l'origine consignée : le premier fait basculer le dossier dans l'étape
    # « Accompagnement CEO » du parcours principal, les deux autres ouvrent un
    # **sous-workflow qui tourne à côté** sans dérouter le dossier de son
    # chemin. Un porteur qui demande un accompagnement pendant que son dossier
    # est au contrôle qualité ne doit pas sortir du contrôle qualité.

    #: Les états où le porteur peut demander un accompagnement — « à tout
    #: moment autorisé du parcours » (section 11, cas 3). Ni avant le dépôt,
    #: ni une fois le dossier sorti du pipeline.
    _ETATS_DEMANDE_ACCOMPAGNEMENT = (
        'depot_express', 'pre_analyse', 'clarification', 'dossier_progressif',
        'quality_gate', 'quality_complement', 'etude_decision',
        'matching_financier', 'mise_en_relation', 'decision_financeur',
    )

    def _open_accompagnement(self, origine, **valeurs):
        """Ouvre le sous-processus d'accompagnement, quelle qu'en soit l'origine."""
        self.ensure_one()
        return self.env['opex.crowdfunding.accompagnement'].create(
            dict({'project_id': self.id, 'origine': origine}, **valeurs))

    def _accompagnement_en_cours(self):
        """L'accompagnement qui n'est ni clos ni refusé, s'il y en a un."""
        self.ensure_one()
        ouverts = self.accompagnement_ids.filtered(
            lambda a: a.state not in ('evalue', 'refuse'))
        return ouverts.sorted('id')[-1] if ouverts else self.env[
            'opex.crowdfunding.accompagnement']

    def action_accompagnement_demande_financeur(self, partner=None):
        """Déclencheur 2 — « intéressé sous condition d'accompagnement CEO ».

        `partner` : l'acteur qui pose la condition, quand l'appelant le sait —
        c'est le cas depuis l'écran de décision de la section 14, où la
        demande arrive par une relation identifiée. Sans lui, on retombe sur
        le premier acteur retenu au matching.

        L'acteur financier pose sa condition ; le dossier ne quitte pas son
        étape, un sous-processus s'ouvre à côté. C'est le schéma de la section
        11, cas 2 : la réévaluation en fin d'accompagnement fera le retour
        vers l'investisseur.
        """
        self._ensure_ceo()
        for project in self:
            if project.state not in ('matching_financier', 'mise_en_relation',
                                     'decision_financeur'):
                raise UserError(_(
                    "Un acteur financier ne peut poser cette condition qu'une "
                    "fois la mise en relation engagée ; ce projet est à l'état "
                    "« %s ».", project._state_label()))
            if project._accompagnement_en_cours():
                raise UserError(_(
                    "Un accompagnement est déjà en cours sur ce projet."))
            demandeur = partner or project.matching_candidate_ids.filtered(
                lambda c: c.state == 'validated')[:1].partner_id
            project._open_accompagnement(
                'acteur_financier', requested_by_partner_id=demandeur.id or False)
            project.message_post(
                body=_("Un acteur financier conditionne son intérêt à un "
                       "accompagnement CEO."),
                subtype_xmlid='mail.mt_note')
        return True

    def action_accompagnement_demande_porteur(self, demande=None):
        """Déclencheur 3 — « Être accompagné par CEO », à la demande du porteur.

        Appelée depuis le portail : pas de contrôle de groupe, mais la liste
        des états où la demande a un sens.
        """
        for project in self:
            if project.state not in project._ETATS_DEMANDE_ACCOMPAGNEMENT:
                raise UserError(_(
                    "Vous ne pouvez pas demander d'accompagnement à ce stade de "
                    "votre parcours."))
            if project._accompagnement_en_cours():
                raise UserError(_(
                    "Une demande d'accompagnement est déjà en cours sur votre "
                    "projet."))
            project._open_accompagnement('porteur', demande=demande or '')
            project.message_post(
                body=_("Le porteur demande un accompagnement CEO."),
                subtype_xmlid='mail.mt_note')
        return True

    # ------------------------------------------------------------------
    # La boucle de réévaluation — ce qui distingue ce processus d'une séquence
    # ------------------------------------------------------------------
    def action_reevaluation(self):
        """`accompagnement` → `reevaluation`, une fois l'accompagnement clos."""
        self._ensure_ceo()
        for project in self:
            if project.state != 'accompagnement':
                raise UserError(_(
                    "La réévaluation suit un accompagnement ; ce projet est à "
                    "l'état « %s ».", project._state_label()))
            abouti = project.accompagnement_ids.filtered(
                lambda a: a.state in ('service_fait', 'evalue'))
            if not abouti:
                raise UserError(_(
                    "Aucun accompagnement n'est arrivé au service fait : il n'y "
                    "a rien à réévaluer."))
            project.state = 'reevaluation'
            project.message_post(
                body=_("Réévaluation du projet après accompagnement."),
                subtype_xmlid='mail.mt_note')
        return True

    def action_retour_matching(self):
        """`reevaluation` → `demo_day`. La boucle se referme, via le Demo Day.

        C'est ce retour qui fait du processus autre chose qu'une séquence
        linéaire : un projet maturé revient chercher son financement, avec
        l'accompagnement derrière lui. Le module générique le construit avec
        une transition de plus ; ici, c'est une méthode de plus.

        Depuis l'ajout du Demo Day (section 18), ce retour ne mène plus
        directement au matching : le projet passe d'abord devant le comité.
        Le nom de la méthode est conservé — le renommer aurait touché la vue,
        les tests et l'historique sans rien apporter.
        """
        self._ensure_ceo()
        for project in self:
            if project.state != 'reevaluation':
                raise UserError(_(
                    "Ce projet n'est pas en réévaluation : il est à l'état "
                    "« %s ».", project._state_label()))
            project.state = 'demo_day'
            project.message_post(
                body=_("Projet réévalué : inscrit au Demo Day."),
                subtype_xmlid='mail.mt_comment')
        return True

    # ------------------------------------------------------------------
    # Demo Day — section 18
    # ------------------------------------------------------------------
    #: La note minimale exigée pour passer le Demo Day.
    NOTE_MINIMALE_DEMO_DAY = 70

    def action_valider_demo_day(self):
        """`demo_day` → `matching_financier`, sous trois conditions.

        « Elle nécessite l'accord du CEO, une présentation Pitch Deck et une
        note ≥ 70/100. » Les trois sont vérifiées ici, et le refus dit
        laquelle manque : « conditions non remplies » ferait recommencer à
        l'aveugle.
        """
        self._ensure_ceo()
        for project in self:
            if project.state != 'demo_day':
                raise UserError(_(
                    "Ce projet n'est pas au Demo Day : il est à l'état « %s ».",
                    project._state_label()))
            manquants = []
            if not project.ceo_approval:
                manquants.append(_("l'accord du comité CEO"))
            if not project.pitch_deck:
                manquants.append(_("la présentation Pitch Deck"))
            if project.score < project.NOTE_MINIMALE_DEMO_DAY:
                manquants.append(_(
                    "une note d'au moins %(minimum)s/100 (actuelle : %(score)s)",
                    minimum=project.NOTE_MINIMALE_DEMO_DAY, score=project.score))
            if manquants:
                raise UserError(_(
                    "Le Demo Day n'est pas validé, il manque :\n%s",
                    "\n".join("— %s" % manque for manque in manquants)))
            project.state = 'matching_financier'
            project.message_post(
                body=_("Demo Day validé (note %s/100) : recherche de financement "
                       "engagée.", project.score),
                subtype_xmlid='mail.mt_comment')
        return True

    # ------------------------------------------------------------------
    # Smart Matching financier — section 10
    # ------------------------------------------------------------------
    def action_run_matching(self):
        """Propose les acteurs financiers compatibles, classés par score.

        Cette méthode **ne fait pas avancer le dossier**, et c'est le point
        central de la section 10 : « le matching est une recommandation ».
        Elle remplit une liste, le comité en fait ce qu'il veut. Aucun score,
        même à 100, ne déclenche quoi que ce soit.
        """
        self._ensure_ceo()
        Candidate = self.env['opex.crowdfunding.matching.candidate']
        for project in self:
            if project.state != 'matching_financier':
                raise UserError(_(
                    "Le matching financier ne s'exécute qu'à cette étape ; ce "
                    "projet est à l'état « %s ».", project._state_label()))
            acteurs = self.env['res.partner'].search([
                ('cf_is_financial_actor', '=', True)])
            deja_vus = project.matching_candidate_ids.partner_id
            nouveaux = Candidate.create([
                {
                    'project_id': project.id,
                    'partner_id': acteur.id,
                    'candidate_type': acteur.cf_actor_type,
                    # `proposed` explicitement : tout candidat créé autrement
                    # est un ajout du comité, et le modèle le marque comme tel.
                    'state': 'proposed',
                }
                for acteur in acteurs - deja_vus
            ])
            # Les exclusions du comité ne sont pas rejouées : un acteur écarté
            # le reste, même si son score remonterait.
            a_evaluer = (project.matching_candidate_ids | nouveaux).filtered(
                lambda c: c.state != 'excluded')
            a_evaluer._evaluate()
            project.message_post(
                body=_("Matching financier : %(total)s acteur(s) évalué(s), "
                       "%(nouveaux)s nouveau(x) candidat(s) proposé(s).",
                       total=len(a_evaluer), nouveaux=len(nouveaux)),
                subtype_xmlid='mail.mt_note',
            )
        return True

    def action_validate_matching(self):
        """Le comité arrête sa liste. → `mise_en_relation`.

        C'est ici, et nulle part ailleurs, que le dossier avance : une décision
        humaine explicite, jamais un seuil de score.
        """
        self._ensure_ceo()
        for project in self:
            if project.state != 'matching_financier':
                raise UserError(_(
                    "Ce projet n'est pas au matching financier : il est à "
                    "l'état « %s ».", project._state_label()))
            retenus = project.matching_candidate_ids.filtered(
                lambda c: c.state == 'validated')
            if not retenus:
                raise UserError(_(
                    "Validez au moins un acteur financier avant de lancer la "
                    "mise en relation."))
            project.state = 'mise_en_relation'
            # Section 13 : le match ouvre une relation, et une relation
            # commence au teaser anonymisé. « Le matching ne signifie pas
            # automatiquement partage du dossier complet. »
            Relation = self.env['opex.crowdfunding.relation']
            deja = project.relation_ids.partner_id
            Relation.create([
                {'project_id': project.id, 'partner_id': acteur.id}
                for acteur in retenus.partner_id - deja
            ])
            project.message_post(
                body=_("Matching validé par le comité : %s acteur(s) retenu(s), "
                       "teaser anonymisé ouvert.", len(retenus)),
                subtype_xmlid='mail.mt_note',
            )
        return True

    # ------------------------------------------------------------------
    # Utilitaires
    # ------------------------------------------------------------------
    def _champs_dossier_requis(self):
        """Les champs exigés par le besoin exprimé — le branchement, en un point.

        COÛT D'UN QUATRIÈME TYPE DE BESOIN — pour le document de comparaison
        Chiffres relevés sur la branche « sponsor » déjà écrite, en comptant
        ses lignes réelles. Ajouter « mécénat », « prêt d'honneur » ou tout
        autre besoin oblige à toucher **cinq fichiers**, par un développeur
        Odoo :

          1. models/crowdfunding_project.py
             · 1 valeur dans le Selection `besoin_type`            1 ligne
             · les champs du nouveau questionnaire                14 lignes
             · 1 entrée dans `_CHAMPS_DOSSIER`                     4 lignes
             · 1 entrée dans `_CHAMPS_DOSSIER_DETAIL`              5 lignes
               (ajoutée à l'Extension 9 : l'échelle de confidentialité
                branche elle aussi sur le besoin — un point d'oubli de plus)
          2. controllers/portal.py
             · 1 entrée dans `_DOSSIER_FIELDS`                     5 lignes
             · 1 entrée dans `_DOSSIER_DOCUMENTS`                  1 ligne
          3. views/portal_templates.xml
             · 1 gabarit de saisie complet                        50 lignes
             · 1 branche `t-if` dans le gabarit d'aiguillage       2 lignes
          4. views/crowdfunding_project_views.xml
             · 1 groupe backend, `invisible` sur `besoin_type`    12 lignes
          5. tests/test_extension4.py
             · 1 jeu de données + 1 champ témoin + parcours       ~25 lignes
                                                          TOTAL ≈ 119 lignes

        Puis : mise à jour du module (`-u opex_crowdfunding`) et redémarrage du
        service. Pas de migration de données — les colonnes ajoutées sont
        nullables et les dossiers déjà en base ne bougent pas.

        Le point le plus coûteux n'est pas le volume, c'est la dispersion :
        cinq fichiers, dont deux qu'on peut oublier sans que rien ne casse
        immédiatement. D'où le refus explicite plus haut quand un besoin n'a
        pas de questionnaire.

        Ces chiffres sont comptés, pas devinés, mais ils décrivent l'ajout
        d'une branche par quelqu'un qui connaît déjà le module. Le benchmark
        de l'Extension 12 y ajoutera le temps réel, chronométré — face à zéro
        ligne et zéro redéploiement côté module générique.
        """
        self.ensure_one()
        if self.besoin_type not in self._CHAMPS_DOSSIER:
            # Le jour où un quatrième besoin sera ajouté au Selection sans son
            # questionnaire, le dossier passerait au contrôle qualité sans
            # aucune vérification. Mieux vaut un refus bruyant qu'un trou
            # silencieux — et cela rend le coût du branchement impossible à
            # oublier à moitié.
            raise UserError(_(
                "Le besoin exprimé pour ce projet ne correspond à aucun "
                "questionnaire. Contactez le comité CEO."))
        return self._CHAMPS_DOSSIER[self.besoin_type]

    def _champs_dossier_manquants(self):
        """Libellés des informations du dossier complémentaire encore absentes."""
        self.ensure_one()
        return self._libelles_manquants(self._champs_dossier_requis())

    def _is_ceo(self):
        """Le seul endroit qui teste l'appartenance au comité CEO."""
        return self.env.user.has_group('opex_crowdfunding.group_ceo')

    def _ensure_ceo(self):
        """Refuse l'action à qui n'est pas du comité CEO.

        Les boutons sont déjà filtrés par `groups=` dans la vue ; ce contrôle
        ferme l'appel direct, qu'il vienne d'un autre rôle interne ou d'un
        appel RPC.
        """
        if not self._is_ceo() and not self.env.su:
            raise AccessError(_(
                "Seul le comité CEO décide de l'issue d'une pré-analyse."))

    def _is_quality_control(self):
        """Le seul endroit qui teste l'appartenance au Contrôle Qualité.

        Le groupe, et rien d'autre : ni le nom de l'utilisateur, ni le fait
        qu'il soit humain. C'est ce qui rendra le remplacement par un agent IA
        possible sans toucher au workflow.
        """
        return self.env.user.has_group('opex_crowdfunding.group_quality_control')

    def _ensure_quality_control(self):
        if not self._is_quality_control() and not self.env.su:
            raise AccessError(_(
                "Seul le Contrôle Qualité rend un avis sur un dossier."))

    def _open_quality_control(self):
        """Ouvre une fiche de contrôle vierge à l'arrivée dans le Quality Gate.

        Une fiche par passage : un dossier revenu de complément est recontrôlé
        à neuf, et les deux avis restent lisibles.
        """
        self.ensure_one()
        return self.quality_control_ids.create({'project_id': self.id})

    def _current_quality_control(self):
        """La fiche de contrôle en cours, créée au besoin."""
        self.ensure_one()
        ouvertes = self.quality_control_ids.filtered(lambda c: not c.date)
        if ouvertes:
            return ouvertes.sorted('id')[-1]
        return self._open_quality_control()

    def _ensure_quality_gate_control(self, avis_attendus):
        """Préconditions communes aux trois sorties du Quality Gate."""
        self.ensure_one()
        if self.state != 'quality_gate':
            raise UserError(_(
                "Ce projet n'est pas au contrôle qualité : il est à l'état "
                "« %s ».", self._state_label()))
        control = self._current_quality_control()
        attendus = (avis_attendus,) if isinstance(avis_attendus, str) else avis_attendus
        if control.avis not in attendus:
            raise UserError(_(
                "L'avis retenu sur la fiche de contrôle ne correspond pas à "
                "cette décision. Choisissez l'avis, puis la suite à donner."))
        if control.avis != 'ok' and not (control.anomalies or '').strip():
            raise UserError(_(
                "Décrivez les anomalies relevées : le porteur ou le comité "
                "doivent savoir ce qui ne va pas."))
        return control

    def _ceo_partners(self):
        """Les contacts du comité CEO, destinataires des alertes."""
        groupe = self.env.ref('opex_crowdfunding.group_ceo', raise_if_not_found=False)
        if not groupe:
            return self.env['res.partner']
        return groupe.sudo().all_user_ids.partner_id

    def _ensure_pre_analyse(self):
        """Précondition commune aux quatre issues : le dossier y est bien."""
        self.ensure_one()
        if self.state != 'pre_analyse':
            raise UserError(_(
                "Ce projet n'est pas en pré-analyse : il est à l'état « %s ».",
                self._state_label()))

    def _current_prequalification(self):
        """La fiche de pré-analyse en cours, créée au besoin."""
        self.ensure_one()
        ouvertes = self.prequalification_ids.filtered(lambda p: not p.resultat)
        if ouvertes:
            return ouvertes.sorted('id')[-1]
        return self.prequalification_ids.create({'project_id': self.id})

    def _champs_depot_manquants(self):
        """Libellés des informations minimales encore absentes du dossier."""
        self.ensure_one()
        return self._libelles_manquants(self._CHAMPS_DEPOT_EXPRESS)

    def _libelles_manquants(self, noms):
        """Libellés, tels qu'affichés, des champs non renseignés parmi `noms`.

        Le porteur doit lire « Business model », pas `business_model` : les
        libellés viennent donc du modèle, jamais d'une liste recopiée à la
        main qui finirait par diverger.
        """
        self.ensure_one()
        if not noms:
            return []
        descriptions = self.fields_get(noms, ['string'])
        return [descriptions[nom]['string'] for nom in noms if not self[nom]]

    def _label(self, nom):
        """Libellé affichable d'un champ `Selection`, ou chaîne vide.

        Le seul endroit qui traduit un code en texte. Le portail s'en sert
        partout : ni le porteur ni un acteur financier ne doit jamais lire un
        code technique (section 16).
        """
        self.ensure_one()
        valeur = self[nom]
        if not valeur:
            return ''
        return dict(self._fields[nom]._description_selection(self.env))[valeur]

    def _state_label(self):
        """Libellé lisible de l'état courant."""
        return self._label('state')

    # ------------------------------------------------------------------
    # Ce qu'un acteur financier peut voir — section 13
    # ------------------------------------------------------------------
    def _portal_reference(self):
        """La référence anonyme d'un dossier, façon « PRJ-127 » (section 10).

        Dérivée de l'identifiant : pas de séquence à maintenir, pas de
        migration, et surtout aucune information sur le projet ni son porteur.
        """
        self.ensure_one()
        return "PRJ-%03d" % self.id

    #: Paliers de montant du teaser. Une fourchette suffit à savoir si le
    #: dossier entre dans le ticket d'un acteur ; le montant exact fait partie
    #: de ce qui se gagne au cran suivant.
    _PALIERS_MONTANT = (
        (1000000, "moins de 1 million"),
        (5000000, "1 à 5 millions"),
        (10000000, "5 à 10 millions"),
        (50000000, "10 à 50 millions"),
    )

    def _portal_fourchette_montant(self):
        self.ensure_one()
        montant = (self.besoin_financier or self.public_montant
                   or self.sponsor_budget or self.montant_indicatif)
        if not montant:
            return _("non précisé")
        devise = self.currency_id.name or ''
        for plafond, libelle in self._PALIERS_MONTANT:
            if montant < plafond:
                return "%s %s" % (libelle, devise)
        return "%s %s" % (_("plus de 50 millions"), devise)

    #: Ce que le dossier détaillé montre, branche par branche : les champs
    #: exigés à l'envoi et ceux qui restent facultatifs.
    _CHAMPS_DOSSIER_DETAIL = {
        'investisseur': (
            'business_model', 'marche', 'traction', 'equipe', 'besoin_financier',
            'utilisation_fonds', 'valorisation', 'previsions_financieres',
        ),
        'sponsor': (
            'sponsor_objectif', 'sponsor_public_cible', 'sponsor_visibilite',
            'sponsor_retombees', 'sponsor_budget', 'sponsor_calendrier',
            'sponsor_partenaires',
        ),
        'financement_public': (
            'public_dispositif', 'public_eligibilite', 'public_montant',
            'public_plan_financement', 'public_impact', 'public_conformite',
            'public_calendrier',
        ),
    }

    def _portal_dossier_detaille(self):
        """Le questionnaire de la branche, en couples (libellé, valeur).

        Rendu au seul niveau `full`, et construit ici plutôt que dans le
        gabarit : un gabarit qui recevrait l'enregistrement pourrait lire
        n'importe quel champ.
        """
        self.ensure_one()
        noms = self._CHAMPS_DOSSIER_DETAIL.get(self.besoin_type, ())
        if not noms:
            return []
        descriptions = self.fields_get(noms, ['string'])
        lignes = []
        for nom in noms:
            valeur = self[nom]
            if valeur:
                lignes.append((descriptions[nom]['string'], valeur))
        return lignes

    # ------------------------------------------------------------------
    # Ce que le porteur voit — section 16
    # ------------------------------------------------------------------
    # « Le workflow système peut être complexe. L'expérience utilisateur ne
    # doit pas l'être. » Les seize états techniques sont donc repliés sur cinq
    # jalons lisibles, et chaque état dit ce que le porteur a à faire — ou
    # qu'il n'a rien à faire. Ces deux tables sont le seul endroit qui
    # traduit : le gabarit ne connaît aucun code d'état.

    #: Libellé public du jalon, puis les états techniques qu'il recouvre.
    _PORTAL_MILESTONES = (
        ("Demande reçue",          ('draft', 'depot_express')),
        ("Projet présélectionné",  ('pre_analyse', 'clarification')),
        ("Dossier complété",       ('dossier_progressif', 'quality_gate', 'quality_complement')),
        ("Étude",                  ('etude_decision', 'accompagnement', 'reevaluation')),
        ("Demo Day",               ('demo_day',)),
        ("Mise en relation",       ('matching_financier', 'mise_en_relation',
                                    'decision_financeur', 'closing', 'closed')),
    )

    #: Par état : ce qu'on dit au porteur, et le bouton s'il a la main.
    #: Une entrée par état, sans exception — un état oublié afficherait une
    #: page muette à quelqu'un qui attend une consigne.
    _PORTAL_NEXT_ACTIONS = {
        'draft': (
            "Il vous reste quelques informations à donner pour présenter votre projet.",
            "Présenter mon projet", '/my/crowdfunding/new',
        ),
        'depot_express': (
            "Votre demande est enregistrée. Le comité CEO va l'examiner.", None, None,
        ),
        'pre_analyse': (
            "Votre projet est en cours de pré-analyse par le comité CEO.", None, None,
        ),
        'clarification': (
            "Le comité CEO vous a adressé des questions. Vos réponses lui "
            "permettront de statuer.",
            "Répondre aux questions", '/my/crowdfunding/%(id)s/clarifications',
        ),
        'dossier_progressif': (
            "Bonne nouvelle : votre projet est retenu pour la suite. Il reste "
            "à compléter votre dossier.",
            "Compléter mon dossier", '/my/crowdfunding/%(id)s/dossier',
        ),
        # Les entrées ci-dessous décriront une action du porteur dès que les
        # extensions suivantes auront ouvert les écrans correspondants. D'ici
        # là elles informent sans promettre de bouton : un bouton mort serait
        # pire que pas de bouton.
        'quality_gate': (
            "Votre dossier est en cours de vérification.", None, None,
        ),
        'quality_complement': (
            "Le contrôle qualité a besoin de compléments sur votre dossier.",
            "Compléter mon dossier", '/my/crowdfunding/%(id)s/dossier',
        ),
        'etude_decision': (
            "Votre dossier est à l'étude au comité CEO.", None, None,
        ),
        'accompagnement': (
            "Un accompagnement est en cours sur votre projet.", None, None,
        ),
        'reevaluation': (
            "Votre projet est réévalué après accompagnement.", None, None,
        ),
        'demo_day': (
            "Votre projet est inscrit au Demo Day. Le comité l'évaluera lors "
            "de la présentation.", None, None,
        ),
        'matching_financier': (
            "Nous recherchons les acteurs financiers correspondant à votre projet.",
            None, None,
        ),
        'mise_en_relation': (
            "Une mise en relation est en cours. Rien à faire pour l'instant.", None, None,
        ),
        'decision_financeur': (
            "Un acteur financier étudie votre dossier.", None, None,
        ),
        'closing': (
            "Votre financement est en cours de finalisation.",
            "Voir mon financement", '/my/crowdfunding/%(id)s/financement',
        ),
        'closed': (
            "Votre financement est conclu. Votre projet est maintenant suivi.",
            "Voir mon financement", '/my/crowdfunding/%(id)s/financement',
        ),
        'rejected': (
            "Votre projet n'a pas été retenu. Le comité CEO reste disponible "
            "pour vous en expliquer les raisons.", None, None,
        ),
    }

    def _portal_progress(self):
        """Les cinq jalons de la section 16, avec leur avancement.

        Renvoie une liste de `{'label', 'status'}`, `status` valant `done`,
        `current` ou `todo` — de quoi rendre les sans que le gabarit
        n'ait à connaître un seul code d'état.
        """
        self.ensure_one()
        courant = None
        for position, (_label, etats) in enumerate(self._PORTAL_MILESTONES):
            if self.state in etats:
                courant = position
                break
        progression = []
        for position, (label, _etats) in enumerate(self._PORTAL_MILESTONES):
            if courant is None:      # dossier sorti du parcours (non retenu)
                statut = 'todo'
            elif position < courant:
                statut = 'done'
            elif position == courant:
                statut = 'current'
            else:
                statut = 'todo'
            progression.append({'label': label, 'status': statut})
        return progression

    def _portal_next_action(self):
        """« Votre prochaine action » : la phrase, et le bouton s'il y en a un."""
        self.ensure_one()
        message, label, url = self._PORTAL_NEXT_ACTIONS[self.state]
        return {
            'message': message,
            'label': label,
            # Les libellés d'URL portent l'identifiant du projet quand ils en
            # ont besoin ; les autres traversent le formatage sans changer.
            'url': url % {'id': self.id} if url else None,
        }

    def _portal_is_editable(self):
        """Le porteur ne modifie sa présentation que tant qu'elle est un brouillon."""
        self.ensure_one()
        return self.state == 'draft'

    def _portal_historique(self):
        """L'audit trail tel que le porteur peut le lire (section 16).

        Deux sources, et deux seulement :

        * les changements d'état, pris dans les valeurs de suivi du fil — elles
          donnent qui, quand, et d'où vers où, en libellés lisibles ;
        * les messages qui lui étaient adressés (`mt_comment`).

        Les notes internes (`mt_note`) n'y figurent pas : l'historique du
        porteur n'est pas le dossier d'instruction du comité. L'audit complet,
        lui, reste dans le fil du projet côté backend.

        Les valeurs de suivi sont écrites par Odoo au **précommit**
        (`_track_finalize`), pas au flush. En production chaque requête HTTP
        commite, donc elles sont là ; dans un test qui ne commite jamais, il
        faut appeler `env.cr.precommit.run()` — sinon cet historique paraît
        vide sans que rien ne soit cassé.
        """
        self.ensure_one()
        comment = self.env.ref('mail.mt_comment', raise_if_not_found=False)
        entrees = []
        for message in self.message_ids.sorted('id'):
            auteur = message.author_id.display_name or _("Système")
            for suivi in message.tracking_value_ids:
                if suivi.field_id.name != 'state':
                    continue
                entrees.append({
                    'date': message.date,
                    'auteur': auteur,
                    'libelle': _("%(depuis)s → %(vers)s",
                                 depuis=suivi.old_value_char or _("Création"),
                                 vers=suivi.new_value_char or ''),
                    'detail': '',
                })
            if comment and message.subtype_id == comment and message.body:
                entrees.append({
                    'date': message.date,
                    'auteur': auteur,
                    'libelle': _("Message du comité"),
                    'detail': message.body,
                })
        return entrees

    def _portal_demande_complement(self):
        """Ce que le contrôle qualité demande au porteur de corriger.

        Seules les anomalies sortent : ni l'avis retenu, ni le détail des six
        vérifications, ni le nom du contrôleur. Le porteur a droit à ce qu'on
        attend de lui, pas au dossier d'instruction.
        """
        self.ensure_one()
        if self.state != 'quality_complement':
            return ''
        demandes = self.quality_control_ids.filtered(lambda c: c.avis == 'a_completer')
        return demandes.sorted('id')[-1].anomalies if demandes else ''
