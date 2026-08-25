from odoo import _, fields, models
from odoo.exceptions import UserError

#: Les trois niveaux, du plus fermé au plus ouvert. L'ordre compte : il sert à
#: comparer, jamais à franchir un cran tout seul.
NIVEAUX = ('teaser', 'limited', 'full')


class OpexCrowdfundingRelation(models.Model):
    """La mise en relation contrôlée entre un projet et un acteur financier.

    « Le matching ne signifie pas automatiquement partage du dossier complet »
    (section 13). Un acteur retenu au matching n'obtient qu'un teaser anonymisé ;
    tout le reste se gagne cran par cran, et chaque cran demande le geste d'un
    acteur habilité :

        match → teaser anonymisé → expression d'intérêt → autorisation du
        porteur → NDA si nécessaire → dossier détaillé

    ⚠️ Le contrôle du niveau vit dans **une seule méthode**, `_portal_payload()`.
    Toutes les routes portail passent par elle et ne reçoivent que les données
    du niveau atteint : les informations réservées ne sont pas masquées à
    l'affichage, elles ne quittent jamais le serveur.
    """

    _name = 'opex.crowdfunding.relation'
    _description = "Mise en relation contrôlée"
    _order = 'id desc'
    _rec_name = 'partner_id'

    project_id = fields.Many2one(
        'opex.crowdfunding.project', string="Projet",
        required=True, ondelete='cascade', index=True,
    )
    partner_id = fields.Many2one(
        'res.partner', string="Acteur financier",
        required=True, ondelete='restrict', index=True,
    )

    niveau_acces = fields.Selection([
        ('teaser',  "Teaser anonymisé"),
        ('limited', "Dossier limité"),
        ('full',    "Dossier détaillé"),
    ], string="Niveau d'accès", default='teaser', required=True, readonly=True)

    # Trace de l'expression d'intérêt. Elle ne figure pas dans la liste de
    # champs de la spécification, mais l'étape y figure : sans elle, personne
    # ne sait quels acteurs le porteur doit envisager d'autoriser.
    interet_exprime = fields.Boolean(string="Intérêt exprimé", readonly=True)
    date_interet = fields.Datetime(string="Date de l'intérêt", readonly=True)

    autorise_par_id = fields.Many2one(
        'res.users', string="Partage autorisé par", readonly=True)
    date_autorisation = fields.Datetime(string="Date d'autorisation", readonly=True)

    # « NDA si nécessaire » : encore faut-il pouvoir dire qu'il l'est. Sans ce
    # second drapeau, `nda_signe` à faux ne distingue pas « pas encore signé »
    # de « pas nécessaire ».
    nda_requis = fields.Boolean(string="NDA requis")
    nda_signe = fields.Boolean(string="NDA signé", readonly=True)
    date_nda = fields.Datetime(string="Date du NDA", readonly=True)

    # ------------------------------------------------------------------
    # La décision de l'acteur financier — section 14
    # ------------------------------------------------------------------
    decision = fields.Selection([
        ('interesse',      "Intéressé"),
        ('informations',   "Besoin d'informations"),
        ('accompagnement', "Accompagnement CEO demandé"),
        ('rendez_vous',    "Rendez-vous proposé"),
        ('non_interesse',  "Non intéressé"),
    ], string="Décision", readonly=True)
    date_decision = fields.Datetime(string="Date de la décision", readonly=True)
    message_financeur = fields.Text(
        string="Message de l'acteur", readonly=True,
        help="Sa question, ou le motif du rendez-vous qu'il propose.")
    date_rendez_vous = fields.Datetime(string="Rendez-vous proposé", readonly=True)

    _project_partner_uniq = models.Constraint(
        'unique(project_id, partner_id)',
        "Cet acteur est déjà en relation avec ce projet.",
    )

    # ------------------------------------------------------------------
    # LA fonction de contrôle d'accès — une seule, pour toutes les routes
    # ------------------------------------------------------------------
    def _portal_payload(self):
        """Ce que cet acteur a le droit de voir, et le gabarit qui l'affiche.

        C'est **le** point de contrôle du module côté confidentialité, et il
        est unique : aucune route ne compose ses propres valeurs, aucun gabarit
        ne reçoit un enregistrement projet à interroger librement. Un gabarit
        qui n'a pas la donnée ne peut pas la laisser fuir, ni dans un `t-if`
        oublié, ni dans un attribut, ni dans une classe CSS.

        Renvoie `(xmlid_du_gabarit, valeurs)`.
        """
        self.ensure_one()
        projet = self.project_id

        # Niveau 1 — teaser anonymisé. Rien qui permette d'identifier le
        # projet ou son porteur : ni titre, ni description, ni montant exact.
        valeurs = {
            # Ni la relation ni le projet ne sont passés au gabarit : avec
            # l'enregistrement en main, un `t-out="relation.project_id.name"`
            # suffirait à contourner tout ce qui précède. Le gabarit ne reçoit
            # que des valeurs déjà filtrées.
            'relation_id': self.id,
            'niveau': self.niveau_acces,
            'niveau_label': self._label_niveau(),
            'reference': projet._portal_reference(),
            'secteur': projet._label('secteur'),
            'maturite': projet._label('maturite'),
            'besoin': projet._label('besoin_type'),
            'porteur_type': projet._label('porteur_type'),
            'fourchette': projet._portal_fourchette_montant(),
            'interet_exprime': self.interet_exprime,
            # Son score à lui, celui du matching qui l'a désigné (section 16).
            # C'est une information sur la correspondance entre son profil et
            # ce dossier : elle le concerne, elle ne dit rien du porteur.
            'score': self._score_matching(),
        }
        if self.niveau_acces == 'teaser':
            return 'opex_crowdfunding.portal_relation_teaser', valeurs

        # Niveau 2 — dossier limité, après autorisation du porteur. Le projet
        # se nomme et se décrit ; son porteur reste anonyme et le dossier
        # financier n'est pas ouvert.
        valeurs.update({
            'titre': projet.name,
            'probleme': projet.probleme,
            'solution': projet.solution,
            'montant': projet.besoin_financier or projet.montant_indicatif,
            'devise': projet.currency_id,
            'nda_requis': self.nda_requis,
            'nda_signe': self.nda_signe,
            # Les cinq boutons de la section 14 n'apparaissent qu'à partir
            # d'ici : au teaser, l'acteur n'a rien lu qui permette de décider.
            'decision': self.decision,
            'decision_label': self._label_decision(),
        })
        if self.niveau_acces == 'limited':
            return 'opex_crowdfunding.portal_relation_limited', valeurs

        # Niveau 3 — dossier détaillé. Le porteur est nommé, le questionnaire
        # de sa branche est ouvert.
        valeurs.update({
            'porteur': projet.partner_id.display_name,
            'porteur_email': projet.partner_id.email or '',
            'dossier': projet._portal_dossier_detaille(),
        })
        return 'opex_crowdfunding.portal_relation_full', valeurs

    def _score_matching(self):
        """Le score du matching qui a désigné cet acteur, ou 0.

        Un acteur ajouté à la main par le comité n'a pas forcément été scoré :
        dans ce cas on n'affiche pas de pourcentage plutôt que d'en inventer un.
        """
        self.ensure_one()
        candidat = self.env['opex.crowdfunding.matching.candidate'].sudo().search([
            ('project_id', '=', self.project_id.id),
            ('partner_id', '=', self.partner_id.id),
        ], limit=1)
        return candidat.score or 0.0

    def _label_decision(self):
        self.ensure_one()
        if not self.decision:
            return ''
        return dict(
            self._fields['decision']._description_selection(self.env)
        )[self.decision]

    def _label_niveau(self):
        self.ensure_one()
        return dict(
            self._fields['niveau_acces']._description_selection(self.env)
        )[self.niveau_acces]

    def _niveau_atteint(self, niveau_minimum):
        """Vrai si la relation donne au moins ce niveau d'accès."""
        self.ensure_one()
        return NIVEAUX.index(self.niveau_acces) >= NIVEAUX.index(niveau_minimum)

    # ------------------------------------------------------------------
    # Les crans, un par un — jamais franchis automatiquement
    # ------------------------------------------------------------------
    def action_exprimer_interet(self):
        """L'acteur se déclare intéressé. Son niveau d'accès ne bouge pas.

        C'est le point que la section 13 protège : dire « ça m'intéresse » ne
        donne aucun droit supplémentaire. La suite appartient au porteur.
        """
        for relation in self:
            if relation.interet_exprime:
                raise UserError(_("Vous avez déjà exprimé votre intérêt."))
            relation.interet_exprime = True
            relation.date_interet = fields.Datetime.now()
            relation.project_id.message_post(
                body=_("%s s'est déclaré intéressé par le projet.",
                       relation.partner_id.display_name),
                subtype_xmlid='mail.mt_note')
        return True

    def action_autoriser_partage(self):
        """Le porteur autorise le partage : teaser → dossier limité.

        « Le porteur peut autoriser la mise en relation avec des acteurs
        financiers » (section 2.A). L'autorisation n'a de sens qu'après un
        intérêt exprimé : on n'ouvre pas son dossier à quelqu'un qui n'a rien
        demandé.
        """
        for relation in self:
            if relation.niveau_acces != 'teaser':
                raise UserError(_("Le partage a déjà été autorisé."))
            if not relation.interet_exprime:
                raise UserError(_(
                    "Cet acteur n'a pas exprimé d'intérêt : il n'y a rien à "
                    "autoriser."))
            relation.niveau_acces = 'limited'
            relation.autorise_par_id = self.env.user
            relation.date_autorisation = fields.Datetime.now()
            relation.project_id.message_post(
                body=_("Partage du dossier autorisé avec %s.",
                       relation.partner_id.display_name),
                subtype_xmlid='mail.mt_note')
        return True

    def action_signer_nda(self):
        """Confirmation horodatée du NDA — pas de signature cryptographique.

        Même parti que sur le Module 1 : la signature électronique est hors
        périmètre assumé, la trace datée suffit à conditionner l'ouverture.
        """
        for relation in self:
            if not relation.nda_requis:
                raise UserError(_("Aucun NDA n'est requis sur cette relation."))
            if relation.nda_signe:
                raise UserError(_("Le NDA est déjà signé."))
            relation.nda_signe = True
            relation.date_nda = fields.Datetime.now()
            relation.project_id.message_post(
                body=_("NDA signé par %s.", relation.partner_id.display_name),
                subtype_xmlid='mail.mt_note')
        return True

    # ------------------------------------------------------------------
    # Les cinq actions de la section 14
    # ------------------------------------------------------------------
    # « Il ne doit pas avoir à comprendre le workflow interne CEO. Le moteur
    # transforme son choix en transition appropriée. »
    #
    # Cinq méthodes, une par bouton. L'acteur choisit dans son vocabulaire à
    # lui — intéressé, pas intéressé, j'ai une question — et c'est ici, d'un
    # seul côté du mur, que le choix devient une transition. Aucune de ces
    # méthodes n'expose un état au demandeur, et aucune ne lui en demande un.

    def action_decision_interesse(self):
        """★ Intéressé → le dossier passe en décision de l'acteur financier."""
        for relation in self:
            relation._ensure_dossier_ouvert()
            relation._enregistrer_decision('interesse')
            projet = relation.project_id
            if projet.state == 'mise_en_relation':
                projet.state = 'decision_financeur'
            projet.message_post(
                body=_("%s se déclare intéressé par le dossier.",
                       relation.partner_id.display_name),
                subtype_xmlid='mail.mt_note')
        return True

    def action_decision_informations(self, message=None):
        """? Besoin d'informations → la question part au comité.

        Le dossier ne bouge pas : une question n'est ni un oui ni un non. Le
        comité relaie vers le porteur — l'acteur n'a pas à savoir qui répond.
        """
        for relation in self:
            relation._ensure_dossier_ouvert()
            if not (message or '').strip():
                raise UserError(_("Formulez votre question avant de l'envoyer."))
            relation._enregistrer_decision('informations', message=message)
            relation.project_id.message_post(
                body=_("%(acteur)s demande des informations complémentaires :\n%(question)s",
                       acteur=relation.partner_id.display_name, question=message),
                partner_ids=relation.project_id._ceo_partners().ids,
                subtype_xmlid='mail.mt_note')
        return True

    def action_decision_accompagnement(self):
        """↗ Demander accompagnement CEO → déclencheur n°2 de la section 11.

        L'acteur pose sa condition ; le sous-processus d'accompagnement s'ouvre
        à côté du parcours, exactement comme lorsque le comité l'ouvre lui-même.
        """
        for relation in self:
            relation._ensure_dossier_ouvert()
            relation._enregistrer_decision('accompagnement')
            relation.project_id.sudo().action_accompagnement_demande_financeur(
                partner=relation.partner_id)
        return True

    def action_decision_rendez_vous(self, date_rendez_vous=None, message=None):
        """↔ Proposer un rendez-vous → la proposition arrive au comité."""
        for relation in self:
            relation._ensure_dossier_ouvert()
            relation._enregistrer_decision('rendez_vous', message=message)
            relation.date_rendez_vous = date_rendez_vous or False
            relation.project_id.message_post(
                body=_("%s propose un rendez-vous.",
                       relation.partner_id.display_name),
                partner_ids=relation.project_id._ceo_partners().ids,
                subtype_xmlid='mail.mt_note')
        return True

    def action_decision_non_interesse(self):
        """✕ Non intéressé → cet acteur sort, le dossier reste.

        Un refus n'écarte pas le projet : d'autres acteurs sont peut-être en
        relation, et c'est au comité de décider de la suite.
        """
        for relation in self:
            relation._ensure_dossier_ouvert()
            relation._enregistrer_decision('non_interesse')
            relation.project_id.message_post(
                body=_("%s n'est pas intéressé par le dossier.",
                       relation.partner_id.display_name),
                subtype_xmlid='mail.mt_note')
        return True

    def _ensure_dossier_ouvert(self):
        """On ne se prononce pas sur un dossier qu'on n'a pas lu.

        Les cinq actions ne s'offrent qu'à partir du dossier limité : au
        teaser, l'acteur n'a rien vu qui permette de décider.
        """
        self.ensure_one()
        if not self._niveau_atteint('limited'):
            raise UserError(_(
                "Le dossier ne vous a pas encore été ouvert : vous ne pouvez "
                "pas encore vous prononcer."))

    def _enregistrer_decision(self, decision, message=None):
        """La trace commune aux cinq choix — l'horodatage, rien de plus."""
        self.ensure_one()
        self.decision = decision
        self.date_decision = fields.Datetime.now()
        if message is not None:
            self.message_financeur = message

    def action_ouvrir_dossier_complet(self):
        """Dossier limité → dossier détaillé, sous condition du NDA.

        Dernier cran, réservé au comité : c'est lui qui organise la mise en
        relation et vérifie que le NDA, quand il est exigé, a bien été signé.
        """
        self.project_id._ensure_ceo()
        for relation in self:
            if relation.niveau_acces != 'limited':
                raise UserError(_(
                    "Le dossier détaillé s'ouvre depuis le dossier limité, "
                    "après autorisation du porteur."))
            if relation.nda_requis and not relation.nda_signe:
                raise UserError(_(
                    "Un NDA est requis et n'a pas été signé : le dossier "
                    "détaillé reste fermé."))
            relation.niveau_acces = 'full'
            relation.project_id.message_post(
                body=_("Dossier détaillé ouvert à %s.",
                       relation.partner_id.display_name),
                subtype_xmlid='mail.mt_note')
        return True
