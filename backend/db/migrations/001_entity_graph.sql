-- Migration 001: Entity Graph — Story Provenance & Entity Relationships
-- Run against an existing media_metrics database to add Phase 1 entity graph tables.
-- All statements use IF NOT EXISTS / IF NOT EXISTS guards — safe to run multiple times.

-- Geographic entities
CREATE TABLE IF NOT EXISTS locations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city TEXT,
    state TEXT,
    country TEXT NOT NULL DEFAULT 'US',
    lat FLOAT,
    lng FLOAT,
    display_name TEXT,
    meta JSONB
);

-- Organizations (rich entity for news outlets, wire services, parent companies, investors)
CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL UNIQUE,
    slug TEXT UNIQUE,
    org_type TEXT,
    domain TEXT,
    location_id UUID REFERENCES locations(id),
    founding_year INTEGER,
    dissolved_year INTEGER,
    political_lean FLOAT,
    country TEXT DEFAULT 'US',
    parent_org_id UUID REFERENCES organizations(id),
    wikipedia_url TEXT,
    wikidata_id TEXT,
    meta JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- People (rich entity for journalists, editors, executives)
CREATE TABLE IF NOT EXISTS people (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    full_name TEXT NOT NULL,
    slug TEXT UNIQUE,
    gender TEXT,
    ethnicity TEXT,
    birth_year INTEGER,
    location_id UUID REFERENCES locations(id),
    byline_variants TEXT[],
    wikipedia_url TEXT,
    wikidata_id TEXT,
    meta JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Employment / affiliation history (temporal)
CREATE TABLE IF NOT EXISTS person_organization (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    person_id UUID NOT NULL REFERENCES people(id),
    org_id UUID NOT NULL REFERENCES organizations(id),
    role TEXT NOT NULL,
    beat TEXT,
    location_id UUID REFERENCES locations(id),
    valid_from DATE,
    valid_to DATE,
    confidence FLOAT DEFAULT 1.0,
    source TEXT,
    meta JSONB
);

CREATE INDEX IF NOT EXISTS idx_person_org_person ON person_organization(person_id);
CREATE INDEX IF NOT EXISTS idx_person_org_org ON person_organization(org_id);
CREATE INDEX IF NOT EXISTS idx_person_org_valid ON person_organization(valid_from, valid_to);

-- Story attribution / provenance
CREATE TABLE IF NOT EXISTS article_provenance (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    article_id UUID NOT NULL REFERENCES articles(id),
    provenance_type TEXT NOT NULL,
    wire_service_id UUID REFERENCES organizations(id),
    source_article_id UUID REFERENCES articles(id),
    confidence FLOAT NOT NULL,
    detection_method TEXT,
    attribution_text TEXT,
    similarity_score FLOAT,
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    meta JSONB
);

CREATE INDEX IF NOT EXISTS idx_provenance_article ON article_provenance(article_id);
CREATE INDEX IF NOT EXISTS idx_provenance_wire ON article_provenance(wire_service_id);

-- Multi-author support
CREATE TABLE IF NOT EXISTS article_authors (
    article_id UUID NOT NULL REFERENCES articles(id),
    person_id UUID NOT NULL REFERENCES people(id),
    author_order INTEGER DEFAULT 1,
    PRIMARY KEY (article_id, person_id)
);

-- Bridge FK columns on existing tables
ALTER TABLE authors ADD COLUMN IF NOT EXISTS person_id UUID REFERENCES people(id);
ALTER TABLE sources ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id);

-- Seed wire service organizations (used for provenance detection matching)
INSERT INTO organizations (name, slug, org_type, domain, country, political_lean)
VALUES
    ('The Associated Press', 'ap', 'wire_service', 'apnews.com', 'US', 0.0),
    ('Reuters', 'reuters', 'wire_service', 'reuters.com', 'GB', 0.0),
    ('Agence France-Presse', 'afp', 'wire_service', 'afp.com', 'FR', 0.0),
    ('Bloomberg', 'bloomberg', 'wire_service', 'bloomberg.com', 'US', 0.0),
    ('United Press International', 'upi', 'wire_service', 'upi.com', 'US', 0.0)
ON CONFLICT (name) DO NOTHING;
