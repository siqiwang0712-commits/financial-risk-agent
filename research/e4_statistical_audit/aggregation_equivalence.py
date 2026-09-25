"""Aggregation-equivalence diagnostic, measured on E4's own published Agent outputs.

`AGENT_REPRESENTATIONS.md` section 2 shows that A1 and A2 packets contain every input B0 and
B6 use, so a structured Agent could reproduce the baseline. That was established by reading
the code and by recovering B0/B6 from the A2 packet. This module asks the next question
empirically:

    on the cases E4 actually ran, does the Agent's structured judgment track the
    deterministic baselines?

Two published artifacts make this answerable without any unpublished data:

* the Codex sub-Agent comparator published all 150 structured judgments (50 cases x A0/A1/A2)
  together with the packet ``input_hash`` each was produced from;
* the replication bundle publishes B0 and B6 for all 2,000 companies.

The packet hash is a fingerprint of a company's facts, so reproducing it recovers which
replication observation each E4-B case is. For those companies the B0/B6 scores are then
identical to E4's, because the packet hash covers exactly ``current``, ``previous`` and
``metrics``.

Everything here is outcome-free except where stated: Spearman correlations between an Agent
score and a baseline need no labels, so they are reported on all matched cases. The
residual-AUROC part of the diagnostic needs labels and is NOT computable here — E4-B has 5
events — so it is explicitly deferred to E5 rather than computed and over-read.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT / "backend"))

from e4s_stats import percentile_linear

REPLICATION_DIR = HERE / "replication"
CODEX_PREDICTIONS = (
    REPO_ROOT / "research" / "e4_posthoc" / "model_capacity" / "sol_codex_agent" / "predictions.json"
)
COHORT_SIZE = 2000


# --------------------------------------------------------------------------------------
# Cohort alignment: recover which replication observation each E4-B case is
# --------------------------------------------------------------------------------------


def e4b_indices() -> list[int]:
    """E4-B's 50 indices, recomputable from the published salt alone."""
    from finrisk.e4_core import AGENT_COHORT_LIMIT, AGENT_SALT

    ranked = sorted(
        range(1, COHORT_SIZE + 1),
        key=lambda index: hashlib.sha256(f"{AGENT_SALT}E4_COMPANY_{index:06d}".encode()).hexdigest(),
    )
    return sorted(ranked[:AGENT_COHORT_LIMIT])


def _case_id_for(observation_id: str) -> str:
    """``E4_OBS_000014`` -> ``E4_COMPANY_000014`` (the spelling packet() uses)."""
    return f"E4_COMPANY_{int(observation_id.split('_')[-1]):06d}"


def align_cohorts() -> dict:
    """Map each E4-B case to a replication observation by reproducing its packet hash."""
    agent = __import__("finrisk.e4_agent", fromlist=["packet"])
    packet = agent.packet
    core = __import__("finrisk.e4_core", fromlist=["canonical_hash"])
    canonical_hash = core.canonical_hash

    codex = json.loads(CODEX_PREDICTIONS.read_text(encoding="utf-8"))
    published = {(row["observation_id"], row["model_id"].removeprefix("SOL_")): row["input_hash"] for row in codex}
    observations = json.loads(
        __import__("gzip").decompress((REPLICATION_DIR / "features.json.gz").read_bytes())
    )

    e4_ids = sorted({observation_id for observation_id, _ in published})
    e4_case_ids = [_case_id_for(observation_id) for observation_id in e4_ids]

    # packet() depends on the observation only through masked_company_id, so building each
    # packet once and swapping case_id is equivalent to rebuilding it per candidate. The
    # equivalence is asserted below rather than assumed.
    probe = observations[0]
    for representation in ("A0", "A1", "A2"):
        rebuilt = packet({**probe, "masked_company_id": e4_case_ids[0]}, representation)
        swapped = {**packet(probe, representation), "case_id": e4_case_ids[0]}
        if rebuilt != swapped:
            raise RuntimeError("case_id is not the only id-dependent field; the fast path is invalid")

    tables: dict[str, dict[str, str]] = {}
    for representation in ("A0", "A1", "A2"):
        table: dict[str, str] = {}
        for observation in observations:
            base = packet(observation, representation)
            own_id = observation["observation_id"]
            for e4_case_id in e4_case_ids:
                table[canonical_hash({**base, "case_id": e4_case_id})] = own_id
        tables[representation] = table

    mapping: dict[str, dict[str, str | None]] = {}
    for observation_id in e4_ids:
        hits = {
            representation: tables[representation].get(published[(observation_id, representation)])
            for representation in ("A0", "A1", "A2")
        }
        agreed = sorted({value for value in hits.values() if value})
        # NOTE: compute consistency before consuming the set. `set.pop()` mutates, and an
        # earlier version checked the set after popping, which reported every case as
        # inconsistent even when all three representations agreed.
        consistent = len(agreed) == 1
        mapping[observation_id] = {
            "replication_observation_id": (agreed[0] if consistent else None),
            "per_representation": hits,
            "consistent": consistent,
        }
    matched = [value["replication_observation_id"] for value in mapping.values() if value["replication_observation_id"]]
    return {
        "e4b_case_count": len(e4_ids),
        "matched": len(matched),
        "unmatched": [key for key, value in mapping.items() if not value["replication_observation_id"]],
        "consistent_across_representations": sum(1 for value in mapping.values() if value["consistent"]),
        "mapping": mapping,
    }


# --------------------------------------------------------------------------------------
# Correlation statistics (outcome-free)
# --------------------------------------------------------------------------------------


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + end - 1) / 2 + 1
        for position in order[start:end]:
            ranks[position] = rank
        start = end
    return ranks


def spearman(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    x, y = _ranks(left), _ranks(right)
    mean_x, mean_y = sum(x) / len(x), sum(y) / len(y)
    numerator = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y, strict=True))
    denominator = math.sqrt(sum((a - mean_x) ** 2 for a in x) * sum((b - mean_y) ** 2 for b in y))
    return numerator / denominator if denominator else None


def ols_r_squared(target: list[float], predictors: list[list[float]]) -> float | None:
    """R^2 of an OLS fit of ``target`` on ``predictors`` plus an intercept (normal equations)."""
    n = len(target)
    if n < len(predictors) + 2:
        return None
    columns = [[1.0] * n, *predictors]
    k = len(columns)
    # normal equations: (X'X) b = X'y, solved by Gaussian elimination
    xtx = [[sum(columns[i][r] * columns[j][r] for r in range(n)) for j in range(k)] for i in range(k)]
    xty = [sum(columns[i][r] * target[r] for r in range(n)) for i in range(k)]
    augmented = [row[:] + [xty[i]] for i, row in enumerate(xtx)]
    for col in range(k):
        pivot = max(range(col, k), key=lambda r: abs(augmented[r][col]))
        if abs(augmented[pivot][col]) < 1e-12:
            return None
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        for row in range(k):
            if row == col:
                continue
            factor = augmented[row][col] / augmented[col][col]
            for c in range(col, k + 1):
                augmented[row][c] -= factor * augmented[col][c]
    beta = [augmented[i][k] / augmented[i][i] for i in range(k)]
    mean_target = sum(target) / n
    ss_total = sum((value - mean_target) ** 2 for value in target)
    if ss_total == 0:
        return None
    ss_residual = sum(
        (target[r] - sum(beta[i] * columns[i][r] for i in range(k))) ** 2 for r in range(n)
    )
    return 1 - ss_residual / ss_total


def diagnostic(mapping: dict, codex_scores: dict[tuple[str, str], float], baselines: dict[str, dict[str, float]]) -> dict:
    """Spearman and R^2 of each Agent representation against B0 and B6, on matched cases."""
    output: dict = {}
    for representation in ("A0", "A1", "A2"):
        agent: list[float] = []
        b0: list[float] = []
        b6: list[float] = []
        for observation_id, value in mapping.items():
            replication_id = value["replication_observation_id"]
            if not replication_id:
                continue
            score = codex_scores.get((observation_id, representation))
            if score is None:
                continue
            reference = baselines.get(replication_id, {})
            if reference.get("B0") is None or reference.get("B6") is None:
                continue
            agent.append(float(score))
            b0.append(float(reference["B0"]))
            b6.append(float(reference["B6"]))
        if len(agent) < 5:
            output[representation] = {"n": len(agent), "status": "INSUFFICIENT_MATCHES"}
            continue
        deltas = [abs(a - b) for a, b in zip(agent, b6, strict=True)]
        output[representation] = {
            "n": len(agent),
            "status": "DESCRIPTIVE_ONLY",
            "spearman_agent_vs_B0": spearman(agent, b0),
            "spearman_agent_vs_B6": spearman(agent, b6),
            "r_squared_agent_on_B0_and_B6": ols_r_squared(agent, [b0, b6]),
            "share_within_0_05_of_B6": sum(1 for value in deltas if value <= 0.05) / len(deltas),
            "share_within_0_10_of_B6": sum(1 for value in deltas if value <= 0.10) / len(deltas),
            "mean_absolute_difference_vs_B6": sum(deltas) / len(deltas),
            "median_agent_score": percentile_linear(agent, 0.5),
            "median_B6": percentile_linear(b6, 0.5),
        }
    return output


def main() -> int:
    alignment = align_cohorts()
    codex = json.loads(CODEX_PREDICTIONS.read_text(encoding="utf-8"))
    codex_scores = {
        (row["observation_id"], row["model_id"].removeprefix("SOL_")): row["score"] for row in codex
    }
    predictions = json.loads((REPLICATION_DIR / "numeric_predictions.json").read_text(encoding="utf-8"))
    baselines: dict[str, dict[str, float]] = {}
    for row in predictions:
        baselines.setdefault(row["observation_id"], {})[row["model_id"]] = row["score"]

    per_representation = diagnostic(alignment["mapping"], codex_scores, baselines)

    payload = {
        "evidence_status": "POST_E4_STATISTICAL_AUDIT",
        "scope": (
            "Aggregation-equivalence diagnostic computed on E4's own published Agent outputs "
            "(the Codex sub-Agent comparator, 50 cases x A0/A1/A2) joined to the published "
            "replication cohort's B0/B6 through reproduced packet hashes."
        ),
        "labels_note": (
            "The correlations are outcome-free and are therefore reported on every matched "
            "case. The residual-AUROC part of the diagnostic in AGENT_REPRESENTATIONS.md "
            "requires labels and is NOT computed here: E4-B has 5 events, at which any AUROC "
            "difference is uninterpretable. It is deferred to E5."
        ),
        "cohort_alignment": {
            "e4b_case_count": alignment["e4b_case_count"],
            "matched": alignment["matched"],
            "unmatched": alignment["unmatched"],
            "consistent_across_representations": alignment["consistent_across_representations"],
        },
        "mapping": alignment["mapping"],
        "aggregation_equivalence": per_representation,
        "interpretation": (
            "A high Spearman against B6 with a high R^2 on (B0, B6) means the Agent's "
            "structured judgment largely re-expresses the deterministic baselines, which is "
            "what the A2 packet's contents make possible. That is a statement about "
            "aggregation, not about reasoning capability, and it must not be reported as the "
            "Agent adding information."
        ),
    }
    print(json.dumps({
        "alignment": payload["cohort_alignment"],
        "diagnostic": payload["aggregation_equivalence"],
    }, indent=1))
    (HERE / "aggregation_equivalence.json").write_text(
        json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
