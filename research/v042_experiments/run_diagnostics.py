"""Bounded, offline post-hoc diagnostics; never fit models or change policy."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encoded(value):
    return (
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()


def validate_rows(rows):
    if not rows:
        raise ValueError("empty OOF cohort")
    for row in rows:
        if (
            type(row["label"]) is not int
            or row["label"] not in {0, 1}
            or type(row["score"]) not in {int, float}
            or not math.isfinite(row["score"])
            or not 0 <= row["score"] <= 1
            or row["score_semantics"] != "UNCALIBRATED_RANKING_SCORE"
            or not isinstance(row["observation_id"], str)
            or not row["observation_id"]
            or not isinstance(row["cik"], str)
            or not row["cik"]
        ):
            raise ValueError("invalid OOF observation")
    if any(
        len({row[key] for row in rows}) != len(rows)
        for key in ("observation_id", "cik")
    ):
        raise ValueError("duplicate observation/company")


def risk_coverage(rows, thresholds):
    """Issue diagnostic predictions by distance from fixed 0.5, never authorize."""
    validate_rows(rows)
    if any(
        type(t) not in {int, float} or not math.isfinite(t) or not 0 <= t <= 0.5
        for t in thresholds
    ):
        raise ValueError("invalid descriptive threshold")
    result = []
    for threshold in thresholds:
        issued = [r for r in rows if abs(r["score"] - 0.5) >= threshold]
        errors = sum((r["score"] >= 0.5) != bool(r["label"]) for r in issued)
        result.append(
            {
                "threshold": threshold,
                "n": len(rows),
                "issued": len(issued),
                "errors": errors,
                "coverage": len(issued) / len(rows),
                "selective_error": errors / len(issued) if issued else "NOT_ESTIMABLE",
                "review_rate": 1 - len(issued) / len(rows),
                "abstain_rate": 0,
                "actual_authorization_rate": "NOT_ESTIMABLE",
            }
        )
    return result


def review_budgets(rows, budgets):
    validate_rows(rows)
    if any(
        type(b) not in {int, float} or not math.isfinite(b) or not 0 < b <= 1
        for b in budgets
    ):
        raise ValueError("invalid review budget")
    ranked = sorted(rows, key=lambda r: (-r["score"], r["observation_id"]))
    events = sum(r["label"] for r in rows)
    result = []
    for budget in budgets:
        count = math.floor(len(rows) * budget)
        captured = sum(r["label"] for r in ranked[:count])
        result.append(
            {
                "budget": budget,
                "reviews": count,
                "n": len(rows),
                "actual_budget_fraction": count / len(rows),
                "events_captured": captured,
                "recall": captured / events if events else "NOT_ESTIMABLE",
                "precision": captured / count if count else "NOT_ESTIMABLE",
                "events_per_100_reviews": 100 * captured / count
                if count
                else "NOT_ESTIMABLE",
            }
        )
    return result


def reliability(runs):
    """Pairwise consistency; empty evidence unions are not evidence agreement."""
    if len(runs) < 2:
        raise ValueError("at least two repeated runs required")
    pairs = list(itertools.combinations(runs, 2))
    result = {
        key + "_consistency": sum(a[key] == b[key] for a, b in pairs) / len(pairs)
        for key in ("proposal", "final", "automation", "reasons", "score")
    }
    jaccards = [
        len(set(a["evidence"]) & set(b["evidence"]))
        / len(set(a["evidence"]) | set(b["evidence"]))
        for a, b in pairs
        if set(a["evidence"]) | set(b["evidence"])
    ]
    result["evidence_jaccard"] = (
        sum(jaccards) / len(jaccards) if jaccards else "NOT_ESTIMABLE"
    )
    return result


def mock_agent_repeats(root):
    from finrisk.agent import FinancialRiskAgent
    from finrisk.assurance import verify_decision_certificate
    from finrisk.llm import MockNarrativeProvider

    fixture = json.loads((root / "examples/synthetic_company.json").read_text())
    cases = []
    for case in ("synthetic_with_pages", "synthetic_without_pages"):
        runs = []
        for _ in range(3):
            agent = FinancialRiskAgent(root, provider=MockNarrativeProvider())
            state = agent.run(
                fixture["company"],
                fixture["fiscal_year"],
                fixture["current"],
                fixture["previous"],
                {int(k): v for k, v in fixture["pages"].items()}
                if case.endswith("with_pages")
                else {},
            )
            if not verify_decision_certificate(
                state.decision_certificate, agent.pipeline.assurance.policy
            ):
                raise ValueError("mock Agent did not produce a valid certificate")
            runs.append(
                {
                    "proposal": state.proposed_decision,
                    "final": state.decision,
                    "automation": state.assurance["automation_allowed"],
                    "reasons": state.assurance["reason_codes"],
                    "score": state.risk_score,
                    "evidence": state.assurance["evidence_assurance"][
                        "verified_evidence_ids"
                    ],
                }
            )
        cases.append({"case": case, "k": 3, "runs": runs, "metrics": reliability(runs)})
    return {
        "status": "MOCK_HARNESS_ONLY",
        "real_run": "NOT_RUN_PROVIDER_UNAVAILABLE",
        "cases": cases,
        "instability_reduction": "NOT_ESTIMABLE_DETERMINISTIC_MOCK",
    }


def build(root=ROOT):
    config = json.loads((root / "research/v042_experiments/config.json").read_text())
    for name, digest in config["inputs"].items():
        if (
            hashlib.sha256(
                (root / name).read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest()
            != digest
        ):
            raise ValueError("experiment input hash mismatch: " + name)
        # Independently bind historical bytes to the recorded source, not just a
        # mutable manifest that could be edited together with its input hashes.
        original = subprocess.check_output(
            ["git", "show", f"{config['source_commit']}:{name}"], cwd=root
        )
        if hashlib.sha256(original).hexdigest() != config["source_blob_sha256"][
            name
        ] or original.replace(b"\r\n", b"\n") != (root / name).read_bytes().replace(
            b"\r\n", b"\n"
        ):
            raise ValueError("experiment source commit mismatch: " + name)
    artifacts = root / "research/strong_tabular_reference/artifacts"
    candidates = json.loads((artifacts / "oof_predictions.json").read_text())[
        "candidates"
    ]
    rows = candidates[config["candidate"]]
    validate_rows(rows)
    if len(rows) != 675 or sum(r["label"] for r in rows) != 235:
        raise ValueError("approved cohort identity/count mismatch")
    folds = json.loads((artifacts / "fold_assignments.json").read_text())["outer_folds"]
    flat = [i for fold in folds for i in fold["test_observation_ids"]]
    if (
        len(flat) != len(set(flat))
        or set(flat) != {r["observation_id"] for r in rows}
        or len(folds) != 5
    ):
        raise ValueError("fold membership mismatch")
    fold_results = []
    for fold in folds:
        subset = [
            r for r in rows if r["observation_id"] in fold["test_observation_ids"]
        ]
        if len(subset) < config["minimum_n"]:
            fold_results.append({"fold": fold["fold"], "status": "INSUFFICIENT_N"})
        else:
            fold_results.append(
                dict(
                    fold=fold["fold"],
                    status="COMPLETE",
                    **risk_coverage(subset, [0])[0],
                )
            )
    common = {
        "source_commit": config["source_commit"],
        "dataset_identity": config["dataset_id"],
        "cohort_identity": config["cohort_sha256"],
        "configuration": config,
        "random_seeds": "NONE_NO_REFITTING_OR_SAMPLING",
        "timestamp_utc": config["timestamp_utc"],
        "code_version_sha256": sha(Path(__file__)),
        "runtime_identity_sha256": sha(
            root / "research/v042_development/runtime_identities.json"
        ),
        "affects_production": False,
        "calibration_status": "UNCALIBRATED",
        "evidence_class": [
            "RETROSPECTIVE_DEVELOPMENT",
            "DESIGN_EXPOSED",
            "POST_HOC_EXPLORATORY",
        ],
    }
    experiments = [
        dict(
            id="V042-RC-01",
            status="COMPLETE",
            **common,
            results=risk_coverage(rows, config["thresholds"]),
        ),
        dict(
            id="V042-BUDGET-01",
            status="COMPLETE",
            **common,
            results=review_budgets(rows, config["review_budgets"]),
        ),
        dict(id="V042-FOLD-01", status="COMPLETE", **common, results=fold_results),
        dict(
            id="V042-AGENT-01",
            **{
                **common,
                "dataset_identity": "examples/synthetic_company.json",
                "cohort_identity": config["inputs"]["examples/synthetic_company.json"],
                "evidence_class": ["SYNTHETIC_ENGINEERING_ONLY"],
            },
            **mock_agent_repeats(root),
        ),
    ]
    return {
        "schema_version": 1,
        "metric_definitions": config["metric_definitions"],
        "experiments": experiments,
        "deferred": [
            {
                "id": "ASSURANCE_ABLATION",
                "status": "NOT_ESTIMABLE",
                "reason": "Historical OOF rows lack Agent evidence, fragility and Assurance states; no intermediate arms fabricated.",
            },
            {
                "id": "SHIFT_SUBGROUP_REFIT",
                "status": "DEFERRED_NON_BLOCKING",
                "reason": "Existing diagnostics preserved; further feature reconstruction/refitting is outside the bounded closeout.",
            },
        ],
    }


def summary(result):
    lines = [
        "# v0.4.2 development experiments",
        "",
        "RETROSPECTIVE_DEVELOPMENT / DESIGN_EXPOSED / POST_HOC_EXPLORATORY.",
        "",
        (
            "Historical OOF predictions: 675 selected verified-label observations, 235 events. "
            "This is a heavily analyzed development cohort, not prospective or external validation. "
            "No model was refitted, winner changed, probability calibrated or production policy changed."
        ),
        "",
    ]
    tables = {
        "V042-RC-01": (
            "Risk and coverage",
            ["threshold", "n", "issued", "coverage", "selective_error", "review_rate"],
        ),
        "V042-BUDGET-01": (
            "Review budget",
            ["budget", "reviews", "events_captured", "recall", "precision"],
        ),
        "V042-FOLD-01": (
            "Existing fold sensitivity",
            ["fold", "n", "errors", "selective_error"],
        ),
    }
    for experiment in result["experiments"]:
        if experiment["id"] not in tables:
            continue
        title, keys = tables[experiment["id"]]
        lines += [
            "## " + title,
            "",
            "| " + " | ".join(keys) + " |",
            "| " + " | ".join(["---"] * len(keys)) + " |",
        ]
        for row in experiment["results"]:
            cells = [
                f"{row[k]:.6f}" if isinstance(row[k], float) else str(row[k])
                for k in keys
            ]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    lines += [
        (
            "Distance from 0.5 is descriptive score separation, not calibrated confidence. "
            "Issued diagnostic predictions are not authorized final decisions. Threshold ties are included. "
            "Budget counts are floored, with score ties broken by observation ID. "
            "Fold errors use existing outer-fold OOF predictions at 0.5, not new fitting or seed trials."
        ),
        "",
        "## Agent repeatability harness",
        "",
        "MOCK_HARNESS_ONLY / SYNTHETIC_ENGINEERING_ONLY. Two synthetic scenarios, k=3. Each certificate is checked against runtime policy. Empty evidence unions are NOT_ESTIMABLE. Real provider: NOT_RUN_PROVIDER_UNAVAILABLE.",
        "",
    ]
    agent = next(e for e in result["experiments"] if e["id"] == "V042-AGENT-01")
    lines += [
        "| Case | Proposal consistency | Final consistency | Evidence Jaccard | Final values | Automation values |",
        "|---|---|---|---|---|---|",
    ]
    for case in agent["cases"]:
        metrics = case["metrics"]
        final_values = ", ".join(sorted({r["final"] for r in case["runs"]}))
        automation = ", ".join(
            str(v) for v in sorted({r["automation"] for r in case["runs"]})
        )
        lines.append(
            f"| {case['case']} | {metrics['proposal_consistency']} | {metrics['final_consistency']} | {metrics['evidence_jaccard']} | {final_values} | {automation} |"
        )
    lines += [
        "",
        "Deterministic mocks cannot establish whether Assurance reduces real-provider instability.",
        "",
        "## Limits and deferred work",
        "",
        (
            "Historical Assurance ablation: NOT_ESTIMABLE because OOF rows lack Agent evidence, fragility and Assurance states. "
            "Further shift/subgroup/refitting studies: DEFERRED_NON_BLOCKING to preserve release priority. "
            "No intermediate states, human annotations, future cohorts, outcomes or E5 exclusions were fabricated."
        ),
        "",
        (
            "Future work may evaluate these descriptive thresholds on genuinely untouched data. "
            "None is a prespecified or validated production threshold. Review-budget precision is not realized profit. "
            "E5 remains BLOCKED / DRAFT_NOT_FROZEN."
        ),
        "",
    ]
    return "\n".join(lines).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = HERE / "results.json"
    observed = build()
    result = encoded(observed)
    rendered = summary(observed)
    manifest = encoded(
        {
            "schema_version": 1,
            "config_sha256": sha(HERE / "config.json"),
            "code_sha256": sha(Path(__file__)),
            "results_sha256": hashlib.sha256(result).hexdigest(),
            "summary_sha256": hashlib.sha256(rendered).hexdigest(),
            "production_policy_changed": False,
            "e5_executed": False,
        }
    )
    if args.check:
        if (
            output.read_bytes() != result
            or (HERE / "manifest.json").read_bytes() != manifest
            or (HERE / "EXPERIMENT_SUMMARY.md").read_bytes() != rendered
        ):
            raise SystemExit("v0.4.2 experimental result/provenance drift")
        print("v0.4.2 derived experiments: PASS (post-hoc, uncalibrated, no E5)")
    else:
        output.write_bytes(result)
        (HERE / "manifest.json").write_bytes(manifest)
        (HERE / "EXPERIMENT_SUMMARY.md").write_bytes(rendered)
        print("Wrote new v0.4.2 derived results; historical artifacts unchanged")


if __name__ == "__main__":
    main()
