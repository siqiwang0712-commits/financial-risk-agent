# E5 outcome-blind model qualification contract — NOT EXECUTED

The current S2 producer design is blocked (E5-P02). This contract does not nominate
an unavailable model or reinterpret a mock as the confirmatory Agent.

Use a separately registered non-E5 qualification corpus: approved historical or
explicitly synthetic engineering cases, with every source/company/hash registered
as a later E5 exclusion. No E5 cohort IDs, predictions or outcomes may be inspected.
Candidates must be recorded before testing: weights/model revision, tokenizer,
quantization, prompt hash, schema hash, runtime/lock/container, hardware and license.
A hosted mutable alias without stable revision and replay assurance is ineligible.

Hard gates: >=99% schema-valid responses under the existing historical planning
requirement; 100% exact case-ID integrity; no silent missing/duplicate outputs;
finite in-range scores; one company per semantic context; deterministic documented
recovery (one identical retry at most, otherwise FAILED); no web/outcome tools;
context fits fixed hardware; a replay-qualified immutable identity. Retain invalid
responses securely with bounded redacted diagnostics. Every candidate uses exactly
the same packets and retry budget. No label-dependent metric enters selection.

Among gate-passing candidates, lexicographic order: schema-valid response rate,
replay agreement, context fit, hardware feasibility, then measured latency and cost;
final ties use lexical immutable identity hash. If no candidate passes, BLOCKED.
Candidate registry/corpus provenance and prompt identity must be independently
approved before tests. No arbitrary winning model is installed by this document.
Qualification outcomes are engineering evidence, not prospective E5 validation.
