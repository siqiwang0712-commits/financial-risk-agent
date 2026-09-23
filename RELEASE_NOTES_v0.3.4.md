# FinRisk v0.3.4 — Hardened Boundaries & Verified Release Runtime

FinRisk v0.3.4 closes the v0.3.x architecture and runtime-hardening work without
changing the project's predictive or empirical claims.

## What changed

- The API, Agent and tool registry reuse one configured `FinRiskPipeline`, with explicit
  ownership for runtime composition, transport schemas, process isolation, frozen pilot
  projection and deployment-verification transport.
- PDF inspection and analysis execute in killable child processes. Timeouts reclaim the
  expensive work instead of returning while it continues in the background.
- SEC acquisition restricts official endpoints and validates identifiers, bounded
  responses and cache integrity. Hosted-LLM endpoints and untrusted document text have
  explicit fail-closed boundaries.
- Narrative extraction runs once per analysis. Agent traces, deterministic facts,
  contradiction checks, fusion and the final decision consume the same admitted evidence.
- The container release workflow builds each image once, verifies the candidate digest
  through both the production overlay and the operator-facing release Compose file, scans
  it, attaches supply-chain evidence and promotes the same manifest bytes.
- Regression coverage protects runtime ownership, process cleanup, external-input
  validation, evidence admission and the deployed authentication, limit, persistence and
  timeout contracts. The pre-release CI suite, including Docker smoke, passed on the
  implementation documented here.

## Research and product boundary

v0.3.4 does not introduce a new predictive model, recalibrate FinRisk scores, regenerate
E1/E2/E3, or modify `research/results/public_v1`. Those empirical artifacts remain
frozen. The hosted-provider smoke validates connectivity and schema conformance; it is not
a financial-reliability benchmark or human validation.

The FinRisk score remains an explainable heuristic risk index. Reliability remains
`UNCALIBRATED`. Predictive superiority, calibrated probability of default, regulatory
compliance, external validation and production validation are not established.
