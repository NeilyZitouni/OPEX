# Protocole de test manuel — Extension IA-2

**Le rapprochement taxonomique du §8**, en deux temps, et le flux
d'enrichissement du référentiel.

Durée : ~25 min. Base `opex_mis_e1`.

```
.\venv\Scripts\python.exe .\odoo\odoo-bin -c odoo.conf -d opex_mis_e1 ^
    -u opex_ai_core,opex_intervenants --http-port=8072 --limit-time-real=0
```

Compte `demo_manager` / `demo1234`.

---

## Partie 1 — L'étape 1 ne coûte rien (6 min)

**Configuration → Synonymes de compétences.**

1. Créer un synonyme : `Audit SI` → une compétence existante du catalogue.

2. Ouvrir un profil expert, bouton **Lire un CV**, déposer un document
   contenant « Audit SI » parmi ses compétences.

**À vérifier** dans le tableau de résultat, colonne **Rapprochement** :

| Badge | Ce qu'il veut dire |
|---|---|
| `catalogue` (vert) | le libellé est au référentiel, tel quel |
| `synonyme` (vert) | reconnu par la table de synonymes |
| `IA 85 %` (bleu) | proposé par l'IA, avec sa confiance |
| `à arbitrer` (orange) | personne n'a su, un humain doit trancher |

3. **Journal des appels à l'IA** : vérifier qu'**aucun appel** n'est parti pour
   les libellés reconnus aux deux premiers badges. C'est le point de l'étape 1 —
   la majorité des intitulés d'un CV sont déjà au catalogue, et les payer au
   fournisseur serait absurde.

⚠ **Le module fonctionne sans clé.** Retirer la clé dans *Paramètres →
Assistance IA*, relancer une lecture : l'extraction échoue proprement, mais si
vous appelez le rapprochement sur une liste de libellés, l'étape 1 continue de
reconnaître ce qu'elle connaît et le reste part en file. C'est la règle 1 du
service, vue depuis le métier.

---

## Partie 2 — L'ambiguïté refuse de choisir (5 min)

**C'est le défaut trouvé pendant l'écriture des tests, et il vaut d'être
montré.**

1. Créer deux compétences au catalogue dont les noms ne diffèrent que par les
   accents ou la ponctuation :
   - `Gestion des risques`
   - `Gestion des risques `  (avec un espace, ou sans accent selon le cas)

2. Lancer un rapprochement sur ce libellé.

**Attendu** : aucun rapprochement automatique. Le libellé part en **file
d'arbitrage**, et le log serveur porte un avertissement nommant les deux
entrées.

Pourquoi c'est la bonne réponse : choisir l'une des deux qualifierait l'expert
au hasard, et le matching comparerait ensuite à celle que la mission a choisie.
Deux fois sur trois, personne ne se croise — **sans qu'aucune erreur ne soit
levée**. C'est le motif exact de la dette D1.

`opex.innovation.competence` n'a pas de contrainte d'unicité et le Module 2 est
gelé : on ne peut pas empêcher le doublon, seulement refuser de choisir à la
place d'un humain.

---

## Partie 3 — La file d'arbitrage (8 min)

**Configuration → Compétences à arbitrer.** L'écran s'ouvre sur les lignes en
attente.

Chaque ligne porte **d'où elle vient** : l'intervenant, le profil, le nom du
document, le niveau et les années lus. C'est la moitié « depuis quel CV » de la
traçabilité ; l'autre moitié arrive avec la décision.

Ouvrir une ligne. Trois issues, et rien d'autre :

1. **Rattacher à la compétence proposée** — l'issue la plus utile, parce
   qu'elle **enseigne**. Le synonyme créé fait que le même libellé sera reconnu
   à l'étape 1 la prochaine fois, sans appel IA et sans arbitrage.

   **À vérifier** : aller dans *Synonymes de compétences*, le nouveau synonyme
   y est, avec l'origine *Issu d'un arbitrage*. Puis relancer un rapprochement
   sur le même libellé : il passe en `synonyme`, sans appel.

2. **Ajouter au catalogue** — une confirmation est demandée, parce que la
   compétence devient disponible pour **tous les modules du portail**.

   **À vérifier** : la compétence existe dans le référentiel du Module 2
   (*Innovation → Configuration → Compétences*), et la ligne d'arbitrage porte
   désormais qui a décidé et quand.

3. **Écarter** — un CV contient des intitulés de poste, des noms d'outils, des
   mentions de diplôme. Les écarter est une réponse à part entière, et elle se
   garde : le même libellé reviendra d'un autre CV, et la trace évite de
   rejuger.

**Le test d'accès** : se connecter en `demo_client` ou `demo_expert` et tenter
d'ouvrir l'écran. Le menu n'y est pas, et un appel direct à la méthode lève —
le contrôle est dans le modèle, parce qu'une action s'appelle aussi par script
et par requête forgée.

---

## Partie 4 — Ce que l'arbitrage ne fait pas (3 min)

**À vérifier après avoir ajouté une compétence au catalogue** : ouvrir le
profil de l'intervenant d'où venait le libellé. **Aucune ligne de compétence
n'y a été ajoutée.**

Deux gestes distincts, et les confondre serait grave :

- **enrichir le catalogue** dit qu'une compétence *existe* ;
- **qualifier un expert** dit qu'une personne la *possède*.

Si l'arbitrage faisait les deux, trancher une file qualifierait des dizaines de
profils d'un coup, sur des niveaux que personne n'a regardés. La qualification
reste ce qu'elle est depuis l'IA-1 : une ligne `opex.expert.skill` avec sa
source et sa confiance, qui n'entre dans le matching qu'une fois confirmée.

---

## Ce que ce protocole ne couvre pas

**L'étape 2 demande une clé fonctionnelle.** Celle du poste authentifie mais
son projet Google est refusé en génération (403). Sans elle, la partie 1 et la
partie 3 se déroulent entièrement — c'est d'ailleurs la démonstration que
l'étape 1 rend le module utile seul — mais aucune proposition de l'IA ne
s'affichera.

**L'écriture des compétences confirmées sur le profil n'est toujours pas
automatique**, et c'est voulu. L'IA-1 a posé le principe — l'extraction
propose, l'humain décide — et l'IA-2 ne le change pas : elle rend la
proposition exploitable. Passer de la file au profil reste un geste de
qualification.

**Le back-office n'est pas vérifiable dans un navigateur piloté** :
l'extension d'automatisation casse le client web d'Odoo. Les écrans se
vérifient dans un Chrome ordinaire.
