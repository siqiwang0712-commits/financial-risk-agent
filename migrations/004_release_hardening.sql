ALTER TABLE risk_cases ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 0;

ALTER TABLE risk_snapshots
    DROP CONSTRAINT IF EXISTS ck_risk_snapshot_period,
    ADD CONSTRAINT ck_risk_snapshot_period
    CHECK (period ~ '^(19|20)[0-9]{2}(-Q[1-4])?$');

ALTER TABLE risk_snapshots
    DROP CONSTRAINT IF EXISTS ck_risk_snapshot_score,
    ADD CONSTRAINT ck_risk_snapshot_score
    CHECK (risk_score IS NULL OR risk_score BETWEEN 0 AND 100);

ALTER TABLE risk_snapshots
    DROP CONSTRAINT IF EXISTS ck_risk_snapshot_coverage,
    ADD CONSTRAINT ck_risk_snapshot_coverage CHECK (coverage BETWEEN 0 AND 1);

ALTER TABLE risk_cases
    DROP CONSTRAINT IF EXISTS ck_risk_case_confidence,
    ADD CONSTRAINT ck_risk_case_confidence CHECK (confidence BETWEEN 0 AND 1),
    DROP CONSTRAINT IF EXISTS ck_risk_case_evidence_coverage,
    ADD CONSTRAINT ck_risk_case_evidence_coverage CHECK (evidence_coverage BETWEEN 0 AND 1);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_entities_org_id') THEN
        ALTER TABLE entities ADD CONSTRAINT uq_entities_org_id UNIQUE (organization_id, id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_audit_event_organization') THEN
        ALTER TABLE audit_events ADD CONSTRAINT fk_audit_event_organization
            FOREIGN KEY (organization_id) REFERENCES organizations(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_cases_tenant_entity') THEN
        ALTER TABLE risk_cases ADD CONSTRAINT fk_cases_tenant_entity
            FOREIGN KEY (organization_id, entity_id) REFERENCES entities(organization_id, id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_entities_tenant_parent') THEN
        ALTER TABLE entities ADD CONSTRAINT fk_entities_tenant_parent
            FOREIGN KEY (organization_id, parent_id) REFERENCES entities(organization_id, id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_documents_tenant_entity') THEN
        ALTER TABLE documents ADD CONSTRAINT fk_documents_tenant_entity
            FOREIGN KEY (organization_id, entity_id) REFERENCES entities(organization_id, id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_alerts_tenant_entity') THEN
        ALTER TABLE alerts ADD CONSTRAINT fk_alerts_tenant_entity
            FOREIGN KEY (organization_id, entity_id) REFERENCES entities(organization_id, id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_temporal_nodes_org_id') THEN
        ALTER TABLE temporal_evidence_nodes ADD CONSTRAINT uq_temporal_nodes_org_id
            UNIQUE (organization_id, id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_temporal_nodes_tenant_entity') THEN
        ALTER TABLE temporal_evidence_nodes ADD CONSTRAINT fk_temporal_nodes_tenant_entity
            FOREIGN KEY (organization_id, entity_id) REFERENCES entities(organization_id, id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_temporal_edges_tenant_source') THEN
        ALTER TABLE temporal_evidence_edges ADD CONSTRAINT fk_temporal_edges_tenant_source
            FOREIGN KEY (organization_id, source_id)
            REFERENCES temporal_evidence_nodes(organization_id, id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_temporal_edges_tenant_target') THEN
        ALTER TABLE temporal_evidence_edges ADD CONSTRAINT fk_temporal_edges_tenant_target
            FOREIGN KEY (organization_id, target_id)
            REFERENCES temporal_evidence_nodes(organization_id, id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_snapshots_tenant_entity') THEN
        ALTER TABLE analysis_snapshots ADD CONSTRAINT fk_snapshots_tenant_entity
            FOREIGN KEY (organization_id, entity_id) REFERENCES entities(organization_id, id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_bundles_tenant_entity') THEN
        ALTER TABLE decision_bundles ADD CONSTRAINT fk_bundles_tenant_entity
            FOREIGN KEY (organization_id, entity_id) REFERENCES entities(organization_id, id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_risk_snapshots_tenant_entity') THEN
        ALTER TABLE risk_snapshots ADD CONSTRAINT fk_risk_snapshots_tenant_entity
            FOREIGN KEY (organization_id, entity_id) REFERENCES entities(organization_id, id);
    END IF;
END $$;
