from __future__ import annotations

from datetime import date

from .auth import authorize
from .decision import verified_paths_for_domain
from .domain import (
    AuditEvent,
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


class EnterpriseRiskService:
    def __init__(self, repository: EnterpriseRepository | None = None):
        self.repository = repository or InMemoryEnterpriseRepository()

    def create_organization(self, name: str, actor_id: str) -> Organization:
        item = self.repository.save(Organization(new_id("org"), name))
        self._audit(
            item.id,
            actor_id,
            "organization.created",
            "organization",
            item.id,
            {"name": name},
        )
        return item

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
        item = self.repository.save(
            Entity(new_id("ent"), principal.organization_id, name, parent_id, sector)
        )
        self._audit(
            principal.organization_id,
            principal.user_id,
            "entity.created",
            "entity",
            item.id,
            {"name": name},
        )
        return item

    def create_policy(
        self, principal: Principal, name: str, thresholds: dict, version: int
    ) -> PolicyVersion:
        authorize(principal, "configure", principal.organization_id)
        item = self.repository.save(
            PolicyVersion(
                new_id("pol"),
                principal.organization_id,
                version,
                name,
                thresholds,
                principal.user_id,
            )
        )
        self._audit(
            principal.organization_id,
            principal.user_id,
            "policy.version_created",
            "policy",
            item.id,
            {"version": version, "thresholds": thresholds},
        )
        return item

    def create_case(self, principal: Principal, case: RiskCase) -> RiskCase:
        authorize(principal, "write", case.organization_id)
        self.repository.get_entity(case.organization_id, case.entity_id)
        if case.snapshot_id:
            snapshot = self.repository.get_snapshot(case.organization_id, case.snapshot_id)
            if snapshot.organization_id != case.organization_id:
                raise PermissionError("snapshot organization does not match risk case")
            if snapshot.entity_id != case.entity_id:
                raise ValueError("snapshot entity does not match risk case")
        saved = self.repository.save(case)
        self._audit(
            case.organization_id,
            principal.user_id,
            "risk_case.created",
            "risk_case",
            case.id,
            case.to_dict(),
        )
        return saved

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
            if not verified_paths_for_domain(trace, case.domain.value):
                raise ValueError("a verified server-side evidence path is required")
        if target is RiskCaseStatus.RESOLVED and not case.resolution_evidence:
            raise ValueError("resolution evidence is required")
        expected_updated_at = case.updated_at
        previous, current = transition_case(case, target)
        saved = self.repository.save_case_transition(case, previous, expected_updated_at)
        self._audit(
            case.organization_id,
            principal.user_id,
            "risk_case.transitioned",
            "risk_case",
            case.id,
            {"from": previous, "to": current},
        )
        return saved

    def add_action(self, principal: Principal, case_id: str, description: str, owner_id: str, due_date: str) -> RiskCase:
        try:
            date.fromisoformat(due_date)
        except ValueError as exc:
            raise ValueError("due_date must be an ISO calendar date") from exc
        case = self.repository.get_case(principal.organization_id, case_id)
        authorize(principal, "write", case.organization_id)
        expected_updated_at = case.updated_at
        payload = add_mitigation_action(case, principal.user_id, description, owner_id, due_date)
        saved = self.repository.save_case_transition(
            case, case.status, expected_updated_at
        )
        self._audit(case.organization_id, principal.user_id, "risk_case.action_added", "risk_case", case.id, payload)
        return saved

    def add_resolution_evidence(self, principal: Principal, case_id: str, evidence_id: str) -> RiskCase:
        case = self.repository.get_case(principal.organization_id, case_id)
        authorize(principal, "review", case.organization_id)
        expected_updated_at = case.updated_at
        record_resolution_evidence(case, evidence_id)
        saved = self.repository.save_case_transition(
            case, case.status, expected_updated_at
        )
        self._audit(case.organization_id, principal.user_id, "risk_case.resolution_evidence_added", "risk_case", case.id, {"evidence_id": evidence_id})
        return saved

    def reopen(self, principal: Principal, case_id: str, reason: str) -> RiskCase:
        case = self.repository.get_case(principal.organization_id, case_id)
        authorize(principal, "review", case.organization_id)
        previous = case.status
        expected_updated_at = case.updated_at
        payload = reopen_case(case, principal.user_id, reason)
        saved = self.repository.save_case_transition(case, previous, expected_updated_at)
        self._audit(case.organization_id, principal.user_id, "risk_case.reopened", "risk_case", case.id, payload)
        return saved

    def save_risk_snapshot(
        self, principal: Principal, snapshot: RiskSnapshot
    ) -> RiskSnapshot:
        authorize(principal, "write", principal.organization_id)
        self.repository.get_entity(principal.organization_id, snapshot.entity_id)
        saved = self.repository.save_risk_snapshot(principal.organization_id, snapshot)
        self._audit(
            principal.organization_id,
            principal.user_id,
            "risk_snapshot.created",
            "risk_snapshot",
            f"{snapshot.entity_id}:{snapshot.period}",
            {"filing_id": snapshot.filing_id, "decision": snapshot.decision},
        )
        return saved

    def risk_timeline(self, principal: Principal, entity_id: str) -> list[RiskSnapshot]:
        authorize(principal, "read", principal.organization_id)
        self.repository.get_entity(principal.organization_id, entity_id)
        return self.repository.list_risk_snapshots(principal.organization_id, entity_id)

    def save_snapshot(self, principal: Principal, snapshot):
        authorize(principal, "write", snapshot.organization_id)
        self.repository.get_entity(snapshot.organization_id, snapshot.entity_id)
        saved = self.repository.save(snapshot)
        self._audit(
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
        return saved

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
        expected_updated_at = case.updated_at
        payload = record_override(case, principal.user_id, original, override, reason)
        saved = self.repository.save_case_transition(
            case, case.status, expected_updated_at
        )
        self._audit(
            case.organization_id,
            principal.user_id,
            "risk_case.overridden",
            "risk_case",
            case.id,
            payload,
        )
        return saved

    def _audit(
        self, organization_id, actor_id, action, object_type, object_id, payload
    ):
        self.repository.append_event(
            AuditEvent(
                new_id("evt"),
                organization_id,
                actor_id,
                action,
                object_type,
                object_id,
                payload,
            )
        )
