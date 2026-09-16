# Capability Maturity Matrix

Updated: 2026-09-15. `Production` means externally operated and validated; no row currently meets that standard.

`Wired` asks a different question from the other columns: is this capability reachable
from a live entry point (`/api/v1/documents/analyze`, `/api/v1/agent/assess`, or the
enterprise API), or does it only exist as a tested library function? A row can be
`Code: Yes / Tested: Yes` and still be `Wired: No`, which is exactly the gap that a
`Code`/`Tested` pair cannot express. `No` means the capability is not on the path a
caller actually reaches, not that it is broken.

| Capability | Code | Tested | Wired | Real data | Validated | Production |
|---|---:|---:|---:|---:|---:|---:|
| Deterministic financial metrics | Yes | Yes | Yes | 90-observation numeric E3 | Formula-tested; empirical endpoint underpowered | No |
| SEC XBRL normalization/provenance | Yes | Yes | Yes | 90 SEC-derived observations | PIT/provenance gate passed; no human extraction gold | No |
| PDF narrative extraction | Yes | Yes | Yes | Sample filing | Partial | No |
| Traditional models | Yes | Yes | Yes | Pilot inputs incomplete | Formula tests | No |
| 68-rule engine | Yes | Yes | Yes | Pilot | Not expert-validated | No |
| Evidence verification/decision trace | Yes | Yes | Yes | Pilot | Partial | No |
| Correlated-evidence de-duplication | Yes | Yes | Yes | Fixture only | Monotonicity property test | No |
| Temporal risk state/attribution | Yes | Yes | Yes | 30-company numeric trajectories | Executed; usefulness not validated | No |
| Temporal evidence graph | Yes | Yes | No | No | No | No |
| Applicability Router | Yes | Yes | Yes | No sector validation | No | No |
| Calibration/selective automation | Yes | Yes | Yes | n=3 diagnostic only | No | No |
| Analyst–Critic–Verifier review | Yes | Yes | Yes | Offline semantics | No | No |
| DecisionBundle/replay | Yes | Yes | Yes | Controlled fixture | Local only | No |
| Risk Case mitigation lifecycle | Yes | Yes | Yes | Controlled fixture | Local only | No |
| Champion–Challenger gate | Yes | Yes | No | No qualified candidate run | No | No |
| Human–AI study | Protocol + analysis | Yes, synthetic | No | No participants | NOT RUN | No |
| PostgreSQL persistence | Schema + adapter | Migration/restart and Compose smoke | Yes | No production deployment | Runtime-tested | No |

`Wired: No` rows and why:

- **Temporal evidence graph** — schema and traversal exist; no entry point populates it.
- **Champion–Challenger gate**, **Human–AI study** — offline/analysis-only by design.

Temporal risk state and selective automation are wired through explicit enterprise
endpoints; they are not silently applied to the one-shot assessment contract.

The matrix deliberately separates software existence from empirical validity, and now
also separates both from reachability.

Every row claimed as `Wired: Yes` should have an end-to-end assertion on the entry
point that reaches it; adding one is the cheapest way to keep this column honest.
