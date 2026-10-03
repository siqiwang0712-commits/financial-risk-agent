# E5 research-readiness audit

Audit status: **BLOCKED**

Scope: repository readiness to freeze a future E5 study; no E5 execution or freeze
Assessment date: 2026-10-03

## Conclusion

The repository is not ready to freeze E5. It has strong reusable governance,
statistical, Assurance and historical-integrity components. The prospective study contract
is now internally reconciled around S0-S4, but freeze-critical implementation choices remain
open: the previous 270-company exclusion list is unavailable, primary E5 estimands and
arm identities remain unfrozen, and no E5-qualified reference-distribution design exists.

[`StrongTabularReference-v1`](../strong_tabular_reference/README.md) now has an approved
675-row historical development manifest, a mechanically selected fitted artifact, replay,
V/O/VO/CC diagnostics, and a label-independent empirical development reference. This is
`DESIGN_EXPOSED` retrospective development work, not prospective E5 evidence.

## Area assessment

| Area | Status | Repository evidence and remaining gap |
|---|---|---|
| Prediction input contract | `PARTIAL` | The authoritative contract now defines the five conceptual arms, while E4 packets retain cutoffs/provenance and the tabular schema is inspectable. Exact arm inputs and implementations remain `TO_BE_FROZEN`. |
| Feature schema stability | `PARTIAL` | `strong_tabular_reference/feature_schema.json` is hashable and validated, but deliberately `DRAFT_NOT_FROZEN`; extraction-to-schema conformance is not yet implemented for a prospective packet. |
| Financial-value vs observability separation | `READY` | Production uses distinct `FinancialFeatureVector` and `ReportingObservabilityVector`; `assurance/shift.py` splits them and tests show observability cannot raise severity. The research schema preserves the same boundary. |
| Strong-reference design/artifact contract | `READY` | `StrongTabularReference-v1` fixes the eligible blocks, two candidate families, finite grids, deterministic selection rule, manifest structure, provenance, output, replay and three distinct hash identities. This is design readiness only. |
| Development-data contract and historical eligibility audit | `READY` | A machine-validated manifest contract and evidence-backed inventory now define temporal, endpoint, provenance, grouping, feature, exposure and E5-exclusion gates. This is governance readiness, not dataset approval. |
| Approved historical development data | `READY` | The 675 verified E4-S rows are approved as `DESIGN_EXPOSED_HISTORICAL_DEVELOPMENT`; exact identities/hashes are bound and all 2,000 source companies are future E5 exclusions. |
| Strong competitive reference predictor | `READY` | The prespecified grouped nested-CV rule selected and fitted the historical S0 artifact; hashes and deterministic replay verify. Its E5 freeze identity remains unresolved. |
| Preprocessing isolation | `READY` | The executed runner fits imputation/scaling inside grouped training folds, disables feature selection and forbids implicit indicators in `V`. |
| Calibration design | `PARTIAL` | v0.4.1 is explicitly resolved as `UNCALIBRATED`; the future E5 protocol must freeze either that state or a valid disjoint calibration design. |
| Reference-distribution design | `PARTIAL` | A label-independent `EMPIRICAL_DEVELOPMENT_REFERENCE_ONLY` profile exists; it is not an E5-frozen or external reference. |
| Assurance policy stability | `PARTIAL` | The actual heuristic v0.4.1 runtime policy/version/hash is bound; future E5 nomination/freeze remains open. |
| Decision Certificate stability | `PARTIAL` | The v0.4.1 certificate schema/code/hash behavior is bound and replay-tested; E5 has not frozen it for the study window. |
| Prospective cohort isolation | `BLOCKED` | No future window is available or enumerated, correctly. Eligibility and five-arm packet rules are not final, and historical exclusion cannot yet be proven. |
| Previous-cohort exclusion reproducibility | `BLOCKED` | `research/e4/_cache/previous_270.json` is unpublished; only its hash is known. The existing harness correctly fails closed when disjointness is unproven. |
| Outcome isolation | `PARTIAL` | `research/e5/harness/e5_harness.py` is bound to the authoritative draft/config, models staged outcome unlock, and rejects early outcome artifacts/paths. It has only synthetic test validation and the protocol is deliberately unfrozen. |
| Model/config/environment provenance | `READY` | The historical fitted artifact binds schema/config/data, folds, selection, Python/packages, source state and model/preprocessor hashes. E5 environment freeze is separate. |
| Deterministic replay | `READY` | The fitted reference verifies hashes before trusted loading and replays a fixed sample under its pinned runtime; E5 is still unfrozen. |
| Research-statistics infrastructure | `READY` | E4-S/E4-R provide paired DeLong, company-cluster bootstrap, grouped nested CV, multiplicity and risk/coverage utilities. Reuse is preferable to reimplementation. |
| E5 governance/freeze chain | `PARTIAL` | One authoritative S0-S4 draft and matching config now control the active harness; legacy B6/A2/Hybrid hypotheses are freeze-ineligible. The chain remains deliberately unfrozen and several nominated identities/estimands are unresolved. |

## Claims cross-check

- E4-R's strong-tabular finding is retrospective and post-hoc; it does not select the
  future E5 reference and does not establish prospective superiority.
- The v0.4 Assurance Runtime has complete internal engineering validation, not external
  or prospective outcome validation.
- The new empirical development profile is label-independent but remains historical and
  development-only; it is not an E5 reference-distribution or external-validation claim.
- E5 remains unexecuted and unfrozen. The absence of cohort, predictions, outcomes and a
  final freeze hash is correct current behavior, not missing output to be generated now.

Machine-readable status is in [`readiness.json`](readiness.json); phase-specific actions
are in [`BLOCKERS.md`](BLOCKERS.md).
