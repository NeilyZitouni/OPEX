# Chargé en premier : `sale` et `project` ne sont pas déclarés au manifeste,
# et tout accès à leurs modèles passe par ce pont. Voir sa docstring pour la
# marche à suivre le jour où ces modules seront disponibles.
from . import optional_backends
from . import mission_referentials
from . import mission_request
from . import mission_application
# Extension 3 — le capital de l'intervenant. Chargé après les référentiels de
# mission : les expériences pointent vers `opex.mission.type` et `.domain`.
from . import expert_capital
from . import expert_profile
from . import res_partner
# Extension 4 — la configuration du Smart Matching. Chargé après le capital :
# les critères comparent ce que `res_partner` expose.
from . import matching
from . import res_users
# Extension 5 — la vue publique de l'appel et la candidature Lean.
from . import mission_public
# Extension 6 — le pool unique : colonnes de Kanban et alertes d'éligibilité.
# Chargé après `matching` : les alertes rejouent ses critères éliminatoires.
from . import mission_application_pool
# Extension 7 — sélection, affectation, contractualisation. `mission_operational`
# est chargé en dernier : il étend les deux modèles centraux et référence les
# deux modèles ci-dessus.
from . import mission_assignment
from . import mission_contract
from . import mission_operational
# Extension 8 — l'exécution. `mission_execution_request` en dernier : il étend
# la mission et référence les trois modèles ci-dessus.
from . import mission_deliverable
from . import mission_execution
from . import mission_execution_request
# Extension 9 — service fait et facturation. `service_acceptance` d'abord : son
# `related` vers `deliverable_unvalidated_count` est ce qui permet à la règle 6
# de garder aussi la validation du cluster. `mission_invoicing` ensuite, et en
# dernier du module : il étend `operational_trigger` par `selection_add`, donc
# après `mission_operational` qui le déclare.
from . import service_acceptance
from . import mission_invoicing
# Extension 10 - évaluations, réputation, historique. `expert_reputation` en
# dernier : il lit les évaluations et les affectations.
from . import mission_evaluation
from . import expert_reputation
# Le pont vers l'assistance IA. Charge tot : plusieurs modeles l'appellent, et
# il ne depend de rien - `opex_ai_core` n'est pas une dependance declaree.
from . import ai_bridge
# Extension 11 - tableaux de bord, notifications et cloche portail.
from . import mission_dashboard
from . import mission_notifications
from . import res_partner_bell
# Extension 12 - integration finale : catalogue filtre, accueil unique, KPI.
from . import portal_integration
# Extension IA-1 - les trois axes du §9 et l'extraction de CV du §6.
# `expert_skill_axes` avant `expert_cv_extraction` : le second vise les
# valeurs que le premier declare.
from . import expert_skill_axes
# Le CV depose, son analyse asynchrone et ses propositions - §6, §17, §24.
from . import expert_cv_source
# Extension IA-2 - la taxonomie du §8 et le rapprochement en deux temps.
#
# `skill_catalog` en premier : il declare `opex.skill.family`, que la ligne
# d'arbitrage reference, et il greffe `family_id` sur le referentiel du
# Module 2 que les trois autres interrogent.
from . import skill_catalog
# `competence_synonyme` ensuite : les deux suivants s'en servent.
from . import competence_synonyme
from . import competence_arbitrage
from . import competence_resolution
# Dette D1 - le referentiel de certifications, et le critere eliminatoire qui
# compare des references canoniques au lieu de texte libre.
#
# `certification_catalog` en premier : il declare `opex.certification.synonyme`
# que les trois suivants interrogent, et greffe `porte` sur le referentiel du
# Module 1.
from . import certification_catalog
from . import certification_resolution
from . import certification_axes
from . import mission_certification
from . import res_partner_certification
# Extension IA-3 - le controle qualite assiste du §11, et la machine a etats
# du cycle de qualification. Charge en dernier : il lit le capital de
# l'Extension 3, les axes de l'IA-1 et le referentiel de certifications de D1.
from . import expert_qualification_review
