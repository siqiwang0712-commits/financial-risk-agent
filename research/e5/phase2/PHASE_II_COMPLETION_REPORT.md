# Phase-II execution report — 2026-10-20

**E5-R: BLOCKED_BEFORE_COHORT_FREEZE. E5-P: PROTOCOL_FROZEN.**
Actual evaluation cohort N = 0; E5 predictions = 0; E5 outcome values accessed = 0.
**Assurance benefit was not evaluated.** No empirical effect, negative result,
primary success, sensitivity result, or completed E5-R experiment is claimed.

## What was completed

The public entrypoint is `python -m research.e5.run_e5`, using
`phase2.precise_engine.PreciseExecution` and the single canonical V3 analysis.
It implements source acquisition, eligibility/non-overlap gates, immutable
protocol/cohort/features, once-only proposals, S0–S4 fanout, verified certificates,
all-role pre-outcome audit, explicit outcome unlock, mature endpoint extraction,
paired analysis, sensitivities and reporting. Real retrospective execution was
attempted and stopped at the actual missing historical exclusion prerequisite;
see `E5R_EXACT_CLOCK_EXECUTION_RESULT.json`. Unfinished scientific stages have
not been represented by synthetic or engineering-fixture results.

Without provider credentials, this follows the explicitly authorized **internal
structured numeric study**, not an LLM or released-agent validation. The raw
producer runs before evidence verification/Assurance; S2–S4 consume the exact
same frozen proposal. The development-only frozen calibrator and study policy
remain separate from released production policy. Historical models were not
refitted. Model identity is
`E5-NUMERIC-CALIBRATED-STUDY-V2-CONSISTENT-EVIDENCE-ADMISSION`;
producer code identity is
`2223ed190fb8f2d4c2eebe1e31f4af85dc0ca4bf13ffbfaa2171b16a9d8dab45`.

Development qualification used 675 approved historical VERIFIED companies,
603 available scores and 72 unavailable scores. Raw AUROC was 0.58091446;
five-fold development CV selected isotonic calibration. These are development
results, not external or E5 evaluation performance. Fixed calibrated review
thresholds remain 0.35/0.65; production policy is unchanged.

## Inference and power

Canonical analysis identity:
`1653696313abcc4c52eb6cebd74cdb215e453ae87c588f30c603a6d75738bef9`.
The fully executed finite null grid contains 13 configurations × 5,000 trials,
with 20,000 paired company bootstrap draws per trial. Error and coverage-NI use
constrained paired nulls; absolute coverage retains V2 boundary Bernoulli;
primary IUT is the maximum of its three component p-values, followed by Holm
for P1/P2 at 0.05. No configuration met the prespecified material
anti-conservatism criterion. Maximum true-null component rejection was 0.0486;
maximum Holm true-null family rejection was 0.0354. Finite simulation-grid
qualification does not establish uniform validity over every population.

V1's absolute-coverage failure and the additional V2 nested NI failures remain
permanent evidence. The V3 repair, all counted execution batches and the
scheduler-only failed attempts are preserved. Canonical inference has not been
changed after qualification.

Three thousand full-kernel planning trials, 1,000 each at N=100/500/2000,
produced zero P1, P2 or joint successes under the frozen development-only
optimistic scenario. This is underpower evidence, not an empirical Assurance
failure. Delta=0.010962962962962964, m=0.05 and c=0.6244444444444444 remain
unchanged. No powered N was selected; the frozen rule is the largest legitimate
mature cohort without lowering thresholds. The separate minimum 100 paired
VERIFIED positive-event requirement remains active. The 35 current metadata
candidates could not satisfy that event-count requirement even if all qualified;
they are neither a final cohort nor empirical results.

## Real source/runtime verification

Official 2025Q3 FSDS was acquired and hash-verified on GitHub Actions. Its raw
archive SHA256 is
`ebe25fa74c3655f4738ed9eb144af3953c3981c80f57d74829fb9ad68b114710`.
The four original E4 input archives were independently verified against their
original declared hashes, proving a conservative 5,498-issuer E4 source superset.
This does **not** establish containment of the separate unpublished previous_270.

The source inspection found 382 original 10-K metadata records, 60 candidates
after known historical exclusions, and 35 with conservative authoritative
future-filing **metadata** availability. No candidate's future financial values
or outcome labels were used. Further temporal expansion/final selection remain
before cohort freeze and cannot resolve missing historical disjointness.

Original EDGAR index documents established that API acceptance timestamps are
not reliable clock authorities, while FSDS values are minute-rounded. Active
input and endpoint adapters use primary-index seconds in Eastern time converted
to UTC. Rejected CompanyFacts and strict all-field equality attempts remain
failed. `ORIGINAL_SOURCE_V3_AMENDMENT.md` documents original-instance precision
resolution and the two additional MSFT depreciation observations; it does not
reclassify the failed equivalence test as passed. Retrospective FSDS and
prospective original-instance observability are reported separately; no pooled
R/P primary inference is authorized.

Workflow **39383429646**, job **118497568350**, actually qualified two already
excluded historical issuers using both archive and live inputs. All common
observed financial values and exact primary clocks agreed. Four real role
runs replayed S0 and executed one raw proposal plus evidence-routing/Full
Assurance in network-disabled, read-only, no-host-volume containers. Certificates
were verified. AVNET remained REVIEW across S2–S4; MSFT remained ABSTAIN across
S2–S4 in both source modes. These fixtures are engineering evidence only.
No E5 outcome or independent human-review claim is attached to them.

Qualified image:
`sha256:3b0a96a0b9888a8e346efe8cbaf7eb37258b55ecc311a4dda427224c3d1f5de1`.
Actions artifact **12246323062**, archive digest
`4921d04257e9927f1d72eb7c0a23c0d0158baa6492bf156b013885a60153db33`,
retains `e5-precise-prediction-image.tar.gz`. Automatic source-qualification
push triggers have been disabled after obtaining the required artifact.

## Prospective freeze and remaining prerequisites

The exact-clock prospective protocol is `e5p-precise/protocol.json`:
SHA256 `40d62fefa7725022abe88685c237af691d70909feb22d92a13fb4bd22bb2f9ae`,
payload identity
`0294633cd7b762d33bd3992bbff175505c5e48b5d8acf52dc16faf582ccf11af`.
Its immutable common-method parent remains intact. Enrollment is fixed to
**2027-01-01 00:00 UTC ≤ accepted < 2028-01-01 00:00 UTC**. No prospective
company has been enumerated or enrolled. A real attempted poll correctly stopped
at the closed-window gate before any official feed request.

The prospective collector freezes official feed snapshots, selects the first
original 10-K per eligible CIK within its declared first-1,000-entry feed frame,
checks complete first-filing history and historical/R exclusions, captures the
original accession's values, and freezes isolated predictions within 24 hours.
Failures and missed deadlines remain explicit; no post-outcome backfill or
silent proposal regeneration is allowed. Poll at least hourly while open and
report feed gaps. No continuously deployed runner is claimed.

Enrollment still requires the exact original previous_270 file with SHA256
`d73b371ccb026f556387cf6ff8ba204a4fde0664dcd780f099f12aa005e36603`,
or an independently established non-overlap proof under a pre-outcome amendment.
Its existence is pinned by commit
`96e60ae91c0ba73342c6e96e42eaa40145f082b1` at 2026-09-25T03:04:52Z,
but the pin does not prove its parent membership universe. A new issuer after
that pin cannot yield a 12-month mature retrospective endpoint before
2027-09-25. Neither later IPO dates nor the known E4 superset close C01. The old
exhaustive recovery search was not repeated, and no exclusion list was invented.

Before enrollment, retain the exact image and rolling state in durable storage
and provision the hourly runner. Current Actions retention expires
**2027-01-18T06:57:20Z**, which does not cover the prospective window. Durable
retention or deployment has not been falsely marked complete.

## Validation and preservation

316 relevant E5/Assurance/frozen-reference tests passed; repository-wide Ruff
passed. All E5 workflow YAML parses. The integrity audit verified 172 immutable
historical baseline files, development calibration artifacts, the frozen common
core, and the exact-clock prospective protocol. Runtime qualification used real
Docker execution on GitHub Actions; local Docker unavailability was not replaced
by a self-attestation. See `VALIDATION_EXACT_CLOCK.json`, qualification proofs,
`precise-attempt-provenance.json` and `REPRODUCIBILITY_EXACT_CLOCK.json`.

All work stays on E5-experiment. No PR, main change, merge or force-push was made.
