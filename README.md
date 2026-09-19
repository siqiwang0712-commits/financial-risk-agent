<div align="center">

<img src="docs/assets/finrisk-platform.svg" alt="FinRisk — evidence-grounded financial risk intelligence" width="100%" />

# FinRisk

### Enterprise Financial Risk Intelligence & Management — Research Prototype

[![CI](https://github.com/siqiwang0712-commits/financial-risk-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/siqiwang0712-commits/financial-risk-agent/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/UI-Next.js-111111?logo=next.js&logoColor=white)](https://nextjs.org/)
[![License](https://img.shields.io/badge/license-MIT-d45b3e)](LICENSE)

**An evidence-grounded financial risk platform where an LLM plans and interprets, deterministic financial tools execute, and every material conclusion must trace back to verified evidence.**

[Quick start](#quick-start) · [Architecture](#architecture) · [Research results](#research-results) · [Workbench](#analyst-workbench) · [Documentation](#documentation)

</div>

> [!IMPORTANT]
> **FinRisk is a research prototype.** The 0–100 risk index is an expert-designed heuristic. It is not a bankruptcy probability, credit rating, fraud finding, or investment recommendation.
>
> **Risk severity ≠ evidence coverage ≠ evidence quality ≠ model disagreement ≠ reliability ≠ probability.** These are separate quantities and are never collapsed into one another. Reliability is reported `UNCALIBRATED`.
>
> No production deployment, external validation, or regulatory approval is claimed. See [Limitations](research/limitations.md).

## Current release

**v0.3.3** — shared rate limiting, secret-file mounting and honest failure diagnostics on top of the v0.3.2 reproducibility and runtime-integrity base. Frozen E1/E2/E3 experiments replay read-only, and `DATABASE_URL` selects durable PostgreSQL persistence.

- [CHANGELOG](CHANGELOG.md) — complete release history
- [Reproducibility and runtime integrity](docs/reproducibility_runtime_integrity.md) — replay, persistence and trust boundaries

## Why FinRisk exists

Annual reports, 10-Ks and 20-Fs scatter material evidence across XBRL facts, statements, footnotes, MD&A, risk factors and auditor language. An analyst must reconcile periods, units and restatements; calculate metrics consistently; test management claims against the numbers; and preserve a defensible source trail.

An unconstrained LLM is the wrong financial-risk oracle. It may transpose columns, lose units, improvise arithmetic, accept optimistic narrative, or produce an unsupported conclusion. FinRisk instead treats the LLM as a **fallible semantic sensor** inside a controlled system:

| Responsibility | System owner | Invariant |
|---|---|---|
| Authoritative numbers and normalization | XBRL + deterministic code | Preserve unit, period, filing and restatement provenance |
| Ratios, trends, scenarios and model formulas | Deterministic tools | Independently reproducible and tested |
| MD&A, notes and audit-language interpretation | Schema-constrained LLM | Semantic extraction only; never final scoring |
| Risk patterns and thresholds | Versioned rules and policy | Inspectable, replayable and organization-scoped |
| Material conclusions | Failure-aware fusion + verification | No valid evidence path → `REVIEW` or `ABSTAIN` |

> **Financial arithmetic belongs to deterministic systems. Semantic interpretation belongs to a constrained LLM. Decisions belong to an auditable evidence path.**

## What you can do

- Ingest SEC Company Facts / inline XBRL and page-aware annual-report PDFs.
- Normalize values across currency, scale, period, taxonomy and restatement candidates.
- Compute liquidity, leverage, profitability, cash-flow, working-capital and trend metrics.
- Run Altman Z, Beneish M, Piotroski F and Ohlson O with explicit applicability checks.
- Evaluate 68 versioned expert rules without scattering thresholds through application code.
- Verify quotations against cited pages before admitting them as evidence.
- Fuse risk using weighted-average, max-severity, hierarchical or interaction-aware strategies.
- Replay an assessment from frozen inputs and versions, then show any output drift.
- Gate automation on evidence coverage, calibrated reliability and disagreement.

## Quick start

Prerequisites: Python >=3.11 (release gate tests 3.11 and 3.12), Node.js 22+, npm 10+, Docker Desktop (optional).

### Backend

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn finrisk.api:app --reload
```

API documentation is available at `http://localhost:8000/docs`; health is at `http://localhost:8000/health`.

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

Open `http://localhost:3000`.

### Docker Compose

```bash
docker compose up --build
```

The development compose file uses an explicitly development-only database password. For the production overlay, provide a non-default secret; migrations run as a one-shot service before the API starts:

```bash
POSTGRES_PASSWORD='<strong-secret>' docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build
```

`POSTGRES_PASSWORD` is only applied when the PostgreSQL volume is **first** initialised.
Changing it afterwards does not change the password stored in the existing volume, so
the containers stop authenticating. The PostgreSQL healthcheck authenticates over TCP,
so this shows up as `unhealthy` (not as a healthy database plus a crashing API).
The probe deliberately connects to the container's own address on the
Compose network rather than to `127.0.0.1`: the image ships
`host all all 127.0.0.1/32 trust` *above* the `scram-sha-256` rule it appends, so a
loopback probe succeeds with any password, including a wrong one.

How the mismatch surfaces depends on when the API has to open a **new** connection:

- **New connection by a running API.** `/health/ready` answers `503` naming the
  rejected credential while `/health/live` stays `200`. Rotating the password inside
  a live database is *not* immediately visible, though: PostgreSQL does not terminate
  established sessions, so an API holding pooled connections keeps answering `200`
  until those sessions break — a server restart, a pool grow, or a lifetime expiry.
  Do not read a `200` right after an `ALTER USER` as proof that the rotation was safe.
- **Start-up with a mismatched password.** The API does not reach request handling at
  all: it builds its connection pool while the app module is imported, and that pool
  readiness wait gives up after 10 s by raising `psycopg_pool.PoolTimeout` (a bare
  timeout — it does not name the credential), so the container exits and **neither
  `/health/live` nor `/health/ready` answers**. Rotate (or recreate the volume)
  *before* a cold start rather than expecting a `503` from it.
- Under Compose the API is gated on `service_healthy`, so an unhealthy database stops
  `up` before the API container is even created.

To rotate the credential, change it inside the database first:

```bash
docker compose exec postgres psql -U finrisk -d finrisk -c "ALTER USER finrisk WITH PASSWORD '<new-secret>'"
```

or recreate the volume with `down -v`, which **destroys the stored data**.

`Strict-Transport-Security` is sent only when the request actually arrives over TLS
(`https`, or an `x-forwarded-proto: https` terminator). On a plain-HTTP stack the
header is omitted rather than advertising a guarantee the deployment does not provide;
put TLS in front and it takes effect automatically.

### Run the synthetic offline demo

```powershell
$env:PYTHONPATH="backend"
python scripts/run_demo.py
```

The included company fixture is explicitly `synthetic`. It validates mechanics, not real-world performance.

### Reproducing the research

Replay the frozen E1/E2/E3 experiments (read-only; verifies manifest and artifact bytes without regenerating anything):

```bash
python scripts/replay_frozen_experiment.py v0.3.1-E1-diagnostic
python scripts/replay_frozen_experiment.py v0.3.1-E2
python scripts/replay_frozen_experiment.py v0.3.1-E3
```

Replay the public pilot into `research/results/v0.3.1/public_pilot_replay`:

```powershell
$env:PYTHONPATH="backend"
python scripts/run_public_benchmark.py
```

The checked-in `research/results/public_v1` directory is the immutable v0.3.0 snapshot; the runner refuses to use it as an output directory.

Run the empirical validation gate (exits non-zero when corpus integrity fails):

```bash
python scripts/prepare_empirical_foundation.py
python scripts/run_empirical_validation.py
```

Rebuilding SEC snapshots requires an identifying User-Agent, and importing official bulk data expects the ZIP in `data/sec-bulk`:

```powershell
$env:SEC_USER_AGENT="FinRisk-Agent your-email@example.com"
python scripts/build_public_benchmark.py
```

```bash
python scripts/import_sec_bulk.py
SEC_USER_AGENT="Researcher Name researcher@example.edu" python scripts/acquire_empirical_corpus.py
```

SEC acquisition has three explicit routes: official `companyfacts.zip` or Financial Statement Data Set ZIPs, a local/offline cache, and the rate-limited live API fallback. Raw bulk files are intentionally Git-ignored.

A previously recorded live Company Facts rebuild received HTTP 403. That is preserved as a real failure, not replaced with synthetic "live" data. Full methodology lives in the [dataset card](research/dataset_card.md) and [evaluation protocol](research/evaluation_protocol.md).

## Documentation

| Topic | Document |
|---|---|
| Architecture and enterprise boundary | [Enterprise platform](docs/enterprise_platform.md) |
| Decision trace, replay, governance and threat model | [Decision-grade controls](docs/decision_grade_controls.md) |
| Reproducibility, replay and deployment maturity | [Reproducibility and runtime integrity](docs/reproducibility_runtime_integrity.md) |
| Three-layer migration | [Migration map](docs/three_layer_migration.md) |
| Temporal risk design | [Temporal risk intelligence](docs/temporal_risk_intelligence.md) |
| Risk Case lifecycle | [Enterprise workflow](docs/risk_case_workflow.md) |
| Capability truth table | [Capability maturity matrix](docs/capability_maturity_matrix.md) |
| Flagship real-data walkthrough | [Case Study 001 — Intel FY2024](docs/case_study_001.md) |
| Release history | [CHANGELOG](CHANGELOG.md) |
| Implemented / partial / not-implemented inventory | [PROJECT_STATUS](PROJECT_STATUS.md) |
| Dataset and label provenance | [Dataset card](research/dataset_card.md) |
| Evaluation design | [Evaluation protocol](research/evaluation_protocol.md) |
| Results and negative findings | [Results](research/results.md) |
| Error analysis | [Error analysis](research/error_analysis.md) |
| Research limitations | [Limitations](research/limitations.md) |
| Human–AI study | [Study protocol](research/human_ai_study_protocol.md) |

## Architecture

<img src="docs/assets/decision-architecture.svg" alt="FinRisk three-layer decision architecture" width="100%" />

The three layers enforce a strict dependency boundary:

1. **Interface Layer** — FastAPI and the Next.js Workbench present data, workflow and proof. They do not calculate financial risk.
2. **Agent Reasoning Layer** — the planner and orchestrator select typed tools, assess sufficiency, cross-check signals, verify claims, reflect, and synthesize or abstain.
3. **Tool / Code Layer** — ingestion, normalization, metrics, models, rules, evidence, contradiction detection, fusion and replay execute deterministically.

```text
User
  ↓
Interface ── Portfolio · Entity · Risk Case · Scenario · Governance · Audit
  ↓
Agent ───── Understand → Plan → Collect → Execute → Cross-check → Verify → Reflect
  ↓                                      ↓
Tools ───── XBRL/PDF · Metrics · Models · Rules · Evidence · Fusion · Replay
  ↓
Verified evidence graph → PASS / FLAG / REVIEW / ABSTAIN
```

Only structured execution metadata is retained: plan step, tool name, status, result summary, evidence references, rationale and confidence. Hidden chain-of-thought is neither stored nor displayed.

### Agent tool registry

| Tool family | Capabilities |
|---|---|
| Ingestion | PDF extraction, XBRL normalization, period and unit reconciliation |
| Financial | ratios, trends, period comparison, missing-data detection, scenarios |
| Models | Altman, Beneish, Piotroski, Ohlson, applicability checks |
| Rules | versioned single-factor and cross-factor risk signals |
| Evidence | retrieval, quote verification, provenance graph construction |
| Consistency | narrative–numeric support, tension and contradiction classification |
| Decision | signal calculation, policy resolution, fusion, snapshot and replay |
| Temporal | entity risk state, evidence delta, attribution and filing timeline |
| Governance | applicability, selective automation, critic/verifier and DecisionBundle |

Unknown tools, malformed arguments and missing required inputs fail closed.

## Evidence is the product

<img src="docs/assets/decision-trace-v2.svg" alt="Auditable FinRisk decision trace" width="100%" />

```text
document → page/section/span → extracted fact or claim → metric/rule/model
         → fusion contribution → risk dimension → final decision
```

A decision trace records reason code, document hash, accession, source page or XBRL concept, rule/model/prompt/fusion versions, confidence, coverage, disagreement and contribution. Evidence states remain explicit:

- `UNVERIFIED` — proposed but not confirmed at the cited location.
- `LOCATED` — extracted from a source location but not reconciled.
- `VERIFIED` — matched to the cited report evidence.
- `REJECTED` — verification failed; the claim cannot influence the result.

Conflicting top-ranked facts are not silently selected. Missing values are never replaced with zero. Broken paths trigger review or abstention.

### Deterministic replay

Each analysis can freeze its inputs into an immutable snapshot: input hash, document version, policy and rule versions, prompt/model version, fusion strategy, configuration and timestamp.

Replay creates a separate result and diff; it never overwrites the historical decision. That makes four audit questions answerable. Was the source document different? Did a threshold, model, prompt or fusion strategy change? Is the result byte-for-byte reproducible? Which decision path changed, and why?

See [Decision-grade controls](docs/decision_grade_controls.md).

### Risk is an evolving state

FinRisk models a filing as an update from `R(t-1)` to `R(t)`, not an isolated score. `RiskDelta` separates dimension, metric and evidence changes, and attaches each attribution driver to evidence-path identifiers. The temporal graph adds `SUPPORTS`, `CONTRADICTS`, `SUPERSEDES`, `DERIVED_FROM`, `CONFIRMS`, `WEAKENS` and `INVALIDATES` relationships.

This capability is code-complete and fixture-tested, and it is exercised through the enterprise snapshot/timeline API and the E3 numeric trajectories. The Agent's own `risk_trajectory` field is derived from the current run only: the single-process local path does not persist history, so it reports `insufficient_history` unless a snapshot store supplies prior periods. Real multi-period attribution quality remains **NOT VALIDATED**.

## Analyst Workbench

<img src="docs/assets/dashboard-running.png" alt="FinRisk analyst workbench running locally" width="100%" />

The Workbench follows the analyst's path rather than a chat metaphor:

```text
Portfolio → Entity → Risk Case → Risk Drivers → Evidence
          → Scenario → Governance → Audit
```

It keeps severity, trajectory, evidence coverage, decision confidence and model disagreement visually separate. Risk findings can become owned cases with reviewer status, due dates, actions, comments and an audited human override.

When the API upstream is unreachable, the Workbench falls back to a bundled sample and labels its origin on screen. That sample is a real pipeline output for the repository's synthetic fixture, not a hand-written mock-up, so a review never opens on an empty shell.

> The screenshot is from the local prototype. It is not evidence of a hosted production deployment.

## Research results

The checked-in public pilot runs five baselines on **three company-disjoint FY2024 observations**: Apple, Microsoft and Intel. It is intentionally too small for inferential claims, but it is reproducible and preserves a valuable negative result.

<img src="research/results/public_v1/baseline-risk-f1.svg" alt="Executed n=3 pilot baseline F1 results" width="760" />

| Baseline | Decision coverage | Risk F1 | Balanced accuracy |
|---|---:|---:|---:|
| LLM Only¹ | 3/3 | 0.000 | 0.500 |
| Ratios Only | 3/3 | **1.000** | **1.000** |
| Rule Engine | 3/3 | 0.667 | 0.750 |
| Traditional Models | 3/3 | 0.500 | 0.500 |
| Full Hybrid² | 2/3 | 0.000 | 0.500 |

¹ The recorded pilot used the deterministic offline semantic provider. A paid LLM baseline was **NOT RUN** because no API credential was supplied.

² This row scores the expert-weighted aggregate over risk dimensions (`scoring.aggregate`); the Agent decision path uses hierarchical escalation instead, so the row does not describe the strategy the product decides with.

**Full Hybrid did not outperform Ratios Only.** This is a negative, underpowered result. It is not evidence of predictive superiority or probability calibration, and most bootstrap intervals span `[0, 1]`.

The separate v0.3.1 numeric corpus (90 observations, 30 companies) yields six labelled test observations from five held-out companies, with one positive endpoint. Every baseline missed that positive case (AUROC 0.100–0.200, FNR 1.0), so the confidence interval is deliberately reported as `CI_NOT_ESTIMABLE`.

Full detail, ablations, robustness checks and RQ-by-RQ status live in [Results](research/results.md) and [Error analysis](research/error_analysis.md).

### Research questions

- **RQ1 — Grounding:** Does hybrid reasoning reduce unsupported claims relative to semantic-only analysis?
- **RQ2 — Consistency:** Do cross-modal checks improve narrative–numeric contradiction detection?
- **RQ3 — Classification:** Does Full Hybrid improve company-level risk classification under company-disjoint evaluation?
- **RQ4 — Robustness:** How sensitive are decisions to narrative, rules, models, trends, missing evidence and perturbations?

Current evidence is diagnostic only: RQ3 is not supported by the pilot, RQ2 has one true positive and one false positive, and RQ1 still requires a real-provider run.

## Project maturity

| Status | What it means here |
|---|---|
| **VALIDATED — limited local scope** | Automated tests and ≥90% coverage gate; Ruff, TypeScript and production frontend build; deterministic finance fixtures; 90-observation SEC numeric ingestion and PIT integrity; corrected B0/B1/B2/B6 execution |
| **IMPLEMENTED, NOT EXTERNALLY VALIDATED** | XBRL/PDF reconciliation, temporal state/attribution, applicability routing, selective automation, constrained provider, critic/verifier, DecisionBundle, risk-case mitigation workflow, RBAC/API keys, PostgreSQL migrations and Workbench |
| **PLANNED / NOT RUN** | Human-adjudicated document/evidence benchmark, paid-LLM evaluation, calibrated risk model, production identity/object storage/worker/telemetry deployment |

## API surface

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/assess` | Assess normalized current/prior financial data and optional page text |
| `POST /api/v1/documents/analyze` | Validate and analyze a PDF upload |
| `POST /api/v1/xbrl/normalize` | Normalize SEC Company Facts with provenance |
| `/api/v1/enterprise/*` | Tenant-scoped entities, cases, scenarios, policies, governance and audit |

PDF uploads validate magic bytes and configurable limits (`FINRISK_MAX_UPLOAD_MB`, `FINRISK_MAX_PDF_PAGES`, `FINRISK_MAX_EXTRACTED_CHARS`, `FINRISK_ANALYSIS_TIMEOUT_SECONDS`). Opening, page counting and page-text scanning run in Starlette's bounded worker pool rather than the async event loop.

Invalid, encrypted, oversized or timed-out inputs fail closed, and temporary files are
removed. Production-mode analysis runs in a killable subprocess so a timeout stops the
expensive pipeline. Internet-facing deployment still needs production identity, malware
scanning, a distributed worker system for scale and operational validation.

The default narrative provider is deterministic and offline. To enable the schema-constrained real provider, copy `.env.example`, set `FINRISK_LLM_PROVIDER=openai`, configure `OPENAI_API_KEY`, and pin model pricing if cost estimates are needed. Tests never require a live API.

## Financial reasoning

Liquidity, leverage, debt service, profitability, cash flow, working capital and multi-period growth are calculated from normalized inputs. Where prior-year values exist, balance-based return and working-capital metrics use average balances; single-period proxies are labelled.

| Model | Output | Guardrail |
|---|---|---|
| Altman Z | distress screening zone | public-manufacturer applicability checks |
| Beneish M | manipulation-risk screening signal | never presented as fraud proof |
| Piotroski-style F-Score proxy | nine-signal financial-strength proxy | limited, non-canonical implementation; original value-stock context disclosed |
| Ohlson O | O-score and separately derived logistic probability | input-domain and unit warnings |

Model mappings are configured in [config/model_scoring.json](config/model_scoring.json).

[rules/rules.json](rules/rules.json) contains 68 versioned definitions covering
single-factor and cross-factor patterns. Runtime enables 43 with real producers; the 25
legacy definitions lacking legitimate producers are explicitly disabled with reasons in
[rules/disabled_rules.json](rules/disabled_rules.json). Startup and CI reject any other
unproducible condition. Correlated rules carry family metadata so scoring and proof
coverage both retain only the strongest applicable family signal.

Missing evidence, low coverage, conflicting evidence, stale data, parser failure, unavailable LLMs, applicability failures and rule/model disagreement are all first-class states. Depending on pinned policy, they reduce evidence sufficiency, increase review requirements, or force abstention. They never produce fabricated certainty.

The incident-style [Failure Lab](failure_lab/README.md) maps each injected failure to its impact, expected fail-closed response and regression test.

## Repository map

```text
financial-risk-agent/
├── backend/finrisk/       # domain, tools, agent, services and REST API
├── frontend/              # Next.js analyst Workbench
├── config/                # scoring, model and policy configuration
├── rules/                 # 68 versioned expert rules
├── tests/                 # unit, security, replay and integration tests
├── research/              # protocol, frozen pilot, ablations and errors
├── docs/                  # architecture, controls, threat model and assets
├── examples/              # explicitly synthetic fixtures and sample report
├── scripts/               # demo, benchmark and data-build entry points
├── portfolio/             # technical narrative and interview materials
├── docker-compose.yml
└── PROJECT_STATUS.md
```

## Verification

```bash
# With DATABASE_URL set, apply the migrations first: the suite assumes the schema
# already exists and does not create it. On a fresh database `rate_limit_events` is
# missing, the limiter fails closed and every authenticated route answers 503.
python scripts/validate_postgres_migration.py
pytest --cov=finrisk --cov-report=term-missing --cov-fail-under=90
ruff check backend tests scripts
```

```bash
cd frontend
npm audit --omit=dev --audit-level=high --registry=https://registry.npmjs.org
npm test
npm run typecheck
npm run build
```

The release gate covers Python 3.11 and 3.12 with a 90% minimum coverage threshold, Ruff, frontend semantic tests, a CI-enforced official-registry production dependency audit, TypeScript, the Next.js production build, prospective provenance validation and read-only E1/E2/E3 replay.

## Security and governance

- Organization-scoped repositories and service checks enforce tenant boundaries.
- Enterprise API credentials are hashed server-side; caller-supplied role headers are not trusted.
- Human overrides retain original decision, new decision, actor, reason and timestamp.
- Model, prompt, rule, fusion and policy versions are recorded for formal runs.
- Credentials, `.env`, private reports, uploads, caches, generated assessments and local builds are ignored.

These are implemented controls in a prototype, not certification claims. Review the [threat model and readiness boundary](docs/decision_grade_controls.md) before any deployment.

## Limitations

The public pilot covers three company-year observations with single-reviewer labels. The E3 numeric corpus covers 90 observations across 30 companies. Neither establishes predictive superiority, and no paid-provider LLM benchmark has been run.

Rules, weights, fusion thresholds and evidence-coverage confidence are not externally calibrated. Component telemetry records observed deltas, not causal attribution. PostgreSQL, Docker, identity, object storage, worker and telemetry configurations have not been validated in a production environment.

The complete list — including right-censoring, machine-review boundaries and model population limits — is in [research/limitations.md](research/limitations.md). For a precise implemented/partial/not-implemented inventory, see [PROJECT_STATUS.md](PROJECT_STATUS.md).

## Contributing

Contributions are welcome. Financial formula changes require edge-case tests and a primary-source rationale. New rules require a stable ID, category, severity, explicit conditions, bounded effect and duplication review. Synthetic fixtures must be labelled `synthetic`.

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

## License

Released under the [MIT License](LICENSE).

---

<div align="center">

**Evidence first. Failure aware. Reproducible by design.**

<sub>FinRisk studies what financial AI should automate, what it must verify, and what must remain a human decision.</sub>

</div>
