# -*- coding: utf-8 -*-
"""FAMILLES C, D, F - droits, regles d'enregistrement, groupes."""
from collections import defaultdict

MODULES = ('opex_workflow', 'opex_membership', 'opex_innovation',
           'opex_intervenants', 'opex_crowdfunding', 'opex_ai_core')

D = env['ir.model.data'].sudo()

def module_de(modele, ids):
    """{id: module} depuis ir.model.data."""
    lignes = D.search([('model', '=', modele), ('res_id', 'in', list(ids))])
    return {l.res_id: l.module for l in lignes}

print("=" * 100)
print("C. ir.model.access - MEME MODELE + MEME GROUPE, DEPUIS PLUSIEURS MODULES")
print("   (Odoo prend l'UNION des droits : la ligne la plus permissive gagne)")
print("=" * 100)
A = env['ir.model.access'].sudo().search([])
mod = module_de('ir.model.access', A.ids)
paires = defaultdict(list)
for a in A:
    m = mod.get(a.id)
    if m not in MODULES:
        continue
    paires[(a.model_id.model, a.group_id.id)].append((m, a))
conflits = 0
for (modele, _g), lignes in sorted(paires.items()):
    if len({m for m, _a in lignes}) < 2:
        continue
    perms = {(a.perm_read, a.perm_write, a.perm_create, a.perm_unlink)
             for _m, a in lignes}
    if len(perms) > 1:
        conflits += 1
        g = lignes[0][1].group_id
        print("\n  %s / groupe %s" % (modele, g.full_name or "(tous)"))
        for m, a in sorted(lignes, key=lambda x: x[0]):
            print("      %-18s r=%d w=%d c=%d u=%d   %s"
                  % (m, a.perm_read, a.perm_write, a.perm_create,
                     a.perm_unlink, a.name))
print("\n  conflits : %d" % conflits)

print()
print("=" * 100)
print("D. ir.rule - MEME MODELE, REGLES POSEES PAR PLUSIEURS MODULES")
print("   (dans un meme groupe les regles sont en OU : la plus large gagne)")
print("=" * 100)
R = env['ir.rule'].sudo().search([])
modr = module_de('ir.rule', R.ids)
parmod = defaultdict(list)
for r in R:
    m = modr.get(r.id)
    if m in MODULES:
        parmod[r.model_id.model].append((m, r))
n = 0
for modele, lignes in sorted(parmod.items()):
    if len({m for m, _r in lignes}) < 2:
        continue
    n += 1
    print("\n  %s" % modele)
    for m, r in sorted(lignes, key=lambda x: x[0]):
        groupes = ", ".join(r.groups.mapped('full_name')) or "GLOBALE (toutes identites)"
        print("      %-18s %-42s [%s]" % (m, r.name[:41], groupes[:46]))
print("\n  modeles concernes : %d" % n)

print()
print("=" * 100)
print("F. GROUPES - LIBELLES HOMONYMES")
print("=" * 100)
G = env['res.groups'].sudo().search([])
modg = module_de('res.groups', G.ids)
noms = defaultdict(list)
for g in G:
    m = modg.get(g.id)
    if m in MODULES:
        noms[g.name].append((m, g))
h = 0
for nom, lignes in sorted(noms.items()):
    if len(lignes) < 2:
        continue
    h += 1
    print("  « %s » : %s" % (nom, ", ".join("%s" % m for m, _g in sorted(lignes))))
print("  homonymes : %d" % h)
