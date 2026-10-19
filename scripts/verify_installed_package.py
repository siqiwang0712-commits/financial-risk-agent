"""Smoke-test an installed FinRisk distribution outside the source import path."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("FINRISK_LLM_PROVIDER", "mock")


def main() -> int:
    import finrisk
    from finrisk.api import app
    from finrisk.assurance import verify_decision_certificate
    from finrisk.pipeline import FinRiskPipeline

    if finrisk.__version__ != "0.4.2":
        raise SystemExit(f"unexpected installed version: {finrisk.__version__}")
    pipeline = FinRiskPipeline()
    prefix = Path(sys.prefix).resolve()
    if not Path(finrisk.__file__).resolve().is_relative_to(prefix):
        raise SystemExit("package smoke imported source instead of the installed wheel")
    if pipeline.root.resolve() != prefix / "finrisk_data":
        raise SystemExit("package smoke loaded checkout resources instead of wheel resources")
    assessment = pipeline.assess(
        "Installed Package Smoke",
        2025,
        {
            "current_assets": 80.0,
            "current_liabilities": 100.0,
            "cash": 5.0,
            "total_assets": 200.0,
            "total_liabilities": 160.0,
            "revenue": 120.0,
            "net_income": -8.0,
        },
    )
    payload = pipeline.decide(assessment)
    if payload["final_decision"] != payload["assurance"]["final_decision"]:
        raise SystemExit("final decision bypassed AssuranceResult")
    if not verify_decision_certificate(
        payload["decision_certificate"], pipeline.assurance.policy
    ):
        raise SystemExit("installed package produced an invalid Decision Certificate")
    if app.version != "0.4.2":
        raise SystemExit(f"unexpected API version: {app.version}")
    print(
        json.dumps(
            {
                "package_version": finrisk.__version__,
                "api_version": app.version,
                "proposed_decision": payload["proposed_decision"],
                "final_decision": payload["final_decision"],
                "assurance_status": payload["assurance"]["assurance_status"],
                "certificate_verified": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
