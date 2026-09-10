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
- PostgreSQL adapter: implemented, unit-tested and CI integration-configured; no local
  PostgreSQL or Docker runtime was available for this validation.
- Rate limiting: the interface is shared-store-ready; the included sliding-window
  implementation is a process-local development fallback.
- Predictive superiority, calibrated probability of default, external validation,
  production SLA and regulatory compliance are not established.
