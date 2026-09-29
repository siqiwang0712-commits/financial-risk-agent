# Container Release and Deployment (GHCR)

How FinRisk container images are built, verified and published, and what the published
artifacts actually guarantee. This is also the operator guide for the published Compose
stack, including first-run bootstrap, credentials, health behavior, TLS and image pinning.

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
   adds `v0.3.x`, `sha-<commit>` and `latest` to it. The candidate tag is deliberately
   left in place — the registry rejects the delete API, so the pipeline cannot remove it
   (see Known limitations). Promotion is a registry-side copy: the manifest bytes for the
   verified digest are `GET` under their own `Content-Type` and `PUT` under each tag,
   then the `docker-content-digest` the registry computes for the tag is read back and
   required to equal the verified digest.

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
| `vX.Y.Z` | release identity | what humans deploy; mutable in principle |
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
3. `scripts/verify_docker_health.py` — readiness (including PostgreSQL and complete
   schema), authenticated entity/document workflow, proxy failure contracts
   (401/413/415/422/429). `FINRISK_VERIFY_API` and `FINRISK_VERIFY_WEB` select
   non-default loopback ports across all credentialed verification scripts (remote
   origins are rejected); `FINRISK_EXPECTED_RUNTIME` selects the expected public
   runtime version and otherwise defaults to `pyproject.toml`.
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

## Verification chain (job `verify-release-compose`)

The step above exercises the *development* stack with the candidate images swapped in.
That leaves `docker-compose.release.yml` — the file an operator actually runs, and the
only stack definition here with no `build:` — executed by nothing. It could rot
silently: a broken healthcheck, a dropped `depends_on` condition or a reintroduced
`build:` would ship inside a release that reported itself green.

So a second job boots that file too, with `FINRISK_API_IMAGE` / `FINRISK_WEB_IMAGE`
pointed at the same candidate digests:

1. Asserts `docker-compose.release.yml` contains no `build:` section. (Checked in both
   directions — the development stack *does* match the pattern, so the check is not
   vacuous.)
2. `up -d postgres migrate api web`, then asserts the `api` and `web` containers carry
   the candidate image ids and that `migrate` carries the **same** id as `api`.
3. `/health/ready` and the web proxy answer on the published loopback ports.
4. `scripts/verify_docker_health.py` on that stack.
5. `scripts/verify_postgres_state.py --phase before`, restart the release API, then
   `--phase after` — this independently proves the operator-facing Compose file did
   not accidentally wire the API to ephemeral storage.

It tests the same artifact — nothing is rebuilt — and `publish` and `dry-run` both
require it, so a broken deployment file can no longer be promoted.

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
* **Attestations** — `actions/attest-build-provenance` (SLSA-style build provenance) and
  `actions/attest` (the SPDX SBOM from the step above) are pushed to the registry keyed
  by digest.
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

## Deploying (first run matters)

For a source checkout, the development stack remains the shortest smoke path:

```bash
docker compose up --build
```

It uses an explicitly development-only database password. For the production overlay,
provide a non-default password; the one-shot migration service must finish before the API
starts:

```bash
POSTGRES_PASSWORD='<strong-secret>' docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build
```

For the published images, start from the release-specific environment template:

```bash
cp .env.release.example .env
# Edit .env before continuing.
docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
```

`.env.release.example` is the template for this stack. Do **not** copy `.env.example`:
that one targets the source build and sets `FINRISK_ENABLE_ORG_BOOTSTRAP=0`, which on a
fresh database leaves no way to create the first administrator.

The stack runs `FINRISK_ENV=production`, where the bootstrap route is token-gated and
needs **both** `FINRISK_ENABLE_ORG_BOOTSTRAP=1` and a non-empty
`FINRISK_BOOTSTRAP_TOKEN`. A missing first value returns 403 "organization bootstrap is
disabled"; a missing second returns 403 "invalid bootstrap token" — an unset expected
token can never match. In both cases the stack starts, reports healthy, and is
unusable, which is why the ordering is called out in the template:

1. Provision with bootstrap on and a token set; store the returned `api_key` (shown once).
2. Set `FINRISK_ENABLE_ORG_BOOTSTRAP=0`, clear the token, `up -d` to recreate the API.

There is no other provisioning path — no preset admin key, no CLI — so this is the only
way in, and the route must not stay reachable afterwards because it mints ADMIN keys
without an API key of its own.

Only `docker-compose.release.yml` and an env file are needed; nothing mounts the source
tree, and the migration script is baked into the API image.

The API answers on `http://127.0.0.1:8000` and the Workbench on
`http://127.0.0.1:3000`. The ports bind to loopback intentionally. Put a TLS terminator in
front before allowing remote access.

After the first start, provision the organization and save the returned API key; it is
shown once:

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/enterprise/organizations \
  -H 'Content-Type: application/json' \
  -H "X-Bootstrap-Token: $FINRISK_BOOTSTRAP_TOKEN" \
  -d '{"name":"Acme","actor_id":"admin"}'
```

Then set `FINRISK_ENABLE_ORG_BOOTSTRAP=0`, clear the bootstrap token and run `up -d`
again. Leaving the route enabled would leave an endpoint that can mint ADMIN keys without
an existing API key.

If only the released stack is needed, the two required files can be downloaded without a
source checkout or build toolchain:

```bash
curl -O https://raw.githubusercontent.com/siqiwang0712-commits/financial-risk-agent/main/docker-compose.release.yml
curl -o .env https://raw.githubusercontent.com/siqiwang0712-commits/financial-risk-agent/main/.env.release.example
$EDITOR .env
docker compose -f docker-compose.release.yml up -d
```

### Runtime configuration

| Variable | Required | Purpose |
|---|---|---|
| `POSTGRES_PASSWORD` | Yes | Applied when the PostgreSQL volume is first initialized; see the credential lifecycle below. |
| `FINRISK_LLM_PROVIDER` | Yes | Fail-closed when absent. Use `openai` for a real provider; `mock` is a deterministic test provider, not a production default. |
| `OPENAI_API_KEY` / `OPENAI_API_KEY_FILE` | When required by the provider | The `_FILE` form keeps the value out of `docker inspect` and shell history. |
| `FINRISK_ENABLE_ORG_BOOTSTRAP` | First provisioning only | Defaults to `0`; enable only long enough to create the first organization and ADMIN key. |
| `FINRISK_BOOTSTRAP_TOKEN` / `FINRISK_BOOTSTRAP_TOKEN_FILE` | With bootstrap enabled in production | Gates the unauthenticated route that mints the first ADMIN key. |

Rate-limit windows are stored in PostgreSQL whenever `DATABASE_URL` is set, so they
survive restarts and are shared across replicas. The in-process window is a local fallback
only. Three optional settings bound datastore latency and fall back to their defaults when
the configured value is unusable:

- `FINRISK_DATABASE_OPERATION_TIMEOUT_SECONDS` (default `5.0`) limits how long a
  request waits for a pooled connection before a controlled `503`.
- `FINRISK_DB_RECONNECT_TIMEOUT_SECONDS` (default `5.0`) replaces the pool's 300-second
  reconnection window.
- `FINRISK_DB_CONNECT_TIMEOUT_SECONDS` (default `5`) limits the libpq handshake.

These database settings are separate from the 60-second document-analysis timeout.

### PostgreSQL credential lifecycle

`POSTGRES_PASSWORD` is applied only when PostgreSQL initializes a new persistent volume.
Changing the environment variable later does not change the password stored in that
volume, so the database healthcheck and new application connections will fail.

The healthcheck authenticates over TCP against the container's own address on the Compose
network. It deliberately does not use `127.0.0.1`: the upstream image places a trusted
loopback rule above its appended `scram-sha-256` rule, so a loopback probe could report a
healthy database even with the wrong password.

How a mismatch appears depends on connection state:

- A running API that needs a new connection keeps `/health/live` at `200` but returns
  `503` from `/health/ready` with the credential rejection. PostgreSQL does not terminate
  existing sessions after `ALTER USER`, so pooled connections may continue to work until
  a server restart, pool growth or connection-lifetime expiry. An immediate `200` after
  rotation is therefore not proof that the rotation succeeded.
- On a cold start, the API creates its pool during module import and waits at most ten
  seconds. A mismatched password produces `psycopg_pool.PoolTimeout`; the container exits
  before request handling, so neither health route answers.
- Compose gates the API on PostgreSQL `service_healthy`. If the database healthcheck fails,
  `up` stops before creating the API container.

Rotate the database credential before a cold start by changing it inside PostgreSQL first:

```bash
docker compose exec postgres psql -U finrisk -d finrisk -c "ALTER USER finrisk WITH PASSWORD '<new-secret>'"
```

Alternatively, `docker compose down -v` recreates the volume on the next start, but it
**destroys all stored data**. Never use volume recreation as an unreviewed password-rotation
shortcut.

### Network and TLS behavior

The release stack binds published ports to loopback and does not terminate TLS. The API
sends `Strict-Transport-Security` only when the request actually arrives over HTTPS, or
when a trusted terminator reports `x-forwarded-proto: https`. On plain HTTP the header is
omitted instead of advertising a transport guarantee the deployment does not provide.

### Pinning and verifying a deployed image

Release tags such as `v0.3.4` and `latest` are convenient references; the digest is the
artifact identity. Set `FINRISK_API_IMAGE` and `FINRISK_WEB_IMAGE` to
`ghcr.io/...:<tag>@sha256:<digest>` for a reproducible deployment. Use the digests emitted
by the release workflow for the exact tag being deployed; documentation-only commits can
change an image digest because the image records the source revision.

```bash
# Pin both default image names to the source-identity tag.
FINRISK_VERSION=sha-<full-commit-sha> docker compose -f docker-compose.release.yml up -d

# Stronger: pin each image to the exact promoted artifact digest.
FINRISK_API_IMAGE=ghcr.io/siqiwang0712-commits/financial-risk-agent-api:v0.3.4@sha256:<api-digest> \
FINRISK_WEB_IMAGE=ghcr.io/siqiwang0712-commits/financial-risk-agent-web:v0.3.4@sha256:<web-digest> \
docker compose -f docker-compose.release.yml up -d
```

Verify GitHub's build-provenance attestation against the pinned reference:

```bash
gh attestation verify oci://ghcr.io/siqiwang0712-commits/financial-risk-agent-api@sha256:<digest> \
  -R siqiwang0712-commits/financial-risk-agent
```

`latest` is never a reproducibility reference.

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
gh workflow run container-release.yml -f version=v0.3.4 -f publish=false

# real release
gh workflow run container-release.yml -f version=v0.3.4 -f publish=true
```

Pushing a `vX.Y.Z` tag also runs it with publishing enabled. The `prepare` job refuses
to continue if the requested version does not match `pyproject.toml`,
`frontend/package.json` and the newest `CHANGELOG.md` section, so a mistyped tag cannot
produce a mislabelled image.

## Verified v0.3.3 release record

The tags below were produced by `Container Release` run
[35448112282](https://github.com/siqiwang0712-commits/financial-risk-agent/actions/runs/35448112282)
from commit `432732def9b9a947eadeee8edcd7c3e6a9cd7990`, all pointing at one digest per
image:

| image | digest | size | user | platform |
|---|---|---|---|---|
| `financial-risk-agent-api` | `sha256:44135b1d5faaa02336dd8e16f426d663cc61207c600f5f034d72e02539a70698` | 100 MiB | `finrisk` (100) | linux/amd64 |
| `financial-risk-agent-web` | `sha256:cba0dd867a8e14903e164ec5388309ddbdbc37a26d08433fbbad125be3a1bfb2` | 82 MiB | `node` (1000) | linux/amd64 |

`v0.3.3`, `sha-432732de…` and `latest` on each image resolve to that image's digest,
asserted by the run itself after publishing. The `api` digest also serves the `migrate`
service, so the migration job and the server are the same artifact.

> **These digests are per-commit.** The image content embeds
> `org.opencontainers.image.revision`, so every commit that touches the build produces
> a new digest — including a commit that only edits this document. Read the digest from
> the run that published the tag you intend to deploy rather than from this page.

## Known limitations

* Single architecture (`linux/amd64`). `linux/arm64` is deliberately not published:
  adding it without an arm64 runtime smoke test would mean advertising a platform the
  release gates never exercised.
* `latest` is mutable and must never be used as a reproducibility reference.
* `candidate-<sha>-<run-id>` tags accumulate. Every run publishes its build under a
  unique candidate tag — including **dry runs**, which build and verify but publish no
  release tag — and GitHub Container Registry rejects the OCI distribution delete API
  (`DELETE /v2/<name>/manifests/<ref>` returns
  `405 UNSUPPORTED`), so the pipeline cannot remove them, not even its own successful
  run's. They are never advertised and are harmless, but the package's version list in
  the GitHub UI grows. Prune them there (`Packages → the image → Delete version`) if
  the list becomes noisy. Note that a dry run's candidate digest differs from the
  published one even when the image content is identical, because the build stamps
  `org.opencontainers.image.revision` with the current commit.
* The pipeline verifies the images, not a Kubernetes/Helm deployment target; there is
  none in this repository.
* Attestations live as OCI referrer manifests next to the image, not on
  `api.github.com`. Verify them with `gh attestation verify oci://<ref> -R <repo>`;
  the `/referrers/<digest>` endpoint on `ghcr.io` returns an empty list.
