from pathlib import Path

import pytest
from finrisk.public_pilot import PublicPilotUnavailable, public_pilot_payload

ROOT = Path(__file__).resolve().parents[1]


def test_public_pilot_projection_is_cached_and_contract_complete():
    public_pilot_payload.cache_clear()
    first = public_pilot_payload(ROOT)
    second = public_pilot_payload(ROOT)

    assert first is second
    assert first["runtime"] == "v0.3.3"
    assert first["rows"]
    required = {"entity", "decision", "score", "reliability", "filing"}
    assert all(required <= set(row) for row in first["rows"])


def test_public_pilot_missing_artifact_fails_closed(tmp_path):
    with pytest.raises(PublicPilotUnavailable, match="snapshot is unavailable"):
        public_pilot_payload(tmp_path)
