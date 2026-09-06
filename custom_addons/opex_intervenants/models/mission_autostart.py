"""Le démarrage automatique d'une mission à sa date de début contractuelle.

POURQUOI CE FICHIER EST SÉPARÉ DE `mission_operational.py`

Ce n'est pas un rangement : `test_contracting.py` lit **chaque méthode des
classes de `mission_operational`**, docstrings retirées, et échoue si l'une
contient `do_transition`. La règle qu'il garde est celle qui gouverne le
module — « le Python implémente les effets ; il ne décide jamais d'une
transition ».

Ce cron, lui, franchit bel et bien une transition. L'y écrire aurait fait
rougir ce test, et la correction de moindre effort aurait été d'assouplir le
test — c'est-à-dire de perdre la garde pour faire passer l'exception. Le
fichier est donc distinct, et la ligne de partage est écrite ici plutôt que
découverte en soutenance.

LA LIGNE DE PARTAGE, ET C'EST UNE DÉCISION À DÉFENDRE

La règle interdit à un **déclencheur métier** de chaîner une transition :
réagir à `atr_select` en franchissant `mtr_start_contracting` rendrait la
configuration décorative, et l'humain ne déciderait plus rien.

L'horloge n'est pas un déclencheur métier. « La mission commence le jour
convenu » est une clause du contrat que les deux parties ont confirmée, pas
un jugement que quelqu'un porte le matin même. Le graphe n'a aucune façon
d'exprimer le passage du temps : `safe_eval` n'expose ni `datetime` ni
`time` (c'est déjà la raison d'être de `date_limite_is_open`, Extension 1).

⚠ Ce cron est **le premier du projet à franchir une transition**.
`_cron_check_sla` du moteur ne fait que marquer et notifier ; les deux
autres crons ne touchent à aucun workflow. C'est donc un précédent, et il
est posé sciemment.

CE QU'IL NE FAIT PAS, ET C'EST L'ESSENTIEL

Il ne décide rien. Il **demande** au moteur, exactement comme un écran :
la transition est cherchée dans `available_transitions(user)`, donc après
`_check_transition_allowed()`, et `do_transition()` rejuge ensuite les
conditions. La règle 5 du §39 — contrat validé — n'est pas réécrite ici ;
si elle n'est pas satisfaite, le cron passe son chemin.

Autrement dit : ce cron ne peut rien faire qu'un responsable n'aurait pu
faire en cliquant. Il choisit **le moment**, pas le droit.
"""
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

#: L'étape d'où part le démarrage, et le code de la transition. Nommés une
#: fois : deux littéraux dispersés divergeraient au premier renommage, et
#: c'est le cron qui cesserait de trouver quoi que ce soit — en silence.
CONTRACTING_STAGE = 'contracting'
START_TRANSITION = 'mission_start'


class MissionAutoStart(models.Model):
    """Le démarrage à échéance, sur `opex.mission.request`."""

    _inherit = 'opex.mission.request'

    @api.model
    def _cron_start_due_missions(self):
        """Démarre les missions dont la date de début contractuelle est atteinte.

        Idempotent **par construction**, et non par un drapeau : une mission
        franchie quitte l'étape `contracting`, donc sort du domaine et ne sera
        pas reprise au passage suivant. C'est le parti de la seconde passe de
        `_cron_process_reminders()` d'`opex_membership`, et il vaut mieux
        qu'un champ « déjà traité » qu'il faudrait penser à remettre à zéro.

        Chaque dossier est traité **dans son propre savepoint** — règle 10
        appliquée à une file. Sans cela, une action configurée qui échoue sur
        une mission (un projet impossible à créer, une écriture refusée)
        abandonnerait la transaction PostgreSQL et empêcherait les suivantes
        d'être traitées, pour une raison qui n'a rien à voir avec elles.

        Renvoie un état des lieux plutôt que `True` : c'est ce qu'on lit dans
        le journal du cron le jour où l'on se demande pourquoi une mission
        n'a pas démarré.
        """
        today = fields.Date.context_today(self)
        candidates = self.sudo().search([
            ('workflow_state', '=', 'running'),
            ('workflow_stage_id.code', '=', CONTRACTING_STAGE),
        ])

        demarrees, pas_encore, refusees = 0, 0, 0
        for mission in candidates:
            debut = mission._autostart_date()
            if not debut or debut > today:
                pas_encore += 1
                continue
            try:
                with self.env.cr.savepoint():
                    if mission._autostart_now():
                        demarrees += 1
                    else:
                        refusees += 1
            except Exception:
                # Le rollback du savepoint défait les écritures, **pas** le
                # cache de l'ORM : sans cela les dossiers suivants liraient
                # des valeurs qui n'ont jamais été écrites (règle 10).
                self.env.invalidate_all()
                refusees += 1
                _logger.exception(
                    "Démarrage automatique impossible sur %s", mission.name)

        resultat = {
            'demarrees': demarrees,
            'pas_encore_a_echeance': pas_encore,
            'non_franchissables': refusees,
        }
        _logger.info("Démarrage automatique des missions : %s", resultat)
        return resultat

    def _autostart_date(self):
        """La date qui déclenche, et pourquoi celle-là.

        **Le contrat en vigueur d'abord.** C'est la date que les deux parties
        ont confirmée ; `date_debut_souhaitee` sur l'appel n'est qu'un
        souhait du client, modifiable après coup, et démarrer une mission sur
        un souhait révisé unilatéralement serait exactement ce que le §19
        cherche à éviter.

        L'affectation en second : elle porte le même instantané, et sert de
        recours si la pièce n'a pas encore été produite.
        """
        self.ensure_one()
        contrat = self.sudo().contract_id
        if contrat and contrat.date_debut:
            return contrat.date_debut
        assignment = self.sudo().assignment_ids.filtered('active')[:1]
        return assignment.date_debut or False

    def _autostart_actor(self, instance):
        """Sous quelle identité franchir — et pourquoi ce n'est pas trivial.

        ⚠ **CE POINT A ÉTÉ TROUVÉ EN L'ESSAYANT, PAS EN LE TESTANT.**

        `do_transition()` juge les rôles de `env.user`, et `sudo()` ne change
        pas `env.user`. Or un `ir.cron` sans `user_id` s'exécute en
        `__system__` (uid 1), qui ne tient **aucun** rôle du module :

            transitions vues par le cron : []
            resultat : {'demarrees': 0, 'non_franchissables': 1}

        Le cron aurait donc tourné tous les jours sans jamais rien démarrer.
        Les tests unitaires ne pouvaient pas le voir : ils appellent la
        méthode `with_user(self.manager)`, c'est-à-dire sous une identité que
        le cron n'a pas. C'est la règle 20 sous un nouveau jour — un test qui
        ne passe pas par le chemin réel ne garde pas ce chemin.

        Trois recours, dans cet ordre, et le premier qui répond gagne :

        1. **l'identité configurée** — `user_id` sur l'`ir.cron`. Un
           administrateur qui désigne un compte de service doit être obéi ;
        2. **un acteur du dossier** portant un rôle autorisé sur la
           transition. C'est le meilleur des trois : la personne que le
           workflow désigne déjà comme responsable de *cette* mission aurait
           pu cliquer elle-même, et le journal nomme quelqu'un de pertinent ;
        3. rien — et le cron le **dit** plutôt que de se taire.

        Il n'y a volontairement **aucun forçage** : `group_workflow_manager`
        aurait tout débloqué d'un coup, et un cron qui force est un cron qui
        peut tout. Le commentaire de la transition dit que le démarrage est
        automatique, donc le journal ne laisse croire à personne que
        l'acteur a cliqué.
        """
        self.ensure_one()
        transition = instance.definition_id.sudo().transition_ids.filtered(
            lambda t: t.code == START_TRANSITION)[:1]
        if not transition:
            return False

        def peut(user):
            return bool(instance.available_transitions(user=user).filtered(
                lambda t: t.code == START_TRANSITION))

        if peut(self.env.user):
            return self.env.user

        # L'ordre est celui dans lequel la transition déclare ses rôles.
        # Sans ce tri, le porteur retenu dépendait de l'ordre de création des
        # lignes d'acteur, c'est-à-dire de rien.
        #
        # ⚠ Mesuré : en pratique c'est **l'intervenant** qui est retenu, et
        # c'est juste. Le responsable de mission tient `mission_manager` par
        # son **groupe**, pas par une ligne d'acteur — il n'est donc pas dans
        # `actor_ids`. Seuls le client et l'intervenant y figurent, posés à
        # la sélection. Or « Démarrer la mission » nomme explicitement
        # `intervenant` : la personne retenue est bien celle que le graphe
        # désigne comme pouvant commencer.
        #
        # On ne cherche délibérément **pas** dans les membres du groupe : il
        # faudrait en élire un, et « le premier trouvé » ne désigne personne
        # de pertinent pour ce dossier-ci.
        rang = {role.id: index
                for index, role in enumerate(transition.allowed_role_ids)}
        porteurs = instance.actor_ids.filtered(
            lambda a: a.role_id in transition.allowed_role_ids).sorted(
                key=lambda a: rang.get(a.role_id.id, len(rang)))
        for acteur in porteurs:
            if acteur.user_id and peut(acteur.user_id):
                return acteur.user_id
        return False

    def _autostart_now(self):
        """Demande la transition au moteur. `False` s'il la refuse.

        ⚠ **Rien n'est forcé.** La transition est cherchée dans
        `available_transitions(user)` — donc après le contrôle de rôle et
        d'étape — et `do_transition()` réévalue ensuite les conditions, dont
        la règle 5 du §39. Un contrat non validé fait simplement renvoyer
        `False`, et le dossier restera candidat au passage suivant : c'est la
        bonne issue, puisque le contrat peut être validé demain.
        """
        self.ensure_one()
        instance = self.sudo().workflow_instance_id
        if not instance:
            return False

        acteur = self._autostart_actor(instance)
        if not acteur:
            _logger.info(
                "%s : « %s » n'est ouverte à personne — ni à %s, ni à un "
                "acteur du dossier. Étape, rôle ou condition.",
                self.name, START_TRANSITION, self.env.user.login)
            return False

        transition = instance.available_transitions(user=acteur).filtered(
            lambda t: t.code == START_TRANSITION)[:1]
        try:
            self.sudo().with_user(acteur).sudo().workflow_do_transition(
                transition, comment=_(
                    "Démarrage automatique : la date de début contractuelle "
                    "du %s est atteinte.") % self._autostart_date())
        except Exception as refus:
            _logger.info("%s : démarrage refusé — %s", self.name, refus)
            return False
        return True
