# Temporal Risk Intelligence

Current v0.4.2 temporal snapshots are **proposals**, not Assurance-authorized
final decisions. The storage-compatible `decision` aliases `proposed_decision` and
`final_decision` is null; final authority requires a verified assessment and certificate.

Status: **IMPLEMENTED, TESTED, AND EXECUTED ON THE 30-COMPANY NUMERIC E3 CORPUS; DOCUMENT/EVIDENCE ATTRIBUTION USEFULNESS NOT VALIDATED**.

## State transition

`EntityRiskState` retains ordered `RiskSnapshot` records. A new reporting period produces a `RiskDelta` rather than an isolated score. The delta contains overall score change, comparable dimension and metric changes, evidence additions/removals, and ranked attribution.

Attribution is deterministic. A driver can only cite evidence-path identifiers attached to the current dimension. Missing prior values remain absent and never become zero.

```text
R(t-1) + filing(t) → R(t)
                    ├── score/dimension/metric delta
                    ├── evidence delta
                    └── risk-change attribution → evidence path
```

## Temporal evidence graph

This is a library/schema capability, not a populated public runtime graph.

The graph supports `SUPPORTS`, `CONTRADICTS`, `SUPERSEDES`, `DERIVED_FROM`, `CONFIRMS`, `WEAKENS`, and `INVALIDATES`. Both nodes must exist and each relationship requires an explicit reason. Graph traversal exposes complete source-to-decision paths and cross-period relationships.

## Persistence and API

Migration `002_temporal_intelligence.sql` adds tenant-scoped risk snapshots, decision bundles and temporal evidence nodes/edges. The enterprise API exposes authenticated snapshot creation and timeline retrieval. Duplicate entity-period snapshots fail closed.

## Validation boundary

Unit and API integration fixtures validate state updates, attribution, evidence deltas, tenant scoping and duplicate rejection. Numeric B6 and 30 multi-period company trajectories were executed in E3. The held-out test is underpowered, and document/evidence attribution usefulness remains **NOT VALIDATED**.
