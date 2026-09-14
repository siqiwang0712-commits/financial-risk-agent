# Executed Ablation Study

Run `PYTHONPATH=backend python scripts/run_public_benchmark.py`. The runner evaluates the same frozen Apple, Microsoft and Intel observations under five variants: full hybrid, without narrative, without rules, without traditional models and without prior-year trends. Raw outputs are committed as `research/results/public_v1/ablations.csv` and `.json`.

## How each variant is produced

Each ablation row carries a `method` field, because the five variants are **not** all obtained the same way:

| Ablation | `method` | What actually happens |
|---|---|---|
| `full_hybrid` | `baseline` | the reference assessment |
| `without_narrative` | `arithmetic_proxy` | the `rule_engine` baseline's probability, reused verbatim — the two are identical by construction (agreement to within 1e-9) |
| `without_rules` | `arithmetic_proxy` | the mean of the `ratios_only` and `traditional_models` probabilities |
| `without_models` | `arithmetic_proxy` | the mean of the `ratios_only` and `rule_engine` probabilities |
| `without_trends` | `rerun` | the pipeline is genuinely re-run with `previous=None` |

So **only `without_trends` is a real ablation**. The other three are arithmetic recombinations of baselines that were already computed; they are published because they bound the plausible range, not because a component was removed and the system re-measured. `ABLATION_METHODS` in `backend/finrisk/research_eval.py` is the single source of truth for this table, and `tests/test_audit_fixes.py` pins it.

Replacing a proxy with a real re-run is a product decision: it needs a pipeline that can be constructed without a given component, and it changes the committed numbers.

## What the study does and does not show

This is a sensitivity diagnostic, not a causal estimate. With only three companies, a single changed prediction moves accuracy by 0.333. The current run shows that removing rule signals improves the Intel classification while removing trends makes Microsoft a false positive. That instability is evidence that the heuristic aggregation and thresholds require validation on a larger independently annotated corpus.

No ablation result is used to tune on the held-out Intel example. Splits are company-disjoint: Apple=train, Microsoft=validation, Intel=test.
