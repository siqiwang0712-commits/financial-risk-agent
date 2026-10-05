# E5 blockers

This list identifies the smallest future work needed at each governance boundary. It is
diagnostic; none of these actions is performed by this audit.

## Must resolve before E5 protocol freeze

1. **Choose the prospective calibration path.** v0.4.1 is explicitly `UNCALIBRATED`.
   Either freeze a
   valid development/calibration/validation design or explicitly freeze E5 as
   `UNCALIBRATED`; do not imply probability reliability.
2. **Freeze the E5 reference-distribution design.** A historical label-independent
   development profile now exists, but E5 must specify its permitted reference cohort,
   statistics, schema, scope and fail-closed behavior.
3. **Nominate the E5 policy/certificate identities.** v0.4.1 versions and hashes are bound,
   but E5 must nominate/freeze them with migration and replay acceptance rules.
4. **Finalize the confirmatory estimands and implementation identities.** Resolve the
   `TO_BE_FROZEN` primary estimands, meaningful effects, alpha allocation, S1 admission
   policy, and exact S2/S3 implementations without inspecting future outcomes.

## Must resolve before cohort freeze

1. **Publish or otherwise verifiably provide the prior 270-company exclusion set.** It is
   missing at `research/e4/_cache/previous_270.json`, so company disjointness cannot be
   reproduced. Add the exact approved list with provenance and hash, without altering
   frozen E4 results.
2. **Freeze eligibility, time windows and packet construction.** The future filing/outcome
   periods must exist, and packet construction must prove every predictor was available by
   its cutoff. Do not enumerate candidates until these rules and the sampling salt freeze.
3. **Freeze historical-cohort exclusion inputs.** Consolidate E1–E4, public-pilot,
   development and prior-validation company identifiers into a versioned exclusion
   manifest whose source hashes are checked by the cohort builder.

## Must resolve before predictions

1. **Bind all five arms to one frozen input/certificate schema.** Record model/config,
   code, container, policy, reference profile and feature-schema identities. Reject schema
   drift and unknown fields.
2. **Qualify E5 replay and environment isolation.** Bind the historical S0 artifact into
   the E5 freeze and enforce that prediction containers cannot mount outcome paths.
3. **Complete outcome-blind software gates.** Run the Assurance bypass, tamper, fragility,
   observability-separation and distribution fail-closed qualification suite named by the
   v0.4 draft.

## Must resolve before outcome access

1. **Freeze and verify predictions/certificates.** Complete the staged manifest chain and
   independently verify every artifact hash, row count, arm coverage and replay sample.
2. **Approve the unlock.** Record that no prediction-stage process could access outcomes,
   all expected arms are complete, and deviations are signed before mounting outcome data.
3. **Freeze analysis/adjudication execution inputs.** Lock the endpoint implementation,
   blinded review packets, multiplicity family, missing-outcome rules and permitted
   sensitivity analyses before labels are read.
