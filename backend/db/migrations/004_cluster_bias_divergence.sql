-- Migration 004: Add bias_divergence to story_clusters
-- Measures spread between most-left and most-right outlet avg lean for a story.
-- High divergence = more contentious/politically split coverage.

ALTER TABLE story_clusters
    ADD COLUMN IF NOT EXISTS bias_divergence FLOAT;

CREATE INDEX IF NOT EXISTS idx_sc_divergence ON story_clusters(bias_divergence);
