from odoo import _, api, fields, models

#: Les quatre colonnes du §10, plus les deux que le document ne nomme pas mais
#: que le pool contient forcément : ce qui n'est pas encore déposé, et ce qui
#: est sorti. Les cacher obligerait le responsable à changer de filtre pour
#: relancer un invité ou retrouver un écarté.
POOL_COLUMNS = [
    ('en_attente', "En attente du candidat"),
    ('nouveaux', "Nouveaux"),
    ('qualifies', "Qualifiés"),
    ('short_list', "Short-list"),
    ('retenus', "Retenus"),
    ('sans_suite', "Sans suite"),
]

#: Étape du workflow → colonne du Kanban. Table plutôt que six `if` : la
#: correspondance se lit d'un coup d'œil, et ajouter une étape à la définition
#: est une ligne ici.
STAGE_TO_COLUMN = {
    'invited': 'en_attente',
    'viewed': 'en_attente',
    'interested': 'en_attente',
    'applied': 'nouveaux',
    'screened': 'qualifies',
    'shortlisted': 'short_list',
    'selected': 'retenus',
    'declined': 'sans_suite',
    'rejected': 'sans_suite',
    'withdrawn': 'sans_suite',
}


class MissionApplicationPool(models.Model):
    """Le pool unique du §10 — Kanban et alertes d'éligibilité.

    « Toutes les candidatures convergent dans un objet unique, indépendamment
    de leur origine. Chaque candidature porte une source : matching, portail,
    invitation directe ou ajout manuel. »

    Rien n'est ajouté ici pour faire converger quoi que ce soit : elles
    convergent **déjà**, depuis l'Extension 1 — un seul modèle, une seule
    définition de workflow, un champ `source`. Ce fichier ajoute ce qui manquait
    pour en tirer parti : la colonne de Kanban et les alertes.
    """

    _inherit = 'opex.mission.application'

    #
    # LA COLONNE DE KANBAN — UNE PROJECTION, PAS UN ÉTAT
    #
    #
    # C'est le même parti que `is_published` sur l'appel à mission, et il
    # mérite d'être redit parce que c'est exactement le champ qu'on nous
    # reprochera en soutenance :
    #
    # `pool_column` est **calculé depuis l'étape du workflow**, stocké pour être
    # groupable par le Kanban, et **jamais écrit à la main** (`readonly=True`,
    # aucune écriture nulle part). Il ne peut donc pas diverger de l'étape : ce
    # n'est pas un second état, c'est une lecture du premier.
    #
    # Pourquoi ne pas grouper directement sur `workflow_stage_id` ? Parce que la
    # définition compte **dix** étapes et que le §10 en demande **quatre**. Un
    # Kanban à dix colonnes n'est pas un outil de décision, c'est une frise. La
    # carte, elle, affiche l'étape réelle — rien n'est masqué.

    pool_column = fields.Selection(
        POOL_COLUMNS,
        string="Colonne du pool",
        compute='_compute_pool_column',
        store=True,
        readonly=True,
        index=True,
        group_expand='_group_expand_pool_column',
        help="Projection de l'étape du workflow sur les colonnes du §10. "
             "Jamais écrite à la main : l'avancement reste porté par "
             "`workflow_stage_id`.",
    )

    @api.depends('workflow_stage_id')
    def _compute_pool_column(self):
        for application in self:
            code = application.workflow_stage_id.sudo().code
            application.pool_column = STAGE_TO_COLUMN.get(code, 'en_attente')

    @api.model
    def _group_expand_pool_column(self, columns, domain):
        """Affiche **toutes** les colonnes, même vides.

        Sans cela, Odoo ne montre que les colonnes qui contiennent quelque
        chose : un pool où personne n'est encore qualifié n'aurait pas de
        colonne « Qualifiés », et le responsable ne verrait pas où glisser une
        carte. Un Kanban dont les colonnes apparaissent au fur et à mesure ne
        se lit pas comme un processus.
        """
        return [code for code, _label in POOL_COLUMNS]

    #
    # §10 — LES ALERTES D'ÉLIGIBILITÉ
    #

    alert_count = fields.Integer(
        string="Alertes", compute='_compute_alert_count',
        help="Nombre de points de vigilance sur cette candidature.")
    has_blocking_alert = fields.Boolean(
        string="Alerte bloquante", compute='_compute_alert_count')

    #: Méthode de calcul **distincte** de celle de `pool_column`.
    #: Le registre refuse un `compute` qui produirait à la fois un champ stocké
    #: et des champs non stockés : lire un compteur d'affichage déclencherait
    #: une écriture de la colonne. Leçon de l'Extension 1, règle 9.
    @api.depends('workflow_stage_id', 'disponibilite', 'tarif_propose',
                 'partner_id', 'mission_id')
    def _compute_alert_count(self):
        for application in self:
            alertes = application.eligibility_alerts()
            application.alert_count = len(alertes)
            application.has_blocking_alert = any(
                alerte['niveau'] == 'danger' for alerte in alertes)

    def eligibility_alerts(self):
        """Les points de vigilance sur cette candidature — §10.

        POURQUOI CET ÉCRAN EST NÉCESSAIRE, ET PAS SEULEMENT CONFORTABLE

        Les critères éliminatoires de l'Extension 4 filtrent le **vivier du
        matching**. Un candidat arrivé par le **portail** (§7) ne passe par
        aucun vivier : il clique « Je suis intéressé » et il entre dans le pool.

        Autrement dit, l'éliminatoire ne protège **que** le canal A. Sans ces
        alertes, un candidat sans la certification obligatoire arriverait dans
        la short-list sans que rien ne le signale — et les deux canaux du §8 ne
        seraient plus comparables, ce que le §21 exige.

        Ces alertes ne bloquent rien : elles **disent**. La sélection reste
        « réalisée par les responsables habilités du cluster » (§16).

        Renvoie une liste de dictionnaires, jamais un recordset : c'est le
        modèle qui décide de ce que l'écran a le droit de lire.
        """
        self.ensure_one()
        application = self.sudo()
        mission = application.mission_id
        partner = application.partner_id
        alertes = []

        # Le profil
        profile = partner.opex_mission_profile()
        if not profile:
            alertes.append({
                'niveau': 'danger',
                'titre': _("Aucun profil expert"),
                'detail': _("Ce candidat n'a pas de profil : il ne devrait pas "
                            "pouvoir candidater (règle 1 du §39)."),
            })
        elif not partner.expert_profile_id:
            alertes.append({
                'niveau': 'info',
                'titre': _("Profil non encore référencé"),
                'detail': _("Candidat externe : son profil est en cours "
                            "d'instruction. Il pourra intégrer le référentiel "
                            "s'il est qualifié (§7)."),
            })

        # Les critères éliminatoires, rejoués sur ce candidat
        #
        # On réutilise **les critères de l'appel**, pas une liste écrite ici.
        # Le jour où le cluster change un critère éliminatoire, ces alertes
        # suivent — deux listes auraient divergé au premier ajustement.
        instance = mission.workflow_instance_id
        if instance:
            eliminatoires = mission.matching_criteria().filtered(
                'is_eliminatoire')
            admis, motifs = mission._matching_check_eliminatoires(
                instance, partner, eliminatoires)
            if not admis:
                alertes.append({
                    'niveau': 'danger',
                    'titre': _("Critère obligatoire non rempli"),
                    'detail': " ; ".join(motifs),
                })

        # Les compétences
        if mission.skill_ids:
            manquantes = mission.skill_ids - partner.expert_skill_competence_ids
            if manquantes == mission.skill_ids:
                alertes.append({
                    'niveau': 'warning',
                    'titre': _("Aucune compétence recherchée déclarée"),
                    'detail': _("L'appel demande : %s.")
                    % ", ".join(mission.skill_ids.mapped('name')),
                })
            elif manquantes:
                alertes.append({
                    'niveau': 'info',
                    'titre': _("Compétences partiellement couvertes"),
                    'detail': _("Manquent : %s.")
                    % ", ".join(manquantes.mapped('name')),
                })

        # La disponibilité
        if application.disponibilite == 'non':
            alertes.append({
                'niveau': 'danger',
                'titre': _("Candidat déclaré non disponible"),
                'detail': application.disponibilite_commentaire or '',
            })
        elif not partner.expert_disponible:
            alertes.append({
                'niveau': 'warning',
                'titre': _("Aucune période de disponibilité au profil"),
                'detail': _("Le candidat n'a pas déclaré de disponibilité "
                            "couvrant aujourd'hui."),
            })

        # Le budget
        #
        # Même arithmétique que le critère « Budget 10 % » de l'Extension 4 :
        # on compare au budget **journalier**, pas au budget total.
        if mission.budget_estimatif and application.tarif_propose:
            journalier = mission.budget_estimatif / (
                mission.duree_estimee_jours or 1)
            if (application.type_tarif == 'tjm'
                    and application.tarif_propose > journalier):
                alertes.append({
                    'niveau': 'warning',
                    'titre': _("Tarif au-dessus du budget"),
                    'detail': _("TJM proposé %(tarif)s pour un budget "
                                "journalier de %(budget).0f.")
                    % {'tarif': application.tarif_propose,
                       'budget': journalier},
                })
            elif (application.type_tarif in ('forfait', 'montant')
                    and application.tarif_propose > mission.budget_estimatif):
                alertes.append({
                    'niveau': 'warning',
                    'titre': _("Proposition au-dessus du budget"),
                    'detail': _("%(tarif)s proposés pour un budget de "
                                "%(budget)s.")
                    % {'tarif': application.tarif_propose,
                       'budget': mission.budget_estimatif},
                })

        # Le dossier lui-même
        if application.workflow_stage_id.sudo().code in (
                'applied', 'screened', 'shortlisted') and not application.score:
            alertes.append({
                'niveau': 'info',
                'titre': _("Candidature non scorée"),
                'detail': _("Le Smart Matching n'a pas encore été lancé, ou "
                            "cette candidature est arrivée par le portail. "
                            "Qualifiez-la pour obtenir un score."),
            })
        if not application.consentement and application.pool_column != 'en_attente':
            alertes.append({
                'niveau': 'info',
                'titre': _("Conditions non acceptées"),
                'detail': _("Le candidat n'a pas coché l'acceptation des "
                            "conditions de candidature (§9)."),
            })
        return alertes

    #
    # La comparaison — §10
    #

    def comparison_row(self):
        """Ce qu'une candidature apporte à l'écran de comparaison.

        Un dictionnaire, jamais le recordset : le responsable compare des
        candidats, il n'a pas à recevoir l'objet entier et, de fil en aiguille,
        le profil complet de chacun. Motif du `_matching_teaser()` du Module 2.

        **Les mêmes clés pour toutes les origines.** C'est le deuxième critère
        d'acceptation du §21 : « une candidature issue du matching et une
        candidature Web sont comparables dans le même écran ». Elles le sont
        parce qu'elles sortent d'ici avec la même forme — `source` n'est qu'une
        colonne de plus.
        """
        self.ensure_one()
        application = self.sudo()
        partner = application.partner_id
        profile = partner.opex_mission_profile()
        return {
            'id': application.id,
            'candidat': partner.display_name,
            'source': dict(
                application._fields['source'].selection).get(
                application.source, ''),
            'etape': application.workflow_stage_label or '',
            'colonne': application.pool_column,
            'score': application.score,
            'explication': application.score_detail or '',
            'disponibilite': dict(
                application._fields['disponibilite'].selection).get(
                application.disponibilite, '—'),
            'delai': application.delai_propose_jours,
            'tarif': application.tarif_propose,
            'type_tarif': dict(
                application._fields['type_tarif'].selection).get(
                application.type_tarif, ''),
            'competences': partner.expert_skill_competence_ids.mapped('name'),
            'seniorite': partner.expert_seniorite or '',
            'certifications': partner.expert_certification_names or '',
            'reputation': partner.expert_reputation,
            'experiences': profile.experience_count if profile else 0,
            'alertes': application.eligibility_alerts(),
            'motivation': application.motivation or '',
            'methodologie': application.methodologie or '',
            'pieces': len(application.document_ids),
        }
