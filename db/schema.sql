CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    config_path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    external_id TEXT,
    author_handle TEXT,
    author_name TEXT,
    text TEXT,
    posted_at TEXT,
    engagement_json TEXT,
    source_query TEXT,
    raw_json TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE (client_id, url)
);

CREATE TABLE IF NOT EXISTS classifications (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL UNIQUE REFERENCES items(id) ON DELETE CASCADE,
    is_relevant INTEGER NOT NULL,
    pillar TEXT,
    author_type TEXT,
    has_pain_or_question INTEGER,
    region TEXT,
    comment_angle TEXT,
    reason TEXT,
    model TEXT,
    prompt_version TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    week TEXT NOT NULL,
    score REAL NOT NULL,
    rank INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'suggested',
    created_at TEXT NOT NULL,
    UNIQUE (client_id, item_id)
);

CREATE TABLE IF NOT EXISTS feedback(
    id INTEGER PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    suggestion_id INTEGER NOT NULL REFERENCES suggestions(id) ON DELETE CASCADE,
    verdict TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (suggestion_id)
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE,
    task TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0, 
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    cached INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_cache(
    key TEXT PRIMARY KEY,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_items_client_posted ON items (client_id, posted_at);
CREATE INDEX IF NOT EXISTS idx_suggestions_client_week ON suggestions (client_id, week);