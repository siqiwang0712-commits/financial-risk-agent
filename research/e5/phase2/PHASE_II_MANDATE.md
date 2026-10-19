# E5 PHASE-II — FINAL EMPIRICAL COMPLETION MANDATE

Repository:
https://github.com/siqiwang0712-commits/financial-risk-agent

Branch:
E5-experiment

Required starting HEAD:
38804c9649e8451b683f9f5f2d97d041e18e69cd

You are continuing an existing E5 research execution, not starting a new readiness audit.

The repository already contains:

- extensive E5 governance and leakage controls;
- immutable artifact/checkpoint infrastructure;
- FrozenProposalProducer wrapper;
- utility thresholds delta/m/c;
- S0 replay qualification;
- V1 inference failure evidence;
- V2 absolute-coverage correction;
- C01 recovery evidence;
- E5-R/E5-P checkpoint reports.

DO NOT redo this work unless required by a correctness bug.

Your task is now to COMPLETE THE ACTUAL EMPIRICAL EXPERIMENT.

The target is:

E5-R = COMPLETE

with a real evaluation cohort, real point-in-time inputs, real predictions,
real S0–S4 outputs, real mature outcomes, locked inference, and a complete
statistical result.

In parallel:

E5-P must be advanced to the strongest legitimate prospective state,
preferably PROTOCOL_FROZEN / ENROLLING or WAITING_FOR_OUTCOMES.

Do not stop by merely reporting existing blockers.

Resolve them whenever technically and scientifically possible.

Scientific integrity remains mandatory:
never fabricate data, model executions, cohort identities, historical exclusions,
outcomes, independent review, or favorable results.

Negative empirical results are valid completion.

======================================================================
1. BEGIN FROM THE ACTUAL CURRENT STATE
======================================================================

First verify:

git branch --show-current == E5-experiment

git rev-parse HEAD ==
38804c9649e8451b683f9f5f2d97d041e18e69cd

Read all existing E5 execution artifacts before modifying anything.

In particular inspect:

research/e5/e5r/E5R_FINAL_REPORT.md
research/e5/e5p/E5P_STATUS.md
research/e5/execution/EXECUTION_RESULT.json
research/e5/execution/RUN_STATE.json
research/e5/execution/SOURCE_ACCESS_REPORT.json
research/e5/execution/C01_RECOVERY.json
research/e5/qualification/CALIBRATION_REPORT.md
research/e5/qualification/INFERENCE_QUALIFICATION_REPORT.md
research/e5/coverage_null_v2.py
research/e5/execution/core.py
research/e5/execution/inference.py
research/e5/run_e5.py
research/e5/autonomy/*
research/e5/experiment_config.json

Preserve all prior failed/blocked evidence.

Never rewrite V1 as if it passed.

Treat V1 failure and V2 amendment as permanent provenance.

======================================================================
2. CHANGE THE EXECUTION GOAL
======================================================================

The current implementation is primarily a gating/checkpoint CLI.

That is no longer sufficient.

Transform it into a real end-to-end execution engine.

The canonical E5-R execution path must become:

ACQUIRE_SOURCE_DATA
→ BUILD_ELIGIBLE_UNIVERSE
→ PROVE_HISTORICAL_DISJOINTNESS
→ FREEZE_PROTOCOL
→ QUALIFY_MODELS
→ FREEZE_COHORT
→ BUILD_FEATURE_PACKETS
→ FREEZE_FEATURE_PACKETS
→ GENERATE_PROPOSALS
→ RUN_S0
→ RUN_S1
→ RUN_S2
→ RUN_S3
→ RUN_S4
→ VERIFY_CERTIFICATES
→ FREEZE_PREDICTIONS
→ PRE_OUTCOME_AUDIT
→ UNLOCK_MATURE_OUTCOMES
→ FREEZE_OUTCOMES
→ ANALYZE
→ RUN_SENSITIVITY_ANALYSES
→ AUDIT
→ E5R_COMPLETE

Implement every missing stage.

Do not leave command names that always return BLOCKED merely because the original
implementation was defensive.

A gate should block only when its actual scientific prerequisite is unsatisfied.

Once the prerequisite has been genuinely supplied, the stage must execute.

======================================================================
3. FIX THE FEATURE SOURCE-IDENTITY BOUNDARY
======================================================================

Before using any real case, strengthen validate_features().

The existing source schema validates timestamp and accession format but does not
fully bind every source to the case identity.

Define an explicit source-role contract.

At minimum distinguish:

index_accession

from any explicitly allowed:

supporting_accessions

If the experiment requires only the index filing, require:

source.accession == packet.accession

If prior filings are legitimately needed, supporting filings must satisfy:

source.cik == packet.cik
source.available_at <= prediction_cutoff
source.filing_timestamp <= prediction_cutoff

and have a declared role such as:

INDEX_FILING
PRIOR_PERIOD_FILING
SUPPORTING_FILING

No unrelated issuer filing may enter a FeaturePacket.

Add regression/adversarial tests for cross-case accession substitution.

======================================================================
4. ACQUIRE REAL AUTHORITATIVE SEC POINT-IN-TIME DATA
======================================================================

Do not stop because the local sandbox cannot directly access sec.gov.

Actively solve acquisition.

Preferred source:

official SEC Financial Statement Data Sets and EDGAR filing archives.

The SEC quarterly Financial Statement Data Sets contain accession-level
submission metadata including acceptance/filed information and filing-bound
reported values.

Use quarterly datasets rather than current/latest CompanyFacts whenever doing so
better preserves accession-specific historical state.

Required minimum source provenance per filing:

CIK
accession / ADSH
form
period
filed date
accepted timestamp
source URL
raw source SHA256
download timestamp
dataset-quarter identity

For narrative/full filing content, fetch the accession-bound 10-K filing only
after the cohort has been selected.

Do NOT use a company's current/latest restated values as a substitute for what
was available at prediction cutoff.

----------------------------------------------------------------------
4A. Network fallback using GitHub Actions
----------------------------------------------------------------------

If the Codex/local environment blocks SEC network access:

DO NOT declare the experiment blocked immediately.

Create a controlled GitHub Actions acquisition workflow.

Example purpose:

.github/workflows/e5-sec-acquisition.yml

The workflow may:

1. run on workflow_dispatch and/or a dedicated E5 acquisition trigger;
2. download only the required SEC quarterly ZIP datasets;
3. use a descriptive SEC-compliant User-Agent;
4. throttle requests conservatively, preferably <= 5 requests/second;
5. verify archive integrity;
6. extract required submission/numeric tables;
7. generate content-addressed manifests;
8. optionally acquire selected accession-bound filing text after cohort selection;
9. upload the resulting immutable dataset/manifests as GitHub Actions artifacts.

Do NOT commit large raw SEC archives to Git unless appropriate.

Prefer:

GitHub Actions artifact
+
SHA256 manifest
+
reproducible acquisition script.

If the current environment can access GitHub Actions artifacts, download the
artifact back into the execution environment.

If GitHub Actions cannot be programmatically triggered from the environment,
create a push-triggered acquisition workflow scoped only to E5-experiment and
remove/disable automatic acquisition once the required immutable artifact exists.

Use the smallest number of authoritative SEC requests necessary.

Do not replace SEC provenance with an arbitrary financial API merely because it
is easier.

======================================================================
5. RESOLVE C01 THROUGH A STRONGER NON-OVERLAP DESIGN
======================================================================

The exact previous_270 was already searched extensively and was not recovered.

Do not keep spending most of the run repeating the same search.

Do not invent previous_270.

Instead attempt to establish a logically stronger contamination-safe cohort.

First determine from immutable historical E1–E4/E4-S/E4-R artifacts:

HISTORICAL_UNIVERSE_CUTOFF

and the latest time at which previous_270 must already have existed.

Use commit/manifests/code references to its expected SHA where appropriate.

Then determine whether the provenance of previous_270 proves that it was sampled
from a filing/company universe observable before that cutoff.

If and ONLY IF that provenance is established, permit a NEW-ISSUER exclusion rule:

candidate issuer must have no eligible SEC filing before the historical cutoff

AND

its first qualifying SEC filing must occur after that cutoff.

Use CIK/company identity, not ticker.

Also check:

- predecessor issuer relationships where discoverable;
- renamed issuers;
- mergers/reorganizations where they can create identity ambiguity.

If this logically guarantees the company could not belong to the historical
sampling universe, record:

HISTORICAL_NONOVERLAP_METHOD =
PROVABLE_NEW_ISSUER_BOUNDARY

This is NOT the same as recovering previous_270.

Document the proof.

If the historical source universe does not permit that proof, do not falsely
close C01.

Instead search for another stronger independently verifiable non-overlap boundary.

The objective is:

prove candidate company ∉ all prior experimental/development universes.

Not:

reconstruct an approximate previous_270.

======================================================================
6. BUILD THE ACTUAL RAW PROPOSAL PRODUCER
======================================================================

The current FrozenProposalProducer wrapper is infrastructure only.

Implement and qualify the actual study producer.

Inspect FinancialRiskAgent carefully.

The current public agent performs claim/evidence verification before the exposed
proposal, so directly copying the final public proposal is not a valid raw S2
ablation.

Create a study-only producer boundary BEFORE:

verify_conclusions
three_role_review
Assurance
certificate authorization

and without consuming downstream evidence-verification results that define S3.

The raw producer must produce one structured ProposalPacket containing:

risk_score
proposed_decision
structured assessment/proposal representation
producer identity
model identity
prompt identity
tool-definition identity
input hash

The output must then fan out immutably to S2/S3/S4.

The producer must never be executed separately for S2, S3 and S4.

The actual invariant is:

one generation
→ one ProposalPacket hash
→ three consumers

For every E5-R case:

ProposalHash_S2
==
ProposalHash_S3
==
ProposalHash_S4

zero mismatches.

----------------------------------------------------------------------
6A. Narrative provider
----------------------------------------------------------------------

Use a REAL supported provider where available.

The repository already supports StructuredLLMProvider.

Check whether a real provider credential is available.

If OPENAI_API_KEY or another configured supported provider is available:

freeze:

provider
exact model identifier
prompt version
prompt hash
schema hash
temperature
max tokens
retry policy
tool identity

and run real model inference.

Do NOT expose the secret.

Do NOT commit the key.

Do NOT use MockNarrativeProvider while claiming real LLM validation.

If no real LLM credential is available, first determine whether the raw proposal
can be scientifically and reproducibly generated from the repository's
deterministic numeric/traditional-model/rule layer while still answering the
frozen E5 scientific question.

If this requires materially changing the scientific question:

create a NEW E5-R protocol identity before any outcome access and describe the
scope accurately.

Never silently substitute a mock provider.

======================================================================
7. DEFINE S2, S3 AND S4 PRECISELY
======================================================================

After implementing the raw producer:

S2 =
the frozen raw proposal itself.

S3 =
the exact same frozen proposal
+
only the prespecified material evidence verification intervention.

S3 must NOT include:

full Assurance policy
fragility layer unless explicitly part of evidence verification
certificate authorization
full policy maturity gates
S4-only reference logic

S4 =
the exact same frozen proposal
+
the full intended Assurance Runtime
+
qualified study authorization policy
+
Decision Certificate.

Write mechanical tests proving intervention isolation.

======================================================================
8. IMPLEMENT DEVELOPMENT-ONLY AGENT CALIBRATION
======================================================================

Now that the actual raw producer exists, create a historical DEVELOPMENT corpus
for that exact producer.

Never use E5-R evaluation outcomes.

Run the same frozen producer on eligible historical development cases.

Collect:

raw producer score
verified historical endpoint
input identities

Then assess score semantics:

directionality
monotonic relationship
finite support
stability

Only if calibration is meaningful:

compare:

Platt/logistic calibration
vs
isotonic regression

using development-only CV.

Primary selection criterion:

Brier score.

Secondary:

log loss
calibration slope/intercept
stability
simplicity.

Freeze the selected calibrator.

Create:

calibration identity
calibration artifact hash
training-company manifest
producer hash
runtime hash
CV report.

Do not call this external validation.

======================================================================
9. CREATE THE STUDY-QUALIFIED S4 POLICY
======================================================================

Keep the released production HEURISTIC_POLICY unchanged.

Create a separate study policy.

It must clearly state:

E5_STUDY_POLICY != RELEASED_PRODUCTION_POLICY

Use frozen calibrated risk semantics and the existing fixed review thresholds
unless a semantics mismatch requires a pre-outcome protocol correction.

Default:

PASS:
risk < .35

REVIEW:
.35 <= risk < .65

FLAG:
risk >= .65

Full Assurance vetoes remain active.

Authorization requires:

valid proposal
verified required evidence
qualified reference/applicability checks
no hard fail-closed runtime condition
successful certificate generation
successful certificate verification
score outside review band

Freeze:

study_policy_id
study_policy_hash
calibration_hash
Assurance source hash
certificate schema hash.

======================================================================
10. COMPLETE V2 STATISTICAL QUALIFICATION
======================================================================

V1 is permanently failed.

V2 currently qualifies only the absolute-coverage component.

Finish V2 BEFORE E5-R outcome access.

Make ONE canonical E5 analysis entrypoint.

Do not leave two competing analysis engines where the analyst could choose after
seeing results.

Canonical identity must explicitly bind:

paired BCa engine
error-benefit test
coverage-NI test
V2 boundary-Bernoulli absolute coverage test
IUT
Holm
draws
seed
delta
m
c

Then run a broader null grid covering:

sample size
event prevalence
VERIFIED fraction
informative and independent missingness
S1/S3/S4 automation rates
paired error discordance
P1/P2 correlation/dependence
boundary and mixed-boundary cases.

Test:

component type-I error

IUT false-positive rate

Holm family-wise error.

Use the predeclared anti-conservatism criterion.

If V2 fails:

repair it BEFORE outcome access
under a new inference identity
and rerun qualification.

Do not inspect E5-R outcomes during this process.

======================================================================
11. COMPLETE JOINT POWER AND DETERMINE N
======================================================================

Use the final canonical V2 inference engine.

Simulate joint power for the full:

IUT + Holm

procedure.

Use development-only/planning quantities.

Include:

prevalence
VERIFIED fraction
proposal success
packet success
paired discordance
expected error benefit
coverage difference
absolute coverage
attrition.

Target approximately >=80% joint power where feasible.

Select N BEFORE cohort outcomes are inspected.

If available mature cases are insufficient:

use the largest valid cohort
without lowering delta/m/c.

Record underpower honestly.

======================================================================
12. CONSTRUCT E5-R COHORT
======================================================================

Using only source/provenance information and frozen eligibility:

identify the latest fully mature temporal window.

A case is mature only if its entire 12-month endpoint window has elapsed and the
required authoritative outcome evidence is actually observable.

Do not use outcome values while selecting cases.

Apply:

industrial/nonfinancial eligibility
existing SIC exclusions where frozen
company uniqueness
historical non-overlap
point-in-time source availability
schema availability

If more than N cases qualify:

select deterministically using the existing salted SHA256 CIK/accession ordering.

If fewer:

expand the enrollment window backward in whole calendar periods under the
predeclared rule.

Freeze:

candidate universe
all exclusions and reasons
final cohort
CIKs
accessions
window
hashes.

Then set:

COHORT_FROZEN

only after non-overlap proof passes.

======================================================================
13. FREEZE PROTOCOL BEFORE EVALUATION
======================================================================

Before generating evaluation predictions freeze:

study classification
research question
P1/P2
arms
producer
model/prompt identity
calibrator
study policy
Assurance code/policy
certificate schema
endpoint
eligibility
cohort selection algorithm
historical non-overlap rule
FeaturePacket schema
delta
m
c
power/N
canonical V2 inference
bootstrap draws = 20000
seed = 20261019
multiplicity
missingness handling
claim language.

Generate immutable protocol identity.

No outcome access before this point.

======================================================================
14. BUILD REAL FEATURE PACKETS
======================================================================

For every E5-R case:

use only sources with:

available_at <= prediction_cutoff

and

filing_timestamp <= prediction_cutoff.

Bind:

CIK
index accession
supporting accessions
source roles
accepted timestamp
prediction cutoff
raw hashes
feature schema
extractor hash
preprocessor hash
reference hash.

No current/latest restatement may enter a historical packet.

Freeze all packets.

Run the adversarial point-in-time tests.

Then:

FEATURE_PACKETS_FROZEN.

======================================================================
15. GENERATE ALL REAL PREDICTIONS
======================================================================

For each case:

1. load frozen FeaturePacket;
2. generate ProposalPacket exactly once;
3. freeze ProposalPacket;
4. run S0;
5. run S1;
6. run S2;
7. run S3;
8. run S4;
9. generate Decision Certificate;
10. verify certificate;
11. persist arm results.

Do not regenerate proposals.

Prediction freeze requires:

all expected cases processed
all arm outputs present
proposal mismatch count = 0
all required certificates valid
prediction/output hashes complete.

Create the prediction manifest.

Then:

PREDICTIONS_FROZEN.

======================================================================
16. PRE-OUTCOME AUDIT
======================================================================

Before any E5-R outcome read, verify:

protocol frozen
producer frozen
calibration frozen
policy frozen
cohort frozen
FeaturePackets frozen
proposals frozen
predictions frozen
V2 inference frozen
power/N frozen
historical non-overlap proven
point-in-time provenance passed
proposal mismatches = 0
prediction chain verified.

Only then permit outcome access.

======================================================================
17. ACQUIRE AND FREEZE REAL MATURE OUTCOMES
======================================================================

Use the frozen endpoint implementation.

Use only evidence after the prediction cutoff within the fixed 12-month horizon
according to the endpoint contract.

Preserve:

VERIFIED
REQUIRES_REVIEW
INSUFFICIENT_DATA
MISSING

semantics.

Never coerce missing to negative.

Freeze raw outcome evidence, adjudication inputs and final endpoint labels.

Record first-outcome-access timestamp.

No design change after this timestamp.

======================================================================
18. RUN THE COMPLETE EMPIRICAL ANALYSIS
======================================================================

Use ONLY the canonical frozen V2 engine.

Primary comparisons:

P1 = S4 vs S1

P2 = S4 vs S3

Primary quantities:

ErrorBenefit_C =
mean(E_C - E_S4)

CoverageDifference_C =
mean(A_S4 - A_C)

Coverage_S4 =
mean(A_S4)

Success requires:

ErrorBenefit_C > delta

CoverageDifference_C > -m

Coverage_S4 > c

and corresponding one-sided tests.

Use:

20,000 paired-company draws

BCa 95% intervals for applicable empirical quantities

V2 boundary-Bernoulli absolute coverage null

three-component IUT:

p_IUT = max(component p-values)

two-primary Holm correction

family alpha = .05.

Report unfavorable values exactly.

Undefined results remain NOT_ESTIMABLE.

======================================================================
19. SECONDARY AND SENSITIVITY ANALYSIS
======================================================================

After primary results are locked, report:

S0–S4 coverage
erroneous automated incidence
review rate
abstention rate
false PASS
false FLAG
AUROC where meaningful
Brier/log loss for calibrated scores
certificate failures
evidence-verification failures
Assurance veto categories
schema failures
outcome observability
missingness.

Run prespecified sensitivity analyses.

Never replace the primary result with a favorable sensitivity result.

======================================================================
20. E5-P
======================================================================

Before E5-R outcome exposure where feasible, freeze the common E5-P scientific
core.

After E5-R is complete, do not silently redesign E5-P using E5-R results while
calling it independently confirmatory.

If E5-R findings motivate changes:

create a new prospective protocol identity and record:

E5R_OUTCOME_EXPOSED = true.

Activate prospective enrollment using the same point-in-time packet machinery.

For currently available future cases:

freeze predictions before outcome maturity.

Expected final state:

E5-P = ENROLLING

or

E5-P = WAITING_FOR_OUTCOMES.

======================================================================
21. DO NOT ACCEPT A FAKE "COMPLETION"
======================================================================

The following are NOT completion:

another readiness report

another blocker inventory

synthetic-only results

development-only results

mock LLM outputs represented as real Agent outputs

a cohort selected after inspecting outcomes

restated/latest financial data represented as point-in-time data

P1/P2 with zero actual companies

NOT_ESTIMABLE due to no execution

renaming BLOCKED to COMPLETE.

E5-R is complete only after real:

cohort
features
proposals
S0–S4 predictions
outcomes
primary analysis

exist.

======================================================================
22. FAILURE ESCALATION
======================================================================

For every failure:

attempt at least one legitimate alternative before stopping.

Examples:

Local SEC blocked
→ GitHub Actions acquisition.

Direct SEC ZIP blocked
→ official accession archive acquisition.

previous_270 missing
→ provably stronger non-overlap design.

V2 inference failure
→ pre-outcome statistical correction under new identity.

full suite unrelated HTTP hang
→ isolate and preserve trace; do not let unrelated hang prevent E5-specific
execution if E5-relevant suites pass.

Provider network failure
→ repair supported provider execution.

Never use a scientific shortcut solely to obtain completion.

======================================================================
23. TESTS
======================================================================

Maintain all existing E5 tests.

Add tests for all new execution stages.

At minimum verify:

cross-accession source substitution rejected
cross-CIK source substitution rejected
post-cutoff source rejected
restated/latest leakage rejected
historical overlap rejected
proposal generation only once
proposal identity equal across S2/S3/S4
provider/model/prompt drift rejected
calibration cannot see E5 labels
policy drift rejected
certificate mismatch rejected
outcome access before freeze rejected
canonical inference identity required
V1 cannot accidentally be used
V2 qualification identity required
cohort rerun deterministic
prediction rerun read-only/idempotent
final analysis reproducible.

======================================================================
24. GIT / CHECKPOINT DISCIPLINE
======================================================================

Stay on E5-experiment.

Commit coherent milestones.

Do not merge main.

Suggested sequence:

research(e5): bind authoritative point-in-time SEC corpus
research(e5): qualify raw proposal producer
research(e5): freeze development calibration and study policy
research(e5): qualify canonical V2 inference and power
research(e5): establish contamination-safe E5-R cohort
research(e5): freeze protocol cohort and feature packets
research(e5): execute and freeze S0-S4 predictions
research(e5): unlock outcomes and complete primary inference
research(e5): finalize E5-R audit and prospective E5-P launch

Push completed commits to E5-experiment.

======================================================================
25. REQUIRED FINAL STATE
======================================================================

Preferred:

E5-R = E5R_COMPLETE

E5-P = WAITING_FOR_OUTCOMES

At minimum E5-R completion requires:

protocol_identity != null
producer_identity != null
calibration_identity != null
study_policy_identity != null
cohort.final_n > 0
real_e5_cases_evaluated > 0
predictions frozen
outcomes accessed only after prediction freeze
P1 evaluated
P2 evaluated
family evaluated
complete_joint_qualification = COMPLETE
completion_claim = true

Do not set completion_claim=true unless these conditions are genuinely satisfied.

======================================================================
26. FINAL REPORT
======================================================================

Replace the current checkpoint report with a genuine completed empirical report
only after execution.

Report:

starting HEAD
final HEAD
all new commits

cohort window
candidate N
final N
VERIFIED N
events
non-events

historical-overlap method

producer/model identity
prompt identity
calibration identity
study-policy identity
protocol identity
V2 inference identity

S0–S4:
coverage
error incidence
review/abstain rate

P1:
error benefit + CI
coverage difference + CI
absolute coverage
component p-values
IUT p
Holm adjusted p
PASS/FAIL/NOT_ESTIMABLE

P2:
same fields

family conclusion

all integrity violations

proposal mismatch count

point-in-time violation count

certificate failure count

tests and CI

limitations

E5-P exact state.

Use the wording:

"Assurance benefit was not evaluated"

only if empirical execution genuinely remains impossible.

Do NOT use:

"E5-R established no empirical benefit"

when N=0.

======================================================================
27. FINAL DIRECTIVE
======================================================================

You already know why the previous run stopped.

Do not spend this run merely rediscovering those reasons.

Build the missing machinery.

Acquire the missing authoritative inputs.

Establish a valid independent cohort.

Qualify the actual producer.

Qualify calibration and study policy.

Finish V2 inference and power.

Freeze the experiment.

Run the experiment.

Analyze it.

Audit it.

Push the completed work.

The objective is not to produce a favorable E5 result.

The objective is to obtain the first genuine, reproducible, leakage-controlled
empirical E5 result supported by this repository.

Begin from commit:

38804c9649e8451b683f9f5f2d97d041e18e69cd

and continue autonomously until E5-R is empirically complete or a genuinely
external prerequisite remains that cannot be obtained by local execution,
GitHub Actions, repository data, or an authoritative public source.