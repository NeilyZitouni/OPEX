# Protocole de test manuel — Extension 2 : la demande client

Se met dans la peau d'un **client**, avec un vrai compte portail. Comptez
20 minutes.

Ce protocole ne teste pas le back-office : il a le sien
(`protocole_test_extension1.md`). Il teste les cinq écrans du §7, le brouillon
auto-sauvegardé, le tableau de bord du §6, et la règle du §8 — la demande ne
devient pas publique toute seule.

---

## 0. Préparer

### 0.1 Le serveur

```bash
cd C:/Users/User/Desktop/stageDeltaLog
venv/Scripts/python.exe odoo/odoo-bin -c odoo.conf -d opex_mis_demo \
    --http-port=8072 --limit-time-real=0
```

> **Port 8072.** Sur 8069, `SO_REUSEADDR` laisse une seconde instance se lier
> sans erreur : les routes neuves répondraient 404 et vous chercheriez le bug
> dans le code.

### 0.2 Les comptes

Ceux du protocole de l'Extension 1 suffisent. Il faut au minimum :

| Login | Mot de passe | Rôle |
|---|---|---|
| `client` | `client` | portail — c'est lui qui dépose |
| `client2` | `client2` | portail — pour l'étanchéité du §3 |
| `secr` | `secr` | secrétariat — pour renvoyer le dossier au §5 |
| `manager` | `manager` | responsable — pour publier au §6 |

Si `client2` n'existe pas, ajoutez-le au script `setup_demo.py` du protocole
précédent : `('client2', 'Entreprise ABC', 'base.group_portal')`.

### 0.3 Une compétence au moins

L'écran 2 exige au moins une compétence recherchée. Si le référentiel est vide,
la page le dit — mais on ne pourra pas avancer. En back-office :
`OPEX Innovation → Configuration → Compétences`, ou par le shell.

---

## 1. La tuile d'accueil — et le piège qu'elle porte

Se connecter en **`client`**, aller sur **`http://localhost:8072/my`**.

> **Une tuile « OPEX Intervenants — demander une intervention »**, alors que
> ce client n'a **aucune** demande.
>
> C'est tout l'intérêt de `config_card` : sans lui, `portal.portal_docs_entry`
> met la tuile en `d-none` tant que le compteur est nul — elle disparaîtrait
> exactement pour celui qui en a le plus besoin.

> **Ouvrez la console du navigateur (F12) et rechargez.**
>
> - Aucune erreur JavaScript.
> - **Aucun spinner qui reste** sur la page. `portal_home_counters.js` retire
>   `.o_portal_doc_spinner` **après** le `Promise.all` : un spinner encore
>   visible signifie qu'une promesse a été rejetée et que tout le JS de
>   l'accueil est mort — pour toutes les tuiles, pas seulement la mienne.
>
> Aucune requête HTTP ne remplace cette vérification : `url_open()` lit le HTML
> rendu par le serveur et passe au vert pendant qu'une exception JS vide la
> page.

Vérifier aussi que les tuiles des autres modules sont toujours là : **OPEX
Innovation**, **mon adhésion**, **mes notifications**.

---

## 2. §7 — Les cinq écrans

Cliquer la tuile → `/my/missions` → **« + Créer une demande de mission »**.

### Écran 1 — Informations générales

> Le fil affiche **cinq pastilles** : Informations générales · Profil
> recherché · Organisation · Budget · Documents. Pas six — le récapitulatif est
> la page de soumission, pas un écran de saisie.
>
> La page ne demande **que** les quatre champs du §7 étape 1. Pas de budget,
> pas de compétences : « jamais un formulaire monolithique ».

**Test du champ obligatoire** : valider avec le titre vide.

> Message de page, pas d'erreur serveur.

Remplir : Titre *Audit cybersécurité*, Type *Audit*, Description et Objectifs
libres. **Continuer**.

> **Le brouillon est déjà créé.** L'URL passe à `/my/missions/<id>/profil` —
> l'identifiant est dans l'URL, jamais dans un champ caché.

### Test du brouillon auto-sauvegardé

**Fermez l'onglet ici**, sans rien valider d'autre. Rouvrez `/my/missions`.

> Bandeau **« Vous avez une demande en cours de saisie : Audit
> cybersécurité »** avec un bouton **Reprendre**.
>
> Sans lui, un client revenu deux jours plus tard recommencerait une saisie
> qu'il a déjà faite.

Cliquer **Reprendre**.

### Écran 2 — Profil recherché

Valider **sans cocher de compétence**.

> « Le domaine et au moins une compétence recherchée sont obligatoires. »
> On le dit ici plutôt que de laisser le client le découvrir trois écrans plus
> loin, au moment de soumettre.

Choisir un domaine, **cocher au moins deux compétences**, renseigner
l'expérience minimale. **Continuer**.

> Revenez sur cet écran après coup (bouton Retour depuis l'écran 3) :
> **les deux cases doivent être encore cochées**. Une seule case retenue
> signalerait que le code lit `post.get()` au lieu de `getlist()` — un
> formulaire qui coche plusieurs valeurs du même nom n'en transmet qu'une à
> `post.get()`, et le client verrait sa sélection réduite au dernier choix
> sans qu'aucune erreur ne le signale.

### Écran 3 — Organisation

Dates de début et de fin, localisation, wilaya, mode d'intervention.
**Continuer**.

**Test de cohérence** : mettre une date de fin **avant** la date de début.

> La page revient avec le message de la contrainte de modèle, nommant les
> deux dates. Le client n'a pas d'erreur serveur.

### Écran 4 — Budget

Saisir le budget **avec une virgule et un espace** : `250 000,50`.

> Accepté. Un `float()` nu aurait rendu une erreur serveur là où le client
> attend un formulaire.

Renseigner le type de rémunération et les modalités. **Continuer**.

### Écran 5 — Documents

Déposer un PDF comme **Cahier des charges**.

> Il apparaît dans le tableau, avec son type et son nom de fichier.

**Trois refus à éprouver** :

| Essai | Attendu |
|---|---|
| Déposer sans libellé | « Donnez un libellé à la pièce. » |
| Déposer un `.html` ou un `.svg` | « Ce type de fichier n'est pas accepté. » |
| Déposer un fichier > 10 Mo | « Le fichier dépasse 10 Mo. » |

> Le refus du HTML et du SVG n'est pas cosmétique : servis en ligne, ils
> s'exécuteraient dans la session de celui qui les ouvre.

**Retirer** la pièce, puis la redéposer. Cliquer **Vérifier et soumettre**.

---

## 3. §8 — La demande ne devient pas publique

### Le récapitulatif

> Les cinq pastilles sont **toutes** marquées franchies.
>
> Le récapitulatif reprend ce qui a été saisi : référence `MIS-2026-nnnn`,
> titre, type, domaine, compétences, période, mode, budget, nombre de pièces.
>
> **L'encart bleu le dit avant le clic** :
> « Votre demande est transmise au cluster, qui la vérifie. Elle **ne devient
> pas publique automatiquement**. »

Cliquer **Soumettre la demande** **sans cocher** la case.

> « Cochez la case de confirmation ». Rien n'a bougé.

Cocher, puis soumettre.

> Redirection vers `/my/missions/<id>`, état **« Demande en cours de
> qualification »** — en toutes lettres, jamais `qualified`.

### La vérification qui compte

En back-office (compte `manager`) : `OPEX Intervenants → Appels à mission`,
ouvrir la demande.

> Statusbar sur **Qualification**.
> **La case « Publié » est décochée.** La demande du client n'a rien publié :
> c'est une transition du cluster qui le fera, et `is_published` est calculé
> depuis l'étape — aucun écran ne peut le cocher.

### Le dossier n'est plus modifiable

Revenir en `client` et forcer l'URL `/my/missions/<id>/budget`.

> Redirection vers `/my/missions`. L'écran de saisie n'est plus servi : la
> version que le contrôleur examine doit être celle qu'il a lue.

---

## 4. L'étanchéité entre clients

Relever l'identifiant de la demande dans l'URL. Se déconnecter, se connecter
en **`client2`**, et forcer `/my/missions/<id>` avec cet identifiant.

> Redirection vers `/my/missions`, **et le titre « Audit cybersécurité »
> n'apparaît nulle part dans la page**.
>
> Vérifiez-le dans le **code source** de la page (Ctrl+U), pas seulement à
> l'œil : « présent dans le HTML » ≠ « visible à l'écran ». Une donnée rendue
> puis masquée en CSS reste une fuite.

Essayer aussi de poster sur `/my/missions/<id>/budget` depuis ce compte — par
exemple avec la console du navigateur. Le montant ne doit pas bouger.

---

## 5. La boucle du §8 — le dossier renvoyé

Se connecter en **`secr`** (back-office). Ouvrir la demande.
`Action → Demander un complément`, motif :
*« Le périmètre technique n'est pas décrit. »*

Revenir en **`client`**, aller sur `/my/missions`.

> Un encart **orange** « Action requise », avec le motif.
>
> **Et surtout : pas** le bandeau bleu « Vous avez une demande en cours de
> saisie ». Le dossier renvoyé est pourtant à la même étape `draft` que la
> saisie en cours — ce qui les distingue, c'est l'historique. Sans cette
> distinction, « Créer une demande » reprendrait le dossier que le contrôleur
> attend.

Ouvrir la demande → **Compléter ma demande** → corriger l'écran 2 ou 4 →
resoumettre par le récapitulatif.

> La demande repart en Qualification.
> L'historique en bas de la fiche montre **deux passages** par « Compléter ma
> demande » et deux par « Demande en cours de qualification ».

**Deuxième retour, pour éprouver le motif** : faire renvoyer le dossier une
seconde fois par `secr`, avec un motif **différent**.

> C'est le **second** motif qui s'affiche, pas le premier. Le motif est lu
> dans l'historique en compréhension : avec `mapped()`, le second passage par la
> même étape serait dédupliqué et on afficherait un motif déjà traité.

---

## 6. §6 — Le tableau de bord

Sur `/my/missions`, en `client`.

> Les quatre indicateurs du §6, dans son ordre : **Mes demandes · Appels en
> cours · Missions en cours · Missions terminées**.
> Le bouton **« + Créer une demande de mission »**.

Faire publier l'appel : en `manager`, renseigner une **date limite de
candidature future**, puis `Action → Publier l'appel`.

Recharger `/my/missions` en `client`.

> **Appels en cours** passe à 1, **Mes demandes** reste à 1.
> La ligne du tableau affiche l'état « Appel publié — recherche
> d'intervenants » et la colonne Candidatures montre `0` au lieu de `—`.
>
> Aucun compteur n'a été écrit nulle part : ils sont recalculés à chaque
> affichage depuis les étapes. Un agrégat mémorisé se décorrélerait du réel à
> la première transition.

Recharger `/my` : le compteur de la tuile doit afficher **1**.

---

## 7. Contrôle final

| Point | Où | Attendu |
|---|---|---|
| Aucune route voisine perdue | back-office → `Paramètres → Technique` ou le test automatique | `/my/innovation/missions`, `/my/membership/new`, `/my/notifications` répondent toujours |
| Le client ne voit pas le back-office | menu principal en `client` | pas de menu **OPEX Intervenants** |
| L'historique est complet | fiche de la demande, bas de page | une ligne par passage, motifs compris |
| Rien n'a été publié par le client | back-office, case **Publié** | décochée tant que le cluster n'a pas publié |

---

## Ce que ce protocole ne teste pas, et pourquoi

- **Aucun email ne part** : le SMTP n'est pas configuré. Et aucune action
  `notify` n'est configurée sur les transitions à ce stade — les notifications
  du §34 sont l'Extension 11.
- **Aucun matching, aucune candidature** : Extensions 4 et 5. La colonne
  « Candidatures » affichera 0 tant que personne ne peut candidater.
- **Le catalogue public `/missions`** : Extension 12. Ici, tout se passe sous
  un compte authentifié.
- **Le client n'a pas d'écran de contrat, de livrable ni de facture** : le §6
  les cite dans ses actions principales ; ils arrivent avec les objets
  correspondants (Extensions 7 à 9).
