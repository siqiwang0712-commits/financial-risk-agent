"""Nested cross-validated tabular baselines for E4-R.

E4-R is a retrospective study, so a single train/test split -- or a grid search scored on
the same rows it reports -- would let hyperparameters absorb the very signal the study is
trying to measure. Everything here therefore runs under nested cross-validation:

    outer (5 company-level stratified folds)
      └── inner (5 stratified folds on the outer training portion only)
             └── pipeline: impute(+missing indicator) -> scale -> estimator

The outer test fold is touched exactly once per model, to produce out-of-fold scores. No
imputation median, no scaling statistic and no selected hyperparameter ever crosses from a
test fold into a training fold.

Feature selection is not performed on the full cohort. The prespecified F0/F1/F2 families
keep their columns whatever their coverage. Only the exploratory F3 (extended) family
applies a *within-fold* availability filter: a column is dropped when fewer than
``min_train_coverage`` of the outer-training rows carry it.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def _pipeline(estimator, add_indicator: bool = True) -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median", add_indicator=add_indicator)),
            ("scale", StandardScaler()),
            ("model", estimator),
        ]
    )


def make_estimator(name: str, seed: int):
    """Instantiate one prespecified estimator family."""
    if name == "logistic":
        return LogisticRegression(penalty=None, solver="lbfgs", max_iter=5000)
    if name == "logistic_l2":
        return LogisticRegression(penalty="l2", solver="lbfgs", max_iter=5000)
    if name == "logistic_l1":
        return LogisticRegression(penalty="l1", solver="liblinear", max_iter=5000)
    if name == "random_forest":
        return RandomForestClassifier(random_state=seed, n_jobs=1)
    if name == "hist_gb":
        return HistGradientBoostingClassifier(random_state=seed, early_stopping=False)
    raise ValueError(f"unknown estimator family {name!r}")


# Prespecified inner-search grids, written into experiment_config.json before the run.
DEFAULT_GRIDS: dict[str, dict[str, list]] = {
    "logistic": {},
    "logistic_l2": {"model__C": [0.01, 0.1, 1.0, 10.0]},
    "logistic_l1": {"model__C": [0.01, 0.1, 1.0, 10.0]},
    "random_forest": {
        "model__n_estimators": [400],
        "model__max_depth": [None, 6],
        "model__min_samples_leaf": [1, 5, 10],
        "model__max_features": ["sqrt", 0.5],
    },
    "hist_gb": {
        "model__learning_rate": [0.05, 0.1],
        "model__max_leaf_nodes": [7, 15, 31],
        "model__min_samples_leaf": [5, 20],
        "model__l2_regularization": [0.0, 1.0],
    },
}

# A deliberately smaller grid used only by the shuffled-temporal negative control, so that
# 10 replicates of the nested loop stay affordable. The control is scored under the same
# reduced config with real and with shuffled temporal columns, so the comparison is fair.
REDUCED_GRIDS: dict[str, dict[str, list]] = {
    "logistic": {},
    "hist_gb": {
        "model__learning_rate": [0.1],
        "model__max_leaf_nodes": [7, 15],
        "model__min_samples_leaf": [20],
        "model__l2_regularization": [1.0],
    },
}


def _product(**named: list) -> list[dict]:
    keys = list(named)
    combos: list[dict] = [{}]
    for key in keys:
        combos = [
            {**existing, key: value} for existing in combos for value in named[key]
        ]
    return combos


def expand_grid(family: str, reduced: bool = False) -> list[dict]:
    """Flatten the prespecified grid into one dict per hyperparameter combination."""
    source = REDUCED_GRIDS if reduced else DEFAULT_GRIDS
    grid = source[family]
    if not grid:
        return [{}]
    return _product(**grid)


@dataclass
class NestedCVResult:
    model_id: str
    estimator_family: str
    feature_set: str
    feature_names: list[str]
    oof_scores: dict[str, float]
    fold_of: dict[str, str]
    selected_params: list[dict] = field(default_factory=list)
    fit_seconds: float = 0.0
    inner_failures: int = 0
    outer_failures: int = 0
    candidates_evaluated: int = 0
    # Audit trail: which rows trained the model that scored each fold, and the imputation
    # medians that fold actually saw. Both let a third party prove the test fold never
    # touched the preprocessing or the fitting.
    train_index_by_fold: dict[str, list[int]] = field(default_factory=dict)
    imputer_medians_by_fold: dict[str, list[float]] = field(default_factory=dict)

    def scores_in_order(self, observation_ids: list[str]) -> list[float]:
        return [self.oof_scores[oid] for oid in observation_ids]


def outer_folds(y: np.ndarray, groups: np.ndarray, n_splits: int, seed: int):
    """Company-level stratified outer folds."""
    splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    return list(splitter.split(np.zeros(len(y)), y, groups))


def _available_columns(matrix: np.ndarray, min_coverage: float) -> list[int]:
    observed = np.sum(~np.isnan(matrix), axis=0) / max(1, matrix.shape[0])
    return [index for index in range(matrix.shape[1]) if observed[index] >= min_coverage]


def nested_cv(
    observation_ids: list[str],
    matrix: list[list[float]],
    labels: list[int],
    groups: list[str],
    feature_names: list[str],
    estimator_family: str,
    model_id: str,
    feature_set: str,
    seed: int = 20260925,
    n_outer: int = 5,
    n_inner: int = 5,
    grid: list[dict] | None = None,
    apply_coverage_filter: bool = False,
    min_train_coverage: float = 0.4,
    reduced_grid: bool = False,
    add_indicator: bool = True,
) -> NestedCVResult:
    """Run the complete nested loop and return out-of-fold scores."""
    X = np.asarray(matrix, dtype=float)
    y = np.asarray(labels, dtype=int)
    group_array = np.asarray(groups, dtype=object)
    grid = grid if grid is not None else expand_grid(estimator_family, reduced=reduced_grid)

    oof: dict[str, float] = {}
    fold_of: dict[str, str] = {}
    train_index_by_fold: dict[str, list[int]] = {}
    imputer_medians_by_fold: dict[str, list[float]] = {}
    selected: list[dict] = []
    inner_failures = 0
    outer_failures = 0
    started = time.perf_counter()

    for fold_index, (train_idx, test_idx) in enumerate(outer_folds(y, group_array, n_outer, seed)):
        keep = (
            _available_columns(X[train_idx], min_train_coverage)
            if apply_coverage_filter
            else list(range(X.shape[1]))
        )
        X_train = X[np.ix_(train_idx, keep)]
        X_test = X[np.ix_(test_idx, keep)]
        y_train = y[train_idx]
        groups_train = group_array[train_idx]

        best_score = float("-inf")
        best_params: dict | None = None
        inner = StratifiedGroupKFold(n_splits=n_inner, shuffle=True, random_state=seed)
        splits = list(inner.split(np.zeros(len(y_train)), y_train, groups_train))
        for params in grid:
            fold_scores: list[float] = []
            for inner_train, inner_test in splits:
                pipe = _pipeline(make_estimator(estimator_family, seed), add_indicator)
                if params:
                    pipe.set_params(**params)
                try:
                    pipe.fit(X_train[inner_train], y_train[inner_train])
                    probabilities = pipe.predict_proba(X_train[inner_test])[:, 1]
                    if len(set(y_train[inner_test])) < 2:
                        continue
                    fold_scores.append(float(roc_auc_score(y_train[inner_test], probabilities)))
                except Exception:  # noqa: BLE001 - a failing candidate is recorded, not hidden
                    inner_failures += 1
            if fold_scores:
                mean_score = sum(fold_scores) / len(fold_scores)
                if mean_score > best_score:
                    best_score = mean_score
                    best_params = params

        train_index_by_fold[str(fold_index)] = [int(index) for index in train_idx]
        entry: dict = {
            "fold": str(fold_index),
            "n_train": len(train_idx),
            "n_test": len(test_idx),
            "n_features_used": len(keep),
        }
        if best_params is None:
            outer_failures += 1
            entry["status"] = "NO_CANDIDATE_SURVIVED"
            selected.append(entry)
            for position in test_idx:
                oof[observation_ids[position]] = float("nan")
                fold_of[observation_ids[position]] = str(fold_index)
            continue

        pipe = _pipeline(make_estimator(estimator_family, seed), add_indicator)
        if best_params:
            pipe.set_params(**best_params)
        try:
            pipe.fit(X_train, y_train)
            scores = pipe.predict_proba(X_test)[:, 1]
        except Exception:  # noqa: BLE001
            outer_failures += 1
            entry["status"] = "OUTER_FIT_FAILED"
            selected.append(entry)
            for position in test_idx:
                oof[observation_ids[position]] = float("nan")
                fold_of[observation_ids[position]] = str(fold_index)
            continue

        entry["status"] = "OK"
        entry["params"] = {str(key): _jsonable(value) for key, value in best_params.items()}
        entry["inner_cv_auroc"] = best_score
        selected.append(entry)
        imputer = pipe.named_steps["impute"]
        imputer_medians_by_fold[str(fold_index)] = [float(value) for value in imputer.statistics_]
        for position, score in zip(test_idx, scores, strict=True):
            oof[observation_ids[position]] = float(score)
            fold_of[observation_ids[position]] = str(fold_index)

    return NestedCVResult(
        model_id=model_id,
        estimator_family=estimator_family,
        feature_set=feature_set,
        feature_names=list(feature_names),
        oof_scores=oof,
        fold_of=fold_of,
        selected_params=selected,
        fit_seconds=time.perf_counter() - started,
        inner_failures=inner_failures,
        outer_failures=outer_failures,
        candidates_evaluated=len(grid) * n_outer * n_inner,
        train_index_by_fold=train_index_by_fold,
        imputer_medians_by_fold=imputer_medians_by_fold,
    )


def _jsonable(value):
    if value is None or isinstance(value, (int, float, str, bool)):
        return value
    return str(value)


def coefficient_stability(
    observation_ids: list[str],
    matrix: list[list[float]],
    labels: list[int],
    groups: list[str],
    feature_names: list[str],
    seed: int = 20260925,
    n_outer: int = 5,
) -> dict:
    """Fit the unregularised logistic model on each outer *training* fold and keep weights.

    These are prediction-time associations fitted on 4/5 of the cohort, not causal effects;
    the summary reports sign consistency and spread across folds, nothing stronger.
    """
    X = np.asarray(matrix, dtype=float)
    y = np.asarray(labels, dtype=int)
    group_array = np.asarray(groups, dtype=object)
    per_feature: dict[str, list[float]] = {name: [] for name in feature_names}
    fold_rows = []
    for fold_index, (train_idx, _test_idx) in enumerate(outer_folds(y, group_array, n_outer, seed)):
        pipe = _pipeline(LogisticRegression(penalty=None, solver="lbfgs", max_iter=5000))
        try:
            pipe.fit(X[train_idx], y[train_idx])
        except Exception:  # noqa: BLE001
            fold_rows.append({"fold": str(fold_index), "status": "FAILED"})
            continue
        weights = pipe.named_steps["model"].coef_[0]
        fold_rows.append(
            {
                "fold": str(fold_index),
                "status": "OK",
                "n_train": len(train_idx),
                "coefficients": {name: float(weights[i]) for i, name in enumerate(feature_names)},
            }
        )
        for index, name in enumerate(feature_names):
            per_feature[name].append(float(weights[index]))
    summary = {}
    for name, values in per_feature.items():
        if not values:
            summary[name] = {"status": "NOT_ESTIMABLE"}
            continue
        positives = sum(1 for value in values if value > 0)
        summary[name] = {
            "folds": len(values),
            "mean": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "positive_folds": positives,
            "sign_consistency": max(positives, len(values) - positives) / len(values),
            "consistent_sign": "positive" if positives * 2 >= len(values) else "negative",
            "values": values,
        }
    return {"folds": fold_rows, "per_feature": summary}
