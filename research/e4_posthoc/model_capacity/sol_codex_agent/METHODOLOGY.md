# ChatGPT5.6 Sol Codex Comparator — Methodology

## Identity and evidence status

`ChatGPT5.6 Sol` is a project-internal experimental codename. It is not an
OpenAI model name and must not be represented as an official ChatGPT model.
The analysis was executed by a Codex sub-agent; this platform did not expose
the sub-agent's exact underlying model ID. The results are **POST-HOC** and
**UNCALIBRATED**. They are not E4 confirmatory evidence.

## Frozen inputs and isolation

The comparator used the 50 anonymized E4-B cases already frozen in
`research/e4/_artifacts/agent_batch_manifest.json`. It produced one judgment
for each of the frozen A0, A1 and A2 representations:

- A0: FY2024 raw financial facts and same-filing FY2023 comparative facts.
- A1: engineered financial features, trends and missingness.
- A2: A0 and A1 evidence plus individual traditional-model outputs and their
  applicability/missingness.

Predictions were completed from the frozen packets before outcomes were used
for evaluation. No company identity, CIK, ticker, accession, outcome, internet
resource, other model's final score or non-packet repository evidence was
provided to the reasoning agents. Work was split by representation so that
each reasoning context handled only its assigned anonymized packets.

The frozen A0/A1/A2 representation contracts, output schema and 0.5 decision
threshold were retained. No prompt, threshold, feature, case selection or
fusion weight was tuned against E4 outcomes. Packet hashes from the frozen
manifest are retained in every output record.

The manifest records the original E4 prompt hashes as reference identifiers;
it does not claim that Codex's platform-level system prompt was identical or
fully controllable. Because the platform did not expose that prompt or the
exact model identity, the frozen outputs are auditable but the inference call
itself is not independently byte-reproducible.

## Outputs and evaluation

Each valid record contains the case ID, representation, model ID, score in
`[0, 1]`, thresholded decision, reason codes, short summary, frozen packet
hash and comparator configuration hash. Coverage counts all 150 requested
case/representation pairs; missing or invalid outputs would remain failures
rather than being imputed.

Predictive metrics use only the unchanged deterministic `VERIFIED` binary
outcomes. `REQUIRES_HUMAN_REVIEW` and `INSUFFICIENT_DATA` are excluded from
predictive metrics. The structured hybrid is fixed as:

`SOL_H0 = 0.5 × B6 + 0.5 × SOL_A2`

and is evaluated only where the same observation has a valid B6 score, a
valid SOL_A2 score and a deterministic `VERIFIED` outcome. It does not replace
the frozen E4 H0 and cannot alter P1/P2/P3.

## Interpretation boundary

This exercise measures a post-hoc structured reasoning comparator on a small,
outcome-verified subset. It does not validate a probability of default,
bankruptcy prediction, production or regulatory use, a full narrative Agent,
or the claimed capability of any named commercial model. Because the E4
outcomes were already available before this new experiment was commissioned,
all comparisons remain exploratory even though prediction generation was kept
outcome-blind.
