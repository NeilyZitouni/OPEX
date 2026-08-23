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
  sprint
- `module1_ux_valide.pdf` — **document de référence principal à partir
  d'Extension 8.** Validé par l'encadrant (Dr. Babaci). Décrit, écran par
  écran et à la lettre, tout le parcours UX attendu (48 sections). En cas de
  divergence entre ce fichier CLAUDE.md et `module1_ux_valide.pdf` sur un
  point de contenu fonctionnel (texte d'écran, libellé, ordre des champs),
  **le PDF fait foi** — ce fichier CLAUDE.md donne la traduction technique
  (modèles, champs, routes), pas le texte exact à afficher.

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

## ⚠️ Règle transversale : collisions de nommage avec l'API interne d'Odoo

Rencontré deux fois déjà (`res.partner.category_id` en Extension 8,
`_register` en Extension 16) : Odoo a une très large surface de noms déjà
pris en interne — champs natifs, attributs de classe (`BaseModel._register`
notamment), méthodes système. Un nom qui semble générique et libre
(`category_id`, `_register`, `_name`, `_state`...) peut déjà exister,
auquel cas la nouvelle définition ne lève pas forcément d'erreur explicite
— elle peut être silencieusement masquée, avec un comportement qui échoue
de façon confuse au runtime plutôt qu'au chargement du module.

**Avant de nommer un nouveau champ ou une nouvelle méthode dans une
extension, vérifie qu'il n'entre pas en collision avec quelque chose
d'existant sur le modèle parent ou sur `BaseModel`.** En cas de doute,
préfixe (`opex_`, ou un nom plus spécifique comme `_register_participant`
plutôt que `_register`).

## ⚠️ Règle transversale : un contrôle d'accès = une seule fonction, jamais recopié

Dès qu'une même condition d'accès doit être vérifiée sur plusieurs routes
(voir Extension 16, `_cluster_access_denied()` appelée par les 5 routes
concernées plutôt que le test dupliqué cinq fois), centralise-la dans une
seule fonction/méthode réutilisée partout. Une vérification recopiée finit
tôt ou tard par en oublier une occurrence — et c'est précisément celle-là
qui reçoit la requête forgée. S'applique à toute future extension qui
ajoute plusieurs routes partageant une même règle de visibilité.

## ⚠️ Règle transversale : "présent dans le HTML" ≠ "visible à l'écran"

Rencontré deux fois sous deux formes différentes :

- **Extension 10 (`certification_ids`)** : bloc caché par un `t-if`
  conditionné à un référentiel (`opex.certification`) resté vide, jamais
  semé.
- **Navigation Vie du Cluster** : tuile portail rendue avec la classe CSS
  `d-none` (le mécanisme natif `portal.portal_docs_entry` masque toute
  carte sans `placeholder_count` ni `config_card` — les deux autres tuiles
  du portail s'en sortaient grâce à un compteur, celle-ci n'en avait pas).

Dans les deux cas, un test qui vérifie `'texte ou url' in response.body`
passe **alors que l'utilisateur ne voit rien** — l'assertion mesure la
présence dans le flux HTML, pas la visibilité réelle. C'est l'assertion
elle-même qui est en cause, autant que le bug qu'elle a laissé passer.

**Deux réflexes à appliquer systématiquement pour toute future extension :**
1. Pour tout champ/bloc dépendant d'une donnée qui peut être vide ou nulle
   (référentiel non semé, compteur à zéro, liste vide) : vérifie le rendu
   réel avec de vraies données, pas seulement la présence du bloc dans le
   template ou la chaîne dans la réponse HTTP.
2. Dans les tests, ne teste jamais uniquement `'x' in body` pour confirmer
   qu'un élément est *affiché* — vérifie l'absence de la classe qui le
   masquerait (`d-none` ou équivalent), ou le rendu réel de l'élément
   cliquable/visible.

Quand un état vide est légitime, affiche un message explicite plutôt que
de masquer silencieusement — un élément qui disparaît sans explication est
pire qu'une erreur visible : ni bug signalé, ni fonctionnalité utilisable.

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

# 🆕 EXTENSIONS 8 À 19 — Alignement complet sur `module1_ux_valide.pdf` (validé encadrant)

**Lis `module1_ux_valide.pdf` en entier avant de commencer quoi que ce soit
ci-dessous.** Ces 12 extensions traduisent ses 48 sections en travail
technique. Elles sont volontairement plus détaillées que les extensions
précédentes car ce document est maintenant LA référence validée — plus rien
ne doit être simplifié ou fusionné sans le signaler explicitement comme écart.

**Rappel non négociable : une extension à la fois, test + commit avant la
suivante.** Ne saute jamais cette règle même si l'utilisateur demande "tout
d'un coup" — c'est justement ce qui a causé les régressions les plus dures à
diagnostiquer jusqu'ici (cf. l'incident `res.groups.privilege` en Odoo 19).

## Extension 8 — Fondations du modèle de données (sous-catégories + formulaire détaillé + workflow étendu)

**Sous-catégories** (déjà décrites en théorie dans le SFD, jamais implémentées) :
- Nouveau modèle `opex.membership.subcategory` : `name`, `category_id`
  (Many2one), `montant_cotisation` (Monetary), `critere_eligibilite` (Char)
- `opex.membership.category` perd `montant_cotisation` (déplacé)
- `res.partner.categorie_membre_id` et `opex.membership.file.category_id`
  renommés `subcategory_id`, pointant vers `opex.membership.subcategory`
- ⚠️ Piège de nommage déjà rencontré : n'ajoute jamais de champ
  `category_id` sur `res.partner` — ce nom est déjà pris par le champ natif
  des tags de contact (`res.partner.category_id`, Many2many vers
  `res.partner.category`). Pour accéder à la catégorie parente depuis un
  partner, utilise `membership_category_id` (related, via
  `subcategory_id.category_id`) — nom déjà retenu, à réutiliser tel quel
  dans toutes les extensions suivantes qui en ont besoin (dashboards,
  annuaire, etc.)
- Table de correspondance exacte à respecter (section 3 du PDF) : Membres
  adhérents→PME/PMI ; Membres associés→Université, Incubateur, Centre de
  recherche ; Partenaires/Sponsors→Grande entreprise, Banque, Institution ;
  Experts/Consultants→Expert ACEO, Cabinet, Consultant indépendant
- 🐛 **Bug trouvé à l'Extension 17, à corriger** : `res.partner.date_adhesion`
  n'est en réalité jamais écrit par aucune étape du workflow — champ
  toujours `NULL`, malgré la spec d'origine ("Système, à l'activation").
  Corrige `_activate_membership()` pour l'écrire réellement (une ligne).
  En attendant, le tableau de bord de l'Extension 17 utilise
  `opex.membership.file.signature_date` comme proxy fiable — garde ce
  contournement en place même après la correction, pas la peine de faire
  une migration rétroactive pour les dossiers déjà actifs tant que ce
  n'est pas gênant.
**Champs du formulaire détaillé** (sections A à D du PDF) ajoutés sur
`opex.membership.file` :
| Section | Champs |
|---|---|
| A — Organisation | `nom_legal`, `nom_commercial`, `forme_juridique`, `nif`, `rc`, `adresse`, `wilaya` (déjà existant, garder), `commune`, `site_web`, `email_pro`, `telephone` |
| B — Activité | `secteur_activite` (existant), `activite_principale`, `description_activite`, `nombre_salaries` (Integer), `chiffre_affaires` (Monetary, optionnel), `certification_ids` (Many2many, nouveau modèle simple `opex.certification` avec juste `name`) |
| C — Représentant | `representant_nom`, `representant_prenom`, `representant_fonction`, `representant_email`, `representant_telephone` |
| D — Complémentaire | `presentation` (Text), `motivation` (Text — "pourquoi rejoindre le GIC OPEX"), `domaines_expertise` (Text), `partenariats_existants` (Text) |

**Documents obligatoires vs optionnels** (section E) : sur `document_ids`,
distinguer via un champ `document_type` (Selection : `registre_commerce`,
`statuts`, `presentation_entreprise`, `certification`, `autre`) sur un
nouveau modèle léger `opex.membership.document` (au lieu de `ir.attachment`
brut) avec `file` (Binary), `document_type`, `is_required` (Boolean, dérivé
du type). Obligatoires : Registre de commerce, Statuts.

**Workflow étendu** — remplace l'ancien `state` à 5 valeurs par la séquence
exacte du PDF (section 15) :
```
draft → control → correction_requested → control → committee
→ copil_pending → copil_validated → payment_pending → payment_verification
→ signature_pending → signature_verification → active
```
Plus les sorties négatives à chaque étape de décision : `rejected_control`,
`rejected_committee`, `rejected_copil`. Garde une méthode utilitaire
`is_rejected()` plutôt que de multiplier les états terminaux dans les vues.

**Nouveau modèle `opex.membership.correction`** : `file_id`, `document_id`
(quel document pose problème), `motif` (Char), `commentaire` (Text),
`date_demande`, `resolved` (Boolean).

---

## Extension 9 — Comité d'admission (acteur distinct, PAS fusionné avec COPIL)

**⚠️ Contredit l'ancien écart 27.1 du SFD** — le document validé confirme
explicitement un acteur séparé. Implémente-le pour de vrai.

- Nouveau groupe `opex_membership.group_comite`, même `res.groups.privilege`
  "Membership" que Secrétariat/COPIL (donc mutuellement exclusif avec eux
  dans le sélecteur simple — comportement voulu)
- `opex.membership.file` gagne `avis_comite` (Selection : `favorable`,
  `defavorable`, `complement`), `commentaire_comite` (Text)
- Route staff `/staff/membership` : le Comité voit `state='committee'`,
  distinct de ce que voient Secrétariat (`control`) et COPIL
  (`copil_pending`/`copil_validated`)
- Bouton "Enregistrer l'avis" → si favorable, transition vers `copil_pending`
  (visible pour COPIL) ; si défavorable → `rejected_committee` ; si
  complément → retour à `correction_requested`
- `action_request_correction()` est un point d'entrée **partagé** entre
  Secrétariat (depuis `control`) et Comité (depuis `committee`, via
  "complément") — même méthode, pas de duplication
- À chaque retour d'un dossier en `committee` après une ronde de
  correction, `avis_comite`/`commentaire_comite` sont remis à vide — sinon
  le COPIL verrait un avis obsolète et validerait sur une décision qui ne
  tient plus. L'historique reste consultable dans le chatter (l'avis est
  tracké avant remise à zéro)

---

## Extension 10 — Parcours candidat en étapes (formulaire multi-écrans + brouillon + récapitulatif)

Remplace le formulaire actuel unique de `/my/membership/new` par un
véritable enchaînement d'écrans, fidèle aux sections 5 à 14 du PDF :
1. `/my/membership/new` — choix catégorie puis sous-catégorie (deux clics,
   pas un simple select)
2. `/my/membership/new/organisation` — Section A
3. `/my/membership/new/activite` — Section B
4. `/my/membership/new/representant` — Section C
5. `/my/membership/new/complement` — Section D
6. `/my/membership/new/documents` — Section E, avec indication claire
   obligatoire/optionnel
7. `/my/membership/new/recap` — Récapitulatif complet + case de
   certification + bouton "DÉPOSER LE DOSSIER"

**Brouillon automatique** : le dossier `opex.membership.file` est créé dès
la première étape (état `draft`), chaque étape suivante fait un `write()`
partiel — pas de perte de données si le candidat quitte. Le message "Votre
demande a été sauvegardée, vous pourrez continuer plus tard" doit
s'afficher s'il revient sur un brouillon existant.

---

## Extension 11 — Correction demandée (flux complet)

- Bouton "Demander correction" côté Secrétariat (et Comité, s'il choisit
  "complément") → crée un `opex.membership.correction`, transition vers
  `correction_requested`
- Formulaire staff : document concerné (select parmi `document_ids` du
  dossier), motif, commentaire → obligatoires avant envoi
- Côté candidat, `/my/membership/<id>` affiche la correction demandée en
  évidence, avec possibilité de re-uploader le document concerné puis de
  re-soumettre → retour à `control`
- Notification au candidat à la création de la correction (voir Extension 18)

---

## Extension 12 — Paiement à deux voies + vérification

**Voie A — Paiement en ligne** : réutilise l'intégration `sale.order`
existante (Extension 1) — bouton "Payer maintenant" natif Odoo si un
fournisseur de paiement est configuré.

**Voie B — Preuve de paiement** (nouveau, absent jusqu'ici) : formulaire
candidat avec `reference_transaction` (Char — réutilise le champ déjà
existant sur `opex.payment` depuis l'Extension 1, ne pas en créer un
second ; seul le libellé du champ dans le formulaire dit "référence de
paiement"), `date_paiement` (Date), `montant`
(Monetary), `justificatif` (Binary, obligatoire) → crée/complète
`opex.payment` avec `state='to_verify'`. Transition du dossier vers
`payment_verification`.

**Vérification staff** : bouton "Confirmer" (→ `opex.payment.state='paid'`,
dossier → `signature_pending`) ou "Rejeter" avec motif (→ dossier reste en
`payment_pending`, candidat notifié pour re-soumettre une preuve).

Deux règles à respecter dans l'implémentation :
- Le calcul du montant réglé (pour savoir si la cotisation est soldée) ne
  doit compter **que** les `opex.payment` à l'état `paid` — jamais les
  preuves encore `to_verify`, sinon un candidat pourrait déclarer n'importe
  quel montant et voir sa cotisation soldée avant toute vérification
- Le bouton "Enregistrer le paiement" (Extension 1/7, côté staff) et le
  couple "Confirmer/Rejeter" (cette extension) ne doivent jamais être
  visibles simultanément sur la même cotisation — le premier ne s'affiche
  que pour une cotisation en `payment_pending` sans preuve en attente,
  le second seulement une fois une preuve déposée (`payment_verification`)

---

## Extension 13 — Signature de la Charte à deux voies + vérification

Sur `opex.membership.file` : `signature_mode` (Selection : `digital`,
`document`), `charte_document` (Binary, la charte signée si voie document),
`signature_date` (déjà existant — pas `charte_signature_date` comme
initialement supposé ici ; déjà affiché dans trois templates, à réutiliser
tel quel).

**Voie A — Digitale** : bouton "Consulter le document" (PDF généré ou
statique) puis "Signer électroniquement" (pour le POC : simple confirmation
horodatée, pas de vraie signature cryptographique — le documenter comme
simplification assumée si le temps manque pour une vraie intégration).

**Voie B — Document** : bouton "Télécharger" la charte vierge, puis
upload du document signé.

Le dépôt de la signature (voie A ou B) fait passer le dossier de
`signature_pending` à `signature_verification` — PAS directement à `active`.
Le Secrétariat contrôle le document (bouton "Confirmer" / "Rejeter", même
esprit que la vérification de paiement de l'Extension 12) ; c'est cette
confirmation, une fois le paiement également confirmé, qui déclenche
`active`. Remplace le stub `action_sign_charte()` ajouté en Extension 8 par
ce vrai enchaînement à deux étapes.

Même règle que pour le paiement (Extension 12) : `signature_pending` est le
tour du **candidat** (signer), jamais du staff — aucun bouton de signature
ne doit apparaître côté Secrétariat/COPIL à cet état. Le staff n'agit qu'à
`signature_verification` (Confirmer/Rejeter). Ne mélange jamais les deux,
y compris au niveau de la route (un POST direct à l'étape candidate doit
échouer silencieusement, pas juste être caché dans l'UI).

---

## Extension 14 — Annuaire enrichi + profil public dédié

- Ajoute les critères `expertise` et `certification` à `/opex/directory`
  (recherche sur `domaines_expertise` et `certification_ids`) — les 5
  critères du cahier des charges sont maintenant tous couverts
- Nouvelle route `/opex/directory/<int:partner_id>` — page de profil public
  dédiée (section 28 du PDF), pas juste une carte dans la liste

---

## Extension 15 — Cotisations post-adhésion : historique, relances, reçu, renouvellement

- Vue candidat `/my/subscriptions` : historique année par année avec état
  (✓ Payée / ○ À renouveler / ⏳ À venir), fidèle à la section 29
- **Relances automatiques** : action planifiée (cron Odoo) qui, X jours
  avant `date_echeance`, notifie le membre ; et si la date est dépassée sans
  paiement, passe `opex.subscription.state` à `late` et notifie à nouveau
- **Reçu** : génération d'un document téléchargeable (QWeb PDF simple) après
  confirmation de paiement, accessible depuis `/my/subscriptions`
- **Renouvellement** : nouvelle méthode `action_renew()` sur
  `opex.membership.file` — crée une nouvelle `opex.subscription` pour la
  période suivante SANS repasser par tout le workflow d'adhésion (pas de
  nouveau dossier, pas de nouveau contrôle Secrétariat)

---

## Extension 16 — Vie du Cluster complète

Le module actuel n'a que le modèle `opex.cluster.event` de base. Cette
extension couvre la Partie VIII du PDF (sections 33 à 40) :

| Nouveau modèle | Champs clés |
|---|---|
| `opex.cluster.news` (Actualités) | `title`, `image`, `content`, `category`, `publish_date`, `attachment_ids` |
| `opex.cluster.event` (existant, enrichi) | + `registration_ids` (One2many vers `opex.cluster.event.registration` : `partner_id`, `event_id`, `training_id`, `state` inscrit/présent) |
| `opex.cluster.training` (Formations) | `name`, `date`, `duration`, `seats_total`, `seats_available` (computed), `registration_ids` |

**✅ Décision actée (première moitié implémentée)** : pas de modèle
`opex.cluster.training.registration` séparé — `opex.cluster.event.registration`
sert aux deux (événements et formations), avec `event_id`/`training_id`
tous deux optionnels mais une contrainte imposant qu'exactement un des deux
soit renseigné. Un événement et une formation partagent la même structure
d'inscription ; un second modèle aurait juste dupliqué une table à
maintenir en double. Garde ce principe pour Documents/Groupes/Comités/
Assemblée si un besoin similaire se présente dans la seconde moitié.
| `opex.cluster.document` | `name`, `folder` (Selection : AG / Règlements / Chartes / Formations / Documents du Cluster), `file`, `version`, `confidentiality` (Selection : public/membres/comité) |
| `opex.cluster.group` (Forums/Groupes) | `name`, `description`, `member_ids` (Many2many res.partner) |
| `opex.cluster.committee` (Comités) | `name`, `member_ids`, `document_ids`, `meeting_ids` |
| `opex.cluster.assembly` (Assemblée Générale) | `date`, `agenda` (Text, ordre du jour), `document_ids`, `participant_ids`, `decisions` (Text), `report` (Binary, compte-rendu) |

**Votes** : section 40 explicitement marquée "évolution" par le document
source lui-même — crée uniquement un stub `opex.cluster.vote` (`question`,
`option_ids`, `assembly_id`) SANS logique de dépouillement, et documente
clairement dans le code que le calcul de résultats est hors périmètre actuel.

Routes portail à ajouter : `/my/cluster/news`, `/my/cluster/events`,
`/my/cluster/trainings`, `/my/cluster/documents`, `/my/cluster/groups`.

**✅ Décision actée : accès réservé aux membres actifs (`is_member = True`)**,
pas ouvert à tout compte portail connecté. Un candidat encore en cours
d'adhésion (`state` différent de `active`) ne doit voir aucune des pages
Vie du Cluster. Vérification côté serveur sur chaque route (redirection
propre, pas juste un lien caché côté template) — même exigence qu'ailleurs
dans ce module. S'applique aux 3 routes déjà livrées (news/events/
trainings) **et** aux routes de la seconde moitié (documents/groupes) à
venir.

**✅ Exception actée (implémentée)** : Secrétariat, Comité, COPIL — les 3
vrais groupes internes du module (`opex_membership.group_*`) — et Admin
(`base.group_system`, natif Odoo, pas un groupe du module à proprement
parler mais avec accès complet partout par construction) peuvent
prévisualiser ces pages depuis le portail même sans être eux-mêmes membres.

Implémenté via `res.users._is_opex_staff()` — **source unique** de la liste
des rôles internes, réutilisée à la fois par `_cluster_access_denied()` et
par la vérification `/staff/...` (`OpexStaff._is_staff()`), qui pointe
maintenant vers la même méthode. Ne jamais recréer une seconde liste de
rôles ailleurs — c'est exactement le risque de divergence que la règle
transversale plus haut dans ce document vise à éviter.

---

## Extension 17 — Tableaux de bord

**Dashboard candidat/membre** (`/my`, tuile enrichie ou nouvelle page
`/my/dashboard`) — fidèle à la section 41 : statut adhésion, statut
cotisation en cours, nombre de documents, prochains événements, dernières
actualités, en un coup d'œil.

**Dashboard Secrétariat** (`/staff/dashboard`) — fidèle à la section 42,
agrégats calculés en direct : demandes d'adhésion par état, cotisations
(payées/en attente/en retard), nombre de membres actifs et nouveaux ce
mois, compteurs Vie du Cluster (événements/formations/AG à venir).

---

## Extension 18 — Notifications complètes (tous les déclencheurs du PDF)

Reprend et complète l'infrastructure `mail.thread` déjà présente depuis la
Phase 1 (jamais pleinement exploitée jusqu'ici — voir l'écart identifié
plus haut dans ce document). Implémente **exactement** la liste de la
section 43 :

**Candidat** (11 déclencheurs) : compte créé, dossier reçu, correction
demandée, dossier accepté, dossier refusé, paiement demandé, paiement
confirmé, signature demandée, adhésion activée, renouvellement, événement
important.

**Secrétariat** (5) : nouveau dossier, dossier corrigé (re-soumis),
paiement à vérifier, signature à vérifier, cotisation en retard.

**Comité** (2) : dossier à examiner, nouvelle demande de décision.

**COPIL** (1) : dossier prêt pour validation.

Règles techniques :
- `message_subscribe(partner_ids=[self.partner_id.id])` automatique à la
  création de tout `opex.membership.file`
- Chaque transition de méthode (`action_submit`, `action_validate_*`,
  `action_request_correction`, `action_confirm_payment`, etc.) appelle
  `message_post()` avec un texte correspondant EXACTEMENT à l'esprit de la
  section 43 — pas un texte technique du type `state changed to X`
- Canaux : email (si serveur configuré) + notification portail (la cloche).
  Pas de SMS, explicitement exclu par le document.

---

## Extension 19 — Historique complet (fil chronologique)

Section 44 du PDF. **✅ Fait** — ce n'était pas une simple vérification comme
supposé initialement ici : `opex.membership.file` n'hérite pas de
`portal.mixin`, donc le chatter natif ne s'affichait sur aucune des deux
pages portail (`/my/membership/<id>`, `/staff/membership/<id>`), seulement
en back-office. Un bloc QWeb dédié en lecture seule (journal, pas un widget
de discussion — choix délibéré) a été construit, partagé entre les deux
pages, alimenté par une méthode `_history_entries()` sur le modèle qui
décide elle-même ce que chaque audience peut voir.

**Règle découverte à cette occasion, à respecter pour tout futur
`message_post()` destiné au staff uniquement** : utiliser le sous-type
`mail.mt_note` (interne), jamais `mail.mt_comment` (public) — sinon tout
follower du dossier (le candidat y compris, abonné automatiquement depuis
l'Extension 18) reçoit la notification par email, même quand le message ne
lui est pas destiné. C'est exactement le bug retrouvé et corrigé sur
`_notify_staff` : les destinataires explicites restent notifiés, les
followers non concernés ne le sont plus.

---

## Extension 20 — Cloche de notification custom pour le portail candidat

**Contexte (issu de l'Extension 18) :** Odoo interdit nativement le type de
notification "inbox" pour un compte portail — contrainte `CHECK` en base de
données (`notification_type = 'email' OR NOT share`), pas une question de
configuration. Le systray natif ne peut donc jamais s'afficher pour un
candidat. Le document UX validé décrit pourtant explicitement une cloche
avec badge pour le candidat — décision actée : la construire nous-mêmes
plutôt que de documenter l'écart.

**Principe** : ne pas essayer de contourner ou forcer le système de
notification natif d'Odoo. Construire une vue custom, alimentée par une
simple requête sur les `mail.message` déjà existants (créés normalement par
tous les `message_post()` de l'Extension 18) — ces messages existent
indépendamment de leur `notification_type`, on peut les lire directement.

**Nouveau champ** : `res.partner.notification_last_seen` (Datetime,
nullable). Horodatage de la dernière consultation de la liste de
notifications par ce partner.

**Nouvelles routes** (`controllers/notifications.py`) :
- `GET /my/notifications` — liste les `mail.message` postés sur les
  enregistrements dont le candidat connecté est partenaire (ses
  `opex.membership.file`, ses `opex.subscription`), triés par date
  décroissante, chacun avec un lien vers l'enregistrement concerné.
  **Filtrage de sécurité strict** : ne jamais renvoyer un message lié à un
  enregistrement qui n'appartient pas au candidat connecté — revérifier
  l'appartenance explicitement, ne pas faire confiance à un filtre côté
  client
- `POST /my/notifications/mark_seen` — met à jour
  `notification_last_seen` à l'instant présent pour le candidat connecté

**Widget** : icône cloche + badge (nombre de messages postés après
`notification_last_seen`), visible sur toutes les pages du portail
candidat (dans le header du layout portail). Au clic, affiche la liste
(dropdown en AJAX léger, ou simple page dédiée si plus simple à fiabiliser
pour un POC) ; l'ouverture déclenche `mark_seen`.

**Hors périmètre volontairement** : pas de temps réel (pas de `bus`/
websocket) — un simple chargement au rendu de page suffit, le document UX
ne demande pas de mise à jour instantanée. Ne complique pas inutilement
ce qui reste, fondamentalement, un compteur avec une liste.

---

## Ordre d'implémentation recommandé

**Déjà fait et testé** : Extension 1 (sale.order), Extension 5 (espace
Candidat), Extension 3 (annuaire public + menu), Extension 6 (page de
présentation), Extension 7 (espace de traitement Secrétariat/COPIL/Admin).

**Restant, dans cet ordre strict** — chaque extension dépend des
précédentes, ne pas réordonner :

1. **Extension 8** (fondations : sous-catégories, champs du formulaire,
   workflow étendu, corrections) — tout le reste en dépend, à faire en
   premier et à tester particulièrement soigneusement (migration de données
   sur les enregistrements de test déjà en base)
2. **Extension 9** (Comité d'admission distinct)
3. **Extension 11** (flux de correction) — dépend directement de 8 et 9
4. **Extension 10** (parcours candidat en étapes) — s'appuie sur les champs
   de l'Extension 8, à faire après pour éviter de construire des écrans sur
   un modèle encore instable
5. **Extension 12** (paiement à deux voies)
6. **Extension 13** (signature à deux voies)
7. **Extension 18** (notifications complètes) — fais-la maintenant plutôt
   qu'à la fin : plus facile d'ajouter les `message_post()` au fil de l'eau
   sur des méthodes déjà stables que de tout reprendre après coup
8. **Extension 19** (vérification de l'historique) — rapide, juste après 18
9. **Extension 20** (cloche custom candidat) — décidé suite à la découverte
   de l'Extension 18 (contrainte native Odoo bloquant la cloche pour un
   compte portail) ; dépend de 18 (les messages doivent déjà exister) mais
   pas de 19 directement, peut se faire indépendamment
10. **Extension 14** (annuaire enrichi)
11. **Extension 15** (cotisations post-adhésion)
12. **Extension 2** (calendar.event) — toujours indépendante
13. **Extension 17** (tableaux de bord) — a besoin que le reste existe déjà
    pour avoir quelque chose à agréger
14. **Extension 16** (Vie du Cluster complète) — la plus grosse, en dernier,
    volontairement : c'est la partie la moins critique pour démontrer le
    cœur du parcours d'adhésion en soutenance
15. **Extension 4** — seulement si tout le reste est stable

Teste et commit après **chaque extension**, pas à la fin de tout. Pour
chaque extension touchant au workflow (8, 9, 11, 12, 13), rejoue le test de
bout en bout complet (candidat → secrétariat → comité → COPIL → paiement →
signature → actif) avant de passer à la suivante — un dossier qui se bloque
silencieusement à mi-parcours est plus difficile à diagnostiquer après coup
qu'immédiatement.
