# Protocole de test manuel — Extension 5 : appel portail et candidature

Trois rôles à enchaîner : **visiteur anonyme**, **expert référencé**, **candidat
externe**. Comptez 30 minutes.

Quatre choses à prouver : la vue publique ne laisse **rien** fuiter, la règle 1
tient **côté serveur**, la règle 3 rend un **message** et pas une erreur de
base, et la candidature Lean ne redemande **rien** de permanent.

---

## 0. Préparer

### 0.1 Le serveur

```bash
cd C:/Users/User/Desktop/stageDeltaLog
venv/Scripts/python.exe odoo/odoo-bin -c odoo.conf -d opex_mis_demo \
    --http-port=8072 --limit-time-real=0
```

### 0.2 Deux comptes, et ils diffèrent sur un point précis

| Compte | Profil expert | Sert à tester |
|---|---|---|
| `expert` | **activé** (voir §0.2 du protocole E3) | le parcours de l'expert référencé |
| `externe` | **aucun** — compte portail nu | le mini-profil du §7 |

`externe` ne doit avoir **aucun** `opex.innovation.expert.profile`. S'il en a
un d'un test précédent, supprimez-le en back-office, sinon le §4 ne prouvera
rien.

### 0.3 Un appel ouvert, et un appel restreint

En `manager`, deux appels **de type Audit**, tous deux amenés jusqu'à
**Candidatures en cours** (`Action → Publier l'appel`, puis
`Action → Ouvrir les candidatures`) :

| | Appel A | Appel B |
|---|---|---|
| Titre | Audit cybersécurité | Formation Lean |
| Budget | 300 000 | 150 000 |
| **Vue publique restreinte** *(onglet Confidentialité)* | **cochée** — le défaut | **décochée** |
| Une pièce `is_public` cochée | Cahier des charges | — |
| Une pièce `is_public` **décochée** | Annexe technique | — |

Laisser un troisième appel en **Brouillon**, avec un titre reconnaissable
(« Appel confidentiel non publié »).

---

## 1. La rubrique publique — en visiteur anonyme

**Se déconnecter complètement** (ou ouvrir une fenêtre de navigation privée).

Aller sur `http://localhost:8072/missions`.

> La rubrique s'affiche **sans être connecté**. C'est la méthode B du §8 :
> le marché, pas seulement le vivier.
>
> Une entrée **« Missions OPEX »** dans le menu principal du site.
>
> Les deux appels ouverts sont là. **Le brouillon n'y est pas.**

Forcer l'URL du brouillon : `/missions/<id du brouillon>`.

> Redirection vers `/missions`. Son titre n'apparaît nulle part.
>
> Sans cela, il suffirait d'incrémenter un nombre dans l'URL pour lire un appel
> non publié.

---

## 2. L'étanchéité de la vue publique

**C'est le point de sécurité de cette extension.**

Ouvrir l'**appel A** (restreint), puis **afficher le code source de la page**
(Ctrl+U) — pas seulement regarder l'écran.

> Rechercher le **nom du client** dans la source : **absent**.
> Rechercher `300000` et `300 000` : **absents**.
> Rechercher `Annexe technique` : **absent**.
>
> « Ne rends jamais dans le HTML une donnée réservée, **même masquée en
> CSS** ». Un `d-none` n'est pas une protection, c'est un aveu : la donnée est
> dans la page, il suffit de la lire.

> Et la page **le dit** : « Le client et le budget de cet appel ne sont
> communiqués qu'aux candidats retenus. » Un blanc passerait pour un oubli.

Ouvrir l'**appel B** (non restreint).

> Le client et le budget **sont** affichés. Le §12 du document UX est servi.
>
> Les deux documents ne se contredisent pas : c'est un **réglage par appel**,
> et c'est le cluster qui le tient.

### Les pièces jointes

Sur l'appel A :

> « Cahier des charges » est listé et se télécharge.
> « Annexe technique » n'est **pas** listée.

Relever l'identifiant de l'annexe en back-office, puis forger l'URL :
`/missions/<id appel>/document/<id annexe>`.

> Redirection, aucun fichier servi. Le contrôle est refait sur la route, pas
> seulement à l'affichage — une URL se forge à la main.

---

## 3. Le CTA et la règle 1 — en expert référencé

Toujours **déconnecté**, sur l'appel A :

> Le bouton dit « Je suis intéressé » et mène à la **connexion**, avec retour
> sur l'appel.

Se connecter en **`expert`**, revenir sur l'appel A.

> Le bouton est un **vrai bouton de formulaire** (POST), pas un lien. Une
> création de candidature n'est pas une lecture : un GET serait rejouable par
> un préchargement de navigateur ou un crawler.
>
> Sous le bouton : « Vous ne ressaisirez pas votre profil ».

Cliquer.

> Redirection vers `/my/missions/candidature/<id>`, étape **« Compléter ma
> candidature »**.
>
> Trois étapes du §12.2 ont été franchies dans la requête — `invited`,
> `viewed`, `interested` — et c'est fidèle : il **a** consulté la fiche pour
> arriver là, et cliquer « Je suis intéressé » **est** la déclaration
> d'intérêt.

---

## 4. La candidature Lean — le §9 à l'écran

Sur le formulaire de candidature.

### 4.1 Ce qui est affiché sans être demandé

> Un bloc **« Ce que nous savons déjà de vous »** : compétences, expériences,
> certifications valides, réputation — **en lecture**.
>
> C'est la preuve à l'écran que rien de permanent n'est redemandé.

### 4.2 Ce qui est demandé

> **Six champs, et pas un de plus** : disponibilité (obligatoire), délai de
> mobilisation, type et montant de la proposition financière, motivation,
> approche proposée, acceptation des conditions.

**Afficher le code source** (Ctrl+U) et chercher :

| Chercher | Attendu |
|---|---|
| `name="domaine_expertise"` | **absent** |
| `name="annees_experience"` | **absent** |
| `name="competence_id"` | **absent** |
| `name="specialites"` | **absent** |

> « Un expert référencé ne ressaisit **jamais** ses informations
> permanentes » — troisième critère d'acceptation du §21.

### 4.3 Les pièces jointes

> Trois types seulement : **proposition technique**, **proposition
> financière**, **autre pièce**.
>
> Ni CV, ni portfolio, ni références, ni certifications : ils sont sur le
> profil. Le §13 du document UX les liste, mais les redemander ici serait
> exactement la ressaisie que le §9 interdit — et le message sous le titre le
> dit au candidat.

Déposer un `.svg` ou un fichier de plus de 10 Mo.

> Refusé, avec un message. Un SVG servi en ligne s'exécuterait dans la
> session de celui qui l'ouvre.

### 4.4 L'envoi

Cliquer **Envoyer ma candidature** **sans** remplir la disponibilité.

> La condition configurée à l'Extension 1 refuse, et **la page l'explique** :
> « Renseignez votre disponibilité, votre délai de mobilisation, votre tarif et
> votre motivation, et acceptez les conditions ».

Remplir, saisir le tarif **avec une virgule et un espace** : `25 000,50`.
Envoyer.

> Accepté. L'étape passe à **« Candidature envoyée »**.
> Le tarif est bien enregistré à 25000.50.

Revenir sur la page.

> Le formulaire a disparu : **« Votre candidature est déposée »**, en lecture
> seule, avec un bouton « Retirer ma candidature ».
>
> La version examinée par le cluster doit être celle qu'il a lue.

---

## 5. La règle 3 — un message, pas une erreur de base

Retourner sur l'appel A, toujours en `expert`.

> Le bouton « Je suis intéressé » **mène désormais à votre candidature
> existante**, pas à une seconde création.

Forcer un second dépôt — depuis la console du navigateur, poster sur
`/missions/<id>/interesse`.

> **Pas de page 500.** Vous êtes renvoyé sur votre candidature.
>
> C'est le point technique : la contrainte SQL `unique(mission_id,
> partner_id)` ne se déclenche qu'au `flush` et **empoisonne la transaction**.
> Sans contrôle applicatif **et** savepoint, tout ce qui suit — y compris le
> rendu de la page d'erreur — recevrait « current transaction is aborted ».

En back-office, vérifier qu'il n'y a **qu'une** candidature de `expert` sur
l'appel A.

---

## 6. Le candidat externe — §7

Se connecter en **`externe`** (aucun profil expert).

Aller sur `/missions`, ouvrir l'appel A, cliquer « Je suis intéressé ».

> Une page qui **explique** : « Pour candidater, vous devez disposer d'un
> profil Expert. Créez-le en quelques champs : il sera instruit par le cluster
> en même temps que votre candidature. »
>
> Un bouton **« Créer mon profil et candidater »**.
>
> Une redirection muette vers `/my` aurait laissé le visiteur sans savoir ce
> qui lui manque.

### 6.1 La vérification serveur

**Avant** de créer le profil, forger le POST sur `/missions/<id>/interesse`
depuis la console du navigateur.

> **Aucune candidature n'est créée.** Vérifiez-le en back-office.
>
> Le `t-if` masque le bouton ; il n'empêche rien. Une requête forgée n'a
> jamais vu le gabarit — c'est pour cela que la règle 1 est vérifiée **sur la
> route**.

### 6.2 Le mini-profil

Cliquer « Créer mon profil et candidater », renseigner le domaine d'expertise,
valider.

> Redirection vers la candidature, étape « Compléter ma candidature ».

En back-office, `OPEX Innovation → Profils → Profils Expert` :

> Un **vrai** profil du Module 2 a été créé, à l'étape **Brouillon**, avec sa
> propre instance de workflow.
>
> Ce n'est pas un objet parallèle : « s'il est qualifié, son profil **peut**
> intégrer le référentiel experts OPEX » — sans que rien n'ait à être recopié.

### 6.3 Les deux niveaux de la règle 1

Toujours en `externe`, aller sur `/my/missions/expertise`.

> « Pour déclarer vos compétences […] vous devez d'abord disposer d'un
> **profil Expert validé** ».
>
> Et c'est cohérent, pas contradictoire :
> - **candidater** demande un profil, quel que soit son avancement ;
> - **entretenir son capital** demande un profil **activé** — on n'entretient
>   un référencement qu'une fois référencé.
>
> Le §7 fait entrer le candidat externe avant qu'il soit référencé ; le cluster
> instruit profil et candidature ensemble.

---

## 7. Contrôle final

| Point | Où | Attendu |
|---|---|---|
| Les trois tuiles du module | `/my`, console ouverte | « demander une intervention », « mon expertise », « mes candidatures » — **aucune erreur JS, aucun spinner figé** |
| Le suivi de candidature | `/my/missions/candidatures` | la liste, avec l'origine et l'état en libellé utilisateur |
| Étanchéité entre candidats | l'URL de la candidature d'un autre | ne montre rien |
| Les routes voisines vivent | `/my/innovation`, `/my/membership/new`, `/opex/directory` | répondent toujours |
| Le moteur n'est pas touché | `git diff opex_workflow/` | **zéro ligne** |

---

## Ce que ce protocole ne teste pas, et pourquoi

- **Les filtres du catalogue** (secteur, compétence, wilaya) : Extension 12,
  qui construit le portail public d'ensemble. Ici la rubrique existe et liste
  ce qui est ouvert, ce que le §7 demande.
- **La qualification du candidat externe** : le profil part en brouillon et
  suit le workflow du Module 2. Son instruction est l'affaire du secrétariat,
  pas de cette extension.
- **Le pool unique et le Kanban** (§10) : Extension 6. Les candidatures des
  deux canaux existent déjà côte à côte dans le même modèle — on le voit dans
  `OPEX Intervenants → Candidatures`, colonne « Origine » — mais l'écran de
  comparaison reste à faire.
- **Aucun email ne part** : SMTP absent, et aucune action `notify` n'est
  configurée avant l'Extension 11.
