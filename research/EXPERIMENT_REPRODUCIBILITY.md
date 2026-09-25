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
| E4-S statistical audit | `research/e4_statistical_audit` |
| E4-R robustness study | `research/e4r_automated_robustness` |
| E5 | Protocol only; no cohort, predictions, labels or results exist |

Historical v0.3.1 snapshots remain archived for audit, but the current CI and
release claims no longer depend on their replay.

## Study directory convention

Every study downstream of E4 follows the same layout, so that a reader can enter
any directory without knowing its history:

| Slot | Contents |
|---|---|
| `README.md` | the directory's landing page: status, the study's question, how to run it, a file index and where it sits in the chain |
| `<REPORT>.md` | the study's own report, numbered by section, with a status line that uses the vocabulary in [EXPERIMENT_OVERVIEW.md](EXPERIMENT_OVERVIEW.md) |
| protocol docs | `STUDY_PROTOCOL.md` plus any prespecification the study freezes, and the machine-readable config |
| artifacts | one JSON per result surface, each carrying the evidence label that says whether it is a measurement, a reconstruction or a refusal |
| verifier | a single command that re-checks the hashes and recomputes the headline statistics |

The convention is enforced where it can be: `tests/test_research_navigation.py`
checks that the index documents link to every study directory that exists and
that the generated README sections match their artifacts.

## Current release verification

Verify the public E4, E4-S, E4-R and post-hoc artifact surface without accessing
ignored raw data or regenerating research outputs:

```bash
python scripts/verify_e4_public_artifacts.py
python research/e4_statistical_audit/verify_audit.py
python research/e4r_automated_robustness/verify_e4r.py
python -m pytest -q tests/test_e4.py tests/test_e4_posthoc.py tests/test_e4_public_release.py
python -m ruff check backend tests scripts research
```

The public verifier checks the locked commit, outcome counts, claim gates,
deterministic/render replay status, post-hoc prediction hash and coverage, and
secret/local-path leakage.

`verify_audit.py` re-checks the SHA-256 of every published E4 artifact (proving
E4-S did not mutate E4) and of its own replication packet, then recomputes the
marginal AUROCs, ΔAUROC, the paired DeLong test, the BCa interval, the
label-permutation null and the score-swap null from the published rows. Add
`--quick` to run at 2,000 replicates instead of 20,000; use `--out <path>` to keep
a quick run from overwriting the committed 20,000-replicate result.

`verify_e4r.py` re-checks the source manifests, the frozen config, every output
hash, the OOF coverage rule and the headline statistics independently from
`oof_predictions.json`.

E4-R and E4-S need packages the product runtime deliberately does not ship.
Install them with `python -m pip install -e ".[research]"`; E4-S itself needs
nothing beyond the standard library.

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
- E4-S's every published number is recomputable from `replication/` plus the
  published E4 summary. **E4's own 674 paired rows are not**: `research/e4/_cache/previous_270.json`
  and `research/e4/_artifacts/*.json` are unpublished, so any claim that depends
  on them is labelled `NOT_INDEPENDENTLY_REPRODUCIBLE`.
- E4-R's cohort, per-observation predictions, ablations and headline statistics
  are recomputable from its committed artifacts by one command. Its cohort is
  E4-S's replication cohort, so it inherits the ~94%-overlap limitation and
  provides no independent sample.
- Learned-model metrics in E4-R are out-of-fold. The reported DeLong and
  bootstrap intervals condition on the realized OOF predictions and do not
  integrate training-procedure uncertainty; that omitted component is measured
  separately in `model_stability.json`.

## Data and artifact policy

- `research/e4/public` is the canonical checked-in E4 result surface.
- `research/e4/_artifacts` and `research/e4/_cache` are large local execution
  state and remain Git-ignored.
- `research/e4_posthoc` may add diagnostics, but every new claim must remain
  explicitly post-hoc.
- `research/e4_statistical_audit` may re-run the frozen pipeline from public
  inputs and publish the resulting cohort, but must never write into
  `research/e4/`; `e4_frozen_artifact_manifest.json` and its test enforce that.
- `research/e4r_automated_robustness` may add analyses, but only through a
  prespecification file whose hash is pinned before the run, and only as
  `POST_HOC_AUTOMATED_ROBUSTNESS`. `experiment_config.json` is immutable once
  written; later passes go in `extension_config.json`, which pins the hash of the
  config it was built against and aborts if it moves.
- Raw SEC ZIPs, downloaded model blobs, secrets, Authorization headers and
  local absolute paths must never be committed.
- Publication-shaped artifacts (JSON, CSV, SVG, Markdown) are pinned to LF in
  `.gitattributes` so that a Windows checkout and a Linux checkout hash
  identically. Verifiers compare bytes, not text.
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
| Does E4's inference test the hypothesis it states? | [E4-S audit report](e4_statistical_audit/AUDIT_REPORT.md) |
| Is B6 robust, and how does it compare to tabular learning? | [E4-R final report](e4r_automated_robustness/FINAL_REPORT.md) |
| What comes next? | [E5 protocol draft](e5/STUDY_PROTOCOL_DRAFT.md) |
