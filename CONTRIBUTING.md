# Contributing

Use a focused branch, add tests for behavioral changes, and run `pytest` plus the frontend build before review. Financial formulas need a primary-source citation in the change description and numeric edge-case tests. New rules require a unique stable ID, category, severity, explicit conditions, bounded effect, rationale, and evidence of non-duplication. Rules must say “signal,” never imply proven fraud or default.

Never commit filings without redistribution permission, personal data, `.env` files, tokens, or generated private reports. Synthetic fixtures must carry `"synthetic": true`. Changes to weights or thresholds require a versioned rationale and evaluation plan. Do not report benchmark results unless the dataset manifest and reproducible output are included.

## Verification before review

With `DATABASE_URL` set, apply and validate migrations before running the suite. Tests
assume the schema already exists; on a fresh unmigrated database `rate_limit_events` is
absent, the limiter fails closed, and authenticated routes return `503`.

```bash
python scripts/validate_postgres_migration.py
pytest --cov=finrisk --cov-report=term-missing --cov-fail-under=90
ruff check backend tests scripts
```

Verify the frontend from its own directory:

```bash
cd frontend
npm audit --omit=dev --audit-level=high --registry=https://registry.npmjs.org
npm test
npm run typecheck
npm run build
```

The release gate covers Python 3.11 and 3.12, a 90% backend coverage minimum, Ruff,
frontend semantic tests, an official-registry production dependency audit, TypeScript,
the Next.js production build, prospective provenance validation and the v0.3.4/E4 public
artifact checks. Research-only verification commands are maintained in
[`research/EXPERIMENT_REPRODUCIBILITY.md`](research/EXPERIMENT_REPRODUCIBILITY.md).

