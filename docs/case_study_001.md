# FinRisk Case Study 001 — From Filing to Decision

## Scope and evidence status

Company: Intel Corporation · Fiscal year: 2024 · Filing: 10-K  
Dataset: `finrisk-sec-mini-v1` frozen public pilot  
Status: **single-reviewer case study; not an externally validated risk opinion**

Source filing metadata and the frozen facts are stored in `research/benchmark/public_company_observations.json`. This case does not claim that the current environment re-downloaded the filing: the recorded SEC rebuild failed with HTTP 403.

## Filing → facts

Selected frozen values, in USD millions:

| Fact | FY2024 | FY2023 | Provenance |
|---|---:|---:|---|
| Revenue | 53,101 | 54,228 | SEC filing manifest |
| Operating income | -11,678 | 93 | SEC filing manifest |
| Net income | -19,233 | 1,675 | SEC filing manifest |
| Operating cash flow | 8,288 | 11,471 | SEC filing manifest |
| Capital expenditure | 23,944 | 25,750 | SEC filing manifest |
| Total debt | 50,011 | 49,266 | SEC filing manifest |

## Facts → deterministic metrics

- Operating margin: `-21.99%`
- Net margin: `-36.22%`
- Operating cash-flow growth: `-27.75%`
- Free cash flow: `-15,656`
- FCF margin: `-29.48%`
- Current ratio: `1.327`

The formulas and full inputs are preserved in `score_decomposition.json`; no LLM performs these calculations.

## Metrics → rules and model applicability

Profitability and cash-flow rules triggered, including `PRO_001`, `PRO_004`, `PRO_006`, `PRO_008`, `CFL_002`, `CFL_004` and `CFL_007`. Traditional models returned missing-component disclosures rather than invented values. The independent Applicability Router now adds `APPLICABLE / LIMITED / NOT_APPLICABLE` decisions based on population assumptions and evidence availability.

## Narrative → verified tension

The pilot contains management language stating that funding sources were believed sufficient. The consistency engine opposed that claim with declining operating cash flow and increased short-term debt and classified a liquidity tension. This is a numerical–narrative signal, not an allegation of deception.

## Fusion → decision and failure analysis

The Full Hybrid pilot probability was `0.427`, producing a negative risk prediction against the single-reviewer positive label. This is a false negative and a central adverse result: the system's dimension aggregation diluted severe profitability and cash-flow deterioration. The released pilot reports Full Hybrid risk F1 `0.000`; no threshold was retuned to make the case pass.

The current decision-grade layer would preserve the evidence paths, surface disagreement and allow policy to return `REVIEW` or `ABSTAIN`. That behavior is implemented and fixture-tested, but it has not been retrospectively rerun as a new published benchmark result.

## Temporal extension

The code can now represent FY2023 as `R(t-1)` and FY2024 as `R(t)`, emitting metric/dimension/evidence deltas and traceable risk-change attribution. Because the public pilot does not contain independently assessed FY2023 risk state labels, no empirical temporal attribution score is claimed.

## Human workflow and replay

A supported finding may become a Risk Case with owner, due date and mitigation action. Resolution requires verified decision paths and resolution evidence; a later filing can reopen the case with a mandatory reason. The immutable DecisionBundle stores document/input/output hashes, calculations, trace, component versions, review and final decision for replay.

## What this case demonstrates

It demonstrates a reproducible failure analysis and the software path from filing evidence to a governed decision. It does **not** demonstrate predictive superiority, calibrated probability, production readiness or an externally validated Intel risk opinion.
