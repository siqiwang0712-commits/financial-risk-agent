# Methodology

The unit of analysis is a company fiscal year. Reports are parsed page by page; extracted values retain document, page, source text, currency, scale, year, and confidence. Restated observations are preserved rather than silently overwritten. Deterministic formulas produce ratios and trends. Four established screening models run only when their required inputs and applicability conditions are met.

The narrative provider returns structured candidate claims. A verifier must locate the cited text on the cited page before a claim can affect scoring. The rule engine evaluates versioned JSON rules. Category scores are capped, combined with documented expert-designed heuristic weights, and reported separately from confidence. Missing evidence lowers confidence; it never becomes zero risk.

To prevent leakage, documents from the same company must not cross train/test partitions. Human annotation guidelines distinguish disclosed facts, management opinions, risk signals, and unsupported assertions. Manipulation signals must never be labelled proven fraud without independent evidence.

