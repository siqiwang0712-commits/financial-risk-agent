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

    def paths_to(self, target: str, max_paths: int = 1000) -> list[list[str]]:
        """Every acyclic path ending at `target`, capped at `max_paths`.

        The number of paths through a DAG grows combinatorially with its edges, so
        an unbounded walk over a densely linked graph enumerates millions of lists
        and exhausts memory before it returns. `seen` already stops cycles, so the
        only thing missing was a bound on the result; callers that need the full
        enumeration can raise `max_paths`.
        """
        if target not in self.nodes:
            raise KeyError(target)
        if max_paths < 1:
            raise ValueError("max_paths must be at least 1")
        incoming: dict[str, list[str]] = {}
        for edge in self.edges:
            incoming.setdefault(edge.target, []).append(edge.source)

        def walk(node: str, seen: frozenset[str]) -> list[list[str]]:
            parents = incoming.get(node, [])
            if not parents:
                return [[node]]
            paths = []
            for parent in parents:
                if parent in seen:
                    continue
                for path in walk(parent, seen | {parent}):
                    paths.append(path + [node])
                    if len(paths) >= max_paths:
                        return paths
            return paths

        return walk(target, frozenset({target}))

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": [asdict(node) for node in self.nodes.values()], "edges": [asdict(edge) for edge in self.edges]}
