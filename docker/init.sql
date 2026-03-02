-- Media Metrics DB initialization

CREATE TABLE IF NOT EXISTS sources (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    domain TEXT,
    country TEXT DEFAULT 'US',
    political_lean TEXT, -- left, center-left, center, center-right, right
    source_type TEXT DEFAULT 'online', -- newspaper, online, tv, magazine
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS authors (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    source_id INT REFERENCES sources(id),
    gender TEXT,
    race TEXT,
    bio TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(name, source_id)
);

CREATE TABLE IF NOT EXISTS articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id INT REFERENCES sources(id),
    author_id INT REFERENCES authors(id),
    title TEXT NOT NULL,
    url TEXT UNIQUE,
    published_at TIMESTAMPTZ,
    content TEXT,
    word_count INT,
    section TEXT,
    tags TEXT[],
    raw_storage_path TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS analyses (
    id SERIAL PRIMARY KEY,
    article_id UUID REFERENCES articles(id) ON DELETE CASCADE,
    analysis_type TEXT NOT NULL, -- bias, sentiment, topic, style
    model_used TEXT,
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_id);
CREATE INDEX IF NOT EXISTS idx_analyses_article ON analyses(article_id);
CREATE INDEX IF NOT EXISTS idx_analyses_type ON analyses(analysis_type);

-- Seed some sources
INSERT INTO sources (name, domain, political_lean, source_type) VALUES
  ('New York Times', 'nytimes.com', 'center-left', 'newspaper'),
  ('Wall Street Journal', 'wsj.com', 'center-right', 'newspaper'),
  ('Fox News', 'foxnews.com', 'right', 'tv'),
  ('CNN', 'cnn.com', 'center-left', 'tv'),
  ('Reuters', 'reuters.com', 'center', 'online'),
  ('NPR', 'npr.org', 'center-left', 'online'),
  ('The Guardian', 'theguardian.com', 'left', 'newspaper'),
  ('Breitbart', 'breitbart.com', 'right', 'online')
ON CONFLICT (name) DO NOTHING;
