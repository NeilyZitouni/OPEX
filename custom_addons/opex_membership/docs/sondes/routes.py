# -*- coding: utf-8 -*-
"""FAMILLES B, E, G - routes doublees, t-call ambigus, vues greffees au meme endroit."""
import glob, os, re
from collections import defaultdict

RACINE = r"C:\Users\User\Desktop\stageDeltaLog\custom_addons"
MODULES = ('opex_workflow', 'opex_membership', 'opex_innovation',
           'opex_intervenants', 'opex_crowdfunding', 'opex_ai_core')

print("=" * 100)
print("B. MEME URL DECLAREE PAR DEUX METHODES DIFFERENTES")
print("   (Odoo n'en garde qu'une ; ni le test de collision de NOMS ni celui")
print("    des liens morts ne le voient - les deux noms different, l'URL resout)")
print("=" * 100)
rmap = env['ir.http'].routing_map()
# Un endpoint par regle : si deux methodes declarent la meme URL, une seule
# survit. On compare donc les DECLARATIONS du source a ce qui a survecu.
declarees = defaultdict(list)
for module in MODULES:
    for chemin in glob.glob(os.path.join(RACINE, module, 'controllers', '*.py')):
        source = open(chemin, encoding='utf-8').read()
        for bloc, methode in re.findall(
                r'@http\.route\(\s*(\[[^\]]*\]|[\'"][^\'"]*[\'"])'
                r'.*?\n\s*def\s+(\w+)', source, re.S):
            for url in re.findall(r'[\'"](/[^\'"]*)[\'"]', bloc):
                declarees[url].append(
                    (module, os.path.basename(chemin), methode))

vivants = {}
for r in rmap.iter_rules():
    f = getattr(r.endpoint, 'func', r.endpoint)
    vivants[r.rule] = (getattr(f, '__module__', '?').split('.')[-1],
                       getattr(f, '__name__', '?'))

n = 0
for url, lieux in sorted(declarees.items()):
    if len({(m, meth) for m, _f, meth in lieux}) < 2:
        continue
    n += 1
    gagnant = vivants.get(url, ("?", "AUCUNE - route absente"))
    print("\n  %s" % url)
    for module, fichier, methode in sorted(lieux):
        marque = "  <== SERVIE" if methode == gagnant[1] else "      perdue"
        print("      %-18s %-30s %-38s%s" % (module, fichier, methode, marque))
print("\n  URL declarees plusieurs fois : %d" % n)

print()
print("=" * 100)
print("E. t-call SANS PREFIXE DE MODULE")
print("   (le nom est resolu par cle ; deux modules qui nomment pareil")
print("    rendent la resolution dependante de l'ordre)")
print("=" * 100)
appels = defaultdict(set)
cles = defaultdict(set)
for module in MODULES:
    for chemin in glob.glob(os.path.join(RACINE, module, 'views', '*.xml')) + \
                  glob.glob(os.path.join(RACINE, module, 'data', '*.xml')):
        texte = open(chemin, encoding='utf-8').read()
        for nom in re.findall(r't-call="([^"{}]+)"', texte):
            if '.' not in nom:
                appels[nom].add("%s/%s" % (module, os.path.basename(chemin)))
        for ident in re.findall(r'<template\s+id="([^"]+)"', texte):
            cles[ident].add(module)
for nom, ou in sorted(appels.items()):
    porteurs = cles.get(nom, set())
    alerte = "  <-- defini dans %d modules" % len(porteurs) if len(porteurs) > 1 else ""
    print("  %-38s appele par %-34s defini par %s%s"
          % (nom, ", ".join(sorted(ou))[:33], ", ".join(sorted(porteurs)) or "?", alerte))
print("  t-call non prefixes : %d" % len(appels))
print()
print("  Gabarits homonymes entre modules (meme suffixe d'identifiant) :")
h = [(k, v) for k, v in sorted(cles.items()) if len(v) > 1]
for ident, mods in h:
    print("      %-38s %s" % (ident, ", ".join(sorted(mods))))
print("      total : %d" % len(h))

print()
print("=" * 100)
print("G. VUES GREFFEES SUR LE MEME PARENT PAR PLUSIEURS MODULES")
print("=" * 100)
V = env['ir.ui.view'].sudo().search([('inherit_id', '!=', False)])
D = env['ir.model.data'].sudo().search(
    [('model', '=', 'ir.ui.view'), ('res_id', 'in', V.ids)])
propr = {d.res_id: d.module for d in D}
parents = defaultdict(list)
for v in V:
    m = propr.get(v.id)
    if m in MODULES:
        parents[v.inherit_id].append((m, v))
n = 0
for parent, enfants in sorted(parents.items(), key=lambda x: x[0].name):
    mods = {m for m, _v in enfants}
    if len(mods) < 2:
        continue
    n += 1
    print("\n  parent « %s » (%s)" % (parent.name, parent.type))
    for m, v in sorted(enfants, key=lambda x: (x[0], x[1].priority)):
        print("      %-18s prio=%-4s %s" % (m, v.priority, v.name[:52]))
print("\n  parents greffes par plusieurs modules : %d" % n)
