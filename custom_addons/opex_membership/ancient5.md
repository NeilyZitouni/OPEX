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

## 📄 Lire le dossier `docs/` avant de commencer

Le dossier `docs/` à la racine du module contient les documents de référence
complets du projet — lis-les avant toute implémentation, ils contiennent des
détails que ce fichier résume mais ne répète pas intégralement :

- `livrable_deltalog.pdf` — diagrammes UML (classes, activité, séquence) et
  spécifications fonctionnelles originales de DELTALOG
- `portail_digital_vision.pdf` — vision globale du portail, les 3 domaines
  métier, l'architecture générale et le socle commun
- `product_backlog.md` — les User Stories (US-01 à US-24) et le planning de
  sprint ; les extensions décrites plus bas dans ce fichier correspondent
  précisément aux US-01, US-03, US-16 et à la section "Jour 9-10" du sprint 1

Si un champ ou un comportement n'est pas assez précis dans ce fichier, vérifie
d'abord dans `docs/` avant de faire une supposition.

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

## Extension 3 — Portail Web Public (annuaire uniquement — voir Extension 5 pour le candidat)

**⚠️ RÉVISÉ** : la partie "inscription" de cette extension (route
`/opex/membership/register`) est **remplacée** par l'Extension 5 ci-dessous, qui
utilise le système de compte portail natif d'Odoo au lieu d'un formulaire public
anonyme. Ne construis PAS la route `/opex/membership/register` décrite plus bas
dans ce document — seule la route `/opex/directory` (annuaire public, sans
authentification) reste valable telle quelle.

**Objectif :** couvrir US-16 (annuaire public), et le sprint "Jour 9-10".

### Route — Annuaire public : `/opex/directory`

- `GET` avec paramètres de recherche optionnels : `secteur`, `wilaya`, `q` (nom)
- Affiche uniquement les `res.partner` où `is_member = True` ET
  `is_published_directory = True`
- Template avec formulaire de recherche multicritère en haut, résultats en cartes
  en dessous (nom, secteur, wilaya, catégorie)
- Route publique (`auth='public'`), lecture seule, utilise `sudo()` en lecture
  uniquement

### Intégration au menu du site (nouveau — obligatoire pour cette extension)

Fichier `data/website_menu.xml`, deux `website.menu` liés au menu racine du site :
- **"Annuaire"** → `/opex/directory`
- **"Devenir membre"** → `/web/signup?redirect=/my/membership/new` (route native
  Odoo — après inscription, redirige directement vers le formulaire de dépôt de
  dossier, pas besoin de coder une redirection custom)

---

## Extension 6 — Page de présentation du cluster (landing page)

**Objectif :** donner une vraie porte d'entrée publique au portail, présentable
pour la soutenance — pas juste des routes techniques sans point d'accès visible.

### Principe important : rester honnête sur ce qui est réellement fonctionnel

Seul le module Membership est développé à ce stade. La page doit présenter les
3 domaines du cluster (cohérence avec la vision du projet), mais **marquer
clairement** Innovation et Intervenants comme "à venir" — ne jamais laisser croire
que ces parties sont fonctionnelles alors qu'elles ne le sont pas encore.

### Nouveau fichier `views/website_homepage.xml`

Template QWeb hérité de `website.layout`, contenu :
- **Hero** : titre "GIC OPEX Group", sous-titre "Cluster d'excellence
  opérationnelle", deux boutons d'action : **"Devenir membre"** (→
  `/web/signup?redirect=/my/membership/new`) et **"Consulter l'annuaire"**
  (→ `/opex/directory`)
- **Section "Réseau & Adhérents"** (fonctionnelle) : description courte + un
  ou deux chiffres réels tirés de la base (nombre de membres actifs, nombre de
  catégories) — passés par le controller, pas codés en dur
- **Sections "Innovation Booster" et "Appels & Interventions"** : présentation
  courte de l'intention, avec un badge/étiquette visuelle claire du type
  "Prochainement" ou "En développement" — pas de lien actif, pas de bouton
  d'action, juste informatif

### Nouveau controller — route `/cluster`

`GET`, `auth='public'`. Calcule les statistiques réelles via `sudo()` en lecture
seule (`res.partner.search_count([('is_member', '=', True)])` etc.) et les passe
au template. Pas d'écriture, route entièrement publique et sûre.

### Définir cette page comme accueil du site (étape manuelle, pas de code)

Une fois la page fonctionnelle à `/cluster`, l'utilisateur définit lui-même
l'accueil dans **Site Web → Configuration → Réglages → URL de la page d'accueil**
= `/cluster`. Ne fais PAS de route codée en dur sur `/` — ça risquerait d'entrer
en conflit avec les pages déjà installées par le module `website`.

---

## Extension 5 — Espace Candidat (compte portail natif)

**Objectif :** implémenter fidèlement le couloir "Candidat" du diagramme d'activité
— "Création du compte" puis "Dépôt du dossier d'adhésion", **avant** toute
intervention de Secrétariat/COPIL. Le candidat ne doit JAMAIS avoir besoin qu'un
Secrétariat ou COPIL crée le dossier à sa place.

### Principe : utiliser le groupe portail natif, pas un nouveau groupe custom

- **Ne crée PAS** de nouveau `res.groups` pour "Candidat"
- Utilise `base.group_portal`, le groupe portail natif d'Odoo (accès limité,
  interface "Mon compte", pas le back-office)
- "Création du compte" = le flux `/web/signup` déjà natif à Odoo (rien à coder) —
  vérifie juste que Réglages → Général → "Comptes clients" autorise
  l'inscription libre (`auth_signup_uninvited = 'b2c'` ou équivalent)

### Sécurité — `ir.model.access.csv`

Ajoute une ligne donnant à `base.group_portal` :
- `perm_read = 1`, `perm_write = 1`, `perm_create = 1`, `perm_unlink = 0` sur
  `opex.membership.file`
- `perm_read = 1` (uniquement) sur `opex.membership.category`

### Sécurité — `ir.rule` (règle d'enregistrement, PAS juste ir.model.access.csv)

Crée une règle sur `opex.membership.file` pour `base.group_portal` :
```python
domain_force = "[('partner_id', '=', user.partner_id.id)]"
```
avec `perm_read=True, perm_create=True` sans restriction supplémentaire, et
```python
domain_force = "[('partner_id', '=', user.partner_id.id), ('state', '=', 'draft')]"
```
pour `perm_write=True` — un candidat ne peut modifier son dossier que tant qu'il
est en Brouillon, plus une fois soumis (le contrôle passe à Secrétariat/COPIL).

### Sécurité — forcer `partner_id` côté serveur (ne pas faire confiance au client)

Dans `opex.membership.file`, surcharge `create()` : si l'utilisateur courant est
dans `base.group_portal`, force `vals['partner_id'] = self.env.user.partner_id.id`
**quelle que soit la valeur envoyée** par le formulaire — empêche un candidat de
créer un dossier au nom de quelqu'un d'autre en trafiquant la requête.

### Controller portail (hérite `CustomerPortal`)

Fichier `controllers/portal.py` :
- `/my/membership` — liste des dossiers du candidat connecté (`GET`)
- `/my/membership/new` — formulaire de dépôt (`GET` affiche, `POST` crée en
  `state='draft'`, `partner_id` forcé côté serveur comme ci-dessus)
- `/my/membership/<int:file_id>` — détail en lecture seule (statut, historique)
- `/my/membership/<int:file_id>/submit` — **(`POST`, statut ✅ implémenté)**
  appelle `action_submit()` sur le dossier pour le faire passer de Brouillon à
  En contrôle. Vérifie `record.partner_id == request.env.user.partner_id`
  avant d'agir (même logique de protection que le `create()` surchargé) —
  sans cette route, le dossier reste bloqué en Brouillon indéfiniment.
- Ajoute le compteur "Mes dossiers d'adhésion" à `_prepare_home_portal_values()`
  (page d'accueil du portail, à côté des compteurs natifs comme "Mes commandes")

### Vues portail (QWeb, héritent `portal.portal_layout`)

- `views/portal_templates.xml` : templates pour les 3 routes ci-dessus, dans le
  style visuel standard du portail Odoo (mêmes classes CSS que les pages
  "Mes commandes"/"Mes factures" natives, pour la cohérence visuelle)

### Ajoute au `__manifest__.py` (cumule avec les dépendances des extensions précédentes)
```python
'depends': ['base', 'mail', 'contacts', 'sale', 'website', 'portal', 'calendar'],
```
**Ne pas ajouter `'documents'`** — absent de certaines installations Community,
rendrait le module non installable. L'app Documents ne sert qu'à l'Extension 4
(optionnelle) ; sans elle, `document_ids` reste sur `ir.attachment`, ce qui
fonctionne très bien pour le POC.

Ajoute `'security/ir_rule.xml'` (nouveau fichier, la règle d'enregistrement
ci-dessus), et `'views/portal_templates.xml'` à la liste `'data'`.

### Nouveaux fichiers pour les Extensions 3 et 5
```
opex_membership/
├── controllers/
│   ├── __init__.py
│   ├── directory.py       (annuaire public, Extension 3)
│   └── portal.py          (espace candidat, Extension 5)
├── security/
│   └── ir_rule.xml        (nouveau, la règle d'enregistrement ci-dessus)
├── views/
│   ├── directory_templates.xml
│   └── portal_templates.xml
```

---

## Extension 4 — Documents via l'app Documents (au lieu d'`ir.attachment` brut)

Si `document_ids` sur `opex.membership.file` utilise actuellement `ir.attachment`,
**garde-le tel quel pour l'instant** — ce n'est pas bloquant. Amélioration optionnelle
seulement si le temps le permet : migrer vers `documents.document` pour bénéficier des
espaces de travail et tags de l'app Documents. Ne fais cette migration QUE si le reste
fonctionne déjà sans erreur.

---

## Extension 7 — Espace de traitement web pour Secrétariat / COPIL / Admin

**Objectif :** donner à Secrétariat, COPIL et Admin un espace **web dédié** pour
consulter et valider les dossiers — symétrique à l'espace candidat (Extension 5),
mais pour le personnel interne. Le back-office Odoo classique reste disponible
et complet ; ceci est une façade web supplémentaire, plus simple à démontrer
dans un navigateur, pas un remplacement.

### Sécurité — connexion interne, pas portail

- `auth='user'` (utilisateur interne connecté, jamais `auth='public'`)
- Contrôle explicite dans le controller à chaque route :
  ```python
  user = request.env.user
  if not (user.has_group('opex_membership.group_secretariat')
          or user.has_group('opex_membership.group_copil')
          or user.has_group('base.group_system')):
      return request.redirect('/my')
  ```
- **Ne duplique jamais la logique métier.** Le controller appelle les méthodes
  déjà existantes sur `opex.membership.file`
  (`action_validate_secretariat()`, `action_validate_copil()`) — il ne
  réécrit aucune règle de transition d'état.

### Nouveau fichier `controllers/staff.py`

- `/staff/membership` — `GET`, liste des dossiers à traiter, filtrée selon le
  rôle du user connecté : Secrétariat voit `state='control'`, COPIL voit
  `state in ('committee', 'validated')`, Admin voit tout
- `/staff/membership/<int:file_id>` — `GET`, détail du dossier (mêmes
  informations que côté candidat, plus les boutons d'action pertinents selon
  le rôle)
- `/staff/membership/<int:file_id>/validate` — `POST`, appelle la méthode de
  transition appropriée selon le groupe de l'utilisateur connecté (jamais
  selon un paramètre envoyé par le formulaire — le rôle vient toujours de
  `request.env.user`, jamais d'une donnée cliente)

### Nouveau fichier `views/staff_templates.xml`

Hérite `website.layout`, même esprit visuel que le reste du site. Liste type
"à traiter" : nom du candidat, catégorie demandée, date de dépôt, bouton
"Traiter" vers le détail.

### Lien de navigation conditionnel (pas un menu public)

Dans le header du site, ajoute un lien **visible uniquement si connecté ET
dans un des 3 groupes** :
```xml
<t t-if="request.env.user.has_group('opex_membership.group_secretariat')
         or request.env.user.has_group('opex_membership.group_copil')
         or request.env.user.has_group('base.group_system')">
    <a href="/staff/membership">Espace validation</a>
</t>
```
Un candidat ou un visiteur non connecté ne doit jamais voir ce lien. Ajoute
aussi un lien simple **"Connexion"** (→ `/web/login`, sans signup) visible
pour tout le monde, non connecté inclus — c'est le point d'entrée pour le
personnel interne qui n'a pas encore de session active.

---

## Ordre d'implémentation recommandé

1. Extension 1 (sale.order) — fait
2. Extension 5 (espace Candidat) — fait et testé de bout en bout
3. Extension 3 (annuaire public + menu) — fait
4. Extension 6 (page de présentation) — fait
5. **Extension 7 (espace de traitement Secrétariat/COPIL/Admin)** — à faire
   maintenant, c'est le trou identifié : le staff n'a aujourd'hui aucun moyen
   de traiter un dossier autrement qu'en passant par le back-office Odoo
6. Extension 2 (calendar.event) — indépendante, peut se faire n'importe quand
7. Extension 4 — seulement si tout le reste est stable

Teste et commit après **chaque extension**, pas à la fin de tout.
