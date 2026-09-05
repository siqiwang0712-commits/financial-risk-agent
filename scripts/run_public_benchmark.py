from pathlib import Path

from finrisk.research_eval import (
    run_public_benchmark,
    run_robustness_checks,
    write_results,
    write_robustness,
)

ROOT = Path(__file__).resolve().parents[1]
rows, summary, ablations = run_public_benchmark(ROOT / "research/benchmark/public_company_observations.json", ROOT)
write_results(rows, summary, ablations, ROOT / "research/results/public_v1")
write_robustness(run_robustness_checks(ROOT / "research/benchmark/public_company_observations.json",ROOT),ROOT / "research/results/public_v1")
print(summary)
