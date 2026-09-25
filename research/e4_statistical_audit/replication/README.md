# Replication artifacts — independent re-execution of the frozen E4-A pipeline

These files exist so that **every number in `../replication_crosscheck.json` can be
recomputed by a third party without any unpublished input**.

They are **not** E4's artifacts and must not be presented as such. See "Status" below.

---

## What was run

The frozen FinRisk `v0.3.4` deterministic pipeline, unmodified:

```
discover_filings  ->  extract_candidate_facts  ->  _stratified_sample
   ->  build_features  ->  run_numeric  ->  build_outcomes
```

Inputs: the eight SEC FSDS archives (`2024q3` … `2026q2`) and the three Zenodo files. Each
was re-downloaded and its SHA-256 / MD5 verified against the frozen `data_hashes` in
`research/e4/protocol/experiment_config.json` and the `ZENODO_MD5` map in
`research/e4_evaluation.py`. All eleven matched exactly.

Code identity: the E4 harness (`backend/finrisk/e4_*.py`) does not exist at the E4-locked
commit `4273b070`; it was added in `96e60ae`. Across the range `4273b070..e2d4133` the only
changes under `backend/` are the *additions* of those harness files, so the scoring library
that produced these scores is byte-identical to the tagged `v0.3.4` release. The harness
itself was therefore taken from `e2d4133`.

## Status

**`REPLICATION_COHORT_INFERENCE`, not `REPRODUCTION`.**

`research/e4/_cache/previous_270.json` — the 270-CIK exclusion set — is unpublished; only
its SHA-256 is pinned. The cohort algorithm was therefore run with an **empty** exclusion
set. Consequences, measured rather than estimated:

| Quantity | E4 published | This re-execution |
|---|---:|---:|
| discovered original FY2024 10-Ks | 3810 | 4050 |
| usable candidates before sampling | 3659 | 3888 |
| selected | 2000 | 2000 |
| `VERIFIED` | 674 | 675 |
| events | 235 | 235 |
| B0 AUROC | 0.6777 | 0.6791 |
| B6 AUROC | 0.7080 | 0.7054 |
| ΔAUROC | +0.0303 | +0.0264 |

Sector composition differs (for example `Agriculture` 0 → 15, `Manufacturing` 1049 → 1003),
so the selected sets are **not** identical.

**Measured overlap with E4's cohort:** 47 of 50 sampled E4-B companies are present here,
proved by reproducing their published packet hashes. So this is a near-reproduction on a
**~94%-overlapping** cohort, not an independent sample. It demonstrates that the pipeline is
reproducible end to end from public inputs and that the P1 direction is stable under a ~6%
cohort perturbation. It does **not** remove the `NOT_INDEPENDENTLY_REPRODUCIBLE` status of
E4's exact 674 rows.

## Files

| File | Contents |
|---|---|
| `cohort.json` | the 2,000 selected companies: masked id, **CIK**, accession, SIC, sector, periods, filing and acceptance timestamps, source archive and its hash, selection hash |
| `features.json.gz` | per-observation facts, prior-period facts, engineered metrics and provenance (gzipped with `mtime=0`, so the hash is deterministic) |
| `numeric_predictions.json` | 10,000 deterministic predictions (B0, B1, B2, B3, B6 × 2,000) |
| `outcomes.json` | the frozen `deterministic_forward_outcome_rule_v1` labels and statuses |
| `analysis.json` | the joined analysis rows actually used for inference: `observation_id`, `masked_company_id`, `model_id`, `score`, `prediction`, `label` |
| `cohort_report.json`, `feature_report.json`, `numeric_report.json`, `outcome_report.json`, `input_inventory.json`, `summaries.json` | the pipeline's own reports |
| `manifest.json` | SHA-256 of every file above, plus provenance |

Publishing `cohort.json` with CIKs is deliberate: it makes the sample checkable against
public SEC filings, and it lets anyone who obtains the 270-CIK list reconstruct E4's exact
cohort and compute the true overlap.

## How to verify

```bash
# verify every hash and recompute the real-data inference (20000 replicates)
python research/e4_statistical_audit/verify_audit.py

# same, faster (2000 replicates, wider tolerances)
python research/e4_statistical_audit/verify_audit.py --quick
```

The verifier checks the SHA-256 of every published E4 artifact (proving the audit did not
mutate E4), the SHA-256 of every file listed above, and then recomputes the marginal
AUROCs, ΔAUROC, the paired DeLong test, the 20,000-replicate BCa interval, the
label-permutation null and the score-swap null — asserting each against
`../replication_crosscheck.json`. It exits non-zero if anything fails.

To go further and regenerate the features and scores from scratch:

1. download the eight archives listed in `input_inventory.json` (they carry their SHA-256);
2. check out `4273b070` (tag `v0.3.4`);
3. split them into a feature mount (`2024q3`–`2025q2`) and an outcome mount
   (`2025q3`–`2026q2`) — the frozen code refuses to build outcomes if they are visible
   during prediction;
4. set `FINRISK_SEC_MAX_ARCHIVE_MEMBER_BYTES` above the largest `num.txt`
   (see `../AUDIT_REPORT.md` finding E4S-04 — without it the frozen 256 MB default rejects
   the 500–600 MB member);
5. run the pipeline over `cohort.json`'s CIKs.

## Warning

The point estimate here (`+0.0264`) differs from E4's published `+0.0303` by 0.004, which is
well inside sampling noise but is **not zero**. Do not quote these numbers as E4's, and do
not use this cohort to claim E4's result was independently confirmed on a fresh sample —
it was not a fresh sample.
