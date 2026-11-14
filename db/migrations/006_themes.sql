-- 006: content ideas. Recurring themes found in the client's collected posts (stage "themes"),
-- the posts that support each theme (evidence), and the client's pick / reject / publish.
CREATE TABLE IF NOT EXISTS themes (
    id INTEGER PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    theme_id TEXT NOT NULL UNIQUE,          -- stable ID, e.g. quartermaster-2026w46-01
    run_date TEXT NOT NULL,                 -- ISO date of the run that found it
    week TEXT NOT NULL,                     -- 2026-W46
    pillar TEXT NOT NULL,                   -- expertise area
    pillar_rank INTEGER,                    -- 1 = strongest
    theme TEXT NOT NULL,                    -- one line naming the tension
    angle TEXT NOT NULL,                    -- one-line suggested angle
    research_cue TEXT,                      -- optional: what to measure to answer it
    post_count INTEGER NOT NULL,
    source_count INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',     -- new, picked, rejected, published (set in the sheet)
    client_note TEXT,
    published_url TEXT,
    prompt_version TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS theme_items (
    theme_pk INTEGER NOT NULL REFERENCES themes(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    PRIMARY KEY (theme_pk, item_id)
);
CREATE INDEX IF NOT EXISTS idx_themes_client_week ON themes (client_id, week);
