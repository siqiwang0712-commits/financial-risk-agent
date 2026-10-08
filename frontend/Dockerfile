# FinRisk Web image (Next.js standalone server).
#
# Build contract (enforced by .github/workflows/container-release.yml):
#   * The only build argument is a *public* client-side timeout that is inlined into
#     the browser bundle by design. No API key, DSN or bootstrap token is ever a
#     build argument, and none is baked into a layer.
#   * The runtime stage contains the standalone server and the static assets only:
#     no node_modules, no build cache, no source map of the server bundle.
#   * The runtime user is the unprivileged `node` user shipped by the base image.
#
# Base images are pinned "tag + digest"; see backend/Dockerfile for the rationale.
ARG NODE_BASE=node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402

# ---------------------------------------------------------------------------
# Stage 1 — build. `package.json` + `package-lock.json` are copied before the
# sources so `npm ci` is cached independently of any application edit.
# ---------------------------------------------------------------------------
FROM ${NODE_BASE} AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
ARG NEXT_PUBLIC_FINRISK_ANALYSIS_TIMEOUT_SECONDS=60
ENV NEXT_PUBLIC_FINRISK_ANALYSIS_TIMEOUT_SECONDS=${NEXT_PUBLIC_FINRISK_ANALYSIS_TIMEOUT_SECONDS}
COPY package.json package-lock.json ./
RUN --mount=type=secret,id=finrisk_ca_bundle \
    if [ -f /run/secrets/finrisk_ca_bundle ]; then export npm_config_cafile=/run/secrets/finrisk_ca_bundle; fi; \
    npm ci
COPY . .
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 — runtime.
# ---------------------------------------------------------------------------
FROM ${NODE_BASE} AS runtime
ARG OCI_VERSION=0.4.2
ARG OCI_REVISION=unknown
ARG OCI_CREATED=1970-01-01T00:00:00Z
LABEL org.opencontainers.image.title="FinRisk Web" \
      org.opencontainers.image.description="FinRisk Analyst Workbench (Next.js standalone server)" \
      org.opencontainers.image.source="https://github.com/siqiwang0712-commits/financial-risk-agent" \
      org.opencontainers.image.url="https://github.com/siqiwang0712-commits/financial-risk-agent" \
      org.opencontainers.image.documentation="https://github.com/siqiwang0712-commits/financial-risk-agent/blob/main/README.md" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.vendor="siqiwang0712-commits" \
      org.opencontainers.image.base.name="docker.io/library/node:22-alpine" \
      org.opencontainers.image.base.digest="sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402" \
      org.opencontainers.image.version="${OCI_VERSION}" \
      org.opencontainers.image.revision="${OCI_REVISION}" \
      org.opencontainers.image.created="${OCI_CREATED}"
WORKDIR /app
# `HOSTNAME`: Next's standalone server binds to `process.env.HOSTNAME` when set, and
# Docker sets that to the container id — so it would listen only on the container IP
# and a loopback health probe (or any sidecar) could not reach it. Pin a real address.
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
# Harden the runtime: the standalone server needs `node` and nothing else, but the
# base image also ships `npm` with its own dependency tree — `tar` (CVE-2026-59873,
# CRITICAL), `pacote`, `sigstore`, `ip-address`, `picomatch`, `brace-expansion`. Those
# advisories are real, so they are removed rather than suppressed in `.trivyignore`;
# the application never loads npm. This also drops ~40 MB of build tooling.
# CVE-2026-85091 affects the base image's zlib 1.3.2-r0. Install the signed
# Alpine fix; a pinned base digest alone does not refresh security packages.
# Require a minimum fixed version rather than pinning a revision that can disappear.
RUN --mount=type=secret,id=finrisk_ca_bundle \
    if [ -f /run/secrets/finrisk_ca_bundle ]; then export SSL_CERT_FILE=/run/secrets/finrisk_ca_bundle; fi; \
    apk upgrade --no-cache zlib \
    && zlib_version="$(apk list --installed zlib | awk '{sub(/^zlib-/,"",$1); print $1}')" \
    && test -n "$zlib_version" \
    && test "$(apk version -t "$zlib_version" 1.3.2-r1)" != '<' \
    && rm -rf /usr/local/lib/node_modules/npm \
           /usr/local/lib/node_modules/corepack \
           /usr/local/bin/npm /usr/local/bin/npx \
           /usr/local/bin/corepack /usr/local/bin/yarn /usr/local/bin/pnpm \
           /opt/yarn /opt/yarn-*
USER node
EXPOSE 3000
CMD ["node", "server.js"]
