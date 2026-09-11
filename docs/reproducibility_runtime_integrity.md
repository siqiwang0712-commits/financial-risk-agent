# Reproducibility and Runtime Integrity

## Frozen experiments

E1, E2 and E3 are historical v0.3.1 artifacts. Replay is deliberately read-only: it
validates the forensic manifest hash and each recorded artifact hash, reports the
original generation commit and the current replay commit, and performs no generation.
External-source re-verification is a separate status and is not implied by byte-level
artifact integrity.

```bash
python scripts/replay_frozen_experiment.py v0.3.1-E1-diagnostic
python scripts/replay_frozen_experiment.py v0.3.1-E2
python scripts/replay_frozen_experiment.py v0.3.1-E3
```

New experiments use a distinct v0.3.2 result directory, schema version and experiment
manifest. Their metadata records the actual Git commit and clean/dirty state. A new run
never rewrites E1/E2/E3 or `research/results/public_v1`.

Prospective provenance uses two explicit forms. Direct facts require accession, period,
concept, unit, dimensional context, source hash and availability time. Derived facts
require a formula and a cycle-free parent graph in which every parent reaches a valid
direct fact. A missing parent makes a submitted derivation invalid. The narrowly scoped
v1 compatibility migration removes the known unsupported `total_debt` value from the
prospective feature view and records it as `UNAVAILABLE` before validation; it never
converts an invalid derivation into a valid fact or coerces missing data to zero.
Historical v1 artifacts are replayed under their frozen bytes, not regenerated or
relabelled under this newer contract.

## Environment chain

Reproducibility is treated as four linked layers: data hashes and PIT manifests; Git code
revision; versioned rule/policy/schema configuration; and environment locks.
`requirements.lock` is a complete constraints set for the Python 3.11/3.12 CI matrix.
CI additionally fixes pip 25.2 and the setuptools 80.9.0 build backend, while official
GitHub Actions are referenced by immutable commit SHA rather than mutable tags.
The frontend uses npm's lockfile. Dockerfiles select fixed major/minor runtime families,
but image digests are not pinned because this machine cannot pull and verify them; image
byte identity is therefore not claimed.

## Runtime persistence

`DATABASE_URL` selects `PostgresEnterpriseRepository` and durable credential storage.
Without it, the in-memory repository is available only for tests and lightweight local
development. Production mode rejects missing or default database configuration.
Migrations cover organizations, entities, policies, risk cases, analysis/risk snapshots,
audit events, model records and credentials. The CI PostgreSQL service validates CRUD,
credential rotation and restart persistence; this is engineering validation, not a
production availability claim.

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
- Rate limiting: the interface is shared-store-ready; the included sliding-window
  implementation is a process-local development fallback.
- Predictive superiority, calibrated probability of default, external validation,
  production SLA and regulatory compliance are not established.
