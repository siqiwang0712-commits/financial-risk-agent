# Enterprise Platform Boundary

FinRisk is an **enterprise financial-risk research prototype**, not a certified production or regulatory system. The upgrade preserves the audited finance pipeline and adds a modular-monolith enterprise boundary around it.

## Preserve / refactor / add / defer

| Boundary | Decision |
|---|---|
| PDF/XBRL provenance, reconciliation, finance formulas, rules/models, structured LLM, verifier, evidence graph, benchmark | Preserve |
| One-shot assessment output | Refactor behind failure-aware fusion, decision, trajectory, coverage and disagreement |
| Organization/entity/RBAC, versioned policy, risk cases, audit events, jobs, storage, scenarios and governance records | Add |
| ERP-specific connectors, SSO, distributed workers, external PostgreSQL validation, malware scanning, 90-observation gold benchmark | PLANNED / NOT VALIDATED |

## Dependency architecture

```text
Enterprise Platform Layer
  organization · entity · RBAC · storage · jobs · audit · REST · workbench
                         ↓
Risk Intelligence Layer
  deterministic finance · constrained LLM · verification · tension · fusion
                         ↓
Enterprise Risk Management Layer
  identify → assess → prioritize → escalate → assign → mitigate → review
```

The implementation remains a modular monolith. That is intentional: transactions, tenant isolation and reproducibility are easier to inspect than in prematurely distributed services.

## Failure-aware decision contract

The API and Agent return separate fields for `severity`, `trajectory`, `evidence_coverage`, `decision_confidence`, `model_disagreement` and `decision`. Coverage below the configured minimum produces `ABSTAIN`; material disagreement or verified contradictions produce `REVIEW`. A heuristic severity is never described as probability of default.

Four fusion strategies share one interface: weighted-average baseline, max severity, hierarchical escalation and transparent pairwise interaction. They are research candidates, not validated optimal models. Organization policies never modify the frozen research benchmark configuration.

## Tenant and governance controls

- Every entity, policy, case, document, job, model record and alert carries `organization_id`.
- RBAC distinguishes Admin, Risk Manager, Analyst, Reviewer and Viewer.
- API keys are stored as hashes; a process-local limiter is supplied for development.
- Audit events are append-only through the service interface; human overrides require actor, original value, replacement, reason and time.
- Local document storage rejects traversal and returns a SHA-256 receipt; object storage can implement the same protocol.
- PostgreSQL DDL covers enterprise records. The psycopg adapter and external database deployment remain **NOT VALIDATED** in this environment.

## REST surface

`/api/v1/enterprise` exposes organization bootstrap, tenant-scoped entities, risk cases, lifecycle transitions, override history, portfolio overview, audit events, deterministic scenarios and selectable fusion. Tenant routes require `X-Organization-Id`, `X-User-Id` and `X-Role` in the prototype.

## Proof and decision ownership

Material assessment claims still pass through the existing evidence verifier. Disclosure tension uses six labels: Supported, Weakly Supported, Context-dependent, Tension, Material Contradiction and Insufficient Evidence. These labels describe evidence relationships, never dishonesty or fraud.

AI detects and structures signals. A human reviewer retains authority over material acceptance, mitigation and closure.
