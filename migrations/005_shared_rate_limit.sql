-- Shared sliding-window rate limiting.
--
-- The process-local limiter reset on every restart and counted once per worker, so
-- the unauthenticated bootstrap endpoint was not actually bounded against an
-- attacker who could spread attempts across replicas or simply wait for a deploy.
-- Keeping the window in the shared database makes the bound hold across processes.

CREATE TABLE IF NOT EXISTS rate_limit_events (
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Pruning and counting always filter on (scope, key) plus the window, so one index
-- covers both the delete and the count.
CREATE INDEX IF NOT EXISTS idx_rate_limit_events_lookup
    ON rate_limit_events (scope, key, occurred_at);
