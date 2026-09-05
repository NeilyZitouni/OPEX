"""Le contrat de `/my/counters`, tenu par les quatre modules à la fois.

LA RÈGLE 6 DU PROJET, EXÉCUTÉE

> Un compteur renvoyé sans nœud DOM correspondant tue tout le JavaScript de
> l'accueil, pour tous les utilisateurs. `placeholder_count` dans le gabarit
> **et** `if 'x_count' in counters` dans le controller — les deux, ou aucun.
> Un `placeholder_count` n'appartient qu'à **une seule** tuile.

POURQUOI CELLE-LÀ MÉRITE UN TEST GÉNÉRIQUE

Le rayon est total et il ne s'arrête pas au module fautif. `/my` charge ses
compteurs en une requête ; une clé sans nœud fait lever le script, et **toutes**
les tuiles restent vides — celles des trois autres modules comprises. Le module
qui casse n'est pas celui qui montre le symptôme.

Quatre modules greffent aujourd'hui vingt vues sur `portal.portal_my_home`.
C'est la surface la plus partagée du portail, et le contrat y était tenu par la
seule convention : treize compteurs, treize tuiles, treize gardes, alignés à la
main depuis quatre modules qui ne se connaissent pas.

Ce test est donc écrit sur un état **sain**. C'est le bon moment : il verrouille
une symétrie correcte au lieu de documenter un désordre.

⚠ LE PIÈGE DU RELEVÉ, PAYÉ EN L'ÉCRIVANT

Chercher les clés en `_count` dans tout un contrôleur ramasse n'importe quel
dictionnaire. `member_count` et `category_count` sont les valeurs d'une page
publique `/cluster` et n'ont rien à voir avec la cloche. Le relevé se borne
donc à ce qui touche **`counters`** — le nom du dictionnaire que `/my` remplit.
"""

import glob
import os
import re
from collections import defaultdict

from odoo.tests.common import TransactionCase, tagged

#: Les modules qui posent une tuile sur l'accueil du portail.
MODULES = ('opex_membership', 'opex_innovation', 'opex_intervenants',
           'opex_crowdfunding')

#: Ce que le controller **écrit** dans le dictionnaire que `/my` reçoit.
#:
#: L'affectation sur `values`, et elle seule. C'est la forme qu'emploient les
#: treize compteurs, et s'y borner écarte le faux positif qui a fait échouer
#: la première version : un littéral `{'member_count': …}` construit les
#: valeurs d'une page publique `/cluster` et n'a rien à voir avec l'accueil du
#: portail. Un relevé qui ramasse toute clé finissant par `_count` signale des
#: compteurs qui n'en sont pas.
ECRITURE = (
    re.compile(r"values\[['\"](\w+_count)['\"]\]\s*="),
)

#: La garde qu'impose la règle 6 : ne rien renvoyer qui n'ait été demandé.
GARDE = re.compile(r"['\"](\w+_count)['\"]\s+in\s+counters")

#: Le nœud DOM, posé par la tuile. `t-set`, pas un attribut — c'est ainsi que
#: `portal.portal_my_home` le lit.
TUILE = re.compile(r't-set="placeholder_count"\s+t-value="\'(\w+)\'"')


def racine_addons():
    ici = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(ici))


def _sans_prose(source):
    """Le code seul : ni docstrings, ni commentaires (règle 15).

    Un fichier qui **explique** le contrat le cite forcément. Sans ce
    nettoyage, le relevé compterait des compteurs qui n'existent que dans une
    phrase, et la correction de moindre effort serait de supprimer
    l'explication.
    """
    source = re.sub(r'("""|\'\'\')(?:.|\n)*?\1', '', source)
    return re.sub(r'#[^\n]*', '', source)


def relever(modules):
    """(compteurs écrits, gardes, tuiles), chacun {clé: {où}}."""
    racine = racine_addons()
    ecrits, gardes, tuiles = (defaultdict(set) for _ in range(3))
    for module in modules:
        for chemin in glob.glob(
                os.path.join(racine, module, 'controllers', '*.py')):
            ou = "%s/%s" % (module, os.path.basename(chemin))
            code = _sans_prose(open(chemin, encoding='utf-8').read())
            for motif in ECRITURE:
                for cle in motif.findall(code):
                    ecrits[cle].add(ou)
            for cle in GARDE.findall(code):
                gardes[cle].add(ou)
        for chemin in glob.glob(os.path.join(racine, module, 'views', '*.xml')):
            ou = "%s/%s" % (module, os.path.basename(chemin))
            contenu = open(chemin, encoding='utf-8').read()
            contenu = re.sub(r'<!--(?:.|\n)*?-->', '', contenu)
            for cle in TUILE.findall(contenu):
                tuiles[cle].add(ou)
    return ecrits, gardes, tuiles


@tagged('post_install', '-at_install')
class TestPortalCounters(TransactionCase):

    def setUp(self):
        super().setUp()
        installes = self.env['ir.module.module'].sudo().search([
            ('name', 'in', list(MODULES)), ('state', '=', 'installed'),
        ]).mapped('name')
        self.assertGreaterEqual(
            len(installes), 3,
            "Presque aucun module du portail n'est installé : le relevé ne "
            "compare presque rien.")
        self.ecrits, self.gardes, self.tuiles = relever(tuple(installes))
        self.assertGreaterEqual(
            len(self.ecrits), 8,
            "Le relevé ne trouve presque aucun compteur : les motifs de "
            "lecture sont probablement faux, et les trois assertions qui "
            "suivent passeraient au vert sans rien vérifier.")

    def test_no_placeholder_is_claimed_by_two_tiles(self):
        """« Un `placeholder_count` n'appartient qu'à une seule tuile. »

        Le script remplit le premier nœud portant l'attribut. La seconde
        tuile reste vide — sans erreur, et sur un écran où l'absence de
        chiffre ressemble à « zéro ».
        """
        doubles = {
            cle: ou for cle, ou in self.tuiles.items() if len(ou) > 1}
        self.assertFalse(
            doubles,
            "Deux tuiles se partagent un compteur : l'une restera vide.\n%s"
            % "\n".join("  %-32s %s" % (cle, ", ".join(sorted(ou)))
                        for cle, ou in sorted(doubles.items())))

    def test_no_counter_is_returned_without_its_tile(self):
        """Le cas qui casse l'accueil de TOUT LE MONDE.

        C'est la moitié de la règle 6 dont le coût ne se voit pas sur le
        module fautif : une clé sans nœud fait lever le script de `/my`, et
        les tuiles des trois autres modules restent vides avec.
        """
        orphelins = {
            cle: ou for cle, ou in self.ecrits.items() if cle not in self.tuiles}
        self.assertFalse(
            orphelins,
            "Des compteurs sont renvoyés sans nœud DOM correspondant : le "
            "JavaScript de `/my` lève, et plus aucune tuile ne s'affiche — "
            "y compris celles des autres modules.\n%s"
            % "\n".join("  %-32s écrit par %s" % (cle, ", ".join(sorted(ou)))
                        for cle, ou in sorted(orphelins.items())))

    def test_no_tile_waits_for_a_counter_nobody_returns(self):
        """L'autre moitié, et elle est silencieuse.

        Une tuile dont personne ne renvoie la clé affiche un compteur vide.
        Rien ne lève : l'utilisateur lit une absence là où il devrait lire un
        chiffre, et personne ne s'en aperçoit.
        """
        muettes = {
            cle: ou for cle, ou in self.tuiles.items() if cle not in self.ecrits}
        self.assertFalse(
            muettes,
            "Des tuiles attendent un compteur que nul ne renvoie : elles "
            "afficheront un vide qui se lit comme un zéro.\n%s"
            % "\n".join("  %-32s tuile de %s" % (cle, ", ".join(sorted(ou)))
                        for cle, ou in sorted(muettes.items())))

    def test_every_counter_is_guarded_by_the_in_counters_test(self):
        """« Les deux, ou aucun. »

        Renvoyer une clé qui n'a pas été demandée est le défaut d'origine.
        La garde `if 'x_count' in counters` est ce qui l'empêche, et elle
        n'existe que par convention dans quatre fichiers indépendants.
        """
        sans = {
            cle: ou for cle, ou in self.ecrits.items() if cle not in self.gardes}
        self.assertFalse(
            sans,
            "Des compteurs sont écrits sans la garde « in counters » : ils "
            "partiront même quand `/my` ne les demande pas.\n%s"
            % "\n".join("  %-32s %s" % (cle, ", ".join(sorted(ou)))
                        for cle, ou in sorted(sans.items())))
