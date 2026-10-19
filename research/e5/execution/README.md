# E5 execution checkpoint

The sponsor's [execution mandate](E5_EXECUTION_MANDATE.md) supersedes the prior
readiness-task ceiling only. Scientific gates, historical artifact identities and
production Assurance behavior remain in force. This execution has made partial
engineering/development progress; it has not completed an empirical E5 study.

Run from the repository root with the research dependencies installed:

```bash
python -m research.e5.run_e5 status
python -m research.e5.run_e5 qualify
python -m research.e5.run_e5 null-qualify
python -m research.e5.run_e5 audit
python -m research.e5.run_e5 pre-outcome-audit
python -m research.e5.run_e5 run-e5r
```

`qualify` verifies the existing S0 artifact and freezes the sponsor-authorized S1
utility calculation. It does not qualify a new Agent or S4 policy. `null-qualify`
uses exactly 5,000 trials per configuration and 20,000 paired draws, persisting
completed configurations by content identity. Repeating a completed run verifies
saved configurations. It is a limited grid, not complete scientific qualification.
`audit` verifies immutable original file bytes and recorded qualification outputs;
it does not attest protocol readiness. `pre-outcome-audit`, `run-e5r`, protocol
freeze and outcome-unlock commands fail with exit 2 while prerequisites remain
unsatisfied. They do not implement a hidden substitute experiment.

`RUN_STATE.json` is a mutable derived checkpoint index, not a frozen scientific
artifact. Referenced checkpoint records and qualification artifacts are immutable.
Completed-stage outputs are never silently overwritten. An interrupted proposal
generation leaves a lock requiring explicit recovery; it cannot silently invoke
an external model a second time. The wrapper is not an actual qualified producer.

Filesystem path checks are engineering guards, not proof of OS-level isolation,
independent review, source authenticity or reviewer blinding. The report explicitly
lists incomplete capabilities. No real E5 feature packets, proposals, predictions,
certificates, labels or primary results were generated.

The original `null-qualify` grid completed with **FAILED_ANTI_CONSERVATISM** and
retains a BLOCKED checkpoint. Its command completing is not a qualification pass.
The separately identified correction is exercised with:

```bash
python -m research.e5.coverage_null_v2
```

That command qualifies only the corrected absolute-coverage component, not the
complete joint inference engine or a scientific E5 protocol. The original failed
grid and all original implementation bytes remain available for audit.
