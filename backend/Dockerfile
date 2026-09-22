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
ARG PYTHON_BASE=python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9

# ---------------------------------------------------------------------------
# Stage 1 — dependency resolution. Only the packaging metadata and the package
# source are copied here, so that editing rules/, config/, migrations/ or the
# frozen research data does not invalidate the (expensive) install layer.
# ---------------------------------------------------------------------------
FROM ${PYTHON_BASE} AS builder
WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
COPY pyproject.toml requirements.lock ./
COPY backend ./backend
RUN python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --no-cache-dir pip==26.2.0 \
    && /opt/venv/bin/python -m pip install --no-cache-dir -c requirements.lock ".[postgres]"

# ---------------------------------------------------------------------------
# Stage 2 — runtime. Carries the venv and the application data, nothing else:
# no pip cache, no build tooling, no test-only packages (requirements.lock is a
# *constraint* file here, so the dev extra is never installed).
# ---------------------------------------------------------------------------
FROM ${PYTHON_BASE} AS runtime
ARG OCI_VERSION=0.3.3
ARG OCI_REVISION=unknown
ARG OCI_CREATED=1970-01-01T00:00:00Z
LABEL org.opencontainers.image.title="FinRisk API" \
      org.opencontainers.image.description="Evidence-grounded hybrid corporate financial risk assessment API" \
      org.opencontainers.image.source="https://github.com/siqiwang0712-commits/financial-risk-agent" \
      org.opencontainers.image.url="https://github.com/siqiwang0712-commits/financial-risk-agent" \
      org.opencontainers.image.documentation="https://github.com/siqiwang0712-commits/financial-risk-agent/blob/main/README.md" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.vendor="siqiwang0712-commits" \
      org.opencontainers.image.base.name="docker.io/library/python:3.12-slim" \
      org.opencontainers.image.base.digest="sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9" \
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
COPY --from=builder /opt/venv /opt/venv
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
