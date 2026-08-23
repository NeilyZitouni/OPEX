# Instance 01 — Smart Crowdfunding

## 1. Finalité

Le **Smart Crowdfunding** est une instance du moteur générique **CEO Smart Workflow** permettant d'orchestrer de manière Lean et progressive la relation entre :

**Porteur de projet → CEO → Contrôle Qualité → Experts → Acteurs financiers**

L'objectif n'est pas de demander au porteur de constituer immédiatement un dossier lourd, mais d'appliquer une logique de **progressive commitment** :

> **Demander le minimum d'information nécessaire à chaque étape pour décider de la suivante.**

Le processus doit ainsi éliminer les dossiers inutiles, réduire les délais de décision et ne solliciter les différents acteurs que lorsqu'une action de leur part apporte réellement de la valeur.

---

# 2. Acteurs du workflow

### A. Porteur de projet

Peut être :

- une personne physique ;
- une startup ;
- une entreprise ;
- un groupe ;
- une association ;
- une autre personne morale.

Il peut :

- déposer une demande ;
- compléter progressivement son dossier ;
- répondre aux demandes de clarification ;
- demander un accompagnement CEO ;
- accepter ou refuser une proposition d'accompagnement ;
- autoriser la mise en relation avec des acteurs financiers ;
- suivre l'avancement de son projet.

---

### B. Comité CEO

Il joue le rôle d'orchestrateur du processus.

Il peut :

- qualifier une demande ;
- décider de poursuivre ou non ;
- demander des informations complémentaires ;
- soumettre le dossier au contrôle qualité ;
- décider d'un accompagnement ;
- mandater des experts ;
- autoriser le matching financier ;
- suivre les interactions entre les différents acteurs.

Le CEO peut donc être **tiers de confiance et orchestrateur**, mais également devenir **acteur de l'accompagnement du projet**, avec une contrepartie définie selon le modèle retenu.

---

### C. Contrôle Qualité

Le Contrôle Qualité constitue un **Quality Gate opérationnel**.

Dans le MVP, ce contrôle peut être réalisé par une personne ou un comité.

À terme :

**Contrôle humain → Contrôle assisté par IA → Agent IA autonome sous supervision CEO.**

Il vérifie notamment :

- complétude ;
- cohérence ;
- qualité des informations ;
- conformité aux critères ;
- anomalies éventuelles ;
- présence des justificatifs requis.

Il produit un avis structuré :

**OK / À compléter / Alerte / Non conforme.**

La décision métier finale reste portée par le workflow et les acteurs autorisés.

---

### D. Expert / Comité d'experts

Un ou plusieurs experts peuvent être mandatés par CEO.

Ils peuvent intervenir pour :

- diagnostic ;
- expertise ;
- due diligence ;
- maturation ;
- coaching ;
- amélioration du business model ;
- préparation à l'investissement ;
- accompagnement technique ou commercial.

Le choix des experts peut provenir du **Smart Matching Engine**.

---

### E. Acteur financier

L'acteur financier peut être :

- investisseur/actionnaire ;
- partenaire financier privé ;
- organisme public de financement ;
- banque ou institution financière ;
- sponsor ;
- partenaire stratégique.

Son rôle et donc son niveau d'accès au dossier dépendent du type de relation envisagé.

---

# 3. Principe de visibilité

Tous les acteurs sont préalablement identifiés dans le référentiel CEO.

Le moteur attribue dynamiquement :

**Identité + rôle + relation au dossier + étape du workflow → droits d'accès.**

Ainsi, être enregistré comme investisseur ne donne pas automatiquement accès à tous les projets.

Exemple :

```text
Projet A
│
├── Porteur            → accès à son dossier
├── CEO                → accès complet
├── Contrôle Qualité   → accès aux données nécessaires au contrôle
├── Expert X           → accès au périmètre de sa mission
├── Investisseur Y     → accès au dossier autorisé / partagé
└── Investisseur Z     → aucun accès
```

Cette logique prolonge le principe du portail existant dans lequel organisations, experts et porteurs appartiennent à un référentiel commun, indépendamment des rôles qu'ils occupent.

---

# 4. Workflow macro Lean

Le workflow de référence est :

```text
① DÉPÔT EXPRESS
      ↓
② PRÉ-ANALYSE
      ↓
   GO / NO GO
      ↓
③ DOSSIER PROGRESSIF
      ↓
④ QUALITY GATE
      ↓
⑤ ÉTUDE / DÉCISION
      ↓
      ├──────────────┐
      ↓              ↓
⑥ MATCHING       ⑦ MATURATION
FINANCIER            │
      │              ↓
      │         ACCOMPAGNEMENT CEO
      │              │
      │              ↓
      │         RÉÉVALUATION
      │              │
      └───────┬──────┘
              ↓
       MATCHING FINANCIER
              ↓
       ⑧ MISE EN RELATION
              ↓
       ⑨ NÉGOCIATION / DÉCISION
              ↓
       ⑩ CLOSING / SUIVI
```

Il ne s'agit donc pas nécessairement d'un processus linéaire.

Le moteur doit supporter les **boucles de maturation et de réévaluation**.

---

# 5. Étape 1 — Dépôt Express

### Objectif

Permettre à un porteur d'entrer dans le dispositif en quelques minutes.

Il ne dépose **pas encore un dossier complet**.

### Informations minimales

Exemple :

- identité ;
- type de porteur ;
- titre du projet ;
- problème/opportunité ;
- solution proposée ;
- secteur ;
- maturité actuelle ;
- besoin recherché ;
- montant indicatif si financement demandé ;
- document/pitch facultatif.

### UX

Le CTA doit rester simple :

**« Présenter mon projet »**

et non :

**« Constituer mon dossier de financement »**.

---

# 6. Étape 2 — Pré-analyse / Go-No Go

CEO réalise une première qualification selon des critères configurables.

Exemples :

```text
Adéquation avec les domaines CEO
Potentiel
Caractère innovant
Faisabilité apparente
Maturité minimale
Besoin identifiable
Crédibilité du porteur
```

Résultats possibles :

```text
GO
│
└── poursuivre le dossier

À CLARIFIER
│
└── poser 1..N questions ciblées

NO GO
│
└── clôture motivée

ORIENTATION
│
└── accompagnement/maturation conseillé
```

Le moteur doit donc supporter plusieurs transitions depuis une même étape.

---

# 7. Étape 3 — Dossier progressif

Uniquement après un **GO**, le système demande les informations supplémentaires nécessaires.

Le formulaire peut dépendre du besoin.

### Exemple

Un projet recherchant un investisseur peut recevoir :

```text
Business Model
Marché
Traction
Équipe
Besoin financier
Utilisation des fonds
Valorisation éventuelle
Prévisions financières
Pitch Deck
```

Un projet recherchant un sponsor aura un questionnaire différent.

Un projet recherchant un financement public peut avoir encore un autre parcours.

Le moteur doit donc permettre :

**Étape → Type de projet → Type de financement → Formulaire dynamique.**

---

# 8. Étape 4 — Quality Gate

Le Contrôle Qualité intervient avant de mobiliser inutilement CEO, experts ou investisseurs.

```text
DOSSIER
   ↓
QUALITY GATE
   │
   ├── Conforme ──────────→ Étude
   │
   ├── À compléter ───────→ Porteur
   │
   └── Alerte ────────────→ CEO
```

À terme :

```text
Documents
   +
Données structurées
   +
Règles CEO
   ↓
Agent IA Quality Control
   ↓
Score + anomalies + recommandations
   ↓
Validation / supervision humaine
```

Le remplacement futur du contrôleur par un agent IA ne doit donc nécessiter **aucune modification du workflow métier** : seul le type d'acteur exécutant l'activité change.

---

# 9. Étape 5 — Étude et décision

Le dossier qualifié arrive au comité CEO.

Trois orientations principales sont proposées.

### Route A — Investment Ready

Le projet est suffisamment mature.

```text
Projet
  ↓
Matching financier
```

### Route B — Potentiel mais maturation nécessaire

```text
Projet
  ↓
Recommandation CEO
  ↓
Accompagnement
  ↓
Réévaluation
  ↓
Matching financier
```

### Route C — Non retenu

```text
Projet
  ↓
Décision motivée
  ↓
Clôture
```

Le rejet ne doit donc pas être confondu avec la maturation.

Un projet intéressant mais insuffisamment mature reste dans le pipeline.

---

# 10. Étape 6 — Smart Matching financier

Le moteur recherche les acteurs financiers compatibles.

Exemple de critères :

```text
Type de financement
Secteur
Ticket d'investissement
Stade du projet
Localisation
Appétence au risque
Type de porteur
Impact
Technologie
Historique
```

Résultat :

```text
Projet PRJ-127

1. Investisseur A       91 %
2. Fonds B              86 %
3. Programme public C   82 %
4. Sponsor D            74 %
```

Le matching est une **recommandation**.

CEO peut :

**Valider / Modifier / Exclure / Ajouter un acteur.**

Le matching entre projets et investisseurs est déjà prévu dans les spécifications fonctionnelles d'OPEX Innovation.

---

# 11. Étape 7 — Accompagnement CEO

L'accompagnement peut être déclenché de trois manières.

### Cas 1 — Recommandation CEO

CEO estime :

> « Projet intéressant mais pas encore Investment Ready. »

Il propose un accompagnement.

### Cas 2 — Demande de l'acteur financier

L'investisseur peut indiquer :

> **Intéressé sous condition d'accompagnement CEO.**

Le workflow devient :

```text
Investisseur intéressé
        ↓
Condition
"Accompagnement CEO"
        ↓
Proposition au porteur
        ↓
Acceptation
        ↓
Mission CEO / Experts
        ↓
Réévaluation
        ↓
Retour investisseur
```

### Cas 3 — Demande directe du porteur

À tout moment autorisé du parcours, le porteur peut demander :

**« Être accompagné par CEO »**

La demande génère un sous-workflow :

```text
Demande
   ↓
Diagnostic
   ↓
Proposition d'accompagnement
   ↓
Contrepartie / conditions
   ↓
Acceptation
   ↓
Matching Expert(s)
   ↓
Mission
   ↓
Jalons
   ↓
Livrables
   ↓
Service fait
   ↓
Évaluation
```

Cela réutilise directement la logique déjà prévue dans le portail pour les experts : sélection, contractualisation, mission, suivi, validation et évaluation.

---

# 12. Contrepartie CEO

Le workflow ne doit pas coder en dur le modèle économique.

La contrepartie doit être configurable.

Par exemple :

```text
Forfait
Commission au succès
Success fee
Participation
Abonnement
Prestation d'accompagnement
Sponsoring
Gratuité dans le cadre d'un programme
Autre convention
```

La transition :

**Accompagnement proposé → Accompagnement actif**

peut alors avoir comme précondition :

```text
Convention acceptée = TRUE
```

---

# 13. Étape 8 — Mise en relation contrôlée

Point important pour la confidentialité : le matching ne signifie pas automatiquement partage du dossier complet.

Je recommande :

```text
MATCH
  ↓
Teaser anonymisé
  ↓
Expression d'intérêt
  ↓
Autorisation de partage
  ↓
NDA si nécessaire
  ↓
Dossier détaillé
  ↓
Meeting / Data Room
```

Cela permet d'appliquer le principe du **minimum nécessaire**, également aux informations.

---

# 14. Étape 9 — Décision de l'acteur financier

L'acteur financier dispose d'actions simples :

```text
★ Intéressé

? Besoin d'informations

↗ Demander accompagnement CEO

↔ Proposer un rendez-vous

✕ Non intéressé
```

Il ne doit pas avoir à comprendre le workflow interne CEO.

Le moteur transforme son choix en transition appropriée.

---

# 15. Étape 10 — Closing et suivi

Selon la nature de l'acteur financier :

```text
Investissement
Partenariat
Financement public
Sponsoring
Prêt
Convention
Autre
```

Le workflow peut déclencher :

- documents ;
- validations ;
- signature ;
- jalons ;
- versements ;
- reporting ;
- engagements du porteur ;
- suivi post-financement.

Le dossier devient alors un projet suivi plutôt qu'une simple candidature.

---

# 16. Principe UX : chaque acteur voit son propre workflow

Le **workflow système peut être complexe**.

L'expérience utilisateur ne doit pas l'être.

### Porteur

```text
Mon projet

✓ Demande reçue
✓ Projet présélectionné
● Compléter mon dossier
○ Étude
○ Mise en relation

Votre prochaine action :
[ Compléter mon dossier ]
```

### Investisseur

```text
3 projets correspondent
à vos critères.

SmartFactory DZ        92 %
GreenPack               87 %
MedTech AI              81 %

[ Découvrir ]
```

### Expert

```text
Nouvelle mission proposée

Projet : SmartFactory DZ
Besoin : Business Model & Go-to-Market

[ Accepter ]
[ Décliner ]
```

### CEO

```text
SMART WORK QUEUE

4  Préqualifications
2  Contrôles en anomalie
3  Décisions CEO
5  Matchings à valider
2  Investisseurs en attente
3  Accompagnements en retard
```

Le principe est donc :

> **Ne pas demander à l'utilisateur de piloter le workflow. Le workflow doit guider l'utilisateur.**

---

# 17. Traduction dans le moteur générique

Cette instance permet de tester pratiquement toutes les capacités attendues du `CEO Smart Workflow Engine`.

| Besoin Smart Crowdfunding | Capacité générique |
|---|---|
| Dépôt express | Form / Event |
| Préqualification | Stage + Rule |
| Go / No Go | Transition |
| Dossier complémentaire | Dynamic Form |
| Contrôle qualité | Quality Gate |
| Comité CEO | Approval |
| Matching experts | Matching Service |
| Matching investisseurs | Matching Service |
| Accompagnement | Sub-Workflow |
| Demande investisseur | Event / Transition |
| Condition d'accompagnement | Business Rule |
| Contrepartie CEO | Contract Rule |
| NDA | Document Action |
| Mise en relation | Workflow Action |
| Relance | SLA / Automation |
| Agent IA | Automated Actor |
| Historique | Audit Trail |

Ainsi, **Smart Crowdfunding ne doit pas être développé comme un workflow codé**.

Il doit être livré comme :

> **une configuration démonstratrice du moteur générique `CEO Smart Workflow`.**

---

# 18. Critère de démonstration aux stagiaires

Une fois Smart Crowdfunding configuré et opérationnel, on demande aux stagiaires :

> **« Ajoutez une étape Demo Day entre Accompagnement et Matching Investisseurs. Elle nécessite l'accord du CEO, une présentation Pitch Deck et une note ≥ 70/100. »**

Ils doivent pouvoir réaliser cela depuis le configurateur :

```text
Accompagnement
      ↓
   Demo Day
      ↓
[CEO approuve]
[Pitch présent]
[Score ≥ 70]
      ↓
Matching Investisseurs
```

**sans modifier le code Python du moteur.**

C'est ce test qui démontrera réellement que nous avons construit un **Smart Workflow Engine générique** et non simplement codé le processus Smart Crowdfunding.