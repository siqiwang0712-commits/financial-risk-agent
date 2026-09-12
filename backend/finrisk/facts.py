"""Single construction point for the fact set the rule engine evaluates.

The Agent path and the pipeline path used to assemble *different* fact sets from
the same filing. The pipeline injected `*_change`, `*_gap`, model outputs and
narrative signals; the Agent passed raw metrics only. The same input therefore
produced 10 rule signals on one path and 15 on the other, and the published
workflow trace disagreed with the decision it was describing.

Both paths now build facts here, so a rule can only ever see one definition of
the data it evaluates.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence

from .domain import Metric, ModelResult, NarrativeClaim
from .metrics import calculate_metrics, resolve_total_debt

MODEL_METRIC_NAMES: dict[str, str] = {
    "Altman Z-Score": "altman_z_score",
    "Beneish M-Score": "beneish_m_score",
    "Piotroski F-Score": "piotroski_f_score",
    "Ohlson O-Score": "ohlson_o_score",
}

# Metrics whose year-over-year *change* is a distinct rule input from the level.
CHANGE_METRICS: tuple[str, ...] = (
    "gross_margin",
    "operating_margin",
    "receivable_days",
    "inventory_days",
    "cash_conversion_cycle",
)

NARRATIVE_SIGNAL_RULES: tuple[tuple[str, Callable[[NarrativeClaim], bool]], ...] = (
    (
        "going_concern_doubt",
        lambda claim: claim.risk_category == "business_going_concern"
        and claim.polarity == "negative",
    ),
    (
        "material_weakness",
        lambda claim: "material weakness" in claim.claim.lower()
        and claim.polarity == "negative",
    ),
    (
        "refinancing_dependency",
        lambda claim: "refinancing" in claim.claim.lower()
        and claim.polarity == "negative",
    ),
)


def narrative_signals(
    accepted_claims: Iterable[NarrativeClaim],
) -> dict[str, list[NarrativeClaim]]:
    """Boolean risk signals derived from admitted (verified) narrative claims."""
    claims = list(accepted_claims)
    return {
        key: [claim for claim in claims if predicate(claim)]
        for key, predicate in NARRATIVE_SIGNAL_RULES
    }


def build_facts(
    current: dict,
    previous: dict | None,
    year: int,
    metrics: dict[str, Metric],
    models: Sequence[ModelResult],
    accepted_claims: Iterable[NarrativeClaim] = (),
) -> dict:
    """Assemble the complete fact set: raw line items, metrics, derived trends,
    model outputs and narrative booleans.

    Missing values stay `None`; nothing is coerced to zero.
    """
    facts: dict = {name: metric.value for name, metric in metrics.items()} | current

    resolved_debt, _ = resolve_total_debt(current)
    if current.get("total_debt") is None and resolved_debt is not None:
        facts["total_debt"] = resolved_debt

    if previous:
        for key in ("short_term_debt",):
            facts[f"{key}_growth"] = (
                None
                if current.get(key) is None or previous.get(key) in (None, 0)
                else (current[key] - previous[key]) / abs(previous[key])
            )
        prior_metrics = calculate_metrics(previous, year - 1)
        for key in CHANGE_METRICS:
            prior = prior_metrics.get(key)
            now = metrics.get(key)
            facts[f"{key}_change"] = (
                None
                if not prior or not now or prior.value is None or now.value is None
                else now.value - prior.value
            )
        for gap_key, base in (
            ("accounts_receivable_growth_gap", "accounts_receivable_growth"),
            ("inventory_growth_gap", "inventory_growth"),
        ):
            base_value = facts.get(base)
            revenue_growth = facts.get("revenue_growth")
            facts[gap_key] = (
                None
                if base_value is None or revenue_growth is None
                else base_value - revenue_growth
            )

    for model in models:
        facts[MODEL_METRIC_NAMES[model.name]] = model.output
    ohlson = next((model for model in models if model.name == "Ohlson O-Score"), None)
    facts["ohlson_probability"] = (
        ohlson.derived_outputs.get("probability") if ohlson is not None else None
    )

    facts.update(
        {
            key: bool(items)
            for key, items in narrative_signals(accepted_claims).items()
        }
    )
    return facts
