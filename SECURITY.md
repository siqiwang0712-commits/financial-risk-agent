# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub's security-advisory
interface for this repository. Do not include credentials, private filings, or other
sensitive data in a public issue. Include the affected version, reproduction steps, and
impact when possible.

## Scope

FinRisk is a research prototype, not a production-validated or regulatory-certified
system. Security controls and tests cover documented tenant, credential, file-input,
and API trust boundaries, but they do not constitute an external security audit or a
compliance claim. Deployers remain responsible for infrastructure hardening, secrets,
network controls, monitoring, backups, and independent review.

## v0.4.2 development boundaries

Credential-bearing LLM requests reject redirects, including same-origin redirects;
configure the final HTTPS endpoint (loopback HTTP remains available for local providers).
Filing text and document names are untrusted data in the user role. Prompt delimiting
and schema validation reduce exposure; they do not eliminate prompt injection or prove
the truth of model explanations. Deterministic provenance and Assurance remain required.

Every final decision requires valid Assurance semantics. A historical v0.3 bundle may
pass its historical integrity check, but cannot satisfy the v0.4 certificate verifier.
Certificate hashes detect changes; they are content hashes, **not signatures or proof
of issuer authenticity**. Policy-bound publication and authenticated, tenant-scoped
storage are required. Verification without a supplied trusted policy checks integrity,
not whether that policy is approved for a new deployment. Persisted certificate evidence
identities and coverage must match the actual recorded paths.

Direct non-PDF API request bodies have a measured 50 MiB default ceiling
(`FINRISK_MAX_REQUEST_BYTES`), a 30-second body-read budget, and two concurrent body
admission slots per API process. PDF admission retains its separate file/framing limits
and authentication before multipart parsing. Deployers still need connection limits,
aggregate resource quotas, and a trusted reverse proxy; these bounds are not protection
against every denial-of-service strategy.

Document workers publish complete results atomically in private temporary directories,
with a 128 MiB result limit and TERM/KILL reclamation on timeout or cancellation.
Their Python-object IPC is trusted local execution, not an upload deserializer or a
security sandbox. Native-parser compromise, hostile same-user processes, and compromised
hosts require separate OS/container isolation. Time budgets must be positive and finite.

Optional build trust configuration uses the `finrisk_ca_bundle` BuildKit secret mount.
It adds the organization's trusted CA bundle for dependency installation without disabling
TLS checks or retaining that bundle in the runtime image. Do not pass application
credentials as build arguments. Historical v0.4.1 identities and empirical artifacts
remain unchanged; v0.4.2 identities are explicitly development outputs, not release or
E5 freeze evidence. See [development audit](docs/SECURITY_HARDENING_v0.4.2.md).
