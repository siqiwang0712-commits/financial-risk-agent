# Container release (GHCR)

How FinRisk container images are built, verified and published, and what the published
artifacts actually guarantee.

Workflow: `.github/workflows/container-release.yml`
Stack for end users: `docker-compose.release.yml`
Stack used by the pipeline: `docker-compose.yml` + `docker-compose.prod.yml` + `docker-compose.candidate.yml`

## Images

| image | contents |
|---|---|
| `ghcr.io/siqiwang0712-commits/financial-risk-agent-api` | FastAPI backend. Also runs the one-shot migration job. |
| `ghcr.io/siqiwang0712-commits/financial-risk-agent-web` | Next.js standalone Workbench (reverse-proxies `/api/*` to the API). |

There are exactly two images. PostgreSQL is **not** repackaged: the stacks use the
official `postgres:17-alpine`, because pinning the upstream digest already gives
reproducibility and a database is not something this project should re-release. The
migration service reuses the **API image** — there is no third image, so the job that
applies migrations and the process that serves traffic are bit-for-bit the same artifact
and cannot drift apart.

## The invariant

> Build once → test that exact image → verify → attest → promote that exact digest.

Concretely:

1. `build-api` / `build-web` build the images **once** and publish them under an
   immutable, non-release `candidate-<sha>-<run-id>` tag. Their digests are recorded.
2. `verify` starts a real Compose stack from `repo@sha256:<digest>` — the `build:`
   sections are deleted by `docker-compose.candidate.yml` using Compose's `!reset`, so
   nothing is rebuilt — and runs the project's full runtime gate chain against it.
3. `scan` runs Trivy against the same digest.
4. `publish` attaches SBOM and build-provenance attestations to that digest and then
   adds `v0.3.x`, `sha-<commit>` and `latest` to it, and deletes the candidate tag.
   Promotion is a registry-side copy: the manifest bytes for the verified digest are
   `GET` under their own `Content-Type` and `PUT` under each tag, then the
   `docker-content-digest` the registry computes for the tag is read back and required
   to equal the verified digest.

**Why promotion cannot use `docker tag`/`docker push`.** Buildx publishes an *OCI
image manifest*; a local `docker pull` + `tag` + `push` re-encodes it as *Docker
schema2*, which is a different document with a different digest. The first release run
was stopped by exactly that mismatch (candidate `sha256:f3a4807…` came back as
`sha256:e3113f8…`), which is the assertion doing its job — but it also meant no release
tag could ever have matched the verified artifact. Copying the manifest bytes keeps the
identity intact.

Nothing is rebuilt after verification. The digest that passed the gates is, byte for
byte, the digest the release tags point at.

## Identity model

| reference | meaning | use it for |
|---|---|---|
| `v0.3.3` | release identity | what humans deploy; mutable in principle |
| `sha-<40-char commit>` | source identity | "which tree was this built from" |
| `sha256:<digest>` | artifact identity | **the only reproducible reference** — pin this |
| `latest` | convenience | never a reproducibility reference; may move |

All three tags on a given image are created from the same digest in the same step, and
the workflow re-pulls each one afterwards and asserts it still resolves to the tested
image. `latest` exists only so `docker run` without a tag works.

## Verification chain (job `verify`)

Run against the candidate images, not against the source tree:

1. `migrate` (API image) applies the PostgreSQL schema and exits `0`; the API only
   starts after `service_completed_successfully`.
2. `/health/ready` and the web proxy answer on the published loopback ports.
3. `scripts/verify_docker_health.py` — readiness, authenticated entity/document
   workflow, proxy failure contracts (401/413/415/422/429).
4. `scripts/verify_postgres_state.py --phase before` — asserts the API really selected
   PostgreSQL (not the in-memory repository) and records a tenant/credential/entity.
5. `docker compose restart api`, then `--phase after` — the data survives a restart.
6. `FINRISK_ANALYSIS_TIMEOUT_SECONDS=0.001` + `scripts/verify_docker_timeout.py` —
   the production timeout and explicit-retry contract (504 twice).
7. The workflow additionally asserts that the running `api`, `web` and `migrate`
   containers resolve to the pulled candidate image id — i.e. that "we tested the
   image we built" is checked, not assumed.

No assertion, timeout, security header or fail-closed behaviour is relaxed for the
container path; it runs the same gates that `ci.yml` runs.

## Vulnerability and secret scanning (job `scan`)

* Trivy, `--scanners vuln`, `CRITICAL,HIGH`, `--ignore-unfixed`.
* **CRITICAL blocks the release.**
* **HIGH blocks the release** unless a justified, dated entry exists in `.trivyignore`.
  That file is empty by default — nothing is currently suppressed.
* Unfixed findings are excluded because "no patch exists yet" cannot be acted on; they
  are re-evaluated every run and become blocking the moment a fix is published.
* A second Trivy pass runs `--scanners secret` at `CRITICAL,HIGH,MEDIUM` on both images
  and blocks on any hit.
* A third check asserts neither image ships a non-empty `OPENAI_API_KEY`,
  `DATABASE_URL` or `FINRISK_BOOTSTRAP_TOKEN` in its own environment.
* JSON results are uploaded as a build artifact for audit.

## Supply-chain artifacts (job `publish`)

* **SBOM** — `anchore/sbom-action` (Syft) produces SPDX JSON per image.
* **Attestations** — `actions/attest-sbom` and `actions/attest-build-provenance`
  (SLSA-style) are pushed to the registry keyed by digest.
* **Provenance note** — BuildKit's *built-in* provenance is disabled
  (`provenance: false`). It wraps the image in an OCI index with an attached
  attestation manifest, which changes the manifest digest and would break
  "promote the exact tested digest". The GitHub attestation above carries the same
  guarantee as a digest-keyed side artifact and leaves the image manifest untouched.
* **OCI metadata** — every image carries `org.opencontainers.image.source / revision /
  version / created / title / description / licenses / url / documentation / vendor /
  base.name / base.digest`.

## Base image pinning

`backend/Dockerfile` and `frontend/Dockerfile` pin `python:3.12-slim` and
`node:22-alpine` as **tag + digest**; `docker-compose.release.yml` pins
`postgres:17-alpine` the same way.

Rationale: the tag keeps the image identifiable and lets Dependabot raise an update
(it understands `FROM <image>@sha256:...`), while the digest makes a rebuild of the
same commit reproducible and immune to a tag being re-pointed under us. The escape
hatch is documented in-file: drop the `@sha256:` suffix to float on the tag.

## Platform policy

Phase 1 is **`linux/amd64` only**, and that is what the verification chain actually
exercised. `linux/arm64` is added only when its build *and* its runtime smoke both run
in this workflow. A successful cross-build is not evidence that ARM64 works — claiming
otherwise would be an unverified platform claim.

## Secrets

* No secret is a build argument. The only build arg the frontend accepts is the
  *public* `NEXT_PUBLIC_FINRISK_ANALYSIS_TIMEOUT_SECONDS`, which is inlined into the
  browser bundle by design.
* No secret is baked into a layer, and none appears in the image's own environment.
* Runtime secrets are supplied through the existing `<NAME>_FILE` mechanism
  (`backend/finrisk/secret_files.py`): `DATABASE_URL_FILE`, `OPENAI_API_KEY_FILE`,
  `FINRISK_BOOTSTRAP_TOKEN_FILE`. Mount a file and the value never appears in
  `docker inspect`, in the build, or in a shell history. `<VAR>_FILE` wins over
  `<VAR>` when set.
* The workflow authenticates with `GITHUB_TOKEN` only — no PAT, no extra secret.

## Permissions

Workflow default is `contents: read`. Per job:

| job | permissions |
|---|---|
| `prepare` | `contents: read` |
| `build-api`, `build-web` | `contents: read`, `packages: write` |
| `verify`, `scan` | `contents: read`, `packages: read` |
| `publish` | `contents: read`, `packages: write`, `attestations: write`, `id-token: write` |

## Triggering a release

```bash
# dry run — builds, verifies and scans, but creates no release tag
gh workflow run container-release.yml -f version=v0.3.3 -f publish=false

# real release
gh workflow run container-release.yml -f version=v0.3.3 -f publish=true
```

Pushing a `vX.Y.Z` tag also runs it with publishing enabled. The `prepare` job refuses
to continue if the requested version does not match `pyproject.toml`,
`frontend/package.json` and the newest `CHANGELOG.md` section, so a mistyped tag cannot
produce a mislabelled image.

## Verified release record

The tags below were produced by `Container Release` run
[35446367210](https://github.com/siqiwang0712-commits/financial-risk-agent/actions/runs/35446367210)
from commit `f09825f869e9467a64ac7c36129fff281cebd70e`, all pointing at one digest per
image:

| image | digest | size | user | platform |
|---|---|---|---|---|
| `financial-risk-agent-api` | `sha256:49f0e1afad1cb29bc49f6d662f6c789921577d63c8a3ace4c2abd8ef0a756631` | 100 MiB | `finrisk` (100) | linux/amd64 |
| `financial-risk-agent-web` | `sha256:03fd9d0e589b85922ad5e6f05ee74054515b2a17a9cf98c4665ed4032b07455f` | 82 MiB | `node` (1000) | linux/amd64 |

`v0.3.3`, `sha-f09825f…` and `latest` on each image resolve to that image's digest,
asserted by the run itself after publishing. The `api` digest also serves the `migrate`
service, so the migration job and the server are the same artifact.

## Known limitations

* Single architecture (`linux/amd64`). `linux/arm64` is deliberately not published:
  adding it without an arm64 runtime smoke test would mean advertising a platform the
  release gates never exercised.
* `latest` is mutable and must never be used as a reproducibility reference.
* `candidate-<sha>-<run-id>` tags accumulate. Every run publishes its build under a
  unique candidate tag, and GitHub Container Registry rejects the OCI distribution
  delete API (`DELETE /v2/<name>/manifests/<ref>` returns
  `405 UNSUPPORTED`), so the pipeline cannot remove them — not even its own successful
  run's. They are never advertised and are harmless, but the package's version list in
  the GitHub UI grows. Prune them there (`Packages → the image → Delete version`) if the
  list becomes noisy.
* The pipeline verifies the images, not a Kubernetes/Helm deployment target; there is
  none in this repository.
* Attestations live as OCI referrer manifests next to the image, not on
  `api.github.com`. Verify them with `gh attestation verify oci://<ref> -R <repo>`;
  the `/referrers/<digest>` endpoint on `ghcr.io` returns an empty list.
