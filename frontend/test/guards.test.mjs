import assert from "node:assert/strict";
import test from "node:test";

import {
  isAgentPayload,
  isAssessmentPayload,
  isDecisionPath,
  isEvidence,
  isPilotPayload,
} from "../lib/guards.mjs";

/**
 * The guards decide whether a 200 is trustworthy. A payload that fails them is
 * reported as "not in the expected shape" instead of rendering half-empty, so a
 * false negative hides a real result and a false positive crashes a tab.
 */

const evidence = {
  source: "10-K",
  document: "filing.pdf",
  page: 12,
  confidence: 0.9,
  verification_status: "VERIFIED",
};

const decisionPath = {
  reason_code: "LIQ_001",
  evidence_path_status: "VERIFIED",
  required_inputs: ["cash"],
  path: ["filing.pdf", "cash"],
  source_evidence: [evidence],
  input_provenance: { cash: [evidence] },
  coverage: 1,
  disagreement: 0,
  fusion_contribution: { method: "hierarchical_escalation", role: "escalator" },
};

const agent = {
  status: "COMPLETED",
  plan: [{ id: "1", phase: "ANALYSE", tool: "financial_metrics", purpose: "ratios" }],
  trace: [{ step_id: "s1", phase: "ANALYSE", tool: "financial_metrics", status: "ran", summary: "ok", latency_ms: 12 }],
  conclusions: [{ claim: "c", reason: "r", tool: "risk_rules", rationale: "why", confidence: 0.5, evidence: [evidence] }],
  component_telemetry: [{
    component: "rules", status: "EXECUTED",
    risk_before: 0, risk_after: 53.8,
    coverage_before: 1, coverage_after: 1,
    disagreement_before: 0, disagreement_after: 0,
    estimated_cost_usd: 0, decision_changed: false, latency_ms: 3,
  }],
  decision_trace: {
    decision_reason_codes: ["LOW_COVERAGE"],
    material_path_count: 1, verified_path_count: 1, proof_coverage: 1,
    paths: [decisionPath],
  },
  fusion: { reason_codes: ["FUSED"] },
};

const assessment = {
  company: "Contoso",
  reporting_period: "2025",
  overall_score: 58,
  risk_level: "Moderate",
  confidence: 0.7,
  evidence_coverage: 1,
  dimensions: { liquidity: { score: 35, coverage: 1, key_drivers: ["LIQ_006"] } },
  models: [],
  triggered_rules: [],
  missing_information: [],
  confidence_components: { coverage: 1, agreement: 0.8 },
  failure_state: { degraded: false, blocking_failures: [], review_failures: [] },
  agent,
};

test("a complete payload passes every guard", () => {
  assert.equal(isEvidence(evidence), true);
  assert.equal(isDecisionPath(decisionPath), true);
  assert.equal(isAgentPayload(agent), true);
  assert.equal(isAssessmentPayload(assessment), true);
});

test("`agent` is optional because a degraded run omits it", () => {
  const { agent: _omitted, ...withoutAgent } = assessment;
  assert.equal(isAssessmentPayload(withoutAgent), true);
  assert.equal(isAssessmentPayload({ ...assessment, agent: null }), true);
});

test("a payload missing any required top-level field is rejected", () => {
  for (const field of [
    "company", "reporting_period", "overall_score", "risk_level", "confidence",
    "evidence_coverage", "dimensions", "models", "triggered_rules",
    "missing_information", "confidence_components", "failure_state",
  ]) {
    const candidate = { ...assessment };
    delete candidate[field];
    assert.equal(isAssessmentPayload(candidate), false, field);
  }
});

test("wrong scalar types and non-finite numbers are rejected", () => {
  assert.equal(isAssessmentPayload(null), false);
  assert.equal(isAssessmentPayload("html error page"), false);
  assert.equal(isAssessmentPayload([]), false);
  assert.equal(isAssessmentPayload({ ...assessment, confidence: "0.7" }), false);
  assert.equal(isAssessmentPayload({ ...assessment, confidence: Number.POSITIVE_INFINITY }), false);
  assert.equal(isAssessmentPayload({ ...assessment, confidence: Number.NaN }), false);
  assert.equal(isAssessmentPayload({ ...assessment, evidence_coverage: 1.5 }), false);
  assert.equal(isAssessmentPayload({ ...assessment, evidence_coverage: -0.1 }), false);
  assert.equal(isAssessmentPayload({ ...assessment, overall_score: "58" }), false);
});

test("a null score stays valid, and a dimension without drivers is not", () => {
  assert.equal(isAssessmentPayload({ ...assessment, overall_score: null }), true);
  assert.equal(
    isAssessmentPayload({ ...assessment, dimensions: { liquidity: { score: null, coverage: 1, key_drivers: [] } } }),
    true,
  );
  assert.equal(
    isAssessmentPayload({ ...assessment, dimensions: { liquidity: { score: 1, coverage: 1, key_drivers: [7] } } }),
    false,
  );
});

test("a failed failure_state shape is rejected", () => {
  assert.equal(isAssessmentPayload({ ...assessment, failure_state: { degraded: "no" } }), false);
  assert.equal(
    isAssessmentPayload({ ...assessment, failure_state: { degraded: false, blocking_failures: [1], review_failures: [] } }),
    false,
  );
});

test("an agent payload without a usable trace is rejected", () => {
  assert.equal(isAgentPayload({ ...agent, decision_trace: undefined }), false);
  assert.equal(isAgentPayload({ ...agent, fusion: undefined }), false);
  assert.equal(
    isAgentPayload({ ...agent, trace: [{ ...agent.trace[0], latency_ms: undefined }] }),
    false,
  );
  // A skipped component legitimately reports no latency: the table shows 0 ms.
  const withoutLatency = {
    ...agent,
    component_telemetry: [{ ...agent.component_telemetry[0], latency_ms: undefined }],
  };
  assert.equal(isAgentPayload(withoutLatency), true);
});

test("a decision path without provenance or fusion metadata is rejected", () => {
  const { input_provenance: _drop, ...withoutProvenance } = decisionPath;
  assert.equal(isDecisionPath(withoutProvenance), false);
  assert.equal(isDecisionPath({ ...decisionPath, fusion_contribution: {} }), false);
  assert.equal(isDecisionPath({ ...decisionPath, source_evidence: [{ document: "x" }] }), false);
  assert.equal(isEvidence({ document: "x", page: 1, confidence: 1, verification_status: "UNVERIFIED" }), true);
  assert.equal(isEvidence({ document: "x", page: "1", confidence: 1, verification_status: "UNVERIFIED" }), false);
});

test("the pilot guard requires rows and rejects an HTML error page", () => {
  const pilot = {
    snapshot: "v0.3.0", runtime: "v0.3.2", benchmark_evidence_coverage: 0.58,
    rows: [{ entity: "ACME", decision: "PASS", score: 24, reliability: "UNCALIBRATED", filing: "acme-2024" }],
  };
  assert.equal(isPilotPayload(pilot), true);
  assert.equal(isPilotPayload({ ...pilot, rows: [{ ...pilot.rows[0], score: "24" }] }), false);
  assert.equal(isPilotPayload({ ...pilot, rows: [] }), true);
  assert.equal(isPilotPayload("<!doctype html>"), false);
  assert.equal(isPilotPayload({ ...pilot, rows: null }), false);
});
