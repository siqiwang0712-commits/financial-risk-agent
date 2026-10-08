# FinRisk v0.4.2 — Security & Reliability Patch

Release metadata date: 2026-10-08. These notes describe the prepared source;
they do not claim that a Git tag, GitHub Release or production image was published.

Changes:

- Reject credential-bearing LLM redirects and treat document names as untrusted
  user data, with safe public transport errors.
- Enforce Assurance evidence/state and proposal/final consistency; separate
  historical bundle integrity from v0.4 authorization; reject certificate downgrade
  and evidence-path disappearance, including persisted PostgreSQL records.
- Bound direct request bodies before parsing and reclaim document workers on
  timeout/cancellation, including incomplete result publication. Reject nonfinite budgets.
- Update the affected source-map-js and sharp/libvips dependency families; preserve
  the existing vulnerability policy, negative tests and 90% coverage threshold.
- Update Next.js/ESLint to 15.5.27 for two response-cache advisories and require the
  signed Alpine zlib fix for CVE-2026-85091 in the refreshed pinned Node 22 image.
- Correct current package, frontend, container and release-tooling identities to 0.4.2.
  The local aggregate gate tests the same built candidate images in both Compose paths.
- Ordinary CI now runs both Compose paths, PostgreSQL corruption/restart checks,
  exact-image vulnerability/secret scans and retained unfiltered inventories.
  Container failures retain diagnostics before cleanup.
- Keep manual `publish=false` runs non-publishing even on tag refs; automatic tag
  pushes and explicitly publishing manual calls retain their verified-gate prerequisites.

Historical v0.4.1, E4, E4-S and E4-R research artifacts remain unchanged. Current
v0.4.2 source identities are separately bound; no model is retrained and E5 remains
BLOCKED / DRAFT_NOT_FROZEN. FinRisk remains HEURISTIC_POLICY / UNCALIBRATED.

Prompt injection cannot be eliminated. Certificate hashes provide integrity rather
than issuer authentication; worker isolation is not a native-code security sandbox.
Unfixed Debian base-image CVEs and one development-only braces advisory remain
explicitly documented and require review/rescan before promotion. This
release makes no external audit, compliance certification or production validation claim.

See [security findings and exact validation evidence](docs/SECURITY_HARDENING_v0.4.2.md)
and [container release controls](docs/CONTAINER_RELEASE.md). The ordinary CI result
and `publish=false` digest-bound dry-run must correspond to the final commit;
publication remains a separate maintainer action.
