"""B6 temporal ablation, rebuilt from the frozen formula rather than re-fitted.

B6 is a deterministic score, not a trained model:

    B6 = min(1, 0.75 * B0 + 0.25 * (adverse / observed))

where ``B0`` is ``ratio_risk_score`` and ``adverse / observed`` counts how many of the four
growth terms that are *present* breach their fixed adverse thresholds. Because B6 has no
fitted weights, an ablation is a re-evaluation of the same closed-form expression with a
term removed -- there is nothing to retrain and nothing to re-tune.

Two structural facts drive the interpretation, and both are reported rather than hidden:

* removing *all* temporal terms leaves ``0.75 * B0``. Since ``B0`` lies in [0, 1], that is
  a strictly increasing map of ``B0``, so ``AUROC(B6-no-temporal)`` equals
  ``AUROC(B0)`` **exactly**. The ablation cannot be "partly better than B0"; it is B0.
* dropping a term changes ``observed`` as well as ``adverse``, so the four
  leave-one-out scores are not a decomposition of B6 into additive parts. They are four
  distinct counterfactual scores.

All four temporal term names and their thresholds are read from the frozen code object
(:func:`e4r_data.discover_b6_definition`) and cross-checked against the expected list.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
for _path in (str(REPO_ROOT / "backend"), str(HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import e4r_data
from finrisk.numeric_benchmark import (
    ratio_risk_score,
    temporal_risk_score,
)


def _predicate(comparator: str, threshold: float):
    import operator

    table = {
        "<": operator.lt,
        "<=": operator.le,
        ">": operator.gt,
        ">=": operator.ge,
        "==": operator.eq,
        "!=": operator.ne,
    }
    if comparator not in table:
        raise ValueError(f"unsupported comparator {comparator!r} read from the frozen code")
    compare = table[comparator]
    return lambda value: compare(value, threshold)


def _build_terms() -> tuple[tuple[str, object, str], ...]:
    """Read the temporal rules out of the frozen code object; never re-type them."""
    definition = e4r_data.discover_b6_definition()
    if not definition["b6_temporal_inputs_match_expected"]:
        raise RuntimeError(
            "the frozen temporal_risk_score no longer uses the expected four growth terms; "
            "the ablation must be re-specified before it is run"
        )
    labels = {
        "revenue_growth": "revenue",
        "operating_cash_flow_growth": "OCF",
        "total_debt_growth": "debt",
        "cash_growth": "cash",
    }
    terms = []
    for index, name in enumerate(definition["b6_temporal_inputs_from_code"]):
        rule = definition["b6_thresholds_from_code"][name]
        terms.append((name, _predicate(rule["comparator"], rule["threshold"]), labels[name]))
    return tuple(terms)


TEMPORAL_TERMS: tuple[tuple[str, object, str], ...] = _build_terms()

TERM_LABELS = {name: label for name, _, label in TEMPORAL_TERMS}
TERM_NAMES = tuple(name for name, _, _ in TEMPORAL_TERMS)


def b6_components(metrics: dict) -> tuple[float | None, int, int, dict[str, int | None]]:
    """Return (base, adverse, observed, per-term trigger) for one observation."""
    base = ratio_risk_score(metrics)
    adverse = 0
    observed = 0
    triggers: dict[str, int | None] = {}
    for name, test, _label in TEMPORAL_TERMS:
        value = metrics.get(name)
        if value is None:
            triggers[name] = None
            continue
        observed += 1
        hit = int(test(value))
        adverse += hit
        triggers[name] = hit
    return base, adverse, observed, triggers


def b6_score_with(metrics: dict, drop: str | None = None, temporal_only: bool = False) -> float | None:
    """Evaluate B6's closed form, optionally omitting one temporal term or all of them.

    ``drop=None`` reproduces the frozen score; ``temporal_only=True`` drops the static
    block entirely (leaving ``adverse / observed``), which isolates the temporal signal.
    """
    base, adverse, observed, triggers = b6_components(metrics)
    if drop is not None:
        if drop not in TERM_NAMES:
            raise ValueError(f"unknown temporal term {drop!r}")
        if triggers[drop] is not None:
            observed -= 1
            adverse -= int(triggers[drop])
    if temporal_only:
        return adverse / observed if observed else None
    if base is None:
        return adverse / observed if observed else None
    if not observed:
        return base
    return min(1.0, 0.75 * base + 0.25 * adverse / observed)


def b6_no_temporal(metrics: dict) -> float | None:
    """B6 with every temporal term removed: the static component alone (0.75 * B0)."""
    base = ratio_risk_score(metrics)
    return None if base is None else 0.75 * base


def ablation_score_vectors(dataset: e4r_data.Dataset) -> dict[str, dict[str, float]]:
    """Per-observation scores for the full score and every ablation."""
    vectors: dict[str, dict[str, float]] = {
        "B6_full": {},
        "B6_no_temporal": {},
        "B6_temporal_only": {},
    }
    for name in TERM_NAMES:
        vectors[f"B6_minus_{TERM_LABELS[name]}"] = {}
    for oid in dataset.observation_ids:
        metrics = dataset.metrics[oid]
        vectors["B6_full"][oid] = _required(b6_score_with(metrics), oid, "B6_full")
        vectors["B6_no_temporal"][oid] = _required(b6_no_temporal(metrics), oid, "B6_no_temporal")
        temporal_only = b6_score_with(metrics, temporal_only=True)
        vectors["B6_temporal_only"][oid] = float("nan") if temporal_only is None else temporal_only
        for name in TERM_NAMES:
            key = f"B6_minus_{TERM_LABELS[name]}"
            value = b6_score_with(metrics, drop=name)
            vectors[key][oid] = float("nan") if value is None else value
    return vectors


def _required(value: float | None, oid: str, label: str) -> float:
    if value is None:
        raise ValueError(f"{label} is undefined for {oid}; the frozen score is defined for all 675 rows")
    return float(value)


def verify_against_frozen(dataset: e4r_data.Dataset, tolerance: float = 1e-12) -> dict:
    """Prove the ablation machinery reproduces the frozen ``temporal_risk_score`` exactly."""
    worst = 0.0
    mismatches = 0
    for oid in dataset.observation_ids:
        metrics = dataset.metrics[oid]
        expected = temporal_risk_score(metrics)
        if expected is None:
            mismatches += 1
            continue
        observed = b6_score_with(metrics)
        gap = abs(observed - expected)
        worst = max(worst, gap)
        mismatches += gap > tolerance
    return {
        "status": "PASS" if mismatches == 0 else "FAIL",
        "tolerance": tolerance,
        "max_abs_error": worst,
        "mismatches": mismatches,
        "observations": dataset.n,
        "formula": "min(1, 0.75 * B0 + 0.25 * adverse/observed)",
    }


def temporal_contributions(dataset: e4r_data.Dataset) -> dict:
    """Per-term contribution of the temporal block to each observation's B6.

    With ``observed`` terms present, each triggered term moves B6 by
    ``0.25 / observed``. Terms that are present but not triggered contribute zero, and
    terms that are missing contribute zero *and* raise the weight of the terms that are
    present -- which is why the summary reports trigger prevalence alongside contribution.
    """
    rows = []
    for oid in dataset.observation_ids:
        base, adverse, observed, triggers = b6_components(dataset.metrics[oid])
        row = {
            "observation_id": oid,
            "label": dataset.labels[oid],
            "sector": dataset.sector[oid],
            "observed_terms": observed,
            "adverse_terms": adverse,
            "static_component": None if base is None else 0.75 * base,
        }
        for name in TERM_NAMES:
            triggered = triggers[name]
            row[f"{name}_present"] = triggered is not None
            row[f"{name}_triggered"] = bool(triggered) if triggered is not None else None
            row[f"{name}_contribution"] = (
                (0.25 * int(triggered) / observed) if (triggered is not None and observed) else 0.0
            )
        rows.append(row)
    return {"per_observation": rows, "terms": list(TERM_NAMES)}
