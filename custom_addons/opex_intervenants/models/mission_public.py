from odoo import _, api, fields, models


class MissionRequestPublic(models.Model):
    """La vue publique de l'appel — §7 et §14 de la spécification Smart Missions.

    CES MÉTHODES RENVOIENT DES DICTIONNAIRES, JAMAIS LE RECORDSET

    « La publication publique utilise une **vue dédiée** de la mission et non
    l'objet interne complet. » (§14)

    Un gabarit qui reçoit `mission` peut lire n'importe lequel de ses cinquante
    champs — budget, coordonnées du client, candidatures reçues, historique du
    workflow — et il suffit d'un `t-out` ajouté un mardi pour publier ce qui ne
    devait pas l'être. Rien dans le code ne l'en empêcherait, et aucun test ne
    le verrait.

    Une liste **fermée** de clés, construite ici, rend cette faute impossible :
    ce qui n'est pas dans le dictionnaire n'existe pas pour la page. C'est le
    motif de `_matching_teaser()` du Module 2, repris pour la même raison.

    Corollaire, et il est dans le CLAUDE.md : ne **jamais** rendre dans le
    HTML une donnée réservée, même masquée en CSS. Un `d-none` n'est pas une
    protection, c'est un aveu — la donnée est dans la source de la page.
    """

    _inherit = 'opex.mission.request'

    #: Étapes où l'appel est visible du public. `selection` en est **exclue** :
    #: `is_published` la couvre — il faut bien que l'appel reste « publié » tant
    #: qu'on choisit — mais un appel dont les candidatures sont closes n'a plus
    #: à figurer au catalogue.
    PUBLIC_STAGES = ('sourcing', 'open')

    #: La seule étape où l'on peut candidater. Publier n'est pas ouvrir : le
    #: §8 distingue le sourcing de la réception des candidatures, et l'E1 en a
    #: fait deux étapes.
    APPLICATION_STAGES = ('open',)

    # ------------------------------------------------------------
    # Ce qui est ouvert, et à qui
    # ------------------------------------------------------------

    def is_open_for_applications(self):
        """Peut-on encore candidater sur cet appel ?

        Deux conditions, et les deux comptent : l'étape **et** la date limite.
        Un appel resté ouvert par oubli après sa date limite ne doit plus
        recevoir de candidature — c'est ce que le candidat comprend en lisant
        « Date limite : 10 septembre ».

        Une seule fonction : la route POST et le `t-if` du bouton posent la
        même question. Deux formulations finiraient par diverger, et c'est
        celle du bouton qui serait la plus permissive.
        """
        self.ensure_one()
        return (
            self.workflow_stage_id.sudo().code in self.APPLICATION_STAGES
            and self.date_limite_is_open
        )

    # ------------------------------------------------------------
    # §7 — Le catalogue
    # ------------------------------------------------------------

    @api.model
    def public_catalogue(self, limit=None):
        """La rubrique « Opportunités / Missions OPEX ».

        `sudo()` assumé : la page est publique, et le visiteur anonyme n'a
        aucun droit sur `opex.mission.request` — il ne doit pas en avoir. Ce
        n'est pas le contrôle d'accès qui protège ici, c'est la **liste fermée
        de clés** : `sudo()` sur un recordset qu'on ne rend jamais.
        """
        missions = self.sudo().search(
            [('workflow_stage_id.code', 'in', self.PUBLIC_STAGES)],
            order='date_limite_candidature asc, id desc',
            limit=limit,
        )
        return [mission.public_card() for mission in missions]

    def public_card(self):
        """La vignette d'un appel dans le catalogue.

        Volontairement plus pauvre que la fiche : une liste n'a pas à porter
        les objectifs ni les documents.
        """
        self.ensure_one()
        mission = self.sudo()
        return {
            'id': mission.id,
            'reference': mission.name,
            'titre': mission.title,
            'type': mission.mission_type_id.name or '',
            'domaine': mission.domaine_id.name or '',
            'competences': mission.skill_ids.mapped('name'),
            'mode': dict(mission._fields['mode_intervention'].selection).get(
                mission.mode_intervention, ''),
            'localisation': mission.localisation or mission.wilaya or '',
            'duree': mission.duree_estimee_jours,
            'date_limite': mission.date_limite_candidature,
            'ouvert': mission.is_open_for_applications(),
        }

    def public_detail(self):
        """La fiche publique — §12 du Module 3, filtrée par le §14 de la
        spécification.

        **Le point de conception de cette extension.**

        Le §12 du document UX liste « Client » et « Budget indicatif » parmi ce
        que la page doit présenter. Le §7 de la spécification dit l'inverse :
        « Le client, le budget ou les documents sensibles peuvent rester masqués
        jusqu'à une étape ultérieure. »

        Les deux se réconcilient par `public_fields_only`, posé sur l'appel dès
        l'Extension 1 : coché — le défaut — le client et le budget ne sortent
        pas ; décoché, l'appel les publie. Ce n'est donc pas un arbitrage entre
        deux documents, c'est un **réglage par appel**, et c'est le cluster qui
        le tient.

        Les clés absentes sont absentes du dictionnaire, pas mises à `False`.
        Un gabarit qui les afficherait recevrait une `KeyError` au premier
        rendu — une erreur bruyante vaut mieux qu'une fuite silencieuse.
        """
        self.ensure_one()
        mission = self.sudo()
        detail = {
            'id': mission.id,
            'reference': mission.name,
            'titre': mission.title,
            'type': mission.mission_type_id.name or '',
            'domaine': mission.domaine_id.name or '',
            'description': mission.description or '',
            'objectifs': mission.objectifs or '',
            'resultats': mission.resultats_attendus or '',
            'competences': mission.skill_ids.mapped('name'),
            'niveau': dict(
                mission._fields['niveau_experience'].selection).get(
                mission.niveau_experience, ''),
            'annees_min': mission.annees_experience_min,
            'certifications': mission.certifications_souhaitees or '',
            'langues': mission.langues or '',
            'mode': dict(mission._fields['mode_intervention'].selection).get(
                mission.mode_intervention, ''),
            'localisation': mission.localisation or '',
            'wilaya': mission.wilaya or '',
            'date_debut': mission.date_debut_souhaitee,
            'date_fin': mission.date_fin_souhaitee,
            'duree': mission.duree_estimee_jours,
            'date_limite': mission.date_limite_candidature,
            'ouvert': mission.is_open_for_applications(),
            'nda_requis': mission.nda_required,
            'documents': mission._public_documents(),
            # Ce que la page doit dire au visiteur **à la place** de ce qui est
            # masqué. Le silence laisserait croire à un oubli.
            'restreint': mission.public_fields_only,
        }

        if not mission.public_fields_only:
            detail['client'] = mission.client_id.display_name
            detail['budget'] = mission.budget_estimatif
            detail['devise'] = mission.currency_id.symbol or ''
            detail['remuneration'] = dict(
                mission._fields['type_remuneration'].selection).get(
                mission.type_remuneration, '')
        return detail

    def _public_documents(self):
        """Les pièces publiables, et elles seules.

        « Les documents sensibles peuvent rester masqués » : le cahier des
        charges d'un appel ouvert est public, une annexe technique ne l'est pas
        forcément. C'est `is_public`, coché pièce par pièce à l'Extension 1.

        On ne renvoie **pas** le contenu du fichier : un identifiant et un
        libellé. Le téléchargement passe par une route qui refait le contrôle.
        """
        self.ensure_one()
        labels = dict(
            self.env['opex.mission.document']._fields['document_type'].selection)
        return [
            {
                'id': document.id,
                'nom': document.name,
                'type': labels.get(document.document_type, ''),
                'fichier': document.filename or document.name,
            }
            for document in self.sudo().document_ids.filtered('is_public')
        ]

    def public_document(self, document_id):
        """Une pièce publiable de **cet** appel, ou rien.

        L'identifiant vient du navigateur : il est cherché **dans** les pièces
        publiables de cet appel, jamais parcouru directement. Une valeur forgée
        ne désigne rien — y compris une pièce non publique du même appel.
        """
        self.ensure_one()
        return self.sudo().document_ids.filtered(
            lambda d: d.id == document_id and d.is_public)[:1]
