"""Les modules optionnels, résolus à l'appel — `sale`, `project`.

POURQUOI CE FICHIER EXISTE

L'instance de déploiement ne dispose ni de `sale` ni de `project`. Les
déclarer au manifeste rendait `opex_intervenants` **non installable** : Odoo
refuse un module dont une dépendance est introuvable, et le refus est total —
pas de portail, pas de matching, pas de workflows.

Le parti retenu est celui qui a déjà servi pour `opex_ai_core` à l'Extension
IA-1, et pour la même raison : **un module absent ne doit bloquer aucun
parcours.** Le service est résolu au moment de l'appel, et son absence se lit
comme une fonctionnalité éteinte, pas comme une panne.

CE QUE CE PONT N'EST PAS

Ce n'est pas une réimplémentation dégradée. Il n'y a pas de facturation de
remplacement, pas de mini-gestion de projet. Quand `sale` est absent, la
mission se clôture **sans commande de vente**, et le dossier le dit par une
note. Quand `project` est absent, la mission démarre **sans projet
d'exécution**, et le dossier le dit aussi. Aucune logique de repli n'est
écrite ici, et c'est ce qui garde ces fichiers lisibles.

COMMENT REBRANCHER, LE JOUR OÙ `sale` SERA DISPONIBLE

Trois gestes, et rien d'autre :

1. remettre `'project', 'sale'` dans `depends` du manifeste ;
2. remettre `invoice_policy` sur le produit de service
   (`data/mission_invoicing_data.xml`) — sans lui, `_create_invoices()`
   refuserait de facturer une quantité livrée nulle ;
3. suivre les blocs marqués « REBRANCHEMENT » dans les quatre fichiers
   concernés : les deux paires `*_ref` / `*_name` y redeviennent des
   `Many2one`, et les deux `@api.depends` retrouvent leur chaîne complète.

La liste exhaustive de ces blocs s'obtient par :

    grep -rn "REBRANCHEMENT" models/ views/ data/ tests/

POURQUOI `self.env.get()` ET PAS UN `try: import`

Un module Odoo peut être présent sur le disque et non installé sur la base.
Seul le registre le sait, et `self.env` est le registre.
"""

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

SALE_ORDER = 'sale.order'
PROJECT = 'project.project'
PROJECT_TASK = 'project.task'

#: Le module qui apporte chaque modèle. Sert uniquement aux messages : un
#: utilisateur à qui l'on dit « le modèle sale.order est absent » n'a rien
#: appris ; « le module Ventes n'est pas installé » lui dit quoi demander.
PROVIDED_BY = {
    SALE_ORDER: "Ventes (sale)",
    PROJECT: "Projet (project)",
    PROJECT_TASK: "Projet (project)",
}


class OptionalBackend(models.AbstractModel):
    """Le point de passage unique vers les modules non déclarés.

    Tout accès à `sale.order`, `project.project` et `project.task` passe par
    ici. Un test lit le source des modèles et refuse un
    `self.env['sale.order']` écrit ailleurs : sans cette discipline, le jour
    où l'on installe sur une base encore plus dépouillée, on découvrirait les
    endroits non protégés un par un, en production.
    """

    _name = 'opex.optional.backend'
    _description = "Accès aux modules optionnels, s'ils sont installés"

    @api.model
    def _backend(self, model_name):
        """Le modèle s'il est au registre, sinon None.

        Ne lève jamais. `self.env['x']` lève une `KeyError` sur un modèle
        absent ; `self.env.get('x')` rend None, ce qui est précisément la
        réponse utile ici.
        """
        return self.env.get(model_name)

    @api.model
    def _backend_available(self, model_name):
        return self.env.get(model_name) is not None

    @api.model
    def _backend_missing_note(self, model_name):
        """La phrase à poser dans le dossier quand la fonction est éteinte.

        Elle nomme le module, pas le modèle, et elle dit **ce qu'il reste à
        faire à la main**. Une note qui constate sans orienter fait perdre le
        temps qu'elle prétend faire gagner.
        """
        return PROVIDED_BY.get(model_name, model_name)

    @api.model
    def _backend_record(self, model_name, record_id):
        """L'enregistrement désigné par son id, ou un recordset vide.

        C'est le pendant en lecture des paires `*_ref` / `*_name` qui ont
        remplacé les `Many2one` : l'id reste conservé en base, et le jour où
        le module revient, la relation se relit sans migration de données.
        """
        model = self.env.get(model_name)
        if model is None or not record_id:
            return None
        return model.sudo().browse(record_id).exists()
