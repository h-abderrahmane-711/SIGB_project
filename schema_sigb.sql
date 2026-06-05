-- ============================================================
-- SIGB Bibliothecaire - Schema PostgreSQL corrige
-- Projet BI 2025-2026
-- Sources : buf.csv (fonds francais) + bua.xls/Feuil1 (fonds arabe)
-- ============================================================

CREATE EXTENSION IF NOT EXISTS unaccent;

DROP TABLE IF EXISTS notice_matiere CASCADE;
DROP TABLE IF EXISTS responsabilite CASCADE;
DROP TABLE IF EXISTS exemplaire CASCADE;
DROP TABLE IF EXISTS notice CASCADE;
DROP TABLE IF EXISTS matiere CASCADE;
DROP TABLE IF EXISTS auteur CASCADE;
DROP TABLE IF EXISTS editeur CASCADE;
DROP TABLE IF EXISTS classification_dewey CASCADE;
DROP TABLE IF EXISTS langue CASCADE;

CREATE TABLE langue (
    id_langue   SERIAL PRIMARY KEY,
    code_langue CHAR(5) NOT NULL UNIQUE,
    libelle     VARCHAR(50) NOT NULL
);

INSERT INTO langue (code_langue, libelle) VALUES
    ('fr_FR', 'Francais'),
    ('ar_AR', 'Arabe');

CREATE TABLE classification_dewey (
    id_classe  SERIAL PRIMARY KEY,
    code_dewey CHAR(3) NOT NULL UNIQUE,
    libelle    VARCHAR(120) NOT NULL
);

INSERT INTO classification_dewey (code_dewey, libelle) VALUES
    ('000', 'Generalites, informatique et information'),
    ('100', 'Philosophie et psychologie'),
    ('200', 'Religion'),
    ('300', 'Sciences sociales'),
    ('400', 'Langues'),
    ('500', 'Sciences naturelles et mathematiques'),
    ('600', 'Technologie et sciences appliquees'),
    ('700', 'Arts et loisirs'),
    ('800', 'Litterature'),
    ('900', 'Histoire et geographie');

CREATE TABLE matiere (
    id_matiere SERIAL PRIMARY KEY,
    libelle    TEXT NOT NULL,
    id_langue  INT REFERENCES langue(id_langue) ON DELETE RESTRICT,
    UNIQUE (libelle, id_langue)
);

CREATE TABLE auteur (
    id_auteur   SERIAL PRIMARY KEY,
    nom_complet TEXT NOT NULL UNIQUE
);

CREATE TABLE editeur (
    id_editeur  SERIAL PRIMARY KEY,
    nom_editeur TEXT NOT NULL,
    ville       VARCHAR(150),
    UNIQUE (nom_editeur, ville)
);

CREATE TABLE notice (
    id_notice      SERIAL PRIMARY KEY,
    titre          TEXT NOT NULL,
    cote           VARCHAR(120),
    annee          SMALLINT,
    nb_pages       INT,
    id_langue      INT REFERENCES langue(id_langue) ON DELETE RESTRICT,
    id_classe      INT REFERENCES classification_dewey(id_classe) ON DELETE RESTRICT,
    id_editeur     INT REFERENCES editeur(id_editeur) ON DELETE SET NULL,
    source_fichier VARCHAR(50),
    date_creation  TIMESTAMP DEFAULT NOW(),
    CONSTRAINT chk_notice_annee CHECK (annee IS NULL OR (annee BETWEEN 1000 AND 2100)),
    CONSTRAINT chk_notice_pages CHECK (nb_pages IS NULL OR (nb_pages > 0 AND nb_pages < 10000))
);

CREATE INDEX idx_notice_titre_gin ON notice USING gin(to_tsvector('simple', coalesce(titre, '')));
CREATE INDEX idx_notice_annee ON notice(annee) WHERE annee IS NOT NULL;
CREATE INDEX idx_notice_langue ON notice(id_langue);
CREATE INDEX idx_notice_classe ON notice(id_classe);
CREATE INDEX idx_notice_source ON notice(source_fichier);

-- Table de liaison Notice <-> Auteur. Elle correspond a notice_auteur dans le MCD.
CREATE TABLE responsabilite (
    id_notice     INT NOT NULL REFERENCES notice(id_notice) ON DELETE CASCADE,
    id_auteur     INT NOT NULL REFERENCES auteur(id_auteur) ON DELETE RESTRICT,
    type_fonction VARCHAR(50) DEFAULT 'Auteur',
    PRIMARY KEY (id_notice, id_auteur)
);

CREATE TABLE notice_matiere (
    id_notice  INT NOT NULL REFERENCES notice(id_notice) ON DELETE CASCADE,
    id_matiere INT NOT NULL REFERENCES matiere(id_matiere) ON DELETE RESTRICT,
    PRIMARY KEY (id_notice, id_matiere)
);

CREATE TABLE exemplaire (
    id_exemplaire   SERIAL PRIMARY KEY,
    id_notice       INT NOT NULL REFERENCES notice(id_notice) ON DELETE CASCADE,
    code_inventaire VARCHAR(30) NOT NULL UNIQUE,
    cote_exemplaire VARCHAR(120),
    statut          VARCHAR(30) DEFAULT 'Disponible',
    localisation    VARCHAR(100) DEFAULT 'Magasin principal',
    date_entree     DATE DEFAULT CURRENT_DATE,
    CONSTRAINT chk_exemplaire_statut CHECK (statut IN ('Disponible', 'Emprunte', 'En reparation', 'Perdu')),
    CONSTRAINT chk_inventaire_format CHECK (code_inventaire ~ '^FSR_[A-Za-z0-9_-]+$')
);

CREATE INDEX idx_exemplaire_notice ON exemplaire(id_notice);
CREATE INDEX idx_exemplaire_inventaire ON exemplaire(code_inventaire);

CREATE OR REPLACE VIEW vw_audit_volumes AS
SELECT 'notices' AS objet, COUNT(*)::BIGINT AS total FROM notice
UNION ALL SELECT 'exemplaires', COUNT(*) FROM exemplaire
UNION ALL SELECT 'auteurs', COUNT(*) FROM auteur
UNION ALL SELECT 'editeurs', COUNT(*) FROM editeur
UNION ALL SELECT 'matieres', COUNT(*) FROM matiere;
