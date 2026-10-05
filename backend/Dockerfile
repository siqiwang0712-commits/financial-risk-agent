# FinRisk API image.
#
# Build contract (enforced by .github/workflows/container-release.yml):
#   * No secret is ever passed as a build argument and none is baked into a layer.
#     Runtime secrets are injected at process start through the existing
#     `<NAME>_FILE` mechanism (backend/finrisk/secret_files.py) and are therefore
#     mountable files, not image content and not process environment of the build.
#   * The runtime user is unprivileged and owns /app.
#   * `org.opencontainers.image.*` metadata is supplied by the release workflow so a
#     published image always carries version, revision and creation time.
#
# Base images are pinned "tag + digest". The tag keeps the image identifiable and
# Dependabot-updatable, the digest makes the build byte-reproducible and immune to a
# tag being re-pointed. Drop the `@sha256:` suffix to float on the tag.
ARG PYTHON_BASE=python:3.12-slim@sha256:dddfd7e07f9d15aeeca61529320492139d21cac7f0070c00609243e51e4e0016

# ---------------------------------------------------------------------------
# Stage 1 — dependency resolution. Only the packaging metadata and the package
# source and packaged runtime policy data are copied here. Editing migrations or
# frozen research data still does not invalidate the dependency-install layer.
# ---------------------------------------------------------------------------
FROM ${PYTHON_BASE} AS builder
WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
COPY pyproject.toml requirements.lock ./
COPY backend ./backend
COPY rules ./rules
COPY config ./config
RUN python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --no-cache-dir pip==26.2.0 \
    && /opt/venv/bin/python -m pip install --no-cache-dir -c requirements.lock ".[postgres]"

# ---------------------------------------------------------------------------
# Stage 2 — runtime. Carries the venv and the application data, nothing else:
# no pip cache, no build tooling, no test-only packages (requirements.lock is a
# *constraint* file here, so the dev extra is never installed).
# ---------------------------------------------------------------------------
FROM ${PYTHON_BASE} AS runtime
ARG OCI_VERSION=0.4.1
ARG OCI_REVISION=unknown
ARG OCI_CREATED=1970-01-01T00:00:00Z
LABEL org.opencontainers.image.title="FinRisk API" \
      org.opencontainers.image.description="Evidence-grounded hybrid corporate financial risk assessment API" \
      org.opencontainers.image.source="https://github.com/siqiwang0712-commits/financial-risk-agent" \
      org.opencontainers.image.url="https://github.com/siqiwang0712-commits/financial-risk-agent" \
      org.opencontainers.image.documentation="https://github.com/siqiwang0712-commits/financial-risk-agent/blob/main/README.md" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.vendor="siqiwang0712-commits" \
      org.opencontainers.image.base.name="docker.io/library/python:3.12-slim" \
      org.opencontainers.image.base.digest="sha256:dddfd7e07f9d15aeeca61529320492139d21cac7f0070c00609243e51e4e0016" \
      org.opencontainers.image.version="${OCI_VERSION}" \
      org.opencontainers.image.revision="${OCI_REVISION}" \
      org.opencontainers.image.created="${OCI_CREATED}"
WORKDIR /app
# `PYTHONPATH` keeps the API running from the source tree exactly as it does in
# the repository; the venv on PATH only supplies the dependency closure.
ENV PYTHONPATH=/app/backend \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
# Debian's security archive publishes fixes *ahead* of the `python:3.12-slim`
# digest refresh, so a digest-pinned base can legitimately lag the security pocket
# for a few days. At the time of writing the pinned digest above still ships
# `libpcre2-8-0 10.46-1~deb13u2` while `trixie-security` already carries
# `10.46-1~deb13u3`, which is the fix for CVE-2026-103111 (HIGH). Refreshing the
# base digest is still the primary remediation — it is what clears the OpenSSL
# advisories — and this step exists only to close that remaining gap.
#
# It is deliberately minimal: a single package, upgraded rather than reinstalled,
# so it is a no-op once the base digest catches up and never downgrades. A blanket
# `apt-get upgrade` would drag unrelated packages into the release image, and
# pinning an exact version here would turn the next base-image bump into a failed
# build. The apt lists are removed so the layer ships no package index.
#
# Only the runtime stage needs this: it is the stage that is published and
# scanned, and the builder's OS packages never reach it (`COPY --from=builder`
# takes `/opt/venv` and nothing else).
RUN apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade libpcre2-8-0 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /opt/venv /opt/venv
# The current 3.12-slim manifest still carries libpcre2-8-0 deb13u2 even though
# Debian has published deb13u3 for CVE-2026-103111. Install that fixed revision
# explicitly so the release image is reproducible and the security update cannot
# be lost when an upstream tag is rebuilt.
RUN apt-get update \
    && apt-get install --no-install-recommends --only-upgrade -y \
       libpcre2-8-0=10.46-1~deb13u3 \
    && rm -rf /var/lib/apt/lists/*
# Harden the runtime: `pip` is build tooling, and the copy it ships also carries its
# own vendored `msgpack` (GHSA-6v7p-g79w-8964) and `setuptools` (CVE-2025-47273) —
# two HIGH advisories that Trivy reports against this image and that the application
# never executes. Deleting the code removes the finding; suppressing it in
# `.trivyignore` would only have hidden it. Nothing at runtime imports pip.
RUN rm -rf /opt/venv/lib/python3.12/site-packages/pip \
           /opt/venv/lib/python3.12/site-packages/pip-*.dist-info \
           /opt/venv/bin/pip /opt/venv/bin/pip3 /opt/venv/bin/pip3.12 \
           /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.12 \
           /usr/local/lib/python3.12/site-packages/pip \
           /usr/local/lib/python3.12/site-packages/pip-*.dist-info \
           /usr/local/lib/python3.12/ensurepip
COPY backend ./backend
COPY rules ./rules
COPY config ./config
COPY research/results/public_v1 ./research/results/public_v1
COPY migrations ./migrations
COPY scripts/validate_postgres_migration.py ./scripts/validate_postgres_migration.py
RUN addgroup --system finrisk && adduser --system --ingroup finrisk finrisk \
    && chown -R finrisk:finrisk /app
USER finrisk
EXPOSE 8000
CMD ["uvicorn", "finrisk.api:app", "--host", "0.0.0.0", "--port", "8000"]
