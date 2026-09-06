# Temporal Risk Intelligence

Status: **IMPLEMENTED AND TESTED WITH CONTROLLED FIXTURES; NOT YET VALIDATED ON A MULTI-PERIOD PUBLIC CORPUS**.

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

The graph supports `SUPPORTS`, `CONTRADICTS`, `SUPERSEDES`, `DERIVED_FROM`, `CONFIRMS`, `WEAKENS`, and `INVALIDATES`. Both nodes must exist and each relationship requires an explicit reason. Graph traversal exposes complete source-to-decision paths and cross-period relationships.

## Persistence and API

Migration `002_temporal_intelligence.sql` adds tenant-scoped risk snapshots, decision bundles and temporal evidence nodes/edges. The enterprise API exposes authenticated snapshot creation and timeline retrieval. Duplicate entity-period snapshots fail closed.

## Validation boundary

Unit and API integration fixtures validate state updates, attribution, evidence deltas, tenant scoping and duplicate rejection. The existing public pilot has only one period per company, so real temporal accuracy and attribution usefulness remain **NOT VALIDATED**.
