"""Prépare la base avant que l'ORM ne recharge le modèle de l'Extension 8.

Deux choses doivent être faites *avant* le chargement du module, pas après.

**Les états.** Le workflow passe de 5 à 13 valeurs (section 15 de la
spécification UX). Un seul ancien code disparaît : `validated` (« Validé
COPIL »), que le nouveau parcours scinde en `copil_validated` puis
`payment_pending`. Les quatre autres — `draft`, `control`, `committee`,
`active` — existent à l'identique et traversent la migration intacts. Un
enregistrement portant une valeur absente de la sélection ne serait plus
lisible par l'ORM : le remappage doit donc précéder son rechargement.

**Les colonnes héritées.** `opex_membership_file.category_id` et
`res_partner.categorie_membre_id` changent de modèle cible. Les mettre de côté
sous un nom que l'ORM ignore évite toute ambiguïté : sans ce renommage,
`category_id` redeviendrait un champ géré par Odoo (related stocké vers la
catégorie de la sous-catégorie) au-dessus de données qui, elles, désignent
encore l'ancienne catégorie. La post-migration lira ces colonnes mises de côté
pour retraduire les identifiants, puis les supprimera.
"""

STATE_RENAMES = {
    # Le COPIL avait validé mais la cotisation n'était pas encore réglée : dans
    # le nouveau parcours, c'est exactement « Paiement en attente ».
    'validated': 'payment_pending',
}

LEGACY_COLUMNS = (
    ('opex_membership_file', 'category_id', 'category_id_legacy'),
    ('res_partner', 'categorie_membre_id', 'categorie_membre_id_legacy'),
)


def _column_exists(cr, table, column):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = %s AND column_name = %s
    """, (table, column))
    return bool(cr.fetchone())


def migrate(cr, version):
    if not version:
        return

    for old_state, new_state in STATE_RENAMES.items():
        cr.execute(
            "UPDATE opex_membership_file SET state = %s WHERE state = %s",
            (new_state, old_state),
        )

    for table, column, legacy in LEGACY_COLUMNS:
        if _column_exists(cr, table, column) and not _column_exists(cr, table, legacy):
            cr.execute(
                'ALTER TABLE "%s" RENAME COLUMN "%s" TO "%s"' % (table, column, legacy)
            )
