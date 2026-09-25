# Post-hoc Local Model Capacity Status

Status: **NOT RUN — STRONGER LOCAL MODEL UNAVAILABLE**

The local Ollama inventory was inspected after E4. It contained only the frozen
`qwen2.5:0.5b` model used by E4. No genuine 3B, 7B, or stronger local instruct
model was already available, so no model-capacity comparison was run. The study
did not download a model after outcomes were visible and did not substitute a
cloud model for a local model.

This absence does not support a claim about the capability ceiling of LLMs or
Agents. E4 supports only the narrower statement that the tested 0.5B local
Agent did not establish incremental value.

## Codex sub-Agent comparator

A separate post-hoc structured comparator was completed under the
project-internal display name `ChatGPT5.6 Sol`. This is not an OpenAI model
name or official ChatGPT model, and the platform did not expose the exact
underlying model ID. It is therefore not evidence from a known stronger local
model and does not resolve the local model-capacity question above.

The comparator completed all 150 frozen A0/A1/A2 judgments. Evaluation was
limited to 18 deterministically verified cases with five events, so its
results are `POST_HOC`, `UNCALIBRATED`, and insufficiently powered. See
[`sol_codex_agent/METHODOLOGY.md`](sol_codex_agent/METHODOLOGY.md).
