"""Le dépôt d'un CV - §6.

Il dépose le document, crée l'enregistrement `opex.expert.cv.source`, et rend
la main. **Il n'analyse rien.**

POURQUOI CET ECRAN NE FAIT PLUS L'ANALYSE

Il l'a faite, dans une première version synchrone : on déposait, on attendait,
on lisait le résultat. Un parsing prend dix à trente secondes. Pendant ce
temps le navigateur tourne, l'utilisateur recharge, et le second appel repart
pour trente secondes - facturé comme le premier.

Le dépôt marque donc « analyse en cours » et un `ir.cron` traite la file.
L'expert voit un état sur la fiche du CV, pas une roue qui tourne.

Il ne reste ici qu'un `TransientModel` : rien de durable n'y passe, le
document est immédiatement porté par `opex.expert.cv.source`.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ExpertCvWizard(models.TransientModel):
    _name = 'opex.expert.cv.wizard'
    _description = "Dépôt d'un CV pour analyse"

    profile_id = fields.Many2one(
        'opex.innovation.expert.profile',
        string="Profil expert",
        required=True,
        ondelete='cascade',
    )
    document = fields.Binary(string="Curriculum vitae", required=True)
    filename = fields.Char(string="Nom du fichier")

    ai_available = fields.Boolean(
        string="Assistance IA active",
        compute='_compute_ai_available',
        help="Le service est installé et une clé est configurée. Sans lui, le "
             "CV peut être déposé - il restera en file jusqu'à ce que "
             "l'assistance soit disponible.",
    )

    def _compute_ai_available(self):
        """La question posée au pont, jamais la lecture d'une clé.

        Le pont répond False aussi bien quand `opex_ai_core` n'est pas
        installé que quand aucune clé n'est configurée. De l'extérieur, les
        deux donnent le même résultat : pas d'analyse.
        """
        available = self.env['opex.ai.bridge']._ai_available()
        for wizard in self:
            wizard.ai_available = available

    def action_deposit(self):
        """Crée le CV en file et ouvre sa fiche. N'analyse pas.

        Le document est déposé même quand l'assistance n'est pas disponible :
        il attendra dans la file. Refuser le dépôt obligerait l'expert à
        revenir, et le CV est utile en lui-même - c'est la pièce qui fait foi
        quand une proposition est contestée.
        """
        self.ensure_one()
        if not self.document:
            raise UserError(_("Déposez un CV avant de lancer l'analyse."))

        source = self.env['opex.expert.cv.source'].sudo().create({
            'profile_id': self.profile_id.id,
            'document': self.document,
            'filename': self.filename or 'cv.pdf',
            'mimetype': self._guess_mimetype(),
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _("CV déposé"),
            'res_model': 'opex.expert.cv.source',
            'view_mode': 'form',
            'res_id': source.id,
        }

    def _guess_mimetype(self):
        """Le type du document, déduit de son nom.

        Gemini lit le PDF nativement, et c'est pour cela qu'on ne convertit
        pas en texte : la mise en page porte de l'information - un titre se
        distingue d'une ligne de corps par sa position et sa taille, pas par
        ses mots.

        Un nom sans extension connue est annoncé en PDF : c'est ce que
        déposent les experts dans l'immense majorité des cas, et se tromper
        coûte un appel raté, pas une panne.
        """
        self.ensure_one()
        name = (self.filename or '').lower()
        if name.endswith('.png'):
            return 'image/png'
        if name.endswith(('.jpg', '.jpeg')):
            return 'image/jpeg'
        if name.endswith('.txt'):
            return 'text/plain'
        return 'application/pdf'
