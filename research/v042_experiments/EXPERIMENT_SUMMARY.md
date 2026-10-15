# v0.4.2 development experiments

RETROSPECTIVE_DEVELOPMENT / DESIGN_EXPOSED / POST_HOC_EXPLORATORY.

Historical OOF predictions: 675 selected verified-label observations, 235 events. This is a heavily analyzed development cohort, not prospective or external validation. No model was refitted, winner changed, probability calibrated or production policy changed.

## Risk and coverage

| threshold | n | issued | coverage | selective_error | review_rate |
| --- | --- | --- | --- | --- | --- |
| 0 | 675 | 675 | 1.000000 | 0.189630 | 0.000000 |
| 0.100000 | 675 | 608 | 0.900741 | 0.152961 | 0.099259 |
| 0.200000 | 675 | 528 | 0.782222 | 0.113636 | 0.217778 |
| 0.300000 | 675 | 454 | 0.672593 | 0.088106 | 0.327407 |
| 0.400000 | 675 | 305 | 0.451852 | 0.055738 | 0.548148 |
| 0.500000 | 675 | 0 | 0.000000 | NOT_ESTIMABLE | 1.000000 |

## Review budget

| budget | reviews | events_captured | recall | precision |
| --- | --- | --- | --- | --- |
| 0.050000 | 33 | 33 | 0.140426 | 1.000000 |
| 0.100000 | 67 | 65 | 0.276596 | 0.970149 |
| 0.200000 | 135 | 120 | 0.510638 | 0.888889 |

## Existing fold sensitivity

| fold | n | errors | selective_error |
| --- | --- | --- | --- |
| 0 | 135 | 30 | 0.222222 |
| 1 | 135 | 22 | 0.162963 |
| 2 | 135 | 28 | 0.207407 |
| 3 | 135 | 25 | 0.185185 |
| 4 | 135 | 23 | 0.170370 |

Distance from 0.5 is descriptive score separation, not calibrated confidence. Issued diagnostic predictions are not authorized final decisions. Threshold ties are included. Budget counts are floored, with score ties broken by observation ID. Fold errors use existing outer-fold OOF predictions at 0.5, not new fitting or seed trials.

## Agent repeatability harness

MOCK_HARNESS_ONLY / SYNTHETIC_ENGINEERING_ONLY. Two synthetic scenarios, k=3. Each certificate is checked against runtime policy. Empty evidence unions are NOT_ESTIMABLE. Real provider: NOT_RUN_PROVIDER_UNAVAILABLE.

| Case | Proposal consistency | Final consistency | Evidence Jaccard | Final values | Automation values |
|---|---|---|---|---|---|
| synthetic_with_pages | 1.0 | 1.0 | 1.0 | ABSTAIN | False |
| synthetic_without_pages | 1.0 | 1.0 | NOT_ESTIMABLE | ABSTAIN | False |

Deterministic mocks cannot establish whether Assurance reduces real-provider instability.

## Limits and deferred work

Historical Assurance ablation: NOT_ESTIMABLE because OOF rows lack Agent evidence, fragility and Assurance states. Further shift/subgroup/refitting studies: DEFERRED_NON_BLOCKING to preserve release priority. No intermediate states, human annotations, future cohorts, outcomes or E5 exclusions were fabricated.

Future work may evaluate these descriptive thresholds on genuinely untouched data. None is a prespecified or validated production threshold. Review-budget precision is not realized profit. E5 remains BLOCKED / DRAFT_NOT_FROZEN.
