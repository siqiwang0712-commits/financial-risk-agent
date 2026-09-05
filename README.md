# FinRisk-Agent

**An Evidence-Grounded Hybrid Agent for Explainable Corporate Financial Risk Assessment**

FinRisk-Agent turns annual reports, 10-Ks, and 20-Fs into traceable risk assessments. It combines deterministic financial calculations, established screening models, versioned expert rules, verified narrative evidence, and narrative–numeric consistency checks. Its 0–100 score is an explainable heuristic risk index—not a bankruptcy probability, credit rating, fraud finding, or investment recommendation.

## Why not LLM-only?

Language models are useful readers but unreliable financial calculators and imperfect sources of truth. They can transpose columns, lose units, accept optimistic management language, or produce plausible claims without page evidence. FinRisk therefore limits the LLM to structured qualitative extraction. Code owns arithmetic, model formulas, rule evaluation, scoring, and evidence admission. **No evidence, no claim.**

## Architecture

```text
Report → page-aware parsing → structured values → metrics and trends
       → financial models → versioned expert rules ┐
Narrative → structured claims → quote verification ├→ 8 dimensions
Claims + indicators → contradiction detection      ┘→ score + confidence
                                                     → report / API / UI
```

Every value can retain its fiscal year, statement, normalized line item, unit, currency, document, page, original text, and extraction confidence. Missing inputs remain `None`; outputs explain why they are N/A and lower confidence. Restatements are represented explicitly.

## What is implemented

- Liquidity, leverage, profitability, cash-flow, working-capital, and trend formulas with inspectable inputs and formulas.
- Altman Z, Beneish M, Piotroski F, and Ohlson O with missing-component and applicability handling.
- 68 independent JSON rules across liquidity, solvency, profitability, cash flow, earnings quality, accounting, governance/audit, refinancing, and going concern.
- Native-text PDF parser (PyMuPDF), conservative normalization, page-level evidence verifier, offline mock narrative provider, and a liquidity contradiction prototype.
- Eight-dimension aggregation using documented **expert-designed heuristic weights**, separate confidence scoring, FastAPI endpoint, PDF/text report, responsive Next.js UI, synthetic demo, and evaluation utilities.

## Local setup

Python 3.11–3.13 is recommended (the core also runs on newer Python versions).

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
uvicorn finrisk.api:app --reload
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`; API docs are at `http://localhost:8000/docs`. To run the offline synthetic demo:

```bash
set PYTHONPATH=backend
python scripts/run_demo.py
```

Or run both services with `docker compose up --build`. No API key is needed: the default provider is deterministic `mock`. `.env.example` documents optional configuration.

## API

`POST /api/v1/assess` accepts normalized data. `POST /api/v1/documents/analyze` accepts a PDF, company, and fiscal year; it validates size/type, parses page text, attaches source references, and returns a review-required assessment. The current extractor is intentionally conservative and does not yet solve complex tables, multi-column reconciliation, XBRL cross-checking, or OCR.

## Scoring and uncertainty

Rules add bounded category deltas to a transparent base score; categories without supporting signals are N/A rather than receiving automatic risk. Thresholds and [rules/rules.json](rules/rules.json) are versioned. Confidence is an **uncalibrated coverage score** based on a fixed core-field matrix, verified evidence, applicable-model coverage, and multi-year coverage; its component breakdown is returned.

## Evaluation

The research design compares LLM Only, Ratios Only, Rule Engine Only, Traditional Models, and Full Hybrid on the same company-disjoint benchmark. Planned measures include extraction accuracy, evidence precision, unsupported-claim and hallucination rates, valid-label classification metrics, contradiction precision/recall/F1, calibration, ablation, and error analysis. The repository contains evaluation code and a **synthetic** regression fixture, but does not claim real-world experimental performance. See [research/evaluation_protocol.md](research/evaluation_protocol.md).

## Security and privacy

Private reports, uploads, generated reports, credentials, caches, and build output are ignored. Do not commit confidential filings or secrets. Validate file size/type and use isolated document processing before internet-facing deployment.

## Limitations

PDF tables and OCR remain inherently noisy; model assumptions vary by sector; narrative grounding does not establish factual truth; the weights are expert heuristics rather than learned optima; and no real-world benchmark has yet been completed. See [research/limitations.md](research/limitations.md).

## Repository map

`backend/` engine/API · `frontend/` interface · `rules/` expert configuration · `config/` scoring · `tests/` unit/integration tests · `research/` evaluation design · `portfolio/` project narrative · `examples/` explicitly synthetic fixtures · `scripts/` local workflows.

## License and contribution

MIT licensed. See [CONTRIBUTING.md](CONTRIBUTING.md). The public repository is maintained at `siqiwang0712-commits/financial-risk-agent`.
