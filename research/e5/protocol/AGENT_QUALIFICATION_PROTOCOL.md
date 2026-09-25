# E5 Agent Qualification Protocol

Status: **OUTCOME-BLIND — MUST COMPLETE BEFORE THE COHORT FREEZE**

Purpose: choose exactly one confirmatory Agent model, and prove its operational
reliability, without ever observing an E5 outcome. Model selection must never be
influenced by how well a model scores on E5.

---

## 1. Why this stage exists

E4's only available local model was Qwen2.5 0.5B Instruct Q4_K_M, run on CPU through
Ollama 0.12.3. E4's own post-hoc audit records that this was an infrastructure limit, not
a scientific choice, and that it "cannot support 'LLMs/Agents do not add value'". A 0.5B
model is therefore inadmissible as the E5 primary Agent.

Equally, E4's five permanent schema failures out of 150 official records could not be
root-caused because only the `TypeError` was retained. E5 makes schema reliability a
measured, gated property rather than an afterthought.

---

## 2. Candidate enumeration

Enumerate instruct/reasoning models that are:

- locally or privately hostable on frozen hardware, **or** obtainable through a provider
  whose exact model ID is stable and can be frozen;
- capable of constrained structured JSON output;
- available under a licence that permits the study's use.

For each candidate record: exact model ID, weights digest, tokenizer, quantization,
context length, runtime and version, licence, hardware requirement, and the date of the
identity check.

Candidates that cannot run on the frozen hardware, or cannot satisfy the isolation
boundary in §5, are rejected at this stage and the rejection is recorded.

---

## 3. Qualification set

- 100–200 packets.
- **Historical or synthetic. Non-E5. Outcome-blind.**
- Must exercise: complete data, heavy missingness, negative equity, zero or negative
  revenue, extreme leverage, very small and very large filers, and multi-year decline.
- Packets are frozen with their hashes before any candidate is run.
- The qualification set is **not** the E5 cohort and shares no company with it.

---

## 4. Gates

A candidate is *qualified* only if every gate passes.

| Gate | Threshold |
|---|---|
| schema-valid outputs | ≥ 99% of packets |
| case-ID fidelity | 100% exact input/output ID equality |
| missing outputs | 0 |
| `risk_score` validity | in [0, 1] for every output |
| `risk_score` determinism | identical output for repeated identical requests at temperature 0 |
| retry behaviour | deterministic; one unchanged retry then deterministic bisection |
| batch-size sensitivity | rank correlation and mean score difference within the frozen tolerance at sizes 1, small, target |
| latency | recorded; must fit the frozen study budget |
| token cost | recorded per packet |
| failure taxonomy | every failure carries a deterministic error code and a retained masked response hash |
| isolation | no web, tools, shell, repository, future data, other model's output, or deterministic final score |

Batch-size sensitivity is a **hard** gate, not a diagnostic. E4 measured a mean absolute
batch-vs-single difference of 0.101 with a rank correlation of only ~0.313; a model that
cannot rank stably across context sizes cannot support a ranking study.

---

## 5. Isolation boundary

The Agent container:

- runs on a Docker internal network with no egress;
- has read-only root filesystems;
- mounts only the frozen packet payload and the model weights;
- receives no SEC, Zenodo, outcome, repository or host-filesystem mount;
- sees anonymised packets only;
- cannot compute or retrieve B0, B2, B6 or Hybrid scores.

---

## 6. Selection rule (frozen lexicographic order)

Among qualified candidates, choose by:

1. highest schema success rate;
2. best context fit for the frozen packet size;
3. best reproducibility (fewest non-deterministic outputs);
4. best hardware feasibility margin;
5. lowest latency.

Ties beyond step 5 are broken by ascending model ID string, so the rule is total and
deterministic. **No step may reference E5 outcome performance, because no E5 outcome
exists at this point.**

Cloud models may be included as an explicitly named comparator only if the exact provider
model ID is stable and frozen. A cloud model may never silently replace the confirmatory
model, and may never gain web, tool or outcome access.

---

## 7. Freeze

On completion, freeze and hash:

- model ID and weights digest
- tokenizer
- quantization
- context length and all inference parameters (temperature, seed, threads, max tokens)
- runtime and its digest
- the prompt for each representation, versioned
- the response JSON Schema
- retry and bisect policy
- batch policy
- score threshold (default 0.5)
- the qualification packet manifest and its hash
- the qualification result table for **every** candidate, including rejected ones

The freeze hash is recorded in the agent-qualification commit (§11 of the study protocol)
and must not change afterwards.

---

## 8. Reporting

Report for every candidate: all gate outcomes, the failure taxonomy with counts, latency
and cost distributions, and the lexicographic ranking. Rejected candidates are reported
with their rejection reason — a qualification report that shows only the winner is not
auditable.
