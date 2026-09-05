# Research Benchmark Upgrade - v0.2.0

This release turns the original research skeleton into an auditable pilot: authoritative-XBRL data contracts, structured LLM boundaries, cross-source reconciliation, six-category consistency checks, and executable baseline/ablation evaluation.

The released empirical result is intentionally negative. On three single-reviewed public companies, Ratios Only achieved risk F1 1.0 while Full Hybrid achieved 0.0 with 2/3 decision coverage. Full Hybrid missed Intel and abstained on Apple. The sample is far too small for model comparison.

SEC blocked the current environment's API and bulk downloads, so the pre-registered 30-company corpus remains pending and no extraction-accuracy result is claimed. No OpenAI key was present, so the real LLM baseline is NOT RUN.

Reproduce with:

```powershell
$env:PYTHONPATH="backend"
python scripts/run_public_benchmark.py
pytest --cov=finrisk --cov-fail-under=90
```
