# Human–AI Study Protocol

Status: **IMPLEMENTED PROTOCOL; NO REAL PARTICIPANTS; NOT RUN**.

## Question

Does FinRisk assistance reduce analysis time, missed material risks, unsupported claims and citation errors without creating automation bias?

## Design

- Within-subject, counterbalanced comparison: `human_only` versus `finrisk_assisted`.
- Public non-financial US issuer cases, blinded company identity where practical.
- Pre-registered rubric and adjudicated case key created independently of system output.
- Log analysis time, missed risks, unsupported claims, citation errors, overrides, decision agreement and usability feedback.
- Do not expose held-out labels, future filings or outcome information during the task.

## Analysis

Use participant-clustered bootstrap intervals and paired differences. Report participant count, exclusions and all adverse findings. The code in `finrisk.human_study` validates and summarizes collected rows. Synthetic rows may test the pipeline only and must retain `SYNTHETIC_DEMO` status.

No participant outcomes are currently claimed.
