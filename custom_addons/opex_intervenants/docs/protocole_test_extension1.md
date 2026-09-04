# Protocole de test manuel — Extension 1

Dérouler **les deux workflows de bout en bout dans le back-office**, boucles
comprises. Comptez 25 minutes.

Ce protocole ne teste pas le portail : il n'y en a pas à ce stade. Il teste ce
que l'Extension 1 livre — deux machines à états configurées, six rôles, et leur
indépendance.

---

## 0. Préparer

### 0.1 Installer sur une base neuve

```bash
cd C:/Users/User/Desktop/stageDeltaLog
venv/Scripts/python.exe odoo/odoo-bin -c odoo.conf -d opex_mis_demo \
    -i opex_intervenants --stop-after-init --http-port=8072
```

### 0.2 Créer les six comptes

Créer six utilisateurs à la main coûte dix minutes et une faute de frappe. Le
script ci-dessous les pose avec des mots de passe connus. Copiez-le dans un
fichier `setup_demo.py`, puis :

```bash
venv/Scripts/python.exe odoo/odoo-bin shell -c odoo.conf -d opex_mis_demo \
    --http-port=8072 < setup_demo.py
```

```python
COMPTES = [
    ('client',    'Entreprise XYZ',      'base.group_portal'),
    ('expert',    'Karim Belhadj',       'base.group_portal'),
    ('expert2',   'Amina Cherif',        'base.group_portal'),
    ('secr',      'Secrétariat OPEX',    'base.group_user,opex_membership.group_secretariat'),
    ('manager',   'Responsable mission', 'base.group_user,opex_intervenants.group_mission_manager'),
    ('decideur',  'Comité de sélection', 'base.group_user,opex_intervenants.group_mission_committee'),
]
for login, name, groups in COMPTES:
    user = env['res.users'].search([('login', '=', login)], limit=1)
    if not user:
        user = env['res.users'].create({
            'name': name, 'login': login, 'password': login,
            'group_ids': [(6, 0, [env.ref(g).id for g in groups.split(',')])],
        })
    print('%-10s / mot de passe : %s' % (login, login))

# Une compétence, pour que la demande soit soumissible.
if not env['opex.innovation.competence'].search([('code', '=', 'demo_ssi')]):
    env['opex.innovation.competence'].create({
        'name': "Sécurité des systèmes d'information", 'code': 'demo_ssi'})
env.cr.commit()
print("Comptes prêts.")
```

### 0.3 Lancer le serveur

```bash
venv/Scripts/python.exe odoo/odoo-bin -c odoo.conf -d opex_mis_demo \
    --http-port=8072 --limit-time-real=0
```

> **Port 8072, pas 8069.** `SO_REUSEADDR` fait qu'une seconde instance se lie
> sans erreur sur 8069 et intercepte les requêtes : vous testeriez un serveur
> fantôme, et les routes neuves répondraient 404.
>
> `--limit-time-real=0`, sinon le serveur meurt au bout de deux minutes dès
> qu'un onglet reste ouvert.

Ouvrir `http://localhost:8072`. Se connecter et se reconnecter selon les rôles.

### 0.4 Ce que vous devez voir avant de commencer

| Vérification | Attendu |
|---|---|
| Menu **OPEX Intervenants** | visible pour `manager`, `decideur`, `secr` — **absent** pour `client` et `expert` |
| **Configuration → Types de mission** | 6 lignes ; **Formation** et **Coaching** ont « Plusieurs intervenants autorisés » coché |
| **Configuration → Domaines d'expertise** | 8 lignes |
| Menu **Configuration** | visible pour `manager` seul, pas pour `decideur` ni `secr` |

---

## 1. Le workflow de la MISSION — 14 étapes

### 1.1 Créer la demande — `manager`

`OPEX Intervenants → Appels à mission → Nouveau`

| Champ | Valeur |
|---|---|
| Titre | Audit cybersécurité |
| Type de mission | Audit |
| Client | Entreprise XYZ |
| Description | Audit du SI industriel. |
| Objectifs | Cartographier et hiérarchiser les vulnérabilités. |
| Domaine (onglet *Profil recherché*) | Cybersécurité |
| Compétences | Sécurité des systèmes d'information |
| Date limite de candidature (onglet *Organisation*) | **dans 30 jours** |
| Début souhaité | dans 45 jours |
| Fin souhaitée | dans 60 jours |

Enregistrer.

> **À vérifier**
> - la **référence** `MIS-2026-nnnn` s'affiche au-dessus du titre, en gris ;
> - le **statusbar** montre les 14 étapes, positionné sur **Brouillon** ;
> - sous le titre, le libellé **« Compléter ma demande »** — pas `draft` ;
> - il n'y a **aucun champ « État »** dans le formulaire. C'est le point.

### 1.2 Le contrôle des dates

Mettre *Fin souhaitée* **avant** *Début souhaité*, enregistrer.

> Message d'erreur nommant les deux dates. Annuler la modification.

### 1.3 La condition de soumission

Vider les **Compétences**, enregistrer, puis **Action**.

> Le wizard propose « Soumettre ma demande » suivi de
> **« — indisponible : Complétez le titre, le type de mission… »**.
> La transition n'est pas cachée, elle est expliquée. Fermer, remettre la
> compétence.

### 1.4 Soumettre — `client`

Se reconnecter en `client`. Le menu OPEX Intervenants n'existe pas pour lui :
ouvrir la mission par son URL, ou rester en `manager` pour la suite si vous
voulez aller vite — mais **la soumission doit être faite par le client**, c'est
son rôle qui la porte.

> Le plus simple : rester en `manager`, cliquer **Action**, et constater que
> « Soumettre ma demande » **n'est pas proposée** — le responsable ne porte pas
> le rôle Client. Puis se connecter en `client` pour la franchir.

`Action → Soumettre ma demande → Confirmer`

> Statusbar sur **Qualification**, libellé
> « Demande en cours de qualification ».

### 1.5 BOUCLE 1 — le complément demandé — `secr`

Se connecter en `secr`. `Action → Demander un complément`.

> Le wizard **exige un commentaire** : confirmer sans rien saisir est refusé.

Saisir « Le périmètre technique n'est pas décrit. », confirmer.

> Statusbar **revenu sur Brouillon**. La boucle du Schéma 3 existe.

Se reconnecter en `client`, modifier la **Description**, enregistrer.

> L'enregistrement passe : le retour en brouillon rend au client le droit
> d'écrire. (En Qualification, la même modification est refusée — c'est
> l'`ir.rule` bornée par l'étape.)

`Action → Soumettre ma demande` à nouveau.

### 1.6 Publier — `manager`

`Action → Publier l'appel`

> Statusbar sur **Sourcing**, libellé « Appel publié — recherche
> d'intervenants », et la case **Publié** de l'en-tête est maintenant cochée
> — sans que personne ne l'ait cochée. C'est une projection de l'étape.

**Variante à essayer** : reculer la date limite dans le passé avant de publier.
Le wizard affiche « — indisponible : La date limite de candidature est déjà
passée ».

`Action → Ouvrir les candidatures` → statusbar sur **Appel ouvert**.

### 1.7 Clore sans candidature

`Action → Clore les candidatures`

> « — indisponible : Aucune candidature n'a encore été déposée ».
> On enchaîne donc sur le second workflow.

---

## 2. Le workflow de la CANDIDATURE — 10 étapes

### 2.1 Créer la candidature — `manager`

`OPEX Intervenants → Candidatures → Nouveau`

| Champ | Valeur |
|---|---|
| Intervenant | Karim Belhadj |
| Appel | MIS-2026-nnnn |
| Origine | Smart Matching |

Enregistrer.

> **Un second statusbar, différent du premier** : 10 étapes, positionné sur
> **Opportunité proposée**. C'est la démonstration à l'écran : deux modèles,
> deux définitions, deux barres.
> Toujours **aucun champ « État »**.

### 2.2 BOUCLE 2 — le refus, puis le retour — `expert`

Se connecter en `expert` (Karim). Ouvrir sa candidature.

`Action → Je ne suis pas disponible` → statusbar sur **Déclinée**.

> Le bouton **Action reste actif**. Une fin ordinaire fermerait l'instance et
> le bouton disparaîtrait : `Déclinée` est **réversible**, c'est l'arbitrage Q1.

`Action → Finalement, cela m'intéresse` → statusbar sur **Consultée**.

> Sans cette transition, la contrainte `unique(mission_id, partner_id)`
> fermerait l'appel définitivement à cet expert.

### 2.3 Candidater — `expert`

`Action → Je suis intéressé` → **Intéressé**, libellé « Compléter ma
candidature ».

Onglet *Proposition* : Disponibilité **Disponible**, Délai **10**, Type **TJM**,
Tarif **25 000**, Motivation libre, **Conditions acceptées** cochée. Enregistrer.

`Action → Envoyer ma candidature` → **Candidature déposée**.

> Essayer maintenant de modifier le tarif : **refusé**. La version examinée
> doit être celle que le responsable a lue.
> Essayer sans remplir le formulaire : « — indisponible : Renseignez votre
> disponibilité, votre délai… ».

### 2.4 BOUCLE 3 — le renvoi à l'analyse

En `manager` : `Action → Qualifier la candidature` → **Qualifiée**, puis
`Action → Mettre en short-list` → **Short-listée**.

En `decideur` : `Action → Renvoyer à l'analyse` → **retour sur Qualifiée**.

En `manager` : `Action → Mettre en short-list` à nouveau.

### 2.5 Retenir — `decideur`

`Action → Retenir cette candidature` (commentaire obligatoire) → **Retenue**.

> En `manager`, cette action n'est **pas proposée** : elle appartient au
> comité.

---

## 3. L'INDÉPENDANCE DES DEUX MACHINES

**C'est le test qui compte** — septième critère d'acceptation du §21.

### 3.1 Trois candidatures dans trois étapes

Créer deux candidatures de plus sur le **même** appel, en `manager` :

| Intervenant | Amener à | Comment |
|---|---|---|
| Amina Cherif | **Candidature déposée** | Consulter → Je suis intéressé → remplir → Envoyer |
| Entreprise XYZ | **Non retenue** | `Action → Retirer l'invitation` + motif |

Ouvrir `Candidatures`, filtrer sur l'appel, **Regrouper par → Étape**.

> Quatre candidatures dans **quatre étapes différentes** : Retenue, Déposée,
> Non retenue — et l'appel, lui, est toujours sur **Appel ouvert**.

### 3.2 La mission n'a pas bougé

Retourner sur l'appel.

> Statusbar toujours sur **Appel ouvert**. Aucune des quatre candidatures ne
> l'a fait avancer.

### 3.3 La règle 3 — pas deux fois le même

Créer une candidature de **Karim Belhadj** sur le **même** appel.

> Refus en base : « Cet intervenant a déjà une candidature sur cet appel ».
> C'est une contrainte SQL, pas un contrôle applicatif.

### 3.4 La règle 4 — un seul retenu

Amener Amina jusqu'à **Short-listée**, puis `Action → Retenir cette candidature`.

> « — indisponible : Une candidature est déjà retenue sur cet appel, et ce
> type de mission n'autorise qu'un seul intervenant. »

**L'exception** : `Configuration → Types de mission`, cocher « Plusieurs
intervenants autorisés » sur **Audit**. Réessayer.

> La sélection passe. La règle 4 est un **paramétrage**, pas du code.
> Décocher pour la suite.

---

## 4. La fin du parcours mission

En `manager` : `Action → Clore les candidatures` → **Sélection**.

> La condition est satisfaite : des candidatures ont été **déposées**.
> Une invitation seule ne suffit pas.

| Rôle | Action | Étape atteinte |
|---|---|---|
| `decideur` | Attribuer la mission *(commentaire)* | **Attribuée** |
| `secr` | Lancer la contractualisation | **Contractualisation** |
| `manager` | Démarrer la mission | **Exécution** |
| `manager` | Soumettre les livrables | **Livrables remis** |

### BOUCLE 4 — les corrections

`manager` : `Action → Demander des corrections` *(commentaire)* → **retour sur
Exécution**. Puis `Action → Soumettre les livrables` à nouveau.

| Rôle | Action | Étape atteinte |
|---|---|---|
| `manager` | Valider le service fait | **Service fait** |
| `secr` | Facturer et clôturer *(commentaire)* | **Clôturée** |

> Le bouton **Action disparaît** : l'instance est terminée.

---

## 5. Contrôle final

| Point | Où le voir | Attendu |
|---|---|---|
| Les 4 boucles ont laissé une trace | Chatter de l'appel | deux passages par Brouillon, deux par Exécution |
| L'historique est complet | `Smart Workflow → Instances` → l'instance de l'appel → onglet Historique | 15 lignes, avec auteur, date et motif |
| L'historique est **immuable** | tenter d'y modifier un commentaire | refusé, même en administrateur |
| Les deux instances sont distinctes | `Smart Workflow → Instances` | une sur `opex.mission.request`, une par candidature sur `opex.mission.application` |
| Les définitions sont publiées | `Smart Workflow → Définitions` | `mission_request` et `mission_application` en **Publié** |
| Le graphe est cohérent | ouvrir une définition → **Valider le graphe** | « 14 étapes, 32 transitions » / « 10 étapes, 20 transitions » |

---

## Ce que ce protocole ne teste pas, et pourquoi

- **Aucun email ne part** : le SMTP n'est pas configuré dans cet environnement.
  Les notifications se vérifieront dans le chatter et dans `mail.message`.
  De toute façon, **aucune action n'est configurée sur les transitions** à ce
  stade — elles viendront avec les objets qu'elles manipulent (E4, E7, E11).
- **Aucun écran portail** : le client et l'intervenant travaillent ici dans le
  back-office. Leur parcours arrive aux Extensions 2 et 5.
- **Aucun score** : l'onglet « Explication du score » d'une candidature affiche
  un encart qui le dit. C'est l'Extension 4.
- **Le rôle Intervenant sur la mission n'a pas de porteur** : « Démarrer la
  mission » et « Soumettre les livrables » lui sont ouvertes, mais l'intervenant
  retenu n'est acteur que de sa *candidature*. C'est l'Extension 7 qui posera
  cet acteur à l'attribution ; d'ici là, le responsable franchit ces deux
  transitions.
