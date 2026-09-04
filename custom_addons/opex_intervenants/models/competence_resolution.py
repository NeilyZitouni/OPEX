"""Le rapprochement en deux temps - §8.

    1. correspondance exacte ou par synonyme, **sans appel IA**
    2. si l'étape 1 échoue, l'IA propose un rapprochement avec sa confiance

Ce qui reste non rapproché part en file d'arbitrage. Rien n'est écrit sur le
profil : l'IA-1 a posé le principe - l'extraction propose, l'humain décide -
et l'IA-2 ne le change pas, elle le rend exploitable.

POURQUOI L'ETAPE 1 EXISTE

Elle ne coûte rien, et elle traite la majorité des cas : les intitulés d'un CV
sont des libellés courants, déjà au catalogue. Les envoyer au fournisseur
serait payer pour retrouver ce qu'on sait déjà.

Elle a un second effet, moins évident et plus important : **le module reste
utile sans clé**. Un cluster qui n'active pas l'assistance IA garde le
rapprochement exact et la file d'arbitrage. C'est la règle 1 du service - une
panne ne bloque aucun parcours - vue depuis le métier.
"""

import json
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

MATCHING_PROMPT = 'competence_matching'

#: En deçà, la proposition de l'IA n'est pas présentée comme un rapprochement
#: mais comme une piste : la ligne part en arbitrage avec la suggestion
#: affichée à côté. Au-dessus, elle est proposée comme rapprochement - et
#: reste, dans les deux cas, soumise à la décision d'un humain.
#:
#: Le seuil est nommé ici parce qu'il se règlera à l'usage. Il ne décide de
#: rien tout seul : aucune valeur de confiance n'écrit quoi que ce soit.
SUGGESTION_THRESHOLD = 70


class CompetenceResolution(models.AbstractModel):
    """Le rapprochement d'un libellé vers le référentiel."""

    _name = 'opex.competence.resolution'
    _description = "Rapprochement des compétences extraites"

    @api.model
    def resolve_skills(self, skills, profile=None, document=None,
                       use_ai=True):
        """Rapproche une liste de compétences extraites. N'écrit aucun profil.

        Rend la même liste, chaque entrée enrichie de :

        - `competence_id` : l'identifiant du référentiel, ou False ;
        - `matched_on` : `referentiel`, `synonyme`, `ia`, ou False ;
        - `confiance_rapprochement` : 100 pour l'étape 1, la valeur rendue par
          l'IA pour l'étape 2, 0 sinon ;
        - `arbitrage_id` : la ligne de file, quand il y en a une.

        La seule écriture est la **file d'arbitrage**, et c'est voulu : une
        question posée doit survivre à la fermeture de l'écran. Le profil de
        l'expert, lui, n'est pas touché.

        `use_ai=False` court-circuite l'étape 2 - c'est ce que fait l'écran
        quand l'assistance n'est pas configurée, et ce que font les tests qui
        n'ont rien à dire sur l'IA.
        """
        Synonyme = self.env['opex.competence.synonyme']
        resolved = []

        for skill in skills or []:
            libelle = (skill or {}).get('libelle')
            if not libelle:
                continue

            entry = dict(skill)
            entry.update({
                'competence_id': False,
                'matched_on': False,
                'confiance_rapprochement': 0,
                'arbitrage_id': False,
            })

            # Étape 1 - gratuite.
            competence = Synonyme.resolve_label(libelle)
            if competence:
                entry.update({
                    'competence_id': competence.id,
                    'matched_on': self._matched_on(competence, libelle),
                    'confiance_rapprochement': 100,
                })
                resolved.append(entry)
                continue

            # Étape 2 - payante, et seulement si elle est activée.
            suggestion = self._suggest(libelle) if use_ai else None
            if suggestion and suggestion.get('competence_id'):
                entry.update({
                    'competence_id': suggestion['competence_id'],
                    'matched_on': 'ia',
                    'confiance_rapprochement': suggestion.get('confiance', 0),
                })

            # Rapprochée ou non, une compétence que l'étape 1 n'a pas reconnue
            # passe par la file : c'est là qu'un humain valide ce que la
            # machine a proposé, et le §8 ne laisse pas d'autre porte.
            #
            # Aucune confiance ne dispense de ce passage, et c'est la garde
            # qu'il faut connaître : « si l'IA écrit au catalogue, il diverge
            # en trois mois et le matching devient faux sans que rien ne le
            # signale ». Mesuré par régression volontaire - un raccourci à 95 %
            # fait rougir trois tests, dont un qui lit le source de ce fichier.
            arbitrage = self.env['opex.competence.arbitrage'].enqueue(
                libelle, profile=profile, document=document, skill=skill,
                suggestion=suggestion)
            entry['arbitrage_id'] = arbitrage.id if arbitrage else False
            resolved.append(entry)

        return resolved

    @api.model
    def _matched_on(self, competence, libelle):
        """Dit par quelle porte la correspondance est passée.

        Utile à l'écran - « reconnu au catalogue » et « reconnu par un
        synonyme » ne se lisent pas pareil - et utile pour mesurer : si la
        plupart des rapprochements passent par des synonymes, le catalogue est
        mal libellé, et c'est une information.
        """
        Synonyme = self.env['opex.competence.synonyme']
        exact = Synonyme._normalise(competence.name) == Synonyme._normalise(
            libelle)
        return 'referentiel' if exact else 'synonyme'

    @api.model
    def _suggest(self, libelle):
        """Demande un rapprochement à l'IA. Rend None si rien d'exploitable.

        Ne lève jamais et n'écrit rien : la règle 1 du service vaut jusqu'ici.
        Une clé absente, un quota, une réponse illisible - le libellé part
        simplement en arbitrage sans suggestion, ce qui est exactement l'état
        où il serait sans IA du tout.

        Le code rendu est **vérifié contre le catalogue**. Un modèle
        invente volontiers un code plausible ; l'accepter sur parole
        rattacherait une compétence à un identifiant qui n'existe pas, ou pire
        à un qui existe et ne correspond pas.
        """
        Synonyme = self.env['opex.competence.synonyme']
        catalogue = Synonyme.catalogue_for_prompt()
        if not catalogue:
            return None

        payload = self.env['opex.ai.bridge']._ai_call_prompt(
            MATCHING_PROMPT,
            values={
                'libelle': libelle,
                'catalogue': json.dumps(catalogue, ensure_ascii=False,
                                        indent=1),
            },
        )
        if not payload:
            return None

        code = str(payload.get('code') or '').strip()
        confiance = self._as_percent(payload.get('confiance'))
        motif = str(payload.get('motif') or '').strip()

        competence = self._competence_for_code(code) if code else None
        if code and not competence:
            # Le modèle a rendu un code absent du catalogue. On le journalise
            # plutôt que de l'ignorer : c'est le signe d'un prompt à revoir.
            _logger.info(
                "opex_intervenants: rapprochement ignoré, code « %s » absent "
                "du catalogue pour le libellé « %s ».", code, libelle)

        return {
            'competence_id': competence.id if competence else False,
            'confiance': confiance,
            'motif': motif,
        }

    @api.model
    def _competence_for_code(self, code):
        """La compétence portant ce code, si elle existe vraiment.

        Le catalogue envoyé au modèle utilise `code` quand il existe, et
        l'identifiant à défaut : la recherche fait les deux dans le même
        ordre.
        """
        Competence = self.env['opex.innovation.competence'].sudo()
        competence = Competence.search([('code', '=', code)], limit=1)
        if competence:
            return competence
        if code.isdigit():
            candidate = Competence.browse(int(code))
            return candidate if candidate.exists() else None
        return None

    @staticmethod
    def _as_percent(value):
        """Un entier de 0 à 100, ou 0.

        Un modèle rend « 0.85 », « 85 % » ou « élevée » selon l'humeur. Les
        deux premiers se rattrapent, le troisième vaut zéro - et zéro est la
        bonne valeur : une confiance qu'on ne sait pas lire n'est pas une
        confiance haute.
        """
        try:
            number = float(str(value).strip().rstrip('%').replace(',', '.'))
        except (TypeError, ValueError):
            return 0
        # « 0.85 » est une probabilité, pas un pourcentage.
        if 0 < number <= 1:
            number *= 100
        return max(0, min(100, int(round(number))))
