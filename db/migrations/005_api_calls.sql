-- 005: paid API calls other than the LLM (e.g. Serper searches), for the cost dashboard.
CREATE TABLE IF NOT EXISTS api_calls (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    service TEXT NOT NULL,          -- e.g. serper
    task TEXT,                      -- the stage that made the call (collect, requests, ...)
    units INTEGER NOT NULL DEFAULT 1,   -- what the service bills for (Serper: credits)
    cost_usd REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
