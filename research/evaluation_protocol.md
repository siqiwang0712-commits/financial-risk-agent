# Evaluation Protocol

## Pilot v1 (executed)

- Dataset: `finrisk-sec-mini-v1`, three FY2024 public technology companies.
- Sources: official SEC 10-K URLs stored per example; values are USD millions.
- Split: Apple=train, Microsoft=validation, Intel=test. No company crosses splits.
- Annotation: single-reviewer pilot, explicitly not definitive.
- Baselines: LLM Only (offline semantic provider), Ratios Only, Rule Engine, Traditional Models and Full Hybrid.
- Ablations: remove narrative, rules, models or temporal trends.
- Outputs: deterministic CSV/JSON plus SVG chart under `research/results/public_v1`.
- Uncertainty: 2,000 company-level bootstrap resamples with seed 20260905.

Reported metrics are risk precision/recall/F1, accuracy and bootstrap CI, contradiction F1, evidence coverage, evidence precision when claims exist, unsupported-claim rate and expected calibration error. Extraction accuracy is not reported in v1 because live SEC XBRL acquisition failed; treating the reviewed input values as both prediction and gold would be circular.

## Confirmatory benchmark (pending)

Create a larger versioned corpus with licensed/public reports and SEC XBRL snapshots. Double-annotate financial values, source locations, narrative claims and contradictions; adjudicate disagreements blind to system output. Freeze concept mappings, prompts, rules and thresholds before test execution. Report tolerance-based extraction accuracy, macro metrics only where valid labels exist, Brier score/ECE, coverage, latency, sector slices and company-clustered bootstrap intervals.

Synthetic fixtures remain engineering tests only and must never be mixed with empirical results.
