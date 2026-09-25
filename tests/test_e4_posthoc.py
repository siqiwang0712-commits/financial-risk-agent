from __future__ import annotations

import hashlib
import json
from pathlib import Path

from finrisk.e4_posthoc import _weighted_auc, percentile

ROOT = Path(__file__).resolve().parents[1]


def test_percentile_is_deterministic_and_interpolated() -> None:
    assert percentile([0.0, 10.0], 0.5) == 5.0
    assert percentile([], 0.5) is None


def test_weighted_auc_respects_pair_weights() -> None:
    labels = [1, 1, 0, 0]
    perfect = _weighted_auc(labels, [0.9, 0.8, 0.2, 0.1], [1.0, 2.0, 3.0, 4.0])
    reversed_auc = _weighted_auc(labels, [0.1, 0.2, 0.8, 0.9], [1.0, 2.0, 3.0, 4.0])
    assert perfect == 1.0
    assert reversed_auc == 0.0


def test_weighted_auc_requires_both_classes() -> None:
    assert _weighted_auc([1, 1], [0.1, 0.2], [1.0, 1.0]) is None


def test_sol_codex_comparator_is_complete_and_traceable() -> None:
    output = ROOT / "research/e4_posthoc/model_capacity/sol_codex_agent"
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    predictions = json.loads((output / "predictions.json").read_text(encoding="utf-8"))

    assert manifest["display_name"] == "ChatGPT5.6 Sol"
    assert manifest["identity_status"] == "PROJECT_INTERNAL_EXPERIMENTAL_CODENAME"
    assert manifest["exact_underlying_model_id"] == "NOT_EXPOSED_BY_PLATFORM"
    assert manifest["evidence_status"] == "POST_HOC"
    assert len(predictions) == 150
    assert len({(row["masked_company_id"], row["model_id"]) for row in predictions}) == 150
    assert {row["model_id"] for row in predictions} == {"SOL_A0", "SOL_A1", "SOL_A2"}
    assert {row["config_hash"] for row in predictions} == {manifest["config_hash"]}
    prediction_bytes = (
        (output / "predictions.json")
        .read_text(encoding="utf-8")
        .replace("\r\n", "\n")
        .encode("utf-8")
    )
    assert hashlib.sha256(prediction_bytes).hexdigest() == manifest["prediction_file_sha256"]

    for row in predictions:
        assert len(row["input_hash"]) == 64
        assert all(character in "0123456789abcdef" for character in row["input_hash"])
        assert 0 <= row["score"] <= 1
        assert row["prediction"] == int(row["score"] >= 0.5)
        assert row["coverage"] == 1.0
        assert row["abstained"] is False
        assert row["reliability"] == "UNCALIBRATED"
        assert row["evidence_status"] == "POST_HOC"
