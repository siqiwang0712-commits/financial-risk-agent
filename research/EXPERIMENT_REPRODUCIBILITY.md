# FinRisk v0.3.4 / E4 Reproducibility Guide

This guide defines the current release verification surface. It distinguishes
checked-in public artifacts from large local execution artifacts and prevents
verification from accidentally regenerating frozen predictions or labels.

## Frozen source

| Item | Identity |
|---|---|
| FinRisk source | tag `v0.3.4`; commit `4273b070678240fe7cbdf01a17527afcc71c500e` |
| E4 public results | `research/e4/public` |
| E4 protocol | `research/e4/protocol` |
| Post-hoc audit | `research/e4_posthoc` |
| E5 | Protocol only; no cohort, predictions, labels or results exist |

Historical v0.3.1 snapshots remain archived for audit, but the current CI and
release claims no longer depend on their replay.

## Current release verification

Verify the public E4 and post-hoc artifact surface without accessing ignored
raw data or regenerating research outputs:

```bash
python scripts/verify_e4_public_artifacts.py
python -m pytest -q tests/test_e4.py tests/test_e4_posthoc.py tests/test_e4_public_release.py
python -m ruff check backend scripts tests
```

The public verifier checks the locked commit, outcome counts, claim gates,
deterministic/render replay status, post-hoc prediction hash and coverage, and
secret/local-path leakage.

`python scripts/run_e4.py status` is available only in the original local
execution workspace because it reads ignored frozen-stage state. It is not a
public-checkout release gate.

On Windows, if pytest cannot access its default temporary directory, use a new
repository-local directory and remove it after the run:

```powershell
python -m pytest -q --basetemp .pytest-tmp-local
```

## E4 phase boundary

E4 enforced this sequence:

`protocol → cohort → features → predictions → future-outcome unlock → labels → evaluation → reproduction`

Feature-side archives were available before prediction freeze. Outcome-side
archives were mounted only after predictions were frozen. Do not rerun `all`,
regenerate stages or overwrite the checked-in public summary merely to verify
the release. Full regeneration requires the original eight verified SEC ZIPs,
the previous-270-CIK exclusion set, isolated mounts and the frozen Local Agent
runtime described in [the protocol](e4/protocol/STUDY_PROTOCOL.md).

## Reproducibility boundary

- E4 cohort, parsing, numeric baselines, outcomes and statistics are
  deterministic.
- With the local ignored execution artifacts present, E4 frozen Agent
  responses can be reparsed deterministically.
- E4 public reports and README research content reproduce from the canonical
  summary.
- The post-hoc comparator's checked-in predictions have a frozen file hash,
  complete IDs, bounded scores and threshold-consistent decisions.
- Recomputing comparator packet hashes requires the ignored local E4 packet
  manifest.
- The comparator's exact Codex model ID, platform system prompt and runtime
  attestation were not exposed. Its saved outputs are auditable, but its
  inference call is not independently byte-reproducible.

## Data and artifact policy

- `research/e4/public` is the canonical checked-in E4 result surface.
- `research/e4/_artifacts` and `research/e4/_cache` are large local execution
  state and remain Git-ignored.
- `research/e4_posthoc` may add diagnostics, but every new claim must remain
  explicitly post-hoc.
- Raw SEC ZIPs, downloaded model blobs, secrets, Authorization headers and
  local absolute paths must never be committed.
- Historical releases remain auditable through archived artifacts, release
  notes, tags and the changelog; they are not current release gates.
- E5 cannot reuse E4 outcomes to create a new confirmatory claim. It requires a
  new untouched feature/outcome period.

## Public evidence map

| Question | Canonical document |
|---|---|
| What was run? | [Experiment overview](EXPERIMENT_OVERVIEW.md) |
| What were the numbers? | [Experiment results](EXPERIMENT_RESULTS.md) |
| What did E4 establish? | [E4 validation report](e4/public/VALIDATION_REPORT.md) |
| What are E4's remaining weaknesses? | [E4 post-completion audit](e4_posthoc/AUDIT_REPORT.md) |
| What comes next? | [E5 protocol draft](e5/STUDY_PROTOCOL_DRAFT.md) |
