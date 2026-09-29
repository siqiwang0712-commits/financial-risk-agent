# Limitations

## Current E4 evidence boundary

E4 performance applies to the 674 deterministically verified observations in a frozen
2,000-company cohort, not to the full cohort or a general population. Verified endpoint
coverage was 33.7%; 571 cases required human review and 755 had insufficient outcome data.
Verification was associated with prediction-time characteristics, so post-hoc propensity
weighting is sensitivity analysis and does not remove selection bias.

The endpoint is a prespecified financial-deterioration rule. It is not bankruptcy,
default, credit loss, insolvency, a credit rating, a fraud finding or an investment
recommendation. Every score remains an `UNCALIBRATED` heuristic index and must not be
read as a probability that an event or a decision is correct.

B6 improved B0 on E4's deterministically verified subset, but the Local Agent and Hybrid
comparisons contained only five paired events. Their incremental value was not
established. E4 did not externally validate a full narrative/document Agent, MD&A or
Risk-Factor grounding, planner/reflection behavior, or production and regulatory use.

E4-S found that E4's published label-permutation p-value tests outcome independence from
both scores, not equality between B6 and B0. Correctly specified paired tests support the
same direction on E4-S's re-execution cohort, but the exact E4 per-observation rows were
not published. The 675-observation E4-S cohort overlaps E4 by about 94%, so it is a
near-reproduction rather than an independent sample.

E4-R is retrospective `POST_HOC_AUTOMATED_ROBUSTNESS` work on that same replication
packet. Strong learned tabular baselines outperform B6, but a material part of their
advantage comes from reporting and missingness structure: a model using only presence/
absence indicators also exceeds B6 on this cohort. Temporal features add little on top
of the strongest static nonlinear learner. The reported DeLong and bootstrap intervals
condition on realized out-of-fold predictions and do not integrate all
training-procedure uncertainty. E4-R is not confirmatory evidence and is not an
independent external validation.

The post-hoc Codex sub-Agent comparator used a project-internal display name rather than
an exposed, attestable model identity. It had only five verified events, was commissioned
after E4 outcomes existed, and is neither independently byte-reproducible nor evidence of
named-model superiority.

Rules, weights, fusion thresholds and evidence-coverage confidence are not externally
calibrated. Component telemetry records observed changes in this pipeline, not causal
component value. PostgreSQL, containers, identity, object storage, distributed workers,
telemetry and availability behavior have not been validated in an externally operated
production environment. No certification, production SLA or regulatory approval is
claimed.

Canonical current results and study-specific caveats are in
[Experiment Results](EXPERIMENT_RESULTS.md), the
[E4-S audit](e4_statistical_audit/AUDIT_REPORT.md), and the
[E4-R final report](e4r_automated_robustness/FINAL_REPORT.md).

## Earlier pilot and E3 limitations

The executed public pilot has only three same-sector companies, one positive risk label and a single annotator. Its point estimates and bootstrap intervals cannot support generalization or a claim that the hybrid approach outperforms alternatives. The LLM-only pilot used the deterministic offline provider. A hosted OpenAI-compatible path has been smoke-tested with an intentionally supplied API key, but no frozen real-provider benchmark has been run.

SEC Company Facts acquisition returned HTTP 403 in the recorded environment. XBRL normalization, provenance, restatement selection and cross-source reconciliation are implemented and unit tested, but public-pilot extraction accuracy is not yet empirically measured. The frozen observations are reviewed statement values, not a substitute for an independently annotated XBRL gold set.

The consistency engine now requires claim-conditioned evidence constructs before classifying a contradiction. This prevents a single ratio from testing a broad liquidity claim, but the construct ontology remains hand-designed and has not been independently validated. Missing marketable-securities or funding-access evidence correctly produces incomplete context; it may also reduce recall.

PDF layouts, scanned documents, XBRL differences, restatements, and ambiguous accounting labels can reduce extraction quality. Sector-specific accounting makes generic ratios and Altman/Beneish/Ohlson/Piotroski models inappropriate in some cases, especially financial institutions. Expert weights are transparent but not statistically optimal. Narrative extraction can miss context even when its quote is genuine. Page-level matching proves provenance, not truth. Scores are decision-support signals—not bankruptcy probabilities, fraud findings, credit ratings, or investment advice.

The v0.3.1 fusion invariants are logical correctness properties, not empirical calibration. `UNCALIBRATED` evidence quality must not be interpreted as the probability that a decision is correct. Component telemetry measures observed before/after deltas in this pipeline; it does not identify causal component value and is not a Value-of-Information method.

The numeric corpus contains all 90 frozen company-years from official SEC quarterly statement archives and passes PIT/split integrity. E3 has 42 verified future numerical endpoints; 17 observations truly have no next annual filing within the frozen calendar-12-month window and 25 remain right-censored because the local official archive horizon ends in 2024Q4. Official 2025 SEC bulk downloads returned 403 from this environment. E3's held-out evaluation therefore still has six labelled observations and one positive. Every B0/B1/B2/B6 baseline missed that positive at its frozen threshold. Of 1,000 clustered replicates, 309 were single-class and invalid; class/cluster counts are inadequate, so the CI is not estimable and superiority is not established. The endpoint is a deterministic deterioration definition, not bankruptcy probability or human-adjudicated hard distress. A separate SEC presentation-to-number machine reconciliation exists, but no human extraction gold, narrative corpus, real-provider LLM benchmark or human reviewer labels exist.

The original Reviewer B path had confirmation exposure and the first candidate-blind replacement still used preselected next-year evidence; both are invalidated. Neutral Reviewer A and B received complete same-company evidence pools with no candidate label, prediction, directional evidence selection or peer output. They agreed on all 90 normalized label states. This remains machine-only agreement, not independent human gold; no human adjudication or inter-rater validity claim is made.
