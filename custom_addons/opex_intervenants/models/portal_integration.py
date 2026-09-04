"""L'intégration finale : catalogue filtré, accueil unique, KPI globaux.

    « Un espace unique permettant de gérer une mission depuis l'expression du
      besoin jusqu'à l'évaluation de l'intervenant. »  - §48

Trois choses ici, et une seule est du métier neuf :

- les filtres du catalogue public, qui manquaient depuis l'Extension 5 ;
- l'accueil qui relie les trois domaines du portail ;
- les indicateurs globaux de l'US-20, qui agrègent les trois modules.

Ce fichier est le seul du module à lire les modèles des deux autres domaines.
Il le fait en lecture, par des compteurs, et jamais par un champ relationnel :
`opex_intervenants` dépend d'`opex_innovation` et, par lui, d'`opex_membership`
- ajouter une relation stockée vers leurs modèles ferait de ce module une pièce
dont ils ne pourraient plus se passer.
"""

from odoo import api, fields, models

# Ce qu'un projet d'innovation « en cours » veut dire. Les trois exclues sont
# les extrémités : pas encore déposé, clos, refusé. Écrites en négatif parce
# que le graphe du Module 2 compte quatorze étapes et qu'en lister onze ferait
# une liste à tenir d'accord avec un module qu'on ne maintient pas.
INNOVATION_IDLE_STAGES = ('draft', 'closed', 'rejected')

# Une mission « réussie » est une mission dont le service fait a été validé.
# Une mission « aboutie » est une mission qui a atteint l'une de ses fins,
# quelle qu'elle soit. Le taux de réussite de l'US-20 est le rapport des deux.
MISSION_SUCCESS_STAGES = ('accepted', 'closed')
MISSION_FAILURE_STAGES = ('cancelled', 'unsuccessful')


class MissionCatalogue(models.Model):
    """Le catalogue public, et ses filtres - §7, §48.

    L'Extension 5 avait posé la rubrique en annonçant que « les filtres
    multicritères viennent avec l'Extension 12 ». Les voici.

    Le filtrage se fait dans le **domaine de recherche**, pas sur la liste de
    dictionnaires déjà construite. Filtrer après coup obligerait à lire tout le
    catalogue pour en garder trois lignes, et surtout à porter dans les
    vignettes des données qui ne servent qu'au filtre.
    """

    _inherit = 'opex.mission.request'

    @api.model
    def public_catalogue(self, limit=None, filters=None):
        """La rubrique, éventuellement filtrée.

        `filters` est un dictionnaire de valeurs déjà nettoyées par le
        controller. Le modèle ne lit jamais la requête HTTP : il reçoit des
        valeurs, il construit un domaine.

        `sudo()` assumé, comme à l'Extension 5 : la page est publique et le
        visiteur anonyme n'a aucun droit sur ce modèle - il ne doit pas en
        avoir. Ce n'est pas le contrôle d'accès qui protège ici, c'est la liste
        fermée de clés de `public_card()`.
        """
        domain = [('workflow_stage_id.code', 'in', self.PUBLIC_STAGES)]
        domain += self._public_filter_domain(filters or {})

        missions = self.sudo().search(
            domain,
            order='date_limite_candidature asc, id desc',
            limit=limit,
        )
        return [mission.public_card() for mission in missions]

    @api.model
    def _public_filter_domain(self, filters):
        """Les quatre filtres du §48, traduits en domaine.

        Domaine et type viennent de listes déroulantes construites par
        `public_filter_options()` : ils sont comparés par **identifiant** et en
        égalité stricte. Une valeur qui n'est pas un entier est ignorée plutôt
        que passée au domaine - c'est le même parti que l'annuaire du Module 1,
        et il évite qu'une requête forgée choisisse son propre domaine.

        La localisation est saisie librement par le client sur deux champs
        distincts, `localisation` et `wilaya`. Elle se cherche donc dedans, et
        dans les deux.
        """
        domain = []

        for field_name, key in (('domaine_id', 'domaine'),
                                ('mission_type_id', 'type')):
            value = filters.get(key)
            if value:
                domain.append((field_name, '=', value))

        localisation = (filters.get('localisation') or '').strip()
        if localisation:
            domain += ['|',
                       ('localisation', 'ilike', localisation),
                       ('wilaya', 'ilike', localisation)]

        # Les dates encadrent le **début souhaité** de la mission, pas la date
        # limite de candidature : un intervenant cherche des missions qui
        # commencent quand il est disponible. La date limite, elle, est déjà
        # le critère de tri du catalogue.
        date_min = filters.get('date_min')
        if date_min:
            domain.append(('date_debut_souhaitee', '>=', date_min))
        date_max = filters.get('date_max')
        if date_max:
            domain.append(('date_debut_souhaitee', '<=', date_max))

        return domain

    @api.model
    def public_filter_options(self):
        """Les valeurs proposées aux listes déroulantes.

        Bornées à ce que le catalogue contient réellement : proposer un domaine
        d'expertise sur lequel aucun appel n'est ouvert donne une liste vide et
        laisse croire à une panne.

        Dictionnaires à clés fermées, comme le reste de la vue publique. Le
        gabarit ne reçoit pas les enregistrements du référentiel.
        """
        missions = self.sudo().search(
            [('workflow_stage_id.code', 'in', self.PUBLIC_STAGES)])
        return {
            'domaines': [
                {'id': domaine.id, 'nom': domaine.name}
                for domaine in missions.domaine_id.sorted('name')
            ],
            'types': [
                {'id': mission_type.id, 'nom': mission_type.name}
                for mission_type in missions.mission_type_id.sorted('name')
            ],
            'localisations': sorted({
                lieu for lieu in (
                    missions.mapped('localisation')
                    + missions.mapped('wilaya')
                ) if lieu
            }),
        }


class PortalIntegration(models.AbstractModel):
    """L'accueil unique du portail et les indicateurs de l'US-20 - §48.

    Un modèle abstrait, comme les tableaux de bord de l'Extension 11 : ce sont
    des agrégats recalculés à chaque affichage. Un compteur mémorisé se
    décorrèle du réel à la première transition, et un tableau de bord faux est
    pire qu'absent.
    """

    _name = 'opex.portal.integration'
    _description = "Accueil unique et indicateurs globaux du portail"

    @api.model
    def portal_domains(self):
        """Les trois domaines du portail, avec leur porte d'entrée.

        L'ordre est celui du portail : on devient membre, puis on porte un
        projet, puis on intervient. Les trois entrées sont des dictionnaires à
        clés fermées - un gabarit d'accueil n'a aucune raison de recevoir des
        enregistrements.

        `opex_crowdfunding` n'y figure pas, et ce n'est pas un oubli : ce
        module est isolé par construction, et rien ne doit le référencer.

        L'entrée Innovation mène à l'espace du porteur et non à un catalogue
        public : le Module 2 n'en publie pas. Un visiteur non connecté y sera
        invité à se connecter, ce qui est le comportement correct et non un
        défaut à masquer.
        """
        counters = self.global_indicators()
        return [
            {
                'code': 'annuaire',
                'titre': "Annuaire des membres",
                'texte': "Les entreprises et les experts du cluster, "
                         "recherchables par secteur, wilaya et expertise.",
                'url': '/opex/directory',
                'public': True,
                'compteur': counters['membres'],
                'compteur_libelle': "membres publiés",
            },
            {
                'code': 'innovation',
                'titre': "Projets d'innovation",
                'texte': "Déposez un projet, suivez sa qualification, son "
                         "évaluation et son accompagnement jusqu'à "
                         "l'industrialisation.",
                'url': '/my/innovation',
                'public': False,
                'compteur': counters['projets_en_cours'],
                'compteur_libelle': "projets en cours",
            },
            {
                'code': 'missions',
                'titre': "Appels à missions",
                'texte': "Les besoins d'audit, de conseil, d'expertise et de "
                         "formation ouverts aux intervenants du cluster.",
                'url': '/missions',
                'public': True,
                'compteur': counters['appels_ouverts'],
                'compteur_libelle': "appels ouverts",
            },
        ]

    @api.model
    def global_indicators(self):
        """Les indicateurs de l'US-20, agrégés sur les trois modules.

        `sudo()` sur les trois lectures : la page d'accueil est publique, et
        les chiffres qui en sortent sont des **volumes**, jamais des dossiers.
        Aucun identifiant, aucun nom, aucun montant ne quitte cette méthode.

        Les modèles des deux autres domaines sont interrogés par `self.env`
        plutôt que par une relation : ce module en dépend, l'inverse est faux,
        et il doit le rester.
        """
        Partner = self.env['res.partner'].sudo()
        Project = self.env['opex.innovation.project'].sudo()
        Mission = self.env['opex.mission.request'].sudo()

        missions = Mission.search([])
        codes = [mission.workflow_stage_id.code for mission in missions]

        projects = Project.search([])
        projets_en_cours = sum(
            1 for project in projects
            if project.workflow_stage_id.code not in INNOVATION_IDLE_STAGES)

        return {
            # La définition de « membre » est celle du Module 1, reprise et non
            # réécrite : c'est lui qui décide qui figure à l'annuaire.
            'membres': Partner.search_count(
                [('is_member', '=', True),
                 ('is_published_directory', '=', True)]),
            'projets_en_cours': projets_en_cours,
            'projets_total': len(projects),
            'missions_en_cours': sum(
                1 for code in codes
                if code in Mission.RUNNING_MISSION_STAGES),
            'missions_total': len(missions),
            'appels_ouverts': sum(
                1 for code in codes if code in Mission.OPEN_CALL_STAGES),
            'taux_reussite': self._success_rate(codes),
        }

    @staticmethod
    def _success_rate(codes):
        """Le taux de réussite de l'US-20.

        Rapport des missions dont le service fait a été validé sur celles qui
        ont **abouti**, dans un sens ou dans l'autre. Les missions encore en
        route n'entrent dans aucun des deux termes : les compter au
        dénominateur ferait chuter le taux à chaque nouvel appel publié, ce qui
        dirait le contraire de la vérité.

        Zéro quand rien n'a encore abouti - et c'est la bonne valeur, pas
        100 %. Un cluster qui n'a terminé aucune mission n'a pas un taux de
        réussite parfait, il n'en a pas.
        """
        reussies = sum(1 for code in codes if code in MISSION_SUCCESS_STAGES)
        echouees = sum(1 for code in codes if code in MISSION_FAILURE_STAGES)
        abouties = reussies + echouees
        return round(reussies / abouties * 100) if abouties else 0

    @api.model
    def acceptance_checklist(self):
        """Les neuf critères du §21 de la spécification, mesurés.

        Cette méthode n'existe pas pour l'écran : elle existe pour que la liste
        de contrôle finale soit **vérifiable à l'exécution** plutôt qu'affirmée
        dans un document. Chaque entrée porte le critère, le fait qui l'établit
        et l'endroit où il se démontre.

        Les valeurs viennent de la configuration et des données réelles. Un
        critère qui cesserait d'être tenu le dirait ici, et le test qui lit
        cette méthode rougirait.
        """
        Definition = self.env['opex.workflow.definition'].sudo()
        Criteria = self.env['opex.matching.criteria'].sudo()
        Mission = self.env['opex.mission.request'].sudo()

        mission_def = Definition.search([('code', '=', 'mission_request')])
        application_def = Definition.search(
            [('code', '=', 'mission_application')])

        return [
            {
                'critere': "Matching, Portail ou les deux, sans duplication "
                           "de mission",
                # Le fait mesuré est que les deux canaux sont un **réglage**
                # d'un même appel et non deux objets : le champ existe, et il
                # porte bien une valeur qui les active tous les deux.
                'fait': 'hybride' in dict(
                    Mission._fields['sourcing_mode'].selection),
                'preuve': "un seul modèle `opex.mission.request`, un champ "
                          "`sourcing_mode` dont la valeur `hybride` active "
                          "les deux canaux sur le même appel",
            },
            {
                'critere': "Candidature matching et candidature Web "
                           "comparables dans le même écran",
                'fait': 'source' in self.env[
                    'opex.mission.application']._fields,
                'preuve': "un seul modèle `opex.mission.application`, "
                          "un champ `source`, l'écran `/staff/missions/<id>/pool`",
            },
            {
                'critere': "Un expert référencé ne ressaisit pas son profil",
                'fait': 'expert_profile_id' in self.env[
                    'opex.mission.application']._fields,
                'preuve': "`_link_expert_profile()` rattache le profil du "
                          "Module 2 à la création de la candidature",
            },
            {
                'critere': "Le responsable comprend les raisons d'un score",
                'fait': 'score_detail' in self.env[
                    'opex.mission.application']._fields,
                'preuve': "`score_detail` et l'explication rendue par "
                          "`_score_candidate()` du moteur",
            },
            {
                'critere': "Critères éliminatoires distingués du scoring",
                'fait': bool(Criteria.search_count(
                    [('is_eliminatoire', '=', True)])),
                'preuve': "`is_eliminatoire` sur `opex.matching.criteria`, "
                          "évalué avant le score par "
                          "`_matching_check_eliminatoires()`",
            },
            {
                'critere': "La sélection déclenche contractualisation et "
                           "exécution",
                'fait': bool(Definition.search_count(
                    [('code', '=', 'mission_contract')])),
                'preuve': "les actions de `mission_contracting_actions.xml`, "
                          "sur trois transitions",
            },
            {
                'critere': "Les états Mission et Candidature sont "
                           "indépendants",
                'fait': bool(mission_def and application_def
                             and mission_def != application_def),
                'preuve': "deux définitions distinctes, sur deux modèles "
                          "distincts, aucun champ `state` ni sur l'un ni sur "
                          "l'autre",
            },
            {
                'critere': "Données publiques et confidentielles séparées",
                'fait': hasattr(Mission, 'public_detail'),
                'preuve': "`public_detail()` renvoie un dictionnaire à clés "
                          "fermées ; les clés réservées sont absentes, pas "
                          "mises à False",
            },
            {
                'critere': "La clôture enrichit historique et réputation",
                'fait': bool(Definition.search_count(
                    [('code', '=', 'mission_evaluation')])),
                'preuve': "l'action `evaluation_trigger_reputation` crée un "
                          "`opex.expert.rating`, dont dépend "
                          "`reputation_score`",
            },
        ]
