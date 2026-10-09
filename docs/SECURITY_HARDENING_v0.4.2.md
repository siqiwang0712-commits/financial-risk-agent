# FinRisk v0.4.2 security and release-preparation evidence

Security changes on `try-v0.4.2`, originally based on
`e60abba2976e389ddf80a147227a56cc4cad8e06`. This is not a release publication,
external audit, or production readiness certification. Current package, frontend
and OCI default versions are 0.4.2. The original security pass below used 0.4.1
package metadata; its evidence remains a historical execution record.

## Branch and research integrity

Before edits, `git status`, `git branch --show-current`, `git log -n 10 --oneline
--decorate`, and `git remote -v` showed a clean `work` checkout at the base above,
with the expected HTTPS GitHub origin. Its fetch configuration initially covered
only `main`. The target branch was fetched explicitly, checked out with tracking,
and verified clean and equal to `origin/try-v0.4.2` before source modifications.
No main commit, tag, release, history rewrite, or research retraining is authorized.

The historical v0.4.1 runtime identity file is retained byte-for-byte and checked
against its original source at the pinned base. Current candidate identities under
`research/v042_development/` bind current security-boundary and release metadata
sources, explicitly excluding publication and E5 freeze. The old v0.4.1 current-source identity check intentionally
fails on changed implementation; CI uses the new v0.4.2 verifier which runs
the same historical research gates and both historical/current identity checks.
It does not rewrite older empirical evidence to make a gate pass.

## Pre-fix findings and resolution

| ID / class | Severity | Component / root cause | Failure mode / reachability | Fix and regression coverage |
|---|---|---|---|---|
| F1 confirmed credential boundary | High | LLM transport uses urllib automatic redirects | A malicious/compromised configured provider can redirect Authorization to another origin; reproduced with local HTTP servers | Reject all redirects; test 301/302/303/307/308, no request reaches the sink |
| F2 confirmed trust boundary | Medium | Caller document names and multipart filenames interpolated into system instructions | Attacker-controlled metadata receives system-role treatment; actual hosted-model exploitation was not tested | Metadata is JSON data inside the user data region; test malicious names and normal extraction |
| F3 confirmed integrity defect | Medium | Assurance verifier checks evidence primarily inside the automation-enabled branch | Rehashed RESTRICTED FLAG with insufficient evidence can pass an internal validation boundary; no external certificate import endpoint found | Validate counts, coverage, evidence state, blockers, failed/status semantics, and proposal-to-final transitions; test rehashed mutations and legitimate optional policies |
| F4 confirmed integrity defect | Medium | Empty certificate hash selects legacy bundle verification | A v0.4 object can be downgraded to a self-consistent hash-only PASS; internal persistence/verification boundary | Require v0.4 certificate identity/hash/Assurance; separate historical bundle integrity; recompute evidence coverage/identities from paths; test tampering and PostgreSQL restart/corruption |
| F5 dependency reports | High (advisory severity) | source-map-js indexed-map offsets and sharp's librsvg dependency | GHSA-68fv-2mgg-jv7q and GHSA-wq5f-xc86-pv6w; application acceptance of exploitable maps/SVGs was not established | Pin source-map-js 1.2.2 and sharp 0.35.5; lock only those dependency families; npm audit, clean install, build and native image smoke |
| H1 reliability hardening | Low | Worker termination and partial multiprocessing Queue receives | TERM-resistant work can survive cleanup; partial result frames can block receive past its timeout and hang executor shutdown | Atomic private result publication, bounded size, TERM then KILL, cleanup; test timeout, cancellation, partial result, early exit and large success |
| H2 conditional availability hardening | Medium | Generic backend bodies parsed without a measured byte limit | Directly exposed API lacks the bound already provided by Next.js; default Compose API remains loopback-only | Independent measured admission before JSON/form parsing, finite read timeout/concurrency; test chunked/understated/declared limits, safe config failure and preserved auth |
| H3 build reliability | Low | Duplicate exact PCRE2 security revision after an upgrade | Exact stale package revision can prevent builds as signed Debian mirrors advance | One signed package upgrade plus minimum fixed-version assertion, no scanner suppression; optional temporary CA mount for controlled TLS proxies |
| H4 CI hardening | Low | Ordinary CI inherited repository-default token permissions | Write permission is unnecessary for checkout/test/audit jobs; current repository-wide defaults were not inferred | Explicit contents:read; publishing workflow's existing job-scoped permissions are unchanged |

Existing CI npm auditing detects F5. Earlier tests covered hash tampering and
automated authorization but missed F1–F4's alternate representations. New negative
tests run in the normal backend suite; PDF preparse/auth/resource controls and
frontend fail-closed guards remain enabled.

## Targeted architecture review

- Uploads: authentication and measured envelope admission precede multipart parsing;
  extension, content type, PDF signature, file bytes, page count and extracted-text
  limits remain enforced. Filenames are metadata, not filesystem destinations.
  Malformed/unsupported documents fail explicitly, and expensive work is isolated
  behind the worker deadline. Archive formats are not an accepted upload format.
- API and configuration: existing API keys, tenant scoping, safe error responses,
  restricted CORS and startup/readiness checks remain authoritative. Secret-file
  resolution is shared with migration tooling; no real secret was added. Default
  loopback exposure is a deployment assumption, not a substitute for authorization.
- LLM and evidence: no new model tools, environment access or control instructions
  were introduced. Claims still require deterministic source matching. Model text
  cannot replace evidence or directly authorize the final decision.
- Persistence and frontend: PostgreSQL verifies stored bundles on read/write;
  the service supplies its trusted policy before publishing a decision. Restart
  and corrupted-payload tests cover the persisted path. Frontend payload guards
  require final-decision/Assurance/certificate agreement and do not fall back to
  a proposal. No arbitrary HTML rendering or secret-bearing browser setting was added.
- Supply chain: existing hash-pinned Actions and release token scopes were inspected;
  ordinary CI is explicitly read-only. Python dependencies are unchanged. Container
  scans cover both actual local images; no ignore entry or threshold was relaxed.

The full suite initially exposed an old certificate fixture that supplied no paths
while carrying an Assurance proof for real paths. Its valid control now uses the
actual paths and explicitly tests rejection when those paths are removed. The
unreleased changelog heading is also separate from published version metadata.

## Validation commands

Backend matrix uses the existing `scripts.verify_v041_release.python_gate` with
separate real PostgreSQL databases for Python 3.11/3.12. It runs `pip check`,
`pip-audit --strict --no-deps -r requirements.lock`, and the full `pytest
--cov=finrisk --cov-fail-under=90` suite, including slow tests, with XML/coverage
evidence. No test exclusion or coverage reduction is used.

Other authoritative commands: `ruff check backend tests scripts research`,
`npm ci`, `npm audit --omit=dev --audit-level=high`, `npm test`, `npm run lint`,
`npm run typecheck`, `npm run build`, `python -m scripts.verify_v042 --ci`,
`scripts.verify_v041_release.package_gate` (wheel/sdist, both clean interpreter
installs, outside-checkout API/Assurance/certificate smoke), and the existing
Docker HTTP/PostgreSQL/restart/timeout verifiers against locally built images.

Builds in this cloud host require its proxy mapping and trusted CA bundle supplied
with `--secret id=finrisk_ca_bundle,src=/etc/ssl/certs/ca-certificates.crt`.
This is a local build input, not a committed credential, runtime CA change, or TLS
verification bypass. Docker images are unprivileged and must carry no credential
or build-proxy environment defaults. Trivy scans source plus the exact locally
exported image archives, with image IDs checked against `docker image inspect`;
these local IDs are not a claim of remote registry digest attestation.

## Residual boundaries

No hosted LLM credential is present: deterministic/mock paths are used. Prompt
injection cannot be eliminated, content hashes are not issuer signatures, worker
processes are not native-code security sandboxes, and resource limits still require
deployment-level aggregate controls. FinRisk remains UNCALIBRATED; E5 remains
blocked and unfrozen. No external SEC acquisition, live hosted model evaluation,
registry publication or release tag is claimed by local validation. Ordinary remote
CI is separately verified below; it is distinct from a container release dry-run.

### Unfixed base-image findings (additional unfiltered scan)

The existing Trivy gate excludes unfixed advisories. An additional scan without
`--ignore-unfixed` reports **44 HIGH package findings / eight unique CVEs** in the
Debian API image, zero CRITICAL, and zero HIGH/CRITICAL in the Alpine web image.
These are retained findings, not a clean unfiltered API scan or new ignore entries.

| Advisory | Root cause / required attack surface | Assessment in this image |
|---|---|---|
| CVE-2026-76642 | Privileged util-linux mount post-hooks after failed helper | No application mount helper invocation or configured fstab entry; local privileged mount boundary remains a deployment risk |
| CVE-2026-78408 | Root nsenter cgroup descriptor survives credential change | No application nsenter invocation; requires a privileged operator entering an attacker-controlled target |
| CVE-2026-78409 | X-mount.subdir intermediate symlink traversal | No configured fstab entry or application mount invocation; privileged local mount surface |
| CVE-2026-78410 | Restricted bind source redirection and ownership hooks | No configured fstab entry or application mount invocation; privileged local mount surface |
| CVE-2026-54369 | Privileged pathname-based ACL symlink race | No application ACL API or root worker; not identified on the document/API path |
| CVE-2025-69720 | infocmp analyze_string stack overflow | infocmp exists but is not called for uploads or model output; no terminal database ingestion feature |
| CVE-2026-16742 | systemd-homed user-record signature bypass | systemd-homed executable is absent; shared library package advisory remains |
| CVE-2026-9538 | Perl Archive::Tar unbounded declared entry allocation | Perl exists but no Archive::Tar/document archive ingestion is invoked |

Evidence: unfiltered archive reports for the same image IDs, runtime uid 100
(`finrisk`), empty/unconfigured `/etc/fstab`, absent systemd-homed, and source
inspection of subprocess/parser usage. The mount binary retains its upstream SUID
bit; nonroot identity alone is not a claim that every local escalation is impossible.
Do not deploy privileged containers or provide untrusted shell access. Native-code
compromise is outside the worker's guarantees. Debian does not report a fixed
package version in these scan results; track all eight exact CVEs and rescan on
base-image refresh before release promotion. Removing packages or changing distro
without evidence of runtime compatibility was not undertaken in this focused pass.

### Local scan evidence identities

Trivy 0.68.2 ran vulnerability and secret scans at the repository's existing
fixable-vulnerability threshold, plus the unfiltered HIGH/CRITICAL scans above.
The source/fixable API/fixable web reports contain zero reported vulnerabilities
at MEDIUM/HIGH/CRITICAL and zero secrets at those severities. Local JSON files are
cloud-workspace evidence, not published release artifacts.

| Report (`/tmp/finrisk-trivy-*.json`) | SHA-256 |
|---|---|
| source | `0d90e3a12e5a6318390b5faf4b8e22b1444dfd24163ce48f3b42603cbd3b4ad5` |
| api | `464ec422820488e2bb377bf32cb77bc815077076beb5e1114b55695d47b63c4b` |
| web | `6e08da3c92fea09c81871a78cde6be513f981a4c1e6c9e8b1dad9be711d4d1b1` |
| api-all (unfiltered) | `a4d26a76a2038ac9b7b6d9c2227e7283769cb002b76ad78e9bed31643b0369c5` |
| web-all (unfiltered) | `331f5e82f4d52b3ae62f848d29d4eac77c922d8cd718554e752708a0c8911c4a` |

API image ID: `sha256:df7c9a2906f380d205e6b0840d99fa803c077e851ac7b9017b3e69a822e993a8`.
Web image ID: `sha256:512b40e1ecc5ac26f2822803f8b2ea9aacad08861286d1c5bdc14ccaabf9dc0f`.

## Historical security-pass gates (d3d16da)

| Gate | Result | Evidence / command | Notes |
|---|---|---|---|
| Confirmed F1–F4 fixes | PASS | Full backend suite and negative redirect/metadata/Assurance/downgrade/evidence tests | Conservative internal integrity severity; no external certificate import claimed |
| Dependency F5 | PASS | `npm audit --omit=dev --audit-level=high`; indexed-map regression and native sharp SVG resize smoke | Zero npm audit vulnerabilities; only affected dependency families updated |
| Security/reliability regressions | PASS | Full suite including request admission, worker timeout/cancellation/partial results | No tests disabled or excluded |
| Backend Python 3.11 | PASS | Existing `python_gate`, PostgreSQL `finrisk311`; `/tmp/finrisk-final-matrix311.log` | 821 passed, zero skipped/failed, coverage 92.09%, 844.51 seconds |
| Backend Python 3.12 | PASS | Existing `python_gate`, PostgreSQL `finrisk`; `/tmp/finrisk-final-matrix312.log` | 821 passed, zero skipped/failed, coverage 92.09%, 706.27 seconds |
| Static checks | PASS | `ruff check backend tests scripts research`; `git diff --check` | Both supported Python environments |
| Frontend tests/lint/types/build | PASS | `npm test`, `npm run lint`, `npm run typecheck`, `npm run build` | 36 tests on host Node 24 and actual image Node 22; production build succeeds |
| Packaging | PASS | Existing `package_gate`; `/tmp/finrisk-final-package.log` | Wheel and sdist built; package version deliberately still 0.4.1 |
| Clean install | PASS | Clean wheel venvs on 3.11/3.12; `pip check`; outside-checkout `verify_installed_package.py` | API/Assurance/certificate smoke succeeds in both |
| Docker builds/runtime | PASS | Both Dockerfiles; `verify_docker_health.py` on development+production and release Compose | Actual nonroot images; configured trust bundle, no TLS bypass |
| PostgreSQL | PASS | `validate_postgres_migration.py`, full integration suite, `verify_postgres_state.py` before/restart/after in both stacks | Idempotent migration; credentials, entity, certificate and replay survive restart; corruption rejected |
| Assurance/certificate integrity | PASS | Full suite, clean installed package smoke, PostgreSQL certificate/replay checks | Missing hash/proof, policy mismatch and evidence disappearance fail closed |
| Upload security | PASS | Docker authenticated PDF flow, 401/413/415/422/429 contracts, `verify_docker_timeout.py` | Actual analysis path; 504 then explicit retry verified |
| Secrets/configuration | PASS | Trivy source/image secret scans; secret/configuration tests; image environment inspection | No committed real secret or runtime credential/proxy/CA defaults introduced |
| Python dependency scans | PASS | `pip-audit --strict --no-deps -r requirements.lock` and `pip check` on both interpreters | No known audited dependency vulnerabilities |
| Configured Trivy source/image gate | PASS | Trivy 0.68.2, exact source/image reports above, existing `--ignore-unfixed` threshold | Zero fixable MEDIUM/HIGH/CRITICAL and zero scanned secrets; empty ignore policy unchanged |
| Supplemental unfiltered API scan | FAIL | `image --scanners vuln --severity HIGH,CRITICAL`, without `--ignore-unfixed` | 44 HIGH / eight CVEs, zero CRITICAL; no identified API reachability, no published Debian fixes; retained risk table above |
| Supplemental unfiltered web scan | PASS | Same unfiltered command on actual web image | Zero HIGH/CRITICAL |
| Research integrity/provenance | PASS | `python -m scripts.verify_v042 --ci`; empirical provenance validator | Historical/current identities, fitted replay, frozen E4, E4-S 44/44, E4-R 136/136, E5 fail-closed contract; no retraining or historical writes |
| Current development artifact gate | PASS | `python -m scripts.verify_v042 --ci` | Same historical gates with separately bound development identity |
| Original v0.4.1 current-source wrapper | NOT APPLICABLE | `verify_v041.py` / full release wrapper expects original source identity | Not claimed passed on changed source; historical bytes and original source identities checked separately |
| Documentation/version consistency | PASS | 66-document Markdown link check and full version-metadata tests | Unreleased section; no version promotion or stronger security claims |
| SQLite integration | NOT APPLICABLE | Persistence architecture inspection | Supported production-like repository is PostgreSQL; no SQLite implementation found |
| Hosted LLM/SEC acquisition | NOT RUN | No hosted provider credential; offline/mock deterministic paths used | No fabricated credential or live inference claim |
| Ordinary remote CI (security commit) | PASS | [run 37583318142](https://github.com/siqiwang0712-commits/financial-risk-agent/actions/runs/37583318142) | Independently verified public Actions page: Success, full d3d16da SHA, backend 3.11/3.12, frontend and docker-smoke succeeded |
| GHCR release dry-run/attestations (security pass) | NOT RUN | Distinct from ordinary CI | No registry upload, tag or release created by the security pass |

Local security fixes and supported runtime checks are complete for development
review. This does not declare the unfiltered API image clean, authorize release
promotion, validate external empirical claims, or resolve the existing E5 blockers.

## v0.4.2 release preparation

Authoritative current metadata is 0.4.2, the changelog uses the normal dated release
format, and the shipped offline synthetic demo was legitimately regenerated. This
demo is not frozen research evidence. No E4/E4-S/E4-R/v0.4.1 historical data or E5
freeze record was changed.

Run the complete local gate with:

```bash
python -m scripts.verify_v042_release --python311 /path/to/python3.11 --python312 /path/to/python3.12
```

A real `DATABASE_URL` is required; separate `FINRISK_GATE_DATABASE_URL311` and
`FINRISK_GATE_DATABASE_URL312` may be supplied for independent matrix databases.
The gate retains full tests, coverage, audits, clean installs, research verifiers
and both Compose paths. It builds candidates once and checks exact local image IDs
for API, web and migration containers; these IDs do not claim registry attestations.
Optional build-network/host/CA inputs support controlled cloud proxies without
disabling TLS. `--build-no-cache` refreshes signed package installation layers.


Release preparation also fixes a publication-condition defect: the previous
`inputs.publish || tag-ref` condition could promote a manual `publish=false` run
on a tag. Publication now requires either a tag **push event**, or an explicit
`workflow_dispatch` with `publish=true`, plus successful verification and scanning.
Eight tests evaluate the actual checked-in workflow condition, including a manual
tag dry-run and failed prerequisites. No workflow with `publish=true` was invoked.

The aggregate gate also exposed historical synthetic reference drift: its stored
source-fixture hash binds CRLF bytes, while Linux materialized LF. All parsed data
and reference statistics matched. `.gitattributes` now preserves the original CRLF
source representation, and a strict raw-byte regression plus ordinary CI verify it.
The reference file, stored hash, source Git blob and historical results are unchanged.

### Release-preparation findings and environment evidence

| ID / class | Severity | Root cause | Change / regression protection |
|---|---|---|---|
| R1 release-control defect | Medium | A manual tag dry-run satisfied the tag publication disjunction | Event-specific publication condition; eight tests evaluate the actual workflow, including `publish=false` on tags and failed prerequisites |
| R2 historical verifier portability | Low | The approved synthetic reference hashes CRLF bytes, but Linux checked out LF | Preserve original bytes through `.gitattributes`; strict raw-hash test and ordinary artifact verification; no historical artifact/hash regeneration |
| R3 dependency advisories | Medium (reported severity) | Next.js 15.5.25 contains CVE-2026-94484 / CVE-2026-94543; pinned Node image carries zlib 1.3.2-r0, affected by CVE-2026-85091 | Next.js/ESLint 15.5.27, refreshed pinned Node 22.23.3 base, signed Alpine package upgrade with minimum zlib 1.3.2-r1; clean install, build, HTTP and exact-image scans |
| R4 gate diagnosability | Low / reliability | Disposable-container cleanup removed the logs needed to investigate a startup failure | Collect logs before cleanup while preserving the original exception; regression asserts collection order and failure propagation |

R3 was identified by the refreshed Trivy DB published on 2026-10-08, after the
initial source scan. The web pre-fix scan reported three fixable MEDIUM findings,
not secrets or HIGH/CRITICAL findings. The disclosed Next.js exploit scenarios
involve root catch-all/Pages Router response caching; the application uses the App
Router and no such application exploit was established. The zlib advisory requires
particular native nonblocking gzip-write calls; API reachability was not established.
These are dependency advisories, not claims of demonstrated application compromise.
The Alpine `3.24-stable` package recipe independently confirms zlib 1.3.2, revision 1.

The initial Docker aggregate reported an unhealthy first PostgreSQL start. A fresh
same-configuration instance became healthy; the original logs had already been
removed by cleanup, so its precise cause is not claimed. A later attempt explicitly
hit cloud disk exhaustion. Disposable build cache and an unused investigation base
image were removed; historical reports, image archives and research artifacts were
retained. No OOM kill was recorded. These failed attempts are not passing evidence.

Initial direct probes returned HTTP 403 for `dl-cdn.alpinelinux.org` and
`api.github.com`. A network configuration draft adds only those destinations;
saving it does not apply or publish it. The final Docker build nevertheless
succeeded through the configured build-proxy route, with uppercase/lowercase proxy
arguments and the optional trusted CA mount: its actual log records the signed
zlib upgrade `1.3.2-r0 -> 1.3.2-r1`, and the final image independently reports that
version and Node 22.23.3. No TLS or APK signature check was bypassed, no alternate
unsigned package was installed, and the minimum-version assertion remains mandatory.
The earlier failed probes are not claimed as passing build evidence.

Ordinary CI now runs the same complete container gate on both Compose paths,
including all prior upload/auth/limits/restart/timeout checks, migration idempotence
and the PostgreSQL integration suite. It builds once, pins API/web/migrate to local
image IDs, scans those IDs, verifies report image identities, uploads the reports,
and publishes counts/advisory IDs in its Actions job summary. This adds verification;
it does not dispatch the GHCR release pipeline or promote any image. Report collection
or scanner execution errors fail CI. All external actions remain commit-pinned and
the default token remains `contents: read`.

For the final source commit, consult the
[ordinary CI runs for this branch](https://github.com/siqiwang0712-commits/financial-risk-agent/actions/workflows/ci.yml?query=branch%3Atry-v0.4.2)
and their Docker job summaries/`v042-container-verification` artifact. Match the
full commit SHA. The historical successful run above is not evidence for a later
commit. The GHCR `version=v0.4.2, publish=false` dry-run is a separate registry-digest
verification and must be dispatched independently; actual publication is a third
operation and was not authorized or performed by release preparation.

### Final local release gates

The final `python -m scripts.verify_v042_release` invocation exited **0** and
printed `LOCAL v0.4.2 RELEASE GATE: PASS`. Cloud-specific arguments used the actual
`/usr/local/bin/docker`, host build networking, the proxy mapping, mounted trust
bundle and `--build-no-cache`; npm/pip caches stayed under writable `/workspace`.
Disposable BuildKit cache was reclaimed after both builds completed to accommodate
the cloud's 32 GiB filesystem and VFS storage driver. Both Compose runs continued
to use the same already-built image IDs; no rebuild, security-policy change or
historical artifact deletion occurred.

| Gate | Result | Evidence / command | Notes |
|---|---|---|---|
| Python 3.11 | PASS | Full `python_gate`; XML and coverage under `.runtime/v042-release-gate` | 839 passed, 0 skipped/failed; 92.09% coverage; 865.73 s; `pip check` and strict locked `pip-audit` passed |
| Python 3.12 | PASS | Same complete gate | 839 passed, 0 skipped/failed; 92.09% coverage; 738.26 s; `pip check` and strict locked `pip-audit` passed |
| Frontend | PASS | `npm ci`; production audit; test/lint/typecheck/build | 36 tests; zero production audit findings; Next.js 15.5.27 |
| Packaging / clean install | PASS | Wheel/sdist and both clean wheel environments; outside-checkout verifier | Package/API 0.4.2 and verified Assurance certificate on both interpreters |
| Docker / HTTP / upload | PASS | Complete `container_gate`, development and release Compose | Same API/web/migrate IDs, authenticated PDF workflow, 401/413/415/422/429 and 504/retry contracts |
| PostgreSQL / authorization integrity | PASS | Idempotent migration, 13 integration tests, before/restart/after verifiers on both stacks | Credential/entity/certificate/replay persistence and corrupted-state rejection |
| Additional current-source runtime | PASS | API on :18000, Next.js 15.5.27 on :3300, isolated real PostgreSQL; original HTTP/state/timeout verifiers | Auth/upload/limits, migration, certificate/replay restart and explicit timeout/retry checks |
| Research / provenance | PASS | `python -m scripts.verify_v042 --ci`, frozen E4, E4-S, E4-R and E5 report-only checks | 44/44 E4-S and 136/136 E4-R; E5 NOT_FROZEN; protected historical paths unchanged |
| Source / image scans | PASS | Trivy 0.68.2 with refreshed 2026-10-08 DB; vulnerability and secret scanners | Zero fixable MEDIUM/HIGH/CRITICAL and zero secrets on source and both tested images |
| Unfiltered image inventory | PASS | Supplemental scans executed without `--ignore-unfixed`; report IDs match candidates | API: 44 HIGH / eight unfixed CVEs, zero CRITICAL; web: zero HIGH/CRITICAL; not a clean unfiltered API claim |
| Supplemental full npm audit | FAIL | `npm audit --json` including development dependencies | Five HIGH propagated findings from one unfixed development-only braces advisory; assessment below; production audit gate passes |
| Docs / static / version | PASS | 70-document link verifier; Ruff; `git diff --check`; release metadata verifier | All current versions 0.4.2; historical 0.4.1 references retained |
| Aggregate local release gate | PASS | `/tmp/finrisk-v042-final-release-gate.log` | Exit 0; failures from earlier attempts remain separate records |
| Hosted LLM evaluation | NOT RUN | No hosted provider credential | Designed deterministic/mock paths used; no live-model resistance claim |

Final local candidate image IDs (not GHCR manifest digests):

- API: `sha256:26f884aadda84f82870f124ad3b291e15010c1e365f726f9f109cf739ab9834d`.
- Web: `sha256:8987eda0bc44048660c61660cdd7a60ecddb58da3e1d8cb72fea50812b891f47`.

| Report under `/tmp/finrisk-v042-release-trivy-` | SHA-256 |
|---|---|
| source-final.json | `96c7d177b82c119f01fa1f24369dd6cf442a00258ecd56961f697ddad525f563` |
| api.json | `080f7decab27848581883adeae01d88a46652d427866b459268bb1dfd23181ba` |
| api-all.json | `2af46dda8631995b7504c446785441dab25921f0f39e20aad1b5b47280ddacb4` |
| web.json | `78dc97db075466a834322cd7a60cf274bf1048cbaea993e6ffa679fb94cc337d` |
| web-all.json | `bc7b87638b40b006dfcfdd5e5ee9b3bb4e1b327af22388e9ae9669c9282c09fc` |

### Unfixed development-tool dependency advisory

The supplemental full npm inventory records **GHSA-vfj7-8cjw-p6xm**, HIGH:
`braces <=3.0.3` can exhaust the stack on deeply nested glob patterns. The five
reported packages are braces plus its micromatch, fast-glob, Next ESLint plugin
and ESLint config dependents; these are not five independent vulnerabilities.
All are `dev: true` in the lockfile, and all five `require.resolve` checks fail
with MODULE_NOT_FOUND in the final standalone runtime image. User documents and
HTTP input do not supply ESLint glob patterns. Malicious repository code/config
is already executable in the build/test trust boundary; the remaining concern is
build/lint availability, not an established application-request exploit.

The registry still reports braces 3.0.3 as latest. No fixed compatible published
package was identified. npm's suggested forced downgrade to ESLint/Next 14 is not
a compatible repair and would undo the current patched framework configuration.
Existing lint, production audits, scanner thresholds and the empty `.trivyignore`
remain enabled; no advisory suppression was added. Recheck this exact advisory
before promotion and when braces publishes a fixed release. The full audit is
retained as a failing supplemental inventory, not represented as a clean audit.


## Adversarial follow-up — 2026-10-09

Starting source: `6a6c6b38411fb8d72c8c3a62cf319e67aeda223e`. Earlier
measurements above remain evidence for that candidate, not subsequent changes.

| Severity / class | Failure and root cause | Fix and regression protection |
|---|---|---|
| Medium / integrity | Rehashed Assurance accepted malformed sufficient evidence, contradictory ablation/distribution statistics, fabricated calibrated probability/reasons, automated FLAG despite fragile evidence, and REVIEW after parser failure. Hash checks did not fully verify semantics. | Exact nested fields/types, finite measurements, identities/aggregates, sufficient-evidence search representation, diagnostic/reason/blocker and final/automation transitions are checked. Even self-consistent ablations must ABSTAIN with no score delta when the last source is removed. Rehashed negative tests failed before fixes; certificate wrapping, JSON round trips and evaluator positives are tested. |
| Medium / persistence integrity | Valid certificates could be relabelled, and a valid sibling payload or corrupted column hash could replace a requested ledger record. | Enforce content-addressed v0.4 IDs; bind reads to requested ID/tenant/entity and stored column hash. In-memory writes/reads also verify integrity. Real PostgreSQL reconnection and in-memory swap tests failed before fixes and reject corruption afterward; legacy v0.3 remains separate. |
| Medium / availability | A second cancellation interrupted cleanup and left a live worker. | Shield and await a strongly referenced reclamation task through repeated cancellation; reject invalid budgets before spawning. A SIGTERM-ignoring regression proves the old leak and PID reclamation after the fix. |
| Medium / release verification | Publication did not require full ordinary CI for the exact source. | The newest matching push CI and all four required jobs must succeed before builds. Other sources/workflows/forks, stale success, failed/cancelled/skipped/missing/duplicate jobs are rejected; the script was exercised against real CI. Only prepare receives actions:read. |
| Low / resource hardening | Oversized multipart metadata reached PDF workers; result limits were checked after oversized partial files were written. | Match JSON company/year limits, bound document names before workers, and enforce quota before every pickle byte write. Metadata/partial-file regressions failed before fixes; valid uploads and large IPC results remain tested. |
| Low / verification | Trivy report identity used substring membership. | Require complete lowercase SHA-256 and exact @digest equality. Tag text, trailing suffixes and truncated digests are rejected; valid empty scan results remain accepted. |
| Low / verification hardening | Digest checks did not independently check OCI source/version. | Both remote Compose paths and the local gate check expected metadata and non-root user. Wrong/missing metadata is rejected; artifact ID/digest and migration/scan binding are retained. |
| Low / container hardening | API inherited unnecessary mount utilities and privilege bits. | Purge only the independently removable mount package, clear SUID/SGID, and inspect the exact candidate. No essential-package override, autoremove, ignore or scan threshold change. Runtime/PDF/PostgreSQL/migration checks protect compatibility. |

The verifier checks observable serialized invariants, not issuer authenticity. It
cannot reconstruct omitted financial inputs, disagreement scalars, reference bounds
or the entire subset search. New publication requires a trusted supplied policy
and authenticated storage. Legacy v0.3 verification remains separate; default
maturity/calibration remain HEURISTIC_POLICY / UNCALIBRATED.

Publication conditions, digest subjects for SBOM/attestations, migration reuse of
API and scanner execution/report binding were reviewed. Candidate tags are registry
locators; verification and promotion use recorded digests. Manual publish=false,
including dispatch from a tag, cannot publish. No release publication or Git tag
creation is part of this follow-up.

Request measurement, authentication before multipart parsing, read budgets,
admission capacity, partial publication, redirects and untrusted document-role
handling retain existing negative tests. Workers are not a native-code sandbox;
prompt injection remains a residual risk. No external audit/certification is claimed.

Only current v0.4.2 source identities were updated. Frozen E4/E4-S/E4-R/v0.4.1
identities/results were not regenerated. E5 remains BLOCKED / DRAFT_NOT_FROZEN.

On small Docker VFS hosts the local gate supports `--prune-build-cache`: it
reclaims only completed build caches between images, preserving the candidates
and all runtime/security checks. Space-exhausted runs are failures, not passing
validation. Prior local development/candidate images were archived with verified
config identities before removing recoverable copies; database volumes and
historical research/scan evidence were retained.

### Final-source local verification

`python -m scripts.verify_v042_release --python311 <3.11 interpreter>
--python312 <3.12 interpreter> --prune-build-cache` completed successfully on
2026-10-09. Cloud builds additionally used the existing optional host network,
proxy host and CA bundle mount; TLS/signature validation remained enabled.
The full log is `/tmp/finrisk-adversarial-release-gate-validated.log`.

| Gate | Result | Executed evidence |
|---|---|---|
| Backend 3.11 / 3.12 | PASS | Full pytest with real PostgreSQL: 927 tests per interpreter, 92.18% coverage each; required minimum remains 90% |
| Python/static | PASS | Both `pip check` and `pip-audit --strict --no-deps -r requirements.lock`; Ruff; `git diff --check` |
| Assurance/certificates/persistence | PASS | Rehashed semantic negatives, content-addressed IDs, in-memory swap and PostgreSQL payload/column corruption rejection in full suite; 16 container PostgreSQL tests |
| Research/provenance | PASS | `python -m scripts.verify_v042 --ci`; frozen E4; E4-S 44/44, E4-R 136/136; prospective E5 preflight and NOT_FROZEN checks |
| Frontend | PASS | `npm ci`, 36 tests, lint, typecheck, production build; `npm audit --omit=dev --audit-level=high` reports zero |
| Complete npm inventory | FAIL / residual | Full `npm audit --json`: five HIGH development package entries for the single unfixed GHSA-vfj7-8cjw-p6xm; no suppression or compatible fixed package identified |
| Packaging | PASS | Wheel and sdist; clean 3.11/3.12 installs; `pip check` and outside-checkout API/Assurance/certificate smoke report 0.4.2 |
| Container/runtime | PASS | API/web builds; OCI source/version and privilege checks; both Compose stacks use the same image IDs; API/web/migrate identity, migration idempotence, persistence/restart and certificate/replay checks |
| HTTP/request/process | PASS | Authenticated document workflow; 401/413/415/422/429 negative contracts; production timeout/retry 504 twice; repeated-cancellation worker reclamation and pre-write quotas |
| Source/image policy scans | PASS | Trivy 0.68.2: source and exact tested API/web images; MEDIUM/HIGH/CRITICAL fixable vulnerability and secret scans report zero |
| Unfiltered image scans | FAIL / residual API | Scanner execution/identity PASS; API 40 HIGH package findings, eight unfixed CVEs, zero CRITICAL; web zero HIGH/CRITICAL |
| Release/documentation | PASS | Aggregate local release gate; all current versions remain 0.4.2; 70-document Markdown link check |

Ordinary GitHub CI and the registry `publish=false` workflow are separate
post-push checks for the new commit. Their exact run IDs and outcomes belong to
the completion report and Actions evidence; earlier runs above cannot validate
this follow-up. No production promotion, tag or release creation is authorized.

The new unfiltered API result has four fewer package findings because `mount`
was removed. All remaining findings lack `FixedVersion` in the fresh official
Trivy database. The same eight advisories remain: CVE-2025-69720,
CVE-2026-16742, CVE-2026-54369, CVE-2026-76642, CVE-2026-78408,
CVE-2026-78409, CVE-2026-78410 and CVE-2026-9538. Necessary Debian
libraries remain installed; SUID/SGID utilities are disabled. No application
request exploit was established, but absence of reachability proof is not a
clean scan or a guarantee. Review the residual-risk table above and rescan
before promotion; no vulnerability ignore or threshold was changed.

Local image IDs (configuration identities, not registry digests):

- api: `sha256:8473d0d7aab37d4f02737c73dc025644c0d6095e41840b702362c88ce8cbbdeb`

- web: `sha256:1f0b58dfd5eec899e4611ec59c4b1b5e46ce182e46ef30438145cb8d790dc871`

Validated Trivy report SHA-256 identities:

- `finrisk-adversarial-source-validated.json`: `70dda23d5eae9581c76dffefb266c74672b07fa3cfa51eb414f72413e5ccfc6c`

- `finrisk-adversarial-api-policy-validated.json`: `969b5f859490cafeacf59dbb614b7e8b01bf27f62db8935a2ff23bcd053336b4`

- `finrisk-adversarial-web-policy-validated.json`: `d4be5f095613c99c2231a952ef2f56df1a8e2ab21de4ae1fd87bef6045bb7041`

- `finrisk-adversarial-api-unfiltered-validated.json`: `e568caf01c02a309b1233a5b6dff8dcfed7e2c7c368e9e289b421c4229c916da`

- `finrisk-adversarial-web-unfiltered-validated.json`: `8f703dddfdcaeb8aed72328ee402139763cae47844d3bcf7e69106baba9278ba`
