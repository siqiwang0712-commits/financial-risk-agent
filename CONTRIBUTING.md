# Contributing

Use a focused branch, add tests for behavioral changes, and run `pytest` plus the frontend build before review. Financial formulas need a primary-source citation in the change description and numeric edge-case tests. New rules require a unique stable ID, category, severity, explicit conditions, bounded effect, rationale, and evidence of non-duplication. Rules must say “signal,” never imply proven fraud or default.

Never commit filings without redistribution permission, personal data, `.env` files, tokens, or generated private reports. Synthetic fixtures must carry `"synthetic": true`. Changes to weights or thresholds require a versioned rationale and evaluation plan. Do not report benchmark results unless the dataset manifest and reproducible output are included.

