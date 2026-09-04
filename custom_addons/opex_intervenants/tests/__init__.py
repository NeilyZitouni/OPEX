from . import test_mission_request
from . import test_mission_application
from . import test_mission_portal
from . import test_expert_capital
from . import test_matching
from . import test_public_portal
from . import test_pool
# Extension 7 — sélection, affectation, contrat, ordre de mission.
from . import test_contracting
# Extension 8 — livrables, points d'avancement, incidents, barre du §40.
from . import test_execution
# Extension 9 — service fait, règle 6 du §39, facturation et paiement.
from . import test_service_acceptance
# Extension 10 - évaluations, réputation, historique.
from . import test_evaluation
# Extension 11 - espaces, priorisation, notifications, cloche portail.
from . import test_dashboard
# Extension 12 - catalogue filtre, accueil unique, indicateurs globaux.
from . import test_integration
# Extension IA-2 - rapprochement taxonomique du §8 et file d'arbitrage.
from . import test_competence_taxonomy
# Extension IA-1 - trois axes du §9, parsing asynchrone du CV (§6, §17, §24).
from . import test_cv_axes
from . import test_cv_parsing
# Modules optionnels - `sale` et `project` ne sont plus des dependances.
from . import test_optional_backends
# Extension IA-2 - la taxonomie du §8, son socle, et les sept attributs.
from . import test_skill_catalog
# La promotion - le maillon qui ferme la chaine CV -> matching.
from . import test_cv_promotion
# Dette D1 - le referentiel de certifications et le critere qui ecarte.
from . import test_certification_d1
