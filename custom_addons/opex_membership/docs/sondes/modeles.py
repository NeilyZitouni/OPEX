# -*- coding: utf-8 -*-
"""FAMILLE A - surcharges de methode sur un modele partage entre modules.

L'analogue cote ORM du defaut `CustomerPortal` : deux modules qui heritent du
meme modele et nomment une methode pareil. Odoo fusionne, le dernier charge
gagne, et si l'un ne relaie pas `super()` la logique de l'autre disparait.
"""
import ast, glob, os
from collections import defaultdict

RACINE = r"C:\Users\User\Desktop\stageDeltaLog\custom_addons"
MODULES = sorted(d for d in os.listdir(RACINE)
                 if os.path.isdir(os.path.join(RACINE, d)) and d.startswith('opex'))

def _valeur(noeud):
    if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
        return [noeud.value]
    if isinstance(noeud, (ast.List, ast.Tuple)):
        return [e.value for e in noeud.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return []

def _relaie(methode):
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == methode.name
               and isinstance(n.func.value, ast.Call)
               and getattr(n.func.value.func, 'id', '') == 'super'
               for n in ast.walk(methode))

# {(modele, methode): [(module, fichier, classe, relaie_super)]}
porteurs = defaultdict(list)
champs = defaultdict(list)

for module in MODULES:
    for chemin in sorted(glob.glob(os.path.join(RACINE, module, 'models', '*.py'))):
        try:
            arbre = ast.parse(open(chemin, encoding='utf-8').read())
        except SyntaxError:
            continue
        for classe in [n for n in arbre.body if isinstance(n, ast.ClassDef)]:
            noms, herite = [], []
            for membre in classe.body:
                if isinstance(membre, ast.Assign) and len(membre.targets) == 1 \
                        and isinstance(membre.targets[0], ast.Name):
                    if membre.targets[0].id == '_name':
                        noms = _valeur(membre.value)
                    elif membre.targets[0].id == '_inherit':
                        herite = _valeur(membre.value)
            # Un modele « etendu » : _inherit sans _name, ou _name == _inherit.
            cibles = [m for m in herite if not noms or m in noms]
            if not cibles:
                continue
            for membre in classe.body:
                ou = (module, os.path.basename(chemin), classe.name)
                if isinstance(membre, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for cible in cibles:
                        porteurs[(cible, membre.name)].append(ou + (_relaie(membre),))
                elif isinstance(membre, ast.Assign) and len(membre.targets) == 1 \
                        and isinstance(membre.targets[0], ast.Name) \
                        and isinstance(membre.value, ast.Call) \
                        and getattr(getattr(membre.value.func, 'value', None), 'id', '') == 'fields':
                    for cible in cibles:
                        champs[(cible, membre.targets[0].id)].append(ou)

print("Modules balayes :", ", ".join(MODULES))
print()
print("=" * 100)
print("A1. MEMES METHODES SUR UN MODELE PARTAGE, DEPUIS PLUSIEURS MODULES")
print("=" * 100)
partages = {k: v for k, v in porteurs.items()
            if len({m for m, _f, _c, _s in v}) > 1}
if not partages:
    print("  aucun")
for (modele, methode), lieux in sorted(partages.items()):
    muets = [l for l in lieux if not l[3]]
    drapeau = "  <-- %d SANS super()" % len(muets) if muets else ""
    print("\n  %s.%s%s" % (modele, methode, drapeau))
    for module, fichier, classe, relaie in sorted(lieux):
        print("      %-18s %-32s %-30s %s"
              % (module, fichier, classe, "super()" if relaie else "PAS de super()"))

print()
print("=" * 100)
print("A2. MEMES NOMS DE CHAMP SUR UN MODELE PARTAGE, DEPUIS PLUSIEURS MODULES")
print("=" * 100)
doubles = {k: v for k, v in champs.items() if len({m for m, _f, _c in v}) > 1}
if not doubles:
    print("  aucun")
for (modele, champ), lieux in sorted(doubles.items()):
    print("  %s.%s : %s" % (modele, champ, ", ".join(
        "%s/%s" % (m, c) for m, _f, c in sorted(lieux))))
