from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypeVar

from .decision_bundle import DecisionBundle, verify_decision_bundle
from .domain import (
    AnalysisSnapshot,
    AuditEvent,
    Entity,
    ModelRecord,
    Organization,
    PolicyVersion,
    RiskCase,
    RiskCaseStatus,
    RiskDomain,
)
from .temporal import RiskSnapshot

T = TypeVar("T")


def _json(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True)


class PostgresEnterpriseRepository:
    """Tenant-scoped psycopg repository used whenever ``DATABASE_URL`` is set."""

    def __init__(self, connection=None, pool=None):
        self.connection = connection
        self.pool = pool

    @classmethod
    def connect(cls, dsn: str) -> PostgresEnterpriseRepository:
        try:
            from psycopg_pool import ConnectionPool
        except ImportError as exc:
            raise RuntimeError("install the 'postgres' extra to use PostgreSQL") from exc
        pool = ConnectionPool(
            dsn,
            min_size=int(os.getenv("FINRISK_DB_POOL_MIN", "1")),
            max_size=int(os.getenv("FINRISK_DB_POOL_MAX", "10")),
            open=True,
        )
        try:
            pool.wait(timeout=10)
        except Exception:
            # The pool is already open here, so a failed readiness wait used to
            # leave its connections and worker threads alive for the process to
            # leak. Close it before reporting the failure.
            pool.close()
            raise
        return cls(pool=pool)

    @contextmanager
    def connection_context(self):
        if self.pool is not None:
            with self.pool.connection() as connection:
                yield connection
        elif self.connection is not None:
            yield self.connection
        else:
            raise RuntimeError("repository has no database connection")

    def close(self) -> None:
        if self.pool is not None:
            self.pool.close()
        elif self.connection is not None:
            self.connection.close()

    def check_ready(self) -> bool:
        with self.connection_context() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            return cursor.fetchone()[0] == 1

    def migrate(self, path: Path) -> None:
        with self.connection_context() as connection:
            with connection.cursor() as cursor:
                cursor.execute(path.read_text(encoding="utf-8"))
            connection.commit()

    def save(self, item: T, event: AuditEvent | None = None) -> T:
        item_organization_id = (
            item.id if isinstance(item, Organization) else getattr(item, "organization_id", None)
        )
        if event is not None and event.organization_id != item_organization_id:
            raise ValueError("mutation and audit event must belong to the same tenant")
        if isinstance(item, Organization):
            sql = "INSERT INTO organizations (id,name,created_at) VALUES (%s,%s,%s) ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name"
            values = (item.id, item.name, item.created_at)
        elif isinstance(item, Entity):
            sql = "INSERT INTO entities (id,organization_id,parent_id,name,sector) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO UPDATE SET parent_id=EXCLUDED.parent_id,name=EXCLUDED.name,sector=EXCLUDED.sector WHERE entities.organization_id=EXCLUDED.organization_id"
            values = (item.id, item.organization_id, item.parent_id, item.name, item.sector)
        elif isinstance(item, PolicyVersion):
            sql = "INSERT INTO policy_versions (id,organization_id,version,name,thresholds,created_by,created_at,status) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s) ON CONFLICT (id) DO UPDATE SET thresholds=EXCLUDED.thresholds,status=EXCLUDED.status WHERE policy_versions.organization_id=EXCLUDED.organization_id"
            values = (item.id, item.organization_id, item.version, item.name, _json(item.thresholds), item.created_by, item.created_at, item.status)
        elif isinstance(item, RiskCase):
            sql = """INSERT INTO risk_cases (id,organization_id,entity_id,domain,severity,trajectory,confidence,evidence_coverage,status,owner_id,reviewer_id,due_date,rationale,evidence_ids,actions,comments,created_at,updated_at,reason_codes,decision_trace,snapshot_id,fusion_version,resolution_evidence,monitoring_state,version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s::jsonb,%s,%s) ON CONFLICT (id) DO UPDATE SET severity=EXCLUDED.severity,trajectory=EXCLUDED.trajectory,confidence=EXCLUDED.confidence,evidence_coverage=EXCLUDED.evidence_coverage,status=EXCLUDED.status,owner_id=EXCLUDED.owner_id,reviewer_id=EXCLUDED.reviewer_id,due_date=EXCLUDED.due_date,rationale=EXCLUDED.rationale,evidence_ids=EXCLUDED.evidence_ids,actions=EXCLUDED.actions,comments=EXCLUDED.comments,updated_at=EXCLUDED.updated_at,reason_codes=EXCLUDED.reason_codes,decision_trace=EXCLUDED.decision_trace,snapshot_id=EXCLUDED.snapshot_id,fusion_version=EXCLUDED.fusion_version,resolution_evidence=EXCLUDED.resolution_evidence,monitoring_state=EXCLUDED.monitoring_state,version=risk_cases.version+1 WHERE risk_cases.organization_id=EXCLUDED.organization_id AND risk_cases.version=EXCLUDED.version"""
            values = (item.id,item.organization_id,item.entity_id,item.domain.value,item.severity,item.trajectory,item.confidence,item.evidence_coverage,item.status.value,item.owner_id,item.reviewer_id,item.due_date,item.rationale,_json(item.evidence_ids),_json(item.actions),_json(item.comments),item.created_at,item.updated_at,_json(item.reason_codes),_json(item.decision_trace),item.snapshot_id,item.fusion_version,_json(item.resolution_evidence),item.monitoring_state,item.version)
        elif isinstance(item, AnalysisSnapshot):
            sql = "INSERT INTO analysis_snapshots (id,organization_id,entity_id,input_hash,output_hash,document_versions,component_versions,frozen_input,frozen_output,created_at) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s) ON CONFLICT (id) DO NOTHING"
            values = (item.id,item.organization_id,item.entity_id,item.input_hash,item.output_hash,_json(item.document_versions),_json(item.component_versions),_json(item.frozen_input),_json(item.frozen_output),item.created_at)
        elif isinstance(item, ModelRecord):
            sql = "INSERT INTO model_registry (id,organization_id,component,version,owner_id,intended_use,limitations,validation_status,dataset_version,prompt_hash,rule_version,fusion_version,policy_version,metrics,last_validation,deployment_state) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s) ON CONFLICT (id) DO UPDATE SET metrics=EXCLUDED.metrics,validation_status=EXCLUDED.validation_status,deployment_state=EXCLUDED.deployment_state WHERE model_registry.organization_id=EXCLUDED.organization_id"
            values = (item.id,item.organization_id,item.component,item.version,item.owner,item.intended_use,item.limitations,item.validation_status,item.dataset_version,item.prompt_hash,item.rule_version,item.fusion_version,item.policy_version,_json(item.metrics),item.last_validation,item.deployment_state)
        else:
            raise TypeError(f"unsupported repository item: {type(item).__name__}")
        with self.connection_context() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(sql, values)
                    if isinstance(item, AnalysisSnapshot) and getattr(cursor, "rowcount", 1) == 0:
                        raise ValueError(f"analysis snapshot already exists: {item.id}")
                    if isinstance(item, (Entity, PolicyVersion, ModelRecord)) and getattr(cursor, "rowcount", 1) == 0:
                        raise ValueError(f"cross-tenant identifier collision rejected: {item.id}")
                    if isinstance(item, RiskCase) and getattr(cursor, "rowcount", 1) == 0:
                        raise ValueError(f"concurrent risk case update rejected: {item.id}")
                    if isinstance(item, RiskCase):
                        cursor.execute(
                            "SELECT version FROM risk_cases WHERE organization_id=%s AND id=%s",
                            (item.organization_id, item.id),
                        )
                        persisted_version = cursor.fetchone()
                        if persisted_version is not None:
                            item.version = persisted_version[0]
                    if event is not None:
                        self._insert_event(cursor, event)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return item

    @staticmethod
    def _case(row: dict[str, Any]) -> RiskCase:
        return RiskCase(
            id=row["id"], organization_id=row["organization_id"], entity_id=row["entity_id"],
            domain=RiskDomain(row["domain"]), severity=row["severity"], trajectory=row["trajectory"],
            confidence=row["confidence"], evidence_coverage=row["evidence_coverage"],
            status=RiskCaseStatus(row["status"]), owner_id=row["owner_id"], reviewer_id=row["reviewer_id"],
            due_date=str(row["due_date"]) if row["due_date"] else None, rationale=row["rationale"],
            evidence_ids=row["evidence_ids"], reason_codes=row["reason_codes"], decision_trace=row["decision_trace"],
            snapshot_id=row["snapshot_id"], fusion_version=row["fusion_version"], actions=row["actions"],
            resolution_evidence=row["resolution_evidence"], monitoring_state=row["monitoring_state"],
            comments=row["comments"], created_at=str(row["created_at"]), updated_at=str(row["updated_at"]),
            version=row.get("version", 0),
        )

    def _one(self, sql: str, values: tuple[Any, ...]) -> dict[str, Any]:
        with self.connection_context() as connection, connection.cursor() as cursor:
            cursor.execute(sql, values)
            row = cursor.fetchone()
            if row is None:
                raise KeyError(values[-1])
            columns = [item.name for item in cursor.description]
        return dict(zip(columns, row, strict=True))

    def get_case(self, organization_id: str, case_id: str) -> RiskCase:
        return self._case(self._one("SELECT * FROM risk_cases WHERE organization_id=%s AND id=%s", (organization_id, case_id)))

    def list_cases(self, organization_id: str) -> list[RiskCase]:
        with self.connection_context() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM risk_cases WHERE organization_id=%s ORDER BY created_at", (organization_id,))
            columns = [item.name for item in cursor.description]
            return [self._case(dict(zip(columns, row, strict=True))) for row in cursor.fetchall()]

    def get_entity(self, organization_id: str, entity_id: str) -> Entity:
        row = self._one("SELECT * FROM entities WHERE organization_id=%s AND id=%s", (organization_id, entity_id))
        return Entity(row["id"], row["organization_id"], row["name"], row["parent_id"], row["sector"])

    def get_policy(self, organization_id: str, policy_id: str) -> PolicyVersion:
        row = self._one("SELECT * FROM policy_versions WHERE organization_id=%s AND id=%s", (organization_id, policy_id))
        return PolicyVersion(row["id"],row["organization_id"],row["version"],row["name"],row["thresholds"],row["created_by"],str(row["created_at"]),row["status"])

    def append_event(self, event: AuditEvent) -> None:
        with self.connection_context() as connection:
            with connection.cursor() as cursor:
                self._insert_event(cursor, event)
            connection.commit()

    @staticmethod
    def _insert_event(cursor, event: AuditEvent) -> None:
        cursor.execute(
            "INSERT INTO audit_events (id,organization_id,actor_id,action,object_type,object_id,payload,occurred_at) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)",
            (event.id,event.organization_id,event.actor_id,event.action,event.object_type,event.object_id,_json(event.payload),event.occurred_at),
        )

    append_audit_event = append_event

    def list_events(self, organization_id: str) -> list[AuditEvent]:
        with self.connection_context() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT id,organization_id,actor_id,action,object_type,object_id,payload,occurred_at FROM audit_events WHERE organization_id=%s ORDER BY sequence",(organization_id,))
            return [AuditEvent(*row[:-1], str(row[-1])) for row in cursor.fetchall()]

    def get_snapshot(self, organization_id: str, snapshot_id: str) -> AnalysisSnapshot:
        row=self._one("SELECT * FROM analysis_snapshots WHERE organization_id=%s AND id=%s",(organization_id,snapshot_id))
        return AnalysisSnapshot(row["id"],row["organization_id"],row["entity_id"],row["input_hash"],row["output_hash"],row["document_versions"],row["component_versions"],row["frozen_input"],row["frozen_output"],str(row["created_at"]))

    def save_risk_snapshot(self, organization_id: str, snapshot: RiskSnapshot, event: AuditEvent | None = None) -> RiskSnapshot:
        if event is not None and event.organization_id != organization_id:
            raise ValueError("mutation and audit event must belong to the same tenant")
        try:
            with self.connection_context() as connection:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("INSERT INTO risk_snapshots (id,organization_id,entity_id,period,filing_id,risk_score,dimension_scores,metrics,evidence_paths,decision,coverage,reliability,calibration_status) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s,%s)",(f"risk_{snapshot.entity_id}_{snapshot.period}",organization_id,snapshot.entity_id,snapshot.period,snapshot.filing_id,snapshot.risk_score,_json(snapshot.dimension_scores),_json(snapshot.metrics),_json(snapshot.evidence_paths),str(snapshot.decision),snapshot.coverage,snapshot.reliability,str(snapshot.calibration_status)))
                        if event is not None:
                            self._insert_event(cursor, event)
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
        except Exception as exc:
            if getattr(exc, "sqlstate", None) == "23505" or exc.__class__.__name__ == "UniqueViolation":
                raise ValueError(f"risk snapshot already exists for {snapshot.period}") from exc
            raise
        return snapshot

    def list_risk_snapshots(self, organization_id: str, entity_id: str) -> list[RiskSnapshot]:
        with self.connection_context() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT period,filing_id,risk_score,dimension_scores,metrics,evidence_paths,decision,coverage,reliability,calibration_status FROM risk_snapshots WHERE organization_id=%s AND entity_id=%s ORDER BY period",(organization_id,entity_id))
            return [RiskSnapshot(entity_id,row[0],row[1],row[2],row[3],row[4],row[5],row[6],row[7],row[8],row[9]) for row in cursor.fetchall()]

    def save_decision_bundle(self, bundle: DecisionBundle) -> DecisionBundle:
        if not verify_decision_bundle(bundle):
            raise ValueError("decision bundle hash verification failed")
        payload = bundle.to_dict()
        try:
            with self.connection_context() as connection:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "INSERT INTO decision_bundles (id,organization_id,entity_id,bundle_hash,payload,created_at) VALUES (%s,%s,%s,%s,%s::jsonb,%s)",
                            (bundle.bundle_id,bundle.organization_id,bundle.entity_id,bundle.bundle_hash,_json(payload),bundle.created_at),
                        )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
        except Exception as exc:
            if getattr(exc, "sqlstate", None) == "23505" or exc.__class__.__name__ == "UniqueViolation":
                raise ValueError(f"decision bundle already exists: {bundle.bundle_id}") from exc
            raise
        return bundle

    def get_decision_bundle(self, organization_id: str, entity_id: str, bundle_id: str) -> DecisionBundle:
        row = self._one(
            "SELECT payload FROM decision_bundles WHERE organization_id=%s AND entity_id=%s AND id=%s",
            (organization_id, entity_id, bundle_id),
        )
        payload = row["payload"]
        payload["evidence_paths"] = tuple(payload["evidence_paths"])
        payload["agent_trace"] = tuple(payload["agent_trace"])
        payload["component_telemetry"] = tuple(payload["component_telemetry"])
        bundle = DecisionBundle(**payload)
        if not verify_decision_bundle(bundle):
            raise ValueError("persisted decision bundle hash verification failed")
        return bundle
