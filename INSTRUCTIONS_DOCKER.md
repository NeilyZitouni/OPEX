# Lancer le portail GIC OPEX Group avec Docker

Guide destiné à quelqu'un qui découvre le projet. Aucune connaissance d'Odoo
n'est nécessaire, mais Docker doit être installé et démarré.

Le module livré s'appelle **`opex_membership`** : gestion des adhésions,
cotisations, annuaire et vie du cluster du GIC OPEX Group.

---

## 1. Prérequis

- **Docker Desktop** (Windows/macOS) ou **Docker Engine + plugin Compose** (Linux).
  Vérification :
  ```bash
  docker --version
  docker compose version
  ```
- Le dossier du projet, contenant `docker-compose.yml` et
  `custom_addons/opex_membership/`.
- Le fichier **`opex_demo.dump`**, fourni séparément (il ne fait pas partie du
  dépôt). Placez-le à côté de `docker-compose.yml`.

> Les commandes ci-dessous utilisent `docker compose` (Compose V2). Avec une
> version plus ancienne, écrivez `docker-compose` (avec un tiret) à la place.

---

## 2. Démarrer les conteneurs

Depuis le dossier qui contient `docker-compose.yml` :

```bash
docker compose up -d
```

Deux conteneurs démarrent :

| Conteneur  | Rôle                         | Image         |
|------------|------------------------------|---------------|
| `opex_db`  | Base de données PostgreSQL   | `postgres:15` |
| `opex_web` | Serveur Odoo                 | `odoo:19.0`   |

Vérifier que les deux tournent :

```bash
docker compose ps
```

Suivre le démarrage d'Odoo (Ctrl+C pour quitter l'affichage, ça n'arrête pas
le serveur) :

```bash
docker compose logs -f web
```

### ⚠ Conflit de port 8069

**Le port 8069 est celui du serveur Odoo natif** installé sur le poste de
développement d'origine (`odoo.conf`, `http_port = 8069`). Les deux ne peuvent
pas écouter sur le même port en même temps : `docker compose up` échouerait
avec un message du type *port is already allocated*.

Deux solutions, au choix :

- **Arrêter le serveur natif** avant de lancer Docker ;
- **ou publier Docker sur un autre port**, sans rien arrêter :

  ```bash
  ODOO_PORT=8074 docker compose up -d
  ```

  Sous Windows PowerShell :
  ```powershell
  $env:ODOO_PORT = "8074"; docker compose up -d
  ```

  Ou, plus durable, créez un fichier `.env` à côté de `docker-compose.yml` :
  ```
  ODOO_PORT=8074
  ```

  Odoo est alors sur `http://localhost:8074`. Adaptez l'adresse partout dans
  la suite de ce guide.

Sur une machine où aucun Odoo n'est installé — le cas courant — il n'y a
aucun conflit et le port reste **8069**.

---

## 3. Charger la base de données fournie (`opex_demo.dump`)

Le dump contient les données de démonstration : dossiers d'adhésion à
différents stades, membres, cotisations, actualités et événements du cluster.

### 3.1 Copier le dump dans le conteneur

```bash
docker cp opex_demo.dump opex_db:/tmp/opex_demo.dump
```

### 3.2 Créer la base vide

```bash
docker compose exec db createdb -U odoo -T template0 odoo19
```

> Le nom `odoo19` est celui utilisé par le projet. Vous pouvez en choisir un
> autre, mais gardez le même dans toutes les commandes qui suivent.

### 3.3 Restaurer

```bash
docker compose exec db pg_restore -U odoo -d odoo19 --no-owner --role=odoo /tmp/opex_demo.dump
```

`--no-owner --role=odoo` réattribue tous les objets à l'utilisateur `odoo` du
conteneur, quel que soit le nom du propriétaire d'origine.

Quelques avertissements en fin de restauration (extensions déjà présentes,
commentaires ignorés) sont normaux et sans conséquence.

### 3.4 ⚠ Si la restauration échoue sur la version

Message du type :

```
pg_restore: error: unsupported version (1.16) in file header
```

**Cause :** le dump a été produit par un `pg_dump` **plus récent** que le
PostgreSQL du conteneur. Le poste d'origine tourne sous PostgreSQL **17/18**,
alors que `docker-compose.yml` demande **`postgres:15`**. Un pg_restore 15 ne
sait pas lire une archive écrite par un pg_dump 17 ou 18 — l'inverse
fonctionne, mais pas ce sens-là.

**Solution la plus simple :** alignez la version de l'image. Dans
`docker-compose.yml`, remplacez :

```yaml
image: postgres:15
```

par `postgres:17` (ou `postgres:18`, selon la version qui a produit le dump),
puis repartez d'un volume propre :

```bash
docker compose down -v
docker compose up -d
```

> `down -v` **supprime les volumes**, donc toutes les données déjà chargées.
> C'est sans risque tant que la seule source de vérité reste `opex_demo.dump`.

Pour savoir quelle version a produit le dump :

```bash
docker compose exec db pg_restore --list /tmp/opex_demo.dump | head -5
```

### 3.5 Alternative recommandée : la sauvegarde Odoo (base + pièces jointes)

Si le dump n'a pas encore été produit, il existe une méthode plus robuste que
`pg_dump`/`pg_restore`, qui règle d'un coup **le problème de version** et
celui **des pièces jointes** (voir section 6) :

1. Sur la machine d'origine, ouvrir `http://localhost:8069/web/database/manager`
2. **Backup** → format **zip** → télécharger
3. Sur la machine cible, ouvrir `http://localhost:8069/web/database/manager`
4. **Restore** → choisir le fichier `.zip` → nommer la base `odoo19`

Le `.zip` contient le SQL **et** le filestore. Il n'y a alors rien à faire des
sections 3.1 à 3.4 ni de la section 6.

---

## 4. Installer ou mettre à jour le module

La base restaurée contient déjà `opex_membership` installé. Il reste à le
mettre à jour pour que le code monté depuis le disque soit pris en compte :

```bash
docker compose stop web
docker compose run --rm web odoo -d odoo19 -u opex_membership --stop-after-init
docker compose start web
```

Sur une base **vierge** (sans dump), remplacez `-u` (update) par `-i`
(install) :

```bash
docker compose run --rm web odoo -d odoo19 -i opex_membership --stop-after-init
```

À refaire après chaque modification du code du module. Un simple
`docker compose restart web` suffit en revanche pour les changements qui ne
touchent ni les vues, ni les modèles, ni les données.

> `docker compose stop web` avant l'opération évite que deux processus Odoo
> écrivent dans la même base au même moment.

---

## 5. Accéder à Odoo et se connecter

Ouvrir **<http://localhost:8069>** (ou le port choisi en section 2).

- Si une seule base existe, Odoo s'y connecte directement.
- Sinon, il affiche la liste des bases : choisir **`odoo19`**.

**Identifiants :** ce sont ceux de la base fournie dans le dump — ils ne sont
pas définis par ce guide. Demandez-les à l'auteur du projet.

Pour lister les comptes existants :

```bash
docker compose exec db psql -U odoo -d odoo19 -c "SELECT login FROM res_users WHERE active = true ORDER BY id;"
```

Si aucun mot de passe n'est connu, on peut en définir un :

```bash
docker compose run --rm web odoo shell -d odoo19
```
puis, à l'invite Python :
```python
env['res.users'].search([('login', '=', 'admin')]).password = 'un_mot_de_passe'
env.cr.commit()
```
(`Ctrl+D` pour quitter.)

### Où regarder une fois connecté

- **`/cluster`** — page de présentation publique du cluster
- **`/opex/directory`** — annuaire public des membres
- **`/my`** — espace du candidat/membre : dossiers, cotisations, Vie du Cluster
- **`/staff/membership`** — espace de traitement (Secrétariat / Comité / COPIL)
- **`/staff/dashboard`** — tableau de bord interne

Le menu principal du site affiche **Vie du Cluster** uniquement aux membres
actifs et au personnel interne : son absence pour un compte candidat est le
comportement attendu, pas un défaut d'installation.

---

## 6. ⚠ Pièces jointes : le dump SQL ne les contient pas

Odoo ne stocke pas les fichiers téléversés dans la base, mais sur disque, dans
un dossier appelé **filestore**. Un dump `pg_dump` ne contient **que** la base.

Conséquence : après une restauration par `pg_restore`, les documents des
dossiers d'adhésion (registres de commerce, statuts, justificatifs de
paiement, chartes signées) apparaissent dans l'interface mais leur
téléchargement échoue.

Deux façons de régler cela :

- **La sauvegarde `.zip` d'Odoo** (section 3.5) — elle embarque le filestore ;
- **ou copier le filestore à la main.** Sur la machine d'origine il se trouve
  dans le `data_dir` d'Odoo, sous `filestore/<nom_de_la_base>` (sous Windows :
  `C:\Users\<vous>\AppData\Local\OpenERP S.A.\Odoo\filestore\odoo19`) :

  ```bash
  docker cp "chemin/vers/filestore/odoo19" opex_web:/var/lib/odoo/filestore/odoo19
  docker compose exec -u root web chown -R odoo:odoo /var/lib/odoo/filestore
  docker compose restart web
  ```

Si la démonstration ne porte pas sur les documents téléversés, ce point peut
être ignoré : tout le reste du parcours fonctionne sans le filestore.

---

## 7. Commandes utiles

| Objectif                              | Commande                                            |
|---------------------------------------|-----------------------------------------------------|
| Démarrer                              | `docker compose up -d`                              |
| Arrêter (en gardant les données)      | `docker compose stop`                               |
| Arrêter et supprimer les conteneurs   | `docker compose down`                               |
| **Tout effacer, volumes compris**     | `docker compose down -v`                            |
| Journaux d'Odoo en direct             | `docker compose logs -f web`                        |
| Console PostgreSQL                    | `docker compose exec db psql -U odoo -d odoo19`     |
| Terminal dans le conteneur Odoo       | `docker compose exec web bash`                      |
| Console Python Odoo                   | `docker compose run --rm web odoo shell -d odoo19`  |
| Mot de passe maître (gestion des bases)| `docker compose exec web cat /etc/odoo/odoo.conf`  |

---

## 8. Dépannage

**`port is already allocated` au démarrage**
Le port 8069 est déjà pris — presque toujours par un Odoo natif. Voir la
section 2.

**Odoo affiche « Database not initialized » ou une liste vide**
Le dump n'a pas été chargé, ou sous un autre nom. Vérifier :
```bash
docker compose exec db psql -U odoo -l
```

**Le module n'apparaît pas dans la liste des applications**
Vérifier que le montage est correct :
```bash
docker compose exec web ls /mnt/extra-addons/opex_membership
```
Le dossier doit contenir `__manifest__.py`. Puis, dans Odoo :
**Apps → Update Apps List**, en ayant activé le mode développeur.

**Modification du code sans effet**
Les vues, modèles et données ne sont relus qu'à la mise à jour du module :
refaire la section 4.

**`could not connect to server` dans les journaux d'Odoo**
PostgreSQL met quelques secondes à accepter les connexions au premier
démarrage. Odoo réessaie ; si l'erreur persiste :
```bash
docker compose restart web
```

---

## 9. Ce que ce montage ne fait pas

- **Aucune image n'est construite** : pas de `Dockerfile`. Les sources Odoo du
  dossier `odoo/` ne sont pas utilisées — l'image officielle `odoo:19.0`
  fournit le même code. Seul `custom_addons/opex_membership` est monté.
- **Aucun serveur de messagerie** n'est configuré : les notifications sont
  bien enregistrées dans l'historique des dossiers et dans la cloche du
  portail, mais aucun e-mail ne part réellement.
- **Ce n'est pas une configuration de production** : mots de passe simples
  (`odoo`/`odoo`), pas de HTTPS, pas de reverse proxy, base exposée sans
  restriction sur le réseau du conteneur. C'est un environnement de
  démonstration et d'évaluation.
