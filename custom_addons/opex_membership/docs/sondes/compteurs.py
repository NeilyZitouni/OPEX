# -*- coding: utf-8 -*-
"""FAMILLE H - le contrat de /my/counters (regle 6 du projet)."""
import glob, os, re
from collections import defaultdict

RACINE = r"C:\Users\User\Desktop\stageDeltaLog\custom_addons"
MODULES = ('opex_membership', 'opex_innovation', 'opex_intervenants',
           'opex_crowdfunding')

compteurs, gardes, tuiles = defaultdict(set), defaultdict(set), defaultdict(set)
for module in MODULES:
    for chemin in glob.glob(os.path.join(RACINE, module, 'controllers', '*.py')):
        texte = open(chemin, encoding='utf-8').read()
        ou = "%s/%s" % (module, os.path.basename(chemin))
        # Ce que le controller ECRIT dans le dictionnaire de /my.
        #
        # L'affectation sur `values`, et elle seule. Un motif plus large
        # ramasse `member_count` et `category_count`, qui sont les valeurs
        # d'une page publique /cluster et n'ont rien a voir avec l'accueil du
        # portail - deux faux positifs au premier essai.
        for cle in re.findall(r"values\[['\"](\w+_count)['\"]\]\s*=", texte):
            compteurs[cle].add(ou)
        # La garde « if 'x_count' in counters » qu'impose la regle 6.
        for cle in re.findall(r"['\"](\w+_count)['\"]\s+in\s+counters", texte):
            gardes[cle].add(ou)
    for chemin in glob.glob(os.path.join(RACINE, module, 'views', '*.xml')):
        texte = open(chemin, encoding='utf-8').read()
        ou = "%s/%s" % (module, os.path.basename(chemin))
        for cle in re.findall(
                r't-set="placeholder_count"\s+t-value="\'(\w+)\'"', texte):
            tuiles[cle].add(ou)

print("compteurs ecrits : %d | tuiles : %d | gardes 'in counters' : %d"
      % (len(compteurs), len(tuiles), len(gardes)))
print()
print("H1. Un placeholder_count porte par PLUSIEURS tuiles")
print("    (le JS ne remplit qu'un noeud : les autres restent vides)")
d = {k: v for k, v in tuiles.items() if len(v) > 1}
for cle, ou in sorted(d.items()):
    print("    %-32s %s" % (cle, ", ".join(sorted(ou))))
print("    total : %d" % len(d))
print()
print("H2. Compteur ECRIT sans tuile correspondante")
print("    (regle 6 : tue tout le JS de l'accueil, pour TOUS les utilisateurs)")
orph = sorted(set(compteurs) - set(tuiles))
for cle in orph:
    print("    %-32s ecrit par %s" % (cle, ", ".join(sorted(compteurs[cle]))))
print("    total : %d" % len(orph))
print()
print("H3. Tuile sans compteur ecrit")
muet = sorted(set(tuiles) - set(compteurs))
for cle in muet:
    print("    %-32s tuile de %s" % (cle, ", ".join(sorted(tuiles[cle]))))
print("    total : %d" % len(muet))
print()
print("H4. Compteur ecrit SANS la garde « in counters »")
sans = sorted(set(compteurs) - set(gardes))
for cle in sans:
    print("    %-32s %s" % (cle, ", ".join(sorted(compteurs[cle]))))
print("    total : %d" % len(sans))
