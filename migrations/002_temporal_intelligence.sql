ALTER TABLE risk_cases
    ADD COLUMN IF NOT EXISTS resolution_evidence JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE risk_cases
    ADD COLUMN IF NOT EXISTS monitoring_state TEXT NOT NULL DEFAULT 'active';

CREATE TABLE IF NOT EXISTS risk_snapshots (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    entity_id TEXT NOT NULL REFERENCES entities(id),
    period TEXT NOT NULL,
    filing_id TEXT NOT NULL,
    risk_score DOUBLE PRECISION,
    dimension_scores JSONB NOT NULL,
    metrics JSONB NOT NULL,
    evidence_paths JSONB NOT NULL,
    decision TEXT NOT NULL,
    coverage DOUBLE PRECISION NOT NULL,
    reliability DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (organization_id, entity_id, period)
);

CREATE TABLE IF NOT EXISTS decision_bundles (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    entity_id TEXT NOT NULL REFERENCES entities(id),
    bundle_hash TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (organization_id, bundle_hash)
);

CREATE TABLE IF NOT EXISTS temporal_evidence_nodes (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    entity_id TEXT NOT NULL REFERENCES entities(id),
    period TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS temporal_evidence_edges (
    id BIGSERIAL PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    source_id TEXT NOT NULL REFERENCES temporal_evidence_nodes(id),
    target_id TEXT NOT NULL REFERENCES temporal_evidence_nodes(id),
    relation TEXT NOT NULL CHECK (relation IN ('SUPPORTS','CONTRADICTS','SUPERSEDES','DERIVED_FROM','CONFIRMS','WEAKENS','INVALIDATES')),
    reason TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_risk_snapshots_timeline
    ON risk_snapshots(organization_id, entity_id, period);
CREATE INDEX IF NOT EXISTS ix_evidence_edges_target
    ON temporal_evidence_edges(organization_id, target_id);
