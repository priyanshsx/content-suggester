-- 002: flag job ads / candidate searches so they can be exported as hiring leads.
ALTER TABLE classifications ADD COLUMN is_job_post INTEGER NOT NULL DEFAULT 0;
