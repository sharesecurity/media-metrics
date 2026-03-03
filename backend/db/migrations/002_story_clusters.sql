-- Migration 002: Story Clusters
-- Groups of articles covering the same underlying news story,
-- detected via embedding cosine similarity + publication date proximity.
-- All statements are idempotent (safe to run multiple times).

CREATE TABLE IF NOT EXISTS story_clusters (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    representative_id       UUID REFERENCES articles(id) ON DELETE SET NULL,
    topic_label             TEXT,          -- auto-generated cluster label
    article_count           INTEGER NOT NULL DEFAULT 0,
    avg_lean                FLOAT,         -- average political lean across cluster
    avg_sentiment           FLOAT,
    source_count            INTEGER,       -- number of distinct outlets covering story
    date_start              TIMESTAMPTZ,   -- earliest article in cluster
    date_end                TIMESTAMPTZ,   -- latest article in cluster
    similarity_threshold    FLOAT NOT NULL DEFAULT 0.78,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS story_cluster_articles (
    cluster_id              UUID NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,
    article_id              UUID NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    similarity_score        FLOAT,         -- highest similarity to another member of cluster
    PRIMARY KEY (cluster_id, article_id)
);

CREATE INDEX IF NOT EXISTS idx_sca_article ON story_cluster_articles(article_id);
CREATE INDEX IF NOT EXISTS idx_sc_date ON story_clusters(date_start);
CREATE INDEX IF NOT EXISTS idx_sc_lean ON story_clusters(avg_lean);
