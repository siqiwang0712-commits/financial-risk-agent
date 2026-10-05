# StrongTabularReference-v1

Status: **FITTED_HISTORICAL_NOT_E5_FROZEN**

Evidence class: **RETROSPECTIVE_DEVELOPMENT / DESIGN_EXPOSED**

Calibration: **UNCALIBRATED**

This research-only package provides the competitive tabular reference intended for a
future E5 S0 arm. It does not replace FinRisk production scoring, authorize decisions,
freeze E5, or establish prospective/external validity.

## Approved development boundary

The approved source is the frozen E4-S replication packet. Supervised development uses
675 `VERIFIED` observations from 675 companies (235 events, 440 non-events). All 2,000
companies in the source cohort—not only the labelled 675—are registered for exclusion
from any future E5 validation cohort. The verified subset is selective and must not be
read as an unbiased sample of the 2,000.

The endpoint is `financial_deterioration_12m`, version
`deterministic_forward_outcome_rule_v1`, with a 12-month forward horizon. It is bound as
`HISTORICAL_DEVELOPMENT_ENDPOINT_V1` and
`ENDPOINT_COMPATIBLE_FOR_DEVELOPMENT`; compatibility with the eventual E5 endpoint must
still be confirmed at protocol freeze. A material E5 endpoint change requires this
reference to be re-developed or re-qualified.

The data are `DESIGN_EXPOSED_HISTORICAL_DEVELOPMENT`: E4-R used the same labelled rows and
informed the candidate families and finite grids. Development CV results therefore are
selection diagnostics, not independent generalization estimates. Outcome-blind means
blind to E5 outcomes and selection information, not blind to legitimate historical
development labels.

See [the data eligibility audit](DATA_ELIGIBILITY_AUDIT.md),
[approved manifest](development_data_manifest.json),
[675-company manifest](artifacts/development_companies_675.json), and
[2,000-company E5 exclusion manifest](artifacts/e5_exclusion_companies_2000.json).

## Feature blocks and production boundary

[`feature_schema.json`](feature_schema.json) separates:

- `V`: financial and temporal values;
- `O`: reporting-observability indicators only;
- `VO`: intentional combination of values and explicit observability;
- `CC`: complete-case sensitivity over `V`.

Only `V` and `VO` can win S0. `O` and `CC` are diagnostic only. `V` never receives
automatic imputer indicators, and `VO` uses only registered observability fields. An
observability signal may inform a research prediction or Assurance eligibility; it does
not silently become production financial severity.

## Prespecified selection and result

The frozen-before-execution development configuration is
[`development_run_config.json`](development_run_config.json). It applies company-grouped
5×5 nested stratified CV with fold-local preprocessing to exactly two candidate families:

- L2 Logistic Regression, `C ∈ {0.01, 0.1, 1, 10}`;
- Histogram Gradient Boosting with the finite declared learning-rate, leaf, minimum-leaf
  and L2 grid.

Eligible family/block pairs are ranked by unrounded mean outer AUROC, mean outer PR-AUC,
the declared family/block tie-break, then canonical JSON order. Failed candidates are
ineligible; no human override is permitted.

The mechanical winner is `VO` + Histogram Gradient Boosting with learning rate `0.05`,
maximum leaf nodes `7`, minimum leaf size `20`, L2 regularization `1.0`, `log_loss`, and
early stopping disabled. Its out-of-fold retrospective-development AUROC is `0.881789`
and PR-AUC is `0.828968`; descriptive Brier is `0.128121` for an uncalibrated score.
Canonical values and full precision live in
[`artifacts/canonical_results.json`](artifacts/canonical_results.json).

## Artifact, output and replay contract

A model file alone is not a StrongTabularReference artifact. The fitted manifest binds
feature order/schema, approved data, fold assignments, preprocessing, exact parameters,
selection record, package/runtime identity, outputs and every component hash. The public
output is `reference_model_score`, not a probability, and has
`final_decision_authority = NONE_PREDICTION_ONLY`.

The loader accepts repository-generated artifacts under the fixed research artifact root,
verifies the manifest, feature schema, development-data identity, model and preprocessor
SHA-256 values before deserialization, and requires callers to supply the exact ordered
feature names. Replay guarantees exact artifact bytes/hashes and deterministic inference
in the pinned Python 3.12.14 / NumPy 2.5.3 / scikit-learn 1.9.1 runtime; cross-platform
bit-identical floating point is not claimed. The product package supports Python 3.11 and
3.12, but a mismatched numeric stack must reject this fitted research replay rather than
claim reproduction.

Three identities remain distinct:

1. the draft design/contract hash;
2. the historical fitted-artifact hash in
   [`artifacts/artifact_manifest.json`](artifacts/artifact_manifest.json);
3. the future E5 freeze identity, still `TO_BE_FROZEN`.

## Diagnostics and reference profile

- [`OBSERVABILITY_DIAGNOSTIC.md`](OBSERVABILITY_DIAGNOSTIC.md) reports V/O/VO/CC
  development diagnostics and their non-causal interpretation.
- [`artifacts/empirical_development_reference.json`](artifacts/empirical_development_reference.json)
  is `EMPIRICAL_DEVELOPMENT_REFERENCE_ONLY`. It is built from prediction-time data without
  labels and keeps financial-value and observability profiles separate.
- Its recorded in-reference rule is deliberately narrow: observed registered financial
  values must lie within all-source-row q01–q99 bounds. Missingness is reported separately;
  the resulting rate is not a general distribution-validity or safety estimate.
- [`artifacts/selective_evaluation.json`](artifacts/selective_evaluation.json) records an
  S0/S1 `RETROSPECTIVE_DEVELOPMENT_DRY_RUN`. S2/S3/S4 are
  `NOT_ESTIMABLE_IN_V0.4.1`; no irreproducible LLM comparison was forced.

## Verify or rebuild

Verify checked-in artifacts without retraining:

```bash
python -m research.strong_tabular_reference.verify_artifact
```

For a source environment, install against the complete matrix lock:

```bash
python -m pip install -c requirements.lock -e ".[dev,postgres,research]"
```

The fitted artifact's `runtime_identity.json` remains bound to the earlier Windows CRLF
lock identity. `artifacts/generation_requirements.lock` preserves the same content in
portable LF form, and the verifier explicitly reconstructs and checks the recorded byte
identity. The active root lock was completed and pinned to LF during release audit without
rewriting that generation provenance.

Rebuild from the approved frozen source packet (expensive; performs nested CV):

```bash
python -m research.strong_tabular_reference.run_development
```

The rebuild first verifies source and development-manifest identities, then reconstructs
features, runs selection, fits the historical artifact, emits diagnostics/reference/report
artifacts and verifies the result. It never enumerates or executes E5.
