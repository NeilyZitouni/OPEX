"""Toute URL de portail écrite quelque part doit correspondre à une route.

LE DÉFAUT QUE CE TEST GARDE

`/my/intervenant` portait un bouton « Mes candidatures » vers
`/my/candidatures`. Cette URL n'a jamais été déclarée par aucun
`@http.route` : l'espace de noms du module est `/my/missions/*` (règle 1).
Trois liens l'avaient oublié, dont **la branche candidat** de
`_application_notification_url()` — donc tout intervenant qui cliquait sur sa
propre notification de cloche tombait sur un 404.

CE QUI L'A LAISSÉ PASSER, ET C'EST LE POINT

Deux tests assertaient l'URL. Tous les deux ainsi :

    self.assertEqual(rendu, '/my/candidatures/%s' % application.id)

Les deux côtés de l'égalité étaient construits par le même `%`, donc faux de
la même façon, donc égaux. Le test écrit **pour** garder cette méthode — après
un premier 404 trouvé au navigateur — a figé l'URL fautive au lieu de la
signaler.

Comparer une chaîne à une chaîne ne peut pas dire si une route existe. Seule
la **carte des routes** le dit, et elle est construite par les `@http.route`,
pas par le test.

CE QUE CE TEST NE COUVRE PAS

Qu'une route existe ne veut pas dire que ce lecteur-là y a droit : c'est la
règle 22, et elle est gardée ailleurs, dossier par dossier. Ici on vérifie
seulement qu'aucun lien ne mène nulle part — ce qui, lui, ne dépend d'aucune
identité.

⚠ Une URL construite par une expression que la lecture statique ne sait pas
réduire est **comptée à part et annoncée**, jamais ignorée en silence. Un
balayage qui n'examine plus rien passe au vert (règle 15).
"""

import ast
import glob
import os
import re
from collections import defaultdict

from odoo.tests.common import TransactionCase, tagged

#: Les quatre modules du portail. `opex_crowdfunding` en fait partie : il est
#: isolé côté métier, pas côté URL.
MODULES = ('opex_membership', 'opex_innovation', 'opex_intervenants',
           'opex_crowdfunding')

#: Seuls les espaces que nous servons. `/web/…`, `/report/…` et les routes
#: natives d'Odoo ne sont pas de notre ressort.
PREFIXES = ('/my', '/staff')

#: Une chaîne qui ressemble à un chemin de portail, dans du XML ou du Python.
CANDIDATE = re.compile(r'["\'](/(?:my|staff)(?:/[^"\'\s]*)?)["\']')

#: Ce qu'une lecture statique sait réduire à un segment : `%s`, `%d`, les
#: convertisseurs de route `<int:x>`, et l'interpolation QWeb `#{…}` / `{{…}}`.
REDUCTIBLES = (
    (re.compile(r'%\((?:[a-z_]+)\)[sd]'), '1'),
    (re.compile(r'%[sd]'), '1'),
    (re.compile(r'<[^>]*int:[^>]*>'), '1'),
    (re.compile(r'<[^>]+>'), 'x'),
    (re.compile(r'#\{[^}]*\}'), '1'),
    (re.compile(r'\{\{[^}]*\}\}'), '1'),
)

#: Ce qui reste après réduction et qui trahit une expression : on ne peut rien
#: conclure, donc on le déclare au lieu de le laisser passer.
IRREDUCTIBLE = re.compile(r'[%<>{}$+]|\)\s*\+|\bstr\b')


def racine_addons():
    ici = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(ici))


def _reduire(url):
    """L'URL, ramenée à un chemin concret ; None si elle reste une expression.

    ⚠ Les interpolations sont réduites **avant** que l'ancre soit retirée.
    L'inverse coupait `t-attf-href="/my/missions/candidature/#{a.id}"` au `#`
    et rendait `/my/missions/candidature`, une URL que personne n'a écrite :
    le test signalait alors cinq liens morts qui n'existaient pas.
    """
    for motif, remplacement in REDUCTIBLES:
        url = motif.sub(remplacement, url)
    url = url.split('?')[0].split('#')[0]
    url = url.rstrip('/') or '/my'
    if IRREDUCTIBLE.search(url):
        return None
    return url


def _urls_du_python(chemin):
    """Les URL citées dans un fichier Python, **hors** déclarations de routes.

    Une chaîne posée dans un `@http.route([...])` *définit* l'espace de noms ;
    la confronter à lui-même ne prouverait rien. Tout le reste — les
    `redirect()`, les URL construites pour un gabarit ou pour la cloche — est
    un **lien**, et c'est ce qu'on vérifie.
    """
    with open(chemin, encoding='utf-8') as fichier:
        source = fichier.read()
    arbre = ast.parse(source)

    declarations = set()
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorateur in noeud.decorator_list:
            if not isinstance(decorateur, ast.Call):
                continue
            nom = getattr(decorateur.func, 'attr', getattr(decorateur.func, 'id', ''))
            if nom != 'route':
                continue
            declarations.update(
                id(n) for n in ast.walk(decorateur) if isinstance(n, ast.Constant))

    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Constant) or not isinstance(noeud.value, str):
            continue
        if id(noeud) in declarations:
            continue
        valeur = noeud.value
        if valeur.startswith(PREFIXES) and ' ' not in valeur:
            yield valeur, noeud.lineno


def _urls_du_xml(chemin):
    """Les URL citées dans un gabarit : `href`, `action`, `t-attf-*`."""
    with open(chemin, encoding='utf-8') as fichier:
        for numero, ligne in enumerate(fichier, start=1):
            for url in CANDIDATE.findall(ligne):
                yield url, numero


def relever(modules=MODULES):
    """{url réduite: {"module/fichier:ligne", …}} et la liste des irréductibles."""
    racine = racine_addons()
    cites, opaques = defaultdict(set), []
    for module in modules:
        fichiers = []
        for motif in ('views/*.xml', 'data/*.xml', 'models/*.py',
                      'controllers/*.py'):
            fichiers.extend(glob.glob(os.path.join(racine, module, motif)))
        for chemin in sorted(fichiers):
            lecteur = _urls_du_xml if chemin.endswith('.xml') else _urls_du_python
            for brute, ligne in lecteur(chemin):
                ou = "%s/%s:%s" % (module, os.path.basename(chemin), ligne)
                reduite = _reduire(brute)
                if reduite is None:
                    opaques.append((brute, ou))
                else:
                    cites[reduite].add(ou)
    return cites, opaques


@tagged('post_install', '-at_install')
class TestPortalLinks(TransactionCase):

    def _modules_installes(self):
        """Les modules du portail présents dans **cette** base.

        `opex_crowdfunding` est isolé par construction et vit sur sa propre
        base de test : ses routes ne sont pas dans ce routing map, et ses
        liens y paraîtraient tous morts. Un test qui compare des fichiers à
        une carte doit se borner à ce que la carte contient.
        """
        installes = self.env['ir.module.module'].sudo().search([
            ('name', 'in', list(MODULES)), ('state', '=', 'installed'),
        ]).mapped('name')
        self.assertGreaterEqual(
            len(installes), 3,
            "Presque aucun module du portail n'est installé : le relevé ne "
            "compare presque rien.")
        return tuple(installes)

    def _motifs_du_routing_map(self):
        """Chaque règle, traduite en expression régulière sur un chemin concret."""
        motifs = []
        for regle in self.env['ir.http'].routing_map().iter_rules():
            brut = regle.rule
            gabarit = re.sub(r'<[^>]*int:[^>]*>', '\x00', brut)
            gabarit = re.sub(r'<[^>]+>', '\x01', gabarit)
            gabarit = re.escape(gabarit)
            gabarit = gabarit.replace('\x00', r'\d+').replace('\x01', r'[^/]+')
            motifs.append((re.compile(gabarit + r'\Z'), brut))
        return motifs

    def test_every_portal_url_written_anywhere_matches_a_route(self):
        """Le balayage des quatre modules, confronté à la carte des routes.

        Un lien qui ne correspond à aucune règle rend un 404. Ce n'est pas une
        dégradation d'affichage : c'est un écran qui n'existe pas, atteint
        depuis un bouton qui prétend le contraire.
        """
        cites, opaques = relever(self._modules_installes())
        self.assertGreaterEqual(
            len(cites), 50,
            "Le relevé ne trouve presque aucune URL : les chemins de lecture "
            "sont probablement faux, et ce test passerait au vert sans rien "
            "vérifier.")

        motifs = self._motifs_du_routing_map()
        self.assertGreaterEqual(
            len(motifs), 100,
            "Le routing map est presque vide : la comparaison ne prouverait "
            "rien.")

        morts = {
            url: ou for url, ou in cites.items()
            if not any(motif.match(url) for motif, _brut in motifs)
        }
        self.assertFalse(
            morts,
            "Des liens de portail ne correspondent à aucune route : "
            "l'utilisateur qui clique obtient un 404.\n%s" % "\n".join(
                "  %-38s écrit dans %s" % (url, ", ".join(sorted(ou)))
                for url, ou in sorted(morts.items())))

        # Les URL que la lecture statique ne sait pas réduire ne sont pas
        # vérifiables ici. Elles sont déclarées : une liste qui gonfle
        # signifierait que le balayage a cessé de couvrir quoi que ce soit.
        self.assertLessEqual(
            len(opaques), 12,
            "Trop d'URL construites par expression échappent au relevé — il "
            "ne garde plus grand-chose :\n%s" % "\n".join(
                "  %s (%s)" % (url, ou) for url, ou in sorted(opaques)))

    def test_no_unqualified_t_call_can_resolve_to_another_module(self):
        """Un `t-call` sans préfixe de module se résout par clé.

        Six identifiants de gabarits sont homonymes entre nos modules —
        `portal_my_projects`, `staff_matching`, `staff_dashboard` et trois
        autres. Ils cohabitent sans risque **parce que** tous les appels sont
        qualifiés : `t-call="opex_innovation.portal_my_projects"`.

        Le jour où l'un ne l'est pas, le gabarit rendu dépend de l'ordre de
        résolution. C'est la règle 1 transposée à QWeb, et le symptôme serait
        le même : la bonne page, sauf parfois.
        """
        racine = racine_addons()
        appels, examines = defaultdict(set), 0
        for module in MODULES:
            for motif in ('views/*.xml', 'data/*.xml'):
                for chemin in glob.glob(os.path.join(racine, module, motif)):
                    contenu = open(chemin, encoding='utf-8').read()
                    contenu = re.sub(r'<!--(?:.|\n)*?-->', '', contenu)
                    for nom in re.findall(r't-call="([^"{}$]+)"', contenu):
                        examines += 1
                        if '.' not in nom:
                            appels[nom].add(
                                "%s/%s" % (module, os.path.basename(chemin)))
        self.assertGreaterEqual(
            examines, 20,
            "Presque aucun `t-call` relevé : le balayage ne vérifie rien.")
        self.assertFalse(
            appels,
            "Des `t-call` ne nomment pas leur module. Six identifiants sont "
            "homonymes entre nos modules : la résolution deviendrait "
            "dépendante de l'ordre de chargement.\n%s" % "\n".join(
                "  %-38s dans %s" % (nom, ", ".join(sorted(ou)))
                for nom, ou in sorted(appels.items())))

    def test_one_label_never_carries_two_urls_in_the_database(self):
        """La règle 24, lue **en base** et non dans les fichiers.

        « Devenir membre » existait à quatre endroits sous deux URL : selon
        l'écran d'où l'on cliquait, un 404 ou un rebond silencieux. Le même
        geste, deux symptômes — de quoi croire à un défaut intermittent.

        Le test qui garde cette règle
        (`test_membership_deposit.test_every_entry_point_uses_the_same_url`)
        lit les **fichiers XML** et l'entrée porteuse d'un xmlid. C'est la
        moitié du problème : un `website.menu` créé à la main n'a pas de
        xmlid, ne figure dans aucun fichier, et lui échappe entièrement.
        Mesuré — une entrée oubliée pointait encore sur `/web/signup`, après
        que la correction eut été appliquée partout dans le source.

        ⚠ Le relevé se borne aux **libellés que nos modules déclarent**. Les
        menus du site sont éditables par l'utilisateur : un test qui rougirait
        sur une entrée que quelqu'un a créée pour ses propres besoins serait
        du bruit, et un test bruyant finit désactivé. Ce qui est vérifié est
        qu'un libellé **à nous** ne mène pas à deux endroits.
        """
        Menu = self.env['website.menu'].sudo()
        notres = self.env['ir.model.data'].sudo().search([
            ('model', '=', 'website.menu'), ('module', 'in', list(MODULES)),
        ])
        libelles = {
            m.name.strip() for m in Menu.browse(notres.mapped('res_id')).exists()
            if m.name and m.name.strip()
        }
        self.assertTrue(
            libelles,
            "Aucun menu déclaré par nos modules n'a été trouvé : le relevé "
            "ne compare rien.")

        fautifs = {}
        for libelle in sorted(libelles):
            portes = Menu.search([('name', '=', libelle)])
            urls = {(m.url or '').strip() for m in portes}
            if len(urls) > 1:
                fautifs[libelle] = sorted(
                    (m.url or '(vide)', m.id) for m in portes)

        self.assertFalse(
            fautifs,
            "Un libellé mène à deux URL. Selon l'entrée cliquée, "
            "l'utilisateur obtient deux comportements — c'est ce qui se lit "
            "comme un défaut intermittent :\n%s" % "\n".join(
                "  « %s »\n%s" % (libelle, "\n".join(
                    "      id=%-5s %s" % (ident, url) for url, ident in lignes))
                for libelle, lignes in sorted(fautifs.items())))

    def test_the_candidate_bell_link_leads_to_a_real_screen(self):
        """Le lien précis qui a mordu, nommé.

        Le test générique le couvre déjà. Celui-ci le nomme : le jour où la
        branche candidat repart sous `/my/candidatures/<id>`, le message dira
        de quel chemin il s'agit plutôt que de renvoyer à un relevé.

        Le lien est construit ici sans passer par le modèle, volontairement :
        ce qui est vérifié est **l'espace de noms**, et l'assertion doit tenir
        même si `_application_notification_url()` change de forme.
        """
        motifs = self._motifs_du_routing_map()

        def sert(url):
            return any(motif.match(url) for motif, _brut in motifs)

        self.assertTrue(
            sert('/my/missions/candidature/1'),
            "La route de la candidature a disparu : la notification du "
            "candidat ne mène plus nulle part.")
        self.assertFalse(
            sert('/my/candidatures/1'),
            "`/my/candidatures/<id>` est redevenue une route. Ce n'est pas "
            "l'espace de noms du module (règle 1) — et si elle existe "
            "désormais, ce test et les liens doivent être revus ensemble.")
