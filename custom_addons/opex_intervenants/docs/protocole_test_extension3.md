# Protocole de test manuel — Extension 3 : le profil expert enrichi

Se met dans la peau d'un **intervenant**, puis d'un **gestionnaire**. Comptez
20 minutes.

Ce que cette extension livre n'a pas d'effet visible en soi : c'est le
**capital** que l'Extension 4 comparera. Le protocole vérifie donc deux choses —
que l'intervenant peut le renseigner, et qu'il **arrive là où le moteur sait le
lire**.

---

## 0. Préparer

### 0.1 Le serveur

```bash
cd C:/Users/User/Desktop/stageDeltaLog
venv/Scripts/python.exe odoo/odoo-bin -c odoo.conf -d opex_mis_demo \
    --http-port=8072 --limit-time-real=0
```

### 0.2 Un compte avec un profil Expert **activé**

Point à ne pas manquer : `partner.expert_profile_id` n'est renseigné qu'à
l'**activation** du profil par le Module 2, pas au dépôt de la demande. Un
compte dont la demande est encore en instruction n'ouvrira pas ces écrans — et
c'est voulu (règle 1 du §39).

Le plus rapide, en back-office avec `manager` ou l'administrateur :

1. `OPEX Innovation → Profils → Profils Expert`
2. Ouvrir le profil de `expert` (le créer s'il n'existe pas : bouton Nouveau,
   contact = `expert`)
3. Le faire avancer jusqu'à **Validé** par le bouton **Action** — ou, plus
   direct, cocher **Profil activé** sur la fiche.

Vérifier ensuite sur la fiche du **contact** (`Contacts → expert`) que le champ
**Profil expert** est renseigné. C'est lui que les écrans interrogent.

### 0.3 Deux ou trois compétences au référentiel

`OPEX Innovation → Configuration → Compétences`. Sans elles, la liste déroulante
de l'écran sera vide.

---

## 1. La tuile, et le refus expliqué

### 1.1 Sans profil expert

Se connecter avec un compte portail **sans** profil expert (`client` fait
l'affaire). Aller sur `/my/missions/expertise`.

> Une page qui **explique** : « vous devez d'abord disposer d'un profil
> Expert validé », avec un bouton vers `/my/innovation/profiles`.
>
> **Aucun formulaire d'ajout.** Une redirection muette vers `/my` aurait
> laissé le membre sans savoir ce qui lui manque ; une page qui montrerait les
> formulaires sans les faire fonctionner serait pire.

### 1.2 Avec profil expert

Se connecter en **`expert`**, aller sur `/my`.

> Une tuile **« OPEX Intervenants — mon expertise »**, distincte de
> « demander une intervention ».
>
> **Console ouverte (F12), rechargez.** Aucune erreur JavaScript, aucun
> spinner figé. Les deux tuiles du module portent des compteurs **différents**
> (`intervenants_mission_count` et `intervenants_expertise_count`) : si elles
> partageaient une clé, `querySelector()` ne renverrait que le premier nœud et
> la seconde resterait masquée jusqu'au rechargement suivant.

---

## 2. Renseigner le capital

Cliquer la tuile → `/my/missions/expertise`.

> **Une page, cinq blocs** : la synthèse, puis Compétences, Expériences,
> Certifications, Disponibilités, et les Évaluations en lecture seule.
>
> Ce n'est délibérément **pas** un parcours en cinq écrans comme la demande de
> mission : un capital s'entretient. On y revient pour changer une date, pas
> pour tout retraverser.

> La synthèse affiche **« — » et « Aucune mission évaluée »** pour la
> réputation, pas « 0 / 5 ». Un zéro laisserait croire à un expert mal noté.

### 2.1 Compétences

Ajouter *Cybersécurité*, niveau **Expert**, 12 ans.

> La ligne apparaît, le compteur « Compétences » passe à 1.

**Trois refus à éprouver** :

| Essai | Attendu |
|---|---|
| Ajouter sans choisir de compétence | « Choisissez une compétence. » |
| Ajouter **deux fois** la même compétence | La page revient avec un message — **pas une erreur 500** |
| Retirer la ligne, puis la remettre | Fonctionne |

> Le second cas est le plus intéressant. Une contrainte SQL ne se déclenche
> pas à la création mais au `flush`, et elle **empoisonne la transaction** :
> sans savepoint, le rendu de la page d'erreur reçoit lui aussi « current
> transaction is aborted » et le client voit un 500. C'était le cas au premier
> essai ; il a fallu isoler la création dans un savepoint.

### 2.2 Expériences

Ajouter *Audit SI industriel*, organisation libre, type **Audit**, domaine
**Cybersécurité**, séniorité **Senior**, avec une période passée cohérente.

Essayer une date de fin **avant** la date de début.

> Message de contrainte, pas d'erreur serveur.

Ajouter une seconde expérience en séniorité **Junior**.

> Ce point se vérifie au §4 : la séniorité exposée au matching doit rester
> **Senior**, la plus haute atteinte — et non la dernière saisie.

### 2.3 Certifications

Ajouter deux certifications :

| Intitulé | Valable jusqu'au | Attendu |
|---|---|---|
| *ISO 27001 Lead Auditor* | dans un an | badge vert **Valide** |
| *ITIL v3* | **hier** | badge gris **Expirée** |

> Le compteur de la synthèse compte **1 sur 2** : les valides, pas le total.
>
> La validité est **calculée à chaque lecture**, jamais stockée. Stockée, une
> certification expirée resterait « valide » jusqu'au prochain recalcul — et
> rien ne déclenche de recalcul quand une échéance passe.

### 2.4 Disponibilités

Ajouter une période **couvrant aujourd'hui**, taux 75 %.

> Badge vert **En cours**, la synthèse affiche « Disponible ».

Ajouter une période entièrement passée.

> Badge **Hors période**. La synthèse ne change pas.

Essayer un taux de **150**.

> Refusé — le taux s'exprime entre 0 et 100.

### 2.5 Évaluations

> Le bloc existe, il est **vide**, et il dit pourquoi : « Les évaluations sont
> portées à la clôture d'une mission, par le client et par le cluster ; elles
> alimentent votre réputation et **ne sont pas modifiables**. »
>
> **Aucun formulaire d'ajout.** Le modèle est créé vide et le reste : les
> notes viendront de l'Extension 10. Un écran qui en saisirait viderait la
> réputation de son sens — le §32 demande un historique « basé sur les missions
> réellement réalisées ».

---

## 3. L'étanchéité entre intervenants

Créer un second expert (`expert2`, profil activé de la même façon) et lui
déclarer une compétence.

Revenir en **`expert`**, relever l'identifiant d'une ligne de `expert2` — par
exemple en back-office — et tenter de la supprimer en forgeant le POST depuis la
console du navigateur sur `/my/missions/expertise/skill`
(`action=remove`, `line_id=<id de l'autre>`).

> **La ligne de l'autre existe toujours.** L'identifiant reçu est cherché
> *dans* les lignes du profil connecté, jamais parcouru directement.

Vérifier aussi que la page de `expert` ne contient **nulle part** les
compétences de `expert2` — dans le **code source** (Ctrl+U), pas seulement à
l'œil.

---

## 4. Le point qui compte : le capital arrive sur `res.partner`

C'est la raison d'être de l'extension. Sans lui, l'Extension 4 n'aurait rien à
comparer, et on ne s'en apercevrait qu'à ce moment-là.

En back-office, `Contacts → expert`, activer le **mode développeur**
(`Paramètres → Général → Activer le mode développeur`), puis ouvrir la fiche et
consulter les champs techniques — le plus simple est la vue *Voir les
métadonnées* ou un filtre personnalisé.

Plus direct, par le shell :

```bash
venv/Scripts/python.exe odoo/odoo-bin shell -c odoo.conf -d opex_mis_demo \
    --http-port=8072
```

```python
p = env['res.users'].search([('login', '=', 'expert')]).partner_id
print("compétences  :", p.expert_skill_competence_ids.mapped('name'))
print("domaines     :", p.expert_experience_domaine_ids.mapped('name'))
print("types        :", p.expert_mission_type_ids.mapped('name'))
print("séniorité    :", p.expert_seniorite)
print("disponible   :", p.expert_disponible, p.expert_taux_disponibilite, "%")
print("certifs      :", p.expert_certification_names)
print("réputation   :", p.expert_reputation)
```

> **Séniorité = `senior`**, pas `junior` : c'est la plus haute atteinte. Un
> `max()` sur les chaînes aurait trié par ordre alphabétique et fait de
> « junior » le sommet de la hiérarchie.
>
> **Certifications = « ISO 27001 Lead Auditor » seule.** L'expirée n'y est
> pas : la cible de matching suit la validité, pas la simple existence.
>
> **Disponible = True, 75 %.**
>
> **Réputation = 0.0** — jamais évalué, et c'est la bonne valeur.

> Pourquoi ces champs sont sur `res.partner` et pas sur le profil : le moteur
> compare à `partner.sudo()[criterion.target_field]`
> (`workflow_instance.py:1077`). Le champ cible est **toujours** un champ de
> `res.partner`. Ce n'est pas un choix de conception, c'est la contrainte du
> moteur qu'on configure.

**Test de fraîcheur** : dans le shell, retirer la disponibilité en cours, puis
relire `p.expert_disponible`.

```python
p.expert_profile_id.expert_availability_ids.filtered('is_current').unlink()
p.invalidate_recordset()
print(p.expert_disponible)   # doit valoir False
```

> `False`. Ces champs ne sont **pas stockés**, et c'est ce qui les rend
> justes : stockés, ils se figeraient au dernier recalcul et le matching
> proposerait des experts indisponibles.

---

## 5. Le back-office

En **`manager`** : `OPEX Innovation → Profils → Profils Expert`, ouvrir celui de
`expert`.

> Un encart **« Capital pour les missions »** au-dessus des onglets :
> compétences, expériences, certifications valides, disponibilité, réputation.
>
> Deux onglets nouveaux — *Compétences et expérience*, *Certifications et
> disponibilité* — **à côté** de « Parcours » et « Justificatifs » du Module 2,
> qui sont intacts.
>
> Un onglet **Évaluations** en lecture seule, sans bouton d'ajout, avec
> l'encart qui explique que l'Extension 10 les alimentera.

> Le formulaire est celui du Module 2, **hérité** et non dupliqué. Le
> gestionnaire qui consulte un intervenant n'a pas à choisir entre deux fiches
> pour la même personne.

Puis `OPEX Intervenants → Capital des intervenants → Compétences`.

> La question inverse : **qui pratique cette compétence ?** Grouper par
> Compétence, filtrer sur « Niveau expert ». C'est ce que le §16 appelle
> comparer, et c'est ce que le matching automatisera à l'Extension 4.

Essayer de **modifier** une ligne de compétence depuis cet écran, en `manager`.

> Refusé en lecture seule par l'`ir.rule` : le capital appartient à
> l'intervenant. Le cluster le consulte pour décider, il ne le corrige pas à sa
> place.

---

## 6. Contrôle final

| Point | Où | Attendu |
|---|---|---|
| Aucun second profil expert | back-office | il n'existe qu'`opex.innovation.expert.profile` |
| Le Module 2 est intact | fiche profil | onglets « Parcours » et « Justificatifs » toujours là |
| Les routes voisines vivent | `/my/innovation/profiles`, `/my/missions` | répondent toujours |
| Deux compteurs distincts | source de `/my` | `intervenants_mission_count` **et** `intervenants_expertise_count` |

---

## Ce que ce protocole ne teste pas, et pourquoi

- **Le matching lui-même** : Extension 4. Ici on vérifie que le capital est
  lisible là où il le sera, pas qu'il produit un score.
- **La réputation réelle** : Extension 10. Le modèle existe, vide, et l'écran
  le dit.
- **Le tarif journalier de l'expert** : le critère « Budget 10 % » du §11 aura
  besoin d'une donnée de ce type sur le profil. Elle n'est dans aucun des cinq
  modèles du périmètre — à trancher à l'Extension 4.
- **Les langues** : le critère « Localisation / langue 5 % » compare un champ
  `langues` de la mission à… rien, côté expert. Même remarque.
- **Un justificatif joint à une certification** : le périmètre nomme
  « intitulé, organisme, date, validité ». Une certification déclarative n'est
  pas une certification prouvée ; à arbitrer si le cluster l'exige.
