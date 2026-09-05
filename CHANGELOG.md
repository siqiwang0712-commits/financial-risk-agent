# Changelog

## [0.2.0] - 2026-09-05

### Added

- SEC XBRL normalization, provenance, restatement selection, cache hashing and cross-source reconciliation.
- Schema-constrained real LLM provider with retry, prompt versioning and usage logging.
- Six-category narrative-numeric consistency engine.
- Public pilot runner with five baselines, five ablations, extended metrics, bootstrap CI, raw predictions, score decomposition and confusion matrices.
- Unit-scale invariance and deterministic 10%/30% missingness robustness checks.
- Dataset card, annotation CSV, pre-registered 30-company candidate registry and executable sample report.

### Fixed

- Missing Hybrid scores are now treated as abstentions rather than forced to probability 0.5/positive predictions.
- PDF report line wrapping, metadata and page numbering.

### Known limitations

- Evaluated corpus remains n=3; SEC rejected current-network API and bulk downloads.
- Real LLM experiment is NOT RUN because no API key was configured.
- Hybrid does not outperform Ratios Only in the released pilot.
