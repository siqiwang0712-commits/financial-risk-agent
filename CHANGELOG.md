# Changelog

## [Unreleased]

### v0.3.2 reproducibility and runtime integrity

- Added read-only E1/E2/E3 frozen replay and dynamic Git clean/dirty provenance for future experiments; frozen v0.3.1 artifacts remain byte-for-byte unchanged.
- Added prospective label schema v2 compatibility and standalone-period FCF v2 semantics without modifying E3.
- Wired `DATABASE_URL` to PostgreSQL runtime persistence and durable long-ID credential storage; hardened tenant-scoped risk-case derivation and final-state evidence gates.
- Protected expensive analysis endpoints, bounded PDF resources, sanitized correlation IDs/errors, and split liveness/readiness health checks.
- Added provenance completeness checks, explicit missing-baseline abstention, selective-performance semantics, correlated-evidence caps and distinct aggregate-critical reason codes.
- Removed frontend localhost coupling, loaded the frozen pilot from its artifact-backed API, added semantic UI tests, and hardened container defaults.

### v0.3.1 — released

- Froze immutable `v0.3.1-E3` after separating the 90 feature observations from a label-only annual outcome pool. The E3 PIT gate reports 0 company overlap and 0 future leakage; deterministic replay matches all frozen benchmark artifacts.
- Audited right-censoring: 42 labels are verified (34 negative, 8 positive), 6 require review, 17 have no next annual filing inside the frozen 12-month window, and 25 remain right-censored at the available 2024Q4 archive horizon. SEC 2025 bulk downloads were attempted through official URLs but returned 403; no outcomes were fabricated.
- Replaced reviewer packets with complete, direction-neutral same-company evidence pools. Independent machine Reviewers A/B agreed on 90/90 normalized label states; this is machine review, not human gold, and the prior confirmation/evidence-selection-exposed artifacts remain explicitly invalid.

- Froze `v0.3.1-E1-diagnostic`, completed score-polarity and label-attrition forensics, and created a separately hashed `v0.3.1-E2` without changing the cohort or thresholds.
- Added filing-level SEC 10-Q/10-K FCF outcome reconciliation and condition-level `TRUE/FALSE/UNKNOWN` label sufficiency.
- Replaced misleading tiny-sample `[0,0]` bootstrap output with valid/invalid replicate counts and `CI_NOT_ESTIMABLE` under inadequate class/cluster power.
- Split extraction reporting into `MACHINE_AGREEMENT`, `VERIFIED_REFERENCE` and `MANUAL_REVIEW_REQUIRED`; no human gold is claimed.
- At E2, invalidated the confirmation-exposed Reviewer B artifact and generated candidate-blind reviewer packets; E3 later supersedes this path with stricter neutral A/B review.

- Rebuilt the frozen 90-observation SEC FSDS corpus after excluding dimensional segment facts from consolidated features.
- Corrected the independent forward endpoint's OCF transition, calendar 12-month window and unavailable two-period FCF handling; 39 labels are verified, 6 require review and 45 are explicitly insufficient.
- Added fact-level accession/period/unit/concept integrity checks and bound each observation to its actual source archive hash.
- Ran corrected B0/B1/B2/B6 experiments; all missed the sole held-out positive and the result is marked `INSUFFICIENT_POWER`, with no predictive-superiority claim.
- Added an independent-code-path SEC presentation/number reconciliation (E2: 1,164/1,165 comparable-field machine agreement), explicitly separated from human-adjudicated extraction gold.

- Added an empirical-validation foundation over the pre-registered 30-company registry: fixed 90-observation acquisition plan, company-disjoint 18/6/6 split, PIT guard, dataset integrity gate and frozen independent label definitions.
- Added fail-closed SEC acquisition, dual-review/extraction-gold contracts, calibration eligibility, company-clustered bootstrap deltas, structured FP/FN taxonomy and experiment-freeze verification.
- Initial diagnostic state: recorded 0/90 acquired, 0 adjudicated labels and benchmark `NOT RUN`; no SEC, annotation or LLM result was fabricated. This state predates the successful local FSDS import summarized above.
- Initial live-API attempt: official SEC acquisition was attempted twice using the repository owner's existing Git contact; all 90 requests were rejected with HTTP 403 and remain preserved in a machine-readable failure report. The later E3 numeric corpus was built from locally supplied official SEC FSDS archives, not from those failed requests.
- Added historical submissions expansion, primary filing/iXBRL HTML hashing, precise timestamp PIT comparison, empty-dataset failure, resumable partial acquisition, and blinded machine-review/run schemas.

- Made hierarchical fusion non-compensatory and monotonic for additional adverse evidence; unknown dimensions remain excluded rather than treated as safe.
- Added verified-evidence de-duplication and stable machine-readable decision reason codes.
- Added claim-conditioned narrative schema and explicit incomplete-context outcomes before contradiction classification.
- Separated evidence quality from calibrated reliability/probability with explicit calibration maturity states.
- Added replayable component delta telemetry for XBRL, rules, models, narrative, Critic, Verifier and fusion.
- Added independent `research/results/v0.3.1` replay output without modifying frozen `public_v1` results.

### Added

- Temporal `EntityRiskState`, snapshots, evidence deltas and traceable risk-change attribution.
- Temporal evidence graph with seven explicit cross-period relationship types.
- Independent model Applicability Router for industry, assumptions and missing evidence.
- Calibration metrics, risk–coverage curve and policy-driven selective automation.
- Structured Analyst–Critic–Deterministic Verifier review and immutable DecisionBundle.
- Risk Case mitigation actions, resolution-evidence gate, monitoring and reopen workflow.
- Ticker-to-CIK/latest 10-K or 10-Q filing metadata path with SEC provenance.
- Failure Lab, Human–AI study pipeline, maturity matrix and Intel failure case study.
- Tenant-scoped temporal persistence schema and authenticated timeline API.

### Fixed

- Enforced API-key authentication and rate limiting on enterprise fusion and scenario endpoints.
- Rejected analysis snapshots whose entity does not belong to the caller's organization.
- Replaced mutable Pydantic collection defaults with explicit factories.

## [0.2.0] - 2026-09-05

### Added

- SEC XBRL normalization, provenance, restatement selection, cache hashing and cross-source reconciliation.
- Schema-constrained real LLM provider with retry, prompt versioning and usage logging.
- Six-category narrative-numeric consistency engine.
- Public pilot runner with five baselines, five ablations, extended metrics, bootstrap CI, raw predictions, score decomposition and confusion matrices.
- Unit-scale invariance and deterministic 10%/30% missingness robustness checks.
- Dataset card, annotation CSV, pre-registered 30-company candidate registry and executable sample report.

### Fixed

- Missing Hybrid scores are now treated as abstentions rather than forced to probability 0.5/positive predictions.
- PDF report line wrapping, metadata and page numbering.

### Known limitations

- Evaluated corpus remains n=3; SEC rejected current-network API and bulk downloads.
- Real LLM experiment is NOT RUN because no API key was configured.
- Hybrid does not outperform Ratios Only in the released pilot.
