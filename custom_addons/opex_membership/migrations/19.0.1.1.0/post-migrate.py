"""Bascule les données existantes vers le modèle de l'Extension 8.

Trois déplacements de données, tous invisibles pour l'ORM et donc traités ici
explicitement :

1. `montant_cotisation` quitte la catégorie pour la sous-catégorie. Odoo ne
   supprime jamais une colonne devenue orpheline : l'ancienne valeur est encore
   lisible en SQL au moment où ce script tourne, c'est ce qui permet de ne rien
   perdre.
2. `opex_membership_file.category_id` et `res_partner.categorie_membre_id`,
   mis de côté par la pré-migration, deviennent des `subcategory_id` pointant
   vers un *autre* modèle : les identifiants sont retraduits, pas renommés.
3. `document_ids` passe d'un `Many2many('ir.attachment')` à un
   `One2many('opex.membership.document')`. Les fichiers déjà déposés sont
   réattachés aux nouvelles pièces, sans recopie des octets.

Toute catégorie préexistante sans sous-catégorie s'en voit créer une, de même
nom, qui reprend son barème. Les dossiers déjà instruits gardent ainsi le
montant sur lequel ils ont été facturés, et le produit de cotisation
(« Cotisation — <nom> ») continue de leur correspondre.

Les écritures passent par l'ORM dès qu'un champ calculé en dépend — c'est le
cas de `category_id`, related stocké vers la catégorie de la sous-catégorie,
qu'un simple UPDATE laisserait désynchronisé.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def _legacy_amounts(cr):
    """Barème encore stocké sur les catégories, avant suppression des colonnes."""
    cr.execute("""
        SELECT column_name FROM information_schema.columns
         WHERE table_name = 'opex_membership_category'
           AND column_name IN ('montant_cotisation', 'currency_id')
    """)
    available = {row[0] for row in cr.fetchall()}
    if 'montant_cotisation' not in available:
        return {}

    currency = 'currency_id' if 'currency_id' in available else 'NULL'
    cr.execute(
        "SELECT id, montant_cotisation, %s FROM opex_membership_category" % currency
    )
    return {
        row[0]: {'montant': row[1] or 0.0, 'currency_id': row[2]}
        for row in cr.fetchall()
    }


def _build_subcategory_mapping(env, cr):
    """Sous-catégorie cible pour chaque ancienne catégorie.

    Les catégories livrées par `data/membership_categories.xml` arrivent avec
    leurs sous-catégories : elles sont reprises telles quelles. Seules celles
    créées à la main avant l'Extension 8 reçoivent une sous-catégorie de
    reprise, portant leur nom et leur barème.
    """
    Subcategory = env['opex.membership.subcategory']
    amounts = _legacy_amounts(cr)
    mapping = {}

    for category in env['opex.membership.category'].search([]):
        existing = Subcategory.search([('category_id', '=', category.id)], limit=1)
        if existing:
            mapping[category.id] = existing.id
            continue

        legacy = amounts.get(category.id, {})
        values = {
            'name': category.name,
            'category_id': category.id,
            'montant_cotisation': legacy.get('montant', 0.0),
        }
        if legacy.get('currency_id'):
            values['currency_id'] = legacy['currency_id']
        mapping[category.id] = Subcategory.create(values).id
        _logger.info(
            "OPEX Membership : sous-catégorie de reprise « %s » créée "
            "(barème %s conservé).", category.name, legacy.get('montant', 0.0),
        )

    return mapping


def _remap(env, cr, model_name, table, legacy_column, mapping):
    """Retraduit une référence catégorie -> sous-catégorie sur un modèle."""
    cr.execute("""
        SELECT column_name FROM information_schema.columns
         WHERE table_name = %s AND column_name = %s
    """, (table, legacy_column))
    if not cr.fetchone():
        return

    cr.execute(
        'SELECT id, "%s" FROM "%s" WHERE "%s" IS NOT NULL'
        % (legacy_column, table, legacy_column)
    )
    rows = cr.fetchall()
    if not rows:
        return

    Model = env[model_name]
    for record_id, category_id in rows:
        subcategory_id = mapping.get(category_id)
        if not subcategory_id:
            _logger.warning(
                "OPEX Membership : %s#%s référence la catégorie %s, introuvable ; "
                "sous-catégorie laissée vide.", model_name, record_id, category_id,
            )
            continue
        Model.browse(record_id).subcategory_id = subcategory_id

    _logger.info(
        "OPEX Membership : %s enregistrement(s) %s rattaché(s) à une sous-catégorie.",
        len(rows), model_name,
    )


def _migrate_documents(env, cr):
    """Convertit les pièces jointes en `opex.membership.document`.

    Le type réel des pièces déjà déposées est inconnu — l'ancien formulaire ne
    le demandait pas — elles sont donc reprises en « Autre document ». Un
    dossier déjà actif n'en souffre pas ; un dossier encore en cours devra se
    voir ajouter ses pièces obligatoires avant d'être soumis.
    """
    cr.execute("SELECT to_regclass('ir_attachment_opex_membership_file_rel')")
    if not cr.fetchone()[0]:
        return

    cr.execute("""
        SELECT rel.opex_membership_file_id, rel.ir_attachment_id, att.name
          FROM ir_attachment_opex_membership_file_rel rel
          JOIN ir_attachment att ON att.id = rel.ir_attachment_id
          JOIN opex_membership_file f ON f.id = rel.opex_membership_file_id
    """)
    rows = cr.fetchall()

    for file_id, attachment_id, name in rows:
        # Insertion en SQL : le contenu binaire vit dans `ir_attachment`, pas
        # dans une colonne de la table, et la pièce doit exister avant qu'on
        # puisse y repointer la pièce jointe.
        cr.execute("""
            INSERT INTO opex_membership_document
                   (name, membership_file_id, document_type, is_required, filename,
                    date_depot, create_uid, write_uid, create_date, write_date)
            VALUES (%s, %s, 'autre', false, %s, now(), %s, %s, now(), now())
         RETURNING id
        """, (name, file_id, name, SUPERUSER_ID, SUPERUSER_ID))
        document_id = cr.fetchone()[0]
        cr.execute("""
            UPDATE ir_attachment
               SET res_model = 'opex.membership.document',
                   res_id = %s,
                   res_field = 'file'
             WHERE id = %s
        """, (document_id, attachment_id))

    cr.execute("DROP TABLE ir_attachment_opex_membership_file_rel")
    env['opex.membership.document'].invalidate_model()
    _logger.info(
        "OPEX Membership : %s pièce(s) jointe(s) reprise(s) en pièces de dossier.",
        len(rows),
    )


def _drop_legacy_columns(cr):
    """Supprime les colonnes orphelines, une fois leurs données reprises."""
    for table, column in (
        ('opex_membership_file', 'category_id_legacy'),
        ('res_partner', 'categorie_membre_id_legacy'),
        ('opex_membership_category', 'montant_cotisation'),
        ('opex_membership_category', 'currency_id'),
    ):
        cr.execute('ALTER TABLE "%s" DROP COLUMN IF EXISTS "%s"' % (table, column))


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    mapping = _build_subcategory_mapping(env, cr)
    _remap(env, cr, 'opex.membership.file', 'opex_membership_file',
           'category_id_legacy', mapping)
    _remap(env, cr, 'res.partner', 'res_partner',
           'categorie_membre_id_legacy', mapping)
    _migrate_documents(env, cr)
    env.flush_all()
    _drop_legacy_columns(cr)
    _logger.info("OPEX Membership : migration Extension 8 terminée.")
