# SIGB Bibliothecaire - Projet BI 2025-2026

## Objectif

Ce projet implemente un mini-SIGB pour integrer deux sources bibliographiques :

- `buf.csv` : fonds francais, CSV separe par `;`, encodage CP1252/ISO-8859-1 ;
- `bua.xls` : fonds arabe, Excel 97-2003, feuille principale `Feuil1`.

Le livrable contient le schema PostgreSQL, le script d'integration, les donnees nettoyees, le MCD/MLD, les vues SQL Power BI, le rapport et le tableau de bord.

## Contenu

| Fichier / dossier | Role |
|---|---|
| `schema_sigb.sql` | Creation des 9 tables, contraintes, index et vue d'audit |
| `insert_sigb.py` | Script Python d'extraction, nettoyage et insertion |
| `views_powerbi.sql` | Vues SQL pour la restitution Power BI |
| `MCD_MLD.md` | MCD/MLD et correspondance sources/tables |
| `Rapport/Rapport.pdf` | Rapport principal |
| `Rapport/Corrections_et_complements.md` | Addendum avec corrections et clarifications |
| `final_data/` | Exports nettoyes en UTF-8 |
| `sigbVis.pbix` | Tableau de bord Power BI |
| `requirements.txt` | Dependances Python |

## Installation Python

```bash
pip install -r requirements.txt
```

Si `requirements.txt` n'est pas utilise :

```bash
pip install pandas psycopg2-binary xlrd openpyxl
```

`xlrd` est necessaire pour lire `bua.xls`.

## Configuration PostgreSQL

Par defaut, le script utilise :

- host : `127.0.0.1`
- port : `5432`
- base : `sigb_db`
- user : `postgres`
- password : `yb1234`

Il est possible de surcharger avec des variables d'environnement :

```powershell
$env:SIGB_DB_HOST = "127.0.0.1"
$env:SIGB_DB_PORT = "5432"
$env:SIGB_DB_NAME = "sigb_db"
$env:SIGB_DB_USER = "postgres"
$env:SIGB_DB_PASSWORD = "votre_mot_de_passe"
```

## Execution Complete

Depuis `C:\Users\Dell\Downloads\sigb_project` :

```powershell
createdb -U postgres sigb_db
psql -U postgres -d sigb_db -f schema_sigb.sql
python insert_sigb.py
psql -U postgres -d sigb_db -f views_powerbi.sql
```

Si la base existe deja, appliquer au minimum :

```powershell
psql -U postgres -d sigb_db -f schema_sigb.sql
python insert_sigb.py
psql -U postgres -d sigb_db -f views_powerbi.sql
```

Important : `schema_sigb.sql` est reexecutable et recrée les tables. Il doit donc etre lance avant l'import si le schema a change.

## Probleme Corrige

L'erreur suivante :

```text
there is no unique or exclusion constraint matching the ON CONFLICT specification
```

venait d'un decalage entre le script et la table `editeur`. Le script faisait un `ON CONFLICT`, mais la contrainte unique attendue n'etait pas presente dans la base active.

Correction appliquee :

- `editeur` possede maintenant `UNIQUE (nom_editeur, ville)` ;
- le script utilise `ON CONFLICT (nom_editeur, ville)` ;
- il faut relancer `schema_sigb.sql` avant `insert_sigb.py`.

## Qualite de l'integration

- Encodage francais lu en CP1252 ;
- Arabe conserve via Excel/Unicode ;
- Inventaires normalises en `FSR_xxxxx` sans supprimer les zeros finaux ;
- Cotes nettoyees sans doubles slashs ;
- Annees validees entre 1000 et 2100 ;
- Pages validees entre 1 et 9999 ;
- Auteurs, editeurs et matieres normalises dans des tables separees ;
- Doublons d'inventaire ignores et journalises ;
- Donnees nettoyees exportees dans `final_data/`.
