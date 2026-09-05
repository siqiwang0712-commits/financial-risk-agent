from pathlib import Path

from finrisk.research_eval import (
    ABLATIONS,
    BASELINES,
    bootstrap_ci,
    run_public_benchmark,
    run_robustness_checks,
    write_results,
    write_robustness,
)

ROOT=Path(__file__).resolve().parents[1]


def test_public_benchmark_is_company_disjoint_and_reproducible(tmp_path):
    manifest=ROOT/"research/benchmark/public_company_observations.json"
    rows,summary,ablations=run_public_benchmark(manifest,ROOT)
    assert {r["baseline"] for r in rows}==set(BASELINES)
    assert {r["split"] for r in rows}=={"train","validation","test"}
    assert {r["ablation"] for r in ablations}==set(ABLATIONS)
    assert summary["company_disjoint"] and summary["bootstrap_samples"]==2000
    write_results(rows,summary,ablations,tmp_path)
    assert (tmp_path/"summary.json").exists() and (tmp_path/"baseline-risk-f1.svg").exists()
    robustness=run_robustness_checks(manifest,ROOT);write_robustness(robustness,tmp_path)
    assert len(robustness)==12 and (tmp_path/"robustness.csv").exists()
    scales=[r for r in robustness if r["check"]=="unit_scale"]
    for example_id in {r["example_id"] for r in scales}:
        pair=[r for r in scales if r["example_id"]==example_id]
        assert pair[0]["score"]==pair[1]["score"]


def test_bootstrap_ci_is_seeded():
    assert bootstrap_ci([0,1,1],lambda x:sum(x)/len(x),100)==bootstrap_ci([0,1,1],lambda x:sum(x)/len(x),100)
