# Final Project Status

Status date: 2026-09-05. This is an honest V1 engineering status; it does not claim benchmark performance.

## Fully Implemented

- Domain records for source-aware financial values, metrics, model results, rules, narrative claims, contradictions, and assessments.
- Deterministic liquidity, leverage, debt-service, profitability, cash-flow, working-capital, and multi-year growth calculations with explicit missing-data behavior.
- Altman Z-Score, Beneish M-Score, Piotroski F-Score, and Ohlson O-Score formulas with input breakdowns, missing components, interpretations, and applicability guardrails.
- Independent JSON rule engine with 68 unique expert-designed risk rules and cross-indicator conditions.
- Eight bounded risk dimensions, configuration-driven weights, overall score/level, separate confidence, and non-probability disclaimer.
- Page-aware native PDF text parsing, section detection, conservative value candidates, structured offline narrative provider, quote verifier, and liquidity contradiction detection.
- FastAPI health/assessment endpoints, text/PDF reporting, responsive Next.js dashboard shell, Dockerfiles, compose file, synthetic demo, security exclusions, research design, and portfolio narrative.
- Reproducible synthetic end-to-end path: parsing/structured inputs → metrics → models → rules → evidence verification → contradiction → assessment → report.

## Partially Implemented

- Financial extraction handles conservative single-line candidates, aliases, scale, currency metadata, negatives, and page provenance; complex tables, automatic multi-column year alignment, restatement reconciliation, and XBRL cross-checking need production expansion.
- OCR is designed as an explicit fallback but no OCR adapter is bundled yet.
- Narrative analysis has a strict provider interface and deterministic mock. A real LLM provider, schema retries, prompt versioning, and cost controls remain to be added when credentials are intentionally configured.
- Contradiction detection implements the flagship liquidity pattern; a broader claim ontology and all-category contradiction library remain future work.
- The frontend calls the multipart PDF analysis endpoint and renders returned dimensions and rule sources. A full PDF page viewer and manual extraction-review editor remain pending.
- PDF export works and includes all assessment sections, but visual branding, tables, charts, hyperlinks, and source-page thumbnails are basic.
- Confidence has a fixed-field component breakdown and is explicitly an uncalibrated coverage score.

## Not Implemented

- Production OCR, SEC/XBRL ingestion, database/object storage, user authentication, job queue, antivirus sandbox, rate limiting, cloud deployment, and real LLM API integration.
- Bank/insurance-specific models and sector-calibrated rules.
- A licensed, adjudicated real-company benchmark or trained/calibrated scoring model.
- Production release automation and CI/CD; the repository itself is now published on GitHub.

## Tests Passed

- `28 passed` on Python 3.12.10; line coverage: `93%`, above the 90% CI threshold.
- Static analysis: Ruff, all checks passed.
- Next.js 15 production build: passed (static route generated).
- Synthetic pipeline CLI: passed; emitted eight dimensions, model missing reasons, triggered rules, verified contradiction, confidence, and disclaimer.
- PDF export smoke test: passed; generated `reports/generated/synthetic_assessment.pdf` (ignored by Git).

## Known Limitations

See `research/limitations.md`. The principal risks are complex PDF table extraction, sector applicability, correlated rule double-counting, English-first narrative patterns, and uncalibrated heuristic weights. Verified provenance demonstrates that text exists on a page; it does not prove the statement is true or complete.

## Experiments Completed

- Synthetic regression and end-to-end engineering validation only. Synthetic output is not evidence of real-world model quality.

## Experiments Pending

- Build and double-annotate a licensed company-disjoint corpus.
- Run LLM Only, Ratios Only, Rule Engine Only, Traditional Models, and Full Hybrid under frozen inputs.
- Report extraction accuracy, evidence precision, unsupported-claim/hallucination rates, contradiction precision/recall/F1, valid-label classification metrics, calibration, sector slices, bootstrap intervals, ablations, and error analysis.

## How to Run

1. Install: `python -m pip install -e ".[dev]"`.
2. Test: `pytest`.
3. Demo: set `PYTHONPATH=backend`, then run `python scripts/run_demo.py`.
4. API: `uvicorn finrisk.api:app --reload`.
5. UI: in `frontend`, run `npm install` and `npm run dev`.
6. Containers: `docker compose up --build`.

## Best Demo Workflow

Use the explicitly synthetic Northstar fixture. Show deteriorating cash, CFO, short-term debt, and current ratio; trace `LIQ_007`; inspect the verified optimistic management quote and contradiction; remove interest expense to demonstrate N/A and lower certainty; then export the assessment. Do not present the illustrative score as a real company result.

## Main Technical Contribution

A provenance-preserving hybrid reasoning pipeline that assigns arithmetic and scoring to deterministic code, qualitative extraction to a constrained semantic provider, admission to an evidence verifier, interactions to a versioned rule engine, and uncertainty to a separate confidence function.

## Main Research Insight

An LLM should be treated as a fallible semantic sensor rather than a financial-risk oracle. Separating extraction, calculation, verification, rules, aggregation, and confidence creates inspectable failure boundaries and makes the central reliability hypothesis empirically testable.

## Six-Angle QA

- **Software architecture:** modules have single responsibilities; configuration is external; offline provider keeps tests deterministic.
- **Financial correctness:** safe division, signs, model components, applicability, and missing values are explicit and tested. More sector-specific validation is pending.
- **LLM reliability:** the LLM cannot calculate scores; unverified claims are rejected; fraud language is prohibited.
- **Evidence grounding:** textual evidence is page-verified; derived evidence records formulas/inputs. Production table provenance still needs richer bounding boxes.
- **Research methodology:** baselines, splits, metrics, ablations, calibration, and error taxonomy are pre-specified; no results are fabricated.
- **Interview defensibility:** design trade-offs and limitations are documented in `portfolio/technical_deep_dive.md` and `portfolio/interview_questions.md`.
