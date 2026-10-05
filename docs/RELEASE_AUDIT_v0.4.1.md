# FinRisk v0.4.1 — Final Release Audit

Status: **RELEASED — ENGINEERING RELEASE GATES PASSED**

Engineering release status does not establish prospective, external, production,
regulatory, calibrated or safety validity.

## 1. Release identity

| Identity | Value |
|---|---|
| Software version / release date | v0.4.1 / 2026-10-05 |
| Final preparation branch | `try-v0.4.1` |
| Final runtime source tested by normal CI and Container Release | `00fc338f73be0529a4adc6a1705d518af7bf8030` |
| Python package / frontend package | `0.4.1` / `0.4.1` |
| Documentation closeout source | Documentation-only successor to the runtime SHA; exact commit identity is recorded in Git history |

This is the maintainer-requested final release-state documentation snapshot. The
closeout operation commits and pushes documentation only; it does not create a tag,
GitHub Release or container release tag. Those publication actions remain with the
maintainer. The engineering evidence below records a non-publishing dry-run, not a
claim that release images or attestations have already been published.

The reviewed runtime fixes include `85e0e5dac5015c41973acf42cd03aa110789f46a`,
`dd2f03aa885444b6b3f6fce7a953d8b04ea961c5`,
`b91462742b30e8271eff27f2bca5c1225588a3bd` and the retained-report fix in the final
runtime SHA. Documentation-only changes do not alter those tested runtime files.
They do create a new source identity: rebuilding an image from the closeout commit
can change its OCI revision and digest. Do not attribute the tested digests below to
that new build or assume a future publication digest without checking its own run.

## 2. Final verdict

The research-prototype software satisfies the audited engineering gates: both supported
Python versions, unchanged coverage threshold, frontend, clean package installs,
research integrity, and digest-bound real-stack/container security checks passed.
The final normal CI and Container Release dry-run completed successfully; report retention
was verified by downloading and inspecting the actual artifact.

The local Docker aggregate check remained blocked by the host environment. Remote
real-stack evidence supplies the deployment verification; it does not rewrite the local
failure as a pass. E5 remains `BLOCKED / DRAFT_NOT_FROZEN / NOT EXECUTED`.

## 3. Issues found and resolved

| Area | Finding | Disposition |
|---|---|---|
| Upload admission | Multipart files were parsed/spooled before authentication and the file ceiling. | Authenticate before reading; measured aggregate ceiling plus 64 KiB framing; 30-second body budget; two requests per process; retain file/page/text/worker limits. |
| Numeric proof | A verified quotation could label a contradiction verified without numeric provenance. | Bind every adverse current/prior input; reject legacy quote-only paths in Assurance and case proof/evidence readers. |
| Assurance payload | A recomputed hash did not reject non-boolean automation or policy-blocked fragility states. | Structural and policy consistency checks now fail closed; hashes remain integrity checks, not issuer signatures. |
| Workbench | Matching null/undefined decision fields could escape the presentation helper. | Missing/invalid authorization stays `UNAUTHORIZED`; never fall back to the proposal. |
| Mounted LLM secret | `OPENAI_API_KEY_FILE` was documented but not read by the provider. | Use the existing file-secret helper; file precedence and unreadable-file failure are tested. |
| Secret wording | File precedence was incorrectly described as removing inline environment secrets. | Clarify that inline DSNs/secrets still appear in container inspection; operators must mount files and remove inline values. |
| Local release gate | Interpreter identities, dependency audits and outside-checkout wheel imports were not all enforced. | Verify interpreter versions, audit both stacks, assert installed resources, isolate Compose cleanup, retain the 90% threshold and all checks. |
| Metadata | Released v0.4.0 was still `Unreleased`; workflow examples used earlier release identifiers. | Preserve v0.4.0's 2026-10-02 date, record v0.4.1's 2026-10-05 date, and use generic release-tag mechanics. |
| Verification prose | Old local test/coverage totals were duplicated. | Centralize the current evidence here; distinguish local, normal CI and digest-bound release checks. |
| Retained scan evidence | The first dry-run validated JSON reports, but the uploader excluded hidden `.runtime/` files and silently retained nothing. | Explicitly include hidden files only for `.runtime/trivy-*.json`; missing upload files are an error. A regression test reproduces the old failure. |

## 4. Local verification, 2026-10-05

| Check | Actual result |
|---|---|
| Python 3.11.16 full pytest | 763 passed, 18 skipped, 84 warnings; 91.09% line coverage; 497.99 seconds |
| Python 3.12.14 full pytest | 763 passed, 18 skipped, 84 warnings; 91.09% line coverage; 387.63 seconds |
| Required coverage | Unchanged: at least 90% |
| Ruff | Pass: `backend tests scripts research` |
| Dependency consistency/security | Both `pip check` and locked `pip-audit --strict --no-deps` pass; no known vulnerabilities found |
| Frontend | 34 tests pass, no skips; clean install, production npm audit (0 vulnerabilities), lint, TypeScript, production build pass |
| Packaging | One `finrisk_agent-0.4.1-py3-none-any.whl` and one `finrisk_agent-0.4.1.tar.gz`; clean 3.11/3.12 wheel installs outside checkout both pass API/pipeline/Assurance/certificate smoke |
| StrongTabularReference | Checked-in schema/data/selection/OOF/metrics/hashes and pinned-3.12 replay pass; no canonical refit |
| Historical integrity | E4 public checks pass; E4-S 44/44; E4-R 136/136; no empirical artifact modified |
| E5 | Preflight passes by correctly reporting `BLOCKED / DRAFT_NOT_FROZEN`; freeze chain `NOT_FROZEN` |
| Synthetic/reference checks | Demo fixture and development reference reproduce; updated demo remains explicitly synthetic |
| Links/whitespace | Markdown link checker and `git diff --check` pass |
| Local Docker aggregate gate | **BLOCKED BY HOST ENVIRONMENT**, not passed: Desktop's Linux-engine pipe is absent; official start/restart did not recover it |

The 18 local skips are 12 real-PostgreSQL tests and six deployed-HTTP contract tests.
All ran in the final normal CI matrix below. The 84 pytest warnings comprise 32
expected all-missing-feature imputation warnings, 50 upstream scikit-learn `penalty`
deprecations (future compatibility work), and two intentional single-class-fold warnings.
No new filters or suppressions were added. pip-audit recommends full dependency hashes;
npm reports an upstream ESLint support deprecation. These do not conceal test failures.

Security source review found the two upload/numeric-proof issues above and included an
independent boundary investigation and one candidate bypass/regression review. Focused
tests confirm rejection of the original trigger classes and preservation of legitimate
uploads/provenance. This is not a claim of exhaustive line-level security coverage of
every research-statistics, test, data and documentation file, nor a production security
certification. Trusted pickle artifacts remain hash-checked before loading; arbitrary
untrusted serialized models must not be loaded.

### Exact local commands

```powershell
$env:FINRISK_LLM_PROVIDER = 'mock'
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
.runtime/v041-audit-py312/Scripts/python.exe scripts/verify_v041_release.py `
  --python311 .runtime/v041-audit-py311/Scripts/python.exe `
  --python312 .runtime/v041-audit-py312/Scripts/python.exe `
  --docker-bin 'C:\Users\WSQ\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe' `
  --npm 'C:\Program Files\nodejs\npm.cmd'
```

The command passed all preceding stages and stopped at the first Docker build. Retained
local evidence is in ignored `.runtime/final-release-gate-03.log` and
`.runtime/v041-release-gate/{tests-311.xml,tests-312.xml,coverage-311.json,coverage-312.json}`.
Individual stage commands remain visible in `scripts/verify_v041_release.py`.
`scripts/verify_v041.py` checks research/version/provenance artifacts without retraining;
it is not the complete deployment/release gate.

After the report-upload regression fix, both full backend suites were rerun with
independent coverage files. Their final counts above come from
`.runtime/final-matrix{311,312}-isolated.log`, with XML/JSON outputs in
`.runtime/v041-final-matrix/`; the earlier aggregate-gate log predates that extra test.
The commands, repeated for `311` and `312`, are:

```powershell
$env:COVERAGE_FILE = '.runtime/coverage-final312'
.runtime/v041-audit-py312/Scripts/python.exe -m pytest --cov=finrisk `
  --cov-report=term-missing --cov-fail-under=90 `
  --cov-report=json:.runtime/v041-final-matrix/coverage-312.json `
  --junitxml=.runtime/v041-final-matrix/tests-312.xml `
  --basetemp=.runtime/pytest-final-matrix312-isolated `
  -o cache_dir=.runtime/pytest-cache-final-matrix312-isolated
```

## 5. Final normal CI evidence

[Normal CI run 37302574534](https://github.com/siqiwang0712-commits/financial-risk-agent/actions/runs/37302574534)
completed successfully on `00fc338f73be0529a4adc6a1705d518af7bf8030`.

| Job | Result |
|---|---|
| backend (3.11), job 111738547973 | 781 passed, 0 skipped, 84 warnings; 92.08% coverage; 300.71 seconds |
| backend (3.12), job 111738548019 | 781 passed, 0 skipped, 84 warnings; 92.08% coverage; 559.42 seconds |
| frontend, job 111738547904 | 34 tests passed; production dependency audit, lint, TypeScript and build passed |
| docker-smoke, job 111738547727 | Real PostgreSQL/Compose health, authenticated workflow, persistence/restart and timeout/retry passed |

Both backend jobs passed Ruff, dependency consistency/audits and idempotent PostgreSQL
migration checks. The research verification stage passed the fitted reference replay,
runtime identities, E5 preflight, E4 public integrity, E4-S 44/44, E4-R 136/136 and
Markdown links. The 90% coverage gate was not lowered. Linux ran the 18 real-stack tests
skipped on local Windows; therefore the local and remote totals/coverage are deliberately
reported separately, not normalized into one number.

## 6. Final Container Release dry-run

[Container Release run 37302629899](https://github.com/siqiwang0712-commits/financial-risk-agent/actions/runs/37302629899)
completed successfully on the same runtime SHA, with `workflow_dispatch`,
`version=v0.4.1`, `publish=false`.

| Job | Result |
|---|---|
| prepare / build-api / build-web | Passed; candidate images built once |
| verify, job 111739084097 | Passed on exact candidate digests: migration, schema sentinels, readiness/liveness, bootstrap/authentication, API serialization, Assurance/certificate flow, restart retrieval/replay and timeout/retry |
| verify-release-compose, job 111739084112 | Passed on those same digests; operator-facing stack, migration, health, authentication and PostgreSQL restart persistence verified |
| scan, job 111739084124 | API/Web vulnerability scans, secret scans, image-secret checks and digest-bound JSON verification passed |
| dry-run | Passed; explicitly recorded that no release tags were published |
| publish | Intentionally skipped; no SBOM/attestation promotion or release-tag publication claimed from this run |

The earlier [dry-run 37300287238](https://github.com/siqiwang0712-commits/financial-risk-agent/actions/runs/37300287238)
at `21b670ef8fee4615a660a34e8e4ca04038e05edf` was green but failed to retain Trivy JSON
files because the uploader excluded hidden paths. It was rejected as insufficient final
evidence. The final runtime commit fixed that uploader, added a regression test and
passed the new dry-run with actual report download/inspection. That issue is resolved,
not an outstanding requirement for another audit dry-run.

## 7. Artifact and security evidence

Candidate tag: `candidate-00fc338-37302629899`; platform: `linux/amd64`.
Both build outputs, both runtime verification jobs and scans used these exact digests:

| Image | Verified candidate digest |
|---|---|
| `financial-risk-agent-api` (also `migrate`) | `sha256:a0a1eefcaff46174782fe7bf453059123ac6e3adf2a640dfedb545e5fe36bb44` |
| `financial-risk-agent-web` | `sha256:adc32489b6d4e105fa6de792f9655466ac51e511ce13d3a9c425b14d7f071358` |

The run retained `trivy-results`, artifact ID **11342570650**, a **50,408-byte** ZIP.
Its downloaded archive SHA-256 was
`d9568ae7f816cbfd0a0084ec8ec42c16c2cf525a878a99aab9b880641b105415`.
It contains `trivy-api.json` and `trivy-web.json`, each valid schema-2 JSON bound to
the appropriate candidate digest and containing zero recorded vulnerability findings
**under the configured `CRITICAL,HIGH`, `--ignore-unfixed` scan policy**.
The separate `CRITICAL,HIGH,MEDIUM` secret scans also passed. `.trivyignore` has no
suppressed findings. This is scoped scan evidence, not proof that all vulnerabilities,
all severities or future advisories are absent. Actions artifact retention is finite;
the recorded run/artifact identities identify the inspected evidence.

## 8. Research-integrity boundary

Original frozen E4 has **674** verified outcomes (235 events). E4-S replication and
StrongTabularReference development have **675** verified companies/observations
(235 events, 440 non-events); these are different historical objects, not inconsistent
counts. Every one of the **2,000** E4-S source companies remains a future E5 exclusion.
Historical E1–E4-R evidence and fitted reference artifacts are byte-unchanged. Development
metrics remain design-exposed retrospective evidence, not unbiased or prospective
validation. Scores and policy remain `UNCALIBRATED`; E5 remains
`BLOCKED / DRAFT_NOT_FROZEN / NOT EXECUTED`.

Canonical historical-development metrics remain AUROC `0.8817891682785299`, PR-AUC
`0.8289679250748645`, and descriptive uncalibrated Brier `0.12812086027177813`.
They are `RETROSPECTIVE_DEVELOPMENT_SELECTION_METRICS`, `DESIGN_EXPOSED`, not prospective
or external estimates. E4-R's negative competitive finding remains unchanged. S2/S3/S4
are not estimable from this tabular development packet. Release documentation changes
no empirical number, fitted model, frozen CSV/JSON, OOF prediction or manifest hash.

## 9. Remaining limitations and future work

- **Engineering:** local Docker Desktop remains unavailable; Linux/ARM64, managed
  production storage, operational chaos testing and production SLAs are not established.
  Upstream dependency deprecations require future maintenance, not suppressed failures.
- **Research:** E5 needs an untouched future window/cohort, final arm/reference identities,
  primary estimands, multiplicity/effect thresholds, the unpublished 270-company
  exclusion, prospective isolation proof, prediction freeze and outcome unlock.
- **Calibration/reference validity:** the policy is heuristic and scores uncalibrated.
  The empirical profile is `EMPIRICAL_DEVELOPMENT_REFERENCE_ONLY`, historically exposed,
  research-only, not externally/production validated or E5-frozen.
- **External/production/regulatory/safety:** none is established by these engineering
  gates. Human review remains necessary for material financial decisions.

These are explicit maturity boundaries and future work, not hidden failed release gates.
