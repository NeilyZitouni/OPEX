# Protocole de test manuel — Extension 12

**Intégration finale**, et le **parcours complet de bout en bout**.

Ce protocole a deux parties. La première vérifie ce que l'Extension 12 ajoute :
le catalogue filtré, l'accueil unique, les indicateurs globaux. La seconde
déroule le §48 en entier — « du besoin à la réputation » — et c'est celle qui
se présente en soutenance.

Durée : ~20 min pour la partie 1, ~50 min pour le parcours complet.

```
.\venv\Scripts\python.exe .\odoo\odoo-bin -c odoo.conf -d opex_mis_e1 ^
    -u opex_intervenants --http-port=8072 --limit-time-real=0
```

**Comptes** — mot de passe `demo1234` :
`demo_client`, `demo_expert`, `demo_manager`, `demo_comite`,
`demo_secretariat`. Créés par `docs/seed_demo.py` (voir le protocole de
l'Extension 11).

**Console ouverte** (F12) pendant toute la partie 1.

---

# Partie A — Ce que l'Extension 12 ajoute

## A1 — L'accueil unique, sans compte (4 min)

**Se déconnecter complètement**, puis ouvrir `/opex`.

C'est le point le plus important de cette page : elle répond **sans
authentification**. Une porte d'entrée qui demande une clé n'en est pas une.

**À vérifier** :

- les **trois** domaines : Annuaire des membres, Projets d'innovation, Appels
  à missions ;
- sous Projets d'innovation, la mention **« Accès après connexion »**. Le
  Module 2 ne publie pas de catalogue public ; la page le dit au lieu de
  laisser le visiteur le découvrir en tombant sur un écran de connexion ;
- les quatre indicateurs : Membres, Projets en cours, Missions en cours, Taux
  de réussite ;
- l'entrée **Le portail OPEX** dans le menu du site.

**Ce qui ne doit pas y être** : aucune mention de crowdfunding. Ce module est
isolé par construction, et un test vérifie qu'aucune des trois entrées ne
pointe vers lui.

## A2 — Le catalogue et ses quatre filtres (8 min)

Toujours sans compte, ouvrir `/missions`.

**À vérifier** : le formulaire porte les quatre filtres du §48 — domaine
d'expertise, type de mission, localisation, démarrage entre deux dates.

1. Choisir un domaine qui **a** des appels : la liste se réduit.
2. Choisir un domaine qui n'en a pas : il **n'est pas proposé**. Les listes
   déroulantes sont bornées à ce que le catalogue contient — proposer un
   critère qui donne zéro résultat laisse croire à une panne.
3. Saisir une localisation qui n'existe pas (« Tamanrasset ») : la liste est
   vide, et le formulaire **reste rempli**. Un filtre qui s'oublie lui-même
   donne l'impression que rien ne s'est passé.
4. Regarder l'URL : les critères y sont. La page est donc partageable, et le
   bouton Précédent les garde. Un POST aurait perdu les deux.

**Le test qui compte** — saisir à la main dans la barre d'adresse :

```
/missions?domaine=abc&type=%27&date_min=zz
```

**Attendu** : la page répond **200**, sans filtre appliqué. Les valeurs
illisibles neutralisent leur filtre au lieu d'atteindre le domaine de
recherche.

Ce cas a été trouvé par un test qui envoie volontairement une requête mal
formée : `date_min=zz` rendait un **500** sur une page publique, ouverte à
tout visiteur. Sur une page publique, ne pas filtrer vaut mieux que ne pas
répondre.

5. Ouvrir une fiche d'appel. **À vérifier** : ni le client, ni le budget. La
   vue publique est un dictionnaire à clés fermées, et les clés réservées en
   sont **absentes** — pas mises à `False`.

## A3 — Les indicateurs globaux et la liste du §21 (5 min)

Se connecter en `demo_manager`, ouvrir `/staff/kpi` (ou depuis la Smart Work
Queue, bouton **Indicateurs globaux**).

**À vérifier** : les quatre indicateurs agrégés sur les **trois** modules —
membres publiés (Module 1), projets en cours (Module 2), missions en cours et
taux de réussite (Module 3).

Puis le tableau des **neuf critères d'acceptation du §21**, chacun avec son
état et ce qui l'établit.

⚠ Ce tableau n'est pas un texte : il est **calculé à l'affichage** depuis la
configuration et les données. Un critère qui cesserait d'être tenu passerait
en rouge à l'écran, et le test qui lit la même méthode rougirait.

**À vérifier aussi** : se déconnecter, se connecter en `demo_expert`, ouvrir
`/staff/kpi`. On est renvoyé sur `/my` — le contrôle vit dans la route.

---

# Partie B — Le parcours complet, du besoin à la réputation

**C'est le §48 en entier.** Une seule mission, six identités, huit écrans.
À dérouler d'une traite.

## B1 — Le besoin (5 min) — compte `demo_client`

1. `/my` → tuile **OPEX Intervenants — demander une intervention**.
2. **Créer une demande** et remplir les cinq écrans : informations générales,
   profil recherché, organisation, budget, documents.
3. Le récapitulatif, puis **Soumettre la demande**.

**À vérifier** : la cloche du client porte « Votre demande d'intervention est
enregistrée ».

## B2 — La qualification et la publication (5 min) — `demo_secretariat`, puis `demo_manager`

4. Back-office → **Appels à mission** → la demande est en *Demande soumise*.
5. Action → **Prendre en charge la demande**.
6. Action → **Publier l'appel**, puis **Ouvrir les candidatures**.

**À vérifier** : le client reçoit « Votre demande est validée ». L'appel
apparaît sur `/missions`, et il est trouvable par les filtres de la partie A2.

## B3 — Les deux canaux du §8 (8 min) — `demo_manager`

7. `/staff/missions/<id>/matching` → **Lancer le matching**.

**À vérifier** : les candidats proposés portent un **score** et son
**explication** — critères positifs, manquants, pénalisants. Et la note des
**écartés** dit pourquoi ils le sont : c'est le §21, « les critères
éliminatoires sont distingués du scoring pondéré ».

8. **Inviter** un expert. Une candidature est créée à l'étape *Invité*.
9. En parallèle, compte `demo_expert` : depuis `/missions`, **Je suis
   intéressé**, puis remplir la candidature Lean.

**À vérifier** : l'expert ne ressaisit **pas** son profil permanent — seules
les données propres à la mission lui sont demandées.

## B4 — Le pool unique et la sélection (8 min) — `demo_manager`, puis `demo_comite`

10. `/staff/missions/<id>/pool`.

**À vérifier** : les candidatures des **deux** canaux sont dans le même écran,
distinguées par leur champ `source` et rien d'autre. C'est le critère
structurant du §21.

11. Qualifier, puis mettre en short-list. Comparer les profils.
12. Fermer les candidatures, puis compte `demo_comite` : **Retenir cette
    candidature**.

**À vérifier** : la mission reste en *Sélection* pendant que les candidatures
avancent chacune de leur côté. Les deux machines à états sont indépendantes.

## B5 — Le contrat (7 min) — `demo_secretariat`, `demo_manager`, `demo_comite`

13. Sur la mission : **Attribuer la mission**, puis **Lancer la
    contractualisation**.

**À vérifier** : le contrat et l'ordre de mission ont été **générés** à la
sélection, et le projet d'exécution ne l'a **pas** encore été.

14. Dérouler le cycle du §19 : soumettre à relecture, envoyer à la signature,
    enregistrer les deux signatures, valider.
15. **Démarrer la mission**.

**À vérifier** : sans contrat validé, « Démarrer la mission » refuse — c'est
la règle 5 du §39, et c'est une condition de transition, pas un `if`.

## B6 — L'exécution (7 min) — `demo_expert`, `demo_manager`

16. Ajouter deux livrables obligatoires avec leurs critères d'acceptation.
17. Sur le premier : Commencer, joindre un fichier, Soumettre à validation.
18. Compte responsable : **Demander une correction** (commentaire
    obligatoire), puis l'expert dépose une nouvelle version.

**À vérifier** : l'historique des versions est conservé, et le motif du refus
est porté par la **version archivée** — pas par le livrable, où il serait
écrasé au refus suivant.

19. Valider les deux livrables, écrire un point d'avancement, puis
    **Soumettre les livrables**.

## B7 — Le service fait et la facturation (7 min)

20. Le constat de service fait s'est ouvert tout seul. Cocher les quatre
    points du §28, **Valider (cluster)**, puis compte client **Valider le
    service fait**.

**À vérifier** : avec un livrable obligatoire non validé, la validation
refuse — règle 6 du §39, portée par le **même enregistrement de règle** que
la transition de la mission.

21. Sur la mission : **Valider le service fait**, puis compte secrétariat
    **Facturer et clôturer**.

**À vérifier** : une commande de vente confirmée, une facture générée.
Enregistrer le paiement, et la situation passe à **Payée**.

## B8 — L'évaluation et la réputation (5 min)

22. Les deux grilles se sont ouvertes à la clôture. Compte client : noter les
    six critères du §30, soumettre. Compte responsable : valider.
23. Idem pour la grille cluster du §31.

**À vérifier** : sur le profil de l'expert, onglet **Réputation**, la note
moyenne, les missions réalisées, les missions terminées, le taux de
satisfaction et le respect des délais se sont mis à jour **tout seuls**.

## B9 — La barre du §40, complète

Sur la fiche de la mission :

```
Demande [x] Appel [x] Sélection [x] Contrat [x] Mission [x]
Validation [x] Facturation [x] Évaluation [x]
```

**Les huit jalons du §48 sont franchis.** C'est le cycle complet :
besoin → appel → candidatures → sélection → contrat → exécution → validation →
facturation → évaluation → réputation.

---

## Ce que ce protocole ne couvre pas

**Le mail ne part pas.** Le SMTP n'est pas configuré : toutes les
notifications se vérifient dans la cloche et dans `mail.message`.

**Les PDF ne se génèrent pas.** `wkhtmltopdf` est absent du poste. Les deux
rapports restent déclarés en `qweb-pdf` — leur forme juste — et le bouton
**Aperçu** ouvre `/report/html/...`, qui rend le même gabarit sans binaire.

**Trois actions du client passent par le back-office** : la signature du
contrat, la validation du service fait et la grille d'évaluation. Les trois
sont autorisées au responsable par les §19, §27 et §31, donc le parcours est
complet — c'est le canal portail qui manque, pas la fonction.
