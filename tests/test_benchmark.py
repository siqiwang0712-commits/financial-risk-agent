from pathlib import Path

from finrisk.benchmark import BASELINES, run_manifest

ROOT=Path(__file__).resolve().parents[1]
def test_all_baselines_and_ablations_execute_on_synthetic_manifest():
    rows=run_manifest(ROOT/"research"/"synthetic_manifest.json",ROOT)
    assert {r["baseline"] for r in rows}==set(BASELINES)
    assert all(r["dataset_kind"]=="synthetic_smoke" for r in rows)
