# Post-hoc GPT-5 External Comparator Status

Status: **NOT RUN — EXTERNAL EGRESS BLOCKED BY THE EXECUTION ENVIRONMENT**

The user explicitly authorized sending the anonymized frozen packets to
ChatAnywhere. The execution environment nevertheless rejected the external
transfer as a platform-level data-egress restriction. No API request occurred.
The credential supplied in chat was deliberately not copied into source,
commands, logs, manifests, or files. Consequently model discovery,
exact-`gpt-5` verification, smoke testing, and batch inference were not run.

No fallback model was used or represented as GPT-5. This infrastructure block
does not alter any E4 conclusion. A future run must freeze the exact provider
model ID and deterministic batch manifest before the first comparator request,
and all resulting claims must remain `POST_HOC`.

The prepared local launcher is
`scripts/run_gpt5_comparator_interactive.ps1`. It prompts with
`Read-Host -AsSecureString`, places the credential only in the child-process
environment, and clears it after execution.
