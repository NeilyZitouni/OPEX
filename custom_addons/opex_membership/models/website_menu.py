"""Réalignement des copies par site des entrées de menu que nous déclarons.

LE DÉFAUT QUE CE FICHIER CORRIGE, ET IL ÉTAIT INVISIBLE

`website.menu` porte **deux** enregistrements pour chaque entrée : le modèle
par défaut (`website_id = False`, celui qui porte notre xmlid) et **une copie
par site** (`website_id = 1`, sans xmlid), instanciée à la création du site.
C'est la copie qui est servie au visiteur ; le modèle par défaut ne sert qu'à
peupler les sites suivants.

L'URL de « Devenir membre » avait été corrigée partout — dans le fichier de
données, et par le `<function>` qui contourne le `noupdate`. Mesuré ensuite :

    id=10   /my/membership/new                        <- le modèle, corrigé
    id=9    /web/signup?redirect=/my/membership/new   <- le site 1, oublié

Autrement dit **le site public affichait encore le lien mort**, alors que le
source, le xmlid et le test qui les lit disaient tous que c'était réglé. La
correction n'avait jamais atteint la page qu'on regarde.

C'est le même mécanisme que le `noupdate` du fichier de données, d'un cran plus
loin : le drapeau protège l'enregistrement porteur du xmlid, et personne ne
protège ses copies. Un `<function>` qui ne cite que le xmlid ne suffit donc pas
pour ce modèle-là.

⚠ CE QUE CE RÉALIGNEMENT ASSUME

Il écrase une URL qu'un administrateur aurait délibérément changée sur un site,
et c'est voulu : la règle 24 du projet dit **un libellé, une URL**. Deux
chemins sous un même libellé produisent un « parfois » — le même geste, deux
comportements — et c'est ce qui a coûté le plus long diagnostic du projet.

Le reste de ce qu'un administrateur peut changer n'est pas touché : le libellé,
l'ordre, la suppression de l'entrée. C'est ce que le `noupdate` du fichier de
données protège, et il continue de le faire.
"""

from odoo import api, models


class WebsiteMenu(models.Model):
    _inherit = 'website.menu'

    @api.model
    def _opex_realign_website_copies(self):
        """Aligne les copies par site sur l'URL déclarée par nos fichiers.

        Appelée par un `<function>` **hors** du bloc `noupdate`, donc à chaque
        `-u`. Le fichier de données est la référence ; l'écran n'en est que la
        vue, et les copies par site n'en sont qu'une vue de plus.

        Une copie se reconnaît à ce qu'elle porte le libellé d'une de nos
        entrées **sans avoir de xmlid** : Odoo ne nomme pas les copies qu'il
        fabrique. Le relevé part donc de nos entrées déclarées, jamais d'une
        liste d'URL écrite ici — une seconde liste divergerait de la première
        au premier ajustement, et c'est toujours la copie périmée qu'on lit.
        """
        donnees = self.env['ir.model.data'].sudo().search([
            ('model', '=', 'website.menu'), ('module', '=', 'opex_membership'),
        ])
        declarees = self.sudo().browse(donnees.mapped('res_id')).exists()
        if not declarees:
            return 0

        nommees = set(declarees.ids)
        realignees = 0
        for menu in declarees:
            libelle = (menu.name or '').strip()
            if not libelle or not menu.url:
                continue
            copies = self.sudo().search([('name', '=', libelle)]).filtered(
                lambda copie: copie.id not in nommees and copie.url != menu.url)
            if copies:
                copies.write({'url': menu.url})
                realignees += len(copies)
        return realignees
