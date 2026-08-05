# CLAUDE.md — Module OPEX Membership (POC)

## Contexte du projet

Ce module Odoo 19 (`opex_membership`) fait partie du portail digital du GIC OPEX
Group (cluster d'excellence opérationnelle). Il gère le réseau et les adhérents :
adhésion, cotisations, paiements, annuaire, vie du cluster.

**Convention retenue : pas de classe abstraite custom.** Contrairement à un modèle
UML purement conceptuel, on suit ici l'architecture technique validée avec
DELTALOG : le référentiel unique est directement `res.partner` (Contacts natif
Odoo), enrichi par héritage `_inherit`. On ne crée PAS de modèle `Acteur`/`Adherent`
séparé — un partner est "membre" via un booléen `is_member` + une catégorie liée.

**Convention de nommage Odoo :** tous les modèles custom sont préfixés `opex.`.

---

## Modèles à implémenter

### 1. Extension de `res.partner` (fichier `models/res_partner.py`)

N'écrit PAS `_name`, seulement `_inherit = 'res.partner'`.

| Champ | Type Odoo | Détail |
|---|---|---|
| `is_member` | `Boolean` | Est un membre du cluster |
| `categorie_membre_id` | `Many2one('opex.membership.category')` | |
| `secteur_activite` | `Char` | |
| `wilaya` | `Char` | |
| `date_adhesion` | `Date` | |
| `membership_file_ids` | `One2many('opex.membership.file', 'partner_id')` | |
| `subscription_ids` | `One2many('opex.subscription', 'partner_id')` | |
| `event_ids` | `Many2many('opex.cluster.event', 'event_partner_rel')` | Participation aux événements |

Méthode : `get_public_profile()` — retourne les champs exposables dans l'annuaire
public (name, secteur_activite, wilaya, categorie_membre_id), utilisée par la vue
portail de l'annuaire.

### 2. `opex.membership.category` (`models/opex_membership_category.py`)

| Champ | Type Odoo |
|---|---|
| `name` | `Char` — valeurs attendues : Adhérent, Associé, Partenaire/Sponsor, Expert |
| `montant_cotisation` | `Monetary` + `currency_id` |
| `droits_acces` | `Char` ou `Text` |

Relation : `res.partner` **(0..\*)** — `appartient à` — **(1)** `opex.membership.category`
*(agrégation : une catégorie ne disparaît pas si un membre est supprimé → `ondelete='restrict'`)*

### 3. `opex.membership.file` — Dossier d'adhésion (`models/opex_membership_file.py`)

| Champ | Type Odoo |
|---|---|
| `partner_id` | `Many2one('res.partner')` |
| `date_depot` | `Datetime` |
| `document_ids` | `Many2many('ir.attachment')` — documents joints |
| `state` | `Selection` : `draft` (Brouillon), `control` (EnControle), `committee` (EnComite), `validated` (ValideCOPIL), `active` (Active) |

Méthodes (boutons du workflow) :
- `action_submit()` — Brouillon → EnControle (`soumettreDossier`)
- `action_validate_secretariat()` — EnControle → EnComite, **uniquement si le
  dossier est complet** sinon lève `UserError` et reste en `EnControle`
  (`validerParSecretariat`)
- `action_validate_copil()` — EnComite → ValideCOPIL → déclenche automatiquement
  la suite du workflow système (voir diagramme d'activité ci-dessous)
  (`validerParCOPIL`)

Relation : `res.partner` **(1)** — `dépose` — **(0..\*)** `opex.membership.file`
*(composition : un dossier n'existe pas sans son partner → `ondelete='cascade'`)*

### 4. `opex.subscription` — Cotisation (`models/opex_subscription.py`)

| Champ | Type Odoo |
|---|---|
| `partner_id` | `Many2one('res.partner')` |
| `montant` | `Monetary` |
| `date_emission` | `Date` |
| `date_echeance` | `Date` |
| `state` | `Selection` : `waiting` (EnAttente), `paid` (Payee), `late` (EnRetard), `cancelled` (Annule) |
| `payment_ids` | `One2many('opex.payment', 'subscription_id')` |

Méthodes :
- `action_generate_reminder()` — envoie une relance si `state == 'late'`
  (`genererRelances`)
- `action_register_payment()` — crée un `opex.payment` lié, passe `state = 'paid'`
  si le montant total payé couvre la cotisation (`enregistrerPaiement`)

Relation : `res.partner` **(1)** — `paie` — **(0..\*)** `opex.subscription`
*(composition, `ondelete='cascade'`)*

### 5. `opex.payment` — Paiement (`models/opex_payment.py`)

| Champ | Type Odoo |
|---|---|
| `subscription_id` | `Many2one('opex.subscription')` |
| `montant` | `Monetary` |
| `date_paiement` | `Datetime` |
| `reference_transaction` | `Char` |
| `mode_paiement` | `Selection` : `card` (Carte), `transfer` (Virement), `cash` (Espèces) |

Relation : `opex.subscription` **(1)** — `génère` — **(0..\*)** `opex.payment`
*(composition — un paiement n'a pas de sens sans sa cotisation, `ondelete='cascade'`.
Une cotisation peut recevoir plusieurs paiements partiels avant d'être soldée.)*

### 6. `opex.cluster.event` — Événement (`models/opex_cluster_event.py`)

| Champ | Type Odoo |
|---|---|
| `name` | `Char` (titre) |
| `date_debut` | `Datetime` |
| `date_fin` | `Datetime` |
| `lieu` | `Char` |
| `partner_ids` | `Many2many('res.partner')` — participants |
| `type` | `Selection` : `training` (Formation), `general_assembly` (AG), `forum` (Forum), `meeting` (Réunion) |

Relation : `res.partner` **(0..\*)** — `participe à` — **(0..\*)** `opex.cluster.event`
*(association simple many-to-many, ni composition ni agrégation)*

---

## Workflow d'adhésion — Diagramme d'activité (à respecter exactement)

Couloirs : **Candidat | Secrétariat | Comité d'admission | COPIL | Système**

```
[Candidat]         ● (début)
[Candidat]         Création du compte
[Candidat]         Dépôt du dossier d'adhésion
        │
[Secrétariat]      Contrôle administratif du dossier
[Secrétariat]      ◇ Dossier complet ?
                        ── Non ──> [Candidat] Retour au candidat pour modifications ──> ◉ (fin)
                        ── Oui ──┐
                                 ▼
[Comité d'admission]  Émission d'un avis consultatif   (⚠ CONSULTATIF SEULEMENT — ne bloque pas, n'active rien)
                                 │
[COPIL]                Validation finale (Activation)   (⚠ C'EST LE COPIL QUI VALIDE, PAS LE COMITÉ)
                                 │
[Système]              Génération de la facture de cotisation
[Système]              Enregistrement du paiement en ligne
[Système]              Signature électronique de la Charte
[Système]              Activation du compte membre
[Système]              Publication automatique dans l'annuaire public
[Système]              ◉ (fin)
```

**Point d'implémentation important :** dans `action_validate_copil()`, chaîner
automatiquement (via le code Python, pas des clics utilisateur séparés) :
génération de la cotisation → attente paiement → une fois payé (`opex.payment`
créé) → déclencher signature (champ `signature_date` ou intégration `sign` plus
tard) → passer `res.partner.is_member = True` et `state = 'active'` → mettre à
jour un champ `is_published_directory = True` pour l'annuaire.

---

## Conventions Odoo à respecter

- Français pour les labels de champs (`string=`), anglais/snake_case pour les
  noms techniques de champs et modèles.
- Chaque modèle avec un `state` : utiliser `Selection`, jamais de `Char` libre.
- Toute transition d'état interdite doit lever `odoo.exceptions.UserError` avec
  un message clair, pas échouer silencieusement.
- Ajouter `_inherit = ['mail.thread', 'mail.activity.mixin']` sur les modèles
  avec un workflow (`opex.membership.file`, `opex.subscription`), pour le suivi
  et les notifications.
- Vues : formulaire avec `<header>` + `statusbar` sur `state`, boutons visibles
  selon l'état (`invisible="state != 'draft'"` etc.), pas d'ancien attribut
  `attrs=`.
- Sécurité minimale pour le POC : un groupe `Secrétariat` et un groupe `COPIL`
  dans `security/security.xml`, droits dans `security/ir.model.access.csv`.

## Ce qui est HORS scope pour ce POC (ne pas développer)

- Signature électronique réelle (juste un champ date, pas d'intégration DocuSign/Sign)
- Génération PDF poussée de la charte (un simple rapport QWeb basique suffit)
- Relances automatiques programmées (cron) — un bouton manuel suffit pour la démo
