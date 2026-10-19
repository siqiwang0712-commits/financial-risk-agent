"""No invented denominators, labels, consistency or experimental identities."""

import json
from copy import deepcopy

import pytest

from research.v042_experiments import run_diagnostics as study


def rows():
    return [
        {
            "label": label,
            "score": score,
            "observation_id": str(i),
            "cik": str(i),
            "score_semantics": "UNCALIBRATED_RANKING_SCORE",
        }
        for i, (label, score) in enumerate([(0, 0.1), (1, 0.9), (1, 0.6), (0, 0.4)])
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("label", True),
        ("label", 2),
        ("label", 0.5),
        ("score", True),
        ("score", float("nan")),
        ("score", float("inf")),
        ("score", -1),
    ],
)
def test_invalid_numeric_observations_fail_closed(field, value):
    data = rows()
    data[0][field] = value
    with pytest.raises(ValueError, match="invalid OOF"):
        study.risk_coverage(data, [0])


def test_confidence_ties_and_zero_issued_do_not_manufacture_accuracy():
    observed = study.risk_coverage(rows(), [0, 0.2, 0.5])
    assert [r["issued"] for r in observed] == [4, 2, 0]
    assert observed[-1]["selective_error"] == "NOT_ESTIMABLE"
    assert observed[-1]["actual_authorization_rate"] == "NOT_ESTIMABLE"


def test_review_budget_is_bounded_and_not_expected_event_capture():
    observed = study.review_budgets(rows(), [0.2, 0.5])
    assert observed[0]["reviews"] == 0
    assert observed[0]["precision"] == "NOT_ESTIMABLE"
    assert observed[1]["reviews"] == 2
    assert observed[1]["events_captured"] == 2
    assert observed[1]["recall"] == 1
    non_events = [{**r, "label": 0} for r in rows()]
    assert study.review_budgets(non_events, [0.5])[0]["recall"] == "NOT_ESTIMABLE"


def test_duplicate_cohort_identity_is_rejected():
    data = rows()
    data[1]["cik"] = data[0]["cik"]
    with pytest.raises(ValueError, match="duplicate"):
        study.validate_rows(data)


def test_reliability_detects_variation_and_empty_evidence_is_not_agreement():
    first = {
        "proposal": "FLAG",
        "final": "REVIEW",
        "automation": False,
        "reasons": ["fragility"],
        "score": 70,
        "evidence": [],
    }
    changed = {**deepcopy(first), "final": "ABSTAIN"}
    observed = study.reliability([first, changed])
    assert observed["final_consistency"] == 0
    assert observed["proposal_consistency"] == 1
    assert observed["evidence_jaccard"] == "NOT_ESTIMABLE"


def test_corrupted_input_is_rejected_without_rewriting_historical_data(tmp_path):
    config = json.loads((study.HERE / "config.json").read_text())
    location = tmp_path / "research/v042_experiments"
    location.mkdir(parents=True)
    (location / "config.json").write_text(json.dumps(config))
    first = next(iter(config["inputs"]))
    corrupted = tmp_path / first
    corrupted.parent.mkdir(parents=True, exist_ok=True)
    corrupted.write_text("{}")
    with pytest.raises(ValueError, match="input hash mismatch"):
        study.build(tmp_path)


def test_checked_in_derived_results_and_manifest_are_reproducible(monkeypatch):
    monkeypatch.setattr("sys.argv", ["run_diagnostics", "--check"])
    study.main()


def test_corrupted_result_manifest_cannot_pass_even_with_valid_inputs(
    tmp_path, monkeypatch
):
    for name in (
        "config.json",
        "results.json",
        "manifest.json",
        "EXPERIMENT_SUMMARY.md",
    ):
        (tmp_path / name).write_bytes((study.HERE / name).read_bytes())
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["results_sha256"] = "0" * 64
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(study, "HERE", tmp_path)
    monkeypatch.setattr("sys.argv", ["run_diagnostics", "--check"])
    with pytest.raises(SystemExit, match="provenance drift"):
        study.main()
