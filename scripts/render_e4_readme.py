"""Render E4 public artifacts and the README from one canonical summary."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from finrisk.e4_core import Stage, StudyState, canonical_hash, read_json, write_json
from finrisk.e4_evaluation import (
    bootstrap_interval,
    performance,
    positive_improvement_claim_allowed,
)

MODELS = ("B0", "B2", "B3", "B6", "A0", "A1", "A2", "H0")
RESEARCH = ROOT / "research"


def _fmt(value: float | None, digits: int = 3) -> str:
    return "NA" if value is None else f"{value:.{digits}f}"


def _signed(value: float | None, digits: int = 4) -> str:
    """Signed number with the typographic minus the rest of the README uses."""
    return "NA" if value is None else f"{value:+.{digits}f}".replace("-", "\u2212")


def _pvalue(value: float | None) -> str:
    """p-values in scientific form; one that underflows to 0.0 is reported as a bound."""
    if value is None:
        return "NA"
    if value == 0.0:
        return "<1e-15 (underflow)"
    return f"{value:.2g}"


def _read_artifact(path: Path) -> dict[str, Any] | None:
    """Load a study artifact, or return ``None`` when it is absent or unreadable.

    The README research section is rendered from committed artifacts so the prose cannot
    drift from the numbers. The two post-hoc studies are checked in alongside E4, but E4's
    own replay must not depend on them: a missing artifact degrades that one subsection to
    a link instead of breaking the render.
    """
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _paired_table(artifacts: Path) -> list[dict[str, Any]]:
    evaluation = read_json(artifacts / "evaluation.json")
    rows = evaluation["analysis_rows"]
    by_model = {model: {row["observation_id"]: row for row in rows if row["model_id"] == model} for model in MODELS}
    common = set.intersection(*(set(values) for values in by_model.values()))
    output = []
    for index, model in enumerate(MODELS):
        subset = [by_model[model][key] for key in sorted(common)]
        measured = performance(subset)
        output.append({
            "model_id": model,
            **measured,
            "auroc_ci": bootstrap_interval(subset, "auroc", seed=20262000 + index),
            "pr_auc_ci": bootstrap_interval(subset, "pr_auc", seed=20262100 + index),
        })
    return output


def _summary(artifacts: Path) -> dict[str, Any]:
    evaluation = read_json(artifacts / "evaluation.json")
    attrition = read_json(artifacts / "attrition.json")
    cohort = read_json(artifacts / "cohort_report.json")
    outcome = read_json(artifacts / "outcome_report.json")
    primary = {row["hypothesis"]: row for row in evaluation["primary_comparisons"]}
    summary = {
        "study": "E4 — Large-Scale Comparative External Validation of Structured Financial Reasoning",
        "source_commit": "4273b070678240fe7cbdf01a17527afcc71c500e",
        "cohort": cohort,
        "outcomes": {
            "cohort_n": attrition["cohort"],
            "verified_n": outcome["status_counts"]["VERIFIED"],
            "events": outcome["verified_events"],
            "event_prevalence": outcome["verified_events"] / outcome["status_counts"]["VERIFIED"],
            "verified_coverage": attrition["verified_coverage"],
            "status_counts": outcome["status_counts"],
        },
        "e4a_results": {model: evaluation["summaries"][model] for model in ("B0", "B1", "B2", "B3", "B6")},
        "e4a_intervals": {model: evaluation["intervals"][model] for model in ("B0", "B1", "B2", "B3", "B6")},
        "paired_e4b_table": _paired_table(artifacts),
        "primary_comparisons": evaluation["primary_comparisons"],
        "claim_gate": {
            "P1": "POSITIVE_PAIRED_AUROC_IMPROVEMENT" if positive_improvement_claim_allowed(primary["P1"]) else "NUMERIC_ONLY",
            "P2": "POSITIVE_PAIRED_AUROC_IMPROVEMENT" if positive_improvement_claim_allowed(primary["P2"]) else "NOT_ESTABLISHED",
            "P3": "POSITIVE_PAIRED_AUROC_IMPROVEMENT" if positive_improvement_claim_allowed(primary["P3"]) else "NOT_ESTABLISHED",
        },
        "agent": {
            "runtime": "Ollama 0.12.3 / Qwen2.5 0.5B Instruct Q4_K_M / CPU",
            "official_failures": len(read_json(artifacts / "agent_raw_responses.json")["failures"]),
            "stability": read_json(artifacts / "agent_stability_summary.json"),
            "batch_sensitivity": read_json(artifacts / "batch_sensitivity_summary.json"),
        },
        "source_concordance": read_json(artifacts / "source_concordance.json"),
        "reproducibility": {
            **read_json(artifacts / "reproducibility_summary.json"),
            "agent_response_replay": read_json(artifacts / "agent_replay_verification.json"),
        },
        "reliability": "UNCALIBRATED",
        "scope": {
            "evaluates": ["structured financial risk ranking", "temporal structured signal", "Local Agent reasoning", "deterministic + Agent structured hybrid"],
            "does_not_validate": ["calibrated default probability", "universal bankruptcy prediction", "production/regulatory use", "full narrative/document Agent", "MD&A / Risk-Factor grounding", "full FinRisk Agent external validation"],
        },
    }
    summary["summary_hash"] = canonical_hash(summary)
    return summary


def _svg_auroc(table: list[dict[str, Any]]) -> str:
    width, height = 940, 440
    elements = []
    for index, row in enumerate(table):
        y = 65 + index * 43
        value = row["auroc"]
        low = row["auroc_ci"]["ci_low"]
        high = row["auroc_ci"]["ci_high"]
        if value is None or low is None or high is None:
            continue
        x, x_low, x_high = 170 + value * 700, 170 + low * 700, 170 + high * 700
        elements.append(f'<text x="30" y="{y + 5}" font-size="14">{row["model_id"]}</text><line x1="{x_low:.1f}" y1="{y}" x2="{x_high:.1f}" y2="{y}" stroke="#2d3748" stroke-width="3"/><circle cx="{x:.1f}" cy="{y}" r="6" fill="#2b6cb0"/><text x="880" y="{y + 5}" font-size="12" text-anchor="end">{value:.3f}</text>')
    ticks = "".join(f'<line x1="{170 + tick * 700:.1f}" y1="40" x2="{170 + tick * 700:.1f}" y2="410" stroke="#e2e8f0"/><text x="{170 + tick * 700:.1f}" y="430" text-anchor="middle" font-size="11">{tick:.1f}</text>' for tick in (0, 0.25, 0.5, 0.75, 1.0))
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#fff"/><text x="30" y="25" font-size="20" font-weight="bold">E4-B paired cohort — AUROC with 95% bootstrap CI</text>{ticks}{"".join(elements)}</svg>\n'


def _svg_deltas(primary: list[dict[str, Any]]) -> str:
    labels = {"P1": "B6 − B0", "P2": "H0 − B0", "P3": "H0 − A2"}
    elements = ['<line x1="470" y1="40" x2="470" y2="210" stroke="#a0aec0" stroke-dasharray="5 4"/>']
    for index, row in enumerate(primary):
        y = 75 + index * 55
        x = 470 + float(row["observed_delta"]) * 700
        low = 470 + float(row["ci_low"]) * 700
        high = 470 + float(row["ci_high"]) * 700
        color = "#2f855a" if row["ci_low"] > 0 and row["holm_adjusted_p"] < 0.05 else "#718096"
        elements.append(f'<text x="30" y="{y + 5}" font-size="14">{labels[row["hypothesis"]]}</text><line x1="{low:.1f}" y1="{y}" x2="{high:.1f}" y2="{y}" stroke="{color}" stroke-width="3"/><circle cx="{x:.1f}" cy="{y}" r="6" fill="{color}"/><text x="900" y="{y + 5}" font-size="12" text-anchor="end">Δ {row["observed_delta"]:+.3f}</text>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="940" height="250" viewBox="0 0 940 250"><rect width="100%" height="100%" fill="#fff"/><text x="30" y="25" font-size="20" font-weight="bold">Primary paired ΔAUROC (95% bootstrap CI)</text>{"".join(elements)}</svg>\n'


def _e4s_section() -> list[str]:
    """The E4-S subsection, rendered from the audit's own artifacts."""
    base = RESEARCH / "e4_statistical_audit"
    crosscheck = _read_artifact(base / "inference_crosscheck.json")
    replication = _read_artifact(base / "replication_crosscheck.json")
    calibration = _read_artifact(base / "method_calibration.json")
    detail = (
        "Canonical detail: [E4-S audit report](research/e4_statistical_audit/AUDIT_REPORT.md), "
        "[method cross-check](research/e4_statistical_audit/inference_crosscheck.json) and the "
        "[replication packet](research/e4_statistical_audit/replication/README.md)."
    )
    heading = [
        "### E4-S statistical audit",
        "",
        ("Status `POST_E4_STATISTICAL_AUDIT`. E4-S re-tests E4's primary inference under a "
        "correctly specified paired test and re-executes the frozen pipeline from public "
        "inputs. It modifies nothing under `research/e4/`: a SHA-256 manifest of every "
        "published E4 artifact, enforced in the test suite, proves it."),
        "",
    ]
    if not crosscheck or not replication or not calibration:
        return [
            *heading,
            "Its artifacts are not present in this checkout, so only the entry point is linked here.",
            "",
            detail,
            "",
        ]

    published = next(
        method
        for method in crosscheck["methods"]
        if method["method"] == "e4_published_label_permutation"
    )
    real = replication["audit_independent_implementation"]
    delong = real["delong"]
    bca = real["auroc_bootstrap"]["bca"]
    swap_p = real["score_swap_randomization"]["p_value"]
    cohort = replication["cohort_provenance"]
    size = calibration["scenarios"]["H0_equality_informative_scores"]["methods"]
    nominal = calibration["scenarios"]["H0_equality_informative_scores"]["nominal_alpha"]
    power = calibration["scenarios"]["alternative_E4_effect"]["methods"]
    return [
        *heading,
        (f"E4's per-observation rows were never published, so the audit re-ran the frozen "
        f"v0.3.4 pipeline with an empty 270-CIK exclusion (a documented deviation) and "
        f"publishes its own cohort, predictions and paired rows. That cohort is "
        f"**{cohort['n_pairs']} observations / {cohort['events']} events**, **~94% "
        f"overlapping** with E4's 674 ({cohort['measured_overlap']}): a near-reproduction, "
        f"not an independent sample."),
        "",
        "| Method | Null it actually tests | ΔAUROC | 95% interval | p |",
        "|---|---|---:|---|---:|",
        (f"| E4 frozen label permutation (2,000 replicates) | `H0_independence` | "
        f"{_signed(published['delta'])} | — | {published['p_value']:.4f} (attainable floor) |"),
        (f"| paired DeLong (the prespecified target) | `H0_equality` | {_signed(delong['observed_delta'])} | "
        f"[{_signed(delong['z_ci_low'])}, {_signed(delong['z_ci_high'])}] | {delong['p_value']:.5f} |"),
        (f"| cluster BCa bootstrap (20,000 replicates) | `H0_equality` | "
        f"{_signed(real['auroc_bootstrap']['observed'])} | [{_signed(bca[0])}, {_signed(bca[1])}] | — |"),
        (f"| score-swap randomization (20,000 replicates) | `H0_exch` | "
        f"{_signed(real['score_swap_randomization']['observed_delta'])} | — | {swap_p:.5f} |"),
        "",
        (f"Verdict `{crosscheck['headline']}`: every test that targets the equality hypothesis "
        f"rejects in the same direction with the same point estimate. Two findings travel "
        f"with it and must be reported together:"),
        "",
        ("- **E4's published p-value is not a test of the hypothesis E4 states.** It shuffles "
        "labels while holding each `(B0, B6)` pair fixed, so its reference distribution is "
        "that of ΔAUROC under `H0_independence` — the outcome is independent of *both* "
        "scores. Rejecting it shows at least one score carries signal; it does not show B6 "
        "carries more than B0. The value is also exactly `1/2001`, the attainable floor at "
        "2,000 permutations."),
        (f"- **At E4's design point the procedure is nonetheless close to nominal.** Measured "
        f"size {size['label_permutation_as_implemented']['empirical_rejection_rate']:.3f} "
        f"against a nominal {nominal} ({size['delong_paired']['empirical_rejection_rate']:.3f} "
        f"for DeLong), and power {power['label_permutation_as_implemented']['empirical_rejection_rate']:.3f} "
        f"against DeLong's {power['delong_paired']['empirical_rejection_rate']:.3f}. E4's "
        f"numbers are unaffected; only its justification changes. The simulation is "
        f"Monte-Carlo with "
        f"{calibration['monte_carlo_precision']['replicates']} replicates, so rates are "
        f"resolved to roughly ±0.03."),
        "",
        detail,
        "",
    ]


def _e4r_section() -> list[str]:
    """The E4-R subsection, rendered from the robustness study's own artifacts."""
    base = RESEARCH / "e4r_automated_robustness"
    model_results = _read_artifact(base / "model_results.json")
    statistics = _read_artifact(base / "statistical_tests.json")
    missingness = _read_artifact(base / "missingness_ablation.json")
    boosting = _read_artifact(base / "boosting_temporal_increment.json")
    controls = _read_artifact(base / "negative_controls.json")
    sector = _read_artifact(base / "sector_heterogeneity.json")
    stability = _read_artifact(base / "model_stability.json")
    detail = (
        "Reproduce with `python research/e4r_automated_robustness/verify_e4r.py`. Full "
        "protocol, artifacts and the generated report are in "
        "[the study directory](research/e4r_automated_robustness/README.md) and "
        "[FINAL_REPORT.md](research/e4r_automated_robustness/FINAL_REPORT.md)."
    )
    heading = [
        "### E4-R automated robustness and competitive baselines",
        "",
        ("`research/e4r_automated_robustness/` is a **`POST_HOC_AUTOMATED_ROBUSTNESS`** "
        "retrospective study run on E4-S's published replication packet. It **does not "
        "modify E4**, **does not create confirmatory evidence**, **does not replace E5**, "
        "and evaluates robustness and competitive baselines only. Its configuration is "
        "frozen before the run and the pipeline aborts if the hash moves."),
        "",
    ]
    if not model_results or not statistics:
        return [
            *heading,
            "Its artifacts are not present in this checkout, so only the entry point is linked here.",
            "",
            detail,
            "",
        ]

    scorers = (
        ("B0", "B0 (frozen heuristic)"),
        ("B6", "B6 (frozen heuristic)"),
        ("logistic_F0", "Logistic, static only"),
        ("logistic_F1", "Logistic, temporal only"),
        ("logistic_F2", "Logistic, static + temporal (prespecified linear challenger)"),
        ("hist_gb_F1", "Gradient boosting, temporal only"),
        ("hist_gb_F2", "Gradient boosting, static + temporal (prespecified nonlinear challenger)"),
    )
    models = model_results["models"]
    primary = {row["id"]: row for row in statistics["primary"]}
    lines = [
        *heading,
        (f"On the same {primary['P1']['n_pairs']} / {primary['P1']['events']} cohort, eleven "
        f"nested-CV baselines (5×5 company-level stratified folds, preprocessing fitted "
        f"inside the fold) and seven B6 ablations:"),
        "",
        "| Scorer | Out-of-fold AUROC | PR-AUC |",
        "|---|---:|---:|",
    ]
    for key, label in scorers:
        entry = models.get(key)
        if entry is None:
            continue
        lines.append(f"| {label} | {_fmt(entry['auroc'])} | {_fmt(entry['pr_auc'])} |")
    lines.extend([
        "",
        (f"P1 `B6 − B0` reproduces: ΔAUROC **{_signed(primary['P1']['delta_auroc'])}**, paired "
        f"DeLong p = {primary['P1']['delong']['p_value']:.5f}, Holm-adjusted p = "
        f"{primary['P1']['holm_adjusted_p']:.5f}, 20,000-replicate BCa "
        f"**[{_signed(primary['P1']['bootstrap_auroc']['bca_low'])}, "
        f"{_signed(primary['P1']['bootstrap_auroc']['bca_high'])}]**. "
        f"P2 `logistic_F2 − B6` is **{_signed(primary['P2']['delta_auroc'])}** (Holm p = "
        f"{_pvalue(primary['P2']['holm_adjusted_p'])}) and P3 `hist_gb_F2 − B6` is "
        f"**{_signed(primary['P3']['delta_auroc'])}** (Holm p = "
        f"{_pvalue(primary['P3']['holm_adjusted_p'])})."),
        "",
        "Three pre-registered interpretation cases fire:",
        "",
        ("- **Case B** — B6's hand-designed aggregation is not competitive with a learned "
        "nonlinear tabular baseline."),
        ("- **Case D** — E4's gain depends materially on the temporal block. This is a "
        "*structural* result: `B6_no_temporal = 0.75 × B0` is a strictly increasing map of B0, "
        "so its AUROC equals B0's exactly and all B6 − B0 ranking separation is mechanically "
        "introduced through the temporal component. It is not a causal finding, and the gain "
        "is not concentrated in one term — removing `cash_growth` slightly *improves* AUROC."),
        ("- **Case F** — the aggregate improvement is not uniformly robust across the "
        "population, though only as a marker: `Transportation_Utilities`'s −0.005 point "
        "estimate has an interval containing zero."),
        "",
    ])

    if missingness and boosting and controls and sector and stability:
        log_cmp = missingness["comparisons"]["logistic"]["A_minus_B_full_F2_without_indicators"]
        hg_cmp = missingness["comparisons"]["hist_gb"]["A_minus_B_full_F2_without_indicators"]
        log_only = missingness["families"]["logistic"]["arms"]["C_missingness_only"]["auroc"]
        hg_only = missingness["families"]["hist_gb"]["arms"]["C_missingness_only"]["auroc"]
        strict = missingness["strict_complete_case"]
        increment = boosting["comparison"]
        shuffle = controls["NC2_temporal_alignment_destroyed"]["models"]
        heterogeneity = sector["heterogeneity"]
        stability_models = stability["models"]
        lines.extend([
            ("A **post-hoc hardening pass** "
            "([EXTENSION_PROTOCOL.md](research/e4r_automated_robustness/EXTENSION_PROTOCOL.md)) "
            "then closed four gaps a reviewer would be right to push on. It cannot upgrade any "
            "statement, and `experiment_config.json` was not touched."),
            "",
            (f"- **A material share of the learned-model advantage is reporting structure.** "
            f"Removing the imputer's missing-value indicators costs the logistic "
            f"**{_signed(log_cmp['delta_auroc'])}** AUROC (95% BCa "
            f"[{_signed(log_cmp['bootstrap_auroc']['bca_low'])}, "
            f"{_signed(log_cmp['bootstrap_auroc']['bca_high'])}]) and the boosting model "
            f"**{_signed(hg_cmp['delta_auroc'])}** "
            f"([{_signed(hg_cmp['bootstrap_auroc']['bca_low'])}, "
            f"{_signed(hg_cmp['bootstrap_auroc']['bca_high'])}]). A model given **only** the "
            f"nine presence/absence flags — no financial value at all — reaches "
            f"**{_fmt(hg_only)}** (boosting) and **{_fmt(log_only)}** (logistic), i.e. above "
            f"B6's {_fmt(models['B6']['auroc'])}. This is **not** called leakage: nothing "
            f"shows an indicator carries outcome-side information, and the timestamp checks "
            f"pass. Strict complete-case leaves {strict['n']} observations and "
            f"{strict['events']} events and is reported as `NOT_ESTIMABLE` rather than "
            f"estimated."),
            (f"- **Temporal features add little once a strong static nonlinear learner is "
            f"used.** `hist_gb_F0` (static only) reaches "
            f"{_fmt(boosting['reference_metrics']['auroc'])} against `hist_gb_F2`'s "
            f"{_fmt(boosting['challenger_metrics']['auroc'])}: Δ "
            f"**{_signed(increment['delta_auroc'])}**, paired DeLong p = "
            f"{increment['delong']['p_value']:.2f}, BCa "
            f"[{_signed(increment['bootstrap_auroc']['bca_low'])}, "
            f"{_signed(increment['bootstrap_auroc']['bca_high'])}]. The superseded `F1 → F2` "
            f"comparison could not answer this because `hist_gb_F0` did not exist."),
            (f"- **The shuffled-temporal control is now genuinely paired** (one shared "
            f"configuration; the original arm's folds asserted equal to the frozen run's). "
            f"Shuffling costs the boosting model a median "
            f"{_signed(shuffle['hist_gb']['drop_median'])} AUROC with "
            f"{shuffle['hist_gb']['replicates_above_original']} of "
            f"{shuffle['hist_gb']['replicates']} replicates reaching the original; the "
            f"logistic moves {_signed(shuffle['logistic']['drop_median'])} with "
            f"P(drop>0) = {shuffle['logistic']['P_drop_gt_0']:.3f}. The superseded "
            f"0.8741-versus-0.8851 discrepancy is explained as an inner-grid difference and "
            f"retained as an audit note rather than deleted."),
            (f"- **Sector heterogeneity is not established.** No gated sector has an "
            f"interval-supported negative effect, and a "
            f"{heterogeneity['permutation_replicates']:,}-replicate permutation test does not "
            f"reject a common effect (p = {heterogeneity['permutation_p_value']:.2f}, "
            f"I² = {heterogeneity['i_squared']:.2f}); the gated sectors cover "
            f"{heterogeneity['gated_share_of_cohort']:.1%} of the cohort."),
            (f"- **Interval honesty.** The reported DeLong and bootstrap intervals condition on "
            f"the realized out-of-fold predictions and do not integrate training-procedure "
            f"uncertainty; repeated 5×5 nested CV measures that omitted component at "
            f"sd ≈ {stability_models['hist_gb_F2']['sd_auroc']:.4f} (boosting) and "
            f"{stability_models['logistic_F2']['sd_auroc']:.4f} (logistic), and it does not "
            f"enter any primary comparison."),
            "",
        ])
    lines.extend([detail, ""])
    return lines


def _post_hoc_sections() -> list[str]:
    """The two post-hoc studies, placed between E4's own results and the boundary sections."""
    return [*_e4s_section(), *_e4r_section()]


def _readme_section(summary: dict[str, Any]) -> str:
    b0 = summary["e4a_results"]["B0"]
    b6 = summary["e4a_results"]["B6"]
    b0_ci = summary["e4a_intervals"]["B0"]["auroc"]
    b6_ci = summary["e4a_intervals"]["B6"]["auroc"]
    p1, p2, p3 = summary["primary_comparisons"]
    lines = [
        "## Research results",
        "",
        "For the current E4 evidence-status map and artifact index, see the",
        "[experiment overview](research/EXPERIMENT_OVERVIEW.md) and",
        "[cross-study results](research/EXPERIMENT_RESULTS.md).",
        "",
        "E4 is followed by two post-hoc studies that read it and exist to make E5",
        "designable: **E4-S**, which audits E4's inference, and **E4-R**, which tests",
        "robustness and competitive baselines. Neither one modifies E4, and neither",
        "licenses a confirmatory claim.",
        "",
        "### E4 external validation",
        "",
        f"E4 evaluates the locked `v0.3.4` implementation on **{summary['outcomes']['cohort_n']:,} company-disjoint FY2024 10-K filers** selected before outcomes were visible. The predefined financial-deterioration endpoint verified {summary['outcomes']['verified_n']:,} companies ({summary['outcomes']['events']} events; prevalence {summary['outcomes']['event_prevalence']:.1%}). Performance estimates apply to the deterministically verifiable subset, not to bankruptcy, default, credit loss or insolvency probability.",
        "",
        "Evidence status: B6 over B0 is `ESTABLISHED_E4`; H0 over B0 and H0 over A2 are `EXPLORATORY_E4`.",
        "",
        f"B6 achieved AUROC **{b6['auroc']:.3f}** (95% CI {b6_ci['ci_low']:.3f}–{b6_ci['ci_high']:.3f}) and PR-AUC {b6['pr_auc']:.3f}, compared with B0 AUROC {b0['auroc']:.3f} ({b0_ci['ci_low']:.3f}–{b0_ci['ci_high']:.3f}) and PR-AUC {b0['pr_auc']:.3f}.",
        "",
        '<img src="research/e4/public/auroc_ci.svg" alt="E4-B paired AUROC confidence intervals" width="820" />',
        "",
        "### Comparative benchmark",
        "",
        "All rows below use the same E4-B paired, verified observations. Agent failures remain in coverage and are not imputed.",
        "",
        "| System | N / events | AUROC (95% CI) | PR-AUC (95% CI) | Recall | Specificity | Coverage |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary["paired_e4b_table"]:
        lines.append(f"| {row['model_id']} | {row['n_decisions']} / {row['events']} | {_fmt(row['auroc'])} ({_fmt(row['auroc_ci']['ci_low'])}–{_fmt(row['auroc_ci']['ci_high'])}) | {_fmt(row['pr_auc'])} ({_fmt(row['pr_auc_ci']['ci_low'])}–{_fmt(row['pr_auc_ci']['ci_high'])}) | {_fmt(row['recall'])} | {_fmt(row['specificity'])} | {row['coverage']:.1%} |")
    lines.extend([
        "",
        "### Incremental value",
        "",
        f"P1 showed a positive paired AUROC improvement for B6 over B0: Δ {p1['observed_delta']:+.3f} (95% CI {p1['ci_low']:+.3f} to {p1['ci_high']:+.3f}; Holm-adjusted p={p1['holm_adjusted_p']:.4f}).",
        "",
        f"P2 H0 versus B0 (Δ {p2['observed_delta']:+.3f}, 95% CI {p2['ci_low']:+.3f} to {p2['ci_high']:+.3f}) and P3 H0 versus A2 (Δ {p3['observed_delta']:+.3f}, {p3['ci_low']:+.3f} to {p3['ci_high']:+.3f}) were exploratory and the paired improvements were not established.",
        "",
        '<img src="research/e4/public/paired_delta_auroc.svg" alt="Primary paired AUROC deltas" width="820" />',
        "",
        "### Local Agent benchmark",
        "",
        "The benchmark communicated with a locally hosted Agent through an HTTP API. No external hosted inference API was used.",
        "",
        "The frozen CPU backend was Qwen2.5 0.5B Instruct (Q4_K_M) through Ollama 0.12.3. Agent and H0 estimates are exploratory because only five verified events were available in the fully paired E4-B subset. The Agent produced five permanent schema failures across the 150 official A0/A1/A2 records; these remain coverage failures. Stability runs at fixed temperature and seed had zero score SD among successful cases, while single-case versus batched inference showed material score sensitivity despite high decision agreement. This finding applies only to the tested 0.5B Local Agent and does not establish that stronger LLMs or Agents lack incremental value.",
        "",
        "### Post-hoc Codex sub-Agent comparator",
        "",
        "`ChatGPT5.6 Sol` is the project-internal display name for a Codex sub-Agent comparator; it is not an OpenAI model name or official ChatGPT model, and the platform did not expose the exact underlying model ID. On the same 50 frozen anonymous E4-B packets it completed 150/150 A0/A1/A2 judgments. Only 18 cases had deterministic `VERIFIED` outcomes and only five were events: AUROC was 0.815 for A0, 0.800 for A1, 0.738 for A2, and 0.708 for the fixed `0.5 × B6 + 0.5 × A2` hybrid. These outcome-blind predictions were commissioned after E4 outcomes existed, so all results are `POST_HOC`, `UNCALIBRATED`, and insufficiently powered; they do not alter E4 or establish model superiority. Full traceability and results are in [the comparator methodology](research/e4_posthoc/model_capacity/sol_codex_agent/METHODOLOGY.md).",
        "",
    ])
    # The two post-hoc studies that read E4 belong inside this section, in dependency order,
    # and they are rendered from their own committed artifacts like everything else here.
    lines.extend(_post_hoc_sections())
    lines.extend([
        "### Robustness and data integrity",
        "",
        f"All eight SEC archives passed SHA-256, CRC, required-member and size checks. Verified endpoint coverage was {summary['outcomes']['verified_coverage']:.1%}; {summary['outcomes']['status_counts']['REQUIRES_HUMAN_REVIEW']} cases required human review and {summary['outcomes']['status_counts']['INSUFFICIENT_DATA']} had insufficient outcome data. Prediction-time diagnostics show that verification was selective, so propensity weighting is post-hoc sensitivity analysis only and does not remove selection bias. Independent SEC–Zenodo processing/source concordance matched within 5% for {summary['source_concordance']['within_5pct']:.1%} of {summary['source_concordance']['n']:,} matched values; this is not extraction accuracy. Deterministic replay was canonical byte-identical.",
        "",
        "### Research boundary",
        "",
        "E4 evaluates structured financial risk ranking, temporal structured signal, Local Agent reasoning, and a deterministic + Agent structured hybrid. It does **not** validate calibrated default probability, universal bankruptcy prediction, production or regulatory use, a full narrative/document Agent, MD&A or Risk-Factor grounding, or full FinRisk Agent external validation. All systems remain `UNCALIBRATED`.",
        "",
        "Full frozen methods and results are in [E4 Validation Report](research/e4/public/VALIDATION_REPORT.md) and [E4 Conclusion](research/e4/public/CONCLUSION.md). The post-completion limitations and sensitivity audit is in [E4 Post-completion Audit](research/e4_posthoc/AUDIT_REPORT.md).",
        "",
        "### Historical studies",
        "",
        "Earlier pilot and v0.3.1 experiments remain preserved as historical audit records, but they are retired from the current test gate and primary result surface. Current claims and release verification are based on the locked v0.3.4/E4 artifacts described above.",
        "",
    ])
    return "\n".join(lines)


def _validation_report(summary: dict[str, Any]) -> str:
    b6 = summary["e4a_results"]["B6"]
    p1, p2, p3 = summary["primary_comparisons"]
    return f"""# E4 Validation Report

## Design

E4 tested the locked FinRisk v0.3.4 commit `{summary['source_commit']}` on {summary['outcomes']['cohort_n']:,} out-of-time, company-disjoint FY2024 SEC filers. Cohort selection and all predictions were frozen before future SEC archives were mounted. The endpoint remained `deterministic_forward_outcome_rule_v1`; all scores remain `UNCALIBRATED` heuristic indices.

## Sample flow

- Eligible before sampling: {summary['cohort']['usable_before_sampling']:,}
- Frozen E4-A cohort: {summary['outcomes']['cohort_n']:,}
- VERIFIED outcomes: {summary['outcomes']['verified_n']:,}
- Events: {summary['outcomes']['events']} ({summary['outcomes']['event_prevalence']:.1%})
- REQUIRES_HUMAN_REVIEW: {summary['outcomes']['status_counts']['REQUIRES_HUMAN_REVIEW']}
- INSUFFICIENT_DATA: {summary['outcomes']['status_counts']['INSUFFICIENT_DATA']}

Performance estimates apply to the deterministically verifiable subset.

## Primary results

B6 AUROC was {b6['auroc']:.3f}, with PR-AUC {b6['pr_auc']:.3f}. P1 B6–B0 ΔAUROC was {p1['observed_delta']:+.3f} (95% CI {p1['ci_low']:+.3f} to {p1['ci_high']:+.3f}; Holm-adjusted p={p1['holm_adjusted_p']:.4f}), meeting the prespecified positive-improvement gate.

P2 H0–B0 was {p2['observed_delta']:+.3f} ({p2['ci_low']:+.3f} to {p2['ci_high']:+.3f}) and P3 H0–A2 was {p3['observed_delta']:+.3f} ({p3['ci_low']:+.3f} to {p3['ci_high']:+.3f}). Both had only {p2['events']} paired events and remain exploratory; neither improvement was established.

## Local Agent

The benchmark communicated with a locally hosted Agent through an HTTP API. No external hosted inference API was used. The frozen backend was {summary['agent']['runtime']}. There were {summary['agent']['official_failures']} permanent failures across 150 official Agent records. Successful fixed-seed stability repeats were deterministic; single-case versus batch scores differed by {summary['agent']['batch_sensitivity']['mean_absolute_difference']:.3f} on average, with {summary['agent']['batch_sensitivity']['decision_agreement']:.1%} decision agreement.

## Robustness and integrity

All SEC inputs passed hashes, CRC and archive-member checks. Feature and outcome mounts were physically separated through prediction freeze. Independent concordance included {summary['source_concordance']['n']:,} values from {summary['source_concordance']['company_count']:,} companies; {summary['source_concordance']['within_5pct']:.1%} agreed within 5%. Metric/raw-fact missingness, sector, threshold, endpoint attrition, Agent failure, stability and batch-context analyses were executed. Deterministic replay was canonical byte-identical.

## Claim boundary

E4 supports a positive paired ranking improvement for B6 over B0 on the verified E4-A subset. It does not establish an Agent or Hybrid improvement, calibrated default probability, universal bankruptcy prediction, production/regulatory fitness, narrative-document grounding, or full FinRisk Agent external validation.
"""


def _conclusion(summary: dict[str, Any]) -> str:
    p1, p2, p3 = summary["primary_comparisons"]
    return f"""# E4 Conclusion

On a 2,000-company out-of-time, company-disjoint cohort, the temporal B6 score showed a small but statistically supported paired AUROC improvement over B0 on 674 deterministically verified outcomes: {p1['observed_delta']:+.3f} (95% CI {p1['ci_low']:+.3f} to {p1['ci_high']:+.3f}). This strengthens evidence for incremental temporal structured signal, not for probability calibration or production use.

The local 0.5B Agent did not provide persuasive incremental evidence. Only five events entered the fully paired E4-B analysis, its scores were concentrated above the 0.5 threshold, five official outputs failed permanently, and batch context changed scores materially in some cases. H0 was numerically above B0 and A2, but P2 and P3 were underpowered and neither paired improvement was established ({p2['observed_delta']:+.3f} and {p3['observed_delta']:+.3f}).

The study therefore yields a mixed conclusion: B6 gains credible external ranking support, while Local Agent and Hybrid claims remain exploratory. Reliability remains `UNCALIBRATED`, and performance estimates apply only to the deterministically verifiable subset.
"""


def render(root: Path, artifacts: Path, state: Any) -> None:
    state.require(Stage.REPRODUCED)
    public = root / "research/e4/public"
    public.mkdir(parents=True, exist_ok=True)
    summary = _summary(artifacts)
    write_json(public / "readme_summary.json", summary, frozen=True)
    (public / "VALIDATION_REPORT.md").write_text(_validation_report(summary), encoding="utf-8")
    (public / "CONCLUSION.md").write_text(_conclusion(summary), encoding="utf-8")
    (public / "auroc_ci.svg").write_text(_svg_auroc(summary["paired_e4b_table"]), encoding="utf-8")
    (public / "paired_delta_auroc.svg").write_text(_svg_deltas(summary["primary_comparisons"]), encoding="utf-8")
    for source, target in (
        ("agent_stability_summary.json", "agent_stability_summary.json"),
        ("batch_sensitivity_summary.json", "batch_sensitivity_summary.json"),
        ("source_concordance.json", "source_concordance_summary.json"),
    ):
        write_json(public / target, read_json(artifacts / source), frozen=True)
    write_json(public / "reproducibility_summary.json", summary["reproducibility"], frozen=True)
    readme = root / "README.md"
    text = readme.read_text(encoding="utf-8")
    start = text.index("## Research results")
    end = text.index("## Project maturity", start)
    rendered = text[:start] + _readme_section(summary) + "\n" + text[end:]
    readme.write_text(rendered, encoding="utf-8")
    state.advance(Stage.REPRODUCED, Stage.README_RENDERED, {"summary_hash": summary["summary_hash"]})


def verify_render(root: Path, artifacts: Path, state: Any) -> dict[str, Any]:
    state.require(Stage.README_RENDERED)
    public = root / "research/e4/public"
    summary = _summary(artifacts)
    expected_text = {
        "VALIDATION_REPORT.md": _validation_report(summary),
        "CONCLUSION.md": _conclusion(summary),
        "auroc_ci.svg": _svg_auroc(summary["paired_e4b_table"]),
        "paired_delta_auroc.svg": _svg_deltas(summary["primary_comparisons"]),
    }
    matches = {
        name: (public / name).read_text(encoding="utf-8") == value
        for name, value in expected_text.items()
    }
    matches["readme_summary.json"] = read_json(public / "readme_summary.json") == summary
    readme = (root / "README.md").read_text(encoding="utf-8")
    start = readme.index("## Research results")
    end = readme.index("## Project maturity", start)
    matches["README.md"] = readme[start:end].rstrip() == _readme_section(summary).rstrip()
    evidence = {
        "byte_identical": all(matches.values()),
        "files": matches,
        "summary_hash": summary["summary_hash"],
    }
    if not evidence["byte_identical"]:
        raise RuntimeError("E4 public render replay mismatch")
    return evidence


def main() -> None:
    artifacts = ROOT / "research/e4/_artifacts"
    render(ROOT, artifacts, StudyState(artifacts))


if __name__ == "__main__":
    main()
