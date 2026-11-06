-- 003: posts where someone asks for outside help (requests), and your review of them.
ALTER TABLE classifications ADD COLUMN is_request INTEGER NOT NULL DEFAULT 0;
ALTER TABLE classifications ADD COLUMN request_summary TEXT;
ALTER TABLE classifications ADD COLUMN requester_company TEXT;
ALTER TABLE classifications ADD COLUMN poster_kind TEXT;          -- person, company, unknown
ALTER TABLE classifications ADD COLUMN request_status TEXT;       -- from the Requests tab
ALTER TABLE classifications ADD COLUMN request_note TEXT;
