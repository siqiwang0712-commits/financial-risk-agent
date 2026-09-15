from __future__ import annotations

from copy import deepcopy
from typing import Protocol, TypeVar

from .domain import (
    AnalysisSnapshot,
    AuditEvent,
    Entity,
    ModelRecord,
    Organization,
    PolicyVersion,
    RiskCase,
    RiskCaseStatus,
)
from .temporal import RiskSnapshot

T = TypeVar("T")


class EnterpriseRepository(Protocol):
    """Tenant-scoped persistence contract shared by memory and PostgreSQL."""

    def save(self, item: T) -> T: ...
    def save_case_transition(
        self,
        case: RiskCase,
        expected_status: RiskCaseStatus,
        expected_updated_at: str | None = None,
    ) -> RiskCase: ...
    def get_case(self, organization_id: str, case_id: str) -> RiskCase: ...
    def get_entity(self, organization_id: str, entity_id: str) -> Entity: ...
    def list_cases(self, organization_id: str) -> list[RiskCase]: ...
    def append_event(self, event: AuditEvent) -> None: ...
    def list_events(self, organization_id: str) -> list[AuditEvent]: ...
    def get_snapshot(self, organization_id: str, snapshot_id: str) -> AnalysisSnapshot: ...
    def save_risk_snapshot(self, organization_id: str, snapshot: RiskSnapshot) -> RiskSnapshot: ...
    def list_risk_snapshots(self, organization_id: str, entity_id: str) -> list[RiskSnapshot]: ...
    def get_policy(self, organization_id: str, policy_id: str) -> PolicyVersion: ...


class InMemoryEnterpriseRepository:
    """Tenant-safe reference repository used for local development and tests."""

    def __init__(self):
        self.organizations: dict[str, Organization] = {}
        self.entities: dict[str, Entity] = {}
        self.policies: dict[str, PolicyVersion] = {}
        self.cases: dict[str, RiskCase] = {}
        self.models: dict[str, ModelRecord] = {}
        self.snapshots: dict[str, AnalysisSnapshot] = {}
        self.risk_snapshots: dict[tuple[str, str, str], RiskSnapshot] = {}
        self._events: list[AuditEvent] = []

    def save(self, item):
        if isinstance(item, AnalysisSnapshot) and item.id in self.snapshots:
            raise ValueError(f"analysis snapshot already exists: {item.id}")
        if isinstance(item, Organization):
            target = self.organizations
        elif isinstance(item, Entity):
            target = self.entities
        elif isinstance(item, PolicyVersion):
            target = self.policies
        elif isinstance(item, RiskCase):
            target = self.cases
        elif isinstance(item, AnalysisSnapshot):
            target = self.snapshots
        elif isinstance(item, ModelRecord):
            target = self.models
        else:
            # `PostgresEnterpriseRepository.save` raises `TypeError` here. The
            # dispatch chain used to end in `self.models`, so an unsupported type
            # (e.g. `ValidationRecord`) was silently filed among the model records
            # -- present in memory, absent from PostgreSQL, and wrong in both.
            raise TypeError(f"unsupported repository item: {type(item).__name__}")
        target[item.id] = deepcopy(item)
        return deepcopy(item)

    def get_case(self, organization_id: str, case_id: str) -> RiskCase:
        item = self.cases.get(case_id)
        if item is None or item.organization_id != organization_id:
            raise KeyError(case_id)
        return deepcopy(item)

    def save_case_transition(
        self,
        case: RiskCase,
        expected_status: RiskCaseStatus,
        expected_updated_at: str | None = None,
    ) -> RiskCase:
        """Persist a case mutation only if the stored revision is unchanged.

        `transition` reads a case, mutates it and saves it back with no
        precondition, so two reviewers acting on the same case both succeeded and
        the second write silently discarded the first -- and with it the state
        machine: a case could end up in a state its own `TRANSITIONS` table
        forbids, because the loser validated against a status that no longer
        existed. Comparing against the status the caller read closes that window.
        """
        stored = self.cases.get(case.id)
        if stored is None or stored.organization_id != case.organization_id:
            raise KeyError(case.id)
        if stored.status is not expected_status:
            raise ValueError(
                f"case {case.id} changed concurrently: expected {expected_status}, "
                f"found {stored.status}"
            )
        if expected_updated_at is not None and stored.updated_at != expected_updated_at:
            raise ValueError(
                f"case {case.id} changed concurrently: expected revision "
                f"{expected_updated_at}, found {stored.updated_at}"
            )
        self.cases[case.id] = deepcopy(case)
        return deepcopy(case)

    def get_entity(self, organization_id: str, entity_id: str) -> Entity:
        item = self.entities.get(entity_id)
        if item is None or item.organization_id != organization_id:
            raise KeyError(entity_id)
        return deepcopy(item)

    def list_cases(self, organization_id: str) -> list[RiskCase]:
        return [
            deepcopy(item)
            for item in self.cases.values()
            if item.organization_id == organization_id
        ]

    def get_policy(self, organization_id: str, policy_id: str) -> PolicyVersion:
        item = self.policies.get(policy_id)
        if item is None or item.organization_id != organization_id:
            raise KeyError(policy_id)
        return deepcopy(item)

    def append_event(self, event: AuditEvent) -> None:
        self._events.append(deepcopy(event))

    def list_events(self, organization_id: str) -> list[AuditEvent]:
        return [
            deepcopy(event)
            for event in self._events
            if event.organization_id == organization_id
        ]

    def get_snapshot(self, organization_id: str, snapshot_id: str) -> AnalysisSnapshot:
        item = self.snapshots.get(snapshot_id)
        if item is None or item.organization_id != organization_id:
            raise KeyError(snapshot_id)
        return deepcopy(item)

    def save_risk_snapshot(
        self, organization_id: str, snapshot: RiskSnapshot
    ) -> RiskSnapshot:
        key = (organization_id, snapshot.entity_id, snapshot.period)
        if key in self.risk_snapshots:
            raise ValueError(f"risk snapshot already exists for {snapshot.period}")
        self.risk_snapshots[key] = deepcopy(snapshot)
        return deepcopy(snapshot)

    def list_risk_snapshots(
        self, organization_id: str, entity_id: str
    ) -> list[RiskSnapshot]:
        return sorted(
            [
                deepcopy(item)
                for (org, entity, _), item in self.risk_snapshots.items()
                if org == organization_id and entity == entity_id
            ],
            key=lambda item: item.period,
        )
