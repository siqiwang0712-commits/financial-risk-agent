# Executed Ablation Study

Run `PYTHONPATH=backend python scripts/run_public_benchmark.py`. The runner evaluates the same frozen Apple, Microsoft and Intel observations under five variants: full hybrid, without narrative, without rules, without traditional models and without prior-year trends. Raw outputs are committed as `research/results/public_v1/ablations.csv` and `.json`.

This is a sensitivity diagnostic, not a causal estimate. With only three companies, a single changed prediction moves accuracy by 0.333. The current run shows that removing rule signals improves the Intel classification while removing trends makes Microsoft a false positive. That instability is evidence that the heuristic aggregation and thresholds require validation on a larger independently annotated corpus.

No ablation result is used to tune on the held-out Intel example. Splits are company-disjoint: Apple=train, Microsoft=validation, Intel=test.
