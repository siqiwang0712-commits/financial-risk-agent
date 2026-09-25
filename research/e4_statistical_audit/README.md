# E4-S — POST-E4 Statistical Audit

**Status: `POST_E4_STATISTICAL_AUDIT`**

E4-S is a **retrospective** audit of E4's primary inference. It re-reads what E4 published and
re-runs the frozen v0.3.4 pipeline from public inputs. It is **not** `ESTABLISHED_E4`, **not**
`CONFIRMATORY`, **not** a new result, and **not** an independent sample.

- it does **not** modify E4 — a SHA-256 manifest of every published E4 artifact is recorded and
  enforced, so no frozen artifact can move without failing the suite;
- it does **not** re-derive outcomes, re-tune thresholds or re-fit anything;
- it does **not** upgrade E4's claim. The narrow P1 conclusion survives; the *justification*
  E4 attaches to it does not.

> **Question.** Does E4's P1 conclusion survive a correctly specified correlated-model
> inference, and does E4's own inference procedure test the hypothesis E4 attaches to it?

---

## Run it

```bash
# full audit verifier: re-check every hash, then recompute the real-data inference
python research/e4_statistical_audit/verify_audit.py

# the same checks at 2,000 replicates instead of 20,000
python research/e4_statistical_audit/verify_audit.py --quick

# only once a candidate 270-CIK exclusion list exists
python research/e4_statistical_audit/verify_previous_270.py
```

`verify_audit.py` writes `verification_result.json` by default. Use `--out <path>` to send it
elsewhere: a quick run inside `pytest` must never silently replace the committed
20,000-replicate result with a 2,000-replicate one, and a test pins the committed file at
20,000 replicates.

Extra dependencies: none. `e4s_stats.py` is deliberately pure Python (no SciPy) so the audit
runs wherever the product runtime runs.

---

## Source

The audit needs E4's paired rows, and E4 never published them. It therefore does two things.

1. **It names the blocker instead of working around it.** `research/e4/_artifacts/*.json` and
   `research/e4/_cache/previous_270.json` are unpublished — only their SHA-256 values are
   pinned. E4's exact 674 paired rows are `NOT_INDEPENDENTLY_REPRODUCIBLE`, and
   `verify_previous_270.py` is the one-command path for whoever releases the 270-CIK list.
2. **It re-executes the frozen pipeline from public inputs and publishes its own rows.** The
   eight SEC FSDS archives and three Zenodo files were re-downloaded and matched the frozen
   hashes exactly; the cohort algorithm ran with an empty 270-CIK exclusion (a documented
   deviation); `build_features` → `run_numeric` → `build_outcomes` ran unmodified.

An audit that criticises a study for reporting an inference whose input rows are unpublished
must not do the same thing, so the re-execution's cohort, predictions, labels and paired
analysis rows ship under `replication/` with their own manifest.

**Cohort:** `VERIFIED` rows from the re-execution — **n = 675**, **235 events**, one
observation per company, **~94% overlapping** with E4's 674. It is a near-reproduction, not
an independent sample.

---

## Files

| File | Contents |
|---|---|
| `README.md`, `AUDIT_REPORT.md` | this page and the audit itself |
| `HANDOVER_VERIFICATION.md` | claim-by-claim verification of the handover brief |
| `verify_audit.py`, `verification_result.json` | the verifier a third party runs, and its output |
| `verify_previous_270.py` | verifies a candidate 270-CIK list and rebuilds E4's exact cohort |
| `inference_crosscheck.json` | method-by-method verdict table and the `CONSISTENT_SUPPORT` determination |
| `paired_auc_inference.json` | E4's published values, internal-consistency checks, surrogate reconstruction, the reproducibility blocker |
| `bootstrap_diagnostics.json` | replicate counts, percentile conventions, Monte Carlo precision |
| `method_calibration.json`, `method_calibration.py` | empirical size and power of each procedure under `H0_equality` |
| `replication_crosscheck.json` | every method on the real paired data of the re-execution |
| `calibration_crosscheck.json`, `calibration_crosscheck.py` | E4's published calibration figures beside the replication's, plus the score-support diagnostics |
| `aggregation_equivalence.json`, `aggregation_equivalence.py` | the Agent outputs joined to the replication cohort, and the outcome-free aggregation-equivalence diagnostic |
| `replication/` | the published cohort, features, predictions, labels, paired analysis rows, manifest and `README.md` |
| `e4_frozen_artifact_manifest.json` | SHA-256 of every published E4 artifact, proving non-mutation |
| `e4s_stats.py` | independent statistical primitives |
| `run_e4_statistical_audit.py` | the runner that produces the artifacts above |
| `tests/test_e4_statistical_audit.py` | primitives, DeLong, bootstrap, both permutation designs, the deterministic null-invariance proof, replication reproduction and artifact integrity |

---

## Reading the result

Start with `AUDIT_REPORT.md`. Three things about it:

- the **finding** is that E4's primary p-value tests `H0_independence`, not
  `H0_equality`, and is censored at the attainable floor `1/2001` — the inference is a
  non-sequitur, and that is proved mechanically rather than asserted;
- the **counter-finding** is reported with the same weight: at E4's design point the
  procedure's empirical size is 0.025 against a nominal 0.05 and its power is 0.930 against
  DeLong's 0.935, so E4's *numbers* are unaffected. The defect is one of logic and
  interpretability, not of measured error rate at this design point;
- every number carries an evidence label — `ORIGINAL_E4`, `POST_E4_STATISTICAL_AUDIT`,
  `REPLICATION_COHORT_INFERENCE`, `SURROGATE_RECONSTRUCTION` or
  `NOT_INDEPENDENTLY_REPRODUCIBLE` — so a reader can tell a reproduction from a model.

Two structural facts are worth knowing before reading any number:

1. **The real-data cross-check is the load-bearing evidence.** Every valid test rejects in the
   same direction with the same point estimate (ΔAUROC ≈ +0.026): DeLong p = 0.00144, BCa
   lower bound +0.01114, score-swap p = 0.00450. The surrogate reconstruction cannot match
   both of E4's published dispersion statistics at once, so its DeLong p is **not** quoted as
   E4's result.
2. **The calibration slope is converged but ill-conditioned.** A slope of 0.06 with an AUROC
   of 0.68 looks like a non-converged optimiser; it is a real fit (gradient norm ≈ 3e-05, IRLS
   agrees to four decimals) and a poor diagnostic for a coarse score whose mass sits at
   exactly zero with a 26% event rate. The audit recommends citing the support diagnostics
   instead, and the finding is recorded either way.

---

## Where this fits

E4-S is the middle link of the post-hoc chain. It reads E4, and the E4-R robustness study
reads *it* — E4-R's entire cohort is E4-S's published replication packet, which is what makes
E4-R's numbers independently checkable at all.

| Step | Study | Directory |
|---|---|---|
| 1 | E4 — external validation | [`research/e4/`](../e4/public/VALIDATION_REPORT.md) |
| 2 | E4 post-completion audit | [`research/e4_posthoc/`](../e4_posthoc/AUDIT_REPORT.md) |
| 3 | **E4-S — statistical audit** | this directory |
| 4 | E4-R — automated robustness and competitive baselines | [`research/e4r_automated_robustness/`](../e4r_automated_robustness/FINAL_REPORT.md) |
| 5 | E5 — confirmatory study | [`research/e5/`](../e5/README.md) |

The project-level index of that chain is
[`research/EXPERIMENT_OVERVIEW.md`](../EXPERIMENT_OVERVIEW.md).
