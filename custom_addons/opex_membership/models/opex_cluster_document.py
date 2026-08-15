from odoo import fields, models


class OpexClusterDocument(models.Model):
    """Document partagé du cluster (section 37 de la spécification UX).

    Bibliothèque unique, classée par dossier. Les comités et les assemblées y
    rattachent leurs pièces au lieu d'avoir chacun leur propre modèle de
    document : un compte rendu reste un document, quel que soit l'organe qui
    l'a produit — même principe que l'inscription commune aux événements et
    aux formations.
    """

    _name = 'opex.cluster.document'
    _description = "Document du cluster"
    _order = 'folder, name'

    name = fields.Char(string="Nom", required=True)
    folder = fields.Selection(
        [
            ('general_assembly', "Assemblées générales"),
            ('regulations', "Règlements"),
            ('charters', "Chartes"),
            ('trainings', "Formations"),
            ('cluster', "Documents du Cluster"),
        ],
        string="Dossier",
        required=True,
        default='cluster',
    )
    file = fields.Binary(string="Fichier", attachment=True)
    filename = fields.Char(string="Nom du fichier")
    version = fields.Char(string="Version")
    confidentiality = fields.Selection(
        [
            ('public', "Public"),
            ('members', "Membres"),
            ('committee', "Comité"),
        ],
        string="Confidentialité",
        required=True,
        default='members',
        help="Détermine qui peut consulter le document depuis le portail.",
    )

    # Niveaux qu'un membre du cluster peut consulter. Le niveau « Comité » en
    # est exclu : il est réservé au personnel interne.
    MEMBER_LEVELS = ('public', 'members')

    def _portal_domain(self, is_staff=False):
        """Documents consultables depuis le portail par cet utilisateur.

        Le personnel interne voit tout, y compris les pièces de comité ; un
        membre ne voit que le public et le réservé aux membres. La règle est
        rendue ici, une fois, plutôt que recopiée dans le gabarit — et une
        règle d'enregistrement la double côté base pour les comptes portail.
        """
        if is_staff:
            return []
        return [('confidentiality', 'in', list(self.MEMBER_LEVELS))]
