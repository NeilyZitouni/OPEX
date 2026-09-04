import base64

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal

from .uploads import read_upload


class MissionRequestPortal(CustomerPortal):
    """§6 et §7 — le client exprime son besoin, en cinq écrans courts.

    TOUT CE QUI EST DÉFINI ICI EST PRÉFIXÉ

    `_generate_routing_rules()` fusionne **toutes les classes feuilles d'un
    même arbre de controller** en une seule classe dynamique. `CustomerPortal`
    est l'ancêtre commun de `opex_membership`, `opex_innovation`,
    `opex_crowdfunding`, du natif `project` et de celui-ci : à l'exécution,
    ils n'en forment qu'un. Pour un nom donné, il n'existe qu'un exemplaire,
    celui qui gagne la MRO — et rien ne le signale, ni au chargement, ni au
    runtime.

    Relevé avant d'écrire ce fichier, sur les treize classes portail des trois
    modules : `portal_missions` **existe déjà** (`opex_innovation`, route
    `/my/innovation/missions`), tout comme `_own_projects`, `_current_draft`,
    `_save_step`, `_handle_step`, `_step_values`, `_add_document`, `_STEPS` et
    `_STEP_FIELDS`. Aucun de ces noms n'est réutilisé ici.

    Routes    → `/my/missions/*`
    Méthodes  → `portal_intervenants_*`
    Helpers   → `_intervenants_*`
    Constantes→ `_INTERVENANTS_*`

    Seul `_prepare_home_portal_values()` garde son nom : c'est un hook natif
    qu'Odoo appelle lui-même, et il relaie `super()`. **La ligne de partage,
    c'est `super()`** — une surcharge coopérative s'exécute en chaîne, une
    méthode définie indépendamment dans deux modules efface l'autre.


    **Écart au principe du module, assumé et signalé** — le même
    qu'`opex_innovation` : ces écrans sont des gabarits QWeb écrits à la main,
    non les formulaires dynamiques de l'Extension 6 du moteur. Le §7 décrit
    cinq écrans très dessinés, avec leurs textes d'aide et leurs groupes de
    champs propres ; le rendu générique les produirait en moins bien. Le
    formulaire dynamique reste le bon outil pour un questionnaire dont le
    contenu **dépend des réponses**, ce que ces cinq écrans ne sont pas.
    """

    #: Les cinq écrans du §7, dans l'ordre. L'enchaînement vit ici et nulle
    #: part ailleurs : « suivant » et « précédent » s'en déduisent, et ajouter
    #: un écran est une ligne.
    #:
    #: Le récapitulatif n'en fait **pas** partie. Le §7 demande « cinq écrans
    #: courts » puis « Soumettre la demande » : la confirmation est la page de
    #: soumission, pas un sixième écran de saisie. Elle réaffiche le fil avec
    #: les cinq étapes franchies.
    _INTERVENANTS_STEPS = (
        ('general', "Informations générales", '/my/missions/new'),
        ('profil', "Profil recherché", '/my/missions/%s/profil'),
        ('organisation', "Organisation", '/my/missions/%s/organisation'),
        ('budget', "Budget", '/my/missions/%s/budget'),
        ('documents', "Documents", '/my/missions/%s/documents'),
    )

    #: Champs que chaque écran a le droit d'écrire. **Listes fermées** : une clé
    #: absente d'ici ne peut pas être écrite par le portail, quelle que soit la
    #: valeur postée. C'est la même protection que la liste blanche du parcours
    #: d'adhésion du Module 1, et elle vaut aussi pour les champs que le client
    #: ne doit jamais toucher — `sourcing_mode`, `nda_required`,
    #: `date_limite_candidature` : ce sont des décisions du cluster (§9).
    _INTERVENANTS_STEP_FIELDS = {
        'general': ('title', 'description', 'objectifs'),
        'profil': ('certifications_souhaitees',),
        'organisation': ('localisation', 'wilaya'),
        'budget': ('conditions_financieres',),
        'documents': (),
    }

    #: Types de pièces que le §7 étape 5 nomme. Fermé : le client ne choisit
    #: pas librement dans la `Selection` du modèle.
    _INTERVENANTS_DOCUMENT_TYPES = (
        ('cahier_charges', "Cahier des charges"),
        ('complementaire', "Document complémentaire"),
    )

    # Les contrôles de dépôt vivent dans `uploads.py`, en constantes de
    # **module**. Déclarés sur cette classe, ils entraient en collision avec
    # ceux de `MissionApplicationPortal`, feuille du même arbre
    # `CustomerPortal` : mêmes valeurs, donc invisible — et c'est précisément
    # ce qui le rendait dangereux. Voir l'en-tête de `uploads.py`.

    #
    # Résolution du dossier — toujours côté serveur
    #

    def _intervenants_own_missions(self):
        """Les demandes du client connecté, résolues depuis `partner_id`.

        Aucun identifiant reçu du navigateur n'est utilisé directement : il est
        cherché **dans** cet ensemble. Une valeur forgée ne désigne donc rien.

        `sudo()` après avoir borné le domaine au contact : les `ir.rule` de
        l'Extension 1 disent déjà la même chose, mais c'est ce domaine-ci qui
        fait autorité pour décider ce que la page affiche.
        """
        return request.env['opex.mission.request'].sudo().search(
            [('client_id', '=', request.env.user.partner_id.id)],
            order='create_date desc')

    def _intervenants_own_mission(self, mission_id):
        return self._intervenants_own_missions().filtered(
            lambda m: m.id == mission_id)[:1]

    def _intervenants_current_draft(self):
        """La saisie en cours, s'il y en a une.

        Restreinte aux brouillons **jamais soumis**. Un dossier renvoyé par
        le secrétariat est lui aussi à l'étape `draft` — c'est la boucle du
        Schéma 3 — mais ce n'est pas une saisie en cours : reprendre celui-là
        depuis « Créer une demande » ferait disparaître le dossier que le
        contrôleur attend.
        """
        return self._intervenants_own_missions().filtered(
            lambda m: m.workflow_stage_id.code == 'draft'
            and m.is_first_draft())[:1]

    def _intervenants_is_editable(self, mission):
        """Le client a-t-il la main sur ce dossier ?

        Une seule fonction, appelée par les six écrans. Elle pose exactement la
        question de l'`ir.rule` d'écriture de l'Extension 1 — l'étape `draft`,
        et elle seule. Six copies de ce contrôle finiraient par diverger, et
        c'est celle qu'on aurait oubliée qui recevrait la requête forgée.
        """
        return bool(mission) and mission.workflow_stage_id.code == 'draft'

    #
    # Le squelette des écrans
    #

    def _intervenants_step_values(self, mission, step, **extra):
        codes = [code for code, _label, _url in self._INTERVENANTS_STEPS]
        values = self._prepare_portal_layout_values()
        values.update({
            'mission': mission,
            'steps': self._INTERVENANTS_STEPS,
            'step': step,
            # Le récapitulatif n'est pas un écran de saisie : il se place
            # après le dernier, ce qui affiche les cinq pastilles franchies.
            'step_index': codes.index(step) if step in codes else len(codes),
            'page_name': 'intervenants_mission',
        })
        values.update(extra)
        return values

    def _intervenants_save_step(self, mission, step, post):
        """Écriture partielle : seuls les champs de l'écran courant.

        C'est ce qui rend chaque validation indépendante — quitter en cours de
        route ne perd que ce qui n'a pas encore été envoyé.
        """
        values = {
            name: (post.get(name) or '').strip()
            for name in self._INTERVENANTS_STEP_FIELDS.get(step, ())
            if isinstance(post.get(name), str)
        }

        if step == 'general':
            raw = (post.get('mission_type_id') or '').strip()
            if raw.isdigit():
                values['mission_type_id'] = int(raw)

        elif step == 'profil':
            raw = (post.get('domaine_id') or '').strip()
            values['domaine_id'] = int(raw) if raw.isdigit() else False
            values['niveau_experience'] = (
                post.get('niveau_experience') or False)
            annees = (post.get('annees_experience_min') or '').strip()
            values['annees_experience_min'] = (
                int(annees) if annees.isdigit() else 0)
            # `getlist()` et non `post.get()` : un formulaire qui coche
            # plusieurs cases du même nom n'en transmet qu'une seule à
            # `post.get()`, et le client verrait sa sélection réduite au
            # dernier choix sans qu'aucune erreur ne le signale.
            ids = [
                int(value)
                for value in request.httprequest.form.getlist('skill_ids')
                if value.isdigit()
            ]
            values['skill_ids'] = [(6, 0, ids)]

        elif step == 'organisation':
            values['mode_intervention'] = (
                post.get('mode_intervention') or False)
            for name in ('date_debut_souhaitee', 'date_fin_souhaitee'):
                values[name] = (post.get(name) or '').strip() or False

        elif step == 'budget':
            values['type_remuneration'] = post.get('type_remuneration') or False
            values['budget_estimatif'] = self._intervenants_parse_amount(
                post.get('budget_estimatif'))

        if values:
            mission.sudo().write(values)

    @staticmethod
    def _intervenants_parse_amount(raw):
        """Un montant saisi à la main, sans faire tomber la page.

        Virgule décimale, espaces d'affichage, champ vide : trois cas qu'un
        `float()` nu refuserait avec une erreur serveur là où le client attend
        un formulaire.
        """
        cleaned = (raw or '').replace(' ', '').replace(' ', '')
        cleaned = cleaned.replace(',', '.').strip()
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0

    def _intervenants_handle_step(self, mission_id, step, next_url, template,
                                  **post):
        """Corps commun des écrans 2 à 5.

        Un seul endroit qui vérifie l'appartenance du dossier **et** son
        éditabilité. Un écran qui referait ce contrôle à sa façon finirait par
        en oublier une moitié.
        """
        mission = self._intervenants_own_mission(mission_id)
        if not self._intervenants_is_editable(mission):
            return request.redirect('/my/missions')

        if request.httprequest.method == 'POST':
            try:
                self._intervenants_save_step(mission, step, post)
            except UserError as refus:
                return request.render(template, self._intervenants_step_values(
                    mission, step, error=str(refus)))
            return request.redirect(next_url % mission.id)

        return request.render(template, self._intervenants_step_values(
            mission, step, error=None))

    #
    # §6 — Le tableau de bord client
    #

    @http.route(['/my/missions'], type='http', auth='user', website=True)
    def portal_intervenants_missions(self, **kw):
        """Les quatre indicateurs du §6, plus la liste des demandes.

        Les compteurs sont calculés **dans le controller**, jamais dans le
        gabarit. Un `search_count()` posé en QWeb s'exécute sous l'identité du
        visiteur et fait tomber **la page entière** en `AccessError` — pas la
        tuile. Règle transversale 5, payée sur le Module 2.
        """
        Mission = request.env['opex.mission.request']
        partner = request.env.user.partner_id
        missions = self._intervenants_own_missions()
        # La file du §43, ajoutée à l'Extension 11. Bornée aux dossiers du
        # client par le modèle : ce controller ne choisit pas le périmètre, il
        # passe le contact.
        priorites = request.env['opex.mission.dashboard'].sudo().client_space(
            partner)['priorites']
        return request.render('opex_intervenants.portal_my_missions', {
            'missions': missions,
            'priorites': priorites,
            'dashboard': Mission.client_dashboard(partner),
            'draft': self._intervenants_current_draft(),
            # Un dossier renvoyé n'est pas une saisie en cours : il a son
            # propre encart, avec le motif du retour.
            'a_completer': missions.filtered(
                lambda m: m.workflow_stage_id.code == 'draft'
                and not m.is_first_draft()),
            'open_stages': Mission.OPEN_CALL_STAGES,
            'running_stages': Mission.RUNNING_MISSION_STAGES,
            'done_stages': Mission.DONE_MISSION_STAGES,
            'page_name': 'intervenants_mission',
        })

    #
    # Écran 1 — Informations générales
    #

    @http.route(['/my/missions/new'], type='http', auth='user', website=True,
                methods=['GET', 'POST'])
    def portal_intervenants_mission_new(self, **post):
        """Le brouillon automatique commence ici.

        La demande est créée dès la validation du premier écran, à l'étape
        `draft`. Le client n'a donc jamais à « tout finir d'un coup » : ce qui
        est saisi est enregistré, et la reprise est possible.

        `client_id` n'est **pas** transmis. Le `create()` du modèle le
        réécrit côté serveur pour un compte portail, quelle que soit la valeur
        reçue — ne pas afficher un champ ne protège de rien, une requête forgée
        n'a jamais vu le formulaire.
        """
        draft = self._intervenants_current_draft()
        types = request.env['opex.mission.type'].sudo().search(
            [('active', '=', True)])

        if request.httprequest.method == 'POST':
            title = (post.get('title') or '').strip()
            type_id = (post.get('mission_type_id') or '').strip()
            description = (post.get('description') or '').strip()
            objectifs = (post.get('objectifs') or '').strip()

            # Les quatre champs marqués d'une étoile au §7 étape 1. Ils sont
            # aussi `required` sur le modèle : sans ce contrôle, le client
            # recevrait une erreur serveur au lieu d'un message de page.
            if not (title and type_id.isdigit() and description and objectifs):
                return request.render(
                    'opex_intervenants.portal_mission_step_general',
                    self._intervenants_step_values(
                        draft, 'general', mission_types=types, posted=post,
                        error=_("Le titre, le type de mission, la description "
                                "et les objectifs sont obligatoires.")))

            if draft:
                mission = draft
                self._intervenants_save_step(mission, 'general', post)
            else:
                mission = request.env['opex.mission.request'].create({
                    'title': title,
                    'mission_type_id': int(type_id),
                    'description': description,
                    'objectifs': objectifs,
                })
            return request.redirect('/my/missions/%s/profil' % mission.id)

        return request.render(
            'opex_intervenants.portal_mission_step_general',
            self._intervenants_step_values(
                draft, 'general', mission_types=types, posted={}, error=None))

    #
    # Écrans 2 à 5
    #

    @http.route(['/my/missions/<int:mission_id>/profil'], type='http',
                auth='user', website=True, methods=['GET', 'POST'])
    def portal_intervenants_mission_profil(self, mission_id, **post):
        mission = self._intervenants_own_mission(mission_id)
        if not self._intervenants_is_editable(mission):
            return request.redirect('/my/missions')

        if request.httprequest.method == 'POST':
            # Domaine et compétences sont marqués d'une étoile au §7 étape 2,
            # et la condition de soumission les exige. On le dit ici plutôt que
            # de laisser le client le découvrir trois écrans plus loin.
            domaine = (post.get('domaine_id') or '').strip()
            skills = request.httprequest.form.getlist('skill_ids')
            if not (domaine.isdigit() and skills):
                return request.render(
                    'opex_intervenants.portal_mission_step_profil',
                    self._intervenants_step_values(
                        mission, 'profil',
                        domaines=self._intervenants_domaines(),
                        competences=self._intervenants_competences(),
                        error=_("Le domaine et au moins une compétence "
                                "recherchée sont obligatoires.")))
            self._intervenants_save_step(mission, 'profil', post)
            return request.redirect('/my/missions/%s/organisation' % mission.id)

        return request.render(
            'opex_intervenants.portal_mission_step_profil',
            self._intervenants_step_values(
                mission, 'profil',
                domaines=self._intervenants_domaines(),
                competences=self._intervenants_competences(), error=None))

    def _intervenants_domaines(self):
        return request.env['opex.mission.domain'].sudo().search(
            [('active', '=', True)])

    def _intervenants_competences(self):
        """Le référentiel du Module 2, réutilisé — pas un second.

        C'est celui que le Smart Matching comparera aux profils experts. Un
        référentiel propre au Module 3 ne se croiserait avec l'autre que par
        coïncidence de libellé.
        """
        return request.env['opex.innovation.competence'].sudo().search(
            [('active', '=', True)])

    @http.route(['/my/missions/<int:mission_id>/organisation'], type='http',
                auth='user', website=True, methods=['GET', 'POST'])
    def portal_intervenants_mission_organisation(self, mission_id, **post):
        return self._intervenants_handle_step(
            mission_id, 'organisation', '/my/missions/%s/budget',
            'opex_intervenants.portal_mission_step_organisation', **post)

    @http.route(['/my/missions/<int:mission_id>/budget'], type='http',
                auth='user', website=True, methods=['GET', 'POST'])
    def portal_intervenants_mission_budget(self, mission_id, **post):
        return self._intervenants_handle_step(
            mission_id, 'budget', '/my/missions/%s/documents',
            'opex_intervenants.portal_mission_step_budget', **post)

    @http.route(['/my/missions/<int:mission_id>/documents'], type='http',
                auth='user', website=True, methods=['GET', 'POST'])
    def portal_intervenants_mission_documents(self, mission_id, **post):
        mission = self._intervenants_own_mission(mission_id)
        if not self._intervenants_is_editable(mission):
            return request.redirect('/my/missions')

        error = None
        if request.httprequest.method == 'POST':
            action = post.get('action')
            if action == 'add':
                error = self._intervenants_add_document(mission, post)
                if not error:
                    return request.redirect(
                        '/my/missions/%s/documents' % mission.id)
            elif action == 'remove':
                # L'identifiant vient du navigateur : on le cherche **dans**
                # les pièces de ce dossier plutôt que de le parcourir.
                raw = (post.get('document_id') or '')
                mission.document_ids.filtered(
                    lambda d: str(d.id) == raw).sudo().unlink()
                return request.redirect(
                    '/my/missions/%s/documents' % mission.id)
            else:
                return request.redirect('/my/missions/%s/recap' % mission.id)

        return request.render(
            'opex_intervenants.portal_mission_step_documents',
            self._intervenants_step_values(
                mission, 'documents', error=error,
                document_types=self._INTERVENANTS_DOCUMENT_TYPES))

    def _intervenants_add_document(self, mission, post):
        """Dépose une pièce, et rend lisible le refus.

        Trois contrôles : libellé, fichier présent, extension et taille. Ils
        sont ici parce qu'aucun n'existe encore sur le modèle — à écrire là-bas
        le jour où une pièce pourra être déposée autrement que par cet écran.
        C'est un écart, et il est signalé plutôt que tu.
        """
        upload = request.httprequest.files.get('file')
        name = (post.get('name') or '').strip()
        document_type = post.get('document_type') or 'complementaire'

        if document_type not in dict(self._INTERVENANTS_DOCUMENT_TYPES):
            return _("Type de document inconnu.")
        if not name:
            return _("Donnez un libellé à la pièce.")
        if not upload or not upload.filename:
            return _("Choisissez un fichier.")

        content, erreur = read_upload(upload)
        if erreur:
            return erreur

        request.env['opex.mission.document'].sudo().create({
            'mission_id': mission.id,
            'name': name,
            'document_type': document_type,
            'filename': upload.filename,
            'file': base64.b64encode(content),
        })
        return None

    #
    # Récapitulatif et soumission — §7 « Puis : Soumettre la demande »
    #

    @http.route(['/my/missions/<int:mission_id>/recap'], type='http',
                auth='user', website=True, methods=['GET', 'POST'])
    def portal_intervenants_mission_recap(self, mission_id, **post):
        """Vérifier, confirmer, soumettre.

        La soumission passe par `workflow_do_transition()`, donc par l'unique
        contrôle d'accès du moteur et par la condition configurée. Ce
        controller ne décide pas que la demande peut partir : il le demande, et
        rend le refus lisible.

        §8 — **la demande ne devient pas publique ici.** Elle part en
        qualification, et c'est le cluster qui décidera de publier. C'est une
        transition du workflow, pas un booléen que cet écran cocherait.
        """
        mission = self._intervenants_own_mission(mission_id)
        if not self._intervenants_is_editable(mission):
            return request.redirect('/my/missions')

        error = None
        if request.httprequest.method == 'POST':
            if not post.get('confirm'):
                error = _("Cochez la case de confirmation pour soumettre "
                          "votre demande.")
            else:
                transition = mission.workflow_instance_id.sudo()\
                    .available_transitions(user=request.env.user)\
                    .filtered(lambda t: t.code == 'mission_submit')[:1]
                if not transition:
                    error = _("La soumission n'est pas ouverte sur ce dossier.")
                else:
                    try:
                        mission.workflow_do_transition(transition)
                        return request.redirect('/my/missions/%s' % mission.id)
                    except UserError as blocked:
                        error = str(blocked)

        return request.render(
            'opex_intervenants.portal_mission_step_recap',
            self._intervenants_step_values(mission, 'recap', error=error))

    #
    # Suivi d'une demande
    #

    @http.route(['/my/missions/<int:mission_id>'], type='http', auth='user',
                website=True)
    def portal_intervenants_mission_detail(self, mission_id, **kw):
        """L'état du dossier, en libellés utilisateur.

        La progression et la prochaine action viennent du **moteur**
        (`progress_steps()`, `next_action_label()`) : le métier n'écrit pas sa
        propre version de « où en est mon dossier ».
        """
        mission = self._intervenants_own_mission(mission_id)
        if not mission:
            return request.redirect('/my/missions')
        instance = mission.workflow_instance_id.sudo()
        return request.render('opex_intervenants.portal_mission_detail', {
            'mission': mission,
            'steps': instance.progress_steps(),
            'next_action': instance.next_action_label(user=request.env.user),
            'editable': self._intervenants_is_editable(mission),
            'complement': mission.complement_reason(),
            'page_name': 'intervenants_mission',
        })

    #
    # Le contrat de `/my/counters`
    #

    def _prepare_home_portal_values(self, counters):
        """Le compteur de la tuile d'accueil.

        Trois règles, et les trois ont été payées sur les modules
        précédents :

        1. **`super()` en premier.** C'est ce qui fait cohabiter les surcharges
           des quatre modules dans la classe fusionnée. Une méthode qui ne
           relaie pas efface celle des autres, sans erreur.
        2. **`if 'x' in counters`, sans exception.** Une clé renvoyée sans nœud
           DOM correspondant fait lever `portal_home_counters.js`, ce qui rejette
           le `Promise.all` et tue **tout** le JavaScript de l'accueil — pour
           tous les utilisateurs, pas seulement pour la tuile fautive.
        3. **`has_access('read')` plutôt qu'un `search_count()` nu.** Il répond
           au lieu de lever : un compte sans droit de lecture reçoit 0, pas une
           page en 403.

        Le nom du compteur est neuf : relevé fait sur les trois modules, les
        clés existantes sont `membership_file_count`, `subscription_count`,
        `innovation_project_count`, `innovation_opportunity_count`,
        `innovation_mission_count`, `innovation_evaluation_count` et les
        `crowdfunding_*`. Un compteur, une tuile, un domaine.
        """
        values = super()._prepare_home_portal_values(counters)
        if 'intervenants_mission_count' in counters:
            Mission = request.env['opex.mission.request']
            values['intervenants_mission_count'] = (
                Mission.search_count(
                    [('client_id', '=', request.env.user.partner_id.id)])
                if Mission.has_access('read') else 0
            )
        return values
