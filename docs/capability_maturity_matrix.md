# Capability Maturity Matrix

Updated: 2026-10-05. v0.4.1 is released. `Production` means externally operated and
validated, not software release status; no row currently meets that standard.

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
| Assurance authority boundary | Yes | Yes | Yes | Synthetic/internal only | Internal development | No |
| Evidence fragility | Yes | Yes | Yes | Synthetic dependency graphs | Deterministic property tests | No |
| Decision-Sufficient Evidence | Yes | Yes | Yes | Synthetic dependency graphs | Exact/approximation contract tests | No |
| Distribution validity | Yes | Yes | Yes | Synthetic runtime profile; historical empirical research profile | Internal mechanics; no external/production validity or E5-frozen reference | No |
| Financial/reporting feature separation | Yes | Yes | Yes | Runtime payloads; 675-row historical V/O/VO/CC diagnostics | Internal development; observability is not financial severity | No |
| StrongTabularReference-v1 | Yes | Yes | No | 675 companies / 235 events / 440 non-events | Design-exposed retrospective selection/replay; uncalibrated | No |
| Empirical development reference | Yes | Yes | No | 2,000 historical source companies; built without labels | `EMPIRICAL_DEVELOPMENT_REFERENCE_ONLY`; not external/production validated or E5-frozen | No |
| Correlated-evidence de-duplication | Yes | Yes | No | Fixture only | Monotonicity property test | No |
| Temporal risk state/attribution | Yes | Yes | Yes | 30-company numeric trajectories | Executed; usefulness not validated | No |
| Temporal evidence graph | Yes | Yes | No | No | No | No |
| Applicability Router | Yes | Yes | Yes | No sector validation | No | No |
| Calibration/selective policy eligibility | Yes | Yes | Yes | n=3 pilot; 675-row research-only S0/S1 selective dry-run | Mechanics tested; policy/scores remain `UNCALIBRATED` | No |
| Analyst–Critic–Verifier review | Yes | Yes | Yes | Offline semantics | No | No |
| Decision Certificate/replay | Yes | Yes | Yes | Synthetic + PostgreSQL restart smoke | Internal development | No |
| Risk Case mitigation lifecycle | Yes | Yes | Yes | Controlled fixtures | Local/CI mechanics, not external operation | No |
| Champion–Challenger gate | Yes | Yes | No | No qualified candidate run | No | No |
| Human–AI study | Protocol + analysis | Yes, synthetic | No | No participants | NOT RUN | No |
| PostgreSQL persistence | Schema + adapter | Migration/restart and Compose smoke | Yes | No production deployment | Runtime-tested | No |

`Wired: No` rows and why:

- **Temporal evidence graph** — schema and traversal exist; no entry point populates it.
- **Correlated-evidence de-duplication** — `deduplicate_contributions` /
  `fuse_verified_contributions` are a tested library capability reached only from tests.
  Both live decision paths (`pipeline.assess` and the Agent) call
  `hierarchical_escalation` directly, which consumes per-dimension maxima without
  invoking the de-duplication step.
- **Champion–Challenger gate**, **Human–AI study** — offline/analysis-only by design.
- **StrongTabularReference-v1**, **Empirical development reference** — research artifacts
  and offline entry points; not silently installed into live scoring or Assurance.

The empirical profile is historical and design-exposed. Its label-independent generation
does not remove prior research exposure or establish prospective validity. All 2,000
source companies remain future E5 exclusions. E5 remains `BLOCKED / DRAFT_NOT_FROZEN`.
The existing runtime synthetic profile remains `DEVELOPMENT_REFERENCE_ONLY`; unknown or
unsupported observations still fail closed. Offline selective diagnostics are not
evidence of a calibrated runtime policy.

Temporal risk state and selective automation are wired through explicit enterprise
endpoints; they are not silently applied to the one-shot assessment contract.

The matrix deliberately separates software existence from empirical validity, and now
also separates both from reachability.

Every row claimed as `Wired: Yes` should have an end-to-end assertion on the entry
point that reaches it; adding one is the cheapest way to keep this column honest.
