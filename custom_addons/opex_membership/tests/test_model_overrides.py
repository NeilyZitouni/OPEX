"""Aucune surcharge muette sur un modèle que plusieurs modules étendent.

LA MÊME FUSION QUE `CustomerPortal`, MAIS SUR LES MODÈLES

Odoo fusionne les classes qui déclarent le même `_inherit`. Deux modules qui
nomment une méthode pareil n'en gardent qu'une chaîne : chacun doit relayer
`super()`, sinon la logique de ceux qui le précèdent disparaît — sans erreur,
sans avertissement.

`test_portal_collisions.py` garde cette propriété sur l'arbre `CustomerPortal`.
Celui-ci la garde là où la surface partagée est bien plus large : **les
modèles**. Quatre de nos modules étendent `res.partner`.

CE QUE LA CHAÎNE PORTE AUJOURD'HUI

Le protocole de la cloche du portail, inventé par `opex_membership` et repris
par les trois autres :

    res.partner._opex_owned_record_ids   4 porteurs
    res.partner._opex_notification_url   4 porteurs

Un maillon muet et la cloche perd les dossiers d'un module entier. C'est
d'ailleurs dans cette zone qu'est née la règle 22, et le défaut d'alors n'avait
été trouvé qu'au navigateur.

⚠ LES TROIS FORMES DE RELAIS, ET POURQUOI IL FAUT LES TROIS

Un relevé naïf produit des faux positifs sur deux d'entre elles, et un test qui
signale du code correct finit désactivé.

1. **`super().x(...)`** — la forme ordinaire.

2. **`getattr(super(), 'x', None)`** — le relais **défensif**, employé quand le
   parent est optionnel. `opex_crowdfunding` ne dépend pas d'`opex_membership`
   et doit rester installable seul : un `super().x()` direct y lèverait un
   `AttributeError`. C'est la forme correcte, pas un oubli.

3. **le définisseur de base** — `opex_membership` a *inventé*
   `_opex_owned_record_ids`. Il n'a aucun parent à relayer, et exiger un
   `super()` de sa part n'aurait aucun sens.

La troisième ne se déduit pas du source : elle se déduit des **dépendances**.
Le module qui ne dépend d'aucun autre porteur est la racine de la chaîne.
"""

import ast
import glob
import os
import re
from collections import defaultdict

from odoo.tests.common import TransactionCase, tagged

MODULES = ('opex_workflow', 'opex_membership', 'opex_innovation',
           'opex_intervenants', 'opex_crowdfunding', 'opex_ai_core')


def racine_addons():
    ici = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(ici))


def _chaines(noeud):
    """Les chaînes d'une constante ou d'une liste/tuple de constantes."""
    if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
        return [noeud.value]
    if isinstance(noeud, (ast.List, ast.Tuple)):
        return [e.value for e in noeud.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return []


def _relaie(methode):
    """La méthode relaie-t-elle son parent, sous l'une des deux formes ?"""
    for n in ast.walk(methode):
        if not isinstance(n, ast.Call):
            continue
        fonction = n.func
        # 1. super().<même nom>(...)
        if isinstance(fonction, ast.Attribute) \
                and fonction.attr == methode.name \
                and isinstance(fonction.value, ast.Call) \
                and getattr(fonction.value.func, 'id', '') == 'super':
            return True
        # 2. getattr(super(), '<même nom>', …) — le relais défensif.
        if getattr(fonction, 'id', '') == 'getattr' and len(n.args) >= 2 \
                and isinstance(n.args[0], ast.Call) \
                and getattr(n.args[0].func, 'id', '') == 'super' \
                and isinstance(n.args[1], ast.Constant) \
                and n.args[1].value == methode.name:
            return True
    return False


def _depends(module):
    """Les dépendances déclarées au manifeste."""
    chemin = os.path.join(racine_addons(), module, '__manifest__.py')
    try:
        source = open(chemin, encoding='utf-8').read()
    except OSError:
        return set()
    trouve = re.search(r"'depends'\s*:\s*(\[[^\]]*\])", source, re.S)
    if not trouve:
        return set()
    try:
        return set(ast.literal_eval(trouve.group(1)))
    except (ValueError, SyntaxError):
        return set()


def _depends_transitif(module, vus=None):
    """Les dépendances, en suivant la chaîne à travers nos modules."""
    vus = vus if vus is not None else set()
    for parent in _depends(module) - vus:
        vus.add(parent)
        if parent in MODULES:
            _depends_transitif(parent, vus)
    return vus


def racine_de_la_chaine(porteurs):
    """Le porteur qui **définit** le protocole, seul exempté de relayer.

    ⚠ Le critère est « quelqu'un dépend de lui », **pas** « il ne dépend de
    personne ». La nuance a été mesurée, et l'erreur inverse rendait le test
    inoffensif là où il comptait le plus.

    `opex_crowdfunding` ne déclare aucun de nos modules dans son manifeste. Le
    premier critère en faisait donc une racine et l'exemptait — alors qu'il
    est une **feuille** : personne ne le précède par construction, rien ne
    garantit son ordre de chargement face à `opex_membership`, et un maillon
    muet y effacerait la cloche du Module 1. C'est exactement pourquoi il
    écrit un relais défensif, et le test devait pouvoir le lui demander.

    Le vrai définisseur se reconnaît à ce qu'un autre porteur **s'appuie sur
    lui** : `opex_innovation` et `opex_intervenants` dépendent
    d'`opex_membership`, donc il est en amont de tous, donc il n'a personne à
    relayer.
    """
    modules = {module for module, _f, _c, _r in porteurs}
    amont = set()
    for module in modules:
        amont |= (_depends_transitif(module) & (modules - {module}))
    return amont


def relever(modules):
    """{(modèle, méthode): [(module, fichier, classe, relaie)]}"""
    racine = racine_addons()
    porteurs = defaultdict(list)
    for module in modules:
        for chemin in sorted(glob.glob(
                os.path.join(racine, module, 'models', '*.py'))):
            try:
                arbre = ast.parse(open(chemin, encoding='utf-8').read())
            except (SyntaxError, UnicodeDecodeError):
                continue
            for classe in [n for n in arbre.body if isinstance(n, ast.ClassDef)]:
                noms, herites = [], []
                for membre in classe.body:
                    if isinstance(membre, ast.Assign) and len(membre.targets) == 1 \
                            and isinstance(membre.targets[0], ast.Name):
                        if membre.targets[0].id == '_name':
                            noms = _chaines(membre.value)
                        elif membre.targets[0].id == '_inherit':
                            herites = _chaines(membre.value)
                # Un modèle **étendu** : `_inherit` sans `_name`, ou les deux
                # égaux. Un `_inherit` avec un `_name` différent est un modèle
                # neuf qui emprunte un mixin — il n'écrase personne.
                cibles = [m for m in herites if not noms or m in noms]
                if not cibles:
                    continue
                for membre in classe.body:
                    if not isinstance(membre, (ast.FunctionDef,
                                               ast.AsyncFunctionDef)):
                        continue
                    if membre.name.startswith('__'):
                        continue
                    for cible in cibles:
                        porteurs[(cible, membre.name)].append(
                            (module, os.path.basename(chemin), classe.name,
                             _relaie(membre)))
    return porteurs


@tagged('post_install', '-at_install')
class TestModelOverrides(TransactionCase):

    def setUp(self):
        super().setUp()
        self.installes = tuple(self.env['ir.module.module'].sudo().search([
            ('name', 'in', list(MODULES)), ('state', '=', 'installed'),
        ]).mapped('name'))
        self.assertGreaterEqual(
            len(self.installes), 3,
            "Presque aucun de nos modules n'est installé : le relevé ne "
            "compare rien.")
        self.porteurs = relever(self.installes)
        self.assertGreaterEqual(
            len(self.porteurs), 30,
            "Le relevé ne trouve presque aucune méthode sur un modèle "
            "étendu : le chemin de lecture est probablement faux, et les "
            "assertions passeraient au vert sans rien lire.")

    def _partages(self):
        """Les noms portés par plus d'un module sur le même modèle."""
        return {
            cle: lieux for cle, lieux in self.porteurs.items()
            if len({module for module, _f, _c, _r in lieux}) > 1
        }

    def test_every_shared_model_method_relays_its_parent(self):
        """Le test central : un maillon muet efface ceux d'avant.

        Seul le définisseur du protocole est exempté, et il se reconnaît à ce
        qu'un autre porteur **dépend de lui** — voir `racine_de_la_chaine()`,
        dont la docstring dit pourquoi le critère inverse rendait ce test
        inoffensif.

        Le déduire du source serait impossible : rien, dans une méthode qui
        n'appelle pas `super()`, ne dit si elle invente le protocole ou si
        elle l'oublie. Seules les dépendances le disent.
        """
        fautifs = []
        for (modele, methode), lieux in sorted(self._partages().items()):
            modules = {module for module, _f, _c, _r in lieux}
            amont = racine_de_la_chaine(lieux)
            for module, fichier, classe, relaie in sorted(lieux):
                if relaie or module in amont:
                    continue
                fautifs.append(
                    "  %s.%s — %s/%s (%s) ne relaie pas son parent ; "
                    "porteurs : %s"
                    % (modele, methode, module, fichier, classe,
                       ", ".join(sorted(modules))))

        self.assertFalse(
            fautifs,
            "Des surcharges effacent celles des modules chargés avant elles. "
            "Odoo ne signale rien : la fonctionnalité disparaît, chez le "
            "voisin.\n%s" % "\n".join(fautifs))

    def test_the_portal_bell_protocol_is_still_relayed_by_everyone(self):
        """Le protocole maison, nommé.

        Le test précédent le couvre. Celui-ci le nomme et compte ses
        porteurs : le jour où un module cesse de participer, le message dira
        lequel des deux cas s'est produit — un maillon muet, ou un maillon
        disparu. Les deux vident la cloche, mais pas pour la même raison.
        """
        for methode in ('_opex_owned_record_ids', '_opex_notification_url'):
            lieux = self.porteurs.get(('res.partner', methode), [])
            modules = {module for module, _f, _c, _r in lieux}
            self.assertGreaterEqual(
                len(modules), 3,
                "« %s » n'est plus porté que par %s. Un module a cessé "
                "d'alimenter la cloche du portail : ses dossiers n'y "
                "apparaîtront plus." % (methode, sorted(modules) or "personne"))
            amont = racine_de_la_chaine(lieux)
            muets = [
                "%s/%s" % (module, classe)
                for module, _f, classe, relaie in lieux
                if not relaie and module not in amont
            ]
            self.assertFalse(
                muets,
                "« %s » : %s n'appelle pas son parent. La cloche perdra les "
                "dossiers des modules chargés avant." % (methode, ", ".join(muets)))

    def test_no_field_is_declared_twice_on_a_shared_model(self):
        """Deux modules, un même nom de champ sur le même modèle.

        Le second gagne, et sa définition remplace la première : type, calcul,
        dépendances comprises. Le module dépossédé continue de lire le champ
        sans savoir qu'il n'est plus le sien.
        """
        racine = racine_addons()
        champs = defaultdict(set)
        examines = 0
        for module in self.installes:
            for chemin in glob.glob(
                    os.path.join(racine, module, 'models', '*.py')):
                try:
                    arbre = ast.parse(open(chemin, encoding='utf-8').read())
                except (SyntaxError, UnicodeDecodeError):
                    continue
                for classe in [n for n in arbre.body
                               if isinstance(n, ast.ClassDef)]:
                    noms, herites = [], []
                    for membre in classe.body:
                        if isinstance(membre, ast.Assign) \
                                and len(membre.targets) == 1 \
                                and isinstance(membre.targets[0], ast.Name):
                            if membre.targets[0].id == '_name':
                                noms = _chaines(membre.value)
                            elif membre.targets[0].id == '_inherit':
                                herites = _chaines(membre.value)
                    cibles = [m for m in herites if not noms or m in noms]
                    if not cibles:
                        continue
                    for membre in classe.body:
                        if not isinstance(membre, ast.Assign) \
                                or len(membre.targets) != 1 \
                                or not isinstance(membre.targets[0], ast.Name) \
                                or not isinstance(membre.value, ast.Call):
                            continue
                        origine = getattr(membre.value.func, 'value', None)
                        if getattr(origine, 'id', '') != 'fields':
                            continue
                        examines += 1
                        for cible in cibles:
                            champs[(cible, membre.targets[0].id)].add(module)
        self.assertGreaterEqual(
            examines, 20,
            "Presque aucun champ relevé sur un modèle étendu : le test ne "
            "vérifie rien.")

        doubles = {cle: mods for cle, mods in champs.items() if len(mods) > 1}
        self.assertFalse(
            doubles,
            "Un même champ est déclaré par deux modules sur le même modèle : "
            "la seconde définition remplace la première, en silence.\n%s"
            % "\n".join("  %s.%s : %s" % (modele, champ, ", ".join(sorted(mods)))
                        for (modele, champ), mods in sorted(doubles.items())))
