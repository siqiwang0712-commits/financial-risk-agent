from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class EvidenceRelation(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    SUPERSEDES = "SUPERSEDES"
    DERIVED_FROM = "DERIVED_FROM"
    CONFIRMS = "CONFIRMS"
    WEAKENS = "WEAKENS"
    INVALIDATES = "INVALIDATES"


@dataclass(frozen=True)
class EvidenceNode:
    id: str
    kind: str
    period: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class EvidenceEdge:
    source: str
    target: str
    relation: EvidenceRelation
    reason: str


# Relations that mean "the source supports the target".
SUPPORT_RELATIONS: frozenset[EvidenceRelation] = frozenset(
    {
        EvidenceRelation.SUPPORTS,
        EvidenceRelation.CONFIRMS,
        EvidenceRelation.DERIVED_FROM,
    }
)

# Relations that mean the opposite. Following these as if they were support is
# how "counter-evidence" became a path *to* the conclusion it contradicts.
ADVERSE_RELATIONS: frozenset[EvidenceRelation] = frozenset(
    {
        EvidenceRelation.CONTRADICTS,
        EvidenceRelation.WEAKENS,
        EvidenceRelation.INVALIDATES,
    }
)

# `SUPERSEDES` is deliberately in neither set: it records that a newer artifact
# replaced an older one, which is provenance rather than support or opposition.
# A caller that wants those paths must ask for them explicitly.


@dataclass
class TemporalEvidenceGraph:
    nodes: dict[str, EvidenceNode] = field(default_factory=dict)
    edges: list[EvidenceEdge] = field(default_factory=list)

    def add_node(self, node: EvidenceNode) -> None:
        if node.id in self.nodes and self.nodes[node.id] != node:
            raise ValueError(f"evidence node id collision: {node.id}")
        self.nodes[node.id] = node

    def link(self, source: str, target: str, relation: EvidenceRelation, reason: str) -> None:
        if source not in self.nodes or target not in self.nodes:
            raise KeyError("both evidence nodes must exist before linking")
        if not reason.strip():
            raise ValueError("evidence relationship requires a reason")
        self.edges.append(EvidenceEdge(source, target, relation, reason))

    def paths_to(
        self, target: str, relations: frozenset[EvidenceRelation] | None = None
    ) -> list[list[str]]:
        """Support paths into `target`.

        `paths_to` used to walk every edge regardless of its relation, so an edge
        meaning "this evidence contradicts the conclusion" came back as a path
        *to* the conclusion - adverse evidence was indistinguishable from
        support. Only `SUPPORT_RELATIONS` are followed by default; a caller that
        wants the opposing chains can pass `ADVERSE_RELATIONS`.
        """
        if target not in self.nodes:
            raise KeyError(target)
        followed = SUPPORT_RELATIONS if relations is None else relations
        incoming: dict[str, list[str]] = {}
        for edge in self.edges:
            if edge.relation in followed:
                incoming.setdefault(edge.target, []).append(edge.source)

        def walk(node: str, seen: frozenset[str]) -> list[list[str]]:
            parents = incoming.get(node, [])
            if not parents:
                return [[node]]
            paths = []
            for parent in parents:
                if parent in seen:
                    continue
                paths.extend(path + [node] for path in walk(parent, seen | {parent}))
            return paths

        return walk(target, frozenset({target}))

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": [asdict(node) for node in self.nodes.values()], "edges": [asdict(edge) for edge in self.edges]}
