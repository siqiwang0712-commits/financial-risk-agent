# Project Summary

**Problem:** corporate filings distribute risk evidence across tables, notes, management prose, and audit language. LLM-only reading is fluent but can be numerically wrong and ungrounded.

**Hypothesis:** a hybrid system that constrains language models with deterministic arithmetic, expert rules, and quote verification will be more reliable and explainable.

**Design and implementation:** FinRisk v0.4.2 is an evidence-grounded corporate-filing financial-risk analysis and decision-assurance research system. Deterministic metrics, four traditional models, 68 versioned rule definitions (43 enabled; 25 explicitly disabled), constrained LLM interpretation and the Agent produce proposals. Assurance alone authorizes the final disposition, checking evidence, fragility, distribution and policy; a content-addressed Decision Certificate binds that state. Confidence is an uncalibrated evidence-quality index, not a probability.

**Current maturity:** v0.4.2 is the 2026-10-19 Security & Reliability Patch source release; this is not a GitHub/container-publication or external-validation claim. Historical E4 supports a limited B6-over-B0 result on 674 verified outcomes. E4-S/E4-R and the 675-row StrongTabularReference are retrospective/design-exposed development, not independent validation. Existing v0.4.2 diagnostics remain exploratory or synthetic/mock. Default Assurance is HEURISTIC_POLICY / UNCALIBRATED; E5 is BLOCKED / DRAFT_NOT_FROZEN. See the [current status](../PROJECT_STATUS.md) and [research overview](../research/EXPERIMENT_OVERVIEW.md).

**Insight:** an LLM should be treated as a fallible semantic sensor, not a financial-risk oracle. Reliability comes from assigning each subsystem the task it can auditably perform.
