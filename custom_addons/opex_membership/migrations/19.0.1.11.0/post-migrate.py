"""Rattache les événements déjà en base à l'agenda natif.

La synchronisation se déclenche à la création et à la modification : sans ce
passage, les événements saisis avant l'Extension 2 n'apparaîtraient dans
l'agenda qu'au jour où quelqu'un les rouvre pour les modifier.

Le rattrapage est idempotent — il ne prend que les événements sans lien — et
réutilise la méthode de synchronisation du modèle plutôt que de recopier ses
règles ici.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    events = env['opex.cluster.event'].search([('calendar_event_id', '=', False)])
    if not events:
        return

    events._sync_calendar_event()
    _logger.info(
        "OPEX Membership : %s événement(s) du cluster rattaché(s) à l'agenda natif.",
        len(events),
    )
