# E5 Governance Workflow

Status: **PROSPECTIVE — EXECUTABLE PROCEDURE**

Purpose: make E5's prospective claim publicly verifiable. A reader must be able to confirm,
from public git history alone, that the protocol existed before the cohort, the cohort
before the predictions, and the predictions before the outcomes.

---

## 1. Why E4 could not do this

E4's protocol, implementation, results and post-hoc audit all entered public history in a
single commit:

```
96e60ae91c0ba73342c6e96e42eaa40145f082b1  research: add E4 comparative validation
  2026-09-25T03:04:52Z   69 files changed
```

That commit added `research/e4/protocol/*`, `backend/finrisk/e4_*.py` (2,168 lines),
`research/e4/public/*` (the results), `research/e4_posthoc/*` (the audit) and
`research/e5/*` — together. It also, in the same commit, added to `.gitignore`:

```
research/e4/_artifacts/
research/e4/_cache/
```

so the per-observation predictions, labels and the 270-CIK exclusion list were excluded
from publication in the very commit that published the results. The locked source commit
`4273b070` (tag `v0.3.4`) predates that commit, but it contains none of the E4 harness:
`backend/finrisk/e4_*.py` and `scripts/run_e4*.py` do not exist there.

The consequence is precise and worth stating exactly:

- E4 **is** internally frozen and auditable: its artifacts carry content hashes, its state
  machine enforces one-stage-at-a-time transitions, and its published summary is
  self-consistent. `research/e4/protocol/STUDY_PROTOCOL.md` hashes to
  `f732aef1697c2246156857c5b9f76a8d8de12cfa5d12a4239cdbd847ab5e683e`, which matches the
  `protocol_sha256` recorded in `protocol_freeze.json`. That check passes.
- E4 is **not** publicly preregistered. A self-attesting freeze file created in the same
  commit as the results cannot demonstrate that the protocol preceded the outcomes.
- E4's inference is **not** independently reproducible. `previous_270.json` is pinned only
  by SHA-256; the raw prediction and label artifacts are not published.

E5 must produce a history in which each of those three statements is true.

---

## 2. Required commit sequence

Each step is its own commit or annotated tag. No step may be amended, rebased, squashed or
force-pushed after it is pushed. Step *n+1* must not exist in public history at the time
step *n* is pushed.

| # | Commit | Must contain | Must NOT contain |
|---|---|---|---|
| 1 | `protocol` | study protocol, inference policy, adjudication protocol, agent qualification protocol, power analysis, experiment config, freeze manifest | any cohort, feature, prediction or outcome |
| 2 | `agent-qualification` | qualification packet manifest + hashes, per-candidate results, chosen model and digest | any E5 cohort or outcome |
| 3 | `cohort-freeze` | candidate enumeration counts, algorithm, salt, final cohort with masked IDs and CIKs | features, scores, outcomes |
| 4 | `feature-freeze` | feature hash, feature manifest | any prediction or outcome |
| 5 | `prediction-freeze` | content-addressed prediction hash, batch manifest, raw agent responses | any outcome |
| 6 | `outcome-unlock` | outcome archive inventory, label hash, status counts | any change to steps 1–5 |
| 7 | `adjudication` | adjudicated labels, agreement statistics, coverage | any change to steps 1–6 |
| 8 | `evaluation` | primary results, all prespecified secondary analyses, method-sensitivity report | any post-hoc redefinition |
| 9 | `results` | public claims rendered from the canonical summary | numbers not present in step 8 |

A step that fails is published as a failed step. The pipeline is never re-run with a
changed prompt, threshold, weight, sample, endpoint or model to improve a headline number.

---

## 3. Freeze manifest schema

Every stage commit writes `research/e5/freeze/<stage>.json`:

```json
{
  "stage": "prediction-freeze",
  "sequence": 5,
  "previous_stage": "feature-freeze",
  "previous_manifest_hash": "<sha256 of the previous stage manifest>",
  "source_commit": "<git rev-parse HEAD>",
  "created_at_utc": "<ISO 8601, Z>",
  "artifacts": [
    {"path": "research/e5/artifacts/predictions.json",
     "sha256": "<sha256>",
     "bytes": 0,
     "role": "prediction"}
  ],
  "config_hash": "<sha256 of experiment_config.json>",
  "protocol_sha256": "<sha256 of STUDY_PROTOCOL.md>",
  "environment": {
    "python": "<version>",
    "packages_lock_sha256": "<sha256 of requirements.lock>",
    "environment_variables": {"<NAME>": "<value>"}
  },
  "counts": {"observations": 0, "predictions": 0},
  "immutable": true
}
```

Rules:

- `previous_manifest_hash` chains the stages; a broken chain is a hard failure.
- `environment_variables` records **every** variable that can change a result, not only
  package versions. This is a direct consequence of the E4 finding in §5 below.
- `created_at_utc` is the commit timestamp, so it is verifiable from git.
- A stage manifest is written with the project's frozen-write helper, which refuses to
  overwrite an existing artifact.

---

## 4. Verification procedure for an independent reader

1. `git log --reverse --format='%H %cI %s' main` and confirm the nine stage commits appear
   in order with increasing timestamps.
2. For each stage commit, recompute every `sha256` in `research/e5/freeze/<stage>.json`
   from the tree at that commit and confirm it matches.
3. Confirm `previous_manifest_hash` chains correctly from stage 2 onward.
4. Confirm the cohort in stage 3 is disjoint from every prior cohort, using the published
   270-CIK list.
5. Confirm stage 5 contains no outcome artifact and that stage 6 introduces the outcome
   mount for the first time.
6. Recompute the primary statistics from stage 8's inputs and confirm they match.

`research/e5/protocol/verify_freeze_chain.py` implements steps 1–3 and 6 mechanically.

---

## 5. Environment recording requirement

E4's outcome stage cannot be reproduced from E4's own documentation. The frozen v0.3.4
guard in `backend/finrisk/sec_bulk.py` rejects archive members larger than
`DEFAULT_MAX_ARCHIVE_MEMBER_BYTES = 256 * 1024 * 1024`, and `.env.example` ships that
default as `FINRISK_SEC_MAX_ARCHIVE_MEMBER_BYTES=268435456`. The SEC FSDS `num.txt`
members are 500–600 MB, so `build_outcomes` raises:

```
ValueError: archive member exceeds the extraction limit: num.txt (542201491 bytes)
```

unless the variable is raised. That override appears in neither
`research/e4/protocol/experiment_config.json` nor
`research/e4_posthoc/environment_manifest.json`.

E5 therefore freezes an explicit `environment_variables` block and treats any undocumented
environment override as a reproducibility defect.

---

## 6. What a stage commit may and may not record

A stage commit **may** record:

- counts, hashes, timestamps and source commits;
- prespecified analyses and their results;
- failures and negative results, verbatim.

A stage commit **may not** record:

- re-tuned parameters presented as prespecified;
- any statistic computed after an outcome-dependent decision, unless it carries the
  `POST_HOC` label;
- a headline number that does not appear in the canonical summary.

---

## 7. Enforcement

- The stage manifests are written through the frozen-write helper, which refuses to
  overwrite an existing artifact, so a stage cannot be silently recomputed.
- The chain hash makes an out-of-order stage detectable without trusting the author.
- CI fails on `git diff --check` and on any change to a previously pushed stage file.
- If a genuine error is found after a stage is pushed, the correction is a **new**
  amendment commit that names the stage it amends and records both the old and new hashes.
  The original stage commit is never rewritten.
