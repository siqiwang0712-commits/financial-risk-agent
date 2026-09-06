from __future__ import annotations

from copy import deepcopy

from .domain import (
    AnalysisSnapshot,
    AuditEvent,
    Entity,
    ModelRecord,
    Organization,
    PolicyVersion,
    RiskCase,
)
from .temporal import RiskSnapshot


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
        target = (
            self.organizations
            if isinstance(item, Organization)
            else self.entities
            if isinstance(item, Entity)
            else self.policies
            if isinstance(item, PolicyVersion)
            else self.cases
            if isinstance(item, RiskCase)
            else self.snapshots
            if isinstance(item, AnalysisSnapshot)
            else self.models
        )
        target[item.id] = deepcopy(item)
        return deepcopy(item)

    def get_case(self, organization_id: str, case_id: str) -> RiskCase:
        item = self.cases.get(case_id)
        if item is None or item.organization_id != organization_id:
            raise KeyError(case_id)
        return deepcopy(item)

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
