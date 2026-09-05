"""Aucun nom écrasé sur l'arbre `CustomerPortal` — ni entre nous, ni avec Odoo.

LE DÉFAUT QUE CE TEST GARDE

Odoo fusionne toutes les sous-classes de `CustomerPortal` en **une seule**
classe. Deux modules qui nomment un attribut pareil n'en gardent qu'un : celui
du module chargé en dernier. Sans erreur, sans avertissement.

Payé deux fois, et les deux symptômes ne se ressemblaient pas.

**Entre nos modules.** `opex_innovation` dépend d'`opex_membership`, donc il
gagne, et trois de ses attributs écrasaient les nôtres :

    _current_draft   cherchait un projet d'innovation, jamais un dossier
    _STEP_FIELDS     rendait les étapes de l'innovation
    _save_step       écrivait selon les règles de l'innovation

Conséquence visible : `/my/membership/new` bouclait sur son premier écran, et
chaque tentative créait un dossier de plus.

**Avec Odoo lui-même**, et celui-là est pire parce que le dégât est chez le
voisin. `opex_innovation.portal_my_projects` portait `/my/innovation` sous le
nom qu'emploie `project/ProjectCustomerPortal` pour `/my/projects`. La route
native **disparaissait du routing map** : 404 sur `/my/projects`, 200 sur
`/my/innovation`. Rien ne pouvait le signaler — la route perdue n'est pas la
nôtre, et son module ne sait pas que nous existons.

CE QUE CE TEST N'INTERDIT PAS

Les surcharges **coopératives**, qui sont le fonctionnement normal d'Odoo :
`_prepare_home_portal_values` est défini par sept de nos classes et sept
classes natives, et chacune relaie `super()`. Interdire tout partage de nom
interdirait le mécanisme d'extension lui-même.

La ligne de partage est donc : **un nom partagé est légitime s'il relaie
`super()`**, fautif sinon. Les quatre tests vérifient les deux faces.

⚠ La leçon de méthode, et elle a coûté un aller-retour : `portal_my_projects`
figurait d'abord dans la liste des noms coopératifs, au motif que deux de nos
classes le partageaient en s'appelant proprement. C'était vrai, et hors sujet :
la chaîne `super()` était interne à `opex_innovation`, et son premier maillon
n'appelait rien — c'est-à-dire écrasait le natif. **Une chaîne d'héritage bien
formée ne prouve rien sur ce qui la précède.**
"""

import ast
import glob
import os
from collections import defaultdict

from odoo.tests.common import TransactionCase, tagged

#: Les modules du portail dont les contrôleurs se rejoignent dans la classe
#: fusionnée. `opex_crowdfunding` en fait partie : il est isolé par
#: construction côté métier, pas côté `CustomerPortal`.
MODULES = ('opex_membership', 'opex_innovation', 'opex_intervenants',
           'opex_crowdfunding')

#: Les points d'extension d'Odoo, partagés par conception. Chacun **doit**
#: relayer `super()`, et c'est ce que le troisième test vérifie.
#:
#: La liste est volontairement courte. Y ajouter un nom pour faire taire un
#: échec revient à déclarer coopératif ce qui ne l'est pas — c'est exactement
#: ce qui a laissé passer `portal_my_projects`.
COOPERATIFS = {
    '_prepare_home_portal_values',
    '_prepare_portal_layout_values',
}


def racine_addons():
    """Le dossier `custom_addons`, quel que soit l'endroit d'où l'on part."""
    ici = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(ici))


def _relaie_super(methode):
    """`super().<même nom>(...)` apparaît-il quelque part dans le corps ?"""
    return any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == methode.name
        and isinstance(n.func.value, ast.Call)
        and getattr(n.func.value.func, 'id', '') == 'super'
        for n in ast.walk(methode))


def _classes_portail_du_fichier(chemin, connues):
    """Les classes du fichier qui aboutissent à `CustomerPortal`.

    `connues` accumule les noms déjà reconnus comme classes de portail, ce qui
    permet d'attraper l'héritage **indirect** — `InnovationHolderDashboard`
    hérite d'`InnovationProjectPortal`, pas de `CustomerPortal`. Sans cela le
    relevé passerait à côté du second maillon d'une chaîne, c'est-à-dire de
    celui qui donne l'illusion que tout va bien.
    """
    with open(chemin, encoding='utf-8') as fichier:
        arbre = ast.parse(fichier.read())
    trouvees = []
    for noeud in arbre.body:
        if not isinstance(noeud, ast.ClassDef):
            continue
        bases = [
            base.id if isinstance(base, ast.Name) else getattr(base, 'attr', '')
            for base in noeud.bases
        ]
        if 'CustomerPortal' in bases or connues & set(bases):
            connues.add(noeud.name)
            trouvees.append(noeud)
    return trouvees


def _membres(classe):
    """(nom, relaie_super) pour chaque méthode et chaque attribut de classe."""
    for membre in classe.body:
        if isinstance(membre, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield membre.name, _relaie_super(membre)
        elif isinstance(membre, ast.Assign):
            for cible in membre.targets:
                if isinstance(cible, ast.Name):
                    yield cible.id, False


def classes_du_portail(base=None, modules=MODULES):
    """Toutes les classes de portail des modules demandés.

    Lecture **statique** du source, et c'est délibéré : à l'exécution, la
    classe est déjà fusionnée et les noms écrasés ont disparu. C'est
    précisément ce qu'on veut voir, donc il faut regarder avant la fusion.
    """
    base = base or racine_addons()
    connues = set()
    trouvees = []
    for module in modules:
        motif = os.path.join(base, module, 'controllers', '*.py')
        for chemin in sorted(glob.glob(motif)):
            for classe in _classes_portail_du_fichier(chemin, connues):
                trouvees.append((module, os.path.basename(chemin), classe))
    return trouvees


def classes_natives():
    """Les mêmes, du côté des addons livrés avec Odoo.

    Le chemin est déduit de `project`, qui est une dépendance du portail :
    coder « ../../odoo/addons » en dur casserait au premier déplacement de
    l'arborescence, et le test passerait au vert en ne lisant rien.
    """
    import odoo.addons.project as ancre
    base = os.path.dirname(os.path.dirname(os.path.abspath(ancre.__file__)))
    connues = set()
    trouvees = []
    for chemin in sorted(glob.glob(os.path.join(base, '*', 'controllers', '*.py'))):
        module = chemin.split(os.sep)[-3]
        if module in MODULES:
            continue
        try:
            for classe in _classes_portail_du_fichier(chemin, connues):
                trouvees.append((module, os.path.basename(chemin), classe))
        except (SyntaxError, UnicodeDecodeError):
            continue
    return trouvees


@tagged('post_install', '-at_install')
class TestPortalCollisions(TransactionCase):

    def test_no_attribute_is_shared_between_portal_classes(self):
        """Le relevé entre nos quatre modules.

        Un nom partagé hors des points d'extension coopératifs est une
        collision : l'un des deux modules perd son attribut, et le symptôme
        apparaîtra ailleurs, longtemps après.
        """
        classes = classes_du_portail()
        self.assertGreaterEqual(
            len(classes), 10,
            "Le relevé ne trouve presque aucune classe : le chemin des "
            "contrôleurs est probablement faux, et ce test passerait au vert "
            "sans rien lire.")

        proprietaires = defaultdict(list)
        for module, _fichier, classe in classes:
            for nom, _relaie in _membres(classe):
                if nom.startswith('__') or nom in COOPERATIFS:
                    continue
                proprietaires[nom].append((module, classe.name))

        collisions = {
            nom: lieux for nom, lieux in proprietaires.items()
            if len({module for module, _c in lieux}) > 1
        }
        self.assertFalse(
            collisions,
            "Des attributs sont partagés entre modules sur l'arbre "
            "`CustomerPortal`. Odoo n'en gardera qu'un, sans erreur — "
            "préfixez-les par leur domaine :\n%s" % "\n".join(
                "  %s : %s" % (nom, ", ".join(
                    "%s/%s" % (m, c) for m, c in lieux))
                for nom, lieux in sorted(collisions.items())))

    def test_no_native_odoo_portal_route_is_shadowed(self):
        """Le relevé contre Odoo lui-même, et c'est celui qui a mordu.

        `opex_innovation.portal_my_projects` a fait disparaître
        `/my/projects` du routing map de `project` : 404 sur une route dont
        nous ne sommes pas propriétaires. Un nom partagé avec un module natif
        n'est acceptable que s'il relaie `super()` — sinon il supprime une
        fonctionnalité qui n'est pas la nôtre.
        """
        natifs = defaultdict(list)
        for module, _fichier, classe in classes_natives():
            for nom, _relaie in _membres(classe):
                if not nom.startswith('__'):
                    natifs[nom].append("%s/%s" % (module, classe.name))
        self.assertGreaterEqual(
            len(natifs), 40,
            "Presque aucun nom natif relevé : le chemin des addons d'Odoo est "
            "faux, et ce test ne compare rien.")

        fautifs = []
        for module, _fichier, classe in classes_du_portail():
            for nom, relaie in _membres(classe):
                if nom.startswith('__') or nom not in natifs or relaie:
                    continue
                fautifs.append(
                    "  %s/%s.%s écrase %s"
                    % (module, classe.name, nom, ", ".join(natifs[nom])))

        self.assertFalse(
            fautifs,
            "Des noms d'Odoo sont repris sans relayer `super()`. La méthode "
            "native est perdue et sa route sort du routing map — chez un "
            "module qui ne sait pas que nous existons :\n%s"
            % "\n".join(sorted(fautifs)))

    def test_no_url_is_declared_by_two_differently_named_methods(self):
        """Le trou entre les deux tests de ce projet.

        Deux méthodes de noms **différents** qui déclarent la **même** URL :
        Odoo n'en garde qu'une, et ni l'un ni l'autre de nos gardes ne le
        voit. `test_no_attribute_is_shared_between_portal_classes` compare des
        noms, et ils diffèrent ; `test_portal_links` vérifie que l'URL
        résout, et elle résout — vers l'autre écran.

        ⚠ Lu par AST, jamais par expression régulière. Deux routes du projet
        sont écrites en concaténation implicite :

            @http.route(['/staff/missions/<int:mission_id>/matching'
                         '/<int:candidate_id>/profil'], …)

        Un relevé qui lit le source ligne à ligne n'en voit que le premier
        fragment et déclare identiques deux URL qui ne le sont pas. Mesuré :
        deux faux positifs au premier essai. `ast.literal_eval` sur le nœud de
        la liste rend la chaîne complète, concaténation comprise.

        ⚠ Le cas légitime, et il existe : une sous-classe qui **redéfinit** la
        route de sa classe parente sous le **même** nom. C'est le mécanisme
        d'extension d'Odoo — `InnovationHolderDashboard` étend ainsi
        `/my/innovation`. Ce qui est fautif est deux noms distincts.
        """
        racine = racine_addons()
        urls = defaultdict(list)
        for module in MODULES:
            for chemin in sorted(glob.glob(
                    os.path.join(racine, module, 'controllers', '*.py'))):
                try:
                    arbre = ast.parse(open(chemin, encoding='utf-8').read())
                except (SyntaxError, UnicodeDecodeError):
                    continue
                for noeud in ast.walk(arbre):
                    if not isinstance(noeud, (ast.FunctionDef,
                                              ast.AsyncFunctionDef)):
                        continue
                    for deco in noeud.decorator_list:
                        if not isinstance(deco, ast.Call) or not deco.args:
                            continue
                        nom = getattr(deco.func, 'attr',
                                      getattr(deco.func, 'id', ''))
                        if nom != 'route':
                            continue
                        try:
                            valeur = ast.literal_eval(deco.args[0])
                        except (ValueError, SyntaxError):
                            continue
                        chaines = ([valeur] if isinstance(valeur, str)
                                   else list(valeur))
                        for url in chaines:
                            urls[url].append(
                                (module, os.path.basename(chemin), noeud.name))

        self.assertGreaterEqual(
            len(urls), 60,
            "Presque aucune route relevée : le test ne compare rien.")

        fautives = {
            url: lieux for url, lieux in urls.items()
            if len({methode for _m, _f, methode in lieux}) > 1
        }
        self.assertFalse(
            fautives,
            "Une même URL est déclarée par deux méthodes de noms différents. "
            "Odoo n'en enregistre qu'une, sans erreur : l'autre écran devient "
            "inatteignable.\n%s" % "\n".join(
                "  %s\n%s" % (url, "\n".join(
                    "      %-18s %-28s %s" % lieu for lieu in sorted(lieux)))
                for url, lieux in sorted(fautives.items())))

    def test_the_membership_journey_owns_its_names(self):
        """Les trois noms qui ont causé le blocage, nommément.

        Le premier test les couvre déjà. Celui-ci les nomme : le jour où l'un
        réapparaît sans préfixe, le message dira lequel et pourquoi, plutôt
        que de renvoyer à un relevé.
        """
        chemin = os.path.join(
            racine_addons(), 'opex_membership', 'controllers', 'portal.py')
        with open(chemin, encoding='utf-8') as fichier:
            arbre = ast.parse(fichier.read())

        noms = set()
        for noeud in arbre.body:
            if isinstance(noeud, ast.ClassDef):
                noms.update(nom for nom, _relaie in _membres(noeud))

        for interdit, raison in (
            ('_current_draft',
             "cherchait un projet d'innovation : le parcours bouclait"),
            ('_STEP_FIELDS',
             "rendait les étapes de l'innovation : aucun champ n'était "
             "enregistré"),
            ('_save_step',
             "écrivait selon les règles de l'innovation"),
        ):
            self.assertNotIn(
                interdit, noms,
                "« %s » est redevenu un nom non préfixé. Écrasé par "
                "`opex_innovation`, il %s." % (interdit, raison))

        # L'assertion positive : les versions préfixées sont bien là.
        for attendu in ('_membership_current_draft',
                        '_MEMBERSHIP_STEP_FIELDS',
                        '_membership_save_step'):
            self.assertIn(
                attendu, noms,
                "« %s » a disparu : le parcours ne peut plus fonctionner."
                % attendu)

    def test_the_cooperative_overrides_all_call_super(self):
        """Le pendant : un point d'extension qui ne relaie pas efface les autres.

        `_prepare_home_portal_values` est défini par sept de nos classes.
        C'est normal — c'est le mécanisme d'extension d'Odoo. Ce qui ne l'est
        pas, c'est qu'une seule d'entre elles oublie `super()` : les compteurs
        des six autres disparaissent alors de l'accueil, sans erreur.
        """
        verifiees = 0
        for module, _fichier, classe in classes_du_portail():
            for nom, relaie in _membres(classe):
                if nom not in COOPERATIFS:
                    continue
                verifiees += 1
                self.assertTrue(
                    relaie,
                    "%s/%s.%s ne relaie pas `super()` : les surcharges des "
                    "autres modules sont effacées, sans erreur."
                    % (module, classe.name, nom))
        self.assertGreaterEqual(
            verifiees, 7,
            "Presque aucune surcharge coopérative examinée : le relevé ne "
            "vérifie rien.")
