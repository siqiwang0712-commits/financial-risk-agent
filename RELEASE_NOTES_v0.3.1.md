# v0.3.1 — Decision Integrity & Research Readiness

v0.3.1 hardens correctness and establishes a reproducible numeric empirical foundation. It does **not** establish real-world predictive superiority, probability-of-default calibration, or full document/LLM validation.

## Highlights

- Coverage-aware, non-compensatory fusion; missing dimensions are unknown, not safe.
- Claim-conditioned evidence verification and explicit incomplete-context outcomes.
- Separate risk, coverage, evidence quality, disagreement, reliability maturity and probability semantics.
- Replayable component telemetry and decision-integrity regression invariants.
- A frozen 30-company × 3-year SEC FSDS corpus with company-disjoint 18/6/6 splits.
- Label-only outcome pool with strict `feature <= cutoff < outcome` separation.
- Immutable E1, E2 and final E3 experiment snapshots plus deterministic replay.

## E3 empirical result

- Numeric observations: 90/90; PIT PASS; company overlap 0; detected future leakage 0.
- Labels: 42 verified (34 negative, 8 positive), 6 review-required, 17 true no-eligible-outcome, 25 right-censored.
- Frozen test: 6 usable observations, 1 positive.
- AUROC: B0 0.100, B1 0.200, B2 0.100, B6 0.100.
- Recall: 0 for all four baselines; FNR: 1.0.
- Bootstrap: 691 valid, 309 single-class invalid; `CI_NOT_ESTIMABLE / INSUFFICIENT_POWER`.
- Conclusion: `SUPERIORITY NOT ESTABLISHED`.

## Validation boundaries

Extraction reports 1,164/1,165 comparable-field **machine reconciliation agreement** (99.914%), not human accuracy; 456 fields remain manual-review-required and zero are human-verified references. Neutral machine Reviewers A/B agreed on 90/90 normalized outcomes, but this is not human gold. Document/NNT/paid-LLM empirical validation remains not run. Official SEC 2025 bulk downloads were blocked with HTTP 403, leaving 25 right-censored observations.

## Reproduce

Place the official SEC 2021Q1–2024Q4 FSDS ZIPs in `data/sec-bulk/`, then run:

```powershell
$env:PYTHONPATH="backend"
python scripts/import_sec_bulk.py
python scripts/run_empirical_validation.py
python scripts/run_numeric_benchmarks.py
```

Raw SEC ZIPs stay Git-ignored. E3 is content-addressed under `research/results/v0.3.1/benchmark_forensics/v0.3.1-E3`.
