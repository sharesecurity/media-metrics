-- Media Metrics Database Schema
-- Initialize on first run

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- for full-text search

-- News organizations / sources
CREATE TABLE IF NOT EXISTS sources (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL UNIQUE,
    domain TEXT,
    country TEXT DEFAULT 'US',
    political_lean FLOAT,  -- -1.0 (far left) to 1.0 (far right), null = unknown
    ownership TEXT,
    founded_year INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Authors
CREATE TABLE IF NOT EXISTS authors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    source_id UUID REFERENCES sources(id),
    gender TEXT,  -- male, female, nonbinary, unknown
    ethnicity TEXT,  -- for future demographic analysis
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(name, source_id)
);

-- Articles (main catalog)
CREATE TABLE IF NOT EXISTS articles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id UUID REFERENCES sources(id),
    author_id UUID REFERENCES authors(id),
    title TEXT NOT NULL,
    url TEXT UNIQUE,
    published_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    word_count INTEGER,
    section TEXT,  -- e.g., politics, sports, tech
    tags TEXT[],
    minio_key TEXT,  -- path to full text in MinIO
    raw_text TEXT,   -- stored here for smaller articles, MinIO for large
    language TEXT DEFAULT 'en',
    gdelt_id TEXT,   -- original GDELT identifier if from GDELT
    extra JSONB      -- flexible metadata
);

-- Analysis results (one per article per analysis run)
CREATE TABLE IF NOT EXISTS analysis_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    article_id UUID REFERENCES articles(id) ON DELETE CASCADE,
    analyzed_at TIMESTAMPTZ DEFAULT NOW(),
    model_used TEXT,
    analysis_type TEXT,  -- bias, sentiment, topic, writing_style, factuality
    -- Bias scores
    political_lean FLOAT,     -- -1.0 to 1.0
    political_confidence FLOAT,
    sentiment_score FLOAT,    -- -1.0 to 1.0
    sentiment_label TEXT,     -- positive, neutral, negative
    subjectivity FLOAT,       -- 0 (objective) to 1 (subjective)
    -- Topics
    primary_topic TEXT,
    topics JSONB,             -- [{label, score}, ...]
    -- Writing style
    reading_level FLOAT,      -- Flesch-Kincaid grade
    avg_sentence_length FLOAT,
    -- Raw output from LLM
    raw_analysis JSONB,
    notes TEXT
);

-- Bias detection methods (configurable by user)
CREATE TABLE IF NOT EXISTS bias_methods (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    prompt_template TEXT,     -- LLM prompt template
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    modified_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_id);
CREATE INDEX IF NOT EXISTS idx_articles_author ON articles(author_id);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_section ON articles(section);
CREATE INDEX IF NOT EXISTS idx_analysis_article ON analysis_results(article_id);
CREATE INDEX IF NOT EXISTS idx_analysis_type ON analysis_results(analysis_type);
CREATE INDEX IF NOT EXISTS idx_articles_title_trgm ON articles USING gin(title gin_trgm_ops);

-- Seed some news sources
INSERT INTO sources (name, domain, country, political_lean) VALUES
    ('The New York Times', 'nytimes.com', 'US', -0.3),
    ('Fox News', 'foxnews.com', 'US', 0.5),
    ('Reuters', 'reuters.com', 'US', 0.0),
    ('The Guardian', 'theguardian.com', 'UK', -0.4),
    ('The Washington Post', 'washingtonpost.com', 'US', -0.3),
    ('The Wall Street Journal', 'wsj.com', 'US', 0.2),
    ('AP News', 'apnews.com', 'US', 0.0),
    ('Breitbart', 'breitbart.com', 'US', 0.8),
    ('HuffPost', 'huffpost.com', 'US', -0.5),
    ('BBC News', 'bbc.com', 'UK', -0.1)
ON CONFLICT (name) DO NOTHING;

-- Seed default bias detection methods
INSERT INTO bias_methods (name, description, prompt_template) VALUES
(
    'Political Lean Analyzer',
    'Analyzes the political lean of an article on a spectrum from far-left to far-right based on language, framing, and topic emphasis.',
    'Analyze the political bias of the following news article. Rate it on a scale from -1.0 (far left) to 1.0 (far right), where 0 is neutral. Consider: word choice, framing of issues, whose voices are quoted, what facts are emphasized or omitted. Return JSON: {"score": float, "confidence": float, "reasoning": string, "key_indicators": [string]}\n\nArticle:\n{text}'
),
(
    'Sentiment Analyzer',
    'Measures the overall sentiment and emotional tone of a news article.',
    'Analyze the sentiment and emotional tone of this news article. Return JSON: {"sentiment": "positive|neutral|negative", "score": float (-1 to 1), "subjectivity": float (0=objective to 1=subjective), "emotional_tone": string, "reasoning": string}\n\nArticle:\n{text}'
),
(
    'Framing Analyzer',
    'Identifies how issues are framed — who is portrayed as victim, villain, hero; what solutions are implied.',
    'Analyze how this news article frames its subject. Who are the heroes, victims, and villains (if any)? What solutions are implied? What is emphasized vs. minimized? Return JSON: {"heroes": [string], "victims": [string], "villains": [string], "implied_solutions": [string], "emphasis_patterns": [string], "framing_summary": string}\n\nArticle:\n{text}'
)
ON CONFLICT (name) DO NOTHING;
