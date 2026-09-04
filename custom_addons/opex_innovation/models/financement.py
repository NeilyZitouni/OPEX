from odoo import _, api, fields, models


class ProjectFinancement(models.Model):
    """Section 25 — le suivi du financement, et section 26 — ce que
    l'investisseur a le droit d'en voir.

    Écrit dans un fichier à part plutôt qu'ajouté à `innovation_project.py` :
    l'Extension 17 se relit d'un bloc, et le modèle projet ne devient pas le
    fourre-tout où chaque extension dépose ses champs.
    """

    _inherit = 'opex.innovation.project'

    # ------------------------------------------------------------
    # Section 25 — Suivi du financement
    # ------------------------------------------------------------

    # **Pas un nouveau champ de stockage.**
    #
    # Le cahier des charges nomme ce champ `financement_recherche`. Or le
    # montant recherché existe déjà depuis la section 9 sous le nom
    # `montant_recherche`, et il est déjà lu par ailleurs : le critère de
    # matching financier du Smart Crowdfunding le compare au ticket maximum de
    # l'investisseur, et la règle `scf_montant_defini` en fait une condition de
    # transition.
    #
    # Créer un second champ donnerait deux réponses possibles à « de combien ce
    # projet a-t-il besoin ». Elles divergeraient au premier écran qui n'écrit
    # que l'un des deux, et le matching se tromperait sans rien signaler.
    #
    # Le nom demandé est donc fourni comme **alias** : même stockage, deux
    # portes d'entrée, une seule vérité.
    financement_recherche = fields.Monetary(
        related='montant_recherche',
        readonly=False,
        string="Financement recherché",
        currency_field='currency_id',
        help="Alias de « Montant recherché » (section 9). Même valeur, même "
             "stockage : le projet n'a qu'un seul besoin de financement.",
    )

    financement_obtenu = fields.Monetary(
        string="Financement obtenu",
        currency_field='currency_id',
        tracking=True,
        help="Montant effectivement engagé par les acteurs financiers. Saisi "
             "par le cluster à mesure des accords.",
    )

    progression_financement = fields.Float(
        string="Progression du financement",
        compute='_compute_progression_financement',
        store=True,
        digits=(5, 2),
        help="Part du besoin couverte, en pourcentage.",
    )

    @api.depends('financement_obtenu', 'montant_recherche')
    def _compute_progression_financement(self):
        for project in self:
            besoin = project.montant_recherche or 0.0
            # Un besoin non chiffré ne vaut pas une progression de 100 % : sans
            # dénominateur, il n'y a pas de progression, et afficher 0 % est la
            # seule réponse qui ne raconte rien de faux.
            if besoin <= 0:
                project.progression_financement = 0.0
                continue
            obtenu = project.financement_obtenu or 0.0
            # Plafonné à 100 : un surfinancement reste un besoin couvert, et une
            # barre de progression à 140 % n'a pas de sens à l'écran. Le
            # dépassement reste lisible dans les deux montants eux-mêmes.
            project.progression_financement = min(100.0, obtenu / besoin * 100.0)

    # ------------------------------------------------------------
    # Le parcours de la section 25
    # ------------------------------------------------------------

    #: « Besoin de financement → Matching investisseurs → Investisseur
    #: intéressé → Échange / analyse → Financement ». Table plutôt que cinq
    #: `if` : l'ordre se lit d'un coup d'œil et en insérer une étape est une
    #: ligne.
    _FINANCEMENT_STEPS = [
        ('besoin', "Besoin de financement"),
        ('matching', "Matching investisseurs"),
        ('interet', "Investisseur intéressé"),
        ('echange', "Échange / analyse"),
        ('finance', "Financement"),
    ]

    def financement_steps(self):
        """Où en est le financement, sans champ d'état supplémentaire.

        Rien n'est stocké ici. Chaque étape est **déduite** de données qui
        existent déjà : le besoin déclaré, les candidats investisseurs proposés
        par le moteur, leurs réponses, le montant obtenu.

        Un champ `etape_financement` aurait été plus simple à lire, et faux dès
        la première divergence — un investisseur qui répond sans que personne
        ne pense à faire avancer le champ. Ici, la question est reposée à
        chaque affichage.
        """
        self.ensure_one()
        instance = self.workflow_instance_id
        Candidate = self.env['opex.matching.candidate'].sudo()

        investisseurs = Candidate.browse()
        if instance:
            investisseurs = Candidate.search([
                ('instance_id', '=', instance.id),
                ('candidate_type', 'in', ('investisseur', 'sponsor')),
            ])
        retenus = investisseurs.filtered(lambda c: c.state == 'accepted')
        interesses = retenus.filtered(
            lambda c: c.candidate_response == 'interested')

        reached = {
            'besoin': bool(self.besoin_financement or self.montant_recherche),
            'matching': bool(investisseurs),
            'interet': bool(interesses),
            # « Échange / analyse » : un investisseur intéressé à qui le
            # dossier détaillé a été ouvert. C'est la mise en relation, et elle
            # se lit sur le niveau d'accès de l'acteur, pas sur un drapeau.
            'echange': bool(interesses) and self._financement_en_echange(),
            'finance': bool(self.financement_obtenu),
        }

        steps = []
        current_found = False
        for code, label in self._FINANCEMENT_STEPS:
            done = reached.get(code, False)
            state = 'done' if done else 'todo'
            if not done and not current_found:
                state, current_found = 'current', True
            steps.append({'code': code, 'label': label, 'state': state})
        return steps

    def _financement_en_echange(self):
        """Un acteur financier a-t-il obtenu l'accès au dossier détaillé ?

        Lu sur `instance.actor`, comme tout le reste de la visibilité. Le
        passage de `limited` à `full` est précisément ce que signifie « le
        dossier lui a été ouvert ».
        """
        self.ensure_one()
        instance = self.workflow_instance_id
        if not instance:
            return False
        role = self.env.ref('opex_workflow.role_investisseur',
                            raise_if_not_found=False)
        if not role:
            return False
        return bool(instance.sudo().actor_ids.filtered(
            lambda a: a.role_id == role and a.access_level == 'full'))

    # ------------------------------------------------------------
    # Section 26 — ce que l'investisseur voit du projet
    # ------------------------------------------------------------

    @api.model
    def _matching_teaser(self, candidate):
        """Ajoute au teaser les informations financières — **et seulement pour
        un acteur financier**.

        Section 32 : l'investisseur voit « les informations financières
        autorisées et la progression du financement ». Un expert, lui, voit
        « les informations autorisées » de la section 20 — pas le budget.

        L'ancienne version renvoyait la même liste fermée à tout le monde.
        Élargir cette liste sans distinguer le type de candidat aurait donné à
        chaque expert proposé le montant recherché par le porteur. C'est une
        fuite, même si personne ne l'aurait vue passer : le gabarit affiche ce
        qu'on lui donne.
        """
        teaser = super()._matching_teaser(candidate)

        project = candidate.instance_id._get_record()
        if not project or project._name != 'opex.innovation.project':
            return teaser
        if candidate.candidate_type not in ('investisseur', 'sponsor'):
            return teaser

        project = project.sudo()
        maturites = dict(project._fields['maturite'].selection)
        potentiels = dict(project._fields['potentiel_commercial'].selection)

        teaser.update({
            'maturite': maturites.get(project.maturite, _("Non précisée")),
            'potentiel': potentiels.get(
                project.potentiel_commercial, _("Non précisé")),
            'financement_recherche': project.montant_recherche,
            'financement_obtenu': project.financement_obtenu,
            'progression_financement': project.progression_financement,
            'currency': project.currency_id,
            'financier': True,
        })
        return teaser

    @api.model
    def _matching_detail(self, candidate):
        """Le « Voir le projet » de la section 26 — une liste fermée de plus.

        Un cran plus détaillé que la vignette, et toujours **un dictionnaire,
        jamais le recordset**. Passer le projet au gabarit lui donnerait accès
        à tout : coordonnées du porteur, évaluations du comité, historique,
        documents. Le gabarit affiche ce qu'on lui donne, et ce qui n'est pas
        dans ce dictionnaire ne peut pas fuir par inadvertance.

        Ce qui s'ajoute à la vignette : le problème, la solution, le marché
        visé, la proposition de valeur et le parcours de financement. Ce qui
        ne s'y ajoute pas, et n'y sera jamais : l'identité du porteur, ses
        coordonnées, les notes des évaluateurs.
        """
        detail = self._matching_teaser(candidate)

        project = candidate.instance_id._get_record()
        if not project or project._name != 'opex.innovation.project':
            return detail
        project = project.sudo()

        detail.update({
            'probleme': project.probleme or '',
            'solution': project.solution or '',
            'marche_cible': project.marche_cible or '',
            'proposition_valeur': project.proposition_valeur or '',
            'etapes_financement': project.financement_steps(),
        })
        return detail
