# -*- coding: utf-8 -*-
"""FAMILLES I, J, K - sequences, crons, sous-types, menus, assets."""
from collections import defaultdict

MODULES = ('opex_workflow', 'opex_membership', 'opex_innovation',
           'opex_intervenants', 'opex_crowdfunding', 'opex_ai_core')
D = env['ir.model.data'].sudo()

def par_module(modele, records):
    lignes = D.search([('model', '=', modele), ('res_id', 'in', records.ids)])
    return {l.res_id: l.module for l in lignes}

def collisions(modele, champ, libelle):
    R = env[modele].sudo().search([])
    mods = par_module(modele, R)
    groupes = defaultdict(list)
    for r in R:
        m = mods.get(r.id)
        if m in MODULES:
            groupes[r[champ]].append((m, r.display_name))
    d = {k: v for k, v in groupes.items() if len({m for m, _n in v}) > 1}
    print("  %-44s collisions : %d   (sur %d objets a nous)"
          % (libelle, len(d), sum(len(v) for v in groupes.values())))
    for cle, lignes in sorted(d.items()):
        print("      « %s » : %s" % (cle, ", ".join(
            "%s (%s)" % (m, n[:34]) for m, n in sorted(lignes))))

print("=" * 100)
print("I. IDENTIFIANTS FONCTIONNELS PARTAGES ENTRE MODULES")
print("=" * 100)
collisions('ir.sequence', 'code', "ir.sequence.code")
collisions('ir.cron', 'cron_name', "ir.cron.cron_name")
collisions('mail.message.subtype', 'name', "mail.message.subtype.name")
collisions('ir.actions.server', 'name', "ir.actions.server.name")

print()
print("=" * 100)
print("J. REGLE 24 DU PROJET - UN LIBELLE, UNE URL (menus du site)")
print("=" * 100)
M = env['website.menu'].sudo().search([])
mods = par_module('website.menu', M)
parlibelle = defaultdict(set)
for m in M:
    parlibelle[(m.name or '').strip()].add((m.url or '', mods.get(m.id) or '(base)'))
mauvais = {k: v for k, v in parlibelle.items() if len({u for u, _m in v}) > 1}
print("  menus : %d | libelles portant PLUSIEURS URL : %d" % (len(M), len(mauvais)))
for nom, paires in sorted(mauvais.items()):
    print("      « %s »" % nom)
    for url, module in sorted(paires):
        print("          %-42s %s" % (url, module))

print()
print("=" * 100)
print("K. ASSETS - MEME FICHIER DECLARE PAR PLUSIEURS MODULES")
print("=" * 100)
A = env['ir.asset'].sudo().search([])
mods = par_module('ir.asset', A)
parchemin = defaultdict(set)
for a in A:
    m = mods.get(a.id)
    if m in MODULES:
        parchemin[(a.bundle, a.path)].add(m)
d = {k: v for k, v in parchemin.items() if len(v) > 1}
print("  assets a nous : %d | doublons : %d"
      % (sum(1 for a in A if mods.get(a.id) in MODULES), len(d)))
for (bundle, chemin), ms in sorted(d.items()):
    print("      %-34s %-44s %s" % (bundle, chemin, ", ".join(sorted(ms))))
