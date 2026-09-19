# Reproducibility and Runtime Integrity

## Frozen experiments

E1, E2 and E3 are historical v0.3.1 artifacts. Replay is deliberately read-only: it
validates the forensic manifest hash and each recorded artifact hash, reports the
original generation commit and the current replay commit, and performs no generation.
The E1/E2/E3 manifests record original generation commit
`1486cf8e2e86115bff27f3f0c8940e2237efaf10`; this provenance is preserved even though
the working tree and released code have advanced.
External-source re-verification is a separate status and is not implied by byte-level
artifact integrity.

```bash
python scripts/replay_frozen_experiment.py v0.3.1-E1-diagnostic
python scripts/replay_frozen_experiment.py v0.3.1-E2
python scripts/replay_frozen_experiment.py v0.3.1-E3
```

New experiments use a distinct v0.3.2 result directory, schema version and experiment
manifest. Their metadata records the actual Git commit and clean/dirty state. Manifests pin
dataset, split, rules, models, fusion, prompt, labels, seed and git revision; incomplete
inputs cannot create an immutable freeze. A new run
never rewrites E1/E2/E3 or `research/results/public_v1`.

Prospective provenance uses two explicit forms. Direct facts require accession, period,
concept, unit, dimensional context, source hash and availability time. Derived facts
require a formula and a cycle-free parent graph in which every parent reaches a valid
direct fact. A missing parent makes a submitted derivation invalid. During final closeout this correctly rejected 24 legacy corpus observations whose historical v1 `total_debt` derivation treated one missing component as zero; those frozen inputs and E3 outputs remain unchanged and are not silently upgraded to v2 provenance semantics. The narrowly scoped
v1 compatibility migration removes the known unsupported `total_debt` value from the
prospective feature view and records it as `UNAVAILABLE` before validation; it never
converts an invalid derivation into a valid fact or coerces missing data to zero.
Historical v1 artifacts are replayed under their frozen bytes, not regenerated or
relabelled under this newer contract.

## Auditability and fail-closed guarantees

The empirical path is designed so that a future run is auditable and fails closed:

- `PointInTimeGuard` rejects evidence made public after an observation cutoff, including later restatements.
- Dataset integrity stops on company overlap, future leakage, duplicate filings, invalid hashes, schema errors or system-generated labels.
- Forward labels are frozen independently of FinRisk output: an objective 12-month distress endpoint and a secondary rule-defined deterioration endpoint.
- Statistical tooling includes ranking/classification metrics, selective coverage and company-clustered bootstrap deltas. Case-control samples are explicitly `RANKING_ONLY`, not population PD calibration.

## Environment chain

Reproducibility is treated as four linked layers: data hashes and PIT manifests; Git code
revision; versioned rule/policy/schema configuration; and environment locks.
`requirements.lock` is a complete constraints set for the Python 3.11/3.12 CI matrix.
CI additionally fixes pip 26.2.0 and the setuptools 83.0.0 build backend, while official
GitHub Actions are referenced by immutable commit SHA rather than mutable tags.
The frontend uses npm's lockfile. Both Dockerfiles pin their base image as
`tag + digest` (`python:3.12-slim@sha256:…`, `node:22-alpine@sha256:…`) and
`docker-compose.release.yml` pins `postgres:17-alpine` the same way, so a rebuild of one
commit resolves the same base layers. The released application images go further: the
container-release workflow builds them once, verifies that exact digest on a real
Compose stack, and promotes the same digest to the release tags, so the artifact that was
tested is the artifact that is served.

The backend image consumes `requirements.lock` and installs the PostgreSQL extra, so a
configured `DATABASE_URL` has its required psycopg runtime. The production compose
overlay requires an explicit database password and bootstrap token, keeps initial
administrator provisioning token-gated, disables runtime auto-migration, and runs
migrations as a separate successful prerequisite. CI exercises
the composed PostgreSQL → migration → API path and checks repository selection through
`/health/ready`. The production-overlay path passed locally on Docker Desktop 29.7.2,
including migration success, non-root API execution and persistence across an API
restart. This validates the composed runtime boundary but is not production deployment
or availability validation.

## Runtime persistence

`DATABASE_URL` selects `PostgresEnterpriseRepository` and durable credential storage.
Without it, the in-memory repository is available only for tests and lightweight local
development. Production mode rejects missing or default database configuration.
Migrations cover organizations, entities, policies, risk cases, analysis and risk
snapshots, decision bundles, audit events, model records, validation records,
credentials, the temporal evidence graph and the shared rate-limit store. `documents`,
`jobs` and `alerts` are provisioned as reserved tables and are not exposed as runtime
endpoints. The CI PostgreSQL service validates CRUD, credential rotation and restart
persistence; this is engineering validation, not a production availability claim.

## Trust boundary

Clients submit business inputs, not trusted provenance. Material Risk Case fields are
derived from a server-held analysis snapshot. Accepted or resolved states require a
verified server-side evidence relationship. Expensive analysis routes require an API
credential and rate-limit check. Credentials use a long random identifier plus a
separately hashed secret; rotation revokes the former credential.

## Maturity and limitations

- Artifact integrity: verified locally for E1/E2/E3.
- External-source re-verification: not run by frozen replay.
- PostgreSQL adapter: implemented and validated locally with PostgreSQL 17 across
  migrations, CRUD, credential rotation and repository restart persistence. The same
  service-backed test is configured in CI; production deployment is not validated.
- Rate limiting: backed by `rate_limit_events` in PostgreSQL whenever `DATABASE_URL` is
  set, so the window survives a restart and is shared by every replica (admission
  serialised per key with a transaction-scoped advisory lock, expired rows swept in
  bounded batches, and a hard row cap that refuses admission rather than evicting live
  events). The in-process sliding window remains only the local/development fallback.
- Predictive superiority, calibrated probability of default, external validation,
  production SLA and regulatory compliance are not established.
