"""Les prompts, en données versionnées plutôt qu'en chaînes dans le code.

Même principe que les définitions de workflow : ce qui se règle se configure,
ce qui s'exécute se code. Un prompt est un réglage - il s'ajuste après une
mauvaise extraction, souvent, et par quelqu'un qui ne relit pas le Python.

UNE DIFFERENCE AVEC LES WORKFLOWS, ET ELLE COMPTE

Les définitions de workflow vivent dans des blocs `noupdate="1"` parce
qu'elles portent un état d'exécution : le compteur d'une séquence, le drapeau
de publication, les instances en cours. Les rejouer à chaque mise à jour
casserait des dossiers vivants.

Un prompt ne porte aucun état. Le fichier de données **est** la référence, et
un `-u` doit le redéployer : c'est ce que veut dire « versionné ». D'où
l'absence de `noupdate` ici. Le corollaire est à connaître : une retouche
faite à l'écran est écrasée à la mise à jour suivante. C'est voulu - l'écran
sert à essayer, le fichier sert à décider.
"""

import logging
import re

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# Les variables attendues dans un corps de prompt, écrites `{nom}`. Repérées
# pour deux choses : lister ce qu'un appelant doit fournir, et refuser un
# rendu incomplet plutôt que d'envoyer `{cv_texte}` au modèle.
PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


class AiPrompt(models.Model):
    """Un prompt nommé, versionné dans les données.

    Aucun champ d'état : un prompt n'a pas d'avancement. Il a une version, qui
    est un numéro qu'on incrémente en le modifiant, et c'est autre chose.
    """

    _name = 'opex.ai.prompt'
    _description = "Prompt d'assistance IA"
    _order = 'code'

    code = fields.Char(
        string="Code", required=True, index=True,
        help="Ce que les appelants citent. Il ne change pas : c'est la seule "
             "chose du prompt qui soit du code.")
    name = fields.Char(string="Intitulé", required=True)
    active = fields.Boolean(string="Actif", default=True)

    body = fields.Text(
        string="Corps du prompt", required=True,
        help="Les variables s'écrivent entre accolades, par exemple "
             "{cv_texte}. Un rendu auquel il manque une variable est refusé "
             "plutôt qu'envoyé tel quel au modèle.")

    version = fields.Integer(
        string="Version", default=1,
        help="Incrémentée dans le fichier de données à chaque modification. "
             "Elle est journalisée avec l'appel : c'est ce qui permettra de "
             "savoir quelle formulation a produit quelle extraction.")

    description = fields.Text(
        string="À quoi il sert",
        help="Pour celui qui le retouchera dans six mois.")

    expected_keys = fields.Char(
        string="Clés attendues en réponse",
        help="Séparées par des virgules. Purement indicatif : le service ne "
             "valide pas la forme de la réponse, c'est l'appelant qui sait ce "
             "qu'il attend. Sert à documenter le contrat du prompt.")

    _code_uniq = models.Constraint(
        'unique(code)',
        "Deux prompts ne peuvent pas porter le même code.",
    )

    @api.depends('code', 'version')
    def _compute_display_name(self):
        for prompt in self:
            prompt.display_name = "%s (v%s)" % (prompt.code or '',
                                                prompt.version)

    @api.model
    def _for_code(self, code):
        """Le prompt actif portant ce code, ou un recordset vide.

        Ne lève pas sur un code inconnu : un prompt manquant est une panne de
        configuration, et la règle 1 du service dit qu'une panne ne bloque pas
        un parcours. L'appelant recevra None et l'utilisateur saisira à la
        main.
        """
        return self.sudo().search([('code', '=', code)], limit=1)

    def placeholders(self):
        """Les variables que ce prompt attend."""
        self.ensure_one()
        return sorted(set(PLACEHOLDER.findall(self.body or '')))

    def render(self, values=None):
        """Le corps, variables remplacées. None si l'une manque.

        Refuser plutôt que rendre partiellement : un prompt envoyé avec
        `{cv_texte}` en toutes lettres produit une réponse plausible et
        fausse, ce qui est le pire des deux mondes. Un rendu refusé, lui, se
        voit dans le journal.

        ⚠ **Substitution par expression régulière, et surtout pas
        `str.format()`.** Un prompt d'extraction contient toujours un exemple
        de JSON attendu - c'est même la seule façon fiable d'obtenir du JSON
        d'un modèle de langage. Or `'{"ok": true}'.format()` lève : Python y
        voit un champ de remplacement nommé `"ok": true`.

        Autrement dit, `str.format()` aurait cassé sur exactement les prompts
        que ce module existe pour porter. La substitution ci-dessous ne touche
        qu'aux `{nom_en_minuscules}` et laisse les accolades du JSON
        tranquilles.
        """
        self.ensure_one()
        values = values or {}
        missing = [name for name in self.placeholders() if name not in values]
        if missing:
            _logger.warning(
                "opex_ai: prompt « %s » non rendu, variables manquantes : %s",
                self.code, ", ".join(missing))
            return None
        return PLACEHOLDER.sub(
            lambda match: str(values[match.group(1)]), self.body or '')

    def action_preview(self):
        """Affiche le corps rendu avec des valeurs d'exemple.

        Utile avant d'enregistrer une retouche : on voit ce qui partira
        vraiment, y compris les variables oubliées.
        """
        self.ensure_one()
        sample = {name: "<%s>" % name for name in self.placeholders()}
        body = self.render(sample) or _(
            "Le prompt n'a pas pu être rendu : voir le log serveur.")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Aperçu de « %s »") % self.code,
                'message': body[:600],
                'type': 'info',
                'sticky': True,
            },
        }
