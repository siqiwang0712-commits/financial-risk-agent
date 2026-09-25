# E4-S — POST-E4 Statistical Audit

Status: **COMPLETE** — audit of the frozen E4 primary inference, with no modification to any
frozen E4 artifact.

Scope: determine whether E4's P1 conclusion survives a correctly specified
correlated-model inference, and whether E4's own inference procedure tests the hypothesis
E4 attaches to it.

Nothing under `research/e4/` was regenerated or re-tuned. A SHA-256 manifest of every
published E4 artifact is recorded in `e4_frozen_artifact_manifest.json`, and
`tests/test_e4_statistical_audit.py::test_frozen_e4_artifacts_are_byte_identical` enforces
it.

---

## 1. Evidence labels used in this report

| Label | Meaning |
|---|---|
| `ORIGINAL_E4` | copied verbatim from a frozen E4 artifact |
| `POST_E4_STATISTICAL_AUDIT` | produced by this audit |
| `REPLICATION_COHORT_INFERENCE` | real paired data from an independent re-execution of the frozen pipeline, on a cohort that is ~94% but not fully overlapping with E4's |
| `SURROGATE_RECONSTRUCTION` | data reconstructed to match E4's published summary statistics |
| `NOT_INDEPENDENTLY_REPRODUCIBLE` | cannot be re-derived from published artifacts |

---

## 2. The central finding, stated precisely

**E4's primary p-value does not test `H0: AUROC(B6) = AUROC(B0)`.**

`e4_evaluation.paired_permutation` shuffles the outcome labels across observations while
keeping each observation's `(B0 score, B6 score)` pair fixed, then recomputes both AUROCs
and takes the difference. Its reference distribution is therefore the distribution of
`ΔAUROC` under

> **`H0_independence`**: the outcome is independent of **both** scores.

The hypothesis E4 attaches to that p-value is

> **`H0_equality`**: `AUROC(B6) = AUROC(B0)`.

`H0_independence` is strictly stronger than `H0_equality`: it implies equal AUROCs (both at
0.5) but is not implied by them. A rejection of `H0_independence` establishes only that *at
least one* score carries signal about the outcome. It does not establish that B6 carries
**more** signal than B0. As written, the inference is a non-sequitur.

This is proved mechanically, not asserted. The null distribution of the label-shuffling
design is a function of `(B0 scores, B6 scores, event count)` alone — it does not contain
the observed labels' association with the scores. Enumerating every label assignment on a
small dataset shows that two datasets sharing the score vectors and event count but
assigning labels in *opposite* orders produce **identical** null distributions, even though
their observed deltas differ by more than 0.05. See
`test_label_permutation_null_depends_only_on_scores_and_label_count`.

Two further properties of the published numbers:

- The published P1 permutation p-value is `0.0004997501249375312`, exactly `1 / (2000 + 1)`
  — the minimum attainable value with 2,000 permutations. Zero replicates reached the
  observed effect, so the published p-value is a **censored lower bound**, not a resolved
  quantity.
- The permutation null is **narrower** than the paired bootstrap distribution of the same
  statistic: implied SD `0.007723` versus `0.008785`, ratio `0.879`.

**What this finding is not.** It is not evidence that E4's conclusion is wrong, and it is
not evidence that the procedure is materially miscalibrated. §5 measures the calibration
directly and finds that, at E4's design point, the label-shuffling design's empirical size
is close to nominal. The defect is one of *logic and interpretability*, not of measured
error rate at this design point. Both statements are reported because both are true, and
reporting only the first would overstate the practical impact.

---

## 3. What could and could not be verified

`previous_270.json`, `research/e4/_artifacts/predictions.json`,
`research/e4/_artifacts/outcomes.json` and `research/e4/_artifacts/features.json` are not
published; only their SHA-256 values are. E4's exact 674 paired rows are therefore
`NOT_INDEPENDENTLY_REPRODUCIBLE`.

The single most consequential missing file is the 270-CIK exclusion set, pinned in
`backend/finrisk/e4_core.py` as
`PREVIOUS_270_SHA256 = "d73b371ccb026f556387cf6ff8ba204a4fde0664dcd780f099f12aa005e36603"`.
The repository contains no list of 200–400 CIKs anywhere, so it cannot be recovered from
what is published: it has to be released. `verify_previous_270.py` is the one-command path
for when it is — it checks a candidate against that frozen constant and, if genuine, runs
the frozen `build_cohort` to rebuild E4's exact cohort and report the true overlap with the
published replication cohort.

Rather than stop there, the audit re-executed the frozen v0.3.4 pipeline from public
inputs. Full detail in `HANDOVER_VERIFICATION.md`; essentials:

- All eight SEC FSDS archives and all three Zenodo files were re-downloaded and matched the
  frozen `data_hashes` / `ZENODO_MD5` **exactly**.
- The cohort algorithm was re-run with an empty 270-CIK exclusion — a documented,
  unavoidable deviation.
- `build_features` → `run_numeric` → `build_outcomes` ran unmodified.

| Quantity | E4 published | Re-execution |
|---|---:|---:|
| usable candidates | 3659 | 3888 |
| selected | 2000 | 2000 |
| `VERIFIED` | 674 | 675 |
| events | 235 | 235 |
| B0 AUROC | 0.6777 | 0.6791 |
| B6 AUROC | 0.7080 | 0.7054 |
| ΔAUROC | +0.0303 | +0.0264 |

Cohort overlap, measured by reproducing published packet hashes: **47 of 50** sampled E4-B
companies are present in the re-execution. The re-execution is a near-reproduction on a
~94%-overlapping cohort, **not** an independent sample. Its value is that it makes every
inference method computable on real data at E4's design point.

### 3.1 The audit publishes its own rows

An audit that criticises a study for reporting an inference whose input rows are
unpublished must not do the same thing. The re-execution's cohort, per-observation
predictions, labels and paired analysis rows are published under
`replication/`, with a SHA-256 manifest and a `replication/README.md` stating the
provenance and the deviation.

`verify_audit.py` is the artifact a reviewer runs. It re-checks the SHA-256 of every
published E4 artifact (proving this audit did not mutate E4), re-checks the SHA-256 of
every published replication artifact, and recomputes the marginal AUROCs, ΔAUROC, the
paired DeLong test, the 20,000-replicate BCa interval, the label-permutation null and the
score-swap null from the published rows, asserting each against
`replication_crosscheck.json`. It exits non-zero on any failure.

```
python research/e4_statistical_audit/verify_audit.py          # 20000 replicates
python research/e4_statistical_audit/verify_audit.py --quick  # 2000 replicates
```

The verifier writes `verification_result.json` by default. Use `--out <path>` to send it
elsewhere — the test suite does exactly that, so a quick run inside `pytest` cannot
silently replace the committed 20,000-replicate result with a 2,000-replicate one. A test
pins the committed file at 20,000 replicates.

Publishing the cohort with CIKs is deliberate: it makes the sample checkable against public
SEC filings, and it lets anyone holding the 270-CIK list reconstruct E4's exact cohort and
compute the true overlap rather than the 47/50 estimate.

---

## 4. Method cross-check on real paired data

`REPLICATION_COHORT_INFERENCE` — 675 paired observations, 235 events, one observation per
company. Source: `replication_crosscheck.json`.

### 4.1 Re-implementation validation

The audit re-implements every procedure from first principles. Fed the same rows, the frozen
routine and the audit implementation return **identical** observed deltas
(`delta_difference = 0.0`). Any divergence below is a genuine method difference, not a
re-implementation error.

### 4.2 Results

| Method | Null it actually tests | ΔAUROC | 95% interval | p | Valid? |
|---|---|---:|---|---:|---|
| E4 frozen `paired_delta` bootstrap (5,000) | equality (interval) | +0.02636 | [+0.01005, +0.04283] | — | yes |
| Audit cluster bootstrap, nearest-rank (20,000) | equality (interval) | +0.02636 | [+0.01039, +0.04298] | — | yes |
| Audit cluster bootstrap, linear (20,000) | equality (interval) | +0.02636 | [+0.01040, +0.04298] | — | yes |
| Audit cluster **BCa** bootstrap (20,000) | equality (interval) | +0.02636 | [+0.01114, +0.04383] | — | yes |
| **Paired DeLong** | **`H0_equality`** | +0.02636 | [+0.01015, +0.04257] | **0.001440** | **yes — prespecified target** |
| Score-swap randomization (20,000) | `H0_exch` (implies equality) | +0.02636 | null [−0.01853, +0.01835] | 0.004500 | yes, conservative |
| E4 frozen label permutation (2,000) | `H0_independence` | +0.02636 | — | 0.0014993 | wrong null |
| Audit label permutation (20,000) | `H0_independence` | +0.02636 | null [−0.01505, +0.01498] | 0.0007000 | wrong null |

PR-AUC, paired, same rows: ΔPR-AUC `+0.03958`, 20,000-replicate linear CI
`[+0.02062, +0.06171]`, BCa CI `[+0.01886, +0.05949]`.

### 4.3 Dispersion comparison

| Quantity | Value | Ratio to bootstrap SE |
|---|---:|---:|
| Bootstrap SE of ΔAUROC | 0.008269 | 1.000 |
| DeLong SE of ΔAUROC | 0.008272 | 1.000 |
| Label-permutation null SD | 0.007687 | 0.930 |
| Score-swap null SD | 0.009437 | 1.141 |

DeLong and the cluster bootstrap agree to three decimal places, which cross-validates both.
The label-permutation null is 7% narrower than the *bootstrap* SD — but the bootstrap SD is
estimated under the observed data-generating process, not under `H0_equality`, so this ratio
is not by itself a size calculation. §5 computes the size directly.

### 4.4 Verdict

**`CONSISTENT_SUPPORT`.**

Every method that is valid for the equality hypothesis rejects at α = 0.05, in the same
direction, with the same point estimate:

- DeLong p = 0.00144;
- BCa interval lower bound +0.01114 > 0;
- score-swap randomization p = 0.00450.

No method conflicts, so the prespecified method-sensitivity rule returns
`CONSISTENT_SUPPORT`, not `METHOD_SENSITIVE`.

**E4's P1 direction is additionally supported by a correctly specified inference — on a
near-reproduction of the E4 cohort, not on E4's exact rows.**

---

## 5. Method calibration: does the implemented test control its size?

The cross-check shows the implemented permutation test *happened* to agree with DeLong. The
calibration study asks whether it *generally* does, by simulating `H0_equality` with
informative scores at E4's design (n₁ = 235, n₀ = 439, common AUROC 0.6777, score
correlation 0.92) and measuring each procedure's empirical rejection rate.

Source: `method_calibration.json`. Nominal α = 0.05, 200 replicates. The Monte Carlo standard
error of a rate near 0.05 is about 0.015, so rates are resolved to roughly ±0.03 at 95%
confidence.

| Scenario | DeLong | label permutation (as implemented) | score-swap randomization |
|---|---:|---:|---:|
| **`H0_equality`**, both AUROC = 0.6777 (the hypothesis E4 states) | **0.025** | **0.025** | 0.035 |
| `H0_independence`, both AUROC = 0.5000 (the hypothesis E4's test actually samples) | 0.075 | 0.075 | 0.075 |
| Alternative at the E4 effect, ΔAUROC = 0.0303 (power) | 0.935 | 0.930 | 0.935 |

### The finding is a null result, and it is reported as one

The audit's prior expectation was that the label-shuffling design would be materially
**anti-conservative** under `H0_equality`, on the grounds that its null is narrower than the
paired bootstrap distribution at E4's design point. **The simulation does not support that
expectation.** The measured size is 0.025 — below nominal, and within Monte Carlo error of
it. Power at the E4 effect is 0.930, versus DeLong's 0.935.

So the honest conclusion has two parts, and they must be stated together:

1. **The procedure is the wrong test.** It does not target the equality null, and its
   p-value cannot be used to support a directional claim. This is a logical defect, and it
   is what the E5 protocol fixes.
2. **At E4's design point it is not materially miscalibrated.** Its rejection rate under the
   equality null is close to nominal, and its power matches DeLong's. E4's numerical
   conclusion is therefore not affected by the defect.

The distinction matters for E5: a procedure that happens to be accurate at one design point
is not a procedure that can be relied upon at another, and the correct fix is still to use a
test that targets the hypothesis.

### Caveat on the calibration model

The calibration study generates scores from a bivariate normal model. §6 shows that this
model cannot reproduce E4's published dispersion pattern, which indicates E4's real score
distribution has a different variance structure (most likely ties, discreteness, or bounded
range). The calibration result is therefore **model-dependent** and should be read as "not
materially miscalibrated under a Gaussian score model", not as a universal guarantee.

---

## 6. Surrogate reconstruction

Because E4's exact rows are unpublished, a paired sample was reconstructed whose AUROCs
match E4's published point estimates exactly and whose dispersion was fitted to E4's
published bootstrap and permutation intervals. Source: `paired_auc_inference.json` →
`surrogate`.

| Quantity | E4 published | Surrogate |
|---|---:|---:|
| B0 AUROC | 0.6776523045606553 | 0.677647457955702 |
| B6 AUROC | 0.7079581253332041 | 0.7079581253332041 |
| ΔAUROC | +0.03030582077254884 | +0.0303106673775021 |
| paired bootstrap implied SD | 0.008785 | 0.007971 (9.3% low) |
| permutation null implied SD | 0.007723 | 0.008193 (6.1% high) |
| dispersion ratio (perm / bootstrap) | 0.879 | 1.028 |

Selected input correlation 0.94 (realised 0.9447). On this surrogate:

| Method | ΔAUROC | 95% interval | p |
|---|---:|---|---:|
| cluster bootstrap, linear (20,000) | +0.03031 | [+0.01524, +0.04575] | — |
| cluster **BCa** bootstrap (20,000) | +0.03031 | [+0.01532, +0.04592] | — |
| **paired DeLong** | +0.03031 | [+0.01491, +0.04571] | 0.0001147 |
| score-swap randomization (20,000) | +0.03031 | — | 0.0000500 (floor) |
| label permutation (20,000) | +0.03031 | — | 0.0002000 |

Verdict: `CONSISTENT_SUPPORT`.

### The surrogate is a weaker instrument than hoped, and that is itself a result

The surrogate **cannot** reproduce both published dispersion statistics at once: the target
ratio of permutation-null SD to bootstrap SD is 0.879, but a bivariate normal score model
produces a ratio above 1.0 across the whole correlation grid searched. The fit therefore
trades one gap against the other (9.3% low on one, 6.1% high on the other).

Consequence: the surrogate's DeLong p-value (`0.000115`) is more extreme than E4's
permutation p-value (`0.000500`), because the fitted correlation is higher than the
published dispersion implies. **The surrogate must not be quoted as E4's DeLong result.** Its
role is to confirm that the *direction* and the *ordering of methods* are stable; the
load-bearing quantitative evidence in this audit is §4, which uses real data.

The inability to match the dispersion pattern is also a positive diagnostic: it says E4's
B0/B6 scores are not well described by a Gaussian copula, which is worth knowing before any
future study reuses them for power planning.

---

## 7. Calibration cross-check

E4's post-hoc audit published descriptive calibration diagnostics and the project uses them
as evidence that every score is `UNCALIBRATED`. Source: `calibration_crosscheck.json`.
E4's figures are on its own 674 verified observations; the audit recomputes them on the
published 675-observation replication cohort.

| Diagnostic | E4 (n = 674) | Replication (n = 675) |
|---|---:|---:|
| B0 ECE | 0.16724 | 0.16985 |
| B6 ECE | 0.12956 | 0.12788 |
| B0 Brier | 0.22810 | 0.22638 |
| B6 Brier | 0.20870 | 0.20814 |
| B0 calibration-in-the-large | −0.06976 | −0.06640 |
| B6 calibration-in-the-large | −0.07878 | −0.07532 |
| B0 calibration slope | 0.06109 | 0.05802 |
| B6 calibration slope | 0.09096 | 0.08467 |

Every figure reproduces to within about 0.006, so E4's published calibration diagnostics
are confirmed.

### 7.1 The calibration slope is converged but ill-conditioned — do not lead with it

A slope of 0.06 alongside an AUROC of 0.68 looks contradictory, and the obvious suspicion is
that E4's hand-rolled optimiser (`e4_posthoc._calibration_slope`: 1500 fixed-rate gradient
steps, no convergence test) had not converged. **It had.** The gradient norm at the frozen
solution is `3.09e-05` (B0) and `2.73e-05` (B6), and an independent Newton–Raphson (IRLS) fit
agrees with the frozen slope to four decimal places (`ratio = 0.99983` / `0.99986`). The
published slope is a real fit.

It is nonetheless a **poor diagnostic for these scores**, and the audit recommends not
leading with it. The reason is visible in the score support:

| | B0 | B6 |
|---|---:|---:|
| distinct score values | **11** | 39 |
| observations at score exactly 0 | 285 / 675 | 175 / 675 |
| event rate at score 0 | **26.0%** | **22.3%** |
| reliability curve monotone? | **no** (4 drops) | **no** (2 drops) |
| top-bin event rate vs the bin below | 0.632 vs 0.713 | 0.643 vs 0.806 |

B0 is a mean of five threshold breaches, so it takes only eleven distinct values and puts
42% of the sample at exactly zero — where the event rate is 26%, not 0%. A single
logistic-linear recalibration cannot represent a coarse step function whose mass sits at an
extreme with a non-zero response rate, so the fitted slope collapses towards zero even though
the score ranks well. The slope is measuring the inadequacy of the recalibration model, not
the absence of signal.

### 7.2 What the evidence for `UNCALIBRATED` actually is

The defensible, easily-communicated facts are these, and they are stronger than the slope:

1. **A score of zero does not mean no risk.** 285 of 675 companies scored exactly 0 on B0,
   and 26.0% of them deteriorated within the window. For B6 it is 22.3%.
2. **The reliability curve is non-monotone.** For B0 the highest bin has a *lower* event rate
   (0.632) than the bin below it (0.713), so a higher score is not monotonically more risky.
3. **Mean score sits below prevalence**: 0.2818 vs 0.3487 (B0) and 0.2728 vs 0.3487 (B6), so
   both scores systematically understate the base rate.
4. **ECE is large**: 0.170 (B0) and 0.128 (B6).

Nothing here calibrates anything, and the replication *strengthens* rather than weakens the
project's `UNCALIBRATED` position. The finding is about which number to cite: the slope is
the one most likely to be misread, and the support diagnostics are the ones that carry the
argument.

---

## 8. Findings register

| ID | Severity | Finding | Fixable now? |
|---|---|---|---|
| E4S-01 | **MAJOR** | `paired_permutation` tests `H0_independence`, not `H0_equality`; its p-value cannot support the directional claim attached to it. Proved mechanically. Empirically not materially miscalibrated at E4's design point (§5). | yes — use DeLong (done for E5) |
| E4S-02 | **MAJOR** | Published P1 p-value equals the attainable floor `1/2001`; it is a censored bound, not a resolved quantity | yes — raise replicate count |
| E4S-03 | **MAJOR** | E4's exact 674 paired rows and `previous_270.json` are unpublished; P1 is `NOT_INDEPENDENTLY_REPRODUCIBLE` | yes — publish the artifacts |
| E4S-04 | **MAJOR** | E4's outcome stage requires an undocumented `FINRISK_SEC_MAX_ARCHIVE_MEMBER_BYTES` override; the frozen default (256 MB) rejects the 500–600 MB `num.txt` members | yes — freeze environment variables |
| E4S-05 | **MAJOR** | The E4 harness (`backend/finrisk/e4_*.py`, `scripts/run_e4*.py`) does not exist at the locked commit `4273b070`; it has no versioned identity predating the results | partially — tag the harness |
| E4S-06 | MODERATE | The inference code path has **no unit tests**: `tests/test_e4.py` exercises no permutation, bootstrap, DeLong or Holm behaviour, only the claim gate on synthetic dicts | yes — this audit adds them |
| E4S-07 | MODERATE | `paired_delta` collapses companies into a dict keyed by `masked_company_id`, silently dropping observations if a company ever has more than one; harmless in E4 (1:1) but a latent defect | yes — assert one row per cluster |
| E4S-08 | MODERATE | E4's score distribution is not well described by a Gaussian copula: its published dispersion ratio (permutation null / bootstrap) cannot be reproduced by that model at any correlation | no — informational; affects future power planning |
| E4S-09 | MINOR | E4's bootstrap uses a nearest-rank percentile; the standard is linear interpolation. The two differ measurably at 5,000 replicates | yes — report both |
| E4S-10 | MINOR | With `core.autocrlf=true`, a Windows checkout produces CRLF working-tree copies of `research/e4/public/*.json` and `research/e4/protocol/*`, which carry no `eol=lf` attribute (unlike `research/results/public_v1/*`) | yes — extend `.gitattributes` |
| E4S-11 | MODERATE | The published calibration slope (0.061 / 0.091) is a converged but **ill-conditioned** diagnostic for these scores: B0 takes 11 distinct values with 42% of mass at exactly 0, where the event rate is 26%. Cite the support diagnostics and ECE/CITL instead — the slope invites the misreading that the score carries no signal | yes — this audit adds the support diagnostics |

A hypothesis the audit tested and **did not** confirm is recorded rather than dropped: the
expectation that the implemented permutation test would be materially anti-conservative is
not supported (§5).

Findings E4S-01, E4S-02, E4S-04, E4S-05, E4S-06 and E4S-10 are carried into the E5 protocol
package as explicit requirements.

---

## 9. What this means for E4 and for E5

**For E4.** The narrow P1 claim survives, and now on three independent footing: the frozen
bootstrap, a 20,000-replicate BCa bootstrap, and a paired DeLong test — all on real data at
E4's design point, all agreeing on direction with ΔAUROC ≈ +0.026 to +0.030.

E4's *conclusion* is sound. E4's *stated justification* is not: the p-value it relies on
tests a different null, and it is censored at the floor. E4's inference is also not
independently reproducible, and its outcome stage requires an undocumented environment
override.

**For E5.** Three changes are mandatory and are now in the protocol:

1. the primary test is paired DeLong; the label-permutation design is reported only under
   its own null (`INFERENCE_POLICY.md`);
2. `previous_270.json` must be published before the cohort freeze, and every
   result-affecting environment variable must be frozen (`STUDY_PROTOCOL.md` §15);
3. the harness must be committed and tagged before the cohort exists, in the nine-stage
   sequence of `GOVERNANCE_WORKFLOW.md`.

---

## 10. Limitations of this audit

- The real-data cross-check runs on a **~94%-overlapping cohort**, not on E4's exact rows.
  Its point estimate (+0.02636) differs from E4's published +0.03031 by 0.004, which is well
  inside sampling noise but is not zero.
- The overlap figure is itself an estimate: it is measured on the 50 E4-B companies, which
  is a hash-selected subset of the 2,000 and therefore unbiased but small (47/50 gives a 95%
  interval of roughly 83% to 99%). The exact overlap cannot be computed without the
  270-CIK list.
- The audit's own numbers are reproducible from the published rows via `verify_audit.py`,
  but that only makes the audit checkable — it does not make E4's rows available.
- The calibration study is Monte Carlo with 200 replicates, so rates are resolved to about
  ±0.03 at 95% confidence. It cannot detect small deviations from nominal.
- The calibration study and the surrogate both assume a bivariate normal score model, which
  §6 shows does not match E4's published dispersion. Both are therefore model-dependent.
- The surrogate reconstruction is a model of E4's data, identified by two dispersion
  constraints that it cannot satisfy simultaneously. It is diagnostic, not confirmatory.
- The audit does not re-derive E4's outcome labels, does not attempt to reproduce the Agent
  arm (E4-B), and makes no claim about the Codex comparator.
- No calibration claim is made anywhere: every E4 score remains `UNCALIBRATED`.
- The calibration cross-check confirms E4's published figures but recommends replacing the calibration *slope* with the support diagnostics when making the `UNCALIBRATED` case (§7).

---

## 11. Artifacts

| File | Contents |
|---|---|
| `AUDIT_REPORT.md` | this report |
| `HANDOVER_VERIFICATION.md` | claim-by-claim verification of the handover brief |
| `verify_audit.py` | the verifier a third party runs: re-checks every hash and recomputes the real-data inference |
| `verify_previous_270.py` | one-command path to verify a candidate 270-CIK list and rebuild E4's exact cohort |
| `verify_previous_270.py` | one-command path to verify a candidate 270-CIK list and rebuild E4's exact cohort |
| `verification_result.json` | the verifier's own output |
| `paired_auc_inference.json` | original E4 values, internal-consistency checks, surrogate reconstruction, reproducibility blocker |
| `bootstrap_diagnostics.json` | replicate counts, percentile conventions, Monte Carlo precision |
| `inference_crosscheck.json` | method-by-method verdict table and the `CONSISTENT_SUPPORT` determination |
| `method_calibration.json` | empirical size and power of each procedure under `H0_equality` |
| `replication_crosscheck.json` | all methods on the independent re-execution's real paired data |
| `calibration_crosscheck.py` | recomputes E4's calibration diagnostics and diagnoses the score support |
| `calibration_crosscheck.json` | E4's published calibration figures beside the replication's, plus the support diagnostics and the converged-optimiser check |
| `replication/` | the published cohort, features, predictions, labels, paired analysis rows and manifest, plus `README.md` |
| `e4_frozen_artifact_manifest.json` | SHA-256 of every published E4 artifact, proving non-mutation |
| `e4s_stats.py` | independent statistical primitives |
| `method_calibration.py` | generators, size/power study, dispersion matching |
| `run_e4_statistical_audit.py` | the runner that produces the artifacts above |
| `tests/test_e4_statistical_audit.py` | primitives, DeLong, bootstrap, both permutation designs, the deterministic null-invariance proof, replication reproduction, and artifact integrity |
