# Methodology

## Agent-oriented comparison

The three-layer runtime enables a future controlled comparison among `LLM-only`, `Code-only`, `LLM+Tools`, and `Full Agent`. The Full Agent condition adds explicit planning, typed tool selection, evidence sufficiency gates, cross-checking, reflection, and abstention; it does not receive different gold labels or hidden test-set tuning. Existing five-baseline pilot results remain frozen and unchanged. New Agent comparisons must use the same company-disjoint splits, annotations and bootstrap protocol before any claim of improvement is made.

The numerical source hierarchy is now explicit: SEC Company Facts/inline XBRL is authoritative when available; PDF values are candidates used for reconciliation and PDF pages remain the source for narrative evidence. Reconciliation never averages conflicting facts. It records both values, absolute/relative differences, tolerance, selected authority and provenance.

The semantic provider is schema-constrained and versioned. It may extract a claim, category, polarity, exact quote, page and confidence; it may not calculate ratios, models or final scores. Failed schema validation or an out-of-source page triggers bounded retry. Accepted claims still pass exact/fuzzy quote verification.

The unit of analysis is a company fiscal year. Reports are parsed page by page; extracted values retain document, page, source text, currency, scale, year, and confidence. Restated observations are preserved rather than silently overwritten. Deterministic formulas produce ratios and trends. Four established screening models run only when their required inputs and applicability conditions are met.

The narrative provider returns structured candidate claims. A verifier must locate the cited text on the cited page before a claim can affect scoring. The rule engine evaluates versioned JSON rules. Category scores are capped, combined with documented expert-designed heuristic weights, and reported separately from confidence. Missing evidence lowers confidence; it never becomes zero risk.

To prevent leakage, documents from the same company must not cross train/test partitions. Human annotation guidelines distinguish disclosed facts, management opinions, risk signals, and unsupported assertions. Manipulation signals must never be labelled proven fraud without independent evidence.
