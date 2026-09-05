# Three-layer migration map

This refactor preserves the deterministic engine and adds an explicit orchestration boundary.

| Previous module | Three-layer role | Migration |
|---|---|---|
| `frontend/app/page.tsx` | Interface | Renders assessment, public Agent trace and evidence paths; performs no finance |
| `api.py` | Interface adapter | Validates transport inputs and invokes `FinancialRiskAgent` |
| `pipeline.py` | Tool/service compatibility facade | Preserved for benchmarks and deterministic assessment assembly |
| `parser.py`, `xbrl.py` | Tool layer / ingestion | Exposed as `pdf_extraction` and `xbrl_extraction` |
| `metrics.py` | Tool layer / financial | Exposed as `financial_metrics` |
| `models.py` | Tool layer / models | Exposed as `traditional_models` and `model_applicability` |
| `rules.py`, `scoring.py` | Tool layer / rules | Exposed as rule and risk-signal tools |
| `llm.py`, `evidence.py` | Semantic sensor + evidence gate | Coordinated by Agent; rejected quotes never enter assessment |
| `contradictions.py` | Tool layer / verification | Exposed as `contradiction_detection` |

The Agent records plan steps, tool names, statuses, summaries, admitted evidence, reflection notes and terminal decisions. It does not store hidden chain-of-thought.

Terminal outcomes are `COMPLETED`, `INSUFFICIENT_EVIDENCE`, `REVIEW_REQUIRED`, and `FAILED`.
