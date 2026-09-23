# Three-layer migration map

This refactor preserves the deterministic engine and adds an explicit orchestration boundary.

| Previous module | Three-layer role | Migration |
|---|---|---|
| `frontend/app/page.tsx` | Interface | State and tab routing only; performs no finance |
| `frontend/components/*.tsx` | Interface | Renders assessment, public Agent trace and evidence paths; performs no finance |
| `frontend/lib/api.ts` | Interface data access | Reads through the `/api/v1` proxy and falls back to the bundled sample only when the upstream is unreachable |
| `frontend/lib/proxy.mjs` | Interface transport policy | Owns upstream/path/limit/header selection; the Next route only streams bounded requests and maps responses |
| `api.py` | Interface adapter | Owns FastAPI models/routes and delegates runtime assembly, process isolation and frozen-data projection |
| `runtime.py` | Runtime composition | Selects memory/PostgreSQL dependencies and parses document limits without importing the HTTP layer |
| `process_isolation.py` | Expensive-work boundary | Owns spawned worker timeout, termination, join and queue cleanup for PDF inspection and analysis |
| `public_pilot.py` | Frozen read model | Validates and caches the immutable public-pilot projection once per process |
| `enterprise/schemas.py` | Enterprise transport contracts | Contains request schemas and numeric-domain validation; `enterprise/api.py` contains routing and authorization |
| `pipeline.py` | Tool/service compatibility facade | Loads immutable rules/configuration once and is shared by the API, Agent and tool registry |
| `parser.py`, `xbrl.py` | Tool layer / ingestion | Exposed as `pdf_extraction` and `xbrl_extraction` |
| `metrics.py` | Tool layer / financial | Exposed as `financial_metrics` |
| `models.py` | Tool layer / models | Exposed as `traditional_models` and `model_applicability` |
| `rules.py`, `scoring.py` | Tool layer / rules | Exposed as rule and risk-signal tools |
| `llm.py`, `evidence.py` | Semantic sensor + evidence gate | Coordinated by Agent; rejected quotes never enter assessment |
| `contradictions.py` | Tool layer / verification | Exposed as `contradiction_detection` |
| `verification_http.py` | Deployment verification transport | Shares loopback-only origins, readiness, bounded HTTP, PDF and multipart primitives across container checks |

The Agent records plan steps, tool names, statuses, summaries, admitted evidence, reflection notes and terminal decisions. It does not store hidden chain-of-thought.

Terminal outcomes are `COMPLETED`, `INSUFFICIENT_EVIDENCE`, `REVIEW_REQUIRED`, and `FAILED`.
