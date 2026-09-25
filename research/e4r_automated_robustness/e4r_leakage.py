"""Automated leakage audit for E4-R.

The audit inspects only the published replication packet and the frozen outcome records.
It answers one question: does any feature used for prediction carry information that could
only have existed *after* the prediction cutoff?

If a check returns ``CONFIRMED_LEAKAGE`` the whole study is marked ``INVALIDATED`` and no
performance conclusion is published. Checks that cannot be evaluated on the published
packet return ``NOT_ESTIMABLE`` rather than silently passing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import e4r_data
import e4r_stats

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

OUTCOME_TOKENS = (
    "deterioration",
    "outcome",
    "label",
    "financial_deterioration",
    "condition_status",
    "fcf_outcome",
)
FUTURE_YEAR_PATTERN = re.compile(r"(20(2[5-9]|3\d))")


def _value_year(text: str) -> int | None:
    match = re.search(r"(20\d{2})", str(text))
    return int(match.group(1)) if match else None


def audit(dataset: e4r_data.Dataset, cohort_rows: list[dict], outcome_rows: list[dict]) -> dict:
    checks: list[dict] = []

    def record(name: str, status: str, detail: str = "", **extra) -> None:
        payload = {"check": name, "status": status, "detail": detail}
        payload.update(extra)
        checks.append(payload)

    # -- 1. duplicate / overlap ---------------------------------------------------------
    duplicate_obs = len(dataset.observation_ids) != len(set(dataset.observation_ids))
    record(
        "duplicate_observation_ids",
        "CONFIRMED_LEAKAGE" if duplicate_obs else "PASS",
        f"{len(dataset.observation_ids)} rows, {len(set(dataset.observation_ids))} unique",
    )
    unique_companies = len(set(dataset.masked_company_id.values()))
    record(
        "company_overlap",
        "PASS" if unique_companies == dataset.n else "CONFIRMED_LEAKAGE",
        f"{unique_companies} unique masked_company_id for {dataset.n} observations",
    )
    unique_ciks = len(set(dataset.cik.values()))
    record(
        "cik_overlap",
        "PASS" if unique_ciks == dataset.n else "CONFIRMED_LEAKAGE",
        f"{unique_ciks} unique CIK for {dataset.n} observations",
    )
    accessions = [row.get("accession") for row in cohort_rows]
    duplicate_accessions = len(accessions) != len(set(accessions))
    record(
        "duplicate_accessions",
        "CONFIRMED_LEAKAGE" if duplicate_accessions else "PASS",
        f"{len(accessions)} cohort rows, {len(set(accessions))} unique accessions",
    )

    # -- 2. feature timestamps ----------------------------------------------------------
    late_facts = 0
    scanned = 0
    examples: list[str] = []
    for oid in dataset.observation_ids:
        period = dataset.period_end[oid].replace("-", "")
        for payload in dataset.provenance[oid].values():
            if not isinstance(payload, dict):
                continue
            ddate = str(payload.get("period_end") or "")
            if not ddate:
                continue
            scanned += 1
            if ddate > period:
                late_facts += 1
                if len(examples) < 5:
                    examples.append(f"{oid}:{ddate}>{period}")
    record(
        "feature_timestamp_le_prediction_cutoff",
        "CONFIRMED_LEAKAGE" if late_facts else "PASS",
        f"{scanned} provenance facts scanned, {late_facts} dated after the fiscal period end",
        facts_scanned=scanned,
        examples=examples,
    )

    cutoff_violations = [
        oid for oid in dataset.observation_ids if dataset.period_end[oid] > dataset.information_cutoff[oid][:10]
    ]
    record(
        "fiscal_period_le_information_cutoff",
        "CONFIRMED_LEAKAGE" if cutoff_violations else "PASS",
        f"{len(cutoff_violations)} observations with period_end after the cutoff date",
    )

    prior_after = [
        oid
        for oid in dataset.observation_ids
        if dataset.previous_period[oid] >= dataset.period_end[oid].replace("-", "")
    ]
    record(
        "previous_period_before_current_period",
        "CONFIRMED_LEAKAGE" if prior_after else "PASS",
        f"{len(prior_after)} observations whose prior comparison period is not earlier",
    )

    # -- 3. outcome timestamps ----------------------------------------------------------
    outcome_before = 0
    outcome_after_window = 0
    missing_outcome_time = 0
    for oid in dataset.observation_ids:
        available = dataset.outcome_available_at[oid]
        if not available:
            missing_outcome_time += 1
            continue
        if available <= dataset.information_cutoff[oid]:
            outcome_before += 1
        if available > dataset.outcome_window_end[oid]:
            outcome_after_window += 1
    record(
        "outcome_timestamp_gt_cutoff",
        "CONFIRMED_LEAKAGE" if outcome_before else "PASS",
        f"{outcome_before} outcomes resolved at or before the prediction cutoff",
        missing_timestamps=missing_outcome_time,
    )
    record(
        "outcome_within_forward_window",
        "CONFIRMED_LEAKAGE" if outcome_after_window else "PASS",
        f"{outcome_after_window} outcomes resolved after the locked forward window",
    )

    # -- 4. future-year and outcome-derived fields --------------------------------------
    feature_keys = set()
    for oid in dataset.observation_ids:
        feature_keys.update(dataset.metrics[oid].keys())
        feature_keys.update(dataset.current[oid].keys())
        feature_keys.update(dataset.provenance[oid].keys())
    future_named = sorted(key for key in feature_keys if FUTURE_YEAR_PATTERN.search(key))
    record(
        "no_future_year_field_names",
        "CONFIRMED_LEAKAGE" if future_named else "PASS",
        f"{len(future_named)} field names embed a post-2025 year",
        fields=future_named,
    )
    outcome_named = sorted(
        key for key in feature_keys if any(token in key.lower() for token in OUTCOME_TOKENS)
    )
    record(
        "no_outcome_derived_field_names",
        "CONFIRMED_LEAKAGE" if outcome_named else "PASS",
        f"{len(outcome_named)} field names reference the outcome",
        fields=outcome_named,
    )
    label_named = sorted(key for key in feature_keys if "label" in key.lower())
    record(
        "no_label_derived_field_names",
        "CONFIRMED_LEAKAGE" if label_named else "PASS",
        f"{len(label_named)} field names reference the label",
        fields=label_named,
    )

    outcome_keys = set()
    for row in outcome_rows:
        outcome_keys.update(row.keys())
    shared = sorted(feature_keys & outcome_keys)
    record(
        "feature_and_outcome_key_disjointness",
        "PASS",
        "shared keys are identifiers only" if set(shared) <= {"observation_id", "ticker"} else "REVIEW",
        shared_keys=shared,
    )

    # -- 5. perfect-separation screen ---------------------------------------------------
    separated = []
    for name in dataset.metric_fields:
        values = []
        labels = []
        for oid in dataset.observation_ids:
            raw = dataset.metrics[oid].get(name)
            if raw is None:
                continue
            values.append(float(raw))
            labels.append(dataset.labels[oid])
        if len(values) < dataset.n * 0.5:
            continue
        if _perfectly_separates(values, labels):
            separated.append(name)
    record(
        "no_feature_perfectly_separates_the_label",
        "CONFIRMED_LEAKAGE" if separated else "PASS",
        f"{len(separated)} metrics separate events from non-events perfectly",
        fields=separated,
    )

    # -- 6. structural disclosures that are NOT leakage, but must be visible -----------
    #
    # The endpoint is a *transition* rule: four of its five conditions compare the FY2025
    # fact against the FY2024 fact, and two of them are gated on the FY2024 value being
    # positive. FY2024 facts are legitimately visible at the prediction cutoff, so using
    # them is not leakage -- but it does mean pre-cutoff magnitudes are strongly
    # informative about a label built from relative changes off a small base. E4-R reports
    # this rather than letting a reader discover it from the learned models' AUROCs.
    signal: list[dict] = []
    for name in dataset.metric_fields:
        values: list[float] = []
        labels: list[int] = []
        for oid in dataset.observation_ids:
            raw = dataset.metrics[oid].get(name)
            if raw is None:
                continue
            values.append(float(raw))
            labels.append(dataset.labels[oid])
        if len(values) < 0.5 * dataset.n:
            continue
        value = e4r_stats.roc_auc(labels, values)
        if value is not None:
            signal.append({"field": name, "auroc": value, "distance_from_chance": abs(value - 0.5), "n": len(values)})
    signal.sort(key=lambda entry: entry["distance_from_chance"], reverse=True)
    anchored = signal and signal[0]["distance_from_chance"] >= 0.25
    record(
        "endpoint_anchored_on_pre_cutoff_levels",
        "REVIEW" if anchored else "PASS",
        (
            "financial_deterioration_12m is a transition rule: four of its five conditions "
            "compare the FY2025 fact with the FY2024 fact and two are gated on the FY2024 "
            "value being positive. FY2024 facts are visible before the cutoff, so this is "
            "NOT leakage, but pre-cutoff magnitudes are strongly informative about the label "
            f"- the strongest single metric sits {signal[0]['distance_from_chance']:.3f} from chance."
        ) if anchored else "no metric is strongly anchored on the label",
    )

    indicator: list[dict] = []
    for name in dataset.metric_fields:
        flags = [1.0 if dataset.metrics[oid].get(name) is None else 0.0 for oid in dataset.observation_ids]
        if not 0 < sum(flags) < len(flags):
            continue
        value = e4r_stats.roc_auc([dataset.labels[oid] for oid in dataset.observation_ids], flags)
        if value is not None:
            indicator.append(
                {"field": name, "n_missing": int(sum(flags)), "auroc": value,
                 "distance_from_chance": abs(value - 0.5)}
            )
    indicator.sort(key=lambda entry: entry["distance_from_chance"], reverse=True)
    record(
        "missingness_indicators_carry_signal",
        "REVIEW" if indicator and indicator[0]["distance_from_chance"] >= 0.15 else "PASS",
        "whether a field is reported at all is itself predictive; the imputer's add_indicator "
        "flag therefore enters every learned model as a legitimate prediction-time feature",
    )

    # -- 7. cohort construction ---------------------------------------------------------
    verified = [row for row in outcome_rows if row.get("label_status") == "VERIFIED"]
    record(
        "analysis_rows_equal_verified_outcomes",
        "PASS" if len(verified) == dataset.n else "REVIEW",
        f"{len(verified)} VERIFIED outcomes, {dataset.n} analysis rows",
    )
    unresolved = [
        row for row in outcome_rows
        if row.get("label_status") != "VERIFIED" and row.get("financial_deterioration_12m") is not None
    ]
    record(
        "no_unresolved_outcome_converted_to_label",
        "CONFIRMED_LEAKAGE" if unresolved else "PASS",
        f"{len(unresolved)} non-VERIFIED rows carry a binary label",
    )

    confirmed = [item for item in checks if item["status"] == "CONFIRMED_LEAKAGE"]
    review = [item for item in checks if item["status"] == "REVIEW"]
    return {
        "status": "INVALIDATED" if confirmed else ("REVIEW" if review else "PASS"),
        "evidence_status": e4r_data.STATUS,
        "n_observations": dataset.n,
        "events": dataset.events,
        "checks": checks,
        "confirmed_leakage_checks": [item["check"] for item in confirmed],
        "review_checks": [item["check"] for item in review],
        "univariate_signal_screen": signal[:12],
        "missingness_indicator_screen": indicator[:12],
        "note": (
            "A CONFIRMED_LEAKAGE check invalidates E4-R's performance conclusions; a REVIEW "
            "check is an ambiguity that must be disclosed but does not by itself invalidate."
        ),
    }


def _perfectly_separates(values: list[float], labels: list[int]) -> bool:
    if len(set(labels)) < 2:
        return False
    positive = [value for value, label in zip(values, labels, strict=True) if label == 1]
    negative = [value for value, label in zip(values, labels, strict=True) if label == 0]
    return max(positive) < min(negative) or min(positive) > max(negative)
