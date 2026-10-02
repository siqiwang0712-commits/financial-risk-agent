"""Locate immutable runtime data in a checkout or an installed distribution."""

from __future__ import annotations

import sys
from pathlib import Path


def runtime_data_root(preferred: Path | None = None) -> Path:
    candidates = (
        preferred,
        Path(__file__).resolve().parents[2],
        Path(sys.prefix) / "finrisk_data",
    )
    for candidate in candidates:
        if candidate is not None and (candidate / "rules" / "rules.json").is_file():
            return candidate
    locations = ", ".join(str(item) for item in candidates if item is not None)
    raise FileNotFoundError(f"FinRisk runtime data is missing; checked: {locations}")


def runtime_data_file(*parts: str) -> Path:
    path = runtime_data_root().joinpath(*parts)
    if not path.is_file():
        raise FileNotFoundError(f"FinRisk runtime data file is missing: {path}")
    return path
