# Final Project Status

Status date: 2026-09-05. This is an honest research-prototype status, not a production or performance claim.

## Fully Implemented

- Existing deterministic metrics, four traditional models, 68-rule engine, eight dimensions, evidence graph, confidence decomposition, FastAPI, Next.js and PDF/text reporting remain intact.
- SEC Company Facts XBRL normalization for US GAAP/IFRS aliases with fiscal year, unit, taxonomy, concept, accession, filed date, period, restatement and source URL provenance.
- Cross-source reconciliation with tolerance, explicit match/conflict/single-source states and XBRL authority—never silent averaging.
- Real OpenAI-compatible narrative provider with strict JSON Schema plus Pydantic validation, bounded retry, prompt version, injectable offline transport, token/cost/latency/status JSONL logging and environment selection. The LLM cannot compute financial outputs or scores.
- Multi-dimensional narrative–numeric consistency checks for liquidity, solvency, profitability, cash flow, earnings quality and going concern, with traceable metric/value conflicts.
- Frozen three-company public pilot, company-disjoint splits, five baselines, five ablations, deterministic CSV/JSON/SVG output and 2,000-sample seeded company bootstrap intervals.
- Real local dashboard screenshot and Intel 2024 sample text/PDF assessment.

## Partially Implemented

- SEC ingestion: normalization/reconciliation and rebuild client exist, but the live Company Facts endpoint returned HTTP 403 in this environment. Inline filing HTML and annual-report PDF remain separate inputs rather than a fully automated filing bundle downloader.
- Public benchmark: actually executed, but only three technology companies and one single-reviewer label. It is useful for pipeline/error discovery, not inference.
- LLM integration: production adapter is implemented and mock-tested; no paid API run was performed because no key was supplied.
- Confidence remains an uncalibrated evidence-coverage score. ECE is computed for baseline risk probabilities, not used to retrofit confidence.

## Not Implemented

- Independently double-annotated, adjudicated, sector-diverse benchmark large enough for a confirmatory hypothesis test.
- Empirical XBRL extraction accuracy on a frozen independently labelled gold set.
- Production OCR, filing bundle orchestration, database/storage, authentication, worker queue, malware scanning and deployment hardening.
- Calibrated probability of default. The heuristic score is explicitly not a bankruptcy probability.

## Tests Passed

- 43 Python tests passed.
- Total line coverage: 91.06%; CI threshold remains 90%.
- Public pilot and ablation artifacts regenerated successfully.
- Previous Ruff, TypeScript and Next.js build checks remain CI-defined; final local QA should be read with the current command logs.

## Experiments Completed

- `finrisk-sec-mini-v1`: Apple/Microsoft/Intel FY2024, company-disjoint train/validation/test.
- Five baselines and five ablations run on frozen observations.
- Full Hybrid: risk F1 0.000, contradiction F1 0.667, decision coverage 2/3, covered accuracy 0.500 [0,1], ECE 0.407.
- Ratios Only: risk F1 1.000 on n=3. This is not evidence of superiority; the sample is too small.
- Detailed results: `research/results/public_v1`; failures: `research/error_analysis.md`.
- A 30-company cross-sector candidate registry is pre-registered but all rows remain `pending_sec_download` and are excluded from results.

## Experiments Pending

- Repeat SEC acquisition from a permitted network and measure non-circular extraction accuracy.
- Run the real LLM baseline with a frozen model/prompt/pricing configuration.
- Double annotation, adjudication, more companies/sectors and a locked confirmatory test.

## How to Run

```powershell
python -m pip install -e ".[dev]"
$env:PYTHONPATH="backend"
python scripts/run_public_benchmark.py
python scripts/generate_public_sample.py
pytest --cov=finrisk --cov-fail-under=90
```

Set `FINRISK_LLM_PROVIDER=openai` and `OPENAI_API_KEY` only when intentionally running a paid provider. Set explicit per-million-token costs because price defaults are zero.

## Best Demo Workflow

Start with the README result table, reproduce it, open Intel's evidence-linked sample report, then show why Full Hybrid missed the labelled risk case and why Apple generated a contradiction false positive. This makes the strongest research story: transparent failure is more credible than a polished but unvalidated score.

## Main Technical Contribution

A provenance-preserving boundary between authoritative structured financial facts, deterministic computation, fallible semantic extraction, evidence admission and cross-modal consistency—plus a runnable evaluation harness that exposes rather than hides failure.

## Main Research Insight

The first public pilot does not prove the hypothesis. It shows that an LLM can be constrained as a semantic sensor, while the remaining scientific difficulty lies in annotation quality, context-aware consistency, applicability and score aggregation. Auditable failure boundaries are the prerequisite for a credible larger study.
