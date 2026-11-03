-- 001: store the classifier's suggested new keywords, and each item's latest score.
-- Scores are recalculated on every run (recency changes), so they live next to the classification.
ALTER TABLE classifications ADD COLUMN new_terms_json TEXT;
ALTER TABLE classifications ADD COLUMN score REAL;
ALTER TABLE classifications ADD COLUMN score_json TEXT;