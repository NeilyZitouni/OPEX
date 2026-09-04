import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MatchingCriteria(models.Model):
    """Le critère du moteur, rendu **pondérable par type de mission et par appel**.

    ON N'ÉCRIT PAS UN SECOND MOTEUR

    Le calcul reste **entièrement** celui d'`opex_workflow` :
    `_score_candidate()` pour le score et son explication, `_compare()` pour la
    comparaison, `opex.matching.candidate` pour le résultat. Pas une ligne de
    scoring n'est écrite ici ni ailleurs dans ce module.

    Trois champs sont ajoutés par `_inherit`, et ils ne changent le
    comportement d'aucun autre module : ils sont vides sur les critères
    d'`opex_innovation`, dont la résolution passe par `run_matching()` et ne les
    lit jamais.

    Pourquoi la résolution ne peut pas passer par `run_matching()`

    `opex.workflow.instance.run_matching()` résout ses critères ainsi
    (`workflow_instance.py:1116`) :

        search([('definition_id', '=', ...), ('active', '=', True)])

    C'est-à-dire **tous** les critères de la définition, sans distinction. Or le
    §11 exige : « Les pondérations sont configurables par type de mission ou par
    appel. » Deux jeux de pondérations coexistant sous la même définition
    seraient donc additionnés — un appel de formation serait noté avec les
    critères d'audit **et** les siens.

    Trois issues possibles, une seule acceptable :

    1. modifier `run_matching()` pour qu'il accepte un recordset de critères →
       **exclu**, cela touche le moteur ;
    2. réécrire un scoring dans ce module → **exclu**, c'est ce que
       l'extension interdit ;
    3. résoudre les critères ici, puis appeler `instance._score_candidate()`
       avec le recordset choisi → **retenu**. Le scoring et l'explication
       restent au moteur ; ce module ne fait que lui dire **quoi** comparer,
       ce qui est exactement le rôle d'une configuration.

    C'est l'option 3. `run_smart_matching()` ci-dessous orchestre ; il ne
    calcule rien.
    """

    _inherit = 'opex.matching.criteria'

    #: Deux critères qui mesurent la même chose portent la même famille, quel
    #: que soit leur poids. C'est par elle que le profil d'un type de mission
    #: remplace le critère par défaut — le `code`, lui, doit rester unique par
    #: définition (contrainte du moteur), donc il est suffixé.
    family = fields.Char(
        string="Famille de critère",
        index=True,
        help="Identifie ce que le critère mesure — competences, experience, "
             "secteur… Le critère d'un type de mission remplace celui par "
             "défaut de la même famille.",
    )
    mission_type_id = fields.Many2one(
        'opex.mission.type',
        string="Type de mission",
        ondelete='cascade',
        index=True,
        help="Laissé vide, le critère s'applique par défaut à tous les appels. "
             "Renseigné, il remplace le critère par défaut de sa famille pour "
             "ce type de mission.",
    )
    mission_id = fields.Many2one(
        'opex.mission.request',
        string="Appel à mission",
        ondelete='cascade',
        index=True,
        help="Pondération propre à un appel précis, qui l'emporte sur celle du "
             "type. Créée par le bouton « Personnaliser les critères ».",
    )

    # Le champ qui porte le critère d'acceptation du §21.
    #
    # « Les critères éliminatoires sont distingués du scoring pondéré. »
    # Un critère éliminatoire n'entre **pas** dans la somme des poids : il est
    # évalué avant, et un candidat qui le rate est écarté du vivier — pas noté
    # zéro sur cette ligne.
    is_eliminatoire = fields.Boolean(
        string="Critère éliminatoire",
        help="Évalué AVANT le score pondéré. Un candidat qui ne le remplit pas "
             "est écarté, il n'est pas mal noté — et n'apparaît donc pas dans "
             "la liste des propositions.",
    )

    _sql_constraints_note = """
    Le moteur impose déjà unique(definition_id, code) : c'est pourquoi les
    critères d'un type ou d'un appel portent un code suffixé.
    """


class MissionRequestMatching(models.Model):
    """Le Smart Matching de l'appel à mission — §6 et §11.

    Ce modèle n'ajoute **aucun** calcul de score. Il résout les critères
    applicables, écarte les candidats qui ratent un critère éliminatoire, puis
    demande au moteur de noter les autres.
    """

    _inherit = 'opex.mission.request'

    # ------------------------------------------------------------
    # Les critères propres à cet appel
    # ------------------------------------------------------------

    matching_criteria_ids = fields.One2many(
        'opex.matching.criteria', 'mission_id',
        string="Critères personnalisés",
        help="Vides, l'appel utilise le profil de son type de mission, ou le "
             "profil par défaut du §11.")
    matching_is_customised = fields.Boolean(
        string="Pondérations personnalisées",
        compute='_compute_matching_counts')

    # ------------------------------------------------------------
    # Le résultat du dernier matching
    # ------------------------------------------------------------

    # `Many2many` calculé et non `One2many` : `opex.matching.candidate` porte
    # une clé vers l'**instance de workflow**, pas vers la mission. Un
    # `One2many` exigerait une colonne inverse qui n'existe pas, et la créer
    # dupliquerait un lien que le moteur possède déjà.
    matching_candidate_ids = fields.Many2many(
        'opex.matching.candidate',
        string="Candidats proposés",
        compute='_compute_matching_candidates')
    matching_candidate_count = fields.Integer(
        string="Nombre de candidats proposés",
        compute='_compute_matching_counts')

    matching_date = fields.Datetime(
        string="Dernier matching", readonly=True, copy=False)
    matching_excluded_count = fields.Integer(
        string="Candidats écartés", readonly=True, copy=False)
    #: L'autre moitié de l'explicabilité.
    #:
    #: Un responsable qui ne voit pas un expert qu'il attendait doit pouvoir
    #: savoir **pourquoi**. Sans cette note, un critère éliminatoire mal réglé
    #: est indétectable : la liste est simplement plus courte, et rien ne le dit.
    matching_excluded_note = fields.Text(
        string="Écartés par un critère éliminatoire",
        readonly=True, copy=False)

    @api.depends('workflow_instance_id')
    def _compute_matching_candidates(self):
        for mission in self:
            instance = mission.workflow_instance_id.sudo()
            mission.matching_candidate_ids = self.env[
                'opex.matching.candidate'].sudo().search(
                [('instance_id', '=', instance.id)]) if instance else False

    @api.depends('matching_candidate_ids', 'matching_criteria_ids')
    def _compute_matching_counts(self):
        for mission in self:
            mission.matching_candidate_count = len(
                mission.matching_candidate_ids)
            mission.matching_is_customised = bool(mission.matching_criteria_ids)

    # ------------------------------------------------------------
    # La résolution des pondérations — §11
    # ------------------------------------------------------------

    def matching_criteria(self):
        """Les critères applicables à **cet** appel, pondérations comprises.

        Trois niveaux, du plus général au plus précis, chacun remplaçant le
        précédent **par famille** :

            profil par défaut  →  profil du type de mission  →  profil de l'appel

        C'est la lecture littérale du §11 : « configurables par type de mission
        **ou par appel** ». Un appel qui ne personnalise rien hérite de son
        type ; un type qui ne personnalise rien hérite du défaut.

        Renvoie un **recordset** de `opex.matching.criteria`, que
        `_score_candidate()` sait consommer tel quel.
        """
        self.ensure_one()
        Criteria = self.env['opex.matching.criteria'].sudo()
        definition = self.workflow_definition_id
        if not definition:
            return Criteria.browse()

        applicables = Criteria.search([
            ('definition_id', '=', definition.id),
            ('active', '=', True),
            '|', '|',
            ('mission_id', '=', self.id),
            ('mission_type_id', '=', self.mission_type_id.id),
            '&', ('mission_id', '=', False), ('mission_type_id', '=', False),
        ])

        # Trois passes, dans l'ordre de priorité croissante. La dernière
        # écriture gagne — c'est ce qui fait qu'un critère d'appel remplace
        # celui de son type, qui remplace celui par défaut.
        par_famille = {}
        for niveau in (
            lambda c: not c.mission_id and not c.mission_type_id,
            lambda c: c.mission_type_id and not c.mission_id,
            lambda c: c.mission_id,
        ):
            for criterion in applicables.filtered(niveau):
                par_famille[criterion.family or criterion.code] = criterion

        retenus = Criteria.browse()
        for criterion in par_famille.values():
            retenus |= criterion
        return retenus.sorted('sequence')

    def action_customise_matching_criteria(self):
        """Recopie le profil applicable sur cet appel, pour l'ajuster.

        Une **copie de vrais enregistrements**, et non une table de
        surcharges. C'est ce qui permet à `_score_candidate()` de lire
        `criterion.weight` comme d'habitude : le moteur ne sait rien de nos
        trois niveaux, et n'a pas à le savoir.

        Le `code` est suffixé de la référence de l'appel : le moteur impose
        `unique(definition_id, code)`.
        """
        self.ensure_one()
        if self.matching_criteria_ids:
            raise UserError(_(
                "Les critères de cet appel sont déjà personnalisés. Modifiez-les "
                "ou supprimez-les pour revenir au profil de son type de mission."))

        applicables = self.matching_criteria()
        if not applicables:
            raise UserError(_(
                "Aucun critère de matching n'est configuré pour ce type de "
                "mission."))

        for criterion in applicables:
            criterion.sudo().copy({
                'code': "%s_%s" % (criterion.family or criterion.code,
                                   self.name.lower().replace('-', '_')),
                'mission_id': self.id,
                'mission_type_id': False,
            })
        self.invalidate_recordset(['matching_criteria_ids'])
        return True

    # ------------------------------------------------------------
    # Le vivier
    # ------------------------------------------------------------

    def _matching_vivier(self):
        """Les contacts que le matching examinera.

        **Le premier filtre éliminatoire, et le moins coûteux.** Le §11 dit
        « les critères éliminatoires sont évalués avant le score pondéré » : le
        vivier en est la forme la plus grossière — on ne note pas quelqu'un qui
        n'est pas un intervenant.

        C'est aussi ce que porte `action.matching_domain` du moteur
        (`workflow_action.py:127`) pour les matchings déclenchés par une
        transition. Ici la restriction est la même, exprimée en Python parce
        que la seconde moitié — les critères éliminatoires **propres à cet
        appel** — ne peut pas s'écrire dans un domaine statique : elle dépend
        de la mission.

        Les intervenants ayant déjà une candidature sur cet appel sont exclus :
        ils sont déjà dans le pool, les reproposer serait du bruit.
        """
        self.ensure_one()
        Partner = self.env['res.partner'].sudo()
        vivier = Partner.search([
            ('is_expert', '=', True),
            ('expert_profile_id', '!=', False),
            ('active', '=', True),
        ])
        deja_candidats = self.sudo().application_ids.partner_id
        return vivier - deja_candidats

    # ------------------------------------------------------------
    # LES CRITÈRES ÉLIMINATOIRES — AVANT LE SCORE
    # ------------------------------------------------------------

    def _matching_check_eliminatoires(self, instance, partner, criteria):
        """Ce candidat passe-t-il les critères obligatoires ?

        Renvoie `(admis, motifs)`. Les motifs servent à expliquer une absence :
        un responsable qui ne voit pas un expert attendu doit pouvoir savoir
        pourquoi.

        La comparaison est **celle du moteur** — `criterion._compare()`,
        exactement la même que pour les critères pondérés. Seule la conséquence
        diffère : ici on écarte, là on note. C'est précisément la distinction
        que demande le §21, « les critères éliminatoires sont distingués du
        scoring pondéré ».

        Un critère illisible **n'écarte pas** : une faute de frappe dans une
        expression ne doit pas vider le vivier en silence. Elle est signalée
        dans les motifs et le candidat passe — c'est la même asymétrie
        prudente que `_evaluate_flag()` du moteur.

        Deux listes et non une, et ce détail a coûté trois tests. Les motifs
        qui écartent et ceux qui ne font qu'avertir se distinguaient autrefois
        par un pictogramme en tête de chaîne, testé au `startswith()`. Un
        nettoyage typographique a retiré le pictogramme des deux côtés : la
        comparaison est devenue `startswith("")`, vraie pour tout le monde, et
        plus aucun candidat n'était écarté. Le vivier restait plein, ce qui ne
        ressemble pas à une panne.

        Aucun caractère décoratif ne porte donc plus de décision ici : ce sont
        deux listes distinctes, et celle où atterrit le motif dit la
        conséquence.
        """
        self.ensure_one()
        avertissements = []
        bloquants = []
        for criterion in criteria:
            try:
                source = instance._evaluate_expression(
                    criterion.source_expression)
            except Exception:  # noqa: BLE001 — critère neutralisé, pas bloquant
                avertissements.append(_(
                    "%s — critère illisible, non appliqué"
                ) % criterion.name)
                continue

            # **Un critère obligatoire que l'appel n'exprime pas ne
            # s'applique pas.**
            #
            # Le §6 dit « obligatoires ou préférentiels **selon la mission** ».
            # Sans ce garde-fou, un appel d'audit qui ne demande aucune
            # certification écarterait la totalité du vivier : `_compare()`
            # renvoie « aucune attente exprimée sur le dossier », donc faux,
            # donc éliminé. La liste serait vide et rien n'expliquerait
            # pourquoi.
            #
            # Pour un critère **pondéré**, la même situation est bénigne : tout
            # le monde perd les mêmes points, le classement ne bouge pas. Pour
            # un éliminatoire, elle vide le vivier. D'où le traitement à part.
            if not criterion._as_set(source):
                continue

            # Un `target_field` absent du modèle **bloque**, il ne se
            # neutralise pas. C'est le pendant du contrôle de configuration :
            # laisser passer le candidat sur un champ qui n'existe pas
            # reviendrait à supprimer le critère en silence, et c'est le
            # défaut que D1 documente.
            if criterion.target_field not in partner._fields:
                bloquants.append(_(
                    "%s — le champ candidat « %s » n'existe pas ; critère non "
                    "vérifiable, candidat écarté par prudence"
                ) % (criterion.name, criterion.target_field))
                continue

            target = partner.sudo()[criterion.target_field]

            # La conjonction du §D1 : chaque valeur attendue est exigée.
            #
            # `_compare()` du moteur teste un recoupement en mode `intersect`.
            # C'est juste pour un critère pondéré et faux pour un
            # éliminatoire : « exiger ISO 27001 et ISO 9001 » doit vouloir
            # dire les deux, sinon on n'en exige au plus qu'une - c'est la
            # troisième défaillance mesurée de D1.
            #
            # La comparaison reste **celle du moteur**, appelée une fois par
            # valeur attendue. Ce module ne réécrit ni `_compare` ni `_as_set`,
            # et un test lit le source pour s'en assurer.
            if criterion.is_conjonctif:
                manquantes = []
                for attendue in self._matching_expected_items(source):
                    ok, _detail = criterion._compare(attendue, target)
                    if not ok:
                        manquantes.append(attendue.display_name
                                          if hasattr(attendue, 'display_name')
                                          else str(attendue))
                if manquantes:
                    bloquants.append(_(
                        "%s — il manque : %s"
                    ) % (criterion.name, ", ".join(sorted(manquantes))))
                continue

            ok, detail = criterion._compare(source, target)
            if not ok:
                bloquants.append("%s — %s" % (criterion.name, detail))
        return not bloquants, avertissements + bloquants

    @staticmethod
    def _matching_expected_items(source):
        """Les valeurs attendues, une par une.

        Un recordset se parcourt enregistrement par enregistrement ; une liste
        élément par élément ; tout le reste vaut une seule valeur. C'est ce
        découpage qui donne son sens à la conjonction — sans lui, un recordset
        de deux certifications serait comparé d'un bloc et le recoupement
        partiel suffirait.
        """
        if isinstance(source, models.BaseModel):
            return list(source)
        if isinstance(source, (list, tuple, set)):
            return list(source)
        return [source]


    # ------------------------------------------------------------
    # Le contrôle de configuration — la seconde moitié de D1
    # ------------------------------------------------------------
    #
    # LE DÉFAUT QUE CE CONTRÔLE EXISTE POUR EMPÊCHER
    #
    # `field('nom_mal_orthographie')` **ne lève pas**. Le helper du moteur est
    # tolérant par conception (`workflow_instance.py:251`) : il rend `False`
    # pour qu'une même règle serve sur deux modèles dont l'un seulement porte
    # le champ. C'est juste pour une condition de transition.
    #
    # Sur un critère éliminatoire, c'est un piège. Le `False` traverse
    # `_as_set()`, qui rend un ensemble vide, et l'élimination conclut « cet
    # appel n'exprime aucune attente » — donc n'écarte personne. Une faute de
    # frappe dans la configuration **supprime le critère**, sans erreur, sans
    # avertissement, et le vivier reste plein. Plus plein, même.
    #
    # C'est exactement le motif du balayage typographique qui avait fait
    # cesser d'écarter (règle 21) : le symptôme ne ressemble pas à une panne.
    #
    # D'où ce contrôle, joué **avant** le matching : les champs nommés par les
    # critères éliminatoires doivent exister. S'ils n'existent pas, on refuse
    # de lancer plutôt que de rendre une liste qui contient des gens qui
    # auraient dû en être écartés. Une liste fausse est pire qu'une absence de
    # liste : personne ne la relit.

    #: Les noms de champs cités par une expression, sous la forme
    #: `field('x')` ou `field("x", defaut)`.
    _FIELD_CALL = re.compile(r"""field\(\s*['"]([a-zA-Z_][a-zA-Z0-9_]*)['"]""")

    def _matching_configuration_errors(self, criteria):
        """Les critères éliminatoires que la configuration rend inopérants.

        Rend une liste de phrases, vide quand tout va bien. Ne porte que sur
        les **éliminatoires** : un critère pondéré mal configuré fait perdre
        les mêmes points à tout le monde, le classement ne bouge pas, et
        bloquer le matching pour cela serait disproportionné.
        """
        self.ensure_one()
        erreurs = []
        for criterion in criteria.filtered('is_eliminatoire'):
            for nom in self._FIELD_CALL.findall(
                    criterion.source_expression or ''):
                if nom not in self._fields:
                    erreurs.append(_(
                        "« %(critere)s » interroge le champ « %(champ)s », qui "
                        "n'existe pas sur un appel à mission. Le critère "
                        "n'écarterait personne."
                    ) % {'critere': criterion.name, 'champ': nom})

            cible = criterion.target_field
            if cible and cible not in self.env['res.partner']._fields:
                erreurs.append(_(
                    "« %(critere)s » compare au champ candidat « %(champ)s », "
                    "qui n'existe pas sur un contact. Le critère écarterait "
                    "tout le monde."
                ) % {'critere': criterion.name, 'champ': cible})

            if not (criterion.source_expression or '').strip():
                erreurs.append(_(
                    "« %s » est éliminatoire et n'exprime aucune attente : il "
                    "n'écarterait personne."
                ) % criterion.name)
        return erreurs

    # ------------------------------------------------------------
    # Le lancement
    # ------------------------------------------------------------

    def run_smart_matching(self, limit=20, min_score=0.0):
        """Propose des intervenants scorés sur cet appel.

        **Ne déclenche aucune transition et n'écrit rien sur l'appel** en
        dehors du compte rendu du dernier passage. « L'IA recommande, l'humain
        décide » : cette méthode produit une liste, le responsable arbitre, et
        c'est lui qui fait avancer le dossier s'il le juge bon.

        Ordre imposé par le §11, et il n'est pas négociable :

            1. vivier          — qui est seulement candidat possible
            2. **éliminatoires** — qui remplit les critères obligatoires
            3. score pondéré   — comment se classent ceux qui restent

        Les candidats déjà arbitrés par un humain ne sont pas recalculés :
        relancer le matching ne doit pas effacer une décision. C'est la règle du
        moteur (`run_matching`, `workflow_instance.py:1130`), reprise ici parce
        que c'est la seule partie de son orchestration qu'on rejoue.
        """
        self.ensure_one()
        instance = self.workflow_instance_id.sudo()
        if not instance:
            raise UserError(_(
                "Cet appel n'est engagé dans aucun workflow : le matching n'a "
                "pas de dossier auquel rattacher ses propositions."))

        criteria = self.matching_criteria()
        if not criteria:
            raise UserError(_(
                "Aucun critère de matching n'est configuré. Vérifiez le profil "
                "de pondération du type de mission « %s »."
            ) % (self.mission_type_id.name or ''))

        # Avant tout : une configuration qui rend un éliminatoire inopérant
        # doit arrêter le matching, pas le laisser produire une liste fausse.
        erreurs = self._matching_configuration_errors(criteria)
        if erreurs:
            raise UserError(_(
                "La configuration des critères éliminatoires est inopérante. "
                "Le matching n'est pas lancé : une liste qui contient des "
                "candidats qui auraient dû être écartés est pire qu'une "
                "absence de liste.%s"
            ) % "".join("\n\n· %s" % erreur for erreur in erreurs))

        eliminatoires = criteria.filtered('is_eliminatoire')
        ponderes = criteria - eliminatoires
        if not ponderes:
            raise UserError(_(
                "Tous les critères configurés sont éliminatoires : il n'en "
                "reste aucun pour établir un classement."))

        Candidate = self.env['opex.matching.candidate'].sudo()
        deja_decides = Candidate.search([
            ('instance_id', '=', instance.id),
            ('candidate_type', '=', 'expert'),
            ('state', '!=', 'proposed'),
        ])
        intouchables = set(deja_decides.partner_id.ids)

        # Les propositions non arbitrées sont remplacées : l'appel a pu évoluer
        # depuis, et laisser d'anciens scores à côté des nouveaux rendrait la
        # liste illisible.
        Candidate.search([
            ('instance_id', '=', instance.id),
            ('candidate_type', '=', 'expert'),
            ('state', '=', 'proposed'),
        ]).unlink()

        scores, ecartes = [], []
        for partner in self._matching_vivier():
            if partner.id in intouchables:
                continue

            admis, motifs = self._matching_check_eliminatoires(
                instance, partner, eliminatoires)
            if not admis:
                ecartes.append("· %s — %s" % (
                    partner.display_name, " ; ".join(motifs)))
                continue

            # Le scoring est **celui du moteur**, appelé tel quel. Ce module
            # ne calcule pas de score et n'écrit pas d'explication : il reçoit
            # les deux.
            score, detail = instance._score_candidate(partner, ponderes)
            if motifs:
                # Un critère éliminatoire illisible a été signalé : l'info
                # remonte dans l'explication plutôt que de disparaître.
                detail = "\n".join(motifs) + "\n\n" + detail
            if score >= min_score:
                scores.append((score, detail, partner))

        scores.sort(key=lambda item: item[0], reverse=True)
        proposes = Candidate.browse()
        for score, detail, partner in scores[:limit]:
            proposes |= Candidate.create({
                'instance_id': instance.id,
                'partner_id': partner.id,
                'candidate_type': 'expert',
                'score': score,
                'detail': self._matching_header(criteria, eliminatoires)
                + "\n" + detail,
            })

        self.sudo().write({
            'matching_date': fields.Datetime.now(),
            'matching_excluded_count': len(ecartes),
            'matching_excluded_note': "\n".join(ecartes) or False,
        })
        self.invalidate_recordset(['matching_candidate_ids'])
        return proposes

    @staticmethod
    def _matching_header(criteria, eliminatoires):
        """L'en-tête de l'explication : sur quoi ce candidat a été jugé.

        Un score de 87 % ne se défend pas sans dire de quoi il est fait. Cette
        ligne dit d'abord **quels critères** ont servi et lesquels étaient
        obligatoires — l'explication du moteur dit ensuite ce que le candidat en
        a rempli.
        """
        ponderes = criteria - eliminatoires
        total = sum(ponderes.mapped('weight')) or 1
        lignes = [
            "Critères appliqués : %s pondérés (%s), %s éliminatoire(s)." % (
                len(ponderes),
                ", ".join("%s %.0f %%" % (c.name, c.weight / total * 100)
                          for c in ponderes.sorted('sequence')),
                len(eliminatoires),
            ),
        ]
        if eliminatoires:
            lignes.append("Obligatoires remplis : %s." % ", ".join(
                eliminatoires.mapped('name')))
        return "\n".join(lignes)

    def action_run_smart_matching(self):
        """Bouton back-office. Ouvre la liste des propositions."""
        self.ensure_one()
        self.run_smart_matching()
        return self.action_view_matching_candidates()

    def action_view_matching_candidates(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Intervenants proposés — %s") % self.display_name,
            'res_model': 'opex.matching.candidate',
            'view_mode': 'list,form',
            'domain': [('instance_id', '=', self.workflow_instance_id.id)],
        }


class MatchingCandidate(models.Model):
    """Le candidat proposé, avec ce qu'il faut pour décider — §6.

    Aucune méthode de décision n'est ajoutée : le moteur en fournit quatre
    (`action_accept`, `action_reject`, `action_exclude`, `action_reset`) et
    elles suffisent. Ce qui manque, c'est le **lien vers la mission** — le
    moteur ne connaît que l'instance.
    """

    _inherit = 'opex.matching.candidate'

    mission_id = fields.Many2one(
        'opex.mission.request',
        string="Appel à mission",
        compute='_compute_mission_id',
        help="L'appel dont dépend l'instance. Calculé : le moteur range ses "
             "candidats par instance, il ne connaît pas nos modèles métier.",
    )

    @api.depends('instance_id')
    def _compute_mission_id(self):
        Mission = self.env['opex.mission.request'].sudo()
        for candidate in self:
            instance = candidate.instance_id.sudo()
            candidate.mission_id = (
                Mission.browse(instance.res_id).exists()
                if instance.res_model == 'opex.mission.request' else False
            )

    def action_invite_to_mission(self):
        """« Inviter » — la première des cinq actions du §6.

        Crée la candidature à l'étape `invited`, avec `source = 'matching'`, et
        marque la proposition comme retenue.

        **C'est un geste humain, jamais un effet du score.** Rien dans ce
        module ne déclenche cette méthode automatiquement : le responsable
        clique. « L'IA recommande. Elle ne doit pas automatiquement décider
        seule. »

        Et cela ne fait **pas** avancer l'appel. La candidature naît sur sa
        propre machine à états ; la mission reste où elle est. C'est
        l'indépendance des deux workflows, vérifiée depuis l'Extension 1.
        """
        Application = self.env['opex.mission.application'].sudo()
        for candidate in self:
            mission = candidate.mission_id
            if not mission:
                raise UserError(_(
                    "Cette proposition n'est rattachée à aucun appel à mission."))
            existante = Application.search([
                ('mission_id', '=', mission.id),
                ('partner_id', '=', candidate.partner_id.id),
            ], limit=1)
            if not existante:
                Application.create({
                    'mission_id': mission.id,
                    'partner_id': candidate.partner_id.id,
                    'source': 'matching',
                    'matching_candidate_id': candidate.id,
                    # Le score et son explication sont recopiés **au moment de
                    # l'invitation** : un recalcul ultérieur du matching ne doit
                    # pas réécrire ce sur quoi la décision a été prise.
                    'score': candidate.score,
                    'score_detail': candidate.detail,
                })
            candidate._decide('accepted')
        return True
