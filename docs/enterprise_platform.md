# Enterprise Platform Boundary

FinRisk is an **assurance-controlled financial-risk research prototype**, not a certified
production or regulatory system. v0.4 preserves the audited finance pipeline and adds an
independent decision-authorization boundary. The authoritative design is
[FinRisk v0.4 Assurance Architecture](assurance_architecture.md).

## Preserve / refactor / add / defer

| Boundary | Decision |
|---|---|
| PDF/XBRL provenance, reconciliation, finance formulas, rules/models, structured LLM, verifier, evidence graph, benchmark | Preserve |
| One-shot assessment output | Refactor behind failure-aware fusion, decision, trajectory, coverage and disagreement |
| Organization/entity/RBAC, versioned policy, risk cases, audit events, scenarios and governance records | Add |
| Jobs, document/object storage, alerts and temporal evidence graph | Library/schema only; not a public runtime capability |
| ERP-specific connectors, SSO, distributed workers, external PostgreSQL validation, malware scanning, 90-observation gold benchmark | PLANNED / NOT VALIDATED |

## Dependency architecture

```text
Enterprise Platform Layer
  organization · entity · RBAC · persistence · audit · REST · workbench
                         ↓
Risk Intelligence Layer
  deterministic finance · constrained LLM · verification · tension · fusion → proposal
                         ↓
Decision Assurance Layer
  evidence assurance · fragility · distribution validity · admission policy
                         ↓
Enterprise Risk Management Layer
  identify → assess → prioritize → escalate → assign → mitigate → review
```

The implementation remains a modular monolith. That is intentional: transactions, tenant isolation and reproducibility are easier to inspect than in prematurely distributed services.

### v0.4 execution and authority boundary

The runtime is organized as a strict four-part decision path:

1. **Interface Layer** — FastAPI and the Next.js Workbench present inputs, workflow and
   proof. They do not calculate financial risk.
2. **Prediction Layer** — tools and Agent reasoning compute signals and a
   `proposed_decision`; neither owns final authorization.
3. **Assurance Layer** — `AssuranceEngine` evaluates evidence, deterministic fragility,
   distribution validity, calibration and policy.
4. **Certificate Layer** — the authorized result and replay metadata are content-hashed.

`FinRiskPipeline` owns the configured rules, scoring policy, narrative provider and
evidence verifier shared by the API, Agent and tool registry. The Agent orchestrates that
pipeline; it does not replace deterministic calculation and cannot authorize itself. The detailed
module migration is recorded in [Three-layer migration map](three_layer_migration.md).

Only structured execution metadata is retained: plan step, tool name, status, result
summary, admitted evidence references, rationale and confidence. Hidden chain-of-thought
is neither stored nor displayed.

### Agent orchestration and tool registry

| Tool family | Capabilities |
|---|---|
| Ingestion | PDF extraction, XBRL normalization, period and unit reconciliation |
| Financial | Ratios, trends, period comparison, missing-data detection and scenarios |
| Models | Altman, Beneish, Piotroski, Ohlson and applicability checks |
| Rules | Versioned single-factor and cross-factor risk signals |
| Evidence | Retrieval, quote verification and provenance graph construction |
| Consistency | Narrative–numeric support, tension and contradiction classification |
| Decision | Signal calculation, policy resolution, fusion, snapshot and replay |
| Temporal | Entity risk state, evidence delta, attribution and filing timeline |
| Governance | Applicability, selective automation, critic/verifier and DecisionBundle |

Unknown tools, malformed arguments and missing required inputs fail closed.

### Deterministic financial layer

Liquidity, leverage, debt service, profitability, cash flow, working capital and
multi-period growth are calculated from normalized inputs. When prior-year values exist,
balance-based return and working-capital metrics use average balances; a single-period
proxy is labeled as such.

| Model | Output | Guardrail |
|---|---|---|
| Altman Z | Distress screening zone | Public-manufacturer applicability checks |
| Beneish M | Manipulation-risk screening signal | Never presented as proof of fraud |
| Piotroski-style F-Score proxy | Nine-signal financial-strength proxy | Limited, non-canonical implementation; original value-stock context disclosed |
| Ohlson O | O-score and separately derived logistic probability | Input-domain and unit warnings |

Model mappings live in [`config/model_scoring.json`](../config/model_scoring.json).
[`rules/rules.json`](../rules/rules.json) contains 68 versioned single-factor and
cross-factor definitions. Runtime enables the 43 rules with real producers; the 25 legacy
definitions without legitimate producers are explicitly disabled with reasons in
[`rules/disabled_rules.json`](../rules/disabled_rules.json). Startup and CI reject any
other unproducible condition. Correlated rules carry family metadata so scoring and proof
coverage retain only the strongest applicable family signal.

Missing evidence, low coverage, conflicts, stale data, parser failure, unavailable LLMs,
applicability failures and rule/model disagreement remain first-class states. Depending on
the pinned policy they reduce evidence sufficiency, require review or force abstention;
they are never converted into fabricated certainty. The incident-style
[Failure Lab](../failure_lab/README.md) maps injected failures to expected fail-closed
responses and regression tests.

## Proposal and Assurance contract

The API and Agent return separate fields for risk, proposal, assurance and final decision.
Coverage below the configured minimum can produce `ABSTAIN`; material disagreement,
fragility or invalid/unknown distribution scope can produce `REVIEW`. A heuristic severity
is never described as probability of default. No valid `AssuranceResult` means no
authorized final decision.

Four fusion strategies share one interface: weighted-average baseline, max severity, hierarchical escalation and transparent pairwise interaction. They are research candidates, not validated optimal models. Organization policies never modify the frozen research benchmark configuration.

## Tenant and governance controls

- Every persisted entity, policy, case, snapshot, bundle, credential and audit event carries `organization_id`.
- RBAC distinguishes Admin, Risk Manager, Analyst, Reviewer and Viewer.
- API keys are stored as hashes server-side (and persisted as hashes in `api_credentials` when PostgreSQL is selected); rate limits live in `rate_limit_events` and are shared across replicas, falling back to an in-process window only for local runs.
- Audit events are append-only through the service interface; human overrides require actor, original value, replacement, reason and time.
- Local document storage rejects traversal and returns a SHA-256 receipt; object storage can implement the same protocol.
- PostgreSQL DDL and the pooled psycopg adapter cover the wired runtime records and
  are migration/restart/Docker tested locally. External production deployment remains
  **NOT VALIDATED**. Reserved jobs/documents/alerts/temporal-graph tables are not
  presented as connected runtime features.

## REST surface

`/api/v1/enterprise` exposes organization bootstrap (disabled by default, and token-gated
whenever it is enabled outside development), tenant-scoped entities,
risk cases, lifecycle transitions, override history, portfolio overview, audit events,
deterministic scenarios and selectable fusion. Tenant identity and role come from the
server-side hashed API credential; caller-supplied role headers are not trusted.

The complete route inventory, upload limits and error contract are in the
[API reference](API_REFERENCE.md).

## Analyst Workbench

The Workbench follows the analyst's operational path rather than a chat metaphor:

```text
Portfolio → Entity → Risk Case → Risk Drivers → Evidence
          → Scenario → Governance → Audit
```

Proposed risk, Assurance status and final decision form the primary hierarchy. Evidence
support, fragility, distribution validity, policy maturity and model disagreement remain
separate. Findings can become owned cases with reviewer status, due dates,
actions, comments and an audited human override.

When the API is unreachable, the Workbench falls back to a bundled sample and labels its
origin on screen. That sample is a real pipeline output for the repository's explicitly
synthetic fixture, not a hand-written mock-up. The screenshot at
[`docs/assets/dashboard-running.png`](assets/dashboard-running.png) is from the local
prototype and is not evidence of a hosted production deployment.

## Proof and decision ownership

Material assessment claims still pass through the existing evidence verifier. Disclosure tension uses six labels: Supported, Weakly Supported, Context-dependent, Tension, Material Contradiction and Insufficient Evidence. These labels describe evidence relationships, never dishonesty or fraud.

Prediction components detect and structure signals. Assurance controls system issuance;
a human reviewer retains authority over material acceptance, mitigation and closure.
