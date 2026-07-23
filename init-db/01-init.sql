-- Runs automatically the FIRST time the db container's data volume is empty.
-- (Docker only executes /docker-entrypoint-initdb.d/*.sql on a fresh volume —
--  if you change this file after the volume exists, run `docker compose down -v`
--  to wipe and re-init, or apply it manually with psql.)

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS accused (
    "AccusedMasterID"      TEXT PRIMARY KEY,
    "Name"                 TEXT NOT NULL,
    "Age"                  INTEGER NOT NULL,
    "IsRepeatOffenderFlag" BOOLEAN NOT NULL DEFAULT FALSE,
    "PriorOffenseCount"    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS case_master (
    "CaseID"              TEXT PRIMARY KEY,
    "AccusedMasterID"     TEXT REFERENCES accused("AccusedMasterID"),
    "CrimeMinorHead"      TEXT NOT NULL,
    "Latitude"            DOUBLE PRECISION NOT NULL,
    "Longitude"           DOUBLE PRECISION NOT NULL,
    "OccurredAt"          TIMESTAMP NOT NULL,
    "BriefFacts"          TEXT,
    "GravityOffenceScore" NUMERIC(4,3),
    "Geom"                GEOMETRY(Point, 4326)   -- populated via trigger below
);

CREATE TABLE IF NOT EXISTS act_section_association (
    id            SERIAL PRIMARY KEY,
    "CaseID"      TEXT REFERENCES case_master("CaseID"),
    "SectionCode" TEXT NOT NULL
);

-- Keep Geom in sync with Latitude/Longitude automatically
CREATE OR REPLACE FUNCTION set_case_geom() RETURNS TRIGGER AS $$
BEGIN
    NEW."Geom" := ST_SetSRID(ST_MakePoint(NEW."Longitude", NEW."Latitude"), 4326);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_set_case_geom ON case_master;
CREATE TRIGGER trg_set_case_geom
    BEFORE INSERT OR UPDATE ON case_master
    FOR EACH ROW EXECUTE FUNCTION set_case_geom();

CREATE INDEX IF NOT EXISTS idx_case_geom ON case_master USING GIST ("Geom");
CREATE INDEX IF NOT EXISTS idx_case_accused ON case_master ("AccusedMasterID");
CREATE INDEX IF NOT EXISTS idx_section_case ON act_section_association ("CaseID");
