# Premier test du module. `opex_membership` n'en avait aucun : il a ete livre
# avant que la discipline de test du projet soit posee, et il est reste gele
# depuis. Ce fichier ne rattrape pas ce retard - il garde le defaut precis qui
# a ete diagnostique, et rien d'autre.
from . import test_membership_deposit
# La regle 1 du projet, executee : aucun nom partage sur `CustomerPortal`.
from . import test_portal_collisions
# Son pendant cote URL : aucun lien de portail ne mene a une route absente.
from . import test_portal_links
# La regle 6 : le contrat de `/my/counters`, tenu par les quatre modules.
from . import test_portal_counters
# La meme fusion, cote ORM : aucune surcharge muette sur un modele partage.
from . import test_model_overrides
