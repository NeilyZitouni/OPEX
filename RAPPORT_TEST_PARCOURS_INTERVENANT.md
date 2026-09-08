# Rapport de test — parcours candidat / intervenant (Module 3)

**Date :** 8 septembre 2026
**Méthode :** sessions HTTP réelles contre un serveur Odoo en fonctionnement.
Connexion par `/web/login` avec jeton CSRF, formulaires postés avec les noms de
champs réellement rendus par les gabarits, comptes portail et personnel distincts.
**Aucun appel ORM n'a été utilisé pour tester** — l'ORM n'a servi qu'à créer les
comptes de départ.

**Base de test :** `opex_parcours`, copie isolée de `opex_mis_e1` (base + filestore),
pour ne rien écrire dans la base de développement.

**Comptes utilisés :**

| Compte | Rôle | Profil expert |
|---|---|---|
| `pt_client` | client portail | — |
| `pt_expert` | intervenant portail | profil **activé** |
| `pt_externe` | membre portail | **aucun profil** au départ |
| `pt_staff` | responsable de mission (+ gestionnaire de workflow) | — |

---

## Résumé

**Le parcours était bloqué dès le premier maillon, et c'est presque certainement
là que le test manuel s'est arrêté.** Un appel à mission déposé au portail ne
pouvait **jamais** être publié : sa publication exige une date limite de
candidature qu'aucun écran du portail — ni côté client, ni côté responsable — ne
permettait de saisir. Sans appel publié, il n'y a pas de catalogue, donc pas de
candidature possible, donc aucun parcours intervenant du tout.

Quatre défauts ont été corrigés, trois défauts ou limites restent documentés.
Après correction, **le parcours complet se déroule de bout en bout sans jamais
ouvrir le back-office** : dépôt du besoin → publication → catalogue public →
candidature → dépôt → qualification → short-list → sélection → contrat signé des
deux côtés → contrat validé → mission démarrée.

| | Nombre |
|---|---|
| Défauts trouvés | 7 |
| Corrigés et vérifiés | 4 |
| Documentés, non corrigés | 3 |
| Régressions introduites | 0 — suite `opex_intervenants` : **491 tests, 0 échec** |

---

# Ce qui a été corrigé

## C1 — La date limite de candidature n'était saisissable nulle part au portail 🔴 bloquant

**Gravité : bloquant.** C'est le défaut qui arrête tout le reste.

**Reproduction**
1. Se connecter en client portail, déposer une demande complète par
   `/my/missions/new` puis les quatre écrans suivants, et la soumettre.
2. Se connecter en responsable, ouvrir `/staff/missions/<id>`, cliquer
   « Démarrer le sourcing ».

**Constaté**

```
L'action « Publier l'appel » n'est pas possible pour le moment :
• Fixez la date limite de candidature et le mode de sourcing avant de publier l'appel.
• La date limite de candidature est déjà passée : reportez-la avant de publier l'appel.
```

L'appel reste bloqué à l'étape « qualifié », indéfiniment.

**Cause** — La transition « Publier l'appel » porte deux conditions
(`rule_mission_has_deadline`, `rule_mission_deadline_open`) qui lisent
`date_limite_candidature`. Or ce champ **n'apparaît sur aucun formulaire du
portail** : les cinq écrans du client couvrent le titre, le type, la description,
les objectifs, le domaine, les compétences, les dates de début et de fin, la
localisation, le mode d'intervention et le budget — pas la date limite. L'écran du
responsable ne fait que l'afficher. Vérification :

```
grep -rn 'name="date_limite_candidature"' views/   →  uniquement les vues back-office
```

Le champ n'était donc saisissable que dans l'interface d'administration d'Odoo.
Le second message (« déjà passée ») est trompeur : la date est vide, pas passée.

**Correction** — Ajout de `date_limite_candidature` et de `duree_estimee_jours` à
l'écran « Organisation », qui portait déjà les deux dates sœurs, et prise en
compte dans l'enregistrement de l'étape. La date limite est en outre récapitulée
avant soumission, en rouge si elle manque, pour que son absence se voie avant que
le cluster ne bute dessus.

*(`views/portal_templates.xml`, `controllers/portal.py`)*

`duree_estimee_jours` est ajouté au passage parce que le critère budgétaire du
Smart Matching ramène le budget total à un tarif journalier en le divisant par
cette durée : vide, il valait 0 et le critère était neutralisé.

**Vérifié** — Nouveau dépôt de bout en bout : la valeur est enregistrée, affichée
au récapitulatif, et l'appel se publie sans toucher au back-office. Il apparaît
ensuite sur `/missions`.

---

## C2 — Le vivier affichait un bouton que le serveur refuse 🟠

**Reproduction**
1. Une candidature déposée sur un appel ouvert.
2. Responsable → `/staff/missions/<id>/pool`.
3. Cliquer « Retirer la candidature ».

**Constaté** — Retour sur le vivier avec
`error=Action inconnue sur une candidature.` Le bouton ne fait jamais rien.

**Cause** — L'écran affichait toutes les transitions que le moteur ouvre à
l'utilisateur. Le responsable portant `group_workflow_manager`, le moteur lui
ouvre aussi `application_withdraw_applied` — le retrait, qui est l'acte du
candidat. Or le POST filtre sur une liste fermée de sept codes qui, elle, ne
contient pas le retrait. Le bouton était donc rendu par une source et refusé par
l'autre — exactement le défaut contre lequel la docstring de la route met en
garde.

**Correction** — Les options affichées sont filtrées par **la même liste fermée
qui garde le POST**. Le retrait reste volontairement hors de cette liste : se
retirer après dépôt est l'acte du candidat, pas une décision du responsable.

*(`controllers/staff.py`)*

**Vérifié** — Sur une candidature neuve, les boutons rendus sont exactement
`application_screen` et `application_reject_applied`, tous deux acceptés.

---

## C3 — Une mission sous contrat validé ne pouvait pas démarrer depuis le portail 🟠

**Reproduction** — Dérouler sélection → attribution → contractualisation, faire
confirmer les deux parties, faire valider le contrat. Puis ouvrir
`/staff/missions/<id>`.

**Constaté** — « Aucune décision ne vous est ouverte sur cet appel ». Le contrat
est validé, la mission reste à l'étape « contractualisation », et **aucune action
n'est proposée**. Le parcours s'arrête là.

**Cause** — La liste fermée des transitions ouvertes au portail responsable
s'arrêtait au lancement de la contractualisation. `mission_start` n'y figurait
pas. Les deux seules portes restantes étaient le back-office et le cron
d'échéance — lequel ne fait rien tant que la date de début contractuelle n'est
pas arrivée (ici, cinq semaines plus tard).

**Correction** — Ajout de `mission_start`, `mission_contracting_failed` et
`mission_cancel_contracting` à la liste. Aucun droit n'est ouvert au passage :
`available_transitions(user)` filtre déjà par rôle, et la règle 5 du §39 —
contrat validé — reste une condition de la transition, rejugée par le moteur.

*(`controllers/staff.py`)*

**Vérifié** — La mission démarre depuis le portail ; l'espace intervenant passe à
« Missions en cours : 1 ».

---

## C4 — Un candidat écarté lisait « Votre candidature est déposée » 🟡

**Reproduction** — Faire écarter une candidature par le responsable, puis
l'ouvrir en tant que candidat.

**Constaté**

> **Votre candidature est déposée**
> Elle est à l'étape « Candidature non retenue ». Vous ne pouvez plus la modifier :
> la version examinée par le cluster doit être celle qu'il a lue.

Le titre et l'explication contredisent le résultat. Le même texte s'affichait pour
une candidature retirée et pour une candidature retenue.

**Cause** — Le gabarit affichait ce titre pour **toutes** les étapes non
modifiables, sans distinguer « en cours d'examen » de « clos ».

**Correction** — Le titre et le paragraphe suivent désormais le dénouement réel
(en cours / retenue / non retenue / retirée / déclinée). Le candidat retenu est
en outre dirigé vers ses pièces contractuelles, le candidat écarté vers les
autres appels ouverts. Le code d'étape est traduit dans le controller ; le
gabarit ne voit qu'un mot métier.

*(`controllers/candidature.py`, `views/candidature_templates.xml`)*

**Vérifié** — Un candidat retenu lit « Votre candidature a été retenue » et
dispose du lien vers ses contrats.

---

## C5 (annexe) — Navigation de l'espace intervenant 🟡

**Constaté** — Dans `/my/intervenant`, le bouton « Mes missions » pointait sur
`/my/missions`, qui est **l'espace du client** : « mes demandes », « Créer une
demande de mission », quatre compteurs à zéro. Un intervenant retenu n'y voyait
rien le concernant. Ses pièces contractuelles n'étaient atteignables que par un
détour — « Mes candidatures » puis « Mes contrats » — alors qu'un intervenant qui
vient signer ne passe pas par la liste de ses candidatures.

**Correction** — « Mes missions » est remplacé par « Mes contrats ».

⚠ **Correction d'une erreur que j'avais moi-même introduite** : j'avais d'abord
ajouté aussi « Services faits » et « Mes évaluations ». Vérification faite, ces
deux écrans sont **bornés au client par construction**
(`_intervenants_service_own` filtre sur `mission_id.client_id` ;
`_intervenants_evaluation_own` sur `client_id` avec le commentaire « on n'évalue
pas soi-même »). Mesuré en session : les deux répondent 200 et affichent des
pages vides rédigées pour quelqu'un d'autre — « Les prestations à réceptionner »,
« Les intervenants que vous avez à évaluer ». Les deux liens ont été retirés.

*(`views/dashboard_templates.xml`)*

---

# Ce qui reste cassé ou manquant — documenté, non corrigé

## D1 — Aucun écran de livrables pour l'intervenant 🔴 fonctionnalité absente

**Constaté** — Une fois la mission démarrée, l'intervenant n'a **aucun écran**
pour déposer un livrable, déclarer son avancement, ou signaler un incident.
Vérifié par sondage HTTP : `/my/missions/livrables`, `/my/missions/deliverables`,
`/my/missions/<id>/livrables`, `/my/missions/execution` répondent tous **404**.

Vérifié dans le code : aucun controller du module ne mentionne `deliverable` ni
`livrable`, et aucune route `/my/*` ne les sert.

```
grep -rln "deliverable\|livrable" controllers/   →  aucun résultat
```

**Portée** — Tout le §21 à §26 (suivi d'exécution, livrables, versions,
incidents, points d'avancement) existe en modèles, en workflow et en écrans
back-office, mais **n'est pas exposé à l'intervenant**. C'est une fonctionnalité
absente du portail, pas un bug de code.

**Pourquoi non corrigé** — Construire cet espace (liste des livrables, dépôt de
version, cycle de validation à cinq étapes, points d'avancement, incidents) est
un chantier d'une demi-journée au moins, avec sa sécurité, ses gabarits et ses
tests. Hors de ce qui pouvait être fait sûrement aujourd'hui.

---

## D2 — Le tableau de priorités renvoie tout le monde sur l'écran du client 🟠

**Reproduction** — Intervenant retenu → `/my/intervenant`. L'entrée « Contrat
signé » de la colonne « Terminé » pointe sur `/my/missions/<mission_id>`.

**Constaté** — Ce lien mène à l'espace du **client**. Pour l'intervenant, la route
ne trouve pas la mission (elle borne par `client_id`) et le renvoie sur sa
**candidature** — pas sur son contrat. Le lien libellé « Contrat signé » n'amène
donc jamais au contrat.

**Cause** — `opex.mission.dashboard._item()` construit son URL par défaut ainsi :

```python
'url': url or ('/my/missions/%s' % mission.id if mission else '/my'),
```

L'URL est déduite de **l'objet**, jamais du **lecteur**. C'est exactement le
défaut décrit par la règle 22 du CLAUDE.md — « une URL de notification se résout
pour le LECTEUR, pas pour l'objet » — réapparu ici. Les entrées « Livrable en
retard » et « Livrable soumis » posent explicitement la même URL.

**Pourquoi non corrigé** — La méthode est partagée par les quatre espaces
(responsable, intervenant, client, candidat), et `/my/missions/<id>` est la bonne
destination pour le client. Corriger proprement demande d'introduire la notion de
lecteur dans le contrat de `_priority_board()`, ce qui touche quatre appelants.
Surtout : pour les deux entrées « livrable », **il n'existe aujourd'hui aucune
destination correcte** (voir D1). Un correctif partiel resterait faux dans deux
cas sur trois.

**Correction recommandée** — Passer le rôle du lecteur à `_priority_board()` et
résoudre l'URL par couple (élément, lecteur) : contrat → `/my/missions/contrats`,
candidature → `/my/missions/candidature/<id>`, livrable → l'écran de D1 une fois
qu'il existera.

---

## D3 — L'exécution n'est pas pilotable depuis le portail responsable 🟡 limite

**Constaté** — Après `mission_start` (désormais possible, cf. C3), l'écran
responsable n'offre plus aucune action : `mission_deliver`,
`mission_accept_service`, `mission_close` et les transitions de suspension ne
sont pas dans la liste fermée du portail. La fin du cycle — remise des livrables,
service fait, facturation, clôture — se pilote au back-office.

**Statut** — C'est cohérent avec le périmètre annoncé du module (« de la
qualification jusqu'au lancement de la contractualisation ») et je ne l'ai pas
étendu au-delà de `mission_start`, qui était nécessaire pour débloquer le
démarrage. À décider : soit assumer et annoncer cette limite, soit ouvrir la
suite du cycle au portail, ce qui suppose au préalable l'écran de D1.

---

# Ce qui fonctionne — vérifié en session

| Étape | Résultat |
|---|---|
| Connexion portail et espace intervenant `/my/intervenant` | ✅ cinq indicateurs corrects |
| Compteur « Appels pertinents » | ✅ exclut bien les appels déjà candidatés |
| Profil d'expertise `/my/missions/expertise` — compétences | ✅ 58 compétences au référentiel, ajout enregistré |
| — disponibilités | ✅ |
| — certifications | ✅ affichée après ajout |
| Membre **sans** profil sur `/my/missions/expertise` | ✅ page explicative, pas de rebond muet, lien vers la demande de profil |
| Catalogue public `/missions` sans authentification | ✅ |
| Fiche publique `/missions/<id>` | ✅ date limite affichée |
| CTA « Je suis intéressé » avec profil | ✅ formulaire POST, candidature créée |
| CTA sans profil | ✅ page explicative + mini-profil en 4 champs |
| Mini-profil puis candidature | ✅ enchaînement complet |
| Formulaire Lean — 6 champs propres à la mission | ✅ tarif « 1 200,50 » normalisé à 1200.5, délai, motivation, méthodologie |
| Le formulaire ne redemande rien de permanent | ✅ bloc « ce que nous savons déjà de vous » |
| Soumission de la candidature | ✅ formulaire verrouillé ensuite |
| Double candidature sur le même appel | ✅ ramène à la candidature existante, aucun doublon |
| Étanchéité : un autre membre ouvre la candidature | ✅ renvoyé sur sa propre liste, sans divulgation |
| Retrait de candidature | ✅ compteur « en cours » passe de 1 à 0 |
| Suivi `/my/missions/candidatures` | ✅ appel, origine, état |
| Vivier responsable `/staff/missions/<id>/pool` | ✅ candidat, score, colonnes Nouveaux/Qualifiés/Short-list/Retenus |
| Qualification → short-list → sélection | ✅ chaque étape visible côté candidat |
| Pièces contractuelles `/my/missions/contrats` | ✅ contrat + ordre de mission |
| Confirmation intervenant puis client | ✅ message explicite sur l'attente de l'autre partie |
| Cycle contrat (révision, envoi, signature, validation) | ✅ piloté au portail |
| Démarrage de la mission | ✅ après C3 |

---

# Vérification finale et non-régression

**Parcours complet rejoué de zéro sur un appel neuf**, portail uniquement, sans
jamais ouvrir le back-office : **17 contrôles, 0 défaut**.

```
F.1 dépôt client avec date limite        OK   (persistée, affichée au récapitulatif)
F.2 publication par le responsable       OK   (appel présent sur /missions)
F.3 candidature + soumission             OK
F.4 aucun bouton mort dans le vivier     OK
F.5 qualification → sélection            OK   (« votre candidature a été retenue »)
    contrat des deux côtés → validé      OK
    démarrage de la mission              OK   (« Missions en cours » incrémenté)
```

**Non-régression** — Suite complète du module rejouée après les corrections :

```
0 failed, 0 error(s) of 491 tests   (opex_intervenants, base opex_mis_e1)
```

---

# Fichiers modifiés

| Fichier | Objet |
|---|---|
| `controllers/portal.py` | C1 — enregistrement de la date limite et de la durée estimée |
| `views/portal_templates.xml` | C1 — deux champs sur l'écran Organisation, rappel au récapitulatif |
| `controllers/staff.py` | C2 — filtrage des boutons du vivier · C3 — ouverture de `mission_start` |
| `controllers/candidature.py` | C4 — traduction de l'étape en dénouement métier |
| `views/candidature_templates.xml` | C4 — titre et message selon le dénouement |
| `views/dashboard_templates.xml` | C5 — navigation de l'espace intervenant |

199 lignes ajoutées, 8 supprimées. Aucune modification de modèle, de workflow,
de sécurité ni de schéma : uniquement des controllers et des gabarits.

---

# Deux pièges d'environnement rencontrés

À connaître, car ils faussent le diagnostic et ils ont failli me faire conclure à
tort qu'une correction ne fonctionnait pas.

**Le serveur fantôme.** `SO_REUSEADDR` permet à une seconde instance Odoo de se
lier au même port sans erreur. Deux serveurs tournaient sur le 8072 ; l'ancien
servait les requêtes avec **l'ancien code Python**, tandis que les gabarits —
qui vivent en base — étaient à jour. Symptôme exact : le champ ajouté
s'affichait, mais sa valeur n'était jamais enregistrée. C'est le piège déjà
consigné dans le CLAUDE.md du projet, rencontré ici en conditions réelles.
**Vérifier le nombre de processus Python avant de conclure qu'un correctif ne
prend pas.**

**Le cron de messagerie.** Le journal contient une trace
`psycopg2.errors.SerializationFailure` sur « Mail: Email Queue Manager ». Deux
causes cumulées, toutes deux environnementales : aucun serveur SMTP n'est
configuré (limite déjà déclarée du projet) et mes deux instances concurrentes
écrivaient la même table. **Ce n'est pas un défaut du module.**

---

# Pour reproduire

La base de test `opex_parcours` est conservée telle quelle, avec ses comptes et
ses dossiers. Le serveur a été arrêté.

```powershell
cd C:\Users\User\Desktop\stageDeltaLog
.\venv\Scripts\python.exe .\odoo\odoo-bin -c odoo.conf -d opex_parcours `
    --http-port=8072 --limit-time-real=0 --workers=0 --max-cron-threads=0
```

Comptes : `pt_client`, `pt_expert`, `pt_externe`, `pt_staff` — mot de passe
identique au login.

Les scripts de test sont dans le répertoire temporaire du travail
(`harness.py`, `t1_prepare_call.py` … `t11_final.py`). Dites-moi si vous voulez
qu'ils soient versionnés dans `tests/` sous forme de tests HTTP Odoo.
