# API Reference

FinRisk exposes a FastAPI application. When the backend is running locally, the
interactive OpenAPI UI is available at `http://localhost:8000/docs`.

This page describes the stable route surface and its operational contracts. Request and
response schemas in the generated OpenAPI document remain the field-level source of truth.

## Authentication and tenancy

The liveness, readiness and frozen public-pilot routes are unauthenticated. Analysis and
enterprise routes require an `X-API-Key` unless noted otherwise. Authenticated requests
are rate-limited per tenant and user.

Enterprise identity, organization and role are resolved from the server-side credential
record. Caller-supplied organization or role headers are not trusted. API keys are shown
only when issued and are stored as hashes server-side.

`POST /api/v1/enterprise/organizations` is the first-run exception: it creates an
organization and returns the first ADMIN key. The route is disabled unless
`FINRISK_ENABLE_ORG_BOOTSTRAP=1`; in production it also requires a matching
`X-Bootstrap-Token`. Disable bootstrap and clear the token immediately after provisioning.

## Health and public data

| Method and path | Purpose |
|---|---|
| `GET /health/live` | Process liveness. It deliberately does not touch the database. |
| `GET /health/ready` | Datastore reachability, credential acceptance and required schema sentinels. |
| `GET /health` | Compatibility alias for readiness; omitted from the OpenAPI schema. |
| `GET /api/v1/public-pilot` | Frozen v0.3.0 public-pilot rows served from a checked-in artifact. |

Readiness proves that the required database objects are present, not that every column,
constraint and index matches the migrations. Use `scripts/validate_postgres_migration.py`
for full migration validation.

## Analysis routes

All routes in this table require `X-API-Key`.

| Method and path | Purpose |
|---|---|
| `POST /api/v1/assess` | Assess normalized current/prior financial data and optional page text through the shared deterministic pipeline. |
| `POST /api/v1/agent/assess` | Run the full Agent workflow over the same input contract. |
| `POST /api/v1/documents/analyze` | Validate and analyze an uploaded PDF. |
| `POST /api/v1/xbrl/normalize` | Normalize SEC Company Facts while retaining provenance. |

The default narrative provider is deterministic and offline. To use the
schema-constrained hosted provider, copy `.env.example`, set
`FINRISK_LLM_PROVIDER=openai`, configure `OPENAI_API_KEY` (preferably through
`OPENAI_API_KEY_FILE` for a deployment), and set explicit model pricing when cost
estimates are required. Tests do not require a live provider.

### PDF upload and process boundary

PDF uploads validate their magic bytes and the configured limits:

- `FINRISK_MAX_UPLOAD_BYTES`
- `FINRISK_MAX_PDF_PAGES`
- `FINRISK_MAX_EXTRACTED_CHARS`
- `FINRISK_ANALYSIS_TIMEOUT_SECONDS`

The historical `FINRISK_MAX_UPLOAD_MB` variable is still honored when the byte-based
setting is absent. Invalid, encrypted, oversized or timed-out documents fail closed and
temporary files are removed.

Opening, page counting, page-text scanning and analysis run in killable child processes
in every environment. A timeout therefore terminates the expensive work instead of
returning while that work continues on the async event loop. Internet-facing deployment
still requires production identity, malware scanning, distributed workers for scale and
operational validation.

## Enterprise routes

The prefix for every route below is `/api/v1/enterprise`. Except for organization
bootstrap, all require `X-API-Key` and are scoped to the authenticated organization.

### Organizations and entities

| Method and path | Purpose |
|---|---|
| `POST /organizations` | First-run provisioning; returns the initial ADMIN key. |
| `POST /entities` | Register a tenant-owned entity. |
| `GET /overview` | Return the organization's portfolio roll-up. |

### Risk cases

| Method and path | Purpose |
|---|---|
| `POST /risk-cases` | Create a case from a server-held analysis snapshot. |
| `GET /risk-cases` | List cases in the authenticated organization. |
| `POST /risk-cases/{case_id}/transition` | Apply a permitted lifecycle transition. |
| `POST /risk-cases/{case_id}/override` | Record a reason-required human override while preserving the original decision. |
| `POST /risk-cases/{case_id}/actions` | Add an owned mitigation action and due date. |
| `POST /risk-cases/{case_id}/resolution-evidence` | Attach evidence required for resolution. |
| `POST /risk-cases/{case_id}/reopen` | Reopen an accepted or resolved case with actor, reason and timestamp. |

Risk cases cannot be created from arbitrary caller claims: material fields are derived
from a server-held snapshot. Accepted and resolved terminal states require a verified
decision path, and every mutation emits an append-only audit event.

### Policies, snapshots and audit

| Method and path | Purpose |
|---|---|
| `POST /policies` | Create versioned KRI thresholds. |
| `POST /policies/{policy_id}/evaluate` | Evaluate stored thresholds against supplied metrics. |
| `POST /snapshots` | Import a snapshot only while bootstrap/import is explicitly enabled; caller-asserted verified paths are rejected. |
| `POST /snapshots/{snapshot_id}/replay-diff` | Compare a replayed output with the immutable historical snapshot. |
| `GET /audit-events` | Return the tenant's append-only audit trail. |

Replay creates a comparison; it does not overwrite the historical decision.

### Temporal risk, applicability and decision support

| Method and path | Purpose |
|---|---|
| `POST /entities/{entity_id}/risk-snapshots` | Store a tenant-scoped risk snapshot. |
| `GET /entities/{entity_id}/risk-timeline` | Return ordered risk states and comparable deltas. |
| `POST /applicability` | Evaluate traditional-model applicability for an industry and fact set. |
| `POST /selective-decision` | Apply evidence coverage, reliability, disagreement and calibration gates. |
| `POST /fusion` | Run a supported transparent fusion strategy. |
| `POST /scenarios` | Compare deterministic stress shocks with a supplied baseline. |

These endpoints expose explicit tools; they do not silently alter the one-shot assessment
contract. Unknown fusion methods, unknown scenario shocks and non-computable scenarios
are rejected rather than guessed.

## Errors and correlation

Failures use a JSON `detail` body and include `X-Correlation-Id`. Middleware-generated
`500` and `503` responses also include a `correlation_id` field in the body. A datastore
outage produces a controlled `503` with `Retry-After`; rate-limiter store failure also
fails closed.

Validation errors return `422` with a JSON-serializable error body instead of becoming a
`500`. The current API does not yet provide a common response envelope or stable
machine-readable error codes, so a single `422` status covers several distinct rejection
reasons.

## Deployment boundary

The API surface is implemented and tested as a research prototype. Production identity,
malware scanning, distributed job execution, externally operated PostgreSQL, object
storage, telemetry operations and regulatory validation are not established. See
[Decision-grade controls](decision_grade_controls.md),
[Container release and deployment](CONTAINER_RELEASE.md), and
[Project Status](../PROJECT_STATUS.md).
