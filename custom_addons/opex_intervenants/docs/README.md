# `docs/` — les documents de référence du Module 3

Les originaux vivent dans `custom_addons/opex_membership/docs/` et **font foi**.
Ce dossier n'en contient que des extractions texte, posées ici pour qu'un
`ls docs/` depuis le module donne ce que le `CLAUDE.md` annonce.

| Fichier | Origine | Autorité |
|---|---|---|
| `Module3_OPEX_Intervenants.md` | `Module3_OPEX_Intervenants (1).pdf`, 38 pages, 48 sections | **Référence UX du métier** — écrans, libellés, règles métier |
| `Specification_OPEX_Smart_Missions.md` | `Specification_OPEX_Smart_Missions_Appel_Candidatures-4Students.pdf`, 7 pages | **Architecture, états, scoring, modèle de données** |
| `product_backlog.md` | copie conforme | US-09 à US-14, US-19, US-20, US-22 |
| `portail_digital_vision.md` | `Portail Digital du GIC OPEX Group rev1.0.pdf` | Le Domaine 3 dans le portail global |
| `instance_smart_crowdfunding.md` | copie conforme | **Les capacités du moteur**, pour savoir ce qui est déjà disponible |
| `schemas/` | 21 images extraites du PDF Module 3 | Les schémas, seule forme sous laquelle ils existent |

## Les schémas ne sont pas dans le texte

`pdf.extract_text()` ne rend aucun des 18 schémas : ce sont des images. Les
extractions `.md` portent donc la légende (« Schéma 15 — Machine à états de la
mission ») et **pas son contenu**. Lire `schemas/` chaque fois qu'une légende
apparaît.

Les trois qui comptent pour l'Extension 1 :

| Image | Contenu |
|---|---|
| `schemas/p30_schema_15.png` | Machine à états de la mission, version document UX |
| `schemas/p14_schema_5.png` | Statuts d'une candidature, version document UX |
| `schemas/p11_schema_3.png` | Workflow de validation de la demande — la boucle « Informations manquantes → retour au client », qu'**aucune** des deux listes d'états ne nomme |

Rappel : ces schémas sont la référence **UX**. La machine à états configurée est
celle du §12.1 / §12.2 de la spécification Smart Missions — arbitrage rendu,
table de correspondance dans le `CLAUDE.md`.

## `instance_smart_crowdfunding.md` n'est pas `opex_crowdfunding`

Ce document décrit **les capacités attendues du moteur générique** et sert de
banc d'essai à `opex_workflow`. Le module `opex_crowdfunding`, lui, est isolé par
construction : `opex_intervenants` ne le référence jamais, ni dans son manifeste,
ni dans son code, ni dans ses tests.
