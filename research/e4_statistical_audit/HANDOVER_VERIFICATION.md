# Handover Verification Register

Every figure and structural claim in the handover brief was checked against the repository.
The repository is treated as the source of truth; where the two disagree, the repository
wins and the disagreement is recorded below.

Repository state at verification: `HEAD = e2d4133e34134254755e68072d2567928b1ed49a`
(2026-09-25T03:34:46Z), default branch `main`, 87 commits reachable.

---

## 1. Confirmed as stated

| Handover claim | Repository value | Verdict |
|---|---|---|
| Repository `siqiwang0712-commits/financial-risk-agent` | matches; public | confirmed |
| E4 locks FinRisk `v0.3.4` at `4273b070678240fe7cbdf01a17527afcc71c500e` | tag `v0.3.4` → `4273b070…` | confirmed |
| HEAD may have moved past the handover | HEAD is `e2d4133`, 11 commits after the previously known `c516449` | confirmed (moved) |
| E4-A: 2,000 company-disjoint FY2024 10-K filers | `cohort.selected = 2000`, `company_disjoint = true` | confirmed |
| `VERIFIED = 674` | `outcomes.verified_n = 674` | confirmed |
| events `= 235` | `outcomes.events = 235` | confirmed |
| verified coverage ≈ 33.7% | `0.337` | confirmed |
| B0 AUROC ≈ 0.678 | `0.6776523045606553` | confirmed |
| B6 AUROC ≈ 0.708 | `0.7079581253332041` | confirmed |
| paired ΔAUROC ≈ +0.030 | `+0.03030582077254884` | confirmed |
| bootstrap 95% CI ≈ +0.014 to +0.048 | `+0.0136488` to `+0.0480862` | confirmed |
| E4-B: 50 selected cases | `agent_cohort_limit = 50` | confirmed |
| 18 VERIFIED | `18` | confirmed |
| fully paired ≈ 16 | `n_pairs = 16` | confirmed |
| positive events only 5 | `events = 5` | confirmed |
| ~5 permanent schema failures in 150 official records | `agent.official_failures = 5` | confirmed |
| Codex comparator internal display name `ChatGPT5.6 Sol` | present, marked project-internal | confirmed |
| that comparator is `POST_HOC` | `evidence_status = POST_HOC` in its predictions | confirmed |
| batch vs single mean absolute score difference ≈ 0.10 | `0.10094790348620689` | confirmed |
| binary agreement high | `0.9655172413793104` | confirmed |
| rank correlation ≈ 0.31 | Spearman and Kendall both ≈ `0.313` | confirmed |
| verification propensity model AUROC ≈ 0.740 | `0.7396444539925078` | confirmed |
| all scores `UNCALIBRATED` | `reliability = UNCALIBRATED` on every summary | confirmed |

---

## 2. Discrepancies and refinements

### 2.1 The E4 harness has no frozen source commit

The brief states E4's locked source is `4273b070` (tag `v0.3.4`). That is true for the
**scoring library**, and verified as such: between `4273b070` and HEAD, the only changes
under `backend/` are the *additions* of `e4_agent.py`, `e4_core.py`, `e4_evaluation.py`,
`e4_outcomes.py` and `e4_posthoc.py` (2,168 insertions, zero modifications to any existing
module). So every deterministic score E4 reports is produced by code byte-identical to the
tagged release.

But the **E4 harness itself does not exist at `4273b070`**:

```
$ git ls-tree -r --name-only 4273b070 | grep -E 'e4_|run_e4'
(no output)
```

`backend/finrisk/e4_*.py` and `scripts/run_e4*.py` first appear in `96e60ae`
("research: add E4 comparative validation"). Since `e4_core.verify_source` asserts
`HEAD == 4273b070`, the study must have been executed from a working tree whose HEAD was
`4273b070` while the harness was still uncommitted.

**Consequence.** The claim "E4 evaluates the exact FinRisk v0.3.4 implementation at
`4273b070`" is accurate about *scoring*. It does not extend to the *evaluation harness*,
which has no versioned identity predating the results. The distinction matters for a
reviewer: the numbers are reproducible from the tag, the inference code is not.

### 2.2 Outcome isolation is procedural, not cryptographic

The brief describes "outcome 在 prediction freeze 后才解锁". The code does enforce this:
`command_freeze_predictions` calls `_require_prediction_isolation`, which raises if
`E4_OUTCOME_INPUT_DIR` is set, if any outcome archive is visible, or if one has leaked into
the feature mount; `command_build_outcomes` refuses to run without an explicit
future-only mount.

That is a real and correctly implemented control. It is nevertheless a *mount* control
inside one environment, not a cryptographic separation: the outcome archives were present
on the same machine throughout. E5's staged-commit governance is the stronger form.

### 2.3 The permuted null is not the null E4 states

The brief asks whether the paired permutation test truly corresponds to
`H0: AUROC(B6) = AUROC(B0)`. It does not. See
`research/e4_statistical_audit/AUDIT_REPORT.md` for the full analysis. Summary:
`e4_evaluation.paired_permutation` shuffles outcome labels across observations while
keeping each observation's `(B0, B6)` score pair fixed, which samples the null of *no
signal in either score*, not the null of equal AUROCs. The published P1 p-value equals
`1/2001`, the attainable floor.

### 2.4 The 20,000-replicate requirement was met

The brief asks for a higher replicate count than E4's 5,000. The audit runs 20,000
replicates for the paired bootstrap, the label permutation and the score-swap
randomization, and reports E4's nearest-rank percentile convention alongside standard
linear interpolation, because the two differ measurably at 5,000 replicates.

### 2.5 An undocumented environment override is required to reproduce E4's outcomes

`backend/finrisk/sec_bulk.py` refuses to read any archive member larger than
`DEFAULT_MAX_ARCHIVE_MEMBER_BYTES = 256 * 1024 * 1024`, and `.env.example` ships that
default. SEC FSDS `num.txt` members are 500–600 MB. Re-running E4's outcome stage with the
frozen code therefore fails:

```
ValueError: archive member exceeds the extraction limit: num.txt (542201491 bytes)
```

unless `FINRISK_SEC_MAX_ARCHIVE_MEMBER_BYTES` is raised. That override appears in neither
`research/e4/protocol/experiment_config.json` nor
`research/e4_posthoc/environment_manifest.json`, so **E4's outcome stage cannot be
reproduced from E4's own documentation**. This is a concrete, fixable governance defect and
is carried into the E5 protocol as an explicit environment-variable freeze.

### 2.6 `previous_270.json` is unpublished

`e4_core.PREVIOUS_270_SHA256` pins the 270-CIK exclusion set by hash, but the file itself
is not in the repository (`research/e4/_cache/` was added to `.gitignore` in the same
commit that published the results). The exact E4 cohort therefore cannot be rebuilt by an
external party. See §3.

---

## 3. Reproducibility boundary

What an external party **can** verify from the public repository:

- the published summary is internally consistent (`verified_n == n_pairs`, marginal AUROC
  difference equals the reported Δ, Holm multiplier matches);
- `research/e4/protocol/STUDY_PROTOCOL.md` hashes to
  `f732aef1697c2246156857c5b9f76a8d8de12cfa5d12a4239cdbd847ab5e683e`, matching
  `protocol_freeze.json`;
- the frozen `.gitignore` does exclude `research/e4/_artifacts/` and `research/e4/_cache/`.

What an external party **cannot** verify:

- the 674 paired `(B0, B6, label)` rows, because they are not published;
- the exact cohort, because the 270-CIK exclusion list is not published;
- the outcome stage, because it needs an undocumented environment override.

Consequently the E4 post-hoc audit's statement that it "re-read the canonical files rather
than relying on the README" describes a check performed with local access to the artifacts.
It is a genuine check, but it is not one an external reviewer can repeat.

### 3.1 What this audit did about it

Rather than accepting the boundary, the audit re-executed the frozen pipeline from public
inputs:

- all eight SEC FSDS archives and all three Zenodo files were re-downloaded and their
  SHA-256 / MD5 values matched the frozen `data_hashes` and `ZENODO_MD5` **exactly**;
- the cohort algorithm was re-run with an empty 270-CIK exclusion (a documented deviation);
- `build_features` → `run_numeric` → `build_outcomes` were executed unmodified.

Result (`_recon/replication/`, and `research/e4_statistical_audit/replication_crosscheck.json`):

| Quantity | E4 published | Re-execution |
|---|---:|---:|
| usable candidates before sampling | 3659 | 3888 |
| selected | 2000 | 2000 |
| `VERIFIED` | 674 | 675 |
| events | 235 | 235 |
| B0 AUROC | 0.6777 | 0.6791 |
| B6 AUROC | 0.7080 | 0.7054 |
| ΔAUROC | +0.0303 | +0.0264 |

Measured cohort overlap: **47 of 50** sampled E4-B companies are present in the
re-execution's cohort (proved by reproducing their published packet hashes). So the
re-execution is a **near-reproduction on a ~94%-overlapping cohort**, not an independent
sample. Its value is that it demonstrates the *pipeline* is reproducible end-to-end from
public inputs, and that the P1 direction is stable under a ~6% cohort perturbation. It does
**not** remove the `NOT_INDEPENDENTLY_REPRODUCIBLE` status of E4's exact rows.
