# Project Summary

**Problem:** corporate filings distribute risk evidence across tables, notes, management prose, and audit language. LLM-only reading is fluent but can be numerically wrong and ungrounded.

**Hypothesis:** a hybrid system that constrains language models with deterministic arithmetic, expert rules, and quote verification will be more reliable and explainable.

**Design and implementation:** FinRisk-Agent preserves provenance, computes formulas and four traditional models in code, evaluates 68 configuration rules, verifies every accepted narrative quote against its page, detects optimistic-language conflicts, and separates risk from confidence.

**Evaluation:** E3 contains 90 SEC-derived observations covering 30 companies and three fiscal years with company-disjoint splits and a passing point-in-time gate. Numeric B0/B1/B2/B6 were executed, but the six-observation held-out test has only one positive and is underpowered. Human-gold extraction, document evidence, and LLM confirmatory validation remain incomplete; synthetic fixtures are used only for engineering tests.

**Insight:** an LLM should be treated as a fallible semantic sensor, not a financial-risk oracle. Reliability comes from assigning each subsystem the task it can auditably perform.
