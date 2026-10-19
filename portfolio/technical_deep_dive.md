# Technical Deep Dive

Current scope: FinRisk v0.4.2 Security & Reliability Patch, source release 2026-10-19.
Analysis → proposal → evidence verification → AssuranceResult → authorized final →
Decision Certificate. Neither models, rules nor the Agent has final authority.

The central data invariant is that absence is not zero. Safe division emits an unavailable metric with missing inputs, and each model returns missing components or “not applicable.” Financial values carry page and source text; derived metrics retain formulas and inputs. This makes the evidence graph traversable from conclusion to rule to metric to filing.

Rules live outside control flow in versioned JSON. A generic operator evaluator makes thresholds reviewable and testable, while multi-condition rules capture interactions such as rising profit with falling CFO. Legacy weighted aggregation remains available for comparison. The live Agent uses non-compensatory hierarchical fusion to form a proposal; a severe dimension cannot be averaged away. The weights and default Assurance policy are explicitly heuristic.

Narrative candidates cannot affect results until the verifier finds their text on the cited page. The mock provider tests the contract offline; the schema-constrained OpenAI-compatible provider implements the same interface. A hosted smoke test establishes connectivity and schema conformance, not financial reliability. Contradiction detection uses verified claims and deterministic facts, and its language deliberately stops at inconsistency rather than fraud attribution.

The legacy confidence field combines data completeness, evidence-verification rate, applicable-model coverage, and time-series coverage. It is an uncalibrated evidence-quality index, not decision probability; future work should calibrate reliability on adjudicated examples and add dependency-aware rule de-correlation. Current Assurance already
rejects empty-source verified paths, deduplicates identical material paths and requires
source IDs for verified coverage. This is separate from legacy contribution-family
deduplication. Rehashed contradictory states fail semantic validation; persisted
certificates remain bound to evidence paths and tenant/entity identity.

Certificate hashes detect mutation; they do not authenticate the issuer. Prompt
injection, native-parser isolation and deployment resource limits remain residual
boundaries. E5 stays BLOCKED / DRAFT_NOT_FROZEN and external validation is not established.

