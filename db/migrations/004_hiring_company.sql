-- 004: the company behind a job post, when the post names it (not the recruiter).
-- NULL = classified before this field existed; "" = classified after, but no company named.
ALTER TABLE classifications ADD COLUMN hiring_company TEXT;
