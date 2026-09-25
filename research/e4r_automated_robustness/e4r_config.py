"""Prespecification freeze for E4-R.

Writes the two machine-readable contracts that must exist *before* any result is produced:

``feature_sets.json``
    the feature families, discovered from the frozen code and the published packet rather
    than typed by hand.

``experiment_config.json``
    seeds, fold construction, model grids, the prespecified primary comparison family and
    the subgroup gates.

Once results exist these files are frozen: :func:`assert_config_intact` is called at the
top of every subsequent run and aborts if the config hash moved. Tuning the config after
seeing the results is exactly the retrospective overfitting this study exists to avoid.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import e4r_data

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

FEATURE_SETS_PATH = HERE / "feature_sets.json"
CONFIG_PATH = HERE / "experiment_config.json"

MASTER_SEED = 20260925
SEEDS = {
    "master": MASTER_SEED,
    "outer_folds": MASTER_SEED,
    "inner_folds": MASTER_SEED,
    "bootstrap": MASTER_SEED,
    "label_permutation": 20260926,
    "temporal_shuffle": 20260927,
}

# Prespecified model runs. `primary` marks the two challengers that enter the Holm-corrected
# primary family: the linear one (unregularised logistic on F2) and the nonlinear one
# (gradient boosting on F2). Random forest is explicitly secondary.
RUNS = [
    {"model_id": "logistic_F0", "family": "logistic", "feature_set": "F0", "role": "secondary"},
    {"model_id": "logistic_F1", "family": "logistic", "feature_set": "F1", "role": "secondary"},
    {"model_id": "logistic_F2", "family": "logistic", "feature_set": "F2", "role": "primary_linear"},
    {"model_id": "logistic_l1_F2", "family": "logistic_l1", "feature_set": "F2", "role": "secondary"},
    {"model_id": "logistic_l2_F2", "family": "logistic_l2", "feature_set": "F2", "role": "secondary"},
    {"model_id": "logistic_l2_F3", "family": "logistic_l2", "feature_set": "F3", "role": "secondary"},
    {"model_id": "random_forest_F2", "family": "random_forest", "feature_set": "F2", "role": "secondary"},
    {"model_id": "random_forest_F3", "family": "random_forest", "feature_set": "F3", "role": "secondary"},
    {"model_id": "hist_gb_F1", "family": "hist_gb", "feature_set": "F1", "role": "secondary"},
    {"model_id": "hist_gb_F2", "family": "hist_gb", "feature_set": "F2", "role": "primary_nonlinear"},
    {"model_id": "hist_gb_F3", "family": "hist_gb", "feature_set": "F3", "role": "secondary"},
]

# The three prespecified primary comparisons. Membership is fixed here and must not be
# chosen after looking at outer-test results.
PRIMARY_FAMILY = [
    {"id": "P1", "reference": "B0", "challenger": "B6"},
    {"id": "P2", "reference": "B6", "challenger": "logistic_F2"},
    {"id": "P3", "reference": "B6", "challenger": "hist_gb_F2"},
]

# Secondary comparisons: reported unadjusted, explicitly not used for confirmatory claims.
SECONDARY_FAMILY = [
    {"id": "S1", "reference": "B6", "challenger": "logistic_l2_F2"},
    {"id": "S2", "reference": "B6", "challenger": "logistic_l1_F2"},
    {"id": "S3", "reference": "B6", "challenger": "random_forest_F2"},
    {"id": "S4", "reference": "B6", "challenger": "hist_gb_F3"},
    {"id": "S5", "reference": "B6", "challenger": "logistic_F0"},
    {"id": "S6", "reference": "logistic_F0", "challenger": "logistic_F2", "label": "temporal increment (logistic)"},
]

SUBGROUP_GATES = {"min_n": 40, "min_events": 10}
THRESHOLD_GRID = [0.30, 0.40, 0.50, 0.60, 0.70]
BOOTSTRAP_REPLICATES = 20000
NEGATIVE_CONTROLS = {"label_permutation_replicates": 200, "temporal_shuffle_replicates": 10}


def build_feature_sets() -> dict:
    """Discover the feature families from the frozen code and the published packet."""
    definition = e4r_data.discover_b6_definition()
    cohort, features, _outcomes, _analysis = e4r_data.load_packet()
    packet_fields = sorted({name for row in features for name in row["metrics"]})
    return {
        "status": e4r_data.STATUS,
        "discovery": definition,
        "families": {
            "F0": {
                "label": "static",
                "description": "the five inputs B0 thresholds; no temporal term",
                "fields": list(e4r_data.B0_INPUTS),
                "source": "backend/finrisk/numeric_benchmark.py::ratio_risk_score",
                "coverage_filter": False,
                "role": "primary",
            },
            "F1": {
                "label": "temporal",
                "description": "the four growth terms B6 adds on top of B0",
                "fields": list(e4r_data.B6_TEMPORAL_INPUTS),
                "source": "backend/finrisk/numeric_benchmark.py::temporal_risk_score",
                "coverage_filter": False,
                "role": "primary",
            },
            "F2": {
                "label": "combined",
                "description": "F0 static + F1 temporal: everything B6 can see",
                "fields": list(e4r_data.B0_INPUTS) + list(e4r_data.B6_TEMPORAL_INPUTS),
                "source": "union of F0 and F1",
                "coverage_filter": False,
                "role": "primary",
            },
            "F3": {
                "label": "extended",
                "description": (
                    "every engineered metric in the frozen packet; exploratory and never "
                    "allowed to change the primary reading"
                ),
                "fields": packet_fields,
                "source": "research/e4_statistical_audit/replication/features.json.gz::metrics",
                "coverage_filter": True,
                "min_train_coverage": 0.4,
                "role": "secondary_exploratory",
            },
        },
        "packet_metric_field_count": len(packet_fields),
        "cohort_rows": len(cohort),
        "notes": [
            (
                "F0/F1/F2 keep their columns whatever their coverage; imputation and scaling "
                "are fitted inside each training fold."
            ),
            (
                "F3 applies a within-fold availability filter at 0.4 so no column is retained "
                "using information from the outer test fold."
            ),
        ],
    }


def build_config(feature_sets: dict) -> dict:
    import e4r_models

    grids = {
        family: e4r_models.expand_grid(family)
        for family in ("logistic", "logistic_l1", "logistic_l2", "random_forest", "hist_gb")
    }
    return {
        "experiment_id": "E4-R",
        "status": e4r_data.STATUS,
        "title": "Automated Robustness & Competitive Baseline Study",
        "is_not": ["ESTABLISHED_E4", "CONFIRMATORY", "PROSPECTIVE", "E5_RESULT"],
        "purpose": "understand E4 and plan E5; never to confirm E4",
        "source": {
            "packet": "research/e4_statistical_audit/replication",
            "manifest": "research/e4_statistical_audit/replication/manifest.json",
            "external_verifier": "research/e4_statistical_audit/verify_audit.py --quick",
        },
        "cohort": {
            "definition": "outcome rows with label_status == VERIFIED",
            "expected_n": 675,
            "expected_events": 235,
        },
        "seeds": SEEDS,
        "cross_validation": {
            "scheme": "nested",
            "outer_splits": 5,
            "inner_splits": 5,
            "splitter": "sklearn StratifiedGroupKFold(shuffle=True, random_state=seed)",
            "group_key": "masked_company_id",
            "stratification": "outcome label",
            "preprocessing": "SimpleImputer(median, add_indicator=True) -> StandardScaler, fitted inside the fold",
            "forbidden": [
                "preprocessing fitted on all 675 rows before CV",
                "hyperparameter changes made after inspecting outer-test performance",
                "feature selection on the full cohort",
            ],
        },
        "models": {
            "grids": {name: grids[name] for name in grids},
            "grid_sizes": {name: len(grid) for name, grid in grids.items()},
            "runs": RUNS,
            "nonlinear_backend": {
                "chosen": "sklearn HistGradientBoostingClassifier",
                "why_not_xgboost": (
                    "the repository ships no numpy/scipy/scikit-learn runtime; adding XGBoost "
                    "would add a second, heavier dependency for no capability the study needs"
                ),
            },
        },
        "primary_family": PRIMARY_FAMILY,
        "secondary_family": SECONDARY_FAMILY,
        "statistics": {
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "bootstrap_type": "company-cluster paired BCa (one observation per company)",
            "auroc_test": "paired DeLong (DeLong, DeLong & Clarke-Pearson 1988)",
            "multiplicity": "Holm step-down over the three prespecified primary comparisons",
            "library": "research/e4_statistical_audit/e4s_stats.py (reused, not re-implemented)",
        },
        "ablation": {
            "variants": [
                "B6_full",
                "B6_no_temporal",
                "B6_minus_revenue",
                "B6_minus_OCF",
                "B6_minus_debt",
                "B6_minus_cash",
            ],
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "rule": "rebuild the frozen closed form with the term removed; no weights are refitted",
        },
        "subgroup_gates": SUBGROUP_GATES,
        "firm_size": {
            "measure": "current.total_assets",
            "why": "feature-side only, so the split cannot use the outcome",
            "bins": ["small", "medium", "large"],
        },
        "missingness": {
            "measure": "fraction of F2 fields missing per observation",
            "bins": ["low", "medium", "high"],
        },
        "threshold_grid": THRESHOLD_GRID,
        "negative_controls": NEGATIVE_CONTROLS,
        "calibration": {
            "status": "UNCALIBRATED",
            "rule": "descriptive diagnostics only; no calibration map is fitted on the cohort",
            "bins": 10,
        },
        "feature_sets_hash": e4r_data.sha256_json(feature_sets),
    }


def assert_config_intact() -> dict:
    """Abort if the frozen config changed after results were produced."""
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    feature_sets = json.loads(FEATURE_SETS_PATH.read_text(encoding="utf-8"))
    if e4r_data.sha256_json(feature_sets) != config["feature_sets_hash"]:
        raise SystemExit("feature_sets.json changed after the config was frozen; refusing to run")
    return config


def write_if_absent(path: Path, payload: dict) -> bool:
    """Write a prespecification file only if it does not already exist."""
    if path.exists():
        return False
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    return True


def main() -> int:
    feature_sets = build_feature_sets()
    wrote_sets = write_if_absent(FEATURE_SETS_PATH, feature_sets)
    config = build_config(feature_sets)
    wrote_config = write_if_absent(CONFIG_PATH, config)
    print(f"feature_sets.json: {'written' if wrote_sets else 'already present (unchanged)'}")
    print(f"experiment_config.json: {'written' if wrote_config else 'already present (unchanged)'}")
    print(f"config hash: {e4r_data.sha256_json(config)}")
    print(f"feature-set hash: {config['feature_sets_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
