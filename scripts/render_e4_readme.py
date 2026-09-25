"""Render E4 public artifacts and the README from one canonical summary."""

from __future__ import annotations

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


def _fmt(value: float | None, digits: int = 3) -> str:
    return "NA" if value is None else f"{value:.{digits}f}"


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
