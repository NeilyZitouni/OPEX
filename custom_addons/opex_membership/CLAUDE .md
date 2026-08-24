# CLAUDE.md — `opex_membership`

⚠ **Ce fichier ne contient plus aucune spécification.** Il en contenait deux, qui
ne concernaient ni l'une ni l'autre ce module, concaténées bout à bout :

| Ancien contenu | Où il vit maintenant |
|---|---|
| Lignes 1–1188 — `opex_workflow` + `opex_innovation` | `../opex_workflow/CLAUDE.md` |
| Lignes 1189–1666 — `opex_crowdfunding` | `../opex_crowdfunding/CLAUDE.md` |

**La spécification de `opex_membership` est dans `claudeAncient.md`**, sous le
titre « Module OPEX Membership — Phase 2 : Portail Web & Intégrations ». Elle n'a
jamais été dans ce fichier-ci.

---

⛔ **`opex_membership` est gelé avant sa présentation à l'encadrant.** Ne rien y
modifier. Les modules qui ont besoin d'étendre `res.partner` ou de lire les
catégories d'adhésion le font depuis chez eux — voir
`opex_innovation/models/res_partner.py`, qui déclare les profils Expert et
Investisseur sans toucher une ligne d'ici.
