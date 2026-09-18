from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime

from .auth import authorize
from .decision_bundle import DecisionBundle, verify_decision_bundle
from .domain import (
    AuditEvent,
    Decision,
    Entity,
    Organization,
    PolicyVersion,
    Principal,
    RiskCase,
    RiskCaseStatus,
    new_id,
)
from .repository import EnterpriseRepository, InMemoryEnterpriseRepository
from .temporal import RiskSnapshot
from .workflow import (
    add_mitigation_action,
    record_override,
    record_resolution_evidence,
    reopen_case,
    transition_case,
)


def verified_evidence_ids(snapshot, risk_domain: str) -> set[str]:
    """Stable IDs for verified evidence scoped to one snapshot and domain."""
    aliases = {
        "accounting": "accounting_anomaly",
        "governance": "governance_audit",
        "going_concern": "business_going_concern",
        "solvency": "solvency_leverage",
    }
    paths = snapshot.frozen_output.get("agent", {}).get("decision_trace", {}).get("paths", [])
    identifiers: set[str] = set()
    for path in paths:
        domain = aliases.get(path.get("risk_domain"), path.get("risk_domain"))
        if path.get("evidence_path_status") != "VERIFIED" or domain != risk_domain:
            continue
        for evidence in path.get("source_evidence", []):
            canonical = json.dumps(
                {
                    "snapshot_id": snapshot.id,
                    "risk_domain": risk_domain,
                    "document": evidence.get("document"),
                    "page": evidence.get("page"),
                    "source_text": evidence.get("source_text"),
                    "period": evidence.get("period"),
                    "value": evidence.get("value"),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            identifiers.add(f"ev_{hashlib.sha256(canonical.encode()).hexdigest()[:24]}")
    return identifiers


class EnterpriseRiskService:
    def __init__(self, repository: EnterpriseRepository | None = None):
        self.repository = repository or InMemoryEnterpriseRepository()

    def create_organization(self, name: str, actor_id: str) -> Organization:
        item = Organization(new_id("org"), name)
        event = self._event(
            item.id,
            actor_id,
            "organization.created",
            "organization",
            item.id,
            {"name": name},
        )
        return self.repository.save(item, event)

    def create_entity(
        self,
        principal: Principal,
        name: str,
        sector: str = "unspecified",
        parent_id: str | None = None,
    ) -> Entity:
        authorize(principal, "write", principal.organization_id)
        if parent_id is not None:
            self.repository.get_entity(principal.organization_id, parent_id)
        item = Entity(new_id("ent"), principal.organization_id, name, parent_id, sector)
        event = self._event(
            principal.organization_id,
            principal.user_id,
            "entity.created",
            "entity",
            item.id,
            {"name": name},
        )
        return self.repository.save(item, event)

    def create_policy(
        self, principal: Principal, name: str, thresholds: dict, version: int
    ) -> PolicyVersion:
        authorize(principal, "configure", principal.organization_id)
        item = PolicyVersion(
                new_id("pol"),
                principal.organization_id,
                version,
                name,
                thresholds,
                principal.user_id,
            )
        event = self._event(
            principal.organization_id,
            principal.user_id,
            "policy.version_created",
            "policy",
            item.id,
            {"version": version, "thresholds": thresholds},
        )
        return self.repository.save(item, event)

    def create_case(self, principal: Principal, case: RiskCase) -> RiskCase:
        authorize(principal, "write", case.organization_id)
        self.repository.get_entity(case.organization_id, case.entity_id)
        if case.snapshot_id:
            snapshot = self.repository.get_snapshot(case.organization_id, case.snapshot_id)
            if snapshot.organization_id != case.organization_id:
                raise PermissionError("snapshot organization does not match risk case")
            if snapshot.entity_id != case.entity_id:
                raise ValueError("snapshot entity does not match risk case")
        event = self._event(
            case.organization_id,
            principal.user_id,
            "risk_case.created",
            "risk_case",
            case.id,
            case.to_dict(),
        )
        return self.repository.save(case, event)

    def transition(
        self, principal: Principal, case_id: str, target: RiskCaseStatus
    ) -> RiskCase:
        case = self.repository.get_case(principal.organization_id, case_id)
        authorize(principal, "review", case.organization_id)
        if target in {RiskCaseStatus.ACCEPTED, RiskCaseStatus.RESOLVED}:
            if not case.snapshot_id:
                raise ValueError("a server-side analysis snapshot is required")
            snapshot = self.repository.get_snapshot(case.organization_id, case.snapshot_id)
            trace = snapshot.frozen_output.get("agent", {}).get("decision_trace", {})
            aliases = {
                "accounting": "accounting_anomaly",
                "governance": "governance_audit",
                "going_concern": "business_going_concern",
                "solvency": "solvency_leverage",
            }
            verified = [
                path for path in trace.get("paths", [])
                if path.get("evidence_path_status") == "VERIFIED"
                and path.get("source_evidence")
                and aliases.get(path.get("risk_domain"), path.get("risk_domain"))
                == case.domain.value
            ]
            if not verified:
                raise ValueError("a verified server-side evidence path is required")
        if target is RiskCaseStatus.RESOLVED and not case.resolution_evidence:
            raise ValueError("resolution evidence is required")
        previous, current = transition_case(case, target)
        event = self._event(
            case.organization_id,
            principal.user_id,
            "risk_case.transitioned",
            "risk_case",
            case.id,
            {"from": previous, "to": current},
        )
        return self.repository.save(case, event)

    def add_action(self, principal: Principal, case_id: str, description: str, owner_id: str, due_date: str) -> RiskCase:
        try:
            parsed_due_date = date.fromisoformat(due_date)
        except ValueError as exc:
            raise ValueError("due_date must be an ISO calendar date") from exc
        if parsed_due_date < datetime.now(UTC).date():
            raise ValueError("due_date cannot be in the past")
        case = self.repository.get_case(principal.organization_id, case_id)
        authorize(principal, "write", case.organization_id)
        if owner_id != principal.user_id:
            raise ValueError("action owner must match the authenticated user")
        payload = add_mitigation_action(case, principal.user_id, description, owner_id, due_date)
        event = self._event(case.organization_id, principal.user_id, "risk_case.action_added", "risk_case", case.id, payload)
        return self.repository.save(case, event)

    def add_resolution_evidence(self, principal: Principal, case_id: str, evidence_id: str) -> RiskCase:
        case = self.repository.get_case(principal.organization_id, case_id)
        authorize(principal, "review", case.organization_id)
        if not case.snapshot_id:
            raise ValueError("resolution evidence requires a server-side snapshot")
        snapshot = self.repository.get_snapshot(case.organization_id, case.snapshot_id)
        if (
            evidence_id not in case.evidence_ids
            or evidence_id not in verified_evidence_ids(snapshot, case.domain.value)
        ):
            raise ValueError("resolution evidence must be a verified case evidence ID")
        record_resolution_evidence(case, evidence_id)
        event = self._event(case.organization_id, principal.user_id, "risk_case.resolution_evidence_added", "risk_case", case.id, {"evidence_id": evidence_id})
        return self.repository.save(case, event)

    def reopen(self, principal: Principal, case_id: str, reason: str) -> RiskCase:
        case = self.repository.get_case(principal.organization_id, case_id)
        authorize(principal, "review", case.organization_id)
        payload = reopen_case(case, principal.user_id, reason)
        event = self._event(case.organization_id, principal.user_id, "risk_case.reopened", "risk_case", case.id, payload)
        return self.repository.save(case, event)

    def save_risk_snapshot(
        self, principal: Principal, snapshot: RiskSnapshot
    ) -> RiskSnapshot:
        authorize(principal, "write", principal.organization_id)
        self.repository.get_entity(principal.organization_id, snapshot.entity_id)
        event = self._event(
            principal.organization_id,
            principal.user_id,
            "risk_snapshot.created",
            "risk_snapshot",
            f"{snapshot.entity_id}:{snapshot.period}",
            {"filing_id": snapshot.filing_id, "decision": snapshot.decision},
        )
        return self.repository.save_risk_snapshot(principal.organization_id, snapshot, event)

    def risk_timeline(self, principal: Principal, entity_id: str) -> list[RiskSnapshot]:
        authorize(principal, "read", principal.organization_id)
        self.repository.get_entity(principal.organization_id, entity_id)
        return self.repository.list_risk_snapshots(principal.organization_id, entity_id)

    def save_decision_bundle(self, principal: Principal, bundle: DecisionBundle) -> DecisionBundle:
        authorize(principal, "write", bundle.organization_id)
        self.repository.get_entity(bundle.organization_id, bundle.entity_id)
        if not verify_decision_bundle(bundle):
            raise ValueError("decision bundle hash verification failed")
        saved = self.repository.save_decision_bundle(bundle)
        persisted = self.repository.get_decision_bundle(
            bundle.organization_id, bundle.entity_id, bundle.bundle_id
        )
        if persisted.bundle_hash != bundle.bundle_hash:
            raise ValueError("decision bundle persistence verification failed")
        return saved

    def save_snapshot(self, principal: Principal, snapshot):
        authorize(principal, "write", snapshot.organization_id)
        self.repository.get_entity(snapshot.organization_id, snapshot.entity_id)
        event = self._event(
            snapshot.organization_id,
            principal.user_id,
            "analysis.snapshot_created",
            "analysis_snapshot",
            snapshot.id,
            {
                "input_hash": snapshot.input_hash,
                "output_hash": snapshot.output_hash,
                "component_versions": snapshot.component_versions,
            },
        )
        return self.repository.save(snapshot, event)

    def record_analysis_execution(self, principal: Principal, payload: dict) -> AuditEvent:
        """Log one real analysis execution, independent of snapshot deduplication.

        Snapshots and decision bundles are content-addressed, so re-analysing an
        unchanged filing reuses the stored artefacts — that is what keeps storage
        bounded. Reuse alone, though, made a second genuine run completely invisible:
        the audit trail could not answer "how many times was this entity analysed, by
        whom, when, and with which engine/rule versions". The artefacts stay
        deduplicated; the run record does not. It is a single small row per execution.
        """
        authorize(principal, "write", principal.organization_id)
        event = self._event(
            principal.organization_id,
            principal.user_id,
            "analysis.executed",
            "analysis_snapshot",
            payload["snapshot_id"],
            payload,
        )
        self.repository.append_event(event)
        return event

    def override(
        self,
        principal: Principal,
        case_id: str,
        original: str,
        override: str,
        reason: str,
    ) -> RiskCase:
        case = self.repository.get_case(principal.organization_id, case_id)
        authorize(principal, "review", case.organization_id)
        try:
            original_decision, override_decision = Decision(original), Decision(override)
        except ValueError as exc:
            raise ValueError("override decisions must be valid Decision values") from exc
        actual = case.decision_trace.get("decision")
        if not actual:
            raise ValueError("risk case has no recorded decision to override")
        if original_decision.value != actual:
            raise ValueError("override original does not match the recorded decision")
        if original_decision == override_decision:
            raise ValueError("override must change the recorded decision")
        payload = record_override(case, principal.user_id, original, override, reason)
        event = self._event(
            case.organization_id,
            principal.user_id,
            "risk_case.overridden",
            "risk_case",
            case.id,
            payload,
        )
        return self.repository.save(case, event)

    @staticmethod
    def _event(
        organization_id, actor_id, action, object_type, object_id, payload
    ) -> AuditEvent:
        return AuditEvent(
            new_id("evt"), organization_id, actor_id, action, object_type, object_id, payload
        )
