# Sondes de cohérence inter-modules

Onze familles de défauts **silencieux** qui peuvent toucher plusieurs modules à
la fois. Ce sont des scripts de **diagnostic**, pas des tests : ils décrivent
l'état, ils n'affirment rien.

## Pourquoi des sondes et pas des tests

Le balayage du 05/09/2026 a trouvé **une seule** famille avec un défaut vivant.
Cinq familles étaient à zéro, et le mécanisme rend leur récidive improbable :
les identifiants externes sont préfixés par module, et chaque module possède ses
propres modèles — il n'y a pas de surface partagée à protéger.

Un test qui ne peut être que vert coûte à maintenir et occupe la place
(règle 20). Ces cinq familles restent donc des sondes, à rejouer quand la
surface partagée change : un module de plus, un module gelé qu'on rouvre, une
reprise de dépendances.

Les familles qui **avaient** une surface partagée réelle sont devenues des
tests, dans `opex_membership/tests/` :

| Famille | Test |
|---|---|
| Noms partagés sur `CustomerPortal` · même URL, deux méthodes | `test_portal_collisions.py` |
| Liens morts · `t-call` non préfixé · un libellé une URL (en base) | `test_portal_links.py` |
| Contrat de `/my/counters` (règle 6) | `test_portal_counters.py` |
| Surcharges muettes sur un modèle partagé | `test_model_overrides.py` |

## Comment les lancer

Elles lisent le source et la base ; elles n'écrivent rien.

```
# Les sondes purement statiques
venv\Scripts\python.exe custom_addons\opex_membership\docs\sondes\modeles.py
venv\Scripts\python.exe custom_addons\opex_membership\docs\sondes\bis.py
venv\Scripts\python.exe custom_addons\opex_membership\docs\sondes\compteurs.py

# Celles qui interrogent la base, via le shell Odoo
venv\Scripts\python.exe odoo\odoo-bin shell -c odoo.conf -d <base> ^
    --http-port=8191 --log-level=warn --shell-interface=python < ...\secu.py
```

⚠ Les sondes qui lisent le routing map ou `ir.model.data` doivent tourner sur
une base où **tous** les modules à comparer sont installés. `opex_crowdfunding`
vit sur la sienne : sur `opex_mis_e1`, tous ses liens paraissent morts et toutes
ses surcharges absentes.

## Les familles, et ce qu'elles ont donné le 05/09/2026

| Sonde | Famille | Résultat |
|---|---|---|
| `modeles.py` | Méthodes et champs homonymes sur un modèle partagé | 2 méthodes, 4 porteurs, tous relaient · 0 champ |
| `bis.py` | Même URL par deux méthodes · contrat `/my/counters` | 0 · 13/13/13 |
| `compteurs.py` | Le contrat `/my/counters`, en détail | 0 doublon, 0 orphelin, 0 tuile muette |
| `routes.py` | Routes doublées · `t-call` · vues greffées au même endroit | 0 · 0 · 3 parents (dont 20 greffes sur « My Portal ») |
| `secu.py` | `ir.model.access` · `ir.rule` · groupes homonymes | 0 · 0 · 0 |
| `reste.py` | Séquences · crons · sous-types · menus · assets | 0 · 0 · 0 · **1 défaut** · 0 |

## Les trois faux positifs à connaître avant de relire une sortie

Ils comptent : un relevé naïf les produit, et un diagnostic bruyant se fait
ignorer.

1. **Le relais défensif.** `getattr(super(), 'x', None)` est la forme correcte
   quand le parent est optionnel — `opex_crowdfunding` doit rester installable
   sans `opex_membership`. Une sonde qui ne cherche que `super().x()` le
   déclare muet à tort.
2. **La concaténation implicite.** Deux routes du projet sont écrites
   `['/a/<int:x>' '/b']`. Une lecture ligne à ligne n'en voit que le premier
   fragment et déclare identiques deux URL distinctes. Il faut
   `ast.literal_eval` sur le nœud.
3. **Le mot hors contexte.** `member_count` et `category_count` sont les
   valeurs d'une page publique `/cluster`, pas des compteurs de portail. Se
   borner à la forme d'écriture réelle (`values['x_count'] = …`).

## Le défaut trouvé, et pourquoi il ne pouvait pas l'être autrement

« Devenir membre » portait deux URL. `website.menu` garde **deux**
enregistrements par entrée : le modèle par défaut, qui porte le xmlid, et une
copie par site, qui n'en a pas — et c'est la copie qui est servie au visiteur.

La correction de l'URL avait atteint le fichier, le xmlid, et le `<function>`
qui contourne le `noupdate`. Elle n'avait jamais atteint la copie du site 1 :
**la page publique affichait encore le lien mort** pendant que le source et les
tests qui le lisent disaient tous l'inverse.

Aucune lecture statique ne pouvait le voir. C'est ce qui justifie qu'une des
sondes soit devenue un test qui interroge **la base**.
