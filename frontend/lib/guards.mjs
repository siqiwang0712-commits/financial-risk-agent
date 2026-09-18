/**
 * Runtime shape guards for the API payloads the Workbench renders.
 *
 * These are the single point that decides whether a 200 is trustworthy: a payload
 * that fails here is reported as "not in the expected shape" rather than rendered
 * half-empty. They live in a plain `.mjs` module (matching `presentation.mjs`) so
 * `node --test` can exercise them without a TypeScript toolchain — previously the
 * only coverage was incidental, through the browser. `lib/api.ts` re-exports them
 * as type predicates, so the module boundaries and the types are unchanged.
 */

function record(value) {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function finite(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function strings(value) {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

export function isEvidence(value) {
  if (!record(value)) return false;
  return typeof value.document === "string"
    && (finite(value.page) || value.page === null)
    && finite(value.confidence)
    && typeof value.verification_status === "string";
}

export function isDecisionPath(value) {
  if (!record(value) || !record(value.fusion_contribution) || !record(value.input_provenance)) {
    return false;
  }
  return typeof value.reason_code === "string"
    && typeof value.evidence_path_status === "string"
    && finite(value.coverage) && finite(value.disagreement)
    && strings(value.required_inputs) && strings(value.path)
    && Array.isArray(value.source_evidence) && value.source_evidence.every(isEvidence)
    && Object.values(value.input_provenance).every(
      (refs) => Array.isArray(refs) && refs.every(isEvidence),
    )
    && typeof value.fusion_contribution.method === "string"
    && typeof value.fusion_contribution.role === "string";
}

export function isAgentPayload(value) {
  if (!record(value) || !record(value.decision_trace) || !record(value.fusion)) return false;
  const trace = value.decision_trace;
  return typeof value.status === "string"
    && Array.isArray(value.plan) && value.plan.every((item) => record(item)
      && typeof item.id === "string" && typeof item.phase === "string"
      && typeof item.tool === "string" && typeof item.purpose === "string")
    && Array.isArray(value.trace) && value.trace.every((item) => record(item)
      && typeof item.step_id === "string" && typeof item.phase === "string"
      && typeof item.tool === "string" && typeof item.status === "string"
      && typeof item.summary === "string" && finite(item.latency_ms))
    && Array.isArray(value.conclusions) && value.conclusions.every((item) =>
      record(item) && typeof item.claim === "string" && typeof item.reason === "string"
      && typeof item.tool === "string" && typeof item.rationale === "string"
      && finite(item.confidence) && Array.isArray(item.evidence)
      && item.evidence.every(isEvidence))
    && Array.isArray(value.component_telemetry) && value.component_telemetry.every((item) =>
      record(item) && typeof item.component === "string" && typeof item.status === "string"
      && (finite(item.risk_before) || item.risk_before === null)
      && (finite(item.risk_after) || item.risk_after === null)
      && finite(item.coverage_before) && finite(item.coverage_after)
      && finite(item.disagreement_before) && finite(item.disagreement_after)
      && finite(item.estimated_cost_usd) && typeof item.decision_changed === "boolean"
      // A component that was skipped reports no latency. The panel renders that
      // as 0 rather than dropping the whole assessment.
      && (finite(item.latency_ms) || item.latency_ms === undefined))
    && strings(trace.decision_reason_codes)
    && finite(trace.material_path_count) && finite(trace.verified_path_count)
    && finite(trace.proof_coverage)
    && Array.isArray(trace.paths) && trace.paths.every(isDecisionPath)
    && strings(value.fusion.reason_codes);
}

export function isAssessmentPayload(body) {
  if (!record(body)) return false;
  const dimensions = body.dimensions;
  const confidenceComponents = body.confidence_components;
  const failure = body.failure_state;
  return (
    typeof body.company === "string"
    && typeof body.reporting_period === "string"
    && (finite(body.overall_score) || body.overall_score === null)
    && typeof body.risk_level === "string"
    && finite(body.confidence)
    && finite(body.evidence_coverage)
    && body.evidence_coverage >= 0 && body.evidence_coverage <= 1
    && record(dimensions) && Object.values(dimensions).every((dimension) =>
      record(dimension) && (finite(dimension.score) || dimension.score === null)
      && finite(dimension.coverage) && strings(dimension.key_drivers))
    && Array.isArray(body.models)
    && Array.isArray(body.triggered_rules)
    && Array.isArray(body.missing_information)
    && record(confidenceComponents) && Object.values(confidenceComponents).every(finite)
    && record(failure) && typeof failure.degraded === "boolean"
    && strings(failure.blocking_failures) && strings(failure.review_failures)
    // `agent` is optional in `AssessmentPayload`: the deterministic endpoint and
    // any degraded run return the assessment without it. Requiring it here threw
    // away an otherwise valid 200 and showed a shape error instead of the result.
    && (body.agent == null || isAgentPayload(body.agent))
  );
}

export function isPilotPayload(body) {
  if (!record(body)) return false;
  return Array.isArray(body.rows)
    && typeof body.snapshot === "string"
    && typeof body.benchmark_evidence_coverage === "number"
    && body.rows.every((row) => record(row)
      && typeof row.entity === "string" && typeof row.decision === "string"
      && (finite(row.score) || row.score === null)
      && typeof row.reliability === "string" && typeof row.filing === "string");
}
