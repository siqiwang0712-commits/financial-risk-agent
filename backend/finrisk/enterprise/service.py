from __future__ import annotations

from .auth import authorize
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
from .repository import InMemoryEnterpriseRepository
from .workflow import record_override, transition_case


class EnterpriseRiskService:
    def __init__(self, repository: InMemoryEnterpriseRepository | None = None):
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
        if (
            target in {RiskCaseStatus.ACCEPTED, RiskCaseStatus.RESOLVED}
            and case.decision_trace.get("verified_path_count", 0) < 1
        ):
            raise ValueError(
                "a verified decision trace is required for a material final state"
            )
        previous, current = transition_case(case, target)
        saved = self.repository.save(case)
        self._audit(
            case.organization_id,
            principal.user_id,
            "risk_case.transitioned",
            "risk_case",
            case.id,
            {"from": previous, "to": current},
        )
        return saved

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
        payload = record_override(case, principal.user_id, original, override, reason)
        saved = self.repository.save(case)
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
