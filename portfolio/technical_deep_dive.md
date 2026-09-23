# Technical Deep Dive

The central data invariant is that absence is not zero. Safe division emits an unavailable metric with missing inputs, and each model returns missing components or “not applicable.” Financial values carry page and source text; derived metrics retain formulas and inputs. This makes the evidence graph traversable from conclusion to rule to metric to filing.

Rules live outside control flow in versioned JSON. A generic operator evaluator makes thresholds reviewable and testable, while multi-condition rules capture interactions such as rising profit with falling CFO. Aggregation caps each dimension before a weighted average to prevent a single cluster of correlated rules from growing without bound. The weights are explicitly heuristic.

Narrative candidates cannot affect results until the verifier finds their text on the cited page. The mock provider tests the contract offline; the schema-constrained OpenAI-compatible provider implements the same interface. A hosted smoke test establishes connectivity and schema conformance, not financial reliability. Contradiction detection uses verified claims and deterministic facts, and its language deliberately stops at inconsistency rather than fraud attribution.

The legacy confidence field combines data completeness, evidence-verification rate, applicable-model coverage, and time-series coverage. It is an uncalibrated evidence-quality index, not decision probability; future work should calibrate reliability on adjudicated examples and add dependency-aware rule de-correlation.

