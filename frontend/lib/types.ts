/**
 * Response shapes for the FinRisk API.
 *
 * These mirror `backend/finrisk/domain.py` and the Agent state. They are
 * deliberately permissive on fields the Workbench does not render, but every
 * field the UI reads is typed.
 */

export type Decision = "PASS" | "FLAG" | "REVIEW" | "ABSTAIN";
export type Severity = "critical" | "high" | "moderate" | "low" | "very_low" | "unknown";
export type VerificationStatus = "verified" | "unverified" | "located" | "rejected";

/**
 * The 8 reason codes `enterprise/integrity.DecisionReasonCode` can emit.
 *
 * Declaring the closed set is what lets `tsc` notice a code that no longer
 * exists; every `reason_code` used to be a bare `string`, so the backend could
 * (and did) publish values from a different vocabulary unnoticed.
 */
export type DecisionReasonCode =
  | "SEVERE_VERIFIED_SIGNAL"
  | "INSUFFICIENT_EVIDENCE"
  | "CLAIM_CONTEXT_INCOMPLETE"
  | "HIGH_MODEL_DISAGREEMENT"
  | "UNVALIDATED_RELIABILITY"
  | "CRITICAL_DIMENSION_ESCALATION"
  | "AGGREGATE_CRITICAL_SCORE"
  | "DUPLICATE_EVIDENCE_SUPPRESSED";

/**
 * The 6 codes `contradictions.ClaimConsistencyReasonCode` can emit.
 *
 * A *separate* vocabulary from `DecisionReasonCode`, sharing three spellings.
 * `NO_ADVERSE_CONFLICT` reports that nothing was found and could never be a
 * reason for a decision, which is precisely why the two must not be merged.
 */
export type ClaimConsistencyReasonCode =
  | "INSUFFICIENT_EVIDENCE"
  | "CLAIM_CONTEXT_INCOMPLETE"
  | "SEVERE_VERIFIED_SIGNAL"
  | "PARTIAL_NUMERIC_TENSION"
  | "CLAIM_NOT_OPTIMISTIC"
  | "NO_ADVERSE_CONFLICT";

export interface Evidence {
  source?: string | null;
  document: string;
  page: number | null;
  quote?: string | null;
  source_text?: string | null;
  confidence: number;
  /** Backend dataclass field; kept for byte-fidelity with the API response. */
  verified?: boolean;
  verification_status: VerificationStatus;
  fiscal_year?: number | null;
  period?: string | null;
  company?: string | null;
  value?: number | null;
  unit?: string | null;
}

export interface Metric {
  name: string;
  value: number | null;
  formula: string;
  inputs: Record<string, number | null>;
  fiscal_year: number;
  missing_reason: string | null;
  source_refs: Evidence[];
}

export interface ModelResult {
  name: string;
  output: number | null;
  interpretation: string;
  applicability: string;
  formula: string;
  inputs: Record<string, number | null>;
  missing_components: string[];
  derived_outputs: Record<string, number>;
}

export interface RuleSignal {
  rule_id: string;
  category: string;
  severity: string;
  score_delta: number;
  rationale: string;
  evidence: string[];
  family: string | null;
  required_inputs: string[];
  input_provenance: Record<string, Evidence[]>;
  source_refs: Evidence[];
}

export interface Contradiction {
  category: string;
  management_claim: string;
  conflicting_evidence: string[];
  interpretation: string;
  evidence: Evidence;
}

export interface ClaimConsistencyEvaluation {
  claim: string;
  risk_dimension: string;
  claim_target: string;
  required_evidence_types: string[];
  available_evidence_types: string[];
  missing_evidence_types: string[];
  supporting_evidence: string[];
  opposing_evidence: string[];
  classification: string;
  reason_code: ClaimConsistencyReasonCode;
  policy_version: string;
  policy_hash: string;
}

export interface DisclosureTension {
  claim: string;
  supporting_evidence: string[];
  opposing_evidence: string[];
  context: string;
  classification: string;
  confidence: number;
  source: Evidence;
  evidence_sufficiency: string;
  reason_code: ClaimConsistencyReasonCode;
}

export interface Dimension {
  score: number | null;
  level: string;
  trend: string;
  coverage: number;
  key_drivers: string[];
}

export interface PlanStep {
  id: string;
  phase: string;
  tool: string;
  purpose: string;
}

export interface TraceStep {
  step_id: string;
  phase: string;
  tool: string;
  status: string;
  summary: string;
  error?: string | null;
  latency_ms: number;
  evidence_ids?: string[];
}

export interface Conclusion {
  claim: string;
  reason: string;
  tool: string;
  rationale: string;
  confidence: number;
  evidence: Evidence[];
}

export interface ComponentTelemetry {
  component: string;
  status: string;
  risk_before: number | null;
  risk_after: number | null;
  delta_risk: number | null;
  coverage_before: number;
  coverage_after: number;
  delta_coverage: number;
  disagreement_before: number;
  disagreement_after: number;
  delta_disagreement: number;
  decision_changed: boolean;
  new_evidence: number;
  latency_ms: number;
  estimated_cost_usd: number;
}

export interface DecisionPath {
  reason_code: string;
  risk_domain: string;
  rule_or_model: string;
  rule_version: string;
  fusion_version: string;
  confidence: number | null;
  coverage: number;
  disagreement: number;
  evidence_path_status: string;
  source_evidence: Evidence[];
  required_inputs: string[];
  input_provenance: Record<string, Evidence[]>;
  fusion_contribution: {
    method: string;
    dimension_score: number | null;
    role: string;
  };
  path: string[];
}

export interface DecisionTrace {
  decision: string;
  decision_reason_codes: DecisionReasonCode[];
  initial_fusion_decision: string;
  failure_aware_decision: string;
  review_decision: string;
  material_path_count: number;
  verified_path_count: number;
  proof_coverage: number;
  paths: DecisionPath[];
}

export interface FusionResult {
  method: string;
  severity: string;
  score: number | null;
  decision: string;
  evidence_coverage: number;
  decision_confidence: number;
  disagreement: number;
  drivers: string[];
  rationale: string;
  evidence_quality: number;
  reliability: number | null;
  reliability_status: string;
  reason_codes: DecisionReasonCode[];
}

export interface Epistemics {
  evidence_coverage: number;
  evidence_quality: number;
  model_disagreement: number;
  reliability: number | null;
  calibration_status: string;
  probability: null;
}

export interface ReviewChallenge {
  code: string;
  severity: string;
  message: string;
}

/**
 * One Analyst judgement, mirroring `agent/review.StructuredJudgement`.
 *
 * The backend serialises the Analyst role as a *list* of these
 * (`"analyst": [asdict(item) for item in judgements]`); it was previously typed
 * as a single `{status, checked_claims}` object, so any future reader would have
 * silently received `undefined`. Note the field is `risk_domain`, not
 * `risk_category`, and that it carries no `status`/`checked_claims` - those
 * belong to the verifier.
 */
export interface AnalystJudgement {
  claim: string;
  risk_domain: string;
  strength: string;
  evidence_path_ids: string[];
  model?: string | null;
}

export interface RoleReview {
  recommended_decision: string;
  analyst?: AnalystJudgement[];
  critic: ReviewChallenge[];
  verifier: {
    status: string;
    checked_claims?: number;
    citation_errors?: string[];
    challenges?: ReviewChallenge[];
  };
}

export interface FailureState {
  decision: string;
  degraded: boolean;
  blocking_failures: string[];
  review_failures: string[];
}

export interface AnalysisSnapshotSummary {
  id: string;
  input_hash: string;
  output_hash: string;
  component_versions: Record<string, string>;
}

export interface AgentPayload {
  status: string;
  decision: Decision | string;
  risk_severity: string;
  risk_trajectory: string;
  risk_score: number | null;
  confidence: number;
  evidence_coverage: number;
  model_disagreement: number;
  epistemics: Epistemics;
  confidence_semantics: string;
  plan: PlanStep[];
  trace: TraceStep[];
  conclusions: Conclusion[];
  component_telemetry: ComponentTelemetry[];
  decision_trace: DecisionTrace;
  role_review: RoleReview;
  fusion: FusionResult;
  reflection: string[];
  warnings: string[];
  analysis_snapshot?: AnalysisSnapshotSummary;
}

/**
 * The assessment payload the Workbench renders.
 *
 * This is the shape of `POST /api/v1/assess` and of
 * `POST /api/v1/documents/analyze` (which returns the assessment with the agent
 * state attached under `agent`). It is **not** the shape of
 * `POST /api/v1/agent/assess`, which returns the raw `AgentState` with the
 * assessment nested under `assessment` — `isAssessmentPayload` would reject it,
 * so do not point `analyzeDocument` at that route without reshaping first.
 */
export interface AssessmentPayload {
  company: string;
  reporting_period: string;
  overall_score: number | null;
  legacy_weighted_score?: number | null;
  risk_level: string;
  confidence: number;
  evidence_quality: number;
  evidence_coverage: number;
  reliability_status: string;
  /** Explains that `confidence` / `evidence_quality` are not probabilities. */
  confidence_semantics?: string;
  final_decision: string;
  failure_state: FailureState;
  disclaimer: string;
  dimensions: Record<string, Dimension>;
  models: ModelResult[];
  triggered_rules: RuleSignal[];
  contradictions: Contradiction[];
  claim_consistency_evaluations: ClaimConsistencyEvaluation[];
  disclosure_tensions: DisclosureTension[];
  claim_verification_summary?: {
    extracted_claim_count: number;
    verified_claim_count: number;
    unsupported_claim_count: number;
    verified_claim_coverage: number | null;
    unsupported_claim_rate: number | null;
  };
  missing_information: string[];
  confidence_components: Record<string, number>;
  /**
   * Declared vs reachable rule coverage.
   *
   * The rule set is published as "68 versioned expert rules"; the reachable
   * subset is smaller because some conditions reference facts no extractor
   * produces. Optional so the payload stays backwards-compatible.
   */
  rule_coverage?: {
    total_rules: number;
    reachable_rules: number;
    reachable_ratio: number;
    unreachable_rule_ids: string[];
    unreachable_metrics: string[];
  };
  enterprise_fusion: FusionResult;
  agent?: AgentPayload;
}

export interface PilotRow {
  entity: string;
  decision: string;
  score: number | null;
  /**
   * Per-company proof-gate coverage. `null` when the frozen artifact has no row
   * for this filing - it is deliberately not backfilled with the dataset mean,
   * which previously made the column identical for every company.
   */
  coverage: number | null;
  reliability: string;
  filing: string;
}

export interface PilotPayload {
  snapshot: string;
  runtime: string;
  annotation_status: string;
  /** Dataset-level mean, shown once in the panel note rather than per row. */
  dataset_evidence_coverage?: number;
  rows: PilotRow[];
}

/** Where the currently displayed data came from. Surfaced in the UI. */
export type DataOrigin = "live" | "offline-sample";

export interface Loaded<T> {
  payload: T;
  origin: DataOrigin;
  note?: string;
}

export interface AnalysisState {
  origin: DataOrigin;
  note?: string;
}
