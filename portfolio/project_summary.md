# Project Summary

**Problem:** corporate filings distribute risk evidence across tables, notes, management prose, and audit language. LLM-only reading is fluent but can be numerically wrong and ungrounded.

**Hypothesis:** a hybrid system that constrains language models with deterministic arithmetic, expert rules, and quote verification will be more reliable and explainable.

**Design and implementation:** FinRisk-Agent preserves provenance, computes formulas and four traditional models in code, evaluates 68 configuration rules, verifies every accepted narrative quote against its page, detects optimistic-language conflicts, and separates risk from confidence.

**Evaluation:** a company-disjoint five-baseline protocol, calibration metrics, ablations, and an error taxonomy are implemented or specified. No real-world result is invented; the current executable fixture is synthetic.

**Insight:** an LLM should be treated as a fallible semantic sensor, not a financial-risk oracle. Reliability comes from assigning each subsystem the task it can auditably perform.

