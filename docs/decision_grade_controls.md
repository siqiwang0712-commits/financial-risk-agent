# Decision-grade Controls and Readiness

Status: **IMPLEMENTED BUT NOT EXTERNALLY VALIDATED**, except where explicitly marked.

## Reproducibility and audit

Each Agent result includes a decision trace and immutable analysis snapshot containing canonical input/output hashes, document hashes, rule/scoring hashes, provider/prompt identity, fusion version and frozen input/output. Replay comparison preserves the historical output and separately reports `IDENTICAL` or `DRIFT_DETECTED`; it never overwrites history. PostgreSQL stores snapshots and validation records. Risk cases cannot enter Accepted or Resolved without at least one verified decision path.

Every decision also carries machine-readable reason codes, so a reviewer can tell why a result landed where it did rather than inferring it from the score. The current set includes `SEVERE_VERIFIED_SIGNAL`, `INSUFFICIENT_EVIDENCE`, `CLAIM_CONTEXT_INCOMPLETE`, `HIGH_MODEL_DISAGREEMENT`, `UNVALIDATED_RELIABILITY` and `CRITICAL_DIMENSION_ESCALATION`.

## Governance

Model lifecycle transitions are Experimental → Validated → Approved → Deprecated. Validation and approval require a validation-record reference. Champion/challenger evaluation reports a recommendation but never auto-promotes. Drift checks cover score distribution and coverage; richer population-stability/calibration monitoring requires a real longitudinal dataset and is **PLANNED**. Human override remains reviewer-authorized, reason-required and append-only audited.

## Threat model

| Threat | Implemented control | Residual limitation |
|---|---|---|
| Cross-tenant/IDOR | Repository queries require organization ID; API identity comes from server-side hashed credential record | In-memory credential store; production identity provider NOT VALIDATED |
| Privilege escalation | Role is no longer accepted from caller headers | User lifecycle/SSO PLANNED |
| Credential theft | Only SHA-256 hashes retained; constant-time check; rotation revokes old key | Hardware-backed secret management PLANNED |
| Unsafe paths | Tenant-scoped storage rejects traversal | Malware scanning/object-store policy PLANNED |
| Prompt/data injection | Document text is delimited as untrusted data and the model is told not to obey it; LLM output is schema validated and cannot perform arithmetic/scoring; quotes require source verification; a zero-claim extraction on risk-bearing text is escalated rather than treated as "no risk found" | Adversarial corpus evaluation NOT RUN |
| Audit tampering | Service is append-only; PostgreSQL trigger rejects update/delete | External database permissions/retention NOT VALIDATED |

No SOC 2, ISO 27001, regulatory certification or production SLA is claimed.

## Observability and proposed SLOs

Structured events include correlation ID, stage, latency and failure type while filtering API keys, authorization values, document text and prompts. The hooks are OpenTelemetry-compatible in shape but no collector/exporter is configured. Proposed—not validated—objectives: API availability 99.5%, 95% job completion within 15 minutes, 100% material decisions with a proof path, and zero cross-tenant reads. These are design targets, not measured SLAs.

## Benchmark validity

The decision-grade manifest validator enforces required provenance, company-disjoint splits, review state and point-in-time leakage checks. The 90-observation numeric E3 corpus passed the PIT gate, and B0/B1/B2/B6 were executed. Neutral machine reviewers agreed on 90/90 normalized states, but this is not human gold. The held-out endpoint is underpowered; document/LLM confirmatory validation and human adjudication remain incomplete. Existing `public_v1` results remain unchanged and explicitly pilot-only.

## Deployment readiness

GitHub Actions provisions PostgreSQL and validates migration and restart persistence
before tests, while retaining lint, ≥90% coverage, frozen benchmark replay, frontend
security/type/test/build gates and a production-overlay Docker smoke test. The same
smoke passed locally using Docker Desktop 29.7.2, including explicit migration,
PostgreSQL-backed readiness, non-root API execution and persistence across API restart.
Production deployment is not claimed.
