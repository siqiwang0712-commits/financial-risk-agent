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
