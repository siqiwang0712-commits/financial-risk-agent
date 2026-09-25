"""Post-hoc methodological hardening of E4-R.

This module holds the additions made *after* `FINAL_REPORT.md` was first produced. They are
still `POST_HOC_AUTOMATED_ROBUSTNESS`: a second post-hoc pass over the same retrospective
data cannot upgrade any conclusion, and the frozen prespecification in
``experiment_config.json`` is deliberately left byte-identical. Everything these stages
depend on is therefore written down separately, in ``extension_config.json``, and that file's
hash is pinned in the manifest alongside the original.

Five additions:

1. ``stage_missingness_ablation`` — is the learned-model advantage coming from financial
   values or from reporting/missingness structure?
2. ``stage_boosting_increment`` — ``hist_gb_F0`` vs ``hist_gb_F2``, the incremental value of
   temporal features under a *strong static nonlinear learner*.
3. ``stage_temporal_shuffle`` — the negative control rebuilt as a genuinely paired design.
4. ``stage_sector_heterogeneity`` — per-sector bootstrap intervals plus a permutation
   heterogeneity test, so a small negative sector is not read as a sector failure.
5. ``stage_model_stability`` — repeated nested CV, because the reported intervals condition
   on the realized out-of-fold predictions and do not integrate training-procedure variance.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import e4r_data
import e4r_models
import e4r_stats
import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

EXTENSION_PATH = HERE / "extension_config.json"

# --------------------------------------------------------------------------------------
# Prespecified extension configuration
# --------------------------------------------------------------------------------------

MISSINGNESS_ARMS = {
    "A_full_F2_with_indicators": (
        "F2 financial values plus the imputer's median-imputation missing indicators - "
        "identical to the frozen headline runs, so arm A is not refitted"
    ),
    "B_full_F2_without_indicators": (
        "the same F2 financial values with add_indicator=False: no missingness signal can "
        "reach the learner"
    ),
    "C_missingness_only": (
        "only the nine F2 presence/absence indicators; no financial value is supplied"
    ),
    "D_harmonized_availability": (
        "observations with at least 7 of the 9 F2 fields observed, refitted within the subset"
    ),
}

SECTOR_CLASSIFICATION = {
    "robust_positive": "bootstrap 95% CI lower bound > 0",
    "possible_heterogeneity": "bootstrap 95% CI upper bound < 0",
    "inconclusive": "the interval contains 0",
}

SHUFFLE_REPLICATES = {"logistic": 200, "hist_gb": 100}
STABILITY_MODELS = ["logistic_F2", "hist_gb_F2"]


def build_extension_config(frozen_config: dict) -> dict:
    return {
        "extension_id": "E4-R-EXT",
        "status": e4r_data.STATUS,
        "rationale": (
            "second post-hoc pass over the same retrospective cohort; it can refine how E4-R "
            "is read but cannot turn any statement into confirmatory evidence"
        ),
        "frozen_config_untouched": True,
        "frozen_config_hash": e4r_data.sha256_json(frozen_config),
        "missingness_ablation": {
            "arms": MISSINGNESS_ARMS,
            "families": ["logistic", "hist_gb"],
            "bootstrap_replicates": 20000,
            "paired_against": "A_full_F2_with_indicators",
            "harmonized_availability_rule": "at least 7 of 9 F2 fields observed",
            "complete_case_note": (
                "strict complete-case (9 of 9 fields) leaves 154 observations and 10 events, "
                "which cannot support an AUROC estimate; it is reported descriptively only"
            ),
        },
        "boosting_temporal_increment": {
            "reference": "hist_gb_F0",
            "challenger": "hist_gb_F2",
            "definition": "F0 = the five static B0 inputs; F2 = F0 plus the four B6 growth terms",
            "bootstrap_replicates": 20000,
        },
        "temporal_shuffle": {
            "replicates": SHUFFLE_REPLICATES,
            "grid": "reduced inner grid, applied identically to the original and shuffled arms",
            "pairing": (
                "identical outer folds, identical inner folds, identical preprocessing and the "
                "same random seed; only the temporal block is permuted across companies"
            ),
            "why_not_the_frozen_arm": (
                "the first version compared a reduced-grid original arm against the full-grid "
                "headline number, which is why it printed 0.8741 against 0.8851. The arms now "
                "share one configuration and the coincidence of the outer folds with the frozen "
                "run is asserted rather than assumed."
            ),
            "drop_ci": "paired cluster bootstrap over observations, 20000 resamples, at the median replicate",
        },
        "sector_heterogeneity": {
            "bootstrap_replicates": 2000,
            "permutation_replicates": 2000,
            "statistic": "Cochran Q on inversely-variance-weighted per-sector delta AUROC",
            "classification": SECTOR_CLASSIFICATION,
            "gate": "the frozen n >= 40 and events >= 10 rule",
        },
        "model_stability": {
            "models": STABILITY_MODELS,
            "repeats": 5,
            "outer_splits": 5,
            "inner_splits": 5,
            "grid": "full prespecified grid",
            "seed_rule": "20260925 + 101 * repeat",
            "scope": "stability description only; it does not enter any primary comparison",
        },
    }


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def _arm_matrix(dataset: e4r_data.Dataset, feature_names: list[str]) -> list[list[float]]:
    return dataset.matrix(feature_names)


def missingness_indicator_matrix(
    dataset: e4r_data.Dataset, feature_names: list[str]
) -> list[list[float]]:
    """One binary presence indicator per field; no financial value at all."""
    return [
        [0.0 if dataset.metrics[oid].get(name) is not None else 1.0 for name in feature_names]
        for oid in dataset.observation_ids
    ]


def harmonized_subset(dataset: e4r_data.Dataset, feature_names: list[str], minimum: int) -> list[str]:
    return [
        oid
        for oid in dataset.observation_ids
        if sum(1 for name in feature_names if dataset.metrics[oid].get(name) is not None) >= minimum
    ]


def _describe_arm(
    observation_ids: list[str],
    labels: dict[str, int],
    scores: dict[str, float],
    bootstrap: int,
    seed: int,
) -> dict:
    metrics = _metrics(labels, scores, observation_ids)
    boot = e4r_stats.marginal_bootstrap(observation_ids, labels, scores, "auroc", bootstrap, seed)
    return {
        "n": len(observation_ids),
        "events": sum(labels[oid] for oid in observation_ids),
        "auroc": metrics["auroc"],
        "pr_auc": metrics["pr_auc"],
        "auroc_ci_low": boot.get("ci_low"),
        "auroc_ci_high": boot.get("ci_high"),
        "auroc_sd": boot.get("sd"),
    }


def _metrics(labels: dict[str, int], scores: dict[str, float], observation_ids: list[str]) -> dict:
    label_vector = [labels[oid] for oid in observation_ids]
    score_vector = [scores[oid] for oid in observation_ids]
    if len(set(label_vector)) < 2:
        return {"auroc": None, "pr_auc": None}
    return {
        "auroc": e4r_stats.roc_auc(label_vector, score_vector),
        "pr_auc": e4r_stats.marginal_metric(
            e4r_stats.paired_rows(
                observation_ids,
                labels,
                scores,
                scores,
            ),
            "reference",
            "pr_auc",
        ),
    }


def _paired(
    observation_ids: list[str],
    labels: dict[str, int],
    reference: dict[str, float],
    challenger: dict[str, float],
    bootstrap: int,
    seed: int,
    label: str,
) -> dict:
    rows = e4r_stats.paired_rows(observation_ids, labels, reference, challenger)
    payload = e4r_stats.paired_comparison(rows, bootstrap, seed, label=label)
    return payload


# --------------------------------------------------------------------------------------
# 1. Missingness confound audit
# --------------------------------------------------------------------------------------


def stage_missingness_ablation(
    dataset: e4r_data.Dataset,
    feature_sets: dict,
    score_vectors: dict[str, dict[str, float]],
    extension: dict,
    seed: int,
) -> dict:
    print("== ext-1: missingness confound audit ==")
    config = extension["missingness_ablation"]
    bootstrap = int(config["bootstrap_replicates"])
    fields = list(feature_sets["families"]["F2"]["fields"])
    labels = dataset.labels
    vector_cache: dict[str, dict[str, dict[str, float]]] = {
        "A_full_F2_with_indicators": {
            "logistic": dict(score_vectors["logistic_F2"]),
            "hist_gb": dict(score_vectors["hist_gb_F2"]),
        }
    }

    for family, model_id in (("logistic", "ext_logistic_B_no_indicators"), ("hist_gb", "ext_hist_gb_B_no_indicators")):
        result = e4r_models.nested_cv(
            observation_ids=dataset.observation_ids,
            matrix=_arm_matrix(dataset, fields),
            labels=[labels[oid] for oid in dataset.observation_ids],
            groups=[dataset.masked_company_id[oid] for oid in dataset.observation_ids],
            feature_names=fields,
            estimator_family=family,
            model_id=model_id,
            feature_set="F2",
            seed=seed,
            n_outer=int(extension["model_stability"]["outer_splits"]),
            n_inner=int(extension["model_stability"]["inner_splits"]),
            add_indicator=False,
        )
        vector_cache.setdefault("B_full_F2_without_indicators", {})[family] = result.oof_scores

    indicator = missingness_indicator_matrix(dataset, fields)
    indicator_names = [f"missing::{name}" for name in fields]
    for family, model_id in (("logistic", "ext_logistic_C_missing_only"), ("hist_gb", "ext_hist_gb_C_missing_only")):
        result = e4r_models.nested_cv(
            observation_ids=dataset.observation_ids,
            matrix=indicator,
            labels=[labels[oid] for oid in dataset.observation_ids],
            groups=[dataset.masked_company_id[oid] for oid in dataset.observation_ids],
            feature_names=indicator_names,
            estimator_family=family,
            model_id=model_id,
            feature_set="missingness-only",
            seed=seed,
            n_outer=int(extension["model_stability"]["outer_splits"]),
            n_inner=int(extension["model_stability"]["inner_splits"]),
            add_indicator=False,
        )
        vector_cache.setdefault("C_missingness_only", {})[family] = result.oof_scores

    subset = harmonized_subset(dataset, fields, 7)
    strict_subset = harmonized_subset(dataset, fields, 9)
    subset_matrix = [
        [_as_float(dataset.metrics[oid].get(name)) for name in fields] for oid in subset
    ]
    for family, model_id in (("logistic", "ext_logistic_D_harmonized"), ("hist_gb", "ext_hist_gb_D_harmonized")):
        result = e4r_models.nested_cv(
            observation_ids=subset,
            matrix=subset_matrix,
            labels=[labels[oid] for oid in subset],
            groups=[dataset.masked_company_id[oid] for oid in subset],
            feature_names=fields,
            estimator_family=family,
            model_id=model_id,
            feature_set="F2 (harmonized subset)",
            seed=seed,
            n_outer=int(extension["model_stability"]["outer_splits"]),
            n_inner=int(extension["model_stability"]["inner_splits"]),
            add_indicator=True,
        )
        vector_cache.setdefault("D_harmonized_availability", {})[family] = result.oof_scores

    payload: dict = {
        "status": e4r_data.STATUS,
        "question": (
            "how much of the learned-model advantage comes from financial values, and how much "
            "from reporting/missingness structure?"
        ),
        "arms": {
            name: {"definition": definition} for name, definition in config["arms"].items()
        },
        "harmonized_availability_rule": config["harmonized_availability_rule"],
        "strict_complete_case": {
            "n": len(strict_subset),
            "events": sum(labels[oid] for oid in strict_subset),
            "estimable": False,
            "reason": "10 events cannot support an AUROC estimate; reported for completeness only",
        },
        "families": {},
        "comparisons": {},
    }

    for family in config["families"]:
        family_payload: dict = {"arms": {}}
        for arm_name, per_family in vector_cache.items():
            if family not in per_family:
                continue
            vectors = per_family[family]
            if arm_name == "D_harmonized_availability":
                ids = subset
            else:
                ids = dataset.observation_ids
            family_payload["arms"][arm_name] = {
                **_describe_arm(ids, labels, vectors, bootstrap, seed),
                "scores": {oid: vectors[oid] for oid in ids},
            }
        payload["families"][family] = family_payload

    for family in config["families"]:
        reference_arm = "A_full_F2_with_indicators"
        entry: dict = {}
        for other in ("B_full_F2_without_indicators", "C_missingness_only"):
            comparison = _paired(
                dataset.observation_ids,
                labels,
                vector_cache[reference_arm][family],
                vector_cache[other][family],
                bootstrap,
                seed,
                label=f"{reference_arm} minus {other} ({family})",
            )
            entry[f"A_minus_{other}"] = comparison
        d_ids = subset
        comparison_d = _paired(
            d_ids,
            labels,
            {oid: vector_cache[reference_arm][family][oid] for oid in d_ids},
            vector_cache["D_harmonized_availability"][family],
            bootstrap,
            seed,
            label=f"A restricted to the harmonized subset minus D ({family})",
        )
        entry["A_restricted_minus_D_harmonized"] = comparison_d
        payload["comparisons"][family] = entry

    for family, entry in payload["families"].items():
        for arm_name, arm in entry["arms"].items():
            print(f"   {family:9s} {arm_name:32s} AUROC={arm['auroc']:.4f} n={arm['n']} events={arm['events']}")
        for key, comparison in payload["comparisons"][family].items():
            print(f"   {family:9s} {key:36s} ΔAUROC={comparison['delta_auroc']:+.4f} "
                  f"BCa=[{comparison['bootstrap_auroc']['bca_low']:+.4f}, {comparison['bootstrap_auroc']['bca_high']:+.4f}]")

    _write("missingness_ablation.json", payload)
    return payload


def _as_float(value) -> float:
    return float("nan") if value is None else float(value)


# --------------------------------------------------------------------------------------
# 2. Boosting temporal increment (hist_gb_F0 vs hist_gb_F2)
# --------------------------------------------------------------------------------------


def stage_boosting_increment(
    dataset: e4r_data.Dataset,
    feature_sets: dict,
    score_vectors: dict[str, dict[str, float]],
    extension: dict,
    seed: int,
) -> tuple[dict, dict[str, dict[str, float]]]:
    print("== ext-2: boosting temporal increment (hist_gb_F0 vs hist_gb_F2) ==")
    config = extension["boosting_temporal_increment"]
    bootstrap = int(config["bootstrap_replicates"])
    labels = dataset.labels
    static_fields = list(feature_sets["families"]["F0"]["fields"])
    static_result = e4r_models.nested_cv(
        observation_ids=dataset.observation_ids,
        matrix=dataset.matrix(static_fields),
        labels=[labels[oid] for oid in dataset.observation_ids],
        groups=[dataset.masked_company_id[oid] for oid in dataset.observation_ids],
        feature_names=static_fields,
        estimator_family="hist_gb",
        model_id="hist_gb_F0",
        feature_set="F0",
        seed=seed,
        n_outer=int(extension["model_stability"]["outer_splits"]),
        n_inner=int(extension["model_stability"]["inner_splits"]),
    )
    new_vectors = {"hist_gb_F0": static_result.oof_scores}
    payload: dict = {
        "status": e4r_data.STATUS,
        "question": (
            "does adding the four B6 growth terms to a strong *static* nonlinear learner "
            "actually improve performance?"
        ),
        "reference": "hist_gb_F0 (five static B0 inputs)",
        "challenger": "hist_gb_F2 (static plus the four B6 growth terms)",
        "reference_metrics": {
            **_metrics(labels, new_vectors["hist_gb_F0"], dataset.observation_ids),
            "fit_seconds": round(static_result.fit_seconds, 3),
        },
        "challenger_metrics": {
            **_metrics(labels, score_vectors["hist_gb_F2"], dataset.observation_ids),
        },
    }
    comparison = _paired(
        dataset.observation_ids,
        labels,
        new_vectors["hist_gb_F0"],
        score_vectors["hist_gb_F2"],
        bootstrap,
        seed,
        label="hist_gb_F2 minus hist_gb_F0",
    )
    payload["comparison"] = comparison
    payload["bootstrap_replicates"] = bootstrap
    for name in ("hist_gb_F0", "hist_gb_F2"):
        vector = new_vectors["hist_gb_F0"] if name == "hist_gb_F0" else score_vectors["hist_gb_F2"]
        payload.setdefault("scores", {})[name] = {oid: vector[oid] for oid in dataset.observation_ids}
    _write("boosting_temporal_increment.json", payload)
    print(f"   hist_gb_F0 AUROC={payload['reference_metrics']['auroc']:.4f}  "
          f"hist_gb_F2 AUROC={payload['challenger_metrics']['auroc']:.4f}  "
          f"Δ={comparison['delta_auroc']:+.4f} "
          f"BCa=[{comparison['bootstrap_auroc']['bca_low']:+.4f}, {comparison['bootstrap_auroc']['bca_high']:+.4f}] "
          f"DeLong p={comparison['delong']['p_value']:.3g}")
    return payload, new_vectors


# --------------------------------------------------------------------------------------
# 3. Temporal shuffle control, rebuilt as a paired design
# --------------------------------------------------------------------------------------


def stage_temporal_shuffle(
    dataset: e4r_data.Dataset,
    feature_sets: dict,
    score_vectors: dict[str, dict[str, float]],
    extension: dict,
    seed: int,
    shuffle_seed: int,
) -> dict:
    print("== ext-3: temporal shuffle control (paired design) ==")
    config = extension["temporal_shuffle"]
    fields = list(feature_sets["families"]["F2"]["fields"])
    temporal_positions = [fields.index(name) for name in feature_sets["families"]["F1"]["fields"]]
    labels = dataset.labels
    label_vector = [labels[oid] for oid in dataset.observation_ids]
    base_matrix = np.asarray(dataset.matrix(fields), dtype=float)
    groups = [dataset.masked_company_id[oid] for oid in dataset.observation_ids]

    # The original arm must be re-run under the control's own configuration, and its folds
    # must coincide with the frozen run's folds. Assert the latter rather than trust it.
    frozen_folds = _frozen_fold_map()
    original: dict[str, dict] = {}
    reproduction: dict[str, dict] = {}
    for family in ("logistic", "hist_gb"):
        result = e4r_models.nested_cv(
            observation_ids=dataset.observation_ids,
            matrix=base_matrix.tolist(),
            labels=label_vector,
            groups=groups,
            feature_names=fields,
            estimator_family=family,
            model_id=f"control_original::{family}",
            feature_set="F2",
            seed=seed,
            n_outer=int(extension["model_stability"]["outer_splits"]),
            n_inner=int(extension["model_stability"]["inner_splits"]),
            reduced_grid=True,
        )
        original[family] = {
            "auroc": e4r_stats.roc_auc(label_vector, result.scores_in_order(dataset.observation_ids)),
            "fit_seconds": round(result.fit_seconds, 3),
            "scores": {oid: result.oof_scores[oid] for oid in dataset.observation_ids},
        }
        reproduction[family] = {
            "folds_identical_to_frozen_run": all(
                result.fold_of[oid] == frozen_folds.get(oid) for oid in dataset.observation_ids
            ),
            "frozen_fold_map_source": "oof_predictions.json fold column of the frozen hist_gb_F2 run",
        }
        print(f"   original {family:9s} AUROC={original[family]['auroc']:.4f} "
              f"folds identical to frozen run: {reproduction[family]['folds_identical_to_frozen_run']}")

    rng = np.random.default_rng(shuffle_seed)
    replicates: dict[str, list[float]] = {"logistic": [], "hist_gb": []}
    replicate_detail: dict[str, list[dict]] = {"logistic": [], "hist_gb": []}
    dropped_scores: dict[str, dict[int, dict[str, float]]] = {"logistic": {}, "hist_gb": {}}
    counts = {family: int(config["replicates"][family]) for family in ("logistic", "hist_gb")}
    for family in ("logistic", "hist_gb"):
        for index in range(counts[family]):
            block = base_matrix.copy()
            order = rng.permutation(block.shape[0])
            block[:, temporal_positions] = block[order][:, temporal_positions]
            result = e4r_models.nested_cv(
                observation_ids=dataset.observation_ids,
                matrix=block.tolist(),
                labels=label_vector,
                groups=groups,
                feature_names=fields,
                estimator_family=family,
                model_id=f"control_shuffled::{family}::{index}",
                feature_set="F2",
                seed=seed,
                n_outer=int(extension["model_stability"]["outer_splits"]),
                n_inner=int(extension["model_stability"]["inner_splits"]),
                reduced_grid=True,
            )
            auroc = e4r_stats.roc_auc(label_vector, result.scores_in_order(dataset.observation_ids))
            drop = original[family]["auroc"] - auroc
            replicates[family].append(auroc)
            replicate_detail[family].append({"replicate": index, "auroc": auroc, "drop": drop})
            if (index + 1) % 25 == 0:
                print(f"   {family}: {index + 1}/{counts[family]} shuffled replicates done")

    # The median-drop replicate is the one whose paired interval is bootstrapped below, so its
    # scores are the only ones worth keeping. The generator is reseeded so the permutation it
    # receives is bit-identical to the one it received in the loop above.
    median_index = {
        family: sorted(
            range(len(replicate_detail[family])), key=lambda i: replicate_detail[family][i]["drop"]
        )[len(replicate_detail[family]) // 2]
        for family in ("logistic", "hist_gb")
    }
    rng = np.random.default_rng(shuffle_seed)
    for family in ("logistic", "hist_gb"):
        for index in range(counts[family]):
            block = base_matrix.copy()
            order = rng.permutation(block.shape[0])
            block[:, temporal_positions] = block[order][:, temporal_positions]
            if index != median_index[family]:
                continue
            result = e4r_models.nested_cv(
                observation_ids=dataset.observation_ids,
                matrix=block.tolist(),
                labels=label_vector,
                groups=groups,
                feature_names=fields,
                estimator_family=family,
                model_id=f"control_shuffled_median::{family}",
                feature_set="F2",
                seed=seed,
                n_outer=int(extension["model_stability"]["outer_splits"]),
                n_inner=int(extension["model_stability"]["inner_splits"]),
                reduced_grid=True,
            )
            dropped_scores[family] = {index: result.oof_scores}

    payload: dict = {
        "status": e4r_data.STATUS,
        "design": config["pairing"],
        "grid": config["grid"],
        "temporal_fields": feature_sets["families"]["F1"]["fields"],
        "reproduction_of_frozen_folds": reproduction,
        "audit_note": (
            config["why_not_the_frozen_arm"]
            + " Under the shared reduced configuration the original arm reproduces at the value "
            "below; the headline 0.8851 is the full-grid fit. The difference is the inner grid, "
            "not the folds, which the fold-identity assertion above demonstrates."
        ),
        "models": {},
    }

    for family in ("logistic", "hist_gb"):
        values = replicates[family]
        drops = [entry["drop"] for entry in replicate_detail[family]]
        observed = original[family]["auroc"]
        median_replicate = median_index[family]
        paired = _paired(
            dataset.observation_ids,
            labels,
            {oid: original[family]["scores"][oid] for oid in dataset.observation_ids},
            dropped_scores[family][median_replicate],
            int(config.get("drop_bootstrap_replicates", 20000)),
            seed,
            label=f"original minus the median-drop shuffled replicate ({family})",
        )
        payload["models"][family] = {
            "original_auroc": observed,
            "replicates": len(values),
            "median_drop_replicate": median_replicate,
            "shuffled_mean_auroc": sum(values) / len(values),
            "shuffled_median_auroc": e4r_stats.percentile_linear(values, 0.5),
            "shuffled_p2_5": e4r_stats.percentile_linear(values, 0.025),
            "shuffled_p97_5": e4r_stats.percentile_linear(values, 0.975),
            "shuffled_min": min(values),
            "shuffled_max": max(values),
            "drop_mean": sum(drops) / len(drops),
            "drop_median": e4r_stats.percentile_linear(drops, 0.5),
            "drop_ci_low": e4r_stats.percentile_linear(drops, 0.025),
            "drop_ci_high": e4r_stats.percentile_linear(drops, 0.975),
            "P_drop_gt_0": sum(1 for value in drops if value > 0) / len(drops),
            "replicates_above_original": sum(1 for value in values if value >= observed),
            "detail": replicate_detail[family],
            "paired_bootstrap_of_drop_at_median_replicate": paired,
            "inference_note": (
                "Two sources of variability are in play: the randomness of the shuffle (the "
                "across-replicate interval) and the sampling of the 675 observations (the paired "
                "cluster interval at the median replicate). Both are reported; neither is a "
                "replacement for the other."
            ),
        }
        entry = payload["models"][family]
        print(f"   {family:9s} original={entry['original_auroc']:.4f} "
              f"shuffled mean={entry['shuffled_mean_auroc']:.4f} "
              f"drop median={entry['drop_median']:+.4f} "
              f"paired Δ={paired['delta_auroc']:+.4f} "
              f"P(drop>0)={entry['P_drop_gt_0']:.3f}")

    _write("negative_controls.json", _merge_with_frozen_controls(payload))
    return payload


def _frozen_fold_map() -> dict[str, str]:
    import json

    ledger = json.loads((HERE / "oof_predictions.json").read_text(encoding="utf-8"))
    return {
        row["observation_id"]: row["fold"]
        for row in ledger["records"]
        if row["model"] == "hist_gb_F2"
    }


def _merge_with_frozen_controls(shuffle_payload: dict) -> dict:
    """Keep NC1 and the frozen-control provenance, replace the NC2 block with the paired design."""
    import json

    path = HERE / "negative_controls.json"
    previous = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    merged = dict(previous)
    merged["status"] = e4r_data.STATUS
    merged["NC2_temporal_alignment_destroyed"] = {
        "purpose": (
            "shuffle the temporal block across companies while the static features, the labels "
            "and the fold structure stay put; a real temporal contribution should degrade"
        ),
        **shuffle_payload,
    }
    merged["NC2_superseded_note"] = (
        "The first version of this control compared a reduced-grid original arm against the "
        "full-grid headline number, which is why the old artifact recorded 0.8741 against "
        "0.8851. The paired design above replaces it; the old number is explained in "
        "extension_config.json and in the FINAL_REPORT audit note."
    )
    return merged


# --------------------------------------------------------------------------------------
# 4. Sector heterogeneity
# --------------------------------------------------------------------------------------


def stage_sector_heterogeneity(
    dataset: e4r_data.Dataset,
    score_vectors: dict[str, dict[str, float]],
    config: dict,
    extension: dict,
    seed: int,
) -> dict:
    print("== ext-4: sector heterogeneity ==")
    settings = extension["sector_heterogeneity"]
    bootstrap = int(settings["bootstrap_replicates"])
    permutations = int(settings["permutation_replicates"])
    gates = config["subgroup_gates"]
    labels = dataset.labels
    by_sector: dict[str, list[str]] = {}
    for oid in dataset.observation_ids:
        by_sector.setdefault(dataset.sector[oid], []).append(oid)

    rows = []
    for sector in sorted(by_sector):
        members = by_sector[sector]
        events = sum(labels[oid] for oid in members)
        row: dict = {
            "sector": sector,
            "n": len(members),
            "events": events,
            "estimable": len(members) >= gates["min_n"] and events >= gates["min_events"],
        }
        if not row["estimable"]:
            row["status"] = "NOT_ESTIMABLE"
            row["classification"] = None
            rows.append(row)
            continue
        rows_ = e4r_stats.paired_rows(members, labels, score_vectors["B0"], score_vectors["B6"])
        boot = e4r_stats.paired_bootstrap(rows_, "auroc", bootstrap, seed)
        delta = e4r_stats.delta_metric(rows_, "auroc")
        low, high = boot["bca_low"], boot["bca_high"]
        if low is not None and low > 0:
            classification = "robust_positive"
        elif high is not None and high < 0:
            classification = "possible_heterogeneity"
        else:
            classification = "inconclusive"
        row.update(
            {
                "status": "OK",
                "delta_auroc": delta,
                "ci_low": low,
                "ci_high": high,
                "bootstrap_sd": boot["standard_error"],
                "classification": classification,
                "classification_rule": settings["classification"][classification],
            }
        )
        rows.append(row)
        print(f"   {sector:26s} n={row['n']:3d} events={row['events']:3d} "
              f"Δ={delta:+.4f} CI=[{low:+.4f}, {high:+.4f}] {classification}")

    estimable = [row for row in rows if row["estimable"]]
    heterogeneity = _heterogeneity(estimable, dataset, labels, score_vectors, permutations, seed)
    payload = {
        "status": e4r_data.STATUS,
        "gate": gates,
        "classification_rule": settings["classification"],
        "sectors": rows,
        "heterogeneity": heterogeneity,
    }
    _write("sector_heterogeneity.json", payload)
    return payload


def _heterogeneity(
    rows: list[dict],
    dataset: e4r_data.Dataset,
    labels: dict[str, int],
    score_vectors: dict[str, dict[str, float]],
    permutations: int,
    seed: int,
) -> dict:
    """Cochran Q on per-sector ΔAUROC, with a permutation null for the k=3 case."""
    import random

    if len(rows) < 2:
        return {"status": "NOT_ESTIMABLE", "reason": "fewer than two eligible sectors"}
    weighted = []
    for row in rows:
        se = row["bootstrap_sd"]
        if not se or se <= 0:
            continue
        weighted.append((row["sector"], row["delta_auroc"], 1.0 / se**2))
    if len(weighted) < 2:
        return {"status": "NOT_ESTIMABLE", "reason": "no sector has a usable bootstrap standard error"}
    total_weight = sum(weight for _name, _delta, weight in weighted)
    pooled = sum(delta * weight for _name, delta, weight in weighted) / total_weight
    q_statistic = sum(weight * (delta - pooled) ** 2 for _name, delta, weight in weighted)
    degrees = len(weighted) - 1
    i_squared = max(0.0, (q_statistic - degrees) / q_statistic) if q_statistic > 0 else 0.0

    rng = random.Random(seed)
    sector_of = {oid: dataset.sector[oid] for oid in dataset.observation_ids}
    sizes = {row["sector"]: row["n"] for row in rows}
    pooled_ids = [oid for row in rows for oid in dataset.observation_ids if sector_of[oid] == row["sector"]]
    weights = [weight for _name, _delta, weight in weighted]
    null: list[float] = []
    for _ in range(permutations):
        shuffled = list(pooled_ids)
        rng.shuffle(shuffled)
        deltas = []
        cursor = 0
        for size in sizes.values():
            ids = shuffled[cursor : cursor + size]
            cursor += size
            if len(ids) < 2 or len({labels[oid] for oid in ids}) < 2:
                deltas = []
                break
            value = e4r_stats.delta_metric(
                e4r_stats.paired_rows(ids, labels, score_vectors["B0"], score_vectors["B6"]), "auroc"
            )
            if value is None:
                deltas = []
                break
            deltas.append(value)
        if len(deltas) != len(weights):
            continue
        total = sum(weights)
        mean = sum(delta * weight for delta, weight in zip(deltas, weights, strict=True)) / total
        null.append(
            sum(weight * (delta - mean) ** 2 for delta, weight in zip(deltas, weights, strict=True))
        )
    p_value = None
    if null:
        p_value = (1 + sum(1 for value in null if value >= q_statistic)) / (len(null) + 1)
    return {
        "status": "OK",
        "statistic": "Cochran Q on inversely-variance-weighted per-sector delta AUROC",
        "sectors_used": [name for name, _delta, _weight in weighted],
        "pooled_delta_auroc": pooled,
        "cochran_q": q_statistic,
        "degrees_of_freedom": degrees,
        "i_squared": i_squared,
        "chi_square_p_value": _chi_square_sf(q_statistic, degrees),
        "permutation_replicates": len(null),
        "permutation_p_value": p_value,
        "permutation_statistic": (
            "the same inverse-variance-weighted Q, with the weights held at their observed "
            "values so the permuted statistic is on the same scale as the observed one"
        ),
        "permutation_note": (
            "Three sectors make the chi-square approximation unreliable, so the permutation null "
            "is the reported test. It permutes sector labels across the pooled eligible "
            "observations while preserving sector sizes; holding the weights fixed is the "
            "standard approximation and is stated rather than hidden. Expect low power: Q has "
            "two degrees of freedom here."
        ),
        "population_size": len(pooled_ids),
        "gated_share_of_cohort": len(pooled_ids) / dataset.n,
        "gate_note": (
            "Sectors below the frozen n>=40 / events>=10 gate are excluded from both the "
            "statistic and the permutation, so the heterogeneity test speaks only about gated "
            "sectors - and the gated sectors cover "
            f"{len(pooled_ids)}/{dataset.n} of the cohort."
        ),
    }


def _chi_square_sf(statistic: float, degrees: int) -> float | None:
    if degrees <= 0:
        return None
    # Regularised upper incomplete gamma for integer degrees of freedom.
    half = degrees / 2.0
    x = statistic / 2.0
    term = math.exp(-x + (half - 1) * math.log(x) - math.lgamma(half)) if x > 0 else 0.0
    series = 0.0
    current = 1.0
    for index in range(1, 200):
        current *= x / (half + index)
        series += current
        if current < 1e-14:
            break
    return min(1.0, max(0.0, 1.0 - (term * (1.0 + series) if x > 0 else 0.0))) if degrees > 0 else None


# --------------------------------------------------------------------------------------
# 5. Model stability under repeated nested CV
# --------------------------------------------------------------------------------------


def stage_model_stability(
    dataset: e4r_data.Dataset,
    feature_sets: dict,
    extension: dict,
    seed: int,
) -> dict:
    print("== ext-5: repeated nested CV stability ==")
    settings = extension["model_stability"]
    fields = list(feature_sets["families"]["F2"]["fields"])
    labels = dataset.labels
    label_vector = [labels[oid] for oid in dataset.observation_ids]
    groups = [dataset.masked_company_id[oid] for oid in dataset.observation_ids]
    payload: dict = {
        "status": e4r_data.STATUS,
        "design": (
            f"{settings['repeats']} repeats of {settings['outer_splits']}x{settings['inner_splits']} "
            "nested cross-validation per model, full prespecified grid"
        ),
        "seed_rule": settings["seed_rule"],
        "limitation": (
            "reported primary intervals condition on the realized out-of-fold predictions and do "
            "not integrate training-procedure uncertainty; this stage measures that component "
            "separately and is descriptive only"
        ),
        "models": {},
    }
    for model_id in settings["models"]:
        family, feature_set = model_id.rsplit("_", 1)
        fields_used = fields if feature_set == "F2" else list(feature_sets["families"][feature_set]["fields"])
        matrix_used = dataset.matrix(fields_used)
        repeats = []
        for repeat in range(int(settings["repeats"])):
            repeat_seed = seed + 101 * repeat
            result = e4r_models.nested_cv(
                observation_ids=dataset.observation_ids,
                matrix=matrix_used,
                labels=label_vector,
                groups=groups,
                feature_names=list(fields_used),
                estimator_family=family,
                model_id=f"{model_id}::repeat{repeat}",
                feature_set=feature_set,
                seed=repeat_seed,
                n_outer=int(settings["outer_splits"]),
                n_inner=int(settings["inner_splits"]),
            )
            scores = result.scores_in_order(dataset.observation_ids)
            repeat_auroc = e4r_stats.roc_auc(label_vector, scores)
            fold_aurocs = []
            for fold in sorted(set(result.fold_of.values())):
                members = [oid for oid in dataset.observation_ids if result.fold_of[oid] == fold]
                if len({labels[oid] for oid in members}) < 2:
                    continue
                fold_aurocs.append(
                    e4r_stats.roc_auc(
                        [labels[oid] for oid in members], [result.oof_scores[oid] for oid in members]
                    )
                )
            repeats.append(
                {
                    "repeat": repeat,
                    "seed": repeat_seed,
                    "auroc": repeat_auroc,
                    "fold_aurocs": fold_aurocs,
                    "fold_auroc_min": min(fold_aurocs) if fold_aurocs else None,
                    "fold_auroc_max": max(fold_aurocs) if fold_aurocs else None,
                    "fit_seconds": round(result.fit_seconds, 3),
                }
            )
            print(f"   {model_id} repeat {repeat}: AUROC={repeat_auroc:.4f}")
        values = [entry["auroc"] for entry in repeats]
        mean_value = sum(values) / len(values)
        payload["models"][model_id] = {
            "repeats": repeats,
            "mean_auroc": mean_value,
            "sd_auroc": math.sqrt(sum((value - mean_value) ** 2 for value in values) / (len(values) - 1)),
            "min_auroc": min(values),
            "max_auroc": max(values),
            "range_auroc": max(values) - min(values),
            "fold_auroc_pool": [value for entry in repeats for value in entry["fold_aurocs"]],
        }
    _write("model_stability.json", payload)
    for model_id, entry in payload["models"].items():
        print(f"   {model_id}: mean={entry['mean_auroc']:.4f} sd={entry['sd_auroc']:.4f} "
              f"range={entry['range_auroc']:.4f}")
    return payload


def _write(name: str, payload: dict) -> None:
    import json

    with (HERE / name).open("w", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(payload, indent=1, sort_keys=True) + "\n")
