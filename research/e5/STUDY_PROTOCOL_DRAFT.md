# E5 — Prospective Validation of Assured Selective Financial Decisions

Status: **DRAFT_NOT_FROZEN — AUTHORITATIVE E5 STUDY CONTRACT**

`E5_PROTOCOL_FREEZE_ALLOWED = false`

Design readiness: **BLOCKED**, not PROTOCOL_FROZEN. This is the human authority;
[`experiment_config.json`](experiment_config.json) is its machine companion and
[`harness/e5_harness.py`](harness/e5_harness.py) is the active stage implementation.
The [Constitution](autonomy/E5_CONSTITUTION.md) constrains all design changes.
Legacy [`protocol/`](protocol/) mechanics apply only when explicitly re-adopted
below. Their B6/A2/fixed-Hybrid hypotheses cannot acquire freeze authority.

## 1. Scientific question and success

Does Full Assurance improve selective **authorization quality**, while retaining
useful decision coverage, beyond a strong simple selective predictor and beyond
evidence verification alone? Success means correct execution, not a favorable
result. Null and negative conclusions must remain possible without protocol change.
Ranking, calibration, selective behavior, source support and authorization are
separate constructs. This study concerns forward financial deterioration, not
bankruptcy/default/credit loss, fraud, investment advice or production safety.

All scores remain **UNCALIBRATED**. No probability interpretation or confirmatory
calibration claim is permitted. Historical performance is design-exposed development,
not E5 evidence; missingness signal must not become financial severity.

## 2. Exact arm responsibilities

### S0 — Strong Tabular Predictor

Adopt the existing fitted StrongTabularReference-v1 artifact, rather than refitting
or reselecting it. Its fitted identity is
`3e1ebd825f1699bcc88e52a531bf9199aad3e93a671cfe28640f15dd33759a26`.
The [candidate identity record](autonomy/design_identities.json) binds schema,
ordered VO features, fitted preprocessing/model, exact hyperparameters, environment,
source config and historical manifests. This is
`DESIGN_EXPOSED_HISTORICAL_DEVELOPMENT`, not an E5 freeze or prospective evidence.
All 2,000 development source companies remain future exclusions. Artifact loading
requires trusted hash verification and qualification replay in the recorded runtime.
S0's score is in [0,1], with the historical 0.5 classification threshold, no Assurance
and no system final-authorization authority.

### S1 — S0 + Simple Selective Policy

Use exactly S0's score and the already-prespecified historical
`s1-fixed-review-band-v1`: score >=0.65 issues FLAG, score <0.35 issues PASS,
otherwise REVIEW. Adopt the existing development rule without threshold search,
new fitting, E5 data or favorable-result selection. Selection procedure: retain this
predeclared rule verbatim, verified against
`strong_tabular_reference/development_run_config.json`. This serious comparator
issued decisions on 562/675 historical rows; that recorded rate is descriptive,
not a target or E5 performance prediction. S1 study issuance is not product Assurance.

### S2 — Frozen Full Prediction-Layer Proposal

S2 must produce one score and proposal from the intended deterministic metrics,
rules, models, fusion and a qualified Agent if justified. It has no final authority.
**E5-P02 remains open:** the released Agent verifies claims *before* fusion and
failure review; its output cannot honestly be relabelled a raw no-verification arm.
Exact structured producer/model/prompt and evidence-independent extraction boundary
remain unresolved. No legacy A2/Hybrid is substituted.

### S3 — Same Proposal + Evidence Verification Only

Consume the exact immutable S2 proposal, adding source/path verification and a
separate evidence-only routing record. No fragility, reference validity, full policy
or certificate-bound final authorization may enter this intervention. It is not
allowed to recompute or replace S2's score/proposal. Its producer and routing
qualification remain blocked with E5-P02.

### S4 — Same Proposal + Full Assurance

Consume the same S2 proposal and apply released v0.4.2 evidence assurance,
deterministic fragility, reference/distribution checks, admission policy and content-
addressed Decision Certificate. Bind the released policy
`assurance-policy-v0.4.0-development`, HEURISTIC_POLICY, certificate schema
`decision-certificate-v0.4` and verifiers through candidate source hashes.
Legacy bundles never gain v0.4 authority; changed material inputs invalidate replay.

**E5-P01:** the adopted heuristic, uncalibrated policy cannot allow automation.
RESTRICTED PASS/FLAG are not automated authorized decisions. Do not remove the
policy maturity/calibration gates, or count such outputs as automated to obtain
coverage. This blocks a useful-automated-coverage confirmatory design as stated.

### Shared proposal contract

`Proposal_S2 == Proposal_S3 == Proposal_S4` means byte-identical canonical JSON of
case ID, input identity, producer identity, score and proposed disposition. Unknown
fields, nonfinite values and bool-as-number are rejected. The shared-packet guard
is mechanically tested. It **does not** qualify a producer or prove scientific
ablation isolation; the actual three-arm runtime invariant is NOT_ESTABLISHED.
The nearest clean equivalent is one approved producer executed once, followed by
immutable packet fan-out and separately recorded interventions. No such producer
is silently installed or claimed qualified here.

## 3. Primary estimand and inference

P1 = S4 vs S1; P2 = S4 vs S3. Both use comparator-minus-S4 erroneous automated
issuance incidence on the **same common VERIFIED-endpoint cases**, including
withheld cases in the denominator. Numerator: an automated PASS with event=1 or
automated FLAG with event=0. Withholding has no issuance incident; it is **not a
correct prediction**. Primary coverage is automated issued decisions divided by
all eligible feature-complete paired cases, including cases without outcomes.
Report both denominators and attrition explicitly.

Missing/review/insufficient outcomes never become negative labels. Exclude them
from the primary incident denominator; report missingness, reasons and prespecified
worst-case incidence bounds (each missing label adverse vs nonadverse) over the
full paired population. This does not remove verification-selection bias.

Use paired company mean differences, one independent case per company, 20,000
company-paired bootstrap replicates, seed 20261019, BCa intervals. For one-sided
primary tests use null-centered paired bootstrap with plus-one p-values. Covariate
or arm-specific resampling is forbidden. Each primary requires BOTH error benefit
and coverage noninferiority/useful coverage. The intersection-union p-value is the
maximum of its safety and coverage p-values. Holm step-down across P1/P2 controls
family-wise alpha=0.05. Zero variance, empty denominators, undefined BCa acceleration
or insufficient paired support means NOT_ESTIMABLE, never significance or success.
Minimum error benefit, coverage margin and useful absolute coverage remain **E5-P03**;
without independent utility/capacity evidence no arbitrary defaults are inserted.
The exact inferential null boundaries therefore cannot yet be executed or frozen.
See [inference design](autonomy/INFERENCE_DESIGN.md).

AUROC/PR-AUC and prevalence are secondary, paired DeLong only on common cases with
both classes and comparable scores. Also report selective error, review/abstain,
risk/error–coverage, fixed-review-budget event capture, evidence paths, unsupported
issuance and out-of-reference authorization. All-abstain selective error is
NOT_ESTIMABLE. Secondary/POST_HOC results cannot rescue failed primaries.
B0/B6 are historical anchors only; no all-pairs primary family is restored.

## 4. Power and eligibility

The [analytic planning artifact](power_plan.json) replaces the AUROC-centric basis.
It covers prevalence, evaluable coverage, schema attrition, paired error discordance
and effect grids; it contains no simulated E5 outcomes. Its normal-approximation
paired safety bounds are **not joint primary power**, selected effects or a final N.
Compare the existing 1200–1500 intention with each grid row; do not preserve it
blindly. Final N is blocked pending joint safety/coverage feasibility and E5-P03.
At least 100 actually paired VERIFIED positives is a future inference gate, not
permission to recruit additional companies after seeing outcomes.

Candidate eligibility design (timing qualification is E5-P04): original 10-K filings, first per CIK; exclude SIC 6000–6999
because the adopted feature/model scope is nonfinancial. Prediction cutoff is the
filing's UTC acceptance timestamp. Window: the first 12 calendar months starting at
the next UTC quarter after protocol freeze. The deterministic sampling order is
SHA256(salt, CIK, accession), one case per company, no discretionary strata. Salt
is derived from the frozen protocol hash, released-source identity and literal
`E5-company-order-v1`; it is determined before enumeration. N remains blocked.
CIK/accession, fixed schema, source hashes, units/periods and availability-by-cutoff
are required. Latest/restated-after-cutoff values cannot backfill features.
These rules do not qualify a prospective extractor or timing feasibility. The
twelve-month collection window needs explicit per-company prediction deadlines and
verified ordering so early cases cannot expose outcomes before prediction freeze.
No rolling/global-freeze equivalence is assumed; E5-P04 remains open.

## 5. Endpoint, reference and exclusions

Adopt `sec_bulk.build_deterioration_labels`,
`deterministic_forward_outcome_rule_v1`, calendar-12-month horizon via
`add_twelve_months`, anchored to filing acceptance. Positive: at least two verified
adverse conditions; a negative needs sufficient known conditions to rule out two.
The historical E4 fixed-archive/date wrapper is not adopted. Raw
REQUIRES_HUMAN_REVIEW maps explicitly to REQUIRES_REVIEW; INSUFFICIENT_DATA stays
unknown. Later adjudication uses two independent blinded reviewers and a third
adjudicator (the legacy adjudication *mechanics* are re-adopted, not its study arms).
No actual reviewer, annotation or outcome is created now.

The historical empirical profile is label-independent but development-only. It is
not in the runtime profile representation or externally validated. Do not relabel it
VALIDATED_EXTERNAL or install the synthetic fixture as an E5 reference. Exact
reference/extraction conformance and applicability scope remain E5-P04.

[Historical exclusion registry](autonomy/historical_exclusions.json) binds sources,
not a future cohort. The missing exact `previous_270.json` is **E5-C01, cohort-freeze
only**, never a protocol-readiness blocker by itself. Resolution: exact original
with pinned provenance/hash, or a proven immutable containing superset; otherwise
cohort freeze fails closed. No containing-superset proof is currently available.
Qualification/prior-validation exclusions must also be complete before enumeration.

## 6. Isolation, qualification, TEVV and amendments

Protocol/prediction/outcome processes require separately controlled storage and
mounts. File-absence guards cannot prove container isolation; future execution also
requires independently reviewed mount/network isolation and no web/outcome tools.
Stable weights/tokenizer/prompt/runtime identities, single-company context, schema
and ID integrity, deterministic retry/recovery, hardware feasibility and replay
must pass the [qualification contract](agent_selection_protocol.md) before model
qualification. A mutable provider alias is not a stable identity.

The separate [TEVV contract](autonomy/TEVV_CONTRACT.md) is prepared, not executed.
E5-Narrative retains separate protocol/config/corpus/metrics/claims and blinded
annotation with planted-defect evaluator validation; neither study validates the other.

The Constitution defines explicit exposure-classified content-addressed amendments.
Scientific change after prediction freeze invalidates affected confirmatory identity.
A negative result never authorizes retuning or primary-family promotion.

## 7. Governance and present decision

The nine existing harness stages remain unchanged. The autonomy lifecycle adds
WAITING_FOR_OUTCOMES and independent AUDIT_COMPLETE gates as future governance
requirements; it does not fabricate corresponding manifests or change old sequence
numbers. Every future stage must be ordered, chained and immutable. Damaged or
unknown manifests are errors, not absence. The current mandate cannot write an
actual freeze or advance beyond READY_TO_FREEZE.

Resolved: authority; historical S0 binding; existing S1 rule; E5 UNCALIBRATED;
released policy/certificate bindings; P1/P2 estimand/denominator, alpha and method;
endpoint adoption; deterministic eligibility/sampling design; planning sensitivity;
amendment and future qualification/TEVV contracts. Unresolved: E5-P01/P02/P03/P04.
Readiness is **BLOCKED**, honestly; no effect, reference or model is invented.

```text
STUDY CONTRACT: BLOCKED / DRAFT_NOT_FROZEN
PROTOCOL FREEZE: NOT_EXECUTED
COHORT: NOT_ENUMERATED
PREDICTIONS: NOT_GENERATED
OUTCOMES: NOT_ACCESSED
CALIBRATION: UNCALIBRATED
E5 VALIDATION: NOT_ESTABLISHED
```
