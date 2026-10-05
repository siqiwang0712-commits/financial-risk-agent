# Historical development-data eligibility audit

Status: `COMPLETE_FOR_CURRENT_REPOSITORY`

Decision boundary: development-data proposal only; no dataset is approved, no model was run.

## Isolation terminology

For this work, **outcome-blind** means blind to E5 validation outcomes, E5 outcome proxies,
future E5 company-selection information, and post-prediction E5 information. It does not
forbid inspecting legitimate historical development labels: a supervised reference will
eventually require them.

`DESIGN_EXPOSED` is not data leakage. It records that a historical cohort has already
influenced analysis, candidate-family choice, or grid design, so reuse can create
model-selection optimism. Leakage is reserved for a violated prediction-time or evaluation
boundary. Future E5 remains the untouched prospective validation boundary.

## Eligibility gates

A dataset may become `APPROVED_FOR_STRONG_REFERENCE_DEVELOPMENT` only when its populated
manifest passes all of these gates:

1. **Provenance:** source identities and hashes are verifiable and reconstruction is
   deterministic or sufficiently specified.
2. **Temporal:** every predictor was available at its prediction cutoff; no outcome or
   future fact enters feature construction.
3. **Endpoint:** labels use a versioned forward-outcome definition suitable for S0.
4. **Company identity and grouping:** stable identifiers exist and all rows from one
   company remain in the same fold.
5. **Feature contract:** the checked-in feature schema is reconstructable without zero
   substitution or silent definition changes.
6. **Integrity:** the source manifests, approved company list, and final manifest are
   hashable.
7. **E5 isolation:** every admitted development company can be excluded from E5.
8. **Exposure:** prior analytical exposure is recorded rather than hidden.

The unavailable historical 270-company list remains an E5 **cohort-freeze** blocker. It is
not required merely to assess or approve historical development data, provided the later E5
builder consumes both that list and the approved development-company exclusion manifest.

## Inventory and classifications

| Source | Size and labels | Period / endpoint | Provenance and reconstruction | Exposure and overlap | Feature compatibility | Eligibility |
|---|---|---|---|---|---|---|
| Public pilot (`finrisk-sec-mini-v1`) | 3 companies; two normal and one risk label | FY2024; single-reviewer holistic risk label | Public filing mechanics exist, but the labels are not the versioned forward endpoint | Publicly demonstrated and far too small | Selected values may exist; full schema and temporal features are not established | **`INELIGIBLE`** as primary development data; mechanics diagnostic only |
| E1 diagnostic | Same 30-company, 90-observation historical corpus lineage | FY2021–FY2023; early diagnostic treatment | Frozen forensic identity is verifiable, but it is an earlier/superseded analysis stage | Historically analyzed; design-exposed | Static values largely available; temporal coverage is incomplete at the first period | **`DIAGNOSTIC_ONLY`** |
| E2 | 30 companies / 90 company-years; usable-label subset inherited from empirical v1 | FY2021–FY2023; forward-label v1 lineage | Frozen forensic artifacts and hashes verify | Historically analyzed; design-exposed | Broadly reconstructable, with first-period temporal missingness | **`DIAGNOSTIC_ONLY`** |
| E3 / `empirical_v1` | 30 companies, 90 observations; 42 `VERIFIED` (34 negative, 8 positive), 6 `REVIEW`, 42 `INSUFFICIENT` | Features FY2021–FY2023; 12-month `finrisk-forward-label-v1.0.0` endpoint | SEC FSDS archives, accession/timestamp lineage, feature/outcome hashes, and company-disjoint splits exist | Prior development/test exposure; zero CIK overlap reported with E4-S replication | Static values directly available; later-year temporal features are derivable; first-year temporal values are absent by design | **`DIAGNOSTIC_ONLY`**: endpoint is compatible with v1, but 42 labels/8 events are inadequate for the planned grouped nested selection |
| Exact E4 published analysis | Published cohort count 2,000; 674 deterministically verified outcomes | FY2024 filings with 12-month deterministic forward endpoint v1 | Aggregate results are frozen, but the exact row-level cohort is not published/reconstructable because the 270-company exclusion input is absent | Historical E4 evidence | Cannot verify the exact row-level schema from published aggregates | **`UNVERIFIABLE`** for development nomination |
| E4-S public replication | 2,000 companies/observations; 675 `VERIFIED`, 568 `REVIEW`, 757 `INSUFFICIENT`; 235 verified events | FY2024 10-K feature window; 2025Q3–2026Q2 outcome archives; `deterministic_forward_outcome_rule_v1` | Cohort, features, outcomes, inventory, reports, SEC archive identities, and SHA-256 values are present | High overlap with exact E4; zero CIK overlap with E3; source of E4-R | All nine registered value/temporal metrics are directly represented; observability flags are deterministically derivable from presence | **`ELIGIBLE_WITH_LIMITATIONS`** and preferred proposal; must be marked `DESIGN_EXPOSED` and excluded from E5 |
| E4-R derived dataset/results | Same 675 verified E4-S rows; no independent observations | Same deterministic v1 endpoint | Derived matrices, OOF predictions, fitted results, and robustness outputs are reproducible historical artifacts | Heavily analyzed; candidate families/grids were partly informed by it | Underlying E4-S inputs are compatible; E4-R predictions/results are forbidden as features or labels | **`DIAGNOSTIC_ONLY`**; not a distinct raw data source |
| Synthetic development/demo fixtures | Small constructed examples | Synthetic outcomes/conditions | Deterministic but not empirical | No prospective evidentiary value | Useful for contract tests only | **`INELIGIBLE`** as primary empirical training data |

SEC FSDS archives are provenance sources, not independently labelled candidate datasets.
They become eligible only through a versioned cohort, feature, endpoint, and company manifest.

## Endpoint compatibility

| Source | Status | Basis |
|---|---|---|
| Public pilot | `NOT_COMPATIBLE` | Holistic reviewer risk labels are not a 12-month forward financial-deterioration endpoint. |
| E1/E2 | `UNRESOLVED` | Their earlier experimental use does not by itself establish the exact current endpoint identity. |
| E3 / empirical v1 | `COMPATIBLE_WITH_DOCUMENTED_DIFFERENCE` | It implements forward-label v1; `label_schema_v2.json` changes FCF handling and has not been nominated for E5. |
| Exact E4 | `COMPATIBLE` at the protocol level, `UNVERIFIABLE` at row level | The protocol uses deterministic endpoint v1, but exact rows are unavailable. |
| E4-S / E4-R source rows | `COMPATIBLE_WITH_DOCUMENTED_DIFFERENCE` | The deterministic v1 endpoint is explicit; the final E5 endpoint version remains `TO_BE_FROZEN`. |

No v1/v2 harmonization is authorized here. If E5 nominates an endpoint differing from the
development endpoint, that difference must be resolved prospectively before dataset approval.

## Feature compatibility

The E4-S replication is the only present source that directly contains all registered
StrongTabularReference financial and temporal values at the required scale. Its presence
pattern can deterministically produce the explicit `observed__*` fields. The E3 corpus can
produce most of the same values, but its earliest company-year lacks legitimate prior-period
inputs and its verified sample is too small for the declared selection procedure. Missing
values must remain missing; zero substitution and feature redefinition are forbidden.

## Preferred proposal and scientific consequence

The proposal in
[`development_data_proposal.json`](development_data_proposal.json) nominates the 675
`VERIFIED` E4-S replication rows as historically exposed development material. This choice
is methodological—scale, provenance, temporal validity, endpoint identity, reconstructability,
grouping, and reproducibility—not performance-driven.

The proposal remains `PROPOSED_NOT_APPROVED`. Because E4-R already analyzed these rows and
informed candidate choices, performance on them cannot estimate unbiased future S0
performance. The proposal conservatively binds all 2,000 E4-S source-cohort companies to
future E5 exclusion, not merely the 675 labelled rows. Only future E5 may provide prospective
validation.

## Approval transition

Promotion to `APPROVED_FOR_STRONG_REFERENCE_DEVELOPMENT` requires a fully populated manifest,
successful mechanical validation, exact admitted-company and E5-exclusion manifests, verified
source hashes, endpoint and feature-schema identities, reconstruction commit, and canonical
manifest hash. Approval precedes any preprocessing fit, candidate evaluation, or model fit.
It does not freeze StrongTabularReference-v1 or E5.
