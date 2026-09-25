# E5 Agent Selection Protocol

Select exactly one confirmatory model before E5 outcomes are accessible.

1. Enumerate locally or privately hostable instruct models and record exact ID,
   weights digest, tokenizer, quantization, context, runtime, and license.
2. Reject candidates that cannot run on frozen hardware or cannot satisfy the
   isolation boundary.
3. Use outcome-free synthetic and historical development packets to measure
   schema success, ID fidelity, context fit, latency, and reproducibility.
4. Choose by a frozen lexicographic rule: schema reliability, context fit,
   reproducibility, hardware feasibility, then latency. Do not use E4/E5 labels.
5. Freeze one prompt per representation, inference parameters, retry/bisect
   behavior, batch size, and the exact response schema.
6. Require masked invalid-response retention and deterministic error codes.
7. Run batch sizes 1, operational-small, and target before outcome unlock and
   apply prespecified score/rank sensitivity gates.

Cloud GPT-5 may be an explicitly named comparator only if its exact provider
model ID is stable and frozen. It may never silently replace the confirmatory
model or gain web/tool/outcome access.
