# CLAUDE.md — Module OPEX Membership — Phase 2 : Portail Web & Intégrations

## ⚠️ LIRE AVANT TOUTE MODIFICATION

Le module `opex_membership` **existe déjà et fonctionne** (installé, testé, workflow
d'adhésion validé de bout en bout). Ce document décrit une **extension**, pas une
réécriture.

**Ne JAMAIS renommer les modèles existants.** Les noms techniques ci-dessous sont
définitifs :
- `opex.membership.category` (PAS `opex.member.category`)
- `opex.membership.file` (PAS `opex.membership.application`)
- `opex.subscription`
- `opex.payment`
- `opex.cluster.event`
- Extension de `res.partner` (champs `is_member`, `categorie_membre_id`, etc.)

Si un doute existe entre ce fichier et un autre prompt, **ce fichier fait autorité**
pour les noms techniques — c'est la source de vérité du projet.

---

## Ce qui est DÉJÀ FAIT (ne pas retoucher, sauf extensions explicites listées plus bas)

- Les 6 modèles listés ci-dessus, avec leurs champs
- Le workflow complet de `opex.membership.file` (draft → control → committee →
  validated → active), avec ses 3 méthodes de transition
- `security/security.xml` avec `res.groups.privilege` (syntaxe Odoo 19 — PAS
  `category_id` directement sur `res.groups`, ce champ n'existe plus en v19)
- Les 2 groupes `Secrétariat` et `COPIL`
- Les vues formulaire/liste pour tous les modèles

---

## Extension 1 — Intégration `sale.order` pour les cotisations

**Objectif :** remplacer le suivi monétaire interne de `opex.subscription` par une
vraie intégration avec la facturation native Odoo, conformément au Product Backlog
(US-03 : "Payer ma cotisation en ligne et recevoir un reçu fiscal").

### Modification de `opex.subscription`

Ajoute un champ :
```python
sale_order_id = fields.Many2one('sale.order', string="Devis/Commande de cotisation", readonly=True)
```

### Nouvelle méthode sur `opex.membership.file`

`action_create_subscription()` — appelée automatiquement à l'intérieur de
`action_validate_copil()` (ne remplace pas cette méthode, elle est appelée PAR elle) :

1. Cherche ou crée un `product.product` nommé d'après la catégorie
   (ex: "Cotisation — Adhérent"), type service, prix = `category_id.montant_cotisation`
2. Crée un `sale.order` pour `partner_id` avec une ligne pour ce produit
3. Crée l'`opex.subscription` lié (`sale_order_id` renseigné), `montant` copié du
   produit, `date_echeance` = aujourd'hui + 30 jours
4. Confirme le `sale.order` (`action_confirm()`)

### Synchronisation retour

Ajoute une méthode surchargée ou un `@api.onchange`/automated action qui, quand le
`sale.order` lié passe à l'état `'done'` ou que sa facture est payée
(`invoice_status == 'invoiced'` + paiement enregistré côté `account.move`), met à jour
`opex.subscription.state = 'paid'` automatiquement — pas besoin que l'utilisateur le
fasse manuellement.

**Ne supprime PAS `opex.payment`** — garde-le pour les cas de paiement partiel ou hors
Odoo (espèces, virement direct), mais le flux principal recommandé passe maintenant par
`sale.order`.

---

## Extension 2 — Intégration `calendar.event` pour la vie du cluster

**Objectif :** rendre les événements du cluster visibles dans l'agenda Odoo natif,
conformément au sprint planning ("Générez l'intégration des événements calendar.event").

### Modification de `opex.cluster.event`

Ajoute :
```python
calendar_event_id = fields.Many2one('calendar.event', string="Événement agenda", readonly=True)
```

### Comportement

À la création ou la sauvegarde d'un `opex.cluster.event` (méthode `create()` ou
`write()` surchargée), crée/met à jour automatiquement un `calendar.event` lié avec
les mêmes `name`, `date_debut` → `start`, `date_fin` → `stop`, et
`partner_ids` → `partner_ids` (les participants).

**Ne remplace pas `opex.cluster.event` par `calendar.event` directement** — garde le
modèle custom pour les champs métier spécifiques (`type` : Formation/AG/Forum/Réunion),
et synchronise juste vers le calendrier natif pour l'affichage agenda.

---

## Extension 3 — Portail Web Public

**Objectif :** couvrir US-01 (inscription en ligne) et US-16 (annuaire public), et le
sprint "Jour 9-10 : Intégration Frontend (Portail)".

### Nouveaux fichiers

```
opex_membership/
├── controllers/
│   ├── __init__.py
│   └── main.py
├── views/
│   └── portal_templates.xml
```

### Ajoute au `__manifest__.py`
```python
'depends': ['base', 'mail', 'contacts', 'sale', 'website', 'calendar', 'documents'],
```
Ajoute aussi `'views/portal_templates.xml'` à la liste `'data'`.

### Route 1 — Inscription publique : `/opex/membership/register`

- `GET` : affiche un formulaire QWeb public (hérite `website.layout`) avec les champs :
  nom, email, téléphone, secteur d'activité, wilaya, catégorie souhaitée
  (`opex.membership.category`, sélectionnable), documents à joindre
- `POST` : crée un `res.partner` (via `sudo()`, car route publique non authentifiée),
  puis un `opex.membership.file` en état `draft` lié à ce partner, avec la catégorie
  choisie
- Redirige vers une page de confirmation ("Votre dossier a été soumis, vous recevrez
  une notification à chaque étape")

### Route 2 — Annuaire public : `/opex/directory`

- `GET` avec paramètres de recherche optionnels : `secteur`, `wilaya`, `q` (nom)
- Affiche uniquement les `res.partner` où `is_member = True` ET
  `is_published_directory = True`
- Template avec formulaire de recherche multicritère en haut, résultats en cartes
  en dessous (nom, secteur, wilaya, catégorie)
- Route publique, pas d'authentification requise (utilise `sudo()` en lecture seule
  uniquement — ne jamais exposer d'écriture sur une route non protégée)

### Sécurité des routes

Les deux routes sont `auth='public'`. Utilise `request.env['model'].sudo()` pour les
opérations, mais reste strict : la route d'inscription ne doit permettre que la
**création** de `res.partner`/`opex.membership.file` en état `draft` — jamais de
lecture ou modification d'autres enregistrements.

---

## Extension 4 — Documents via l'app Documents (au lieu d'`ir.attachment` brut)

Si `document_ids` sur `opex.membership.file` utilise actuellement `ir.attachment`,
**garde-le tel quel pour l'instant** — ce n'est pas bloquant. Amélioration optionnelle
seulement si le temps le permet : migrer vers `documents.document` pour bénéficier des
espaces de travail et tags de l'app Documents. Ne fais cette migration QUE si le reste
fonctionne déjà sans erreur.

---

## Ordre d'implémentation recommandé

1. Extension 1 (sale.order) — la plus proche du code existant, risque le plus faible
2. Extension 2 (calendar.event) — indépendante, risque faible
3. Extension 3 (portail web) — la plus grosse pièce, teste après les deux premières
4. Extension 4 — seulement si tout le reste est stable

Teste et commit après **chaque extension**, pas à la fin de tout.
