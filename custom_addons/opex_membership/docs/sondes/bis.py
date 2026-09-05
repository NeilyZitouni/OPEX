# -*- coding: utf-8 -*-
import ast, glob, os, re
from collections import defaultdict

RACINE = r"C:\Users\User\Desktop\stageDeltaLog\custom_addons"
MODULES = ('opex_workflow', 'opex_membership', 'opex_innovation',
           'opex_intervenants', 'opex_crowdfunding', 'opex_ai_core')

print("=" * 100)
print("B (refait par AST). MEME URL DECLAREE PAR DEUX METHODES")
print("=" * 100)
urls = defaultdict(list)
for module in MODULES:
    for chemin in glob.glob(os.path.join(RACINE, module, 'controllers', '*.py')):
        arbre = ast.parse(open(chemin, encoding='utf-8').read())
        for n in ast.walk(arbre):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for deco in n.decorator_list:
                if not isinstance(deco, ast.Call):
                    continue
                if getattr(deco.func, 'attr', getattr(deco.func, 'id', '')) != 'route':
                    continue
                if not deco.args:
                    continue
                try:
                    valeur = ast.literal_eval(deco.args[0])
                except (ValueError, SyntaxError):
                    continue
                for u in ([valeur] if isinstance(valeur, str) else list(valeur)):
                    urls[u].append((module, os.path.basename(chemin), n.name))
n = 0
for u, lieux in sorted(urls.items()):
    if len(lieux) < 2:
        continue
    n += 1
    print("  %s" % u)
    for module, fichier, methode in lieux:
        print("      %-18s %-28s %s" % (module, fichier, methode))
print("  URL declarees plusieurs fois : %d   (sur %d routes)" % (n, len(urls)))

print()
print("=" * 100)
print("H. REGLE 6 DU PROJET - COMPTEURS /my ET placeholder_count")
print("   « un compteur renvoye sans noeud DOM tue tout le JS de l'accueil »")
print("   « un placeholder_count n'appartient qu'a UNE seule tuile »")
print("=" * 100)
compteurs, placeholders = defaultdict(set), defaultdict(set)
for module in MODULES:
    for chemin in glob.glob(os.path.join(RACINE, module, 'controllers', '*.py')):
        texte = open(chemin, encoding='utf-8').read()
        for cle in re.findall(r"counters\[['\"](\w+)['\"]\]\s*=", texte):
            compteurs[cle].add(module)
        for cle in re.findall(r"['\"](\w+_count)['\"]\s*(?:in counters|:)", texte):
            compteurs[cle].add(module)
    for chemin in glob.glob(os.path.join(RACINE, module, 'views', '*.xml')):
        texte = open(chemin, encoding='utf-8').read()
        for cle in re.findall(r'placeholder_count=["\']([^"\']+)["\']', texte):
            placeholders[cle].add("%s/%s" % (module, os.path.basename(chemin)))
print("  compteurs declares : %d | placeholder_count distincts : %d"
      % (len(compteurs), len(placeholders)))
print()
print("  H1. Un placeholder_count porte par PLUSIEURS tuiles :")
d = {k: v for k, v in placeholders.items() if len(v) > 1}
for cle, ou in sorted(d.items()):
    print("      %-28s %s" % (cle, ", ".join(sorted(ou))))
print("      total : %d" % len(d))
print()
print("  H2. Compteur renvoye SANS tuile correspondante (tue le JS de /my) :")
orphelins = sorted(set(compteurs) - set(placeholders))
for cle in orphelins:
    print("      %-28s renvoye par %s" % (cle, ", ".join(sorted(compteurs[cle]))))
print("      total : %d" % len(orphelins))
print()
print("  H3. Tuile SANS compteur correspondant :")
muettes = sorted(set(placeholders) - set(compteurs))
for cle in muettes:
    print("      %-28s declaree par %s" % (cle, ", ".join(sorted(placeholders[cle]))))
print("      total : %d" % len(muettes))
