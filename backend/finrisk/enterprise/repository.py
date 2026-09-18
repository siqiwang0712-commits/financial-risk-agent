from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Protocol, TypeVar

from .decision_bundle import DecisionBundle
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

T = TypeVar("T")


class EnterpriseRepository(Protocol):
    """Tenant-scoped persistence contract shared by memory and PostgreSQL."""

    def save(self, item: T, event: AuditEvent | None = None) -> T: ...
    def get_case(self, organization_id: str, case_id: str) -> RiskCase: ...
    def get_entity(self, organization_id: str, entity_id: str) -> Entity: ...
    def list_cases(self, organization_id: str) -> list[RiskCase]: ...
    def append_event(self, event: AuditEvent) -> None: ...
    def list_events(self, organization_id: str) -> list[AuditEvent]: ...
    def get_snapshot(self, organization_id: str, snapshot_id: str) -> AnalysisSnapshot: ...
    def find_snapshot(
        self, organization_id: str, entity_id: str, input_hash: str, output_hash: str
    ) -> AnalysisSnapshot | None: ...
    def list_snapshots(self, organization_id: str) -> list[AnalysisSnapshot]: ...
    def save_risk_snapshot(self, organization_id: str, snapshot: RiskSnapshot, event: AuditEvent | None = None) -> RiskSnapshot: ...
    def list_risk_snapshots(self, organization_id: str, entity_id: str) -> list[RiskSnapshot]: ...
    def get_policy(self, organization_id: str, policy_id: str) -> PolicyVersion: ...
    def save_decision_bundle(self, bundle: DecisionBundle) -> DecisionBundle: ...
    def get_decision_bundle(self, organization_id: str, entity_id: str, bundle_id: str) -> DecisionBundle: ...


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
        self.decision_bundles: dict[str, DecisionBundle] = {}
        self._events: list[AuditEvent] = []
        self._event_ids: set[str] = set()
        self._lock = RLock()

    def save(self, item, event: AuditEvent | None = None):
        with self._lock:
            item_organization_id = (
                item.id if isinstance(item, Organization) else getattr(item, "organization_id", None)
            )
            if event is not None:
                if event.organization_id != item_organization_id:
                    raise ValueError("mutation and audit event must belong to the same tenant")
                if event.id in self._event_ids:
                    raise ValueError(f"audit event already exists: {event.id}")
            if isinstance(item, AnalysisSnapshot) and item.id in self.snapshots:
                raise ValueError(f"analysis snapshot already exists: {item.id}")
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
            existing = target.get(item.id)
            if (
                existing is not None
                and hasattr(item, "organization_id")
                and item.organization_id != existing.organization_id
            ):
                raise ValueError(f"cross-tenant identifier collision rejected: {item.id}")
            saved = deepcopy(item)
            if isinstance(item, RiskCase) and item.id in self.cases:
                current = self.cases[item.id]
                if item.organization_id != current.organization_id or item.version != current.version:
                    raise ValueError(f"concurrent risk case update rejected: {item.id}")
                saved.version += 1
            target[item.id] = saved
            if event is not None:
                self._events.append(deepcopy(event))
                self._event_ids.add(event.id)
            return deepcopy(saved)

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

    def get_policy(self, organization_id: str, policy_id: str) -> PolicyVersion:
        item = self.policies.get(policy_id)
        if item is None or item.organization_id != organization_id:
            raise KeyError(policy_id)
        return deepcopy(item)

    def append_event(self, event: AuditEvent) -> None:
        with self._lock:
            if event.organization_id not in self.organizations:
                raise ValueError("audit event organization does not exist")
            if event.id in self._event_ids:
                raise ValueError(f"audit event already exists: {event.id}")
            self._events.append(deepcopy(event))
            self._event_ids.add(event.id)

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

    def find_snapshot(
        self, organization_id: str, entity_id: str, input_hash: str, output_hash: str
    ) -> AnalysisSnapshot | None:
        """Most recent snapshot of an identical frozen input/output, if any."""
        matches = [
            item
            for item in self.snapshots.values()
            if item.organization_id == organization_id
            and item.entity_id == entity_id
            and item.input_hash == input_hash
            and item.output_hash == output_hash
        ]
        if not matches:
            return None
        return deepcopy(max(matches, key=lambda item: item.created_at))

    def list_snapshots(self, organization_id: str) -> list[AnalysisSnapshot]:
        """Every frozen analysis snapshot held for one tenant, oldest first.

        Deduplication is content-addressed, so the row count is the observable proof
        that repeated identical runs do not grow storage.
        """
        return [
            deepcopy(item)
            for item in self.snapshots.values()
            if item.organization_id == organization_id
        ]

    def save_risk_snapshot(
        self, organization_id: str, snapshot: RiskSnapshot, event: AuditEvent | None = None
    ) -> RiskSnapshot:
        key = (organization_id, snapshot.entity_id, snapshot.period)
        with self._lock:
            if event is not None:
                if event.organization_id != organization_id:
                    raise ValueError("mutation and audit event must belong to the same tenant")
                if event.id in self._event_ids:
                    raise ValueError(f"audit event already exists: {event.id}")
            if key in self.risk_snapshots:
                raise ValueError(f"risk snapshot already exists for {snapshot.period}")
            self.risk_snapshots[key] = deepcopy(snapshot)
            if event is not None:
                self._events.append(deepcopy(event))
                self._event_ids.add(event.id)
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

    def save_decision_bundle(self, bundle: DecisionBundle) -> DecisionBundle:
        with self._lock:
            if bundle.bundle_id in self.decision_bundles:
                raise ValueError(f"decision bundle already exists: {bundle.bundle_id}")
            self.get_entity(bundle.organization_id, bundle.entity_id)
            self.decision_bundles[bundle.bundle_id] = deepcopy(bundle)
            return deepcopy(bundle)

    def get_decision_bundle(self, organization_id: str, entity_id: str, bundle_id: str) -> DecisionBundle:
        bundle = self.decision_bundles.get(bundle_id)
        if bundle is None or bundle.organization_id != organization_id or bundle.entity_id != entity_id:
            raise KeyError(bundle_id)
        return deepcopy(bundle)
