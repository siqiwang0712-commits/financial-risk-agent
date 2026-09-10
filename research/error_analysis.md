# Error Analysis — Public Pilot v1

The executed `finrisk-sec-mini-v1` pilot contains three FY2024 technology companies and one positive risk label. It is single-reviewer and is not a definitive benchmark.

## Observed failures

1. **Full Hybrid missed Intel.** Intel is labelled high risk in this pilot after a large net loss, negative free cash flow and profitability deterioration, but the configured aggregation returned 42.7 (Moderate). Category normalization and averaging dilute severe profitability/cash-flow signals. This is the most important current scoring error.
2. **Apple consistency false positive.** The engine flags Apple's liquidity sufficiency statement because current ratio is below 1 and short-term debt increased. The claim explicitly includes marketable securities and access to debt markets; cash-only/current-ratio checks omit that context. This demonstrates why contradiction rules need claim-conditioned variables and human review.
3. **Traditional models over-predicted risk.** Applicability limits and missing market variables make model-vote aggregation unstable on this sample.
4. **LLM-only missed the positive risk case.** The offline semantic baseline correctly avoids inventing a conclusion but cannot classify risk from language alone. No paid-provider run is claimed.
5. **Intervals are extremely wide.** Most 95% company-bootstrap accuracy intervals span 0–1. Point estimates must not be ranked as evidence of superiority.

## End-to-end decomposition

- **Apple (gold normal):** current ratio 0.867, negative working capital and 32.1% short-term-debt growth trigger liquidity rules. The optimistic liquidity quote conflicts with two numeric checks, but explicitly mentions $140.8B of cash plus marketable securities and debt-market access. The aggregate has only one covered dimension and correctly abstains after the evaluation bug fix. Contradiction prediction remains a false positive because the numeric representation omits liquid securities/context.
- **Microsoft (gold normal):** strong margins, CFO conversion and positive FCF coexist with lower cash and higher debt. Liquidity and solvency rules yield scores 28 and 20; the aggregate is 24 (Low), a true negative. Ratios Only also predicts normal.
- **Intel (gold risk):** net margin -36.2%, operating margin -22.0%, FCF -$15.7B and CFO decline 27.7% trigger seven profitability and four cash-flow rules. Profitability reaches 73 and cash flow 44, but uncovered categories plus weighted averaging produce overall 42.7, a false negative at the frozen 0.5 decision threshold. Ratios Only catches the case because two of four coarse checks are positive. Traditional models are unavailable due missing inputs.

The evaluation originally converted `overall_score=None` to probability .5 and then classified it positive. This incorrectly counted Apple's abstention as a false positive. v0.2.0 preserves `None`, reports 2/3 Hybrid decision coverage, and evaluates classification only on decisions. This is an evaluation correctness fix, not threshold tuning.

## Data acquisition failure

The SEC Company Facts endpoint returned HTTP 403 twice from the recorded environment despite an identifying User-Agent. The code preserves the failure boundary: the build script stopped, no fake response was substituted, and extraction accuracy is not reported. The checked-in pilot uses manually reviewed statement observations linked to official filing URLs. Future work should rebuild XBRL snapshots from a permitted network and independently verify them.

## Next annotation round

- At least two independent annotators, blind to system output.
- Claim spans, category, polarity, contradiction label and adjudication reason.
- Explicit context variables such as marketable securities and committed credit.
- Sector diversity and company-level resampling.
- Freeze prompts and thresholds before touching the test companies.

## v0.3.1 integrity replay

The v0.3.1 replay applies legacy fusion v1 and integrity fusion v2 to the same newly claim-conditioned evidence. It is not labelled as a reconstruction of the historical `public_v1` score. The three-company pilot produced fusion deltas of 0, +4 and 0 points. The test-company severe profitability dimension is no longer diluted by a moderate cash-flow dimension under integrity fusion.

Claim conditioning removed the Apple liquidity false positive because its statement depends on marketable securities and debt-market access that are absent from the normalized evidence. The pilot contradiction F1 consequently changed from 0.667 to 1.000, but n=3 and single-reviewer labels make this diagnostic only—not evidence of generalization or superiority.

The Full Hybrid risk-classification F1 remains 0.000 in the independently generated v0.3.1 baseline output because that baseline intentionally preserves the prior assessment-score path. The decision-integrity replay separately exercises the new enterprise fusion. This separation avoids silently changing the benchmark definition.

## Empirical benchmark error protocol

The corrected v0.3.1 run invalidated the earlier apparent B1 advantage after two general correctness fixes: dimensional `segments` facts are now excluded from consolidated totals, and the forward label now uses a calendar 12-month window with correct OCF transition semantics and conservative handling of the unavailable two-period FCF condition. On the corrected six-row held-out endpoint, B0/B1/B2/B6 all missed the single positive. This is classified as insufficient power and numeric/threshold failure evidence, not a basis for post-hoc tuning.

The machine extraction reconciliation found one retained construct error: Ford FY2023 exposes both `NetIncomeLoss` and the income-statement-presented `ProfitLoss`. The production alias path selected 4.347B while the SEC presentation path selected 4.329B. Both share period and unit; the difference reflects attribution scope. This is categorized as `CONTEXT_ERROR` / taxonomy ambiguity and requires human adjudication before it can become extraction gold.

## Numeric benchmark forensics: E1 → E2

No polarity or positive-class inversion was found. `label=1` consistently means future deterioration and every baseline's higher score consistently means greater risk. E1's sole test positive, NUE FY2022, ranked 5–6/6 in B0 and 6/6 in B1/B2/B6 because its T-period fundamentals were strong; the positive endpoint is caused by FY2023 revenue and OCF deterioration that PIT-safe predictors could not observe.

E1 is frozen under `benchmark_forensics/v0.3.1-E1-diagnostic`. E2 adds only correctness fixes: SEC `PaymentsToAcquireProductiveAssets` CapEx equivalence, filing-level two-period FCF outcomes, per-condition `TRUE/FALSE/UNKNOWN` sufficiency, and valid/invalid clustered-bootstrap accounting. Verified count remains 39 but composition changes from 32/7 negative/positive to 31/8. E2 test remains 6 rows with one positive and zero recall for all baselines. The prior `[0,0]` interval is withdrawn: 691 replicates were valid, 309 were single-class invalid, and class/cluster power makes the CI `CI_NOT_ESTIMABLE`.

## E3 right-censoring closeout

E3 fixes a corpus-wiring error without altering the cohort, label definition, models, thresholds or weights: future annual filings now live in a separate outcome-only pool rather than being restricted to the 2021–2023 feature plan. This recovered three FY2023 labels already present in the official 2024Q4 archive. Final status is 42 verified (34 negative, 8 positive), 6 review-required, 17 `TRUE_NO_ELIGIBLE_OUTCOME`, and 25 `RIGHT_CENSORED_DATA_HORIZON`. The latter could not be resolved because official 2025 bulk ZIP requests returned 403; they are not treated as negatives.

The held-out composition remains six usable rows with one positive, so B0/B1/B2/B6 metrics and the 691-valid/309-invalid bootstrap accounting are unchanged from E2. E3 therefore closes the censoring semantics but does not improve or establish predictive performance. Its frozen artifacts replay byte-for-byte.

When independently labelled predictions become available, every FP/FN is emitted as a structured case with one of: `EXTRACTION_ERROR`, `CONTEXT_ERROR`, `MODEL_APPLICABILITY`, `RULE_THRESHOLD`, `NARRATIVE_OVERWEIGHT`, `NUMERIC_OVERWEIGHT`, `MISSING_EVIDENCE`, `TEMPORAL_ERROR`, `FUSION_ERROR` or `LABEL_AMBIGUITY`. This taxonomy and generator are implemented and fixture-tested; no real empirical error counts are reported because the corpus and adjudicated labels are currently unavailable.
