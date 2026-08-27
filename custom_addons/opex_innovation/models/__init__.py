from . import innovation_competence
from . import innovation_document
from . import expert_profile
from . import investor_profile
from . import innovation_project
from . import project_document
from . import evaluation
from . import remediation
# Extension 17 — financement, industrialisation, clôture, évaluation finale.
# `financement` étend `opex.innovation.project` : chargé après lui.
from . import financement
from . import industrialisation
from . import closure
from . import final_evaluation
# Extension 18 — surcharge `write()` de `opex.innovation.project` : chargé
# après `financement`, qui déclare le champ observé.
from . import notifications
# Extension 19 — les jalons lisibles par le porteur.
from . import milestone
# Extension 16 — accompagnement, roadmap, livrables. `deliverable` référence
# `accompagnement` : chargé après lui.
from . import accompagnement
from . import deliverable
from . import res_partner

# Point de contrôle de rôle unique du module (règle transversale 2).
from . import res_users
