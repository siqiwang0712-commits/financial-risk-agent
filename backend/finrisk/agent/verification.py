from __future__ import annotations

from .state import MaterialConclusion

# A conclusion is supported when its evidence is either a verified document quote
# or a value produced by the deterministic rule engine (whose numeric inputs are
# themselves verified upstream). `located` (found but not yet verified) and
# `unverified` are NOT supported.
#
# `synthesis` labels deterministic evidence `derived`; requiring only `verified`
# rejected every metric-derived conclusion in a run, so the gate reported "0 of N
# conclusions supported" even when the evidence chain was intact.
PROOF_STATUSES = frozenset({"verified", "derived"})


def verify_conclusions(
    conclusions: list[MaterialConclusion],
) -> tuple[list[MaterialConclusion], list[str]]:
    accepted, warnings = [], []
    for conclusion in conclusions:
        if conclusion.evidence and all(
            item.get("verification_status") in PROOF_STATUSES
            for item in conclusion.evidence
        ):
            accepted.append(conclusion)
        else:
            warnings.append(f"Rejected unsupported conclusion: {conclusion.claim}")
    return accepted, warnings
