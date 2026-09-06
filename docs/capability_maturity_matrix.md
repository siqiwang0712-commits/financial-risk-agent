# Capability Maturity Matrix

Updated: 2026-09-06. `Production` means externally operated and validated; no row currently meets that standard.

| Capability | Code | Tested | Real data | Validated | Production |
|---|---:|---:|---:|---:|---:|
| Deterministic financial metrics | Yes | Yes | Pilot | Fixture-validated | No |
| SEC XBRL normalization/provenance | Yes | Yes | Frozen pilot | Partial | No |
| PDF narrative extraction | Yes | Yes | Sample filing | Partial | No |
| Traditional models | Yes | Yes | Pilot inputs incomplete | Formula tests | No |
| 68-rule engine | Yes | Yes | Pilot | Not expert-validated | No |
| Evidence verification/decision trace | Yes | Yes | Pilot | Partial | No |
| Temporal risk state/attribution | Yes | Yes | No multi-period corpus | No | No |
| Temporal evidence graph | Yes | Yes | No | No | No |
| Applicability Router | Yes | Yes | No sector validation | No | No |
| Calibration/selective automation | Yes | Yes | n=3 diagnostic only | No | No |
| Analyst–Critic–Verifier review | Yes | Yes | Offline semantics | No | No |
| DecisionBundle/replay | Yes | Yes | Controlled fixture | Local only | No |
| Risk Case mitigation lifecycle | Yes | Yes | Controlled fixture | Local only | No |
| Champion–Challenger gate | Yes | Yes | No qualified candidate run | No | No |
| Human–AI study | Protocol + analysis | Yes, synthetic | No participants | NOT RUN | No |
| PostgreSQL persistence | Schema + adapter | CI migration | No deployment | CI only | No |

The matrix deliberately separates software existence from empirical validity.
