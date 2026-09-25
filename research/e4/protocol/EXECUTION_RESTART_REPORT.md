# E4 pre-prediction execution restart

## Status

The first Local Agent execution attempt was aborted before any Agent prediction
artifact was written and before outcome data was unlocked. The frozen study
design, cohort, feature corpus, model, prompts, representations, threshold,
hybrid weight, hypotheses, and statistical plan are unchanged.

## Cause

The initial batch builder used a conservative character-ratio estimate for the
Qwen token budget. Ollama runtime logs showed actual rendered prompts of 4,290
and 4,412 tokens against a 4,096-token context, so Ollama truncated them. This
violated the frozen requirement that each request remain within 70% of context.
No truncated response is admissible.

The aborted `agent_batch_manifest.json` had SHA-256
`944197ac6f3fefd52d3ed1ac757d9b249d3304a439fe88bb1a54bf972f57e261`.
It is retained only by this audit record, not as a valid frozen manifest.

## Corrective execution

The retry keeps the same scientific batching rule and changes only the
implementation used to enforce it: the preflight bound counts the full rendered
system prompt, user JSON, and response schema at a worst-case one token per
character. Batches are therefore smaller but remain in the original order and
use the same packets, hashes, prompt, model, options, retry policy, and
deterministic bisection.

This is a pre-prediction implementation restart, not a post-outcome protocol
change. If any corrected request exceeds 70% according to Ollama's returned
`prompt_eval_count`, execution must stop again and E4 must be invalidated.
