"""Contrôles de dépôt de fichier, partagés par les écrans du module.

POURQUOI CE FICHIER EXISTE

`MissionRequestPortal` (Extension 2) et `MissionApplicationPortal`
(Extension 5) sont **deux feuilles du même arbre `CustomerPortal`**. Elles
déclaraient toutes deux `_INTERVENANTS_BLOCKED_EXTENSIONS` et
`_INTERVENANTS_MAX_UPLOAD`, avec les mêmes valeurs.

C'était sans conséquence — les valeurs étaient identiques — et c'est
exactement pour cela que c'était dangereux : le jour où l'une des deux passe
la limite à 20 Mo, **les deux écrans changent**, ou aucun, selon la MRO. Sans
erreur, sans avertissement, et sans qu'aucun test ne le voie.

Le relevé qui l'a trouvé est reproductible :

    vus = {}
    for classe in (MissionRequestPortal, ExpertCapitalPortal,
                   MissionApplicationPortal, MissionPublicPortal):
        for attribut in vars(classe):
            vus.setdefault(attribut, []).append(classe.__name__)
    {k: v for k, v in vus.items() if len(v) > 1}

Des constantes de **module** n'appartiennent à aucune classe : elles ne
peuvent donc pas s'écraser. Et le contrôle vit désormais en un seul endroit,
ce qui était de toute façon le bon découpage.
"""

from odoo import _

#: Extensions refusées au dépôt. Un HTML ou un SVG rendu en ligne
#: s'exécuterait dans la session de celui qui l'ouvre.
BLOCKED_EXTENSIONS = (
    '.html', '.htm', '.svg', '.xhtml', '.js', '.exe', '.bat', '.sh')

#: 10 Mo. Au-delà, c'est une data room, pas une pièce jointe.
MAX_UPLOAD = 10 * 1024 * 1024


def read_upload(upload):
    """Lit un fichier déposé et le refuse s'il ne convient pas.

    Renvoie `(contenu, erreur)` : l'un des deux est toujours `None`. Le message
    est destiné à la page — un dépôt refusé se dit, il ne lève pas.
    """
    if not upload or not upload.filename:
        return None, _("Choisissez un fichier.")
    if upload.filename.lower().endswith(BLOCKED_EXTENSIONS):
        return None, _(
            "Ce type de fichier n'est pas accepté. Déposez un PDF, une image "
            "ou un document bureautique.")
    content = upload.read()
    if not content:
        return None, _("Le fichier est vide.")
    if len(content) > MAX_UPLOAD:
        return None, _("Le fichier dépasse 10 Mo.")
    return content, None
