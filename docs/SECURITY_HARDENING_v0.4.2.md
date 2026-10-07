# FinRisk v0.4.2 development security pass

Development changes on `try-v0.4.2`, based on
`e60abba2976e389ddf80a147227a56cc4cad8e06`. This is not a release publication,
external audit, or production readiness certification. Package and OCI default
versions remain 0.4.1 pending the explicit release versioning step.

## Branch and research integrity

Before edits, `git status`, `git branch --show-current`, `git log -n 10 --oneline
--decorate`, and `git remote -v` showed a clean `work` checkout at the base above,
with the expected HTTPS GitHub origin. Its fetch configuration initially covered
only `main`. The target branch was fetched explicitly, checked out with tracking,
and verified clean and equal to `origin/try-v0.4.2` before source modifications.
No main commit, tag, release, history rewrite, or research retraining is authorized.

The historical v0.4.1 runtime identity file is retained byte-for-byte and checked
against its original source at the pinned base. New identities under
`research/v042_development/` explicitly describe development only and bind current
security-boundary sources. The old v0.4.1 current-source identity check intentionally
fails on changed implementation; CI uses the new development verifier which runs
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
remote CI run, registry publication or release tag is claimed by local validation.

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

## Final local readiness gates

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
| Remote CI/GHCR release dry-run/attestations | NOT RUN | Local execution only | Required for actual release promotion; no registry upload, tag or release created |

Local security fixes and supported runtime checks are complete for development
review. This does not declare the unfiltered API image clean, authorize release
promotion, validate external empirical claims, or resolve the existing E5 blockers.
