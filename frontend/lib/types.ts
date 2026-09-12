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
  reason_code: string;
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
  reason_code: string;
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
  decision_reason_codes: string[];
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
  reason_codes: string[];
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

export interface RoleReview {
  recommended_decision: string;
  analyst?: { status?: string; checked_claims?: number };
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
  final_decision: string;
  failure_state: FailureState;
  disclaimer: string;
  dimensions: Record<string, Dimension>;
  models: ModelResult[];
  triggered_rules: RuleSignal[];
  contradictions: Contradiction[];
  claim_consistency_evaluations: ClaimConsistencyEvaluation[];
  disclosure_tensions: DisclosureTension[];
  missing_information: string[];
  confidence_components: Record<string, number>;
  enterprise_fusion: FusionResult;
  agent?: AgentPayload;
}

export interface PilotRow {
  entity: string;
  decision: string;
  score: number | null;
  coverage: number;
  reliability: string;
  filing: string;
}

export interface PilotPayload {
  snapshot: string;
  runtime: string;
  annotation_status: string;
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
