# Protocole de test manuel — Extension 9

**Service fait et facturation** : le constat du §28, la règle 6 du §39 en
condition, la commande de vente et le suivi du paiement.

Durée : ~30 min. Base `opex_mis_e1`.

```
.\venv\Scripts\python.exe .\odoo\odoo-bin -c odoo.conf -d opex_mis_e1 ^
    -u opex_intervenants --limit-time-real=0
```

**Point de départ** : une mission en `Mission en cours` avec au moins un
livrable obligatoire. Le protocole de l'Extension 8 y mène ; si vous en avez
déjà une, reprenez-la.

**Prérequis comptable.** Cette extension émet de vraies écritures. Vérifiez
avant de commencer que la base a un plan comptable, un journal de vente et un
journal de banque (Comptabilité → Configuration → Journaux). Sans eux, la
partie 4 échouera — proprement, avec un message dans le dossier, mais elle
échouera. Sur `opex_mis_e1` c'est le cas : 51 comptes, un journal de vente, un
journal de banque.

---

## Partie 1 — Le constat s'ouvre tout seul (5 min)

**§27.**

1. Sur la mission, faire valider le livrable obligatoire :
   Action → **Commencer**, joindre un fichier, **Soumettre à validation**, puis
   compte responsable → **Valider**.

2. Sur la fiche de l'appel : Action → **Soumettre les livrables**.
   La mission passe à *Livrables remis*.

3. Onglet **Service fait et facturation** — il vient d'apparaître.

**À vérifier** :

- un constat **SF-2026-0001** existe, à l'étape *Vérification du cluster en
  cours* ;
- le bouton de statistique **Service fait** est apparu en haut de la fiche ;
- le montant à facturer est repris de l'affectation, **sans saisie**.

Personne ne l'a créé à la main. C'est une action `set_field` configurée sur
la transition « Soumettre les livrables ». Menu **Configuration → Workflows**
(module `opex_workflow`) → définition *Appel à mission* → transition
« Soumettre les livrables » → onglet Actions : « Ouvrir le constat de service
fait » s'y trouve, et on peut la détacher sans toucher à une ligne de Python.

---

## Partie 2 — La règle 6 du §39 (8 min)

**C'est le cœur de l'extension. À faire dans cet ordre.**

1. Ajouter à la mission un **second livrable obligatoire**, et ne pas le
   valider. L'onglet *Suivi d'exécution* affiche
   « Livrables obligatoires non validés : 1 ».

2. Ouvrir le constat de service fait, onglet **Validation finale — §28**, et
   cocher les quatre points.

3. Action → **Valider (cluster)**.

   Attendu : **refus** —

   > La mission ne peut pas être déclarée terminée tant que les livrables
   > obligatoires ne sont pas validés (règle 6 du §39).

   Et un bandeau rouge le disait déjà en haut de la fiche, avant le clic.

4. Valider le second livrable. Rejouer **Valider (cluster)** : ça passe.

**Ce qu'il faut voir** : la règle 6 n'est pas un `if` dans une méthode. C'est
un enregistrement `opex.workflow.rule`, visible dans le configurateur, dont
l'expression est `field('deliverable_unvalidated_count', 1) == 0`.

**Et c'est le même enregistrement qui garde deux transitions** :
« Valider (cluster) » sur le constat, et « Valider le service fait » sur la
mission. Ouvrir la règle dans le configurateur et regarder ses transitions :
elles sont deux. Une règle jumelle aurait divergé de celle-ci au premier
ajustement.

---

## Partie 3 — Les deux validations et la contestation (8 min)

**§27, §28.**

1. Le constat est à *Action requise : valider le service fait*, et l'acteur
   attendu est le **client**.

2. **Contester d'abord**, pour voir la boucle. Compte client (ou responsable,
   que le §27 autorise) : Action → **Contester le service fait**.
   Le commentaire est **obligatoire** — saisir « Le rapport ne couvre pas le
   périmètre convenu ».

   **À vérifier** :
   - le constat est à *Service fait contesté* ;
   - la mission **ne peut pas** franchir « Valider le service fait » : le
     message dit que le constat doit être validé ;
   - le constat n'est **pas** clos. Le bouton **Action** est toujours là.

   C'est la règle 14 du CLAUDE.md, et elle se démontre ici : si `disputed`
   était marquée finale, le moteur aurait posé `state = 'done'` et le client
   qui conteste aurait fermé la mission **définitivement**. Mesuré par
   régression volontaire : trois tests rougissent, dont un sur
   `'done' != 'running'` et un sur la reprise devenue infranchissable.

3. Action → **Reprendre après contestation** (commentaire obligatoire).
   Revalider côté cluster, puis côté client : Action → **Valider le service
   fait**.

4. Onglet **Qui a validé, et quand**.

   **À vérifier** : la date et le commentaire affichés sont ceux du
   **second** contrôle, pas du premier.

Ces six champs ne sont saisis nulle part — ils sont relus dans le journal du
moteur. Un champ écrit au premier passage aurait affiché « Premier contrôle »
pour toujours. C'est la leçon de l'Extension 8 sur le motif de refus d'un
livrable, appliquée aux validations du §28.

---

## Partie 4 — La facturation (7 min)

**§29, Schéma 12.**

1. Sur la mission : Action → **Valider le service fait** (compte responsable
   ou client). La mission passe à *Service accepté*.

2. Action → **Facturer et clôturer** (compte **secrétariat**, commentaire
   obligatoire).

3. Onglet **Service fait et facturation**.

**À vérifier** :

- **Situation de facturation : En attente de paiement** ;
- une commande de vente existe, à l'état *Bon de commande* ;
- une facture est générée, du montant du constat ;
- le chatter porte une note « Facturation émise : S00xxx pour … ».

4. Ouvrir la commande (bouton **Commande**), puis la facture. Vérifier que la
   ligne reprend bien les six informations du §29 : client, intervenant,
   référence de mission, montant, prestation, date.

5. **Le paiement.** Confirmer la facture, puis **Enregistrer un paiement**.

   **À vérifier** : de retour sur la mission, **Situation de facturation :
   Payée**, et *Reste à payer : 0,00*.

Rien de tout cela n'est un workflow de ce module. Les quatre cases du
Schéma 12 sont celles de `sale.order` et d'`account.move`. Une cinquième
définition les aurait doublées — et se serait désynchronisée à l'instant
précis de ce clic sur « Enregistrer un paiement », qui ne franchit aucune
transition.

---

## Partie 5 — La barre du §40 (2 min)

Sur la fiche de la mission clôturée :

```
Demande [x] Appel [x] Sélection [x] Contrat [x] Mission [x]
Validation [x] Facturation [>] Évaluation [ ]
```

Après enregistrement du paiement, **Facturation** passe à `[x]`.

**À vérifier** : l'étape de la mission n'a pas bougé (`closed` dans les deux
cas), et pourtant le jalon a changé. C'est le seul des huit que l'étape du
workflow ne suffit pas à décrire — la démonstration, en un écran, de pourquoi
la facturation n'a pas de définition.

**Évaluation reste `[ ]`** même sur une mission payée. C'est déclaré : elle
attend l'Extension 10, et un test le consigne et rougira ce jour-là.

---

## Ce que ce protocole ne couvre pas — à annoncer

**La validation du client se fait aujourd'hui depuis le back-office.**
L'écran portail relève de l'Extension 11, exactement comme la signature du
contrat à l'Extension 7. Le §27 autorisant explicitement « le client **ou le
responsable habilité** », le parcours est complet ; c'est le canal qui manque,
pas la fonction. Les droits sont déjà posés du bon côté : le client lit le
constat, il ne peut pas cocher les quatre points du cluster.

**Le mail ne part pas.** Le SMTP n'est pas configuré sur le poste : les
notifications de cette extension — demande de validation au client, annonce du
service fait, annonce de la facturation — se vérifient dans la **cloche** et
dans `mail.message`, pas dans une boîte de réception.
