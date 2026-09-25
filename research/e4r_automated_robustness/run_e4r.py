"""Run the E4-R automated robustness and competitive-baseline study end to end.

Usage::

    python research/e4r_automated_robustness/run_e4r.py            # full study
    python research/e4r_automated_robustness/run_e4r.py --quick     # 2000 bootstrap replicates

The script is fail-closed at three points: the source-integrity gate, the leakage audit and
the frozen-config check. If any of them fails the run stops and no performance claim is
written.

Everything written here is derived from artifacts; nothing is hand-entered.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import platform
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np

# scikit-learn 1.8 deprecates `penalty` in favour of `l1_ratio`; the study pins the classic
# L1/L2/unpenalised forms deliberately, so the future warning is noise here.
warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn")

import e4r_ablation
import e4r_analysis
import e4r_config
import e4r_data
import e4r_leakage
import e4r_models
import e4r_stats

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
for _path in (str(REPO_ROOT / "backend"), str(REPO_ROOT / "research" / "e4_statistical_audit"), str(HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

FIGURE_DIR = HERE / "figures"


def _write(name: str, payload: dict | list) -> Path:
    path = HERE / name
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    return path


def _read(name: str):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def _metrics(labels: list[int], scores: list[float]) -> dict:
    return e4r_analysis.metrics(labels, scores)


def git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=str(REPO_ROOT), check=False
        )
        return result.stdout.strip() or "UNKNOWN"
    except OSError:
        return "UNKNOWN"


def package_versions(names: list[str]) -> dict[str, str]:
    from importlib import metadata

    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "NOT_INSTALLED"
    return versions


# --------------------------------------------------------------------------------------
# Pipeline stages
# --------------------------------------------------------------------------------------


def stage_integrity(skip_external: bool) -> dict:
    print("== stage 1: source integrity ==")
    report = e4r_data.verify_sources(run_external=not skip_external)
    print(f"   replication files: {len(report.replication_files)}, failures: {len(report.failures)}")
    print(f"   status: {report.status}")
    if report.status != "PASS":
        for failure in report.failures:
            print(f"   FAIL {failure}")
        raise SystemExit("source integrity failed; E4-R stopped by design")
    return report.to_dict()


def stage_dataset() -> tuple[e4r_data.Dataset, dict]:
    print("== stage 2: cohort + B0/B6 reconstruction ==")
    dataset = e4r_data.build_dataset()
    reconstruction = e4r_data.check_reconstruction(dataset)
    print(f"   n={dataset.n} events={dataset.events}")
    print(f"   B0 max|error| vs published: {reconstruction['b0_max_abs_error']:.3e}")
    print(f"   B6 max|error| vs published: {reconstruction['b6_max_abs_error']:.3e}")
    if reconstruction["b0_mismatches"] or reconstruction["b6_mismatches"]:
        raise SystemExit("frozen B0/B6 could not be reconstructed from the packet; E4-R stopped")
    return dataset, reconstruction


def stage_leakage(dataset: e4r_data.Dataset) -> dict:
    print("== stage 3: leakage audit ==")
    cohort, _features, outcomes, _analysis = e4r_data.load_packet()
    result = e4r_leakage.audit(dataset, cohort, outcomes)
    print(f"   status: {result['status']}")
    for check in result["checks"]:
        if check["status"] != "PASS":
            print(f"   {check['status']}: {check['check']} -- {check['detail']}")
    _write("leakage_audit.json", result)
    if result["status"] == "INVALIDATED":
        raise SystemExit("confirmed leakage; E4-R is INVALIDATED and publishes no performance claim")
    return result


def stage_ablation(dataset: e4r_data.Dataset, bootstrap: int, seed: int) -> tuple[dict, dict]:
    print("== stage 4: B6 temporal ablation ==")
    verification = e4r_ablation.verify_against_frozen(dataset)
    print(f"   ablation reproduces the frozen score: {verification['status']} (max err {verification['max_abs_error']:.3e})")
    if verification["status"] != "PASS":
        raise SystemExit("ablation does not reproduce the frozen B6; refusing to report ablation results")

    vectors = e4r_ablation.ablation_score_vectors(dataset)
    labels = [dataset.labels[oid] for oid in dataset.observation_ids]
    full_key = "B6_full"
    payload: dict = {
        "status": e4r_data.STATUS,
        "formula_verification": verification,
        "definitions": {
            "B6_full": "the frozen temporal_risk_score",
            "B6_no_temporal": "0.75 * B0 with every growth term removed; a strictly increasing map of B0",
            "B6_temporal_only": "adverse / observed, the temporal block alone",
            "B6_minus_<term>": "the frozen closed form with that growth term removed from both the numerator and the denominator",
        },
        "variants": {},
        "comparisons": {},
    }
    for name, vector in vectors.items():
        scores = [vector[oid] for oid in dataset.observation_ids]
        complete = not any(math.isnan(value) for value in scores)
        payload["variants"][name] = {
            "n_scored": sum(1 for value in scores if not math.isnan(value)),
            "complete": complete,
            **(_metrics(labels, scores) if complete else {"auroc": None, "pr_auc": None}),
        }

    for name in vectors:
        if name == full_key:
            continue
        rows = e4r_stats.paired_rows(
            dataset.observation_ids, dataset.labels, vectors[full_key], vectors[name]
        )
        comparison = {
            "delta_auroc_vs_full": e4r_stats.delta_metric(rows, "auroc"),
            "delta_pr_auc_vs_full": e4r_stats.delta_metric(rows, "pr_auc"),
            "delong_vs_full": e4r_stats.delong_paired(rows, "auroc"),
            "bootstrap_delta_auroc_vs_full": e4r_stats.paired_bootstrap(rows, "auroc", bootstrap, seed),
        }
        b0_rows = e4r_stats.paired_rows(
            dataset.observation_ids, dataset.labels, vectors["B6_no_temporal"], vectors[name]
        )
        comparison["delta_auroc_vs_b0_equivalent"] = e4r_stats.delta_metric(b0_rows, "auroc")
        payload["comparisons"][name] = comparison
        print(f"   {name}: AUROC={payload['variants'][name]['auroc']:.4f} "
              f"Δ vs B6_full={comparison['delta_auroc_vs_full']:+.4f}")

    payload["structural_note"] = (
        "B6_no_temporal is 0.75 * B0. Because B0 lies in [0, 1] that is a strictly increasing "
        "map of B0, so AUROC(B6_no_temporal) equals AUROC(B0) exactly; the 0.25 temporal block "
        "is the only thing that can reorder observations."
    )
    _write("temporal_ablation.json", payload)
    return vectors, payload


def stage_contribution(dataset: e4r_data.Dataset) -> dict:
    print("== stage 5: temporal contribution attribution ==")
    raw = e4r_ablation.temporal_contributions(dataset)
    summary: dict = {
        "status": e4r_data.STATUS,
        "n": len(raw["per_observation"]),
        "events": sum(row["label"] for row in raw["per_observation"]),
        "terms": {},
        "sector_trigger_rates": {},
    }
    for name in e4r_ablation.TERM_NAMES:
        present = [row for row in raw["per_observation"] if row[f"{name}_present"]]
        triggered = [row for row in present if row[f"{name}_triggered"]]
        events = [row for row in triggered if row["label"] == 1]
        non_events = [row for row in triggered if row["label"] == 0]
        contributions = [row[f"{name}_contribution"] for row in raw["per_observation"]]
        event_rate_present = sum(row["label"] for row in present) / len(present) if present else None
        summary["terms"][name] = {
            "label": e4r_ablation.TERM_LABELS[name],
            "present_n": len(present),
            "present_share": len(present) / len(raw["per_observation"]),
            "triggered_n": len(triggered),
            "trigger_prevalence_overall": len(triggered) / len(raw["per_observation"]),
            "trigger_rate_when_present": len(triggered) / len(present) if present else None,
            "event_rate_when_triggered": sum(row["label"] for row in triggered) / len(triggered) if triggered else None,
            "event_rate_when_present": event_rate_present,
            "mean_contribution": sum(contributions) / len(contributions),
            "mean_contribution_among_events": (
                sum(row[f"{name}_contribution"] for row in raw["per_observation"] if row["label"] == 1)
                / max(1, sum(row["label"] for row in raw["per_observation"]))
            ),
            "mean_contribution_among_non_events": (
                sum(row[f"{name}_contribution"] for row in raw["per_observation"] if row["label"] == 0)
                / max(1, sum(1 - row["label"] for row in raw["per_observation"]))
            ),
            "event_share_of_triggers": len(events) / len(triggered) if triggered else None,
            "non_event_triggers": len(non_events),
        }
    sectors: dict[str, dict] = {}
    for row in raw["per_observation"]:
        bucket = sectors.setdefault(row["sector"], {"n": 0, "triggers": {name: 0 for name in e4r_ablation.TERM_NAMES}})
        bucket["n"] += 1
        for name in e4r_ablation.TERM_NAMES:
            bucket["triggers"][name] += int(bool(row[f"{name}_triggered"]))
    summary["sector_trigger_rates"] = {
        sector: {
            "n": bucket["n"],
            **{name: (bucket["triggers"][name] / bucket["n"]) for name in e4r_ablation.TERM_NAMES},
        }
        for sector, bucket in sorted(sectors.items())
    }
    _write("temporal_contribution_summary.json", summary)
    for name, entry in summary["terms"].items():
        print(f"   {name}: present {entry['present_share']:.3f}, trigger {entry['trigger_prevalence_overall']:.3f}, "
              f"mean contribution {entry['mean_contribution']:.4f}")
    return summary


def stage_models(dataset: e4r_data.Dataset, feature_sets: dict, config: dict) -> dict[str, dict]:
    print("== stage 6: nested cross-validated baselines ==")
    families = feature_sets["families"]
    labels = [dataset.labels[oid] for oid in dataset.observation_ids]
    groups = [dataset.masked_company_id[oid] for oid in dataset.observation_ids]
    score_vectors: dict[str, dict[str, float]] = {
        "B0": {oid: dataset.published_scores["B0"][oid] for oid in dataset.observation_ids},
        "B6": {oid: dataset.published_scores["B6"][oid] for oid in dataset.observation_ids},
    }
    details: dict[str, dict] = {}
    fold_of: dict[str, dict[str, str]] = {}
    for run in config["models"]["runs"]:
        family = families[run["feature_set"]]
        fields = family["fields"]
        matrix = dataset.matrix(fields)
        result = e4r_models.nested_cv(
            observation_ids=dataset.observation_ids,
            matrix=matrix,
            labels=labels,
            groups=groups,
            feature_names=list(fields),
            estimator_family=run["family"],
            model_id=run["model_id"],
            feature_set=run["feature_set"],
            seed=config["seeds"]["master"],
            n_outer=config["cross_validation"]["outer_splits"],
            n_inner=config["cross_validation"]["inner_splits"],
            apply_coverage_filter=bool(family.get("coverage_filter")),
            min_train_coverage=float(family.get("min_train_coverage", 0.4)),
        )
        score_vectors[run["model_id"]] = result.oof_scores
        fold_of[run["model_id"]] = result.fold_of
        scores = result.scores_in_order(dataset.observation_ids)
        details[run["model_id"]] = {
            "model_id": run["model_id"],
            "estimator_family": run["family"],
            "feature_set": run["feature_set"],
            "role": run["role"],
            "n_features_requested": len(fields),
            "prediction_source": "out-of-fold (each observation scored by a model that never saw it)",
            "fit_seconds": round(result.fit_seconds, 3),
            "candidates_evaluated": result.candidates_evaluated,
            "inner_failures": result.inner_failures,
            "outer_failures": result.outer_failures,
            "selected_params_by_fold": result.selected_params,
            **_metrics(labels, scores),
        }
        print(
            f"   {run['model_id']:22s} AUROC={details[run['model_id']]['auroc']:.4f} "
            f"PR-AUC={details[run['model_id']]['pr_auc']:.4f} ({result.fit_seconds:.1f}s)"
        )
    return {"score_vectors": score_vectors, "details": details, "fold_of": fold_of}


def write_oof_ledger(rows: list[dict], model_names: list[str]) -> None:
    """Write the CSV and JSON halves of the ledger from one set of records."""
    with (HERE / "oof_predictions.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["observation_id", "label", "fold", "model", "predicted_score", "B0", "B6"],
            # csv's default terminator is CRLF, which would make the ledger CRLF on Windows
            # and LF everywhere else - and the manifest hashes this file.
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    _write("oof_predictions.json", {
        "status": e4r_data.STATUS,
        "rows": len(rows),
        "models": sorted(model_names),
        "coverage_rule": "every observation appears exactly once per learned model; B0 and B6 are "
                         "deterministic functions with nothing to fit, so they carry fold=NA",
        "records": rows,
    })
    print(f"   {len(rows)} rows across {len(model_names)} scorers")


def stage_oof(dataset: e4r_data.Dataset, score_vectors: dict[str, dict], fold_of: dict) -> None:
    print("== stage 7: out-of-fold prediction ledger ==")
    rows = []
    for model_id, vector in sorted(score_vectors.items()):
        for oid in dataset.observation_ids:
            rows.append(
                {
                    "observation_id": oid,
                    "label": dataset.labels[oid],
                    "fold": fold_of.get(model_id, {}).get(oid, "NA"),
                    "model": model_id,
                    "predicted_score": vector[oid],
                    "B0": dataset.published_scores["B0"][oid],
                    "B6": dataset.published_scores["B6"][oid],
                }
            )
    write_oof_ledger(rows, list(score_vectors))


def stage_statistics(
    dataset: e4r_data.Dataset,
    score_vectors: dict[str, dict[str, float]],
    config: dict,
    bootstrap: int,
) -> dict:
    print("== stage 8: statistical comparison ==")
    seed = config["seeds"]["bootstrap"]

    def compare(entry: dict) -> dict:
        rows = e4r_stats.paired_rows(
            dataset.observation_ids, dataset.labels, score_vectors[entry["reference"]], score_vectors[entry["challenger"]]
        )
        payload = e4r_stats.paired_comparison(rows, bootstrap, seed, label=entry.get("label"))
        payload["id"] = entry["id"]
        payload["reference"] = entry["reference"]
        payload["challenger"] = entry["challenger"]
        payload["direction"] = f"{entry['challenger']} - {entry['reference']}"
        return payload

    def available(entry: dict) -> bool:
        return entry["reference"] in score_vectors and entry["challenger"] in score_vectors

    primary = [compare(entry) for entry in config["primary_family"] if available(entry)]
    e4r_stats.holm_family(primary)
    secondary = []
    for entry in config["secondary_family"]:
        if not available(entry):
            continue
        rows = e4r_stats.paired_rows(
            dataset.observation_ids, dataset.labels, score_vectors[entry["reference"]], score_vectors[entry["challenger"]]
        )
        payload = {
            "id": entry["id"],
            "reference": entry["reference"],
            "challenger": entry["challenger"],
            "label": entry.get("label"),
            "direction": f"{entry['challenger']} - {entry['reference']}",
            "delta_auroc": e4r_stats.delta_metric(rows, "auroc"),
            "delta_pr_auc": e4r_stats.delta_metric(rows, "pr_auc"),
            "reference_auroc": e4r_stats.marginal_metric(rows, "reference", "auroc"),
            "challenger_auroc": e4r_stats.marginal_metric(rows, "challenger", "auroc"),
            "delong": e4r_stats.delong_paired(rows, "auroc"),
            "bootstrap_auroc": e4r_stats.paired_bootstrap(rows, "auroc", bootstrap, seed),
            "holm_adjusted_p": None,
        }
        secondary.append(payload)

    for item in primary:
        print(f"   {item['id']}: Δ={item['delta_auroc']:+.4f} DeLong p={item['delong']['p_value']:.4g} "
              f"Holm p={item['holm_adjusted_p']:.4g} BCa=[{item['bootstrap_auroc']['bca_low']:+.4f}, "
              f"{item['bootstrap_auroc']['bca_high']:+.4f}]")
    for item in secondary:
        print(f"   {item['id']} (secondary): Δ={item['delta_auroc']:+.4f} DeLong p={item['delong']['p_value']:.4g}")

    payload = {
        "status": e4r_data.STATUS,
        "bootstrap_replicates": bootstrap,
        "bootstrap_seed": seed,
        "multiplicity": "Holm step-down across the three prespecified primary comparisons; secondary "
                        "comparisons are reported unadjusted and carry no confirmatory weight",
        "primary": primary,
        "secondary": secondary,
    }
    _write("statistical_tests.json", payload)
    return payload


def stage_incremental(
    dataset: e4r_data.Dataset, feature_sets: dict, config: dict, seed: int
) -> dict:
    print("== stage 9: temporal incremental value (logistic, coefficient stability) ==")
    fields = list(feature_sets["families"]["F2"]["fields"])
    matrix = dataset.matrix(fields)
    labels = [dataset.labels[oid] for oid in dataset.observation_ids]
    groups = [dataset.masked_company_id[oid] for oid in dataset.observation_ids]
    stability = e4r_models.coefficient_stability(
        dataset.observation_ids, matrix, labels, groups, fields, seed=seed,
        n_outer=config["cross_validation"]["outer_splits"],
    )
    payload = {
        "status": e4r_data.STATUS,
        "design": "Y ~ F0 versus Y ~ F0 + temporal, both scored out-of-fold",
        "caution": "coefficients are fitted prediction-time associations on 4/5 of the cohort, "
                   "not causal effects and not a mediation analysis",
        "feature_order": fields,
        "coefficient_stability_across_outer_folds": stability["per_feature"],
        "fold_fits": stability["folds"],
    }
    _write("temporal_incremental_test.json", payload)
    for name, entry in stability["per_feature"].items():
        print(f"   {name:30s} mean={entry['mean']:+.4f} sign={entry['consistent_sign']} "
              f"consistency={entry['sign_consistency']:.2f}")
    return payload


def stage_subgroups(dataset: e4r_data.Dataset, score_vectors: dict, config: dict, feature_sets: dict) -> dict:
    print("== stage 10: sector / firm-size / missingness robustness ==")
    gates = config["subgroup_gates"]
    focus = ["B0", "B6", "hist_gb_F2", "logistic_F2"]
    focused = {name: score_vectors[name] for name in focus if name in score_vectors}

    sector_rows = e4r_analysis.subgroup_table(
        dataset.observation_ids, dataset.labels, dataset.sector, focused,
        min_n=gates["min_n"], min_events=gates["min_events"],
    )
    for row in sector_rows:
        if row["estimable"]:
            b0 = row["models"]["B0"]["auroc"]
            b6 = row["models"]["B6"]["auroc"]
            delta = None if (b0 is None or b6 is None) else b6 - b0
            print(f"   sector {row['subgroup']:24s} n={row['n']:3d} events={row['events']:3d} "
                  f"B0={b0:.4f} B6={b6:.4f} Δ={delta:+.4f}" if delta is not None else "")
        else:
            print(f"   sector {row['subgroup']:24s} n={row['n']:3d} events={row['events']:3d} NOT_ESTIMABLE")

    size_values = {
        oid: float(dataset.current[oid]["total_assets"])
        for oid in dataset.observation_ids
        if dataset.current[oid].get("total_assets") is not None
    }
    if len(size_values) >= 0.9 * dataset.n:
        membership = e4r_analysis.quantile_membership(
            [oid for oid in dataset.observation_ids if oid in size_values], size_values,
            tuple(config["firm_size"]["bins"]),
        )
        size_rows = e4r_analysis.subgroup_table(
            [oid for oid in dataset.observation_ids if oid in size_values],
            dataset.labels, membership, focused,
            min_n=gates["min_n"], min_events=gates["min_events"],
        )
        size_status = "OK"
        size_note = f"split on {config['firm_size']['measure']} (feature-side, no outcome used); {len(size_values)}/{dataset.n} observations carry the measure"
    else:
        size_rows = []
        size_status = "NOT_ESTIMABLE"
        size_note = f"only {len(size_values)}/{dataset.n} observations carry {config['firm_size']['measure']}"

    f2_fields = feature_sets["families"]["F2"]["fields"]
    column_matrix = {
        name: [e4r_data._as_float(dataset.metrics[oid].get(name)) for oid in dataset.observation_ids]
        for name in f2_fields
    }
    profile = e4r_analysis.missingness_profile(dataset.observation_ids, column_matrix, f2_fields)
    bands = e4r_analysis.missingness_bands(profile, tuple(config["missingness"]["bins"]))
    missing_rows = e4r_analysis.subgroup_table(
        dataset.observation_ids, dataset.labels, bands, focused,
        min_n=gates["min_n"], min_events=gates["min_events"],
    )
    for row in missing_rows:
        print(f"   missingness {row['subgroup']:8s} n={row['n']:3d} events={row['events']:3d} "
              f"B0={row['models']['B0']['auroc']:.4f} B6={row['models']['B6']['auroc']:.4f} "
              f"Boosting={row['models']['hist_gb_F2']['auroc']:.4f}")

    payload = {
        "status": e4r_data.STATUS,
        "gates": gates,
        "focus_models": focus,
        "sector": {"status": "OK", "rows": sector_rows},
        "firm_size": {"status": size_status, "note": size_note, "rows": size_rows},
        "missingness": {
            "status": "OK",
            "measure": "fraction of F2 fields missing per observation",
            "profile_mean": sum(profile.values()) / len(profile),
            "rows": missing_rows,
        },
    }
    _write("subgroup_results.json", payload)
    return payload


def stage_influence(dataset: e4r_data.Dataset, score_vectors: dict, subgroup: dict, seed: int) -> dict:
    print("== stage 11: influence analysis ==")
    rows = e4r_stats.paired_rows(
        dataset.observation_ids, dataset.labels, score_vectors["B0"], score_vectors["B6"]
    )
    observed = e4r_stats.delta_metric(rows, "auroc")
    loo = e4r_stats.leave_one_out_delta(rows)
    loo_summary = e4r_stats.describe_influence(loo, "observation_id", observed)
    sectors_kept = [
        row["subgroup"] for row in subgroup["sector"]["rows"] if row["estimable"]
    ]
    sector_groups = {oid: dataset.sector[oid] for oid in dataset.observation_ids}
    loso = e4r_stats.leave_group_out_delta(rows, sector_groups)
    loso_summary = e4r_stats.describe_influence(
        [entry for entry in loso if entry["group"] in sectors_kept], "group", observed
    )
    payload = {
        "status": e4r_data.STATUS,
        "comparison": "B6 - B0",
        "observed_delta_auroc": observed,
        "leave_one_out": loo_summary,
        "leave_sector_out": {
            "status": loso_summary["status"],
            "observed_delta_auroc": observed,
            "sectors_evaluated": sectors_kept,
            "entries": loso,
            "summary": loso_summary,
        },
    }
    _write("influence_analysis.json", payload)
    print(f"   LOO: observed Δ={observed:+.4f}, min after deletion={loo_summary['min_delta_after_deletion']:+.4f}, "
          f"max={loo_summary['max_delta_after_deletion']:+.4f}, sign flips={loo_summary['deletions_flipping_sign']}")
    return payload


def stage_negative_controls(
    dataset: e4r_data.Dataset, score_vectors: dict, feature_sets: dict, config: dict, replicates: int
) -> dict:
    print("== stage 12: negative controls ==")
    labels = [dataset.labels[oid] for oid in dataset.observation_ids]
    rng = np.random.default_rng(config["seeds"]["label_permutation"])

    # NC1 -- labels carry no signal: every scorer must fall back to chance.
    nc1_models = ["B0", "B6", "logistic_F2", "hist_gb_F2"]
    nc1: dict[str, list[float]] = {name: [] for name in nc1_models}
    permuted_labels = list(labels)
    for _ in range(replicates):
        rng.shuffle(permuted_labels)
        for name in nc1_models:
            scores = [score_vectors[name][oid] for oid in dataset.observation_ids]
            value = e4r_stats.roc_auc(permuted_labels, scores)
            if value is not None:
                nc1[name].append(value)

    def describe(values: list[float]) -> dict:
        ordered = sorted(values)
        return {
            "replicates": len(values),
            "mean": sum(values) / len(values),
            "sd": e4r_stats.percentile_linear(values, 0.5) and math.sqrt(
                sum((value - sum(values) / len(values)) ** 2 for value in values) / (len(values) - 1)
            ),
            "p2_5": e4r_stats.percentile_linear(values, 0.025),
            "median": e4r_stats.percentile_linear(values, 0.5),
            "p97_5": e4r_stats.percentile_linear(values, 0.975),
            "min": ordered[0],
            "max": ordered[-1],
            "share_above_0_55": sum(1 for value in values if value > 0.55) / len(values),
        }

    nc1_summary = {name: describe(values) for name, values in nc1.items()}
    for name, entry in nc1_summary.items():
        print(f"   NC1 {name:12s} mean AUROC={entry['mean']:.4f} sd={entry['sd']:.4f} "
              f"[{entry['p2_5']:.4f}, {entry['p97_5']:.4f}]")

    # NC2 -- destroy the alignment between a company and its own temporal block.
    fields = list(feature_sets["families"]["F2"]["fields"])
    temporal_fields = list(feature_sets["families"]["F1"]["fields"])
    temporal_positions = [fields.index(name) for name in temporal_fields]
    matrix = np.asarray(dataset.matrix(fields), dtype=float)
    groups = [dataset.masked_company_id[oid] for oid in dataset.observation_ids]
    controls = config["negative_controls"]
    shuffle_replicates = int(controls["temporal_shuffle_replicates"])
    nc2_targets = [("logistic", "logistic_F2"), ("hist_gb", "hist_gb_F2")]

    def run_nc2(block: np.ndarray, tag: str) -> dict:
        out = {}
        for family, label in nc2_targets:
            result = e4r_models.nested_cv(
                observation_ids=dataset.observation_ids,
                matrix=block.tolist(),
                labels=labels,
                groups=groups,
                feature_names=fields,
                estimator_family=family,
                model_id=f"{label}::{tag}",
                feature_set="F2",
                seed=config["seeds"]["master"],
                n_outer=config["cross_validation"]["outer_splits"],
                n_inner=config["cross_validation"]["inner_splits"],
                reduced_grid=True,
            )
            scores = result.scores_in_order(dataset.observation_ids)
            out[family] = {
                "auroc": e4r_stats.roc_auc(labels, scores),
                "pr_auc": e4r_stats.marginal_metric(
                    e4r_stats.paired_rows(
                        dataset.observation_ids, dataset.labels,
                        {oid: s for oid, s in zip(dataset.observation_ids, scores, strict=True)},
                        {oid: s for oid, s in zip(dataset.observation_ids, scores, strict=True)},
                    ),
                    "reference", "pr_auc",
                ),
                "fit_seconds": round(result.fit_seconds, 3),
            }
        return out

    real = run_nc2(matrix, "real")
    shuffled_runs = []
    shuffle_rng = np.random.default_rng(config["seeds"]["temporal_shuffle"])
    for index in range(shuffle_replicates):
        block = matrix.copy()
        order = shuffle_rng.permutation(block.shape[0])
        block[:, temporal_positions] = block[order][:, temporal_positions]
        shuffled_runs.append(run_nc2(block, f"shuffled_{index}"))
        print(f"   NC2 replicate {index}: logistic={shuffled_runs[-1]['logistic']['auroc']:.4f} "
              f"hist_gb={shuffled_runs[-1]['hist_gb']['auroc']:.4f}")

    nc2_summary = {}
    for family, _label in nc2_targets:
        observed = [entry[family]["auroc"] for entry in shuffled_runs if entry[family]["auroc"] is not None]
        nc2_summary[family] = {
            "real_auroc": real[family]["auroc"],
            "shuffled_replicates": len(observed),
            "shuffled_mean_auroc": sum(observed) / len(observed) if observed else None,
            "shuffled_min_auroc": min(observed) if observed else None,
            "shuffled_max_auroc": max(observed) if observed else None,
            "mean_drop_vs_real": (
                (real[family]["auroc"] - sum(observed) / len(observed)) if observed and real[family]["auroc"] is not None else None
            ),
            "replicates_above_real": (
                sum(1 for value in observed if real[family]["auroc"] is not None and value >= real[family]["auroc"])
                if observed else None
            ),
        }
    payload = {
        "status": e4r_data.STATUS,
        "NC1_label_permutation": {
            "purpose": "sanity check that the pipeline returns to chance under random labels; "
                       "not an equal-AUROC test",
            "replicates": replicates,
            "seed": config["seeds"]["label_permutation"],
            "models": nc1_summary,
        },
        "NC2_temporal_alignment_destroyed": {
            "purpose": "shuffle the temporal block across companies while static features and "
                       "labels stay put; a real temporal contribution should degrade",
            "shuffled_fields": temporal_fields,
            "config": "reduced inner grid, identical for the real and shuffled arms",
            "real": real,
            "replicates": shuffled_runs,
            "summary": nc2_summary,
        },
    }
    _write("negative_controls.json", payload)
    return payload


def stage_calibration_thresholds(dataset: e4r_data.Dataset, score_vectors: dict, config: dict) -> dict:
    print("== stage 13: calibration diagnostics and threshold sensitivity ==")
    labels = [dataset.labels[oid] for oid in dataset.observation_ids]
    focus = ["B0", "B6", "logistic_F2", "hist_gb_F2", "logistic_l2_F2", "random_forest_F2"]
    focus = [name for name in focus if name in score_vectors]
    vectors = {name: [score_vectors[name][oid] for oid in dataset.observation_ids] for name in focus}
    calibration = e4r_analysis.calibration_table(labels, vectors, config["calibration"]["bins"])
    _write("calibration_diagnostics.json", calibration)
    thresholds = e4r_analysis.threshold_table(labels, vectors, config["threshold_grid"])
    _write("threshold_robustness.json", thresholds)
    for name, entry in calibration["models"].items():
        print(f"   {name:18s} Brier={entry['brier']:.4f} ECE={entry['ece']:.4f} "
              f"slope={entry['calibration_slope']:.3f} unique={entry['unique_score_values']}")
    return {"calibration": calibration, "thresholds": thresholds}


def stage_complexity(dataset: e4r_data.Dataset, details: dict, config: dict) -> dict:
    print("== stage 14: cost and complexity ==")
    entries = []
    entries.append({
        "model": "B0",
        "family": "deterministic heuristic",
        "fit_required": False,
        "fit_seconds": 0.0,
        "features_required": len(config and __import__("e4r_data").B0_INPUTS),
        "dependencies": "standard library only",
        "deterministic_reproducibility": "exact: a pure function of the packet, no seed involved",
        "failure_rate": 0.0,
        "llm_cost": None,
    })
    entries.append({
        "model": "B6",
        "family": "deterministic heuristic",
        "fit_required": False,
        "fit_seconds": 0.0,
        "features_required": len(__import__("e4r_data").B0_INPUTS) + len(__import__("e4r_data").B6_TEMPORAL_INPUTS),
        "dependencies": "standard library only",
        "deterministic_reproducibility": "exact: a pure function of the packet, no seed involved",
        "failure_rate": 0.0,
        "llm_cost": None,
    })
    for model_id, entry in sorted(details.items()):
        candidates = max(1, entry["candidates_evaluated"])
        frozen = entry["estimator_family"].startswith("frozen")
        entries.append({
            "model": model_id,
            "family": entry["estimator_family"],
            "fit_required": not frozen,
            "fit_seconds": entry["fit_seconds"],
            "candidates_evaluated": entry["candidates_evaluated"],
            "seconds_per_outer_fold": (
                None if frozen else round(entry["fit_seconds"] / config["cross_validation"]["outer_splits"], 3)
            ),
            "features_required": entry["n_features_requested"],
            "dependencies": "standard library only" if frozen else "numpy, scipy, scikit-learn",
            "deterministic_reproducibility": (
                "exact: a pure function of the packet, no seed involved" if frozen
                else "deterministic under a fixed seed and single-threaded execution"
            ),
            "failure_rate": 0.0 if frozen else (entry["inner_failures"] + entry["outer_failures"]) / candidates,
            "llm_cost": None,
        })
    payload = e4r_analysis.complexity_table(entries)
    payload["environment"] = {
        "python": platform.python_version(),
        "packages": package_versions(["numpy", "scipy", "scikit-learn", "matplotlib", "pytest", "ruff"]),
    }
    payload["note"] = (
        "E4-R compares deterministic heuristics against conventional tabular learners; no LLM "
        "inference is involved, so no token or API cost is attributed to any comparator."
    )
    _write("complexity_comparison.json", payload)
    return payload


def build_manifest(config: dict, feature_sets: dict, integrity: dict, extra: dict) -> dict:
    outputs = [
        "README.md", "STUDY_PROTOCOL.md", "INTERPRETATION_POLICY.md", "experiment_config.json",
        "feature_sets.json", "leakage_audit.json", "oof_predictions.csv", "oof_predictions.json",
        "model_results.json", "temporal_ablation.json", "temporal_contribution_summary.json",
        "subgroup_results.json", "influence_analysis.json", "negative_controls.json",
        "calibration_diagnostics.json", "statistical_tests.json", "complexity_comparison.json",
        "FINAL_REPORT.md",
    ]
    files = []
    for name in outputs:
        path = HERE / name
        files.append(
            {
                "path": f"research/e4r_automated_robustness/{name}",
                "bytes": path.stat().st_size if path.is_file() else None,
                "sha256": e4r_data.sha256_file(path) if path.is_file() else None,
                "present": path.is_file(),
            }
        )
    for path in sorted(FIGURE_DIR.glob("*.svg")):
        files.append(
            {
                "path": f"research/e4r_automated_robustness/figures/{path.name}",
                "bytes": path.stat().st_size,
                "sha256": e4r_data.sha256_file(path),
                "present": True,
            }
        )
    source = []
    manifest = json.loads((e4r_data.REPLICATION_DIR / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        path = REPO_ROOT / entry["path"]
        source.append({"path": entry["path"], "sha256": entry["sha256"], "on_disk_sha256": e4r_data.sha256_file(path)})
    return {
        "experiment_id": "E4-R",
        "status": e4r_data.STATUS,
        "generated_utc": extra["generated_utc"],
        "git_commit": git_commit(),
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "packages": package_versions(["numpy", "scipy", "scikit-learn", "matplotlib", "pytest", "ruff"]),
        "seeds": config["seeds"],
        "config_hash": e4r_data.sha256_json(config),
        "feature_sets_hash": config["feature_sets_hash"],
        "source_artifacts": source,
        "source_integrity": {
            "status": integrity["status"],
            "replication_files_checked": len(integrity["replication_files"]),
            "external_verifier": (integrity.get("external_verifier") or {}).get("status"),
            "b0_reconstruction_max_abs_error": (integrity.get("b0_reconstruction") or {}).get("max_abs_error"),
            "b6_reconstruction_max_abs_error": (integrity.get("b6_reconstruction") or {}).get("max_abs_error"),
        },
        "outputs": files,
        "verification_command": "python research/e4r_automated_robustness/verify_e4r.py",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="2000 bootstrap replicates instead of 20000")
    parser.add_argument("--skip-external-verifier", action="store_true", help="skip the E4-S verifier subprocess")
    parser.add_argument("--skip-models", action="store_true", help="reuse cached model results if present")
    parser.add_argument(
        "--reuse-oof",
        action="store_true",
        help="reload the out-of-fold ledger and model results instead of refitting; the ledger "
             "is the complete record of every score, so downstream stages are unchanged",
    )
    args = parser.parse_args()

    config = e4r_config.assert_config_intact()
    feature_sets = json.loads(e4r_config.FEATURE_SETS_PATH.read_text(encoding="utf-8"))
    bootstrap = 2000 if args.quick else int(config["statistics"]["bootstrap_replicates"])

    started = time.time()
    integrity = stage_integrity(args.skip_external_verifier)
    dataset, reconstruction = stage_dataset()
    integrity["b0_reconstruction"] = {
        "max_abs_error": reconstruction["b0_max_abs_error"], "mismatches": reconstruction["b0_mismatches"]
    }
    integrity["b6_reconstruction"] = {
        "max_abs_error": reconstruction["b6_max_abs_error"], "mismatches": reconstruction["b6_mismatches"]
    }
    leakage = stage_leakage(dataset)

    ablation_vectors, _ablation = stage_ablation(dataset, bootstrap, config["seeds"]["bootstrap"])
    stage_contribution(dataset)

    if args.reuse_oof:
        # The ledger is the complete record of every score the study uses, so reloading it
        # reproduces the downstream stages exactly without paying for the fits again.
        print("== stage 6: reloading the published out-of-fold ledger ==")
        ledger = json.loads((HERE / "oof_predictions.json").read_text(encoding="utf-8"))
        score_vectors = {}
        for row in ledger["records"]:
            score_vectors.setdefault(row["model"], {})[row["observation_id"]] = float(row["predicted_score"])
        # Rewrite both halves of the ledger from its own records so the CSV cannot drift
        # from the JSON it is supposed to mirror.
        write_oof_ledger(ledger["records"], sorted(score_vectors))
        models = {
            "score_vectors": score_vectors,
            "details": json.loads((HERE / "model_results.json").read_text(encoding="utf-8"))["models"],
            "fold_of": {},
        }
    else:
        models = stage_models(dataset, feature_sets, config)
        score_vectors = dict(models["score_vectors"])
        score_vectors.update({key: value for key, value in ablation_vectors.items()})
    fold_of = dict(models["fold_of"])

    details = dict(models["details"])
    labels = [dataset.labels[oid] for oid in dataset.observation_ids]
    if not args.reuse_oof:
        for name, vector in ablation_vectors.items():
            scores = [vector[oid] for oid in dataset.observation_ids]
            details[name] = {
                "model_id": name,
                "estimator_family": "frozen heuristic (ablated)",
                "feature_set": "F2" if name != "B6_no_temporal" else "F0",
                "role": "ablation",
                "n_features_requested": None,
                "prediction_source": "deterministic function, no fitting",
                "fit_seconds": 0.0,
                "candidates_evaluated": 0,
                "inner_failures": 0,
                "outer_failures": 0,
                "selected_params_by_fold": [],
                **(_metrics(labels, scores) if not any(math.isnan(value) for value in scores) else {"auroc": None, "pr_auc": None}),
            }
        stage_oof(dataset, score_vectors, fold_of)

    # B0 and B6 anchor every comparison, so they must appear in the results table whether
    # the scores were refitted or reloaded from the ledger.
    for name in ("B0", "B6"):
        vector = score_vectors[name]
        scores = [vector[oid] for oid in dataset.observation_ids]
        details.setdefault(
            name,
            {
                "model_id": name,
                "estimator_family": "frozen heuristic",
                "feature_set": "F0" if name == "B0" else "F2",
                "role": "reference",
                "n_features_requested": len(feature_sets["families"]["F0" if name == "B0" else "F2"]["fields"]),
                "prediction_source": "deterministic function, no fitting",
                "fit_seconds": 0.0,
                "candidates_evaluated": 0,
                "inner_failures": 0,
                "outer_failures": 0,
                "selected_params_by_fold": [],
                **_metrics(labels, scores),
            },
        )
    _write("model_results.json", {
        "status": e4r_data.STATUS,
        "n": dataset.n,
        "events": dataset.events,
        "prevalence": dataset.events / dataset.n,
        "primary_linear_challenger": "logistic_F2",
        "primary_nonlinear_challenger": "hist_gb_F2",
        "models": details,
    })

    stage_statistics(dataset, score_vectors, config, bootstrap)
    stage_incremental(dataset, feature_sets, config, config["seeds"]["master"])
    subgroups = stage_subgroups(dataset, score_vectors, config, feature_sets)
    stage_influence(dataset, score_vectors, subgroups, config["seeds"]["master"])
    stage_negative_controls(dataset, score_vectors, feature_sets, config,
                                       int(config["negative_controls"]["label_permutation_replicates"]))
    stage_calibration_thresholds(dataset, score_vectors, config)
    stage_complexity(dataset, models["details"], config)

    print("== stage 15: figures and manifest ==")
    import e4r_figures
    import e4r_report

    e4r_figures.render_all(HERE)
    # The manifest is built twice: once so the report can quote the commit and hashes, then
    # again so it can hash the report itself. It never lists itself.
    build = lambda: build_manifest(
        config, feature_sets, integrity, {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    )
    _write("manifest.json", build())
    e4r_report.write_final_report(HERE)
    _write("manifest.json", build())
    print(f"\nE4-R complete in {time.time() - started:.1f}s; status {e4r_data.STATUS}")
    print(f"leakage: {leakage['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
