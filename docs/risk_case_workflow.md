# Risk Case Workflow

Status: **IMPLEMENTED AND TESTED IN THE IN-MEMORY REFERENCE SERVICE; PRODUCTION OPERATIONS NOT VALIDATED**.

```text
Signal → Detected → Open → Under Review → Mitigating
                                  ├→ Accepted → Closed
                                  └→ Resolved → Monitoring → Reopen
```

Each case is organization- and entity-scoped. Mitigation actions require description, owner and due date. `Resolved` requires both at least one valid decision path and explicit resolution evidence. `Accepted` preserves the human risk-acceptance decision. Reopen is restricted to accepted/resolved cases and requires actor, reason and timestamp.

Every mutation emits an append-only audit event. Human overrides require a reason and preserve the original and replacement decisions. AI output cannot silently close a case.

Current limitations: notification delivery, calendar escalation, production identity, database transaction concurrency and long-running monitoring workers remain **NOT PRODUCTION VALIDATED**.
