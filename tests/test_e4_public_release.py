from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_e4_public_release_surface_passes() -> None:
    path = ROOT / "scripts/verify_e4_public_artifacts.py"
    spec = importlib.util.spec_from_file_location("verify_e4_public_artifacts", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.verify()
    assert result["status"] == "PASS"
    assert result["e4_verified"] == 674
    assert result["posthoc_predictions"] == 150
