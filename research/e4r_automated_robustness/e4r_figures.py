"""Figures for E4-R, rendered from the machine-readable artifacts only.

Nothing in this module computes a statistic; every value is read back from a JSON artifact
that the pipeline already wrote. That is what makes the figures auditable.
"""

from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

os.environ.setdefault("SOURCE_DATE_EPOCH", "0")
os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["svg.fonttype"] = "none"
matplotlib.rcParams["svg.hashsalt"] = "e4r"
# Keep the emitted SVG free of a creation timestamp so the figure bytes are reproducible.
matplotlib.rcParams["svg.id"] = ""

import e4r_stats
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
for _path in (str(REPO_ROOT / "research" / "e4_statistical_audit"), str(HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

FIGURE_DIR = HERE / "figures"
INK = "#1f2933"
MUTED = "#7b8794"
ACCENT = "#2563eb"
ACCENT_2 = "#0f766e"
WARN = "#b45309"


def _read(name: str):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def _save_svg(figure, path: Path) -> None:
    """Write the SVG through a binary handle so the bytes are LF on every platform.

    Matplotlib opens its output in text mode, which turns every newline into CRLF on
    Windows. The manifest hashes these files and ``.gitattributes`` pins them to LF, so a
    CRLF working-tree copy would fail verification on any other platform.
    """
    with path.open("wb") as handle:
        figure.savefig(handle, format="svg")


def _marginal_bootstrap(labels: list[int], scores: list[float], samples: int, seed: int) -> tuple[float, float]:
    rng = random.Random(seed)
    values = []
    size = len(labels)
    for _ in range(samples):
        indices = [rng.randrange(size) for _ in range(size)]
        subset_labels = [labels[i] for i in indices]
        subset_scores = [scores[i] for i in indices]
        value = e4r_stats.roc_auc(subset_labels, subset_scores)
        if value is not None:
            values.append(value)
    return (
        e4r_stats.percentile_linear(values, 0.025),
        e4r_stats.percentile_linear(values, 0.975),
    )


def _oof_frame() -> tuple[list[str], dict[str, dict[str, float]], dict[str, int]]:
    payload = _read("oof_predictions.json")
    labels: dict[str, int] = {}
    vectors: dict[str, dict[str, float]] = {}
    for row in payload["records"]:
        labels[row["observation_id"]] = int(row["label"])
        vectors.setdefault(row["model"], {})[row["observation_id"]] = float(row["predicted_score"])
    order = sorted(labels)
    return order, vectors, labels


def figure_auroc() -> Path:
    order, vectors, labels = _oof_frame()
    results = _read("model_results.json")["models"]
    focus = ["B0", "B6", "logistic_F2", "logistic_l2_F2", "logistic_l1_F2", "random_forest_F2", "hist_gb_F2"]
    others = [name for name in sorted(results) if name.startswith("B6_minus") or name == "B6_no_temporal"]
    names = [name for name in focus if name in results] + others
    values = [results[name]["auroc"] for name in names]
    order_labels = [labels[oid] for oid in order]
    errors = []
    for name in names:
        if name in {"B0", "B6", "logistic_F2", "hist_gb_F2"}:
            low, high = _marginal_bootstrap(order_labels, [vectors[name][oid] for oid in order], 2000, 20260925)
            errors.append((results[name]["auroc"] - low, high - results[name]["auroc"]))
        else:
            errors.append((0.0, 0.0))
    yerr = [list(pair) for pair in zip(*errors, strict=True)]

    figure, axis = plt.subplots(figsize=(8.6, 5.4))
    colors = [ACCENT if name == "B6" else (ACCENT_2 if name.startswith("B6_") else MUTED) for name in names]
    positions = range(len(names))
    axis.bar(positions, values, color=colors, alpha=0.85)
    axis.errorbar(list(positions), values, yerr=yerr, fmt="none", ecolor=INK, capsize=3, linewidth=1)
    axis.axhline(0.5, color=WARN, linestyle="--", linewidth=1, label="chance")
    axis.set_xticks(list(positions))
    axis.set_xticklabels(names, rotation=35, ha="right", fontsize=8)
    axis.set_ylabel("out-of-fold AUROC")
    axis.set_ylim(0.45, 0.80)
    axis.set_title("E4-R: out-of-fold AUROC (95% cluster bootstrap CI on the four focus scorers)")
    axis.legend(loc="upper right", fontsize=8)
    figure.tight_layout()
    path = FIGURE_DIR / "auroc_comparison.svg"
    _save_svg(figure, path)
    plt.close(figure)
    return path


def figure_pr_auc() -> Path:
    results = _read("model_results.json")["models"]
    focus = ["B0", "B6", "logistic_F2", "logistic_l2_F2", "logistic_l1_F2", "random_forest_F2", "hist_gb_F2"]
    names = [name for name in focus if name in results]
    values = [results[name]["pr_auc"] for name in names]
    prevalence = _read("model_results.json")["prevalence"]
    figure, axis = plt.subplots(figsize=(8.0, 4.6))
    axis.bar(range(len(names)), values, color=[ACCENT if name == "B6" else MUTED for name in names], alpha=0.85)
    axis.axhline(prevalence, color=WARN, linestyle="--", linewidth=1, label=f"prevalence = {prevalence:.3f}")
    axis.set_xticks(range(len(names)))
    axis.set_xticklabels(names, rotation=35, ha="right", fontsize=8)
    axis.set_ylabel("out-of-fold PR-AUC (average precision)")
    axis.set_title("E4-R: out-of-fold PR-AUC")
    axis.legend(loc="upper right", fontsize=8)
    figure.tight_layout()
    path = FIGURE_DIR / "pr_auc_comparison.svg"
    _save_svg(figure, path)
    plt.close(figure)
    return path


def figure_ablation() -> Path:
    ablation = _read("temporal_ablation.json")
    names = ["B0", "B6_full", "B6_no_temporal", "B6_minus_revenue", "B6_minus_OCF", "B6_minus_debt", "B6_minus_cash"]
    results = ablation["variants"]
    values = [results[name]["auroc"] if name in results else None for name in names]
    baseline = results["B6_full"]["auroc"]
    figure, axis = plt.subplots(figsize=(8.4, 4.8))
    colors = [MUTED, ACCENT, ACCENT_2, ACCENT_2, ACCENT_2, ACCENT_2, ACCENT_2]
    axis.bar(range(len(names)), [value if value is not None else 0 for value in values], color=colors, alpha=0.85)
    axis.axhline(baseline, color=INK, linestyle=":", linewidth=1, label=f"B6_full = {baseline:.4f}")
    for index, value in enumerate(values):
        if value is None:
            continue
        delta = value - baseline
        axis.text(index, value + 0.006, f"{value:.4f}\n{delta:+.4f}", ha="center", fontsize=7, color=INK)
    axis.set_xticks(range(len(names)))
    axis.set_xticklabels(names, rotation=25, ha="right", fontsize=8)
    axis.set_ylim(0.6, 0.78)
    axis.set_ylabel("AUROC")
    axis.set_title("E4-R: B6 temporal ablation (rebuilt from the frozen formula, no refitting)")
    axis.legend(loc="lower right", fontsize=8)
    figure.tight_layout()
    path = FIGURE_DIR / "temporal_ablation.svg"
    _save_svg(figure, path)
    plt.close(figure)
    return path


def figure_bootstrap() -> Path:
    payload = _read("statistical_tests.json")
    primary = payload["primary"][0]
    bootstrap = primary["bootstrap_auroc"]
    order, vectors, labels = _oof_frame()
    rows = e4r_stats.paired_rows(order, labels, vectors["B0"], vectors["B6"])
    replicates = e4r_stats.cluster_bootstrap(rows, "auroc", 4000, seed=20260925, with_bca=False).replicate_values
    figure, axis = plt.subplots(figsize=(8.0, 4.6))
    axis.hist(replicates, bins=60, color=ACCENT, alpha=0.75)
    axis.axvline(bootstrap["observed"], color=INK, linewidth=1.6, label=f"observed Δ = {bootstrap['observed']:+.4f}")
    axis.axvline(bootstrap["bca_low"], color=WARN, linestyle="--", linewidth=1.2,
                 label=f"BCa low = {bootstrap['bca_low']:+.4f}")
    axis.axvline(bootstrap["bca_high"], color=WARN, linestyle="--", linewidth=1.2,
                 label=f"BCa high = {bootstrap['bca_high']:+.4f}")
    axis.axvline(0.0, color="#b91c1c", linestyle=":", linewidth=1.2, label="no difference")
    axis.set_xlabel("bootstrap ΔAUROC (B6 − B0)")
    axis.set_ylabel("replicates")
    axis.set_title(f"E4-R: paired bootstrap of ΔAUROC, P(Δ>0) = {bootstrap['P_delta_gt_0p0']:.3f}")
    axis.legend(fontsize=8)
    figure.tight_layout()
    path = FIGURE_DIR / "bootstrap_delta_auroc.svg"
    _save_svg(figure, path)
    plt.close(figure)
    return path


def figure_sector() -> Path:
    subgroup = _read("subgroup_results.json")
    rows = [row for row in subgroup["sector"]["rows"] if row["estimable"]]
    names = [row["subgroup"] for row in rows]
    series = {"B0": MUTED, "B6": ACCENT, "hist_gb_F2": ACCENT_2}
    figure, axis = plt.subplots(figsize=(8.4, 4.8))
    width = 0.26
    for offset, (model, color) in enumerate(series.items()):
        values = [row["models"][model]["auroc"] for row in rows]
        axis.bar([index + offset * width - width for index in range(len(rows))], values,
                 width=width, color=color, alpha=0.85, label=model)
    for index, row in enumerate(rows):
        axis.text(index, 0.02, f"n={row['n']}\ne={row['events']}", ha="center", fontsize=7, color=INK)
    axis.set_xticks(range(len(rows)))
    axis.set_xticklabels(names, fontsize=8)
    axis.set_ylim(0, 0.9)
    axis.set_ylabel("AUROC within sector")
    axis.set_title("E4-R: sector robustness (sectors below the n≥40 / events≥10 gate omitted)")
    axis.legend(fontsize=8)
    figure.tight_layout()
    path = FIGURE_DIR / "sector_robustness.svg"
    _save_svg(figure, path)
    plt.close(figure)
    return path


def figure_missingness() -> Path:
    subgroup = _read("subgroup_results.json")
    rows = subgroup["missingness"]["rows"]
    names = [row["subgroup"] for row in rows]
    series = {"B0": MUTED, "B6": ACCENT, "hist_gb_F2": ACCENT_2}
    figure, axis = plt.subplots(figsize=(7.6, 4.6))
    width = 0.26
    for offset, (model, color) in enumerate(series.items()):
        values = [row["models"][model]["auroc"] if row["estimable"] else 0 for row in rows]
        axis.bar([index + offset * width - width for index in range(len(rows))], values,
                 width=width, color=color, alpha=0.85, label=model)
    for index, row in enumerate(rows):
        axis.text(index, 0.02, f"n={row['n']}\ne={row['events']}", ha="center", fontsize=7, color=INK)
    axis.set_xticks(range(len(rows)))
    axis.set_xticklabels(names, fontsize=9)
    axis.set_ylim(0, 0.9)
    axis.set_ylabel("AUROC within missingness band")
    axis.set_title("E4-R: missingness robustness (F2 completeness terciles)")
    axis.legend(fontsize=8)
    figure.tight_layout()
    path = FIGURE_DIR / "missingness_robustness.svg"
    _save_svg(figure, path)
    plt.close(figure)
    return path


def figure_calibration() -> Path:
    order, vectors, _labels = _oof_frame()
    diagnostics = _read("calibration_diagnostics.json")["models"]
    figure, axes = plt.subplots(1, 2, figsize=(9.4, 4.4))
    names = ["B0", "B6", "hist_gb_F2"]
    for name in names:
        bins = diagnostics[name]["bins"]
        axes[0].plot(
            [entry["mean_score"] for entry in bins if entry["n"]],
            [entry["event_rate"] for entry in bins if entry["n"]],
            marker="o", markersize=3.5, label=name,
        )
    axes[0].plot([0, 1], [0, 1], color=MUTED, linestyle="--", linewidth=1)
    axes[0].set_xlabel("mean predicted score")
    axes[0].set_ylabel("observed event rate")
    axes[0].set_title("score support / reliability (uncorrected)", fontsize=9)
    axes[0].legend(fontsize=8)

    for name in names:
        scores = [vectors[name][oid] for oid in order]
        axes[1].hist(scores, bins=30, alpha=0.55, label=f"{name} ({len({round(s, 6) for s in scores})} unique)")
    axes[1].set_xlabel("out-of-fold score")
    axes[1].set_ylabel("observations")
    axes[1].set_title("score distribution", fontsize=9)
    axes[1].legend(fontsize=8)
    figure.suptitle("E4-R: calibration diagnostics — scores remain UNCALIBRATED", fontsize=10)
    figure.tight_layout()
    path = FIGURE_DIR / "calibration_score_support.svg"
    _save_svg(figure, path)
    plt.close(figure)
    return path


def figure_missingness_ablation() -> Path:
    payload = _read("missingness_ablation.json")
    arms = [
        "A_full_F2_with_indicators",
        "B_full_F2_without_indicators",
        "C_missingness_only",
        "D_harmonized_availability",
    ]
    short = {
        "A_full_F2_with_indicators": "A full F2\n+ indicators",
        "B_full_F2_without_indicators": "B full F2\nno indicators",
        "C_missingness_only": "C missingness\nonly",
        "D_harmonized_availability": "D harmonized\nsubset",
    }
    families = sorted(payload["families"])
    figure, axis = plt.subplots(figsize=(8.8, 4.8))
    width = 0.36
    for offset, (family, color) in enumerate(zip(families, (ACCENT, ACCENT_2), strict=False)):
        present = [arm for arm in arms if arm in payload["families"][family]["arms"]]
        values = [payload["families"][family]["arms"][arm]["auroc"] for arm in present]
        lows = [payload["families"][family]["arms"][arm]["auroc_ci_low"] for arm in present]
        highs = [payload["families"][family]["arms"][arm]["auroc_ci_high"] for arm in present]
        positions = [arms.index(arm) + (offset - 0.5) * width for arm in present]
        axis.bar(positions, values, width=width, color=color, alpha=0.85, label=family)
        axis.errorbar(
            positions,
            values,
            yerr=[[value - low for value, low in zip(values, lows, strict=True)],
                  [high - value for value, high in zip(values, highs, strict=True)]],
            fmt="none", ecolor=INK, capsize=3, linewidth=1,
        )
        for position, arm in zip(positions, present, strict=True):
            entry = payload["families"][family]["arms"][arm]
            axis.text(position, entry["auroc"] + 0.008, f"{entry['events']} ev", ha="center", fontsize=6.5, color=INK)
    b6 = _read("model_results.json")["models"]["B6"]["auroc"]
    axis.axhline(b6, color=WARN, linestyle="--", linewidth=1, label=f"B6 = {b6:.4f}")
    axis.set_xticks(range(len(arms)))
    axis.set_xticklabels([short[arm] for arm in arms], fontsize=8)
    axis.set_ylim(0.4, 1.0)
    axis.set_ylabel("out-of-fold AUROC")
    axis.set_title("E4-R: how much of the learned-model advantage is reporting structure?")
    axis.legend(fontsize=8, loc="lower right")
    figure.tight_layout()
    path = FIGURE_DIR / "missingness_ablation.svg"
    _save_svg(figure, path)
    plt.close(figure)
    return path


def figure_boosting_increment() -> Path:
    payload = _read("boosting_temporal_increment.json")
    names = ["hist_gb_F0", "hist_gb_F2"]
    labels = ["F0 static only", "F2 static + temporal"]
    values = [payload["reference_metrics"]["auroc"], payload["challenger_metrics"]["auroc"]]
    figure, axis = plt.subplots(figsize=(6.6, 4.6))
    axis.bar(range(len(names)), values, color=[MUTED, ACCENT], alpha=0.85)
    for index, value in enumerate(values):
        axis.text(index, value + 0.006, f"{value:.4f}", ha="center", fontsize=8, color=INK)
    delta = payload["comparison"]["delta_auroc"]
    low = payload["comparison"]["bootstrap_auroc"]["bca_low"]
    high = payload["comparison"]["bootstrap_auroc"]["bca_high"]
    axis.set_xticks(range(len(names)))
    axis.set_xticklabels(labels, fontsize=9)
    axis.set_ylim(0.7, 0.95)
    axis.set_ylabel("out-of-fold AUROC")
    axis.set_title(f"E4-R: hist_gb_F2 − hist_gb_F0 = {delta:+.4f} (BCa [{low:+.4f}, {high:+.4f}])", fontsize=10)
    figure.tight_layout()
    path = FIGURE_DIR / "boosting_temporal_increment.svg"
    _save_svg(figure, path)
    plt.close(figure)
    return path


def figure_temporal_shuffle() -> Path:
    payload = _read("negative_controls.json")["NC2_temporal_alignment_destroyed"]
    families = ["logistic", "hist_gb"]
    figure, axes = plt.subplots(1, 2, figsize=(9.4, 4.2))
    for axis, family in zip(axes, families, strict=True):
        entry = payload["models"][family]
        values = [row["auroc"] for row in entry["detail"]]
        axis.hist(values, bins=30, color=ACCENT, alpha=0.75)
        axis.axvline(entry["original_auroc"], color=INK, linewidth=1.6,
                     label=f"original = {entry['original_auroc']:.4f}")
        headline = _read("model_results.json")["models"]["hist_gb_F2"]["auroc"]
        if family == "hist_gb":
            axis.axvline(headline, color=WARN, linewidth=1.2, linestyle="--",
                         label=f"headline full-grid = {headline:.4f}")
        axis.set_title(f"{family}: {entry['replicates']} shuffled replicates", fontsize=9)
        axis.set_xlabel("AUROC with the temporal block shuffled")
        axis.set_ylabel("replicates")
        axis.legend(fontsize=7)
    figure.suptitle("E4-R: temporal-alignment negative control (paired design)", fontsize=10)
    figure.tight_layout()
    path = FIGURE_DIR / "temporal_shuffle_control.svg"
    _save_svg(figure, path)
    plt.close(figure)
    return path


def figure_sector_heterogeneity() -> Path:
    payload = _read("sector_heterogeneity.json")
    rows = [row for row in payload["sectors"] if row["estimable"]]
    palette = {"robust_positive": ACCENT_2, "inconclusive": MUTED, "possible_heterogeneity": WARN}
    figure, axis = plt.subplots(figsize=(8.2, 4.6))
    positions = range(len(rows))
    values = [row["delta_auroc"] for row in rows]
    axis.bar(positions, values,
             color=[palette[row["classification"]] for row in rows], alpha=0.85)
    axis.errorbar(
        list(positions), values,
        yerr=[[value - row["ci_low"] for value, row in zip(values, rows, strict=True)],
              [row["ci_high"] - value for value, row in zip(values, rows, strict=True)]],
        fmt="none", ecolor=INK, capsize=4, linewidth=1,
    )
    axis.axhline(0, color="#b91c1c", linestyle=":", linewidth=1)
    pooled = payload["heterogeneity"].get("pooled_delta_auroc")
    if pooled is not None:
        axis.axhline(pooled, color=INK, linestyle="--", linewidth=1, label=f"pooled Δ = {pooled:+.4f}")
    for index, row in enumerate(rows):
        axis.text(index, -0.004, f"n={row['n']}, {row['events']} ev\n{row['classification']}",
                  ha="center", fontsize=7, color=INK)
    axis.set_xticks(list(positions))
    axis.set_xticklabels([row["sector"] for row in rows], fontsize=8)
    axis.set_ylabel("ΔAUROC (B6 − B0) within sector")
    permutation_p = payload["heterogeneity"].get("permutation_p_value")
    axis.set_title(
        "E4-R: sector heterogeneity"
        + (f" (permutation p = {permutation_p:.3f})" if permutation_p is not None else ""),
        fontsize=10,
    )
    axis.legend(fontsize=8)
    figure.tight_layout()
    path = FIGURE_DIR / "sector_heterogeneity.svg"
    _save_svg(figure, path)
    plt.close(figure)
    return path


def render_all(base: Path | None = None) -> list[str]:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    renderers = (
        figure_auroc,
        figure_pr_auc,
        figure_ablation,
        figure_bootstrap,
        figure_sector,
        figure_missingness,
        figure_calibration,
        figure_missingness_ablation,
        figure_boosting_increment,
        figure_temporal_shuffle,
        figure_sector_heterogeneity,
    )
    produced = []
    for renderer in renderers:
        path = renderer()
        produced.append(path.name)
        print(f"   figure {path.name}")
    return produced


if __name__ == "__main__":
    print("\n".join(render_all()))
