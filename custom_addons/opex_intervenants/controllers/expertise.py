from odoo import _, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal


class ExpertCapitalPortal(CustomerPortal):
    """§15 et §16 — l'intervenant renseigne et maintient son capital.

    UNE PAGE, PAS UN PARCOURS

    Le dépôt d'une demande de mission est un parcours : cinq écrans, un début,
    une fin, une soumission. Le capital d'un expert n'en est pas un — il
    s'**entretient**. On y revient pour ajouter une certification obtenue le
    mois dernier, corriger un taux de disponibilité, retirer une compétence
    qu'on ne pratique plus.

    D'où une page unique à quatre blocs, chacun avec son formulaire d'ajout et
    ses boutons de retrait. Un assistant en cinq étapes obligerait à traverser
    tout le capital pour changer une date.

    NOMS PRÉFIXÉS — arbre `CustomerPortal`

    Même règle qu'à l'Extension 2, et les noms de celle-ci comptent aussi :
    `_intervenants_own_missions`, `_intervenants_step_values`,
    `_intervenants_save_step`… sont déjà pris par `MissionRequestPortal`, qui
    est une feuille du même arbre. Ceux-ci portent tous `_intervenants_expert`.
    """

    #: Les quatre blocs modifiables. `rating` n'y est pas : les évaluations
    #: viennent de l'Extension 10, aucun écran n'en crée.
    _INTERVENANTS_EXPERT_BLOCKS = {
        'skill': 'opex.expert.skill',
        'experience': 'opex.expert.experience',
        'certification': 'opex.expert.certification',
        'availability': 'opex.expert.availability',
    }

    #: Champs que chaque bloc a le droit d'écrire. **Listes fermées** : une clé
    #: absente d'ici ne peut pas être écrite par le portail, quelle que soit la
    #: valeur postée. `profile_id` n'y figure évidemment pas — il est imposé
    #: côté serveur.
    _INTERVENANTS_EXPERT_FIELDS = {
        'skill': ('competence_id', 'niveau', 'annees'),
        'experience': ('name', 'organisation', 'mission_type_id', 'domaine_id',
                       'seniorite', 'date_debut', 'date_fin', 'duree_jours',
                       'description'),
        'certification': ('name', 'organisme', 'reference', 'date_obtention',
                          'date_expiration'),
        'availability': ('date_debut', 'date_fin', 'taux', 'note'),
    }

    #: Champs à convertir : le formulaire ne renvoie que des chaînes.
    _INTERVENANTS_EXPERT_INTEGERS = (
        'annees', 'duree_jours', 'taux', 'competence_id', 'mission_type_id',
        'domaine_id')
    _INTERVENANTS_EXPERT_DATES = (
        'date_debut', 'date_fin', 'date_obtention', 'date_expiration')

    #
    # Le profil, résolu côté serveur
    #

    def _intervenants_expert_profile(self):
        """Le profil **activé** du contact connecté, sinon rien.

        `partner.expert_profile_id` et non une recherche sur les demandes :
        ce champ n'est renseigné qu'à l'**activation** du profil, par
        `action_activate_profile()` du Module 2. Une demande encore en cours
        d'instruction n'ouvre donc pas ces écrans — c'est la règle 1 du §39,
        « un utilisateur ne peut candidater que s'il possède le statut/profil
        Expert », appliquée en amont plutôt qu'au moment de candidater.

        Aucun identifiant ne vient de l'URL : il n'y a rien à forger.
        """
        return request.env.user.partner_id.sudo().expert_profile_id

    def _intervenants_expert_values(self, profile, **extra):
        values = self._prepare_portal_layout_values()
        values.update({
            'profile': profile,
            'summary': profile.capital_summary(),
            'competences': request.env['opex.innovation.competence'].sudo()
            .search([('active', '=', True)]),
            'mission_types': request.env['opex.mission.type'].sudo()
            .search([('active', '=', True)]),
            'domaines': request.env['opex.mission.domain'].sudo()
            .search([('active', '=', True)]),
            'niveaux': request.env['opex.expert.skill']
            ._fields['niveau'].selection,
            'seniorites': request.env['opex.expert.experience']
            ._fields['seniorite'].selection,
            'page_name': 'intervenants_expertise',
        })
        values.update(extra)
        return values

    def _intervenants_expert_clean(self, block, post):
        """Traduit un formulaire en valeurs ORM, sans faire tomber la page.

        Trois conversions, et chacune a sa raison :

        - les **entiers** arrivent en chaîne ; une valeur vide ou non numérique
          vaut 0 plutôt qu'une erreur serveur ;
        - un **Many2one** vide doit valoir `False` et non `0`, sinon l'ORM
          cherche l'enregistrement d'identifiant 0 ;
        - une **date** vide doit valoir `False` et non `''`.
        """
        values = {}
        for name in self._INTERVENANTS_EXPERT_FIELDS[block]:
            raw = post.get(name)
            if not isinstance(raw, str):
                continue
            raw = raw.strip()
            if name in self._INTERVENANTS_EXPERT_DATES:
                values[name] = raw or False
            elif name in self._INTERVENANTS_EXPERT_INTEGERS:
                if name.endswith('_id'):
                    values[name] = int(raw) if raw.isdigit() else False
                else:
                    values[name] = int(raw) if raw.isdigit() else 0
            else:
                values[name] = raw
        return values

    def _intervenants_expert_lines(self, profile, block):
        """Les lignes d'un bloc, **bornées à ce profil**.

        Un identifiant reçu du navigateur est cherché *dans* cet ensemble et
        jamais parcouru directement : une valeur forgée ne désigne rien.
        """
        model = self._INTERVENANTS_EXPERT_BLOCKS[block]
        return request.env[model].sudo().search(
            [('profile_id', '=', profile.id)])

    #
    # L'écran
    #

    @http.route(['/my/missions/expertise'], type='http', auth='user',
                website=True)
    def portal_intervenants_expertise(self, **kw):
        """Le capital de l'intervenant, en une page.

        Sans profil activé, la page l'explique et renvoie vers la demande de
        profil du Module 2 — plutôt qu'une redirection muette vers `/my` qui
        laisserait le membre sans savoir ce qui lui manque.
        """
        profile = self._intervenants_expert_profile()
        if not profile:
            return request.render(
                'opex_intervenants.portal_expertise_no_profile',
                {'page_name': 'intervenants_expertise'})
        return request.render(
            'opex_intervenants.portal_expertise',
            self._intervenants_expert_values(profile, error=kw.get('error')))

    @http.route(['/my/missions/expertise/<string:block>'], type='http',
                auth='user', website=True, methods=['POST'])
    def portal_intervenants_expertise_edit(self, block, **post):
        """Ajout et retrait d'une ligne, pour les quatre blocs.

        Un seul point d'entrée : quatre routes jumelles auraient fini par
        diverger sur la vérification du profil, et c'est celle qu'on aurait
        oubliée qui aurait reçu la requête forgée.

        `profile_id` est **imposé** ici, jamais lu dans le formulaire. C'est
        le même verrou que `client_id` sur la demande de mission : ne pas
        afficher un champ ne protège de rien.
        """
        if block not in self._INTERVENANTS_EXPERT_BLOCKS:
            return request.redirect('/my/missions/expertise')

        profile = self._intervenants_expert_profile()
        if not profile:
            return request.redirect('/my/missions/expertise')

        model = request.env[self._INTERVENANTS_EXPERT_BLOCKS[block]].sudo()
        action = post.get('action')
        error = None

        if action == 'remove':
            raw = (post.get('line_id') or '')
            self._intervenants_expert_lines(profile, block).filtered(
                lambda line: str(line.id) == raw).unlink()
        elif action == 'add':
            values = self._intervenants_expert_clean(block, post)
            values['profile_id'] = profile.id
            error = self._intervenants_expert_create(model, block, values)

        if error:
            return request.render(
                'opex_intervenants.portal_expertise',
                self._intervenants_expert_values(profile, error=error))
        return request.redirect('/my/missions/expertise')

    def _intervenants_expert_create(self, model, block, values):
        """Crée la ligne, et rend lisible le refus.

        Les contrôles vivent sur les **modèles** — unicité d'une compétence,
        cohérence des dates, taux entre 0 et 100. Un dépôt par le back-office
        ou par une requête forgée passe donc par les mêmes règles ; ce
        controller ne fait que traduire l'erreur en message de page au lieu
        d'une erreur serveur.
        """
        obligatoires = {
            'skill': ('competence_id', "Choisissez une compétence."),
            'experience': ('name', "Donnez un intitulé à l'expérience."),
            'certification': ('name', "Donnez un intitulé à la certification."),
            'availability': ('date_debut', "Indiquez une date de début."),
        }
        champ, message = obligatoires[block]
        if not values.get(champ):
            return _(message)
        if block == 'availability' and not values.get('date_fin'):
            return _("Indiquez une date de fin.")

        # **Savepoint obligatoire, et `flush_recordset()` dedans.**
        #
        # Une contrainte SQL ne se déclenche pas à `create()` mais au `flush`,
        # et elle **empoisonne la transaction** : tout ce qui suit reçoit
        # « current transaction is aborted », y compris le rendu de la page
        # d'erreur — le client reçoit un 500 au lieu du message. Un
        # `try/except` seul n'y change rien.
        #
        # Le savepoint isole l'échec ; `flush_recordset()` force l'INSERT
        # **à l'intérieur**, sans quoi l'erreur surviendrait plus tard, hors
        # de sa portée. `invalidate_all()` après le rollback : celui-ci défait
        # les écritures en base mais pas le cache de l'ORM, qui contiendrait
        # alors des valeurs jamais écrites.
        #
        # C'est exactement ce que fait le moteur dans `_execute_actions()`
        # (`workflow_instance.py:805`), pour la même raison.
        try:
            with request.env.cr.savepoint():
                model.create(values).flush_recordset()
        except (UserError, ValidationError) as refus:
            request.env.invalidate_all()
            return str(refus)
        except Exception:  # noqa: BLE001 — contrainte SQL, message générique
            request.env.invalidate_all()
            return _(
                "Cette ligne n'a pas pu être enregistrée. Vérifiez qu'elle "
                "n'existe pas déjà et que les valeurs sont cohérentes.")
        return None

    #
    # Le contrat de `/my/counters`
    #

    def _prepare_home_portal_values(self, counters):
        """Le compteur de la tuile « mon expertise ».

        Les trois règles de l'Extension 2 s'appliquent à l'identique :
        `super()` en premier, `if 'x' in counters` sans exception, et une clé
        **neuve** — un compteur, une tuile, un domaine.

        Ici le compteur mesure le **capital**, pas les demandes : nombre de
        compétences qualifiées. C'est ce que la tuile annonce et ce que l'écran
        contient — deux tuiles qui compteraient la même chose laisseraient la
        seconde masquée, `querySelector()` ne renvoyant que le premier nœud.
        """
        values = super()._prepare_home_portal_values(counters)
        if 'intervenants_expertise_count' in counters:
            profile = self._intervenants_expert_profile()
            Skill = request.env['opex.expert.skill']
            values['intervenants_expertise_count'] = (
                Skill.search_count([('profile_id', '=', profile.id)])
                if profile and Skill.has_access('read') else 0
            )
        return values
