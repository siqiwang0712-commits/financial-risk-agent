-- Bounded retention for the shared rate limiter.
--
-- 005 created `rate_limit_events` with an index on (scope, key, occurred_at), which
-- serves the per-key prune and count. Nothing pruned *other* keys, so a caller that
-- varied the key (the bootstrap limiter keys on the client address, so rotating
-- addresses is enough) left one stale row set behind per key and the table grew
-- without bound. The limiter now runs a periodic global retention sweep, which
-- filters on `occurred_at` alone and therefore needs its own index.

CREATE INDEX IF NOT EXISTS idx_rate_limit_events_expiry
    ON rate_limit_events (occurred_at);
