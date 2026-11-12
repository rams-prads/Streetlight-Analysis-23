-- Phase 6: link GlobalUserProfile (the directory/admin-facing row) to the real auth User row by
-- foreign key, and record the exact role string that signs that user in - instead of guessing it
-- from assigned_roles with an if/elif chain, and instead of re-matching the two tables by email
-- on every write.
--
-- This repo has no migration tooling (no Alembic - just Base.metadata.create_all() at startup,
-- which only creates missing tables and never alters an existing one). Local dev SQLite doesn't
-- need this script: app/db/dev_schema.py's ensure_local_schema() detects the new columns via
-- PRAGMA table_info and rebuilds+reseeds the dev file automatically on next startup. Apply this
-- script by hand against any Postgres database (staging/production) before deploying the Phase 6
-- backend code.
--
-- Safe to run more than once.

ALTER TABLE global_user_profiles ADD COLUMN IF NOT EXISTS user_id VARCHAR(36) REFERENCES users(id);
ALTER TABLE global_user_profiles ADD COLUMN IF NOT EXISTS primary_role VARCHAR(50);
CREATE INDEX IF NOT EXISTS ix_global_user_profiles_user_id ON global_user_profiles (user_id);

-- Backfill existing rows: link each profile to its matching auth user by email (the same match the
-- old code performed on every request), and carry that user's current role forward as primary_role
-- so existing accounts keep behaving exactly as they do today until an admin explicitly changes them.
UPDATE global_user_profiles gup
SET user_id = u.id,
    primary_role = u.role
FROM users u
WHERE gup.user_id IS NULL
  AND lower(gup.email) = lower(u.email);
