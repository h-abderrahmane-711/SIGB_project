#!/usr/bin/env python3
# ============================================================
# SIGB Bibliothecaire - Script d'integration PostgreSQL
# Sources : buf.csv (Francais) + bua.xls (Arabe)
# Usage   : python insert_sigb.py
# ============================================================

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

import pandas as pd
import psycopg2

BASE_DIR = Path(__file__).parent
CSV_FR_PATH = BASE_DIR / "buf.csv"
XLS_AR_PATH = BASE_DIR / "bua.xls"
CLEAN_DIR = BASE_DIR / "final_data"

DB_CONFIG = {
    "host": os.getenv("SIGB_DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("SIGB_DB_PORT", "5432")),
    "dbname": os.getenv("SIGB_DB_NAME", "sigb_db"),
    "user": os.getenv("SIGB_DB_USER", "postgres"),
    "password": os.getenv("SIGB_DB_PASSWORD", "yb1234"),
}

COLUMNS = [
    "Cote",
    "Titre",
    "Auteur",
    "Lieu",
    "Editeur",
    "Annee",
    "Nb_pages",
    "Matiere",
    "Inventaire",
]
EXPORT_COLUMNS = ["Cote", "Titre", "Auteur", "Editeur", "Lieu", "Annee", "Nb pages", "Matiere", "Inventaire"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(BASE_DIR / "import_log.txt", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def clean_str(value) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).replace("\u00a0", " ").strip().strip('"').strip("'").strip()
    text = re.sub(r"\s+", " ", text)
    return text or None


def clean_cote(value) -> str | None:
    text = clean_str(value)
    if not text:
        return None
    text = text.replace("_", "/")
    text = re.sub(r"/{2,}", "/", text)
    return text.strip(" /") or None


def clean_annee(value) -> int | None:
    text = clean_str(value)
    if not text:
        return None
    match = re.search(r"\d{3,4}", text)
    if not match:
        return None
    year = int(match.group(0))
    return year if 1000 <= year <= 2100 else None


def clean_pages(value) -> int | None:
    text = clean_str(value)
    if not text:
        return None
    match = re.search(r"\d+", text)
    if not match:
        return None
    pages = int(match.group(0))
    return pages if 0 < pages < 10000 else None


def format_inventaire(value) -> str | None:
    """Normalise l'inventaire sans supprimer les zeros significatifs finaux."""
    if pd.isna(value):
        return None
    if isinstance(value, float) and value.is_integer():
        raw = str(int(value))
    else:
        raw = str(value).strip()
        raw = re.sub(r"\.0$", "", raw)
    raw = re.sub(r"[^0-9A-Za-z_-]", "", raw)
    if not raw:
        return None
    if raw.upper().startswith("FSR"):
        raw = re.sub(r"^FSR_?", "", raw, flags=re.IGNORECASE)
    return f"FSR_{raw}"


def get_dewey_code(cote: str | None) -> str | None:
    if not cote:
        return None
    match = re.search(r"\d+", cote)
    if not match:
        return None
    value = int(match.group(0)[:3].ljust(3, "0"))
    if value > 999:
        return None
    return str((value // 100) * 100).zfill(3)


def split_authors(value: str | None) -> list[str]:
    text = clean_str(value)
    if not text:
        return []
    parts = re.split(r"\s*;\s*", text)
    return [part.strip() for part in parts if part.strip() and part.strip() not in {"-", "."}]


def db_value(value):
    if pd.isna(value):
        return None
    return value


def load_data() -> pd.DataFrame:
    log.info("Chargement buf.csv (Francais)...")
    df_fr = pd.read_csv(CSV_FR_PATH, names=COLUMNS, encoding="cp1252", delimiter=";")
    df_fr["_lang"] = "fr_FR"
    df_fr["_source"] = "buf.csv"
    log.info("  -> %s lignes chargees", len(df_fr))

    log.info("Chargement bua.xls (Arabe, Feuil1)...")
    df_ar = pd.read_excel(XLS_AR_PATH, sheet_name=0, header=0, engine="xlrd")
    df_ar = df_ar.iloc[:, :9]
    df_ar.columns = COLUMNS
    df_ar["_lang"] = "ar_AR"
    df_ar["_source"] = "bua.xls/Feuil1"
    log.info("  -> %s lignes chargees", len(df_ar))

    df = pd.concat([df_fr, df_ar], ignore_index=True)
    log.info("Total combine : %s lignes", len(df))
    return df


def normalize_data(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    cleaned["Cote"] = cleaned["Cote"].map(clean_cote)
    for col in ["Titre", "Auteur", "Lieu", "Editeur", "Matiere"]:
        cleaned[col] = cleaned[col].map(clean_str)
    cleaned["Annee"] = cleaned["Annee"].map(clean_annee)
    cleaned["Nb_pages"] = cleaned["Nb_pages"].map(clean_pages)
    cleaned["Inventaire"] = cleaned["Inventaire"].map(format_inventaire)
    return cleaned


def export_clean_files(df: pd.DataFrame) -> None:
    CLEAN_DIR.mkdir(exist_ok=True)
    export = df.rename(columns={"Nb_pages": "Nb pages"})
    export[export["_lang"] == "fr_FR"][EXPORT_COLUMNS].to_csv(CLEAN_DIR / "buf_clean.csv", index=False, encoding="utf-8")
    export[export["_lang"] == "ar_AR"][EXPORT_COLUMNS].to_csv(CLEAN_DIR / "bua_clean.csv", index=False, encoding="utf-8")
    log.info("Fichiers nettoyes exportes dans final_data/")


def insert_all(conn, df: pd.DataFrame) -> dict[str, int]:
    cur = conn.cursor()
    lang_cache: dict[str, int] = {}
    dewey_cache: dict[str, int] = {}
    editeur_cache: dict[tuple[str, str | None], int] = {}
    auteur_cache: dict[str, int] = {}
    matiere_cache: dict[tuple[str, int], int] = {}
    inventaire_seen: set[str] = set()

    cur.execute("SELECT code_langue, id_langue FROM langue")
    lang_cache.update(cur.fetchall())
    cur.execute("SELECT code_dewey, id_classe FROM classification_dewey")
    dewey_cache.update(cur.fetchall())

    def get_or_create_editeur(nom: str | None, ville: str | None) -> int | None:
        if not nom:
            return None
        key = (nom[:300], ville[:150] if ville else None)
        if key in editeur_cache:
            return editeur_cache[key]
        cur.execute(
            """
            INSERT INTO editeur (nom_editeur, ville)
            VALUES (%s, %s)
            ON CONFLICT (nom_editeur, ville)
            DO UPDATE SET nom_editeur = EXCLUDED.nom_editeur
            RETURNING id_editeur
            """,
            key,
        )
        editeur_cache[key] = cur.fetchone()[0]
        return editeur_cache[key]

    def get_or_create_auteur(nom: str | None) -> int | None:
        if not nom:
            return None
        key = nom[:300]
        if key in auteur_cache:
            return auteur_cache[key]
        cur.execute(
            """
            INSERT INTO auteur (nom_complet)
            VALUES (%s)
            ON CONFLICT (nom_complet) DO NOTHING
            RETURNING id_auteur
            """,
            (key,),
        )
        row = cur.fetchone()
        if row is None:
            cur.execute("SELECT id_auteur FROM auteur WHERE nom_complet = %s", (key,))
            row = cur.fetchone()
        auteur_cache[key] = row[0]
        return auteur_cache[key]

    def get_or_create_matiere(libelle: str | None, id_langue: int) -> int | None:
        if not libelle:
            return None
        key = (libelle[:500], id_langue)
        if key in matiere_cache:
            return matiere_cache[key]
        cur.execute(
            """
            INSERT INTO matiere (libelle, id_langue)
            VALUES (%s, %s)
            ON CONFLICT (libelle, id_langue) DO NOTHING
            RETURNING id_matiere
            """,
            key,
        )
        row = cur.fetchone()
        if row is None:
            cur.execute("SELECT id_matiere FROM matiere WHERE libelle = %s AND id_langue = %s", key)
            row = cur.fetchone()
        matiere_cache[key] = row[0]
        return matiere_cache[key]

    stats = {
        "raw_rows": len(df),
        "inserted_notices": 0,
        "skipped_empty_title": 0,
        "skipped_duplicate_inventaire": 0,
        "rows_without_inventory": 0,
    }

    for idx, row in df.iterrows():
        if idx % 1000 == 0:
            log.info("  Progression : %s/%s (%s%%)", idx, len(df), 100 * idx // max(len(df), 1))
            conn.commit()

        titre = row["Titre"]
        if not titre:
            log.warning("Ligne %s ignoree : titre vide", idx)
            stats["skipped_empty_title"] += 1
            continue

        inventaire = row["Inventaire"]
        if inventaire:
            if inventaire in inventaire_seen:
                log.warning("Doublon inventaire ignore : %s", inventaire)
                stats["skipped_duplicate_inventaire"] += 1
                continue
            inventaire_seen.add(inventaire)
        else:
            stats["rows_without_inventory"] += 1

        id_lang = lang_cache.get(row["_lang"])
        cote = row["Cote"]
        id_classe = dewey_cache.get(get_dewey_code(cote))
        id_editeur = get_or_create_editeur(row["Editeur"], row["Lieu"])

        cur.execute(
            """
            INSERT INTO notice (titre, cote, annee, nb_pages, id_langue, id_classe, id_editeur, source_fichier)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id_notice
            """,
            (
                titre,
                cote,
                db_value(row["Annee"]),
                db_value(row["Nb_pages"]),
                id_lang,
                id_classe,
                id_editeur,
                row["_source"],
            ),
        )
        id_notice = cur.fetchone()[0]

        for auteur in split_authors(row["Auteur"]):
            id_auteur = get_or_create_auteur(auteur)
            if id_auteur:
                cur.execute(
                    """
                    INSERT INTO responsabilite (id_notice, id_auteur, type_fonction)
                    VALUES (%s, %s, 'Auteur')
                    ON CONFLICT DO NOTHING
                    """,
                    (id_notice, id_auteur),
                )

        id_matiere = get_or_create_matiere(row["Matiere"], id_lang)
        if id_matiere:
            cur.execute(
                """
                INSERT INTO notice_matiere (id_notice, id_matiere)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (id_notice, id_matiere),
            )

        if inventaire:
            cur.execute(
                """
                INSERT INTO exemplaire (id_notice, code_inventaire, cote_exemplaire)
                VALUES (%s, %s, %s)
                ON CONFLICT (code_inventaire) DO NOTHING
                """,
                (id_notice, inventaire, cote),
            )

        stats["inserted_notices"] += 1

    conn.commit()
    stats["distinct_authors_cache"] = len(auteur_cache)
    stats["distinct_publishers_cache"] = len(editeur_cache)
    stats["distinct_subjects_cache"] = len(matiere_cache)

    log.info("=" * 60)
    log.info("Import termine")
    for key, value in stats.items():
        log.info("   %-32s : %s", key, value)
    log.info("=" * 60)
    cur.close()
    return stats


def print_stats(conn) -> None:
    cur = conn.cursor()
    queries = {
        "Total notices": "SELECT COUNT(*) FROM notice",
        "Notices francaises": "SELECT COUNT(*) FROM notice n JOIN langue l ON n.id_langue = l.id_langue WHERE l.code_langue = 'fr_FR'",
        "Notices arabes": "SELECT COUNT(*) FROM notice n JOIN langue l ON n.id_langue = l.id_langue WHERE l.code_langue = 'ar_AR'",
        "Total exemplaires": "SELECT COUNT(*) FROM exemplaire",
        "Total auteurs": "SELECT COUNT(*) FROM auteur",
        "Total editeurs": "SELECT COUNT(*) FROM editeur",
        "Total matieres": "SELECT COUNT(*) FROM matiere",
    }
    log.info("")
    log.info("Statistiques de la base :")
    for label, query in queries.items():
        cur.execute(query)
        log.info("   %-25s: %7s", label, cur.fetchone()[0])
    cur.close()


if __name__ == "__main__":
    log.info("Connexion a PostgreSQL...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        log.info("Connecte")
    except Exception as exc:
        log.error("Connexion echouee : %s", exc)
        log.error("Verifiez SIGB_DB_HOST, SIGB_DB_PORT, SIGB_DB_NAME, SIGB_DB_USER et SIGB_DB_PASSWORD.")
        sys.exit(1)

    try:
        raw_df = load_data()
        clean_df = normalize_data(raw_df)
        export_clean_files(clean_df)
        insert_all(conn, clean_df)
        print_stats(conn)
    except Exception as exc:
        conn.rollback()
        log.error("Erreur fatale : %s", exc)
        raise
    finally:
        conn.close()
        log.info("Connexion fermee.")
