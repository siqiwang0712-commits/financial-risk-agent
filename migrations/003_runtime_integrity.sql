ALTER TABLE risk_snapshots
    ADD COLUMN IF NOT EXISTS calibration_status TEXT NOT NULL DEFAULT 'UNCALIBRATED';

CREATE TABLE IF NOT EXISTS api_credentials (
    id TEXT PRIMARY KEY,
    credential_prefix TEXT UNIQUE NOT NULL,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    secret_hash TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_credentials_active_prefix
    ON api_credentials(credential_prefix) WHERE active;
