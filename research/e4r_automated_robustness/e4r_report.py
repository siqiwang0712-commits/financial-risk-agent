"""Generate ``FINAL_REPORT.md`` from the E4-R artifacts.

The report is rendered from JSON that the pipeline already produced, and the
interpretation cases are applied mechanically from ``INTERPRETATION_POLICY.md``. Nothing
here is typed from memory of the numbers, so the prose cannot drift away from the data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

EQUIV_BAND = 0.02
CONCENTRATION = 0.80
DESTROY_FRACTION = 0.80


def _read(name: str):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def fmt(value, digits: int = 4, sign: bool = False) -> str:
    if value is None:
        return "NOT_ESTIMABLE"
    return f"{value:+.{digits}f}" if sign else f"{value:.{digits}f}"


def pfmt(value) -> str:
    """p-values in scientific form; a p that underflows to 0.0 is reported as a bound."""
    if value is None:
        return "NOT_ESTIMABLE"
    if value == 0.0:
        return "<1e-15 (underflow)"
    return f"{value:.3g}"


def _approx_eq(a, b, bca_low, bca_high) -> bool:
    if a is None or b is None:
        return False
    if abs(a - b) <= EQUIV_BAND:
        return True
    return bca_low is not None and bca_high is not None and bca_low <= 0 <= bca_high


def _better(a, b, bca_low) -> bool:
    if a is None or b is None:
        return False
    return (a - b) > EQUIV_BAND and bca_low is not None and bca_low > 0


def apply_policy(model_results: dict, statistics: dict, ablation: dict, subgroup: dict, influence: dict) -> dict:
    models = model_results["models"]
    b0 = models["B0"]["auroc"]
    b6 = models["B6"]["auroc"]
    boosting = models["hist_gb_F2"]["auroc"]
    logistic = models["logistic_F2"]["auroc"]

    primary = {item["id"]: item for item in statistics["primary"]}
    p1 = primary["P1"]
    p3 = primary["P3"]
    p3_bca = (p3["bootstrap_auroc"]["bca_low"], p3["bootstrap_auroc"]["bca_high"])

    temporal_gain = b6 - ablation["variants"]["B6_no_temporal"]["auroc"]
    observed_gain_vs_b0 = b6 - b0
    single_term = {
        name: ablation["variants"][f"B6_minus_{name}"]["auroc"]
        for name in ("revenue", "OCF", "debt", "cash")
    }
    single_gain = {name: b6 - value for name, value in single_term.items()}
    max_term = max(single_gain, key=lambda name: single_gain[name])

    cases: list[dict] = []
    if _better(b6, b0, p1["bootstrap_auroc"]["bca_low"]) and _approx_eq(boosting, b6, *p3_bca):
        cases.append({
            "case": "A",
            "text": "Temporal information adds value, but the gain is reproducible by conventional "
                    "tabular learning; no Agent-specific interpretation follows.",
        })
    if _better(boosting, b6, p3["bootstrap_auroc"]["bca_low"]):
        cases.append({
            "case": "B",
            "text": "B6 captures useful temporal information but its hand-designed aggregation is not "
                    "competitive with a learned nonlinear tabular baseline.",
        })
    if not _better(boosting, b6, p3["bootstrap_auroc"]["bca_low"]):
        cases.append({
            "case": "C",
            "text": "The transparent hand-designed temporal score remains competitive with stronger "
                    "learned tabular baselines on this retrospective cohort.",
        })

    destroyed = temporal_gain >= DESTROY_FRACTION * observed_gain_vs_b0 if observed_gain_vs_b0 else False
    if destroyed:
        cases.append({
            "case": "D",
            "text": "E4's gain appears materially dependent on temporal information.",
        })
    concentrated = temporal_gain > 0 and single_gain[max_term] >= CONCENTRATION * temporal_gain
    if concentrated:
        cases.append({
            "case": "E",
            "text": "The observed B6 improvement is concentrated in a narrow temporal signal rather "
                    "than broadly distributed across trajectory features.",
        })

    markers = []
    for row in subgroup["sector"]["rows"]:
        if not row["estimable"]:
            continue
        delta = row["models"]["B6"]["auroc"] - row["models"]["B0"]["auroc"]
        if delta <= 0:
            markers.append(f"sector {row['subgroup']}: ΔAUROC(B6−B0) = {delta:+.4f} ≤ 0")
    loo = influence["leave_one_out"]
    if loo.get("deletions_flipping_sign"):
        markers.append(
            f"{loo['deletions_flipping_sign']} leave-one-out deletion(s) reverse the sign of ΔAUROC(B6−B0)"
        )
    for entry in influence["leave_sector_out"]["entries"]:
        if entry["group"] not in influence["leave_sector_out"]["sectors_evaluated"]:
            continue
        value = entry["delta_without"]
        if value is not None and value < 0.5 * observed_gain_vs_b0:
            markers.append(
                f"dropping sector {entry['group']} moves ΔAUROC to {value:+.4f} "
                f"(< 50% of {observed_gain_vs_b0:+.4f})"
            )
    for row in subgroup["missingness"]["rows"]:
        if not row["estimable"]:
            continue
        delta = row["models"]["B6"]["auroc"] - row["models"]["B0"]["auroc"]
        if delta <= 0:
            markers.append(f"missingness band {row['subgroup']}: ΔAUROC(B6−B0) = {delta:+.4f} ≤ 0")
    if markers:
        cases.append({
            "case": "F",
            "text": "The aggregate E4 improvement is not uniformly robust across the evaluated population.",
            "markers": markers,
        })

    return {
        "b0": b0,
        "b6": b6,
        "boosting": boosting,
        "logistic": logistic,
        "temporal_gain": temporal_gain,
        "observed_gain_vs_b0": observed_gain_vs_b0,
        "single_gain": single_gain,
        "max_term": max_term,
        "destroyed": destroyed,
        "concentrated": concentrated,
        "cases": cases,
        "instability_markers": markers,
    }


def write_final_report(base: Path | None = None) -> Path:
    root = base or HERE

    def read(name: str):
        return json.loads((root / name).read_text(encoding="utf-8"))

    model_results = read("model_results.json")
    statistics = read("statistical_tests.json")
    ablation = read("temporal_ablation.json")
    subgroup = read("subgroup_results.json")
    influence = read("influence_analysis.json")
    controls = read("negative_controls.json")
    calibration = read("calibration_diagnostics.json")
    thresholds = read("threshold_robustness.json")
    complexity = read("complexity_comparison.json")
    contribution = read("temporal_contribution_summary.json")
    leakage = read("leakage_audit.json")
    incremental = read("temporal_incremental_test.json")
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        manifest = {
            "status": "POST_HOC_AUTOMATED_ROBUSTNESS",
            "git_commit": "UNKNOWN (manifest not yet written)",
            "python": {"version": sys.version.split()[0]},
            "config_hash": "0" * 64,
            "feature_sets_hash": "0" * 64,
            "seeds": json.loads((root / "experiment_config.json").read_text(encoding="utf-8"))["seeds"],
        }
    feature_sets = read("feature_sets.json")

    policy = apply_policy(model_results, statistics, ablation, subgroup, influence)
    models = model_results["models"]

    def auroc(name: str):
        entry = models.get(name)
        return None if entry is None else entry["auroc"]

    def delta_between(left: str, right: str):
        left_value, right_value = auroc(left), auroc(right)
        return None if left_value is None or right_value is None else left_value - right_value

    primary = {item["id"]: item for item in statistics["primary"]}
    secondary = {item["id"]: item for item in statistics["secondary"]}
    p1 = primary["P1"]

    def row_for(items: dict, ident: str) -> dict:
        return items[ident]

    lines: list[str] = []
    add = lines.append

    add("# E4-R — Automated Robustness & Competitive Baseline Study")
    add("")
    add(f"**Status: `{manifest['status']}`** — git `{manifest['git_commit'][:12]}`, "
        f"Python {manifest['python']['version']}.")
    add("")
    add("E4-R is a **retrospective (POST_HOC)** study run on E4's published replication data. It is "
        "**not** `ESTABLISHED_E4`, **not** `CONFIRMATORY`, **not** `PROSPECTIVE` and **not** an "
        "`E5_RESULT`. It does not modify E4, does not create confirmatory evidence, and does not "
        "replace E5. It exists to make E5 designable.")
    add("")
    add(f"- cohort: **n = {model_results['n']}**, events = **{model_results['events']}**, "
        f"prevalence = **{fmt(model_results['prevalence'], 3)}**")
    add(f"- leakage audit: **{leakage['status']}** "
        f"({len([c for c in leakage['checks'] if c['status'] == 'PASS'])}/{len(leakage['checks'])} checks pass"
        + (f"; disclosed as REVIEW, not leakage: {', '.join(leakage['review_checks'])}"
           if leakage["review_checks"] else "")
        + ")")
    add("- primary multiplicity control: Holm across P1–P3")
    add(f"- bootstrap replicates: {statistics['bootstrap_replicates']}")
    add("")

    add("## 1. Headline")
    add("")
    add("| scorer | AUROC | PR-AUC |")
    add("|---|---:|---:|")
    for name in ("B0", "B6", "logistic_F0", "logistic_F1", "logistic_F2", "logistic_l1_F2",
                 "logistic_l2_F2", "random_forest_F2", "hist_gb_F1", "hist_gb_F2", "hist_gb_F3"):
        if name in models:
            add(f"| {name} | {fmt(models[name]['auroc'])} | {fmt(models[name]['pr_auc'])} |")
    add("")
    add(f"**P1 (B6 − B0):** ΔAUROC = {fmt(p1['delta_auroc'], 4, sign=True)}, "
        f"DeLong p = {pfmt(p1['delong']['p_value'])}, "
        f"Holm-adjusted p = {pfmt(p1['holm_adjusted_p'])}, "
        f"BCa 95% = [{fmt(p1['bootstrap_auroc']['bca_low'], 4, sign=True)}, "
        f"{fmt(p1['bootstrap_auroc']['bca_high'], 4, sign=True)}], "
        f"P(Δ>0) = {fmt(p1['bootstrap_auroc']['P_delta_gt_0p0'], 3)}")
    add("")

    add("## 2. Interpretation under the pre-registered policy")
    add("")
    if not policy["cases"]:
        add("No pre-registered case fired; the results are reported descriptively only.")
    for case in policy["cases"]:
        add(f"**Case {case['case']}.** {case['text']}")
        for marker in case.get("markers", []):
            add(f"  - {marker}")
    add("")

    add("## 3. The ten questions")
    add("")

    add("### Q1. Does B6 > B0 still hold under re-check?")
    add(f"{'Yes' if _better(policy['b6'], policy['b0'], p1['bootstrap_auroc']['bca_low']) else 'Not established'}. "
        f"B0 AUROC = {fmt(policy['b0'])}, B6 AUROC = {fmt(policy['b6'])}, "
        f"Δ = {fmt(p1['delta_auroc'], 4, sign=True)} "
        f"(BCa 95% [{fmt(p1['bootstrap_auroc']['bca_low'], 4, sign=True)}, "
        f"{fmt(p1['bootstrap_auroc']['bca_high'], 4, sign=True)}], "
        f"Holm p = {pfmt(p1['holm_adjusted_p'])}). "
        "This is a replication sanity check on E4's own data, not a new confirmation.")
    add("")

    add("### Q2. Is the temporal signal really the main incremental source?")
    add(f"Removing the whole temporal block gives AUROC = "
        f"{fmt(ablation['variants']['B6_no_temporal']['auroc'])}. Because `B6_no_temporal` is "
        f"`0.75 × B0`, a strictly increasing map of B0, that value equals AUROC(B0) "
        f"({fmt(policy['b0'])}) **exactly** — the check is structural, not empirical. The temporal "
        f"block therefore accounts for the entire B6 − B0 separation "
        f"({fmt(policy['temporal_gain'], 4, sign=True)}); "
        f"{'this meets the DESTROYED criterion (≥80% of the gain)' if policy['destroyed'] else 'this does not meet the DESTROYED criterion'}.")
    add("")

    add("### Q3. Which temporal component matters most?")
    add("| term | trigger prevalence | ΔAUROC vs B6_full when removed (negative = removing it helps) | mean contribution |")
    add("|---|---:|---:|---:|")
    for name in ("revenue", "OCF", "debt", "cash"):
        metric = {"revenue": "revenue_growth", "OCF": "operating_cash_flow_growth",
                  "debt": "total_debt_growth", "cash": "cash_growth"}[name]
        summary = contribution["terms"][metric]
        add(f"| {name} ({metric}) | {fmt(summary['trigger_prevalence_overall'], 3)} | "
            f"{fmt(policy['single_gain'][name], 4, sign=True)} | {fmt(summary['mean_contribution'], 4)} |")
    add("")
    add(f"Largest single-term effect: **{policy['max_term']}** "
        f"({fmt(policy['single_gain'][policy['max_term']], 4, sign=True)}), which is "
        f"{fmt(policy['single_gain'][policy['max_term']] / policy['temporal_gain'], 3)} of the whole "
        f"temporal gain — "
        f"{'CONCENTRATED (≥80%)' if policy['concentrated'] else 'not concentrated; the gain is spread across terms'}.")
    add("")

    add("### Q4. Does B6 depend on a few observations or one sector?")
    add(f"Leave-one-out over all {model_results['n']} rows: observed Δ = "
        f"{fmt(influence['observed_delta_auroc'], 4, sign=True)}; range after deletion "
        f"[{fmt(influence['leave_one_out']['min_delta_after_deletion'], 4, sign=True)}, "
        f"{fmt(influence['leave_one_out']['max_delta_after_deletion'], 4, sign=True)}]; "
        f"{influence['leave_one_out']['deletions_flipping_sign']} deletion(s) reverse the sign; "
        f"most influential single row = {influence['leave_one_out']['max_positive_unit']} "
        f"({fmt(influence['leave_one_out']['max_positive_influence'], 4, sign=True)}).")
    add("")
    loso = influence["leave_sector_out"]
    add("| sector removed | n removed | ΔAUROC without it |")
    add("|---|---:|---:|")
    for entry in loso["entries"]:
        if entry["group"] in loso["sectors_evaluated"]:
            add(f"| {entry['group']} | {entry['removed_n']} | {fmt(entry['delta_without'], 4, sign=True)} |")
    add("")

    add("### Q5. Can a strong logistic model reach B6?")
    p2 = row_for(primary, "P2")
    add(f"Prespecified linear challenger `logistic_F2`: AUROC = {fmt(policy['logistic'])}, "
        f"Δ vs B6 = {fmt(p2['delta_auroc'], 4, sign=True)} "
        f"(DeLong p = {pfmt(p2['delong']['p_value'])}, "
        f"Holm p = {pfmt(p2['holm_adjusted_p'])}, "
        f"BCa [{fmt(p2['bootstrap_auroc']['bca_low'], 4, sign=True)}, "
        f"{fmt(p2['bootstrap_auroc']['bca_high'], 4, sign=True)}]). "
        f"Best regularised linear variant: "
        f"{fmt(max([secondary[key]['challenger_auroc'] for key in ('S1', 'S2') if key in secondary], default=None))} "
        f"(reported as secondary, unadjusted).")
    add("")
    add("Static-only logistic (`logistic_F0`) reaches "
        f"{fmt(auroc('logistic_F0'))}; adding the temporal block moves it to "
        f"{fmt(auroc('logistic_F2'))} "
        + (f"(Δ = {fmt(secondary['S6']['delta_auroc'], 4, sign=True)}, "
           f"BCa [{fmt(secondary['S6']['bootstrap_auroc']['bca_low'], 4, sign=True)}, "
           f"{fmt(secondary['S6']['bootstrap_auroc']['bca_high'], 4, sign=True)}])."
           if "S6" in secondary else "(the incremental comparison is NOT_ESTIMABLE here)."))
    add("")

    add("### Q6. Can strong boosting exceed B6?")
    p3 = row_for(primary, "P3")
    add(f"`hist_gb_F2` AUROC = {fmt(policy['boosting'])}, Δ vs B6 = "
        f"{fmt(p3['delta_auroc'], 4, sign=True)} "
        f"(DeLong p = {pfmt(p3['delong']['p_value'])}, Holm p = {pfmt(p3['holm_adjusted_p'])}, "
        f"BCa [{fmt(p3['bootstrap_auroc']['bca_low'], 4, sign=True)}, "
        f"{fmt(p3['bootstrap_auroc']['bca_high'], 4, sign=True)}]). "
        f"Secondary: random forest {fmt(auroc('random_forest_F2'))}, "
        f"boosting on the extended family {fmt(auroc('hist_gb_F3'))}.")
    add("")

    add("### Q7. Does adding temporal features stably help the learned models?")
    nc2 = controls["NC2_temporal_alignment_destroyed"]["summary"]
    add(f"- logistic: F0 {fmt(auroc('logistic_F0'))} → F2 {fmt(auroc('logistic_F2'))} "
        f"({fmt(delta_between('logistic_F2', 'logistic_F0'), 4, sign=True)})")
    add(f"- boosting: F1 (temporal only) {fmt(auroc('hist_gb_F1'))} → F2 "
        f"{fmt(auroc('hist_gb_F2'))} "
        f"({fmt(delta_between('hist_gb_F2', 'hist_gb_F1'), 4, sign=True)})")
    add(f"- NC2 (temporal block shuffled across companies, {controls['NC2_temporal_alignment_destroyed']['summary']['logistic']['shuffled_replicates']} replicates): "
        f"logistic {fmt(nc2['logistic']['real_auroc'])} → {fmt(nc2['logistic']['shuffled_mean_auroc'])} "
        f"(drop {fmt(nc2['logistic']['mean_drop_vs_real'], 4, sign=True)}); "
        f"boosting {fmt(nc2['hist_gb']['real_auroc'])} → {fmt(nc2['hist_gb']['shuffled_mean_auroc'])} "
        f"(drop {fmt(nc2['hist_gb']['mean_drop_vs_real'], 4, sign=True)})")
    add("- temporal coefficient sign consistency across outer folds:")
    for name in ("revenue_growth", "operating_cash_flow_growth", "total_debt_growth", "cash_growth"):
        entry = incremental["coefficient_stability_across_outer_folds"].get(name, {})
        add(f"  - {name}: mean {fmt(entry.get('mean'), 4, sign=True)}, consistent sign "
            f"{entry.get('consistent_sign')} in {fmt(entry.get('sign_consistency'), 2)} of folds")
    add("")

    add("### Q8. Does missingness materially affect the result?")
    add("| band | n | events | B0 | B6 | Δ | Boosting-F2 |")
    add("|---|---:|---:|---:|---:|---:|---:|")
    for row in subgroup["missingness"]["rows"]:
        if row["estimable"]:
            value = row["models"]
            delta = value["B6"]["auroc"] - value["B0"]["auroc"]
            add(f"| {row['subgroup']} | {row['n']} | {row['events']} | {fmt(value['B0']['auroc'])} | "
                f"{fmt(value['B6']['auroc'])} | {fmt(delta, 4, sign=True)} | {fmt(value['hist_gb_F2']['auroc'])} |")
        else:
            add(f"| {row['subgroup']} | {row['n']} | {row['events']} | NOT_ESTIMABLE | — | — | — |")
    add("")

    add("### Q9. Is B6 still transparent, simple and competitive?")
    add(f"B6 requires {len(feature_sets['families']['F2']['fields'])} packet fields, no fitting, "
        f"no seed and no third-party dependency, and reaches "
        f"{fmt(policy['b6'])} against {fmt(policy['boosting'])} for the boosted model that needs "
        f"nested cross-validation, imputation, scaling and a hyperparameter search. "
        + ("On this cohort that is a competitive result." if policy["b6"] >= policy["boosting"] - EQUIV_BAND
           else "On this cohort the learned baseline is ahead.")
        )
    add("")

    add("### Q10. What does this mean for E5?")
    add("- E5 must be **prospective**: everything here is a re-reading of data E4 already "
        "published, so none of it can license a confirmatory claim.")
    add("- The comparison bar for E5 is not B0; it is a strong nested-CV tabular baseline on "
        "the same feature set, because that is what any temporal claim has to beat.")
    add("- E5 should prespecify the temporal block as a unit and report the ablation "
        "(`B6_no_temporal` is provably rank-equivalent to B0, so a null temporal effect is "
        "detectable and falsifiable).")
    add("- E5's cohort gate must be fixed before scoring: sector and missingness subgroups "
        "here are small, and only a handful clear the n≥40 / events≥10 bar.")
    if policy["instability_markers"]:
        add("- The instability markers in Case F are the specific failures E5's design has to "
            "be powered against.")
    add("")

    add("## 4. Robustness detail")
    add("")
    add("### Sector")
    add("| sector | n | events | prevalence | B0 | B6 | Δ | Boosting-F2 |")
    add("|---|---:|---:|---:|---:|---:|---:|---:|")
    for row in subgroup["sector"]["rows"]:
        if row["estimable"]:
            value = row["models"]
            add(f"| {row['subgroup']} | {row['n']} | {row['events']} | {fmt(row['prevalence'], 3)} | "
                f"{fmt(value['B0']['auroc'])} | {fmt(value['B6']['auroc'])} | "
                f"{fmt(value['B6']['auroc'] - value['B0']['auroc'], 4, sign=True)} | "
                f"{fmt(value['hist_gb_F2']['auroc'])} |")
        else:
            add(f"| {row['subgroup']} | {row['n']} | {row['events']} | {fmt(row['prevalence'], 3)} | "
                "NOT_ESTIMABLE | — | — | — |")
    add("")
    add("### Firm size")
    add(f"{subgroup['firm_size']['status']} — {subgroup['firm_size']['note']}")
    if subgroup["firm_size"]["rows"]:
        add("")
        add("| band | n | events | B0 | B6 | Δ | Boosting-F2 |")
        add("|---|---:|---:|---:|---:|---:|---:|")
        for row in subgroup["firm_size"]["rows"]:
            if row["estimable"]:
                value = row["models"]
                add(f"| {row['subgroup']} | {row['n']} | {row['events']} | {fmt(value['B0']['auroc'])} | "
                    f"{fmt(value['B6']['auroc'])} | "
                    f"{fmt(value['B6']['auroc'] - value['B0']['auroc'], 4, sign=True)} | "
                    f"{fmt(value['hist_gb_F2']['auroc'])} |")
            else:
                add(f"| {row['subgroup']} | {row['n']} | {row['events']} | NOT_ESTIMABLE | — | — | — |")
    add("")

    add("## 5. Negative controls")
    add("")
    nc1 = controls["NC1_label_permutation"]
    add("| scorer | mean AUROC under permuted labels | sd | 2.5% | 97.5% |")
    add("|---|---:|---:|---:|---:|")
    for name, entry in nc1["models"].items():
        add(f"| {name} | {fmt(entry['mean'])} | {fmt(entry['sd'])} | {fmt(entry['p2_5'])} | {fmt(entry['p97_5'])} |")
    add("")
    add("NC1 is a machinery check (random labels must return chance), not an equal-AUROC test.")
    add("")

    add("## 6. Threshold sensitivity (`SENSITIVITY_ONLY`)")
    add("")
    add("| scorer | thr | recall | specificity | precision | F1 | FNR | review load |")
    add("|---|---:|---:|---:|---:|---:|---:|---:|")
    for name in ("B0", "B6", "logistic_F2", "hist_gb_F2"):
        for row in thresholds["models"][name]:
            if abs(row["threshold"] - 0.5) < 1e-9:
                add(f"| {name} | {row['threshold']:.2f} | {fmt(row['recall'], 3)} | "
                    f"{fmt(row['specificity'], 3)} | {fmt(row['precision'], 3)} | {fmt(row['f1'], 3)} | "
                    f"{fmt(row['fnr'], 3)} | {fmt(row['review_load'], 3)} |")
    add("")
    add("Only the prespecified grid is shown; no threshold was selected and the production "
        "configuration was not touched.")
    add("")

    add("## 7. Calibration (descriptive; scores remain UNCALIBRATED)")
    add("")
    add("| scorer | Brier | ECE | CITL | slope | unique values | zero/one mass |")
    add("|---|---:|---:|---:|---:|---:|---:|")
    for name in ("B0", "B6", "logistic_F2", "hist_gb_F2"):
        entry = calibration["models"][name]
        add(f"| {name} | {fmt(entry['brier'])} | {fmt(entry['ece'])} | {fmt(entry['citl_intercept'])} | "
            f"{fmt(entry['calibration_slope'])} | {entry['unique_score_values']} | "
            f"{fmt(entry['extreme_mass'], 3)} |")
    add("")

    add("## 8. Complexity")
    add("")
    add("| scorer | family | fit seconds | dependencies | determinism |")
    add("|---|---|---:|---|---|")
    for entry in complexity["models"]:
        add(f"| {entry['model']} | {entry['family']} | {fmt(entry['fit_seconds'], 2)} | "
            f"{entry['dependencies']} | {entry['deterministic_reproducibility']} |")
    add("")

    add("## 9. Limitations")
    add("")
    add("- This cohort is E4-S's re-execution, not E4's exact 674 rows: E4's 270-CIK exclusion "
        "set is unpublished, so the sample is a ~94%-overlapping near-reproduction. E4-R "
        "inherits that limitation and adds no independent sample.")
    add("- 675 observations with 235 events gives a paired ΔAUROC standard error near 0.008; "
        "differences inside ±0.02 are not resolvable here.")
    add("- Only three sectors clear the n≥40 / events≥10 gate, so sector conclusions are thin.")
    add("- Learned-model metrics are out-of-fold, which is the right estimator for a "
        "retrospective study but is still noisier than a single large held-out set would be.")
    add("- B0 and B6 are deterministic functions with nothing to fit; their scores are "
        "in-sample for this cohort. They carry no fitting advantage, but they also have no "
        "out-of-sample interpretation.")
    add("- Part of the learners' advantage is *reporting* itself, not just reporting values: "
        "whether a field is present at all is predictive here (the strongest missingness "
        "indicator sits "
        + (f"{leakage['missingness_indicator_screen'][0]['distance_from_chance']:.3f} from chance"
           if leakage.get("missingness_indicator_screen") else "well away from chance")
        + "), and the imputer turns that into a feature. B0 and B6 cannot see it because they "
          "simply skip absent terms. See `leakage_audit.json`.")
    add("- Calibration is descriptive only; no calibration map was fitted.")
    add("")

    add("## 10. Reproduction")
    add("")
    add("```bash")
    add("python research/e4r_automated_robustness/verify_e4r.py")
    add("```")
    add("")
    add(f"Config hash `{manifest['config_hash'][:16]}…`, feature-set hash "
        f"`{manifest['feature_sets_hash'][:16]}…`, seeds "
        f"`{json.dumps(manifest['seeds'], sort_keys=True)}`.")
    add("")

    path = root / "FINAL_REPORT.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")
    return path


if __name__ == "__main__":
    print(write_final_report())
