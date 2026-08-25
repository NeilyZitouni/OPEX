from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

#: Quels types d'acteurs répondent à quel besoin. Codé en dur : c'est une
#: règle métier du dispositif, pas un paramètre.
TYPES_PAR_BESOIN = {
    'investisseur': ('investisseur', 'fonds', 'banque', 'partenaire_strategique'),
    'sponsor': ('sponsor', 'partenaire_strategique'),
    'financement_public': ('programme_public', 'banque'),
}

#: Le risque qu'un projet représente, déduit de sa maturité.
RISQUE_PAR_MATURITE = {
    'idee': 'elevee',
    'prototype': 'elevee',
    'mvp': 'moyenne',
    'premiers_client': 'moyenne',
    'croissance': 'faible',
}

#: Les trois niveaux d'appétence, ordonnés — pour mesurer un écart.
NIVEAUX_RISQUE = ('faible', 'moyenne', 'elevee')

#: Secteurs considérés comme porteurs d'impact, et comme technologiques.
#: Le dépôt express ne demande ni l'un ni l'autre (section 5) : on les déduit
#: du secteur plutôt que d'alourdir le formulaire du porteur.
SECTEURS_IMPACT = ('environnement', 'sante', 'formation', 'agroalimentaire')
SECTEURS_TECHNOLOGIQUES = ('numerique', 'energie', 'sante')


class OpexCrowdfundingMatchingCandidate(models.Model):
    """Un acteur financier proposé pour un projet (section 10).

    ⚠️ « Le matching est une **recommandation**. » Rien dans ce modèle ne
    déclenche de transition : le score classe des candidats, le comité décide.
    Aucune méthode ici ne touche à `project_id.state`.

    Pas d'apprentissage automatique : dix critères pondérés, écrits en Python,
    dont chacun rend sa contribution *et son explication*. Un score de 91 % qui
    ne saurait pas dire d'où viennent ses 91 points n'est pas défendable.
    """

    _name = 'opex.crowdfunding.matching.candidate'
    _description = "Candidat au matching financier"
    _order = 'score desc, id'
    _rec_name = 'partner_id'

    project_id = fields.Many2one(
        'opex.crowdfunding.project', string="Projet",
        required=True, ondelete='cascade', index=True,
    )
    partner_id = fields.Many2one(
        'res.partner', string="Acteur financier",
        required=True, ondelete='restrict', index=True,
    )
    candidate_type = fields.Selection(
        selection=lambda self: self.env['res.partner']._fields['cf_actor_type'].selection,
        string="Type d'acteur",
    )
    score = fields.Float(string="Score", digits=(5, 1), help="Sur 100.")
    detail = fields.Text(
        string="Explication du score",
        help="La contribution de chacun des dix critères. Obligatoire dès "
             "qu'un candidat est validé.",
    )
    state = fields.Selection([
        ('proposed',       "Proposé"),
        ('validated',      "Validé"),
        ('excluded',       "Exclu"),
        ('added_manually', "Ajouté manuellement"),
    ], string="État", default='added_manually', required=True)

    # Odoo 19 : `models.Constraint`, l'ancien `_sql_constraints` n'a plus cours.
    _project_partner_uniq = models.Constraint(
        'unique(project_id, partner_id)',
        "Cet acteur figure déjà parmi les candidats de ce projet.",
    )

    @api.constrains('state', 'detail')
    def _check_detail_si_valide(self):
        """Un candidat validé sans explication ne passe pas.

        La contrainte ne porte que sur l'état validé : un candidat exclu ou en
        cours d'ajout n'a pas encore à être justifié.
        """
        for candidate in self:
            if candidate.state == 'validated' and not (candidate.detail or '').strip():
                raise ValidationError(_(
                    "Expliquez le score de %s avant de le valider : un "
                    "pourcentage sans justification n'est pas défendable.",
                    candidate.partner_id.display_name))

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        """Le type d'acteur suit le référentiel, sans l'y enfermer."""
        for candidate in self:
            if candidate.partner_id.cf_actor_type:
                candidate.candidate_type = candidate.partner_id.cf_actor_type

    # ------------------------------------------------------------------
    # Le scoring — dix critères pondérés, explicables
    # ------------------------------------------------------------------
    def _evaluate(self):
        """Calcule le score et rédige son explication, ligne par ligne.

        ═══════════════════════════════════════════════════════════════════
        COÛT D'UN ONZIÈME CRITÈRE — pour le document de comparaison
        ═══════════════════════════════════════════════════════════════════
        Une méthode `_critere_*` (~12 lignes), une ligne dans le tableau
        ci-dessous, et surtout : **rééquilibrer les dix poids existants** pour
        que le total reste sur 100. Puis mise à jour du module et
        redéploiement. Changer un seul poids — passer le secteur de 15 à 20 —
        demande exactement la même chose : c'est du code.
        ═══════════════════════════════════════════════════════════════════
        """
        for candidate in self:
            # Les dix critères de la section 10, avec leurs poids. Total : 100.
            criteres = (
                (candidate._critere_type_financement, 20, "Type de financement"),
                (candidate._critere_secteur,          15, "Secteur"),
                (candidate._critere_ticket,           15, "Ticket d'investissement"),
                (candidate._critere_stade,            10, "Stade du projet"),
                (candidate._critere_localisation,      8, "Localisation"),
                (candidate._critere_appetence_risque,  8, "Appétence au risque"),
                (candidate._critere_type_porteur,      6, "Type de porteur"),
                (candidate._critere_impact,            6, "Impact"),
                (candidate._critere_technologie,       6, "Technologie"),
                (candidate._critere_historique,        6, "Historique"),
            )
            score = 0.0
            lignes = []
            for methode, poids, libelle in criteres:
                ratio, explication = methode()
                contribution = poids * ratio
                score += contribution
                lignes.append("%s : %.1f / %s — %s" % (
                    libelle, contribution, poids, explication))
            lignes.append("TOTAL : %.1f / 100" % score)
            candidate.score = score
            candidate.detail = "\n".join(lignes)
        return True

    def _critere_type_financement(self):
        """Le type d'acteur répond-il au besoin exprimé ?"""
        self.ensure_one()
        besoin = self.project_id.besoin_type
        attendus = TYPES_PAR_BESOIN.get(besoin, ())
        type_acteur = self.candidate_type or self.partner_id.cf_actor_type
        if not besoin or not type_acteur:
            return 0.5, "besoin ou type d'acteur non renseigné, critère neutralisé"
        if type_acteur in attendus:
            return 1.0, "ce type d'acteur répond au besoin exprimé"
        return 0.0, "ce type d'acteur ne correspond pas au besoin exprimé"

    def _critere_secteur(self):
        self.ensure_one()
        secteur = self.project_id.secteur
        partner = self.partner_id
        if not secteur:
            return 0.5, "secteur du projet non renseigné, critère neutralisé"
        if partner.cf_secteur and partner.cf_secteur == secteur:
            return 1.0, "secteur de prédilection de l'acteur"
        if partner.cf_tous_secteurs:
            return 0.6, "acteur généraliste, sans spécialité sur ce secteur"
        return 0.0, "l'acteur n'intervient pas dans ce secteur"

    def _critere_ticket(self):
        """Le besoin financier tombe-t-il dans la fourchette de l'acteur ?"""
        self.ensure_one()
        projet = self.project_id
        montant = projet.besoin_financier or projet.public_montant \
            or projet.sponsor_budget or projet.montant_indicatif
        partner = self.partner_id
        if not montant or not (partner.cf_ticket_min or partner.cf_ticket_max):
            return 0.5, "montant ou fourchette inconnus, critère neutralisé"
        minimum = partner.cf_ticket_min or 0.0
        maximum = partner.cf_ticket_max or float('inf')
        if minimum <= montant <= maximum:
            return 1.0, "le besoin tombe dans la fourchette de l'acteur"
        if minimum * 0.5 <= montant <= maximum * 1.5:
            return 0.5, "le besoin est proche de la fourchette de l'acteur"
        return 0.0, "le besoin est hors de la fourchette de l'acteur"

    def _critere_stade(self):
        self.ensure_one()
        stades = [code for code, _l in self.project_id._fields['maturite'].selection]
        maturite = self.project_id.maturite
        minimum = self.partner_id.cf_stade_min
        if not maturite or not minimum:
            return 0.5, "stade du projet ou seuil de l'acteur inconnu, critère neutralisé"
        ecart = stades.index(maturite) - stades.index(minimum)
        if ecart >= 0:
            return 1.0, "le projet a dépassé le stade minimum financé"
        if ecart == -1:
            return 0.5, "le projet est juste en deçà du stade minimum financé"
        return 0.0, "le projet est trop en amont pour cet acteur"

    def _critere_localisation(self):
        """La ville du porteur contre la zone d'intervention de l'acteur.

        Le dépôt express ne demande pas la localisation du projet (section 5) :
        on prend celle du contact porteur plutôt que d'ajouter un champ au
        formulaire pour un seul critère.
        """
        self.ensure_one()
        ville = (self.project_id.partner_id.city or '').strip().lower()
        zone = (self.partner_id.cf_localisation or '').strip().lower()
        if not ville or not zone:
            return 0.5, "localisation inconnue d'un côté, critère neutralisé"
        if ville == zone:
            return 1.0, "l'acteur intervient sur la zone du porteur"
        return 0.3, "l'acteur intervient sur une autre zone"

    def _critere_appetence_risque(self):
        self.ensure_one()
        risque = RISQUE_PAR_MATURITE.get(self.project_id.maturite)
        appetence = self.partner_id.cf_appetence_risque
        if not risque or not appetence:
            return 0.5, "risque du projet ou appétence de l'acteur inconnu, critère neutralisé"
        ecart = abs(NIVEAUX_RISQUE.index(risque) - NIVEAUX_RISQUE.index(appetence))
        if ecart == 0:
            return 1.0, "le risque du projet correspond à l'appétence de l'acteur"
        if ecart == 1:
            return 0.5, "le risque du projet s'écarte d'un cran de l'appétence de l'acteur"
        return 0.0, "le risque du projet est à l'opposé de l'appétence de l'acteur"

    def _critere_type_porteur(self):
        self.ensure_one()
        prefere = self.partner_id.cf_porteur_type_prefere
        if not prefere:
            return 0.5, "l'acteur n'exprime pas de préférence, critère neutralisé"
        if prefere == self.project_id.porteur_type:
            return 1.0, "type de porteur recherché par l'acteur"
        return 0.0, "l'acteur cible un autre type de porteur"

    def _critere_impact(self):
        self.ensure_one()
        if not self.partner_id.cf_recherche_impact:
            return 0.5, "l'acteur ne cible pas particulièrement l'impact, critère neutralisé"
        if self.project_id.secteur in SECTEURS_IMPACT:
            return 1.0, "secteur reconnu comme porteur d'impact"
        return 0.0, "l'acteur cherche de l'impact, ce secteur n'en relève pas"

    def _critere_technologie(self):
        self.ensure_one()
        if not self.partner_id.cf_interet_technologie:
            return 0.5, "l'acteur ne cible pas particulièrement la technologie, critère neutralisé"
        if self.project_id.secteur in SECTEURS_TECHNOLOGIQUES:
            return 1.0, "secteur à composante technologique"
        return 0.0, "l'acteur cherche de la technologie, ce secteur n'en relève pas"

    def _critere_historique(self):
        """Combien de fois cet acteur a-t-il déjà été retenu par le comité ?

        Lu dans les candidatures validées, pas dans un champ à tenir à jour :
        l'historique se constate, il ne se saisit pas.
        """
        self.ensure_one()
        anterieures = self.search_count([
            ('partner_id', '=', self.partner_id.id),
            ('state', '=', 'validated'),
            ('id', '!=', self.id),
        ])
        if anterieures >= 3:
            return 1.0, "acteur déjà retenu %s fois par le comité" % anterieures
        if anterieures >= 1:
            return 0.6, "acteur déjà retenu %s fois par le comité" % anterieures
        return 0.3, "aucune opération antérieure avec cet acteur"

    # ------------------------------------------------------------------
    # Ce que le comité fait de la recommandation
    # ------------------------------------------------------------------
    # Valider / Modifier / Exclure / Ajouter. Aucune de ces méthodes ne touche
    # à l'état du projet : la recommandation ne décide de rien.

    def action_validate(self):
        """Le comité retient cet acteur."""
        for candidate in self:
            if not (candidate.detail or '').strip():
                candidate._evaluate()
            candidate.state = 'validated'
        return True

    def action_exclude(self):
        """Le comité écarte cet acteur, malgré son score."""
        self.state = 'excluded'
        return True

    def action_reevaluate(self):
        """Recalcule score et explication après modification du référentiel."""
        return self._evaluate()
